"""Reviewed spot market/GTC limit intents with durable, at-most-once submission."""

import json
import math
import sqlite3
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import ccxt

from sibyl.exchanges.catalog import exchange_spec
from sibyl.models import ExchangeOrderRequest
from sibyl.services.market import Market
from sibyl.services.order_discovery import OrderDiscovery
from sibyl.services.order_lifecycle import OrderLifecycle
from sibyl.services.order_reconciliation import OrderReconciliation
from sibyl.services.order_recovery import OrderRecovery
from sibyl.storage import Store
from sibyl.strategies.execution.controls import require_submissions


class ExchangeTrading:
    """Submit reviewed orders and retain uncertain outcomes without automatic retries.

    Native execution is restricted to the reviewed provider allowlist and the
    server execution flag. Demo limit orders share the explicit Demo wallet.
    Agent tools may read retained monitor/reconciliation evidence, but never expose
    submission, cancellation or tracking controls. Approved strategies use the same durable intents.
    """

    def __init__(self, market: Market, store: Store):
        self.market, self.store = market, store
        with store.db() as db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS exchange_orders ("
                "id TEXT PRIMARY KEY, request_key TEXT UNIQUE NOT NULL, payload TEXT NOT NULL)"
            )
        self.lifecycle = OrderLifecycle(self)
        self.recovery = OrderRecovery(self)
        self.reconciliation = OrderReconciliation(self)
        self.discovery = OrderDiscovery(self)

    def _enabled(self):
        if not self.market.settings.allow_live_trading:
            raise ValueError(
                "Exchange orders are disabled. Enable SIBYL_ALLOW_LIVE_TRADING on the server first."
            )

    def _connection(self, connection_id: str, *, allow_demo: bool = False):
        connection = next((item for item in self.store.connections() if item.id == connection_id), None)
        if connection is None:
            raise LookupError("Connection not found.")
        if connection.exchange == "demo" and not allow_demo:
            raise ValueError("Demo accounts use paper orders.")
        return connection

    def list_orders(self) -> list[dict]:
        """Inspect the latest 100 local intents, including previews and uncertain writes."""
        with self.store.db() as db:
            rows = db.execute(
                "SELECT payload FROM exchange_orders WHERE COALESCE(json_extract(payload,'$.origin'),'sibyl')!='imported' ORDER BY rowid DESC LIMIT 100"
            ).fetchall()
        details = [self.reconciliation.detail(json.loads(row[0])["id"]) for row in rows]
        return [{**detail["order"], "reconciliation": detail["reconciliation"]} for detail in details]

    def monitor(self, *, account_id="", exchange="", origin="", status="", limit=25, offset=0):
        """Page retained local/imported orders with filters applied before the display limit."""
        clauses, values = ["json_extract(payload,'$.status')!='preview'"], []
        for column, value in (
            ("json_extract(payload,'$.request.connection_id')", account_id),
            ("json_extract(payload,'$.exchange')", exchange),
            ("COALESCE(json_extract(payload,'$.origin'),'sibyl')", origin),
        ):
            if value:
                clauses.append(column + "=?")
                values.append(value)
        if status == "active":
            clauses.append(
                "json_extract(payload,'$.status') NOT IN ('closed','canceled','expired','rejected')"
            )
        elif status == "terminal":
            clauses.append("json_extract(payload,'$.status') IN ('closed','canceled','expired','rejected')")
        where = " AND ".join(clauses)
        with self.store.db() as db:
            db.execute("BEGIN")
            total = db.execute(f"SELECT COUNT(*) FROM exchange_orders WHERE {where}", values).fetchone()[0]
            identities = [
                row[0]
                for row in db.execute(
                    f"SELECT id FROM exchange_orders WHERE {where} ORDER BY json_extract(payload,'$.created_at') DESC,id DESC LIMIT ? OFFSET ?",
                    [*values, limit, offset],
                )
            ]
            accounts = {
                row[0]: {"id": row[0], "label": row[1], "exchange": row[2]}
                for row in db.execute(
                    "SELECT DISTINCT json_extract(payload,'$.request.connection_id'),json_extract(payload,'$.account'),json_extract(payload,'$.exchange') FROM exchange_orders WHERE json_extract(payload,'$.status')!='preview'"
                )
            }
        for connection in self.store.connections():
            if connection.active or connection.id in accounts:
                accounts[connection.id] = {
                    "id": connection.id,
                    "label": connection.label,
                    "exchange": connection.exchange,
                }
        details = [self.reconciliation.detail(identity) for identity in identities]
        return {
            "items": [{**detail["order"], "reconciliation": detail["reconciliation"]} for detail in details],
            "total": total,
            "offset": offset,
            "limit": limit,
            "has_more": offset + len(details) < total,
            "accounts": sorted(accounts.values(), key=lambda row: (row["exchange"], row["label"], row["id"])),
        }

    def refresh(self, intent_id: str) -> dict:
        """Read native status and one execution page; Demo also advances its matcher."""
        self.lifecycle.refresh(intent_id)
        detail = self.reconciliation.sync(intent_id, manual=True)
        return {**detail["order"], "reconciliation": detail["reconciliation"]}

    def recover(self, intent_id: str) -> dict:
        """Read one client-ID lookup page, then check status/fills only after identity is confirmed."""
        intent = self.recovery.check(intent_id, manual=True)
        if intent.get("exchange_order_id"):
            return self.refresh(intent_id)
        detail = self.reconciliation.detail(intent_id)
        return {**detail["order"], "reconciliation": detail["reconciliation"]}

    def preview(
        self,
        request: ExchangeOrderRequest,
        *,
        strategy_job_id=None,
        strategy_close_review_id=None,
        strategy_expiry_seconds=None,
    ) -> dict:
        """Validate exact precision, native spot limits and free funds without reserving them.

        GTC limits use their explicit price for notional checks. Market orders use
        the current side of the book. The exchange rechecks funds at submission.
        """
        if request.connection_id != "demo":
            self._enabled()
        connection = self._connection(request.connection_id, allow_demo=True)
        demo = connection.exchange == "demo"
        if demo and request.order_type != "limit":
            raise ValueError("Demo market orders use paper orders in the separate market-order form.")
        if not demo:
            self._enabled()
        if not connection.active:
            raise ValueError("Activate this exchange account in Settings before reviewing an order.")
        if not (demo or exchange_spec(connection.exchange).supports_order(request.order_type)):
            raise ValueError(
                "Manual exchange orders are not enabled for this provider. Read access is available."
            )
        with self.store.db() as db:
            previous = db.execute(
                "SELECT payload FROM exchange_orders WHERE request_key = ?", (request.idempotency_key,)
            ).fetchone()
        if previous:
            intent = json.loads(previous[0])
            if intent["request"] != request.model_dump():
                raise ValueError("This idempotency key belongs to a different exchange order.")
            if strategy_job_id is not None and (
                intent.get("strategy_job_id"),
                intent.get("strategy_close_review_id"),
            ) != (strategy_job_id, strategy_close_review_id):
                raise ValueError("This order key belongs to another strategy approval.")
            return intent
        with self.market.adapter(connection) as client:
            client.load_markets()
            if request.symbol not in client.markets:
                raise ValueError("This market is unavailable on the selected exchange.")
            market = client.market(request.symbol)
            if not market.get("spot", False) or market.get("active") is False:
                raise ValueError("Choose an active spot market.")
            precise = client.amount_to_precision(request.symbol, request.quantity)
            if Decimal(precise) <= 0 or Decimal(precise) != Decimal(str(request.quantity)):
                raise ValueError(
                    f"Quantity exceeds market precision. Use {precise} or another valid quantity."
                )
            if request.order_type == "limit":
                price = request.limit_price
                precise_price = client.price_to_precision(request.symbol, price)
                if Decimal(precise_price) <= 0 or Decimal(precise_price) != Decimal(str(price)):
                    raise ValueError(
                        f"Price exceeds market precision. Use {precise_price} or another valid price."
                    )
            else:
                ticker = client.fetch_ticker(request.symbol)
                price = ticker.get("ask" if request.side == "buy" else "bid") or ticker.get("last")
            if not price or not math.isfinite(price) or price <= 0:
                raise ValueError("No executable reference price is available.")
            notional = request.quantity * price
            if not math.isfinite(notional):
                raise ValueError("Order notional must be finite.")
            fields = [("amount", request.quantity), ("cost", notional)]
            if request.order_type == "limit":
                fields.append(("price", price))
            for field, value in fields:
                limits = (market.get("limits") or {}).get(field) or {}
                if limits.get("min") is not None and value < limits["min"]:
                    raise ValueError(f"Order is below the exchange minimum {field} of {limits['min']}.")
                if limits.get("max") is not None and value > limits["max"]:
                    raise ValueError(f"Order exceeds the exchange maximum {field}.")
            balances = client.fetch_balance().get("free", {})
            client_order_id = client.format_client_order_id(str(uuid4()))
        base, quote = request.symbol.split("/")
        buffer = 1.001 if demo else 1.01
        needed, asset = (notional * buffer, quote) if request.side == "buy" else (request.quantity, base)
        available = float(balances.get(asset) or 0)
        if not math.isfinite(available) or available < needed:
            fee_note = "0.1% paper fee" if demo else "1% price/fee buffer"
            raise ValueError(f"Insufficient available {asset}; buys require a {fee_note}.")
        now = datetime.now(UTC)
        intent = {
            "id": uuid4().hex,
            "request": request.model_dump(),
            "status": "preview",
            "account": connection.label,
            "exchange": connection.exchange,
            "sandbox": connection.sandbox,
            "mode": "paper" if demo else "exchange",
            "environment": "demo" if demo else "test" if connection.sandbox else "production",
            "price": float(price),
            "notional": float(notional),
            "fee": None,
            "confirmation": f"{request.side.upper()} {base}",
            "created_at": now.isoformat(),
            "expires_at": (now + timedelta(seconds=60)).isoformat(),
            "client_order_id": client_order_id,
            "tracking": False,
        }
        if strategy_job_id is not None:
            intent.update(
                origin="strategy",
                strategy_job_id=strategy_job_id,
                strategy_action="close" if strategy_close_review_id else "signal",
                strategy_close_review_id=strategy_close_review_id,
                strategy_expiry_seconds=strategy_expiry_seconds,
            )
        try:
            with self.store.db() as db:
                db.execute(
                    "INSERT INTO exchange_orders VALUES (?, ?, ?)",
                    (intent["id"], request.idempotency_key, json.dumps(intent, allow_nan=False)),
                )
        except sqlite3.IntegrityError:
            return self.preview(
                request,
                strategy_job_id=strategy_job_id,
                strategy_close_review_id=strategy_close_review_id,
                strategy_expiry_seconds=strategy_expiry_seconds,
            )
        return intent

    def execute(
        self,
        intent_id: str,
        confirmation: str,
        *,
        strategy_job_id: str | None = None,
        before_submit=None,
    ) -> dict:
        """Persist submitting before one native write; duplicate confirmations never resend."""
        with self.lifecycle.lock(intent_id):
            return self._execute(
                intent_id, confirmation, strategy_job_id=strategy_job_id, before_submit=before_submit
            )

    def _execute(
        self,
        intent_id: str,
        confirmation: str,
        *,
        strategy_job_id: str | None = None,
        before_submit=None,
    ) -> dict:
        with self.store.db() as db:
            db.execute("BEGIN IMMEDIATE")
            intent = self.lifecycle.read(db, intent_id)
            if intent.get("origin") == "strategy" and strategy_job_id != intent.get("strategy_job_id"):
                raise ValueError("This order belongs to a strategy approval. Use the strategy controls.")
            if intent.get("origin") == "imported":
                raise ValueError("Imported orders are read-only and cannot be submitted.")
            if confirmation != intent["confirmation"]:
                raise ValueError(f"Type {intent['confirmation']} to confirm this exchange order.")
            if intent["status"] != "preview":
                return intent
            connection = self._connection(intent["request"]["connection_id"], allow_demo=True)
            if connection.exchange != "demo":
                self._enabled()
            if not connection.active:
                raise ValueError(
                    "This account is inactive. Activate it and review the order before confirming."
                )
            if datetime.now(UTC) > datetime.fromisoformat(intent["expires_at"]):
                raise ValueError("Order preview expired. Review a fresh quote before confirming.")
            if intent.get("origin") == "strategy" and not intent.get("strategy_close_review_id"):
                require_submissions(db, intent.get("strategy_control_revision", 0))
                if not self.market.settings.allow_strategy_execution:
                    raise ValueError("Automated execution is disabled on this backend.")
                row = db.execute(
                    "SELECT payload FROM strategy_jobs WHERE id=?", (strategy_job_id,)
                ).fetchone()
                if not row or json.loads(row[0])["status"] != "running" or intent.get("strategy_abandoned"):
                    raise ValueError("This strategy is paused or its unsent order was abandoned.")
            if before_submit is not None:
                # Internal domain guard reads ownership in this same write
                # transaction, immediately before committing the native write boundary.
                before_submit(db, intent)
            intent.update(
                status="submitting", tracking=True, next_check=0, submitted_at=datetime.now(UTC).isoformat()
            )
            if strategy_job_id and intent.get("strategy_expiry_seconds") is not None:
                intent["strategy_expires_at"] = (
                    datetime.fromisoformat(intent["submitted_at"])
                    + timedelta(seconds=intent["strategy_expiry_seconds"])
                ).isoformat()
            self.lifecycle.write(db, intent)
        request = ExchangeOrderRequest(**intent["request"])
        try:
            with self.market.adapter(connection, write=True) as client:
                kwargs = {"price": request.limit_price} if request.order_type == "limit" else {}
                result = client.create_order(
                    request.symbol,
                    request.order_type,
                    request.side,
                    request.quantity,
                    params={"clientOrderId": intent["client_order_id"]},
                    **kwargs,
                )
            identity = result.get("id")
            if not isinstance(identity, str) or not identity or len(identity) > 200:
                raise ValueError("Provider did not confirm a usable native order identity.")
            intent.update(exchange_order_id=identity, status="submitted")
            with self.store.db() as db:
                self.lifecycle.write(db, intent)
            return self.lifecycle.observe(intent_id, result)
        except (ccxt.NetworkError, TimeoutError):
            intent.update(
                status="unknown",
                message="Submission outcome is unknown. Do not resubmit. "
                "Check the exchange using this client order ID before creating another order.",
            )
        except ccxt.ExchangeError:
            intent.update(
                status="rejected",
                tracking=False,
                message="The exchange rejected this order. Check account permissions and limits.",
            )
        except Exception:
            intent.update(
                status="unknown",
                message="Submission could not be confirmed. Check the exchange before placing another order.",
            )
        with self.store.db() as db:
            self.lifecycle.write(db, intent)
        return intent

"""Explicit exchange order intents with validation, expiry, and retry protection."""

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
from sibyl.storage import Store


class ExchangeTrading:
    """Send only user-confirmed market orders when the server explicitly enables it.

    An intent is persisted as submitting before calling the exchange. Ambiguous
    transport failures become unknown and are never retried automatically: check
    the exchange using the displayed client order ID before placing a new order.
    """

    def __init__(self, market: Market, store: Store):
        self.market, self.store = market, store
        with store.db() as db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS exchange_orders ("
                "id TEXT PRIMARY KEY, request_key TEXT UNIQUE NOT NULL, payload TEXT NOT NULL)"
            )

    def _enabled(self):
        if not self.market.settings.allow_live_trading:
            raise ValueError(
                "Exchange orders are disabled. Enable SIBYL_ALLOW_LIVE_TRADING on the server first."
            )

    def _connection(self, connection_id: str):
        connection = next((item for item in self.store.connections() if item.id == connection_id), None)
        if connection is None:
            raise LookupError("Connection not found.")
        if connection.exchange == "demo":
            raise ValueError(
                "Demo accounts use paper orders. They cannot enter the live exchange order flow."
            )
        return connection

    def list_orders(self) -> list[dict]:
        """Inspect intents and sanitized provider results, including uncertain submissions."""
        with self.store.db() as db:
            rows = db.execute("SELECT payload FROM exchange_orders ORDER BY rowid DESC LIMIT 100").fetchall()
        return [json.loads(row[0]) for row in rows]

    def refresh(self, intent_id: str) -> dict:
        """Read a known exchange order's latest status without submitting or retrying it.

        This read remains available when new execution is disabled. Unknown outcomes
        without an exchange order ID must be reconciled directly at the exchange.
        """
        with self.store.db() as db:
            row = db.execute("SELECT payload FROM exchange_orders WHERE id = ?", (intent_id,)).fetchone()
        if row is None:
            raise LookupError("Exchange order intent not found.")
        intent = json.loads(row[0])
        if not intent.get("exchange_order_id"):
            raise ValueError(
                "No exchange order ID is recorded. Check the exchange using the client order ID; do not resubmit an uncertain order."
            )
        connection = self._connection(intent["request"]["connection_id"])
        with self.market.adapter(connection) as client:
            result = client.fetch_order(intent["exchange_order_id"], intent["request"]["symbol"])
        intent.update(
            status=result.get("status") or intent["status"],
            filled=result.get("filled"),
            average=result.get("average"),
            refreshed_at=datetime.now(UTC).isoformat(),
            message="Status read from the exchange. Reference notional remains the original preview value.",
        )
        with self.store.db() as db:
            db.execute("UPDATE exchange_orders SET payload = ? WHERE id = ?", (json.dumps(intent), intent_id))
        return intent

    def preview(self, request: ExchangeOrderRequest) -> dict:
        """Check market support, quantity precision, limits, and available spot balance.

        Preview does not place an exchange order or claim to reserve funds. Prices
        and balances can change before confirmation; the exchange is authoritative.
        """
        self._enabled()
        connection = self._connection(request.connection_id)
        if not connection.active:
            raise ValueError("Activate this exchange account in Settings before reviewing an order.")
        if not exchange_spec(connection.exchange).market_orders:
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
            return intent
        with self.market.adapter(connection) as client:
            client.load_markets()
            if request.symbol not in client.markets:
                raise ValueError("This market is unavailable on the selected exchange.")
            market = client.market(request.symbol)
            if not market.get("spot", False) or market.get("active") is False:
                raise ValueError("Choose an active spot market.")
            precise = client.amount_to_precision(request.symbol, request.quantity)
            if Decimal(precise) != Decimal(str(request.quantity)):
                raise ValueError(
                    f"Quantity exceeds market precision. Use {precise} or another valid quantity."
                )
            ticker = client.fetch_ticker(request.symbol)
            price = ticker.get("ask" if request.side == "buy" else "bid") or ticker.get("last")
            if not price or not math.isfinite(price) or price <= 0:
                raise ValueError("No executable reference price is available.")
            notional = request.quantity * price
            for field, value in [("amount", request.quantity), ("cost", notional)]:
                limits = market.get("limits", {}).get(field, {})
                if limits.get("min") is not None and value < limits["min"]:
                    raise ValueError(f"Order is below the exchange minimum {field} of {limits['min']}.")
                if limits.get("max") is not None and value > limits["max"]:
                    raise ValueError(f"Order exceeds the exchange maximum {field}.")
            balances = client.fetch_balance().get("free", {})
        base, quote = request.symbol.split("/")
        needed, asset = (notional * 1.01, quote) if request.side == "buy" else (request.quantity, base)
        if float(balances.get(asset) or 0) < needed:
            raise ValueError(f"Insufficient available {asset}; buys require a 1% price/fee buffer.")
        now = datetime.now(UTC)
        intent = {
            "id": uuid4().hex,
            "request": request.model_dump(),
            "status": "preview",
            "account": connection.label,
            "exchange": connection.exchange,
            "sandbox": connection.sandbox,
            "price": float(price),
            "notional": float(notional),
            "fee": None,
            "confirmation": f"{request.side.upper()} {base}",
            "created_at": now.isoformat(),
            "expires_at": (now + timedelta(seconds=60)).isoformat(),
            "client_order_id": str(uuid4()),
        }
        try:
            with self.store.db() as db:
                db.execute(
                    "INSERT INTO exchange_orders VALUES (?, ?, ?)",
                    (intent["id"], request.idempotency_key, json.dumps(intent)),
                )
        except sqlite3.IntegrityError:
            # A concurrent preview with this key won the insert. Reuse its persisted intent.
            return self.preview(request)
        return intent

    def execute(self, intent_id: str, confirmation: str) -> dict:
        """Submit a reviewed intent once, returning its persisted state on duplicate calls."""
        self._enabled()
        with self.store.db() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT payload FROM exchange_orders WHERE id = ?", (intent_id,)).fetchone()
            if row is None:
                raise LookupError("Exchange order intent not found.")
            intent = json.loads(row[0])
            if confirmation != intent["confirmation"]:
                raise ValueError(f"Type {intent['confirmation']} to confirm this exchange order.")
            if intent["status"] != "preview":
                return intent
            if not db.execute(
                "SELECT 1 FROM active_accounts WHERE account_id=?", (intent["request"]["connection_id"],)
            ).fetchone():
                raise ValueError(
                    "This account is inactive. Activate it and review the order before confirming."
                )
            if datetime.now(UTC) > datetime.fromisoformat(intent["expires_at"]):
                raise ValueError("Order preview expired. Review a fresh quote before confirming.")
            intent["status"] = "submitting"
            db.execute("UPDATE exchange_orders SET payload = ? WHERE id = ?", (json.dumps(intent), intent_id))
        request = ExchangeOrderRequest(**intent["request"])
        try:
            connection = self._connection(request.connection_id)
            with self.market.adapter(connection) as client:
                result = client.create_order(
                    request.symbol,
                    "market",
                    request.side,
                    request.quantity,
                    params={"clientOrderId": intent["client_order_id"]},
                )
            intent.update(
                status=result.get("status") or "submitted",
                exchange_order_id=result.get("id"),
                filled=result.get("filled"),
                average=result.get("average"),
                message="Submitted to the exchange. Check the exchange account for final settlement.",
            )
        except (ccxt.NetworkError, TimeoutError):
            intent.update(
                status="unknown",
                message="Submission outcome is unknown. Do not resubmit. "
                "Check the exchange using this client order ID before creating another order.",
            )
        except ccxt.ExchangeError:
            intent.update(
                status="rejected",
                message="The exchange rejected this order. Check account permissions and limits.",
            )
        except Exception:
            intent.update(
                status="unknown",
                message="Submission could not be confirmed. Check the exchange before placing another order.",
            )
        with self.store.db() as db:
            db.execute("UPDATE exchange_orders SET payload = ? WHERE id = ?", (json.dumps(intent), intent_id))
        return intent

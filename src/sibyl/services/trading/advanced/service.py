"""Durable OCO groups whose child orders use the existing status/fill/recovery pipeline."""

import json
from datetime import UTC, datetime
from uuid import uuid4

import ccxt

from sibyl.exchanges.binance_advanced import ADVANCED_PROVIDERS
from sibyl.models import ExchangeOrderRequest
from sibyl.services.trading.advanced.contracts import OCORequest
from sibyl.services.trading.recovery import validate_candidate


class AdvancedOrders:
    """Commit one list attempt before writing; uncertain groups recover each saved child ID."""

    def __init__(self, trading):
        self.trading, self.store = trading, trading.store
        with self.store.db() as db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS order_groups (id TEXT PRIMARY KEY, request_key TEXT UNIQUE NOT NULL, payload TEXT NOT NULL)"
            )

    @staticmethod
    def _read(db, identity):
        row = db.execute("SELECT payload FROM order_groups WHERE id=?", (identity,)).fetchone()
        if not row:
            raise LookupError("OCO review not found.")
        return json.loads(row[0])

    @staticmethod
    def _write(db, group):
        db.execute(
            "UPDATE order_groups SET payload=? WHERE id=?", (json.dumps(group, allow_nan=False), group["id"])
        )

    def detail(self, identity):
        """Read list intent and actual retained leg states; list acknowledgment is not settlement."""
        with self.store.db() as db:
            group = self._read(db, identity)
            group["orders"] = [self.trading.lifecycle.read(db, key) for key in group["children"]]
        return group

    def preview(self, request: OCORequest):
        """Validate both alternative legs against one balance without submitting or reserving funds."""
        self.trading._enabled()
        with self.trading.lifecycle.lock("oco:" + request.idempotency_key):
            with self.store.db() as db:
                row = db.execute(
                    "SELECT id FROM order_groups WHERE request_key=?", (request.idempotency_key,)
                ).fetchone()
                if row:
                    group = self._read(db, row[0])
                    if group["request"] != request.model_dump():
                        raise ValueError("This key belongs to a different OCO request.")
                    return self.detail(group["id"])
            connection = self.trading._connection(request.connection_id)
            if connection.exchange not in ADVANCED_PROVIDERS or not connection.active:
                raise ValueError("OCO requires an active Binance or Binance Testnet account.")
            with self.trading.market.adapter(connection) as client:
                if not client.advanced_support(request.symbol)["oco"]:
                    raise ValueError("Native OCO is unavailable on this spot market.")
            identity = uuid4().hex
            common = {
                "connection_id": request.connection_id,
                "symbol": request.symbol,
                "side": request.side,
                "quantity": request.quantity,
            }
            orders = []
            try:
                for label, kind, price, trigger in (
                    ("take", "take_profit_limit", request.take_profit_price, request.take_profit_price),
                    ("stop", "stop_loss_limit", request.limit_price, request.trigger_price),
                ):
                    orders.append(
                        self.trading.preview(
                            ExchangeOrderRequest(
                                **common,
                                order_type=kind,
                                limit_price=price,
                                trigger_price=trigger,
                                idempotency_key=f"oco:{identity}:{label}",
                            ),
                            oco_group_id=identity,
                        )
                    )
            except Exception:
                with self.store.db() as db:
                    for order in orders:
                        db.execute(
                            "DELETE FROM exchange_orders WHERE id=? AND json_extract(payload,'$.status')='preview'",
                            (order["id"],),
                        )
                raise
            group = {
                "id": identity,
                "request": request.model_dump(),
                "children": [order["id"] for order in orders],
                "client_order_id": uuid4().hex,
                "status": "preview",
                "account": connection.label,
                "environment": orders[0]["environment"],
                "confirmation": f"OCO {request.symbol}",
                "expires_at": min(order["expires_at"] for order in orders),
                "created_at": orders[0]["created_at"],
            }
            with self.store.db() as db:
                db.execute(
                    "INSERT INTO order_groups VALUES(?,?,?)",
                    (identity, request.idempotency_key, json.dumps(group)),
                )
            return self.detail(identity)

    def execute(self, identity, confirmation):
        """Submit a two-leg list once; duplicate approvals return its saved evidence."""
        with self.trading.lifecycle.lock("oco:" + identity):
            with self.store.db() as db:
                db.execute("BEGIN IMMEDIATE")
                group = self._read(db, identity)
                if confirmation != group["confirmation"]:
                    raise ValueError("Type " + group["confirmation"] + " to confirm.")
                if group["status"] != "preview":
                    return self.detail(identity)
                self.trading._enabled()
                connection = self.trading._connection(group["request"]["connection_id"])
                if not connection.active or connection.exchange not in ADVANCED_PROVIDERS:
                    raise ValueError("Review an active supported account before submitting.")
                if datetime.now(UTC) > datetime.fromisoformat(group["expires_at"]):
                    raise ValueError("OCO review expired.")
                group.update(status="submitting", submitted_at=datetime.now(UTC).isoformat())
                self._write(db, group)
                for key in group["children"]:
                    order = self.trading.lifecycle.read(db, key)
                    if order["status"] != "preview":
                        raise ValueError("An OCO leg changed; review a new list.")
                    order.update(
                        status="submitting", submitted_at=group["submitted_at"], tracking=True, next_check=0
                    )
                    self.trading.lifecycle.write(db, order)
            request = OCORequest(**group["request"])
            legs = self.detail(identity)["orders"]
            try:
                with self.trading.market.adapter(connection, write=True) as client:
                    result = client.create_oco(
                        request.symbol,
                        request.side,
                        request.quantity,
                        request.take_profit_price,
                        request.trigger_price,
                        request.limit_price,
                        group["client_order_id"],
                        legs[0]["client_order_id"],
                        legs[1]["client_order_id"],
                    )
                if result.get("client_id") != group["client_order_id"] or not result.get("id"):
                    raise ValueError("Invalid native list identity.")
                reports = {row.get("clientOrderId"): row for row in result["orders"]}
                if len(reports) != 2 or set(reports) != {leg["client_order_id"] for leg in legs}:
                    raise ValueError("Incomplete native list evidence.")
                with self.store.db() as db:
                    db.execute("BEGIN IMMEDIATE")
                    for leg in legs:
                        row = reports[leg["client_order_id"]]
                        current = self.trading.lifecycle.read(db, leg["id"])
                        if current.get("exchange_order_id"):
                            validate_candidate(current, row)
                            if current["exchange_order_id"] != row["id"]:
                                raise ValueError("Native list leg conflicts with recovered identity.")
                            # A concurrent read may have newer fills/fees/status than
                            # the submission response. Attach list identity only.
                            current["oco_list_id"] = result["id"]
                            self.trading.lifecycle.write(db, current)
                        else:
                            self.trading.recovery.accept(db, current, row)
                            current.update(oco_list_id=result["id"], status="submitted")
                            self.trading.lifecycle.merge_observation(db, current, row)
                    group.update(status="submitted", exchange_list_id=result["id"])
                    self._write(db, group)
                return self.detail(identity)
            except ccxt.ExchangeError as error:
                # Timeouts and duplicate-ID errors cannot establish that a list was rejected.
                definitive = isinstance(
                    error, (ccxt.InsufficientFunds, ccxt.InvalidOrder, ccxt.AuthenticationError)
                ) and not isinstance(error, ccxt.NetworkError)
                state = "rejected" if definitive else "unknown"
            except Exception:
                state = "unknown"
            with self.store.db() as db:
                db.execute("BEGIN IMMEDIATE")
                group.update(
                    status=state,
                    message="OCO submission was not confirmed. Inspect both saved client IDs; never resubmit an uncertain list.",
                )
                self._write(db, group)
                for leg in legs:
                    current = self.trading.lifecycle.read(db, leg["id"])
                    if not current.get("exchange_order_id"):
                        current.update(status=state, tracking=state == "unknown", message=group["message"])
                        self.trading.lifecycle.write(db, current)
            return self.detail(identity)

"""Real native advanced-order lifecycle checks through the application's HTTP contracts."""

from uuid import uuid4


class AdvancedAcceptance:
    """Inspect actual Testnet outcomes; never invent partial fills, fees or outages."""

    symbol = "BTC/USDT"

    def __init__(self, client, account, report):
        self.client, self.account, self.report = client, account, report
        self.market = client.app.state.services.market

    def request(self, method, path, body=None):
        response = self.client.request(method, "/api/v1" + path, json=body)
        if response.status_code >= 400:
            raise RuntimeError(f"Acceptance HTTP {response.status_code} at {path}")
        return response.json()

    def prices(self):
        with self.market.adapter(self.account) as venue:
            last = venue.fetch_ticker(self.symbol)["last"]
            return {
                key: float(venue.price_to_precision(self.symbol, last * multiplier))
                for key, multiplier in (
                    ("low", 0.95),
                    ("lower", 0.94),
                    ("high", 1.05),
                    ("higher", 1.06),
                    ("rest", 0.9),
                    ("replace", 0.92),
                    ("cross", 1.005),
                )
            }

    def amount(self, price):
        with self.market.adapter(self.account) as venue:
            quantity = float(venue.amount_to_precision(self.symbol, 12 / price))
        if not 0 < quantity * price <= 15:
            raise ValueError("Quantity cannot fit the acceptance cap.")
        return quantity

    def order(self, kind, price, trigger=None):
        body = {
            "connection_id": self.account.id,
            "symbol": self.symbol,
            "side": "buy",
            "quantity": self.amount(price),
            "order_type": kind,
            "limit_price": price,
            "idempotency_key": uuid4().hex,
        }
        if trigger:
            body["trigger_price"] = trigger
        review = self.request("POST", "/exchange-orders/preview", body)
        self.report.update(phase=kind, latest_intent=review["id"])
        return self.confirm(review)

    def confirm(self, review):
        path = f"/exchange-orders/{review['id']}/confirm"
        result = self.request("POST", path, {"confirmation": review["confirmation"]})
        if result["status"] not in {"open", "closed"} or not result.get("exchange_order_id"):
            raise RuntimeError("Unconfirmed native order; inspect retained state before another run.")
        repeated = self.request("POST", path, {"confirmation": review["confirmation"]})
        if repeated.get("exchange_order_id") != result["exchange_order_id"]:
            raise RuntimeError("Repeated approval changed the native identity.")
        self.report.record(
            "advanced_order_confirmed",
            intent_id=result["id"],
            native_id=result["exchange_order_id"],
            status=result["status"],
            kind=result["request"]["order_type"],
        )
        return result

    def cancel(self, order):
        if order["status"] not in {"open", "pending", "submitted"}:
            raise RuntimeError("Order filled before cancellation review; inspect retained virtual holdings.")
        review = self.request("POST", f"/exchange-orders/{order['id']}/cancel/preview")
        self.request(
            "POST",
            f"/exchange-orders/{order['id']}/cancel",
            {"cancel_id": review["id"], "confirmation": review["confirmation"]},
        )
        result = self.request("POST", f"/exchange-orders/{order['id']}/refresh")
        if result["status"] not in {"canceled", "closed"}:
            raise RuntimeError("Cancellation is not terminal; no write will be retried.")
        self.report.record(
            "advanced_cancel_observed",
            intent_id=order["id"],
            status=result["status"],
            filled=result.get("filled"),
        )
        return result

    def run(self, *, lose_oco_response=False, observe_fill_race=False):
        price = self.prices()
        stop = self.order("stop_loss_limit", price["higher"], price["high"])
        self.cancel(stop)
        take = self.order("take_profit_limit", price["low"], price["low"])
        self.cancel(take)
        price = self.prices()
        body = {
            "connection_id": self.account.id,
            "symbol": self.symbol,
            "side": "buy",
            "quantity": self.amount(price["higher"]),
            "take_profit_price": price["low"],
            "trigger_price": price["high"],
            "limit_price": price["higher"],
            "idempotency_key": uuid4().hex,
        }
        review = self.request("POST", "/exchange-order-lists/preview", body)
        path = f"/exchange-order-lists/{review['id']}/confirm"
        self.report.update(phase="oco", latest_group=review["id"])
        result = self.request("POST", path, {"confirmation": review["confirmation"]})
        repeated = self.request("POST", path, {"confirmation": review["confirmation"]})
        if result["children"] != repeated["children"]:
            raise RuntimeError("Repeated OCO confirmation changed child identities.")
        if lose_oco_response:
            if result["status"] != "unknown":
                raise RuntimeError("The actual OCO response was not discarded as requested.")
            for child in result["orders"]:
                self.request("POST", f"/exchange-orders/{child['id']}/recover")
            result = self.request("GET", f"/exchange-order-lists/{review['id']}")
        if any(not leg.get("exchange_order_id") or leg["status"] != "open" for leg in result["orders"]):
            raise RuntimeError("Both native list legs were not observed open; inspect retained state.")
        self.report.record("native_oco_legs_observed", group_id=review["id"], recovered=lose_oco_response)
        self.cancel(result["orders"][0])
        for leg in result["orders"]:
            observed = self.request("POST", f"/exchange-orders/{leg['id']}/refresh")
            if observed["status"] not in {"canceled", "closed"}:
                raise RuntimeError("An OCO sibling remains unresolved.")
            self.report.record(
                "oco_leg_terminal",
                intent_id=leg["id"],
                status=observed["status"],
                filled=observed.get("filled"),
            )
        price = self.prices()
        original = self.order("limit", price["rest"])
        review = self.request(
            "POST",
            f"/exchange-orders/{original['id']}/replace/preview",
            {
                "quantity": original["request"]["quantity"],
                "limit_price": price["replace"],
                "idempotency_key": uuid4().hex,
            },
        )
        replaced = self.confirm(review)
        old = self.request("POST", f"/exchange-orders/{original['id']}/refresh")
        if old["status"] != "canceled":
            raise RuntimeError("Original cancellation is unresolved after replacement.")
        self.cancel(replaced)
        if observe_fill_race:
            price = self.prices()
            order = self.order("limit", price["cross"])
            if order["status"] == "open":
                order = self.cancel(order)
            evidence = self.request("POST", f"/exchange-orders/{order['id']}/reconcile")
            for _ in range(2):
                if evidence["reconciliation"]["status"] == "matched":
                    break
                evidence = self.request("POST", f"/exchange-orders/{order['id']}/reconcile")
            self.report.record(
                "native_fill_cancel_outcome",
                intent_id=order["id"],
                status=order["status"],
                filled=order.get("filled"),
                reconciliation=evidence["reconciliation"]["status"],
            )
        self.report.update(
            phase="complete",
            partial_fill_acceptance="Only actual recorded intermediate partial fills count; none is forced.",
            late_fee_acceptance="Not induced; deterministic correction tests are separate.",
            connectivity_acceptance="Optional OCO response loss is controlled injection, not a genuine outage.",
        )

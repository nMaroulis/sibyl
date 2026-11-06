"""Reviewed Binance Spot conditional, OCO and STOP_ON_FAILURE replacement requests.

Native endpoints are signed by the existing CCXT transport. No write retries,
local trigger simulation, margin parameters or caller-supplied URLs are used.
"""

from decimal import Decimal

import ccxt

CONDITIONAL = {"stop_loss_limit": "STOP_LOSS_LIMIT", "take_profit_limit": "TAKE_PROFIT_LIMIT"}
ADVANCED_PROVIDERS = {"binance", "binance-testnet"}


class BinanceAdvanced:
    """Provider-specific order semantics, shared by production and dedicated Testnet."""

    def advanced_support(self, symbol):
        """Read native spot instrument permissions after loading this account's actual environment."""
        if self.id not in ADVANCED_PROVIDERS:
            return {"types": [], "oco": False, "replace": False}
        self.market(symbol)
        info = self._exchange.market(symbol).get("info") or {}
        kinds = info.get("orderTypes") or []
        return {
            "types": [name for name, native in CONDITIONAL.items() if native in kinds],
            "oco": info.get("ocoAllowed") is True,
            "replace": info.get("cancelReplaceAllowed") is True,
        }

    def create_order(self, symbol, type, side, amount, params=None, *, price=None):
        """Submit a native GTC conditional limit; ordinary orders use the existing adapter."""
        if type not in CONDITIONAL:
            return super().create_order(symbol, type, side, amount, params, price=price)
        params = params or {}
        if set(params) != {"clientOrderId", "triggerPrice"} or not params["clientOrderId"]:
            raise ValueError("Conditional orders need only a client ID and trigger price.")
        with self.lock:
            self._require("createOrder", private=True)
            if type not in self.advanced_support(symbol)["types"] or side not in {"buy", "sell"}:
                raise ccxt.NotSupported("This conditional order is unavailable on the selected spot market.")
            request = self._conditional_request(
                symbol, type, side, amount, price, params["triggerPrice"], params["clientOrderId"]
            )
            return self._order(
                self._exchange.parse_order(
                    self._exchange.privatePostOrder(request), self._exchange.market(symbol)
                )
            )

    def _conditional_request(self, symbol, kind, side, amount, price, trigger, client_id):
        """Require exact precision even if this adapter is called outside the HTTP preview path."""
        for value, precise in (
            (amount, self.amount_to_precision(symbol, amount)),
            (price, self.price_to_precision(symbol, price)),
            (trigger, self.price_to_precision(symbol, trigger)),
        ):
            if Decimal(str(value)) != Decimal(precise) or Decimal(precise) <= 0:
                raise ValueError("Conditional price/quantity exceeds native precision.")
        return {
            "symbol": self._exchange.market(symbol)["id"],
            "side": side.upper(),
            "type": CONDITIONAL[kind],
            "quantity": self.amount_to_precision(symbol, amount),
            "price": self.price_to_precision(symbol, price),
            "stopPrice": self.price_to_precision(symbol, trigger),
            "timeInForce": "GTC",
            "newClientOrderId": client_id,
            "newOrderRespType": "RESULT",
        }

    def create_oco(self, symbol, side, amount, take_profit, stop, stop_limit, list_id, take_id, stop_id):
        """Submit one native two-leg list; the exchange links and reserves the two alternatives."""
        with self.lock:
            self._require("createOrder", private=True)
            support = self.advanced_support(symbol)
            if not support["oco"] or set(support["types"]) != set(CONDITIONAL) or side not in {"buy", "sell"}:
                raise ccxt.NotSupported("OCO conditional limits are unavailable on this spot market.")
            take = self._conditional_request(
                symbol, "take_profit_limit", side, amount, take_profit, take_profit, take_id
            )
            loss = self._conditional_request(
                symbol, "stop_loss_limit", side, amount, stop_limit, stop, stop_id
            )
            above, below = (take, loss) if side == "sell" else (loss, take)
            request = {
                "symbol": take["symbol"],
                "side": take["side"],
                "quantity": take["quantity"],
                "listClientOrderId": list_id,
                "newOrderRespType": "RESULT",
            }
            for prefix, leg in (("above", above), ("below", below)):
                request.update(
                    {
                        f"{prefix}Type": leg["type"],
                        f"{prefix}ClientOrderId": leg["newClientOrderId"],
                        f"{prefix}Price": leg["price"],
                        f"{prefix}StopPrice": leg["stopPrice"],
                        f"{prefix}TimeInForce": "GTC",
                    }
                )
            result = self._exchange.privatePostOrderListOco(request)
            return {
                "id": str(result["orderListId"]),
                "client_id": result["listClientOrderId"],
                "orders": [
                    self._order(self._exchange.parse_order(row, self._exchange.market(symbol)))
                    for row in result.get("orderReports", [])
                ],
            }

    def cancel_replace(self, symbol, old_id, side, amount, price, client_id):
        """Replace only a wholly unfilled order; cancellation success does not guarantee a new order."""
        with self.lock:
            self._require("createOrder", private=True)
            if not self.advanced_support(symbol)["replace"]:
                raise ccxt.NotSupported("Native cancel/replace is unavailable for this spot market.")
            request = {
                "symbol": self._exchange.market(symbol)["id"],
                "cancelOrderId": old_id,
                "cancelReplaceMode": "STOP_ON_FAILURE",
                "cancelRestrictions": "ONLY_NEW",
                "orderRateLimitExceededMode": "DO_NOTHING",
                "side": side.upper(),
                "type": "LIMIT",
                "quantity": self.amount_to_precision(symbol, amount),
                "price": self.price_to_precision(symbol, price),
                "timeInForce": "GTC",
                "newClientOrderId": client_id,
                "newOrderRespType": "RESULT",
            }
            result = self._exchange.privatePostOrderCancelReplace(request)
            market = self._exchange.market(symbol)
            return {
                "cancel_result": result.get("cancelResult"),
                "new_result": result.get("newOrderResult"),
                "canceled": self._order(self._exchange.parse_order(result["cancelResponse"], market))
                if result.get("cancelResult") == "SUCCESS"
                else None,
                "order": self._order(self._exchange.parse_order(result["newOrderResponse"], market))
                if result.get("newOrderResult") == "SUCCESS"
                else None,
            }

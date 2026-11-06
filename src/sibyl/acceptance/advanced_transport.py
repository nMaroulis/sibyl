"""Finite, Testnet-only transport admission for advanced-order acceptance."""

import threading
from decimal import Decimal
from urllib.parse import parse_qs, urlsplit

import ccxt


class AdvancedTestnetTransport:
    """Admit five capped BUY commands and cancellations of their observed native IDs only.

    An optional sixth marketable limit observes a cancellation/fill race. No
    production destination, arbitrary sell, replay or synthetic fill is admitted.
    """

    def __init__(self, fetch, report, *, lose_oco_response=False, observe_fill_race=False):
        self.fetch, self.report = fetch, report
        self.lose_oco_response, self.observe_fill_race = lose_oco_response, observe_fill_race
        self.lock, self.attempts, self.native_ids = threading.RLock(), [], set()

    def __call__(self, adapter, url, method="GET", headers=None, body=None):
        target = urlsplit(url)
        if (
            target.scheme != "https"
            or target.hostname != "testnet.binance.vision"
            or target.port not in {None, 443}
            or target.username
            or target.password
            or not target.path.startswith("/api/v3/")
        ):
            raise ValueError("Advanced acceptance refused a non-Testnet destination.")
        params = parse_qs("&".join(value for value in (target.query, body) if value))
        command = None
        if method != "GET":
            with self.lock:
                if any(len(value) != 1 for value in params.values()):
                    raise ValueError("Duplicate native fields refused.")
                if method == "DELETE" and target.path == "/api/v3/order":
                    if params.get("orderId", [None])[0] not in self.native_ids:
                        raise ValueError("Cancellation must name an acceptance-owned native order.")
                elif method == "POST" and target.path in {
                    "/api/v3/order",
                    "/api/v3/orderList/oco",
                    "/api/v3/order/cancelReplace",
                }:
                    if len(self.attempts) >= (6 if self.observe_fill_race else 5):
                        raise ValueError("Finite acceptance write budget exhausted.")
                    allowed = {
                        "symbol",
                        "side",
                        "type",
                        "timeInForce",
                        "quantity",
                        "price",
                        "stopPrice",
                        "newClientOrderId",
                        "newOrderRespType",
                        "timestamp",
                        "recvWindow",
                        "signature",
                        "listClientOrderId",
                        "aboveType",
                        "belowType",
                        "aboveClientOrderId",
                        "belowClientOrderId",
                        "abovePrice",
                        "belowPrice",
                        "aboveStopPrice",
                        "belowStopPrice",
                        "aboveTimeInForce",
                        "belowTimeInForce",
                        "cancelOrderId",
                        "cancelReplaceMode",
                        "cancelRestrictions",
                        "orderRateLimitExceededMode",
                    }
                    if (
                        set(params) - allowed
                        or params.get("symbol") != ["BTCUSDT"]
                        or params.get("side") != ["BUY"]
                    ):
                        raise ValueError("Order escaped the reviewed spot BUY scope.")
                    amount = Decimal(params["quantity"][0])
                    prices = [
                        Decimal(value[0])
                        for key, value in params.items()
                        if key
                        in {
                            "price",
                            "stopPrice",
                            "abovePrice",
                            "belowPrice",
                            "aboveStopPrice",
                            "belowStopPrice",
                        }
                    ]
                    if (
                        not prices
                        or not amount.is_finite()
                        or amount <= 0
                        or any(not value.is_finite() or value <= 0 or value * amount > 15 for value in prices)
                    ):
                        raise ValueError("Each native leg must fit the 15 virtual-USDT price cap.")
                    if target.path.endswith("cancelReplace") and (
                        params.get("cancelOrderId", [None])[0] not in self.native_ids
                        or params.get("cancelReplaceMode") != ["STOP_ON_FAILURE"]
                        or params.get("cancelRestrictions") != ["ONLY_NEW"]
                    ):
                        raise ValueError("Replacement escaped the unfilled-owned-order restriction.")
                    ids = [
                        params[key][0]
                        for key in (
                            "newClientOrderId",
                            "listClientOrderId",
                            "aboveClientOrderId",
                            "belowClientOrderId",
                        )
                        if key in params
                    ]
                    if not ids or any(
                        identity in row["client_ids"] for identity in ids for row in self.attempts
                    ):
                        raise ValueError("Acceptance cannot repeat a native submission ID.")
                    command = {"path": target.path, "client_ids": ids}
                    self.attempts.append(command)
                    self.report.record("advanced_native_write_admitted", **command)
                else:
                    raise ValueError("Advanced acceptance refused an unexpected write.")
        result = self.fetch(adapter, url, method, headers, body)
        if command is not None and isinstance(result, dict):
            rows = (
                result.get("orderReports", [])
                if target.path.endswith("/oco")
                else [result.get("newOrderResponse", {})]
                if target.path.endswith("cancelReplace")
                else [result]
            )
            with self.lock:
                self.native_ids.update(str(row["orderId"]) for row in rows if row.get("orderId") is not None)
            self.report.record(
                "advanced_native_write_returned", path=target.path, native_ids=sorted(self.native_ids)
            )
            if self.lose_oco_response and target.path.endswith("/oco"):
                self.report.record("actual_oco_response_deliberately_discarded")
                raise ccxt.RequestTimeout("Controlled loss after a real Testnet OCO response.")
        return result

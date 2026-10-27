"""A finite Testnet write gate around real CCXT HTTP, with optional response loss."""

import threading
from decimal import Decimal, InvalidOperation
from urllib.parse import parse_qs, urlsplit

import ccxt


class TestnetTransport:
    """Allow one capped BTC buy and one owned sell; reject all other native writes.

    Public Binance GETs are allowed solely for shared-risk reference prices.
    Every authenticated call is confined to Spot Testnet. The optional fault
    discards an actual successful buy response; it never invents an order or fill.
    """

    public_paths = {"/api/v3/exchangeInfo", "/api/v3/ticker/24hr", "/api/v3/ticker/price"}

    def __init__(self, fetch, report, *, lose_entry_response=False):
        self.fetch, self.report = fetch, report
        self.lose_entry_response = lose_entry_response
        self.lock = threading.RLock()
        self.attempts = []
        self.native_ids = set()
        self.sell_allowance = Decimal(0)

    def allow_sell(self, owned):
        """Bound a later separately approved exit to reconciled strategy-owned units."""
        with self.lock:
            amount = Decimal(str(owned))
            if not amount.is_finite() or amount <= 0:
                raise ValueError("No finite strategy ownership is available for an exit.")
            self.sell_allowance = amount

    def _write(self, path, method, parameters):
        if any(len(values) != 1 for values in parameters.values()):
            raise ValueError("Acceptance refused duplicate native parameters.")
        if path != "/api/v3/order":
            raise ValueError("Acceptance refused an unexpected write endpoint.")
        if method == "DELETE":
            if parameters.get("orderId", [None])[0] not in self.native_ids:
                raise ValueError("Acceptance refused cancellation of an unowned order.")
            return None
        if method != "POST":
            raise ValueError("Acceptance refused an unexpected write method.")
        allowed = {
            "symbol",
            "side",
            "type",
            "timeInForce",
            "quantity",
            "price",
            "newClientOrderId",
            "newOrderRespType",
            "timestamp",
            "recvWindow",
            "signature",
        }
        if set(parameters) - allowed:
            raise ValueError("Acceptance refused unreviewed native order parameters.")
        try:
            side = parameters["side"][0]
            amount, price = (Decimal(parameters[key][0]) for key in ("quantity", "price"))
            identity = parameters["newClientOrderId"][0]
        except (KeyError, InvalidOperation, IndexError) as error:
            raise ValueError("Acceptance refused an incomplete native order.") from error
        expected = "BUY" if not self.attempts else "SELL"
        if (
            len(self.attempts) >= 2
            or side != expected
            or parameters.get("symbol") != ["BTCUSDT"]
            or parameters.get("type") != ["LIMIT"]
            or parameters.get("timeInForce") != ["GTC"]
            or not identity
            or any(row["client_id"] == identity for row in self.attempts)
            or not amount.is_finite()
            or not price.is_finite()
            or amount <= 0
            or price <= 0
            or amount * price > 15
            or (side == "SELL" and amount > self.sell_allowance)
        ):
            raise ValueError("Acceptance refused an order outside its finite Testnet scope.")
        receipt = {"side": side, "client_id": identity, "quantity": str(amount), "limit_price": str(price)}
        self.attempts.append(receipt)  # Reserve before the HTTP call, even if its outcome is unknown.
        self.report.record("native_write_admitted", **receipt)
        return receipt

    def __call__(self, adapter, url, method="GET", headers=None, body=None):
        parsed = urlsplit(url)
        parameters = parse_qs("&".join(value for value in (parsed.query, body) if value))
        private = "signature" in parameters or any(key.lower() == "x-mbx-apikey" for key in (headers or {}))
        if parsed.scheme != "https" or parsed.port not in {None, 443} or parsed.username or parsed.password:
            raise ValueError("Acceptance refused an unexpected HTTP destination.")
        if parsed.hostname == "api.binance.com":
            if method != "GET" or parsed.path not in self.public_paths or private:
                raise ValueError("Acceptance permits only credential-free public reference reads.")
        elif parsed.hostname != "testnet.binance.vision" or not parsed.path.startswith("/api/v3/"):
            raise ValueError("Acceptance refused a non-Testnet destination.")
        with self.lock:
            receipt = self._write(parsed.path, method, parameters) if method != "GET" else None
        result = self.fetch(adapter, url, method, headers, body)
        if method == "GET" and parsed.hostname == "testnet.binance.vision" and parsed.path == "/api/v3/order":
            if isinstance(result, dict) and result.get("orderId") is not None:
                with self.lock:
                    if any(row["client_id"] == result.get("clientOrderId") for row in self.attempts):
                        self.native_ids.add(str(result["orderId"]))
        if receipt is not None:
            native_id = result.get("orderId") if isinstance(result, dict) else None
            if native_id is None:
                raise RuntimeError("Native write returned no order identity; inspect retained state.")
            with self.lock:
                self.native_ids.add(str(native_id))
            self.report.record("native_write_returned", side=receipt["side"], native_id=str(native_id))
            if self.lose_entry_response and receipt["side"] == "BUY":
                self.report.record("entry_response_deliberately_discarded", native_id=str(native_id))
                raise ccxt.RequestTimeout("Acceptance deliberately discarded the Testnet entry response.")
        return result

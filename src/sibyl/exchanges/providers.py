"""Explicit spot clients: provider differences live here, not in domain services."""

import ccxt

from sibyl.exchanges import coinex_activity
from sibyl.exchanges.base import number
from sibyl.exchanges.binance_advanced import BinanceAdvanced
from sibyl.exchanges.ccxt_client import CCXTClient
from sibyl.exchanges.mexc_activity import market_order_limits, original_market_quantity


class BinanceClient(BinanceAdvanced, CCXTClient):
    """Binance spot, including the separate testnet when explicitly selected."""

    id = "binance"
    history_kind = "binance-id"
    options = {"fetchMarkets": {"types": ["spot"]}}
    balance_params = {"type": "spot"}
    book_limits = (5, 10, 20, 50, 100)

    def stream_symbol(self, symbol: str) -> str:
        """Resolve the native public-stream identifier from this environment's spot catalog."""
        with self.lock:
            self.market(symbol)
            return self._exchange.market(symbol)["id"]


class BinanceTestnetClient(BinanceClient):
    """Dedicated Binance Spot Test Network client; production routing is impossible."""

    id = "binance-testnet"


class BinanceUSClient(BinanceClient):
    """Binance.US uses its own endpoint and credentials; no sandbox is exposed."""

    id = "binanceus"


class CoinbaseClient(CCXTClient):
    """Coinbase Advanced Trade with CDP key name and PEM signing key."""

    id = "coinbase"
    history_kind = "coinbase-cursor"
    balance_params = {"type": "spot"}

    def stream_symbol(self, symbol: str) -> str:
        """Resolve an exact production spot product before subscribing without credentials."""
        with self.lock:
            self.market(symbol)
            return self._exchange.market(symbol)["id"]

    def _submit_market_order(self, symbol: str, side: str, amount: float, client_order_id: str) -> dict:
        """Preserve the reviewed base quantity and ID in Coinbase's native IOC fields.

        CCXT's buy default uses quote cost and otherwise requires a reference price.
        The native configuration overrides that default with a base-sized IOC for
        both sides. The installed SDK currently needs native client_order_id too.
        """
        return self._exchange.create_order(
            symbol,
            "market",
            side,
            amount,
            params={
                "client_order_id": client_order_id,
                "createMarketBuyOrderRequiresPrice": False,
                "order_configuration": {
                    "market_market_ioc": {"base_size": self._exchange.amount_to_precision(symbol, amount)}
                },
            },
        )


class CoinbaseSandboxClient(CCXTClient):
    """Coinbase Exchange sandbox with key, secret and passphrase; not Advanced Trade."""

    id = "coinbase-sandbox"
    history_kind = "coinbase-exchange-cursor"


class KrakenClient(CCXTClient):
    """Kraken spot account; Kraken Futures is a separate, unsupported product."""

    id = "kraken"
    history_kind = "kraken-cursor"

    def stream_symbol(self, symbol: str) -> str:
        """Use Kraken v2's canonical BTC/DOGE names after validating the exact spot market."""
        with self.lock:
            self.market(symbol)
            return self._exchange.market(symbol)["symbol"]


class OKXClient(CCXTClient):
    """OKX trading wallet, passphrase signing, and explicit simulated-trading mode."""

    id = "okx"
    history_kind = "okx-bill"
    options = {"fetchMarkets": {"types": ["spot"]}}
    balance_params = {"type": "spot"}

    def format_client_order_id(self, identity: str) -> str:
        """OKX accepts at most 32 alphanumeric characters; persist the native ID."""
        return identity.replace("-", "")

    @staticmethod
    def _order(row: dict) -> dict:
        """Keep native cash order IDs and separate quote-size requests from executed cost."""
        order = CCXTClient._order(row)
        native = row.get("info")
        if not isinstance(native, dict) or native.get("instType") != "SPOT" or native.get("tdMode") != "cash":
            return order
        if native.get("ordId"):
            order["id"] = str(native["ordId"])
        if native.get("ordType") == "market":
            quantity_unit = native.get("tgtCcy") or (
                "quote_ccy" if native.get("side") == "buy" else "base_ccy"
            )
            if quantity_unit != "base_ccy":
                order.update(amount=None, remaining=None, cost=None)
        return order

    def _submit_market_order(self, symbol: str, side: str, amount: float, client_order_id: str) -> dict:
        """Use cash trading and base units, including market buys."""
        return self._exchange.create_order(
            symbol,
            "market",
            side,
            amount,
            params={"clientOrderId": client_order_id, "tdMode": "cash", "tgtCcy": "base_ccy"},
        )


class BybitClient(CCXTClient):
    """Bybit spot markets and unified balances, which may include shared collateral."""

    id = "bybit"
    history_kind = "bybit-execution"
    options = {
        "fetchMarkets": {"types": ["spot"]},
        "enableUnifiedAccount": True,
        "enableUnifiedMargin": False,
        "fetchOrder": {"acknowledged": True},
    }
    balance_params = {"accountType": "UNIFIED"}
    book_limits = (1, 50, 200)

    @staticmethod
    def _order(row: dict) -> dict:
        """Expose base size only when a Bybit market order reports its original sizing unit."""
        order = CCXTClient._order(row)
        native = row.get("info")
        if isinstance(native, dict):
            if native.get("orderType") == "Limit" or native.get("marketUnit") == "baseCoin":
                order["amount"] = number(native.get("qty"))
            elif native.get("orderType") == "Market":
                order.update(amount=None, remaining=None)
            if native.get("orderStatus") == "PartiallyFilledCanceled":
                order["status"] = "canceled"
        return order

    def _submit_market_order(self, symbol: str, side: str, amount: float, client_order_id: str) -> dict:
        """UTA spot buys/sells use the reviewed base quantity, never quote cost."""
        return self._exchange.create_order(
            symbol,
            "market",
            side,
            amount,
            params={"clientOrderId": client_order_id, "marketUnit": "baseCoin", "isLeverage": 0},
        )


class KuCoinClient(CCXTClient):
    """KuCoin classic spot trading wallet; main/funding and UTA imports remain separate."""

    id = "kucoin"
    history_kind = "kucoin-hf"
    options = {"fetchMarkets": {"types": ["spot"]}, "uta": False}
    balance_params = {"type": "trade"}
    book_limits = (20, 100)

    @staticmethod
    def _order(row: dict) -> dict:
        """Honor Classic's sizing units when a market order was placed in quote funds."""
        order = CCXTClient._order(row)
        native = row.get("info")
        if isinstance(native, dict) and native.get("type") == "market":
            if (number(native.get("size")) or 0) <= 0:
                order.update(amount=None, remaining=None)
        return order


class GateClient(CCXTClient):
    """Gate spot wallet with optional sandbox credentials."""

    id = "gate"
    history_kind = "gate-cash"
    order_fill_kind = "gate-order"
    options = {"fetchMarkets": {"types": ["spot"]}, "unifiedAccount": False}
    balance_params = {"type": "spot"}

    def format_client_order_id(self, identity: str) -> str:
        """Persist the complete native Gate text ID, including its t- prefix."""
        return "t-" + identity.replace("-", "")[:26]

    @staticmethod
    def _order(row: dict) -> dict:
        """Keep native executed amounts and avoid deriving a base request from a quote budget."""
        order = CCXTClient._order(row)
        native = row.get("info")
        if isinstance(native, dict) and native.get("account") == "spot":
            if (filled := number(native.get("filled_amount"))) is not None:
                order["filled"] = filled
            if native.get("type") == "market" and native.get("side") == "buy":
                order.update(
                    amount=None,
                    remaining=None,
                    filled=filled,
                    cost=number(native.get("filled_total")),
                )
        return order


class BitgetClient(CCXTClient):
    """Bitget classic spot assets and passphrase authentication."""

    id = "bitget"
    history_kind = "bitget-id"
    options = {"uta": False}
    balance_params = {"type": "spot"}

    def format_client_order_id(self, identity: str) -> str:
        """Use a stable compact classic-account clientOid."""
        return identity.replace("-", "")

    @staticmethod
    def _order(row: dict) -> dict:
        """Show reported base/quote fills and leave original market sizing units unknown."""
        order = CCXTClient._order(row)
        native = row.get("info")
        if isinstance(native, dict):
            if native.get("orderType") == "market":
                order.update(amount=None, remaining=None)
            elif native.get("orderType") == "limit" and native.get("price") not in (None, ""):
                order["price"] = number(native["price"])
        return order

    def _submit_limit_order(self, symbol, side, amount, price, client_order_id):
        """Classic v2 requires lowercase native force; avoid SDK unified-field leakage."""
        return self._exchange.create_order(
            symbol, "limit", side, amount, price, params={"clientOid": client_order_id, "force": "gtc"}
        )


class MEXCClient(CCXTClient):
    """MEXC spot account, excluding contract markets."""

    id = "mexc"
    history_kind = "mexc-window"
    balance_params = {"type": "spot"}
    book_limits = (5, 10, 20, 50, 100)

    def format_client_order_id(self, identity: str) -> str:
        """MEXC client IDs fit its 32-character native limit."""
        return identity.replace("-", "")

    def market_order_limits(self, symbol: str, side: str, amount: float) -> dict:
        """Check fresh, exact-pair permissions and return the market-specific preview limits."""
        with self.lock:
            self.market(symbol)
            return market_order_limits(self._exchange, symbol, side, amount)

    def _submit_market_order(self, symbol, side, amount, client_order_id):
        """Recheck pair rules and send native base quantity with the stored client ID."""
        try:
            self.market_order_limits(symbol, side, amount)
        except (ValueError, ccxt.NetworkError) as error:
            # The preflight failed before the native order endpoint was called.
            raise ccxt.InvalidOrder("MEXC market order rules could not be satisfied.") from error
        return super()._submit_market_order(symbol, side, amount, client_order_id)

    @staticmethod
    def _order(row: dict) -> dict:
        """Retain native amount and quote cost across the MEXC spot response variants."""
        order = CCXTClient._order(row)
        native = row.get("info")
        if isinstance(native, dict):
            if "cumulativeQuoteQty" in native:
                cost = number(native["cumulativeQuoteQty"])
                order["cost"] = cost if cost is not None and cost >= 0 else None
                order["average"] = cost / order["filled"] if cost and cost > 0 and order["filled"] else None
            if native.get("type") == "MARKET":
                amount = original_market_quantity(native)
                filled = number(native.get("executedQty"))
                remaining = (
                    amount - filled
                    if amount is not None and filled is not None and 0 <= filled <= amount
                    else None
                )
                order.update(amount=amount, remaining=remaining, filled=filled)
            elif order["amount"] is None and (amount := number(native.get("Qty"))) is not None:
                order["amount"] = amount
                if order["filled"] is not None and amount >= order["filled"]:
                    order["remaining"] = amount - order["filled"]
        return order


class HTXClient(CCXTClient):
    """HTX spot account, excluding margin and swaps."""

    id = "htx"
    history_kind = "htx-cash"
    order_fill_kind = "htx-order"
    balance_params = {"type": "spot"}
    book_limits = (5, 10, 20)

    def _spot_account(self) -> str:
        """Require one actual spot wallet; never fall back to the first margin account."""
        from sibyl.exchanges.htx_orders import spot_account

        return spot_account(self._exchange)

    def balance_parameters(self) -> dict:
        """Bind balance reads to the same exact spot account used by submissions."""
        return {"type": "spot", "account-id": self._spot_account()}

    def _submit_limit_order(self, symbol, side, amount, price, client_order_id):
        """Use the verified spot account ID and native spot-api source only."""
        return self._exchange.create_order(
            symbol,
            "limit",
            side,
            amount,
            price,
            params={
                "account-id": self._spot_account(),
                "clientOrderId": client_order_id,
                "timeInForce": "GTC",
                "source": "spot-api",
            },
        )

    @staticmethod
    def _order(row: dict) -> dict:
        """Keep HTX market-buy quote budgets separate from requested base quantities."""
        order = CCXTClient._order(row)
        native = row.get("info")
        if isinstance(native, dict):
            raw_type = native.get("type", "")
            if raw_type == "buy-market":
                order.update(amount=None, remaining=None)
            elif raw_type == "sell-market":
                order["amount"] = number(native.get("amount"))
                if order["amount"] is not None and order["filled"] is not None:
                    order["remaining"] = max(0, order["amount"] - order["filled"])
            instruction = raw_type.partition("-")[2]
            if instruction in {"limit", "ioc", "limit-maker", "limit-fok"}:
                order.update(
                    type="limit",
                    timeInForce={"limit": "GTC", "ioc": "IOC", "limit-maker": "PO", "limit-fok": "FOK"}[
                        instruction
                    ],
                )
        return order


class CryptoComClient(CCXTClient):
    """Crypto.com Exchange account, separate from the retail mobile app."""

    id = "cryptocom"
    history_kind = "cryptocom-cash"
    book_limits = (10, 50)

    @staticmethod
    def _order(row: dict) -> dict:
        """Retain actual cumulative amounts; quote budgets never stand in for base units."""
        order = CCXTClient._order(row)
        native = row.get("info")
        if isinstance(native, dict) and native.get("instrument_name"):
            from sibyl.exchanges.cryptocom_orders import OPEN, stamp

            order.update(
                filled=number(native.get("cumulative_quantity")),
                cost=number(native.get("cumulative_value")),
            )
            if native.get("create_time") is not None:
                order["timestamp"] = stamp(native) // 1000000
            if native.get("status") in OPEN:
                order["status"] = "open"
            if native.get("order_type") == "MARKET" and native.get("side") == "BUY":
                if (number(native.get("quantity")) or 0) <= 0:
                    order.update(amount=None, remaining=None)
        return order

    def _submit_market_order(self, symbol, side, amount, client_order_id):
        """Submit a base-sized cash IOC market order; never replace quantity with notional."""
        return self._exchange.create_order(
            symbol,
            "market",
            side,
            amount,
            params={"client_oid": client_order_id, "timeInForce": "IOC", "spot_margin": "SPOT"},
        )

    def _submit_limit_order(self, symbol, side, amount, price, client_order_id):
        """The installed SDK omits unified clientOrderId; send native client_oid."""
        return self._exchange.create_order(
            symbol,
            "limit",
            side,
            amount,
            price,
            params={"client_oid": client_order_id, "timeInForce": "GTC", "spot_margin": "SPOT"},
        )


class BitstampClient(CCXTClient):
    """Bitstamp spot account with key/secret authentication."""

    id = "bitstamp"
    history_kind = "bitstamp-transactions"


class GeminiClient(CCXTClient):
    """Gemini spot and sandbox reads; native market orders are not supported here."""

    id = "gemini"
    history_kind = "gemini-trades"


class BitfinexClient(CCXTClient):
    """Bitfinex exchange wallet, excluding margin and funding balances."""

    id = "bitfinex"
    history_kind = "bitfinex-window"
    balance_params = {"type": "exchange"}
    book_limits = (1, 25, 100)

    def format_client_order_id(self, identity: str) -> str:
        """Bitfinex cid is a positive int45; admission rejects any local collision."""
        return str(int(identity.replace("-", "")[:11], 16) + 1)

    def _submit_market_order(self, symbol, side, amount, client_order_id):
        """Keep the native cash EXCHANGE MARKET type, signed base amount and int45 cid."""
        cid = int(client_order_id)
        if not 0 < cid < 2**45:
            raise ValueError("Bitfinex client order ID must be a positive int45.")
        return self._exchange.create_order(symbol, "market", side, amount, params={"cid": cid})

    def _submit_limit_order(self, symbol, side, amount, price, client_order_id):
        """Use integer cid and a native non-margin EXCHANGE LIMIT."""
        cid = int(client_order_id)
        if not 0 < cid < 2**45:
            raise ValueError("Bitfinex client order ID must be a positive int45.")
        return self._exchange.create_order(symbol, "limit", side, amount, price, params={"cid": cid})

    @staticmethod
    def _order(row: dict) -> dict:
        """Keep native creation time separate from updates and leave executed cost to fills."""
        order = CCXTClient._order(row)
        native = row.get("info")
        if isinstance(native, list) and len(native) >= 18:
            order.update(timestamp=number(native[4]), cost=None)
            order["average"] = number(native[17]) or None
        return order

    def fetch_order(self, order_id: str, symbol: str) -> dict:
        """Track exact cash orders through active and retained native closed-order reads."""
        from sibyl.exchanges.bitfinex_orders import read_order

        with self.lock:
            self._require("fetchOrder", private=True)
            self.market(symbol)
            return self._order(read_order(self._exchange, order_id, self._exchange.market(symbol)))


class CoinExClient(CCXTClient):
    """CoinEx spot trading account."""

    # Trading instruments infer currency codes; deposit-network metadata is outside this client scope.
    fetch_currencies = False
    id = "coinex"
    history_kind = "coinex-page"
    balance_params = {"type": "spot"}
    book_limits = (5, 10, 20, 50)

    def format_client_order_id(self, identity: str) -> str:
        """CoinEx accepts at most 32 bytes for a client_id."""
        return identity.replace("-", "")

    def _submit_limit_order(self, symbol, side, amount, price, client_order_id):
        """Pass the native field so no duplicate unified clientOrderId reaches v2."""
        return self._exchange.create_order(
            symbol, "limit", side, amount, price, params={"client_id": client_order_id, "timeInForce": "GTC"}
        )

    def market_order_limits(self, symbol: str, side: str, amount: float) -> dict:
        """Check current Spot API permission and base sizing before review."""
        with self.lock:
            self.market(symbol)
            coinex_activity.market_order_amount(self._exchange, self._exchange.market(symbol), amount)
        return {}

    def _submit_market_order(self, symbol, side, amount, client_order_id):
        """Send one Spot order with the base currency explicitly set on either side."""
        market = self._exchange.market(symbol)
        try:
            quantity = coinex_activity.market_order_amount(self._exchange, market, amount)
        except (ValueError, ccxt.NetworkError) as error:
            raise ccxt.InvalidOrder("CoinEx market order rules could not be satisfied.") from error
        request = {
            "market": market["id"],
            "market_type": "SPOT",
            "side": side,
            "type": "market",
            "ccy": market["baseId"],
            "amount": quantity,
            "client_id": client_order_id,
        }
        response = self._exchange.v2PrivatePostSpotOrder(request)
        return coinex_activity.market_order_ack(self._exchange, market, request, response)

    def _order(self, row: dict) -> dict:
        """Preserve v2 lifecycle states and keep currency-selected market sizing explicit."""
        order = CCXTClient._order(row)
        native = row.get("info")
        if isinstance(native, dict):
            order["status"] = coinex_activity.STATUS.get(native.get("status"), order["status"])
            kind = native.get("type")
            if kind in coinex_activity.INSTRUCTIONS:
                order.update(type="limit", timeInForce=coinex_activity.INSTRUCTIONS[kind])
            elif kind == "market":
                market = self._exchange.markets.get(order["symbol"], {})
                order.update(coinex_activity.market_quantities(native, market.get("baseId")))
        return order


class BitMartClient(CCXTClient):
    """BitMart spot; the API memo is passed through CCXT's uid credential field."""

    # Avoid coupling spot reads to the separate deposit/withdrawal currency endpoint.
    fetch_currencies = False
    id = "bitmart"
    history_kind = "bitmart-window"
    balance_params = {"type": "spot"}

    def format_client_order_id(self, identity: str) -> str:
        """BitMart requires an alphanumeric ID of at most 32 characters."""
        return identity.replace("-", "")

    @staticmethod
    def _order(row: dict) -> dict:
        """Keep native filled sizes separate from a market buy's quote-currency budget."""
        order = CCXTClient._order(row)
        native = row.get("info")
        if isinstance(native, dict):
            kind = native.get("type")
            if kind == "limit":
                order["timeInForce"] = "GTC"
            elif kind == "market" and native.get("side") == "buy":
                order.update(
                    amount=None,
                    remaining=None,
                    filled=number(native.get("filledSize", native.get("filled_size"))),
                    average=number(native.get("priceAvg", native.get("price_avg"))),
                )
        return order


class PhemexClient(CCXTClient):
    """Phemex spot wallet and optional testnet."""

    id = "phemex"
    history_kind = "phemex-spot"
    balance_params = {"type": "spot"}

    def _order(self, row: dict) -> dict:
        """Correct native spot scaling and quote-sized requests across every order read."""
        from sibyl.exchanges.phemex_activity import parse_order

        native = row.get("info")
        if isinstance(native, dict) and native.get("symbol"):
            row = parse_order(self._exchange, native, self._exchange.market(row["symbol"]))
        return CCXTClient._order(row)

    def _submit_market_order(self, symbol, side, amount, client_order_id):
        """Use spot base quantities and native IOC without a quote budget or reference price."""
        return self._exchange.create_order(
            symbol,
            "market",
            side,
            amount,
            params={
                "clientOrderId": client_order_id,
                "qtyType": "ByBase",
                "timeInForce": "ImmediateOrCancel",
            },
        )

    def _submit_limit_order(self, symbol, side, amount, price, client_order_id):
        """Phemex spot accepts native GoodTillCancel rather than unified GTC."""
        return self._exchange.create_order(
            symbol,
            "limit",
            side,
            amount,
            price,
            params={"clientOrderId": client_order_id, "timeInForce": "GoodTillCancel"},
        )


class PoloniexClient(CCXTClient):
    """Poloniex spot account; no sandbox is exposed by Sibyl."""

    id = "poloniex"
    history_kind = "poloniex-page"

    @staticmethod
    def _order(row: dict) -> dict:
        """Preserve native spot costs and keep a pending cancellation active until confirmed."""
        from sibyl.exchanges.poloniex_orders import STATUS

        order = CCXTClient._order(row)
        native = row.get("info")
        if isinstance(native, dict) and native.get("accountType") == "SPOT":
            order["status"] = STATUS.get(native.get("state"), order["status"])
            if "filledAmount" in native:
                order["cost"] = number(native["filledAmount"])
            if native.get("type") == "MARKET" and native.get("side") == "BUY":
                order.update(
                    amount=None,
                    remaining=None,
                    filled=number(native.get("filledQuantity")),
                    average=number(native.get("avgPrice")),
                )
        return order


class UpbitClient(CCXTClient):
    """Upbit default endpoint; regional API variants require their own adapter."""

    id = "upbit"
    history_kind = "upbit-orders"

    @staticmethod
    def _order(row: dict) -> dict:
        """Keep executed funds separate from quote budgets and unexecuted limit prices."""
        order = CCXTClient._order(row)
        native = row.get("info")
        if not isinstance(native, dict):
            return order
        cost = number(native.get("executed_funds"))
        trades = native.get("trades")
        if cost is None and isinstance(trades, list) and trades:
            funds = [number(trade.get("funds")) if isinstance(trade, dict) else None for trade in trades]
            if all(value is not None and value >= 0 for value in funds):
                cost = sum(funds)
        filled = number(native.get("executed_volume"))
        order.update(cost=cost, average=cost / filled if cost is not None and filled else None)
        if native.get("ord_type") == "price":
            order.update(amount=None, remaining=None, filled=filled)
        return order


CLIENTS = {
    client.id: client
    for client in (
        BinanceClient,
        BinanceTestnetClient,
        CoinbaseSandboxClient,
        BinanceUSClient,
        CoinbaseClient,
        KrakenClient,
        OKXClient,
        BybitClient,
        KuCoinClient,
        GateClient,
        BitgetClient,
        MEXCClient,
        HTXClient,
        CryptoComClient,
        BitstampClient,
        GeminiClient,
        BitfinexClient,
        CoinExClient,
        BitMartClient,
        PhemexClient,
        PoloniexClient,
        UpbitClient,
    )
}

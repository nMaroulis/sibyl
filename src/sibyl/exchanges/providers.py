"""Explicit spot clients: provider differences live here, not in domain services."""

from sibyl.exchanges.binance_advanced import BinanceAdvanced
from sibyl.exchanges.ccxt_client import CCXTClient


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


class GateClient(CCXTClient):
    """Gate spot wallet with optional sandbox credentials."""

    id = "gate"
    options = {"fetchMarkets": {"types": ["spot"]}, "unifiedAccount": False}
    balance_params = {"type": "spot"}

    def format_client_order_id(self, identity: str) -> str:
        """Persist the complete native Gate text ID, including its t- prefix."""
        return "t-" + identity.replace("-", "")[:26]


class BitgetClient(CCXTClient):
    """Bitget classic spot assets and passphrase authentication."""

    id = "bitget"
    history_kind = "bitget-id"
    options = {"uta": False}
    balance_params = {"type": "spot"}

    def format_client_order_id(self, identity: str) -> str:
        """Use a stable compact classic-account clientOid."""
        return identity.replace("-", "")

    def _submit_limit_order(self, symbol, side, amount, price, client_order_id):
        """Classic v2 requires lowercase native force; avoid SDK unified-field leakage."""
        return self._exchange.create_order(
            symbol, "limit", side, amount, price, params={"clientOid": client_order_id, "force": "gtc"}
        )


class MEXCClient(CCXTClient):
    """MEXC spot account, excluding contract markets."""

    id = "mexc"
    balance_params = {"type": "spot"}
    book_limits = (5, 10, 20, 50, 100)

    def format_client_order_id(self, identity: str) -> str:
        """MEXC client IDs fit its 32-character native limit."""
        return identity.replace("-", "")


class HTXClient(CCXTClient):
    """HTX spot account, excluding margin and swaps."""

    id = "htx"
    balance_params = {"type": "spot"}
    book_limits = (5, 10, 20)

    def _spot_account(self) -> str:
        """Require one actual spot wallet; never fall back to the first margin account."""
        accounts = [row for row in self._exchange.load_accounts() if row.get("type") == "spot"]
        if len(accounts) != 1 or not accounts[0].get("id"):
            raise ValueError("HTX requires one unambiguous spot account for balance and order access.")
        return str(accounts[0]["id"])

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


class CryptoComClient(CCXTClient):
    """Crypto.com Exchange account, separate from the retail mobile app."""

    id = "cryptocom"
    book_limits = (10, 50)

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
    balance_params = {"type": "exchange"}
    book_limits = (1, 25, 100)

    def format_client_order_id(self, identity: str) -> str:
        """Bitfinex cid is a positive int45; admission rejects any local collision."""
        return str(int(identity.replace("-", "")[:11], 16) + 1)

    def _submit_limit_order(self, symbol, side, amount, price, client_order_id):
        """Use integer cid and a native non-margin EXCHANGE LIMIT."""
        cid = int(client_order_id)
        if not 0 < cid < 2**45:
            raise ValueError("Bitfinex client order ID must be a positive int45.")
        return self._exchange.create_order(symbol, "limit", side, amount, price, params={"cid": cid})


class CoinExClient(CCXTClient):
    """CoinEx spot trading account."""

    # Trading instruments infer currency codes; deposit-network metadata is outside this client scope.
    fetch_currencies = False
    id = "coinex"
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


class BitMartClient(CCXTClient):
    """BitMart spot; the API memo is passed through CCXT's uid credential field."""

    # Avoid coupling spot reads to the separate deposit/withdrawal currency endpoint.
    fetch_currencies = False
    id = "bitmart"
    balance_params = {"type": "spot"}

    def format_client_order_id(self, identity: str) -> str:
        """BitMart requires an alphanumeric ID of at most 32 characters."""
        return identity.replace("-", "")


class PhemexClient(CCXTClient):
    """Phemex spot wallet and optional testnet."""

    id = "phemex"
    balance_params = {"type": "spot"}

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


class UpbitClient(CCXTClient):
    """Upbit default endpoint; regional API variants require their own adapter."""

    id = "upbit"


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

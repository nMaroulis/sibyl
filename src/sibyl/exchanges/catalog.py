"""The reviewed spot-provider allowlist and its credential/UI metadata.

Adding a CCXT identifier here does not enable trading. New providers start with
read access; execution requires a separate review of amount and order-ID semantics.
"""

from dataclasses import asdict, dataclass
from typing import Literal

ExchangeId = Literal[
    "binance",
    "binanceus",
    "coinbase",
    "kraken",
    "okx",
    "bybit",
    "kucoin",
    "gate",
    "bitget",
    "mexc",
    "htx",
    "cryptocom",
    "bitstamp",
    "gemini",
    "bitfinex",
    "coinex",
    "bitmart",
    "phemex",
    "poloniex",
    "upbit",
]


ConnectionExchangeId = ExchangeId | Literal["demo", "binance-testnet", "coinbase-sandbox"]


@dataclass(frozen=True)
class ExchangeSpec:
    """Describe configured support, not a promise of account or regional availability."""

    id: ConnectionExchangeId
    name: str
    note: str = "API key + secret · spot account"
    passphrase: bool = False
    uid: bool = False
    sandbox: bool = False
    market_orders: bool = False
    limit_only: bool = False
    account: str = "Spot trading wallet"
    credentials_required: bool = True
    simulated: bool = False
    test_environment: bool = False
    ccxt_id: str = ""
    setup_url: str = ""

    @property
    def spot_trading(self) -> bool:
        """Whether Sibyl has reviewed an order submission and cancellation path."""
        return self.market_orders or self.limit_only or self.simulated

    def supports_order(self, order_type: str) -> bool:
        """Keep domain and adapter execution gates aligned, including limit-only venues."""
        if order_type == "limit":
            return self.spot_trading
        return order_type == "market" and self.market_orders

    def public(self) -> dict:
        """Return non-secret metadata consumed by connection forms and API clients."""
        return {
            **asdict(self),
            "ccxt_id": self.ccxt_id or self.id,
            "verification": "Adapter-tested; verify this account separately with Check access.",
            "limit_orders": self.spot_trading,
            "cancel_orders": self.spot_trading,
        }


EXCHANGES = (
    ExchangeSpec("binance", "Binance", sandbox=True, market_orders=True),
    ExchangeSpec(
        "binanceus", "Binance.US", market_orders=True, account="US spot account; separate Binance.US keys"
    ),
    ExchangeSpec("coinbase", "Coinbase", "CDP API key name + supported PEM private key", market_orders=True),
    ExchangeSpec("kraken", "Kraken", market_orders=True),
    ExchangeSpec(
        "okx",
        "OKX",
        "API key + secret + passphrase",
        market_orders=True,
        passphrase=True,
        sandbox=True,
        account="Trading account; funding wallet excluded",
    ),
    ExchangeSpec(
        "bybit",
        "Bybit",
        sandbox=True,
        market_orders=True,
        account="Unified account; balances may include shared collateral",
    ),
    ExchangeSpec(
        "kucoin",
        "KuCoin",
        "API key + secret + passphrase",
        market_orders=True,
        passphrase=True,
        account="Spot trading account; main/funding wallet excluded",
    ),
    ExchangeSpec("gate", "Gate", sandbox=True),
    ExchangeSpec("bitget", "Bitget", "API key + secret + passphrase", passphrase=True),
    ExchangeSpec("mexc", "MEXC"),
    ExchangeSpec("htx", "HTX"),
    ExchangeSpec("cryptocom", "Crypto.com Exchange", sandbox=True),
    ExchangeSpec("bitstamp", "Bitstamp", market_orders=True),
    ExchangeSpec("gemini", "Gemini", sandbox=True, limit_only=True),
    ExchangeSpec("bitfinex", "Bitfinex", account="Exchange wallet; margin/funding wallets excluded"),
    ExchangeSpec("coinex", "CoinEx"),
    ExchangeSpec("bitmart", "BitMart", "API key + secret + API memo", uid=True),
    ExchangeSpec("phemex", "Phemex", sandbox=True),
    ExchangeSpec("poloniex", "Poloniex"),
    ExchangeSpec("upbit", "Upbit", account="Global CCXT endpoint; regional variants are not configured"),
)
DEMO = ExchangeSpec(
    "demo",
    "Demo",
    "No API keys · simulated funds",
    account="Persistent paper wallet",
    credentials_required=False,
    simulated=True,
)
TEST_ENVIRONMENTS = (
    ExchangeSpec(
        "binance-testnet",
        "Binance Testnet",
        "Spot testnet API key + secret",
        sandbox=True,
        market_orders=True,
        account="Binance Spot Test Network · virtual funds",
        test_environment=True,
        ccxt_id="binance",
        setup_url="https://testnet.binance.vision/",
    ),
    ExchangeSpec(
        "coinbase-sandbox",
        "Coinbase Exchange Sandbox",
        "Exchange Sandbox key + secret + passphrase; CDP Portal sandbox keys use a different API",
        passphrase=True,
        sandbox=True,
        market_orders=True,
        account="Coinbase Exchange sandbox · test funds",
        test_environment=True,
        ccxt_id="coinbaseexchange",
        setup_url="https://public.sandbox.exchange.coinbase.com/",
    ),
)
CATALOG = {item.id: item for item in (*EXCHANGES, *TEST_ENVIRONMENTS, DEMO)}


def exchange_spec(identity: str) -> ExchangeSpec:
    """Reject arbitrary CCXT class names and unknown exchange identifiers."""
    if identity not in CATALOG:
        raise ValueError("Unsupported exchange. Choose a provider from the exchange catalog.")
    return CATALOG[identity]

"""Provider read policies, separate from CCXT's internal throttle cost units.

Only reviewed endpoint families receive weight/counter estimates. Unknown requests
retain native throttling and existing app spacing, with an explicit coverage gap.
No raw endpoint, symbol, account ID, key or parameter is retained in a request.
"""

import json
from dataclasses import dataclass

BINANCE_DOCS = "https://github.com/binance/binance-spot-api-docs/blob/master/rest-api.md#limits"
KRAKEN_DOCS = "https://docs.kraken.com/exchange/guides/rest/ratelimits"
EXCHANGE_DOCS = "https://docs.cdp.coinbase.com/exchange/rest-api/rate-limits"
REVIEWED = "2026-11-09"


@dataclass(frozen=True)
class Call:
    family: str
    environment: str
    partition: str
    label: str = "Unreviewed request"
    charges: tuple = ()
    exchange_info: bool = False
    reviewed: bool = False


def family(provider):
    return "binance" if provider == "binance-testnet" else provider


def describe(provider):
    """Explain implemented policy without discovering an account's tier or contacting it."""
    name = family(provider)
    if name == "demo":
        return {
            "name": "Offline Demo",
            "reviewed_at": None,
            "reference": None,
            "coverage": "Synthetic local data; no external request quota.",
            "identity": "Offline workspace.",
            "headroom": "No provider requests.",
        }
    if name in {"binance", "binanceus"}:
        return {
            "name": "Binance spot weight budgets",
            "reviewed_at": REVIEWED,
            "reference": "https://docs.binance.us/" if name == "binanceus" else BINANCE_DOCS,
            "coverage": "Reviewed Spot v3 GET weights; observed one-minute IP limits. Wallet/SAPI and other endpoints remain unreviewed.",
            "identity": "Shared locally across public and saved clients for this provider/environment.",
            "headroom": "Local reads: 600 weight and 120 requests per UTC minute. A reported one-minute IP limit adds an 80% read ceiling; order counters are observational only.",
        }
    if name == "kraken":
        return {
            "name": "Kraken conservative read counters",
            "reviewed_at": REVIEWED,
            "reference": KRAKEN_DOCS,
            "coverage": "Public reads and reviewed private account/history POST reads. Trading-engine limits are separate.",
            "identity": "Public budget shared locally; private budgets share identical API keys, without exposing their identity.",
            "headroom": "Public: one request per second. Private: capacity 12, decay 0.30/sec, history cost 4 and other reviewed reads cost 1. Tier is unknown; this is a conservative application estimate.",
        }
    if name == "coinbase-sandbox":
        return {
            "name": "Coinbase Exchange Sandbox read buckets",
            "reviewed_at": REVIEWED,
            "reference": EXCHANGE_DOCS,
            "coverage": "Reviewed Exchange public/private GET reads, with an additional fills bucket. Advanced Trade uses a different API.",
            "identity": "Public reads share one local bucket; all saved profiles conservatively share private/fills buckets because profile identity is not inferred.",
            "headroom": "Local public capacity 10/refill 8 per second; private 12/10; fills also 8/8. These app allowances do not establish purchased or account-specific quotas.",
        }
    return {
        "name": "Shared request controls",
        "reviewed_at": None,
        "reference": None,
        "coverage": "Endpoint quota policy is not reviewed for this provider. Shared spacing and cooldowns remain in force, alongside native throttling where the adapter provides it.",
        "identity": "One local process; no cross-process or external-client coordination.",
        "headroom": "Provider quota/headroom is unknown.",
    }


def _symbols(params):
    value = params.get("symbols")
    if isinstance(value, str) and len(value) < 20000:
        try:
            value = json.loads(value)
        except (ValueError, TypeError, RecursionError):
            return 1000
    return len(value) if isinstance(value, list) else 1000


def request(source, api, method, path, params, partition="shared"):
    """Reduce SDK request metadata to fixed labels and reviewed numeric costs only."""
    name = family(source["provider"])
    env = source["environment"]
    group = (
        api
        if isinstance(api, str)
        else "/".join(api)
        if isinstance(api, list) and all(isinstance(v, str) for v in api)
        else ""
    )
    params = params if isinstance(params, dict) else {}
    if not isinstance(path, str) or not isinstance(method, str):
        return Call(name, env, partition)
    label, charges, reviewed, info = "Unreviewed request", (), False, False
    if name in {"binance", "binanceus"} and group in {"public", "private"} and method == "GET":
        weights = {
            "ping": 1,
            "time": 1,
            "exchangeInfo": 20,
            "trades": 25,
            "historicalTrades": 25,
            "aggTrades": 4,
            "klines": 2,
            "uiKlines": 2,
            "avgPrice": 2,
            "account": 20,
            "order": 4,
            "allOrders": 20,
            "rateLimit/order": 40,
            "allOrderList": 20,
            "openOrderList": 6,
            "orderList": 4,
            "account/commission": 20,
            "myAllocations": 20,
        }
        cost = weights.get(path)
        if path == "depth":
            limit = params.get("limit", 100)
            cost = next(
                (
                    weight
                    for maximum, weight in ((100, 5), (500, 25), (1000, 50), (5000, 250))
                    if isinstance(limit, (int, float))
                    and not isinstance(limit, bool)
                    and 0 < limit <= maximum
                ),
                None,
            )
        elif path == "openOrders":
            cost = 6 if params.get("symbol") else 80
        elif path == "myTrades":
            cost = 5 if params.get("orderId") is not None else 20
        elif path in {"ticker/price", "ticker/bookTicker"}:
            cost = 2 if params.get("symbol") else 4
        elif path == "ticker/24hr":
            count = 1 if params.get("symbol") else _symbols(params)
            cost = 2 if count <= 20 else 40 if count <= 100 else 80
        if cost is not None:
            label = "Spot market information" if path == "exchangeInfo" else "Spot weighted read"
            charges = (("local_weight", cost), ("local_requests", 1), ("ip_weight", cost))
            reviewed, info = True, path == "exchangeInfo"
        else:
            charges = (("local_requests", 1),)
    elif name == "kraken":
        if (
            group == "public"
            and method == "GET"
            and path
            in {"Time", "SystemStatus", "Assets", "AssetPairs", "Ticker", "OHLC", "Depth", "Trades", "Spread"}
        ):
            label, charges, reviewed = "Public spot read", (("public_reads", 1),), True
        elif group == "private" and method == "POST":
            history = {"TradesHistory", "Ledgers", "ClosedOrders"}
            ordinary = {
                "Balance",
                "BalanceEx",
                "TradeBalance",
                "OpenOrders",
                "QueryOrders",
                "QueryTrades",
                "OpenPositions",
                "TradeVolume",
                "QueryLedgers",
                "DepositStatus",
                "WithdrawStatus",
                "GetApiKeyInfo",
            }
            if path in history | ordinary:
                label = "Private history estimate" if path in history else "Private account estimate"
                charges, reviewed = (("private_counter", 4 if path in history else 1),), True
    elif name == "coinbase-sandbox" and method == "GET":
        if group == "public" and (path in {"time", "products", "currencies"} or path.startswith("products/")):
            label, charges, reviewed = "Exchange public read", (("public_reads", 1),), True
        elif group == "private" and (
            path in {"accounts", "orders", "fills"} or path.startswith(("accounts/", "orders/"))
        ):
            label, charges, reviewed = "Exchange private read", (("private_reads", 1),), True
            if path == "fills":
                label, charges = "Exchange fills read", ((*charges, ("private_fills", 1)))
    return Call(name, env, partition, label, charges, info, reviewed)


def specifications(call):
    """Return only application allowances; reported Binance limits are installed separately."""
    if call.family in {"binance", "binanceus"}:
        return {
            "local_weight": ("Local read weight", "provider_environment", 600, 60, None),
            "local_requests": ("Local request allowance", "provider_environment", 120, 60, None),
        }
    if call.family == "kraken":
        return {
            "public_reads": ("Public read allowance", "provider_environment", 1, None, 1),
            "private_counter": ("Conservative private counter", "credential", 12, None, 0.30),
        }
    if call.family == "coinbase-sandbox":
        return {
            "public_reads": ("Public read allowance", "provider_environment", 10, None, 8),
            "private_reads": ("Private read allowance", "all_local_profiles", 12, None, 10),
            "private_fills": ("Private fills allowance", "all_local_profiles", 8, None, 8),
        }
    return {}

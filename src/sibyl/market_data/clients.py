"""Bounded, read-only aggregator adapters behind the normal market client contract."""

import time
from datetime import UTC, datetime

import ccxt
import httpx

from sibyl.exchanges.base import ExchangeClient, number
from sibyl.exchanges.data import TIMEFRAMES

COIN_IDS = {
    "BTC": "bitcoin",
    "ETH": "ethereum",
    "SOL": "solana",
    "LINK": "chainlink",
    "AVAX": "avalanche-2",
    "DOT": "polkadot",
}


def object_row(value) -> dict:
    """Reject malformed nested provider records with a sanitized domain error."""
    if not isinstance(value, dict):
        raise ccxt.ExchangeError("Market provider returned an invalid record.")
    return value


def numeric(value) -> float | None:
    """Provider booleans are not numeric observations."""
    return None if isinstance(value, bool) else number(value)


class PublicAPIClient(ExchangeClient):
    """Only fixed provider endpoints, finite timeouts and bounded JSON are accepted."""

    timeframes: dict = {}

    def __init__(self, base_url: str, headers: dict, transport=None):
        super().__init__()
        self._http = httpx.Client(
            base_url=base_url, headers=headers, timeout=12, follow_redirects=False, transport=transport
        )
        self._cache: dict = {}

    def _get(self, path: str, params: dict) -> dict:
        try:
            with self._http.stream("GET", path, params=params) as response:
                response.raise_for_status()
                chunks, size = [], 0
                for chunk in response.iter_bytes():
                    size += len(chunk)
                    if size > 2_000_000:
                        raise ValueError("Market response exceeds the size limit.")
                    chunks.append(chunk)
                import json

                result = json.loads(b"".join(chunks))
                if (
                    not isinstance(result, dict)
                    or result.get("Response") == "Error"
                    or result.get("status", {}).get("error_code")
                ):
                    raise ValueError("Market provider returned an unsuccessful response.")
                return result
        except httpx.HTTPError:
            raise ccxt.ExchangeNotAvailable(
                "Market provider request failed. Check access and quota."
            ) from None
        except (ValueError, TypeError, AttributeError):
            raise ccxt.ExchangeError("Market provider returned invalid data.") from None

    def _cached(self, key, loader, ttl=60):
        with self.lock:
            previous = self._cache.get(key)
            if previous and time.monotonic() - previous[0] < ttl:
                return previous[1]
            value = loader()
            self._cache[key] = (time.monotonic(), value)
            return value

    def fetch_balance(self) -> dict:
        raise ccxt.NotSupported("This provider supplies market data, not accounts.")

    def amount_to_precision(self, symbol: str, amount: float) -> str:
        raise ccxt.NotSupported("This provider cannot execute orders.")

    def fetch_order_book(self, symbol: str, limit: int = 10) -> dict:
        raise ccxt.NotSupported("This aggregated feed has no exchange order book.")

    def fetch_ohlcv(self, symbol: str, timeframe: str = "1d", limit: int = 180) -> list[list]:
        raise ccxt.NotSupported("This adapter supplies quotes only. Choose a candle-capable source.")

    def close(self) -> None:
        with self.lock:
            self._http.headers.clear()
            self._http.close()
            self._cache.clear()


class CryptoCompareClient(PublicAPIClient):
    """CCCAGG reference quotes and direct-pair OHLCV; synthetic conversions are disabled."""

    id = "cryptocompare"
    timeframes = TIMEFRAMES
    intervals = {
        "1m": ("histominute", 1),
        "5m": ("histominute", 5),
        "15m": ("histominute", 15),
        "30m": ("histominute", 30),
        "1h": ("histohour", 1),
        "4h": ("histohour", 4),
        "12h": ("histohour", 12),
        "1d": ("histoday", 1),
        "1w": ("histoday", 7),
    }

    def __init__(self, api_key: str = "", transport=None):
        super().__init__(
            "https://min-api.cryptocompare.com",
            {"Authorization": f"Apikey {api_key}"} if api_key else {},
            transport,
        )

    def load_markets(self) -> dict:
        """Expose six curated reference assets; exchange feeds offer broader discovery."""
        return {
            f"{base}/{quote}": {
                "symbol": f"{base}/{quote}",
                "base": base,
                "quote": quote,
                "spot": True,
                "active": True,
                "precision": {},
                "limits": {},
            }
            for base in COIN_IDS
            for quote in ("USD", "USDT", "BTC", "ETH")
            if base != quote
        }

    def fetch_ticker(self, symbol: str) -> dict:
        self.market(symbol)
        base, quote = symbol.split("/")
        result = self._cached(
            f"quotes:{quote}",
            lambda: self._get(
                "/data/pricemultifull",
                {
                    "fsyms": ",".join(COIN_IDS),
                    "tsyms": quote,
                    "e": "CCCAGG",
                    "tryConversion": "false",
                },
            ),
        )
        row = object_row(object_row(object_row(result.get("RAW", {})).get(base, {})).get(quote, {}))
        price = numeric(row.get("PRICE"))
        if price is None or price <= 0:
            raise ccxt.BadSymbol("No direct aggregated quote is available for this pair.")
        stamp = numeric(row.get("LASTUPDATE"))
        if stamp is not None and (stamp <= 0 or stamp > datetime.now(UTC).timestamp() + 300):
            raise ccxt.ExchangeError("No valid dated reference quote is available.")
        return {
            "symbol": symbol,
            "last": price,
            "close": price,
            "timestamp": stamp * 1000 if stamp is not None else None,
            "percentage": numeric(row.get("CHANGEPCT24HOUR")),
            "quoteVolume": numeric(row.get("VOLUME24HOURTO")),
            "baseVolume": numeric(row.get("VOLUME24HOUR")),
        }

    def fetch_ohlcv(self, symbol: str, timeframe: str = "1d", limit: int = 180) -> list[list]:
        self.market(symbol)
        if timeframe not in self.intervals or not 1 <= limit <= 1000:
            raise ValueError("Unsupported interval or candle count.")
        endpoint, aggregate = self.intervals[timeframe]
        if limit * aggregate > 2000:
            raise ValueError(
                f"This interval supports at most {2000 // aggregate - 1} closed candles per request."
            )
        base, quote = symbol.split("/")
        result = self._get(
            f"/data/v2/{endpoint}",
            {
                "fsym": base,
                "tsym": quote,
                "e": "CCCAGG",
                "limit": limit,
                "aggregate": aggregate,
                "aggregatePredictableTimePeriods": "true",
                "tryConversion": "false",
            },
        )
        rows = object_row(result.get("Data", {})).get("Data")
        if not isinstance(rows, list) or len(rows) > 2002:
            raise ccxt.ExchangeError("Invalid aggregated candle response.")
        candles = {}
        for row in rows:
            row = object_row(row)
            values = [
                numeric(row.get(field)) for field in ("time", "open", "high", "low", "close", "volumefrom")
            ]
            if any(value is None for value in values):
                raise ccxt.ExchangeError("Missing aggregated candle values.")
            stamp, opening, high, low, close, volume = values
            # Empty/no-trade placeholder intervals are not observed price candles.
            if opening == high == low == close == 0:
                continue
            if (
                stamp <= 0
                or min(opening, high, low, close) <= 0
                or volume < 0
                or low > min(opening, close)
                or high < max(opening, close)
            ):
                raise ccxt.ExchangeError("Invalid aggregated candle bounds.")
            candles[stamp] = [stamp * 1000, opening, high, low, close, volume]
        return [candles[key] for key in sorted(candles)][-limit:]


class CoinGeckoClient(PublicAPIClient):
    """Dated USD reference quotes, batched by reviewed coin IDs rather than ambiguous tickers.

    Historical OHLCV is deliberately unsupported: the simple-price API does not
    contain candle volume. No volume or candles are fabricated from snapshots.
    """

    def __init__(self, api_key: str, pro: bool = False, transport=None):
        self.id = "coingecko-pro" if pro else "coingecko"
        super().__init__(
            "https://pro-api.coingecko.com" if pro else "https://api.coingecko.com",
            {"x-cg-pro-api-key" if pro else "x-cg-demo-api-key": api_key},
            transport,
        )

    def load_markets(self) -> dict:
        return {
            f"{base}/USD": {
                "symbol": f"{base}/USD",
                "base": base,
                "quote": "USD",
                "spot": True,
                "active": True,
                "precision": {},
                "limits": {},
            }
            for base in COIN_IDS
        }

    def fetch_ticker(self, symbol: str) -> dict:
        self.market(symbol)
        base = symbol.split("/")[0]
        result = self._cached(
            "quotes",
            lambda: self._get(
                "/api/v3/simple/price",
                {
                    "ids": ",".join(COIN_IDS.values()),
                    "vs_currencies": "usd",
                    "include_24hr_vol": "true",
                    "include_24hr_change": "true",
                    "include_last_updated_at": "true",
                },
            ),
        )
        row = object_row(result.get(COIN_IDS[base], {}))
        price, stamp = numeric(row.get("usd")), numeric(row.get("last_updated_at"))
        if (
            price is None
            or price <= 0
            or stamp is None
            or stamp <= 0
            or stamp > datetime.now(UTC).timestamp() + 300
        ):
            raise ccxt.ExchangeError("No valid dated reference quote is available.")
        return {
            "symbol": symbol,
            "last": price,
            "close": price,
            "timestamp": stamp * 1000,
            "percentage": numeric(row.get("usd_24h_change")),
            "quoteVolume": numeric(row.get("usd_24h_vol")),
        }

"""Bounded, attributable conversion of native asset quantities into USDT."""

import math
import time
from datetime import UTC, datetime

import ccxt

from sibyl.services.crypto_library import ASSETS as RESEARCH_ASSETS
from sibyl.services.market import Market

CURRENCY = "USDT"
BRIDGES = ("USDC", "USD", "BTC", "ETH", "EUR", "DAI")
MAX_QUOTES = 80
MAX_PATHS = 3
MAX_HISTORY = 12
MAX_SECONDS = 12


class Valuation:
    """Resolve short conversion paths within one frozen market source.

    Call inside ``Market.snapshot()``. Direct markets are preferred, then inverse
    markets, then at most two reviewed bridge assets. Only exact native pairs
    are read. Each leg is shared across holdings, with finite quote, chart and
    elapsed-time budgets. Stale/invalid quotes are excluded; undated observations
    are usable but explicitly labeled. Only the denomination itself equals one.
    """

    def __init__(self, market: Market):
        self.market = market
        self.metadata = market.metadata()
        self.started = time.monotonic()
        self.tickers: dict[str, dict] = {}
        self.prices: dict[str, dict] = {}
        self.histories: dict[str, dict[str, float]] = {}
        self.history_reads = 0
        self.catalog: list[dict] = []
        self.edges: dict[tuple[str, str], list[dict]] = {}
        self.loaded = False
        self.catalog_error = False

    def _catalog(self) -> None:
        """Load once on demand; empty wallets and USDT alone need no public requests."""
        if self.loaded:
            return
        self.loaded = True
        try:
            self.catalog = self.market.symbols()["items"]
        except (ccxt.BaseError, ValueError):
            self.catalog, self.catalog_error = [], True
        for row in self.catalog:
            base, quote = row["base"], row["quote"]
            for origin, target, inverse in ((base, quote, False), (quote, base, True)):
                self.edges.setdefault((origin, target), []).append(
                    {"symbol": row["symbol"], "from_asset": origin, "to_asset": target, "inverse": inverse}
                )
        for edges in self.edges.values():
            edges.sort(key=lambda edge: edge["inverse"])

    def _paths(self, asset: str) -> list[list[dict]]:
        """Enumerate a deterministic bounded set, preferring fewest conversion legs."""
        paths = []
        sequences = [(asset, CURRENCY)]
        bridges = [coin for coin in BRIDGES if coin != asset]
        sequences += [(asset, bridge, CURRENCY) for bridge in bridges]
        sequences += [(asset, a, b, CURRENCY) for a in bridges for b in bridges if a != b]
        for sequence in sequences:
            options = [[]]
            for origin, target in zip(sequence[:-1], sequence[1:], strict=True):
                edges = self.edges.get((origin, target), [])
                options = [path + [edge] for path in options for edge in edges][:MAX_PATHS]
            paths.extend(options)
            if len(paths) >= MAX_PATHS:
                break
        return paths[:MAX_PATHS]

    def _leg(self, edge: dict) -> dict:
        """Validate both current and previous prices before applying inversion."""
        symbol = edge["symbol"]
        if symbol not in self.tickers:
            if len(self.tickers) >= MAX_QUOTES or time.monotonic() - self.started > MAX_SECONDS:
                return {"status": "limited", "reason": "Pricing budget reached; try refreshing later."}
            self.tickers[symbol] = self.market.valuation_ticker(symbol)
        ticker = self.tickers[symbol]
        price, stamp = ticker.get("price"), ticker.get("timestamp")
        if price is None or price <= 0 or not math.isfinite(price):
            return {"status": "unavailable", "reason": "A conversion quote is unavailable or invalid."}
        now = datetime.now(UTC).timestamp() * 1000
        if stamp is not None and (stamp <= 0 or stamp > now + 60_000):
            return {"status": "unavailable", "reason": "A conversion quote has an invalid timestamp."}
        if self.metadata["source"] != "demo" and stamp is not None and now - stamp > 300_000:
            return {"status": "stale", "reason": "A conversion quote is older than five minutes."}
        change = ticker.get("change")
        previous = price / (1 + change / 100) if change is not None and change > -100 else None
        if previous is not None and (previous <= 0 or not math.isfinite(previous)):
            previous = None
        rate = 1 / price if edge["inverse"] else price
        prior = 1 / previous if previous is not None and edge["inverse"] else previous
        if not math.isfinite(rate) or rate <= 0 or (prior is not None and not math.isfinite(prior)):
            return {"status": "unavailable", "reason": "A conversion rate is invalid."}
        return {
            **edge,
            "rate": rate,
            "previous_rate": prior,
            "observed_at": datetime.fromtimestamp(stamp / 1000, UTC).isoformat() if stamp else None,
            "received_at": ticker.get("received_at"),
            "status": "fresh" if stamp is not None else "undated",
        }

    def price(self, asset: str) -> dict:
        """Return a price and evidence, or an explicit reason for exclusion from totals."""
        if asset in self.prices:
            return self.prices[asset]
        if asset != CURRENCY:
            self._catalog()
        known = next((row for row in RESEARCH_ASSETS.values() if row.symbol == asset), None)
        entry = next((row for row in self.catalog if row["base"] == asset), {})
        result = {
            "asset": asset,
            "currency": CURRENCY,
            "name": entry.get("name") or (known.name if known else asset),
            "color": entry.get("color") or (known.color if known else "#7994b3"),
            "price": None,
            "change": None,
            "route": [],
            "path": [],
            "observed_at": None,
            "status": "unavailable",
            "reason": "No supported conversion path to USDT on this feed.",
        }
        if asset == CURRENCY:
            result.update(price=1.0, change=0.0, path=[asset], status="identity", reason=None)
        elif self.catalog_error:
            result["reason"] = "The selected feed's market catalog is unavailable."
        else:
            for path in self._paths(asset):
                legs = []
                for edge in path:
                    leg = self._leg(edge)
                    if leg["status"] not in {"fresh", "undated"}:
                        result.update(status=leg["status"], reason=leg["reason"])
                        break
                    legs.append(leg)
                if len(legs) != len(path):
                    continue
                price = math.prod(leg["rate"] for leg in legs)
                previous = (
                    math.prod(leg["previous_rate"] for leg in legs)
                    if all(leg["previous_rate"] is not None for leg in legs)
                    else None
                )
                if not math.isfinite(price) or price <= 0:
                    continue
                dated = all(leg["observed_at"] is not None for leg in legs)
                move = (price / previous - 1) * 100 if previous and math.isfinite(previous) else None
                result.update(
                    price=price,
                    change=move if move is not None and math.isfinite(move) else None,
                    route=legs,
                    path=[asset, *(leg["to_asset"] for leg in legs)],
                    status="fresh" if dated else "undated",
                    observed_at=min(leg["observed_at"] for leg in legs) if dated else None,
                    reason=None,
                )
                break
        self.prices[asset] = result
        return result

    def history(self, quote: dict) -> list[dict]:
        """Compose up to 90 aligned daily closes along the actual valuation route.

        Histories are optional and never determine whether a current quote is
        usable. No forward filling, parity conversion or alternate route is used.
        The twelve-read budget bounds mini-chart work across the entire portfolio.
        """
        if not quote["route"] or not self.metadata["capabilities"]["candles"]:
            return []
        legs = []
        for edge in quote["route"]:
            symbol = edge["symbol"]
            if symbol not in self.histories:
                self.histories[symbol] = {}
                if self.history_reads >= MAX_HISTORY or time.monotonic() - self.started > MAX_SECONDS:
                    return []
                self.history_reads += 1
                try:
                    self.histories[symbol] = {
                        row["timestamp"]: row["close"] for row in self.market.candles(symbol, 90)
                    }
                except (ccxt.BaseError, ValueError):
                    pass
            rows = self.histories[symbol]
            legs.append({stamp: 1 / value if edge["inverse"] else value for stamp, value in rows.items()})
        common = set.intersection(*(set(rows) for rows in legs))
        result = []
        for stamp in sorted(common):
            value = math.prod(rows[stamp] for rows in legs)
            if math.isfinite(value) and value > 0:
                result.append({"timestamp": stamp, "value": value})
        return result

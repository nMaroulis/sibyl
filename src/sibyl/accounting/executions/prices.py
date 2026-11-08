"""Dated conversion paths from retained, fully closed candles.

A last closed candle is an approximate historical mark, not an execution quote.
Rates never assume stablecoin/fiat parity, bridge across environments, consume
future candle closes or silently fetch a network price during an accounting read.
"""

import hashlib
import json
from bisect import bisect_right
from collections import deque
from decimal import Decimal

from sibyl.market_data.archive import step_ms


class HistoricalPrices:
    """A bounded immutable read snapshot with at most three observed conversion legs."""

    def __init__(self, db, source, environment, start_ms, end_ms, max_age_ms=86_400_000):
        self.source, self.environment, self.max_age_ms = source, environment, max_age_ms
        self.series = []
        self._graphs = {}
        tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if "candle_series" not in tables:
            return
        series = db.execute(
            "SELECT id,metadata FROM candle_series WHERE json_extract(metadata,'$.source')=? AND json_extract(metadata,'$.environment')=? ORDER BY id",
            (source, environment),
        ).fetchall()
        if len(series) > 200:
            raise ValueError(
                "Historical conversion supports at most 200 retained series per selected feed/environment."
            )
        total = 0
        for identity, raw in series:
            meta = json.loads(raw)
            step = step_ms(meta["timeframe"])
            rows = db.execute(
                "SELECT timestamp,close,observed_at FROM candle_rows WHERE series_id=? AND timestamp>=? AND timestamp<=? ORDER BY timestamp LIMIT 100001",
                (identity, start_ms - max_age_ms - step, end_ms - step),
            ).fetchall()
            total += len(rows)
            if total > 100_000:
                raise ValueError(
                    "Historical conversion exceeds 100,000 bars. Select a shorter accounting period or another feed."
                )
            if rows:
                self.series.append((meta, step, rows, [row[0] + step for row in rows]))

    def fingerprint(self):
        """Bind reports to the actual retained price snapshot, including corrections."""
        facts = {
            "source": self.source,
            "environment": self.environment,
            "max_age_ms": self.max_age_ms,
            "series": [(meta, step, [list(row) for row in rows]) for meta, step, rows, _ in self.series],
        }
        return hashlib.sha256(json.dumps(facts, sort_keys=True).encode()).hexdigest()

    def graph(self, timestamp_ms):
        """Choose the newest eligible close for each exact directed pair."""
        if timestamp_ms in self._graphs:
            return self._graphs[timestamp_ms]
        edges = {}
        for meta, step, rows, closes in self.series:
            index = bisect_right(closes, timestamp_ms) - 1
            if index < 0 or timestamp_ms - closes[index] > self.max_age_ms:
                continue
            timestamp, value, observed = rows[index]
            rate = Decimal(str(value))
            base, quote = meta["symbol"].split("/")
            evidence = {
                "symbol": meta["symbol"],
                "timeframe": meta["timeframe"],
                "candle_open_ms": timestamp,
                "candle_close_ms": timestamp + step,
                "observed_at": observed,
            }
            for left, right, amount, inverse in (
                (base, quote, rate, False),
                (quote, base, Decimal(1) / rate, True),
            ):
                previous = edges.get((left, right))
                if previous is None or evidence["candle_close_ms"] > previous[1]["candle_close_ms"]:
                    edges[left, right] = (amount, {**evidence, "inverse": inverse, "rate": str(amount)})
        if len(self._graphs) >= 32:
            self._graphs.pop(next(iter(self._graphs)))
        self._graphs[timestamp_ms] = edges
        return edges

    def rate(self, asset, currency, timestamp_ms):
        """Return an observed dated path or None; identity conversion is exactly one."""
        if asset == currency:
            return Decimal(1), []
        edges = self.graph(timestamp_ms)
        queue = deque([(asset, Decimal(1), [], {asset})])
        while queue:
            current, value, path, visited = queue.popleft()
            if len(path) == 3:
                continue
            for (left, right), (rate, evidence) in sorted(edges.items()):
                if left != current or right in visited:
                    continue
                updated = value * rate
                if right == currency:
                    return updated, [*path, evidence]
                queue.append((right, updated, [*path, evidence], visited | {right}))
        return None

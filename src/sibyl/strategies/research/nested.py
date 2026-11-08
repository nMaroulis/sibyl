"""Inner chronological selection entirely inside each outer training prefix.

Rule-based strategies have no learned weights. Inner windows score fixed
candidate settings on later observations with only their preceding indicator
context. Outer test prices never enter a candidate score or eligibility check.
"""

from statistics import mean


def windows(end, request, warmup):
    """Build disjoint inner validation blocks and require usable initial context."""
    first = end * request.inner_train_pct // 100
    boundaries = [
        first + (end - first) * index // request.inner_folds for index in range(request.inner_folds + 1)
    ]
    result = list(zip(boundaries[:-1], boundaries[1:], strict=True))
    if first < warmup + 20 or any(right - left < 20 for left, right in result):
        raise ValueError(
            "Nested selection needs 20 initial scored bars after warm-up and at least 20 bars per inner window. Use a longer dataset or fewer inner windows."
        )
    return result


def score(engine, candles, parameters, intervals):
    """Keep every inner-window metric and aggregate only those fixed candidate scores."""
    results = []
    for left, right in intervals:
        result = engine.run(candles[:right], parameters, evaluation_start=left)
        results.append(
            {
                "start": candles[left]["timestamp"],
                "last_candle": candles[right - 1]["timestamp"],
                "bars": right - left,
                **{key: result[key] for key in ("return_pct", "sharpe", "max_drawdown", "trades", "fees")},
            }
        )
    return {
        "return_pct": mean(row["return_pct"] for row in results),
        "sharpe": mean(row["sharpe"] for row in results),
        "max_drawdown": max(row["max_drawdown"] for row in results),
        "trades": sum(row["trades"] for row in results),
        "fees": sum(row["fees"] for row in results),
        "inner_results": results,
    }

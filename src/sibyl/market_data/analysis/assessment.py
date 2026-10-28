"""A transparent heuristic of technical direction, separate from investment risk."""

from math import isclose


def technical_assessment(metrics: dict, sample: dict) -> dict:
    """Weight five disclosed votes; never treat the result as forecast confidence.

    Undefined votes contribute no weight. At least 50 consecutive candles, fresh
    observations and 80% of the original weight are required for an overall score.
    """
    trend, momentum, volume = (metrics[key] for key in ("trend", "momentum", "volume"))
    price = metrics["price"]

    def compare(a, b, tolerance=0.0):
        if a is None or b is None:
            return None
        if abs(a - b) <= tolerance or isclose(a, b, rel_tol=1e-10, abs_tol=1e-12):
            return 50
        return 100 if a > b else 0

    definitions = [
        (
            "ema",
            "EMA alignment",
            25,
            compare(trend["ema9"], trend["ema21"]),
            "EMA 9 vs EMA 21: above 100, equal 50, below 0.",
        ),
        (
            "sma",
            "Medium-term trend",
            20,
            compare(price, trend["sma50"]),
            "Close vs SMA 50: above 100, equal 50, below 0.",
        ),
        (
            "macd",
            "MACD momentum",
            20,
            compare(momentum["macd"], momentum["macd_signal"]),
            "MACD 12/26 vs signal 9: above 100, equal 50, below 0.",
        ),
        (
            "rsi",
            "RSI momentum",
            20,
            compare(momentum["rsi14"], 50, 5),
            "RSI 14: above 55 scores 100, 45–55 scores 50, below 45 scores 0.",
        ),
        (
            "cmf",
            "Volume pressure",
            15,
            compare(volume["cmf20"], 0, 0.05),
            "CMF 20: above 0.05 scores 100, −0.05–0.05 scores 50, below −0.05 scores 0.",
        ),
    ]
    components = [
        {"id": key, "label": label, "weight": weight, "value": value, "rule": rule}
        for key, label, weight, value, rule in definitions
    ]
    coverage = sum(row["weight"] for row in components if row["value"] is not None)
    reason = None
    if sample["observations"] < 50:
        reason = "At least 50 consecutive closed candles are needed for the score."
    elif sample["stale"]:
        reason = "The latest candle is too old for a current technical score."
    elif coverage < 80:
        reason = "Too few indicator inputs are available for a technical score."
    score = (
        None
        if reason
        else round(
            sum(row["weight"] * row["value"] for row in components if row["value"] is not None) / coverage
        )
    )
    label = (
        "Unavailable"
        if score is None
        else ("Bullish" if score >= 65 else "Bearish" if score <= 35 else "Mixed")
    )
    return {
        "version": "technical-bias-v1",
        "score": score,
        "label": label,
        "available_weight": coverage,
        "components": components,
        "reason": reason,
        "note": "Technical direction from historical candles, not a buy/sell recommendation or probability of profit. Higher is more bullish, not safer. Available weights are normalized; correlated signals are not independent evidence.",
    }

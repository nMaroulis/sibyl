"""Hourly descriptive basket risk using exact-source closed daily conversion legs.

No orders, fitted probabilities or account-return claims. Retain compact metrics,
weights, converted closes and a fingerprint, within the existing evidence budget.
"""

import math

from sibyl.accounting.risk.engine import DAY, analyze, closes, converted
from sibyl.forecasting.engine import fingerprint
from sibyl.market_data.archive import milliseconds, now_ms

HISTORICAL = {"volatility", "tail_loss"}


def basket_sample(market, rule, holdings):
    """Revalue the explicitly selected currently held basket and observe its historical tails."""
    selected = {row["asset"]: row for row in holdings if row["asset"] in rule["basket_assets"]}
    if set(selected) != set(rule["basket_assets"]):
        raise ValueError("Every watched basket asset must still be held with a positive current value.")
    value = math.fsum(row["value"] for row in selected.values())
    total = math.fsum(row["value"] for row in holdings)
    if not math.isfinite(value) or value <= 0:
        raise ValueError("The watched basket needs a finite positive value.")
    routes = {asset: row["route"] for asset, row in selected.items()}
    symbols = sorted({leg["symbol"] for route in routes.values() for leg in route})
    if len(symbols) > 16:
        raise ValueError("The watched basket exceeds the 16 historical conversion-leg budget.")
    days = rule["history_days"]
    raw = {symbol: market.candles(symbol, days + 1, "1d") for symbol in symbols}
    histories = {symbol: closes(rows) for symbol, rows in raw.items()}
    end = now_ms() // DAY * DAY
    anchors = range(end - (days + 1) * DAY, end, DAY)
    converted_history = {asset: converted(route, histories, anchors) for asset, route in routes.items()}
    # Some providers ignore limits. Never expand a saved watch beyond its reviewed window.
    converted_history = {
        asset: {t: p for t, p in rows.items() if end - (days + 1) * DAY <= t < end}
        for asset, rows in converted_history.items()
    }
    result = analyze(converted_history, {asset: row["value"] / value for asset, row in selected.items()})
    lag = max(0, (end - milliseconds(result["end"])) // DAY)
    if lag > 2:
        raise ValueError(
            "Basket history is more than two days behind; no historical risk assessment was recorded."
        )
    result.pop("daily_returns")
    inputs = {
        asset: [{"timestamp": t, "close": p} for t, p in sorted(rows.items())]
        for asset, rows in converted_history.items()
    }
    return {
        **result,
        "selected_assets": rule["basket_assets"],
        "requested_days": days,
        "history_lag_days": lag,
        "selected_value": value,
        "share_of_account_value_pct": value / total * 100,
        "entire_account_basket": len(selected) == len(holdings),
        "converted_closes": inputs,
        "routes": routes,
        "fingerprint": fingerprint({"histories": inputs, "valuation": selected, "source": rule["source"]}),
        "coverage_note": "Selected assets only, renormalized to current basket weights. This is a hypothetical daily-rebalanced historical basket, not account performance or a future loss guarantee.",
    }

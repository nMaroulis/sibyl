"""Value-weighted asset concentration, with no return, correlation or suitability claims."""

import math


def diversification(holdings, *, complete=True):
    """Summarize the whole valued basket; incomplete coverage never produces a portfolio score.

    Identical assets across accounts are combined. Cash and stablecoins remain
    separate assets. HHI is sum(weight²) on a 0–100 scale; its reciprocal is the
    effective number of equally weighted assets, not independent risk factors.
    """
    result = {
        "version": "asset-concentration-1",
        "status": "incomplete" if not complete else "empty",
        "assets": 0,
        "hhi": None,
        "effective_assets": None,
        "largest_pct": None,
        "top_three_pct": None,
        "largest_asset": None,
        "note": "Value concentration only. Cash/stablecoins count as separate assets; this does not measure correlations, volatility, liquidity or investment risk.",
    }
    amounts = {}
    for row in holdings:
        value, asset = row.get("value"), row.get("asset")
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
            or value < 0
            or not isinstance(asset, str)
            or not asset
        ):
            return {**result, "status": "invalid"}
        amounts[asset] = amounts.get(asset, 0) + value
    amounts = {asset: value for asset, value in amounts.items() if value > 0}
    result["assets"] = len(amounts)
    if not complete or not amounts:
        return result
    scale = max(amounts.values())
    if not math.isfinite(scale):
        return {**result, "status": "invalid"}
    total = math.fsum(value / scale for value in amounts.values())
    weights = sorted(
        ((asset, value / scale / total) for asset, value in amounts.items()),
        key=lambda item: (-item[1], item[0]),
    )
    hhi = math.fsum(weight**2 for _, weight in weights)
    return {
        **result,
        "status": "observed",
        "hhi": hhi * 100,
        "effective_assets": 1 / hhi,
        "largest_pct": weights[0][1] * 100,
        "largest_asset": weights[0][0],
        "top_three_pct": math.fsum(weight for _, weight in weights[:3]) * 100,
    }

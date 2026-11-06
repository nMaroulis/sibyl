"""Causal cost-aware reference portfolios over the strategy's exact evaluation window.

All capital exists at the start; cash earns zero interest. Calendar-independent
schedules use a disclosed candle cadence. Reference fills use opens, configured
costs and final-close liquidation, without signal fitting or venue execution.
"""

import math

from sibyl.exchanges.data import TIMEFRAMES
from sibyl.services.markets.analytics import performance_metrics

VERSION = "reference-portfolios-1"


def summary(label, kind, curve, fills, request, *, cadence=None):
    """Describe actual reference cash flows and returns, with the same initial capital and clock."""
    final = curve[-1]["value"]
    metrics = performance_metrics(
        [request.capital, *[row["value"] for row in curve]], [], 365 * 86400 / TIMEFRAMES[request.timeframe]
    )
    return {
        "label": label,
        "kind": kind,
        "version": VERSION,
        "initial_capital": request.capital,
        "final_equity": final,
        "return_pct": (final / request.capital - 1) * 100,
        "max_drawdown": metrics["max_drawdown"],
        "sharpe": None if kind == "cash" else metrics["sharpe"],
        "fees": sum(row["fee"] for row in fills),
        "execution_count": len(fills),
        "curve": curve,
        "fills": fills,
        "cadence_bars": cadence,
        "assumptions": "Same evaluation window and initial capital. Cash earns zero; no later contributions. Scheduled opens, configured fees/slippage, final-close liquidation. Not an optimized strategy or a recommendation.",
    }


def simulate(candles, request, kind):
    """Build an installment or fixed 50/50 reference using only the current scheduled open."""
    cadence = request.benchmark_interval
    fee, slip = request.fee_bps / 10000, request.slippage_bps / 10000
    cash, units = request.capital, 0.0
    installments = math.ceil(len(candles) / cadence)
    tranche = request.capital / installments
    curve, fills = [], []

    def trade(row, side, quantity, price):
        nonlocal cash, units
        if quantity <= 1e-14:
            return
        cost = quantity * price
        commission = cost * fee
        if side == "buy":
            cash -= cost + commission
            units += quantity
        else:
            cash += cost - commission
            units -= quantity
        # Precision noise must not become virtual credit or leverage.
        if cash < -max(1e-8, request.capital * 1e-12) or units < -1e-12:
            raise ValueError("Reference portfolio exceeded its cash or unit budget.")
        cash, units = max(0.0, cash), max(0.0, units)
        fills.append(
            {
                "timestamp": row["timestamp"],
                "side": side,
                "quantity": quantity,
                "price": price,
                "fee": commission,
            }
        )

    for index, row in enumerate(candles):
        opened = float(row["open"])
        if index % cadence == 0:
            if kind == "installments":
                price = opened * (1 + slip)
                trade(row, "buy", min(tranche, cash) / (price * (1 + fee)), price)
            else:
                # Rebalance towards half the pre-trade portfolio value. Costs
                # can leave a small disclosed deviation from exactly 50/50.
                desired = (cash + units * opened) * 0.5 / opened
                difference = desired - units
                if difference > 0:
                    price = opened * (1 + slip)
                    trade(row, "buy", min(difference, cash / (price * (1 + fee))), price)
                else:
                    trade(row, "sell", min(-difference, units), opened * (1 - slip))
        curve.append({"timestamp": row["timestamp"], "value": cash + units * float(row["close"])})
    if units:
        trade(candles[-1], "sell", units, float(candles[-1]["close"]) * (1 - slip))
        curve[-1]["value"] = cash
    return summary(
        "Scheduled installments" if kind == "installments" else "50/50 asset & cash",
        kind,
        curve,
        fills,
        request,
        cadence=cadence,
    )


def references(candles, request, start, buy_hold_curve):
    """Return four named, versioned references without changing the strategy's execution."""
    window = candles[start:]
    fee, slip = request.fee_bps / 10000, request.slippage_bps / 10000
    buy = float(window[0]["open"]) * (1 + slip)
    units = request.capital / (buy * (1 + fee))
    sell = float(window[-1]["close"]) * (1 - slip)
    hold_fills = [
        {
            "timestamp": window[0]["timestamp"],
            "side": "buy",
            "quantity": units,
            "price": buy,
            "fee": units * buy * fee,
        },
        {
            "timestamp": window[-1]["timestamp"],
            "side": "sell",
            "quantity": units,
            "price": sell,
            "fee": units * sell * fee,
        },
    ]
    return {
        "buy_hold": summary("Buy & hold", "buy_hold", buy_hold_curve, hold_fills, request),
        "cash": summary(
            "Cash · zero interest",
            "cash",
            [{"timestamp": row["timestamp"], "value": request.capital} for row in window],
            [],
            request,
        ),
        **{kind: simulate(window, request, kind) for kind in ("installments", "balanced")},
    }

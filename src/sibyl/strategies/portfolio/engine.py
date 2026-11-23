"""Cost-aware target allocation at scheduled opens, with previous-close drift decisions.

The simulator has no exchange/client dependency. Sells fund buys, quantities are
fractional and a post-cost NAV solve avoids leverage or asset-order bias. Cash
has zero yield. A planned final-close liquidation is shared by both strategies.
"""

import hashlib
import json
import math

import numpy as np

from sibyl.exchanges.data import TIMEFRAMES
from sibyl.market_data.archive import iso, milliseconds, step_ms

VERSION = "multi-asset-rebalance-1"


def risk_metrics(curve, capital, timeframe):
    """Use one return per full evaluated bar, including initial/final execution costs."""
    values = np.asarray([capital, *[row["value"] for row in curve]], dtype=float)
    returns = values[1:] / values[:-1] - 1
    periods = 365 * 86400 / TIMEFRAMES[timeframe]
    peak = np.maximum.accumulate(values)
    dd = (values / peak - 1) * 100
    std = float(returns.std(ddof=1)) if len(returns) > 1 else 0
    downside = float(np.sqrt(np.mean(np.minimum(returns, 0) ** 2)))
    exponent = math.log(values[-1] / capital) * periods / len(returns)
    annual = math.expm1(exponent) * 100 if abs(exponent) < 20 else None
    return {
        "final_equity": float(values[-1]),
        "net_profit": float(values[-1] - capital),
        "return_pct": float((values[-1] / capital - 1) * 100),
        "max_drawdown": float(-dd.min()),
        "drawdown_curve": [float(x) for x in dd[1:]],
        "sharpe": float(returns.mean() / std * math.sqrt(periods)) if std > 1e-15 else None,
        "sortino": float(returns.mean() / downside * math.sqrt(periods)) if downside > 1e-15 else None,
        "annualized_volatility_pct": std * math.sqrt(periods) * 100,
        "annualized_return_pct": annual,
        "return_observations": len(returns),
    }


class PortfolioSimulation:
    """One fresh, long-only ledger per simulation; no shared virtual or exchange funds."""

    def __init__(self, recipe, prices, timestamps, *, rebalance=True):
        self.recipe, self.prices, self.timestamps = recipe, prices, timestamps
        self.symbols = [leg.symbol for leg in recipe.legs]
        self.target = {leg.symbol: leg.weight_pct / 100 for leg in recipe.legs}
        self.units = dict.fromkeys(self.symbols, 0.0)
        self.cash = recipe.capital
        self.fee, self.slip = recipe.fee_bps / 10000, recipe.slippage_bps / 10000
        self.fills, self.events, self.curve, self.allocations = [], [], [], []
        self.rebalance = rebalance
        self.turnover = 0.0
        self.tolerance = max(1e-8, recipe.capital * 1e-12)

    def nav(self, marks):
        return self.cash + math.fsum(self.units[s] * marks[s] for s in self.symbols)

    def fill(self, symbol, quantity, marks, index, reason, decision_at):
        if quantity == 0:
            return
        side = "buy" if quantity > 0 else "sell"
        amount = abs(quantity)
        reference = marks[symbol]
        price = reference * (1 + self.slip if quantity > 0 else 1 - self.slip)
        notional = amount * price
        fee = notional * self.fee
        self.cash += -notional - fee if quantity > 0 else notional - fee
        self.units[symbol] += quantity
        if self.cash < -self.tolerance or self.units[symbol] < -1e-12 or not math.isfinite(self.cash):
            raise ValueError("Portfolio simulation exceeded its cash/unit budget.")
        self.cash = max(0.0, self.cash)
        self.units[symbol] = max(0.0, self.units[symbol])
        self.fills.append(
            {
                "timestamp": self.timestamps[index],
                "execution_at": iso(
                    milliseconds(self.timestamps[index])
                    + (step_ms(self.recipe.timeframe) if reason == "liquidation" else 0)
                ),
                "phase": "close" if reason == "liquidation" else "open",
                "bar": index,
                "decision_at": decision_at,
                "symbol": symbol,
                "side": side,
                "quantity": amount,
                "reference_price": reference,
                "price": price,
                "notional": notional,
                "fee": fee,
                "slippage_cost": amount * abs(price - reference),
                "reason": reason,
            }
        )

    def rebalance_at(self, marks, index, reason, decision_at, drift):
        """Solve post-cost target NAV, then sell before buying at the current open.

        Desired quantities target post-cost marked equity. The monotonic scalar
        equation includes directional slippage and quote fees on every trade.
        It avoids spending cash in arbitrary symbol order or borrowing for fees.
        """
        before = self.nav(marks)
        buy_cost = self.slip + self.fee + self.slip * self.fee
        sell_cost = self.slip + self.fee - self.slip * self.fee

        def cost(equity):
            changes = [self.target[s] * equity - self.units[s] * marks[s] for s in self.symbols]
            return math.fsum(change * buy_cost if change > 0 else -change * sell_cost for change in changes)

        low, high = 0.0, before
        for _ in range(64):
            midpoint = (low + high) / 2
            if midpoint + cost(midpoint) > before:
                high = midpoint
            else:
                low = midpoint
        desired = {s: self.target[s] * low / marks[s] for s in self.symbols}
        changes = {s: desired[s] - self.units[s] for s in self.symbols}
        begin = len(self.fills)
        for buying in (False, True):
            for symbol in self.symbols:
                change = changes[symbol]
                if (change > 0) == buying and abs(change * marks[symbol]) > self.tolerance:
                    self.fill(symbol, change, marks, index, reason, decision_at)
        after = self.nav(marks)
        costs = math.fsum(row["fee"] + row["slippage_cost"] for row in self.fills[begin:])
        if abs(before - after - costs) > self.tolerance * 10:
            raise ValueError("Portfolio cost conservation check failed.")
        traded = math.fsum(abs(row["quantity"] * row["reference_price"]) for row in self.fills[begin:])
        if reason == "rebalance":
            self.turnover += traded / before * 100
        self.events.append(
            {
                "timestamp": self.timestamps[index],
                "decision_at": decision_at,
                "bar": index,
                "reason": reason,
                "drift_pct": drift,
                "equity_before": before,
                "equity_after": after,
                "cost": costs,
                "traded_mark_notional": traded,
                "fills": len(self.fills) - begin,
            }
        )

    def run(self):
        for index, timestamp in enumerate(self.timestamps):
            opened = {s: float(self.prices[s][index]["open"]) for s in self.symbols}
            closed = {s: float(self.prices[s][index]["close"]) for s in self.symbols}
            if index == 0:
                self.rebalance_at(opened, index, "initial", None, None)
            elif self.rebalance:
                previous = {s: float(self.prices[s][index - 1]["close"]) for s in self.symbols}
                equity = self.nav(previous)
                weights = {s: self.units[s] * previous[s] / equity for s in self.symbols}
                cash_target = 1 - math.fsum(self.target.values())
                drift = (
                    max(
                        [abs(weights[s] - self.target[s]) for s in self.symbols]
                        + [abs(self.cash / equity - cash_target)]
                    )
                    * 100
                )
                due = (
                    index % self.recipe.interval_bars == 0
                    if self.recipe.rule == "interval"
                    else drift >= self.recipe.drift_pct
                )
                if due:
                    self.rebalance_at(
                        opened,
                        index,
                        "rebalance",
                        iso(milliseconds(self.timestamps[index - 1]) + step_ms(self.recipe.timeframe)),
                        drift,
                    )
            value = self.nav(closed)
            if not math.isfinite(value) or value <= 0:
                raise ValueError("Portfolio equity must stay positive and finite.")
            self.curve.append({"timestamp": timestamp, "value": value})
            self.allocations.append(
                {
                    "timestamp": timestamp,
                    "cash_pct": self.cash / value * 100,
                    "weights": {s: self.units[s] * closed[s] / value * 100 for s in self.symbols},
                }
            )
        terminal = {"cash": self.cash, "units": dict(self.units), "weights": self.allocations[-1]}
        closing = {s: float(self.prices[s][-1]["close"]) for s in self.symbols}
        for symbol in self.symbols:
            self.fill(symbol, -self.units[symbol], closing, len(self.timestamps) - 1, "liquidation", None)
        self.curve[-1]["value"] = self.cash
        metrics = risk_metrics(self.curve, self.recipe.capital, self.recipe.timeframe)
        self.curve = [
            dict(row, drawdown_pct=dd)
            for row, dd in zip(self.curve, metrics.pop("drawdown_curve"), strict=True)
        ]
        return {
            **metrics,
            "curve": self.curve,
            "allocations": self.allocations,
            "fills": self.fills,
            "rebalance_events": self.events,
            "pre_liquidation": terminal,
            "fees": math.fsum(row["fee"] for row in self.fills),
            "slippage_cost": math.fsum(row["slippage_cost"] for row in self.fills),
            "gross_traded_notional": math.fsum(row["notional"] for row in self.fills),
            "rebalance_turnover_pct": self.turnover,
            "rebalance_count": sum(
                event["reason"] == "rebalance" and event["fills"] > 0 for event in self.events
            ),
            "execution_count": len(self.fills),
            "final_cash": self.cash,
        }


def simulate(recipe, prices, timestamps):
    """Run the actual strategy and cost-matched buy-and-hold from identical inputs/cash."""
    result = PortfolioSimulation(recipe, prices, timestamps).run()
    hold = PortfolioSimulation(recipe, prices, timestamps, rebalance=False).run()
    return {
        **result,
        "benchmarks": {
            "buy_hold": hold,
            "cash": {
                "final_equity": recipe.capital,
                "return_pct": 0.0,
                "max_drawdown": 0.0,
                "fees": 0.0,
                "execution_count": 0,
                "sharpe": None,
                "sortino": None,
                "curve": [{"timestamp": t, "value": recipe.capital, "drawdown_pct": 0.0} for t in timestamps],
            },
        },
        "excess_return_pct": result["return_pct"] - hold["return_pct"],
        "decision_fingerprint": hashlib.sha256(
            json.dumps([result["fills"], result["curve"]], sort_keys=True, allow_nan=False).encode()
        ).hexdigest(),
    }

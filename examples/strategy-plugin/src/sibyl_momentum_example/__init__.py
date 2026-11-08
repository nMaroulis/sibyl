"""Causal trailing momentum: a real, minimal local research extension."""

from sibyl.strategies.plugins import Parameter, PluginSpec, StrategyPlugin


class Momentum(StrategyPlugin):
    """Enter/exit around a configurable trailing close return, without hidden state."""

    @property
    def spec(self):
        return PluginSpec(
            name="Local momentum",
            description="Buy positive trailing momentum above a threshold; sell below its negative threshold.",
            warmup=51,
            parameters={
                "period": Parameter(label="Momentum lookback", minimum=5, maximum=50, default=14),
                "threshold_pct": Parameter(
                    label="Return threshold · %", kind="float", minimum=0, maximum=20, default=1
                ),
            },
        )

    def signal(self, candles, parameters):
        period = parameters["period"]
        change = (candles[-1]["close"] / candles[-1 - period]["close"] - 1) * 100
        if change > parameters["threshold_pct"]:
            return 1
        if change < -parameters["threshold_pct"]:
            return -1
        return 0

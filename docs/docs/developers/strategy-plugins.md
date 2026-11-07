---
title: Custom strategy plugins
description: Trusted installed Python extensions for causal, source-pinned historical backtests.
---

# Custom strategy plugins

Sibyl accepts **installed local Python packages** advertising the `sibyl.strategies` entry-point group. Plugins are historical research extensions. They do not become paper/exchange jobs or optimization candidates. The six built-in algorithms retain their existing execution paths. Freqtrade integration is separate pending work.

## Install and enable

Review [the working momentum example](https://github.com/nMaroulis/sibyl/tree/main/examples/strategy-plugin), then install it in **the same Python environment as Sibyl**. From a source checkout:

```bash
uv pip install --no-deps ./examples/strategy-plugin
```

`--no-deps` keeps the already-installed Sibyl checkout/package. For an ordinary virtual environment, use `python -m pip install --no-deps ./examples/strategy-plugin` instead. Add this explicit allowlist to your Sibyl environment or `.env`, then restart the backend:

```dotenv
SIBYL_STRATEGY_PLUGINS=["local-momentum"]
```

Open **Strategies → Custom Python strategies**. The same shared pair, interval, current/saved/Demo input, virtual capital, fees, slippage and close-based risk limits apply; plugin controls are separate. Run the backtest, inspect actual buy/sell markers and round trips, export JSON, reopen saved results or **Rerun exact custom input**. No LLM is needed. Current/Demo pages allow 60–720 candles; immutable saved inputs allow up to 2,000. Demo is explicitly synthetic and never changes the active feed/accounts.

:::warning[Trusted backend code]

An installed enabled plugin runs with the Python backend process's privileges. Install only reviewed code you trust. The prefix interface is a data contract, **not a security sandbox, process isolation or a hard timeout**. No browser code upload/editor or automatic package installation is provided. A blocking plugin can occupy its request until it returns. Removing a name from the allowlist and restarting prevents future execution; retained results remain readable.

:::

## Write a plugin

```python title="my_package/__init__.py"
from sibyl.strategies.plugins import Parameter, PluginSpec, StrategyPlugin

class Momentum(StrategyPlugin):
    @property
    def spec(self):
        return PluginSpec(
            name="Momentum",
            description="Follow a bounded trailing close return.",
            warmup=51,
            parameters={
                "period": Parameter(label="Lookback", minimum=5, maximum=50, default=14),
            },
        )

    def signal(self, candles, parameters):
        change = candles[-1]["close"] / candles[-1-parameters["period"]]["close"] - 1
        return 1 if change > 0.01 else -1 if change < -0.01 else 0
```

```toml title="pyproject.toml"
[project.entry-points."sibyl.strategies"]
my-momentum = "my_package:Momentum"
```

Use a lowercase entry-point name with letters, digits and hyphens. The manifest has at most eight bounded numeric controls, fixed warmup of 30–200 bars and a readable name/description. Warmup must cover **all** permitted parameter settings. Each run creates a fresh instance; signals must be deterministic Python integers: BUY=1, SELL=-1, HOLD=0. No I/O, clocks, random state, credentials or hidden cross-run state belong in a strategy. Candles are tuples of immutable mappings containing only timestamp/OHLCV through that decision's close. The current final candle is used for terminal liquidation rather than a new signal.

## Execution and provenance

The existing fee/slippage-aware next-open engine consumes the validated directions. A decision at close t may fill at open t+1; close-based stops/take-profits follow the same rule. Final holdings liquidate at the last close. Charts and metrics derive from actual simulated fills. No signal can bypass the long-only simulator or submit an exchange order.

The registry imports only explicit allowlist names at startup. Disabled packages are listed without importing them. Missing, duplicate or invalid entry points remain unavailable with sanitized errors. Install a regular package/wheel; editable installs without recorded Python source files are not supported for pinned research. Allowed packages must expose an inspectable Python distribution: at most 256 `.py` files and two MiB of source. A revision hashes its manifest, package source, entry point/distribution version, Sibyl/Python and NumPy/Pandas versions. It does not prove package trust or freeze every transitive/external dependency.

Before and after a run, source/revision checks reject changed code. Results retain immutable dataset identity, exact parameters, source labels, per-close directions and a signal fingerprint under the separate `plugin_backtest` kind. Offline reruns require the matching installed revision and reproduce the original signal fingerprint; changed decisions reject success. This catches observed nondeterminism, not every possible external dependency. Repeated research can still overfit. At most 100 custom results are retained; users explicitly remove old results.

## API and agents

- `GET /api/v1/strategies/plugins`: discovered/ready/disabled/unavailable manifests.
- `POST /api/v1/strategies/plugins/backtests`: reviewed `plugin_id`, `revision`, numeric `values`, explicit input and simulation costs.
- `GET /api/v1/strategies/plugins/backtests`: recent compact summaries.
- `GET /api/v1/strategies/plugins/backtests/{id}`: full retained/exportable evidence.
- `POST /api/v1/strategies/plugins/backtests/{id}/rerun`: exact saved input with current revision/signal checks.
- `DELETE /api/v1/strategies/plugins/backtests/{id}`: remove only that local research result.

Broker's existing native `strategy_guide` and `backtest_report` inspect plugin metadata/results. Tools omit full signal/price/equity series and never instantiate plugins, run research, install packages or alter the allowlist. No custom ProtoLink execution plumbing is introduced.

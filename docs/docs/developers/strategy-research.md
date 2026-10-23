# Strategy research engine

`src/sibyl/strategies/` owns the domain: `catalog.py` declares the six implemented algorithms, `signals.py` calculates causal indicators/signals, `backtest.py` owns deterministic historical execution and evidence, `paper.py` owns ongoing isolated evaluation, and `journal.py` persists run events and observations. There is no generated performance fixture: Demo supplies explicitly synthetic OHLCV to the same engine.

`BacktestEngine.run()` validates positive finite prices, chronological unique timestamps and consistent intervals. Signals use the prior closed candle; historical entries/exits fill at the following open with configured adverse slippage and fees. Positions use all available quote capital, without leverage or shorts. Close-based risk exits also wait until the following open. A remaining position is sold at the final close, explicitly recorded as `End of backtest`. These assumptions do not model order books, partial fills or intrabar stops.

The response retains the OHLCV price trace, every execution, benchmark equity and matched round trips. Round-trip net P&L subtracts both fees; summing it equals final equity minus initial capital. Summary metrics include cash profit factor, expectancy in quote units, exposure by evaluated bars, turnover, average holding time and annualized return when finite. Existing risk metrics include Sharpe, Sortino, Calmar and percentage-return profit factor. The UI labels cash P&L profit factor separately. Undefined ratios remain null.

The buy-and-hold comparator uses the identical evaluated period and entry/exit costs. Warm-up is excluded from performance, and shown separately. Full results remain in SQLite; charts do not recalculate performance from a sampled display. At most 400 execution markers and the latest 200 round trips are rendered for responsiveness; complete executions and round trips can be exported. The time brush changes the chart viewport. Saved comparisons require the same immutable dataset fingerprint and initial capital.

## Immutable inputs and reruns

Current-feed backtests first retain an exact contiguous dataset. Saved datasets support 60–20,000 bars without provider reads; current-feed requests support 60–720. A rerun loads that run's recorded parameters and original immutable dataset, calculates with the current engine, records `engine_revision` and a persisted `rerun_of` link, and creates a new result. It never edits the old result. Identical input/parameters/engine produce identical calculations; future engine changes may change results. Older runs without retained input cannot be replayed.

Broker's native ProtoLink `backtest_report` tool reads selected results and at most ten round trips without running experiments or making trades. Current page selection pins the requested experiment.

## API

| Method | `/api/v1` path                     | Behavior                                                                         |
| ------ | ---------------------------------- | -------------------------------------------------------------------------------- |
| POST   | `/strategies/backtest`             | Fetch configured feed input, snapshot and simulate                               |
| POST   | `/strategies/backtest/demo`        | Snapshot explicit synthetic input; no account activation or feed-setting changes |
| POST   | `/strategies/backtest/dataset`     | Simulate a retained input offline                                                |
| POST   | `/strategies/backtests/{id}/rerun` | Replay original input and parameters, saving a new result                        |
| POST   | `/strategies/jobs/demo`            | Start the actual paper evaluator pinned to Demo prices                           |

Paper Demo runs have their own capital, decisions and journal. Their source is pinned independently of account activation and the default market feed. Other paper jobs retain the existing source-change pause behavior. Approved exchange execution is implemented separately in `strategies/execution/`; see the [execution guide](../guides/strategy-execution.md).

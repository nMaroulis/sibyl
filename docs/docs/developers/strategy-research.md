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

## Chronological parameter validation

`strategies/validation.py` defines strict `WalkForwardRequest`/`ValidationParameters`, a deterministic `WalkForwardEngine` and the `StrategyValidation` persistence boundary owned by `Strategies.validation`. The API passes the request to this domain; it does not implement selection logic. No provider read is required. `validation/options` exposes the actual strategy-specific searchable fields and limits. Unknown/irrelevant fields, duplicate/nonfinite values, invalid period combinations and excessive grids fail before simulation.

The initial training boundary is `floor(count * initial_train_pct / 100)`. The remainder is divided into disjoint test intervals using integer boundaries; every remaining bar is tested exactly once. Training expands from the dataset start through the boundary immediately before each test. Candidates share the maximum warm-up of all candidates and fixed settings, then are ordered by the requested training score and stable candidate ID; optional minimum completed training trades controls eligibility. No test simulation is evaluated until that window's selection is fixed.

`BacktestEngine.run(..., evaluation_start=index)` computes causal indicators over the supplied prefix but starts in cash at that index. Only its suffix contributes fills, benchmark and performance. Training receives no test candles; selected/fixed test simulations receive no candles after their own test end. Tests force a cost-aware close and reset capital per window. Their summary is an unweighted mean, never a stitched deployment account. Prior tests may enter later training history. See the [user guide](../guides/strategy-validation.md) for interpretation.

The work guard counts `sum(evaluated_candidates * train_end + 2 * test_end)` input rows, including indicator context; the 60,000-row bound is checked before simulation. Grid requests allow two axes with four distinct values each. Seeded random search allows four axes with eight values each (up to 4,096 finite combinations), but evaluates at most sixteen sampled configurations. Both modes allow five windows, 20 scored initial training bars and 20 bars per test. A nonblocking per-workspace lock prevents concurrent searches in the supported single-worker deployment. This is bounded synchronous research, not a general background job system.

### Candidate-plan contract

`strategies/research/search.py` validates the complete finite space without reading candles or running backtests. Parameter names sort lexicographically; value lists keep their supplied order. Cartesian indices are zero-based internally and one-based in evidence. Grid mode evaluates all combinations in that order. Fixed mode retains one empty override.

Random mode requires `search_method: random`, `sample_size` (1–16, no greater than the space size), and a strict integer `seed` (0–4,294,967,295). Grid mode rejects random-only fields. Use the default `grid` method with an empty `grid` mapping for fixed settings. Every combination is checked with the same `ValidationParameters`, even if it would not be drawn. No invalid choices are discarded or silently retried.

Sampler `sha256-rank-v1` sorts space indices by the byte digest of UTF-8 `sha256-rank-v1:{seed}:{zero_based_index}` (index breaks a hash tie) and takes the requested prefix. This yields a deterministic pseudorandom sample without replacement, independent of Python RNG state or price data. The plan is constructed once for scoring and reused across all folds. Candidate IDs follow draw/evaluation order, preserving deterministic score ties. It samples explicit finite choices, not continuous distributions or adaptive/Bayesian proposals.

The artifact records method, sampler, seed, space/sample sizes, coverage, candidate IDs/space indices/overrides, space fingerprint and plan fingerprint. Fingerprints use SHA-256 of sorted compact JSON with non-finite values forbidden. The space recipe covers normalized base parameters and ordered axis values. The plan fingerprint covers the evidence before the fingerprint field itself. These are reproducibility/consistency checks, not authentication against a malicious workspace owner.

Completed results commit atomically to `strategy_validations`, with compact metadata and bounded search-plan evidence separate from full rankings/test executions. A failed or interrupted request leaves no partial record. Summary reads return the latest 50 rows with an optional Demo filter. Replay reconstructs and compares the saved candidate plan before loading the immutable dataset and using the current engine; a mismatch refuses replay. Earlier studies without plan metadata retain their original grid behavior. A rerun saves a new `rerun_of` result without overwriting a study or changing a job/account/source. Broker's native `validation_report` reads sampling/summary/window evidence without invoking research or execution.

| Method | `/api/v1` path                       | Purpose                                                       |
| ------ | ------------------------------------ | ------------------------------------------------------------- |
| GET    | `/strategies/validation/options`     | Implemented search fields and bounds                          |
| POST   | `/strategies/validations`            | Bounded offline parameter search and chronological evaluation |
| GET    | `/strategies/validations?demo=true`  | Latest 50 compact summaries; optional Demo boundary           |
| GET    | `/strategies/validations/{id}`       | Complete retained study, also usable as a JSON export         |
| POST   | `/strategies/validations/{id}/rerun` | Recompute exact original input/settings and retain the parent |

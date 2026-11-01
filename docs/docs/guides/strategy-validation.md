# Walk-forward strategy validation

Open **Strategies → Build & backtest → Validate on unseen data**. This optional panel uses the exact immutable dataset from your selected experiment or saved research input. It works offline and follows the workspace's real-data or clearly labeled Demo boundary.

1. Run a backtest or choose a saved dataset. Check the pair, source, timeframe and input fingerprint.
2. Keep your fixed settings, compare a small grid of indicator parameters, or choose **Sample a larger parameter space**. Grid search accepts up to two parameters with one to four explicit values each. Random search accepts up to four parameters with one to eight values each, an evaluated-candidate budget and a reproducibility seed. The backend lists only parameters used by that algorithm. These choices are not recommended trading settings.
3. Choose the initial training share and one to five later test windows. One window is a chronological holdout. Multiple windows expand the training prefix before selecting settings again.
4. Optionally expand **Selection rules & limits** to select highest net return, highest Sharpe or lowest maximum drawdown, and a minimum number of completed training round trips.
5. Select **Run walk-forward test**. Inspect each window, its price-chart executions, training ranking, fixed-settings comparator and cost-aware buy-and-hold result. **Ask Broker** reads the saved study through its native ProtoLink tool.

## What is selected and tested

Training always precedes its test. Every candidate is scored over the same training period after the longest candidate/fixed-configuration warm-up. Selection uses the training objective only; equal scores use recorded candidate order. The chosen settings are then simulated on the next test window. Other candidates are not ranked using that test's results.

## Seeded random search

Random search samples **1–16 distinct configurations** from the finite combinations you enter, without replacement. It accepts at most 4,096 possible combinations, while the same simulation-work limit still applies to the evaluated sample. **Add parameter** reveals additional axes used by the selected algorithm; choose **None** to exclude an axis. The candidate budget is capped by the entered space size in the UI.

The seed and ordered choices fix the sample before any prices are scored. That same sample is reused in every test window; it is not changed based on winning scores or later prices. Every possible combination must satisfy the strategy's parameter rules, including combinations that would not be sampled. Invalid ranges are rejected instead of silently reducing the search space.

Results show the evaluated count, total space, percentage coverage, seed and plan fingerprint. Expand **Evaluated candidate plan** to inspect each candidate's values and one-based space index. Training rankings refer only to that recorded plan. A seed preserves reproducibility; it does not make a configuration better. Changing seeds after inspecting results is another experiment and can overfit.

This initial sampler selects explicit numeric options through a deterministic pseudorandom ordering; it does not search continuous distributions or use Bayesian optimization. Scikit-learn's [parameter-search overview](https://scikit-learn.org/stable/modules/grid_search.html#randomized-parameter-optimization) explains the distinction between exhaustive enumeration and sampled candidates; Sibyl implements its own small finite-space sampler and does not add scikit-learn as a dependency.

Earlier candles supply indicator context without creating inherited test positions or training profits. A signal from the last training close may fill at the first test open. Each test starts in cash with the same virtual capital and liquidates at its final close. Configured entry/exit fees, adverse slippage and close-based risk exits use the regular backtest engine. The fixed-settings strategy and buy-and-hold comparator use the same test period and costs.

The summary displays **unweighted means of independent window returns**, not a compounded equity curve. The chart shows one test window at a time. Earlier test windows become training history for later windows, as they would in a chronological expanding-window procedure. Repeatedly choosing inputs, grids or methods after reading results can still overfit; this is not an untouched final dataset or a forecast. With a zero minimum training-trade count, an inactive candidate can win; inspect round trips alongside scores.

## Limits, saved evidence and reruns

Searches evaluate at most 16 candidates and five test windows. The initial training period needs at least 20 scored bars after common warm-up; each test needs at least 20 bars. A request may process at most 60,000 candle rows across training, selected-test and fixed-test simulations, including indicator context. Reduce the evaluated-candidate budget, window count or dataset length when this bound is exceeded. Invalid parameter combinations reject the request rather than disappearing from its ranking. Only one validation runs at a time in the local backend.

Completed studies persist in SQLite with the input fingerprint, exact request, candidate plan/fingerprints, training rankings, selected parameters, test fills/metrics, fixed-settings comparisons, method version and engine revision. **Saved validations** lists the latest 50 studies for the current real-data or Demo workspace. **Rerun exact study** checks that the recipe/sampler still reproduces the saved candidate plan before computing a new study from the original immutable input. It records the parent ID and retains the original. A mismatched plan fails visibly. A future backtest-engine revision may change execution results. Failed or interrupted searches save no partial study and are not replayed on startup.

Export the complete evidence as JSON or the test-window summary as CSV. **Ask Broker** exposes the recorded sampling method, coverage and candidate plan through the existing native ProtoLink evidence tool. Research never changes running strategies, submits orders, activates an account or changes market-source settings. Continuous rebalanced deployment simulations, Bayesian/distribution-based optimization, nested validation, additional benchmarks and strategy plugins remain pending in the [implementation checklist](../developers/backend-roadmap.md).

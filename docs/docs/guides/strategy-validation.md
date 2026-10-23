# Walk-forward strategy validation

Open **Strategies → Build & backtest → Validate on unseen data**. This optional panel uses the exact immutable dataset from your selected experiment or saved research input. It works offline and follows the workspace's real-data or clearly labeled Demo boundary.

1. Run a backtest or choose a saved dataset. Check the pair, source, timeframe and input fingerprint.
2. Keep your fixed settings, or compare a small grid of indicator parameters. Choose up to two parameters and enter one to four comma-separated values for each. These are explicit search values, not recommended trading settings. The backend lists only parameters used by that algorithm.
3. Choose the initial training share and one to five later test windows. One window is a chronological holdout. Multiple windows expand the training prefix before selecting settings again.
4. Optionally expand **Selection rules & limits** to select highest net return, highest Sharpe or lowest maximum drawdown, and a minimum number of completed training round trips.
5. Select **Run walk-forward test**. Inspect each window, its price-chart executions, training ranking, fixed-settings comparator and cost-aware buy-and-hold result. **Ask Broker** reads the saved study through its native ProtoLink tool.

## What is selected and tested

Training always precedes its test. Every candidate is scored over the same training period after the longest candidate/fixed-configuration warm-up. Selection uses the training objective only; equal scores use recorded candidate order. The chosen settings are then simulated on the next test window. Other candidates are not ranked using that test's results.

Earlier candles supply indicator context without creating inherited test positions or training profits. A signal from the last training close may fill at the first test open. Each test starts in cash with the same virtual capital and liquidates at its final close. Configured entry/exit fees, adverse slippage and close-based risk exits use the regular backtest engine. The fixed-settings strategy and buy-and-hold comparator use the same test period and costs.

The summary displays **unweighted means of independent window returns**, not a compounded equity curve. The chart shows one test window at a time. Earlier test windows become training history for later windows, as they would in a chronological expanding-window procedure. Repeatedly choosing inputs, grids or methods after reading results can still overfit; this is not an untouched final dataset or a forecast. With a zero minimum training-trade count, an inactive candidate can win; inspect round trips alongside scores.

## Limits, saved evidence and reruns

Searches allow at most 16 combinations and five test windows. The initial training period needs at least 20 scored bars after common warm-up; each test needs at least 20 bars. A request may process at most 60,000 candle rows across training, selected-test and fixed-test simulations, including indicator context. Reduce the grid, window count or dataset length when this bound is exceeded. Invalid parameter combinations reject the request rather than disappearing from its ranking. Only one validation runs at a time in the local backend.

Completed studies persist in SQLite with the input fingerprint, exact request, training rankings, selected parameters, test fills/metrics, fixed-settings comparisons, method version and engine revision. **Saved validations** lists the latest 50 studies for the current real-data or Demo workspace. **Rerun exact study** computes a new study from the original immutable input and settings, records its parent ID and retains the original. A future engine revision may change results. Failed or interrupted searches save no partial study and are not replayed on startup.

Export the complete evidence as JSON or the test-window summary as CSV. Research never changes running strategies, submits orders, activates an account or changes market-source settings. Continuous rebalanced deployment simulations, Bayesian/random search, nested validation, additional benchmarks and strategy plugins remain pending in the [implementation checklist](../developers/backend-roadmap.md).

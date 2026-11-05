---
title: Live forecast scorecard
description: Compare predictions saved before their targets with later closes from the same source.
---

# Live forecast scorecard

In **Forecast → Trained models**, select a trained model and find **Live forecast scorecard** below its historical test results. This is separate from held-out and rolling historical evaluation.

1. Save a forecast using **Current feed**. Its original predictions, observation window, source and model version remain immutable.
2. Expand **Track a saved current-feed forecast** and select that saved output. Only targets after its original save time are eligible. Tracking later does not turn predictions made after their targets into live evidence. Saved-input and Demo forecasts are excluded.
3. Wait for daily target closes. The app checks its retained candle archive hourly while running. **Refresh matching feed** explicitly reads a bounded current daily page from the pinned provider; Markets history imports can also supply missing closes.
4. Inspect the original predicted path against actual observations, absolute errors, naïve benchmark errors and band coverage. The table distinguishes not-yet-due targets from due targets missing in the archive.
5. Compare equal horizons across tracked outputs in the aggregate table, including a drift benchmark calculated only from the original input window. Export the evidence, or pause/resume checks. No model is retrained, selected or deployed.

A missing price is never zero, interpolated or taken from another provider. If the archive has not retained an older target, use the matching Markets historical import. The current refresh page is limited to 90 daily candles.

Later archive corrections update actuals and their metrics without rewriting the original forecast. A per-target version and the latest five correction receipts remain inspectable. Tracked outputs are protected from ordinary recent-forecast cleanup; the workspace supports at most 200 tracked outputs.

Operator-selected forecasts and overlapping multi-day targets are not an unbiased leaderboard or independent accuracy trials. Small sample counts, retrospective selection of which forecasts to track, source corrections and missing targets all limit interpretation. Coverage measures observed outcomes; it does not guarantee future bands or profitable trades.

**Ask Chronos** reads the selected scorecard through a native read-only tool, including in no-model mode. Local scoring never calls an LLM or sends a message.

Equal-horizon aggregate sample counts use unique target days, keeping the earliest original save when the same origin is saved repeatedly. **Remove tracking** deletes local actual/correction receipts after confirmation and frees tracking capacity. The original recent forecast remains, without retention protection. Export first to keep a copy.

# Forecast drift and candidate recalibration

In **Forecasting → Trained models**, expand **Drift & candidate recalibration**. Checking observations reads the exact retained source/environment/pair's closed daily candles. It never fetches a provider or rewrites original forecast evidence.

The reference uses only the saved model's training partition. Recent returns must come after the **entire original input**, including its test window. The chosen 30–180-return window needs one additional close; insufficient observations stay explicitly insufficient. Missing intervals are rejected and closes older than two days cannot authorize recalibration.

## Descriptive statistics

Jensen–Shannon divergence compares return histograms using training-only decile boundaries, fixed 0.5 count smoothing and natural logarithms. Mean shift in reference standard deviations and a volatility ratio supplement the divergence. Constant reference volatility yields undefined normalized ratios. The threshold is a user-defined descriptive trigger, not a calibrated significance test or confidence in the forecast. Sample size, binning, dependence and repeated checks affect interpretation.

## Explicit candidate policy

Save a revision-bound policy with the displayed confirmation phrase. It specifies a recent window, divergence threshold, minimum new days and cooldown. Demo/imported-origin and archived models cannot enable this automation. Run once deliberately, or create a daily local job from this panel. Jobs retain the policy revision; changing it invalidates those jobs rather than silently granting new settings. Manage or pause schedules in **Settings → Workspace → Local jobs**.

When all gates pass, Sibyl snapshots a recent consecutive window with the original input count and exact source. It reuses the fixed family, causal features, lags, regularization and horizon. The existing training engine fits a new numbered child version, with chronological train/calibration/test metrics and an immutable input fingerprint. **The existing model remains unchanged.** The new child is a research candidate that the user must inspect; this does not promote a model, change a strategy or guarantee better future accuracy.

A `(parent, input, policy revision)` receipt prevents repeated fitting for the same admitted input while retained. At most twenty detailed candidate receipts and one latest drift assessment are shown per parent; the existing one-hundred model-version budget still applies. Failed/interrupted work is retained, not replayed on restart. Cancellation cannot undo a model already committed. A new policy revision is needed to deliberately retry an identical failed input. No price-fetch schedule is implicit: arrange source history imports separately.

Chronos reads the saved policy and drift evidence through its native `model_report` tool. It cannot train candidates, change settings or schedule jobs.

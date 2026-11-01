# Trained forecasts with Chronos

**Forecasting → Trained models** fits a real numerical model, stores its coefficients and shows independent evaluation before you produce forecasts. The separate **Statistical baseline** tab retains the untrained drift/volatility projection. Neither workspace places orders. An LLM is optional: Chronos can explain the evidence, but does not fit or approve the numerical model.

## Train your first version

1. Choose **Train model**. Enter an exact spot pair and choose 360, 540 or 720 daily observations from your configured market feed.
2. Alternatively, select a saved daily dataset. Training uses its entire immutable input, with 360–5,000 consecutive closed daily candles. Prepare longer ranges in **Markets → History & datasets**.
3. Optionally expand **Model settings & assumptions**. Choose 5, 14 or 30 daily return lags, a positive ridge penalty and a maximum 7-, 14- or 30-day horizon.
4. Choose **Train & evaluate**. The completed model version appears in the registry with its source, environment, dataset fingerprint, settings and independent test evidence.

A smaller **Try with Demo prices** action uses synthetic daily candles through the same engine. It does not activate Demo accounts or change your market source. Demo-trained models and forecasts remain labeled. Missing history, gaps, unfinished days and provider failures do not trigger Demo substitution.

Only one fit runs per workspace at a time. Current-feed pages are bounded to 720 candles; saved inputs support 5,000. The registry retains at most 100 versions. These are local, synchronous bounded research operations rather than scheduled training jobs.

## What the model learns

For each future horizon, Chronos fits a separate **ridge regression** from recent daily log-return lags to the cumulative log return over that horizon. Features contain information available at the forecast origin. Standardization and coefficients use the first 60% of the dataset only.

The next 20% supplies calibration errors. The last 20% supplies independent test targets. Examples whose target would cross a partition boundary are excluded. Models remain fixed after training; there is no hidden refit on the full dataset, automatic parameter optimization or selection using the test period.

Repeatedly trying settings after looking at test results can still overfit that period. This initial model family is autoregressive ridge, not LSTM, ARIMA or pretrained foundation-model weights.

## Read the evaluation

Choose a horizon to see the corresponding held-out targets and chart:

| Evidence | Interpretation |
| --- | --- |
| MAE | Mean absolute price error, in the pair's quote units. Lower is better. |
| RMSE | Root mean squared price error, also in quote units; emphasizes larger errors. |
| MAPE | Mean absolute percentage price error. It is not investment return. |
| MAE skill vs naïve | `100 × (1 − model MAE / naïve MAE)`. Positive means lower model error; negative means the naïve forecast did better. Undefined when naïve MAE is effectively zero. |
| Observed band coverage | Share of held-out targets inside the empirical band, compared with nominal 90%. |

The **naïve** benchmark holds the origin's last close. The **drift** benchmark uses the mean daily log return from the training partition. All methods use the same test origins and targets. The chart displays at most 400 samples, while metrics and JSON exports retain the full bounded selection.

Horizons above one day have overlapping targets, so observations are not independent trials. Outperformance in this historical test does not establish future forecast quality or trading profitability.

## Empirical bands and input shift

For each horizon, calibration collects absolute log-return prediction errors and chooses the ordered error at rank `ceil((n + 1) × 0.9)`. Predictions use that fixed symmetric log-error radius. Coefficients and widths are fixed before test scoring.

This is empirical calibration at a nominal 90% level. Financial time series have dependence and changing distributions; these bands do not have a distribution-free future coverage guarantee. Their held-out coverage and width remain visible rather than being treated as known probabilities.

The input-shift check counts lag features outside the training sample's observed minimum/maximum ranges. It is a descriptive diagnostic, not a calibrated drift detector, significance test or automatic reason to trade/retrain. Rolling evaluation, monitored drift and automatic recalibration remain pending.

## Produce and reopen forecasts

- **Forecast saved input** applies the unchanged coefficients to the original dataset's final observation window, offline.
- **Use latest matching feed** explicitly reads the model's original source, environment and exact pair. It does not silently switch providers or refit. An unavailable source fails visibly.
- Every forecast shows its observation origin, source, input kind, bands and input-shift evidence. Observations more than two days beyond their closing boundary are marked older; inspect dates even when a provider responds successfully.
- The latest twenty forecasts per model version are retained with their exact bounded input windows and fingerprints. Reopen them without contacting the provider. Older outputs are removed as new ones are saved; model versions and original training datasets are retained.

**Rerun exact training input** fits a new numbered version in the same model series, preserving the original version. The same input/settings/engine and numerical environment reproduce the artifact; dependency or platform changes can introduce numerical differences. Export a model for JSON coefficients, source provenance, partitions, all horizon metrics and complete test traces. Export a forecast separately for its exact inputs and results.

**Ask Chronos** reads the selected version and forecast through native ProtoLink tools. Sibyl can discover Chronos and inspect this evidence too. Agents cannot train, refit, alter settings or execute trades.

## Remaining work

Additional model families, richer features, chronological rolling evaluation, automated recalibration, empirically evaluated drift monitoring, larger model lifecycle management and live forward-performance monitoring remain in the [planning checklist](../developers/backend-roadmap.md).

Trained forecast origins and chart targets use the daily candle close time, when the close becomes available. Raw dataset timestamps and partition boundaries retain the archive’s opening-time convention; a target close can equal the exclusive end boundary of the partition containing its candle.

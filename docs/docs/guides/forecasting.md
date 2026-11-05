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

## Rolling evaluation

Select a saved model and open **Rolling evaluation** below its independent test results. This evaluates its fixed **recipe** (lags and ridge penalty) across successive historical periods. It refits coefficients and calibration bands for each period; the saved model version remains unchanged. The source, exact market, original dataset and recipe stay pinned, with no provider reads or new dependencies.

1. Choose a supported horizon, two to eight successive test windows, test days and calibration days. Defaults use two 60-day test windows with 60 calibration days each.
2. Optionally open **Training window**. **Expanding** uses all earlier training history; **Fixed window** retains only the chosen number of earlier training days.
3. Select **Run rolling evaluation**. Invalid or undersized plans fail explicitly; the engine never silently shrinks a window. Training and rolling evaluation share one fit slot.
4. Compare pooled model/naïve/drift errors and inspect the per-window table. **Inspect fold** shows that fold's training/calibration/test boundaries and actual/predicted prices with both benchmarks.
5. Reopen a **Saved rolling evaluation**, **Export rolling evidence**, or **Rerun exact evaluation**. Reruns save a separate report with a reproducible result fingerprint. The latest ten reports per model and one hundred workspace-wide are retained, with older reports removed as new ones are saved.

Each test block excludes forecast targets crossing its end, and training/calibration exclude targets crossing their own boundaries. This leaves gaps between scored test blocks. Lag features update from observations available at each daily forecast origin, while coefficients and band widths stay fixed within the fold. Earlier test periods may enter later calibration/training once those prices would have been observed. Multi-day targets can overlap **within** a fold.

**Pooled MAE skill** and RMSE are recomputed from all retained target errors, rather than averaged percentages or per-fold RMSE. **Folds beating naïve MAE** reports variation across periods, not statistical significance. All errors use the pair's quote units; MAPE and band widths are percentages. The chart is a bounded visual view; metrics and exports retain the complete saved traces.

These windows come from the original historical input, which the user may already have inspected while choosing a model. Rolling evaluation is not a new untouched holdout, live forward test, investment return or guarantee of future performance. It never chooses, deploys or automatically recalibrates a model. **Ask Chronos** includes the selected rolling report and reads its dated metrics through a native read-only tool, including when no LLM is configured.

## Empirical bands and input shift

For each horizon, calibration collects absolute log-return prediction errors and chooses the ordered error at rank `ceil((n + 1) × 0.9)`. Predictions use that fixed symmetric log-error radius. Coefficients and widths are fixed before test scoring.

This is empirical calibration at a nominal 90% level. Financial time series have dependence and changing distributions; these bands do not have a distribution-free future coverage guarantee. Their held-out coverage and width remain visible rather than being treated as known probabilities.

The input-shift check counts lag features outside the training sample's observed minimum/maximum ranges. It is a descriptive diagnostic, not a calibrated drift detector, significance test or automatic reason to trade/retrain. Monitored drift and automatic recalibration remain pending.

## Produce and reopen forecasts

- **Forecast saved input** applies the unchanged coefficients to the original dataset's final observation window, offline.
- **Use latest matching feed** explicitly reads the model's original source, environment and exact pair. It does not silently switch providers or refit. An unavailable source fails visibly.
- Every forecast shows its observation origin, source, input kind, bands and input-shift evidence. Observations more than two days beyond their closing boundary are marked older; inspect dates even when a provider responds successfully.
- The latest twenty forecasts per model version are retained with their exact bounded input windows and fingerprints. Reopen them without contacting the provider. Older outputs are removed as new ones are saved; model versions and original training datasets are retained.

**Rerun exact training input** fits a new numbered version in the same model series, preserving the original version. The same input/settings/engine and numerical environment reproduce the artifact; dependency or platform changes can introduce numerical differences. Export a model for JSON coefficients, source provenance, partitions, all horizon metrics and complete test traces. Export a forecast separately for its exact inputs and results.

**Ask Chronos** reads the selected version and forecast through native ProtoLink tools. Sibyl can discover Chronos and inspect this evidence too. Agents cannot train, refit, alter settings or execute trades.

## Remaining work

Additional model families, richer features, automated recalibration, empirically evaluated drift monitoring, larger model lifecycle management and live forward-performance monitoring remain in the [planning checklist](../developers/backend-roadmap.md).

Trained forecast origins and chart targets use the daily candle close time, when the close becomes available. Raw dataset timestamps and partition boundaries retain the archive’s opening-time convention; a target close can equal the exclusive end boundary of the partition containing its candle.

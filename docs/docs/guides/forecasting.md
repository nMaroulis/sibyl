# Trained forecasts with Chronos

**Forecasting → Trained models** fits a real numerical model, stores its coefficients and shows independent evaluation before you produce forecasts. The separate **Statistical baseline** tab retains the untrained drift/volatility projection. Neither workspace places orders. An LLM is optional: Chronos can explain the evidence, but does not fit or approve the numerical model.

## Train your first version

1. Choose **Train model**. Enter an exact spot pair and choose 360, 540 or 720 daily observations from your configured market feed.
2. Alternatively, select a saved daily dataset. Training uses its entire immutable input, with 360–5,000 consecutive closed daily candles. Prepare longer ranges in **Markets → History & datasets**.
3. Optionally expand **Model settings & assumptions**. Choose 5, 14 or 30 daily return lags, a positive regularization penalty and a maximum 7-, 14- or 30-day horizon.
4. Choose **Train & evaluate**. The completed model version appears in the registry with its source, environment, dataset fingerprint, settings and independent test evidence.

A smaller **Try with Demo prices** action uses synthetic daily candles through the same engine. It does not activate Demo accounts or change your market source. Demo-trained models and forecasts remain labeled. Missing history, gaps, unfinished days and provider failures do not trigger Demo substitution.

Only one fit runs per workspace at a time. Current-feed pages are bounded to 720 candles; saved inputs support up to 5,000 for ridge, 2,000 for Huber and 1,000 for the small neural model. The registry retains at most 100 versions. Fitting is a bounded local research operation. Separate opt-in drift policies can schedule candidate recalibration; they never promote a candidate automatically.

## What the model learns

By default, for each future horizon Chronos fits a separate **ridge regression** from recent daily log-return lags to the cumulative log return over that horizon. Features contain information available at the forecast origin. Standardization and coefficients use the first 60% of the dataset only.

The next 20% supplies calibration errors. The last 20% supplies independent test targets. Examples whose target would cross a partition boundary are excluded. Models remain fixed after training; there is no hidden refit on the full dataset, automatic parameter optimization or selection using the test period.

Repeatedly trying settings after looking at test results can still overfit that period. Ridge is the default; robust Huber and a small neural model are optional. None uses ARIMA, LSTM or pretrained foundation-model weights.

## Read the evaluation

Choose a horizon to see the corresponding held-out targets and chart:

| Evidence               | Interpretation                                                                                                                                                     |
| ---------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| MAE                    | Mean absolute price error, in the pair's quote units. Lower is better.                                                                                             |
| RMSE                   | Root mean squared price error, also in quote units; emphasizes larger errors.                                                                                      |
| MAPE                   | Mean absolute percentage price error. It is not investment return.                                                                                                 |
| MAE skill vs naïve     | `100 × (1 − model MAE / naïve MAE)`. Positive means lower model error; negative means the naïve forecast did better. Undefined when naïve MAE is effectively zero. |
| Observed band coverage | Share of held-out targets inside the empirical band, compared with nominal 90%.                                                                                    |

The **naïve** benchmark holds the origin's last close. The **drift** benchmark uses the mean daily log return from the training partition. All methods use the same test origins and targets. The chart displays at most 400 samples, while metrics and JSON exports retain the full bounded selection.

Horizons above one day have overlapping targets, so observations are not independent trials. Outperformance in this historical test does not establish future forecast quality or trading profitability.

## Rolling evaluation

Select a saved model and open **Rolling evaluation** below its independent test results. This evaluates its fixed **recipe** (family, features, lags, regularization and any Huber delta) across successive historical periods. It refits coefficients and calibration bands for each period; the saved model version remains unchanged. The source, exact market, original dataset and recipe stay pinned, with no provider reads or new dependencies.

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

The input-shift check counts lag features outside the training sample's observed minimum/maximum ranges. It is a descriptive diagnostic, not a calibrated drift detector, significance test or automatic reason to trade/retrain. The separate **Drift & candidate recalibration** panel compares recent retained observations and can train a new research candidate under an explicit policy. See the [drift workflow](../developers/forecast-drift.md).

## Produce and reopen forecasts

- **Forecast saved input** applies the unchanged coefficients to the original dataset's final observation window, offline.
- **Use latest matching feed** explicitly reads the model's original source, environment and exact pair. It does not silently switch providers or refit. An unavailable source fails visibly.
- Every forecast shows its observation origin, source, input kind, bands and input-shift evidence. Observations more than two days beyond their closing boundary are marked older; inspect dates even when a provider responds successfully.
- The latest twenty forecasts per model version are retained with their exact bounded input windows and fingerprints. Reopen them without contacting the provider. Older outputs are removed as new ones are saved; model versions and original training datasets are retained.

**Rerun exact training input** fits a new numbered version in the same model series, preserving the original version. The same input/settings/engine and numerical environment reproduce the artifact; dependency or platform changes can introduce numerical differences. Export a model for JSON coefficients, source provenance, partitions, all horizon metrics and complete test traces. Export a forecast separately for its exact inputs and results.

**Ask Chronos** reads the selected version and forecast through native ProtoLink tools. Sibyl can discover Chronos and inspect this evidence too. Agents cannot train, refit, alter settings or execute trades.

## Remaining work

The [Live forecast scorecard](forecast-outcomes.md) compares saved prospective predictions with actual closes. ARIMA and additional neural/model families, richer features, real-data drift/calibration studies and larger model lifecycle management remain in the [planning checklist](../developers/backend-roadmap.md).

Trained forecast origins and chart targets use the daily candle close time, when the close becomes available. Raw dataset timestamps and partition boundaries retain the archive’s opening-time convention; a target close can equal the exclusive end boundary of the partition containing its candle.

## Move and organize models

**Model library → Export portable bundle** downloads a JSON package with the training recipe, recorded numerical evidence and complete immutable daily input. In another workspace, expand **Import a model from another workspace**, choose the file and select **Import & verify**. Sibyl verifies the data and hashes, then fits the recipe locally; uploaded coefficients and scores never become trusted computed results.

Imports are explicitly **Imported · unverified source**, with a separate imported namespace. They support saved-input forecasts and historical evaluation; they cannot use a claimed provider identity for current-feed forecasting or prospective tracking. Repeated identical imports reuse the saved version. Bundles accept the supported ridge/Huber/neural engines with each family’s input bounds (at least 360 closed daily candles) and at most 16 MiB, within the workspace’s existing model/dataset budgets. They include research prices, not account credentials or assistant models.

**Archive model** hides a version from the default picker and disables new saved forecasts. **Show archived versions → Restore model** brings it back. Saved outputs, evaluations and any existing outcome monitors remain intact; archiving neither deletes storage nor silently pauses monitors. Pause outcome tracking separately if needed. Read-only Chronos help explains these controls and can inspect archived versions on request.

## Optional trend and volatility features

In **Train model → Model settings & assumptions**, choose **Returns + trend & volatility**. Alongside the selected daily-return lags, this adds six statistics over exactly the same preceding price window: mean log return, population return volatility, downside RMS around zero, positive-return share, log drawdown from the trailing maximum, and distance from the trailing log-price mean. There are no volume, order-book or external inputs.

The recipe is shown beside the saved model's engine and parameters. Training-only scaling, purged chronological train/calibration/test boundaries, empirical calibration bands and naive/drift comparisons still apply. Compare recorded held-out results; extra features can make performance worse. This feature recipe is available to ridge, Huber and the small neural model; it is not automatic feature selection.

Exact reruns, rolling studies, saved/current-input forecasts, portable bundle imports and prospective tracking keep that model's feature recipe. Older returns-only artifacts remain supported unchanged. Chronos can explain which recipe a selected model actually uses.

## Try a small neural model

Open **Train model → Model settings & assumptions → Numerical model** and choose **Small neural network**. Ridge stays the default. The optional network learns eight tanh hidden units from the same causal return features, with a fixed seed and 120 Adam steps. It needs no LLM, GPU or extra ML package. Inputs are limited to 360–1,000 closed consecutive daily candles and forecasts to 14 days; current/Demo pages retain their 720-candle limit.

**Neural training evidence** shows actual initial/final training objective and architecture per horizon. A lower training loss is not proof of predictive skill: compare the independent test results with naive/drift, inspect calibrated coverage, and run rolling evaluation. The calibration/test data never choose weights, training normalization or iteration count. The selected family is retained through exact-input reruns, saved forecasts, portable local refits and Chronos evidence. Demo prices remain explicitly synthetic. Other neural families and ARIMA are pending.

## Try robust Huber autoregression

Open **Train model → Model settings & assumptions → Numerical model → Huber · robust autoregression**. It uses the same daily price features and held-out evaluation as ridge, with a different fitting loss: large training residuals receive less influence while every observation remains in the input. It needs no LLM, GPU or extra ML package.

**Huber delta** controls when residual downweighting starts after training-only target scaling. The default is 1.35; lower values begin downweighting sooner. Scale uses the training target median/MAD with a small numerical floor. This does not automatically clean data, make input features robust or establish that an unusual price is an error. Genuine market shocks can still affect forecasts.

**Huber training evidence** shows actual iterations, whether the fit converged or reached its 60-step limit, residual cutoff, downweighted samples/effective weights and initial/final training objective. A step-limit result stays visibly unconverged. Convergence and a smaller training loss are not evidence of future accuracy; compare independent MAE/RMSE, naive/drift skill and empirical interval coverage. Loss scales differ across horizons.

Huber supports 360–2,000 consecutive closed daily candles and up to 30 forecast days; current/Demo pages still provide at most 720 candles. Both return-only and trend/volatility features work. Exact-input reruns, rolling studies, portable local refits and explicit recalibration candidates keep the chosen delta and family. Models, forecasts and Demo input retain the existing labels and source boundaries. Chronos can explain the saved diagnostics but cannot train or select a model for you.

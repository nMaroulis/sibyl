# Chronos training and model contracts

`forecasting/` separates request contracts, pure NumPy estimation and a small registry service. FastAPI routes call the service; ordinary typed Chronos tools read the same model and output evidence. No custom agent runtime, ML dependency, model download or import-time training is added.

## Engine `chronos-ridge-1`

Given daily log prices `p[t]`, features at origin `t` are the latest `L` observed differences, newest first. For each horizon `h`, the target is `p[t+h] - p[t]`. Training standardizes each feature with its training mean and population standard deviation. A near-constant standard deviation below `1e-12` uses scale 1.

The intercept is the mean training target. Coefficients solve:

```text
(Zᵀ Z + αI) β = Zᵀ(y − mean(y))
```

The intercept is not penalized. Positive α is required. The stored JSON includes coefficients, means/scales, horizon, calibration radius, sample counts and observed feature ranges. NumPy and engine versions are retained. Singular/numerically unstable fits fail rather than persisting partial artifacts or clipping predictions.

Partitions are `[0, floor(.6N))`, `[floor(.6N), floor(.8N))`, and `[floor(.8N), N)`. Training origins start at `L`; calibration/test origins start at their own boundaries. Every target must stay strictly inside its partition. At least `max(60, 3L)` training examples and 20 calibration/test examples per horizon are required. The default 720-candle input supports horizons through 30 days.

Only training data fits coefficients, feature normalization and drift-benchmark parameters. Calibration sets an absolute log-error quantile at rank `ceil((n+1) × .9)`. Testing measures fixed-model price errors, last-close/training-drift benchmarks and coverage without refitting. Overlapping multi-day targets and time-series dependence are disclosed; no exchangeability or future-coverage guarantee is claimed.

See the [user guide](../guides/forecasting.md) for metric definitions and limitations. Method references: the authors' [forecast evaluation and benchmark discussion](https://otexts.com/fpp3/toolbox.html) and [NumPy's linear-system solver](https://numpy.org/doc/stable/reference/generated/numpy.linalg.solve.html).

## Persistence and admission

`ForecastModels` uses one local nonblocking fit lock and short SQLite transactions. Training captures an immutable existing candle dataset before computation and atomically inserts a complete model only after successful fitting/evaluation. A failed fit can leave the explicitly captured research dataset, but no partial model version. The process remains a single-worker workspace.

- `forecast_models` retains immutable JSON metadata/payloads, series IDs and unique numbered versions. Maximum: 100 versions per workspace.
- `forecast_outputs` retains the latest twenty outputs per model version. Each contains at most ninety observed daily candles, source/environment/pair, origin, input fingerprint, result fingerprint and predictions.
- Model fingerprints cover dataset provenance and numerical artifacts. Metadata must agree with artifact parameters and source identity. Load/export checks detect changed persisted artifacts. No pickle, user-supplied executable model or secret-provider configuration is stored in these documents.
- Reruns reuse the exact saved dataset/settings and create a new version. No older model is overwritten. Exact hashes apply within the same numerical environment; cross-platform BLAS/dependency changes can differ.

Current input pages allow 360–720 bars. Saved daily inputs allow 360–5,000. Engine validation rejects nonconsecutive/off-grid/duplicate/open/future days and nonpositive/nonfinite closes. Existing archive hashing and OHLCV validation protect retained input. Training never interpolates, changes source settings or starts a strategy.

Current-feed inference is explicitly requested and pinned to the original source/environment/pair. Observations older than the training dataset endpoint are rejected. Saved-input inference is fully offline. Each forecast is reproducible from exported coefficients and its exact retained observation window; it does not mutate the model. Forecast history reads do not refresh a source.

## HTTP API

All routes use existing workspace authorization/origin checks and `Cache-Control: no-store`. Synchronous computation runs in FastAPI's normal worker thread; no second execution wrapper is introduced.

| Method | `/api/v1` path | Contract |
| --- | --- | --- |
| GET | `/forecast-models` | Bounded model-version metadata |
| POST | `/forecast-models` | Explicit input capture, fit, calibration, test and atomic save |
| GET | `/forecast-models/{id}?horizon=7` | All compact metrics, one horizon's test trace and saved output headers |
| GET | `/forecast-models/{id}/export` | Complete JSON artifact, recipe and all test traces |
| POST | `/forecast-models/{id}/rerun` | New version from the exact original input |
| POST | `/forecast-models/{id}/forecasts` | Body: `input_kind` (`saved_input` or `current_feed`) and `horizon` (1–30) |
| GET | `/forecast-models/outputs/{id}` | Exact retained output and observation window |
| GET | `/forecast` | Existing separate untrained baseline; unchanged contract |

Training accepts `label`, `input_kind` (`current_feed`, `saved_dataset`, `demo`), optional saved `dataset_id`, exact `symbol`, `candles`, `lags` (5/14/30), positive `alpha` (0.01–1000), and `max_horizon` (1–30). Saved input uses its entire actual dataset. Public-source availability and native retention can return fewer bars than requested; fewer than 360 fails explicitly.

## Native Chronos integration

`agents/chronos.py` declares `price_forecast`, `trained_models`, `model_report`, `forecast_method`, `rolling_evaluation` and `page_help` as ordinary typed native tools. Page context may carry `forecast_model_id`, `forecast_run_id` and `forecast_evaluation_id`. `price_forecast(model_id=...)` also supports discovered versions outside the page. Saved forecast identity is checked against its model; unavailable horizons are rejected.

Native tools only read persisted evidence or calculate from the original retained input, without saving outputs or fetching providers. Direct page requests use the registered specialist; Sibyl uses native discovery/delegation. Training and forecast persistence remain explicit application actions.

## Verification and remaining scope

Tests cover causal features, purged partitions, isolation of test/calibration changes, benchmark math, constant markets, invalid/bounded inputs, fit failures, concurrent admission, JSON integrity, exact-input reruns, retention, API privacy and native Chronos evidence. Controlled data and successful provider retrieval do not establish predictive profitability. Prospective tracking now uses a separate [outcome service](performance-outcomes-alerts.md). Neural/ARIMA families, calibrated drift monitoring, managed archive/import and automatic training remain pending.

An isolated October 29, 2026 acceptance run trained on 720 real Binance BTC/USDT daily candles, retained 137 seven-day test origins and produced a seven-point forecast. Its exact-input rerun reproduced the artifact fingerprint with zero additional provider reads. The transport admitted only credential-free GET requests to Binance's public spot `exchangeInfo` and `klines` endpoints (two requests); there were no private requests, account reads or orders. This establishes the observed data/fit/replay workflow, not forecast quality or other providers' history coverage.

Trained forecast origins and chart targets use the daily candle close time, when the close becomes available. Raw dataset timestamps and partition boundaries retain the archive’s opening-time convention; a target close can equal the exclusive end boundary of the partition containing its candle.


## Rolling evaluation `chronos-rolling-1`

`rolling.py` evaluates one fixed saved ridge recipe, with shared `engine.fit_horizon` and `score_horizon` primitives. The existing `chronos-ridge-1` fitting/evaluation artifacts remain numerically unchanged. `evaluations.py` owns separate immutable receipts; no trained model version or forecast is overwritten. There is no automatic training, model selection, live forward evaluation or provider refresh.

For `N` daily closes, `F` folds, test length `T`, calibration length `C` and horizon `h`, fold `i` starts testing at `s = N − F×T + i×T`. Its training ends at `s−C`; calibration covers `[s−C,s)` and testing `[s,s+T)`. Expanding training starts at zero; fixed-window training starts at `s−C−training_days`. Training origins start at `training_start + lags`, calibration/test origins start at their own boundaries, and each target index must stay strictly inside its partition. There must be at least `max(60,3×lags)` training samples and twenty calibration/test samples. Thus the minimum training duration is `lags + max(60,3×lags) + h`; calibration/test durations must each be at least `h+20`.

Each fold estimates standardization, coefficients, feature ranges and drift on training data only. Calibration fixes the same nominal 90% radius as the original engine. Fits and widths remain fixed throughout a block; origin lag features use only closes observed by that origin. Prior test periods can enter later training/calibration after becoming historical observations. Later test prices cannot affect earlier fitted artifacts or traces. Multi-day return windows may overlap within blocks; boundary purging leaves unscored gaps between blocks. This is blocked historical rolling-origin research, not an independent holdout or continuous deployment simulation. See the authors' [time-series cross-validation discussion](https://otexts.com/fpp3/toolbox.html#time-series-cross-validation).

Pooled metrics are calculated from concatenated matching target errors: RMSE is the square root of the pooled mean squared error, and skill is calculated from pooled model/naïve MAE. Fold percentages and RMSE values are not averaged. Undefined zero-error benchmark skill stays null. Reports retain per-fold parameters/scalers/coefficients/radius, training drift, explicit boundaries, all traces and benchmark metrics. JSON fingerprints reject non-finite values and cover result/provenance separately; they are consistency checks, not cryptographic signatures or provider-truth proofs.

### Persistence, admission and HTTP

`forecast_evaluations(id,model_id,payload)` lives in the existing workspace database and is covered by the ordinary encrypted workspace archive. The original saved dataset is resolved and its provenance checked before fitting. The existing nonblocking fit lock admits either training or one rolling evaluation; failure leaves no partial report and releases admission. Save/retention happen in one short SQLite transaction. The newest ten per model and one hundred workspace-wide are retained. Reads/exports do not require current source access or refit anything; missing/pruned reports are explicit 404s.

| Method | Path below `/api/v1` | Behavior |
| --- | --- | --- |
| POST | `/forecast-models/{model_id}/evaluations` | Explicitly run and retain a recipe evaluation; 201 on success |
| GET | `/forecast-models/{model_id}/evaluations` | Retained report headers and limits |
| GET | `/forecast-models/evaluations/{evaluation_id}` | Exact saved report, including reproducibility artifacts and traces; used for export |

Requests accept strict integer `horizon` (1–30), `folds` (2–8), `test_days` (21–180), `calibration_days` (21–365), `window` (`expanding`/`rolling`) and `training_days` (120–2000, required only for `rolling`). The horizon cannot exceed the saved recipe's maximum. The source dataset remains bounded at 5,000 candles, so at most eight refits and fewer than 1,440 test origins are scored. Existing workspace authorization/origin checks and no-store responses apply.

### Native evidence and UI

Chronos's ordinary typed `rolling_evaluation(model_id?,evaluation_id?)` tool lists headers or returns bounded per-fold metrics/boundaries, exact provenance and interpretation notes. It reads the private selected `forecast_evaluation_id` context. Foreign or missing selections receive native correctable rejections. Coefficients and full chart traces remain in explicit report/export endpoints; the agent tool does not refit or mutate. With no LLM, the selected evaluation is read through the native group handle and summarized deterministically. No custom execution wrapper or LLM router is added.

The UI has progressive window settings, pinned recipe/source attribution, saved history, pooled metrics, fold selection, exact JSON export and an explicit separate rerun. It reuses the existing bounded chart with at most 400 displayed points and disables chart animation. Selecting a different model clears evaluation context; cross-model report URLs are rejected. Completing an old request after navigation cannot select its report into the new model's UI.

Tests cover future-price perturbations, fixed-window isolation, later-fold admission of now-historical data, purged boundaries, pooled metrics, constant-price skill, strict input/budget failures, rollback/admission, retention, integrity, restarts, HTTP controls and native selected-report evidence without provider reads. Automatic recalibration, monitored drift, additional model families and live forward-performance monitoring remain pending.

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

| Method | `/api/v1` path                    | Contract                                                                  |
| ------ | --------------------------------- | ------------------------------------------------------------------------- |
| GET    | `/forecast-models`                | Bounded model-version metadata                                            |
| POST   | `/forecast-models`                | Explicit input capture, fit, calibration, test and atomic save            |
| GET    | `/forecast-models/{id}?horizon=7` | All compact metrics, one horizon's test trace and saved output headers    |
| GET    | `/forecast-models/{id}/export`    | Complete JSON artifact, recipe and all test traces                        |
| POST   | `/forecast-models/{id}/rerun`     | New version from the exact original input                                 |
| POST   | `/forecast-models/{id}/forecasts` | Body: `input_kind` (`saved_input` or `current_feed`) and `horizon` (1–30) |
| GET    | `/forecast-models/outputs/{id}`   | Exact retained output and observation window                              |
| GET    | `/forecast`                       | Existing separate untrained baseline; unchanged contract                  |

Training accepts `label`, `input_kind` (`current_feed`, `saved_dataset`, `demo`), optional saved `dataset_id`, exact `symbol`, `candles`, `lags` (5/14/30), positive `alpha` (0.01–1000), and `max_horizon` (1–30). Saved input uses its entire actual dataset. Public-source availability and native retention can return fewer bars than requested; fewer than 360 fails explicitly.

## Native Chronos integration

`agents/chronos.py` declares `price_forecast`, `trained_models`, `model_report`, `forecast_method`, `rolling_evaluation` and `page_help` as ordinary typed native tools. Page context may carry `forecast_model_id`, `forecast_run_id` and `forecast_evaluation_id`. `price_forecast(model_id=...)` also supports discovered versions outside the page. Saved forecast identity is checked against its model; unavailable horizons are rejected.

Native tools only read persisted evidence or calculate from the original retained input, without saving outputs or fetching providers. Direct page requests use the registered specialist; Sibyl uses native discovery/delegation. Training and forecast persistence remain explicit application actions.

## Verification and remaining scope

Tests cover causal features, purged partitions, isolation of test/calibration changes, benchmark math, constant markets, invalid/bounded inputs, fit failures, concurrent admission, JSON integrity, exact-input reruns, retention, API privacy and native Chronos evidence. Controlled data and successful provider retrieval do not establish predictive profitability. Prospective tracking now uses a separate [outcome service](performance-outcomes-alerts.md). Ridge, fixed-scale Huber, native nonseasonal ARIMA and a small neural family are implemented. [Retained-source drift policies](forecast-drift.md) can explicitly train new candidate versions; additional neural/model families, seasonal/exogenous variants, real-data drift calibration and larger managed lifecycles remain pending.

An isolated October 29, 2026 acceptance run trained on 720 real Binance BTC/USDT daily candles, retained 137 seven-day test origins and produced a seven-point forecast. Its exact-input rerun reproduced the artifact fingerprint with zero additional provider reads. The transport admitted only credential-free GET requests to Binance's public spot `exchangeInfo` and `klines` endpoints (two requests); there were no private requests, account reads or orders. This establishes the observed data/fit/replay workflow, not forecast quality or other providers' history coverage.

Trained forecast origins and chart targets use the daily candle close time, when the close becomes available. Raw dataset timestamps and partition boundaries retain the archive’s opening-time convention; a target close can equal the exclusive end boundary of the partition containing its candle.

## Rolling evaluation `chronos-rolling-1`

`rolling.py` evaluates one fixed saved ridge recipe, with shared `engine.fit_horizon` and `score_horizon` primitives. The existing `chronos-ridge-1` fitting/evaluation artifacts remain numerically unchanged. `evaluations.py` owns separate immutable receipts; no trained model version or forecast is overwritten. There is no automatic training, model selection, live forward evaluation or provider refresh.

For `N` daily closes, `F` folds, test length `T`, calibration length `C` and horizon `h`, fold `i` starts testing at `s = N − F×T + i×T`. Its training ends at `s−C`; calibration covers `[s−C,s)` and testing `[s,s+T)`. Expanding training starts at zero; fixed-window training starts at `s−C−training_days`. Training origins start at `training_start + lags`, calibration/test origins start at their own boundaries, and each target index must stay strictly inside its partition. There must be at least `max(60,3×lags)` training samples and twenty calibration/test samples. Thus the minimum training duration is `lags + max(60,3×lags) + h`; calibration/test durations must each be at least `h+20`.

Each fold estimates standardization, coefficients, feature ranges and drift on training data only. Calibration fixes the same nominal 90% radius as the original engine. Fits and widths remain fixed throughout a block; origin lag features use only closes observed by that origin. Prior test periods can enter later training/calibration after becoming historical observations. Later test prices cannot affect earlier fitted artifacts or traces. Multi-day return windows may overlap within blocks; boundary purging leaves unscored gaps between blocks. This is blocked historical rolling-origin research, not an independent holdout or continuous deployment simulation. See the authors' [time-series cross-validation discussion](https://otexts.com/fpp3/toolbox.html#time-series-cross-validation).

Pooled metrics are calculated from concatenated matching target errors: RMSE is the square root of the pooled mean squared error, and skill is calculated from pooled model/naïve MAE. Fold percentages and RMSE values are not averaged. Undefined zero-error benchmark skill stays null. Reports retain per-fold parameters/scalers/coefficients/radius, training drift, explicit boundaries, all traces and benchmark metrics. JSON fingerprints reject non-finite values and cover result/provenance separately; they are consistency checks, not cryptographic signatures or provider-truth proofs.

### Persistence, admission and HTTP

`forecast_evaluations(id,model_id,payload)` lives in the existing workspace database and is covered by the ordinary encrypted workspace archive. The original saved dataset is resolved and its provenance checked before fitting. The existing nonblocking fit lock admits either training or one rolling evaluation; failure leaves no partial report and releases admission. Save/retention happen in one short SQLite transaction. The newest ten per model and one hundred workspace-wide are retained. Reads/exports do not require current source access or refit anything; missing/pruned reports are explicit 404s.

| Method | Path below `/api/v1`                           | Behavior                                                                            |
| ------ | ---------------------------------------------- | ----------------------------------------------------------------------------------- |
| POST   | `/forecast-models/{model_id}/evaluations`      | Explicitly run and retain a recipe evaluation; 201 on success                       |
| GET    | `/forecast-models/{model_id}/evaluations`      | Retained report headers and limits                                                  |
| GET    | `/forecast-models/evaluations/{evaluation_id}` | Exact saved report, including reproducibility artifacts and traces; used for export |

Requests accept strict integer `horizon` (1–30), `folds` (2–8), `test_days` (21–180), `calibration_days` (21–365), `window` (`expanding`/`rolling`) and `training_days` (120–2000, required only for `rolling`). The horizon cannot exceed the saved recipe's maximum. The source dataset remains bounded at 5,000 candles, so at most eight refits and fewer than 1,440 test origins are scored. Existing workspace authorization/origin checks and no-store responses apply.

### Native evidence and UI

Chronos's ordinary typed `rolling_evaluation(model_id?,evaluation_id?)` tool lists headers or returns bounded per-fold metrics/boundaries, exact provenance and interpretation notes. It reads the private selected `forecast_evaluation_id` context. Foreign or missing selections receive native correctable rejections. Coefficients and full chart traces remain in explicit report/export endpoints; the agent tool does not refit or mutate. With no LLM, the selected evaluation is read through the native group handle and summarized deterministically. No custom execution wrapper or LLM router is added.

The UI has progressive window settings, pinned recipe/source attribution, saved history, pooled metrics, fold selection, exact JSON export and an explicit separate rerun. It reuses the existing bounded chart with at most 400 displayed points and disables chart animation. Selecting a different model clears evaluation context; cross-model report URLs are rejected. Completing an old request after navigation cannot select its report into the new model's UI.

Tests cover future-price perturbations, fixed-window isolation, later-fold admission of now-historical data, purged boundaries, pooled metrics, constant-price skill, strict input/budget failures, rollback/admission, retention, integrity, restarts, HTTP controls and native selected-report evidence without provider reads. Separate [drift/candidate policies](forecast-drift.md) and [prospective scorecards](../guides/forecast-outcomes.md) are implemented. Rolling evaluation itself neither deploys nor selects a model; additional families and broader real-data studies remain pending.

## Portable bundles and archive state

`forecasting/bundles.py` accepts only bounded finite JSON (`sibyl-forecast-bundle`, schema 1), with duplicate-key rejection, envelope/model/input fingerprints, a known engine, validated request parameters, source agreement and consecutive closed daily OHLCV. `POST /forecast-models/import` accepts the raw JSON file body and returns a locally refitted version. It shares nonblocking training admission and checks both 100-model/1,000-dataset budgets before committing model and dataset atomically. An identical bundle digest reuses the imported version.

`GET /forecast-models/{id}/bundle` exports the complete immutable input, recipe and recorded fit; the older artifact-only export remains available. Imported input is always assigned a new `import:<digest>` / `imported` identity. Hashes establish internal integrity, not provider authenticity. Uploaded artifacts/metrics are retained only as fingerprint comparisons; fresh local fitting computes the stored results. Original output IDs, tracking and live claims are not imported. No executable deserialization or provider reads occur.

`POST /forecast-models/{id}/archive` accepts `{archived, revision}`. Organization metadata is updated atomically without changing the numerical fingerprint. Registry reads hide archived versions unless `include_archived=true`. Existing evidence remains readable; new saved forecasts require restoration. Outcome tracking remains independently controlled. Chronos `trained_models(include_archived=True)` and typed `page_help(topic="portability")` expose read-only evidence/help, not mutations.

## Causal feature recipes

`TrainForecast.feature_set` accepts `returns` (default) or `returns_context`. The default retains legacy artifact parameters, engine identity and numerical behavior. The richer recipe uses `chronos-ridge-context-1` and appends six trailing-window features to the lag vector; the artifact stores readable feature names. All features for origin t depend only on closes through t. Scaling and range evidence use training rows only, with minimum training size based on actual feature width.

Predict, rolling evaluation and bundle validation dispatch from the recorded recipe, never current UI settings. Bundle request, metadata and artifact engines/parameters must agree; offline imports refit that exact recipe. Tests perturb held-out prices, compare prefix feature vectors, retain default behavior, refit bundles and exercise the actual rolling engine. More features do not establish better generalization or calibrated drift detection.

## Bounded neural family

`TrainForecast.family` accepts `ridge` (default), `mlp` or `huber`. Default ridge parameters and engine identity remain unchanged. `forecasting/families/neural.py` implements one 8-unit tanh layer and scalar standardized cumulative-log-return output in NumPy. Each horizon uses seed `1729 + horizon`, 120 full-batch Adam steps, learning rate 0.02, mean squared standardized-target error plus `alpha/n` weight L2. Inputs and targets are normalized from training rows only; fixed iterations avoid hidden test-driven stopping. JSON stores finite weights, normalization and actual initial/final objective. No executable serialization is accepted.

Neural engine identities are `chronos-mlp-1` and `chronos-mlp-context-1`. Actual input length is checked in training and rolling evaluation, independently of request fields: at most 1,000 candles and 14 forecast days. The existing purged partitions, empirical calibration radius, independent benchmarks, causal feature recipes, immutable artifacts, archive controls and prospective scoring apply. Bundle request/metadata/artifact must agree on engine/family; imports locally refit the recorded recipe. Rolling reports retain the compatibility field `ridge_engine`, whose value now identifies the selected numerical family. This bounded model is not an accuracy claim or a replacement for larger studies.


## Fixed-scale Huber family

`families/huber.py` fits a genuinely different robust-loss autoregression using NumPy only. It uses the shared direct per-horizon targets, training-only input mean/std scaling, purged partitions, empirical calibration and independent price-error benchmarks. Engine IDs are `chronos-huber-1` and `chronos-huber-context-1`; parameters retain `family="huber"` and `huber_delta` (default 1.35, bounded 0.25–5). Non-Huber requests reject a nondefault Huber-only control instead of silently ignoring it. Ridge artifacts retain their original parameter/engine identity.

For each horizon, y is centered by the training median and scaled by `max(1e-6, 1.4826 * median(abs(y - median(y))))`. That center/scale stays fixed. The objective is mean Huber loss of the standardized residual plus `alpha/(2n)` times the squared standardized-target feature coefficients; the intercept is unpenalized. The Huber loss is quadratic within delta and linear beyond it. This is a fixed-scale estimator, **not** scikit-learn’s jointly estimated scale implementation. See the [SciPy Huber definition](https://docs.scipy.org/doc/scipy/reference/generated/scipy.special.huber.html) and [HuberRegressor distinction](https://scikit-learn.org/stable/modules/generated/sklearn.linear_model.HuberRegressor.html).

Each IRLS step uses weights 1 inside the cutoff or `delta/abs(residual)` outside, then solves the weighted ridge system. Rows are never removed. Stop on max coefficient change `<= 1e-8 * (1 + previous coefficient max norm)` or 60 steps. Numerical failures/nonfinite or increasing objectives are rejected. A finite bounded fit at the step limit remains explicitly unconverged, with an artifact note and UI badge; it is not silently labeled optimized. Coefficients/intercept are converted back to cumulative-log-return units for the existing prediction path.

Training receipts include actual initial/final objective, steps/cap/convergence, training target center/MAD scale, original-unit residual cutoff, downweighted count, positive minimum weight and effective weight sum. Losses use horizon-specific standardized target units and should not be compared as price accuracy. They do not label observations as incorrect, detect market regimes or make input leverage robust. Feature scaling is still the shared mean/std recipe.

Requests and actual frozen inputs both enforce at most 2,000 candles; horizons support 1–30 days. Current/Demo pages keep their 720-candle cap. Saved inputs, exact reruns, expanding/rolling historical evaluations, prospective outputs, portable recipe refits and retained-source recalibration preserve family/delta. No startup fit, additional ML dependency, executable serialization, automatic model selection or trading is introduced. Bundle recipe mismatches are rejected before local refit.

Acceptance checks the robust objective’s first-order stationarity, controlled residual-contamination behavior, deterministic real fits, unchanged training parameters under calibration/test perturbation, flat targets, explicit step-limit reporting, request/actual-data bounds, exact offline reruns, source-unverified portable refits, rolling boundary causality and native Chronos evidence. Controlled synthetic examples are not real-market accuracy or profitability acceptance; seasonal/exogenous models, broader neural families and real-data studies remain pending.


## Native ARIMA family

`families/arima.py` uses the [statsmodels ARIMA API](https://www.statsmodels.org/stable/generated/statsmodels.tsa.arima.model.ARIMA.html). An ARMA(p,q) return model corresponds to ARIMA(p,1,q) on log prices with drift. The reviewed recipe fixes d = 1, permits p = 1–3 and q = 0–2, includes a native constant on returns, and enforces stationarity/invertibility. No seasonal/exogenous input, automatic order search, ridge penalty or context-feature recipe is accepted. Engine `chronos-arima-1` retains p/q, difference, 90-close context and maximum horizon; irrelevant lag/penalty keys are absent from its artifact parameters. Nondefault irrelevant request controls are rejected. Older families retain exact parameter identity.

Only training log returns estimate center, population standard deviation and native state-space maximum-likelihood parameters. Fits use L-BFGS with a 100-iteration cap and reject nonconvergence, nonfinite diagnostics, nonpositive innovation variance or return standard deviation below 1e-10. All horizons share that single native vector. The JSON receipt includes statsmodels version, actual iterations/convergence, named coefficients, standardized-return likelihood/AIC/BIC and relevant fit-warning categories. Dependency deprecation notices are not numerical fit evidence. Information criteria must not be ranked across differently scaled/input training data or treated as held-out skill.

For every calibration/test/inference origin, construct the same reviewed native model on exactly 89 returns from the last 90 observed closes, then [filter](https://www.statsmodels.org/stable/generated/statsmodels.tsa.arima.model.ARIMA.filter.html) using the unchanged parameter vector and [forecast](https://www.statsmodels.org/stable/generated/statsmodels.tsa.arima.model.ARIMAResults.get_forecast.html) the next returns. Rescale and cumulatively integrate them into log-price changes. There is no refit, future smoothing or executable serialization. Filtering is deliberately reinitialized per finite context, not continued from an unbounded hidden state. The same context for evaluation/inference avoids a hidden warm-up mismatch. Point prices exponentiate predicted logs without a lognormal mean correction. Existing empirical calibration fixes each horizon's radius; native Gaussian intervals are not presented as calibrated bands.

The shared 60/20/20 partitions, purged calibration/test targets, naive/drift comparisons, overlapping-target disclosures and price-error scoring remain. ARIMA fits all within-training one-step returns, never an h-step target crossing its end. Rolling folds fit only their own expanding/fixed training window; at least 120 training closes are required. Bounds apply to actual frozen input as well as requests: at most 1,000 candles and 14 days, while current/Demo pages remain at most 720. Existing model budgets and fit admission still apply.

`engine.py` dispatches this family without changing ridge/Huber/neural math. Saved inference requires 90 closes; current-source reads remain exact-source and at least that size. Original inputs, portable local refits, rolling reports and candidate recalibration preserve order/context. Native Chronos tools return the actual receipt and guide users to the explicit UI; no agent mutation primitive is added. Tests cover native reference forecasts/known AR structure, causal future perturbations, test/calibration isolation, strict bounds, failed-fit rollback, versioned reruns, bundle recipe mismatch, rolling pooled errors, Demo isolation, native read-only agent access and retained recalibration. Larger real-data/seasonal/exogenous validation remains pending.

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

`agents/chronos.py` declares `price_forecast`, `trained_models`, `model_report`, `forecast_method` and `page_help` as ordinary typed native tools. Page context may carry `forecast_model_id` and `forecast_run_id`. `price_forecast(model_id=...)` also supports discovered versions outside the page. Saved forecast identity is checked against its model; unavailable horizons are rejected.

Native tools only read persisted evidence or calculate from the original retained input, without saving outputs or fetching providers. Direct page requests use the registered specialist; Sibyl uses native discovery/delegation. Training and forecast persistence remain explicit application actions.

## Verification and remaining scope

Tests cover causal features, purged partitions, isolation of test/calibration changes, benchmark math, constant markets, invalid/bounded inputs, fit failures, concurrent admission, JSON integrity, exact-input reruns, retention, API privacy and native Chronos evidence. Controlled data and successful provider retrieval do not establish predictive profitability. Neural/ARIMA families, rolling forward evaluation, calibrated drift monitoring, managed archive/import and automatic training remain pending.

An isolated October 29, 2026 acceptance run trained on 720 real Binance BTC/USDT daily candles, retained 137 seven-day test origins and produced a seven-point forecast. Its exact-input rerun reproduced the artifact fingerprint with zero additional provider reads. The transport admitted only credential-free GET requests to Binance's public spot `exchangeInfo` and `klines` endpoints (two requests); there were no private requests, account reads or orders. This establishes the observed data/fit/replay workflow, not forecast quality or other providers' history coverage.

Trained forecast origins and chart targets use the daily candle close time, when the close becomes available. Raw dataset timestamps and partition boundaries retain the archive’s opening-time convention; a target close can equal the exclusive end boundary of the partition containing its candle.

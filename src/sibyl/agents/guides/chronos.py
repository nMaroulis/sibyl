"""Forecasting instructions aligned with the trained registry and separate statistical baseline."""

from typing import Literal

from sibyl.agents.guides import Guide

Topic = Literal["outcomes", "overview", "inputs", "intervals", "models", "rolling", "portability"]
GUIDES = {
    "portability": Guide(
        "Move and organize trained research models",
        "/forecast?tab=models",
        (
            "Model library → Export portable bundle includes the recipe, recorded fit and full immutable daily input as bounded JSON.",
            "Import a model from another workspace → choose the JSON bundle → Import & verify. Sibyl checks hashes and input contracts and refits locally; uploaded coefficients and scores are never trusted. Repeated identical imports reuse the saved version.",
            "Imported provider origin is unverified and uses a separate import namespace. Use saved input for forecasts and historical evaluations; imports cannot become live forward evidence.",
            "Archive model hides the version from the default picker and disables new forecasts. Show archived versions → Restore model makes it selectable again. Outputs, evaluations and existing outcome monitors stay retained; archiving does not free storage or stop monitors.",
        ),
        (
            "16 MiB per bundle, known ridge/neural engine, 360–5,000 closed consecutive daily candles and existing workspace budgets apply. Bundles include price research, not API credentials or chat models.",
        ),
    ),
    "outcomes": Guide(
        "Follow live forecast outcomes",
        "/forecast?tab=models",
        (
            "Save a current-feed forecast and select it in Live forecast scorecard. Historical saved-input and Demo forecasts are excluded.",
            "The worker checks retained daily closes; Refresh matching feed explicitly fetches a bounded current page. Import older missing closes in Markets.",
            "Read original predictions against actuals, correction versions and equal-horizon benchmarks; pause/resume or export the evidence.",
        ),
        (
            "Targets must follow original save time. Missing prices stay missing; operator selection and overlapping forecasts limit interpretation.",
        ),
    ),
    "rolling": Guide(
        "Evaluate a recipe across successive periods",
        "/forecast?tab=models",
        (
            "Select a trained model, then open Rolling evaluation below its independent test results.",
            "Choose a horizon, test/calibration days and fold count. Expanding uses all earlier training history; Fixed window uses the selected number of training days.",
            "Run rolling evaluation uses the saved input offline. Inspect pooled benchmarks and each fold's boundaries, metrics and price trace. It creates a separate report; the model version stays unchanged.",
            "Reopen a retained report, Export rolling evidence, or Rerun exact evaluation. Ask Chronos includes the selected evaluation. The latest ten reports per model and one hundred workspace-wide are retained.",
        ),
        (
            "Prior test periods can join later training windows. Purged boundaries, overlapping multi-day targets and repeated experimentation limit interpretation; no automatic selection or deployment occurs.",
        ),
    ),
    "overview": Guide(
        "Train and inspect daily forecasts",
        "/forecast?tab=models",
        (
            "Open Trained models and choose current-feed daily prices or a saved immutable dataset.",
            "Select Train & evaluate, then inspect chronological test errors against naive and training-drift benchmarks.",
            "Forecast saved input offline, or explicitly read the latest matching feed. Ask Chronos about the selected model or saved result.",
        ),
        ("Statistical baseline is a separate tab. Research models never execute trades.",),
    ),
    "inputs": Guide(
        "Prepare forecast inputs",
        "/forecast?tab=models",
        (
            "Use an exact spot pair with 360–720 consecutive closed daily candles from the current feed.",
            "Saved daily datasets accept 360–5,000 candles. Prepare longer ranges in Markets → History & datasets.",
            "Try with Demo prices uses synthetic input through the same fitting/evaluation engine without activating an account or changing sources.",
        ),
        ("Missing, duplicated, open or nonconsecutive days are rejected; they are not interpolated.",),
    ),
    "intervals": Guide(
        "Interpret empirical and theoretical bands",
        "/forecast?tab=models",
        (
            "Trained models use chronological calibration log errors for nominal 90% bands, then report coverage on separate later test targets.",
            "Compare model error with naive/drift benchmarks; negative MAE skill means the naive forecast performed better.",
            "The baseline tab retains approximate 95% theoretical bands from constant historical drift/volatility.",
        ),
        (
            "Time-series dependence, overlapping targets and repeated experimentation limit interpretation. Bands do not guarantee prices or profitable trades.",
        ),
    ),
    "models": Guide(
        "Saved versions and model limits",
        "/forecast?tab=models",
        (
            "Each JSON artifact keeps its input fingerprint, source, engine, coefficients, train/calibration/test dates and complete evidence.",
            "Rerun exact training input saves a new numbered version without overwriting the old result or fetching prices.",
            "Model settings & assumptions offers return lags only or Returns + trend & volatility, adding six causal trailing-price statistics. The richer recipe is retained through rolling studies, predictions and portable refits; extra features do not establish better accuracy.",
            "Edit model settings explicitly for another experiment. AI model selection changes the assistant, not the numerical forecast model.",
        ),
        (
            "Ridge is the default. Model settings & assumptions → Numerical model also offers fixed-scale Huber autoregression: choose delta, then inspect actual IRLS steps, convergence, residual cutoff and downweighted counts. It accepts up to 2,000 saved daily candles and 30 days, requires no extra package, retains all rows and does not solve feature leverage. The same menu offers a trained 8-unit tanh network with 120 fixed Adam steps, training-only scaling and a 1,000-candle / 14-day cap. Inspect Neural training evidence and independent test benchmarks. ARIMA is also available: choose autoregressive p (1–3), moving-average q (0–2), with one log-price difference and drift. It accepts up to 1,000 daily candles and 14 days, uses one native statsmodels training-only fit for all horizons and an identical 90-close causal filter for testing/inference. ARIMA training evidence shows convergence, native coefficients, training likelihood and AIC/BIC; these do not replace held-out accuracy. Set Seasonality to Weekly to fit one additional AR term at a seven-day lag. Compare its held-out errors with the same-input nonseasonal fit; check the retained ar.S.L7 coefficient in Weekly SARIMA training evidence. Flat-return/nonconverged fits are rejected. Additional neural/model families remain pending. Retained-source candidate recalibration is separately opt-in and never promotes a model automatically.",
        ),
    ),
}

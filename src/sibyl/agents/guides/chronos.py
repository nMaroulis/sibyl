"""Forecasting instructions aligned with the trained registry and separate statistical baseline."""

from typing import Literal

from sibyl.agents.guides import Guide

Topic = Literal["overview", "inputs", "intervals", "models"]
GUIDES = {
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
            "Edit model settings explicitly for another experiment. AI model selection changes the assistant, not the numerical forecast model.",
        ),
        (
            "Trained autoregressive ridge is available. Neural/ARIMA models, rolling evaluation, automated recalibration and calibrated drift monitoring remain pending.",
        ),
    ),
}

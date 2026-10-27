"""Forecast page controls and the implemented statistical baseline."""

from typing import Literal

from sibyl.agents.guides import Guide

Topic = Literal["overview", "inputs", "intervals", "models"]
GUIDES = {
    "overview": Guide(
        "Explore a price baseline",
        "/forecast",
        (
            "Choose the market and displayed 7-, 14- or 30-day horizon in Forecasting.",
            "Read the observed history, baseline path and interval together with the source and Demo labels.",
            "Ask Chronos to explain the selected calculation and its assumptions.",
        ),
    ),
    "inputs": Guide(
        "Choose forecast inputs",
        "/forecast",
        (
            "Select the exact supported pair and horizon; market data use the configured source.",
            "Change market providers in Settings → Market data if your source cannot supply daily candle history.",
        ),
        (
            "A quotes-only source cannot supply this baseline. Missing history is not replaced with fabricated prices.",
        ),
    ),
    "intervals": Guide(
        "Interpret the baseline band",
        "/forecast",
        (
            "The central path extrapolates historical daily log-return drift; the band scales sample volatility with the square root of the horizon.",
            "Compare the horizon and assumptions before interpreting the width; it is an approximate model interval with no empirical calibration.",
        ),
        ("The band is not a guaranteed price range or a probability of a profitable trade.",),
    ),
    "models": Guide(
        "What is and is not trained",
        "/forecast",
        (
            "The implemented forecast is a statistical drift/volatility baseline, not trained Chronos model weights.",
            "An AI model lets Chronos explain evidence but does not train, replace or validate the forecasting calculation.",
        ),
        (
            "Training pipelines, trained artifacts, versioned forecasts and empirical calibration are pending.",
        ),
    ),
}

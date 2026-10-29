"""Chronos reads forecast models, held-out evidence and the separate price baseline.

The model chooses typed ProtoLink evidence or help tools; it does not train a
forecast model. Tool descriptions explain their purpose to the reasoning model.
"""

from typing import Annotated

from protolink import Agent
from pydantic import Field

from sibyl.agents.common import COMMON_PROMPT, Services, selected
from sibyl.agents.guides import read_guide
from sibyl.agents.guides.chronos import GUIDES, Topic
from sibyl.services.analytics import forecast

NAME = "Chronos"
TAGLINE = "Explore what comes next"
DESCRIPTION = (
    "Explain selected trained forecasts, model evaluation and baseline assumptions; guide Forecasting."
)
SYSTEM_PROMPT = (
    "Use page_help for Forecasting controls and setup, forecast_method for conceptual methodology, "
    "and price_forecast for a selected trained result or baseline. Use trained_models and model_report "
    "to inspect registry versions, chronological evaluation, naive/drift benchmarks, calibration and data provenance. "
    "Ask for a model, symbol or horizon when ambiguous. Trained autoregressive ridge coefficients and "
    "the untrained drift baseline are distinct. Negative skill means the naive benchmark performed better. "
    "Bands and input-shift checks provide research evidence, not guaranteed coverage, calibrated regime detection "
    "or profitable trade probabilities. You can read model evidence but cannot train, refit or save forecasts. "
)


def create_agent(services: Services, **runtime) -> Agent:
    """Declare Chronos's tools and expose them through ProtoLink's runtime transport."""
    market = services.market

    def price_forecast(
        symbol: str | None = None,
        horizon: Annotated[int | None, Field(ge=1, le=30)] = None,
        model_id: Annotated[str | None, Field(pattern=r"^[a-f0-9]{32}$")] = None,
    ) -> dict:
        """Read the page's saved trained forecast, or calculate its selected statistical baseline.

        Omit symbol and horizon to use the Forecasting page selection (otherwise
        BTC/USDT and 14 days). Supply an exact BASE/QUOTE pair for another market.
        Supply model_id from trained_models to choose a saved version outside this page.
        Returns the path, last price, source and relevant uncertainty evidence.
        When a trained model is selected, returns that version's retained result or an
        offline calculation from its frozen input, with empirical bands and provenance.
        Otherwise uses the untrained log-return baseline and theoretical interval.
        """
        explicit_model = model_id is not None
        identity = selected("forecast_model_id", model_id)
        if identity:
            if not services.forecasts:
                raise ValueError("Trained forecasting is unavailable in this workspace.")
            model = services.forecasts.detail(identity)["model"]
            symbol = symbol or (
                model["symbol"] if explicit_model else selected("symbol", None, model["symbol"])
            )
            horizon = horizon or (
                min(14, model["parameters"]["max_horizon"])
                if explicit_model
                else selected("horizon", None, min(14, model["parameters"]["max_horizon"]))
            )
            if symbol != model["symbol"]:
                raise ValueError("The selected trained model uses a different market. Choose its exact pair.")
            run_id = (
                selected("forecast_run_id", None)
                if not explicit_model or identity == selected("forecast_model_id", None)
                else None
            )
            return services.forecasts.preview(identity, horizon, run_id=run_id)
        symbol = selected("symbol", symbol, "BTC/USDT")
        horizon = selected("horizon", horizon, 14)
        if not 1 <= horizon <= 30:
            raise ValueError("Forecast horizon must be between 1 and 30 days.")
        with market.snapshot(selected("market_source", None, None)):
            return {
                "symbol": symbol,
                "source": market.source,
                **forecast(market.candles(symbol, 180), horizon),
            }

    def forecast_method() -> dict:
        """Explain trained autoregressive forecasts and the separate statistical baseline.

        Use for questions about forecast methodology or whether a model has been
        trained. Returns the implemented assumptions and calibration limitations.
        """
        return {
            "method": "Trained direct autoregressive ridge, or the separate untrained log-return baseline",
            "training": "Separate autoregressive ridge models use frozen daily input, chronological 60/20/20 train/calibration/test partitions and purged boundary-crossing targets.",
            "trained_intervals": "Nominal 90% bands from calibration log errors; held-out coverage is reported and future coverage is not guaranteed.",
            "horizon_days": [1, 30],
            "baseline_intervals": "Approximate 95% theoretical bands from constant historical drift/volatility, without empirical calibration.",
            "interpretation": "Neither model's bands are probabilities of profitable trades.",
        }

    def trained_models() -> dict:
        """List saved Chronos model versions, their exact markets, datasets and training settings.

        Use to find a model ID before inspecting its evaluation or a retained forecast.
        Returns the local registry only; does not train, fetch prices or select a model for the user.
        """
        rows = services.forecasts.list()["items"] if services.forecasts else []
        return {
            "items": [
                {
                    key: row[key]
                    for key in ("id", "label", "version", "symbol", "source", "environment", "parameters")
                }
                for row in rows[:20]
            ],
            "total": len(rows),
            "limit": 20,
        }

    def model_report(model_id: str | None = None) -> dict:
        """Inspect a trained model's test errors, naive/drift benchmarks and interval coverage.

        Omit model_id to use the Forecasting page selection. Returns dataset/source
        provenance, version, training/calibration/test dates, metrics and interpretation notes.
        """
        identity = selected("forecast_model_id", model_id)
        if not identity or not services.forecasts:
            raise ValueError("Select a trained model in Forecasting or choose an ID from trained_models.")
        report = services.forecasts.detail(identity)
        return {key: value for key, value in report.items() if key not in {"test_trace", "outputs"}}

    def page_help(topic: Topic = "overview") -> dict:
        """Explain Forecasting controls, input requirements, baseline intervals or model availability.

        Choose a topic for concrete instructions and an in-app link. Use overview for orientation.
        """
        return read_guide(GUIDES, topic)

    agent = Agent(
        name="sibyl-chronos",
        description=DESCRIPTION,
        tools=[price_forecast, forecast_method, page_help, trained_models, model_report],
        system_prompt=COMMON_PROMPT + SYSTEM_PROMPT,
        **runtime,
    )
    agent.card.capabilities.delegation = False
    return agent

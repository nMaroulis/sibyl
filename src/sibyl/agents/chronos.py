"""Chronos exposes the forecast baseline, its assumptions and Forecasting help.

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
    "Explain the selected forecast baseline, its intervals and assumptions; guide the Forecasting page."
)
SYSTEM_PROMPT = (
    "Use page_help for Forecasting controls and setup, forecast_method for conceptual methodology, "
    "and price_forecast for an actual selected calculation. Ask for a symbol or "
    "horizon if ambiguous. The implementation is a log-return statistical baseline with uncalibrated "
    "intervals, not Chronos trained weights or a validated price prediction. Never claim model training "
    "has occurred. "
)


def create_agent(services: Services, **runtime) -> Agent:
    """Declare Chronos's tools and expose them through ProtoLink's runtime transport."""
    market = services.market

    def price_forecast(
        symbol: str | None = None, horizon: Annotated[int | None, Field(ge=1, le=30)] = None
    ) -> dict:
        """Calculate a daily price baseline and approximate interval for a spot market.

        Omit symbol and horizon to use the Forecasting page selection (otherwise
        BTC/USDT and 14 days). Supply an exact BASE/QUOTE pair for another market.
        Returns the baseline path, last price, historical volatility and source label.
        This statistical calculation does not use trained Chronos weights.
        """
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
        """Explain the log-return baseline, supported horizon and interpretation of its interval.

        Use for questions about forecast methodology or whether a model has been
        trained. Returns the implemented assumptions and calibration limitations.
        """
        return {
            "method": "Historical log-return drift and volatility baseline",
            "training": "No trained Chronos model or ML pipeline is implemented.",
            "horizon_days": [1, 30],
            "intervals": "Approximate, uncalibrated; not probabilities of profitable trades.",
        }

    def page_help(topic: Topic = "overview") -> dict:
        """Explain Forecasting controls, input requirements, baseline intervals or model availability.

        Choose a topic for concrete instructions and an in-app link. Use overview for orientation.
        """
        return read_guide(GUIDES, topic)

    agent = Agent(
        name="sibyl-chronos",
        description=DESCRIPTION,
        tools=[price_forecast, forecast_method, page_help],
        system_prompt=COMMON_PROMPT + SYSTEM_PROMPT,
        **runtime,
    )
    agent.card.capabilities.delegation = False
    return agent

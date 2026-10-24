"""Chronos: its prompt, read-only tools and native ProtoLink Agent."""

from protolink import Agent

from sibyl.agents.common import COMMON_PROMPT, Services, background_tool, selected
from sibyl.services.analytics import forecast

NAME = "Chronos"
TAGLINE = "Explore what comes next"
DESCRIPTION = "Explain statistical forecast assumptions and uncalibrated intervals."
SYSTEM_PROMPT = (
    "Explain the selected market forecast using price_forecast and forecast_method. Ask for a symbol or "
    "horizon if ambiguous. The implementation is a log-return statistical baseline with uncalibrated "
    "intervals, not Chronos trained weights or a validated price prediction. Never claim model training "
    "has occurred. "
)


def create_agent(services: Services, **runtime) -> Agent:
    """Declare Chronos's tools and expose them through ProtoLink's runtime transport."""
    market = services.market

    def price_forecast(symbol: str | None = None, horizon: int | None = None) -> dict:
        """Read a statistical baseline for the selected market and 1–30 day horizon."""
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
        """Explain the current forecast implementation and its limitations."""
        return {
            "method": "Historical log-return drift and volatility baseline",
            "training": "No trained Chronos model or ML pipeline is implemented.",
            "horizon_days": [1, 30],
            "intervals": "Approximate, uncalibrated; not probabilities of profitable trades.",
        }

    agent = Agent(
        name="sibyl-chronos",
        description=DESCRIPTION,
        tools=[background_tool(price_forecast), background_tool(forecast_method)],
        system_prompt=COMMON_PROMPT + SYSTEM_PROMPT,
        **runtime,
    )
    agent.card.capabilities.delegation = False
    return agent

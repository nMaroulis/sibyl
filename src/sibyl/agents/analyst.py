"""Analyst: its prompt, read-only tools and native ProtoLink Agent."""

from protolink import Agent

from sibyl.agents.common import COMMON_PROMPT, Services, background_tool, selected
from sibyl.services.analytics import analyze
from sibyl.services.market import TIMEFRAMES

NAME = "Analyst"
TAGLINE = "Find the signal"
DESCRIPTION = "Interpret technical indicators and correlations without overstating predictive power."
SYSTEM_PROMPT = (
    "Interpret market prices, RSI, EMA alignment, volatility and correlations. Call market_analysis for "
    "the requested symbol, timeframe and source. An omitted selection uses the current page; a "
    "different coin named by the user requires its explicit BASE/QUOTE symbol. Explain indicator "
    "limitations with analysis_help. Never present technical indicators as certain forecasts. "
)


def create_agent(services: Services, **runtime) -> Agent:
    """Declare Analyst's tools and expose them through ProtoLink's runtime transport."""
    market = services.market

    def market_analysis(
        symbol: str | None = None,
        timeframe: str | None = None,
        limit: int | None = None,
        source: str | None = None,
    ) -> dict:
        """Read exact page-selected quotes or indicators from one frozen source."""
        symbol = selected("symbol", symbol, "BTC/USDT")
        timeframe = selected("timeframe", timeframe, "1d")
        limit = selected("limit", limit, 180)
        source = selected("market_source", source, "")
        if timeframe not in TIMEFRAMES or not 60 <= limit <= 720:
            raise ValueError("Choose a supported timeframe and 60–720 candles.")
        with market.snapshot(source or None):
            market.client().market(symbol)
            metadata = market.metadata()
            if not metadata["capabilities"]["candles"]:
                return {
                    "symbol": symbol,
                    **metadata,
                    "price": market.price(symbol),
                    "note": "Quotes only. This adapter cannot provide candle indicators or history.",
                }
            result = analyze(market.candles(symbol, limit, timeframe), 365 * 86400 / TIMEFRAMES[timeframe])
            return {
                "symbol": symbol,
                "timeframe": timeframe,
                **metadata,
                **{key: value for key, value in result.items() if key != "candles"},
            }

    def analysis_help() -> dict:
        """Explain implemented indicators, source selection and their limits."""
        return {
            "indicators": ["RSI", "EMA trend", "annualized return volatility", "correlation"],
            "settings_url": "/settings?tab=market",
            "note": "Indicators describe past observations, not guaranteed future returns. Quotes-only sources cannot supply candle indicators.",
        }

    agent = Agent(
        name="sibyl-analyst",
        description=DESCRIPTION,
        tools=[background_tool(market_analysis), background_tool(analysis_help)],
        system_prompt=COMMON_PROMPT + SYSTEM_PROMPT,
        **runtime,
    )
    agent.card.capabilities.delegation = False
    return agent

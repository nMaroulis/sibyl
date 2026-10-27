"""Analyst combines computed market evidence with practical Markets guidance.

ProtoLink derives tool descriptions and argument schemas from these functions;
page instructions are retrieved separately from prices and statistical evidence.
"""

from typing import Annotated

from protolink import Agent
from pydantic import Field

from sibyl.agents.common import COMMON_PROMPT, Services, selected
from sibyl.agents.guides import read_guide
from sibyl.agents.guides.analyst import GUIDES, Topic
from sibyl.services.analytics import analyze
from sibyl.services.market import TIMEFRAMES

NAME = "Analyst"
TAGLINE = "Find the signal"
DESCRIPTION = "Interpret market prices, technical statistics and directional scores; explain Markets controls and indicator limitations."
SYSTEM_PROMPT = (
    "Use page_help for Markets navigation, chart controls, source/pair selection, watchlists and history. "
    "Interpret market prices, trend, momentum, drawdowns, volatility, volume and levels. Call market_analysis for "
    "the requested symbol, timeframe and source. An omitted selection uses the current page; a "
    "different coin named by the user requires its explicit BASE/QUOTE symbol. Explain indicator "
    "limitations with analysis_help. market_analysis includes statistics and a technical-bias score with weighted votes. Explain the score as bullish/bearish direction, never a buy/sell recommendation, investment quality, safety or probability of profit. Report source, timeframe, actual sample, gaps, stale data and missing inputs. Statistics use the latest contiguous segment and do not follow browser chart zoom. Never present technical indicators as certain forecasts. "
)


def create_agent(services: Services, **runtime) -> Agent:
    """Declare Analyst's tools and expose them through ProtoLink's runtime transport."""
    market = services.market

    def market_analysis(
        symbol: str | None = None,
        timeframe: str | None = None,
        limit: Annotated[int | None, Field(ge=60, le=720)] = None,
        source: str | None = None,
    ) -> dict:
        """Analyze a spot market's price, trend, momentum, volatility, risk, volume and technical bias.

        Use for questions about actual market conditions. Omitted arguments follow the
        selected pair, timeframe, observation count and source on Markets; otherwise
        defaults are BTC/USDT, 1d and 180 candles. Specify an exact BASE/QUOTE symbol
        when the user asks for another market. Returns calculated statistics, score votes,
        sample coverage and source labels; quotes-only providers return a quote instead.
        Chart zoom does not change this calculation's sample.
        """
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
        """Explain the available technical indicators and the directional score's weighting and limits.

        Use for definitions or methodology, rather than current market values. Includes
        the statistics-methodology link; page_help covers chart and source controls.
        """
        return {
            "indicators": [
                "SMA 20/50/200 and EMA 9/21",
                "RSI 14",
                "MACD 12/26/9",
                "ADX 14",
                "Stochastic 14/3",
                "ATR 14 and Bollinger 20/2",
                "CMF 20 and OBV change",
                "20-candle typical-price VWAP",
                "return distributions",
                "sample drawdowns",
                "zero-rate Sharpe and Sortino",
                "empirical one-candle VaR/ES 95%",
                "prior 20-candle extremes and previous-candle classic pivots",
                "correlation",
            ],
            "score": "technical-bias-v1: EMA alignment 25%, close/SMA50 20%, MACD/signal 20%, RSI 20%, CMF 15%. Votes are 0/50/100; available weights are normalized. Requires 50 consecutive fresh candles and at least 80% available weight. It is a heuristic, not validated predictive confidence.",
            "methodology": "https://nmaroulis.github.io/sibyl/guides/market-statistics",
            "settings_url": "/settings?tab=market",
            "note": "Indicators describe past observations, not guaranteed future returns. Quotes-only sources cannot supply candle indicators.",
        }

    def page_help(topic: Topic = "overview") -> dict:
        """Explain Markets controls: sources, any supported pair, watchlist, chart zoom, statistics, correlations or history.

        Choose a topic for practical steps and a destination link. Use overview for
        orientation; market_analysis provides actual quotes and computed statistics.
        """
        return read_guide(GUIDES, topic)

    agent = Agent(
        name="sibyl-analyst",
        description=DESCRIPTION,
        tools=[market_analysis, analysis_help, page_help],
        system_prompt=COMMON_PROMPT + SYSTEM_PROMPT,
        **runtime,
    )
    agent.card.capabilities.delegation = False
    return agent

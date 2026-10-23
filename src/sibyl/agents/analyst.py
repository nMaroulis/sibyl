"""Analyst: its prompt, read-only tools and native ProtoLink Agent."""

from protolink import Agent

from sibyl.agents.common import COMMON_PROMPT, Services, background_tool, selected
from sibyl.services.analytics import analyze
from sibyl.services.market import TIMEFRAMES

NAME = "Analyst"
TAGLINE = "Find the signal"
DESCRIPTION = "Interpret technical indicators and correlations without overstating predictive power."
SYSTEM_PROMPT = (
    "Interpret market prices, trend, momentum, drawdowns, volatility, volume, levels and correlations. Call market_analysis for "
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

    agent = Agent(
        name="sibyl-analyst",
        description=DESCRIPTION,
        tools=[background_tool(market_analysis), background_tool(analysis_help)],
        system_prompt=COMMON_PROMPT + SYSTEM_PROMPT,
        **runtime,
    )
    agent.card.capabilities.delegation = False
    return agent

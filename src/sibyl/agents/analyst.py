"""Analyst combines computed market evidence with practical Markets guidance.

ProtoLink derives tool descriptions and argument schemas from these functions;
page instructions are retrieved separately from prices and statistical evidence.
"""

from typing import Annotated, Literal

from protolink import Agent, Tool
from pydantic import Field

from sibyl.agents.guides import read_guide
from sibyl.agents.guides.analyst import GUIDES, Topic
from sibyl.agents.utils.common import COMMON_PROMPT, Services, selected
from sibyl.services.markets.analytics import analyze, correlation
from sibyl.services.markets.service import TIMEFRAMES

NAME = "Analyst"
TAGLINE = "Find the signal"
DESCRIPTION = "Interpret market prices, technical statistics and directional scores; explain Markets controls and indicator limitations."
SYSTEM_PROMPT = (
    "Use market_analysis for exact pair, feed and closed-candle indicators. Follow the page unless the user specifies "
    "another BASE/QUOTE pair. Attribute source, timeframe, coverage and stale or missing data. Technical-bias votes "
    "describe historical direction. Avoid investment recommendations or profit odds. Chart zoom does not affect statistics. "
    "Use market_relationships for dependence, same-interval OLS/Theil–Sen and Granger lag tests. Explain shared samples, "
    "serial dependence and gaps. Distance is unsigned and sample-biased. Regression beta is descriptive. Granger "
    "adjustment covers one request; distinguish classical inference from held-out errors. No result shows causation. "
    "Use live_market_status for public forming previews and actual feed health. Empty means no active viewer. "
    "Coinbase previews use exact products and native 5m candles; other intervals retain REST candles. Check source "
    "and actual trade freshness. Use page_help for navigation and analysis_help for indicator definitions."
)


def create_agent(services: Services, **runtime) -> Agent:
    """Register this specialist's evidence and help tools on a native Agent.

    Args:
        services: Workspace domain services; credentials stay in their owners.
        **runtime: AgentGroup configuration, including the lazy model factory,
            native state, worker defaults and context policy.

    Returns:
        An unstarted Agent. Static guides run inline; domain reads inherit the
        runtime's execution policy (bounded threads in Sibyl). AgentGroup owns
        startup and shutdown.
    """
    market = services.market

    def market_analysis(
        symbol: str | None = None,
        timeframe: str | None = None,
        limit: Annotated[int | None, Field(ge=60, le=720)] = None,
        source: str | None = None,
    ) -> dict:
        """Analyze closed candles for an exact pair, interval and source, or follow the Markets page.
        Returns indicators, descriptive statistics, assessment components and coverage. A score
        summarizes historical conditions, not future returns or a recommendation. Disclose stale or
        short inputs.
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

    def market_relationships(
        symbols: Annotated[list[str] | None, Field(min_length=2, max_length=8)] = None,
        method: Literal["pearson", "spearman", "distance"] | None = None,
        transform: Literal["log_returns", "prices", "changes"] | None = None,
        timeframe: str | None = None,
        limit: Annotated[int | None, Field(ge=30, le=720)] = None,
        source: str | None = None,
        lags: Annotated[int | None, Field(ge=1, le=5)] = None,
        robust: bool | None = None,
    ) -> dict:
        """Compare exact spot-pair dependence and reference-first return regressions.

        Defaults follow Markets. Set robust to compare Theil–Sen and OLS on the same
        returns. Set lags (1–5) for Granger F tests, adjusted p-values and held-out
        errors. Constants and gaps stay explicit. Results do not show causation.
        """
        from sibyl.models import OrderRequest

        symbol = selected("symbol", None, "BTC/USDT")
        symbols = selected("comparison_symbols", symbols) or [
            symbol,
            "ETH/USDT" if symbol == "BTC/USDT" else "BTC/USDT",
        ]
        method = selected("correlation_method", method, "pearson")
        transform = selected("correlation_transform", transform, "log_returns")
        symbols = list(dict.fromkeys(OrderRequest.valid_symbol(item) for item in symbols))
        timeframe = selected("timeframe", timeframe, "1d")
        limit = selected("limit", limit, 180)
        if not 2 <= len(symbols) <= 8 or timeframe not in TIMEFRAMES or not 30 <= limit <= 720:
            raise ValueError(
                "Choose two to eight distinct spot pairs, a supported timeframe and 30–720 candles."
            )
        with market.snapshot(selected("market_source", source, None)):
            for pair in symbols:
                market.client().market(pair)
            histories = {pair: market.candles(pair, limit, timeframe) for pair in symbols}
            result = correlation(
                histories,
                method,
                transform,
                seconds=TIMEFRAMES[timeframe],
                robust=selected("robust_regression", robust, False),
            )
            order = selected("granger_lags", lags)
            if order is not None:
                from sibyl.market_data.analysis.granger import granger

                result["granger"] = granger(histories, seconds=TIMEFRAMES[timeframe], lags=order)
                for item in result["granger"]["items"]:
                    item.pop("models", None)
            result["regression"]["items"] = [
                {key: value for key, value in row.items() if key != "points"}
                for row in result["regression"]["items"]
            ]
            return {**market.metadata(), "timeframe": timeframe, **result, "url": "/markets?tab=correlation"}

    def live_market_status(source: str | None = None) -> dict:
        """Inspect the selected market feed's live connection, freshness, interruptions and fallback status.

        Omit source to follow the page. Returns observed public ticker/candle stream
        activity and last previews for currently viewed markets. An empty list means
        no active viewer; it does not prove an outage. Forming candles are separate
        from the closed-candle statistics returned by market_analysis.
        """
        source = selected("market_source", source, "")
        return market.live.snapshot(source or None)

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
        tools=[
            market_analysis,
            market_relationships,
            live_market_status,
            Tool.from_callable(analysis_help, sync_execution="inline"),
            Tool.from_callable(page_help, sync_execution="inline"),
        ],
        system_prompt=COMMON_PROMPT + SYSTEM_PROMPT,
        **runtime,
    )
    agent.card.capabilities.delegation = False
    return agent

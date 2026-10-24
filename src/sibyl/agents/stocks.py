"""Equity Analyst: its prompt, read-only tools and native ProtoLink Agent."""

from protolink import Agent

from sibyl.agents.common import COMMON_PROMPT, Services, background_tool, selected

NAME = "Equity Analyst"
TAGLINE = "A wider market lens"
DESCRIPTION = "Explain an equity quote and its observed history. Never invent company fundamentals."
SYSTEM_PROMPT = (
    "Explain the requested equity quote and observed daily history using equity_quote. Use equity_help "
    "to explain available sources and optional setup. State the ticker, quote currency, history period, "
    "demo status and missing fundamentals. Never invent earnings, disclosures or advanced analytics. "
)


def create_agent(services: Services, **runtime) -> Agent:
    """Declare Equity Analyst's tools and expose them through ProtoLink's runtime transport."""
    research = services.research

    def equity_quote(symbol: str | None = None) -> dict:
        """Read one equity quote and daily history from the configured data source."""
        symbol = selected("equity_symbol", symbol, "AAPL")
        result = research.stock(symbol)
        return {**result, "history": result["history"][-7:]}

    def equity_help() -> dict:
        """Explain equity data setup, supported demo tickers and missing advanced research."""
        return {
            "source": "Yahoo Finance via the optional yfinance dependency in live mode",
            "installation": "uv sync --extra stocks",
            "demo_tickers": ["AAPL", "MSFT", "NVDA", "COIN"],
            "note": "Demo data are illustrative. Disclosure archives and advanced company analytics are not implemented.",
        }

    agent = Agent(
        name="sibyl-stocks",
        description=DESCRIPTION,
        tools=[background_tool(equity_quote), background_tool(equity_help)],
        system_prompt=COMMON_PROMPT + SYSTEM_PROMPT,
        **runtime,
    )
    agent.card.capabilities.delegation = False
    return agent

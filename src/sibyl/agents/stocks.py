"""Equity Analyst exposes supplied equity evidence and Research → Equities help.

Typed native tools describe the observations they provide; the separate guide
tool explains controls and setup without contacting a quote provider.
"""

from protolink import Agent

from sibyl.agents.common import COMMON_PROMPT, Services, selected
from sibyl.agents.guides import read_guide
from sibyl.agents.guides.stocks import GUIDES, Topic

NAME = "Equity Analyst"
TAGLINE = "A wider market lens"
DESCRIPTION = (
    "Explain equity quotes, observed history and available company data; guide equity research setup."
)
SYSTEM_PROMPT = (
    "Use page_help for Equities navigation and controls. Explain the requested equity quote and "
    "observed daily history using equity_quote, including company fields only when actually returned. Use equity_help "
    "to explain available sources and optional setup. State the ticker, quote currency, history period, "
    "demo status and missing fundamentals. Never invent earnings, disclosures or advanced analytics. "
)


def create_agent(services: Services, **runtime) -> Agent:
    """Declare Equity Analyst's tools and expose them through ProtoLink's runtime transport."""
    research = services.research

    def equity_quote(symbol: str | None = None) -> dict:
        """Get an equity's quote, available company profile and seven recent daily observations.

        Omit symbol to use the selected ticker (otherwise AAPL), or supply an explicit
        ticker. Returns the configured source's evidence, currency and Demo/availability labels.
        """
        symbol = selected("equity_symbol", symbol, "AAPL")
        result = research.stock(symbol)
        return {**result, "history": result["history"][-7:]}

    def equity_help() -> dict:
        """Explain the live equity-data dependency, sample tickers and research limitations.

        Use for provider setup or capability questions, rather than a current quote.
        """
        return {
            "source": "Yahoo Finance via the optional yfinance dependency in live mode",
            "installation": "uv sync --extra stocks",
            "demo_tickers": ["AAPL", "MSFT", "NVDA", "COIN"],
            "note": "Demo data are illustrative. Disclosure archives and advanced company analytics are not implemented.",
        }

    def page_help(topic: Topic = "overview") -> dict:
        """Explain Equities controls, live data setup, displayed statistics or research limitations.

        Choose a topic for practical steps and a destination link; equity_quote supplies actual observations.
        """
        return read_guide(GUIDES, topic)

    agent = Agent(
        name="sibyl-stocks",
        description=DESCRIPTION,
        tools=[equity_quote, equity_help, page_help],
        system_prompt=COMMON_PROMPT + SYSTEM_PROMPT,
        **runtime,
    )
    agent.card.capabilities.delegation = False
    return agent

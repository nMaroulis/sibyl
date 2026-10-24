"""Oracle: its prompt, read-only tools and native ProtoLink Agent."""

from protolink import Agent

from sibyl.agents.common import COMMON_PROMPT, Services, background_tool, selected

NAME = "Oracle"
TAGLINE = "Your portfolio, in perspective"
DESCRIPTION = "Connect portfolio context with market observations and explain uncertainty."
SYSTEM_PROMPT = (
    "Help the user understand their combined or selected-account portfolio. Call portfolio_snapshot for "
    "workspace facts; do not guess balances. Explain concentration, pricing coverage and "
    "demo/test/production labels. Explain how Sibyl modules fit together and consult the user about "
    "ambiguous account scopes. "
)


def create_agent(services: Services, **runtime) -> Agent:
    """Declare Oracle's tools and expose them through ProtoLink's runtime transport."""
    portfolio = services.portfolio

    def portfolio_snapshot(scope: str | None = None) -> dict:
        """Read priced holdings, source labels, warnings, and account allocation."""
        scope = selected("portfolio_scope", scope, "all")
        result = portfolio.overview(scope)
        return {key: value for key, value in result.items() if key != "history"}

    agent = Agent(
        name="sibyl-oracle",
        description=DESCRIPTION,
        tools=[background_tool(portfolio_snapshot)],
        system_prompt=COMMON_PROMPT + SYSTEM_PROMPT,
        **runtime,
    )
    agent.card.capabilities.delegation = False
    return agent

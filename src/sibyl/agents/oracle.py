"""Oracle puts account holdings in context and explains the workspace's modules.

This specialist does not delegate. Sibyl remains the coordinator; native tools
here provide portfolio observations or focused workspace instructions.
"""

from protolink import Agent

from sibyl.agents.common import COMMON_PROMPT, Services, selected
from sibyl.agents.guides import read_guide
from sibyl.agents.guides.oracle import GUIDES, Topic

NAME = "Oracle"
TAGLINE = "Your portfolio, in perspective"
DESCRIPTION = (
    "Explain combined or selected-account holdings, portfolio context and how Sibyl's modules fit together."
)
SYSTEM_PROMPT = (
    "Use page_help for workspace navigation, accounts, assistants, model setup or messaging. "
    "Help the user understand their combined or selected-account portfolio. Call portfolio_snapshot for "
    "workspace facts; do not guess balances. Explain concentration, pricing coverage and "
    "demo/test/production labels. Explain how Sibyl modules fit together and consult the user about "
    "ambiguous account scopes. "
)


def create_agent(services: Services, **runtime) -> Agent:
    """Declare Oracle's tools and expose them through ProtoLink's runtime transport."""
    portfolio = services.portfolio

    def portfolio_snapshot(scope: str | None = None) -> dict:
        """Inspect holdings, allocation, prices and valuation warnings for the requested account scope.

        Omit scope to follow Account's current selection, otherwise use 'all' or an exact
        scope returned by the account selector. Includes source/environment labels and
        unpriced coverage. Use page_help for navigation without reading balances.
        """
        scope = selected("portfolio_scope", scope, "all")
        result = portfolio.overview(scope)
        return {key: value for key, value in result.items() if key != "history"}

    def page_help(topic: Topic = "overview") -> dict:
        """Explain workspace navigation, combined accounts, specialist/Sibyl chats, model setup or messaging.

        Choose a topic for concrete steps and an in-app link. overview describes each
        module; this tool provides instructions rather than portfolio observations.
        """
        return read_guide(GUIDES, topic)

    agent = Agent(
        name="sibyl-oracle",
        description=DESCRIPTION,
        tools=[portfolio_snapshot, page_help],
        system_prompt=COMMON_PROMPT + SYSTEM_PROMPT,
        **runtime,
    )
    agent.card.capabilities.delegation = False
    return agent

"""Explorer explains observed Bitcoin blocks, chain concepts and explorer controls.

Native evidence and help tools keep current observations separate from curated
instructions. ProtoLink reads their docstrings as model-facing descriptions.
"""

from protolink import Agent

from sibyl.agents.common import COMMON_PROMPT, Services
from sibyl.agents.guides import read_guide
from sibyl.agents.guides.explorer import GUIDES, Topic

NAME = "Explorer"
TAGLINE = "Follow the chain"
DESCRIPTION = "Explain recent Bitcoin blocks, confirmations and how to use the block explorer."
SYSTEM_PROMPT = (
    "Use page_help for explorer controls and navigation. Explain Bitcoin blocks, confirmations "
    "and chain mechanics. Call bitcoin_blocks for recent source- "
    "labeled block observations and blockchain_help for concepts. You cannot inspect an arbitrary "
    "address or transaction yet; say so and direct the user to the linked public explorer. Never invent "
    "on-chain activity. "
)


def create_agent(services: Services, **runtime) -> Agent:
    """Declare Explorer's tools and expose them through ProtoLink's runtime transport."""
    research = services.research

    def bitcoin_blocks() -> dict:
        """Get recent Bitcoin block heights, timestamps, transaction counts, sizes and source labels.

        Use to explain observed chain activity or the displayed blocks. These summaries
        do not provide arbitrary transaction or address lookup.
        """
        return research.blocks()

    def blockchain_help() -> dict:
        """Explain Bitcoin confirmations, available block fields and supported explorer scope.

        Use for chain concepts and capability questions; bitcoin_blocks supplies actual observations.
        """
        return {
            "network": "Bitcoin",
            "supported": "Recent block heights, timestamps, transaction counts and size.",
            "confirmations": "Each block after inclusion adds a confirmation; block times vary.",
            "not_implemented": ["address inspection", "transaction lookup", "additional chains"],
            "source": "https://mempool.space/",
        }

    def page_help(topic: Topic = "overview") -> dict:
        """Explain the block explorer's controls, block statistics/export or where to inspect a transaction.

        Choose a topic for practical steps, an in-app destination and current scope.
        """
        return read_guide(GUIDES, topic)

    agent = Agent(
        name="sibyl-explorer",
        description=DESCRIPTION,
        tools=[bitcoin_blocks, blockchain_help, page_help],
        system_prompt=COMMON_PROMPT + SYSTEM_PROMPT,
        **runtime,
    )
    agent.card.capabilities.delegation = False
    return agent

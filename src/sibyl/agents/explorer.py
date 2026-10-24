"""Explorer: its prompt, read-only tools and native ProtoLink Agent."""

from protolink import Agent

from sibyl.agents.common import COMMON_PROMPT, Services, background_tool

NAME = "Explorer"
TAGLINE = "Follow the chain"
DESCRIPTION = "Explain recent Bitcoin blocks and confirmation mechanics using supplied block data."
SYSTEM_PROMPT = (
    "Explain Bitcoin blocks, confirmations and chain mechanics. Call bitcoin_blocks for recent source- "
    "labeled block observations and blockchain_help for concepts. You cannot inspect an arbitrary "
    "address or transaction yet; say so and direct the user to the linked public explorer. Never invent "
    "on-chain activity. "
)


def create_agent(services: Services, **runtime) -> Agent:
    """Declare Explorer's tools and expose them through ProtoLink's runtime transport."""
    research = services.research

    def bitcoin_blocks() -> dict:
        """Read recent Bitcoin blocks with transaction counts and source labels."""
        return research.blocks()

    def blockchain_help() -> dict:
        """Explain available Bitcoin research and the limits of the built-in explorer."""
        return {
            "network": "Bitcoin",
            "supported": "Recent block heights, timestamps, transaction counts and size.",
            "confirmations": "Each block after inclusion adds a confirmation; block times vary.",
            "not_implemented": ["address inspection", "transaction lookup", "additional chains"],
            "source": "https://mempool.space/",
        }

    agent = Agent(
        name="sibyl-explorer",
        description=DESCRIPTION,
        tools=[background_tool(bitcoin_blocks), background_tool(blockchain_help)],
        system_prompt=COMMON_PROMPT + SYSTEM_PROMPT,
        **runtime,
    )
    agent.card.capabilities.delegation = False
    return agent

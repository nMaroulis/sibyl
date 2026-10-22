"""Wiki: its prompt, read-only tools and native ProtoLink Agent."""

from protolink import Agent

from sibyl.agents.common import COMMON_PROMPT, Services, background_tool, selected

NAME = "Wiki"
TAGLINE = "Make the complex clear"
DESCRIPTION = "Teach crypto concepts using the supplied glossary, public crypto profiles, and source links."
SYSTEM_PROMPT = (
    "Teach crypto concepts using search_knowledge. Use crypto_catalog to find a supported crypto ID "
    "before requesting its sourced profile. Explain concepts plainly, include returned sources, "
    "distinguish glossary facts from public profile history and disclose unavailable data. Do not "
    "invent token fundamentals. "
)


def create_agent(services: Services, **runtime) -> Agent:
    """Declare Wiki's tools and expose them through ProtoLink's runtime transport."""
    research = services.research

    def search_knowledge(query: str | None = None, crypto_id: str | None = None) -> list[dict] | dict:
        """Search the glossary or read the selected backend-fetched crypto profile, with sources."""
        crypto_id = selected("crypto_id", crypto_id, "")
        query = selected("query", query, "")
        return research.crypto.profile(crypto_id) if crypto_id else research.knowledge(query)[:6]

    def crypto_catalog() -> dict:
        """List supported crypto profile IDs so a profile can be selected explicitly."""
        return research.crypto.catalog()

    agent = Agent(
        name="sibyl-wiki",
        description=DESCRIPTION,
        tools=[background_tool(search_knowledge), background_tool(crypto_catalog)],
        system_prompt=COMMON_PROMPT + SYSTEM_PROMPT,
        **runtime,
    )
    agent.card.capabilities.delegation = False
    return agent

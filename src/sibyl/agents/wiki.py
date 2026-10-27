"""Wiki teaches sourced crypto concepts and guides the Research library.

Native tools distinguish glossary searches, public project evidence and page
instructions. ProtoLink publishes their typed arguments and docstrings.
"""

from protolink import Agent

from sibyl.agents.common import COMMON_PROMPT, Services, selected
from sibyl.agents.guides import read_guide
from sibyl.agents.guides.wiki import GUIDES, Topic

NAME = "Wiki"
TAGLINE = "Make the complex clear"
DESCRIPTION = "Teach crypto concepts, explain sourced project profiles and help users browse Research."
SYSTEM_PROMPT = (
    "Use page_help for Research controls and source explanations. Teach crypto concepts using "
    "search_knowledge(query=...) explicitly for a glossary question, even on a project page. "
    "Use crypto_catalog to find a supported crypto ID "
    "before requesting its sourced profile. Explain concepts plainly, include returned sources, "
    "distinguish glossary facts from public profile history and disclose unavailable data. Do not "
    "invent token fundamentals. "
)


def create_agent(services: Services, **runtime) -> Agent:
    """Declare Wiki's tools and expose them through ProtoLink's runtime transport."""
    research = services.research

    def search_knowledge(query: str | None = None, crypto_id: str | None = None) -> list[dict] | dict:
        """Find sourced glossary definitions or read a particular crypto project's profile and history.

        Pass query for a glossary search, or crypto_id from crypto_catalog for a project
        profile. An explicit glossary query overrides the page's selected project.
        Omit both to follow the Research page selection. Returns up to six glossary
        entries or the profile's attributable sections and source availability.
        """
        crypto_id = selected("crypto_id", crypto_id, "") if query is None else (crypto_id or "")
        query = selected("query", query, "")
        return research.crypto.profile(crypto_id) if crypto_id else research.knowledge(query)[:6]

    def crypto_catalog() -> dict:
        """Find the supported project names, symbols and profile IDs for crypto research.

        Use before requesting a particular project's profile with search_knowledge.
        This curated selection is not a live market-cap ranking.
        """
        return research.crypto.catalog()

    def page_help(topic: Topic = "overview") -> dict:
        """Explain Research's glossary, crypto profiles and their sources with practical steps and links.

        Choose a topic or overview for orientation. Use the research tools for actual
        definitions or project evidence rather than navigation instructions.
        """
        return read_guide(GUIDES, topic)

    agent = Agent(
        name="sibyl-wiki",
        description=DESCRIPTION,
        tools=[
            search_knowledge,
            crypto_catalog,
            page_help,
        ],
        system_prompt=COMMON_PROMPT + SYSTEM_PROMPT,
        **runtime,
    )
    agent.card.capabilities.delegation = False
    return agent

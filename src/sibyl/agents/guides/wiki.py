"""Research navigation, glossary and attributable project profiles."""

from typing import Literal

from sibyl.agents.guides import Guide

Topic = Literal["overview", "glossary", "profiles", "sources", "library"]
GUIDES = {
    "library": Guide(
        "Use your research library",
        "/research?tab=library",
        (
            "Add a text PDF, UTF-8 text or Markdown source, optionally naming its author, URL and publication date.",
            "Search uploads and retained news by keyword, then open exact passages/page numbers. Optionally expand Semantic search, check/save an installed local Ollama embedding model and explicitly index passages; choose Semantic or Hybrid next to the query. Check scoped coverage and continue missing batches when needed.",
            "Ask Wiki or Reporter to retrieve and cite passages. Reindex uploads from their retained originals; remove a source to delete its original and search entries.",
        ),
        (
            "Imported passages can be sent to the configured model when requested; keep credentials out of files. Scans need OCR before import. Ranks and cosine scores are relevance, not confidence or verified truth. Semantic search needs its separate local embedding setup and only covers indexed passages. Saving a model or reindexing a source clears relevant vectors. Cited web search and broader model quality evaluation remain pending.",
        ),
    ),
    "overview": Guide(
        "Use crypto research",
        "/research?tab=knowledge",
        (
            "Crypto knowledge searches the built-in glossary; Crypto profiles provides backend-fetched information about 20 selected projects.",
            "Block explorer and Equities are separate Research tabs with their own specialists.",
        ),
    ),
    "glossary": Guide(
        "Find a crypto concept",
        "/research?tab=knowledge",
        (
            "Search Crypto knowledge by keyword, such as RSI, custody or diversification, and follow the returned reference links.",
            "Ask Wiki to explain a concept plainly or compare the sourced definitions.",
        ),
        (
            "This is a curated glossary. My research separately supports imported documents and retained-news passage search. Optional local semantic/hybrid search is configured in My research, separately from chat models. Cited web search remains pending.",
        ),
    ),
    "profiles": Guide(
        "Read a project's background",
        "/research?tab=crypto",
        (
            "Search Crypto profiles by project name or symbol, optionally filter category, then select a project.",
            "Inspect overview, history, consensus, supply and market observations alongside dates and source status; follow official links where supplied.",
            "Use Ask Wiki to discuss the selected project and its sources.",
        ),
        (
            "The 20 projects are an editorial selection, not a current ranking or recommendation. Public profiles do not use exchange account credentials.",
        ),
    ),
    "sources": Guide(
        "Check profile sources and dates",
        "/research?tab=crypto",
        (
            "CoinPaprika supplies available project/market data; Wikipedia supplies bounded introduction/history excerpts with attribution and revision details.",
            "Inspect each component's retrieval date and Stale/Unavailable status; missing data stay unavailable.",
        ),
        (
            "Profiles are neither a complete history nor audited fundamentals. Public USD prices can differ from the selected exchange.",
        ),
    ),
}

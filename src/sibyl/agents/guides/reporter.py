"""News reading, provenance and sentiment guidance for Reporter."""

from typing import Literal

from sibyl.agents.guides import Guide

Topic = Literal["overview", "sources", "articles", "filters", "sentiment", "fear_greed", "models"]
GUIDES = {
    "overview": Guide(
        "Read the news workspace",
        "/news",
        (
            "News shows publisher-attributed headlines, excerpts, dates, sentiment summaries and the separate Fear & Greed index.",
            "Use the page filters, Read full article for original reporting, and Ask Reporter for an explanation of the selected stories.",
        ),
    ),
    "sources": Guide(
        "Choose and inspect news sources",
        "/settings?tab=news",
        (
            "Open Settings → News and choose Live sources or the exclusive Demo preview; select publisher cards and configure optional API credentials there.",
            "Return to News and inspect Sources for each publisher's retained count, last attempt, successful check and freshness status.",
            "The source note below the articles names enabled collectors and links to publishers. Refresh checks due sources while preserving dated older observations on failure.",
        ),
        (
            "Demo stories are illustrative. An empty or unavailable live feed is not replaced with Demo reporting.",
        ),
    ),
    "articles": Guide(
        "Read an entire article",
        "/news",
        (
            "Choose Read full article on a story to open the original reporting at its publisher.",
            "Publisher excerpt and extractive summary display only the supplied excerpt. Demo opens a labeled sample reading dialog.",
            "Give Reporter the selected story or its ID to discuss the retained text and source links.",
        ),
        (
            "Reporter cannot claim to have read full publisher text that the tool did not supply. Paywalls and publisher availability remain external.",
        ),
    ),
    "filters": Guide(
        "Filter the news and sentiment sample",
        "/news",
        (
            "Filter by publisher, asset mention, text polarity, query and date range.",
            "Totals and mean sentiment describe all matching retained stories, not just the visible article page.",
            "Ask Reporter uses the selected filters. Source settings are changed through the Settings link, rather than a second news-source selector.",
        ),
    ),
    "sentiment": Guide(
        "Understand article sentiment",
        "/news",
        (
            "Read positive, neutral or negative as English text polarity measured by VADER on supplied titles/excerpts.",
            "Inspect the underlying stories and dates before drawing conclusions from an average or an asset group.",
        ),
        (
            "Asset groups identify mentions, not sentiment directed at an asset. Polarity is neither investor positioning nor a price forecast. Connecting an LLM does not recalibrate these scores.",
        ),
    ),
    "fear_greed": Guide(
        "Understand Fear & Greed",
        "/news",
        (
            "Inspect the Bitcoin Fear & Greed index value, classification, publication date and yesterday/week/29-day comparisons.",
            "Follow the adjacent Alternative.me attribution for the original provider and check any Stale/Demo label.",
        ),
        (
            "This market index differs from the wording polarity of news articles. It is not a trading instruction or a probability of future returns.",
        ),
    ),
    "models": Guide(
        "Enable Reporter explanations",
        "/settings?tab=models",
        (
            "Choose and configure an API or Local model in Settings → AI models; Reporter can inherit the workspace default or use an Agent models override.",
            "Return to News and Ask Reporter. Without a model, the dialog provides a Tool snapshot rather than an AI interpretation.",
        ),
        (
            "News collection, text sentiment, extractive summaries and Fear & Greed work without an LLM. Mock model answers remain simulated.",
        ),
    ),
}

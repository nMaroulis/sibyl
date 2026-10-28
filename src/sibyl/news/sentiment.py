"""Deterministic excerpt analysis; no model downloads or inferred trading signals."""

import re
from collections import Counter
from functools import lru_cache

from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

ASSETS = {
    "BTC": ("bitcoin",),
    "ETH": ("ethereum", "ether"),
    "SOL": ("solana",),
    "BNB": ("binance coin",),
    "XRP": ("ripple",),
    "ADA": ("cardano",),
    "DOGE": ("dogecoin",),
    "AVAX": ("avalanche",),
    "DOT": ("polkadot",),
    "LINK": ("chainlink",),
    "LTC": ("litecoin",),
    "BCH": ("bitcoin cash",),
    "TRX": ("tron",),
    "XLM": ("stellar",),
    "XMR": ("monero",),
    "USDT": ("tether",),
    "USDC": ("usd coin",),
    "SHIB": ("shiba inu",),
    "UNI": ("uniswap",),
    "ETC": ("ethereum classic",),
}
NOTE = (
    "VADER scores headline and publisher-excerpt wording, not market sentiment or price direction. "
    "Asset groups include articles mentioning that asset; scores are not targeted to the asset."
)


@lru_cache(maxsize=1)
def analyzer() -> SentimentIntensityAnalyzer:
    """Load the bundled English VADER lexicon once."""
    return SentimentIntensityAnalyzer()


def analyze_article(item: dict) -> dict:
    """Score original text and attach conservative rule-based asset mentions."""
    text = item["title"] + ". " + item["summary"]
    score = analyzer().polarity_scores(text)
    label = (
        "positive" if score["compound"] >= 0.05 else "negative" if score["compound"] <= -0.05 else "neutral"
    )
    assets = [
        symbol
        for symbol, names in ASSETS.items()
        if re.search(r"(?<!\w)\$?" + symbol + r"(?!\w)", text)
        or any(re.search(r"\b" + re.escape(name) + r"\b", text, re.I) for name in names)
    ]
    return {**item, "assets": assets, "sentiment": {**score, "label": label}}


def extract_summary(text: str) -> str:
    """Select at most two excerpt sentences by repeated-word frequency, in source order."""
    sentences = re.split(r"(?<=[.!?])\s+", text)
    terms = Counter(re.findall(r"[a-z]{4,}", text.lower()))
    scores = [
        (sum(terms[w] for w in re.findall(r"[a-z]{4,}", sentence.lower())) / max(1, len(sentence.split())), i)
        for i, sentence in enumerate(sentences)
    ]
    return " ".join(sentences[i] for i in sorted(i for _, i in sorted(scores, reverse=True)[:2]))


def distribution(items: list[dict]) -> dict:
    """Return equal-weight article statistics; missing samples produce a null mean."""
    return {
        "count": len(items),
        "compound": round(sum(i["sentiment"]["compound"] for i in items) / len(items), 4) if items else None,
        **{
            label: sum(i["sentiment"]["label"] == label for i in items)
            for label in ("positive", "neutral", "negative")
        },
    }


def sentiment_report(items: list[dict]) -> dict:
    """Aggregate the filtered archive before pagination, with UTC-day and asset samples."""
    days = sorted({i["published_at"][:10] for i in items if i.get("published_at")})
    groups = [
        {"asset": asset, **distribution([i for i in items if asset in i.get("assets", [])])}
        for asset in ASSETS
        if any(asset in i.get("assets", []) for i in items)
    ]
    return {
        "model": "VADER",
        "version": "3.3.2",
        "input": "headline + publisher excerpt",
        **distribution(items),
        "note": NOTE,
        "undated": sum(not i.get("published_at") for i in items),
        "timeline": [
            {"date": day, **distribution([i for i in items if (i.get("published_at") or "")[:10] == day])}
            for day in days
        ],
        "assets": sorted(groups, key=lambda g: -g["count"]),
    }

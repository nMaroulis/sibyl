"""Offline sample briefings that never enter the public publisher archive."""

import hashlib
from datetime import datetime, timedelta

from sibyl.news.sentiment import analyze_article

STORIES = [
    (
        "The bigger picture: reading a changing market",
        "Market structure",
        "A sample briefing on how Bitcoin volume, liquidity, and volatility can help frame market moves.",
    ),
    (
        "Beyond the price: a closer look at Ethereum",
        "Ecosystem",
        "A sample research note exploring Ethereum network activity and the difference between usage and token value.",
    ),
    (
        "A thoughtful approach to portfolio concentration",
        "Portfolio",
        "A sample risk note on position sizing and how correlations can change during periods of stress.",
    ),
    (
        "What a backtest can, and cannot, tell you",
        "Strategies",
        "A sample guide to fees, realistic execution, and evaluating a strategy outside its training period.",
    ),
    (
        "Your API keys deserve a smaller permission set",
        "Security",
        "A sample operational note on read-only access, IP restrictions, and key rotation.",
    ),
    (
        "Bitcoin growth brings optimism, with questions ahead",
        "Markets",
        "An illustrative positive-text sample: Bitcoin adoption shows strong growth and encouraging progress. This is not current reporting.",
    ),
    (
        "Solana outage raises concerns in a sample scenario",
        "Ecosystem",
        "An illustrative negative-text sample: a Solana outage creates disruption, losses, and uncertainty. This event is fictional.",
    ),
    (
        "A closer look at stablecoin reserves",
        "Stablecoins",
        "A sample explainer about USDC and USDT reserve disclosures, redemption, and issuer risk.",
    ),
]


def demo_items(now: datetime) -> list[dict]:
    """Return stable article IDs with explicitly illustrative timestamps and wording."""
    hour = now.replace(minute=0, second=0, microsecond=0)
    return [
        analyze_article(
            {
                "id": hashlib.sha256(title.encode()).hexdigest()[:24],
                "source_id": "demo",
                "title": title,
                "category": category,
                "summary": text,
                "body": text
                + "\n\n"
                + {
                    "Market structure": "A market move can look different when viewed alongside trading volume, order-book depth, and the time window. Compare those observations before drawing a conclusion from a single price change.",
                    "Ecosystem": "Network activity, transaction costs, and developer participation describe different aspects of an ecosystem. None of these observations establishes what its token should be worth.",
                    "Portfolio": "Start with position sizes and the assets that dominate the portfolio. Historical correlations can change, especially during market stress, so diversification should be reviewed over more than one sample window.",
                    "Strategies": "A historical simulation should include fees, slippage, and realistic fill timing. Review drawdowns and evaluate rules on data that was not used to choose their parameters.",
                    "Security": "A dedicated read-only API key is enough for account research. Restrict its permissions and available IP addresses, keep withdrawals disabled, and revoke unused keys at the exchange.",
                    "Markets": "This fictional briefing illustrates how the news reader separates publisher wording from price observations. A positive article score does not imply that a market price will rise.",
                    "Stablecoins": "An issuer's reserve disclosure, redemption process, and legal structure help explain a stablecoin's design. A target price is not a guarantee that every market trade will occur at that value.",
                }.get(category, "This is an illustrative research briefing for exploring the demo workspace.")
                + "\n\nThis briefing is a Sibyl demo sample, not current reporting.",
                "publisher": "Sibyl sample briefing",
                "published_at": (hour - timedelta(hours=i * 8)).isoformat(),
                "collected_at": hour.isoformat(),
                "first_seen_at": hour.isoformat(),
                "url": None,
            }
        )
        for i, (title, category, text) in enumerate(STORIES)
    ]

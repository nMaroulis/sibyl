"""The Bitcoin block explorer's actual controls and supported scope."""

from typing import Literal

from sibyl.agents.guides import Guide

Topic = Literal["overview", "blocks", "transactions"]
GUIDES = {
    "overview": Guide(
        "Explore Bitcoin blocks",
        "/research?tab=explorer",
        (
            "Open Research → Block explorer to view recent Bitcoin block heights, dates, transaction counts and sizes.",
            "Inspect source labels: live summaries come from mempool.space and Demo observations are labeled samples.",
        ),
    ),
    "blocks": Guide(
        "Inspect and export block statistics",
        "/research?tab=explorer",
        (
            "Choose 10, 25, 50 or 100 blocks and inspect the transaction-count chart, mean size/count and observed mean block interval.",
            "Export CSV for the supplied sample or follow a block reference to its public explorer.",
        ),
        ("A sample mean block interval is not a guarantee about the next confirmation time.",),
    ),
    "transactions": Guide(
        "Find transaction and address details",
        "/research?tab=explorer",
        (
            "Use the linked public explorer for an arbitrary Bitcoin transaction or address.",
            "Sibyl's built-in view currently provides recent block summaries, not address balances, transaction inspection or additional chains.",
        ),
    ),
}

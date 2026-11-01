"""The Bitcoin block explorer's actual controls and supported scope."""

from typing import Literal

from sibyl.agents.guides import Guide

Topic = Literal["overview", "blocks", "transactions"]
GUIDES = {
    "overview": Guide(
        "Explore Bitcoin blocks",
        "/research?tab=explorer",
        (
            "Open Research → Block explorer. Paste a Bitcoin mainnet transaction ID or address into the lookup, or inspect recent blocks below.",
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
            "Paste a complete transaction ID or checksummed mainnet address and choose Inspect. Lookups are sent to mempool.space; private keys and seed phrases are never needed.",
            "Inspect confirmations, fees in satoshis and sat/vB, and paged inputs/outputs. An address shows confirmed balance, pending change and confirmed activity; load older pages or separately inspect pending transactions.",
            "Use the small Demo links for synthetic examples. Ask Explorer includes the current reference; an address is not a complete wallet or proof of ownership.",
        ),
    ),
}

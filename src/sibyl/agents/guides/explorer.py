"""The Bitcoin block explorer's actual controls and supported scope."""

from typing import Literal

from sibyl.agents.guides import Guide

Topic = Literal["overview", "blocks", "transactions", "ethereum"]
GUIDES = {
    "ethereum": Guide(
        "Inspect Ethereum blocks and transactions",
        "/research?tab=explorer&chain=ethereum",
        (
            "Choose Ethereum in Research → Block explorer. Enter a block height or hash, or load the RPC-reported finalized head. Page by the exact displayed block hash.",
            "Enter an exact transaction hash or select Read receipt beside a block transaction. Gas cost excludes separate blob fees. A matching receipt is an observation from the public RPC.",
        ),
    ),
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
            "Export CSV for recent blocks or enter a height/hash in Historical block lookup. Page by block hash, open a transaction in the inspector or export one page as JSON.",
        ),
        ("A sample mean block interval is not a guarantee about the next confirmation time.",),
    ),
    "transactions": Guide(
        "Find transaction and address details",
        "/research?tab=explorer",
        (
            "Paste a complete transaction ID or checksummed mainnet address and choose Inspect. Lookups are sent to mempool.space; private keys and seed phrases are never needed.",
            "Inspect confirmations, fees in satoshis and sat/vB, and paged inputs/outputs. An address shows confirmed balance, pending change and confirmed activity; load older pages or separately inspect pending transactions.",
            "In a transaction, select Check output spends below Outputs. Inspect the current page’s spending state and follow a spending transaction; Refresh checks reads a new observation. Export spends retains that dated snapshot. Unspent does not guarantee spendability; pending spends can change.",
            "For a confirmed transaction, choose Verify inclusion to compare its Merkle branch against the displayed block header. Best-chain status comes from the indexer.",
            "Choose Watch on an output to receive local inbox notices when its spend or block inclusion changes. Manage pause, resume, and removal under Output watches.",
            "Use the small Demo links for synthetic examples. Ask Explorer includes the current reference; an address is not a complete wallet or proof of ownership.",
        ),
    ),
}

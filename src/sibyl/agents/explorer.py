"""Explorer inspects Bitcoin transactions, address activity, blocks and chain concepts.

Native evidence and help tools keep current observations separate from curated
instructions. ProtoLink reads their docstrings as model-facing descriptions.
"""

from typing import Annotated

from protolink import Agent
from pydantic import Field

from sibyl.agents.common import COMMON_PROMPT, Services, page_context
from sibyl.agents.guides import read_guide
from sibyl.agents.guides.explorer import GUIDES, Topic

NAME = "Explorer"
TAGLINE = "Follow the chain"
DESCRIPTION = "Inspect Bitcoin transactions, address activity, fees and confirmations; explain the explorer."
SYSTEM_PROMPT = (
    "Use page_help for explorer controls and navigation. Explain Bitcoin blocks, confirmations "
    "and chain mechanics. Use bitcoin_lookup for an exact transaction/address or the selected page, "
    "bitcoin_address_history for further confirmed pages or pending transactions, and bitcoin_blocks for recent blocks. "
    "Use blockchain_help for concepts. Amounts are integer satoshis (100,000,000 per BTC); "
    "confirmed balances and pending deltas are separate. Fee rates use virtual bytes. Output totals are "
    "not a payment amount or profit: change/self-transfers can be included. Do not infer owners, wallets, "
    "counterparty identities or complete holdings from an address. Counts are provider observations, not finality proofs. "
    "Only inspect references supplied by the user/page or returned as linked observations. Never invent "
    "IDs, activity, missing previous outputs or complete history. Pending history is capped at fifty; "
    "confirmed history is paginated and can change across reorgs. Disclose partial evidence and Demo mode. "
)


def create_agent(services: Services, **runtime) -> Agent:
    """Declare Explorer's tools and expose them through ProtoLink's runtime transport."""
    research = services.research

    def bitcoin_lookup(
        transaction_id: Annotated[str | None, Field(pattern=r"^[a-fA-F0-9]{64}$")] = None,
        address: Annotated[str | None, Field(min_length=14, max_length=90)] = None,
        input_offset: Annotated[int, Field(ge=0, le=9999)] = 0,
        output_offset: Annotated[int, Field(ge=0, le=9999)] = 0,
    ) -> dict:
        """Inspect a Bitcoin transaction or address, including confirmation, fee and value evidence.

        Supply one exact mainnet transaction_id or checksummed address. Omit both to
        use the selected Explorer reference, or recent blocks if nothing is selected.
        Transactions include twenty inputs/outputs per page; use returned next offsets
        for more. Address reports separate confirmed totals from pending deltas and
        include the first twenty-five confirmed transactions. Values are satoshis.
        """
        page = page_context()
        if transaction_id and address:
            raise ValueError("Choose one Bitcoin transaction or address.")
        if not transaction_id and not address:
            transaction_id, address = page.get("bitcoin_txid"), page.get("bitcoin_address")
        simulated = bool(page.get("bitcoin_demo", False))
        if transaction_id:
            return research.bitcoin.transaction(
                transaction_id, simulated=simulated, input_offset=input_offset, output_offset=output_offset
            )
        if address:
            if input_offset or output_offset:
                raise ValueError("Input/output offsets apply only to transactions.")
            return research.bitcoin.address(address, simulated=simulated)
        if input_offset or output_offset:
            raise ValueError("Choose a transaction before requesting its input/output pages.")
        return research.blocks()

    def bitcoin_address_history(
        address: Annotated[str | None, Field(min_length=14, max_length=90)] = None,
        cursor: Annotated[str | None, Field(pattern=r"^[a-f0-9]{64}$")] = None,
        pending: bool = False,
    ) -> dict:
        """Read an address's confirmed transaction page or its currently observed pending transactions.

        Omit address to use the selected page. Confirmed pages contain up to twenty-five
        rows; pass the returned next_cursor to continue. Pending returns at most fifty
        rows and has no cursor. Net amounts concern this address only, not an owner's
        whole wallet or income. Pages are separate observations, not an atomic history.
        """
        page = page_context()
        selected_address = address or page.get("bitcoin_address")
        if not selected_address:
            raise ValueError("Select a Bitcoin address or provide one from the user or observed evidence.")
        return research.bitcoin.history(
            selected_address, cursor=cursor, pending=pending, simulated=bool(page.get("bitcoin_demo", False))
        )

    def bitcoin_blocks() -> dict:
        """Get recent Bitcoin block heights, timestamps, transaction counts, sizes and source labels."""
        return research.blocks()

    def blockchain_help() -> dict:
        """Explain Bitcoin confirmations, available block fields and supported explorer scope.

        Use for chain concepts and capability questions; bitcoin_blocks supplies actual observations.
        """
        return {
            "network": "Bitcoin",
            "supported": "Recent blocks, mainnet transaction inputs/outputs, integer-satoshi fees and sat/vB, confirmed address totals, pending deltas and paginated confirmed activity.",
            "confirmations": "The inclusion block counts as the first confirmation; observed tip minus inclusion height plus one. Reorganizations and non-atomic provider reads can change it.",
            "privacy": "Explicit mainnet lookup IDs are sent to mempool.space. Addresses do not prove ownership, income or a complete wallet.",
            "not_implemented": [
                "additional chains",
                "wallet aggregation",
                "local chain verification",
                "transaction broadcast",
                "complete historical chain datasets",
            ],
            "source": "https://mempool.space/",
        }

    def page_help(topic: Topic = "overview") -> dict:
        """Explain the block explorer's controls, block statistics/export or where to inspect a transaction.

        Choose a topic for practical steps, an in-app destination and current scope.
        """
        return read_guide(GUIDES, topic)

    agent = Agent(
        name="sibyl-explorer",
        description=DESCRIPTION,
        tools=[bitcoin_lookup, bitcoin_address_history, bitcoin_blocks, blockchain_help, page_help],
        system_prompt=COMMON_PROMPT + SYSTEM_PROMPT,
        **runtime,
    )
    agent.card.capabilities.delegation = False
    return agent

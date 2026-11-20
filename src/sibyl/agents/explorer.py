"""Explorer inspects Bitcoin transactions, address activity, blocks and chain concepts.

Native evidence and help tools keep current observations separate from curated
instructions. ProtoLink reads their docstrings as model-facing descriptions.
"""

from typing import Annotated

from protolink import Agent, Tool
from pydantic import Field

from sibyl.agents.guides import read_guide
from sibyl.agents.guides.explorer import GUIDES, Topic
from sibyl.agents.utils.common import COMMON_PROMPT, Services, page_context
from sibyl.blockchain.bitcoin import BLOCK_PAGE, MAX_BLOCK_TRANSACTIONS, MAX_HEIGHT

NAME = "Explorer"
TAGLINE = "Follow the chain"
DESCRIPTION = "Inspect Bitcoin transactions, output spends, address activity, fees and confirmations; explain the explorer."
SYSTEM_PROMPT = (
    "Use page_help for explorer controls and navigation. Explain Bitcoin blocks, confirmations "
    "and chain mechanics. Use bitcoin_lookup for an exact transaction/address or the selected page, "
    "bitcoin_address_history for further confirmed pages or pending transactions, bitcoin_output_spends for output spending evidence, and bitcoin_blocks for block lookup or recent blocks. "
    "Output-spend observations distinguish unspent, pending, confirmed and incomplete details. Unspent does not mean spendable or prove ownership. Never infer unspent from a failed lookup. "
    "Use blockchain_help for concepts. Amounts are integer satoshis (100,000,000 per BTC); "
    "confirmed balances and pending deltas are separate. Fee rates use virtual bytes. Output totals are "
    "not a payment amount or profit: change/self-transfers can be included. Do not infer owners, wallets, "
    "counterparty identities or complete holdings from an address. Counts are provider observations, not finality proofs. "
    "Only inspect references supplied by the user/page or returned as linked observations. Never invent "
    "IDs, activity, missing previous outputs or complete history. Pending history is capped at fifty; "
    "confirmed history is paginated and can change across reorgs. Disclose partial evidence and Demo mode. "
)


def create_agent(services: Services, **runtime) -> Agent:
    """Register this specialist's evidence and help tools on a native Agent.

    Args:
        services: Workspace domain services; credentials stay in their owners.
        **runtime: AgentGroup configuration, including the lazy model factory,
            native state, worker defaults and context policy.

    Returns:
        An unstarted Agent. Static guides run inline; domain reads inherit the
        runtime's execution policy (bounded threads in Sibyl). AgentGroup owns
        startup and shutdown.
    """
    research = services.research

    def bitcoin_lookup(
        transaction_id: Annotated[str | None, Field(pattern=r"^[a-fA-F0-9]{64}$")] = None,
        address: Annotated[str | None, Field(min_length=14, max_length=90)] = None,
        input_offset: Annotated[int, Field(ge=0, le=9999)] = 0,
        output_offset: Annotated[int, Field(ge=0, le=9999)] = 0,
    ) -> dict:
        """Inspect a Bitcoin transaction/address or follow the Explorer selection. Returns attributable
        on-chain observations, confirmations and availability. An address is not a verified
        identity; mempool data can change. Never requests keys, signs or broadcasts transactions.
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
        """Read a bounded page of a Bitcoin address's transaction history and source coverage. Omit
        address/cursor to follow the page. Provider limits and unconfirmed activity remain explicit;
        this is not complete wallet accounting or proof of ownership. Never moves funds.
        """
        page = page_context()
        selected_address = address or page.get("bitcoin_address")
        if not selected_address:
            raise ValueError("Select a Bitcoin address or provide one from the user or observed evidence.")
        return research.bitcoin.history(
            selected_address, cursor=cursor, pending=pending, simulated=bool(page.get("bitcoin_demo", False))
        )

    def bitcoin_output_spends(
        transaction_id: Annotated[str | None, Field(pattern=r"^[a-fA-F0-9]{64}$")] = None,
        output_offset: Annotated[int | None, Field(ge=0, le=9999)] = None,
    ) -> dict:
        """Read which outputs of a selected Bitcoin transaction are observed spent, with spender
        identities and source freshness. Omit transaction_id for the page selection. Unspent/mempool
        observations can change; spendability remains unknown. They do not prove ownership. Never broadcasts a transaction.
        """
        page = page_context()
        identity = transaction_id or page.get("bitcoin_txid")
        if not identity:
            raise ValueError("Choose a transaction from the user or returned Explorer evidence first.")
        return research.bitcoin.output_spends(
            identity,
            output_offset=output_offset
            if output_offset is not None
            else (page.get("bitcoin_output_offset") or 0)
            if identity == page.get("bitcoin_txid")
            else 0,
            simulated=bool(page.get("bitcoin_demo", False)),
        )

    def bitcoin_blocks(
        height: Annotated[int | None, Field(ge=0, le=MAX_HEIGHT, strict=True)] = None,
        block_hash: Annotated[str | None, Field(pattern=r"^[a-fA-F0-9]{64}$")] = None,
        offset: Annotated[int | None, Field(ge=0, lt=MAX_BLOCK_TRANSACTIONS, multiple_of=BLOCK_PAGE)] = None,
    ) -> dict:
        """Inspect a block's best-chain status and paged transactions by height or hash. With no selection, list recent blocks."""
        page = page_context()
        if height is None and block_hash is None:
            block_hash = page.get("bitcoin_block_hash")
        if height is None and block_hash is None:
            return research.blocks()
        offset = (
            offset
            if offset is not None
            else (page.get("bitcoin_block_offset", 0) if block_hash == page.get("bitcoin_block_hash") else 0)
        )
        return research.bitcoin.block(
            height=height, block_hash=block_hash, offset=offset, simulated=bool(page.get("bitcoin_demo"))
        )

    def blockchain_help() -> dict:
        """Explain Bitcoin confirmations, available block fields and supported explorer scope.

        Use for chain concepts and capability questions; bitcoin_blocks supplies actual observations.
        """
        return {
            "network": "Bitcoin",
            "supported": "Recent and historical blocks with paged transactions, mainnet transaction inputs/outputs, integer-satoshi fees and sat/vB, confirmed address totals, pending deltas, paginated confirmed activity and output-spend observations with spending transaction links.",
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
        tools=[
            bitcoin_lookup,
            bitcoin_address_history,
            bitcoin_output_spends,
            bitcoin_blocks,
            Tool.from_callable(blockchain_help, sync_execution="inline"),
            Tool.from_callable(page_help, sync_execution="inline"),
        ],
        system_prompt=COMMON_PROMPT + SYSTEM_PROMPT,
        **runtime,
    )
    agent.card.capabilities.delegation = False
    return agent

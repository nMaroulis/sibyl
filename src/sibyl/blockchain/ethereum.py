"""Bounded, read-only Ethereum mainnet block and execution lookups."""

import json
import re
from datetime import UTC, datetime
from uuid import uuid4

import httpx

RPC = "https://ethereum-rpc.publicnode.com"
SOURCE = "PublicNode Ethereum mainnet"
HASH = re.compile(r"0x[0-9a-fA-F]{64}")
ADDRESS = re.compile(r"0x[0-9a-fA-F]{40}")
QUANTITY = re.compile(r"0x(?:0|[1-9a-fA-F][0-9a-fA-F]{0,63})")
MAX_BYTES = 4 * 1024 * 1024


def digest(value):
    """Validate the exact width of a public chain hash."""
    if not isinstance(value, str) or not HASH.fullmatch(value):
        raise ValueError("Use a 32-byte Ethereum hash starting with 0x.")
    return value.lower()


def quantity(value):
    """Keep JSON-RPC quantities exact before producing a browser-safe value."""
    if not isinstance(value, str) or not QUANTITY.fullmatch(value):
        raise ValueError("Ethereum RPC returned an invalid hexadecimal quantity.")
    return int(value, 16)


def address(value):
    """Accept a reported account identity or a null contract-creation target."""
    if value is None:
        return None
    if not isinstance(value, str) or not ADDRESS.fullmatch(value):
        raise ValueError("Ethereum RPC returned an invalid address.")
    return value.lower()


class EthereumExplorer:
    """Return one block or transaction from the reviewed mainnet RPC, with explicit source scope."""

    def __init__(self, transport=None):
        self.transport = transport

    @staticmethod
    def _read(client, method, params):
        identity = uuid4().hex
        try:
            with client.stream(
                "POST", RPC, json={"jsonrpc": "2.0", "id": identity, "method": method, "params": params}
            ) as response:
                response.raise_for_status()
                body = bytearray()
                for chunk in response.iter_bytes(chunk_size=65536):
                    body.extend(chunk)
                    if len(body) > MAX_BYTES:
                        raise ValueError("Ethereum RPC response exceeds 4 MiB.")
            result = json.loads(body)
        except (httpx.HTTPError, UnicodeError, json.JSONDecodeError):
            raise ValueError("Ethereum RPC could not complete this lookup.") from None
        if (
            not isinstance(result, dict)
            or result.get("jsonrpc") != "2.0"
            or result.get("id") != identity
            or "error" in result
            or "result" not in result
        ):
            raise ValueError("Ethereum RPC returned an invalid or rejected lookup.")
        return result["result"]

    def _connect(self):
        return httpx.Client(
            timeout=httpx.Timeout(8, connect=3),
            follow_redirects=False,
            trust_env=False,
            transport=self.transport,
        )

    def _mainnet(self, client):
        if quantity(self._read(client, "eth_chainId", [])) != 1:
            raise ValueError("Ethereum RPC did not identify mainnet.")

    def block(self, reference="finalized", *, offset=0, limit=25):
        """Read a finalized head or exact block, with an ordered page of transaction hashes."""
        reference = reference.strip()
        if reference in {"finalized", "latest"}:
            selector = reference
        elif re.fullmatch(r"[0-9]{1,12}", reference):
            selector = hex(int(reference))
        else:
            selector = digest(reference)
        by_hash = HASH.fullmatch(selector) is not None
        with self._connect() as client:
            self._mainnet(client)
            row = self._read(
                client, "eth_getBlockByHash" if by_hash else "eth_getBlockByNumber", [selector, False]
            )
        if row is None:
            raise LookupError("Ethereum block not found at this RPC.")
        if not isinstance(row, dict) or not isinstance(row.get("transactions"), list):
            raise ValueError("Ethereum RPC did not return block evidence.")
        block_hash = digest(row.get("hash"))
        height = quantity(row.get("number"))
        if (
            height >= 10**12
            or (by_hash and block_hash != selector)
            or (selector.startswith("0x") and not by_hash and height != int(selector, 16))
        ):
            raise ValueError("Ethereum RPC returned a different block.")
        hashes = [digest(value) for value in row["transactions"]]
        if len(set(hashes)) != len(hashes):
            raise ValueError("Ethereum RPC returned duplicate block transactions.")
        stamp = quantity(row.get("timestamp"))
        if stamp > int(datetime.now(UTC).timestamp()) + 300:
            raise ValueError("Ethereum RPC returned an invalid block time.")
        return {
            "chain": "ethereum",
            "source": SOURCE,
            "block_hash": block_hash,
            "height": height,
            "timestamp": datetime.fromtimestamp(stamp, UTC).isoformat(),
            "gas_used": str(quantity(row.get("gasUsed"))),
            "base_fee_wei": str(quantity(row["baseFeePerGas"]))
            if row.get("baseFeePerGas") is not None
            else None,
            "reported_finalized_head": selector == "finalized",
            "transaction_count": len(hashes),
            "transactions": hashes[offset : offset + limit],
        }

    def transaction(self, transaction_hash):
        """Return exact value, receipt execution status and gas cost without transaction calldata."""
        identity = digest(transaction_hash.strip())
        with self._connect() as client:
            self._mainnet(client)
            row = self._read(client, "eth_getTransactionByHash", [identity])
            if row is None:
                raise LookupError("Ethereum transaction not found at this RPC.")
            if not isinstance(row, dict) or digest(row.get("hash")) != identity:
                raise ValueError("Ethereum RPC returned a different transaction.")
            receipt = self._read(client, "eth_getTransactionReceipt", [identity])
        if receipt is not None and not isinstance(receipt, dict):
            raise ValueError("Ethereum RPC returned an invalid receipt.")
        block_hash = digest(row["blockHash"]) if row.get("blockHash") is not None else None
        block_number = quantity(row["blockNumber"]) if row.get("blockNumber") is not None else None
        if (block_hash is None) != (block_number is None) or (block_number or 0) >= 10**12:
            raise ValueError("Ethereum RPC returned incomplete block identity.")
        sender, recipient = address(row.get("from")), address(row.get("to"))
        if sender is None:
            raise ValueError("Ethereum RPC did not report the transaction sender.")
        fee, status = None, "pending" if block_hash is None else "receipt_unavailable"
        if receipt is not None:
            if (
                digest(receipt.get("transactionHash")) != identity
                or digest(receipt.get("blockHash")) != block_hash
                or quantity(receipt.get("blockNumber")) != block_number
            ):
                raise ValueError(
                    "Ethereum receipt disagrees with the transaction or its block. Reload the observation."
                )
            execution = quantity(receipt["status"]) if receipt.get("status") is not None else None
            if execution not in (0, 1, None):
                raise ValueError("Ethereum receipt returned an unsupported execution status.")
            status = {0: "reverted", 1: "succeeded", None: "legacy_receipt"}[execution]
            if receipt.get("effectiveGasPrice") is not None:
                fee = str(quantity(receipt["gasUsed"]) * quantity(receipt["effectiveGasPrice"]))
        return {
            "chain": "ethereum",
            "source": SOURCE,
            "hash": identity,
            "from": sender,
            "to": recipient,
            "value_wei": str(quantity(row.get("value"))),
            "execution_gas_cost_wei": fee,
            "block_hash": block_hash,
            "block_number": block_number,
            "execution_status": status,
        }

"""Verify a TXID's Merkle branch against an exact serialized Bitcoin block header."""

import hashlib
import re

from sibyl.blockchain.identifiers import txid
from sibyl.blockchain.normalize import integer


def hash256(value: bytes) -> bytes:
    """Return Bitcoin's double SHA-256 digest in internal byte order."""
    return hashlib.sha256(hashlib.sha256(value).digest()).digest()


def inclusion(transaction_id, block_hash, tx_count, header_hex, proof):
    """Validate the branch shape using the reported transaction count and recalculate its root."""
    if not isinstance(header_hex, str) or not re.fullmatch(r"[0-9a-fA-F]{160}", header_hex):
        raise ValueError("A Bitcoin header must contain exactly 80 bytes.")
    header = bytes.fromhex(header_hex)
    position = integer(proof["pos"], tx_count - 1)
    branch = proof["merkle"]
    if not isinstance(branch, list) or len(branch) != (tx_count - 1).bit_length():
        raise ValueError("The Merkle branch does not fit the reported transaction count.")
    siblings = [txid(value) for value in branch]
    current = bytes.fromhex(transaction_id)[::-1]
    index, width = position, tx_count
    for sibling_hash in siblings:
        sibling = bytes.fromhex(sibling_hash)[::-1]
        duplicated = (index ^ 1) >= width
        if duplicated != (current == sibling):
            raise ValueError("The Merkle branch has an inconsistent duplicate node.")
        current = hash256(sibling + current if index % 2 else current + sibling)
        index //= 2
        width = (width + 1) // 2

    calculated_hash = hash256(header)[::-1].hex()
    root = header[36:68]
    return {
        "position": position,
        "header": header.hex(),
        "siblings": siblings,
        "header_hash": calculated_hash,
        "header_merkle_root": root[::-1].hex(),
        "calculated_merkle_root": current[::-1].hex(),
        "header_matches": calculated_hash == block_hash,
        "root_matches": current == root,
        "verified": calculated_hash == block_hash and current == root,
    }

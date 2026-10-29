"""Validate Bitcoin mainnet identifiers before sending anything to a public indexer.

Base58Check uses the versioned payload checksum. Witness addresses follow the
Bech32/Bech32m checksum and padding rules in BIP 173/350. No key material is used.
"""

import hashlib
import re

BASE58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
BECH32 = "qpzry9x8gf2tvdw0s3jn54khce6mua7l"


def txid(value: str) -> str:
    """Canonicalize a complete transaction hash; reject URLs, paths and abbreviated IDs."""
    if not isinstance(value, str):
        raise ValueError("A Bitcoin transaction ID must be text.")
    value = value.strip().lower()
    if not re.fullmatch(r"[a-f0-9]{64}", value):
        raise ValueError("Enter a complete 64-character hexadecimal Bitcoin transaction ID.")
    return value


def _witness(value):
    if value != value.lower() and value != value.upper():
        return False
    value = value.lower()
    payload = value[3:]
    if not value.startswith("bc1") or len(payload) < 7 or any(c not in BECH32 for c in payload):
        return False
    digits = [BECH32.index(c) for c in payload]
    checksum = 1
    expanded = [ord(c) >> 5 for c in "bc"] + [0] + [ord(c) & 31 for c in "bc"] + digits
    generators = (0x3B6A57B2, 0x26508E6D, 0x1EA119FA, 0x3D4233DD, 0x2A1462B3)
    for digit in expanded:
        high = checksum >> 25
        checksum = ((checksum & 0x1FFFFFF) << 5) ^ digit
        for bit, generator in enumerate(generators):
            if high & (1 << bit):
                checksum ^= generator
    version = digits[0]
    if version > 16 or checksum != (1 if version == 0 else 0x2BC830A3):
        return False
    # Convert the five-bit program without accepting excess or nonzero padding.
    accumulator = bits = length = 0
    for digit in digits[1:-6]:
        accumulator = (accumulator << 5 | digit) & 0xFFF
        bits += 5
        if bits >= 8:
            bits -= 8
            length += 1
    if bits >= 5 or (accumulator << (8 - bits)) & 255:
        return False
    return 2 <= length <= 40 and (version != 0 or length in {20, 32})


def address(value: str) -> str:
    """Accept checksummed mainnet P2PKH/P2SH and witness addresses; reject other networks."""
    if not isinstance(value, str):
        raise ValueError("A Bitcoin address must be text.")
    value = value.strip()
    valid = False
    if 14 <= len(value) <= 90 and value.lower().startswith("bc1"):
        valid = _witness(value)
        value = value.lower()
    elif 26 <= len(value) <= 35 and all(c in BASE58 for c in value):
        number = 0
        for character in value:
            number = number * 58 + BASE58.index(character)
        raw = b"\0" * (len(value) - len(value.lstrip("1"))) + number.to_bytes(
            (number.bit_length() + 7) // 8, "big"
        )
        if len(raw) == 25 and raw[0] in {0, 5}:
            valid = hashlib.sha256(hashlib.sha256(raw[:-4]).digest()).digest()[:4] == raw[-4:]
    if not valid:
        raise ValueError("Enter a valid checksummed Bitcoin mainnet address (1…, 3… or bc1…).")
    return value

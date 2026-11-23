"""Explicit synthetic Bitcoin observations; these are never a live-source fallback."""

from sibyl.blockchain.merkle import hash256

ADDRESS = "12ZEw5Hcv1hTb6YUQJ69y1V7uhcoDz92PH"
PEER = "147Us9aEq2PvBC5wobBJw1yEpQEbPKzssA"
TXID = "d" * 64
PENDING_TXID = "e" * 64
TIP = 900_035
BLOCK_HEIGHT = 900_030
BLOCK_TIME = 1767243600
BLOCK_TXIDS = ("c" * 64, *(f"{1000 + i:064x}" for i in range(1, 29)))
BLOCK_PARENT = f"{BLOCK_HEIGHT - 1:064x}"


def block_tree():
    """Build the synthetic block's ordered Merkle levels with Bitcoin's odd-node duplication."""
    levels = [[bytes.fromhex(identity)[::-1] for identity in BLOCK_TXIDS]]
    while len(levels[-1]) > 1:
        level = levels[-1]
        paired = level + level[-1:] if len(level) % 2 else level
        levels.append([hash256(left + right) for left, right in zip(paired[::2], paired[1::2], strict=True)])
    return levels


BLOCK_HEADER = (
    bytes.fromhex("01000000")
    + bytes.fromhex(BLOCK_PARENT)[::-1]
    + block_tree()[-1][0]
    + BLOCK_TIME.to_bytes(4, "little")
    + bytes.fromhex("ffff001d00000000")
)
BLOCK_HASH = hash256(BLOCK_HEADER)[::-1].hex()


def _output(value, target):
    return {"value": value, "scriptpubkey_type": "p2pkh", "scriptpubkey_address": target}


def _transaction(identity, height, inputs, outputs, confirmed=True):
    return {
        "txid": identity,
        "version": 2,
        "locktime": 0,
        "size": 225,
        "weight": 900,
        "fee": 1000,
        "status": {
            "confirmed": confirmed,
            **(
                {
                    "block_height": height,
                    "block_hash": f"{height:064x}",
                    "block_time": 1767225600 + (height - 900_000) * 600,
                }
                if confirmed
                else {}
            ),
        },
        "vin": inputs,
        "vout": outputs,
    }


def _input(identity, target, value):
    return {"txid": identity, "vout": 0, "is_coinbase": False, "prevout": _output(value, target)}


def transactions():
    """Return 29 confirmed examples and one pending spend, with consistent satoshi totals."""
    rows = [
        _transaction(f"{i:064x}", 900_000 + i, [_input("a" * 64, PEER, 101_000)], [_output(100_000, ADDRESS)])
        for i in range(1, 29)
    ]
    rows.append(
        _transaction(
            TXID, 900_029, [_input(f"{i:064x}", ADDRESS, 100_000) for i in (1, 2)], [_output(199_000, PEER)]
        )
    )
    pending = _transaction(
        PENDING_TXID, 0, [_input(f"{3:064x}", ADDRESS, 100_000)], [_output(99_000, PEER)], False
    )
    return list(reversed(rows)), [pending]


def block_transactions():
    """Return a separate two-page Demo block with transaction details available for each row."""
    coinbase = _transaction(
        BLOCK_TXIDS[0], BLOCK_HEIGHT, [{"is_coinbase": True}], [_output(312_500_000, ADDRESS)]
    )
    coinbase["fee"] = 0
    rows = [
        coinbase,
        *[
            _transaction(
                BLOCK_TXIDS[i],
                BLOCK_HEIGHT,
                [_input(f"{2000 + i:064x}", PEER, 101_000)],
                [_output(100_000, ADDRESS)],
            )
            for i in range(1, 29)
        ],
    ]
    for row in rows:
        row["status"].update(block_hash=BLOCK_HASH, block_time=BLOCK_TIME)
    return rows


def read(path):
    """Serve only named Demo resources; unknown IDs never receive fabricated observations."""
    confirmed, pending = transactions()
    block_path = f"/block/{BLOCK_HASH}"
    if path == f"/block-height/{BLOCK_HEIGHT}":
        return BLOCK_HASH
    if path == block_path:
        return {
            "id": BLOCK_HASH,
            "height": BLOCK_HEIGHT,
            "timestamp": BLOCK_TIME,
            "tx_count": 29,
            "size": 6605,
            "weight": 26420,
            "previousblockhash": BLOCK_PARENT,
        }
    if path == block_path + "/header":
        return BLOCK_HEADER.hex()
    if path == block_path + "/status":
        return {"in_best_chain": True, "height": BLOCK_HEIGHT}
    if path in {block_path + "/txs", block_path + "/txs/25"}:
        rows = block_transactions()
        return rows[25:] if path.endswith("/25") else rows[:25]
    if path == "/blocks/tip/height":
        return str(TIP)
    if path.startswith("/tx/"):
        identity = path.removeprefix("/tx/")
        if identity.endswith("/merkle-proof"):
            transaction_id = identity.removesuffix("/merkle-proof")
            if transaction_id not in BLOCK_TXIDS:
                raise LookupError("No inclusion proof is available for this Demo transaction.")
            position = BLOCK_TXIDS.index(transaction_id)
            index, siblings = position, []
            for level in block_tree()[:-1]:
                siblings.append(level[min(index ^ 1, len(level) - 1)][::-1].hex())
                index //= 2
            return {"block_height": BLOCK_HEIGHT, "pos": position, "merkle": siblings}
        if identity.endswith("/outspends"):
            parent_id = identity.removesuffix("/outspends")
            parent = next(
                (row for row in confirmed + pending + block_transactions() if row["txid"] == parent_id), None
            )
            if parent is None:
                raise LookupError("Unknown Demo transaction.")
            observations = []
            for index in range(len(parent["vout"])):
                matches = [
                    (row, vin)
                    for row in confirmed + pending
                    for vin, item in enumerate(row["vin"])
                    if item.get("txid") == parent_id and item.get("vout") == index
                ]
                if matches:
                    row, vin = matches[0]
                    observations.append(
                        {"spent": True, "txid": row["txid"], "vin": vin, "status": row["status"]}
                    )
                else:
                    observations.append({"spent": False})
            return observations
        match = next((row for row in confirmed + pending if row["txid"] == identity), None)
        if match:
            return match
        match = next((row for row in block_transactions() if row["txid"] == identity), None)
        if match:
            return match
    prefix = f"/address/{ADDRESS}"
    if path == prefix:
        return {
            "address": ADDRESS,
            "chain_stats": {
                "tx_count": 29,
                "funded_txo_count": 28,
                "funded_txo_sum": 2_800_000,
                "spent_txo_count": 2,
                "spent_txo_sum": 200_000,
            },
            "mempool_stats": {
                "tx_count": 1,
                "funded_txo_count": 0,
                "funded_txo_sum": 0,
                "spent_txo_count": 1,
                "spent_txo_sum": 100_000,
            },
        }
    if path == prefix + "/txs/mempool":
        return pending
    if path.startswith(prefix + "/txs/chain"):
        cursor = path.removeprefix(prefix + "/txs/chain").lstrip("/")
        if not cursor:
            return confirmed[:25]
        index = next((i for i, row in enumerate(confirmed) if row["txid"] == cursor), None)
        if index is not None:
            return confirmed[index + 1 : index + 26]
    raise LookupError("Demo supports only its provided example transaction and address references.")

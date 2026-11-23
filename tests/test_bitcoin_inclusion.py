"""Local Merkle evidence covers known, mutated, incomplete and source-pinned proofs."""

import httpx
import pytest
from test_bitcoin_explorer import transport

from sibyl.blockchain import demo
from sibyl.blockchain.bitcoin import BitcoinExplorer, BitcoinUnavailable
from sibyl.blockchain.merkle import inclusion

GENESIS_TRANSACTION = "4a5e1e4baab89f3a32518a88c31bc87f618f76673e2cc77ab2127b7afdeda33b"
GENESIS_BLOCK = "000000000019d6689c085ae165831e934ff763ae46a2a6c172b3f1b60a8ce26f"
GENESIS_HEADER = (
    "01000000"
    + "00" * 32
    + "3ba3edfd7a7b12b27ac72c3e67768f617fc81bc3888a51323a9fb8aa4b1e5e4a"
    + "29ab5f49ffff001d1dac2b7c"
)


def test_genesis_header_and_empty_branch_match_public_bitcoin_vector():
    proof = {"pos": 0, "merkle": []}
    result = inclusion(GENESIS_TRANSACTION, GENESIS_BLOCK, 1, GENESIS_HEADER, proof)
    assert result["verified"] and result["header_merkle_root"] == GENESIS_TRANSACTION
    wrong_tx = inclusion("1" * 64, GENESIS_BLOCK, 1, GENESIS_HEADER, proof)
    assert wrong_tx["header_matches"] and not wrong_tx["root_matches"] and not wrong_tx["verified"]
    wrong_block = inclusion(GENESIS_TRANSACTION, "1" * 64, 1, GENESIS_HEADER, proof)
    assert wrong_block["root_matches"] and not wrong_block["header_matches"] and not wrong_block["verified"]


@pytest.mark.parametrize("position", [0, 1, 7, 24, 28])
def test_demo_supports_left_right_and_odd_duplicate_branches(position):
    explorer = BitcoinExplorer(lambda: pytest.fail("Demo reached a public source"))
    selected = demo.BLOCK_TXIDS[position]
    result = explorer.verify_inclusion(selected, demo.BLOCK_HASH, simulated=True)
    assert result["source"] == "demo" and result["position"] == position
    assert result["verified"] and len(result["siblings"]) == 5
    assert result["header_hash"] == demo.BLOCK_HASH


def test_padding_or_truncating_branch_cannot_produce_a_verification():
    selected = demo.BLOCK_TXIDS[-1]
    proof = demo.read(f"/tx/{selected}/merkle-proof")
    for altered in (
        {**proof, "merkle": []},
        {**proof, "pos": 29},
        {**proof, "pos": True},
        {**proof, "merkle": ["a" * 64, *proof["merkle"][1:]]},
    ):
        with pytest.raises(ValueError):
            inclusion(selected, demo.BLOCK_HASH, 29, demo.BLOCK_HEADER.hex(), altered)


def test_provider_move_returns_conflict_without_reading_a_replacement_header():
    selected = demo.BLOCK_TXIDS[0]

    def override(request):
        if request.url.path.endswith("/merkle-proof"):
            return httpx.Response(200, json={"block_height": demo.BLOCK_HEIGHT + 1})

    explorer, calls = transport(override)
    with pytest.raises(BitcoinUnavailable) as caught:
        explorer.verify_inclusion(selected, demo.BLOCK_HASH)
    assert caught.value.status == 409
    assert len(calls) == 2


def test_api_keeps_demo_separate_and_request_hashes_validated(client, monkeypatch):
    explorer = client.app.state.services.research.bitcoin
    monkeypatch.setattr(explorer, "_client_factory", lambda: pytest.fail("Demo made a public request"))
    body = {"transaction_id": demo.BLOCK_TXIDS[1], "block_hash": demo.BLOCK_HASH, "demo": True}
    result = client.post("/api/v1/bitcoin/inclusion-proof", json=body)
    assert result.status_code == 200 and result.headers["cache-control"] == "no-store"
    assert result.json()["verified"] and result.json()["position"] == 1
    assert (
        client.post("/api/v1/bitcoin/inclusion-proof", json={**body, "block_hash": "../"}).status_code == 422
    )
    missing = client.post("/api/v1/bitcoin/inclusion-proof", json={**body, "transaction_id": demo.TXID})
    assert missing.status_code == 404 and missing.headers["cache-control"] == "no-store"

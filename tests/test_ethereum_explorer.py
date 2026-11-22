"""Use exact public Ethereum RPC shapes with controlled HTTP and no live dependencies."""

import json

import httpx
import pytest

from sibyl.blockchain.ethereum import RPC, EthereumExplorer

BLOCK = "0x" + "9" * 64
TX = "0x" + "1" * 64
OTHER = "0x" + "2" * 64
SENDER = "0x" + "3" * 40


@pytest.fixture
def source():
    calls = []
    results = {
        "eth_chainId": "0x1",
        "eth_getBlockByNumber": {
            "hash": BLOCK,
            "number": "0x64",
            "timestamp": "0x67748580",
            "transactions": [TX, OTHER],
            "gasUsed": "0x5208",
        },
        "eth_getTransactionByHash": {
            "hash": TX,
            "blockHash": BLOCK,
            "blockNumber": "0x64",
            "from": SENDER,
            "to": None,
            "value": "0x100000000000000000001",
            "input": "NOT-RETAINED",
        },
        "eth_getTransactionReceipt": {
            "transactionHash": TX,
            "blockNumber": "0x64",
            "blockHash": BLOCK,
            "gasUsed": "0x5208",
            "effectiveGasPrice": "0x10000000",
            "status": "0x0",
            "logs": ["NOT-RETAINED"],
        },
    }
    results["eth_getBlockByHash"] = results["eth_getBlockByNumber"]

    def respond(request):
        body = json.loads(request.content)
        assert str(request.url).rstrip("/") == RPC and request.method == "POST"
        assert "Authorization" not in request.headers
        assert body["jsonrpc"] == "2.0"
        calls.append((body["method"], body["params"]))
        return httpx.Response(
            200, json={"id": body["id"], "jsonrpc": "2.0", "result": results[body["method"]]}
        )

    return EthereumExplorer(httpx.MockTransport(respond)), results, calls


def test_ethereum_routes_pin_block_hash_and_match_exact_receipt(client, monkeypatch, source):
    explorer, _, calls = source
    monkeypatch.setattr(client.app.state.services.research, "ethereum", explorer)
    root = "/api/v1/ethereum"
    first = client.get(f"{root}/blocks/finalized", params={"limit": 1}).json()
    assert first["block_hash"] == BLOCK and first["transactions"] == [TX]
    assert first["reported_finalized_head"]
    second = client.get(f"{root}/blocks/{BLOCK}", params={"offset": 1}).json()
    assert second["transactions"] == [OTHER] and not second["reported_finalized_head"]
    assert ("eth_getBlockByHash", [BLOCK, False]) in calls
    response = client.get(f"{root}/transactions/{TX}")
    assert response.status_code == 200, response.text
    tx = response.json()
    assert tx["execution_status"] == "reverted" and tx["block_number"] == 100
    assert tx["value_wei"] == str(int("100000000000000000001", 16))
    assert tx["execution_gas_cost_wei"] == str(21000 * 0x10000000)
    assert "NOT-RETAINED" not in response.text


def test_ethereum_rejects_wrong_network_wrong_hash_and_receipt_conflicts(source):
    explorer, values, calls = source
    values["eth_chainId"] = "0xaa36a7"
    with pytest.raises(ValueError, match="mainnet"):
        explorer.block("finalized")
    assert calls == [("eth_chainId", [])]
    values["eth_chainId"] = "0x1"
    with pytest.raises(ValueError, match="different block"):
        explorer.block("101")
    values["eth_getTransactionReceipt"]["transactionHash"] = OTHER
    with pytest.raises(ValueError, match="disagrees"):
        explorer.transaction(TX)
    values["eth_getTransactionByHash"].update(blockHash=None, blockNumber=None)
    values["eth_getTransactionReceipt"] = None
    assert explorer.transaction(TX)["execution_status"] == "pending"

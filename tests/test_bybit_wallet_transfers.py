"""Bybit same-UID funding history through actual signed reads and retained account evidence."""

import json
from urllib.parse import parse_qs, urlsplit

import ccxt
import pytest

from sibyl.exchanges import create_client
from sibyl.exchanges.funding import DAY
from sibyl.models import ConnectionCreate
from sibyl.services.transfers.reconciliation import eligible

START = 1_704_067_200_021
END = START + 8 * DAY
PATH = "/v5/asset/transfer/query-inter-transfer-list"
PRIVATE = "RAW_ADDRESS_OR_UID"


def native(identity, *, source="FUND", target="UNIFIED", status="SUCCESS", timestamp=START + 2000):
    return {
        "transferId": identity,
        "coin": "BTC",
        "amount": "0.011",
        "fromAccountType": source,
        "toAccountType": target,
        "timestamp": str(timestamp),
        "status": status,
        "uid": PRIVATE,
    }


def envelope(rows, cursor=""):
    return {"retCode": 0, "result": {"list": rows, "nextPageCursor": cursor}}


def test_signed_get_paginates_raw_rows_and_trims_subsecond_edges(monkeypatch):
    client = create_client("bybit", credentials={"apiKey": "test-key", "secret": "test-secret"})
    boundary = START // 1000 * 1000 + 7 * DAY
    responses = iter(
        [
            envelope([native("other-wallets", source="SPOT", target="FUND")], "page+two="),
            envelope([native("before", timestamp=START - 1), native("first", timestamp=boundary - 1)]),
            envelope(
                [
                    native("second", source="UNIFIED", target="FUND", status="PENDING", timestamp=boundary),
                    native("after", timestamp=END + 1),
                ]
            ),
        ]
    )
    calls = []

    def fetch(url, method, headers, body):
        parsed = urlsplit(url)
        assert parsed.scheme == "https" and parsed.path == PATH
        assert method == "GET" and body is None and headers.get("X-BAPI-SIGN")
        calls.append({key: values[0] for key, values in parse_qs(parsed.query).items()})
        return next(responses)

    monkeypatch.setattr(client._exchange, "fetch", fetch)
    try:
        page1 = client.fetch_funding_page("transfer", {"start": START, "end": END})
        assert page1.items == [] and not page1.caught_up
        page2 = client.fetch_funding_page("transfer", page1.cursor)
        page3 = client.fetch_funding_page("transfer", page2.cursor)
    finally:
        client.close()
    assert not page2.caught_up and page3.caught_up
    assert calls[0]["startTime"] == str(START // 1000 * 1000)
    assert calls[1] == calls[0] | {"cursor": "page+two="}
    assert calls[1]["endTime"] == str(boundary - 1)
    assert calls[2] == {"startTime": str(boundary), "endTime": str(END), "limit": "50"}
    (first,) = page2.items
    (second,) = page3.items
    assert first["native_id"] == "first" and first["status"] == "completed"
    assert first["wallet_route"] == {"from": "FUND", "to": "UNIFIED"}
    assert first["direction"] == "in" and second["direction"] == "out"
    assert second["native_id"] == "second" and second["status"] == "pending"
    assert first["fee"] == {"currency": None, "cost": None} and "posted_ms" not in first
    assert PRIVATE not in json.dumps([first, second])


@pytest.mark.parametrize(
    "result",
    [
        {"list": []},
        {"list": [], "nextPageCursor": "more"},
        {"list": [native("one")], "nextPageCursor": "same"},
        {"list": [native("one", timestamp=END + DAY)], "nextPageCursor": ""},
    ],
)
def test_malformed_page_cannot_signal_complete(monkeypatch, result):
    client = create_client("bybit", credentials={"apiKey": "test-key", "secret": "test-secret"})
    try:
        monkeypatch.setattr(
            client._exchange, "privateGetV5AssetTransferQueryInterTransferList", lambda _: {"result": result}
        )
        with pytest.raises(ccxt.ExchangeError):
            client.fetch_funding_page("transfer", {"start": START, "end": END, "page": "same"})
    finally:
        client.close()


def test_bybit_range_import_revises_record_without_guessing_posting_fee_or_cross_account_link(
    manual_client, monkeypatch
):
    client = manual_client
    services = client.app.state.services
    account = services.store.add_connection(
        ConnectionCreate(exchange="bybit", label="Bybit", api_key="test-key", secret="test-secret")
    )
    adapter = services.market.client(account)
    status = ["PENDING"]
    monkeypatch.setattr(
        adapter._exchange,
        "privateGetV5AssetTransferQueryInterTransferList",
        lambda _: envelope([native("9007199254740995", status=status[0])]),
    )
    accounts = client.get("/api/v1/funding-sync").json()["accounts"]
    row = next(row for row in accounts if row["id"] == account.id)
    assert (
        row["funding_streams"]
        == row["pending_update_streams"]
        == row["recent_sync_streams"]
        == [
            "withdrawal",
            "transfer",
        ]
    )
    body = {"streams": ["transfer"], "start": "2024-01-01T00:00:00Z", "end": "2024-01-03T00:00:00Z"}
    path = f"/api/v1/connections/{account.id}/funding-sync"
    assert client.post(path, json=body).status_code == 202
    services.funding_sync.tick()
    assert (
        client.get("/api/v1/account-ledger/funding?kind=transfer").json()["items"][0]["status"] == "pending"
    )
    status[0] = "SUCCESS"
    assert client.post(path, json=body).status_code == 202
    services.funding_sync.tick()
    records = client.get("/api/v1/account-ledger/funding?kind=transfer").json()
    (row,) = records["items"]
    assert row["native_id"] == "9007199254740995" and row["observed_version_count"] == 2
    assert row["wallet_route"] == {"from": "FUND", "to": "UNIFIED"}
    assert row["status"] == "completed" and row["wallet_scope"] == "configured"
    assert row["posted_ms"] is None and row["fee_known"] is False
    assert row["balance_effect"]["quantity"] is None
    assert not eligible(row, "in") and PRIVATE not in json.dumps(records)
    assert [row["field"] for row in row["last_observed_change"]["changes"]] == ["status"]

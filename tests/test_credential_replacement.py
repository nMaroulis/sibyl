"""Same-account key replacement keeps history and rejects stale, active or ambiguous edits."""

import json

import pytest

from sibyl.credentials.connections import CONFIRMATION, ConnectionCredentials
from sibyl.credentials.rotation import CONFIRMATION as VAULT_CONFIRMATION
from sibyl.credentials.rotation import RotateVault, VaultRotation
from sibyl.models import ConnectionCreate
from sibyl.services.accounts.ledger import AccountLedger, ledger_fill


def saved(client, *, active=False):
    return client.app.state.services.store.add_connection(
        ConnectionCreate(
            exchange="binance",
            label="My existing account",
            api_key="OLD-PRIVATE-KEY",
            secret="OLD-PRIVATE-SECRET",
        ),
        activate=active,
    )


def body(state, **values):
    return {
        "api_key": "NEW-PRIVATE-KEY",
        "secret": "NEW-PRIVATE-SECRET",
        "same_account": True,
        "confirmation": CONFIRMATION,
        "revision": state["revision"],
        **values,
    }


def status(client, identity):
    response = client.get(f"/api/v1/connections/{identity}/credentials/status")
    assert response.status_code == 200, response.text
    return response.json()


def test_replacement_preserves_identity_history_and_never_contacts_exchange(manual_client, monkeypatch):
    client = manual_client
    services = client.app.state.services
    account = saved(client)
    row = ledger_fill(
        {
            "id": "old-fill",
            "symbol": "BTC/USDT",
            "side": "buy",
            "amount": 1,
            "price": 100,
            "cost": 100,
            "timestamp": 1_700_000_000_000,
            "fees": [{"currency": "USDT", "cost": 0}],
        },
        {
            "account_id": account.id,
            "account": account.label,
            "symbol": "BTC/USDT",
            "exchange": "binance",
            "environment": "production",
        },
    )
    with services.store.db() as db:
        AccountLedger.upsert_fills(db, [row], "2026-01-01T00:00:00Z")

    def forbidden(*_args, **_kwargs):
        pytest.fail("Saving credentials contacted a provider")

    monkeypatch.setattr(services.market, "adapter", forbidden)
    state = status(client, account.id)
    response = client.put(f"/api/v1/connections/{account.id}/credentials", json=body(state))
    assert response.status_code == 200, response.text
    assert response.json()["revision"] != state["revision"]
    assert not response.json()["active"]
    assert "PRIVATE" not in response.text
    assert response.headers["cache-control"] == "no-store"
    assert services.store.credentials(account.id)["apiKey"] == "NEW-PRIVATE-KEY"
    assert len(response.json()["history"]) == 1
    assert (
        next(item for item in services.store.connections() if item.id == account.id).created_at
        == account.created_at
    )
    with services.store.db() as db:
        assert (
            json.loads(db.execute("SELECT payload FROM account_fills WHERE id=?", (row["id"],)).fetchone()[0])
            == row
        )
        assert "PRIVATE" not in str(
            [tuple(record) for record in db.execute("SELECT * FROM connection_key_changes")]
        )


def test_active_connection_cannot_change_keys_and_same_revision_does_not_replay(manual_client):
    client = manual_client
    account = saved(client, active=True)
    state = status(client, account.id)
    assert client.put(f"/api/v1/connections/{account.id}/credentials", json=body(state)).status_code == 400
    assert client.app.state.services.store.credentials(account.id)["apiKey"] == "OLD-PRIVATE-KEY"
    client.post(f"/api/v1/connections/{account.id}/activation", json={"active": False})
    assert client.put(f"/api/v1/connections/{account.id}/credentials", json=body(state)).status_code == 200
    assert client.put(f"/api/v1/connections/{account.id}/credentials", json=body(state)).status_code == 400
    assert len(status(client, account.id)["history"]) == 1


@pytest.mark.parametrize(
    "changes", [{"same_account": False}, {"confirmation": "replace"}, {"secret": ""}, {"exchange": "kraken"}]
)
def test_incomplete_or_unconfirmed_replacement_never_changes_the_stored_secret(manual_client, changes):
    client = manual_client
    account = saved(client)
    response = client.put(
        f"/api/v1/connections/{account.id}/credentials", json=body(status(client, account.id), **changes)
    )
    assert response.status_code in {400, 422}
    assert client.app.state.services.store.credentials(account.id)["secret"] == "OLD-PRIVATE-SECRET"
    assert status(client, account.id)["history"] == []


def test_vault_rotation_invalidates_a_prepared_credential_edit(manual_client):
    client = manual_client
    account = saved(client)
    before = status(client, account.id)
    service = VaultRotation(client.app.state.services.store)
    service.rotate(RotateVault(key_id=service.state()["key_id"], confirmation=VAULT_CONFIRMATION))
    assert client.put(f"/api/v1/connections/{account.id}/credentials", json=body(before)).status_code == 400
    assert client.app.state.services.store.credentials(account.id)["apiKey"] == "OLD-PRIVATE-KEY"


def test_demo_has_no_credential_rotation_and_unknown_account_is_not_found(manual_client):
    client = manual_client
    assert client.get("/api/v1/connections/demo/credentials/status").status_code == 400
    assert client.get("/api/v1/connections/no-such-account/credentials/status").status_code == 404
    assert ConnectionCredentials(client.app.state.services.store).store is client.app.state.services.store

"""Native private subscriptions and persisted read wakeups; never real account activity."""

import asyncio
import base64
import hashlib
import hmac
import json
import time
from types import SimpleNamespace

import ccxt
import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, utils
from test_order_management import setup as setup
from test_order_management import submit

from sibyl.exchanges.streams.clients import create_stream
from sibyl.exchanges.streams.service import PrivateAccountStreams, StreamAction
from sibyl.models import ConnectionCreate
from sibyl.operations.recovery import prepare_recovery


class Cache(list):
    def getLimit(self, symbol, limit):
        return limit


@pytest.mark.parametrize("exchange", ["binance", "binance-testnet", "coinbase", "kraken"])
async def test_actual_native_subscription_signing_endpoints_and_safe_signal_fields(exchange, monkeypatch):
    key = ec.generate_private_key(ec.SECP256R1())
    pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.TraditionalOpenSSL,
        serialization.NoEncryption(),
    ).decode()
    credentials = {
        "apiKey": "organizations/test/apiKeys/controlled-key" if exchange == "coinbase" else "STREAM-KEY",
        "secret": pem
        if exchange == "coinbase"
        else base64.b64encode(b"controlled-secret").decode()
        if exchange == "kraken"
        else "STREAM-SECRET",
    }
    stream = create_stream(
        SimpleNamespace(exchange=exchange, sandbox=exchange == "binance-testnet"), credentials
    )
    native = stream.native
    sent = []
    rest = []

    async def markets(*args, **kwargs):
        return {}

    native.load_markets = markets
    native.nonce = lambda: 1234567890000

    async def fetch(url, method="GET", headers=None, body=None, **kwargs):
        rest.append((url, headers, body))
        assert exchange == "kraken" and url.endswith("/0/private/GetWebSocketsToken")
        return {"error": [], "result": {"token": "NATIVE-PRIVATE-TOKEN", "expires": 900}}

    native.fetch = fetch

    async def watch(url, message_hash, message=None, *args, **kwargs):
        sent.append((url, message))
        if message and message.get("method") == "userDataStream.subscribe.signature":
            return {"subscriptionId": 0}
        return Cache(
            [
                {
                    "id": "native-123",
                    "symbol": "BTC/USDT",
                    "status": "closed",
                    "filled": 0.01,
                    "cost": 500,
                    "info": {"secret": "NEVER-RETURN"},
                }
            ]
        )

    native.watch = watch
    try:
        result = await stream.receive()
        assert result[0]["id"] == "native-123" and "info" not in result[0]
        assert "PRIVATE-TOKEN" not in json.dumps(result) and "NEVER-RETURN" not in json.dumps(result)
        if exchange.startswith("binance"):
            url, payload = sent[0]
            expected = (
                "wss://ws-api.testnet.binance.vision/ws-api/v3"
                if exchange == "binance-testnet"
                else "wss://ws-api.binance.com:443/ws-api/v3"
            )
            assert url == expected and payload["method"] == "userDataStream.subscribe.signature"
            params = dict(payload["params"])
            signature = params.pop("signature")
            query = "&".join(f"{k}={v}" for k, v in sorted(params.items()))
            assert signature == hmac.new(b"STREAM-SECRET", query.encode(), hashlib.sha256).hexdigest()
            assert params["apiKey"] == "STREAM-KEY" and not rest
        elif exchange == "coinbase":
            url, payload = sent[0]
            assert (
                url == "wss://advanced-trade-ws.coinbase.com"
                and payload["channel"] == "user"
                and payload["product_ids"] == []
            )
            encoded = payload["jwt"].split(".")

            def decode(text):
                return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))

            header, claims = json.loads(decode(encoded[0])), json.loads(decode(encoded[1]))
            assert header["kid"] == credentials["apiKey"] and claims["sub"] == credentials["apiKey"]
            signature = decode(encoded[2])
            r = int.from_bytes(signature[:32], "big")
            s = int.from_bytes(signature[32:], "big")
            key.public_key().verify(
                utils.encode_dss_signature(r, s), ".".join(encoded[:2]).encode(), ec.ECDSA(hashes.SHA256())
            )
            assert claims["exp"] - claims["nbf"] == 120 and not rest
        else:
            url, payload = sent[0]
            assert url == "wss://ws-auth.kraken.com/v2" and payload["method"] == "subscribe"
            assert (
                payload["params"]["channel"] == "executions"
                and payload["params"]["token"] == "NATIVE-PRIVATE-TOKEN"
            )
            assert payload["params"]["snap_orders"] is True and rest[0][1]["API-Key"] == "STREAM-KEY"
            assert rest[0][1]["API-Sign"] and credentials["secret"] not in rest[0][1]["API-Sign"]
    finally:
        await stream.close()


class QueueStream:
    def __init__(self):
        self.queue = asyncio.Queue()
        self.closed = False

    async def receive(self):
        result = await self.queue.get()
        if isinstance(result, Exception):
            raise result
        return result

    async def close(self):
        self.closed = True


def configure(service, connection, enabled=True):
    row = next(row for row in service.snapshot()["accounts"] if row["account_id"] == connection.id)
    return service.configure(connection.id, StreamAction(enabled=enabled, revision=row["revision"]))


@pytest.fixture
def observer(setup):
    trading, venue, connection = setup
    streams = []

    def factory(account, credentials):
        assert account.id == connection.id
        stream = QueueStream()
        streams.append(stream)
        return stream

    service = PrivateAccountStreams(trading.store, trading, factory=factory)
    return service, streams, trading, venue, connection


async def settle(predicate):
    deadline = time.monotonic() + 3
    while not predicate() and time.monotonic() < deadline:
        await asyncio.sleep(0.005)
    assert predicate()


async def test_stream_only_schedules_enabled_rest_tracking_preserves_pause_and_never_mutates_fill_evidence(
    observer,
):
    service, streams, trading, venue, connection = observer
    intent = submit(trading, connection)
    trading.lifecycle.track(intent["id"], True)
    with trading.store.db() as db:
        row = trading.lifecycle.read(db, intent["id"])
        row["next_check"] = 9999999999
        trading.lifecycle.write(db, row)
        fills = trading.reconciliation._read(db, intent["id"])
        fills["next_attempt"] = 9999999999
        trading.reconciliation._write(db, intent["id"], fills)
    configure(service, connection)
    await service.tick()
    await settle(lambda: len(streams) == 1)
    with trading.store.db() as db:
        assert trading.lifecycle.read(db, intent["id"])["next_check"] == 0
        before = trading.lifecycle.read(db, intent["id"])
        assert db.execute("SELECT COUNT(*) FROM account_fills").fetchone()[0] == 0
    signal = {"id": "native-123", "symbol": "BTC/USDT", "status": "closed", "filled": 0.01, "cost": 500}
    await streams[0].queue.put([signal, signal])
    await settle(lambda: service.snapshot()["accounts"][0].get("signals", 0) == 1)
    await service.tick()
    with trading.store.db() as db:
        after = trading.lifecycle.read(db, intent["id"])
        assert after["status"] == before["status"] and after.get("filled") == before.get("filled")
        assert db.execute("SELECT COUNT(*) FROM account_fills").fetchone()[0] == 0
    assert venue.calls == 1 and venue.cancels == 0
    trading.lifecycle.track(intent["id"], False)
    await streams[0].queue.put([{**signal, "filled": 0.02}])
    await settle(lambda: service.snapshot()["accounts"][0]["signals"] == 2)
    await service.tick()
    with trading.store.db() as db:
        assert not trading.lifecycle.read(db, intent["id"])["tracking"]
        assert not trading.reconciliation._read(db, intent["id"])["enabled"]
    await service.close()
    assert streams[0].closed


async def test_reconnect_restart_and_backstop_keep_pending_account_sweeps_durable(observer):
    service, streams, trading, venue, connection = observer
    configure(service, connection)
    await service.tick()
    await settle(lambda: len(streams) == 1)
    await streams[0].queue.put(ccxt.NetworkError("SECRET-RAW-URL"))
    await settle(lambda: service.snapshot()["accounts"][0]["state"] == "retrying")
    snapshot = service.snapshot()
    assert "SECRET" not in json.dumps(snapshot) and snapshot["accounts"][0]["wake_pending"]
    # Recreating the owner preserves enabled intent and marks a full read sweep.
    await service.close()
    restarted = PrivateAccountStreams(trading.store, trading, factory=service.factory)
    with trading.store.db() as db:
        row = restarted._read(db, connection.id)
        assert row["wake_pending"] and row["full_sweep"]
    await restarted.tick()
    await settle(lambda: len(streams) == 2)
    row = next(row for row in restarted.snapshot()["accounts"] if row["account_id"] == connection.id)
    assert row["last_wakeup_at"] and row["wakeups"] >= 2
    await restarted.close()


async def test_pause_stale_generation_inactivity_and_changed_key_version_stop_observation(observer):
    service, streams, trading, venue, connection = observer
    configure(service, connection)
    await service.tick()
    await settle(lambda: len(streams) == 1)
    with trading.store.db() as db:
        generation = service._read(db, connection.id)["generation"]
    configure(service, connection, False)
    service.signal(connection.id, generation, [{"id": "OLD", "symbol": "BTC/USDT"}])
    await service.tick()
    assert streams[0].closed
    assert service.snapshot()["accounts"][0]["signals"] == 0
    configure(service, connection)
    await service.tick()
    await settle(lambda: len(streams) == 2)
    trading.store.activate_account(connection.id, False)
    await service.tick()
    assert streams[-1].closed and service.snapshot()["accounts"][0]["state"] == "inactive"
    # Credential-replacement audit identity, independent of vault encryption rotation.
    with trading.store.db() as db:
        db.execute(
            "CREATE TABLE IF NOT EXISTS connection_key_changes(id INTEGER PRIMARY KEY,account_id TEXT)"
        )
        db.execute("INSERT INTO connection_key_changes(account_id) VALUES(?)", (connection.id,))
    await service.tick()
    state = service.snapshot()["accounts"][0]
    assert not state["enabled"] and state["state"] == "credentials_changed"
    await service.close()


async def test_native_access_rejection_is_blocked_until_explicit_reenable(observer):
    service, streams, trading, venue, connection = observer
    configure(service, connection)
    await service.tick()
    await settle(lambda: len(streams) == 1)
    await streams[0].queue.put(ccxt.AuthenticationError("PRIVATE-KEY"))
    await settle(lambda: service.snapshot()["accounts"][0]["state"] == "attention")
    await service.tick()
    assert len(streams) == 1
    configure(service, connection, False)
    configure(service, connection)
    await service.tick()
    await settle(lambda: len(streams) == 2)
    await service.close()


async def test_stream_restore_is_paused_and_opt_in_does_not_authenticate(observer):
    service, streams, trading, venue, connection = observer
    configure(service, connection)
    assert streams == []
    prepare_recovery(trading.store, "isolated-archive")
    assert not service.snapshot()["accounts"][0]["enabled"]
    await service.tick()
    assert streams == []
    await service.close()


def test_api_supported_inventory_passive_state_and_stale_editor(manual_client):
    client = manual_client
    response = client.get("/api/v1/account-streams")
    assert response.status_code == 200 and response.headers["cache-control"] == "no-store"
    account = client.app.state.services.store.add_connection(
        ConnectionCreate(
            exchange="binance", label="Isolated observer", api_key="TEST-KEY", secret="TEST-SECRET"
        )
    )
    response = client.put(
        "/api/v1/account-streams/" + account.id, json={"enabled": True, "revision": "0" * 32}
    )
    assert response.status_code == 200 and response.json()["accounts"][0]["enabled"]
    assert not client.app.state.services.account_streams.tasks
    stale = client.put("/api/v1/account-streams/" + account.id, json={"enabled": False, "revision": "0" * 32})
    assert stale.status_code == 409 or stale.status_code == 400
    spec = next(row for row in client.get("/api/v1/exchanges").json()["items"] if row["id"] == "binance")
    features = [feature for group in spec["support"] for feature in group["features"]]
    assert next(feature for feature in features if feature["id"] == "private_orders")["status"] == "available"

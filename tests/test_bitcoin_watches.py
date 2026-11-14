"""Persistent Bitcoin watches retain only meaningful changes from checked observations."""

import copy
from concurrent.futures import ThreadPoolExecutor
from threading import Event

import httpx
from test_bitcoin_output_spends import source

from sibyl.blockchain import demo
from sibyl.blockchain.watches import BitcoinWatches
from sibyl.operations.recovery import prepare_recovery

PARENT = f"{3:064x}"
WATCHES = "/api/v1/bitcoin/watches"
INBOX = "/api/v1/notifications"


def add(client, *, simulated=False, index=0):
    response = client.post(WATCHES, json={"transaction_id": PARENT, "output_index": index, "demo": simulated})
    assert response.status_code == 201, response.text
    assert response.headers["cache-control"] == "no-store"
    return response.json()


def control(client, watch, action):
    return client.post(f"{WATCHES}/{watch['id']}", json={"action": action, "revision": watch["revision"]})


def setup(manual_client, override):
    service = manual_client.app.state.services.bitcoin_watches
    clock = [1796083200]
    service.clock = lambda: clock[0]
    service.explorer, calls = source(override)
    return service, clock, calls


def test_restored_checkpoint_retains_spend_changes_and_is_private(manual_client):
    row = {"spent": False}
    owner, clock, calls = setup(manual_client, lambda path: [row] if path.endswith("/outspends") else None)
    watch = add(manual_client)
    assert watch == add(manual_client) and not calls
    owner.tick()
    assert manual_client.get(INBOX).json()["items"] == []
    baseline = owner.list()["items"][0]["observation"]
    assert baseline["state"] == "unspent" and baseline["parent_block_hash"]

    # Recreate the scheduler against the same database. It must compare with retained evidence.
    owner = BitcoinWatches(owner.store, owner.explorer, clock=owner.clock)
    row.update(spent=True, txid=demo.PENDING_TXID, vin=0, status={"confirmed": False})
    clock[0] += 120
    owner.tick()
    owner.tick()
    document = manual_client.get(f"{INBOX}/export?kind=bitcoin")
    assert document.headers["cache-control"] == "no-store"
    (notice,) = document.json()["items"]
    assert notice["previous"] == baseline
    assert notice["current"]["spending_txid"] == demo.PENDING_TXID
    assert notice["changes"] == ["Output spend changed"]
    assert notice["rule_id"] == watch["id"] and notice["cycle"] == 1
    assert control(manual_client, watch, "remove").status_code == 200
    assert not owner.list()["items"] and manual_client.get(INBOX).json()["total"] == 1


def test_pending_inclusion_relocation_and_reversal_ignore_depth_changes(manual_client):
    transaction = copy.deepcopy(demo.read(f"/tx/{PARENT}"))
    row = copy.deepcopy(demo.read(f"/tx/{PARENT}/outspends")[0])
    tip = [demo.TIP]

    def override(path):
        return {
            f"/tx/{PARENT}": transaction,
            f"/tx/{PARENT}/outspends": [row],
            "/blocks/tip/height": str(tip[0]),
        }.get(path)

    owner, clock, _ = setup(manual_client, override)
    add(manual_client)
    owner.tick()
    row["status"] = copy.deepcopy(demo.read(f"/tx/{demo.TXID}")["status"])
    clock[0] += 120
    owner.tick()
    assert manual_client.get(INBOX).json()["items"][0]["changes"] == ["Spender inclusion changed"]
    transaction["status"]["block_hash"] = "b" * 64
    row["status"]["block_hash"] = "f" * 64
    clock[0] += 120
    owner.tick()
    latest = manual_client.get(INBOX).json()["items"][0]
    assert latest["changes"] == ["Parent inclusion changed", "Spender inclusion changed"]
    assert latest["current"]["parent_block_hash"] == "b" * 64
    tip[0] += 8
    clock[0] += 120
    owner.tick()
    assert manual_client.get(INBOX).json()["total"] == 2
    row["status"] = {"confirmed": False}
    clock[0] += 120
    owner.tick()
    reverted = manual_client.get(INBOX).json()["items"][0]
    assert reverted["changes"] == ["Spender inclusion changed"]
    assert reverted["previous"]["spending_block_hash"] == "f" * 64
    assert reverted["current"]["state"] == "pending"


def test_indeterminate_and_rate_limited_reads_do_not_replace_reliable_evidence(manual_client):
    response = [None]

    def override(path):
        if path.endswith("/outspends"):
            return response[0]

    owner, clock, calls = setup(manual_client, override)
    watch = add(manual_client)
    owner.tick()
    baseline = owner.list()["items"][0]["observation"]
    response[0] = [{"spent": True}]
    clock[0] += 120
    owner.tick()
    retry = owner.list()["items"][0]
    assert retry["error"] and retry["observation"] == baseline
    calls.clear()
    clock[0] += 239
    owner.tick()
    assert not calls
    response[0] = httpx.Response(429, text="private upstream error")
    clock[0] += 1
    owner.tick()
    add(manual_client, index=1)
    demo_watch = add(manual_client, simulated=True)
    calls.clear()
    owner.tick()
    watches = {item["id"]: item for item in owner.list()["items"]}
    simulated = watches[demo_watch["id"]]["observation"]
    assert not calls and simulated["state"] == baseline["state"]
    assert simulated["spending_txid"] == baseline["spending_txid"]
    assert watches[watch["id"]]["observation"] == baseline
    assert "rate limiting" in next(x["error"] for x in watches.values() if x["error"])
    assert manual_client.get(INBOX).json()["total"] == 0


def test_pause_fences_a_running_check_and_conflicting_controls(manual_client):
    started, release = Event(), Event()

    def override(path):
        if path.endswith("/outspends") and clock[0] > 1796083200:
            started.set()
            assert release.wait(5)
            return [{"spent": False}]

    owner, clock, _ = setup(manual_client, override)
    active = add(manual_client)
    owner.tick()
    clock[0] += 120

    with ThreadPoolExecutor(max_workers=1) as pool:
        running = pool.submit(owner.tick)
        try:
            assert started.wait(5)
            pause = control(manual_client, active, "pause")
            assert pause.status_code == 200 and not pause.json()["active"]
            assert control(manual_client, active, "remove").status_code == 409
        finally:
            release.set()
        running.result(timeout=5)

    (retained,) = owner.list()["items"]
    assert retained["observation"]["state"] == "pending"
    assert manual_client.get(INBOX).json()["total"] == 0
    assert control(manual_client, retained, "resume").json()["active"]
    owner.tick()
    assert manual_client.get(INBOX).json()["total"] == 1


def test_recovery_pauses_watches_and_retains_demo_evidence(manual_client):
    service, _, _ = setup(manual_client, None)
    watch = add(manual_client, simulated=True)
    service.tick()
    prepare_recovery(service.store, "opaque-backup-id")
    recovered = BitcoinWatches(service.store, service.explorer, recovery_required=True)
    (saved,) = recovered.list()["items"]
    assert saved["id"] == watch["id"]
    assert not saved["active"] and saved["next_check"] is None
    assert saved["revision"] == watch["revision"] + 1
    assert saved["observation"]["state"] == "pending"

    manual_client.app.state.services.bitcoin_watches = recovered
    assert control(manual_client, saved, "resume").status_code == 409
    assert manual_client.post(WATCHES, json={"transaction_id": PARENT, "output_index": 0}).status_code == 409

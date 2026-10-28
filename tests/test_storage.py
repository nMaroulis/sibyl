"""Verify financial invariants, encryption, and persistence across store instances."""

from concurrent.futures import ThreadPoolExecutor

import pytest

from sibyl.models import ConnectionCreate, OrderRequest
from sibyl.storage import Store


def order(**changes):
    return OrderRequest(side="buy", quantity=0.01, idempotency_key="paper-test-1", **changes)


def test_credentials_are_encrypted_and_write_only(store):
    connection = store.add_connection(
        ConnectionCreate(
            exchange="binance",
            label="My account",
            api_key="sentinel-api-secret",
            secret="sentinel-secret-key",
        )
    )
    assert store.credentials(connection.id)["apiKey"] == "sentinel-api-secret"
    assert b"sentinel-api-secret" not in store.path.read_bytes()
    assert "sentinel" not in connection.model_dump_json()
    assert "credentials" not in store.connections()[0].model_dump()
    assert store.path.stat().st_mode & 0o077 == 0


def test_paper_fee_and_balance_accounting(store):
    before = store.balances()
    fill = store.execute_paper(order(), 50_000)
    after = store.balances()
    assert fill["fee"] == 0.5
    assert after["USDT"] == pytest.approx(before["USDT"] - 500.5)
    assert after["BTC"] == pytest.approx(before["BTC"] + 0.01)


def test_sell_credits_quote_less_fee(store):
    before = store.balances()
    request = OrderRequest(side="sell", quantity=0.1, idempotency_key="paper-sell-1")
    store.execute_paper(request, 50_000)
    assert store.balances()["USDT"] == before["USDT"] + 4995
    assert store.balances()["BTC"] == pytest.approx(before["BTC"] - 0.1)


def test_concurrent_retry_spends_exactly_once(store):
    before = store.balances()
    with ThreadPoolExecutor(max_workers=8) as pool:
        fills = list(pool.map(lambda _: store.execute_paper(order(), 50_000), range(12)))
    assert len({fill["id"] for fill in fills}) == 1
    assert len(store.orders()) == 1
    assert store.balances()["USDT"] == pytest.approx(before["USDT"] - 500.5)


def test_reused_key_cannot_change_order_details(store):
    store.execute_paper(order(), 50_000)
    different = OrderRequest(side="buy", quantity=0.02, idempotency_key="paper-test-1")
    with pytest.raises(ValueError, match="different order"):
        store.execute_paper(different, 50_000)


@pytest.mark.parametrize("side,quantity", [("buy", 10), ("sell", 100)])
def test_insufficient_funds_roll_back(store, side, quantity):
    before = store.balances()
    with pytest.raises(ValueError, match="Insufficient"):
        store.execute_paper(
            OrderRequest(side=side, quantity=quantity, idempotency_key="overspend-test"), 50_000
        )
    assert store.balances() == before
    assert store.orders() == []


def test_restart_preserves_vault_balances_and_runs(store, settings):
    store.execute_paper(order(), 50_000)
    connection = store.add_connection(
        ConnectionCreate(exchange="kraken", label="Kraken", api_key="key", secret="secret")
    )
    store.record("test", {"answer": 42})
    restarted = Store(settings.data_dir)
    assert restarted.balances() == store.balances()
    assert restarted.credentials(connection.id)["secret"] == "secret"
    assert restarted.runs("test")[0]["payload"] == {"answer": 42}

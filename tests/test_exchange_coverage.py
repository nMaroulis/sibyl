"""Category colours describe implemented app paths, never account connectivity."""

import pytest

from sibyl.exchanges import create_client
from sibyl.exchanges.catalog import exchange_spec
from sibyl.exchanges.registry import provider_catalog
from sibyl.exchanges.support import category_summary, support_groups


@pytest.mark.parametrize(
    "statuses, expected, count",
    [
        (["available", "available"], "supported", 2),
        (["available", "pending"], "partial", 1),
        (["available", "unavailable"], "partial", 1),
        (["pending", "unavailable"], "unsupported", 0),
        (["simulated", "simulated"], "simulated", 2),
        (["simulated", "unavailable"], "simulated", 1),
        ([], "unsupported", 0),
    ],
)
def test_category_summary_counts_every_feature(statuses, expected, count):
    assert category_summary([{"status": status} for status in statuses]) == {
        "status": expected,
        "implemented": count,
        "total": len(statuses),
    }


def test_binance_categories_do_not_hide_missing_features():
    provider = next(row for row in provider_catalog()["items"] if row["id"] == "binance")
    groups = {row["id"]: row for row in provider["support"]}
    assert groups["account"]["summary"] == {"status": "supported", "implemented": 3, "total": 3}
    assert groups["spot"]["summary"]["status"] == "partial"  # Stop/OCO is not implemented.
    assert groups["history"]["summary"]["status"] == "partial"  # Transfers are not imported.
    assert groups["market"]["summary"]["status"] == "partial"  # No WebSockets.
    assert groups["limits"]["summary"]["status"] == "unsupported"


def test_sdk_flags_cannot_enable_unreviewed_writes_or_imports():
    capabilities = dict.fromkeys(
        ["ticker", "candles", "order_book", "balances", "order_status", "open_orders", "trade_history"],
        "native",
    )
    groups = support_groups(exchange_spec("bitmart"), capabilities, None)
    rows = {row["id"]: row for group in groups for row in group["features"]}
    assert next(group for group in groups if group["id"] == "spot")["summary"]["status"] == "unsupported"
    for identity in [
        "market_orders",
        "limit_orders",
        "cancel_orders",
        "history_import",
        "fill_reconciliation",
        "recovery",
        "discovery",
        "backfills",
    ]:
        assert rows[identity]["status"] == "pending"
    account = next(group for group in groups if group["id"] == "account")
    assert account["summary"]["status"] == "supported"
    capabilities["balances"] = "unavailable"
    account = support_groups(exchange_spec("bitmart"), capabilities, None)[0]
    assert account["summary"]["status"] == "partial"
    assert next(row for row in account["features"] if row["id"] == "permissions")["status"] == "unavailable"


def test_catalog_backfills_and_imports_match_real_client_gates(store):
    for provider in provider_catalog()["items"]:
        client = (
            create_client(provider["id"], store=store)
            if provider["simulated"]
            else create_client(provider["id"])
        )
        try:
            features = {row["id"]: row for group in provider["support"] for row in group["features"]}
            available = {"available", "simulated"}
            assert (features["backfills"]["status"] in available) == bool(client.candle_history)
            assert (features["history_import"]["status"] in available) == bool(client.history_kind)
            for group in provider["support"]:
                assert group["summary"] == category_summary(group["features"])
        finally:
            client.close()

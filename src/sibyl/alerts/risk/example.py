"""Isolated illustrative risk evidence; no Demo activation, balance read or saved rule."""


def risk_alert_example():
    """Preview a fixed account set, a reviewed limit and original notification evidence."""
    at = "2026-10-23T10:00:00+00:00"
    account = dict(id="demo", exchange="demo", label="Demo account", sandbox=False, created_at=at)
    source = dict(
        source="demo", source_label="Sibyl Demo", source_kind="demo", provider="demo", environment="demo"
    )
    observation = dict(total=12000, currency="USDT", metric_value=64, peak=12500, peak_at=at, as_of=at)
    sample = dict(
        id=1,
        revision=1,
        policy=dict(
            metric="concentration", asset="BTC", threshold=60, reset_threshold=58, label="Bitcoin allocation"
        ),
        **observation,
        environment="demo",
        source_info=source,
        accounts=[account],
        started_at=at,
        complete=True,
        balance_reads=[dict(account_id="demo", received_at=at)],
        holdings=[
            dict(asset="BTC", value=7680, allocation=64, path=["BTC", "USDT"], observed_at=at),
            dict(asset="USDT", value=4320, allocation=36, path=["USDT"], observed_at=None),
        ],
    )
    rule = dict(
        id="example-risk-rule",
        source="demo",
        source_info=source,
        environment="demo",
        account_ids=["demo"],
        accounts=[account],
        metric="concentration",
        asset="BTC",
        threshold=60,
        reset_threshold=58,
        cooldown_seconds=300,
        notify_recovery=True,
        label="Bitcoin allocation",
        status="armed",
        revision=1,
        cycle=1,
        notifications=1,
        checks=1,
        created_at=at,
        updated_at=at,
        armed_at=at,
        next_check=0,
        peak=12500,
        peak_at=at,
        in_breach=True,
        incident_notified=True,
        cooldown_until=0,
        last_sample_id=1,
        last_observation=observation,
        last_checked_at=at,
        last_notified_at=at,
        error=None,
        failures=0,
        evaluation_note=None,
    )
    notification = dict(
        kind="risk",
        id="example-risk-notice",
        rule_id=rule["id"],
        rule_revision=1,
        label=rule["label"],
        source="demo",
        source_label="Sibyl Demo",
        environment="demo",
        pricing_environment="demo",
        accounts=[account],
        account_ids=["demo"],
        metric="concentration",
        asset="BTC",
        threshold=60,
        reset_threshold=58,
        action="breached",
        **{key: observation[key] for key in ("total", "currency", "metric_value", "peak", "peak_at")},
        observed_at=at,
        created_at=at,
        read_at=None,
        sample_id=1,
        cycle=1,
    )
    return dict(
        rules=dict(
            items=[rule],
            count=1,
            total=1,
            limit=25,
            offset=0,
            page_size=50,
            check_interval_seconds=60,
            max_accounts=10,
            delivery="in_app",
            requires_running_server=True,
        ),
        inbox=dict(items=[notification], total=1, unread=1, limit=20, offset=0, delivery="in_app"),
        evidence=dict(
            rule=rule,
            sample=sample,
            samples=[dict(id=1, **observation)],
            revision=1,
            selected_sample_id=1,
            retention_days=14,
            sample_limit=120,
            note="Illustrative only; values include cash movements and are not investment returns.",
        ),
    )

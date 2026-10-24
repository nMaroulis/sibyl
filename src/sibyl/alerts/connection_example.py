"""Illustrative connection alert, isolated from saved rules and provider telemetry."""


def connection_alert_example():
    """Preview recorded-failure evidence without connecting, probing or saving anything."""
    at = "2026-10-23T09:00:00+00:00"
    source = dict(
        id="binance",
        name="Binance",
        kind="exchange",
        provider="binance",
        environment="production",
        available=True,
    )
    state = dict(
        failures=3,
        successes=0,
        incident=True,
        session="example",
        generation="example",
        sequence=3,
        at=at,
        error_kind="network",
    )
    rule = dict(
        id="example-connection-alert",
        source="binance",
        source_info=source,
        label="My price feed",
        failures_required=3,
        successes_required=2,
        notify_recovery=True,
        status="armed",
        revision=1,
        notifications=1,
        cursor=3,
        operations={"fetch_ticker": state},
        tracking_note=None,
        created_at=at,
        updated_at=at,
        armed_at=at,
        next_check=0,
        last_checked_at=at,
        last_event_at=at,
        last_notified_at=at,
    )
    notification = dict(
        id="example-connection-notification",
        kind="connection",
        rule_id=rule["id"],
        rule_revision=1,
        source="binance",
        source_label="Binance",
        provider="binance",
        environment="production",
        label=rule["label"],
        operation="fetch_ticker",
        action="failing",
        error_kind="network",
        reason="Provider temporarily unavailable; shared reads will retry after backoff.",
        failures=3,
        successes=0,
        failures_required=3,
        successes_required=2,
        event_id=3,
        cycle=3,
        observed_at=at,
        created_at=at,
        read_at=None,
    )
    return dict(
        rules=dict(
            items=[rule],
            sources=[source],
            count=1,
            total=1,
            limit=50,
            page_size=50,
            offset=0,
            recording=dict(status="ready", dropped_observations=0, last_failure_at=None),
            delivery="in_app",
            requires_running_server=True,
        ),
        inbox=dict(items=[notification], total=1, unread=1, limit=20, offset=0, delivery="in_app"),
    )

"""Deterministic observed-value risk transitions, separate from reads and storage."""


def baseline(rule: dict):
    """Start a new observation window, including its observed peak and incident state."""
    rule.update(
        peak=None,
        peak_at=None,
        in_breach=False,
        incident_notified=False,
        cooldown_until=0,
        last_sample_id=None,
        last_observation=None,
        checks=0,
        last_checked_at=None,
        last_notified_at=None,
        error=None,
        failures=0,
        evaluation_note=None,
    )


def assess_risk(rule: dict, sample: dict, now: float) -> str | None:
    """Update from a complete fresh sample; return breach/recovery only when due.

    A recovery level supplies hysteresis. A new breach inside cooldown waits for
    another fresh qualifying sample after cooldown. Unnotified incidents do not
    produce orphaned recoveries. Peaks are observed account values, not returns.
    """
    total = sample["total"]
    if rule["peak"] is None or total > rule["peak"]:
        rule.update(peak=total, peak_at=sample["as_of"])
    if rule["metric"] == "value_floor":
        value = total
    elif rule["metric"] == "concentration":
        if total <= 0:
            rule["evaluation_note"] = "Concentration is unavailable for a zero-value account set."
            sample.update(metric_value=None, peak=rule["peak"], peak_at=rule["peak_at"])
            return None
        held = next((row["value"] for row in sample["holdings"] if row["asset"] == rule["asset"]), 0)
        value = min(100, held / total * 100)
    else:
        if rule["peak"] <= 0:
            rule["evaluation_note"] = "Waiting for a positive observed account value to establish a peak."
            sample.update(metric_value=None, peak=rule["peak"], peak_at=rule["peak_at"])
            return None
        value = max(0, min(100, (rule["peak"] - total) / rule["peak"] * 100))
    sample.update(metric_value=value, peak=rule["peak"], peak_at=rule["peak_at"])
    breached = value <= rule["threshold"] if rule["metric"] == "value_floor" else value >= rule["threshold"]
    cleared = (
        value >= rule["reset_threshold"]
        if rule["metric"] == "value_floor"
        else value <= rule["reset_threshold"]
    )
    rule["evaluation_note"] = None
    if rule["in_breach"] and cleared:
        notified = rule["incident_notified"]
        rule.update(in_breach=False, incident_notified=False)
        return "recovered" if notified and rule["notify_recovery"] else None
    if breached:
        rule["in_breach"] = True
        if not rule["incident_notified"]:
            if now >= rule["cooldown_until"]:
                rule.update(incident_notified=True, cooldown_until=now + rule["cooldown_seconds"])
                return "breached"
            rule["evaluation_note"] = (
                "Limit observed during cooldown; a fresh qualifying check is required after cooldown."
            )
    return None

"""Small deterministic price-alert transitions; persistence and quote reads live elsewhere."""

from datetime import datetime

MAX_CROSSING_GAP = 300


def rule_defaults(rule: dict) -> dict:
    """Read older one-shot rules without changing their behavior or rewriting their history."""
    return {
        "repeat": "once",
        "cooldown_seconds": 300,
        "cooldown_until": 0,
        "waiting_reset": False,
        "baseline_price": None,
        "baseline_at": None,
        "evaluation_note": None,
        **rule,
    }


def qualifies(rule: dict, price: float) -> bool:
    """A touch qualifies; the opposite side used to establish a crossing is strict."""
    return (
        price >= rule["threshold"]
        if rule["condition"] in {"above", "crosses_above"}
        else price <= rule["threshold"]
    )


def assess(rule: dict, price: float, observed_at: str, wall_time: float) -> bool:
    """Update a rule from one ordered quote and report whether a notification is due.

    Crossing rules need a previous, strictly opposite observation no more than
    five minutes earlier. Recurring level rules may notify on their first quote,
    then require an observed reset and a new entry. Moves during cooldown are
    consumed, never delivered later from an old crossing. Missing/error evidence
    clears the baseline in the caller; the last displayed price remains retained.
    """
    observed = datetime.fromisoformat(observed_at).timestamp()
    if rule.get("observed_at") and observed <= datetime.fromisoformat(rule["observed_at"]).timestamp():
        rule["evaluation_note"] = (
            "Waiting for a newer provider quote; repeated or older observations are ignored."
        )
        return False
    previous = rule["baseline_price"]
    if (
        not rule["baseline_at"]
        or not 0 < observed - datetime.fromisoformat(rule["baseline_at"]).timestamp() <= MAX_CROSSING_GAP
    ):
        previous = None
    rule.update(
        last_price=price,
        observed_at=observed_at,
        baseline_price=price,
        baseline_at=observed_at,
        evaluation_note=None,
    )
    matched = qualifies(rule, price)
    recurring = rule["repeat"] == "after_reset"
    if rule["waiting_reset"]:
        rule["waiting_reset"] = matched
        rule["evaluation_note"] = (
            "Waiting for the price to return to the other side of the level."
            if matched
            else "Reset observed. Waiting for a new qualifying move after cooldown."
        )
        return False
    if wall_time < rule["cooldown_until"]:
        if recurring and matched:
            rule["waiting_reset"] = True
        rule["evaluation_note"] = "Cooldown active. Qualifying moves during cooldown are skipped."
        return False
    crossing = rule["condition"].startswith("crosses_") or (recurring and rule["triggered_at"] is not None)
    should_notify = matched and (not crossing or (previous is not None and not qualifies(rule, previous)))
    if crossing and previous is None:
        rule["evaluation_note"] = "A fresh baseline was recorded. Waiting for a newly observed crossing."
    if recurring and rule["triggered_at"] is not None and matched and not should_notify:
        rule["waiting_reset"] = True
    return should_notify

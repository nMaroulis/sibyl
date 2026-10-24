"""Deterministic transport-incident transitions, without provider or database calls."""

from datetime import datetime

MAX_OBSERVATION_GAP = 300


def reset_streaks(rule: dict, note: str):
    """Forget uncertain streaks but retain recorded incidents until confirming reads."""
    for state in rule["operations"].values():
        state.update(failures=0, successes=0, session=None, generation=None, sequence=None, at=None)
    rule["tracking_note"] = note


def assess_connection(rule: dict, event: dict, now: float) -> str | None:
    """Count consecutive actual reads of the same operation, with strict continuity.

    Retired profiles and request/market errors cannot establish source failure or
    recovery. Session/profile changes and recording gaps reset streaks. An open
    incident is historical evidence, not a claim that a source is currently down.
    """
    if event["retired"]:
        return None
    try:
        parsed = datetime.fromisoformat(event["at"])
        if parsed.tzinfo is None or parsed.timestamp() > now + 60:
            raise ValueError("Invalid read time")
        observed = parsed.timestamp()
    except (ValueError, TypeError, OverflowError):
        reset_streaks(rule, "A read timestamp could not be trusted; waiting for new evidence.")
        return None
    operation = event["operation"]
    state = rule["operations"].setdefault(
        operation,
        {
            "failures": 0,
            "successes": 0,
            "incident": False,
            "session": None,
            "generation": None,
            "sequence": None,
            "at": None,
            "error_kind": None,
        },
    )
    same_stream = (state["session"], state["generation"]) == (event["session"], event["generation"])
    if state["sequence"] is not None and same_stream and event["sequence"] <= state["sequence"]:
        state.update(failures=0, successes=0)
        rule["tracking_note"] = "Out-of-order read evidence ignored; consecutive counts restarted."
        return None
    gap = observed - datetime.fromisoformat(state["at"]).timestamp() if state["at"] else None
    if (
        not same_stream
        or state["sequence"] != event["sequence"] - 1
        or (gap is not None and (gap < 0 or gap > MAX_OBSERVATION_GAP))
    ):
        if state["sequence"] is not None:
            rule["tracking_note"] = (
                "Session/profile, timing or recording continuity changed; consecutive counts restarted."
            )
        state.update(failures=0, successes=0)
    state.update(
        session=event["session"], generation=event["generation"], sequence=event["sequence"], at=event["at"]
    )
    kind = event["error_kind"]
    if kind == "request":
        state.update(failures=0, successes=0)
        return None
    if kind is not None:
        state.update(successes=0, failures=min(10, state["failures"] + 1), error_kind=kind)
        if not state["incident"] and state["failures"] >= rule["failures_required"]:
            state["incident"] = True
            return "failing"
    else:
        state.update(failures=0, successes=min(5, state["successes"] + 1))
        if state["incident"] and state["successes"] >= rule["successes_required"]:
            state.update(incident=False, error_kind=None)
            return "recovered" if rule["notify_recovery"] else None
    return None

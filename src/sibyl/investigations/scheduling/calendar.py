"""Compute future wall-clock occurrences without replaying missed calendar times."""

from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo


def next_occurrence(schedule: dict, after: datetime) -> datetime:
    """Return the first valid occurrence strictly after an aware UTC instant.

    A nonexistent spring-forward wall time skips that date. An ambiguous fall-back
    wall time uses its first occurrence only. UTC round trips validate local times;
    comparisons always happen in UTC, so the repeated hour cannot run twice.
    """
    if after.tzinfo is None:
        raise ValueError("Scheduling requires an aware timestamp.")
    zone = ZoneInfo(schedule["timezone"])
    local_date = after.astimezone(zone).date()
    wall_time = time.fromisoformat(schedule["local_time"])
    for offset in range(15):
        day = local_date + timedelta(days=offset)
        if schedule["frequency"] == "weekly" and day.weekday() != schedule["weekday"]:
            continue
        local = datetime.combine(day, wall_time, zone).replace(fold=0)
        candidate = local.astimezone(UTC)
        if candidate.astimezone(zone).replace(tzinfo=None) != local.replace(tzinfo=None):
            continue
        if candidate > after.astimezone(UTC):
            return candidate
    raise ValueError("No valid calendar occurrence was found in the next two weeks.")

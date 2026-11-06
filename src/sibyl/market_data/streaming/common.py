"""Small shared validation primitives for public display protocols."""

import math
from datetime import datetime


class SubscriptionRejected(ConnectionError):
    """A public native subscription was rejected; REST remains available without reconnect churn."""


def number(value, *, positive=False):
    if isinstance(value, bool):
        raise ValueError("Invalid public stream number.")
    value = float(value)
    if not math.isfinite(value) or value < 0 or (positive and value == 0):
        raise ValueError("Invalid public stream number.")
    return value


def timestamp(value):
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("Missing stream timezone.")
    return parsed.timestamp()

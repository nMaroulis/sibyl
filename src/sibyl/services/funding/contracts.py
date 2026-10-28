"""Explicit opt-in controls and fixed budgets for retained pending funding records."""

from typing import Literal

from pydantic import Field

from sibyl.models import Request

PAGE_LIMIT = 20
TARGET_LIMIT = 1000
MISSING_LIMIT = 5
READ_GAP = 10
SCAN_PAGE_LIMIT = 200
SCAN_SOURCE_LIMIT = 10_000


def refresh_streams(connection):
    """Only sources exposing pending history are eligible; posted Kraken entries are excluded."""
    return (
        []
        if connection.sandbox
        else {"binance": ["deposit", "withdrawal"], "bybit": ["withdrawal"]}.get(connection.exchange, [])
    )


def scan_streams(connection):
    """Rolling history sync uses only implemented production native funding adapters."""
    return (
        []
        if connection.sandbox
        else {
            "binance": ["deposit", "withdrawal"],
            "kraken": ["deposit", "withdrawal", "transfer"],
            "bybit": ["withdrawal"],
        }.get(connection.exchange, [])
    )


class FundingRefreshConflict(ValueError):
    """The saved controls changed after the user loaded them."""


class RefreshFunding(Request):
    """Opt in to local status reads; no control can create a native funding transaction."""

    enabled: bool
    interval_minutes: Literal[5, 15, 60] = 5
    replace_revision: str | None = Field(default=None, pattern=r"^[a-f0-9]{32}$")
    check_now: bool = False


class ScanFunding(Request):
    """Authorize a rolling creation-time history window, separately from retained pending checks."""

    enabled: bool
    interval_minutes: Literal[15, 60, 360] = 60
    lookback_days: Literal[1, 7, 30] = 7
    replace_revision: str | None = Field(default=None, pattern=r"^[a-f0-9]{32}$")
    check_now: bool = False

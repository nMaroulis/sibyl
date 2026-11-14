"""Strict native balance and market minimum observations for position reviews."""

import math
import time
from datetime import UTC, datetime

from sibyl.strategies.execution.contracts import ExecutionGuard
from sibyl.strategies.execution.venue import is_dust, order_book


def now():
    return datetime.now(UTC).isoformat()


def amount(balance, group, asset):
    """Require an explicit finite balance; absence is unknown rather than zero."""
    value = (balance.get(group) or {}).get(asset)
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or value < 0
    ):
        raise ExecutionGuard(
            f"A finite native {group} balance for {asset} is required; missing values are unknown."
        )
    return float(value)


def observe(runner, job):
    """Fetch one bounded native balance/book observation without altering ownership."""
    connection = runner.account(job["connection_id"])
    if (connection.exchange, connection.sandbox) != (job["exchange"], job["sandbox"]):
        raise ExecutionGuard("The strategy account environment changed.")
    base = job["parameters"]["symbol"].split("/")[0]
    started = time.time()
    try:
        with runner.market.adapter(connection) as client:
            client.load_markets()
            book = order_book(client, job["parameters"]["symbol"])
            balance = client.fetch_balance()
            total, free = amount(balance, "total", base), amount(balance, "free", base)
            if free > total + max(1e-10, total * 1e-8):
                raise ExecutionGuard("Native free balance exceeds the total; review account access.")
            if time.time() - started > 30:
                raise ExecutionGuard("The position check expired during the exchange read. Try again.")
            stamp = balance.get("timestamp")
            if stamp is not None and (
                isinstance(stamp, bool)
                or not isinstance(stamp, (int, float))
                or not math.isfinite(stamp)
                or not -5000 <= time.time() * 1000 - stamp <= 30_000
            ):
                raise ExecutionGuard("The exchange balance timestamp is stale or invalid.")
            limits = client.market(job["parameters"]["symbol"]).get("limits") or {}
            dust = is_dust(client, job["parameters"]["symbol"], job["quantity"], book["bid"])
    except ExecutionGuard:
        raise
    except Exception as error:
        raise ExecutionGuard(
            "Could not read native balances, book and minimums. Check exchange access."
        ) from error
    return {
        "total": total,
        "free": free,
        "reference_bid": book["bid"],
        "dust": dust,
        "amount_min": (limits.get("amount") or {}).get("min"),
        "cost_min": (limits.get("cost") or {}).get("min"),
        "observed_at": now(),
    }

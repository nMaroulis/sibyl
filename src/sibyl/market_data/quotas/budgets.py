"""Bounded process-local quota estimates, under ProviderControl's existing condition.

Fixed minute windows retain local charges; observed Binance counters can only
raise the current minute's IP estimate. In-flight reservations are included, and
an old reply cannot overwrite a new minute. Token allowances retain debt for
bypassed preflight reads. No budget here can admit/retry an exchange mutation.
"""

import math
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from itertools import islice
from uuid import uuid4

from sibyl.market_data.quotas.policies import describe, family, specifications


def stamp(wall):
    return datetime.fromtimestamp(wall, UTC).isoformat()


def integer(value, maximum=1_000_000_000):
    if isinstance(value, bool):
        return None
    if isinstance(value, str) and not re.fullmatch(r"[0-9]{1,10}", value):
        return None
    if not isinstance(value, (int, str)):
        return None
    number = int(value)
    return number if 0 <= number <= maximum else None


@dataclass
class Bucket:
    name: str
    scope: str
    capacity: float
    period: float | None
    refill: float | None
    used: float = 0
    epoch: int = -1
    updated: float = 0
    tokens: float | None = None
    provider_limit: int | None = None
    observed_at: str | None = None
    limit_observed_at: str | None = None
    reported_used: int | None = None
    pending: dict = field(default_factory=dict)

    def refresh(self, mono, wall):
        if self.period:
            epoch = math.floor(wall / self.period)
            if epoch > self.epoch:
                self.epoch, self.used, self.reported_used, self.observed_at = epoch, 0, None, None
                self.pending.clear()
        else:
            self.tokens = (
                self.capacity
                if self.tokens is None
                else min(self.capacity, self.tokens + max(0, mono - self.updated) * self.refill)
            )
        self.updated = mono

    def delay(self, cost, mono, wall):
        self.refresh(mono, wall)
        if self.period:
            return (
                max(0, (self.epoch + 1) * self.period - wall + 1) if self.used + cost > self.capacity else 0
            )
        return max(0, (cost - self.tokens) / self.refill)

    def take(self, identity, cost, mono, wall):
        self.refresh(mono, wall)
        if self.period:
            self.used += cost
            self.pending[identity] = (self.epoch, cost)
        else:
            self.tokens -= cost

    def public(self, mono, wall):
        self.refresh(mono, wall)
        used = self.used if self.period else self.capacity - self.tokens
        return {
            "name": self.name,
            "scope": self.scope,
            "capacity": self.capacity,
            "used": round(used, 3),
            "remaining": round(max(0, self.capacity - used), 3),
            "period_seconds": self.period,
            "refill_per_second": self.refill,
            "provider_limit": self.provider_limit,
            "reported_used": self.reported_used,
            "limit_observed_at": self.limit_observed_at,
            "observed_at": self.observed_at,
            "reset_at": stamp((self.epoch + 1) * self.period + 1) if self.period else None,
            "basis": "observed_limit_and_local_estimate" if self.provider_limit else "application_allowance",
        }


class Quotas:
    """Keep safe per-session projections; callers serialize access with the transport gate."""

    def __init__(self):
        self.buckets = {}
        self.sources = {}
        self.order_limits = {}
        self.gaps = 0

    def _state(self, source, state, partition):
        key = state["generation"]
        if key not in self.sources:
            if len(self.sources) >= 1024:
                # Retired diagnostics may be dropped, but live budgets are never refunded.
                self.sources.pop(next(iter(self.sources)))
                self.gaps += 1
            self.sources[key] = {
                "partition": partition,
                "attempts": 0,
                "reviewed": 0,
                "unreviewed": 0,
                "bypassed": 0,
                "last": None,
                "orders": {},
                "generation": key,
                "blocked": None,
            }
        return self.sources[key]

    def _key(self, call, identity, scope):
        partition = call.partition if scope == "credential" else "shared"
        return call.family, call.environment, partition, identity

    def _get(self, call, identity):
        spec = specifications(call).get(identity)
        if spec is None:
            return self.buckets.get((call.family, call.environment, "shared", identity))
        name, scope, capacity, period, refill = spec
        key = self._key(call, identity, scope)
        if key not in self.buckets:
            if len(self.buckets) >= 2048:
                self.gaps += 1
                return None
            self.buckets[key] = Bucket(name, scope, capacity, period, refill)
        return self.buckets[key]

    def delay(self, call, mono, wall):
        return max(
            (
                b.delay(cost, mono, wall)
                for identity, cost in call.charges
                if (b := self._get(call, identity)) is not None
            ),
            default=0,
        )

    def charge(self, source, state, call, mono, wall, *, bypass=False):
        """Charge each actual attempt once; never refund an uncertain response or reset."""
        record = self._state(source, state, call.partition)
        record["blocked"] = None
        record["attempts"] += 1
        record["reviewed" if call.reviewed else "unreviewed"] += 1
        record["bypassed"] += bool(bypass)
        record["last"] = {
            "operation": call.label,
            "reviewed": call.reviewed,
            "at": stamp(wall),
            "read_admission": not bypass,
            "costs": [{"budget": i, "cost": c} for i, c in call.charges],
        }
        identity = uuid4().hex
        reservations = []
        for budget, cost in call.charges:
            bucket = self._get(call, budget)
            if bucket is not None:
                bucket.take(identity, cost, mono, wall)
                reservations.append(bucket)
        return {"id": identity, "call": call, "wall": wall, "record": record, "buckets": reservations}

    def observe(self, reservation, headers, result, mono, wall):
        """Read only allowlisted numeric counters and rate declarations, never raw headers/body."""
        call = reservation["call"]
        for bucket in reservation["buckets"]:
            bucket.pending.pop(reservation["id"], None)
        if call.family not in {"binance", "binanceus"}:
            return
        if call.exchange_info and isinstance(result, dict):
            limits = result.get("rateLimits")
            if isinstance(limits, list):
                for item in limits[:16]:
                    if not isinstance(item, dict):
                        continue
                    limit = integer(item.get("limit"))
                    multiple = integer(item.get("intervalNum"), 86400)
                    interval = item.get("interval")
                    unit = (
                        {"SECOND": 1, "MINUTE": 60, "HOUR": 3600, "DAY": 86400}.get(interval)
                        if isinstance(interval, str)
                        else None
                    )
                    kind = item.get("rateLimitType")
                    if not limit or not multiple or not unit:
                        continue
                    seconds = multiple * unit
                    if kind == "REQUEST_WEIGHT" and seconds == 60:
                        key = call.family, call.environment, "shared", "ip_weight"
                        budget = self.buckets.get(key)
                        if budget is None:
                            if len(self.buckets) >= 2048:
                                self.gaps += 1
                                continue
                            local = self._get(call, "local_weight")
                            budget = Bucket(
                                "Observed IP weight read ceiling",
                                "provider_environment",
                                max(1, math.floor(limit * 0.8)),
                                60,
                                None,
                            )
                            budget.refresh(mono, wall)
                            if local:
                                local.refresh(mono, wall)
                                budget.used = local.used
                                budget.pending = dict(local.pending)
                            self.buckets[key] = budget
                        budget.capacity = max(1, math.floor(limit * 0.8))
                        budget.provider_limit = limit
                        budget.limit_observed_at = stamp(wall)
                    elif kind == "ORDERS" and seconds <= 86400 and len(self.order_limits) < 128:
                        self.order_limits[(call.family, call.environment, seconds)] = limit
        if not isinstance(headers, Mapping):
            return
        # Header names/values outside this small allowlist are never copied or logged.
        safe = {
            k.lower(): v
            for k, v in islice(headers.items(), 256)
            if isinstance(k, str)
            and len(k) < 80
            and (
                k.lower() == "date"
                or re.fullmatch(r"x-mbx-(?:used-weight|order-count)-[0-9]{1,5}[smhd]", k.lower())
            )
        }
        observed_wall = reservation["wall"]
        date = safe.get("date")
        if isinstance(date, str) and len(date) <= 128:
            try:
                parsed = parsedate_to_datetime(date)
                if parsed.tzinfo is not None and abs(parsed.timestamp() - wall) <= 300:
                    observed_wall = parsed.timestamp()
            except (ValueError, TypeError, OverflowError):
                pass
        reported = integer(safe.get("x-mbx-used-weight-1m"))
        if reported is not None:
            bucket = self._get(call, "ip_weight")
            if bucket is not None:
                bucket.refresh(mono, wall)
                bucket.pending.pop(reservation["id"], None)
                if math.floor(observed_wall / 60) == bucket.epoch:
                    outstanding = sum(
                        cost for epoch, cost in bucket.pending.values() if epoch == bucket.epoch
                    )
                    bucket.used = max(bucket.used, reported + outstanding)
                    bucket.reported_used = max(bucket.reported_used or 0, reported)
                    bucket.observed_at = stamp(wall)
            else:
                reservation["record"]["unpaired_ip_weight"] = {
                    "used": reported,
                    "at": stamp(wall),
                    "provider_limit": None,
                }
        for key, value in safe.items():
            match = re.fullmatch(r"x-mbx-order-count-([0-9]{1,5})([smhd])", key)
            count = integer(value)
            if match and count is not None:
                seconds = int(match[1]) * {"s": 1, "m": 60, "h": 3600, "d": 86400}[match[2]]
                if 1 <= seconds <= 86400 and (
                    seconds in reservation["record"]["orders"] or len(reservation["record"]["orders"]) < 8
                ):
                    reservation["record"]["orders"][seconds] = {
                        "period_seconds": seconds,
                        "used": count,
                        "observed_at": stamp(wall),
                        "provider_limit": self.order_limits.get((call.family, call.environment, seconds)),
                        "enforced": False,
                    }

    def deferred(self, source, state, call, wall):
        record = self._state(source, state, call.partition)
        record["blocked"] = call
        record["last_deferral"] = {
            "at": stamp(wall),
            "operation": call.label,
            "reason": "Reviewed read allowance is exhausted; no request was sent.",
        }

    def snapshot(self, source, state, mono, wall):
        """Project local allowances and dated provider evidence without revealing private groups."""
        name = family(source["provider"])
        record = self.sources.get(state["generation"]) if state else None
        partition = record["partition"] if record else None
        buckets = []
        for (provider, environment, group, identity), bucket in self.buckets.items():
            if (provider, environment) != (name, source["environment"]):
                continue
            if bucket.scope == "credential" and (
                source["kind"] != "connection" or not record or group != partition
            ):
                continue
            if bucket.scope == "all_local_profiles" and source["kind"] != "connection":
                continue
            buckets.append({"id": identity, **bucket.public(mono, wall)})
        policy = describe(source["provider"])
        return {
            "policy": policy,
            "status": "demo" if name == "demo" else "observed" if record else "not_observed",
            "attempts": record["attempts"] if record else 0,
            "reviewed_attempts": record["reviewed"] if record else 0,
            "unreviewed_attempts": record["unreviewed"] if record else 0,
            "bypassed_attempts": record["bypassed"] if record else 0,
            "last_request": record["last"] if record else None,
            "budgets": buckets,
            "reported_order_counts": list(record["orders"].values()) if record else [],
            "unpaired_ip_weight": record.get("unpaired_ip_weight")
            if record and not any(b["id"] == "ip_weight" for b in buckets)
            else None,
            "coverage_gaps": self.gaps,
            "last_deferral": record.get("last_deferral") if record else None,
            "retry_after": math.ceil(self.delay(record["blocked"], mono, wall))
            if record and record.get("blocked")
            else 0,
            "scope": "single_process",
            "writes": "not_queued_or_retried",
        }

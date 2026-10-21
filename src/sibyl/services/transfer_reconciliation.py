"""Reviewable own-account transfer assertions over retained funding observations."""

import hashlib
import json
from collections import Counter
from datetime import UTC, datetime
from decimal import Decimal, localcontext
from uuid import uuid4

from pydantic import Field

from sibyl.models import Request
from sibyl.services.transfer_allocation import TransferAllocation, allocate
from sibyl.storage import Store

MAX_EVENTS = 1000
MAX_SUGGESTIONS = 40
WINDOW_MS = 72 * 3_600_000
CLOCK_SKEW_MS = 300_000
NOTE = (
    "Confirmed links are your own-account transfer assertions, not independent proof of settlement or ownership. "
    "Reported amounts and fees stay separate. Unlinked records are unreviewed, not automatically external cash flows. "
    "Confirmation saves a classification without moving funds. Performance can carry original lots for eligible "
    "zero-fee pairs or explicitly reviewed, balanced same-asset fee allocations. Other cases remain provisional. "
    "Fee inventory cost stays separate from trading P&L; historical fee valuation and account returns are unavailable."
)
FACT_FIELDS = (
    "id",
    "native_id",
    "reference",
    "account_id",
    "exchange",
    "environment",
    "asset",
    "kind",
    "timestamp_ms",
    "direction",
    "quantity",
    "status",
    "fee",
    "fee_known",
    "internal",
    "amount_basis",
)


class TransferConflict(ValueError):
    """The review is stale or an observation is already reserved by another link."""


class TransferPair(Request):
    """Identify observations and an optional explicit, version-checked fee allocation."""

    outgoing_id: str = Field(pattern=r"^[a-f0-9]{64}$")
    incoming_id: str = Field(pattern=r"^[a-f0-9]{64}$")
    outgoing_fingerprint: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    incoming_fingerprint: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    allocation: TransferAllocation | None = None


class TransferConfirm(TransferPair):
    """Confirm only the source versions that the user has actually reviewed."""

    outgoing_fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    incoming_fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    note: str = Field(default="", max_length=1000)


def fingerprint(event: dict) -> str:
    """Ignore display labels/observation times; changes to accounting facts invalidate a review."""
    payload = {key: event.get(key) for key in FACT_FIELDS}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, allow_nan=False).encode()).hexdigest()


def same_review(payload: str, request: TransferConfirm, allocation: dict | None) -> bool:
    """Display-label updates alone do not turn an exact repeated confirmation into a new decision."""
    saved = json.loads(payload)
    return (
        saved["outgoing"]["fingerprint"] == request.outgoing_fingerprint
        and saved["incoming"]["fingerprint"] == request.incoming_fingerprint
        and saved.get("allocation") == allocation
    )


def eligible(event: dict, direction: str) -> bool:
    """Only positive completed outgoing/incoming funding facts can form a one-to-one link."""
    kinds = {"withdrawal", "transfer"} if direction == "out" else {"deposit", "transfer"}
    return (
        event.get("direction") == direction
        and event.get("kind") in kinds
        and event.get("status") == "completed"
        and event.get("quantity", 0) > 0
    )


def comparison(outgoing: dict, incoming: dict) -> dict:
    """Compare reported native amounts without assuming how fees affect either amount."""
    issues, warnings = [], []
    if outgoing["id"] == incoming["id"] or outgoing["account_id"] == incoming["account_id"]:
        issues.append("Choose observations from two different accounts.")
    if not eligible(outgoing, "out") or not eligible(incoming, "in"):
        issues.append("Choose a positive completed withdrawal/transfer out and deposit/transfer in.")
    if outgoing["asset"] != incoming["asset"]:
        issues.append("Both observations must use the same asset; conversions are not transfer pairs.")
    if outgoing["environment"] != incoming["environment"]:
        issues.append("Demo, test and production observations cannot be linked together.")
    with localcontext() as context:
        context.prec = 50
        delta = Decimal(str(outgoing["quantity"])) - Decimal(str(incoming["quantity"]))
        equal = delta == 0
        fee = outgoing.get("fee") or {}
        fee_explanation = (
            fee.get("currency") == outgoing["asset"]
            and fee.get("cost") is not None
            and delta == Decimal(str(fee["cost"]))
            and not equal
        )
    gap = incoming["timestamp_ms"] - outgoing["timestamp_ms"]
    if not equal:
        warnings.append(
            "Reported amounts differ. The difference is not inferred to be a fee; explain it in your review note."
        )
    if fee_explanation:
        warnings.append(
            "The amount difference equals the reported outgoing fee. Fee inclusion still needs your review."
        )
    if not outgoing.get("fee_known") or not incoming.get("fee_known"):
        warnings.append("At least one observation has unavailable fee data.")
    if gap < -CLOCK_SKEW_MS or gap > WINDOW_MS:
        warnings.append(
            "Timing falls outside the 72-hour suggestion window. Explain the timing in your review note."
        )
    shared_reference = bool(
        outgoing.get("reference")
        and outgoing["reference"] == incoming.get("reference")
        and outgoing["exchange"] == incoming["exchange"]
    )
    return {
        "outgoing": {**outgoing, "fingerprint": fingerprint(outgoing)},
        "incoming": {**incoming, "fingerprint": fingerprint(incoming)},
        "valid": not issues,
        "issues": issues,
        "warnings": warnings,
        "amount_difference": float(delta),
        "asset": outgoing["asset"],
        "equal_amounts": equal,
        "difference_matches_outgoing_fee": fee_explanation,
        "time_gap_ms": gap,
        "shared_venue_reference": shared_reference,
        "note_required": not equal or gap < -CLOCK_SKEW_MS or gap > WINDOW_MS,
        "note": NOTE,
    }


def candidates(events: list[dict], reserved: set[str], account_id: str = "") -> list[dict]:
    """Rank bounded heuristic suggestions; no candidate is ever confirmed automatically."""
    outputs = [row for row in events if eligible(row, "out") and row["id"] not in reserved]
    inputs = [row for row in events if eligible(row, "in") and row["id"] not in reserved]
    matches = []
    for outgoing in outputs:
        for incoming in inputs:
            if account_id and account_id not in {outgoing["account_id"], incoming["account_id"]}:
                continue
            if (
                outgoing["account_id"] == incoming["account_id"]
                or outgoing["asset"] != incoming["asset"]
                or outgoing["environment"] != incoming["environment"]
            ):
                continue
            gap = incoming["timestamp_ms"] - outgoing["timestamp_ms"]
            if not -CLOCK_SKEW_MS <= gap <= WINDOW_MS:
                continue
            delta = Decimal(str(outgoing["quantity"])) - Decimal(str(incoming["quantity"]))
            fee = outgoing.get("fee") or {}
            fee_matches = (
                fee.get("currency") == outgoing["asset"]
                and fee.get("cost") is not None
                and delta == Decimal(str(fee["cost"]))
            )
            if (
                abs(delta)
                > max(Decimal(str(outgoing["quantity"])), Decimal(str(incoming["quantity"])))
                * Decimal("0.01")
                and not fee_matches
            ):
                continue
            shared = bool(
                outgoing.get("reference")
                and outgoing["reference"] == incoming.get("reference")
                and outgoing["exchange"] == incoming["exchange"]
            )
            score = (100 if shared else 0) + (40 if delta == 0 else 25 if fee_matches else 10)
            matches.append((score, abs(gap), outgoing, incoming))
    alternatives = Counter(row["id"] for item in matches for row in item[2:])
    result = []
    for _, _, outgoing, incoming in sorted(
        matches, key=lambda item: (-item[0], item[1], item[2]["id"], item[3]["id"])
    )[:MAX_SUGGESTIONS]:
        evidence = comparison(outgoing, incoming)
        evidence["alternatives"] = max(alternatives[outgoing["id"]], alternatives[incoming["id"]])
        evidence["reasons"] = [
            "Same asset and environment",
            "Timing within 72 hours",
            "Equal reported amounts"
            if evidence["equal_amounts"]
            else "Amount difference matches a reported fee"
            if evidence["difference_matches_outgoing_fee"]
            else "Reported amounts within 1%",
        ]
        if evidence["shared_venue_reference"]:
            evidence["reasons"].append("Shared reference at the same venue")
        result.append(evidence)
    return result


def read_event(db, identity: str) -> dict | None:
    """Read one retained source observation inside the caller's snapshot/transaction."""
    row = db.execute("SELECT payload FROM funding_events WHERE id=?", (identity,)).fetchone()
    return json.loads(row[0]) if row else None


def link_view(db, record: dict) -> dict:
    """Recheck source facts on every read; corrections never silently preserve confirmation."""
    saved = json.loads(record["payload"])
    outgoing, incoming = read_event(db, record["outgoing_id"]), read_event(db, record["incoming_id"])
    changed = [
        name
        for name, current in (("outgoing", outgoing), ("incoming", incoming))
        if current is None or fingerprint(current) != saved[name]["fingerprint"]
    ]
    status = "removed" if record["state"] == "removed" else "needs_review" if changed else "confirmed"
    return {
        "id": record["id"],
        "status": status,
        "created_at": record["created_at"],
        "updated_at": record["updated_at"],
        "review_note": record["review_note"],
        "reviewed": saved,
        "current": comparison(outgoing, incoming) if outgoing and incoming else None,
        "changed_sides": changed,
        "cost_basis_applied": False,
        "allocation": saved.get("allocation"),
    }


def memberships(db, identities: list[str]) -> dict[str, dict]:
    """Decorate a bounded funding page without changing the reported amounts or summaries."""
    if (
        not identities
        or not db.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='transfer_links'"
        ).fetchone()
    ):
        return {}
    rows = db.execute(
        "SELECT DISTINCT l.* FROM transfer_links l JOIN transfer_members m ON m.link_id=l.id WHERE m.event_id IN ("
        + ",".join("?" for _ in identities)
        + ")",
        identities,
    ).fetchall()
    result = {}
    for row in rows:
        link = link_view(db, dict(row))
        for side, other in (("outgoing", "incoming"), ("incoming", "outgoing")):
            event = link["reviewed"][side]
            if event["id"] in identities:
                result[event["id"]] = {
                    "link_id": link["id"],
                    "status": link["status"],
                    "counterpart_account": link["reviewed"][other]["account"],
                }
    return result


class TransferReconciliation:
    """Persist reversible, audited user assertions; never mutate funding facts or wallet balances."""

    def __init__(self, store: Store):
        self.store = store
        with store.db() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS transfer_links (
                    id TEXT PRIMARY KEY, outgoing_id TEXT NOT NULL, incoming_id TEXT NOT NULL,
                    state TEXT NOT NULL, payload TEXT NOT NULL, review_note TEXT NOT NULL,
                    created_at TEXT NOT NULL, updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS transfer_members (
                    event_id TEXT PRIMARY KEY, link_id TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS transfer_members_link ON transfer_members(link_id);
                CREATE TABLE IF NOT EXISTS transfer_audit (
                    id INTEGER PRIMARY KEY, link_id TEXT NOT NULL, action TEXT NOT NULL,
                    created_at TEXT NOT NULL, payload TEXT NOT NULL
                );
            """)

    def preview(self, request: TransferPair) -> dict:
        """Prepare an exact source-version review without persisting a link."""
        with self.store.db() as db:
            db.execute("BEGIN")
            outgoing, incoming = self._pair(db, request)
            result = comparison(outgoing, incoming)
            self._allocation_preview(result, request)
            result["memberships"] = memberships(db, [request.outgoing_id, request.incoming_id])
        return result

    @staticmethod
    def _allocation_preview(result: dict, request: TransferPair) -> None:
        """Validate allocation against the exact displayed versions before presenting it."""
        if request.allocation is None:
            return
        if any(
            result[side]["fingerprint"] != getattr(request, f"{side}_fingerprint")
            for side in ("outgoing", "incoming")
        ):
            raise TransferConflict("Source observations changed. Refresh and review both records again.")
        if not result["valid"]:
            raise ValueError(" ".join(result["issues"]))
        result["allocation"] = allocate(result["outgoing"], result["incoming"], request.allocation)

    @staticmethod
    def example_preview(request: TransferPair) -> dict:
        """Review only the isolated fixture; no saved accounts or source records are read."""
        example = TransferReconciliation.example()
        pairs = [*example["candidates"], *(item["reviewed"] for item in example["items"])]
        events = {event["id"]: event for pair in pairs for event in (pair["outgoing"], pair["incoming"])}
        if request.outgoing_id not in events or request.incoming_id not in events:
            raise LookupError("Example observation not found.")
        result = comparison(events[request.outgoing_id], events[request.incoming_id])
        TransferReconciliation._allocation_preview(result, request)
        return result

    @staticmethod
    def _pair(db, request: TransferPair) -> tuple[dict, dict]:
        outgoing, incoming = read_event(db, request.outgoing_id), read_event(db, request.incoming_id)
        if outgoing is None or incoming is None:
            raise LookupError("Funding observation not found.")
        return outgoing, incoming

    def confirm(self, request: TransferConfirm, link_id: str = "") -> dict:
        """Atomically check both reviewed versions and reserve each observation once.

        Reconfirmation accepts updated evidence for an existing pair; restoration
        of a removed link uses the same checks and cannot steal another link's
        observations. Exact repeated confirmation is idempotent, without a second
        audit entry. Non-equal amounts or unusual timing require a review note.
        """
        with self.store.db() as db:
            db.execute("BEGIN IMMEDIATE")
            outgoing, incoming = self._pair(db, request)
            evidence = comparison(outgoing, incoming)
            if not evidence["valid"]:
                raise ValueError(" ".join(evidence["issues"]))
            if (
                evidence["outgoing"]["fingerprint"] != request.outgoing_fingerprint
                or evidence["incoming"]["fingerprint"] != request.incoming_fingerprint
            ):
                raise TransferConflict("Source observations changed. Refresh and review both records again.")
            note = request.note.strip()
            allocation = allocate(outgoing, incoming, request.allocation) if request.allocation else None
            if allocation:
                evidence["allocation"] = allocation
            if (evidence["note_required"] or allocation) and len(note) < 8:
                raise ValueError(
                    "Explain the amount difference, timing or fee allocation in a review note (at least 8 characters)."
                )
            previous = (
                db.execute("SELECT * FROM transfer_links WHERE id=?", (link_id,)).fetchone()
                if link_id
                else None
            )
            if link_id and previous is None:
                raise LookupError("Transfer link not found.")
            if previous and (previous["outgoing_id"], previous["incoming_id"]) != (
                request.outgoing_id,
                request.incoming_id,
            ):
                raise ValueError(
                    "A review must keep the original pair. Remove the link before choosing different records."
                )
            reserved = db.execute(
                "SELECT event_id,link_id FROM transfer_members WHERE event_id IN (?,?)",
                (request.outgoing_id, request.incoming_id),
            ).fetchall()
            if not link_id and reserved:
                ids = {row["link_id"] for row in reserved}
                if len(ids) == 1:
                    old = db.execute("SELECT * FROM transfer_links WHERE id=?", (next(iter(ids)),)).fetchone()
                    if (
                        old
                        and old["outgoing_id"] == request.outgoing_id
                        and old["incoming_id"] == request.incoming_id
                        and same_review(old["payload"], request, allocation)
                        and old["review_note"] == note
                    ):
                        return link_view(db, dict(old))
                raise TransferConflict(
                    "At least one observation is already linked. Open its saved link to review or remove it."
                )
            if any(row["link_id"] != link_id for row in reserved):
                raise TransferConflict(
                    "At least one observation belongs to another link. Remove that link before reusing it."
                )
            identity = link_id or uuid4().hex
            now = datetime.now(UTC).isoformat()
            payload = json.dumps(evidence, sort_keys=True, allow_nan=False)
            action = (
                "restore"
                if previous and previous["state"] == "removed"
                else "reconfirm"
                if previous
                else "confirm"
            )
            if (
                previous
                and previous["state"] == "confirmed"
                and same_review(previous["payload"], request, allocation)
                and previous["review_note"] == note
            ):
                return link_view(db, dict(previous))
            db.execute(
                "INSERT INTO transfer_links VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET state=excluded.state,payload=excluded.payload,review_note=excluded.review_note,updated_at=excluded.updated_at",
                (
                    identity,
                    request.outgoing_id,
                    request.incoming_id,
                    "confirmed",
                    payload,
                    note,
                    previous["created_at"] if previous else now,
                    now,
                ),
            )
            for event_id in (request.outgoing_id, request.incoming_id):
                db.execute(
                    "INSERT INTO transfer_members VALUES(?,?) ON CONFLICT(event_id) DO UPDATE SET link_id=excluded.link_id",
                    (event_id, identity),
                )
            self._audit(
                db,
                identity,
                action,
                dict(previous) if previous else None,
                {"reviewed": evidence, "review_note": note},
                now,
            )
            return link_view(
                db, dict(db.execute("SELECT * FROM transfer_links WHERE id=?", (identity,)).fetchone())
            )

    @staticmethod
    def _audit(db, identity: str, action: str, before, after, now: str) -> None:
        db.execute(
            "INSERT INTO transfer_audit(link_id,action,created_at,payload) VALUES(?,?,?,?)",
            (
                identity,
                action,
                now,
                json.dumps({"before": before, "after": after}, sort_keys=True, allow_nan=False),
            ),
        )

    def remove(self, identity: str) -> None:
        """Soft-remove an assertion and release reservations; source facts and audit remain recoverable."""
        with self.store.db() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM transfer_links WHERE id=?", (identity,)).fetchone()
            if row is None:
                raise LookupError("Transfer link not found.")
            if row["state"] == "removed":
                return
            now = datetime.now(UTC).isoformat()
            db.execute("UPDATE transfer_links SET state='removed',updated_at=? WHERE id=?", (now, identity))
            db.execute("DELETE FROM transfer_members WHERE link_id=?", (identity,))
            self._audit(db, identity, "remove", dict(row), None, now)

    def detail(self, identity: str) -> dict:
        """Read current/saved evidence and the latest fifty explicit review actions."""
        with self.store.db() as db:
            db.execute("BEGIN")
            row = db.execute("SELECT * FROM transfer_links WHERE id=?", (identity,)).fetchone()
            if row is None:
                raise LookupError("Transfer link not found.")
            result = link_view(db, dict(row))
            audit = db.execute(
                "SELECT action,created_at,payload FROM transfer_audit WHERE link_id=? ORDER BY id DESC LIMIT 50",
                (identity,),
            ).fetchall()
            return {
                **result,
                "audit": [{"action": row[0], "created_at": row[1], **json.loads(row[2])} for row in audit],
                "audit_limit": 50,
                "note": NOTE,
            }

    def events(
        self,
        direction: str,
        account_id: str = "",
        asset: str = "",
        environment: str = "",
        q: str = "",
        limit: int = 25,
        offset: int = 0,
    ) -> dict:
        """Search eligible retained records, including old ranges and disconnected accounts."""
        clauses = [
            "status='completed'",
            "json_extract(payload,'$.direction')=?",
            "json_extract(payload,'$.quantity')>0",
            "stream IN (?,?)",
        ]
        values = [direction, "withdrawal" if direction == "out" else "deposit", "transfer"]
        for column, value in (
            ("account_id", account_id),
            ("asset", asset),
            ("json_extract(payload,'$.environment')", environment),
        ):
            if value:
                clauses.append(f"{column}=?")
                values.append(value)
        if q:
            clauses.append(
                "(id LIKE ? ESCAPE '\\' OR native_id LIKE ? ESCAPE '\\' OR asset LIKE ? ESCAPE '\\' OR json_extract(payload,'$.account') LIKE ? ESCAPE '\\' OR json_extract(payload,'$.reference') LIKE ? ESCAPE '\\')"
            )
            term = "%" + q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
            values.extend([term] * 5)
        where = " AND ".join(clauses)
        with self.store.db() as db:
            db.execute("BEGIN")
            total = db.execute(f"SELECT COUNT(*) FROM funding_events WHERE {where}", values).fetchone()[0]
            rows = [
                json.loads(row[0])
                for row in db.execute(
                    f"SELECT payload FROM funding_events WHERE {where} ORDER BY timestamp_ms DESC,id DESC LIMIT ? OFFSET ?",
                    [*values, limit, offset],
                )
            ]
            membership = memberships(db, [row["id"] for row in rows])
        return {
            "items": [
                {**row, "fingerprint": fingerprint(row), "reconciliation": membership.get(row["id"])}
                for row in rows
            ],
            "total": total,
            "has_more": offset + len(rows) < total,
            "offset": offset,
            "limit": limit,
        }

    def report(
        self,
        account_id: str = "",
        asset: str = "",
        environment: str = "",
        include_removed: bool = False,
        limit: int = 50,
        offset: int = 0,
    ) -> dict:
        """Read saved links and a bounded heuristic scan in one local database snapshot."""
        clauses, values = [], []
        if not include_removed:
            clauses.append("state='confirmed'")
        for field, value in (("account_id", account_id), ("asset", asset), ("environment", environment)):
            if value:
                clauses.append(
                    f"(json_extract(payload,'$.outgoing.{field}')=? OR json_extract(payload,'$.incoming.{field}')=?)"
                )
                values.extend([value, value])
        where = " AND ".join(clauses) or "1=1"
        with self.store.db() as db:
            db.execute("BEGIN")
            total = db.execute(f"SELECT COUNT(*) FROM transfer_links WHERE {where}", values).fetchone()[0]
            links = [
                link_view(db, dict(row))
                for row in db.execute(
                    f"SELECT * FROM transfer_links WHERE {where} ORDER BY updated_at DESC,id LIMIT ? OFFSET ?",
                    [*values, limit, offset],
                )
            ]
            eligible_clauses, eligible_values = (
                [
                    "status='completed'",
                    "json_extract(payload,'$.quantity')>0",
                    "((stream IN ('withdrawal','transfer') AND json_extract(payload,'$.direction')='out') OR (stream IN ('deposit','transfer') AND json_extract(payload,'$.direction')='in'))",
                ],
                [],
            )
            for column, value in (("asset", asset), ("json_extract(payload,'$.environment')", environment)):
                if value:
                    eligible_clauses.append(f"{column}=?")
                    eligible_values.append(value)
            eligible_where = " AND ".join(eligible_clauses)
            eligible_count = db.execute(
                f"SELECT COUNT(*) FROM funding_events WHERE {eligible_where}", eligible_values
            ).fetchone()[0]
            events = [
                json.loads(row[0])
                for row in db.execute(
                    f"SELECT payload FROM funding_events WHERE {eligible_where} ORDER BY timestamp_ms DESC,id LIMIT ?",
                    [*eligible_values, MAX_EVENTS],
                )
            ]
            reserved = set()
            for start in range(0, len(events), 500):
                identities = [row["id"] for row in events[start : start + 500]]
                reserved.update(
                    row[0]
                    for row in db.execute(
                        "SELECT event_id FROM transfer_members WHERE event_id IN ("
                        + ",".join("?" for _ in identities)
                        + ")",
                        identities,
                    )
                )
            suggestions = candidates(events, reserved, account_id)
        return {
            "items": links,
            "total": total,
            "offset": offset,
            "limit": limit,
            "has_more": offset + len(links) < total,
            "candidates": suggestions,
            "scanned_events": len(events),
            "eligible_events": eligible_count,
            "scan_limited": eligible_count > MAX_EVENTS,
            "event_limit": MAX_EVENTS,
            "candidate_limit": MAX_SUGGESTIONS,
            "scope": "Account filter matches either side of a pair. Suggestions scan the latest eligible records for the selected asset/environment across all accounts.",
            "note": NOTE,
        }

    @staticmethod
    def example() -> dict:
        """Compute ambiguous candidates and a saved-link example without persistent fixtures."""
        from sibyl.services.funding_ledger import funding_event

        observations = []
        for index, (account, venue, kind, direction, asset, quantity, fee, minutes) in enumerate(
            [
                ("north", "binance", "withdrawal", "out", "BTC", 0.05, 0.0001, 0),
                ("daily", "kraken", "deposit", "in", "BTC", 0.0499, None, 30),
                ("reserve", "binance", "deposit", "in", "BTC", 0.0499, None, 55),
                ("north", "binance", "withdrawal", "out", "ETH", 0.4, 0, 120),
                ("daily", "kraken", "deposit", "in", "ETH", 0.4, 0, 150),
                ("north", "binance", "withdrawal", "out", "USDT", 1000, 0, -1440),
                ("daily", "kraken", "deposit", "in", "USDT", 1000, None, -1410),
            ]
        ):
            observations.append(
                funding_event(
                    {
                        "native_id": f"transfer-example-{index}",
                        "reference": None,
                        "asset": asset,
                        "timestamp_ms": 1_704_153_600_000 + minutes * 60_000,
                        "kind": kind,
                        "direction": direction,
                        "quantity": quantity,
                        "fee": {"currency": asset if fee is not None else None, "cost": fee},
                        "status": "completed",
                        "internal": False,
                        "amount_basis": "provider_reported",
                    },
                    {
                        "account_id": account,
                        "account": {
                            "north": "North wallet",
                            "daily": "Daily wallet",
                            "reserve": "Reserve wallet",
                        }[account],
                        "exchange": venue,
                        "environment": "demo",
                        "stream": kind,
                        "start_ms": 1,
                        "end_ms": 1_800_000_000_000,
                    },
                )
            )
        saved = comparison(observations[-2], observations[-1])
        return {
            "example": True,
            "items": [
                {
                    "id": "example-link",
                    "status": "confirmed",
                    "created_at": "2024-01-01T00:00:00Z",
                    "updated_at": "2024-01-01T00:00:00Z",
                    "review_note": "Example user-confirmed transfer between own wallets.",
                    "reviewed": saved,
                    "current": saved,
                    "changed_sides": [],
                    "cost_basis_applied": False,
                }
            ],
            "total": 1,
            "offset": 0,
            "limit": 50,
            "has_more": False,
            "candidates": candidates(observations[:-2], set()),
            "scanned_events": len(observations),
            "eligible_events": len(observations),
            "scan_limited": False,
            "event_limit": MAX_EVENTS,
            "candidate_limit": MAX_SUGGESTIONS,
            "scope": "Isolated example. No source records or links are persisted.",
            "note": NOTE,
        }

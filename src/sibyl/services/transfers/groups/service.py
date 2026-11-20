"""Atomic, audited transfer groups sharing the pair membership reservation.

Provider observations are never edited. Corrections invalidate the whole group;
a stale group reserves its members until an explicit re-review or removal.
"""

import json
from datetime import UTC, datetime
from uuid import uuid4

from sibyl.accounting.funding.reviews import FundingReviews
from sibyl.services.transfers.groups.contracts import GroupPreview
from sibyl.services.transfers.groups.planning import plan, source_version
from sibyl.services.transfers.reconciliation import TransferConflict, read_event


def group_events(db, request):
    """Load all member facts and latest separate balance decisions in one snapshot."""
    rows = [read_event(db, leg.event_id) for leg in [*request.outgoing, *request.incoming]]
    if any(row is None for row in rows):
        raise LookupError("Funding observation not found.")
    return {row["id"]: row for row in FundingReviews.enrich(db, rows)}


def group_view(db, record):
    """Expose saved evidence and current source validity without applying cost basis."""
    saved = json.loads(record["payload"])
    request = GroupPreview.model_validate(saved["request"])
    changed, current, error = [], None, None
    for leg in [*request.outgoing, *request.incoming]:
        event = read_event(db, leg.event_id)
        current_event = FundingReviews.enrich(db, [event])[0] if event else None
        if current_event is None or source_version(current_event) != leg.source_version:
            changed.append(leg.event_id)
    if not changed:
        try:
            current = plan(request, group_events(db, request))
        except (ValueError, LookupError) as exc:
            error = str(exc)
    status = (
        "removed" if record["state"] == "removed" else "needs_review" if changed or error else "confirmed"
    )
    return {
        "id": record["id"],
        "revision": record["revision"],
        "status": status,
        "created_at": record["created_at"],
        "updated_at": record["updated_at"],
        "review_note": record["review_note"],
        "reviewed": saved["plan"],
        "request": saved["request"],
        "changed_members": changed,
        "current": current,
        "reason": error,
        "cost_basis_applied": False,
    }


class TransferGroups:
    """Review bounded inventory allocations without moving funds or claiming account returns."""

    def __init__(self, store):
        self.store = store
        FundingReviews(store)
        with store.db() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS transfer_groups (
                    id TEXT PRIMARY KEY, state TEXT NOT NULL, revision INTEGER NOT NULL,
                    payload TEXT NOT NULL, review_note TEXT NOT NULL,
                    created_at TEXT NOT NULL, updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS transfer_group_audit (
                    id INTEGER PRIMARY KEY, group_id TEXT NOT NULL, created_at TEXT NOT NULL,
                    action TEXT NOT NULL, payload TEXT NOT NULL
                );
            """)

    def preview(self, request):
        """Show the exact conservation plan and current reservations, without writing."""
        with self.store.db() as db:
            db.execute("BEGIN")
            result = plan(request, group_events(db, request))
            ids = [leg.event_id for leg in [*request.outgoing, *request.incoming]]
            result["reservations"] = [
                dict(row)
                for row in db.execute(
                    "SELECT event_id,link_id FROM transfer_members WHERE event_id IN ("
                    + ",".join("?" for _ in ids)
                    + ")",
                    ids,
                )
            ]
            return result

    def confirm(self, request, identity=""):
        """Compare source/review versions and atomically reserve members against pairs/groups."""
        with self.store.db() as db:
            db.execute("BEGIN IMMEDIATE")
            preview_request = GroupPreview.model_validate(
                request.model_dump(include=set(GroupPreview.model_fields))
            )
            result = plan(preview_request, group_events(db, preview_request))
            if result["review_fingerprint"] != request.review_fingerprint:
                raise TransferConflict(
                    "The group preview changed. Preview and review it again before confirming."
                )
            ids = [leg.event_id for leg in [*request.outgoing, *request.incoming]]
            previous = (
                db.execute("SELECT * FROM transfer_groups WHERE id=?", (identity,)).fetchone()
                if identity
                else None
            )
            if identity and previous is None:
                raise LookupError("Transfer group not found.")
            reserved = db.execute(
                "SELECT event_id,link_id FROM transfer_members WHERE event_id IN ("
                + ",".join("?" for _ in ids)
                + ")",
                ids,
            ).fetchall()
            # An exact retried submission is safe even if the client missed its receipt.
            owners = {row["link_id"] for row in reserved}
            if not identity and len(owners) == 1:
                candidate = db.execute(
                    "SELECT * FROM transfer_groups WHERE id=?", (next(iter(owners)),)
                ).fetchone()
                if candidate and self._same(candidate, result, request.note.strip()):
                    return group_view(db, candidate)
            if any(row["link_id"] != identity for row in reserved):
                raise TransferConflict(
                    "A funding record already belongs to another pair or group. Review or remove that reservation first."
                )
            if previous:
                before = json.loads(previous["payload"])["request"]
                if any(
                    {leg["event_id"] for leg in before[side]}
                    != {leg.event_id for leg in getattr(request, side)}
                    for side in ("outgoing", "incoming")
                ):
                    raise ValueError(
                        "A re-review must keep the original members; remove the group to choose different records."
                    )
                if previous["state"] == "confirmed" and self._same(previous, result, request.note.strip()):
                    return group_view(db, previous)
                if previous["revision"] != request.revision:
                    raise TransferConflict("The group revision changed. Reload before reviewing it.")
            elif request.revision != 0:
                raise TransferConflict("A new group must start at revision zero.")
            identity = identity or uuid4().hex
            stamp = datetime.now(UTC).isoformat()
            payload = json.dumps(
                {
                    "request": preview_request.model_dump(mode="json"),
                    "plan": result,
                    "assertions": {"own_accounts_confirmed": True, "configured_wallets_confirmed": True},
                },
                sort_keys=True,
                allow_nan=False,
            )
            revision = previous["revision"] + 1 if previous else 1
            action = (
                "restore"
                if previous and previous["state"] == "removed"
                else "review"
                if previous
                else "confirm"
            )
            db.execute(
                "INSERT INTO transfer_groups VALUES(?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET state=excluded.state,revision=excluded.revision,payload=excluded.payload,review_note=excluded.review_note,updated_at=excluded.updated_at",
                (
                    identity,
                    "confirmed",
                    revision,
                    payload,
                    request.note.strip(),
                    previous["created_at"] if previous else stamp,
                    stamp,
                ),
            )
            for event_id in ids:
                db.execute(
                    "INSERT INTO transfer_members VALUES(?,?) ON CONFLICT(event_id) DO UPDATE SET link_id=excluded.link_id",
                    (event_id, identity),
                )
            after = dict(db.execute("SELECT * FROM transfer_groups WHERE id=?", (identity,)).fetchone())
            self._audit(db, identity, stamp, action, dict(previous) if previous else None, after)
            return group_view(db, after)

    @staticmethod
    def _same(record, result, note):
        saved = json.loads(record["payload"])
        return (
            saved["plan"]["review_fingerprint"] == result["review_fingerprint"]
            and record["review_note"] == note
        )

    @staticmethod
    def _audit(db, identity, stamp, action, before, after):
        db.execute(
            "INSERT INTO transfer_group_audit(group_id,created_at,action,payload) VALUES(?,?,?,?)",
            (identity, stamp, action, json.dumps({"before": before, "after": after}, sort_keys=True)),
        )

    def remove(self, identity, revision):
        """Withdraw one exact revision, release every member and keep its audit."""
        with self.store.db() as db:
            db.execute("BEGIN IMMEDIATE")
            before = db.execute("SELECT * FROM transfer_groups WHERE id=?", (identity,)).fetchone()
            if before is None:
                raise LookupError("Transfer group not found.")
            if before["revision"] != revision:
                raise TransferConflict("Group changed. Reload its revision before removing it.")
            if before["state"] == "removed":
                return {"removed": True}
            stamp = datetime.now(UTC).isoformat()
            db.execute(
                "UPDATE transfer_groups SET state='removed',revision=revision+1,updated_at=? WHERE id=?",
                (stamp, identity),
            )
            db.execute("DELETE FROM transfer_members WHERE link_id=?", (identity,))
            after = dict(db.execute("SELECT * FROM transfer_groups WHERE id=?", (identity,)).fetchone())
            self._audit(db, identity, stamp, "remove", dict(before), after)
        return {"removed": True}

    def detail(self, identity):
        """Read saved/current evidence and up to fifty immutable review actions."""
        with self.store.db() as db:
            db.execute("BEGIN")
            row = db.execute("SELECT * FROM transfer_groups WHERE id=?", (identity,)).fetchone()
            if row is None:
                raise LookupError("Transfer group not found.")
            result = group_view(db, row)
            request = GroupPreview.model_validate(result["request"])
            members = [read_event(db, leg.event_id) for leg in [*request.outgoing, *request.incoming]]
            current_members = FundingReviews.enrich(db, [event for event in members if event is not None])
            result["current_members"] = [
                {**event, "group_fingerprint": source_version(event)} for event in current_members
            ]
            result["audit"] = [
                {"action": row["action"], "created_at": row["created_at"], **json.loads(row["payload"])}
                for row in db.execute(
                    "SELECT * FROM transfer_group_audit WHERE group_id=? ORDER BY id DESC LIMIT 50",
                    (identity,),
                )
            ]
            result["audit_limit"] = 50
            return result

    def report(self, account_id="", asset="", environment="", include_removed=False, limit=20, offset=0):
        """Page group reviews; account filters match any member, never just one side."""
        clauses, args = [], []
        if not include_removed:
            clauses.append("state!='removed'")
        for field, value in (("asset", asset), ("environment", environment)):
            if value:
                clauses.append("json_extract(payload,'$.plan." + field + "')=?")
                args.append(value)
        if account_id:
            clauses.append(
                "EXISTS(SELECT 1 FROM json_each(json_extract(payload,'$.plan.outgoing')) o WHERE json_extract(o.value,'$.event.account_id')=?) OR EXISTS(SELECT 1 FROM json_each(json_extract(payload,'$.plan.incoming')) i WHERE json_extract(i.value,'$.event.account_id')=?)"
            )
            clauses[-1] = "(" + clauses[-1] + ")"
            args.extend([account_id, account_id])
        where = " AND ".join(clauses) or "1=1"
        with self.store.db() as db:
            db.execute("BEGIN")
            total = db.execute("SELECT COUNT(*) FROM transfer_groups WHERE " + where, args).fetchone()[0]
            items = [
                group_view(db, row)
                for row in db.execute(
                    "SELECT * FROM transfer_groups WHERE "
                    + where
                    + " ORDER BY updated_at DESC,id LIMIT ? OFFSET ?",
                    [*args, limit, offset],
                )
            ]
        return {
            "items": items,
            "total": total,
            "has_more": offset + len(items) < total,
            "limit": limit,
            "offset": offset,
        }

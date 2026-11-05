"""Measured account returns with explicit opening/closing snapshots and review evidence.

No legacy chart point is promoted to an accounting boundary. Historical flow
values and completeness are user assertions, separated from provider facts.
Revisions and source fingerprints invalidate stale reviews and results.
"""

import hashlib
import json
import threading
import time
from datetime import UTC, datetime
from uuid import uuid4

from sibyl.accounting.funding.reviews import FundingReviews
from sibyl.accounting.funding.rules import fingerprint
from sibyl.alerts.risk.observations import RiskObservations
from sibyl.market_data.archive import milliseconds
from sibyl.services.accounts.service import Accounts
from sibyl.services.portfolio.returns.calculation import dietz
from sibyl.services.transfers.reconciliation import link_view


def digest(value):
    return hashlib.sha256(
        json.dumps(
            value,
            sort_keys=True,
            allow_nan=False,
            default=lambda item: item.hex() if isinstance(item, bytes) else str(item),
        ).encode()
    ).hexdigest()


def stamp():
    return datetime.now(UTC).isoformat()


class ReturnPeriods:
    """Retain up to 100 periods over fixed account sets and one USDT reference source."""

    def __init__(self, market, store):
        self.market, self.store = market, store
        self.observations = RiskObservations(market, store)
        self.lock = threading.Lock()
        with store.db() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS return_periods (id TEXT PRIMARY KEY, payload TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS return_audit (id INTEGER PRIMARY KEY, period_id TEXT NOT NULL, created_at TEXT NOT NULL, payload TEXT NOT NULL);
            """)

    @staticmethod
    def read(db, identity):
        row = db.execute("SELECT payload FROM return_periods WHERE id=?", (identity,)).fetchone()
        if not row:
            raise LookupError("Performance period not found.")
        return json.loads(row[0])

    @staticmethod
    def revision(row, expected):
        if row["revision"] != expected:
            raise ValueError("This performance period changed. Refresh before saving.")

    @staticmethod
    def write(db, row, action, details):
        row.update(revision=row["revision"] + 1, updated_at=stamp())
        db.execute(
            "UPDATE return_periods SET payload=? WHERE id=?", (json.dumps(row, allow_nan=False), row["id"])
        )
        db.execute(
            "INSERT INTO return_audit(period_id,created_at,payload) VALUES(?,?,?)",
            (
                row["id"],
                stamp(),
                json.dumps(dict(action=action, revision=row["revision"], details=details), allow_nan=False),
            ),
        )

    def capture(self, ids, source):
        if not 1 <= len(ids) <= 10:
            raise ValueError("Measure one to ten active accounts per period.")
        started = time.monotonic()
        _, guard = self.observations.configuration(ids, source)
        samples = {}
        for identity in ids:
            sample, _ = self.observations.read(dict(account_ids=[identity], source=source))
            samples[identity] = sample
            if time.monotonic() - started > 45:
                raise ValueError("The account set took over 45 seconds to value. Measure fewer accounts.")
        return samples, guard

    def start(self, body):
        if not self.lock.acquire(blocking=False):
            raise ValueError("A performance valuation is already running.")
        try:
            ids = sorted(row.id for row in Accounts(self.store).resolve(body.scope))
            with self.market.snapshot():
                source = self.market.metadata()["source"]
            samples, guard = self.capture(ids, source)
            row = dict(
                id=uuid4().hex,
                label=body.label,
                scope=body.scope,
                account_ids=ids,
                source=source,
                currency="USDT",
                environment=next(iter(samples.values()))["environment"],
                opening=samples,
                closing=None,
                configuration_fingerprint=digest(guard),
                revision=1,
                created_at=stamp(),
                updated_at=stamp(),
                reviews={},
                manual_flows={},
                coverage=None,
            )
            with self.store.db() as db:
                db.execute("BEGIN IMMEDIATE")
                if db.execute("SELECT COUNT(*) FROM return_periods").fetchone()[0] >= 100:
                    raise ValueError("The workspace budget is 100 performance periods.")
                self.observations.current(dict(account_ids=ids, source=source), guard, db)
                for sample in samples.values():
                    self.observations.fresh(sample)
                db.execute(
                    "INSERT INTO return_periods VALUES(?,?)", (row["id"], json.dumps(row, allow_nan=False))
                )
                db.execute(
                    "INSERT INTO return_audit(period_id,created_at,payload) VALUES(?,?,?)",
                    (row["id"], stamp(), json.dumps(dict(action="start", revision=1))),
                )
            return self.detail(row["id"])
        finally:
            self.lock.release()

    def close(self, identity, body):
        if not self.lock.acquire(blocking=False):
            raise ValueError("A performance valuation is already running.")
        try:
            with self.store.db() as db:
                row = self.read(db, identity)
                self.revision(row, body.revision)
                if row["closing"]:
                    raise ValueError(
                        "This period already has a frozen closing valuation. Start another period for later performance."
                    )
            samples, guard = self.capture(row["account_ids"], row["source"])
            if digest(guard) != row["configuration_fingerprint"]:
                raise ValueError(
                    "Account or feed configuration changed since the opening observation. Start a new period with the current configuration."
                )
            with self.store.db() as db:
                db.execute("BEGIN IMMEDIATE")
                current = self.read(db, identity)
                self.revision(current, body.revision)
                self.observations.current(row, guard, db)
                for sample in samples.values():
                    self.observations.fresh(sample)
                if min(milliseconds(s["started_at"]) for s in samples.values()) <= max(
                    milliseconds(s["as_of"]) for s in row["opening"].values()
                ):
                    raise ValueError("Wait for a distinct closing observation after the opening valuation.")
                current["closing"] = samples
                self.write(db, current, "close", samples)
            return self.detail(identity)
        finally:
            self.lock.release()

    def evidence(self, db, row):
        start = min(milliseconds(s["started_at"]) for s in row["opening"].values())
        end = max(milliseconds(s["as_of"]) for s in (row["closing"] or row["opening"]).values())
        ids = row["account_ids"]
        raw = db.execute(
            f"SELECT payload FROM funding_events WHERE account_id IN ({','.join('?' for _ in ids)}) AND (timestamp_ms>=? OR json_extract(payload,'$.posted_ms')>=?) AND timestamp_ms<=? ORDER BY timestamp_ms,id LIMIT 2001",
            (*ids, start, start, end),
        ).fetchall()
        if len(raw) > 2000:
            raise ValueError(
                "This period exceeds 2,000 funding observations. Use shorter measurement periods."
            )
        events = FundingReviews.enrich(db, [json.loads(item[0]) for item in raw])
        events.extend(row.get("manual_flows", {}).values())
        links = {}
        for event in events:
            link = db.execute(
                "SELECT l.* FROM transfer_links l JOIN transfer_members m ON m.link_id=l.id WHERE m.event_id=?",
                (event["id"],),
            ).fetchone()
            if link:
                links[event["id"]] = link_view(db, dict(link))
        version = digest(
            dict(
                events=[dict(id=e["id"], source=fingerprint(e), effect=e["balance_effect"]) for e in events],
                links=links,
                reviews=row["reviews"],
                closing=row["closing"],
            )
        )
        return events, links, version

    def review(self, identity, event_id, body):
        with self.store.db() as db:
            db.execute("BEGIN IMMEDIATE")
            row = self.read(db, identity)
            self.revision(row, body.revision)
            if not row["closing"]:
                raise ValueError("Close the measurement period before reviewing cash flows.")
            events, links, _ = self.evidence(db, row)
            event = next((e for e in events if e["id"] == event_id), None)
            if not event or fingerprint(event) != body.source_version:
                raise ValueError(
                    "The funding observation changed or is outside this period. Review it again."
                )
            if body.classification in {"external", "own_transfer"} and body.value <= 0:
                raise ValueError("Enter a positive historical principal value in USDT, excluding fees.")
            if body.classification != "outside" and event["balance_effect"]["wallet_scope"] != "configured":
                raise ValueError("Review the movement's configured-wallet scope in Account history first.")
            if body.classification == "own_transfer" and links.get(event_id, {}).get("status") != "confirmed":
                raise ValueError("Confirm a current own-account transfer link in Account history first.")
            if body.classification == "outside" and event["balance_effect"]["wallet_scope"] != "outside":
                raise ValueError("Resolve the outside-wallet classification in the funding review first.")
            row["reviews"][event_id] = dict(**body.model_dump(mode="json"), reviewed_at=stamp())
            row["coverage"] = None
            self.write(db, row, "flow_review", row["reviews"][event_id] | {"event_id": event_id})
        return self.detail(identity)

    def manual(self, identity, body):
        with self.store.db() as db:
            db.execute("BEGIN IMMEDIATE")
            row = self.read(db, identity)
            self.revision(row, body.revision)
            if not row["closing"] or body.account_id not in row["account_ids"]:
                raise ValueError("Close the period and choose one of its pinned accounts.")
            if len(row.get("manual_flows", {})) >= 200:
                raise ValueError("Keep at most 200 manual external flows in a period.")
            at = int(body.occurred_at.timestamp() * 1000)
            if (
                not max(milliseconds(s["as_of"]) for s in row["opening"].values())
                < at
                < min(milliseconds(s["started_at"]) for s in row["closing"].values())
            ):
                raise ValueError("Choose a timestamp strictly inside the observed period.")
            event_id = digest([row["id"], body.account_id, at, body.direction, str(body.value)])
            if event_id in row.get("manual_flows", {}):
                raise ValueError("This exact manual cash flow is already present.")
            event = dict(
                id=event_id,
                account_id=body.account_id,
                account=row["opening"][body.account_id]["accounts"][0]["label"],
                exchange="manual",
                environment=row["environment"],
                kind="manual",
                asset="USDT",
                quantity=float(body.value),
                timestamp_ms=at,
                posted_ms=at,
                direction=body.direction,
                status="completed",
                fee={"currency": None, "cost": None},
                fee_known=False,
                internal=False,
                amount_basis="user_value",
                wallet_scope="configured",
                provenance="user_assertion",
            )
            event["balance_effect"] = dict(
                wallet_scope="configured", provenance="user_assertion", quantity=None
            )
            row.setdefault("manual_flows", {})[event_id] = event
            row["reviews"][event_id] = dict(
                source_version=fingerprint(event),
                classification="external",
                value=str(body.value),
                occurred_at=body.occurred_at.isoformat(),
                note=body.note,
                reviewed_at=stamp(),
            )
            row["coverage"] = None
            self.write(db, row, "manual_external_flow", {"event": event, "review": row["reviews"][event_id]})
        return self.detail(identity)

    def remove_manual(self, identity, event_id, body):
        with self.store.db() as db:
            db.execute("BEGIN IMMEDIATE")
            row = self.read(db, identity)
            self.revision(row, body.revision)
            if event_id not in row.get("manual_flows", {}):
                raise LookupError("Manual cash flow not found.")
            previous = row["manual_flows"].pop(event_id)
            row["reviews"].pop(event_id, None)
            row["coverage"] = None
            self.write(db, row, "remove_manual_flow", previous)
        return self.detail(identity)

    def attest(self, identity, body):
        with self.store.db() as db:
            db.execute("BEGIN IMMEDIATE")
            row = self.read(db, identity)
            self.revision(row, body.revision)
            if not row["closing"]:
                raise ValueError("Capture the closing valuation first.")
            _, _, current = self.evidence(db, row)
            if current != body.evidence_fingerprint:
                raise ValueError(
                    "Funding or review evidence changed. Read it again before confirming coverage."
                )
            row["coverage"] = dict(**body.model_dump(), reviewed_at=stamp())
            self.write(db, row, "coverage_review", row["coverage"])
        return self.detail(identity)

    def detail(self, identity):
        with self.store.db() as db:
            db.execute("BEGIN")
            row = self.read(db, identity)
            events, links, version = self.evidence(db, row)
            audit = [
                dict(created_at=r[0], **json.loads(r[1]))
                for r in db.execute(
                    "SELECT created_at,payload FROM return_audit WHERE period_id=? ORDER BY id DESC LIMIT 50",
                    (identity,),
                )
            ]
        blockers, flows, views = [], [], []
        if not row["closing"]:
            blockers.append("Capture a closing valuation to measure this period.")
        coverage = row.get("coverage")
        if not coverage or not coverage["confirmed"] or coverage["evidence_fingerprint"] != version:
            blockers.append(
                "Confirm complete funding coverage for every selected wallet and this exact period. Imported pages alone do not establish completeness."
            )
        for event in events:
            review = row["reviews"].get(event["id"])
            current = bool(review and review["source_version"] == fingerprint(event))
            view = dict(
                event=event,
                source_version=fingerprint(event),
                review=review,
                review_current=current,
                transfer=links.get(event["id"]),
            )
            views.append(view)
            if event["status"] in {"failed", "cancelled"}:
                continue
            if event["status"] != "completed" or not current:
                blockers.append(
                    "A funding observation is pending, unsupported or needs a current cash-flow review."
                )
                continue
            at = milliseconds(review["occurred_at"])
            account = event["account_id"]
            opening, closing = row["opening"][account], (row["closing"] or row["opening"])[account]
            if not milliseconds(opening["as_of"]) < at < milliseconds(closing["started_at"]):
                blockers.append(
                    "A cash-flow timestamp overlaps a valuation boundary or lies outside the measured period."
                )
                continue
            if (
                not max(milliseconds(s["as_of"]) for s in row["opening"].values())
                < at
                < min(milliseconds(s["started_at"]) for s in row["closing"].values())
            ):
                blockers.append("A flow overlaps the combined account valuation window.")
                continue
            classification = review["classification"]
            value = float(review["value"]) * (1 if event["direction"] == "in" else -1)
            link = links.get(event["id"])
            if link and link["status"] == "confirmed" and classification not in {"own_transfer", "outside"}:
                blockers.append(
                    "Classify confirmed own-account links as own transfers; they are not investment income."
                )
                continue
            combined_internal = False
            if classification == "own_transfer":
                if not link or link["status"] != "confirmed":
                    blockers.append("An own-account transfer link needs review.")
                    continue
                pair = [link["reviewed"][side] for side in ("outgoing", "incoming")]
                if all(member["account_id"] in row["account_ids"] for member in pair):
                    pair_reviews = [row["reviews"].get(member["id"]) for member in pair]
                    if not all(r and r["classification"] == "own_transfer" for r in pair_reviews):
                        blockers.append(
                            "Review both legs of each transfer inside this combined scope; in-transit boundary transfers remain unavailable."
                        )
                        continue
                    combined_internal = True
            if (
                classification == "external"
                and link
                and link["status"] == "confirmed"
                and all(
                    link["reviewed"][side]["account_id"] in row["account_ids"]
                    for side in ("outgoing", "incoming")
                )
            ):
                blockers.append(
                    "A confirmed transfer inside this scope cannot be classified as external cash flow."
                )
                continue
            if classification == "outside" and event["balance_effect"]["wallet_scope"] != "outside":
                blockers.append("An outside-wallet funding review changed.")
                continue
            flows.append(
                dict(
                    event_id=event["id"],
                    account_id=account,
                    timestamp_ms=at,
                    value=value if classification in {"external", "own_transfer"} else 0,
                    combined_value=0
                    if combined_internal
                    else value
                    if classification in {"external", "own_transfer"}
                    else 0,
                    classification=classification,
                )
            )
        result, accounts = None, []
        if row["closing"] and not blockers:
            for account in row["account_ids"]:
                opening, closing = row["opening"][account], row["closing"][account]
                accounts.append(
                    dict(
                        account_id=account,
                        label=opening["accounts"][0]["label"],
                        **dietz(
                            opening["total"],
                            closing["total"],
                            milliseconds(opening["as_of"]),
                            milliseconds(closing["as_of"]),
                            [f for f in flows if f["account_id"] == account],
                        ),
                    )
                )
            result = dietz(
                sum(s["total"] for s in row["opening"].values()),
                sum(s["total"] for s in row["closing"].values()),
                max(milliseconds(s["as_of"]) for s in row["opening"].values()),
                max(milliseconds(s["as_of"]) for s in row["closing"].values()),
                [{**f, "value": f["combined_value"]} for f in flows],
            )
        return dict(
            **row,
            evidence_fingerprint=version,
            flows=views,
            result=result,
            account_results=accounts,
            blockers=list(dict.fromkeys(blockers)),
            audit=audit,
            method="Timestamp-weighted Modified Dietz estimate",
            note="Fresh observed valuations in USDT; historical principal values, timing, classifications and completeness are your audited assertions, not provider-verified facts. Returns are approximate, not exact time-weighted returns or tax P&L. Fees and income remain in investment performance. Account sets and source/environment are fixed; Demo is simulated. Old chart points are never used as accounting boundaries.",
        )

    def remove(self, identity, body):
        with self.store.db() as db:
            db.execute("BEGIN IMMEDIATE")
            row = self.read(db, identity)
            self.revision(row, body.revision)
            db.execute("DELETE FROM return_audit WHERE period_id=?", (identity,))
            db.execute("DELETE FROM return_periods WHERE id=?", (identity,))
        return {"removed": True}

    def list(self, scope="all"):
        with self.store.db() as db:
            rows = [
                json.loads(r[0])
                for r in db.execute("SELECT payload FROM return_periods ORDER BY rowid DESC LIMIT 100")
            ]
        return dict(
            items=[
                {
                    k: r[k]
                    for k in (
                        "id",
                        "label",
                        "scope",
                        "account_ids",
                        "revision",
                        "created_at",
                        "updated_at",
                        "source",
                        "environment",
                        "closing",
                    )
                }
                | {"closing": bool(r["closing"])}
                for r in rows
                if r["scope"] == scope
            ],
            limit=100,
        )

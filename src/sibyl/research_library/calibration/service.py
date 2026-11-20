"""Retained semantic-cutoff experiments and opt-in, fail-closed retrieval policies.

Each worker turn embeds one labeled query against an immutable corpus/index.
Stop/restart fences late results; fitting never enables a policy. Search uses
only the calibrated leading passage and withholds results after any bound
configuration/source change. No native agent can create experiments or edit policy.
"""

import json
import math
import threading
from datetime import UTC, datetime
from uuid import uuid4

from sibyl.research_library.calibration.metrics import calibrate
from sibyl.research_library.snapshot import retrieval_snapshot


def now():
    return datetime.now(UTC).isoformat()


class RetrievalCalibration:
    """Own experiments, exact relevance labels and revision-checked per-scope activation."""

    def __init__(self, library):
        self.library = library
        self.lock = threading.Lock()
        self.closed = False
        with library.db() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS retrieval_calibrations(id TEXT PRIMARY KEY,state TEXT NOT NULL,payload TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS retrieval_cutoffs(kind TEXT PRIMARY KEY,revision INTEGER NOT NULL,payload TEXT NOT NULL);
            """)
            for row in db.execute(
                "SELECT payload FROM retrieval_calibrations WHERE state IN ('queued','running')"
            ).fetchall():
                item = json.loads(row[0])
                item.update(
                    state="interrupted",
                    finished_at=now(),
                    error="Backend restarted. Run a fresh experiment explicitly; no queries were replayed.",
                )
                self._write(db, item)

    def snapshot(self, db):
        return retrieval_snapshot(self.library, db)

    @staticmethod
    def _write(db, item):
        db.execute(
            "INSERT OR REPLACE INTO retrieval_calibrations VALUES(?,?,?)",
            (item["id"], item["state"], json.dumps(item, allow_nan=False)),
        )

    @staticmethod
    def _get(db, identity):
        row = db.execute("SELECT payload FROM retrieval_calibrations WHERE id=?", (identity,)).fetchone()
        if not row:
            raise LookupError("Search calibration report not found.")
        return json.loads(row[0])

    def get(self, identity):
        with self.library.db() as db:
            return self._get(db, identity)

    @staticmethod
    def _policy(db, kind):
        row = db.execute("SELECT revision,payload FROM retrieval_cutoffs WHERE kind=?", (kind,)).fetchone()
        return (
            dict(json.loads(row[1]), revision=row[0])
            if row
            else {"kind": kind, "revision": 0, "enabled": False, "report_id": None}
        )

    def _guard(self, db, kind, snapshot=None):
        policy = self._policy(db, kind)
        if not policy["enabled"]:
            return {**policy, "state": "disabled"}
        report = self._get(db, policy["report_id"])
        current = self.snapshot(db) if snapshot is None else snapshot
        return {
            **policy,
            "state": "active" if current == report["snapshot"] else "stale",
            "threshold": report["calibration"]["threshold"],
            "fit": report["calibration"]["fit"],
            "validation": report["calibration"]["validation"],
        }

    def status(self):
        """Read compact local receipts and exact-scope policies, without provider calls."""
        with self.library.db() as db:
            db.execute("BEGIN")
            reports = [
                json.loads(r[0])
                for r in db.execute(
                    "SELECT json_remove(payload,'$.cases','$.results','$.gold') FROM retrieval_calibrations ORDER BY rowid DESC LIMIT 100"
                )
            ]
            snapshot = self.snapshot(db) if reports else None
            return {
                "reports": [
                    {**report, "snapshot_current": report["snapshot"] == snapshot} for report in reports
                ],
                "policies": {kind: self._guard(db, kind, snapshot) for kind in ("all", "document", "news")},
                "note": "Opt-in top-one semantic retrieval only. Keyword/hybrid search is uncalibrated; exact source scopes do not inherit each other's cutoffs. Source/model/index changes require a fresh experiment. This is not answer confidence.",
            }

    def start(self, body):
        """Pin labels/corpus/index and queue work; do not embed a query or enable filtering here."""
        with self.library.db() as db:
            db.execute("BEGIN IMMEDIATE")
            if self.closed:
                raise ValueError("Search calibration worker is closed.")
            if db.execute(
                "SELECT 1 FROM retrieval_calibrations WHERE state IN ('queued','running')"
            ).fetchone():
                raise ValueError("A calibration is already active. Wait or stop it first.")
            if db.execute("SELECT COUNT(*) FROM retrieval_calibrations").fetchone()[0] >= 100:
                raise ValueError("Keep at most 100 calibration reports. Remove an old inactive report first.")
            coverage = self.library.semantic.coverage(db, body.kind)
            if not self.library.semantic.config(db)[1] or not coverage["total"] or coverage["partial"]:
                raise ValueError(
                    "Configure a semantic model and completely index this source scope before calibration."
                )
            gold = []
            for case in body.cases:
                citations = []
                for identity in case.expected:
                    row = db.execute(
                        "SELECT p.*,d.kind,d.metadata,d.fingerprint FROM passages p JOIN documents d ON d.id=p.document_id WHERE p.id=?",
                        (identity,),
                    ).fetchone()
                    if not row or body.kind != "all" and row["kind"] != body.kind:
                        raise ValueError(
                            "Every relevant ID must belong to a retained passage in this source scope."
                        )
                    citations.append(
                        {
                            **self.library._citation(row),
                            "fingerprint": row["fingerprint"],
                            "source": json.loads(row["metadata"]),
                        }
                    )
                gold.append(citations)
            item = {
                "id": uuid4().hex,
                **body.model_dump(),
                "created_at": now(),
                "finished_at": None,
                "state": "queued",
                "completed": 0,
                "total": len(body.cases),
                "error": None,
                "snapshot": self.snapshot(db),
                "coverage": coverage,
                "gold": gold,
                "results": [],
                "calibration": None,
                "algorithm": "semantic-top-one-cutoff-v1",
            }
            self._write(db, item)
            return item

    def tick(self):
        """Run one query at a time; native library/provider validation remains authoritative."""
        if not self.lock.acquire(blocking=False):
            return
        try:
            if not self.closed:
                self._one()
        finally:
            self.lock.release()

    def _one(self):
        with self.library.db() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT payload FROM retrieval_calibrations WHERE state IN ('queued','running') ORDER BY rowid LIMIT 1"
            ).fetchone()
            if not row:
                return
            item = json.loads(row[0])
            item["state"] = "running"
            self._write(db, item)
        try:
            with self.library.db() as db:
                db.execute("BEGIN")
                if self.snapshot(db) != item["snapshot"]:
                    raise ValueError("Changed corpus/index")
            case = item["cases"][item["completed"]]
            # Explicit domain-only bypass: experiments measure raw rankings, never another cutoff.
            found = self.library.search(case["query"], item["kind"], 1, "semantic", False)
            top = found["items"][0] if found["items"] else None
            similarity = top["similarity"] if top else None
            if top and (
                type(similarity) not in {float, int}
                or not math.isfinite(similarity)
                or not -1 <= similarity <= 1
            ):
                raise ValueError("Invalid cosine score")
            result = {
                **case,
                "passage_id": top["id"] if top else None,
                "similarity": similarity,
                "citation": top,
            }
            with self.library.db() as db:
                db.execute("BEGIN IMMEDIATE")
                if self._get(db, item["id"])["state"] != "running":
                    return
                if self.snapshot(db) != item["snapshot"]:
                    raise ValueError("Changed corpus/index")
                item["results"].append(result)
                item["completed"] += 1
                if item["completed"] == item["total"]:
                    item.update(state="completed", finished_at=now(), calibration=calibrate(item["results"]))
                self._write(db, item)
        except Exception:
            with self.library.db() as db:
                db.execute("BEGIN IMMEDIATE")
                current = self._get(db, item["id"])
                if current["state"] == "running":
                    current.update(
                        state="failed",
                        finished_at=now(),
                        error="Retrieval failed or the corpus/index changed. Review semantic setup and run a new experiment. Partial results cannot enable a cutoff.",
                    )
                    self._write(db, current)

    def stop(self, identity):
        with self.library.db() as db:
            db.execute("BEGIN IMMEDIATE")
            item = self._get(db, identity)
            if item["state"] in {"queued", "running"}:
                item.update(state="stopped", finished_at=now())
                self._write(db, item)
            return item

    def set_policy(self, kind, body):
        """Activate only reviewed held-out results on the exact current snapshot; disable explicitly."""
        if kind not in {"all", "document", "news"}:
            raise ValueError("Choose a valid research source scope.")
        with self.library.db() as db:
            db.execute("BEGIN IMMEDIATE")
            previous = self._policy(db, kind)
            if previous["revision"] != body.revision:
                raise ValueError("The cutoff setting changed. Refresh and review it before saving.")
            if body.enabled:
                report = self._get(db, body.report_id)
                if (
                    report["kind"] != kind
                    or report["state"] != "completed"
                    or not report["calibration"]["eligible"]
                ):
                    raise ValueError(
                        "Choose a completed report with held-out relevant matches and zero observed incorrect accepts in this scope."
                    )
                if self.snapshot(db) != report["snapshot"]:
                    raise ValueError("The corpus/index changed. Fit and validate a new cutoff first.")
            policy = {
                "kind": kind,
                "enabled": body.enabled,
                "report_id": body.report_id if body.enabled else previous["report_id"],
                "updated_at": now(),
            }
            db.execute(
                "INSERT OR REPLACE INTO retrieval_cutoffs VALUES(?,?,?)",
                (kind, previous["revision"] + 1, json.dumps(policy)),
            )
        return self.status()

    def search(self, query, kind, limit):
        """Apply an explicitly enabled top-one cutoff; stale or changed policies withhold evidence."""
        if (
            kind not in {"all", "document", "news"}
            or not query.strip()
            or len(query) > 300
            or not 1 <= limit <= 20
        ):
            raise ValueError(
                "Choose a source scope, a nonblank query up to 300 characters and a limit of 1–20."
            )
        with self.library.db() as db:
            db.execute("BEGIN")
            before = self._guard(db, kind)
        if before["state"] == "stale":
            return self._withheld(
                query,
                before,
                "The calibrated corpus or embedding index changed. Recalibrate or explicitly disable the cutoff; no model query was sent.",
            )
        result = self.library.semantic.search(query, kind, 1 if before["enabled"] else limit, "semantic")
        with self.library.db() as db:
            db.execute("BEGIN")
            after = self._guard(db, kind)
        if after["revision"] != before["revision"] or after["state"] == "stale":
            return self._withheld(
                query,
                {**after, "state": "changed"},
                "The cutoff or corpus/index changed during retrieval. No passage was released; run the search again after reviewing setup.",
            )
        if not before["enabled"]:
            return {**result, "calibration": {**after, "applied": False, "abstained": False}}
        top = result["items"][0] if result["items"] else None
        accept = bool(top and top["similarity"] >= before["threshold"])
        return {
            **result,
            "items": [top] if accept else [],
            "calibration": {
                **after,
                "applied": True,
                "abstained": not accept,
                "state": "accepted" if accept else "abstained",
                "top_similarity": top["similarity"] if top else None,
                "note": (
                    "Only the leading passage passed the cutoff. "
                    if accept
                    else "The leading passage did not meet your cutoff; no passage was released. "
                )
                + "This is empirical retrieval evidence, not answer confidence or verified truth.",
            },
        }

    @staticmethod
    def _withheld(query, policy, note):
        return {
            "query": query,
            "items": [],
            "retrieval": "calibrated top-one cosine",
            "calibration": {**policy, "applied": True, "abstained": True, "note": note},
            "note": note,
        }

    def delete(self, identity):
        with self.library.db() as db:
            db.execute("BEGIN IMMEDIATE")
            item = self._get(db, identity)
            if item["state"] in {"queued", "running"}:
                raise ValueError("Stop the active calibration before deleting it.")
            if db.execute(
                "SELECT 1 FROM retrieval_cutoffs WHERE json_extract(payload,'$.enabled')=1 AND json_extract(payload,'$.report_id')=?",
                (identity,),
            ).fetchone():
                raise ValueError("Disable the cutoff using this report before deleting it.")
            db.execute("DELETE FROM retrieval_calibrations WHERE id=?", (identity,))

    def close(self):
        """Drain in-flight query work before the shared library/provider resources close."""
        with self.lock:
            self.closed = True

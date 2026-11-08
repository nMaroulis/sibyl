"""Durable, bounded local retrieval comparisons with one query per worker iteration.

Gold labels are supplied by the owner, never inferred by an LLM. The corpus and
optional embedding index are fingerprinted before admission and before each
commit. Stop fences late results; restart marks unfinished work interrupted and
never replays it. A report evaluates retrieval, not answer correctness.
"""

import hashlib
import json
import threading
import time
from datetime import UTC, datetime
from statistics import mean
from uuid import uuid4

from sibyl.research_library.evaluations.metrics import score


def now():
    return datetime.now(UTC).isoformat()


class RetrievalEvaluations:
    def __init__(self, library):
        self.library = library
        self.lock = threading.Lock()
        self.closed = False
        with library.db() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS retrieval_suites(id TEXT PRIMARY KEY,payload TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS retrieval_evaluations(id TEXT PRIMARY KEY,state TEXT NOT NULL,payload TEXT NOT NULL);
            """)
            for row in db.execute(
                "SELECT id,payload FROM retrieval_evaluations WHERE state IN ('queued','running')"
            ).fetchall():
                item = json.loads(row["payload"])
                item.update(
                    state="interrupted",
                    finished_at=now(),
                    error="Backend restarted. Start a fresh run explicitly.",
                )
                self._write(db, item)

    @staticmethod
    def _write(db, item):
        db.execute(
            "INSERT OR REPLACE INTO retrieval_evaluations VALUES(?,?,?)",
            (item["id"], item["state"], json.dumps(item, allow_nan=False)),
        )

    def save(self, body):
        item = {"id": uuid4().hex, "created_at": now(), **body.model_dump(), "gold": []}
        with self.library.db() as db:
            db.execute("BEGIN IMMEDIATE")
            if db.execute("SELECT COUNT(*) FROM retrieval_suites").fetchone()[0] >= 20:
                raise ValueError("Keep at most 20 evaluation suites. Remove an old suite first.")
            for case in body.cases:
                citations = []
                for identity in case.expected:
                    row = db.execute(
                        "SELECT p.*,d.kind,d.metadata,d.fingerprint FROM passages p JOIN documents d ON p.document_id=d.id WHERE p.id=?",
                        (identity,),
                    ).fetchone()
                    if not row or (body.kind != "all" and row["kind"] != body.kind):
                        raise ValueError(
                            "Every expected ID must be a retained passage in the selected source type."
                        )
                    citations.append(
                        {
                            **self.library._citation(row),
                            "fingerprint": row["fingerprint"],
                            "source": json.loads(row["metadata"]),
                        }
                    )
                item["gold"].append(citations)
            db.execute("INSERT INTO retrieval_suites VALUES(?,?)", (item["id"], json.dumps(item)))
        return item

    def catalog(self):
        with self.library.db() as db:
            return {
                "suites": [
                    {key: value for key, value in json.loads(row[0]).items() if key != "gold"}
                    for row in db.execute("SELECT payload FROM retrieval_suites ORDER BY rowid DESC")
                ],
                "runs": [
                    json.loads(row[0])
                    for row in db.execute(
                        "SELECT json_remove(payload,'$.results','$.suite','$.plan') FROM retrieval_evaluations ORDER BY rowid DESC"
                    )
                ],
            }

    def get(self, identity):
        with self.library.db() as db:
            return self._get(db, identity)

    @staticmethod
    def _get(db, identity):
        row = db.execute("SELECT payload FROM retrieval_evaluations WHERE id=?", (identity,)).fetchone()
        if not row:
            raise LookupError("Retrieval evaluation not found.")
        return json.loads(row[0])

    def _snapshot(self, db, semantic):
        # BM25 uses corpus-wide document statistics even when a kind filter is applied.
        digest, count = hashlib.sha256(), 0
        for row in db.execute(
            "SELECT p.id,p.text,d.fingerprint,d.metadata FROM passages p JOIN documents d ON p.document_id=d.id ORDER BY p.id"
        ):
            digest.update(json.dumps(tuple(row), ensure_ascii=False).encode())
            count += 1
        result = {"corpus": digest.hexdigest(), "passages": count}
        if semantic:
            revision, profile = self.library.semantic.config(db)
            vectors = hashlib.sha256()
            for row in db.execute(
                "SELECT passage_id,content_hash,vector FROM semantic_vectors ORDER BY passage_id"
            ):
                vectors.update(json.dumps(tuple(row)[:2]).encode())
                vectors.update(row["vector"])
            result.update(
                semantic_revision=revision,
                model=profile.get("model"),
                model_digest=profile.get("model_digest"),
                index=vectors.hexdigest(),
            )
        return result

    def start(self, identity, body):
        with self.library.db() as db:
            db.execute("BEGIN IMMEDIATE")
            if self.closed:
                raise ValueError("Retrieval evaluation worker is closed.")
            if db.execute(
                "SELECT 1 FROM retrieval_evaluations WHERE state IN ('queued','running')"
            ).fetchone():
                raise ValueError("One retrieval evaluation is already active. Stop it or wait.")
            if db.execute("SELECT COUNT(*) FROM retrieval_evaluations").fetchone()[0] >= 100:
                raise ValueError(
                    "Keep at most 100 evaluation reports. Remove an old suite and its reports first."
                )
            row = db.execute("SELECT payload FROM retrieval_suites WHERE id=?", (identity,)).fetchone()
            if not row:
                raise LookupError("Evaluation suite not found.")
            suite = json.loads(row[0])
            for gold in suite["gold"]:
                for citation in gold:
                    current = db.execute(
                        "SELECT p.text,d.fingerprint FROM passages p JOIN documents d ON p.document_id=d.id WHERE p.id=?",
                        (citation["id"],),
                    ).fetchone()
                    if not current or tuple(current) != (citation["text"], citation["fingerprint"]):
                        raise ValueError(
                            "A labeled passage changed or was removed. Save updated judgments first."
                        )
            semantic = any(method != "keyword" for method in body.methods)
            coverage = self.library.semantic.coverage(db, suite["kind"])
            if semantic and (not self.library.semantic.config(db)[1] or not coverage["indexed"]):
                raise ValueError(
                    "Configure a local embedding model and index passages before comparing semantic methods."
                )
            item = {
                "id": uuid4().hex,
                "suite_id": identity,
                "title": suite["title"],
                "suite": suite,
                "created_at": now(),
                "state": "queued",
                "finished_at": None,
                "error": None,
                **body.model_dump(),
                "snapshot": self._snapshot(db, semantic),
                "coverage": coverage if semantic else None,
                "plan": [
                    {"method": method, "case": index}
                    for index in range(len(suite["cases"]))
                    for method in body.methods
                ],
                "results": [],
                "summary": {},
                "completed": 0,
                "total": len(suite["cases"]) * len(body.methods),
                "note": "Owner-labeled passage relevance, not factual verification or answer confidence. Partial indexes and incomplete gold labels limit comparisons. Latency includes local query embedding; shared-server load and caching can affect it.",
            }
            self._write(db, item)
        return item

    def stop(self, identity):
        with self.library.db() as db:
            db.execute("BEGIN IMMEDIATE")
            item = self._get(db, identity)
            if item["state"] in {"queued", "running"}:
                item.update(state="stopped", finished_at=now())
                self._write(db, item)
            return item

    def delete(self, identity):
        with self.library.db() as db:
            db.execute("BEGIN IMMEDIATE")
            if db.execute(
                "SELECT 1 FROM retrieval_evaluations WHERE json_extract(payload,'$.suite_id')=? AND state IN ('queued','running')",
                (identity,),
            ).fetchone():
                raise ValueError("Stop this suite's active evaluation first.")
            if not db.execute("SELECT 1 FROM retrieval_suites WHERE id=?", (identity,)).fetchone():
                raise LookupError("Evaluation suite not found.")
            db.execute(
                "DELETE FROM retrieval_evaluations WHERE json_extract(payload,'$.suite_id')=?", (identity,)
            )
            db.execute("DELETE FROM retrieval_suites WHERE id=?", (identity,))

    def tick(self):
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
                "SELECT payload FROM retrieval_evaluations WHERE state IN ('queued','running') ORDER BY rowid LIMIT 1"
            ).fetchone()
            if not row:
                return
            item = json.loads(row[0])
            item["state"] = "running"
            self._write(db, item)
        try:
            with self.library.db() as db:
                db.execute("BEGIN")
                if self._snapshot(db, item["coverage"] is not None) != item["snapshot"]:
                    raise ValueError("corpus_changed")
            task = item["plan"][item["completed"]]
            case = item["suite"]["cases"][task["case"]]
            started = time.monotonic()
            found = self.library.search(case["query"], item["suite"]["kind"], item["k"], task["method"])
            result = {
                **task,
                "query": case["query"],
                "metrics": score([row["id"] for row in found["items"]], case["expected"], item["k"]),
                "milliseconds": round((time.monotonic() - started) * 1000, 2),
                "items": found["items"],
            }
            with self.library.db() as db:
                db.execute("BEGIN IMMEDIATE")
                current = self._get(db, item["id"])
                if current["state"] != "running":
                    return  # Stop fences late results from an already admitted query.
                if self._snapshot(db, item["coverage"] is not None) != item["snapshot"]:
                    raise ValueError("corpus_changed")
                item["results"].append(result)
                item["completed"] += 1
                if item["completed"] == item["total"]:
                    item.update(state="completed", finished_at=now())
                    for method in item["methods"]:
                        rows = [row for row in item["results"] if row["method"] == method]
                        item["summary"][method] = {
                            key: mean(row["metrics"][key] for row in rows) for key in rows[0]["metrics"]
                        }
                        item["summary"][method]["mean_milliseconds"] = mean(
                            row["milliseconds"] for row in rows
                        )
                self._write(db, item)
        except Exception:
            # Embedding errors can contain endpoints or native response text; keep private details out of reports.
            with self.library.db() as db:
                db.execute("BEGIN IMMEDIATE")
                current = self._get(db, item["id"])
                if current["state"] == "running":
                    current.update(
                        state="failed",
                        finished_at=now(),
                        error="Retrieval failed or the corpus/index changed. Review local search setup and start a fresh run; partial results are not a complete comparison.",
                    )
                    self._write(db, current)

    def close(self):
        with self.lock:
            self.closed = True

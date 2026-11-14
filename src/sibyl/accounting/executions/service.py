"""Cross-market accounting requests and source-consistent read snapshots.

This service derives asset books from retained observations. It neither starts
exchange imports nor assumes that the retained inventory is a complete history.
Opening cost remains an audited user assertion in one reporting currency.
"""

import hashlib
import json
from collections import defaultdict
from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

from pydantic import AwareDatetime, Field, model_validator

from sibyl.accounting.executions.books import replay
from sibyl.accounting.executions.prices import HistoricalPrices
from sibyl.accounting.funding.reviews import FundingReviews
from sibyl.models import Request
from sibyl.services.accounts.sync import environment
from sibyl.services.transfers.allocation import movement_plan
from sibyl.services.transfers.reconciliation import link_view

ASSET = r"^[A-Z0-9][A-Z0-9.]{0,19}$"
MAX_INPUTS = 20_000


class AssetOpening(Request):
    """An explicit asset acquisition assertion, before its first retained execution."""

    asset: str = Field(pattern=ASSET)
    currency: str = Field(default="USDT", pattern=ASSET)
    quantity: Decimal = Field(gt=0, le=Decimal("1e24"), allow_inf_nan=False)
    total_cost: Decimal | None = Field(default=None, ge=0, le=Decimal("1e30"), allow_inf_nan=False)
    as_of: AwareDatetime
    revision: int = Field(default=0, ge=0, strict=True)
    note: str = Field(min_length=3, max_length=1000)

    @model_validator(mode="after")
    def past(self):
        if not 0 <= self.as_of.timestamp() <= datetime.now(UTC).timestamp():
            raise ValueError("Use a past timezone-aware opening date.")
        if not self.note.strip():
            raise ValueError("Explain the opening inventory evidence.")
        if self.asset == self.currency and self.total_cost is not None and self.total_cost != self.quantity:
            raise ValueError("Reporting-unit inventory has identity cost equal to its quantity.")
        return self


class AccountBooksService:
    """Keep audited assertions separate from immutable fills, funding and source candles."""

    def __init__(self, store):
        self.store = store
        with store.db() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS asset_openings (
                    id TEXT PRIMARY KEY, account_id TEXT NOT NULL, environment TEXT NOT NULL,
                    asset TEXT NOT NULL, currency TEXT NOT NULL, payload TEXT NOT NULL,
                    UNIQUE(account_id,environment,asset,currency)
                );
                CREATE TABLE IF NOT EXISTS asset_opening_audit (
                    id INTEGER PRIMARY KEY, opening_id TEXT NOT NULL, created_at TEXT NOT NULL, payload TEXT NOT NULL
                );
            """)

    def save_opening(self, account_id, body):
        """Validate date/quantity and optimistic revision, then append one local decision."""
        account = next((row for row in self.store.connections() if row.id == account_id), None)
        if account is None:
            raise LookupError("Connection not found.")
        env = environment(account)
        with self.store.db() as db:
            db.execute("BEGIN IMMEDIATE")
            previous = db.execute(
                "SELECT id,payload FROM asset_openings WHERE account_id=? AND environment=? AND asset=? AND currency=?",
                (account_id, env, body.asset, body.currency),
            ).fetchone()
            before = json.loads(previous["payload"]) if previous else None
            if body.revision != (before["revision"] if before else 0):
                raise ValueError("Opening inventory changed. Reload its revision before saving.")
            fills = db.execute(
                "SELECT payload FROM account_fills WHERE account_id=?", (account_id,)
            ).fetchall()
            if len(fills) > MAX_INPUTS:
                raise ValueError("Opening review exceeds the 20,000-fill accounting budget.")
            for raw in fills:
                row = json.loads(raw[0])
                affected = set(row["symbol"].split("/")) | {
                    fee["currency"] for fee in row["fees"] if fee["currency"]
                }
                if (
                    row["environment"] == env
                    and body.asset in affected
                    and body.as_of.timestamp() * 1000 >= row["timestamp_ms"]
                ):
                    raise ValueError(
                        "Opening inventory must precede every retained execution affecting that asset."
                    )
            stamp = datetime.now(UTC).isoformat()
            saved = {
                **body.model_dump(mode="json"),
                "id": previous["id"] if previous else uuid4().hex,
                "account_id": account_id,
                "environment": env,
                "revision": body.revision + 1,
                "timestamp_ms": int(body.as_of.timestamp() * 1000),
                "updated_at": stamp,
            }
            if body.asset == body.currency:
                saved["total_cost"] = str(body.quantity)
            db.execute(
                "INSERT INTO asset_openings VALUES(?,?,?,?,?,?) ON CONFLICT(account_id,environment,asset,currency) DO UPDATE SET payload=excluded.payload",
                (saved["id"], account_id, env, body.asset, body.currency, json.dumps(saved)),
            )
            db.execute(
                "INSERT INTO asset_opening_audit(opening_id,created_at,payload) VALUES(?,?,?)",
                (saved["id"], stamp, json.dumps({"action": "save", "before": before, "after": saved})),
            )
        return saved

    def openings(self, account_id="", currency="USDT"):
        """Read current assertions without decrypting or contacting an exchange."""
        with self.store.db() as db:
            rows = db.execute(
                "SELECT payload FROM asset_openings WHERE currency=? AND (?='' OR account_id=?) ORDER BY account_id,asset",
                (currency, account_id, account_id),
            ).fetchall()
        return {"items": [json.loads(row[0]) for row in rows]}

    def remove_opening(self, identity, revision):
        """Withdraw one versioned assertion while retaining its full audit journal."""
        with self.store.db() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT payload FROM asset_openings WHERE id=?", (identity,)).fetchone()
            if row is None:
                raise LookupError("Opening inventory not found.")
            before = json.loads(row[0])
            if before["revision"] != revision:
                raise ValueError("Opening inventory changed. Reload before removing.")
            db.execute(
                "INSERT INTO asset_opening_audit(opening_id,created_at,payload) VALUES(?,?,?)",
                (
                    identity,
                    datetime.now(UTC).isoformat(),
                    json.dumps({"action": "remove", "before": before, "after": None}),
                ),
            )
            db.execute("DELETE FROM asset_openings WHERE id=?", (identity,))
        return {"removed": True}

    def report(self, account_id="", environment_filter="", currency="USDT", source="binance"):
        """Replay all required acquisitions, then filter rows; never truncate inputs."""
        with self.store.db() as db:
            db.execute("BEGIN")
            fills = self._facts(db, "account_fills", environment_filter)
            funding = FundingReviews.enrich(db, self._facts(db, "funding_events", environment_filter))
            openings = [
                json.loads(row[0])
                for row in db.execute("SELECT payload FROM asset_openings WHERE currency=?", (currency,))
            ]
            links, blocked_links = self._transfers(db, environment_filter)
            groups, blocked_groups = self._groups(db, environment_filter)
            links.extend(groups)
            blocked_links.extend(blocked_groups)
            openings, blocked_openings = self._valid_openings(openings, fills)
            cutoffs = {
                (row["account_id"], row["environment"], row["asset"]): row["timestamp_ms"] for row in openings
            }
            eligible = []
            for link in links:
                if any(
                    (event.get("posted_ms") or event["timestamp_ms"])
                    <= cutoffs.get((event["account_id"], event["environment"], event["asset"]), -1)
                    for event in (
                        [leg["event"] for side in ("outgoing", "incoming") for leg in link["plan"][side]]
                        if link.get("kind") == "group"
                        else (link["outgoing"], link["incoming"])
                    )
                ):
                    blocked_links.append(
                        {
                            "id": link["id"],
                            "reason": "An opening assertion covers a transfer leg; cross-boundary carryover is unavailable.",
                        }
                    )
                else:
                    eligible.append(link)
            links = eligible
            # Include all accounts: a selected destination depends on acquisitions at its source.
            # A hard budget rejects oversized work rather than erasing those dependencies.
            all_facts = [*fills, *funding]
            minimum = min((row["timestamp_ms"] for row in all_facts), default=0)
            maximum = max((row.get("posted_ms") or row["timestamp_ms"] for row in all_facts), default=0)
            grouped = defaultdict(list)
            for row in fills:
                grouped[row["environment"]].append(row)
            environments = sorted(
                set(grouped)
                | {row["environment"] for row in funding}
                | {
                    row["environment"]
                    for row in openings
                    if not environment_filter or row["environment"] == environment_filter
                }
            )
            reports, price_fingerprints = [], {}
            for env in environments:
                prices = HistoricalPrices(db, source, env, minimum, maximum)
                price_fingerprints[env] = prices.fingerprint()
                result = replay(
                    currency,
                    prices,
                    grouped[env],
                    [row for row in funding if row["environment"] == env],
                    [row for row in openings if row["environment"] == env],
                    [
                        row
                        for row in links
                        if (
                            row["plan"]["environment"]
                            if row.get("kind") == "group"
                            else row["outgoing"]["environment"]
                        )
                        == env
                    ],
                )
                for row in result["items"]:
                    row["environment"] = env
                reports.append({"environment": env, **result})
            revisions = db.execute("SELECT COUNT(*),COALESCE(MAX(rowid),0) FROM fill_versions").fetchone()
        for result in reports:
            if account_id:
                result["items"] = [row for row in result["items"] if row["account_id"] == account_id]
                result["disposals"] = [row for row in result["disposals"] if row["account_id"] == account_id]
        fingerprint = hashlib.sha256(
            json.dumps(
                {
                    "fills": fills,
                    "funding": funding,
                    "openings": openings,
                    "links": links,
                    "price_snapshots": price_fingerprints,
                    "source": source,
                    "currency": currency,
                },
                sort_keys=True,
            ).encode()
        ).hexdigest()
        return {
            "currency": currency,
            "source": source,
            "method": "account-asset-fifo-v1",
            "account_id": account_id,
            "as_of": datetime.now(UTC).isoformat(),
            "input_fingerprint": fingerprint,
            "fill_count": len(fills),
            "funding_count": len(funding),
            "fill_observation_count": revisions[0],
            "reports": reports,
            "unapplied_transfers": blocked_links,
            "unapplied_openings": blocked_openings,
            "price_snapshots": price_fingerprints,
            "complete_history": False,
            "note": "FIFO across retained pairs with separate account/environment books. Historical conversion uses the last fully closed candle at or before the event, up to 24 hours old, or an exact reported fill ratio. It is an approximate mark, not an execution quote. Unknown basis and missing conversions are excluded from matched results. Funding classifications and complete wallet history are not inferred; these are modeled accounting components, not complete account returns or tax results.",
        }

    @staticmethod
    def _valid_openings(openings, fills):
        """An older import or corrected timestamp can invalidate a saved assertion."""
        earliest = {}
        for fill in fills:
            assets = set(fill["symbol"].split("/")) | {
                fee["currency"] for fee in fill["fees"] if fee["currency"]
            }
            for asset in assets:
                key = fill["account_id"], fill["environment"], asset
                earliest[key] = min(earliest.get(key, float("inf")), fill["timestamp_ms"])
        valid, blocked = [], []
        for row in openings:
            if row["timestamp_ms"] >= earliest.get(
                (row["account_id"], row["environment"], row["asset"]), float("inf")
            ):
                blocked.append(
                    {
                        "id": row["id"],
                        "account_id": row["account_id"],
                        "asset": row["asset"],
                        "reason": "Retained executions now precede this opening. Review its date and quantity before it can apply.",
                    }
                )
            else:
                valid.append(row)
        return valid, blocked

    @staticmethod
    def _facts(db, table, env):
        if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone():
            return []
        rows = db.execute(
            f"SELECT payload FROM {table} WHERE (?='' OR json_extract(payload,'$.environment')=?) ORDER BY timestamp_ms,id LIMIT ?",
            (env, env, MAX_INPUTS + 1),
        ).fetchall()
        if len(rows) > MAX_INPUTS:
            raise ValueError(
                f"Accounting exceeds {MAX_INPUTS:,} retained {table} inputs including transfer dependencies; inputs are never silently truncated."
            )
        return [json.loads(row[0]) for row in rows]

    @staticmethod
    def _transfers(db, env):
        if not db.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='transfer_links'"
        ).fetchone():
            return [], []
        rows = db.execute("SELECT * FROM transfer_links WHERE state='confirmed' LIMIT 2001").fetchall()
        if len(rows) > 2000:
            raise ValueError("Accounting exceeds the 2,000 transfer-link dependency budget.")
        valid, blocked = [], []
        for record in rows:
            link = link_view(db, dict(record))
            out, inc = (link["reviewed"][side] for side in ("outgoing", "incoming"))
            if env and out["environment"] != env:
                continue
            try:
                if link["status"] != "confirmed" or (out.get("posted_ms") or out["timestamp_ms"]) > (
                    inc.get("posted_ms") or inc["timestamp_ms"]
                ):
                    raise ValueError("Transfer facts changed or receipt precedes dispatch.")
                plan = movement_plan(link, out, inc)
            except ValueError as exc:
                blocked.append({"id": link["id"], "reason": str(exc)})
            else:
                valid.append({"id": link["id"], "outgoing": out, "incoming": inc, "plan": plan})
        return valid, blocked

    @staticmethod
    def _groups(db, env):
        """Admit complete, currently reviewed groups; never apply a valid subset."""
        if not db.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='transfer_groups'"
        ).fetchone():
            return [], []
        from sibyl.services.transfers.groups.service import group_view

        rows = db.execute("SELECT * FROM transfer_groups WHERE state='confirmed' LIMIT 1001").fetchall()
        if len(rows) > 1000:
            raise ValueError("Accounting exceeds the 1,000 transfer-group dependency budget.")
        valid, blocked = [], []
        for row in rows:
            group = group_view(db, row)
            if env and group["reviewed"]["environment"] != env:
                continue
            if group["status"] != "confirmed":
                blocked.append(
                    {
                        "id": group["id"],
                        "reason": group["reason"]
                        or "Group funding facts or balance decisions changed; review every member again.",
                    }
                )
            else:
                valid.append({"id": group["id"], "kind": "group", "plan": group["current"]})
        return valid, blocked

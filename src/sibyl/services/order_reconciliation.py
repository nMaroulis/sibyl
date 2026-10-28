"""Durable, bounded execution imports and honest comparisons with native order totals."""

import hashlib
import json
import time
from collections import defaultdict
from datetime import datetime
from decimal import Decimal, localcontext

import ccxt

from sibyl.exchanges.history import TradePage
from sibyl.market_data.control import ProviderDeferred
from sibyl.services.ledger import AccountLedger, ledger_fill, now_iso
from sibyl.services.order_lifecycle import TERMINAL

READ_LIMIT = 10_000


def summarize(intent: dict, fills: list[dict], job: dict | None) -> dict:
    """Compare gross base units and reported quote cost; never equate a match with settlement.

    Native-currency fees and rebates remain separate from traded quantities.
    Unknown fees remain unknown. Totals always use the whole bounded selection,
    not the first page displayed by the UI, and are recalculated after corrections.
    """
    with localcontext() as context:
        context.prec = 50
        quantity = sum((Decimal(str(fill["quantity"])) for fill in fills), Decimal(0))
        expected = intent.get("filled")
        expected = Decimal(str(expected)) if expected is not None else None
        difference = quantity - expected if expected is not None else None
        tolerance = max(
            Decimal("1e-10"),
            Decimal(str(intent["request"].get("quantity") or expected or 0)) * Decimal("1e-8"),
        )
        cost_known = all(fill["notional"] is not None for fill in fills)
        cost = sum((Decimal(str(fill["notional"])) for fill in fills), Decimal(0)) if cost_known else None
        native_cost = intent.get("cost")
        cost_difference = (
            cost - Decimal(str(native_cost)) if cost is not None and native_cost is not None else None
        )
        cost_tolerance = max(Decimal("1e-8"), abs(Decimal(str(native_cost or 0))) * Decimal("1e-6"))
        fees = defaultdict(Decimal)
        unknown_fees = sum(not fill["fees_known"] for fill in fills)
        identity_conflict = any(
            fill["side"] != intent["request"]["side"]
            or fill["environment"] != intent["environment"]
            or fill["exchange"] != intent["exchange"]
            for fill in fills
        )
        for fill in fills:
            for fee in fill["fees"]:
                if fee["currency"] and fee["cost"] is not None:
                    fees[fee["currency"]] += Decimal(str(fee["cost"]))
        if len(fills) > READ_LIMIT:
            status = "limit_reached"
        elif identity_conflict or (difference is not None and difference > tolerance):
            status = "mismatch"
        elif difference is not None and difference < -tolerance:
            status = "missing_fills"
        elif cost_difference is not None and abs(cost_difference) > cost_tolerance:
            status = "mismatch"
        elif expected is None:
            status = "unverified" if fills or job else "not_checked"
        elif unknown_fees:
            status = "fees_missing"
        elif intent["status"] not in TERMINAL or (job and not job.get("caught_up")):
            status = "pending"
        else:
            status = "matched"

        def finite(value):
            if value is None:
                return None
            result = float(value)
            return result if abs(result) != float("inf") else None

        return {
            "status": status,
            "fill_count": len(fills),
            "quantity": finite(quantity),
            "native_filled": finite(expected),
            "quantity_difference": finite(difference),
            "notional": finite(cost),
            "cost_difference": finite(cost_difference),
            "native_cost": finite(Decimal(str(native_cost))) if native_cost is not None else None,
            "average": finite(cost / quantity) if cost is not None and quantity else None,
            "fees": [
                {"currency": currency, "cost": finite(value)} for currency, value in sorted(fees.items())
            ],
            "unknown_fee_fills": unknown_fees,
            "sync": {
                key: value
                for key, value in (job or {}).items()
                if key
                in {
                    "state",
                    "enabled",
                    "caught_up",
                    "pages",
                    "checked_at",
                    "error",
                    "next_attempt",
                    "terminal_passes",
                }
            },
            "settlement_final": False,
            "note": "Compared with retained native executions. A quantity match and reported fees do not guarantee final settlement or complete account history.",
        }


class OrderReconciliation:
    """Import exact-order fills into the shared ledger, with atomic page checkpoints.

    The application runs one API worker. Per-intent lifecycle locks serialize
    local checks and pause/resume. Background reads require an active account.
    Three complete terminal passes (immediate, +60s, +300s) bound late-fee checks;
    explicit rechecks remain available afterwards, including on inactive accounts.
    """

    def __init__(self, trading):
        self.trading, self.store = trading, trading.store
        AccountLedger(self.store, recover=False)
        with self.store.db() as db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS order_fill_sync (intent_id TEXT PRIMARY KEY, payload TEXT NOT NULL)"
            )

    @staticmethod
    def _read(db, identity: str) -> dict | None:
        row = db.execute("SELECT payload FROM order_fill_sync WHERE intent_id=?", (identity,)).fetchone()
        return json.loads(row[0]) if row else None

    @staticmethod
    def _write(db, identity: str, job: dict) -> None:
        db.execute(
            "INSERT INTO order_fill_sync VALUES(?,?) ON CONFLICT(intent_id) DO UPDATE SET payload=excluded.payload",
            (identity, json.dumps(job, allow_nan=False)),
        )

    def schedule(self, db, intent: dict) -> None:
        """Create local read work in the same transaction as an order observation."""
        if not intent.get("exchange_order_id") or intent["status"] == "preview":
            return
        job = self._read(db, intent["id"])
        if job is None:
            job = {
                "cursor": {},
                "seen": [],
                "pages": 0,
                "caught_up": False,
                "enabled": intent.get(
                    "fill_tracking", intent["status"] in TERMINAL or intent.get("tracking", False)
                ),
                "state": "queued",
                "terminal_passes": 0,
                "next_attempt": 0,
                "failures": 0,
            }
        observed = [intent["status"], intent.get("filled"), intent.get("cost")]
        if job.get("observed") != observed:
            job.update(observed=observed, terminal_passes=0, next_attempt=0)
            if job["state"] == "complete":
                job.update(enabled=True, state="queued")
        self._write(db, intent["id"], job)

    def tracking(self, identity: str, enabled: bool) -> dict:
        """Change fill-read scheduling only; never cancel or change a venue order."""
        with self.trading.lifecycle.lock(identity), self.store.db() as db:
            db.execute("BEGIN IMMEDIATE")
            intent = self.trading.lifecycle.read(db, identity)
            if not intent.get("exchange_order_id") or intent["status"] == "preview":
                raise ValueError("A confirmed native order ID is required for execution checks.")
            self.schedule(db, intent)
            job = self._read(db, identity)
            if job is None:
                raise ValueError("A confirmed native order ID is required for execution checks.")
            job.update(enabled=enabled, state="queued" if enabled else "paused", next_attempt=0, failures=0)
            if enabled:
                job["terminal_passes"] = 0
            self._write(db, identity, job)
        return self.detail(identity)

    def detail(self, identity: str) -> dict:
        """Read a coherent local snapshot without provider calls or new import jobs."""
        with self.store.db() as db:
            db.execute("BEGIN")
            intent = self.trading.lifecycle.read(db, identity)
            job = self._read(db, identity)
            fill_revision = AccountLedger.order_revision(db, intent)
            intent["recovery"] = self.trading.recovery.summary(db, intent)
            rows = db.execute(
                "SELECT payload FROM account_fills WHERE account_id=? AND symbol=? "
                "AND json_extract(payload,'$.order_id')=? ORDER BY timestamp_ms,id LIMIT ?",
                (
                    intent["request"]["connection_id"],
                    intent["request"]["symbol"],
                    intent.get("exchange_order_id", ""),
                    READ_LIMIT + 1,
                ),
            ).fetchall()
        fills = [json.loads(row[0]) for row in rows]
        summary = summarize(intent, fills, job)
        return {
            "order": intent,
            "fill_revision": fill_revision,
            "reconciliation": summary,
            "fills": fills[:200],
            "has_more": len(fills) > 200,
        }

    def sync(self, identity: str, *, manual: bool = False) -> dict:
        """Read and commit at most one page; failures preserve fills and cursor together."""
        with self.trading.lifecycle.lock(identity):
            with self.store.db() as db:
                intent = self.trading.lifecycle.read(db, identity)
                if not intent.get("exchange_order_id") or intent["status"] == "preview":
                    raise ValueError(
                        "No confirmed native order ID. Inspect the venue using the client order ID; never resubmit."
                    )
                self.schedule(db, intent)
                job = self._read(db, identity)
            if job is None:
                raise ValueError(
                    "No confirmed native order ID. Inspect the venue using the client order ID; never resubmit."
                )
            if not manual and (not job["enabled"] or job["next_attempt"] > time.time()):
                return self.detail(identity)
            if manual:
                job["failures"] = 0
            try:
                connection = self.trading._connection(intent["request"]["connection_id"], allow_demo=True)
                if connection.exchange != intent["exchange"] or connection.sandbox != intent["sandbox"]:
                    raise ValueError("Account environment changed.")
                if not manual and not connection.active:
                    job.update(
                        state="waiting_account",
                        error="Activate this saved account to resume automatic execution checks.",
                        next_attempt=time.time() + 60,
                    )
                    with self.store.db() as db:
                        self._write(db, identity, job)
                    return self.detail(identity)
                cursor = {} if job["caught_up"] else job["cursor"]
                if not cursor and intent["exchange"] == "bybit":
                    # Skip empty years for a newly submitted order. Native cursors
                    # still exhaust every seven-day slice from its creation time.
                    cursor = {
                        "start": max(
                            1,
                            int(datetime.fromisoformat(intent["created_at"]).timestamp() * 1000) - 86_400_000,
                        )
                    }
                seen = [] if job["caught_up"] else job["seen"]
                pages = 0 if job["caught_up"] else job["pages"]
                if pages >= 100:
                    raise ccxt.NotSupported("Order import exceeds the reviewed page budget.")
                with self.trading.market.adapter(connection) as client:
                    if not hasattr(client, "fetch_order_fill_page"):
                        raise ccxt.NotSupported("Order execution import unavailable.")
                    page = client.fetch_order_fill_page(
                        intent["exchange_order_id"], intent["request"]["symbol"], cursor
                    )
                if not isinstance(page, TradePage) or len(page.items) > 100:
                    raise ValueError("Invalid execution page.")
                signature = hashlib.sha256(json.dumps(page.cursor, sort_keys=True).encode()).hexdigest()
                if not page.caught_up and (page.cursor == cursor or signature in seen):
                    raise ValueError("Order execution cursor did not advance.")
                metadata = {
                    "account_id": connection.id,
                    "account": intent["account"],
                    "exchange": intent["exchange"],
                    "environment": intent["environment"],
                    "symbol": intent["request"]["symbol"],
                }
                fills = [ledger_fill(row, metadata) for row in page.items]
                identities = {}
                for fill in fills:
                    if (
                        fill["order_id"] != intent["exchange_order_id"]
                        or fill["side"] != intent["request"]["side"]
                    ):
                        raise ValueError("Execution belongs to a different order or side.")
                    if fill["id"] in identities and identities[fill["id"]] != fill:
                        raise ValueError("Conflicting execution identity.")
                    identities[fill["id"]] = fill
                with self.store.db() as db:
                    db.execute("BEGIN IMMEDIATE")
                    for fill in identities.values():
                        previous = db.execute(
                            "SELECT payload FROM account_fills WHERE id=?", (fill["id"],)
                        ).fetchone()
                        if previous and json.loads(previous[0])["order_id"] not in {None, fill["order_id"]}:
                            raise ValueError("Execution ID was already attributed to another order.")
                    AccountLedger.upsert_fills(db, list(identities.values()), now_iso())
                    terminal = intent["status"] in TERMINAL
                    passes = job["terminal_passes"] + int(terminal and page.caught_up)
                    candidate = {**job}
                    candidate.update(
                        cursor=page.cursor,
                        seen=[*seen, signature],
                        pages=pages + 1,
                        caught_up=page.caught_up,
                        checked_at=now_iso(),
                        error=None,
                        failures=0,
                        terminal_passes=passes,
                        state="idle" if page.caught_up else "queued",
                        next_attempt=time.time() + (60 if passes == 1 else 300 if terminal else 20)
                        if page.caught_up
                        else time.time() + 1,
                    )
                    if terminal and page.caught_up and passes >= 3:
                        candidate.update(enabled=False, state="complete")
                    self._write(db, identity, candidate)
                job = candidate
            except Exception as error:
                deferred, unsupported = (
                    isinstance(error, ProviderDeferred),
                    isinstance(error, ccxt.NotSupported),
                )
                failures = job.get("failures", 0) + int(not deferred)
                job.update(
                    failures=failures,
                    state="unsupported" if unsupported else "error",
                    error="Order execution reads are unavailable for this provider or exceed the reviewed budget."
                    if unsupported
                    else "Execution check failed or evidence was invalid. Previous fills and checkpoint are retained.",
                    next_attempt=time.time()
                    + (error.retry_after if deferred else min(900, 20 * 2 ** min(failures, 6))),
                )
                if unsupported or failures >= 5:
                    job["enabled"] = False
                with self.store.db() as db:
                    self._write(db, identity, job)
        return self.detail(identity)

    def tick(self) -> None:
        """Read one due active-account page; opaque cursors and schedules survive restart."""
        with self.trading.lifecycle._worker:
            if not self.trading.lifecycle._closed:
                self._tick()

    def _tick(self) -> None:
        with self.store.db() as db:
            row = db.execute(
                "SELECT intent_id FROM order_fill_sync WHERE json_extract(payload,'$.enabled')=1 "
                "AND json_extract(payload,'$.next_attempt')<=? ORDER BY json_extract(payload,'$.next_attempt'),rowid LIMIT 1",
                (time.time(),),
            ).fetchone()
        if row:
            try:
                self.sync(row[0])
            except Exception:
                # A missing local intent/identity must not kill the shared order worker.
                with self.store.db() as db:
                    job = self._read(db, row[0])
                    if job:
                        job.update(
                            enabled=False,
                            state="error",
                            error="Confirmed local order evidence is unavailable. Review this order manually.",
                        )
                        self._write(db, row[0], job)

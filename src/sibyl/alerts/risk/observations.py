"""Bounded spot-balance valuation for alerts; no charts, performance history or writes."""

import math
import time
from datetime import UTC, datetime

from sibyl.exchanges.base import number
from sibyl.services.valuation import CURRENCY, Valuation

MAX_ASSETS = 100
MAX_SAMPLE_SECONDS = 45


class RiskReadError(ValueError):
    """A fixed, user-readable coverage/quality message, never a raw provider error."""


class RiskObservations:
    """Read exactly the pinned active accounts and feed, with explicit quality gates.

    Private balance timestamps are not consistently available. We record their
    completion/receipt times, never claim an atomic cross-exchange snapshot, and
    reject slow assemblies. Every conversion leg must have a fresh provider time.
    Configuration guards remain private and never enter API/agent evidence.
    """

    def __init__(self, market, store, *, clock=time.time):
        self.market, self.store, self.clock = market, store, clock

    def accounts(self, identities):
        """Resolve exact active identities without expanding a saved set or reading secrets."""
        rows = {row.id: row for row in self.store.connections()}
        if any(identity not in rows or not rows[identity].active for identity in identities):
            raise RiskReadError("A pinned account is inactive or disconnected. Activate it or edit the rule.")
        selected = [rows[identity] for identity in identities]
        environments = {
            "demo" if row.exchange == "demo" else "test" if row.sandbox else "production" for row in selected
        }
        if len(environments) != 1:
            raise RiskReadError("Demo, test and production funds must be watched separately.")
        return selected, environments.pop()

    @staticmethod
    def _guard(db, identities, source):
        """Compare encrypted snapshots in memory; never acquire settings locks under a DB write."""
        accounts = sorted(set(identities) | ({source[11:]} if source.startswith("connection:") else set()))
        rows = db.execute(
            "SELECT id,exchange,label,sandbox,created_at,credentials,"
            "EXISTS(SELECT 1 FROM active_accounts WHERE account_id=connections.id) "
            f"FROM connections WHERE id IN ({','.join('?' for _ in accounts)}) ORDER BY id",
            accounts,
        ).fetchall()
        profile = db.execute("SELECT value FROM workspace_settings WHERE key='data:market'").fetchone()
        return tuple(tuple(row) for row in rows), profile[0] if profile else None

    def configuration(self, identities, source):
        """Validate local setup and capture a private encrypted-configuration guard, without HTTP."""
        with self.store.db() as db:
            db.execute("BEGIN")
            guard = self._guard(db, identities, source)
        rows, environment = self.accounts(identities)
        with self.market.snapshot(source):
            metadata = self.market.metadata()
            if (environment == "demo") != (metadata["source"] == "demo"):
                raise RiskReadError(
                    "Demo accounts require the offline Demo feed; exchange funds require a live reference feed."
                )
            info = {
                key: metadata[key]
                for key in ("source", "source_label", "source_kind", "provider", "environment")
            }
        accounts = [
            {
                key: row.model_dump(mode="json")[key]
                for key in ("id", "exchange", "label", "sandbox", "created_at")
            }
            for row in rows
        ]
        config = dict(accounts=accounts, environment=environment, source_info=info)
        with self.store.db() as db:
            self.current(dict(account_ids=identities, source=source), guard, db)
        return config, guard

    def current(self, rule, guard, db):
        """Validate under the commit's SQLite snapshot, without Python locks or provider calls."""
        if self._guard(db, rule["account_ids"], rule["source"]) != guard:
            raise RiskReadError(
                "Account or reference-feed configuration changed during this check; waiting for a new check."
            )

    def fresh(self, sample):
        """Recheck receipt/quote ages at commit, after every delayed provider response."""
        now = self.clock()
        if not -0.001 <= now - datetime.fromisoformat(sample["started_at"]).timestamp() <= MAX_SAMPLE_SECONDS:
            raise RiskReadError("This valuation took too long; no risk assessment was recorded.")
        for holding in sample["holdings"]:
            if holding["asset"] == CURRENCY:
                continue
            stamp = holding["observed_at"]
            if stamp is None:
                raise RiskReadError("A conversion quote is undated; no risk assessment was recorded.")
            age = now - datetime.fromisoformat(stamp).timestamp()
            if not -60 <= age <= 300:
                raise RiskReadError(
                    "A conversion quote is stale or future-dated; no risk assessment was recorded."
                )

    def read(self, rule):
        """Assemble one all-or-nothing sample within ten accounts, 100 assets and existing quote budgets."""
        started = self.clock()
        config, guard = self.configuration(rule["account_ids"], rule["source"])
        quantities, reads = {}, []
        rows, _ = self.accounts(rule["account_ids"])
        for account in rows:
            if self.clock() - started > MAX_SAMPLE_SECONDS:
                raise RiskReadError("This valuation took too long; no risk assessment was recorded.")
            with self.market.adapter(account) as client:
                balance = client.fetch_balance()
            totals = balance.get("total") if isinstance(balance, dict) else None
            if not isinstance(totals, dict):
                raise RiskReadError("A spot balance response is incomplete; no risk assessment was recorded.")
            reads.append(
                dict(account_id=account.id, received_at=datetime.fromtimestamp(self.clock(), UTC).isoformat())
            )
            for asset, raw in totals.items():
                value = None if isinstance(raw, bool) else number(raw)
                if not isinstance(asset, str) or not asset or value is None or value < 0:
                    raise RiskReadError(
                        "A spot balance contains unsupported or invalid quantities; no risk assessment was recorded."
                    )
                if value:
                    quantities[asset] = quantities.get(asset, 0) + value
            if len(quantities) > MAX_ASSETS:
                raise RiskReadError(
                    "This account set exceeds the 100-asset risk valuation budget. Watch a smaller account set."
                )
        with self.market.snapshot(rule["source"]):
            with self.store.db() as db:
                self.current(rule, guard, db)
            valuation = Valuation(self.market)
            holdings = []
            for asset, quantity in quantities.items():
                if not math.isfinite(quantity):
                    raise RiskReadError("A combined quantity is invalid; no risk assessment was recorded.")
                quote = valuation.price(asset)
                if quote["status"] not in {"fresh", "identity"} or quote["price"] is None:
                    raise RiskReadError(
                        "Some holdings could not be priced with fresh dated conversion quotes; no risk assessment was recorded."
                    )
                value = quantity * quote["price"]
                if not math.isfinite(value) or value < 0:
                    raise RiskReadError(
                        "A reference holding value is invalid; no risk assessment was recorded."
                    )
                holdings.append(
                    dict(asset=asset, value=value, path=quote["path"], observed_at=quote["observed_at"])
                )
        total = math.fsum(row["value"] for row in holdings)
        if not math.isfinite(total):
            raise RiskReadError("The account total is invalid; no risk assessment was recorded.")
        for row in holdings:
            row["allocation"] = row["value"] / total * 100 if total else 0
        sample = dict(
            **config,
            currency=CURRENCY,
            total=total,
            holdings=sorted(holdings, key=lambda row: row["value"], reverse=True),
            balance_reads=reads,
            started_at=datetime.fromtimestamp(started, UTC).isoformat(),
            as_of=datetime.fromtimestamp(self.clock(), UTC).isoformat(),
            complete=True,
        )
        self.fresh(sample)
        return sample, guard

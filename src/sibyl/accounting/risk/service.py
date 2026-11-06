"""Explicit saved account-basket studies over frozen current holdings and public history."""

import json
import math
import threading
from collections import defaultdict
from datetime import UTC, datetime
from uuid import uuid4

import ccxt

from sibyl.accounting.risk.engine import DAY, analyze, closes, converted
from sibyl.forecasting.engine import fingerprint
from sibyl.market_data.archive import milliseconds, now_ms
from sibyl.services.portfolio.valuation import CURRENCY, Valuation


class HistoricalRisk:
    def __init__(self, owner, market, store):
        self.owner, self.market, self.store = owner, market, store
        self.lock = threading.Lock()
        with store.db() as db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS account_risk_studies(id TEXT PRIMARY KEY,metadata TEXT NOT NULL,payload TEXT NOT NULL)"
            )

    def list(self, scope):
        with self.store.db() as db:
            return {
                "items": [
                    json.loads(row[0])
                    for row in db.execute(
                        "SELECT metadata FROM account_risk_studies WHERE json_extract(metadata,'$.scope')=? ORDER BY rowid DESC LIMIT 50",
                        (scope,),
                    )
                ]
            }

    def get(self, identity):
        with self.store.db() as db:
            row = db.execute("SELECT payload FROM account_risk_studies WHERE id=?", (identity,)).fetchone()
        if not row:
            raise LookupError("Account risk study not found.")
        return json.loads(row[0])

    def delete(self, identity):
        with self.store.db() as db:
            if not db.execute("DELETE FROM account_risk_studies WHERE id=?", (identity,)).rowcount:
                raise LookupError("Account risk study not found.")

    def create(self, body):
        if not self.lock.acquire(blocking=False):
            raise ValueError("Another account risk study is running. Try again shortly.")
        try:
            with self.store.db() as db:
                if db.execute("SELECT COUNT(*) FROM account_risk_studies").fetchone()[0] >= 100:
                    raise ValueError("Keep at most 100 saved risk studies. Remove an old study first.")
            with self.market.snapshot():
                result = self._create(body)
            with self.store.db() as db:
                db.execute("BEGIN IMMEDIATE")
                if db.execute("SELECT COUNT(*) FROM account_risk_studies").fetchone()[0] >= 100:
                    raise ValueError("Keep at most 100 saved risk studies. Remove an old study first.")
                metadata = {
                    key: result[key]
                    for key in (
                        "id",
                        "scope",
                        "created_at",
                        "source",
                        "mode",
                        "requested_days",
                        "selected_assets",
                        "fingerprint",
                    )
                }
                db.execute(
                    "INSERT INTO account_risk_studies VALUES(?,?,?)",
                    (result["id"], json.dumps(metadata), json.dumps(result, allow_nan=False)),
                )
            return result
        finally:
            self.lock.release()

    def _create(self, body):
        metadata = self.market.metadata()
        if not metadata["capabilities"]["candles"]:
            raise ValueError("Select a reference feed with historical candles in Settings → Market data.")
        accounts = self.owner.connections(body.scope)
        if not accounts:
            raise ValueError("Connect an active exchange account or explicitly enable Demo first.")
        amounts, failed = defaultdict(float), []
        for account in accounts:
            try:
                for asset, quantity in self.market.balance(account).items():
                    if quantity > 0:
                        amounts[asset] += quantity
            except (ccxt.BaseError, ValueError):
                failed.append(account.id)
        valuation, holdings, unpriced = Valuation(self.market), {}, []
        for asset, quantity in amounts.items():
            quote = valuation.price(asset)
            if quote["price"] is None:
                unpriced.append(asset)
            else:
                value = quantity * quote["price"]
                if not math.isfinite(value):
                    raise ValueError("Current holding values exceed the numerical range.")
                holdings[asset] = {**quote, "quantity": quantity, "value": value}
        if any(asset not in holdings for asset in body.assets):
            raise ValueError(
                "Every selected asset must be a currently held, priced asset in this account scope."
            )
        selected = {asset: holdings[asset] for asset in body.assets}
        value = sum(row["value"] for row in selected.values())
        if not math.isfinite(value) or value <= 0:
            raise ValueError("The selected basket needs finite positive current value.")
        known_value = sum(row["value"] for row in holdings.values())
        routes = {asset: row["route"] for asset, row in selected.items()}
        symbols = sorted({leg["symbol"] for route in routes.values() for leg in route})
        if len(symbols) > 16:
            raise ValueError(
                "This basket needs more than 16 historical conversion legs. Choose fewer assets."
            )
        raw = {symbol: self.market.candles(symbol, body.days + 1, "1d") for symbol in symbols}
        history = {symbol: closes(rows) for symbol, rows in raw.items()}
        end = now_ms() // DAY * DAY
        anchors = range(end - (body.days + 1) * DAY, end, DAY)
        converted_history = {asset: converted(route, history, anchors) for asset, route in routes.items()}
        result = analyze(converted_history, {asset: row["value"] / value for asset, row in selected.items()})
        all_selected = len(selected) == len(holdings) and not unpriced and not failed
        return {
            **result,
            "id": uuid4().hex,
            "created_at": datetime.now(UTC).isoformat(),
            "scope": body.scope,
            "mode": self.owner.selection.mode(accounts),
            "source": metadata,
            "currency": CURRENCY,
            "requested_days": body.days,
            "selected_assets": body.assets,
            "accounts": [
                {"id": a.id, "label": a.label, "exchange": a.exchange, "sandbox": a.sandbox} for a in accounts
            ],
            "valuation_complete": not failed and not unpriced,
            "entire_account_basket": all_selected,
            "selected_value": value,
            "known_priced_value": known_value,
            "share_of_priced_value_pct": value / known_value * 100,
            "excluded_unpriced": unpriced,
            "failed_accounts": failed,
            "valuation": list(selected.values()),
            "history_lag_days": max(0, (end - milliseconds(result["end"])) // DAY),
            "inputs": {
                "market_candles": raw,
                "converted_closes": {
                    asset: [{"timestamp": stamp, "close": price} for stamp, price in sorted(rows.items())]
                    for asset, rows in converted_history.items()
                },
            },
            "fingerprint": fingerprint(
                {
                    "accounts": [a.id for a in accounts],
                    "valuation": selected,
                    "candles": raw,
                    "request": body.model_dump(),
                }
            ),
            "coverage_note": "The selected basket covers the full observed, priced account scope."
            if all_selected
            else "Subset analysis only. Weights are renormalized within the selected priced assets; unselected/unpriced holdings or failed accounts can materially change whole-account risk.",
        }

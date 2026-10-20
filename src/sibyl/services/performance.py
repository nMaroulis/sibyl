"""Market-level FIFO evidence over retained fills, never inferred account returns."""

import json
import math
import time
from collections import Counter, defaultdict, deque
from datetime import UTC, datetime
from decimal import Decimal, localcontext

import ccxt
from pydantic import AwareDatetime, Field, field_validator, model_validator

from sibyl.exchanges.base import number
from sibyl.models import OrderRequest, Request
from sibyl.services.ledger import ledger_fill
from sibyl.services.market import Market
from sibyl.services.valuation import MAX_SECONDS, Valuation
from sibyl.storage import Store

MAX_FILLS = 20_000
MAX_MARKS = 20
ZERO = Decimal(0)
NOTE = (
    "Market-level FIFO over all retained fills and user-entered opening inventory. "
    "Accounts, environments and quote currencies stay separate. Transfers, cash flows, "
    "cross-market basis and historical conversion of other-currency fees are not included. "
    "Matched results are not complete account returns or tax results."
)


def decimal(value) -> Decimal:
    """Use recorded decimal text, rejecting non-finite accounting inputs."""
    result = Decimal(str(value))
    if not result.is_finite():
        raise ValueError("Non-finite accounting value.")
    return result


def public(value: Decimal | None) -> float | None:
    """Keep unsupported/overflow values nullable at the JSON boundary."""
    if value is None:
        return None
    result = float(value)
    return result if math.isfinite(result) else None


class OpeningInventory(Request):
    """A user's explicit pre-history quantity and optional total cost in this pair's quote."""

    symbol: str
    quantity: Decimal = Field(gt=0, le=Decimal("1e24"))
    total_cost: Decimal | None = Field(default=None, ge=0, le=Decimal("1e30"))
    as_of: AwareDatetime

    @field_validator("symbol")
    @classmethod
    def canonical_symbol(cls, value: str) -> str:
        return OrderRequest.valid_symbol(value)

    @model_validator(mode="after")
    def historical_date(self):
        """An opening assertion must precede current time, in an explicit timezone."""
        if self.as_of > datetime.now(UTC) or self.as_of.timestamp() < 0:
            raise ValueError("Opening inventory must have a past date with a timezone.")
        return self


def fifo(fills: list[dict], opening: dict | None = None) -> dict:
    """Match exact-market lots chronologically, with decimal quantity/cost arithmetic.

    Quote fees adjust acquisition cost or disposal proceeds. Base fees adjust
    received/consumed inventory. Rebates retain their signs. Missing fees and
    third-currency fees prevent a final net figure. Unknown-basis quantities are
    consumed in FIFO order and never silently assigned zero cost. Partial sales
    report only their known matched portion, with unknown portions disclosed.
    """
    with localcontext() as context:
        context.prec = 50
        lots, issues, fee_totals = deque(), [], defaultdict(lambda: ZERO)
        missing_fees, unknown_sold, realized, known_sold = 0, ZERO, ZERO, ZERO
        disposals, curve = [], []
        if opening:
            lots.append(
                {
                    "quantity": decimal(opening["quantity"]),
                    "cost": decimal(opening["total_cost"]) if opening["total_cost"] is not None else None,
                }
            )
        ties = any(count > 1 for count in Counter(row["timestamp_ms"] for row in fills).values())
        if ties:
            issues.append("Some fills share a timestamp; their execution ordering is not established.")
        blocked, estimated_notional, unconverted = False, False, set()
        for row in sorted(fills, key=lambda item: (item["timestamp_ms"], item["id"])):
            base, quote = row["symbol"].split("/")
            quantity = decimal(row["quantity"])
            notional = (
                decimal(row["notional"]) if row["notional"] is not None else quantity * decimal(row["price"])
            )
            estimated_notional |= row["notional"] is None
            base_fee, quote_fee = ZERO, ZERO
            if not row["fees_known"]:
                missing_fees += 1
            for fee in row["fees"]:
                currency, cost = fee["currency"], fee["cost"]
                if currency is None or cost is None:
                    continue
                cost = decimal(cost)
                fee_totals[currency] += cost
                if currency == base:
                    base_fee += cost
                elif currency == quote:
                    quote_fee += cost
                elif cost:
                    unconverted.add(currency)
            if blocked:
                continue
            if row["side"] == "buy":
                received, cost = quantity - base_fee, notional + quote_fee
                if received <= 0 or cost < 0:
                    blocked = True
                    issues.append(
                        "A fill has inconsistent net quantity or cost; subsequent lot matching is unavailable."
                    )
                    continue
                # An unknown-currency/amount fee may change inventory itself.
                lots.append({"quantity": received, "cost": cost if row["fees_known"] else None})
                continue
            consumed, proceeds = quantity + base_fee, notional - quote_fee
            if consumed <= 0 or proceeds < 0:
                blocked = True
                issues.append(
                    "A disposal has inconsistent net quantity or proceeds; subsequent lot matching is unavailable."
                )
                continue
            remaining, known, matched_cost, unknown = consumed, ZERO, ZERO, ZERO
            while remaining > 0 and lots:
                lot = lots[0]
                matched = min(remaining, lot["quantity"])
                fraction = matched / lot["quantity"]
                if lot["cost"] is None:
                    unknown += matched
                else:
                    cost = lot["cost"] * fraction
                    matched_cost += cost
                    known += matched
                    lot["cost"] -= cost
                lot["quantity"] -= matched
                remaining -= matched
                if lot["quantity"] == 0:
                    lots.popleft()
            unknown += remaining
            known_proceeds = proceeds * known / consumed
            pnl = known_proceeds - matched_cost
            realized += pnl
            known_sold += known
            unknown_sold += unknown
            disposals.append(
                {
                    "id": row["id"],
                    "trade_id": row["trade_id"],
                    "timestamp": row["created_at"],
                    "quantity": public(consumed),
                    "known_quantity": public(known),
                    "unknown_quantity": public(unknown),
                    "matched_cost": public(matched_cost),
                    "matched_proceeds": public(known_proceeds),
                    "pnl_before_other_fees": public(pnl),
                }
            )
            curve.append({"timestamp": row["created_at"], "value": public(realized)})
        if missing_fees:
            issues.append(
                f"{missing_fees} fills have incomplete fee data; inventory and net P&L may be incomplete."
            )
        if unconverted:
            issues.append(
                "Fees/rebates in "
                + ", ".join(sorted(unconverted))
                + " are retained in native units, without historical quote conversion."
            )
        if estimated_notional:
            issues.append(
                "Some execution notionals use reported price × quantity rather than a reported total."
            )
        if unknown_sold:
            issues.append(
                "Some disposed units have no opening/purchase cost basis; their proceeds are excluded from matched P&L."
            )
        net_known = not (missing_fees or unconverted or ties or blocked or estimated_notional)
        open_quantity = sum((lot["quantity"] for lot in lots), ZERO)
        known_open_quantity = sum((lot["quantity"] for lot in lots if lot["cost"] is not None), ZERO)
        open_cost = sum((lot["cost"] for lot in lots if lot["cost"] is not None), ZERO)
        if any(public(value) is None for value in (realized, open_quantity, open_cost, unknown_sold)):
            issues.append("Accounting values exceed the supported display range.")
            net_known, blocked = False, True
        return {
            "fill_count": len(fills),
            "disposal_count": len(disposals),
            "matched_sold_quantity": public(known_sold),
            "unknown_sold_quantity": public(unknown_sold),
            "realized_before_other_fees": public(realized),
            "net_matched_realized": public(realized) if net_known else None,
            "open_quantity": public(open_quantity),
            "known_open_quantity": public(known_open_quantity),
            "known_open_cost": public(open_cost),
            "unknown_open_quantity": public(open_quantity - known_open_quantity),
            "fee_totals": {key: public(value) for key, value in fee_totals.items()},
            "missing_fee_count": missing_fees,
            "unconverted_fee_currencies": sorted(unconverted),
            "net_known": net_known,
            "matching_blocked": blocked,
            "disposals": list(reversed(disposals[-100:])),
            "curve": curve[-500:],
            "issues": issues,
        }


class AccountPerformance:
    """Recompute retained exact-market FIFO and mark reconciled open lots on demand.

    Opening inventory is a user assertion, stored separately from immutable
    imported execution facts. Reads never submit orders or queue imports. A
    current account balance must match the single-market lot quantity before an
    unrealized result is available. This is not full account reconciliation.
    """

    def __init__(self, market: Market, store: Store):
        self.market, self.store = market, store
        with store.db() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS opening_inventory (
                    account_id TEXT NOT NULL, symbol TEXT NOT NULL, quantity TEXT NOT NULL,
                    total_cost TEXT, as_of TEXT NOT NULL, updated_at TEXT NOT NULL,
                    PRIMARY KEY(account_id, symbol)
                );
                CREATE TABLE IF NOT EXISTS opening_inventory_audit (
                    id INTEGER PRIMARY KEY, account_id TEXT NOT NULL, symbol TEXT NOT NULL,
                    changed_at TEXT NOT NULL, payload TEXT NOT NULL
                );
            """)

    def save_opening(self, account_id: str, request: OpeningInventory) -> dict:
        """Save a pre-fill basis assertion and its audit snapshot in one transaction."""
        with self.store.db() as db:
            db.execute("BEGIN IMMEDIATE")
            if not db.execute("SELECT 1 FROM connections WHERE id=?", (account_id,)).fetchone():
                raise LookupError("Connection not found.")
            first = db.execute(
                "SELECT MIN(timestamp_ms) FROM account_fills WHERE account_id=? AND symbol=?",
                (account_id, request.symbol),
            ).fetchone()[0]
            if first is not None and request.as_of.timestamp() * 1000 >= first:
                raise ValueError(
                    "Opening inventory must be dated before the first retained fill for this market."
                )
            now = datetime.now(UTC).isoformat()
            row = {
                "account_id": account_id,
                "symbol": request.symbol,
                "quantity": str(request.quantity),
                "total_cost": str(request.total_cost) if request.total_cost is not None else None,
                "as_of": request.as_of.astimezone(UTC).isoformat(),
                "updated_at": now,
            }
            previous = db.execute(
                "SELECT * FROM opening_inventory WHERE account_id=? AND symbol=?",
                (account_id, request.symbol),
            ).fetchone()
            db.execute(
                "INSERT INTO opening_inventory VALUES(?,?,?,?,?,?) ON CONFLICT(account_id,symbol) DO UPDATE SET quantity=excluded.quantity,total_cost=excluded.total_cost,as_of=excluded.as_of,updated_at=excluded.updated_at",
                tuple(row.values()),
            )
            db.execute(
                "INSERT INTO opening_inventory_audit(account_id,symbol,changed_at,payload) VALUES(?,?,?,?)",
                (
                    account_id,
                    request.symbol,
                    now,
                    json.dumps(
                        {"action": "save", "before": dict(previous) if previous else None, "after": row}
                    ),
                ),
            )
        return row

    def remove_opening(self, account_id: str, symbol: str) -> None:
        """Remove an assertion, retaining its previous values in the local audit history."""
        with self.store.db() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT * FROM opening_inventory WHERE account_id=? AND symbol=?", (account_id, symbol)
            ).fetchone()
            if row:
                db.execute(
                    "INSERT INTO opening_inventory_audit(account_id,symbol,changed_at,payload) VALUES(?,?,?,?)",
                    (
                        account_id,
                        symbol,
                        datetime.now(UTC).isoformat(),
                        json.dumps({"action": "remove", "before": dict(row), "after": None}),
                    ),
                )
                db.execute(
                    "DELETE FROM opening_inventory WHERE account_id=? AND symbol=?", (account_id, symbol)
                )

    def audit(self, account_id: str, symbol: str) -> dict:
        """Read the latest fifty assertion edits, including disconnected accounts."""
        with self.store.db() as db:
            rows = db.execute(
                "SELECT changed_at,payload FROM opening_inventory_audit WHERE account_id=? AND symbol=? ORDER BY id DESC LIMIT 50",
                (account_id, symbol),
            ).fetchall()
        return {"items": [{"changed_at": row[0], **json.loads(row[1])} for row in rows], "limit": 50}

    def markets(self) -> dict:
        """List retained markets, including opening-only inventory without an import job."""
        with self.store.db() as db:
            rows = db.execute(
                "SELECT symbol FROM account_fills UNION SELECT symbol FROM opening_inventory ORDER BY symbol"
            ).fetchall()
        return {"symbols": [row[0] for row in rows]}

    @staticmethod
    def example() -> dict:
        """Compute an isolated educational fixture without writing fills, balances or orders."""
        opening = {
            "account_id": "example",
            "symbol": "BTC/USDT",
            "quantity": "0.2",
            "total_cost": "8000",
            "as_of": "2024-01-01T00:00:00+00:00",
            "updated_at": "2024-01-01T00:00:00+00:00",
        }
        scope = {
            "account_id": "example",
            "account": "Example account",
            "exchange": "demo",
            "environment": "demo",
            "symbol": "BTC/USDT",
        }
        fills = [
            ledger_fill(
                {
                    "id": str(index),
                    "order": None,
                    "symbol": "BTC/USDT",
                    "timestamp": 1_704_153_600_000 + index * 86400000,
                    "side": side,
                    "amount": quantity,
                    "price": price,
                    "cost": quantity * price,
                    "fees": [{"currency": currency, "cost": fee}],
                },
                scope,
            )
            for index, (side, quantity, price, currency, fee) in enumerate(
                [
                    ("buy", 0.1, 45000, "USDT", 4.5),
                    ("sell", 0.15, 52000, "USDT", 7.8),
                    ("buy", 0.02, 50000, "BTC", 0.00002),
                    ("sell", 0.08, 54000, "USDT", 4.32),
                ]
            )
        ]
        result = fifo(fills, opening)
        return {
            "example": True,
            "fill_count": len(fills),
            "complete_history": False,
            "basis_method": "FIFO by account and exact market",
            "as_of": "2024-01-05T00:00:00+00:00",
            "note": NOTE,
            "items": [
                {
                    **scope,
                    "base": "BTC",
                    "quote": "USDT",
                    **result,
                    "opening": opening,
                    "opening_applied": True,
                    "active": False,
                    "cross_market": False,
                    "unrealized": None,
                    "mark_price": None,
                    "balance_quantity": None,
                    "mark_status": "not_requested",
                    "mark_note": "Educational fixture only; no wallet balance or current mark is attached.",
                }
            ],
            "totals": [
                {
                    "environment": "demo",
                    "quote": "USDT",
                    "markets": 1,
                    "matched_realized": result["realized_before_other_fees"],
                    "net_matched_realized": result["net_matched_realized"],
                    "unrealized": None,
                }
            ],
        }

    def report(
        self, account_id: str = "", symbol: str = "", environment: str = "", mark: bool = False
    ) -> dict:
        """Read one consistent ledger/basis snapshot, without applying page/side filters."""
        clauses, values = [], []
        for column, value in [
            ("account_id", account_id),
            ("symbol", symbol),
            ("json_extract(payload,'$.environment')", environment),
        ]:
            if value:
                clauses.append(f"{column}=?")
                values.append(value)
        where = " AND ".join(clauses) or "1=1"
        with self.store.db() as db:
            db.execute("BEGIN")
            count = db.execute(f"SELECT COUNT(*) FROM account_fills WHERE {where}", values).fetchone()[0]
            if count > MAX_FILLS:
                raise ValueError(
                    "This report supports up to 20,000 fills. Choose a single account or market; history is never silently truncated."
                )
            fills = [
                json.loads(row[0])
                for row in db.execute(
                    f"SELECT payload FROM account_fills WHERE {where} ORDER BY timestamp_ms,id", values
                )
            ]
            basis = [
                dict(row)
                for row in db.execute(
                    "SELECT * FROM opening_inventory" + (" WHERE account_id=?" if account_id else ""),
                    (account_id,) if account_id else (),
                )
                if not symbol or row["symbol"] == symbol
            ]
            # Detect outside-market inventory even when this report filters to one pair.
            inventory_markets = defaultdict(set)
            for identity, pair in db.execute(
                "SELECT account_id,symbol FROM account_fills UNION SELECT account_id,symbol FROM opening_inventory"
            ):
                for asset in pair.split("/"):
                    inventory_markets[(identity, asset)].add(pair)
        accounts = {row.id: row for row in self.store.connections()}
        grouped = defaultdict(list)
        for row in fills:
            grouped[(row["account_id"], row["symbol"])].append(row)
        openings = {(row["account_id"], row["symbol"]): row for row in basis}
        for key in openings:
            if not environment or (key[0] in accounts and self._environment(accounts[key[0]]) == environment):
                grouped.setdefault(key, [])
        rows = []
        for (identity, pair), executions in sorted(grouped.items()):
            connection = accounts.get(identity)
            scope = (
                executions[0]
                if executions
                else {
                    "account_id": identity,
                    "account": connection.label if connection else "Disconnected account",
                    "exchange": connection.exchange if connection else "",
                    "environment": self._environment(connection) if connection else "unknown",
                }
            )
            opening = openings.get((identity, pair))
            overlap = (
                opening
                and executions
                and datetime.fromisoformat(opening["as_of"]).timestamp() * 1000
                >= min(row["timestamp_ms"] for row in executions)
            )
            summary = fifo(executions, None if overlap else opening)
            if overlap:
                summary["issues"].append(
                    "Opening inventory now overlaps an earlier imported fill and is ignored. Review its date and quantity."
                )
                summary["net_known"] = False
                summary["net_matched_realized"] = None
            rows.append(
                {
                    **{key: scope[key] for key in ("account_id", "account", "exchange", "environment")},
                    "symbol": pair,
                    "base": pair.split("/")[0],
                    "quote": pair.split("/")[1],
                    "first_fill_at": executions[0]["created_at"] if executions else None,
                    **summary,
                    "opening": opening,
                    "opening_applied": bool(opening and not overlap),
                    "active": bool(connection and connection.active),
                    "unrealized": None,
                    "mark_price": None,
                    "balance_quantity": None,
                    "mark_status": "not_requested",
                    "mark_note": "Refresh current marks to compare FIFO inventory with an active account balance.",
                }
            )
        for row in rows:
            if len(inventory_markets[(row["account_id"], row["base"])]) > 1:
                row["issues"].append(
                    "This asset appears in other markets on this account. Cross-market cost basis is not reconstructed."
                )
                row["cross_market"] = True
                row["net_known"] = False
                row["net_matched_realized"] = None
            else:
                row["cross_market"] = False
        if mark and rows:
            self._mark(rows, accounts)
        totals = defaultdict(
            lambda: {
                "matched_realized": ZERO,
                "matched_known": True,
                "net_matched_realized": ZERO,
                "net_known": True,
                "unrealized": ZERO,
                "unrealized_known": True,
                "markets": 0,
            }
        )
        for row in rows:
            total = totals[(row["environment"], row["quote"])]
            total["matched_known"] &= row["realized_before_other_fees"] is not None
            if row["realized_before_other_fees"] is not None:
                total["matched_realized"] += decimal(row["realized_before_other_fees"])
            total["net_known"] &= row["net_matched_realized"] is not None
            if row["net_matched_realized"] is not None:
                total["net_matched_realized"] += decimal(row["net_matched_realized"])
            total["unrealized_known"] &= row["unrealized"] is not None
            if row["unrealized"] is not None:
                total["unrealized"] += decimal(row["unrealized"])
            total["markets"] += 1
        return {
            "items": rows,
            "fill_count": count,
            "complete_history": False,
            "basis_method": "FIFO by account and exact market",
            "totals": [
                {
                    "environment": key[0],
                    "quote": key[1],
                    "markets": total["markets"],
                    "matched_realized": public(total["matched_realized"]) if total["matched_known"] else None,
                    "net_matched_realized": public(total["net_matched_realized"])
                    if total["net_known"]
                    else None,
                    "unrealized": public(total["unrealized"]) if total["unrealized_known"] else None,
                }
                for key, total in sorted(totals.items())
            ],
            "as_of": datetime.now(UTC).isoformat(),
            "note": NOTE,
        }

    @staticmethod
    def _environment(connection) -> str:
        return "demo" if connection.exchange == "demo" else "test" if connection.sandbox else "production"

    def _mark(self, rows: list[dict], accounts: dict) -> None:
        """Use one frozen feed and cached balances; never value unknown/reconciled-away lots."""
        balances = {}
        try:
            with self.market.snapshot():
                valuation = Valuation(self.market)
                for index, row in enumerate(rows):
                    row.update(mark_status="unavailable", mark_source=valuation.metadata)
                    connection = accounts.get(row["account_id"])
                    if index >= MAX_MARKS or time.monotonic() - valuation.started > MAX_SECONDS:
                        row["mark_note"] = "Mark budget reached. Filter to a single account or market."
                        continue
                    if not connection or not connection.active:
                        row["mark_note"] = "Activate this saved account to read its current balance."
                        continue
                    if valuation.metadata["source"] == "demo" and row["environment"] != "demo":
                        row["mark_note"] = "Choose a real market-data source to mark exchange inventory."
                        continue
                    if row["cross_market"] or row["matching_blocked"]:
                        row["mark_note"] = (
                            "Cross-market or blocked inventory cannot be reconciled by this report."
                        )
                        continue
                    if connection.id not in balances:
                        try:
                            balances[connection.id] = {
                                item["asset"]: item["total"]
                                for item in self.market.account_balances(connection)
                            }
                        except (ccxt.BaseError, ValueError):
                            balances[connection.id] = None
                    balance = balances[connection.id]
                    if balance is None:
                        row["mark_note"] = "The current account balance is unavailable."
                        continue
                    actual = number(balance.get(row["base"], 0))
                    row["balance_quantity"] = actual
                    expected = row["open_quantity"]
                    if (
                        actual is None
                        or expected is None
                        or not math.isclose(actual, expected, rel_tol=1e-8, abs_tol=1e-10)
                    ):
                        row["mark_note"] = (
                            "Current balance differs from FIFO inventory. Add opening inventory or reconcile transfers/missing fills."
                        )
                        continue
                    if row["unknown_open_quantity"] or not row["net_known"]:
                        row["mark_note"] = "Open inventory cost or fee coverage is incomplete."
                        continue
                    if expected == 0:
                        row.update(
                            unrealized=0.0,
                            mark_status="closed",
                            mark_note="No open inventory; current balance is zero.",
                        )
                        continue
                    base, quote = valuation.price(row["base"]), valuation.price(row["quote"])
                    if base["price"] is None or quote["price"] is None:
                        row["mark_note"] = "A fresh conversion rate is unavailable from the selected feed."
                        continue
                    price = public(decimal(base["price"]) / decimal(quote["price"]))
                    if price is None:
                        continue
                    unrealized = expected * price - row["known_open_cost"]
                    if not math.isfinite(price) or not math.isfinite(unrealized):
                        continue
                    row.update(
                        mark_price=price,
                        unrealized=unrealized,
                        mark_status="undated" if "undated" in {base["status"], quote["status"]} else "fresh",
                        mark_note="Reference mark of balance-matched known lots. Future disposal fees are not included.",
                        mark_routes={"base": base["route"], "quote": quote["route"]},
                    )
        except (ccxt.BaseError, ValueError):
            for row in rows:
                row.update(mark_status="unavailable", mark_note="The selected reference feed is unavailable.")

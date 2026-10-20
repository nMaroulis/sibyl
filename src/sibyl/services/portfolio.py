"""Aggregate native account balances using independent, attributable spot valuation."""

import hashlib
import math
from datetime import UTC, datetime

import ccxt

from sibyl.services.accounts import Accounts
from sibyl.services.market import STABLES, Market
from sibyl.services.valuation import CURRENCY, Valuation
from sibyl.storage import Store

CASH_ASSETS = STABLES | {"EUR", "GBP", "CHF", "JPY", "AUD", "CAD"}


class Portfolio:
    """Value connected holdings independently of the personal market watchlist.

    Demo, test and production balances retain their account boundaries. Prices
    come exclusively from the configured reference feed, with no automatic
    fallback, invented cost basis or USD-stablecoin parity assumption.
    """

    def __init__(self, market: Market, store: Store):
        self.market, self.store = market, store
        self.selection = Accounts(store)

    def connections(self, scope: str = "all"):
        """Select overview accounts; sandbox funds never aggregate with production."""
        return self.selection.resolve(scope)

    def overview(self, scope: str = "all") -> dict:
        """Aggregate balances and expose coverage, conversion paths and quote quality."""
        connections = self.connections(scope)
        if not connections:
            return self._empty(scope)
        with self.market.snapshot():
            warnings, balances, venues = [], {}, []
            mode = self.selection.mode(connections)
            account_balances = {}
            for connection in connections:
                try:
                    account = self.market.balance(connection)
                    account_balances[connection.id] = account
                    venues.append(
                        {
                            "id": connection.id,
                            "name": connection.label,
                            "exchange": connection.exchange,
                            "status": "simulated" if connection.exchange == "demo" else "connected",
                            "assets": len(account),
                        }
                    )
                    for asset, quantity in account.items():
                        balances[asset] = balances.get(asset, 0) + quantity
                except (ccxt.BaseError, ValueError):
                    warnings.append(f"Could not read {connection.label}. Its balance is excluded.")
                    venues.append(
                        {
                            "id": connection.id,
                            "name": connection.label,
                            "exchange": connection.exchange,
                            "status": "error",
                            "assets": 0,
                        }
                    )
            valuation = Valuation(self.market)
            holdings, unpriced = [], []
            for asset, quantity in balances.items():
                if quantity <= 0:
                    continue
                quote = valuation.price(asset)
                contributors = [
                    {
                        "account_id": connection.id,
                        "account": connection.label,
                        "exchange": connection.exchange,
                        "quantity": account_balances.get(connection.id, {}).get(asset, 0),
                    }
                    for connection in connections
                    if account_balances.get(connection.id, {}).get(asset, 0) > 0
                ]
                value = quantity * quote["price"] if quote["price"] is not None else None
                if value is None or not math.isfinite(value):
                    unpriced.append({**quote, "quantity": quantity, "accounts": contributors})
                    continue
                holdings.append(
                    {**quote, "quantity": quantity, "value": value, "sparkline": [], "accounts": contributors}
                )
            for venue in venues:
                venue["total"] = (
                    None
                    if venue["status"] == "error"
                    else sum(
                        account_balances[venue["id"]].get(row["asset"], 0) * row["price"] for row in holdings
                    )
                )
                venue["unpriced"] = sum(
                    account_balances.get(venue["id"], {}).get(row["asset"], 0) > 0 for row in unpriced
                )
                venue["sandbox"] = next(row.sandbox for row in connections if row.id == venue["id"])
            holdings.sort(key=lambda row: row["value"], reverse=True)
            total = math.fsum(row["value"] for row in holdings)
            histories = {}
            for row in holdings:
                row["allocation"] = row["value"] / total * 100 if total else 0
                history = valuation.history(row)
                histories[row["asset"]] = {point["timestamp"]: point["value"] for point in history}
                row["sparkline"] = [point["value"] for point in history[-30:]]
            complete = not unpriced and all(row["status"] != "error" for row in venues)
            if unpriced:
                warnings.append(f"{len(unpriced)} assets are unpriced and excluded from the total.")
            undated = sum(row["status"] == "undated" for row in holdings)
            if undated:
                warnings.append(
                    f"{undated} asset prices include undated provider quotes; their age cannot be verified."
                )
            history, history_note = self._history(holdings, histories, total, complete, connections)
            previous = None
            if complete and all(row["change"] is not None and row["change"] > -100 for row in holdings):
                previous = math.fsum(row["value"] / (1 + row["change"] / 100) for row in holdings)
            if holdings and previous is None:
                warnings.append(
                    "The total daily move is unavailable because an account, price or daily change is missing."
                )
            return {
                "total": total,
                "complete": complete,
                "coverage": {"priced": len(holdings), "total": len(holdings) + len(unpriced)},
                "change": (total / previous - 1) * 100 if previous else None,
                "change_value": total - previous if previous is not None else None,
                "holdings": holdings,
                "unpriced": unpriced,
                "history": history,
                "history_note": history_note,
                "history_kind": "illustrative" if history_note.startswith("Current paper") else "observed",
                "venues": venues,
                "warnings": warnings,
                "cash": sum(row["value"] for row in holdings if row["asset"] in CASH_ASSETS),
                **valuation.metadata,
                "currency": CURRENCY,
                "mode": mode,
                "scope": scope,
                "active": bool(connections),
                "as_of": datetime.now(UTC).isoformat(),
                "valuation_note": "Reference prices in USDT, using exact conversion routes from the selected feed. "
                "USD, fiat and stablecoins require observed rates; only USDT itself equals 1 USDT. "
                "Unpriced assets and failed account reads are excluded. Prices are indicative, not executable quotes. "
                "Daily moves value current quantities and do not measure investment returns.",
            }

    def _history(self, holdings, histories, total, complete, connections) -> tuple[list, str]:
        """Keep illustrative demo history separate from complete account observations."""
        mode = self.selection.mode(connections)
        if self.market.source == "demo" and mode == "demo" and holdings:
            series = [histories[row["asset"]] for row in holdings if row["asset"] != CURRENCY]
            if complete and series and all(series):
                dates = sorted(set.intersection(*(set(rows) for rows in series)))
                return [
                    {
                        "timestamp": stamp,
                        "value": sum(
                            row["quantity"]
                            * (1 if row["asset"] == CURRENCY else histories[row["asset"]][stamp])
                            for row in holdings
                        ),
                    }
                    for stamp in dates
                ], "Current paper holdings valued at aligned historical demo rates; not actual performance."
        identities = hashlib.sha256(
            ",".join(sorted(connection.id for connection in connections)).encode()
        ).hexdigest()[:16]
        scope = f"valuation-v2:{mode}:{self.market.source}:{identities}"
        history = self.store.snapshot(total if complete and connections else None, scope=scope)
        note = "Observed complete account values in USDT; deposits and withdrawals affect the chart."
        if not complete:
            note += " No new history point is saved while assets or accounts are unavailable."
        return history, note

    def accounts(self, scope: str = "all") -> dict:
        """Value separate free/reserved/total balances with the same conversion engine."""
        connections = self.connections(scope)
        if not connections:
            return {
                **self._empty(scope),
                "accounts": [],
                "quote_rates": {CURRENCY: 1.0},
                "quote_details": {},
                "note": "Connect or activate exchange accounts, or explicitly enable Demo preview.",
            }
        with self.market.snapshot():
            valuation = Valuation(self.market)
            accounts = []
            for connection in connections:
                try:
                    balances = self.market.account_balances(connection)
                except (ccxt.BaseError, ValueError):
                    accounts.append(
                        {
                            "id": connection.id,
                            "name": connection.label,
                            "exchange": connection.exchange,
                            "sandbox": connection.sandbox,
                            "status": "error",
                            "holdings": [],
                            "total": None,
                            "unpriced": 0,
                            "complete": False,
                        }
                    )
                    continue
                holdings = []
                for balance in balances:
                    quote = valuation.price(balance["asset"])
                    value = quote["price"] * balance["total"] if quote["price"] is not None else None
                    if value is not None and not math.isfinite(value):
                        value = None
                    holdings.append(
                        {**balance, **{k: v for k, v in quote.items() if k != "asset"}, "value": value}
                    )
                unpriced = sum(row["value"] is None for row in holdings)
                accounts.append(
                    {
                        "id": connection.id,
                        "name": connection.label,
                        "exchange": connection.exchange,
                        "sandbox": connection.sandbox,
                        "status": "simulated" if connection.exchange == "demo" else "connected",
                        "holdings": sorted(holdings, key=lambda row: row["value"] or 0, reverse=True),
                        "total": math.fsum(row["value"] for row in holdings if row["value"] is not None),
                        "unpriced": unpriced,
                        "complete": unpriced == 0,
                    }
                )
            rates = {CURRENCY: 1.0}
            for asset in ("USD", "USDC", "BTC", "ETH", "EUR") if connections else ():
                quote = valuation.price(asset)
                if quote["price"] is not None:
                    rates[asset] = quote["price"]
            return {
                **valuation.metadata,
                "currency": CURRENCY,
                "mode": self.selection.mode(connections),
                "scope": scope,
                "accounts": accounts,
                "quote_rates": rates,
                "quote_details": {asset: valuation.price(asset) for asset in rates},
                "as_of": datetime.now(UTC).isoformat(),
                "note": "Reference values use observed direct, inverse or bridge conversion rates. "
                "Unpriced holdings and failed accounts are excluded from totals. "
                "Test accounts are shown separately and excluded from the portfolio overview. "
                "Free/reserved balances may be unavailable for a provider.",
            }

    @staticmethod
    def _empty(scope: str) -> dict:
        """Return first-use state without resolving a feed or fetching any account data."""
        return {
            "source": "",
            "source_label": "No active accounts",
            "mode": "none",
            "scope": scope,
            "active": False,
            "total": 0,
            "cash": 0,
            "currency": CURRENCY,
            "complete": True,
            "coverage": {"priced": 0, "total": 0},
            "change": None,
            "change_value": None,
            "holdings": [],
            "unpriced": [],
            "venues": [],
            "warnings": [],
            "history": [],
            "history_kind": "observed",
            "history_note": "No account history is recorded until accounts are activated.",
            "valuation_note": "Connect one or many exchange accounts, or explicitly enable Demo preview.",
            "as_of": datetime.now(UTC).isoformat(),
        }

"""Aggregate portfolios while keeping paper balances separate from connected accounts."""

from datetime import UTC, datetime

import ccxt

from sibyl.services.market import ASSETS, STABLES, Market
from sibyl.storage import Store


class Portfolio:
    """Value spot assets using an explicitly named market source and quote currency."""

    def __init__(self, market: Market, store: Store):
        self.market, self.store = market, store

    def connections(self):
        """Select accounts for overview totals; test and production funds never aggregate."""
        demo_mode = self.market.settings.mode == "demo"
        return [
            connection
            for connection in self.store.connections()
            if (connection.exchange == "demo") == demo_mode and not connection.sandbox
        ]

    def overview(self) -> dict:
        """Return paper fixtures in demo mode or actual balances in live mode.

        Assets without a supported quote are reported as unpriced. Connected
        account failures are visible; they never inflate the total with fixtures.
        """
        warnings, balances, venues = [], {}, []
        for connection in self.connections():
            try:
                account = self.market.balance(connection)
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
        prices = {item["asset"]: item for item in self.market.overview()["items"]}
        holdings, unpriced = [], []
        for asset, quantity in balances.items():
            if quantity <= 1e-10:
                continue
            item = prices.get(asset)
            if not item and asset not in STABLES:
                unpriced.append({"asset": asset, "quantity": quantity})
                continue
            price = 1.0 if asset in STABLES else item["price"]
            name, _, color = ASSETS.get(asset, (asset, 1, "#94b7a0"))
            holdings.append(
                {
                    "asset": asset,
                    "name": name,
                    "quantity": quantity,
                    "price": price,
                    "value": quantity * price,
                    "change": 0 if item is None else item["change"],
                    "color": color,
                    "sparkline": [] if item is None else item["sparkline"],
                }
            )
        holdings.sort(key=lambda h: h["value"], reverse=True)
        total = sum(h["value"] for h in holdings)
        for holding in holdings:
            holding["allocation"] = holding["value"] / total * 100 if total else 0
        if self.market.settings.mode == "demo":
            histories = {
                h["asset"]: self.market.candles(f"{h['asset']}/USDT", 90)
                for h in holdings
                if h["asset"] not in STABLES
            }
            dates = next(iter(histories.values()), [])
            history = [
                {
                    "timestamp": candle["timestamp"],
                    "value": sum(
                        h["quantity"] * (1 if h["asset"] in STABLES else histories[h["asset"]][i]["close"])
                        for h in holdings
                    ),
                }
                for i, candle in enumerate(dates)
            ]
            history_kind = "Current paper holdings valued at historical demo prices; not actual performance."
        else:
            history = self.store.snapshot(total)
            history_kind = "Observed account value snapshots; deposits and withdrawals affect the chart."
        previous = sum(h["value"] / (1 + h["change"] / 100) for h in holdings)
        return {
            "total": total,
            "change": (total / previous - 1) * 100 if previous else 0,
            "change_value": total - previous,
            "holdings": holdings,
            "unpriced": unpriced,
            "history": history,
            "history_note": history_kind,
            "venues": venues,
            "warnings": warnings,
            "cash": sum(h["value"] for h in holdings if h["asset"] in STABLES),
            "source": self.market.source,
            "currency": "USDT",
            "mode": self.market.settings.mode,
            "as_of": datetime.now(UTC).isoformat(),
        }

    def accounts(self) -> dict:
        """Read each account's spot quantities and approximate USDT valuation separately."""
        quotes = {item["asset"]: item for item in self.market.overview()["items"]}
        rates = {
            "USDT": 1.0,
            "USD": 1.0,
            **{asset: quotes[asset]["price"] for asset in ("BTC", "ETH") if asset in quotes},
        }
        accounts = []
        sources = []
        # Show test accounts individually, while overview totals contain no sandbox funds.
        active = {connection.id: connection for connection in self.connections()}
        active.update(
            {connection.id: connection for connection in self.store.connections() if connection.sandbox}
        )
        for connection in active.values():
            try:
                sources.append(
                    (connection.id, connection.label, connection, self.market.account_balances(connection))
                )
            except (ccxt.BaseError, ValueError):
                accounts.append(
                    {
                        "id": connection.id,
                        "name": connection.label,
                        "exchange": connection.exchange,
                        "sandbox": connection.sandbox,
                        "status": "error",
                        "holdings": [],
                        "total": 0,
                        "unpriced": 0,
                    }
                )
        for identity, name, connection, balances in sources:
            holdings = []
            for balance in balances:
                asset = balance["asset"]
                price = 1 if asset in STABLES else quotes.get(asset, {}).get("price")
                holdings.append(
                    {
                        **balance,
                        "price": price,
                        "value": price * balance["total"] if price is not None else None,
                    }
                )
            accounts.append(
                {
                    "id": identity,
                    "name": name,
                    "exchange": connection.exchange,
                    "sandbox": connection.sandbox,
                    "status": "simulated" if connection.exchange == "demo" else "connected",
                    "holdings": sorted(holdings, key=lambda item: item["value"] or 0, reverse=True),
                    "total": sum(item["value"] or 0 for item in holdings),
                    "unpriced": sum(item["value"] is None for item in holdings),
                }
            )
        return {
            "source": self.market.source,
            "accounts": accounts,
            "quote_rates": rates,
            "as_of": datetime.now(UTC).isoformat(),
            "note": "USD stablecoins are approximated at parity with USDT. Unpriced assets are excluded. Sandbox accounts contain test funds and are excluded from live portfolio totals. Free/reserved balances may be unavailable for a provider.",
        }

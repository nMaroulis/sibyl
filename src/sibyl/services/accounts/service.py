"""Explicit workspace account activation and safe portfolio aggregation scopes."""

import hashlib

from sibyl.models import Connection
from sibyl.storage import Store


class Accounts:
    """Separate saved credentials, active accounts and a page's viewing scope.

    Demo is an opt-in preview and never coexists with active exchange accounts.
    Combined totals contain production accounts, or test accounts when there are
    no production accounts. Test funds are never mixed into production totals.
    Public-market and research configuration remains independent.
    """

    def __init__(self, store: Store):
        self.store = store

    def public(self) -> dict:
        """Describe selection and available views using one credential-free snapshot."""
        saved = self.store.connections()
        active = [row for row in saved if row.active]
        mode = self.mode(active)
        primary = [row for row in active if not row.sandbox] or active
        scopes = []
        if active:
            label = (
                "Demo preview"
                if mode == "demo"
                else "Combined test accounts"
                if mode == "test"
                else "All exchanges"
            )
            scopes.append({"id": "all", "label": label, "kind": "combined", "count": len(primary)})
            for exchange in dict.fromkeys(row.exchange for row in primary):
                group = [row for row in primary if row.exchange == exchange]
                if exchange != "demo":
                    scopes.append(
                        {
                            "id": f"exchange:{exchange}",
                            "label": exchange,
                            "kind": "exchange",
                            "exchange": exchange,
                            "count": len(group),
                        }
                    )
            scopes.extend(
                {
                    "id": f"account:{row.id}",
                    "label": row.label,
                    "kind": "account",
                    "exchange": row.exchange,
                    "sandbox": row.sandbox,
                    "count": 1,
                }
                for row in active
            )
        signature = hashlib.sha256(",".join(sorted(row.id for row in active)).encode()).hexdigest()[:16]
        return {
            "mode": mode,
            "active_ids": [row.id for row in active],
            "accounts": [row.model_dump(mode="json") for row in saved],
            "scopes": scopes,
            "signature": signature,
            "demo_available": not any(row.exchange != "demo" for row in active),
        }

    @staticmethod
    def mode(accounts: list[Connection]) -> str:
        """Name the selected funds, independently of reference-price mode."""
        if not accounts:
            return "none"
        if all(row.exchange == "demo" for row in accounts):
            return "demo"
        return "test" if all(row.sandbox for row in accounts) else "live"

    def resolve(self, scope: str = "all") -> list[Connection]:
        """Resolve a validated page view from active accounts, with no provider calls."""
        active = [row for row in self.store.connections() if row.active]
        primary = [row for row in active if not row.sandbox] or active
        if scope == "all":
            return primary
        if scope.startswith("account:"):
            result = [row for row in active if row.id == scope.removeprefix("account:")]
        elif scope.startswith("exchange:"):
            result = [row for row in primary if row.exchange == scope.removeprefix("exchange:")]
        else:
            raise ValueError("Choose a combined, exchange or account portfolio view.")
        if not result:
            raise ValueError(
                "This portfolio view has no active accounts. Choose another view or activate the account in Settings."
            )
        return result

    def require_demo(self) -> None:
        """Gate manual paper funds behind an explicit Demo preview selection."""
        if self.public()["mode"] != "demo":
            raise ValueError(
                "Enable Demo preview to use the virtual wallet. Connect an exchange account for exchange funds."
            )

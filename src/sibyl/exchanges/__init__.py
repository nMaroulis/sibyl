"""Exchange client boundary; imports never open connections or perform requests."""

from typing import TYPE_CHECKING

from sibyl.exchanges.base import ExchangeClient
from sibyl.exchanges.catalog import EXCHANGES, ExchangeId, exchange_spec

if TYPE_CHECKING:
    from sibyl.storage import Store


def create_client(
    exchange: str, *, credentials: dict | None = None, sandbox: bool = False, store: "Store | None" = None
) -> ExchangeClient:
    """Construct an allowlisted real client, or an explicit offline DemoClient.

    Demo credentials and sandbox flags are rejected to prevent accidental routing
    of a real account into a simulated wallet. Real failures never fall back here.
    """
    if exchange == "demo":
        if credentials or sandbox:
            raise ValueError("Demo clients do not accept credentials or sandbox configuration.")
        from sibyl.exchanges.demo import DemoClient

        return DemoClient(store)
    exchange_spec(exchange)
    from sibyl.exchanges.providers import CLIENTS

    return CLIENTS[exchange](credentials=credentials, sandbox=sandbox)


__all__ = ["EXCHANGES", "ExchangeClient", "ExchangeId", "create_client", "exchange_spec"]

"""Explicit reference-feed capabilities; no provider requests during discovery."""

from sibyl.exchanges.catalog import EXCHANGES
from sibyl.exchanges.registry import provider_catalog

API_PROVIDERS = {
    "cryptocompare": {
        "name": "CryptoCompare",
        "description": "Aggregated prices and OHLCV from CoinDesk's legacy CCCAGG feed.",
        "requires_key": True,
        "candles": True,
        "website": "https://developers.coindesk.com/documentation/legacy/Historical/dataHistominute",
        "note": "Requires a CoinDesk / CryptoCompare API key with access to legacy endpoints. Available history depends on your plan.",
    },
    "coingecko": {
        "name": "CoinGecko Demo API",
        "description": "Live aggregated quotes using a free CoinGecko Demo API key.",
        "requires_key": True,
        "candles": False,
        "website": "https://docs.coingecko.com/demo/reference/simple-price",
        "note": "Quotes only in this adapter. CoinGecko's Demo plan is live data, separate from Sibyl's offline Demo.",
    },
    "coingecko-pro": {
        "name": "CoinGecko Pro API",
        "description": "Live aggregated quotes using your paid CoinGecko plan.",
        "requires_key": True,
        "candles": False,
        "website": "https://docs.coingecko.com/reference/simple-price",
        "note": "Quotes only in this adapter. Uses the Pro endpoint and a separate Pro credential.",
    },
}


def source_catalog(connections, profiles: dict) -> list[dict]:
    """Describe public feeds, saved accounts and provider key presence without secrets."""
    capabilities = {row["id"]: row["capabilities"] for row in provider_catalog()["items"]}
    items = [
        {
            "id": "demo",
            "name": "Demo prices",
            "kind": "demo",
            "provider": "demo",
            "environment": "demo",
            "requires_key": False,
            "has_api_key": False,
            "available": True,
            "candles": True,
            "order_book": True,
            "description": "Offline, deterministic prices and candles. No connection required.",
            "website": None,
        }
    ]
    for connection in connections:
        if connection.exchange == "demo":
            continue
        caps = capabilities[connection.exchange]
        items.append(
            {
                "id": f"connection:{connection.id}",
                "name": connection.label,
                "kind": "connection",
                "provider": connection.exchange,
                "environment": "test" if connection.sandbox else "production",
                "requires_key": False,
                "has_api_key": False,
                "available": True,
                "candles": caps["candles"] != "unavailable",
                "order_book": caps["order_book"] != "unavailable",
                "description": "Use this saved account's exchange and environment for market reads.",
                "website": None,
            }
        )
    for spec in EXCHANGES:
        caps = capabilities[spec.id]
        items.append(
            {
                "id": spec.id,
                "name": spec.name,
                "kind": "exchange",
                "provider": spec.id,
                "environment": "production",
                "requires_key": False,
                "has_api_key": False,
                "available": True,
                "candles": caps["candles"] != "unavailable",
                "order_book": caps["order_book"] != "unavailable",
                "description": "Public spot quotes, candles and order-book snapshots. No API key required.",
                "website": spec.setup_url or "https://docs.ccxt.com/",
            }
        )
    for identity, provider in API_PROVIDERS.items():
        has_key = bool(profiles.get(identity, {}).get("api_key"))
        items.append(
            {
                **provider,
                "id": identity,
                "kind": "api",
                "provider": identity,
                "environment": "production",
                "has_api_key": has_key,
                "available": has_key or not provider["requires_key"],
                "order_book": False,
            }
        )
    return items

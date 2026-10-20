"""Non-secret runtime capability discovery for the configured exchange clients."""

from functools import lru_cache

import ccxt

from sibyl.exchanges.catalog import DEMO, EXCHANGES, TEST_ENVIRONMENTS
from sibyl.exchanges.data import TIMEFRAMES
from sibyl.exchanges.providers import CLIENTS


@lru_cache(maxsize=1)
def provider_catalog() -> dict:
    """Inspect the installed CCXT version locally; never probe accounts or endpoints.

    ``native``/``emulated`` describe CCXT support, not successful network checks.
    Sandbox is exposed only where Sibyl has explicitly configured that environment.
    """
    demo = {
        **DEMO.public(),
        "verification": "offline simulator",
        "capabilities": dict.fromkeys(
            ("ticker", "candles", "order_book", "balances", "order_status", "open_orders", "trade_history"),
            "simulated",
        ),
        "timeframes": list(TIMEFRAMES),
        "history_import": "demo-keyset",
    }
    items = [demo]
    for spec in (*TEST_ENVIRONMENTS, *EXCHANGES):
        adapter = getattr(ccxt, spec.ccxt_id or spec.id)()
        capabilities = {}
        for name, method in {
            "ticker": "fetchTicker",
            "candles": "fetchOHLCV",
            "order_book": "fetchOrderBook",
            "balances": "fetchBalance",
            "order_status": "fetchOrder",
            "open_orders": "fetchOpenOrders",
            "trade_history": "fetchMyTrades",
        }.items():
            value = adapter.has.get(method)
            capabilities[name] = "emulated" if value == "emulated" else "native" if value else "unavailable"
        items.append(
            {
                **spec.public(),
                "capabilities": capabilities,
                "timeframes": list(adapter.timeframes or {}),
                "history_import": CLIENTS[spec.id].history_kind or None,
            }
        )
        session = getattr(adapter, "session", None)
        if session is not None:
            session.close()
    return {
        "items": items,
        "ccxt_version": ccxt.__version__,
        "not_configured": sorted(
            set(ccxt.exchanges) - {spec.ccxt_id or spec.id for spec in (*EXCHANGES, *TEST_ENVIRONMENTS)}
        ),
        "demo": demo,
    }

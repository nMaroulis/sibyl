"""Thin HTTP routes: validate input, call a service, return JSON contracts."""

import asyncio
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.responses import StreamingResponse

from sibyl import __version__
from sibyl.agents.providers import ProviderId
from sibyl.api.app import Services
from sibyl.exchanges.registry import provider_catalog
from sibyl.models import (
    AccountActivation,
    AgentRequest,
    BacktestRequest,
    CancelOrderConfirm,
    Connection,
    ConnectionCreate,
    ExchangeOrderConfirm,
    ExchangeOrderRequest,
    OrderRequest,
    OrderTracking,
    Timeframe,
)
from sibyl.services.account_sync import AccountSyncRequest
from sibyl.services.alerts import PriceAlertAction, PriceAlertCreate, alert_example
from sibyl.services.analytics import analyze, correlation, forecast
from sibyl.services.data_settings import MarketSettingsRequest, NewsSettingsRequest
from sibyl.services.funding_sync import FundingSyncRequest
from sibyl.services.llm_settings import ModelSettingsRequest
from sibyl.services.market import TIMEFRAMES
from sibyl.services.performance import OpeningInventory
from sibyl.services.reporting import trading_report
from sibyl.services.roadmap import implementation_status
from sibyl.services.strategies import CATALOG, backtest
from sibyl.services.transfer_reconciliation import TransferConfirm, TransferPair
from sibyl.services.watchlists import WatchlistItem, WatchlistOrder

router = APIRouter()


def services(request: Request) -> Services:
    """Resolve application-scoped services without module-level singleton state."""
    return request.app.state.services


S = Annotated[Services, Depends(services)]
Symbol = Annotated[str, Query(pattern=r"^[A-Z0-9]{1,12}/[A-Z0-9]{1,12}$")]
MarketSource = Annotated[str, Query(max_length=120, pattern=r"^[a-z0-9:-]+$")]


@router.get("/system", tags=["System"])
def system(s: S):
    """Expose safe configuration, including the distinction between data and execution modes."""
    model = s.agents.models.resolve()
    return {
        "version": __version__,
        "mode": s.settings.mode,
        "market_exchange": s.settings.market_exchange,
        "market_source": s.data_settings.public_market()["active"],
        "execution": "paper",
        "llm_provider": model["provider"],
        "llm_model": model["model"],
        "agent_engine": "ProtoLink",
        "agents": len(s.agents.agents),
        "allow_live_trading": s.settings.allow_live_trading,
        "accounts": s.accounts.public(),
    }


@router.get("/settings/llm", tags=["Settings"])
def model_settings(s: S, response: Response):
    """List supported providers and saved metadata without exposing API keys."""
    response.headers["Cache-Control"] = "no-store"
    return s.agents.models.public()


@router.post("/settings/llm", tags=["Settings"])
def save_model_settings(body: ModelSettingsRequest, s: S, response: Response):
    """Encrypt a provider key and activate its model for subsequent requests."""
    response.headers["Cache-Control"] = "no-store"
    return s.agents.models.save(body)


@router.delete("/settings/llm/{provider}/key", tags=["Settings"])
def remove_model_key(provider: ProviderId, s: S, response: Response):
    """Remove a saved provider key; environment credentials remain separately configured."""
    response.headers["Cache-Control"] = "no-store"
    return s.agents.models.remove_key(provider)


@router.get("/accounts", tags=["Accountant"])
def active_accounts(s: S, response: Response):
    """Read active selection and combined/exchange/account viewing options without provider calls."""
    response.headers["Cache-Control"] = "no-store"
    return s.accounts.public()


@router.post("/accounts/demo", tags=["Accountant"])
def enable_demo(s: S):
    """Explicitly connect and activate the isolated virtual preview, without resetting its ledger."""
    s.store.add_connection(ConnectionCreate(exchange="demo", label="Demo preview"))
    return s.accounts.public()


@router.post("/connections/{connection_id}/activation", tags=["Accountant"])
def activate_account(connection_id: str, body: AccountActivation, s: S):
    """Change inclusion in account views; activating an exchange automatically disables Demo."""
    before = set(s.accounts.public()["active_ids"])
    s.store.activate_account(connection_id, body.active)
    result = s.accounts.public()
    for identity in before - set(result["active_ids"]):
        s.account_sync.pause(identity)
        s.funding_sync.pause(identity)
    return result


@router.get("/portfolio", tags=["Accountant"])
def portfolio(s: S, scope: str = Query("all", max_length=120, pattern=r"^[a-z0-9:-]+$")):
    """Aggregate priced spot balances and disclose incomplete valuation."""
    return s.portfolio.overview(scope)


@router.get("/settings/news", tags=["Settings"])
def news_settings(s: S, response: Response):
    """List available news collectors and saved selections without returning provider keys."""
    response.headers["Cache-Control"] = "no-store"
    return s.data_settings.public_news()


@router.post("/settings/news", tags=["Settings"])
def save_news_settings(body: NewsSettingsRequest, s: S, response: Response):
    """Save publisher choices, a collector method and an encrypted optional NewsAPI key."""
    response.headers["Cache-Control"] = "no-store"
    return s.data_settings.save_news(body)


@router.get("/settings/market", tags=["Settings"])
def market_settings(s: S, response: Response):
    """Discover feeds and key presence without exposing encrypted credentials."""
    response.headers["Cache-Control"] = "no-store"
    return s.data_settings.public_market()


@router.post("/settings/market", tags=["Settings"])
def save_market_settings(body: MarketSettingsRequest, s: S, response: Response):
    """Activate a reference feed for subsequent reads, independently of account mode."""
    response.headers["Cache-Control"] = "no-store"
    result = s.data_settings.save_market(body)
    if body.api_key is not None:
        s.market.forget_source(body.source)
    return result


@router.delete("/settings/market/{provider}/key", tags=["Settings"])
def remove_market_key(provider: str, s: S, response: Response):
    """Delete a provider credential; select another default before removing a required key."""
    response.headers["Cache-Control"] = "no-store"
    result = s.data_settings.remove_market_key(provider)
    s.market.forget_source(provider)
    return result


@router.get("/markets", tags=["Analyst"])
def markets(s: S, source: MarketSource | None = None):
    """Read a sourced watchlist; a page override never changes workspace preferences."""
    return s.watchlists.overview(source)


@router.get("/markets/watchlist", tags=["Analyst"])
def market_watchlist(s: S, response: Response, source: MarketSource | None = None):
    """Read the selected feed's persisted symbols and order, without fetching quotes."""
    response.headers["Cache-Control"] = "no-store"
    return s.watchlists.config(source)


@router.post("/markets/watchlist/items", tags=["Analyst"])
def add_watchlist_item(body: WatchlistItem, s: S, source: MarketSource | None = None):
    """Append an exact provider pair idempotently; credentials never enter the list."""
    return s.watchlists.add(body.symbol, source)


@router.delete("/markets/watchlist/items", tags=["Analyst"])
def remove_watchlist_item(s: S, symbol: Symbol, source: MarketSource | None = None):
    """Remove a saved pair without requiring a successful provider quote."""
    return s.watchlists.remove(symbol, source)


@router.post("/markets/watchlist/order", tags=["Analyst"])
def reorder_watchlist(body: WatchlistOrder, s: S, source: MarketSource | None = None):
    """Save a permutation of the latest list, rejecting edits that would discard members."""
    return s.watchlists.reorder(body.symbols, source)


@router.get("/markets/analysis", tags=["Analyst"])
def analysis(
    s: S,
    symbol: Symbol = "BTC/USDT",
    limit: int = Query(180, ge=60, le=720),
    timeframe: Timeframe = "1d",
    source: MarketSource | None = None,
):
    """Calculate indicators for an exact provider pair using closed candle intervals."""
    with s.market.snapshot(source):
        s.market.client().market(symbol)
        return {
            "symbol": symbol,
            "timeframe": timeframe,
            **s.market.metadata(),
            **analyze(s.market.candles(symbol, limit, timeframe), 365 * 86400 / TIMEFRAMES[timeframe]),
        }


@router.get("/markets/correlation", tags=["Analyst"])
def correlations(
    s: S,
    symbols: str = Query("BTC/USDT,ETH/USDT,SOL/USDT,LINK/USDT", max_length=350),
    timeframe: Timeframe = "1d",
    limit: int = Query(90, ge=30, le=720),
    method: Literal["pearson", "spearman"] = "pearson",
    transform: Literal["log_returns", "prices", "changes"] = "log_returns",
    source: MarketSource | None = None,
):
    """Compare up to eight exact provider pairs on aligned closed candles from one feed."""
    selected = list(dict.fromkeys(symbols.split(",")))
    if not 2 <= len(selected) <= 8:
        raise ValueError("Choose between two and eight markets.")
    import re

    if any(not re.fullmatch(r"[A-Z0-9]{1,12}/[A-Z0-9]{1,12}", symbol) for symbol in selected):
        raise ValueError("Use canonical symbols such as BTC/USDT.")
    with s.market.snapshot(source):
        for symbol in selected:
            s.market.client().market(symbol)
        histories = {symbol: s.market.candles(symbol, limit, timeframe) for symbol in selected}
        return {**s.market.metadata(), "timeframe": timeframe, **correlation(histories, method, transform)}


@router.get("/markets/symbols", tags=["Analyst"])
def market_symbols(s: S, source: MarketSource | None = None):
    """Discover exact spot pairs, supported timeframes and provider candle limits."""
    with s.market.snapshot(source):
        return s.market.symbols()


@router.get("/markets/orderbook", tags=["Broker"])
def orderbook(
    s: S, symbol: Symbol = "BTC/USDT", depth: int = Query(10, ge=5, le=50), source: MarketSource | None = None
):
    """Read an exact public order-book snapshot without submitting orders."""
    with s.market.snapshot(source):
        s.market.client().market(symbol)
        return s.market.orderbook(symbol, depth)


@router.get("/portfolio/accounts", tags=["Accountant"])
def account_details(s: S, scope: str = Query("all", max_length=120, pattern=r"^[a-z0-9:-]+$")):
    """Read separate account balances and available quote-conversion rates."""
    return s.portfolio.accounts(scope)


@router.get("/reports/trading", tags=["Broker"])
def trade_report(s: S):
    """Inspect local execution records and matched-lot paper P&L."""
    return trading_report(s.store, s.trading)


@router.get("/exchanges", tags=["Technician"])
def exchange_providers():
    """Discover configured exchanges, credential fields and installed SDK capabilities."""
    return provider_catalog()


def account_connection(s: Services, connection_id: str) -> Connection:
    """Resolve public account metadata without exposing vault contents."""
    connection = next((item for item in s.store.connections() if item.id == connection_id), None)
    if connection is None:
        raise HTTPException(404, "Connection not found.")
    return connection


@router.get("/connections/{connection_id}/balances", tags=["Technician"])
def connection_balances(connection_id: str, s: S):
    """Read one saved real or demo account, explicitly identifying its source."""
    connection = account_connection(s, connection_id)
    return {
        "source": connection.exchange,
        "sandbox": connection.sandbox,
        "items": s.market.account_balances(connection),
    }


@router.get("/connections/{connection_id}/open-orders", tags=["Broker"])
def connection_open_orders(connection_id: str, s: S, symbol: Symbol = "BTC/USDT"):
    """Read one market's open orders; this route never submits or cancels orders."""
    connection = account_connection(s, connection_id)
    with s.market.adapter(connection) as client:
        items = client.fetch_open_orders(symbol)
    return {"source": connection.exchange, "sandbox": connection.sandbox, "symbol": symbol, "items": items}


@router.get("/connections/{connection_id}/trades", tags=["Broker"])
def connection_trades(
    connection_id: str,
    s: S,
    symbol: Symbol = "BTC/USDT",
    since: int | None = Query(None, ge=0),
    limit: int = Query(100, ge=1, le=500),
):
    """Read a bounded page of exchange fills; since is UTC Unix milliseconds."""
    connection = account_connection(s, connection_id)
    with s.market.adapter(connection) as client:
        items = client.fetch_my_trades(symbol, since=since, limit=limit)
    return {
        "source": connection.exchange,
        "sandbox": connection.sandbox,
        "symbol": symbol,
        "items": items,
        "limit": limit,
        "since": since,
        "complete_history": False,
    }


@router.get("/account-sync", tags=["Accountant"])
def account_sync_status(s: S):
    """Read import support, saved progress and failures without contacting exchanges."""
    return s.account_sync.snapshot()


@router.post("/connections/{connection_id}/sync", status_code=202, tags=["Accountant"])
def sync_account(connection_id: str, body: AccountSyncRequest, s: S):
    """Queue selected-market fill imports; this never submits an exchange order."""
    connection = account_connection(s, connection_id)
    if not connection.active:
        raise ValueError("Activate this account in Settings before importing history.")
    return s.account_sync.enqueue(connection, body.symbols)


@router.post("/connections/{connection_id}/sync/pause", tags=["Accountant"])
def pause_account_sync(connection_id: str, s: S, symbol: Symbol | None = None):
    """Pause selected or all account imports, keeping retained fills and checkpoints."""
    account_connection(s, connection_id)
    return s.account_sync.pause(connection_id, symbol)


@router.get("/connections/{connection_id}/markets", tags=["Accountant"])
def connection_markets(connection_id: str, s: S):
    """List exact spot markets for a saved account's venue and test environment."""
    connection = account_connection(s, connection_id)
    with s.market.adapter(connection) as client:
        symbols = sorted(client.load_markets())
    return {"source": connection.exchange, "sandbox": connection.sandbox, "symbols": symbols}


@router.get("/account-ledger/fills", tags=["Accountant"])
def account_fills(
    s: S,
    account_id: str = Query("", max_length=100),
    symbol: Symbol | None = None,
    side: Literal["", "buy", "sell"] = "",
    environment: Literal["", "demo", "test", "production"] = "",
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0, le=1_000_000),
):
    """Read retained normalized fills; native fee currencies are never summed together."""
    return s.account_sync.ledger.fills(account_id, symbol or "", side, environment, limit, offset)


@router.get("/account-ledger/performance", tags=["Accountant"])
def account_performance(
    s: S,
    response: Response,
    account_id: str = Query("", max_length=100),
    symbol: Symbol | None = None,
    environment: Literal["", "demo", "test", "production"] = "",
    mark: bool = False,
):
    """Compute market FIFO over all selected retained fills; current marks are opt-in."""
    response.headers["Cache-Control"] = "no-store"
    return s.performance.report(account_id, symbol or "", environment, mark)


@router.get("/funding-sync", tags=["Accountant"])
def funding_sync_status(s: S, response: Response):
    """Read funding support and range progress without private exchange reads."""
    response.headers["Cache-Control"] = "no-store"
    return s.funding_sync.snapshot()


@router.post("/connections/{connection_id}/funding-sync", status_code=202, tags=["Accountant"])
def sync_funding(connection_id: str, body: FundingSyncRequest, s: S, response: Response):
    """Queue read-only funding history in an explicit date range; no transfers are initiated."""
    response.headers["Cache-Control"] = "no-store"
    return s.funding_sync.enqueue(account_connection(s, connection_id), body)


@router.post("/connections/{connection_id}/funding-sync/pause", tags=["Accountant"])
def pause_funding(
    connection_id: str, s: S, stream: Literal["deposit", "withdrawal", "transfer"] | None = None
):
    """Pause future funding pages, retaining observations and the last successful checkpoint."""
    account_connection(s, connection_id)
    return s.funding_sync.pause(connection_id, stream)


@router.get("/account-ledger/funding", tags=["Accountant"])
def funding_events(
    s: S,
    response: Response,
    account_id: str = Query("", max_length=100),
    asset: str = Query("", max_length=20, pattern=r"^$|^[A-Z0-9][A-Z0-9.]{0,19}$"),
    kind: Literal["", "deposit", "withdrawal", "transfer"] = "",
    status: Literal["", "pending", "completed", "failed", "cancelled", "restricted", "unknown"] = "",
    environment: Literal["", "demo", "test", "production"] = "",
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0, le=1_000_000),
):
    """Read retained funding observations and completed native-asset totals."""
    response.headers["Cache-Control"] = "no-store"
    return s.funding_sync.ledger.events(account_id, asset, kind, status, environment, limit, offset)


@router.get("/account-ledger/funding/example", tags=["Accountant"])
def funding_example(s: S, response: Response):
    """Read an isolated funding example without changing wallet or ledger state."""
    response.headers["Cache-Control"] = "no-store"
    return s.funding_sync.example()


@router.get("/account-ledger/transfers", tags=["Accountant"])
def transfer_reviews(
    s: S,
    response: Response,
    account_id: str = Query("", max_length=100),
    asset: str = Query("", max_length=20, pattern=r"^$|^[A-Z0-9][A-Z0-9.]{0,19}$"),
    environment: Literal["", "demo", "test", "production"] = "",
    include_removed: bool = False,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0, le=1_000_000),
):
    """Read heuristic suggestions and user-confirmed classifications, without inferring cash-flow returns."""
    response.headers["Cache-Control"] = "no-store"
    return s.transfers.report(account_id, asset, environment, include_removed, limit, offset)


@router.get("/account-ledger/transfers/example", tags=["Accountant"])
def transfer_example(s: S, response: Response):
    """Compute an isolated ambiguous-pair example without inserting funding observations or links."""
    response.headers["Cache-Control"] = "no-store"
    return s.transfers.example()


@router.get("/account-ledger/transfers/events", tags=["Accountant"])
def transfer_records(
    s: S,
    response: Response,
    direction: Literal["in", "out"],
    account_id: str = Query("", max_length=100),
    asset: str = Query("", max_length=20, pattern=r"^$|^[A-Z0-9][A-Z0-9.]{0,19}$"),
    environment: Literal["", "demo", "test", "production"] = "",
    q: str = Query("", max_length=120),
    limit: int = Query(25, ge=1, le=50),
    offset: int = Query(0, ge=0, le=1_000_000),
):
    """Search retained records for a manual pair, including records outside the suggestion scan."""
    response.headers["Cache-Control"] = "no-store"
    return s.transfers.events(direction, account_id, asset, environment, q, limit, offset)


@router.post("/account-ledger/transfers/example/preview", tags=["Accountant"])
def preview_example_transfer(body: TransferPair, s: S, response: Response):
    """Validate an allocation against isolated fixture records only; no persistence."""
    response.headers["Cache-Control"] = "no-store"
    return s.transfers.example_preview(body)


@router.post("/account-ledger/transfers/preview", tags=["Accountant"])
def preview_transfer(body: TransferPair, s: S, response: Response):
    """Prepare exact source versions for a review; this endpoint persists nothing."""
    response.headers["Cache-Control"] = "no-store"
    return s.transfers.preview(body)


@router.post("/account-ledger/transfers", tags=["Accountant"])
def confirm_transfer(body: TransferConfirm, s: S, response: Response):
    """Save an audited user assertion; source-version checks and unique membership prevent stale/double links."""
    response.headers["Cache-Control"] = "no-store"
    return s.transfers.confirm(body)


@router.get("/account-ledger/transfers/{link_id}", tags=["Accountant"])
def transfer_detail(link_id: str, s: S, response: Response):
    """Read saved/current evidence and the latest fifty confirm/reconfirm/remove actions."""
    response.headers["Cache-Control"] = "no-store"
    return s.transfers.detail(link_id)


@router.post("/account-ledger/transfers/{link_id}/review", tags=["Accountant"])
def review_transfer(link_id: str, body: TransferConfirm, s: S, response: Response):
    """Reconfirm changed source facts or restore a removed link after reviewing current observations."""
    response.headers["Cache-Control"] = "no-store"
    return s.transfers.confirm(body, link_id)


@router.delete("/account-ledger/transfers/{link_id}", status_code=204, tags=["Accountant"])
def remove_transfer(link_id: str, s: S):
    """Soft-remove a classification; retain the audit trail and release source records for another review."""
    s.transfers.remove(link_id)
    return Response(status_code=204, headers={"Cache-Control": "no-store"})


@router.post("/connections/{connection_id}/opening-inventory", tags=["Accountant"])
def save_opening_inventory(connection_id: str, body: OpeningInventory, s: S, response: Response):
    """Record user-entered opening quantity and optional quote cost, separate from fills."""
    response.headers["Cache-Control"] = "no-store"
    return s.performance.save_opening(connection_id, body)


@router.get("/account-ledger/performance/example", tags=["Accountant"])
def performance_example(s: S, response: Response, transfers: bool = False, fees: bool = False):
    """Read an isolated computed example; never create paper orders or ledger entries."""
    response.headers["Cache-Control"] = "no-store"
    return s.performance.transfer_example(fees) if transfers or fees else s.performance.example()


@router.get("/account-ledger/performance/markets", tags=["Accountant"])
def performance_markets(s: S, response: Response):
    """List market filters from retained fills and opening-only assertions, without provider reads."""
    response.headers["Cache-Control"] = "no-store"
    return s.performance.markets()


@router.get("/connections/{connection_id}/opening-inventory/audit", tags=["Accountant"])
def opening_inventory_audit(connection_id: str, symbol: Symbol, s: S, response: Response):
    """Read the latest fifty local changes to a market's opening inventory assertion."""
    response.headers["Cache-Control"] = "no-store"
    return s.performance.audit(connection_id, symbol)


@router.delete("/connections/{connection_id}/opening-inventory", status_code=204, tags=["Accountant"])
def remove_opening_inventory(connection_id: str, symbol: Symbol, s: S):
    """Remove a basis assertion, retaining its local audit trail and imported fills."""
    s.performance.remove_opening(connection_id, symbol)
    return Response(status_code=204, headers={"Cache-Control": "no-store"})


@router.get("/connections", response_model=list[Connection], tags=["Technician"])
def connections(s: S):
    """Read saved connection metadata; API credentials cannot be retrieved."""
    return s.store.connections()


@router.post("/connections", response_model=Connection, status_code=201, tags=["Technician"])
def add_connection(body: ConnectionCreate, s: S):
    """Save encrypted credentials. A separate check makes a provider request."""
    before = set(s.accounts.public()["active_ids"])
    result = s.store.add_connection(body)
    for identity in before - set(s.accounts.public()["active_ids"]):
        s.account_sync.pause(identity)
        s.funding_sync.pause(identity)
    return result


@router.delete("/connections/{connection_id}", status_code=204, tags=["Technician"])
def delete_connection(connection_id: str, s: S):
    """Disconnect a saved account and clear its cached decrypted client."""
    s.store.delete_connection(connection_id)
    s.account_sync.pause(connection_id, disconnected=True)
    s.funding_sync.pause(connection_id, disconnected=True)
    s.market.forget(connection_id)
    return Response(status_code=204)


@router.post("/connections/{connection_id}/check", tags=["Technician"])
def check_connection(connection_id: str, s: S):
    """Verify credentials against the exchange using read-only balance access."""
    return s.market.check_connection(account_connection(s, connection_id))


@router.get("/paper/balances", tags=["Broker"])
def paper_balances(s: S):
    """Read the separate manual paper ledger, including in live-data mode."""
    s.accounts.require_demo()
    from sibyl.exchanges.demo import DemoClient

    balance = DemoClient(store=s.store).fetch_balance()
    return {"mode": "paper", "balances": balance["free"], "total": balance["total"], "used": balance["used"]}


@router.get("/orders", tags=["Broker"])
def orders(s: S):
    """Read persisted manual paper fills."""
    return s.store.orders()


@router.post("/orders/preview", tags=["Broker"])
def preview_order(body: OrderRequest, s: S):
    """Estimate notional and a 0.1% paper fee without mutating funds."""
    s.accounts.require_demo()
    with s.market.snapshot():
        price = s.market.price(body.symbol)
        notional = price * body.quantity
        return {
            "symbol": body.symbol,
            "side": body.side,
            "quantity": body.quantity,
            "price": price,
            "notional": notional,
            "fee": notional * 0.001,
            "total": notional * (1.001 if body.side == "buy" else 0.999),
            "mode": "paper",
            "source": s.market.source,
        }


@router.post("/orders", status_code=201, tags=["Broker"])
def place_order(body: OrderRequest, s: S):
    """Fill a paper market order atomically. Real exchange execution is unavailable."""
    s.accounts.require_demo()
    return s.store.execute_paper(body, s.market.price(body.symbol), require_demo=True)


@router.get("/exchange-orders", tags=["Broker"])
def exchange_orders(s: S, response: Response):
    """List exchange order intents and their actual submission status."""
    response.headers["Cache-Control"] = "no-store"
    return s.trading.list_orders()


@router.get("/exchange-orders/example", tags=["Broker"])
def order_monitor_example(response: Response):
    """Return illustrative status observations without creating wallet/order records."""
    response.headers["Cache-Control"] = "no-store"
    return [
        {
            "id": "example-" + symbol.replace("/", "-") + "-" + status,
            "request": {
                "connection_id": "example",
                "symbol": symbol,
                "side": side,
                "quantity": quantity,
                "order_type": "limit",
                "limit_price": price,
            },
            "account": "Example account",
            "exchange": "demo",
            "sandbox": True,
            "environment": "illustrative",
            "mode": "paper",
            "status": status,
            "price": price,
            "filled": filled,
            "remaining": quantity - filled,
            "average": price if filled else None,
            "tracking": status == "open",
            "client_order_id": "example-only",
            "exchange_order_id": "example-only",
        }
        for symbol, side, quantity, price, status, filled in [
            ("BTC/USDT", "buy", 0.02, 50000, "open", 0.008),
            ("ETH/USDT", "sell", 0.5, 3500, "open", 0.0),
            ("SOL/USDT", "buy", 3.0, 140, "canceled", 1.0),
        ]
    ]


@router.post("/exchange-orders/{intent_id}/refresh", tags=["Broker"])
def refresh_exchange_order(intent_id: str, s: S, response: Response):
    """Read the status of a recorded exchange order without any resubmission."""
    response.headers["Cache-Control"] = "no-store"
    return s.trading.refresh(intent_id)


@router.post("/exchange-orders/preview", tags=["Broker"])
def preview_exchange_order(body: ExchangeOrderRequest, s: S):
    """Validate a spot market/GTC limit order and create a 60 second review intent."""
    return s.trading.preview(body)


@router.post("/exchange-orders/{intent_id}/confirm", tags=["Broker"])
def confirm_exchange_order(intent_id: str, body: ExchangeOrderConfirm, s: S):
    """Submit an explicit, user-confirmed exchange order at most once."""
    return s.trading.execute(intent_id, body.confirmation)


@router.post("/exchange-orders/{intent_id}/cancel/preview", tags=["Broker"])
def preview_cancellation(intent_id: str, s: S, response: Response):
    """Observe native status and create a separate 60 second cancellation review."""
    response.headers["Cache-Control"] = "no-store"
    return s.trading.lifecycle.preview_cancel(intent_id)


@router.post("/exchange-orders/{intent_id}/cancel", tags=["Broker"])
def cancel_exchange_order(intent_id: str, body: CancelOrderConfirm, s: S, response: Response):
    """Send a user-confirmed cancellation once; ambiguous outcomes remain uncertain."""
    response.headers["Cache-Control"] = "no-store"
    return s.trading.lifecycle.cancel(intent_id, body.cancel_id, body.confirmation)


@router.post("/exchange-orders/{intent_id}/tracking", tags=["Broker"])
def order_tracking(intent_id: str, body: OrderTracking, s: S, response: Response):
    """Persist automatic native status reads; this never enables order execution."""
    response.headers["Cache-Control"] = "no-store"
    return s.trading.lifecycle.track(intent_id, body.enabled)


@router.get("/strategies", tags=["Broker"])
def strategies():
    """Describe the six available strategy algorithms."""
    return CATALOG


@router.post("/strategies/backtest", tags=["Broker"])
def run_backtest(body: BacktestRequest, s: S):
    """Simulate a strategy with next-open fills, fees, and slippage; persist its result."""
    with s.market.snapshot():
        result = {
            **backtest(s.market.candles(body.symbol, body.candles, body.timeframe), body),
            "source": s.market.source,
        }
        record = s.store.record("backtest", result)
        return {**result, "id": record["id"]}


@router.get("/strategies/jobs", tags=["Broker"])
def strategy_jobs(s: S):
    """Read durable paper strategies, current virtual equity, and execution logs."""
    return s.strategies.jobs()


@router.post("/strategies/jobs", status_code=201, tags=["Broker"])
def start_strategy(body: BacktestRequest, s: S):
    """Start a paper-only job with its own virtual capital."""
    return s.strategies.start(body)


@router.get("/strategies/jobs/{job_id}", tags=["Broker"])
def strategy_monitor(job_id: str, s: S, limit: int = Query(300, ge=10, le=2000)):
    """Read the run, observed price/equity chart, and recorded decision markers."""
    return s.strategies.journal.monitor(job_id, limit)


@router.get("/strategies/jobs/{job_id}/events", tags=["Broker"])
def strategy_events(
    job_id: str,
    s: S,
    limit: int = Query(100, ge=1, le=500),
    before: int | None = Query(None, ge=1),
    action: Literal[
        "all",
        "fills",
        "HOLD",
        "SKIP_BUY",
        "SKIP_SELL",
        "ERROR",
        "START",
        "PAUSE",
        "RESUME",
        "STOP",
        "BUY",
        "SELL",
        "RECOVERED",
    ] = "all",
):
    """Page the durable decision journal newest first, with optional action filtering."""
    return s.strategies.journal.events(job_id, limit, before, action)


@router.get("/strategies/jobs/{job_id}/events.csv", tags=["Broker"])
def strategy_events_export(
    job_id: str,
    s: S,
    action: Literal[
        "all",
        "fills",
        "HOLD",
        "SKIP_BUY",
        "SKIP_SELL",
        "ERROR",
        "START",
        "PAUSE",
        "RESUME",
        "STOP",
        "BUY",
        "SELL",
        "RECOVERED",
    ] = "all",
):
    """Stream the complete matching journal in CSV without exposing credentials."""
    chunks = s.strategies.journal.export(job_id, action)
    return StreamingResponse(
        chunks,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=strategy-events.csv"},
    )


@router.post("/strategies/jobs/{job_id}/{action}", tags=["Broker"])
def strategy_action(job_id: str, action: Literal["pause", "resume", "stop"], s: S):
    """Pause, resume, or permanently stop evaluation without liquidating virtual holdings."""
    return s.strategies.status(job_id, {"pause": "paused", "resume": "running", "stop": "stopped"}[action])


@router.get("/forecast", tags=["Chronos"])
def price_forecast(s: S, symbol: Symbol = "BTC/USDT", horizon: int = Query(14, ge=1, le=30)):
    """Return an explicitly untrained log-return baseline and uncertainty band."""
    with s.market.snapshot():
        return {
            "symbol": symbol,
            "source": s.market.source,
            **forecast(s.market.candles(symbol, 180), horizon),
        }


@router.get("/news", tags=["Reporter"])
def news(
    s: S,
    summary: Literal["excerpt", "extractive"] = "excerpt",
    mode: Literal["demo", "live"] | None = None,
    publisher: str = Query("", max_length=40),
    asset: str = Query("", max_length=10),
    sentiment: Literal["", "positive", "neutral", "negative"] = "",
    q: str = Query("", max_length=200),
    days: int = Query(7, ge=0, le=365),
    limit: int = Query(24, ge=1, le=100),
    offset: int = Query(0, ge=0, le=5000),
):
    """Search retained excerpts and analyze the filtered set before pagination."""
    return s.research.news(
        summary,
        mode=mode,
        publisher=publisher,
        asset=asset,
        sentiment=sentiment,
        q=q,
        days=days,
        limit=limit,
        offset=offset,
    )


@router.get("/news/sources", tags=["Reporter"])
def news_sources(s: S):
    """Inspect publisher health without initiating network requests."""
    return {"items": s.research.news_service.sources()}


@router.post("/news/refresh", tags=["Reporter"])
def refresh_news(s: S):
    """Refresh public publisher feeds with a per-source 60-second minimum interval."""
    return s.research.news_service.refresh(force=True)


@router.get("/news/fear-greed", tags=["Reporter"])
def fear_greed(s: S, mode: Literal["demo", "live"] | None = None):
    """Read attributed Alternative.me observations or explicitly illustrative demo values."""
    return s.research.fear_greed.read(mode or s.research.news_service.default_mode)


@router.get("/news/{article_id}", tags=["Reporter"])
def news_article(article_id: str, s: S, mode: Literal["demo", "live"] | None = None):
    """Read an archived story by its stable ID, independently of paging and filters."""
    return {"item": s.research.news_service.article(article_id, mode)}


@router.get("/knowledge", tags=["Wiki"])
def knowledge(s: S, q: str = Query("", max_length=200)):
    """Search the built-in glossary without a model or embedding database."""
    return s.research.knowledge(q)


@router.get("/research/crypto", tags=["Research"])
def crypto_catalog(s: S):
    """List the 20 curated crypto profiles; this is not a live ranking."""
    return s.research.crypto.catalog()


@router.get("/research/crypto/{asset_id}", tags=["Research"])
def crypto_profile(asset_id: str, s: S):
    """Fetch public fundamentals, background/history, and an independently sourced market snapshot."""
    return s.research.crypto.profile(asset_id)


@router.get("/blocks", tags=["Explorer"])
def blocks(s: S, count: int = Query(10, ge=1, le=100)):
    """Read recent Bitcoin block summaries."""
    return s.research.blocks(count)


@router.get("/stocks/{symbol}", tags=["Stocks"])
def stock(symbol: str, s: S):
    """Read sample equities or optional yfinance-backed data."""
    return s.research.stock(symbol)


@router.get("/agents", tags=["Oracle"])
def agents(s: S):
    """Describe all embedded ProtoLink agents and their available module tools."""
    return s.agents.catalog()


@router.post("/agents/ask", tags=["Oracle"])
async def ask_agent(body: AgentRequest, s: S):
    """Run a module's ProtoLink tool and optionally perform model inference."""
    try:
        return await s.agents.ask(body)
    except TimeoutError as exc:
        raise HTTPException(
            504, "The model request timed out. Try a shorter question or check your provider."
        ) from exc
    except asyncio.CancelledError:
        raise
    except LookupError:
        raise
    except Exception as exc:
        raise HTTPException(
            502, "The agent could not complete this request. Check the provider and module data."
        ) from exc


@router.get("/runs", tags=["System"])
def runs(s: S, kind: Literal["agent", "backtest"] | None = None):
    """Inspect the 50 latest persisted agent runs or historical backtests."""
    return s.store.runs(kind)


@router.get("/roadmap", tags=["System"])
def roadmap():
    """Expose the audited implementation inventory, including explicitly deferred scope."""
    return implementation_status()


@router.get("/alerts", tags=["Alerts"])
def price_alerts(
    s: S, response: Response, include_archived: bool = False, offset: int = Query(0, ge=0, le=1_000_000)
):
    """Read saved rules without evaluating them or calling providers."""
    response.headers["Cache-Control"] = "no-store"
    return s.alerts.rules(include_archived, offset)


@router.post("/alerts", tags=["Alerts"], status_code=201)
def create_price_alert(body: PriceAlertCreate, s: S, response: Response):
    """Arm one source-pinned threshold rule; no trade or external delivery is possible."""
    response.headers["Cache-Control"] = "no-store"
    return s.alerts.create(body)


@router.post("/alerts/{rule_id}/action", tags=["Alerts"])
def change_price_alert(rule_id: str, body: PriceAlertAction, s: S, response: Response):
    """Pause, rearm, archive or restore a price rule."""
    response.headers["Cache-Control"] = "no-store"
    return s.alerts.change(rule_id, body.action)


@router.post("/alerts/{rule_id}/check", tags=["Alerts"])
def check_price_alert(rule_id: str, s: S, response: Response):
    """Check one armed rule if due; preserve the provider cooldown/backoff budget."""
    response.headers["Cache-Control"] = "no-store"
    return s.alerts.check(rule_id)


@router.get("/notifications", tags=["Alerts"])
def notification_inbox(
    s: S, response: Response, limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0, le=1_000_000)
):
    """Page retained local notifications; reading never acknowledges them."""
    response.headers["Cache-Control"] = "no-store"
    return s.alerts.inbox(limit, offset)


@router.post("/notifications/read-all", tags=["Alerts"])
def read_all_notifications(s: S, response: Response):
    """Acknowledge unread local notifications without deleting their evidence."""
    response.headers["Cache-Control"] = "no-store"
    return s.alerts.mark_read()


@router.post("/notifications/{notification_id}/read", tags=["Alerts"])
def read_notification(notification_id: str, s: S, response: Response):
    """Persist one notification's read state idempotently."""
    response.headers["Cache-Control"] = "no-store"
    return s.alerts.mark_read(notification_id)


@router.get("/alerts/example", tags=["Alerts"])
def price_alert_example(response: Response):
    """Inspect an isolated example without saving rules or triggering notifications."""
    response.headers["Cache-Control"] = "no-store"
    return alert_example()

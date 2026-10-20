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
    AgentRequest,
    BacktestRequest,
    Connection,
    ConnectionCreate,
    ExchangeOrderConfirm,
    ExchangeOrderRequest,
    OrderRequest,
    Timeframe,
)
from sibyl.services.account_sync import AccountSyncRequest
from sibyl.services.analytics import analyze, correlation, forecast
from sibyl.services.data_settings import MarketSettingsRequest, NewsSettingsRequest
from sibyl.services.llm_settings import ModelSettingsRequest
from sibyl.services.market import TIMEFRAMES
from sibyl.services.reporting import trading_report
from sibyl.services.strategies import CATALOG, backtest
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


@router.get("/portfolio", tags=["Accountant"])
def portfolio(s: S):
    """Aggregate priced spot balances and disclose incomplete valuation."""
    return s.portfolio.overview()


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
def account_details(s: S):
    """Read separate account balances and available quote-conversion rates."""
    return s.portfolio.accounts()


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
    return s.account_sync.enqueue(account_connection(s, connection_id), body.symbols)


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


@router.get("/connections", response_model=list[Connection], tags=["Technician"])
def connections(s: S):
    """Read saved connection metadata; API credentials cannot be retrieved."""
    return s.store.connections()


@router.post("/connections", response_model=Connection, status_code=201, tags=["Technician"])
def add_connection(body: ConnectionCreate, s: S):
    """Save encrypted credentials. A separate check makes a provider request."""
    return s.store.add_connection(body)


@router.delete("/connections/{connection_id}", status_code=204, tags=["Technician"])
def delete_connection(connection_id: str, s: S):
    """Disconnect a saved account and clear its cached decrypted client."""
    s.store.delete_connection(connection_id)
    s.account_sync.pause(connection_id, disconnected=True)
    s.market.forget(connection_id)
    return Response(status_code=204)


@router.post("/connections/{connection_id}/check", tags=["Technician"])
def check_connection(connection_id: str, s: S):
    """Verify credentials against the exchange using read-only balance access."""
    return s.market.check_connection(account_connection(s, connection_id))


@router.get("/paper/balances", tags=["Broker"])
def paper_balances(s: S):
    """Read the separate manual paper ledger, including in live-data mode."""
    return {"mode": "paper", "balances": s.store.balances()}


@router.get("/orders", tags=["Broker"])
def orders(s: S):
    """Read persisted manual paper fills."""
    return s.store.orders()


@router.post("/orders/preview", tags=["Broker"])
def preview_order(body: OrderRequest, s: S):
    """Estimate notional and a 0.1% paper fee without mutating funds."""
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
    return s.store.execute_paper(body, s.market.price(body.symbol))


@router.get("/exchange-orders", tags=["Broker"])
def exchange_orders(s: S):
    """List exchange order intents and their actual submission status."""
    return s.trading.list_orders()


@router.post("/exchange-orders/{intent_id}/refresh", tags=["Broker"])
def refresh_exchange_order(intent_id: str, s: S):
    """Read the status of a recorded exchange order without any resubmission."""
    return s.trading.refresh(intent_id)


@router.post("/exchange-orders/preview", tags=["Broker"])
def preview_exchange_order(body: ExchangeOrderRequest, s: S):
    """Validate an exchange market order and create a 60 second review intent."""
    return s.trading.preview(body)


@router.post("/exchange-orders/{intent_id}/confirm", tags=["Broker"])
def confirm_exchange_order(intent_id: str, body: ExchangeOrderConfirm, s: S):
    """Submit an explicit, user-confirmed exchange order at most once."""
    return s.trading.execute(intent_id, body.confirmation)


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

"""Application factory, lifecycle ownership, and local API access controls."""

import asyncio
import secrets
import sqlite3
from contextlib import asynccontextmanager
from dataclasses import dataclass

import ccxt
import httpx
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from sibyl import __version__
from sibyl.accounting.balance_checks import BalanceChecks
from sibyl.accounting.funding.reviews import FundingReviewConflict
from sibyl.agents.utils.model_selection import ModelConflict
from sibyl.agents.utils.registry import AgentRegistry
from sibyl.alerts.delivery.service import AlertDelivery
from sibyl.api.dashboard import mount_dashboard
from sibyl.config import Settings
from sibyl.exchanges.streams.service import PrivateAccountStreams
from sibyl.forecasting.service import ForecastModels
from sibyl.investigations.scheduling.service import BriefingScheduler
from sibyl.investigations.service import Investigations
from sibyl.local_models.ollama import OllamaService
from sibyl.market_data.backfills import CandleHistory
from sibyl.market_data.control import ProviderDeferred
from sibyl.messaging.channels.service import PrivateChannels
from sibyl.messaging.service import TelegramService
from sibyl.operations.archives import WorkspaceArchives
from sibyl.operations.health import WorkerHealth
from sibyl.operations.jobs.handlers import application_handlers
from sibyl.operations.jobs.service import LocalJobs
from sibyl.research_library.service import ResearchLibrary
from sibyl.services.accounts.service import Accounts
from sibyl.services.accounts.sync import AccountSync
from sibyl.services.alerts.service import AlertConflict, PriceAlerts
from sibyl.services.funding.contracts import FundingRefreshConflict
from sibyl.services.funding.sync import FundingSync
from sibyl.services.markets.service import Market
from sibyl.services.markets.watchlists import Watchlists
from sibyl.services.portfolio.performance import AccountPerformance
from sibyl.services.portfolio.service import Portfolio
from sibyl.services.research.service import Research
from sibyl.services.trading.service import ExchangeTrading
from sibyl.services.transfers.reconciliation import TransferConflict, TransferReconciliation
from sibyl.services.workspace.data_settings import DataSettings
from sibyl.storage import Store
from sibyl.strategies import Strategies
from sibyl.strategies.execution.controls import ControlConflict


@dataclass
class Services:
    """Explicit application dependencies, constructed once inside the app lifespan."""

    settings: Settings
    store: Store
    market: Market
    portfolio: Portfolio
    research: Research
    strategies: Strategies
    agents: AgentRegistry
    trading: ExchangeTrading
    data_settings: DataSettings
    account_sync: AccountSync
    watchlists: Watchlists
    accounts: Accounts
    performance: AccountPerformance
    funding_sync: FundingSync
    transfers: TransferReconciliation
    alerts: PriceAlerts
    history: CandleHistory
    messaging: TelegramService
    ollama: OllamaService
    balance_checks: BalanceChecks
    forecasts: ForecastModels
    investigations: Investigations
    briefings: BriefingScheduler
    alert_delivery: AlertDelivery
    library: ResearchLibrary
    workers: WorkerHealth
    archives: WorkspaceArchives
    jobs: LocalJobs
    private_channels: PrivateChannels
    account_streams: PrivateAccountStreams


def create_app(settings: Settings | None = None) -> FastAPI:
    """Create an isolated ASGI app; start persistence and workers only on startup."""
    config = settings or Settings()
    if config.host not in {"127.0.0.1", "localhost", "::1"} and not config.api_token.get_secret_value():
        raise ValueError("Set SIBYL_API_TOKEN before exposing the API beyond loopback.")

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        nonlocal config
        store = Store(config.data_dir)
        recovery = bool(store.data_profile("workspace-recovery").get("required"))
        if recovery:
            config = config.model_copy(
                update={"allow_live_trading": False, "allow_strategy_execution": False}
            )
        data_settings = DataSettings(config, store)
        data_settings.apply_startup()
        market = Market(config, store, data_settings)
        portfolio, research = Portfolio(market, store), Research(config, data_settings)
        library = ResearchLibrary(config.data_dir, research.news_service.repository)
        workers = WorkerHealth(store)
        workers.recovery_required = recovery
        archives = WorkspaceArchives(store)
        strategies = Strategies(market, store)
        account_sync = AccountSync(market, store)
        funding_sync = FundingSync(market, store)
        transfers = TransferReconciliation(store)
        performance = AccountPerformance(market, store)
        balance_checks = BalanceChecks(market, store)
        forecasts = ForecastModels(market, store)
        agents = AgentRegistry(
            config,
            store,
            market,
            portfolio,
            strategies,
            research,
            account_sync,
            performance,
            funding_sync,
            transfers,
            balance_checks,
            forecasts,
            library,
            workers,
        )
        await agents.network.start()
        investigations = Investigations(store, agents.network)
        try:
            await investigations.start_runtime()
        except BaseException:
            await agents.network.close()
            raise
        messaging = TelegramService(store, agents.network, library=library)
        private_channels = PrivateChannels(store, agents.network)
        messaging.notifications.use_channels(private_channels)
        briefings = BriefingScheduler(investigations, messaging)
        ollama = OllamaService(agents.models)
        trading = ExchangeTrading(market, store)
        account_streams = PrivateAccountStreams(store, trading)
        trading.account_streams = account_streams
        strategies.attach_execution(trading)
        alerts = PriceAlerts(market, store)
        alert_delivery = AlertDelivery(store, messaging)
        history = CandleHistory(market, store)
        local_jobs = LocalJobs(store, application_handlers(performance, forecasts, workers, strategies))
        workers.jobs = local_jobs
        app.state.services = Services(
            config,
            store,
            market,
            portfolio,
            research,
            strategies,
            agents,
            trading,
            data_settings,
            account_sync,
            Watchlists(market, store),
            Accounts(store),
            performance,
            funding_sync,
            transfers,
            alerts,
            history,
            messaging,
            ollama,
            balance_checks,
            forecasts,
            investigations,
            briefings,
            alert_delivery,
            library,
            workers,
            archives,
            local_jobs,
            private_channels,
            account_streams,
        )

        def background_call(method):
            with market.requests.background():
                return method()

        async def briefing_tick():
            with market.requests.background():
                await briefings.tick()

        def news_tick():
            if research.news_service.default_mode == "live":
                research.news_service.refresh()

        def account_tick():
            for method in (account_sync.tick, funding_sync.tick):
                background_call(method)

        def order_tick():
            # Preserve the existing lifecycle → reconciliation → discovery order.
            for method in (trading.lifecycle.tick, trading.reconciliation.tick, trading.discovery.tick):
                background_call(method)

        # One record per actual worker iteration; provider phases retain their ordering.
        jobs = [
            ("private-account-streams", "Private order observers", account_streams.tick, 1, 60),
            ("local-jobs", "Local scheduled jobs", local_jobs.tick, 1, 300),
            ("strategies", "Strategy execution", lambda: background_call(strategies.tick), 30, 120),
            ("news", "News collection", news_tick, 30, 120),
            ("accounts", "Account and funding imports", account_tick, 1, 120),
            ("orders", "Order maintenance", order_tick, 1, 120),
            ("prices", "Price alerts", lambda: background_call(alerts.tick), 1, 120),
            ("strategy-alerts", "Strategy alerts", strategies.alerts.tick, 1, 60),
            ("connection-alerts", "Connection alerts", market.connection_alerts.tick, 1, 60),
            (
                "risk-alerts",
                "Account-risk alerts",
                lambda: background_call(portfolio.risk_alerts.tick),
                1,
                120,
            ),
            ("execution-alerts", "Order and fill notifications", trading.alerts.tick, 1, 60),
            ("notification-retention", "Read-notification retention", alerts._inbox.history.tick, 60, 60),
            ("forecast-observations", "Forecast outcomes", forecasts.forward.tick, 60, 120),
            ("history", "Candle history", lambda: background_call(history.tick), 1, 120),
            ("briefings", "Scheduled investigations", briefing_tick, 2, 120),
            ("alert-delivery", "Alert delivery admission", alert_delivery.tick, 1, 60),
            ("messaging", "Telegram messaging", messaging.tick, 0.5, 120),
            ("library", "Retained-news search index", library.synchronize_news, 30, 120),
            ("retrieval-evaluations", "Research retrieval evaluations", library.evaluations.tick, 1, 120),
        ]
        for channel in ("discord", "slack", "signal", "whatsapp", "email"):

            async def channel_tick(channel=channel):
                await private_channels.tick(channel)

            jobs.append(("messaging-" + channel, channel.capitalize() + " messaging", channel_tick, 2, 120))
        for name, label, action, interval, deadline in jobs:
            workers.start(
                name,
                label,
                action,
                interval=interval,
                deadline=deadline,
                retryable=(sqlite3.Error,)
                if name
                in {
                    "risk-alerts",
                    "briefings",
                    "alert-delivery",
                    "messaging",
                    "library",
                    "retrieval-evaluations",
                    "execution-alerts",
                    "forecast-observations",
                }
                else (),
                paused=recovery,
            )
        if not recovery:
            workers.watchdog.start()
        try:
            yield
        finally:
            await market.live.close()
            await workers.close()
            await account_streams.close()
            await asyncio.to_thread(library.evaluations.close)
            await asyncio.to_thread(alerts._inbox.history.close)
            await asyncio.to_thread(alert_delivery.close)
            await asyncio.to_thread(trading.alerts.close)
            await asyncio.to_thread(forecasts.forward.close)
            await briefings.close()
            await private_channels.close()
            await messaging.close()
            await investigations.close()
            await asyncio.to_thread(ollama.close)
            await agents.network.close()
            await asyncio.to_thread(account_sync.close)
            await asyncio.to_thread(funding_sync.close)
            await asyncio.to_thread(trading.lifecycle.close)
            await asyncio.to_thread(trading.discovery.close)
            await asyncio.to_thread(alerts.close)
            await asyncio.to_thread(strategies.alerts.close)
            await asyncio.to_thread(market.connection_alerts.close)
            await asyncio.to_thread(portfolio.risk_alerts.close)
            await asyncio.to_thread(history.close)
            market.close()

    app = FastAPI(
        title="Sibyl API",
        version=__version__,
        lifespan=lifespan,
        description="Local-first portfolio, market research, paper execution, and ProtoLink agents.",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=config.cors_origins,
        allow_methods=["GET", "POST", "DELETE"],
        allow_headers=["Content-Type", "Authorization"],
    )

    @app.middleware("http")
    async def access_control(request: Request, call_next):
        # This exact provider route authenticates its own HMAC/token before parsing.
        # No settings, prefix siblings or other HTTP methods bypass workspace auth.
        if request.url.path == "/api/v1/webhooks/whatsapp" and request.method in {"GET", "POST"}:
            return await call_next(request)
        if request.url.path.startswith("/api/") and request.method != "OPTIONS":
            origin = request.headers.get("origin")
            allowed = set(config.cors_origins) | {str(request.base_url).rstrip("/")}
            if origin and origin not in allowed:
                return JSONResponse({"detail": "Origin is not allowed."}, status_code=403)
            expected = config.api_token.get_secret_value()
            if expected and not secrets.compare_digest(
                request.headers.get("authorization", ""), f"Bearer {expected}"
            ):
                return JSONResponse(
                    {"detail": "Enter your workspace API token in Settings."}, status_code=401
                )
            host = request.headers.get("host", "").split(":")[0]
            if not expected and host not in {"localhost", "127.0.0.1", "[", "testserver"}:
                return JSONResponse({"detail": "Local workspace access only."}, status_code=403)
        return await call_next(request)

    @app.exception_handler(RequestValidationError)
    async def validation_error(_request, exc):
        # Pydantic includes raw input in errors by default; credentials must never be reflected.
        errors = [{"loc": error["loc"], "msg": error["msg"], "type": error["type"]} for error in exc.errors()]
        return JSONResponse({"detail": errors}, status_code=422)

    @app.exception_handler(ValueError)
    async def invalid_request(_request, exc):
        return JSONResponse({"detail": str(exc)}, status_code=400)

    @app.exception_handler(TransferConflict)
    async def stale_transfer_review(_request, exc):
        return JSONResponse({"detail": str(exc)}, status_code=409)

    @app.exception_handler(FundingReviewConflict)
    async def stale_funding_review(_request, exc):
        return JSONResponse({"detail": str(exc)}, status_code=409, headers={"Cache-Control": "no-store"})

    @app.exception_handler(FundingRefreshConflict)
    async def stale_funding_controls(_request, exc):
        return JSONResponse({"detail": str(exc)}, status_code=409, headers={"Cache-Control": "no-store"})

    @app.exception_handler(ModelConflict)
    async def stale_agent_models(_request, exc):
        return JSONResponse({"detail": str(exc)}, status_code=409, headers={"Cache-Control": "no-store"})

    @app.exception_handler(ControlConflict)
    async def stale_strategy_control(_request, exc):
        return JSONResponse({"detail": str(exc)}, status_code=409, headers={"Cache-Control": "no-store"})

    @app.exception_handler(AlertConflict)
    async def stale_alert_editor(_request, exc):
        return JSONResponse({"detail": str(exc)}, status_code=409, headers={"Cache-Control": "no-store"})

    @app.exception_handler(LookupError)
    async def missing_record(_request, _exc):
        return JSONResponse({"detail": "Record not found."}, status_code=404)

    async def provider_error(_request, _exc):
        return JSONResponse(
            {"detail": "Provider request failed. Check connectivity, market availability, and permissions."},
            status_code=502,
        )

    @app.exception_handler(ProviderDeferred)
    async def provider_deferred(_request, exc):
        return JSONResponse(
            {
                "detail": "Provider reads are queued or cooling down. Try again shortly.",
                "retry_after": exc.retry_after,
            },
            status_code=503,
            headers={"Retry-After": str(exc.retry_after), "Cache-Control": "no-store"},
        )

    for exception in (ccxt.BaseError, httpx.HTTPError):
        app.add_exception_handler(exception, provider_error)

    from sibyl.api.jobs import router as local_jobs_router

    app.include_router(local_jobs_router)
    from sibyl.api.asset_accounting import router as asset_accounting_router

    app.include_router(asset_accounting_router)
    from sibyl.api.transfer_groups import router as transfer_groups_router

    app.include_router(transfer_groups_router)
    from sibyl.api.account_returns import router as returns_router
    from sibyl.api.advanced_orders import router as advanced_orders_router
    from sibyl.api.notification_history import router as notification_history_router
    from sibyl.api.order_alerts import router as order_alerts_router

    app.include_router(advanced_orders_router)
    app.include_router(returns_router)
    app.include_router(order_alerts_router)
    app.include_router(notification_history_router)
    from sibyl.api.account_risk import router as account_risk_router

    app.include_router(account_risk_router)
    from sibyl.api.library import router as library_router
    from sibyl.api.workspace import router as workspace_router

    app.include_router(workspace_router)
    app.include_router(library_router)
    from sibyl.api.market_streams import router as market_stream_router
    from sibyl.api.routes import router

    app.include_router(router, prefix="/api/v1")
    app.include_router(market_stream_router, prefix="/api/v1")
    from sibyl.api.strategy_research import router as strategy_research_router

    app.include_router(strategy_research_router)
    from sibyl.api.market_relationships import router as market_relationships_router

    app.include_router(market_relationships_router)
    from sibyl.api.strategy_execution import router as strategy_execution_router

    app.include_router(strategy_execution_router)
    from sibyl.api.messaging import router as messaging_router

    app.include_router(messaging_router)
    from sibyl.api.account_streams import router as account_streams_router

    app.include_router(account_streams_router)
    from sibyl.api.channels import router as channels_router

    app.include_router(channels_router)
    from sibyl.api.whatsapp import router as whatsapp_router

    app.include_router(whatsapp_router)
    from sibyl.api.local_models import router as local_models_router

    app.include_router(local_models_router)
    from sibyl.api.strategy_alerts import router as strategy_alerts_router

    app.include_router(strategy_alerts_router)
    from sibyl.api.connection_alerts import router as connection_alerts_router

    app.include_router(connection_alerts_router)
    from sibyl.api.risk_alerts import router as risk_alerts_router

    app.include_router(risk_alerts_router)
    from sibyl.api.balance_checks import router as balance_checks_router

    app.include_router(balance_checks_router)
    from sibyl.api.funding_reviews import router as funding_reviews_router

    app.include_router(funding_reviews_router)
    from sibyl.api.funding_refresh import router as funding_refresh_router

    app.include_router(funding_refresh_router)
    from sibyl.api.funding_scans import router as funding_scans_router

    app.include_router(funding_scans_router)

    from sibyl.api.forecasting import router as forecasting_router

    app.include_router(forecasting_router)

    from sibyl.api.bitcoin import router as bitcoin_router

    app.include_router(bitcoin_router)

    from sibyl.api.investigations import router as investigations_router

    app.include_router(investigations_router)

    from sibyl.api.briefings import router as briefings_router

    app.include_router(briefings_router)

    from sibyl.api.alert_delivery import router as alert_delivery_router

    app.include_router(alert_delivery_router)

    from sibyl.api.message_deliveries import router as message_deliveries_router

    app.include_router(message_deliveries_router)

    @app.get("/health", tags=["System"])
    def health():
        """Report process readiness without exposing account or provider configuration."""
        return {"status": "ok", "version": __version__}

    mount_dashboard(app, config.dashboard_dir)
    return app

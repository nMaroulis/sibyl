"""Application factory, lifecycle ownership, and local API access controls."""

import asyncio
import secrets
from contextlib import asynccontextmanager, suppress
from dataclasses import dataclass
from pathlib import Path

import ccxt
import httpx
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from sibyl import __version__
from sibyl.agents.registry import AgentRegistry
from sibyl.config import Settings
from sibyl.services.account_sync import AccountSync
from sibyl.services.data_settings import DataSettings
from sibyl.services.market import Market
from sibyl.services.portfolio import Portfolio
from sibyl.services.research import Research
from sibyl.services.strategies import Strategies
from sibyl.services.trading import ExchangeTrading
from sibyl.storage import Store


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


def create_app(settings: Settings | None = None) -> FastAPI:
    """Create an isolated ASGI app; start persistence and workers only on startup."""
    config = settings or Settings()
    if config.host not in {"127.0.0.1", "localhost", "::1"} and not config.api_token.get_secret_value():
        raise ValueError("Set SIBYL_API_TOKEN before exposing the API beyond loopback.")

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        store = Store(config.data_dir)
        data_settings = DataSettings(config, store)
        data_settings.apply_startup()
        market = Market(config, store, data_settings)
        portfolio, research = Portfolio(market, store), Research(config, data_settings)
        strategies = Strategies(market, store)
        account_sync = AccountSync(market, store)
        agents = AgentRegistry(config, store, market, portfolio, strategies, research, account_sync)
        trading = ExchangeTrading(market, store)
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
        )

        async def worker():
            while True:
                await asyncio.to_thread(strategies.tick)
                await asyncio.sleep(30)

        async def news_worker():
            # This worker never shares the strategy loop or reads account credentials.
            while True:
                if research.news_service.default_mode == "live":
                    await asyncio.to_thread(research.news_service.refresh)
                await asyncio.sleep(30)

        async def account_worker():
            while True:
                await asyncio.to_thread(account_sync.tick)
                await asyncio.sleep(1)

        task = asyncio.create_task(worker())
        news_task = asyncio.create_task(news_worker())
        account_task = asyncio.create_task(account_worker())
        try:
            yield
        finally:
            for background in (task, news_task, account_task):
                background.cancel()
            for background in (task, news_task, account_task):
                with suppress(asyncio.CancelledError):
                    await background
            await asyncio.to_thread(account_sync.close)
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

    @app.exception_handler(LookupError)
    async def missing_record(_request, _exc):
        return JSONResponse({"detail": "Record not found."}, status_code=404)

    async def provider_error(_request, _exc):
        return JSONResponse(
            {"detail": "Provider request failed. Check connectivity, market availability, and permissions."},
            status_code=502,
        )

    for exception in (ccxt.BaseError, httpx.HTTPError):
        app.add_exception_handler(exception, provider_error)

    from sibyl.api.routes import router

    app.include_router(router, prefix="/api/v1")

    @app.get("/health", tags=["System"])
    def health():
        """Report process readiness without exposing account or provider configuration."""
        return {"status": "ok", "version": __version__}

    # A container serves the built React app from the same origin as the API.
    static_dir = Path(__file__).resolve().parents[3] / "frontend" / "dist"
    if static_dir.is_dir():

        class SPAFiles(StaticFiles):
            async def get_response(self, path, scope):
                from starlette.exceptions import HTTPException

                try:
                    return await super().get_response(path, scope)
                except HTTPException as exc:
                    if exc.status_code != 404 or path.startswith("api/") or "." in path.rsplit("/", 1)[-1]:
                        raise
                    return await super().get_response("index.html", scope)

        app.mount("/", SPAFiles(directory=static_dir, html=True), name="dashboard")
    return app

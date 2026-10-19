"""Validated application configuration; no network or filesystem work on import."""

from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from sibyl.agents.providers import ProviderId


class Settings(BaseSettings):
    """Configure a local workspace with ``SIBYL_`` environment variables."""

    model_config = SettingsConfigDict(env_prefix="SIBYL_", env_file=".env", extra="ignore")

    host: str = "127.0.0.1"
    port: int = Field(default=8000, ge=1, le=65535)
    data_dir: Path = Path(".sibyl")
    mode: Literal["demo", "live"] = "demo"
    market_exchange: Literal["binance", "coinbase", "kraken"] = "binance"
    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]
    api_token: SecretStr = SecretStr("")
    allow_live_trading: bool = False
    llm_provider: ProviderId = "none"
    llm_model: str = ""
    llm_base_url: str = "http://127.0.0.1:11434"

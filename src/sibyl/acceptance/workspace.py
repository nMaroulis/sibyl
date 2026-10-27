"""Isolated encrypted state and sanitized receipts for real Testnet checks."""

import json
import threading
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path

from sibyl.config import Settings
from sibyl.models import ConnectionCreate
from sibyl.storage import Store


class AcceptanceReport:
    """Keep evidence durable before writes, without serializing credentials or balances."""

    def __init__(self, workspace: Path, *, lose_entry_response: bool):
        self.path = workspace / "acceptance.json"
        self.lock = threading.RLock()
        self.values = {
            "started_at": datetime.now(UTC).isoformat(),
            "workspace": str(workspace.resolve()),
            "provider": "binance-testnet",
            "environment": "test",
            "ccxt": version("ccxt"),
            "order_cap_usdt": 15,
            "lose_entry_response": lose_entry_response,
            "checks": [],
            "phase": "starting",
        }
        self.update()

    def update(self, **values):
        """Atomically replace the private receipt so interruption leaves valid JSON."""
        with self.lock:
            self.values.update(values)
            temporary = self.path.with_suffix(".tmp")
            temporary.touch(mode=0o600, exist_ok=True)
            temporary.write_text(json.dumps(self.values, indent=2, allow_nan=False) + "\n")
            temporary.replace(self.path)

    def record(self, check, **evidence):
        """Record deliberately selected public evidence; never pass raw provider responses."""
        with self.lock:
            self.values["checks"].append({"check": check, **evidence})
            self.update()
        print(check, json.dumps(evidence), flush=True)


def create_workspace(source: Store, account_id: str, workspace: Path):
    """Copy only a dedicated Testnet account; never change the source workspace's flags."""
    selected = next((row for row in source.connections() if row.id == account_id), None)
    if selected is None or selected.exchange != "binance-testnet" or not selected.sandbox:
        raise ValueError("Choose a dedicated Binance Testnet connection.")
    workspace.mkdir(mode=0o700, parents=True, exist_ok=False)
    credentials = source.credentials(selected.id)
    settings = Settings(
        data_dir=workspace,
        _env_file=None,
        host="127.0.0.1",
        api_token="",
        mode="demo",
        news_mode="demo",
        llm_provider="none",
        allow_live_trading=True,
        allow_strategy_execution=True,
    )
    store = Store(workspace)
    store.save_data_profile("market", {"source": "demo", "profiles": {}})
    account = store.add_connection(
        ConnectionCreate(
            exchange="binance-testnet",
            label="Strategy acceptance — Testnet",
            api_key=credentials["apiKey"],
            secret=credentials["secret"],
            sandbox=True,
        )
    )
    return settings, account

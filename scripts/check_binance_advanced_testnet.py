"""Run finite native conditional/OCO/replacement acceptance in a new encrypted Testnet workspace."""

import argparse
from pathlib import Path
from unittest.mock import patch

import ccxt
from fastapi.testclient import TestClient

from sibyl.acceptance.advanced import AdvancedAcceptance
from sibyl.acceptance.advanced_transport import AdvancedTestnetTransport
from sibyl.acceptance.workspace import AcceptanceReport, create_workspace
from sibyl.api.app import create_app
from sibyl.config import Settings
from sibyl.storage import Store


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--account-id", required=True)
    parser.add_argument("--workspace", required=True, type=Path)
    parser.add_argument(
        "--execute-testnet",
        action="store_true",
        help="Authorize five native Testnet BUY commands, each at most 15 virtual USDT, and their cancellations",
    )
    parser.add_argument("--lose-oco-response", action="store_true")
    parser.add_argument(
        "--observe-fill-race",
        action="store_true",
        help="Authorize one additional capped marketable Testnet BUY limit; purchased virtual units may remain",
    )
    args = parser.parse_args()
    if not args.execute_testnet:
        parser.error("Explicit --execute-testnet is required.")
    settings, account = create_workspace(Store(Settings().data_dir), args.account_id, args.workspace)
    settings.allow_strategy_execution = False
    report = AcceptanceReport(args.workspace, lose_entry_response=False)
    report.update(suite="native-advanced-orders", lose_oco_response=args.lose_oco_response)
    transport = AdvancedTestnetTransport(
        ccxt.binance.fetch,
        report,
        lose_oco_response=args.lose_oco_response,
        observe_fill_race=args.observe_fill_race,
    )

    def fetch(adapter, url, method="GET", headers=None, body=None):
        return transport(adapter, url, method, headers, body)

    try:
        with patch.object(ccxt.binance, "fetch", fetch), TestClient(create_app(settings)) as client:
            client.portal.call(client.app.state.services.workers.close)
            AdvancedAcceptance(client, account, report).run(
                lose_oco_response=args.lose_oco_response, observe_fill_race=args.observe_fill_race
            )
    except Exception as error:
        report.update(phase="incomplete", error_type=type(error).__name__)
        print(
            "Acceptance stopped. Inspect the retained workspace and native Testnet orders; no uncertain write is retried."
        )
        return 1
    print("Advanced Testnet acceptance complete:", report.path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

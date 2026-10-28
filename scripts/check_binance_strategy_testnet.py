"""Opt-in real Binance Spot Testnet strategy acceptance; never production execution."""

import argparse
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

import ccxt
from fastapi.testclient import TestClient

from sibyl.acceptance.strategy import StrategyAcceptance
from sibyl.acceptance.transport import TestnetTransport
from sibyl.acceptance.workspace import AcceptanceReport, create_workspace
from sibyl.api.app import create_app
from sibyl.config import Settings
from sibyl.storage import Store


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--account-id", required=True)
    parser.add_argument("--workspace", type=Path, required=True, help="A new, isolated workspace directory")
    parser.add_argument(
        "--execute-testnet", action="store_true", help="Authorize at most one Testnet buy and one owned sell"
    )
    parser.add_argument(
        "--lose-entry-response",
        action="store_true",
        help="Deliberately discard the actual buy response to check identity recovery",
    )
    parser.add_argument(
        "--signal-wait", type=int, default=300, help="Wait 60–600 seconds for a real closed-candle entry"
    )
    args = parser.parse_args()
    if not args.execute_testnet:
        parser.error("Use --execute-testnet to authorize finite virtual-fund orders.")
    if not 60 <= args.signal_wait <= 600:
        parser.error("--signal-wait must be between 60 and 600 seconds.")
    try:
        settings, account = create_workspace(Store(Settings().data_dir), args.account_id, args.workspace)
    except ValueError as error:
        parser.error(str(error))
    report = AcceptanceReport(args.workspace, lose_entry_response=args.lose_entry_response)
    transport = TestnetTransport(ccxt.binance.fetch, report, lose_entry_response=args.lose_entry_response)

    def guarded_fetch(adapter, url, method="GET", headers=None, body=None):
        return transport(adapter, url, method, headers, body)

    def exercise(client, method):
        check = StrategyAcceptance(client, account, report, transport)
        try:
            method(check)
        except Exception:
            try:
                check.halt_on_failure()
            except Exception as error:
                report.record("failure_halt_unconfirmed", error_type=type(error).__name__)
            raise

    with patch.object(ccxt.binance, "fetch", guarded_fetch):
        try:
            with TestClient(create_app(settings)) as client:

                def before_restart(check):
                    check.start()
                    check.wait_for_entry(args.signal_wait)
                    check.prepare_restart()

                exercise(client, before_restart)
            with TestClient(create_app(settings)) as client:

                def after_restart(check):
                    check.after_restart()
                    check.close_position()

                exercise(client, after_restart)
            disabled = settings.model_copy(
                update={"allow_live_trading": False, "allow_strategy_execution": False}
            )
            with TestClient(create_app(disabled)) as client:
                check = StrategyAcceptance(client, account, report, transport)
                if check.job()["status"] != "stopped" or len(check.orders()) != 2:
                    raise RuntimeError("Final order/strategy evidence did not survive restart.")
                for order in check.orders():
                    detail = check.request("GET", f"/exchange-orders/{order['id']}/reconciliation")
                    if order["status"] != "closed" or detail["reconciliation"]["status"] != "matched":
                        raise RuntimeError("Retained native fills are not fully reconciled after restart.")
                if not check.request("GET", "/strategies/exchange/controls")["halted"]:
                    raise RuntimeError("Global halt did not survive restart.")
                report.record("disabled_restart_retains_orders_and_halt")
            if len(transport.attempts) != 2:
                raise RuntimeError("Acceptance did not exercise exactly two native order writes.")
            report.update(
                phase="complete",
                completed_at=datetime.now(UTC).isoformat(),
                partial_fill_acceptance="Not induced; no live partial-fill acceptance is claimed.",
            )
        except Exception as error:
            report.update(stopped_error_type=type(error).__name__)
            print(
                "Acceptance stopped. Inspect the retained workspace; no uncertain write was retried.",
                flush=True,
            )
            return 1
    print("Strategy Testnet acceptance complete. Evidence:", args.workspace, flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

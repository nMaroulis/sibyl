"""Opt-in Binance Spot Testnet acceptance through Sibyl's actual order API.

Only an existing binance-testnet account can supply credentials. An isolated,
retained encrypted workspace contains that one account. CCXT HTTP requests are
pinned to testnet.binance.vision, and production workspace flags are unchanged.
Ambiguous writes stop the check; retained state supports manual investigation.
"""

import argparse
import json
import time
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path
from unittest.mock import patch
from urllib.parse import urlsplit
from uuid import uuid4

import ccxt
from fastapi.testclient import TestClient

from sibyl.api.app import create_app
from sibyl.config import Settings
from sibyl.models import ConnectionCreate
from sibyl.storage import Store


class TestnetAcceptance:
    """Exercise real native test orders with finite reviewed amounts and durable evidence."""

    symbol = "BTC/USDT"
    cap = 15

    def __init__(self, client, account, report):
        self.client, self.account, self.report = client, account, report
        self.services = client.app.state.services

    def request(self, method, path, body=None):
        response = self.client.request(method, "/api/v1" + path, json=body)
        if response.status_code >= 400:
            raise RuntimeError(f"Acceptance HTTP {response.status_code}: {path}")
        return response.json()

    def record(self, check, **evidence):
        self.report["checks"].append({"check": check, **evidence})
        self.save()
        print(check, json.dumps(evidence), flush=True)

    def save(self):
        path = Path(self.report["workspace"]) / "acceptance.json"
        path.write_text(json.dumps(self.report, indent=2) + "\n")
        path.chmod(0o600)

    def quantity(self, price, owned=None):
        with self.services.market.adapter(self.account) as venue:
            amount = float(venue.amount_to_precision(self.symbol, 12 / price if owned is None else owned))
        if amount <= 0 or amount * price > self.cap:
            raise ValueError("Quantity cannot fit the test review cap")
        return amount

    def order(self, side, order_type, price, owned=None):
        self.report["phase"] = f"{side}_{order_type}_review"
        self.save()
        body = {
            "connection_id": self.account.id,
            "symbol": self.symbol,
            "side": side,
            "quantity": self.quantity(price, owned),
            "order_type": order_type,
            "idempotency_key": uuid4().hex,
        }
        if order_type == "limit":
            body["limit_price"] = price
        review = self.request("POST", "/exchange-orders/preview", body)
        if (
            review["environment"] != "test"
            or review["exchange"] != "binance-testnet"
            or review["notional"] > self.cap
        ):
            raise ValueError("Review escaped the test scope")
        self.record(
            "review",
            intent_id=review["id"],
            side=side,
            order_type=order_type,
            quantity=body["quantity"],
            reference_notional=review["notional"],
        )
        self.report["phase"] = f"{side}_{order_type}_submission"
        self.save()
        result = self.request(
            "POST", f"/exchange-orders/{review['id']}/confirm", {"confirmation": review["confirmation"]}
        )
        self.record(
            "submission",
            intent_id=review["id"],
            native_id=result.get("exchange_order_id"),
            status=result["status"],
        )
        if result["status"] not in {"open", "closed"} or not result.get("exchange_order_id"):
            raise RuntimeError("Unconfirmed/rejected submission; do not retry")
        repeated = self.request(
            "POST", f"/exchange-orders/{review['id']}/confirm", {"confirmation": review["confirmation"]}
        )
        if repeated.get("exchange_order_id") != result["exchange_order_id"]:
            raise RuntimeError("Repeated confirmation changed native identity")
        self.record("duplicate_confirmation_retained_identity", intent_id=review["id"])
        return result

    def reconcile(self, identity):
        self.report["phase"] = "reconciliation"
        self.save()
        result = None
        for _ in range(3):
            result = self.request("POST", f"/exchange-orders/{identity}/reconcile")
            if result["reconciliation"]["status"] == "matched":
                break
            time.sleep(0.5)
        summary = result["reconciliation"]
        self.record(
            "reconciliation",
            intent_id=identity,
            status=summary["status"],
            fills=summary["fill_count"],
            fees=summary["fees"],
        )
        if summary["status"] != "matched":
            raise RuntimeError("Native fills/fees did not reconcile; inspect retained state")
        return result

    def run(self):
        with self.services.market.adapter(self.account) as venue:
            venue.load_markets()
            ticker = venue.fetch_ticker(self.symbol)
            bid, ask = ticker.get("bid"), ticker.get("ask")
            if not bid or not ask or ask < bid:
                raise ValueError("Testnet has no usable BTC/USDT book")
            limit = float(venue.price_to_precision(self.symbol, bid * 0.85))
        order = self.order("buy", "limit", limit)
        if order["status"] != "open":
            raise RuntimeError("Resting test order unexpectedly filled; inspect retained state")
        review = self.request("POST", f"/exchange-orders/{order['id']}/cancel/preview")
        result = self.request(
            "POST",
            f"/exchange-orders/{order['id']}/cancel",
            {"cancel_id": review["id"], "confirmation": review["confirmation"]},
        )
        self.record("cancellation", intent_id=order["id"], status=result["status"])
        canceled = self.reconcile(order["id"])
        if canceled["order"]["status"] != "canceled":
            raise RuntimeError("Cancellation not confirmed; do not continue")
        with self.services.market.adapter(self.account) as venue:
            ask = venue.fetch_ticker(self.symbol)["ask"]
        bought = self.order("buy", "market", ask)
        detail = self.reconcile(bought["id"])
        if detail["order"]["status"] != "closed":
            raise RuntimeError("Buy is not terminal; do not continue")
        filled = detail["reconciliation"]["quantity"]
        fee = sum(max(0, row["cost"]) for row in detail["reconciliation"]["fees"] if row["currency"] == "BTC")
        with self.services.market.adapter(self.account) as venue:
            stamp = int(time.time() * 1000)
            lookup = venue.fetch_order_lookup_page(
                bought["client_order_id"], self.symbol, {}, stamp - 3600000, stamp
            )
            found = any(row.get("id") == bought["exchange_order_id"] for row in lookup.candidates)
            bid = venue.fetch_ticker(self.symbol)["bid"]
        if not found:
            raise RuntimeError("Client-ID read did not find the submitted order")
        self.record("native_client_id_lookup", intent_id=bought["id"], matched=True)
        sold = self.order("sell", "market", bid, owned=filled - fee)
        self.reconcile(sold["id"])
        self.report["phase"] = "complete"
        self.report["partial_fill_acceptance"] = (
            "Not induced; deterministic tests cover partial fills separately."
        )
        self.save()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--account-id", required=True)
    parser.add_argument(
        "--workspace", type=Path, required=True, help="New isolated directory; never an existing workspace"
    )
    parser.add_argument(
        "--execute-testnet", action="store_true", help="Explicitly allow the finite test-fund order lifecycle"
    )
    args = parser.parse_args()
    if not args.execute_testnet:
        parser.error(
            "Use --execute-testnet to authorize test-fund orders; no production account is accepted."
        )
    source = Store(Settings().data_dir)
    selected = next((row for row in source.connections() if row.id == args.account_id), None)
    if selected is None or selected.exchange != "binance-testnet" or not selected.sandbox:
        parser.error("Choose a dedicated Binance Testnet connection.")
    args.workspace.mkdir(mode=0o700, parents=True, exist_ok=False)
    credentials = source.credentials(selected.id)
    settings = Settings(
        data_dir=args.workspace,
        _env_file=None,
        host="127.0.0.1",
        api_token="",
        mode="demo",
        news_mode="demo",
        llm_provider="none",
        allow_live_trading=True,
        allow_strategy_execution=False,
    )
    store = Store(settings.data_dir)
    store.save_data_profile("market", {"source": "demo", "profiles": {}})
    account = store.add_connection(
        ConnectionCreate(
            exchange="binance-testnet",
            label="Testnet acceptance",
            api_key=credentials["apiKey"],
            secret=credentials["secret"],
            sandbox=True,
        )
    )
    del credentials
    report = {
        "started_at": datetime.now(UTC).isoformat(),
        "workspace": str(args.workspace.resolve()),
        "environment": "test",
        "provider": "binance-testnet",
        "ccxt": version("ccxt"),
        "review_cap_usdt": 15,
        "checks": [],
        "phase": "starting",
    }
    original_fetch = ccxt.binance.fetch

    def testnet_only(adapter, url, *positional, **named):
        if urlsplit(url).hostname != "testnet.binance.vision":
            raise RuntimeError("Acceptance transport refused a non-Testnet destination")
        return original_fetch(adapter, url, *positional, **named)

    with patch.object(ccxt.binance, "fetch", testnet_only):
        try:
            with TestClient(create_app(settings)) as client:
                check = TestnetAcceptance(client, account, report)
                check.run()
                identities = [row["intent_id"] for row in report["checks"] if row["check"] == "submission"]
            # Reopen with submission disabled and verify durable results without another write.
            with TestClient(create_app(settings.model_copy(update={"allow_live_trading": False}))) as client:
                survived = all(
                    client.get(f"/api/v1/exchange-orders/{identity}/reconciliation").status_code == 200
                    for identity in identities
                )
                report["restart_retained_orders"] = survived
                if not survived:
                    raise RuntimeError("Retained order evidence missing after restart")
            check.save()
        except Exception as error:
            report["stopped_error_type"] = type(error).__name__
            check = locals().get("check")
            if check:
                check.save()
            print(
                "Acceptance stopped. Inspect the retained workspace; no uncertain write was retried.",
                flush=True,
            )
            return 1
    print("Testnet acceptance complete. State and evidence:", args.workspace, flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

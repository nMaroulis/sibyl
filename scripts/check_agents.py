"""Opt-in real Ollama checks using the app's native agents in a disposable workspace.

Run with the development dependencies installed. No account, job, credential or
workspace profile is copied. Only the selected loopback Ollama port is reachable.
Checks inspect receipts and explicit answer markers, not overall answer quality;
review the retained answers and evidence before making a model-quality claim.
"""

import argparse
import asyncio
import json
import socket
import threading
import time
from contextlib import contextmanager
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from urllib.parse import urlsplit
from urllib.request import urlopen
from uuid import uuid4

from fastapi.testclient import TestClient
from protolink import request_context

from sibyl.agents.conversations import SibylRequest
from sibyl.api.app import create_app
from sibyl.config import Settings
from sibyl.storage import Store

CASES = {
    "setup": {
        "module": "technician",
        "message": "How do I connect my Binance account? Include the settings link. Keep it brief.",
        "expected_tools": ["exchange_setup"],
        "markers": ["/settings?tab=exchanges"],
    },
    "history": {
        "module": "broker",
        "message": "How can I see my account history in Sibyl? Give the steps and page link briefly.",
        "expected_tools": ["trade_help"],
        "markers": ["/trade?tab=history"],
    },
    "news": {
        "module": "reporter",
        "message": "Summarize the currently available news briefly. Name the source and explain whether these are demo stories.",
        "context": {"news_mode": "demo", "news_days": 7},
        "expected_tools": ["news_briefing"],
        "markers": ["demo"],
    },
    "market": {
        "module": "analyst",
        "message": "Analyze the selected ETH/USDT market briefly. State the source, timeframe and whether this is demo data. Is the technical score a probability of profit?",
        "context": {"symbol": "ETH/USDT", "timeframe": "1d", "limit": 60, "market_source": "demo"},
        "expected_tools": ["market_analysis"],
        "markers": ["eth", "demo"],
    },
    "consultation": {
        "message": "Ask Broker to reason about the limitations of backtests compared with paper runs in Sibyl. Delegate the reasoning question to Broker rather than executing its tools directly, then summarize the answer briefly.",
        "expected_inference": True,
        "markers": ["paper"],
    },
    "sibyl": {
        "message": "How can I see my account history? Consult Broker for the actual Sibyl instructions and give me the page link briefly.",
        "expected_tools": ["trade_help"],
        "markers": ["/trade?tab=history"],
    },
}


@contextmanager
def ollama_only(port):
    """Permit inference at one loopback port; reject other process-local TCP reads."""
    connect = socket.socket.connect
    connect_ex = socket.socket.connect_ex

    def restricted(sock, address):
        if isinstance(address, tuple) and address[0] in {"127.0.0.1", "::1"} and address[1] == port:
            return connect(sock, address)
        raise OSError("Acceptance checks allow only the selected local Ollama endpoint.")

    def restricted_ex(sock, address):
        if isinstance(address, tuple) and address[0] in {"127.0.0.1", "::1"} and address[1] == port:
            return connect_ex(sock, address)
        raise OSError("Acceptance checks allow only the selected local Ollama endpoint.")

    with (
        patch.object(socket.socket, "connect", restricted),
        patch.object(socket.socket, "connect_ex", restricted_ex),
    ):
        yield


def ask(client, name, case, **extra):
    """Call the actual HTTP handler once; retain its result and native report summary."""
    body = {
        key: value
        for key, value in case.items()
        if key not in {"expected_tools", "markers", "absent_markers", "expected_inference"}
    }
    body.update(extra)
    endpoint = "/api/v1/agents/ask/stream" if "module" in body else "/api/v1/sibyl/ask/stream"
    store = client.app.state.services.agents.network.run_store
    before = {record.run_id for record in store.list_report_records()}
    start = time.monotonic()
    response = client.post(endpoint, json=body)
    frames = [json.loads(line) for line in response.text.splitlines()] if response.status_code == 200 else []
    final = frames[-1] if frames else {}
    reply = final.get("reply", {})
    tools = [item["tool"] for item in reply.get("observations", [])]
    if reply.get("run_id"):
        summary = client.get(f"/api/v1/agents/runs/{reply['run_id']}/summary").json()
        tools = [item["tool"] for item in summary.get("tools", []) if item["outcome"] == "completed"]
    else:
        summary = None
    native = []
    for record in store.list_report_records():
        if record.run_id in before:
            continue
        run = store.get_report(record.run_id)
        events = []
        for event in run.events:
            data = {**event.payload.get("metadata", {}), **event.payload}
            if event.type == "llm.call.completed":
                events.append({"type": event.type, "native": data.get("native"), "agent": event.agent_name})
            elif event.type in {"run.failed", "action.rejected", "action.failed"}:
                events.append({"type": event.type, "error": data.get("error")})
            elif event.type == "context.prepared":
                events.append(
                    {"type": event.type, "tokens": data.get("manifest", {}).get("total_estimated_tokens")}
                )
        native.append(
            {
                "run_id": record.run_id,
                "events": events,
                "actions": list(run.actions),
                "terminal_state": (run.final_task or {}).get("state"),
                "error": (run.final_task or {}).get("metadata", {}).get("error"),
            }
        )
    answer = reply.get("answer", "").lower()
    checks = {
        "completed": final.get("type") == "reply" and bool(answer),
        "expected_tools": all(tool in tools for tool in case.get("expected_tools", [])),
        "answer_markers": all(marker.lower() in answer for marker in case.get("markers", [])),
        "no_foreign_markers": all(marker.lower() not in answer for marker in case.get("absent_markers", [])),
        "delegated_inference": not case.get("expected_inference")
        or any(
            action.get("kind") == "agent.call" and action.get("payload", {}).get("action") == "infer"
            for run in native
            for action in run["actions"]
        ),
    }
    row = {
        "case": name,
        "seconds": round(time.monotonic() - start, 2),
        "checks": checks,
        "http_status": response.status_code,
        "question": body["message"],
        "reply": reply,
        "summary": summary,
        "native_runs": native,
        "activity": [item for item in frames if item["type"] == "activity"],
        "error": final if final.get("type") == "error" else response.text if not frames else None,
    }
    print(f"{name}: {row['seconds']}s {checks}", flush=True)
    return row


def cancellation(client):
    """Stop a real model request after native inference starts; check health and no late answer."""
    network = client.app.state.services.agents.network
    chat = network.conversations.create()
    request_id = uuid4().hex
    began = threading.Event()

    async def run():
        async def progress(event):
            if event.type == "llm.call.started":
                began.set()

        with request_context({"progress": progress}):
            return await network.ask(
                SibylRequest(
                    message="Explain how to evaluate a backtest in detail.",
                    session_id=chat["id"],
                    request_id=request_id,
                )
            )

    future = client.portal.start_task_soon(run)
    started = began.wait(timeout=30)
    before = time.monotonic()
    health = client.get("/health")
    health_seconds = time.monotonic() - before
    before = time.monotonic()
    stopped = client.post(f"/api/v1/sibyl/conversations/{chat['id']}/cancel", json={"request_id": request_id})
    try:
        result = future.result(timeout=15)
        error = None
    except Exception as exc:
        result, error = {}, type(exc).__name__
        future.cancel()
    # Let the canceled model call settle; it cannot commit a completed UI turn.
    client.portal.call(asyncio.sleep, 1)
    saved = network.conversations.get(chat["id"])["turns"]
    row = {
        "case": "stop",
        "session_id": chat["id"],
        "error": error,
        "seconds": round(time.monotonic() - before, 2),
        "health_seconds": round(health_seconds, 3),
        "checks": {
            "inference_started": started,
            "health_responsive": health.status_code == 200 and health_seconds < 2,
            "cancel_accepted": stopped.status_code == 202,
            "cancelled": result.get("status") == "cancelled",
            "no_saved_answer": not saved,
        },
    }
    print(f"stop: {row['seconds']}s {row['checks']}", flush=True)
    return row


def main():
    """Select explicit local inference cases and write a reviewable JSON receipt."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", required=True)
    parser.add_argument("--context-window", type=int, default=32768)
    parser.add_argument("--url", default="http://127.0.0.1:11434")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--case", action="append", choices=[*CASES, "memory", "stop"])
    args = parser.parse_args()
    url = urlsplit(args.url)
    if (
        url.scheme != "http"
        or url.hostname not in {"localhost", "127.0.0.1", "::1"}
        or url.username
        or url.password
        or url.query
        or url.fragment
        or url.path not in {"", "/"}
    ):
        parser.error("Use a plain loopback Ollama URL without credentials or a path.")
    if not 4096 <= args.context_window <= 131072:
        parser.error("Choose a context window from 4096 to 131072 tokens.")
    cases = args.case or [*CASES, "memory", "stop"]
    rows = []
    report = {
        "time": datetime.now(UTC).isoformat(),
        "model": args.model,
        "protolink": version("protolink"),
        "context_window": args.context_window,
        "url": args.url,
        "results": rows,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)

    def save():
        args.output.write_text(json.dumps(report, indent=2) + "\n")

    with ollama_only(url.port or 80), TemporaryDirectory(prefix="sibyl-acceptance-") as directory:
        with urlopen(f"{args.url.rstrip('/')}/api/version", timeout=5) as response:
            report["ollama"] = json.load(response)
        settings = Settings(
            data_dir=Path(directory),
            _env_file=None,
            host="127.0.0.1",
            api_token="",
            mode="demo",
            news_mode="demo",
            allow_live_trading=False,
            allow_strategy_execution=False,
            llm_provider="ollama",
            llm_model=args.model,
            llm_base_url=args.url,
        )
        Store(settings.data_dir).save_data_profile("market", {"source": "demo", "profiles": {}})
        with TestClient(create_app(settings)) as client:
            client.post(
                "/api/v1/settings/llm",
                json={
                    "provider": "ollama",
                    "model": args.model,
                    "base_url": args.url,
                    "context_window": args.context_window,
                },
            ).raise_for_status()
            for name in cases:
                if name in CASES:
                    rows.append(ask(client, name, CASES[name]))
                elif name == "memory":
                    first = ask(
                        client,
                        "memory_set",
                        {
                            "module": "wiki",
                            "message": "Remember my research label is cobalt-kestrel-42. Reply briefly.",
                        },
                    )
                    rows.append(first)
                    if first["checks"]["completed"]:
                        rows.append(
                            ask(
                                client,
                                "memory_recall",
                                {
                                    "module": "wiki",
                                    "message": "What is the research label I gave you?",
                                    "markers": ["cobalt-kestrel-42"],
                                },
                                session_id=first["reply"]["session_id"],
                            )
                        )
                        rows.append(
                            ask(
                                client,
                                "memory_isolation",
                                {
                                    "module": "wiki",
                                    "message": "Have I given you a research label in this chat? Answer briefly.",
                                    "absent_markers": ["cobalt-kestrel-42"],
                                },
                            )
                        )
                else:
                    rows.append(cancellation(client))
                save()
            report["no_accounts_or_orders"] = (
                not client.app.state.services.store.connections() and not client.get("/api/v1/orders").json()
            )
            run_ids = [row["reply"]["run_id"] for row in rows if row.get("reply", {}).get("run_id")]
        # Startup must preserve successful reports and keep a stopped request stopped.
        with TestClient(create_app(settings)) as client:
            report["reports_survive_restart"] = all(
                client.get(f"/api/v1/agents/runs/{run_id}/summary").status_code == 200 for run_id in run_ids
            )
            for row in rows:
                if row["case"] == "stop":
                    row["checks"]["no_late_answer_after_restart"] = not client.get(
                        f"/api/v1/sibyl/conversations/{row['session_id']}"
                    ).json()["turns"]
        save()
    print(f"Receipt: {args.output}", flush=True)
    return int(
        not (
            all(all(row["checks"].values()) for row in rows)
            and report["no_accounts_or_orders"]
            and report["reports_survive_restart"]
        )
    )


if __name__ == "__main__":
    raise SystemExit(main())

"""Technician explains setup, supported connections and recorded diagnostics.

ProtoLink exposes these typed functions and their docstrings directly. Guides
provide instructions; status tools report saved metadata, not verified credentials.
"""

import json
from typing import Literal

from protolink import Agent, Tool

from sibyl.agents.utils.common import COMMON_PROMPT, Services
from sibyl.alerts.history.service import NotificationHistory
from sibyl.exchanges.catalog import CATALOG, exchange_spec
from sibyl.exchanges.registry import provider_catalog
from sibyl.messaging.reply_review import reply_evidence
from sibyl.messaging.review import delivery_evidence
from sibyl.services.workspace.llm_settings import ModelSettings

NAME = "Technician"
TAGLINE = "Keep everything connected"
DESCRIPTION = "Guide settings, exchange connection fields, model/agent setup, data sources, messaging and alerts; explain saved diagnostics."
SYSTEM_PROMPT = (
    "Use source_health for actual saved read outcomes, quota allowance/counter evidence, waiting work and coverage gaps. Distinguish application estimates from reported provider limits, transport success from credential/data validity, and read deferral from a provider outage. It is passive; do not recommend retrying uncertain writes or bypassing native limits. "
    "Use telegram_delivery_review to explain actual app-origin delivery outcomes and separate user acknowledgments. It cannot read private message bodies or send/review messages. "
    "Use notification_history for retained inbox cleanup policy, protections and actual receipts; never clear history for the user. "
    "Use background_service_status for the local OS login-service state and CLI instructions. Native manager state is not API readiness; the currently viewed server may be a manual process or another workspace. You cannot install/start/stop services. Never request environment-file contents or credentials. "
    "Use worker_incidents for saved stalls, observation gaps and confirmed resumption of progress; observation_ended means recovery is unknown. It cannot establish external uptime or restart a worker. Use workspace_operations for actual worker health and backup/recovery instructions. Never request passphrases in chat. "
    "Help users configure Sibyl, not just diagnose connection counts. For how-to questions call "
    "settings_guide with exchanges, models, news, market, messaging, alerts, strategies or workspace "
    "(including installation and launcher help); "
    "overview lists the available sections. For a particular "
    "exchange, call exchange_setup with its catalog ID, e.g. binance. Use connection_status only when "
    "actual saved setup matters. Give numbered, practical instructions and a settings link. Explain "
    "that users can connect multiple accounts and view combined or individual portfolios. No account is "
    "active by default; Demo is an explicit preview and turns off when an actual account is active. "
    "Never ask users to paste secrets into chat. Do not claim connectivity was verified by listing "
    "metadata. Explain provider-specific credential fields from the tool. Telegram is available with encrypted bot credentials, one allowed private user, "
    "explicit connection checks and enable/pause. Discord private HTTP DMs, Slack Socket Mode, signed WhatsApp Cloud API webhooks, paired IMAP/SMTP email and the separately linked local Signal bridge are also implemented. Agents cannot connect accounts or "
    "mutate settings for the user. For saved read-failure alerts and notifications call connection_alerts; "
    "these are transport observations, not uptime checks, full data validation or verification of current credentials. "
)

GUIDES = {
    "overview": {
        "url": "/settings",
        "steps": [
            "Settings has Exchanges, AI models, News, Market data, Messaging and Workspace sections.",
            "Choose a section for its setup instructions. Alerts and Strategies have dedicated workspaces and help here too.",
            "Enter credentials only in the appropriate settings form, never in an assistant chat. Exchange/API keys are stored locally and encrypted on the Python backend machine.",
        ],
    },
    "strategies": {
        "url": "/strategies?view=monitor",
        "steps": [
            "Use Halt automation above the strategy workspace to block new automatic strategy orders across all accounts and pause exchange runs.",
            "Wait for confirmation; an already admitted native request can finish before the halt returns. Existing orders and holdings remain live.",
            "Approved cancellation policies, manual Trade, separately reviewed exits and paper runs keep their existing permissions.",
            "Review & release requires the displayed phrase. Releasing resumes no run; inspect orders/fills and Resume each run explicitly. Old unused Start reviews stay invalid.",
        ],
    },
    "exchanges": {
        "url": "/settings?tab=exchanges",
        "steps": [
            "Choose an exchange, give the account a label and enter its required credentials in Settings, never in chat.",
            "Inspect the exchange feature tabs before connecting. Use balance/order-history read permissions; add spot trading permission only for supported manual orders or explicitly approved exchange strategies. Keep withdrawals and wallet transfers disabled; restrict IPs where supported.",
            "Save the connection and use its connection check to verify it. Saving metadata alone is not verification. Optional Live order updates supports Binance/Testnet, Coinbase Advanced and Kraken private signals; activate that account and Enable signals. It only wakes separately enabled REST order/fill/discovery readers, preserves pauses and never trades. Signal and scheduling timestamps do not prove reconciliation.",
            "Open Account after activating the account to include it in the portfolio. Connect and activate more accounts to view combined balances or select one account.",
            "To replace API credentials for the same account, use Saved accounts → Update keys, deactivate the connection, enter a complete key set and confirm the same-account assertion/phrase. Check access and reactivate explicitly. History remains attached to this account ID. Use a new connection for a different account; existing venue orders are not cancelled.",
            "For a preview, explicitly enable Demo. Actual active accounts turn Demo off; test environments remain clearly labeled.",
            "For automated spot strategies, open Strategies and expand Run on a connected exchange. Both SIBYL_ALLOW_LIVE_TRADING and SIBYL_ALLOW_STRATEGY_EXECUTION must be enabled on the backend. Review the exact account, pair, budget and limits, then type the confirmation. Start with test funds. Pause/Stop do not cancel venue orders or liquidate holdings.",
        ],
    },
    "models": {
        "url": "/settings?tab=models",
        "steps": [
            "Choose API or Local and a ProtoLink provider.",
            "Choose a predefined model or enter its custom ID. Save as workspace default applies to agents without an override; Save profile only keeps the default unchanged.",
            "Expand Agent models to choose a provider and preset/custom model for Sibyl or any specialist. An override reuses its provider profile key/endpoint. Follow workspace default removes it; tool mode applies only to that selected agent.",
            "For API providers, enter the key in Settings. For a local server, set the endpoint; for llama.cpp-local, supply an existing GGUF path.",
            "For Ollama, use Check status to detect the server and installed models, Start Ollama for an installed local CLI, and the download/setup links if it is missing. Model installation is separate. Save to apply configuration to new turns; already queued/running requests keep their frozen team choices. No provider call is made just by saving. None leaves module snapshots available; Sibyl requires a model. Mock produces simulated answers.",
        ],
    },
    "news": {
        "url": "/settings?tab=news",
        "steps": [
            "Choose Live sources or the exclusive Demo preview.",
            "Select publisher cards; public feeds need no key. Configure NewsAPI credentials if using NewsAPI.",
            "Open News to collect/read the archive and inspect source health and dates.",
            "Sentiment is English VADER text polarity, not price direction. Reporter reads the fetched archive and cached Fear & Greed index.",
        ],
    },
    "market": {
        "url": "/settings?tab=market",
        "steps": [
            "Choose a public exchange, a saved exchange account or a data API source.",
            "Public exchange data do not require account credentials. Provide a key in Settings only for a provider that requires one.",
            "Choose the source and any supported coin/pair in Markets; edit the watchlist there.",
            "Quotes-only providers cannot supply candle history or technical indicators. Demo is an explicit separate source.",
            "Expand Source health to inspect observed reads, queues and Read allowances & quota evidence. App allowances, reported Binance IP counters and conservative Kraken/Coinbase Exchange estimates are separate. Unsupported endpoint costs and actual account tiers stay unknown. Refresh reads local diagnostics and never probes a provider. Native writes/cancellations are never queued or replayed by this read policy; provider limits and external traffic can still reject requests.",
        ],
    },
    "messaging": {
        "url": "/settings?tab=messaging",
        "steps": [
            "Messaging lets you talk to Sibyl through another app. Telegram, Discord private HTTP DMs, Slack Socket Mode, signed WhatsApp webhooks, paired IMAP/SMTP email and a local unofficial Signal bridge are implemented. Telegram can optionally send long replies and scheduled briefings as bounded UTF-8 text documents; incoming documents, local photo OCR and bounded speech transcription are opt-in with optional local processors. Scheduled briefings and per-rule alerts can select any of the six checked private text channels; enabling chat alone does not enable these deliveries.",
            "Review message delivery opens actual queued text, the recorded private target and part outcomes. Withdraw queued remainders or record separate received/dismissed user reviews; admitted sends must finish first, and review never resends or changes native confirmation.",
            "Telegram: create a bot with BotFather, enter its token and your numeric user ID, save, Check bot, then Enable Telegram. Setup and enabling do not require an AI model. Open the bot’s private chat and press Start; help/status work immediately, while questions receive setup guidance until a model is active. WhatsApp needs a Meta business phone, explicit Graph version, signed public HTTPS callback /api/v1/webhooks/whatsapp and messages subscription. Email needs a dedicated TLS mailbox plus private pairing phrase in each subject; From alone is not authorization. For implemented channels save the private recipient and complete credentials, Check connection, then Enable private replies. Pause remains available during a model request; editing/removal requires pause. Sent receipts mean provider acceptance, not human receipt. Telegram attachments are separate opt-in preferences: PDF/text/Markdown import to My research, photo text needs local Tesseract and voice/audio needs local FFmpeg plus whisper-cli and a .bin model. No model/program is downloaded. Documents are retained; media originals are discarded after uncertain OCR/transcription. Native Wiki/Reporter tools read the retained citations. No group chats are processed.",
        ],
    },
    "alerts": {
        "url": "/alerts?tab=strategies",
        "steps": [
            "Open More → Alerts → Strategy alerts, or Run alerts in a strategy monitor.",
            "Choose a saved run, select pauses/errors/recovery and/or lifecycle changes, then Watch strategy events. Only future committed journal entries are watched; existing errors are not replayed.",
            "Pausing an alert stops notifications only. Resume starts from the current journal tail, while armed alerts retain their cursor across API restarts. The API must be running to process events.",
            "Inbox and the top-bar bell show retained evidence with Paper/Exchange and Demo/test labels. Open monitor follows that exact run. Mark read acknowledges a notice without deleting it.",
            "Connections tab: select a configured/previously observed source and consecutive failed-read threshold. Successes of the same operation can notify recovery. Rules watch future recorded HTTP reads only, without polling or activating the source. Demo has no connection; View example is isolated.",
            "Read counters reset on session/profile changes, recording gaps or more than five minutes between reads. No observations means no connection-status conclusion. Recovery describes successful transport reads, not fully validated data or verified current credentials. Pausing/resuming begins a new observation window.",
            "Account risk tab: select a fixed set of up to ten active accounts in one environment and a reference feed. Choose a value floor in USDT, asset/top-three concentration, overall HHI concentration (0–100), observed-value drawdown, or hourly historical basket volatility/95% daily expected shortfall (up to eight held assets and 60/90/180 days). Arming authorizes background balance/quote reads. New connections are not automatically included; deactivate a pinned account and the watch waits for complete coverage.",
            "Recovery levels prevent repeated notices near a limit. Edits save paused; Resume resets the observed peak and incident state. Drawdown includes deposits and withdrawals, so it is not investment return. View evidence reads retained valuation details without fetching accounts.",
            "Inbox → History export & retention exports JSON/CSV with kind and UTC date filters (up to 2,000 newest notices). Automatic cleanup is off by default; saving an opt-in age policy clears only old read notices in bounded batches. Unread notices and unfinished delivery evidence are protected. Disabling the policy stops later automatic deletion; rules, financial records and delivery receipts remain separate.",
            "No AI model is required. A rule’s Delivery button selects Telegram, Discord, Slack, Signal, WhatsApp or email to its checked private recipient. WhatsApp requires an open private 24-hour reply window; no templates are sent. A changed connection revision or recipient requires selecting the checked target again. Every save starts from future events; existing inbox entries stay local. Cooldowns suppress extra messages and delivery windows reject stale observations. Alerts never trade, stop strategies or cancel orders. Worker incidents are observed separately and do not prove external host uptime.",
        ],
    },
    "workspace": {
        "url": "/settings?tab=workspace",
        "steps": [
            "Workspace displays Python process CPU (one busy CPU = 100%), resident memory, threads, database/WAL bytes, free workspace-volume space and process uptime. CPU requires two observations at least five seconds apart; Ollama/browser/other processes are excluded. Provider saved read history exposes latency histogram upper bounds and sample coverage, not external uptime.",
            "Inspect server configuration, actual background-worker progress/faults, encrypted backup controls and documentation links in Workspace. Use workspace_operations for current diagnostics. Run health check in Workspace explicitly creates a bounded read-only SQLite check and content-free JSON report; download is passive, and reports expire on restart. A quick check does not verify account data or every database invariant. A worker heartbeat does not prove provider readiness or successful trades.",
            "Complete release wheels include the dashboard and can run with sibyl --open-browser, without Node.js. Use sibyl --version or --help for launcher options. Public wheel URLs require a published GitHub Release. Homebrew, PyPI and prebuilt registry images remain optional future work; no new repository is needed for the Python package.",
            "Source checkouts keep their repository .sibyl workspace. Installed apps default to per-user application data: macOS Application Support/Sibyl, Windows Local AppData/Sibyl or Linux XDG data/sibyl. Use --data-dir or SIBYL_DATA_DIR to open an existing workspace; no installer moves or deletes it.",
            "Background service in Workspace reads native launchd/systemd/Task Scheduler status. Use sibyl service preview to inspect generated choices, install to register next-login startup without starting now, then start deliberately. Stop disables future login starts until the next start. Reinstall with --replace after stopping when the Python environment moves. No admin/root service or password is requested; Windows requires the user to be logged in and task termination may be abrupt. Uninstall retains workspace/vault/logs. A private --env-file path can be supplied explicitly; shell-only environment values are not copied.",
            "Use --env-file for an explicit configuration file, --no-env-file to ignore .env, and --port for a different listening port. Use Workspace backups for encrypted online SQLite snapshots, inspection/download and separate-directory restore. Keep the archive passphrase outside agent chat. For manual filesystem copies, stop the app and copy its databases and vault key together.",
            "If workspace access is token-protected, enter the server's configured access token in the browser's access field, never in agent chat.",
            "Local jobs in Workspace saves paused health-check, retained accounting or pinned forecast-training tasks. Run once queues explicit work; Enable schedule starts future occurrences. Pausing stops scheduling, Cancel targets one run, and Archive also withdraws queued/run interest. Inspect/download actual receipts; read-only interrupted work can retry, while training is never automatically repeated after interruption.",
            "Credential vault rotates only local wrapping encryption with an explicit phrase and interruption recovery. It never revokes provider tokens or shares key files with agents. Keep recovery key files until completion, preserve matching backups and review credential-bound funding sync controls after rotation.",
            "This is a local workspace. Hosted multi-user accounts and tenant isolation are deferred.",
        ],
    },
}


def create_agent(services: Services, **runtime) -> Agent:
    """Register this specialist's evidence and help tools on a native Agent.

    Args:
        services: Workspace domain services; credentials stay in their owners.
        **runtime: AgentGroup configuration, including the lazy model factory,
            native state, worker defaults and context policy.

    Returns:
        An unstarted Agent. Static guides run inline; domain reads inherit the
        runtime's execution policy (bounded threads in Sibyl). AgentGroup owns
        startup and shutdown.
    """

    def connection_status() -> dict:
        """Inspect configured accounts, active/Demo flags, model setup and history-import progress.

        Use to understand the workspace's saved setup or missing configuration. This
        metadata does not verify exchange connectivity or model-provider availability.
        settings_guide and exchange_setup provide instructions without needing account details.
        """
        return {
            "connections": [item.model_dump(mode="json") for item in services.store.connections()],
            "mode": services.settings.mode,
            "market_exchange": services.settings.market_exchange,
            "permissions": "Agents are read-only. Manual spot trading depends on provider support, API permissions and the server execution setting.",
            "history_imports": services.account_sync.snapshot()["jobs"] if services.account_sync else [],
            "history_help": "Trade → Account history → Fills & imports. Sync resumes saved pages. Pause active work before Rescan available history to refresh older fees/fills within provider retention; retained observations are never deleted.",
            "history_scope": "Imports cover selected spot markets and provider retention, not reconciled account history or exchange P&L.",
            "model": ModelSettings(services.settings, services.store).public(),
        }

    def connection_alerts() -> dict:
        """Explain configured connection alerts and the last ten recorded read-failure/recovery notices.

        Returns saved rules, observed transport notices and the Connections alerts link.
        These observations do not establish continuous uptime or current credential validity.
        """
        with services.store.db() as db:
            rows = db.execute(
                "SELECT payload,created_at FROM alert_notifications "
                "WHERE json_extract(payload,'$.kind')='connection' "
                "ORDER BY created_at DESC,rowid DESC LIMIT 10"
            ).fetchall()
        return {
            "rules": services.market.connection_alerts.rules(),
            "recent_notifications": [
                {**json.loads(row["payload"]), "created_at": row["created_at"]} for row in rows
            ],
            "url": "/alerts?tab=connections",
            "scope": "Recorded transport reads only; no continuous uptime or credential verification. Optional private delivery through any of the six checked text channels is selected separately for each alert rule.",
        }

    def source_health(source_id: str = "") -> dict:
        """Explain observed connection reads, queued work, read allowances and reported quota evidence.

        Supply a known source ID such as binance, kraken or connection:<saved ID>;
        omit it for up to twelve default/observed sources. Returns observation times,
        transport outcomes, application budget estimates, provider counters and
        unreviewed-cost gaps. These do not establish current credentials, account
        tier, complete quota coverage or external uptime. No provider check is run.
        """
        report = services.market.provider_health(source_id or None)
        rows = report["items"]
        if not source_id:
            rows = [
                row
                for row in rows
                if row["default"] or row["requests"] or row["quotas"]["attempts"] or row["queued"]
            ]
        return {
            "items": rows[:12],
            "matching_count": len(rows),
            "limit": 12,
            "as_of": report["as_of"],
            "started_at": report["started_at"],
            "scope": "single_process_observations",
            "url": "/settings?tab=market",
        }

    def settings_guide(
        section: Literal[
            "overview",
            "exchanges",
            "models",
            "news",
            "market",
            "messaging",
            "alerts",
            "strategies",
            "workspace",
        ] = "overview",
    ) -> dict:
        """Explain setup steps and controls for a settings section. overview lists sections; choose
        exchanges, models, news, market, messaging, alerts, strategies or workspace. Returns
        practical instructions and exact in-app links. Never changes settings or needs credentials
        in chat.
        """
        return {"section": section, **GUIDES[section], "sections": list(GUIDES)}

    def exchange_setup(exchange: str = "binance", feature_details: bool = False) -> dict:
        """Explain how to connect a particular exchange and which features Sibyl implements for it.

        Supply the catalog exchange ID, such as binance, kraken, okx or demo. Returns
        required form fields, feature statuses, local key-storage details,
        environment labels and setup steps. Set feature_details for each feature's full limitations. Never paste credentials in chat.
        """
        if exchange not in CATALOG:
            return {"error": "Choose a supported exchange.", "exchanges": list(CATALOG)}
        spec = exchange_spec(exchange)
        fields = [] if spec.simulated else ["api_key", "secret"]
        if spec.passphrase:
            fields.append("passphrase")
        if spec.uid:
            fields.append("uid (API memo)")
        catalog = provider_catalog()
        exchange_info = dict(next(item for item in catalog["items"] if item["id"] == exchange))
        if not feature_details:
            exchange_info["support"] = [
                {
                    "id": group["id"],
                    "label": group["label"],
                    "summary": group["summary"],
                    "features": {feature["id"]: feature["status"] for feature in group["features"]},
                }
                for group in exchange_info["support"]
            ]
            exchange_info = {
                key: exchange_info[key]
                for key in (
                    "id",
                    "name",
                    "account",
                    "market_orders",
                    "limit_orders",
                    "support",
                )
            }
        return {
            # Put setup guidance before the matrix so native context previews retain it.
            **GUIDES["exchanges"],
            "required_fields": ["label", *fields],
            "key_storage": catalog["key_storage"],
            "manual_execution_enabled": services.settings.allow_live_trading,
            "note": "Demo accepts no credentials." if spec.simulated else spec.note,
            "test_environment": spec.test_environment,
            "exchange": exchange_info,
        }

    agent = Agent(
        name="sibyl-technician",
        description=DESCRIPTION,
        tools=[
            connection_status,
            connection_alerts,
            source_health,
            Tool.from_callable(settings_guide, sync_execution="inline"),
            exchange_setup,
        ],
        system_prompt=COMMON_PROMPT + SYSTEM_PROMPT,
        **runtime,
    )
    agent.card.capabilities.delegation = False

    @agent.tool
    def notification_history() -> dict:
        """Inspect the saved inbox retention policy, eligible counts and recent cleanup receipts.

        Explains which old read notices are eligible, and which unread or unfinished
        delivery records are protected. Includes the export/retention controls link.
        This tool cannot acknowledge, export or delete notices or change the policy.
        """
        return {**NotificationHistory.read_status(services.store), "url": "/alerts?tab=inbox"}

    @agent.tool
    def workspace_operations() -> dict:
        """Inspect worker progress, Python process resources, the last explicit database check and
        local job outcomes. Explain encrypted backup/restore controls. Counts do not prove provider
        readiness or completed trades. Never restarts workers, decrypts archives or asks for
        passphrases in chat.
        """
        return {
            "health": services.workers.snapshot() if services.workers else {"available": False},
            "last_health_report": services.workers.diagnostics.last() if services.workers else None,
            "jobs": {
                "run_counts": services.workers.jobs.state()["run_counts"],
                "items": [
                    {key: row[key] for key in ("id", "label", "kind", "state", "next_due", "latest_run")}
                    for row in services.workers.jobs.state()["items"][:12]
                ],
                "limit": 12,
            }
            if services.workers and services.workers.jobs
            else {"available": False},
            "url": "/settings?tab=workspace",
            "backup_help": "Create a passphrase-encrypted archive in Settings → Workspace. It contains local databases, documents and the vault key inside encryption. Download it and keep the passphrase separately. Restore creates a separate workspace with automatic work paused. Launch the returned directory, review connections/orders, complete recovery and restart. Accounts remain inactive until explicitly enabled.",
        }

    @agent.tool
    def background_service_status() -> dict:
        """Inspect the current user's installed OS service, observed process state and CLI controls.

        Use for startup-at-login, installation, start/stop, log locations or moved
        Python environments. Returns verified service ownership and workspace matching.
        OS state does not prove HTTP readiness or worker progress. Changes require
        explicit local CLI commands; this tool cannot manage a service.
        """
        from sibyl.installation.services.manager import service_status

        return {
            **service_status(services.store.path.parent, services.settings.port),
            "url": "/settings?tab=workspace",
        }

    @agent.tool
    def worker_incidents() -> dict:
        """Read five recent worker stalls, observer freshness and sample gaps. First detection is
        sampled; recovery requires a later successful iteration. Observation ending leaves recovery
        unknown. Local incidents do not establish host/exchange uptime or authorize worker
        restart/cancellation.
        """
        if not services.workers:
            return {"available": False}
        result = services.workers.watchdog.snapshot()
        return {
            **result,
            "items": result["items"][:5],
            "gaps": result["gaps"][:5],
            "limit": 5,
            "url": "/settings?tab=workspace",
        }

    @agent.tool
    def telegram_delivery_review() -> dict:
        """Inspect app-origin notification outcomes by channel and Telegram reply outcomes, without private text or targets.

        Explain Settings → Messaging review controls: unsent withdrawal and separate
        user acknowledgments. Reviews never resend or replace native confirmation.
        """
        return {
            **delivery_evidence(services.store),
            "reply_items": reply_evidence(services.store),
            "note": "App-origin and conversation outcomes remain separate. Alert delivery history → Review delivery inspects exact app-origin text/targets; Settings → Messaging reviews Telegram conversation replies; user acknowledgment never changes native confirmation or resends a message.",
        }

    return agent

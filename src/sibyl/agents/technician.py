"""Technician explains setup, supported connections and recorded diagnostics.

ProtoLink exposes these typed functions and their docstrings directly. Guides
provide instructions; status tools report saved metadata, not verified credentials.
"""

import json
from typing import Literal

from protolink import Agent

from sibyl.agents.common import COMMON_PROMPT, Services
from sibyl.exchanges.catalog import CATALOG, exchange_spec
from sibyl.exchanges.registry import provider_catalog
from sibyl.services.llm_settings import ModelSettings

NAME = "Technician"
TAGLINE = "Keep everything connected"
DESCRIPTION = "Guide settings, exchange connection fields, model/agent setup, data sources, messaging and alerts; explain saved diagnostics."
SYSTEM_PROMPT = (
    "Help users configure Sibyl, not just diagnose connection counts. For how-to questions call "
    "settings_guide with exchanges, models, news, market, messaging, alerts, strategies or workspace; "
    "overview lists the available sections. For a particular "
    "exchange, call exchange_setup with its catalog ID, e.g. binance. Use connection_status only when "
    "actual saved setup matters. Give numbered, practical instructions and a settings link. Explain "
    "that users can connect multiple accounts and view combined or individual portfolios. No account is "
    "active by default; Demo is an explicit preview and turns off when an actual account is active. "
    "Never ask users to paste secrets into chat. Do not claim connectivity was verified by listing "
    "metadata. Explain provider-specific credential fields from the tool. Telegram is available with encrypted bot credentials, one allowed private user, "
    "explicit connection checks and enable/pause. Other messaging channels are unavailable previews. Agents cannot connect accounts or "
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
            "Save the connection and use its connection check to verify it. Saving metadata alone is not verification.",
            "Open Account after activating the account to include it in the portfolio. Connect and activate more accounts to view combined balances or select one account.",
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
        ],
    },
    "messaging": {
        "url": "/settings?tab=messaging",
        "steps": [
            "Messaging lets you talk to Sibyl through another app. Telegram is implemented; WhatsApp, Discord, Slack, Signal and Email are unavailable previews.",
            "Telegram: create a bot with BotFather, enter its token and your numeric user ID, save, Check bot, then Enable Telegram. Setup and enabling do not require an AI model. Open the bot’s private chat and press Start; help/status work immediately, while questions receive setup guidance until a model is active. Other channels remain unavailable previews.",
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
            "Account risk tab: select a fixed set of up to ten active accounts in one environment and a reference feed. Choose a value floor in USDT, asset concentration or observed-value drawdown limit. Arming authorizes background balance/quote reads. New connections are not automatically included; deactivate a pinned account and the watch waits for complete coverage.",
            "Recovery levels prevent repeated notices near a limit. Edits save paused; Resume resets the observed peak and incident state. Drawdown includes deposits and withdrawals, so it is not investment return. View evidence reads retained valuation details without fetching accounts.",
            "No AI model is required. Alerts do not execute, stop strategies, cancel orders, close positions, detect silent worker outages or send external messages.",
        ],
    },
    "workspace": {
        "url": "/settings?tab=workspace",
        "steps": [
            "Inspect server configuration and documentation links in Workspace.",
            "If workspace access is token-protected, enter the server's configured access token in the browser's access field, never in agent chat.",
            "This is a local workspace. Hosted multi-user accounts and tenant isolation are deferred.",
        ],
    },
}


def create_agent(services: Services, **runtime) -> Agent:
    """Define Technician's read-only diagnostic and setup tools."""

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
            "scope": "Recorded transport reads only; no continuous uptime, credential verification or external delivery.",
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
        """Get step-by-step setup instructions and links for a Sibyl settings or operations section.

        Choose models for API/Local providers, per-agent models or Ollama; exchanges
        for account activation; news/market for data sources; messaging for Telegram;
        alerts or strategies for their controls; workspace for local access settings.
        overview lists the settings sections. This tool explains setup without changing it.
        """
        return {"section": section, **GUIDES[section], "sections": list(GUIDES)}

    def exchange_setup(exchange: str = "binance") -> dict:
        """Explain how to connect a particular exchange and which features Sibyl implements for it.

        Supply the catalog exchange ID, such as binance, kraken, okx or demo. Returns
        required form fields, the implemented support matrix, local key-storage details,
        environment labels and steps to connect/activate accounts. Never paste credentials in chat.
        """
        if exchange not in CATALOG:
            return {"error": "Choose a supported exchange.", "exchanges": list(CATALOG)}
        spec = exchange_spec(exchange)
        fields = [] if spec.simulated else ["api_key", "secret"]
        if spec.passphrase:
            fields.append("passphrase")
        if spec.uid:
            fields.append("uid (API memo)")
        return {
            "exchange": next(item for item in provider_catalog()["items"] if item["id"] == exchange),
            "key_storage": provider_catalog()["key_storage"],
            "manual_execution_enabled": services.settings.allow_live_trading,
            "required_fields": ["label", *fields],
            **GUIDES["exchanges"],
            "note": "Demo accepts no credentials." if spec.simulated else spec.note,
            "test_environment": spec.test_environment,
        }

    agent = Agent(
        name="sibyl-technician",
        description=DESCRIPTION,
        tools=[
            connection_status,
            connection_alerts,
            settings_guide,
            exchange_setup,
        ],
        system_prompt=COMMON_PROMPT + SYSTEM_PROMPT,
        **runtime,
    )
    agent.card.capabilities.delegation = False
    return agent

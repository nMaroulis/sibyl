"""Technician: connection status and practical help for every settings section."""

from protolink import Agent

from sibyl.agents.common import COMMON_PROMPT, Services, background_tool
from sibyl.exchanges.catalog import CATALOG, exchange_spec
from sibyl.exchanges.registry import provider_catalog
from sibyl.services.llm_settings import ModelSettings

NAME = "Technician"
TAGLINE = "Keep everything connected"
DESCRIPTION = "Explain account connectivity, settings and read-only API permissions. Never request secrets."
SYSTEM_PROMPT = (
    "Help users configure Sibyl, not just diagnose connection counts. For how-to questions call "
    "settings_guide with exchanges, models, news, market, messaging or workspace. For a particular "
    "exchange, call exchange_setup with its catalog ID, e.g. binance. Use connection_status only when "
    "actual saved setup matters. Give numbered, practical instructions and a settings link. Explain "
    "that users can connect multiple accounts and view combined or individual portfolios. No account is "
    "active by default; Demo is an explicit preview and turns off when an actual account is active. "
    "Never ask users to paste secrets into chat. Do not claim connectivity was verified by listing "
    "metadata. Explain provider-specific credential fields from the tool. Telegram is available with encrypted bot credentials, one allowed private user, "
    "explicit connection checks and enable/pause. Other messaging channels are unavailable previews. Agents cannot connect accounts or "
    "mutate settings for the user. "
)

GUIDES = {
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
            "Choose a predefined model or enter its custom ID.",
            "For API providers, enter the key in Settings. For a local server, set the endpoint; for llama.cpp-local, supply an existing GGUF path.",
            "For Ollama, use Check status to detect the server and installed models, Start Ollama for an installed local CLI, and the download/setup links if it is missing. Model installation is separate. Save to activate the model for new turns. No provider call is made just by saving. None leaves module snapshots available; Sibyl requires a model. Mock produces simulated answers.",
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
            "WhatsApp, Telegram, Discord, Slack, Signal and Email are planned ways to talk to Sibyl.",
            "Telegram: create a bot with BotFather, enter its token and your numeric user ID, save, Check bot, then Enable Telegram. Setup and enabling do not require an AI model. Open the bot’s private chat and press Start; help/status work immediately, while questions receive setup guidance until a model is active. Other channels remain unavailable previews.",
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
        """List saved account metadata, active flags and import status, without credentials or private reads."""
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

    def settings_guide(section: str = "exchanges") -> dict:
        """Get actionable Sibyl setup instructions: exchanges, models, news, market, messaging or workspace."""
        if section not in GUIDES:
            return {"sections": list(GUIDES), "note": "Choose a listed settings section."}
        return {"section": section, **GUIDES[section]}

    def exchange_setup(exchange: str = "binance") -> dict:
        """Read supported credential fields and practical connection steps for a catalog exchange ID."""
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
            background_tool(connection_status),
            background_tool(settings_guide),
            background_tool(exchange_setup),
        ],
        system_prompt=COMMON_PROMPT + SYSTEM_PROMPT,
        **runtime,
    )
    agent.card.capabilities.delegation = False
    return agent

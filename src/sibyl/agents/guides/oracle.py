"""Workspace orientation for Oracle, without shadowing Sibyl's native delegation."""

from typing import Literal

from sibyl.agents.guides import Guide

Topic = Literal["overview", "accounts", "agents", "models", "messaging"]
GUIDES = {
    "overview": Guide(
        "Find your way around Sibyl",
        "/account",
        (
            "Account combines active exchange holdings; Markets analyzes prices; Trade handles reviewed orders and retained history.",
            "Strategies offers backtests and monitored runs; News, Forecasting and Research have specialist analysis tools.",
            "Sibyl is the coordinating chat. Page Ask buttons open their own specialist in place.",
        ),
    ),
    "accounts": Guide(
        "View one or many accounts",
        "/settings?tab=exchanges",
        (
            "Connect and activate one or many exchange accounts in Settings → Exchanges, then choose combined, exchange or individual scope in Account.",
            "With no active account, connect one or explicitly choose Preview with Demo. Actual active accounts turn Demo off.",
        ),
    ),
    "agents": Guide(
        "Choose a specialist or talk to Sibyl",
        "/sibyl",
        (
            "Use Ask on a page for its specialist, or open Sibyl for a question that spans modules.",
            "Sibyl discovers available specialists automatically through ProtoLink and can consult their reasoning or tools.",
            "More → Agents shows registered specialists and their actual tools. Completed observations and consulted agents appear with answers.",
        ),
        (
            "Assistants provide read-only explanations. They cannot submit orders, change settings, start strategies or send messages.",
        ),
    ),
    "models": Guide(
        "Configure assistant models",
        "/settings?tab=models",
        (
            "Choose an API or Local provider and model in Settings → AI models, then save the workspace default.",
            "Agent models optionally overrides the provider/model for one agent. No model leaves specialist Tool snapshots; Sibyl needs a configured model.",
            "Keep credentials in Settings, never in chat. New settings apply to new turns; running requests keep their selected team models.",
        ),
    ),
    "messaging": Guide(
        "Talk to Sibyl from another app",
        "/settings?tab=messaging",
        (
            "Telegram is implemented: enter a BotFather token and allowed numeric user ID, save, Check bot, then Enable Telegram.",
            "Open the bot's private chat and press Start. Setup/help work without a model; AI answers require Sibyl's model.",
        ),
        (
            "WhatsApp, Discord, Slack, Signal and Email are unavailable previews. The agents cannot configure or send messages themselves.",
        ),
    ),
}

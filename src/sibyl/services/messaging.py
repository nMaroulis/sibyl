"""Read-only setup requirements for unavailable messaging integrations.

The catalog describes planned provider authentication and private sender IDs.
It deliberately accepts no credentials and owns no clients or persistence.
"""

CHANNELS = [
    {
        "id": "whatsapp",
        "name": "WhatsApp",
        "description": "Talk to Sibyl through a WhatsApp Business number.",
        "planned_transport": "cloud_api",
        "docs_url": "https://developers.facebook.com/documentation/business-messaging/whatsapp/get-started",
        "fields": [
            {
                "id": "access_token",
                "label": "Access token",
                "type": "password",
                "placeholder": "Meta system user access token",
            },
            {
                "id": "phone_number_id",
                "label": "Phone number ID",
                "type": "text",
                "placeholder": "WhatsApp Business phone number ID",
            },
            {
                "id": "app_secret",
                "label": "Meta app secret",
                "type": "password",
                "placeholder": "For verifying incoming messages",
            },
            {
                "id": "verify_token",
                "label": "Webhook verification token",
                "type": "password",
                "placeholder": "Your chosen verification token",
            },
            {
                "id": "allowed_phone_number",
                "label": "Your WhatsApp number",
                "type": "tel",
                "placeholder": "+15551234567",
                "help": "Your personal number, in international format.",
            },
        ],
        "setup_note": "A public HTTPS webhook URL will be needed when this integration is available.",
    },
    {
        "id": "telegram",
        "name": "Telegram",
        "description": "Message Sibyl through your own Telegram bot.",
        "planned_transport": "long_polling",
        "docs_url": "https://core.telegram.org/bots/tutorial#obtain-your-bot-token",
        "fields": [
            {
                "id": "bot_token",
                "label": "Bot token",
                "type": "password",
                "placeholder": "Token from @BotFather",
            },
            {
                "id": "allowed_user_id",
                "label": "Your Telegram user ID",
                "type": "text",
                "placeholder": "Numeric user ID",
                "help": "Your numeric ID, rather than your @username.",
            },
        ],
        "setup_note": "The planned connection uses polling, so a public webhook URL is not required.",
    },
    {
        "id": "discord",
        "name": "Discord",
        "description": "Chat with Sibyl through a Discord bot.",
        "planned_transport": "gateway",
        "docs_url": "https://docs.discord.com/developers/quick-start/getting-started",
        "fields": [
            {
                "id": "bot_token",
                "label": "Bot token",
                "type": "password",
                "placeholder": "Token from the Discord Developer Portal",
            },
            {
                "id": "application_id",
                "label": "Application ID",
                "type": "text",
                "placeholder": "Your Discord application's ID",
            },
            {
                "id": "allowed_user_id",
                "label": "Your Discord user ID",
                "type": "text",
                "placeholder": "Numeric user ID",
                "help": "Available through Discord's Developer Mode.",
            },
        ],
        "setup_note": "The planned bot uses Discord's Gateway and will need the relevant message intents enabled.",
    },
    {
        "id": "slack",
        "name": "Slack",
        "description": "Have a conversation with Sibyl inside Slack.",
        "planned_transport": "socket_mode",
        "docs_url": "https://docs.slack.dev/apis/events-api/using-socket-mode/",
        "fields": [
            {"id": "bot_token", "label": "Bot user OAuth token", "type": "password", "placeholder": "xoxb-…"},
            {
                "id": "app_token",
                "label": "App-level token",
                "type": "password",
                "placeholder": "xapp-…",
                "help": "An app-level token with the connections:write scope.",
            },
            {"id": "allowed_user_id", "label": "Your Slack member ID", "type": "text", "placeholder": "U…"},
        ],
        "setup_note": "The planned connection uses Socket Mode, so a public webhook URL is not required.",
    },
]


class MessagingSettings:
    """Expose the future setup fields without collecting or storing credentials."""

    def public(self) -> dict:
        """Report every channel as unavailable; this is a configuration preview only."""
        return {
            "channels": [{**channel, "status": "unavailable", "connected": False} for channel in CHANNELS]
        }

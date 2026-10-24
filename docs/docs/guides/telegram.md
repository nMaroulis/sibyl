# Talk to Sibyl on Telegram

Telegram connects your private bot chat to the same ProtoLink Sibyl agent and specialist registry used by the dashboard. A running Python backend is required. You can save, check and enable the connection before configuring an AI model; AI answers need an active model. No public webhook or Telegram SDK is required.

1. Create a bot using [BotFather](https://core.telegram.org/bots/tutorial#obtain-your-bot-token).
2. Find your **numeric Telegram user ID**. This is neither your username nor the bot ID. If needed, send a message to your new bot and inspect `message.from.id` using Telegram's [getUpdates API](https://core.telegram.org/bots/api#getupdates) locally before enabling Sibyl. Keep the bot token private.
3. In **Settings → Messaging**, enter the bot token and your numeric user ID, then **Save connection**. The token is encrypted in Sibyl's local vault; it is never returned to the browser or passed to agents.
4. Select **Check bot**. Sibyl validates bot identity and checks for an existing webhook. It never deletes a webhook or replaces another bot application's configuration.
5. Select **Enable Telegram**, open your bot's private chat and press Start. Only ordinary private messages from your configured user are accepted; groups, other users and forwarded messages are ignored. Without an active model, help/status commands work and questions receive model-setup guidance. Configure a model whenever you are ready; the enabled connection will use it without needing to reconnect.

Ask a question normally. `/new` starts a fresh conversation; `/status` shows model readiness; `/help` explains the connection. Questions and answers appear in Sibyl's saved local conversations. Commands are processed in order, so a long AI answer can delay a later command. Messages older than the first enablement are ignored. A paused connection resumes its saved polling position.

Replies can contain private workspace observations requested by you. Those replies pass through Telegram, and reasoning uses the AI provider selected in Sibyl. Stored chat messages and queue bodies are local SQLite data, not encrypted chat storage; bot/model credentials are encrypted. Agents remain read-only. The transport replies to the bound private chat; it does not give agents a general send-message tool.

## Delivery and interruption

Incoming updates are persisted before the polling checkpoint advances. Native update IDs deduplicate repeated pages. Answers are split into durable plain-text reply chunks. Explicit rate-limit rejections retry with Telegram's delay and a bounded attempt count. A timeout, server failure or process interruption during a send leaves delivery **uncertain**: Telegram has no send idempotency key, so Sibyl does not automatically repeat it. Check the chat before asking again. Later chunks of an unconfirmed answer are blocked.

Interrupted inference is not replayed automatically. An already committed Sibyl answer can be recovered into the outbox after restart; otherwise the interrupted question remains visible in Settings and must be sent again. Pending replies resume only for the same enabled connection. A changed token/user or disconnect invalidates old work. **Pause Telegram** stops future polls and sends; a native send already in flight can still finish. Disconnect removes the local token while retaining conversation history. Run one API worker per bot, and stop other pollers using that bot token.

Settings shows connection errors and sent, queued, uncertain or interrupted counts. A successful bot check verifies identity/API access, not end-to-end AI delivery. Automated tests replace the HTTP transport and native agent boundary; real-bot acceptance remains a deployment check. WhatsApp, Discord, Slack, Signal and Email are still unavailable previews.

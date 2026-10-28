# Talk to Sibyl on Telegram

Telegram connects your private bot chat to the same ProtoLink Sibyl agent and specialist registry used by the dashboard. A running Python backend is required. You can save, check and enable the connection before configuring an AI model; AI answers need an active model. No public webhook or Telegram SDK is required.

1. Create a bot using [BotFather](https://core.telegram.org/bots/tutorial#obtain-your-bot-token).
2. Find your **numeric Telegram user ID**. This is neither your username nor the bot ID. If needed, send a message to your new bot and inspect `message.from.id` using Telegram's [getUpdates API](https://core.telegram.org/bots/api#getupdates) locally before enabling Sibyl. Keep the bot token private.
3. In **Settings → Messaging**, enter the bot token and your numeric user ID, then **Save connection**. The token is encrypted in Sibyl's local vault; it is never returned to the browser or passed to agents.
4. Select **Check bot**. Sibyl validates bot identity and checks for an existing webhook. It never deletes a webhook or replaces another bot application's configuration.
5. Select **Enable Telegram**, open your bot's private chat and press Start. Only ordinary private messages from your configured user are accepted; groups, other users and forwarded messages are ignored. Without an active model, help/status commands work and questions receive model-setup guidance. Configure a model whenever you are ready; the enabled connection will use it without needing to reconnect.

The **Bot token** field takes the complete BotFather token, including its colon. A `t.me/...` link or `@bot_username` opens the bot's chat; neither is a credential or your personal ID. The number before the token's colon is the bot's ID, not yours. **Your numeric Telegram user ID** is the human sender's `message.from.id` in a private update.

For an optional simpler lookup, open [@userinfobot](https://t.me/userinfobot) in Telegram, press Start and copy its numeric Id. This is a third-party bot; never send it your BotFather token. Reading your own bot's `getUpdates` remains the direct API alternative. The form's **Where do I find my personal user ID?** section links to both options.

**Save connection** validates both fields and folds them into a **Credentials saved** summary. The summary masks the personal ID and confirms encrypted token storage. **Edit credentials** reopens the user ID and a blank replacement-token field; the saved token is never returned or revealed. Leave that field blank to keep it. Save or cancel editing before starting the connection.

**Check bot** verifies the saved bot identity. **Enable Telegram** starts the connection; the listening panel shows an ambient signal and the most recent successful poll time. **Pause Telegram** stops future work while keeping credentials and the conversation, and **Resume Telegram** starts it again. Edit fields are locked while listening; pause before changing them. **Disconnect**, inside credential editing, removes the stored connection. A missing AI model does not lock connection setup. If a token has been shared publicly or in a chat, revoke it with BotFather and enter a replacement only in the token field.

Ask a question normally. `/new` starts a fresh conversation; `/status` shows model readiness; `/help` explains the connection. Questions and answers appear in Sibyl's saved local conversations. Commands are processed in order, so a long AI answer can delay a later command. Messages older than the first enablement are ignored. A paused connection resumes its saved polling position.

Replies can contain private workspace observations requested by you. Those replies pass through Telegram, and reasoning uses the AI provider selected in Sibyl. Stored chat messages and queue bodies are local SQLite data, not encrypted chat storage; bot/model credentials are encrypted. Agents remain read-only. The transport replies to the bound private chat; it does not give agents a general send-message tool.

## Delivery and interruption

Incoming updates are persisted before the polling checkpoint advances. Native update IDs deduplicate repeated pages. Answers are split into durable plain-text reply chunks. Explicit rate-limit rejections retry with Telegram's delay and a bounded attempt count. A timeout, server failure or process interruption during a send leaves delivery **uncertain**: Telegram has no send idempotency key, so Sibyl does not automatically repeat it. Check the chat before asking again. Later chunks of an unconfirmed answer are blocked.

Interrupted inference is not replayed automatically. An already committed Sibyl answer can be recovered into the outbox after restart; otherwise the interrupted question remains visible in Settings and must be sent again. Pending replies resume only for the same enabled connection. A changed token/user or disconnect invalidates old work. **Pause Telegram** stops future polls and sends; a native send already in flight can still finish. Disconnect removes the local token while retaining conversation history. Run one API worker per bot, and stop other pollers using that bot token.

## Connection activity

- **Messages received** counts accepted private messages and commands from the configured user, excluding ignored traffic.
- **Replies delivered** counts a reply only after all its message parts are confirmed sent. The smaller **message parts sent** count explains how a long answer can produce several Telegram messages.
- **In progress** combines queued requests, a currently processing request and replies still waiting to finish delivery. Pausing retains this work for resumption.

Connection errors, failed/blocked or uncertain message parts, and interrupted requests stay visible. The animation reflects an enabled connection without a currently reported error; it is not an uptime guarantee. The last poll is a successful Telegram read, while **Bot checked** refers to the explicit identity check. A successful bot check does not establish end-to-end AI delivery. Automated tests replace the HTTP transport and native agent boundary; real-bot acceptance remains a deployment check. WhatsApp, Discord, Slack, Signal and Email are still unavailable previews.

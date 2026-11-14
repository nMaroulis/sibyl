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

## Scheduled briefings

[Scheduled investigations](briefings.md) can deliver a summary or fuller report to this checked bot and private user. Select delivery explicitly in each investigation’s schedule editor. If this is an older saved connection, choose **Check bot** once to register its stable bot identity. No additional credentials are needed.

Briefing deliveries have separate counters in Messaging and per-part outcomes in the investigation’s schedule history. Pause Telegram or the schedule to withdraw unsent briefings. Reports completed while Telegram is paused stay local; they do not form a delivery backlog. Changed bot/user identities require reviewing the schedule’s recipient again. The same uncertainty policy below applies to automated messages.

## Alert notifications

Use **Delivery** on any saved price, account-risk, strategy or connection rule to select this checked bot/private user. Telegram chat alone does not enable alerts. Alert delivery needs no model, applies to future events only and has its own cooldown and freshness window. **Alerts → Delivery** shows message-part confirmations, skipped events and failures; Messaging counts alerts separately from replies and research briefings. See [Telegram alert delivery](alert-delivery.md).

## Connection activity

- **Messages received** counts accepted private messages and commands from the configured user, excluding ignored traffic.
- **Replies delivered** counts a reply only after all its message parts are confirmed sent. The smaller **message parts sent** count explains how a long answer can produce several Telegram messages.
- **In progress** combines queued requests, a currently processing request and replies still waiting to finish delivery. Pausing retains this work for resumption.

Connection errors, failed/blocked or uncertain message parts, and interrupted requests stay visible. The animation reflects an enabled connection without a currently reported error; it is not an uptime guarantee. The last poll is a successful Telegram read, while **Bot checked** refers to the explicit identity check. A successful bot check does not establish end-to-end AI delivery. Automated tests replace the HTTP transport and native agent boundary; real-bot acceptance remains a deployment check. Discord, Slack, WhatsApp, Signal and Email have their own private text connections; see [channel setup](../developers/private-messaging.md).

## Review alert and briefing delivery

In **Settings → Messaging → Telegram**, expand **Review Telegram deliveries**, choose Alerts, Scheduled briefings or Conversation replies and open a receipt. The same **Review delivery** control appears on notification receipts. This view explicitly reveals the queued message text, the recorded bot/private recipient, native message IDs and each part's actual outcome. Conversation replies are grouped across all their chunks and retain their original target separately from alert/briefing receipts. Older replies with no captured bot identity show that identity as unavailable; a replacement bot never supplies it.

Use **Withdraw unsent remainder** while work is queued or waiting after a rate-limit rejection. Confirmed parts stay delivered; an admitted send must finish before review controls are available. An uncertain, failed or partial delivery can be marked **I received it in Telegram** or **Dismiss review**, with an optional local note. These entries are user assertions: the original native status, confirmed part count and native IDs remain unchanged. No review control resends a message or recalls a confirmed send.

Concurrent outcome changes invalidate an older review token, requiring a refresh. Review history is bounded to ten entries per delivery and remains with its receipt under existing retention. Uncertain native outcomes remain protected evidence even after a user acknowledgment. Technician can explain compact outcomes and review states without seeing private message text, recipient IDs or credentials. All six private text clients and opt-in Telegram attachments are implemented; broader media/live acceptance remain pending; outgoing text documents are described below.

Conversation review never reruns a Sibyl question, changes its chat turn, or retries an ambiguous send. The same stale-token, admitted-send and separate-user-acknowledgment rules apply. Unsent withdrawal and sender admission serialize through the local database, so a withdrawn chunk cannot later be claimed. Reply chunks respect Telegram's UTF-16 length bound, including emoji. Existing locally retained replies receive grouped receipts without inferring unknown historical bot identities.

## Optional text documents

Pause Telegram, choose **Edit credentials**, and enable **Send long replies as a text document** if you prefer one file for answers longer than a single message. Save and enable the connection again. Short replies remain plain text. Each accepted question keeps its chosen reply format; changing settings does not rewrite an older queued answer. A generated `.txt` attachment contains the complete UTF-8 answer up to 64 KiB. Larger answers stay in Sibyl and receive a short Telegram notice.

An investigation schedule independently offers **Delivery format → One text document** when Telegram is selected, alongside its summary/full content choice. A document preserves the entire selected content; an oversized report stays local with an explicit delivery error. Text messages keep their existing bounded chunking/shortening behavior. These files may contain private research, just like messages; they use the same reviewed bot/private recipient. Receipts and **Review delivery** show the actual filename, content and native confirmation. A queued file is not a confirmed send, and uncertain uploads never retry automatically. Incoming documents, photo OCR and bounded audio transcription are separate opt-in attachment features described below.


## Incoming attachments

Open **Telegram attachments** in Messaging settings to opt in separately to documents, photo text or voice/audio. Imported content appears in **Research → My research**. Photo OCR and speech transcription need separately installed local processors; all three types start off. Read [attachment setup, limits and retention](../developers/telegram-attachments.md).

# Private messaging channels

Sibyl's read-only coordinator can receive private text questions through Telegram, Discord, Slack, WhatsApp, email and a separately linked local Signal bridge. Configure them in **Settings → Messaging**. No model is needed to save/check/enable a connection; ordinary questions receive model-setup guidance until an LLM is ready. Commands `/help`, `/status` and `/new` are handled locally.

Credentials are write-only, encrypted in the backend's vault. After saving, the form collapses to the checked identity, private recipient and controls. Editing requires a paused connection and complete replacement credentials. A live receiver indicator uses actual poll timing alongside enabled state. It does not claim a provider is reachable without observations.

## Discord

Use a **bot token**, application ID and your numeric user ID from Discord Developer Mode. Check creates/reuses the private DM with that recipient and verifies the bot application. Sibyl polls only that DM through Discord's HTTP API; no user token, Gateway, guild/channel access, online presence or slash-command handling is implemented.

Enabling starts a new receive boundary; messages sent while paused are intentionally not imported. Pending pages reaching the bounded 100-message limit stop for explicit history review rather than claiming a complete backfill. Replies disable mentions and embeds. References: [Discord users/DMs](https://docs.discord.com/developers/resources/user), [message reads/writes](https://docs.discord.com/developers/resources/message).

## Slack

Use a bot OAuth token, app-level Socket Mode token and your member ID. Configure Socket Mode, `connections:write` on the app token, bot `chat:write`, `im:write` and `im:history` access, and a `message.im` event subscription. Install the app in the intended workspace.

Sibyl accepts only the checked workspace, configured user and one private conversation. Envelope acknowledgments occur after local ingestion commits. Native event IDs suppress repeated inference. Socket reconnects do not establish complete history recovery; Slack retention/retry limits and extended downtime can leave gaps. Outbound text disables model-generated formatting, mentions and unfurls. Reference: [native Socket Mode protocol](https://docs.slack.dev/apis/events-api/using-socket-mode/), [chat.postMessage](https://docs.slack.dev/reference/methods/chat.postMessage/).

## Signal

Signal does not provide an official bot API. Link a current **unofficial signal-cli** installation separately, then run its **multi-account HTTP daemon** bound to loopback with ordinary automatic receiving. Enter the loopback origin, linked account phone number (or ACI for a numberless account), and your personal sender ACI. Sibyl neither registers nor links the account and accepts no Signal PIN or account-recovery secret.

The client uses native JSON-RPC and SSE, checking the configured local account and sender ACI. Replies go only to that ACI. Group, sync, view-once and old messages are ignored. Persisted `Last-Event-ID` supports the daemon's bounded replay buffer; it is not a full message archive. Bridge restarts or old daemon versions can leave gaps. References: [signal-cli JSON-RPC/HTTP](https://github.com/AsamK/signal-cli/blob/master/man/signal-cli-jsonrpc.5.adoc), [recipient identifiers](https://github.com/AsamK/signal-cli/blob/master/man/signal-cli.1.adoc).

## Local routing and delivery

Each channel has an independent receiver and at most 100 pending accepted messages. Only normalized authorized text is stored; foreign senders, channels and unsupported content are discarded. The durable inbox commits before a native acknowledgment or saved receive cursor. ProtoLink handles model requests, specialist discovery, delegation and conversation storage. These integrations add no financial action tools.

Replies are split below native text limits and bound to the recorded recipient and connection revision. **Sent means provider acceptance**, not human delivery/read. Explicit rate limits can retry within a bounded budget; timeouts, server failures and interrupted sends become uncertain and are never automatically resent. Later parts are blocked after an unconfirmed part. Metadata receipts expose actual IDs, attempts and outcomes without credential values or private message bodies.

Pause changes the control generation immediately, including while the model is working. Late answers cannot queue a new reply. A send already admitted to a provider can still complete. Restart retains completed answers; interrupted inference is not automatically rerun. Restored archives quarantine queued messages/sends and disable channels for explicit review. Provider acceptance and account-specific setup still need deployment testing with your own service account; automated transport tests do not send real messages.

## WhatsApp Cloud API

Use your Meta business phone number ID, system-user access token, app secret, chosen webhook verification token, an explicitly selected supported Graph API version and your personal recipient number. Sibyl does not change API versions silently. Checking verifies access to the business phone; it does not prove your public webhook is reachable.

Configure a public HTTPS callback ending **`/api/v1/webhooks/whatsapp`**, the same verification token and a `messages` subscription in Meta. Only this exact GET/POST endpoint uses provider authentication instead of the workspace bearer token. All other API routes keep normal access controls. The subscription handshake checks the private token; POST checks HMAC-SHA256 over bounded raw bytes **before parsing**. Bad signatures, oversized bodies and saturated intake are rejected without acknowledging unretained events. Handshake query strings are removed from Uvicorn access logs.

Only native text messages for the checked business phone and configured personal sender are accepted. Groups/media/templates are unsupported. Replies require a recent accepted inbound message within the service reply window. A closed window fails explicitly rather than silently switching to a paid template. Provider acceptance is retained; delivery/read-status webhooks are not currently projected as human receipts. References: [Meta Cloud API collection](https://www.postman.com/meta/whatsapp-business-platform/documentation/wlk6lh4/whatsapp-cloud-api), [Meta webhook verification](https://whatsapp.github.io/WhatsApp-Nodejs-SDK/api-reference/webhooks/start/). Provider account eligibility, permissions, supported version and live callback acceptance still need deployment verification.

## Email

Use a **dedicated Sibyl mailbox**, separate from your personal sender. Configure IMAP/SMTP hosts, ports, TLS/STARTTLS modes, usernames, app passwords and an IMAP folder. TLS certificate and hostname verification is mandatory. Provider OAuth flows are not implemented.

Choose a private 24–100-character pairing phrase and begin each question's subject with **`[Sibyl:YOUR_PAIRING_PHRASE]`**. The sender address **and** phrase must match. From headers alone are forgeable; the phrase is not included in prompts, returned settings or generated reply headers. Keep it private and replace the connection if it becomes known. This is shared-secret pairing, not S/MIME or DKIM validation.

Checks authenticate IMAP/SMTP without sending a message. Enabling starts at the mailbox's current UIDNEXT boundary. Sibyl selects the folder read-only and uses BODY.PEEK; it does not mark mail read, delete it or modify mailbox flags. UIDVALIDITY changes block reads for review instead of assigning old IDs to new messages. Receives are bounded to ten messages and 128 KiB per message. Only bounded plain text is routed; HTML-only content, attachments, automatic/list mail and unauthorized sender/phrase combinations are ignored.

Replies always use the saved personal address. Incoming Reply-To, CC/BCC, subject text and model-generated addresses cannot redirect them. Native SMTP acceptance is retained with its generated Message-ID; an uncertain send is not retried. Standard-library network calls run in owned threads and drain on shutdown; cancellation cannot kill a submitted SMTP call. Enabling after pause starts a fresh receive boundary rather than importing paused mailbox history.

Opt-in [Telegram attachments](telegram-attachments.md) are implemented. [Private alert delivery](alert-delivery.md) can select any of the six checked text connections through the shared app-origin outbox. Scheduled briefings remain Telegram-only; non-Telegram media/briefings and live external acceptance remain in the [release plan](release-2.4.md).

# Meet Sibyl

**Sibyl** is your main conversation with the workspace. Open its gradient star in the floating dock. Ask a general question, investigate a market, compare news with indicators, or discuss your portfolio and strategies.

Sibyl uses [ProtoLink](https://github.com/nMaroulis/protolink)’s automatic registry discovery and native agent delegation. The SDK exposes the registered specialists to its model, which decides which ones to consult. It can answer general questions directly. Questions that need workspace evidence can involve Analyst, Reporter, Accountant, Broker, Chronos, Wiki, Explorer, Technician, Oracle, or Equity Analyst. The choice comes from the model, rather than a keyword router.

## Connect a model first

Open **Settings → AI models**, select an API or local provider, then **Save & use**. Sibyl shows a setup message and link until a model is configured. A missing required key, model ID, or installed provider dependency also shows a setup state. Configuration readiness does not verify that a remote model server is reachable or that your provider accepts the model.

The Mock runtime is available for interface testing and is explicitly labeled simulated. Its ordinary default response does not perform real reasoning or automatically consult specialists. Use an API or local model that supports tool calling for useful collaboration. Model settings apply immediately without restarting the agent network.

## A conversation with your whole workspace

Try questions such as:

- “Compare ETH/USDT indicators with the available Ethereum news.”
- “What are the main concentrations in my combined portfolio?”
- “Explain this running paper strategy and the limitations of its results.” Include the job ID when referring to a specific strategy.
- “Which connections have I configured, and what is still missing?”

Use an explicit market, exchange, account or strategy when you have one in mind. Sibyl can ask for clarification when the selection is ambiguous. Data still follows your workspace source and account settings. Demo observations, mock responses, and paper strategies remain labeled; Sibyl does not silently activate an account or switch a data source.

When Sibyl consults someone, expand the **consultations** panel under the answer. It shows the actual specialist requests, completed or unavailable status, returned answers, selections, and returned source observations. This is a record of collaboration, not hidden model reasoning or every internal specialist tool call. A failed native specialist execution can end the turn; completed consultation evidence stays available in request history.

The model decides whether to use a specialist. The interface never invents consultation badges for an answer that involved no specialists.

## Follow or stop a request

While Sibyl works, the chat shows its current stage and the specialists actually being consulted, with working/completed states. Progress refreshes about once a second; the final answer appears when complete. It does not show private model reasoning or stream answer tokens.

Use **Stop** to cancel this specific request, including one waiting for an available slot. Completed consultations remain available, and a stopped request does not add a pretend answer to the conversation. An already committed answer is retained if it completes just before Stop reaches the server. A provider call already in flight may still finish or incur charges; Stop prevents further consultations and a late answer from that request.

Open **Request history** beside the conversation picker to inspect the latest 20 attempts and their retained consultation observations, including failures and stopped requests. **Use this question** puts a previous question back in the composer for you to review and send. This does not retry automatically.

## Saved conversations

Choose a chat from **Saved conversations** or use **New chat** for a fresh context. Completed answers and consultation evidence persist locally across application restarts. A conversation displays its latest 100 completed turns; the model receives the latest six. The picker lists the most recent 100 chats. Unsent drafts are not saved across page reloads. Reopening a running conversation shows its pending state and refreshes completed answers automatically.

One turn may run at a time in a conversation. Different chats and direct module questions share a two-request limit. Native ProtoLink run budgets bound delegation, model calls and tool reads. A turn waits at most 150 seconds including queue time. Sibyl is request-driven; starting the app makes the agents available without running inference or creating background research tasks.

If the application restarts before a request finishes, the attempt is marked **Interrupted by restart**. Completed consultation observations survive, but the investigation is not resumed or replayed. Reopening the chat lets you inspect it and choose whether to ask again.

**Delete conversation** permanently removes that chat's local messages, request history and collaboration evidence. It does not remove separately recorded specialist runs. Deletion is blocked while an answer is running.

## Talk directly to a specialist

The gradient **Ask** buttons on module pages still open the corresponding specialist in place. An Analyst question goes directly to Analyst through the ProtoLink agent client; it does not pass through Sibyl. These specialists can still return factual tool snapshots without a configured model. The **More → Agents** directory remains available.

## Messaging channels: coming soon

Once available, you’ll be able to talk to Sibyl through WhatsApp, Telegram, Discord, Slack, Signal or email.

**Settings → Messaging** shows app icons, a clear **Unavailable** status, and disabled previews of the credentials and personal sender IDs each integration will need. There are no save buttons or draft storage. Channel clients, authentication, webhooks, message delivery and external chat access are not implemented yet; no credentials can be entered or saved.

Email previews incoming IMAP and outgoing SMTP settings with separate credentials and TLS/STARTTLS options. Signal previews a separately linked account on the unofficial signal-cli bridge. See the [Messaging setup fields](./settings.md#messaging) for the requirements and limitations.

## What your model receives

Your question, recent chat turns, and any consulted specialists' observations are sent to your selected model provider. Portfolio consultations can include balances and other private account observations. Choose a local model to keep inference on your machine. The local conversation store is not encrypted; saved provider credentials use the workspace vault.

Sibyl and its specialists have read-only tools. They cannot place trades, withdraw funds, change settings, start strategies or send external messages. Verify sources, dates and uncertainty before acting on an answer.

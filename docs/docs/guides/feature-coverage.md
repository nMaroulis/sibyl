# Feature coverage and roadmap

This page summarizes the **v2.0.0 baseline**. Open **More → Coming soon** for the backend's implementation inventory. Planned features describe scope rather than promised release dates; subsequent shipped changes belong in the [changelog](../changelog.md).

| Workspace | Available in v2.0.0 | Pending extensions |
| --- | --- | --- |
| Account / Accountant | Combined/exchange/account scopes, allocations, free/reserved balances, exact-route valuation, observed history, native-asset balance checks and CSV | Broader wallet coverage, full reconciliation and cash-flow-adjusted returns |
| Markets / Analyst | Searchable pairs, source-specific watchlists, line/OHLC charts, indicators, region zoom, statistics, explainable technical bias, Pearson/Spearman comparisons and CSV | WebSockets, additional historical adapters and advanced statistical methods |
| Market history | Retained source-specific candles, reviewed resumable backfills, coverage gaps, retention and immutable datasets | Broader provider acceptance and endpoint-weighted quota policies |
| Strategies / Broker | Six algorithms, fees/slippage-aware backtests, execution overlays, benchmarks, exact-input reruns, bounded search, holdout/walk-forward validation and persistent paper monitors | Nested validation, continuous deployment simulation, broader optimization and strategy plugins |
| Exchange strategies | Approved account-bound runs on nine provider/environment variants, capped GTC orders, fill-derived ownership, restart pause, reviewed cancellation/exits, global halt and shared exposure/daily-loss controls | Broader authenticated venue/race acceptance, residual ownership handling and richer risk policies |
| Trade | Persistent Demo wallet, reviewed native market/GTC orders and cancellation on the execution allowlist, cumulative status/fill monitoring | Cancel/replace, conditional/OCO orders, additional order types and providers |
| Account history | Eleven-client/environment selected-market fill imports, incremental checkpoints/rescans, native fees, retained FIFO and audited opening inventory | Additional adapters, cross-market basis and historical third-currency fee valuation |
| Funding and transfers | Supported Binance/Kraken/Bybit streams, range imports, pending updates, recent scans, observed versions, fetched-window gaps, audited transfer review and eligible original-lot carryover | More funding streams, older out-of-window corrections, split/merged carryover and definitive removal/settlement handling |
| Sibyl & Agents | Coordinator plus ten native ProtoLink specialists, typed read-only tools/page help, saved chats, native consultation evidence, live activity, Stop and request reports | User-facing token streaming, deeper evaluated investigations, scheduling/resumption and mutation approval contracts |
| Models and messaging | API/local profiles, preset/custom models, per-agent overrides, frozen request selection, Ollama detection/owned-server controls and direct-HTTP private-user Telegram | Real-bot acceptance, richer delivery and WhatsApp/Discord/Slack/Signal/Email clients |
| News / Reporter | Five public publishers, optional web/NewsAPI collection, retained excerpts, filters, deduplication, source health, VADER distributions/trends and attributed Fear & Greed | Finance-trained/entity-targeted sentiment and licensed full-article processing |
| Forecast / Chronos | Untrained log-return statistical baseline and theoretical model bands | Reproducible training, model artifacts, held-out evaluation and calibration |
| Research / Wiki | Curated glossary and 20 backend-fetched crypto profiles with fundamentals, attributed history excerpts and source links | Document ingestion, embeddings, hybrid RAG and cited web search |
| Explorer & Equities | Recent Bitcoin blocks and statistics; optional equity quotes, adjusted history and available company information | Address/transaction inspection, more chains and disclosure archives |
| Alerts | Price levels/crossings, strategy subscriptions, recorded connection-failure watches, account-value/concentration/observed-drawdown rules and persistent inbox | Broader risk metrics, silent-worker detection and optional external delivery |
| Settings / Technician | Exchanges, AI models, News, Market data, Messaging and Workspace; encrypted local credentials, activation, capability indicators and retained source diagnostics | Managed model downloads, backup/restore and credential/key lifecycle tooling |

The [backend checklist](../developers/backend-roadmap.md) retains detailed completed and pending work. It separates implementation, provider constraints and authenticated acceptance.

## Account and execution scope

New workspaces have no active accounts. Multiple exchanges can be active together; optional Demo is explicit and turns off when an exchange activates. Test funds are separately identified and excluded from production totals. Market and research source settings are independent of account activation.

Twenty production exchange adapters share an interface, but their order, history and automation coverage differs. The Settings feature dialog reflects the implementation for the selected provider/environment. Balance-read access does not establish trading permission. See [exchange coverage](../developers/exchange-clients.md) and [acceptance evidence](../developers/exchange-acceptance.md).

Paper strategies use isolated virtual capital even with real market prices. Exchange strategies require account-bound approval and both execution flags. Manual exchange orders have their own review. AI agents cannot submit orders or access credentials.

## Evidence and accounting scope

Live sources retain visible errors and stale states rather than substituting Demo fixtures. Retained fill FIFO, transfer assertions and native-asset balance checks describe the evidence imported into this workspace; they do not establish complete account history or tax reporting.

Funding imports support Binance crypto deposits/withdrawals, Kraken posted deposit/withdrawal/transfer ledgers and Bybit master-UID on-chain withdrawals. Pending updates and recent scans are opt-in. Observed versions preserve changes seen locally, not a provider's complete revision history. See [funding contracts](../developers/funding-history.md) and [recent sync](../developers/funding-recent-sync.md).

Transfer review can carry acquisition lots across eligible confirmed pairs, including explicit balanced same-asset fee allocations. Historical transfer-fee valuation, split/merged transfers, cross-market basis and account-wide cash-flow-adjusted returns remain pending. See [transfer cost basis](../developers/transfer-cost-basis.md).

## Analysis and AI scope

Backtests retain their inputs and assumptions, support exact-input reruns with the current engine, and show simulated executions. Holdout/walk-forward validation uses chronological windows, but repeated experimentation can still overfit. The technical-bias score measures mechanical direction; news sentiment measures supplied wording; Chronos is explicitly untrained.

Sibyl requires a configured API/local model and consults specialists through native ProtoLink discovery/delegation. Page dialogs retain direct specialist access and factual tool mode. Telegram is implemented with private-user binding and durable delivery; real-bot acceptance remains pending. Other messaging integrations are unavailable setup previews. See [Sibyl](sibyl.md) and [Telegram](telegram.md).

## Deployment scope

The current application is a single-user, single-worker workspace. Multi-user hosting is deferred and remains visible in Coming soon. Follow the [deployment guide](../developers/deployment.md) for token, persistence and network requirements.

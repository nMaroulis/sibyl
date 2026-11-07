---
title: Changelog
description: Release notes for Sibyl, starting with the v2.0.0 connected crypto workspace.
---

import Tabs from '@theme/Tabs';
import TabItem from '@theme/TabItem';

# Changelog

:::info[About this changelog]

User-visible Sibyl releases are recorded here using [Keep a Changelog](https://keepachangelog.com/en/1.0.0/) categories and [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

**v2.0.0 is the baseline for the current application.** Subsequent releases will document changes to this workspace. Planned work is tracked separately in the [implementation checklist](developers/backend-roadmap.md).

:::

:::tip[Install or update Sibyl]

From a source checkout, select the release you intend to run, install its locked dependencies and build the dashboard. See [installation](getting-started/installation.md) and [deployment](developers/deployment.md) for complete setup and workspace backup instructions.

<Tabs groupId="sibyl-installation">
<TabItem value="source" label="Source checkout" default>

```bash title="Terminal"
uv sync --frozen
npm ci
npm run build
uv run sibyl
```

</TabItem>
<TabItem value="docker" label="Docker Compose">

```bash title="Terminal"
# Configure .env, including a private SIBYL_API_TOKEN.
docker compose up --build
```

</TabItem>
</Tabs>

:::

---

## Release notes

## [2.3.0] - 2026-11-10

:::note[Latest Release]

Markets adds live Binance, Kraken and Coinbase previews, with clear source/interval limits and REST fallback. Trade gains reviewed native Binance conditional/OCO orders and unfilled replacement. Research expands with comparable strategy references, nested validation, custom Python research plugins, Granger lag analysis, continuous position-carrying replay, portable ridge/neural forecasts with optional causal features, and saved retrieval-quality evaluations. Account adds observed-history basket risk and hourly volatility/tail watches alongside concentration metrics. Bitstamp/Gemini fill imports, protected inbox retention/export, process/latency diagnostics, content-free workspace health reports and Telegram notification/conversation review extend local operations. Native read-only ProtoLink tools explain the saved evidence and controls throughout.

:::

### Added

- Workspace health reports: an explicit bounded read-only SQLite quick check, allowlisted runtime/resource/worker summaries, JSON download without credentials or private content, and passive Technician access to the last report.

- Trusted local Python strategy plugins for historical backtests: explicit installed entry-point allowlists, bounded manifests/controls, immutable prefix-only observations, shared next-open cost simulation, source-revision pins, retained inputs/decision fingerprints, offline reruns, charts/exports and native read-only Broker evidence. An installable momentum example is included; plugin jobs/optimization and Freqtrade remain pending.
- Markets Granger lag analysis with an explicit one-to-five lag order, reference-first bidirectional tests, consecutive return windows, training-only classical F/Bonferroni evidence, independent later-target MAE comparisons, residual diagnostics, source-labeled UI/JSON export and native Analyst context. Inference assumptions and the distinction between lag predictability and causation remain explicit.

- Optional trained small neural forecasts: an eight-unit tanh network fitted locally with fixed-seed Adam, training-only normalization, chronological calibration and independent test/rolling benchmarks. The UI exposes real training loss, numerical family and bounded portable refits; ridge remains the default.
- Opt-in hourly historical basket-risk watches for annualized volatility and daily 95% expected shortfall, using up to eight currently held assets, exact-source conversion history, complete fresh valuation, clear subset labels, hysteresis and retained inputs. These descriptive watches never enforce trading policy or guarantee future losses.
- Optional Telegram `.txt` documents for long conversation replies and scheduled research briefings, sent with direct HTTP multipart uploads. Complete UTF-8 content is capped at 64 KiB; actual confirmations, uncertainty, rate limits, original recipient binding and unsent withdrawal reuse the existing durable outboxes.

- Coinbase Advanced Trade public ticker previews and native five-minute candles through the existing bounded stream lifecycle. Exact spot IDs, connection-wide sequence checks including subscription acknowledgments, sanitized rejection, public USDC-alias refusal and same-source REST fallback preserve attribution. A bounded actual unauthenticated BTC-USD ticker/candle observation passed through the production transport/parser.
- Optional continuous single-market walk-forward deployment replay carrying cash, units and entry cost through parameter updates, with actual fills/fees, global trade cap, transition balances, fixed-setting comparison and retained independent-window scores. This historical replay starts no live strategy.
- Explicit saved Account basket-risk studies with current-value weights, observed inverse/bridge history, a common consecutive daily suffix, sample covariance/correlation, volatility, historical VaR/shortfall, variance contributions, hypothetical paths, bounded work/storage and full input export. Subset coverage and dated evidence stay visible; Accountant reads saved results through native ProtoLink tools.
- Telegram conversation-reply review reusing the notification review contract: grouped chunks, original recorded targets, unknown legacy identity disclosure, exact text inspection, atomic unsent withdrawal and separate bounded user acknowledgments. No review action resends or reruns inference. Emoji chunks now respect native UTF-16 limits.

- Optional nested strategy validation scores fixed candidates across inner chronological windows wholly inside each outer training prefix, retaining per-window metrics, deterministic selection, work budgets, independent outer tests and native Broker evidence.
- A richer causal forecast recipe adds six trailing-price trend/volatility statistics to return lags. Train-only scaling, purged evaluation, rolling studies, exact reruns, prospective forecasts and portable refits retain the selected recipe; legacy returns-only artifacts remain unchanged.
- An owner-labeled Research retrieval-quality lab with saved suites, keyword/semantic/hybrid comparisons, pinned corpus/index evidence, precision/recall/MRR/nDCG/hit-rate metrics, query rankings, exact citations, export, Stop and restart interruption. Wiki/Reporter read saved results through native ProtoLink tools; scores do not establish answer confidence.
- Telegram alert/briefing delivery review with explicit queued-text/target inspection, withdrawal of unsent remainders, stale-review protection and separate bounded user acknowledgments. Confirmed native outcomes are preserved; no review action resends a message. Technician receives compact read-only outcomes without private message bodies.

- Shared, on-demand Binance production/Testnet public ticker and candle WebSockets, bounded viewer queues, validated source/environment selection, reconnect/backoff, freshness states, background-tab cleanup and authenticated browser display streams. Closed-candle analysis and execution remain on their existing REST paths.
- Native stop-loss and take-profit GTC limits, with separate trigger/limit validation and exact conditional recovery matching. Per-instrument permissions and the Settings capability inventory reflect implemented paths.
- Durable native two-leg OCO reviews, one-quantity semantics, typed list confirmation, independent child status/fill reconciliation and exact child-ID recovery after uncertain list submission. Demo and other adapters do not emulate these orders.
- Separately reviewed, wholly unfilled manual-limit replacement through native STOP_ON_FAILURE/ONLY_NEW requests. Retain both records, estimated reservation release, a durable compound-command latch and conservative uncertainty; cancellation and replacement are explicitly non-atomic.
- Progressive OCO entry, conditional fields and eligible order-monitor replacement controls. Native read-only Analyst stream evidence and Broker OCO/trigger/replacement evidence, plus updated typed page help.
- A bounded, opt-in native advanced-order Testnet acceptance runner with isolated encrypted state, endpoint/notional gates, controlled OCO response-loss recovery and optional fill/cancel observation. Deterministic tests cover concurrency, restart, partial-fill races, SDK request fields and stream lifecycle.

- Cost-aware buy-and-hold, cash, scheduled-installment and 50/50 asset/cash backtest references over the exact strategy evaluation window, with a selectable equity overlay, configurable candle cadence, fees, returns, drawdowns and disclosed assumptions. Older saved runs remain readable.
- Portable bounded JSON forecast bundles containing the full frozen input and recipe. Imports verify integrity, refit locally, deduplicate and retain an explicitly unverified import namespace; forecasts and prospective outcomes are not copied. Model archive/restore retains outputs and evaluations and does not silently stop existing monitors.
- Authenticated inbox JSON/CSV exports with kind and UTC date filters, explicit truncation, and opt-in age retention for read notices. Bounded cleanup protects unread records, unfinished delivery evidence and unprocessed enabled delivery cursors. Monotonic notification sequences preserve future delivery admission after cleanup.
- Lightweight current-Python-process CPU, resident memory, thread count, database/WAL size, free workspace-volume space and process uptime in Workspace. Saved provider read history adds fixed latency histograms, p50/p95 upper bounds and sample coverage across restarts; historical reads without buckets remain visibly partial.
- Native read-only Broker/Chronos/Technician evidence and page help for the new research, library and history controls.

- Bitstamp selected-market imports using native transaction IDs and Gemini millisecond-boundary imports with retained edge identities, durable restart checkpoints and native-currency fees. Embedded native order details feed exact-order reconciliation for both. Saturated Gemini timestamp groups, reversal flags and missing identity/side evidence stop for review instead of inventing complete coverage. Settings reflects implemented support; private-account acceptance remains outstanding.
- Kraken v2 public ticker/OHLC previews through the shared bounded stream lifecycle, supported native intervals, explicit provider/receipt timing, historical-snapshot rejection and rejection/REST-fallback states. Receipt timing does not establish last-trade freshness; no execution or indicator path consumes forming candles.
- Unsigned sample distance correlation with a 360-observation work bound, explicit undefined coefficients, and same-interval log-return OLS beta/intercept/R²/residual summaries, scatter inspection and export. Analyst receives exact comparison selections through native request context and offers compact typed relationship evidence.
- Whole-basket asset HHI, effective asset count and largest/top-three value shares in Account, with no score for incomplete coverage. Optional fixed-account HHI/top-three alerts reuse fresh complete valuations, hysteresis, cooldowns, saved evidence and existing Telegram delivery. Accountant/Technician explain the implemented scope.

### Fixed

- Correlations deep links now select the requested panel. Factual Ask dialogs follow the selected Granger order or saved custom/built-in backtest instead of returning unrelated market or default-strategy summaries.

- Constant-series correlations now remain unavailable instead of displaying fabricated zero coefficients. Return comparisons require adjacent selected intervals and never bridge missing candles.
- Preserve newer verified native fill/status observations when a delayed or lost single-order/OCO submission acknowledgment arrives. Group uncertainty cannot overwrite an independently recovered child.

### Verification

On November 6, 2026, actual public ticker events were observed from production and Testnet streams. In a separate virtual-fund Testnet workspace, conditional limit submission/cancellation, OCO child recovery after deliberately discarding a successful response, sibling cancellation, native replacement and duplicate approval identity passed. A marketable limit filled before cancellation; this is not intermediate partial-fill or genuine outage acceptance. No production order was submitted.

## [2.2.0] - 2026-11-07

:::note[Release summary]

Sibyl gains saved investigations and scheduled AI briefings, with inspectable specialist evidence and optional Telegram delivery. A new research library supports document imports and optional local semantic search, while Account performance estimates, live forecast scorecards, rolling forecast evaluation and Bitcoin output-spend checks deepen the analysis tools.

Order/fill notifications, background-worker diagnostics and encrypted workspace backup and recovery make everyday operation easier to inspect and manage.

:::

### Added

- Measured Account investment-performance periods with fresh opening/closing valuations, source-bound funding reviews, explicit/manual external-flow assertions, coverage gates, per-account/combined Modified Dietz estimates, audit/export and native Accountant evidence. Historical conversion automation and provider-verified full accounting remain outside this workflow.
- Live forecast scorecards for predictions saved before their targets, exact-source observed daily closes, versioned actual-price corrections, equal-horizon naïve/drift comparisons, pause/resume, explicit feed refresh, JSON exports and native Chronos tools. Missing prices and historical/Demo predictions cannot become live evidence.
- Per-account order/fill notifications with atomic observed-change receipts, future-only cursors, partial-fill/cancellation/error/correction categories, inbox history, retention-gap handling, native Broker evidence and optional existing Telegram delivery.
- Optional local Ollama embeddings in **Research → My research**, with explicit model checks, bounded checkpointed indexing, partial-coverage reporting, cosine search and keyword/semantic rank fusion. Exact source citations survive retrieval; deletion and reindexing invalidate vectors. Wiki and Reporter use native typed retrieval/status tools. Chat settings stay independent; broader real-model relevance evaluation and hosted embedding providers remain pending.
- Historical rolling forecast evaluation with expanding/fixed training windows, fresh causal ridge fits and calibration per fold, purged boundaries, pooled naïve/drift comparisons, saved reproducible reports, per-window charts and JSON exports. Chronos reads selected reports through native ProtoLink tools; training and evaluation share bounded admission. No automatic model selection, deployment or recalibration is added.
- Bitcoin output-spend checks in **Research → Block explorer**, with explicit per-page refresh, confirmed/pending/unspent/unknown states, spending-transaction navigation, dated JSON exports, deterministic Demo examples and a native read-only Explorer tool. Failed checks never imply unspent funds; spendability and independent chain verification remain outside scope.
- **Research → My research**: bounded PDF/text/Markdown imports, original retention, attributed exact passages, lexical search across uploads and retained news, source management and changed-citation protection. Wiki and Reporter expose native read-only library tools; search/reading also work without an LLM.
- Background-worker supervision with actual iteration times, duration/deadline states, sanitized fault history, explicit storage retries, cancellation/draining and an app-wide attention notice. Workspace settings exposes current progress; Technician can inspect it through a native tool.
- Passphrase-encrypted local workspace archives with authenticated inspection, download/import, SQLite online snapshots and non-destructive restore into a new directory. Recovery starts with workers/exchange execution paused, accounts inactive, strategy/calendar pauses and pending-message quarantine; explicit review and restart are required. Installed-package smoke coverage exercises isolated research, worker diagnostics and encrypted recovery.
- Saved investigations in **Sibyl → Investigations**: reusable questions, progressive starting-context controls, native specialist collaboration, structured findings, uncertainty and follow-up questions.
- Versioned reruns with fresh conversations and frozen team-model choices, consultation progress, exact-request Stop, restart interruption, saved history, side-by-side comparison and JSON export.
- Inspectable source receipts from retained native ProtoLink evidence, with actual tool attribution, source links, retrieval times, bounded previews and fingerprints. Invalid structured answers or invented tool citations fail explicitly; uncited interpretations remain labeled.
- Native read-only Sibyl tools for finding previous investigations, reading dated reports and inspecting actual briefing calendars/delivery outcomes, with setup help separated from observations.
- Daily/weekly investigation briefings with local time-zone/DST rules, pause/resume/edit/archive controls, extra run-now actions, frozen queued team models, missed-time handling and schedule-specific report retention. No inference backlog is replayed after restart.
- Opt-in Telegram briefing summaries or fuller reports through the existing direct-HTTP client, bound to the explicitly reviewed bot/private user. Durable message-part receipts, rate-limit retries, expiry and conservative uncertain-send handling keep delivery inspectable.
- User/developer briefing guides, progressive calendar controls and delivery history, plus native collaboration, concurrent admission, privacy, restart, retention and mock-transport acceptance tests.

- Opt-in Telegram delivery for price, account-risk, strategy and connection alert rules, with future-only cursors, explicitly checked recipients, cooldown suppression and observation-based expiry.
- Per-rule delivery editors and a shared Delivery history tab with confirmed part counts, failure/suppression reasons and pause controls. Shared outbox admission and restart tests preserve briefing behavior; Technician setup help explains the new workflow.
- A developer agent-evaluation command using native ProtoLink cases, repeated runs, actual specialist tool evidence, scope/link/number checks and baseline score comparisons. Isolated local-model fixtures cover missing accounts/models, explicit market selection, native consultations and an untrusted news excerpt; model-specific failures remain recorded.
- Native correctable selection errors for removed articles, trained models, strategy runs and saved investigations/calendars, with useful next steps and focused acceptance tests. Agent help explains opt-in alert delivery.

### Fixed

- Make the investigation credential-privacy test independent of optional OpenAI SDK installation. Drain automatic workers before forecast and strategy tests that advance fake clocks manually, removing CI timing races without weakening runtime guards.
- Fix repository-helper imports during CI test collection by setting pytest’s checkout-root import path explicitly. Name application, release-package, installed-platform and documentation jobs/steps by their purpose.
- Replace the large Account summary cards and stacked pricing warnings with a compact metric strip and one accessible warning disclosure. Keep partial values, excluded asset counts, shared valuation-feed attribution and workspace strategy scope explicit; update Accountant help and the Account guide.
- Make the account-sync API test wait for asynchronous completion when the background worker already owns the import slot, avoiding a timing-dependent failure.
- Label retained exchange strategy summaries with their actual environment instead of describing every selected run as paper execution; leave unavailable equity explicit and distinguish the mixed saved-run catalog. Record paper mode when creating virtual runs. Reject investigation/calendar mismatches instead of returning another investigation's schedule.

## [2.1.0] - 2026-11-01

:::note[Release summary]

Chronos gains its first trained forecasting workflow: reproducible daily inputs, versioned numerical models, chronological evaluation and saved forecasts. Explorer adds public Bitcoin transaction and address inspection. Strategy research adds reproducible seeded random search with recorded candidate plans and chronological evaluation. These workflows keep source attribution, optional Demo input and implementation limits visible.

:::

### Added

- Complete Python wheels and source archives containing the built React dashboard, with installed-resource lookup and source-checkout development support. The launcher adds version, port, workspace, environment-file, dashboard override and readiness-based browser-opening options.
- A Python-package distribution workflow with isolated installed-app checks on Linux, Windows, Apple Silicon and Intel. Manual runs produce reviewable artifacts; published GitHub Releases receive the wheel, source archive, locked runtime requirements and checksum manifest after checks pass. No extra repository or registry is required.
- One release-version command synchronizes Python/npm metadata and lock entries without changing dependencies. Current docs headings and package commands derive their version from metadata; historical release notes remain fixed.

- A modular Python `forecasting/` engine for direct autoregressive ridge models. It fits daily log-return lags with NumPy, without new ML dependencies or startup model downloads.
- Current-feed training from 360–720 closed daily candles and offline training from immutable daily datasets with up to 5,000 observations. The smaller Demo action uses synthetic input through the same numerical pipeline without changing account or source settings.
- Chronological 60/20/20 training, calibration and test partitions, with targets crossing a boundary excluded. Feature scaling, coefficients and benchmark drift use training data only; empirical band widths are fixed before independent testing.
- Per-horizon MAE, RMSE, MAPE, naïve/drift comparisons, MAE skill and observed band coverage. Negative skill remains visible, and overlapping multi-day targets are disclosed.
- Nominal 90% empirical bands from calibration log errors and descriptive counts of lag features outside training ranges. Neither provides a guaranteed future coverage rate or calibrated regime-change detection.
- A bounded JSON model registry with numbered versions, engine/NumPy provenance, source/input/artifact fingerprints and exact-input reruns that preserve previous versions.
- Explicit forecasts from saved input or the original matching market feed, with observation dates, stale-input labels and the latest twenty saved outputs per model. Retained observation windows and result fingerprints support offline inspection and JSON export.
- A Trained models workspace with progressive model settings, source/environment badges, partition summaries, held-out price charts, metrics, forecast charts and model/evidence exports.
- Native typed Chronos tools for finding model versions, inspecting evaluation and reading selected saved forecasts. Page Ask dialogs and Sibyl consultations use the same registry and evidence; training and persistence remain explicit application actions.
- User/developer forecasting guides and refreshed implementation coverage, with remaining model families, rolling evaluation and calibrated drift monitoring kept on the pending checklist.
- Bitcoin mainnet transaction/address lookup through a dedicated read-only backend package and the public mempool.space indexer. Checksummed mainnet identifiers are validated before requests; no API key or exchange connection is required.
- Transaction inclusion/confirmation observations, exact satoshi fees and sat/vB, available previous-output evidence, coinbase handling and paged inputs/outputs. Address reports separate confirmed totals from pending changes and offer cursor-based confirmed history plus bounded pending activity.
- An in-page Bitcoin lookup with source/time labels, explicit synthetic Demo examples, linked reference navigation, JSON observation exports and contextual Explorer conversations. Native typed ProtoLink tools expose the same lookup and activity evidence to Explorer and Sibyl.
- Bitcoin user/developer guides covering public-query privacy, non-atomic chain observations, missing evidence, pagination/response bounds and the distinction between an address and an owner's complete wallet.
- Seeded finite random search for strategy validation: up to four indicator parameters and eight explicit values each, sampling at most sixteen distinct candidates from up to 4,096 combinations. The existing chronological train/test and 60,000-bar work limits remain in force.
- Price-independent, versioned candidate plans with seed, sampled space indices, coverage, recipe/plan fingerprints and complete-space parameter validation. A mismatched saved plan refuses exact-study replay instead of silently changing candidates.
- Progressive random-search controls, evaluated-candidate tables and sampling evidence in saved studies/exports and Broker's existing native ProtoLink report tool. Grid and fixed-setting workflows remain available; Bayesian/distribution-based optimization and nested validation remain pending.

### Changed

- Keep agent declarations at the top level of `agents/` and organize shared runtime, model, request and presentation code under `agents/utils/`. Update application imports, scripts, tests and developer documentation to the new layout.

- Group services into domain subpackages for accounts, markets, portfolio, trading, funding, transfers, research, alerts and workspace settings. Consolidate funding imports with the existing funding workers and update all callers and documentation.

- Installed apps use a stable per-user data directory unless an explicit environment/CLI path is set. Source checkouts retain their repository `.sibyl`, including without an environment file. Docker installs a normal complete package; the existing source-build Compose setup remains available. Homebrew and prebuilt registry images are deferred independently of package publication.

- Give the documentation a full-width landing page with an animated crystal ball, exchange and AI-provider marks, and direct paths into the guides. Refresh guide typography, navigation, tables and reading layouts; illustration motion can be paused and respects reduced-motion preferences. Fonts and integration artwork are served locally.
- Refine the crystal-ball illustration with intersecting perspective orbits, compact tiles for nine integrations including Gemini, DeepSeek and Bybit, provider marks that pass in front of and behind the glass, fading provider-colored trails, moving reflections, soft depth shading and opal edge lighting. Motion stays lightweight and shares the existing pause and reduced-motion controls.
- Split documentation navigation into Getting started, User guide and Developers, with dedicated sidebars and guide/developer overview pages. Welcome belongs to Getting started; chapter links stay visible without category dropdowns.

- Show the complete exchange catalog, hosted/local AI choices and messaging availability on the documentation homepage. Add illustrated introductions and reading paths to Getting started and key user/developer guides, plus a visual explanation of technical-bias weights. Clarify current source/Docker installation paths and record proposed distribution methods separately.
- Forecasting now opens the trained-model workspace; the existing untrained log-return projection remains available under Statistical baseline with its original API contract.
- Align application, Python/npm package metadata and documentation branding at v2.1.0.

### Fixed

- Normalize Windows path separators when deciding whether to serve the dashboard fallback. Missing API routes and assets keep their 404 responses on every platform, while dashboard deep links still open normally.

- Packaged dashboard documentation links open the public site instead of requiring a local Docusaurus server; development builds keep the local preview.

- Give the homepage gradient heading enough space for its descenders so “See the bigger picture.” renders without cropped letters.

- Replace the approximate DeepSeek marks in the documentation and dashboard with the official whale SVG, served locally with its original proportions and source attribution.

### Scope

This is the initial trained model family, not LSTM/ARIMA or pretrained Chronos weights. Independent historical test results do not establish profitable trading or future calibration. Automatic recalibration, monitored drift, richer model families and larger model lifecycle management remain pending. Bitcoin research trusts a public indexer; it does not aggregate complete wallets, verify spendability/chain proofs or broadcast transactions. No exchange-execution or agent mutation permissions are added.

## [2.0.0] - 2026-10-28

:::note[Release summary]

A major upgrade to Sibyl: a complete connected crypto workspace with a React interface, modular Python backend and a native ProtoLink AI team. Accounts, market analysis, strategy research, reviewed spot execution and source-linked research come together in one application you can run locally.

This release establishes the current product baseline, with explicit provider coverage, optional Demo previews and documented implementation boundaries.

:::

### Added

#### Workspace and connected accounts

- A React dashboard with a floating navigation dock, focused module pages, contextual AI dialogs, responsive layouts and progressive advanced controls.
- Combined, exchange and individual-account portfolio views, allocation and holdings filters, free/reserved balances, valuation history and CSV exports.
- Twenty production exchange adapters through a shared `ExchangeClient` interface, dedicated Binance Spot Testnet and Coinbase Exchange Sandbox clients, and an offline `DemoClient` using the same domain APIs.
- Searchable exchange setup with provider logos, required credential fields and implementation-based account, trading, history, market-data and automation indicators.
- Explicit account activation: fresh workspaces have no active accounts, multiple exchange accounts can be active together, and activating an exchange disables the optional Demo account.
- Exact direct, inverse and short-route held-asset valuation, with observed stablecoin/fiat conversions, timestamps, incomplete coverage and visible unpriced assets.

#### Markets and reusable data

- Searchable spot pairs, configurable per-source watchlists, public exchange feeds, saved account environments and supported CoinGecko/CryptoCompare API sources.
- Interactive line and candlestick charts with indicators, OHLCV inspection, volume, drag-region zoom, panning, a navigator and CSV export.
- Backend-calculated returns, trend/momentum, volatility, drawdowns, tail-risk and volume statistics, correlations and a versioned, explainable technical-bias score.
- Persistent source-specific candle history, reviewed resumable backfills, coverage-gap inspection, retention controls and immutable research datasets.
- Shared read admission, bounded concurrency, cooldowns and retained provider-read diagnostics, separating observed connectivity from quote freshness.

#### Trade, history and accounting

- Reviewed spot market and GTC limit orders, cancellation and persisted partial-fill/status monitoring on the documented provider allowlist. Gemini supports GTC limits and cancellation only.
- A persistent Demo wallet with virtual reservations, resting limit matching, cancellations and simulated fills.
- Native order/fill reconciliation, bounded client-ID recovery for uncertain submissions and read-only open/recent order discovery on supported clients.
- Durable selected-market fill imports, incremental checkpoints, pause/resume, rescans and native-currency fee evidence.
- Retained market-level FIFO performance, audited opening inventory and optional current marks, with unresolved cost and coverage kept explicit.
- Binance crypto funding imports, Kraken posted deposit/withdrawal/transfer ledger imports and Bybit master-UID on-chain withdrawal imports.
- Opt-in pending-record updates and rolling recent-history scans, with resumable pages, source-change guards, observed funding versions and persistent fetched-window gaps.
- Audited own-account transfer review and eligible original-lot carryover, including explicit same-asset fee allocations.
- Saved native-asset balance checkpoints, comparisons with retained trades/fees/eligible funding, funding-effect reviews and downloadable evidence.

#### Strategy studio

- Six configurable algorithms: EMA Crossover, RSI Reversion, Bollinger Bands, Bollinger Surge, Impulse Breakout and Quantum Momentum.
- Deterministic historical simulation with fees/slippage, price-chart execution markers, equity and cost-aware buy-and-hold comparisons, drawdowns, trade-level accounting and performance metrics.
- Saved immutable inputs, compatible experiment comparison, exact-input reruns and full evidence exports.
- Bounded grid search, chronological holdouts and expanding walk-forward validation with retained training rankings and independent test-window results.
- Persistent isolated paper runs with price/equity/drawdown monitoring, decision journals, skipped-signal reasons and lifecycle controls.
- Separately approved exchange strategies for nine provider/environment variants, with account-bound allocations, price-capped GTC orders, fill-derived ownership and paused restart recovery.
- Reviewed stop/cancel and position-exit flows, optional order lifetimes, per-order limits, a durable global submission halt and opt-in shared exposure/observed UTC daily-loss policies.

#### Sibyl and the AI team

- A dedicated Sibyl chat that discovers and consults ten registered specialists through native ProtoLink discovery and delegation.
- Individual agent files, system prompts, typed read-only tools and topic-based page help for Accountant, Analyst, Broker, Chronos, Reporter, Technician, Wiki, Explorer, Equity Analyst and Oracle.
- Contextual specialist dialogs, saved conversations, live tool/consultation activity, request-specific Stop, retained outcomes and inspectable native run evidence.
- Native ProtoLink 0.8.3 lifecycle, bounded threaded tool execution, lazy request-local model factories, frozen team model selection, private dependencies, conversation storage and correlated reports.
- API/local provider selection, model presets and custom IDs, encrypted provider profiles and optional per-agent model overrides.
- Ollama server/model detection, setup guidance and explicit Start/Stop controls for a server started by Sibyl.
- A direct-HTTP Telegram client with encrypted bot configuration, private-user binding, polling, conversation mapping and durable delivery outcomes.
- Clearly unavailable setup previews for WhatsApp, Discord, Slack, Signal and Email.

#### News, research and forecasting

- Public publisher collectors for CoinDesk, Cointelegraph, Decrypt, The Block and CryptoSlate; optional CryptoSlate website collection and NewsAPI access.
- A retained deduplicated news archive, source health, publisher/asset/date/search filters, excerpt summaries, VADER text-polarity distributions and trends, and links to full articles at the publisher.
- An attributed Alternative.me Fear & Greed index with dated comparisons and explicit stale/unavailable states.
- Twenty backend-fetched crypto project profiles with CoinPaprika information, attributed Wikipedia history excerpts and source links, plus a curated concept glossary.
- Recent Bitcoin block inspection and optional equity quotes, adjusted price history, company information and descriptive statistics.
- Chronos log-return forecast baselines and theoretical uncertainty bands, explicitly labeled untrained.

#### Alerts, documentation and deployment

- Persistent price-level/crossing rules, strategy lifecycle subscriptions, recorded connection-failure watches and fixed-account value/concentration/observed-drawdown alerts.
- A local notification inbox with retained evidence, unread state, review links and revision-checked alert controls.
- Unified Settings sections for Exchanges, AI models, News, Market data, Messaging and Workspace.
- Docusaurus installation, user, security, API, architecture, testing and deployment guides, plus an audited implementation checklist and Coming soon inventory.
- Locked Python/npm dependencies, a combined dashboard/API container, Docker Compose configuration and automated backend, frontend and documentation checks.

### Changed

- Establish React and FastAPI as the application interface and API, with domain logic in modular Python packages.
- Run every module assistant through ProtoLink primitives; use domain tools for evidence and keep execution in the reviewed trading pipeline.
- Treat Demo as an explicit optional preview, with source and environment labels across account, market, trading and research workflows.
- Derive exchange capability indicators from implemented features and document authenticated acceptance separately from adapter support.

### Fixed

- Explain Telegram's bot-token and personal-user-ID fields, validate incomplete setup without silently disabling Save, and show why Check/Enable require a saved connection.
- Fold saved Telegram credentials behind Edit, distinguish listening/paused/setup states with ambient activity, clarify Enable/Pause/Resume and separate complete replies from sent message parts.
- Keep scripted model-configuration tests independent of optional provider SDK installation, while verifying that missing SDKs still report an unavailable setup.

### Security

- Store exchange, model and messaging credentials encrypted in the backend's local Fernet vault; never return them through public APIs or agent tools.
- Keep exchange submissions disabled by default. Manual and automated execution require their applicable server flags, account permissions and scoped review/approval.
- Retain uncertain native writes without automatic resubmission; reconcile retained order and execution evidence before further action.
- Require an API token for non-loopback binding and document the one-user, one-worker deployment boundary.

### Release scope

Implementation is provider-specific. Recorded acceptance includes Binance/Coinbase account reads, bounded Binance funding reads and scoped Binance Testnet order/strategy lifecycles. Broader authenticated execution, live correction scenarios and venue-specific failure acceptance remain pending; see the [acceptance record](developers/exchange-acceptance.md).

The technical-bias score measures rule-based direction. News sentiment describes supplied text. Chronos is an untrained baseline. These outputs retain their assumptions and evidence rather than claiming calibrated predictions.

The [feature coverage](guides/feature-coverage.md) and [pending checklist](developers/backend-roadmap.md) track remaining work, including broader reconciliation, conditional orders, WebSockets, trained forecasting, RAG, additional messaging clients and deferred multi-user hosting.

---

## Version 1.0

The original Python/Streamlit dashboard is preserved in [nMaroulis/sibyl-streamlit](https://github.com/nMaroulis/sibyl-streamlit), including its exchange overview, strategy planning/backtesting, market analysis, forecasting, research and AI-assistant modules. It is maintained separately from the v2.0.0 application baseline documented here.

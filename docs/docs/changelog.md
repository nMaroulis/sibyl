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

## [2.1.0] - 2026-10-29

:::note[Release summary]

Chronos gains its first trained forecasting workflow: reproducible daily inputs, versioned numerical models, chronological evaluation and saved forecasts. Explorer adds public Bitcoin transaction and address inspection. Strategy research adds reproducible seeded random search with recorded candidate plans and chronological evaluation. These workflows keep source attribution, optional Demo input and implementation limits visible.

:::

### Added

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

- Give the documentation a full-width landing page with an animated crystal ball, exchange and AI-provider marks, and direct paths into the guides. Refresh guide typography, navigation, tables and reading layouts; illustration motion can be paused and respects reduced-motion preferences. Fonts and integration artwork are served locally.
- Refine the crystal-ball illustration with intersecting perspective orbits, compact tiles for nine integrations including Gemini, DeepSeek and Bybit, provider marks that pass in front of and behind the glass, fading provider-colored trails, moving reflections, soft depth shading and opal edge lighting. Motion stays lightweight and shares the existing pause and reduced-motion controls.
- Split documentation navigation into Getting started, User guide and Developers, with dedicated sidebars and guide/developer overview pages. Welcome belongs to Getting started; chapter links stay visible without category dropdowns.

- Show the complete exchange catalog, hosted/local AI choices and messaging availability on the documentation homepage. Add illustrated introductions and reading paths to Getting started and key user/developer guides, plus a visual explanation of technical-bias weights. Clarify current source/Docker installation paths and record proposed distribution methods separately.
- Forecasting now opens the trained-model workspace; the existing untrained log-return projection remains available under Statistical baseline with its original API contract.
- Align application, Python/npm package metadata and documentation branding at v2.1.0.

### Fixed

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

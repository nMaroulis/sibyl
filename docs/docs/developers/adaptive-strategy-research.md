# Adaptive strategy research

Strategies adds **Adaptive search**, beside the existing grid/random walk-forward workspace. It samples explicit numeric distributions using native **Optuna TPE** or **Optuna RandomSampler**, then evaluates selected settings on later chronological windows. Built-in algorithms and explicitly enabled trusted Python plugins share the existing next-open cost-aware simulation.

This is historical research. It never deploys settings, starts a paper/exchange strategy, changes execution approval or submits an order.

## Install the optional sampler

From a source checkout:

```bash
uv sync --frozen --extra optimization
```

For an installed release that includes this feature:

```bash
pip install 'sibyl[optimization]'
```

The optional extra uses Optuna 4.9.x. The dashboard reports actual dependency presence; saving/opening reports needs no optional sampler. No package, model or plugin is installed from the UI or by an agent. The main CI job installs this extra so native sampler tests run, while installed-package smoke tests still exercise a base installation.

## Use the workspace

1. Run a backtest or choose a retained dataset. Adaptive studies require that exact immutable source, pair, interval and candle count; there is no current-feed refresh during a study.
2. Expand **Adaptive search**. Choose the built-in algorithm already configured above, or a ready installed plugin.
3. Select up to four effective parameters. Set explicit integer/float bounds, optional exact steps and optional log scale. Irrelevant fields, wrong numeric types, out-of-range domains and bounds that would be silently rounded are rejected.
4. Choose TPE or random distributions, trials, seed, objective and minimum training trades. Current fee/slippage/stop settings are retained. The UI uses a 60% initial training prefix; the API permits 40–80%.
5. **Queue research study** saves a paused one-off local recipe and explicitly submits one idempotent run. Continue using the app while its worker calculates. Inspect the actual job state and retained outcome; it is never automatically retried after interruption.
6. Open each recorded window. Inspect every sampled choice, invalid/pruned settings, training score, selected trial and later price/equity/drawdown chart with exact simulated buys/sells. Export the full JSON evidence or use **Ask Broker** for the selected study/window.

A custom backtest's **Queue pinned backtest** uses its already retained dataset, implementation revision and exact parameter values. It creates a separate historical research job, not a continuously running strategy. Jobs and their receipts remain available in **Settings → Workspace → Local jobs**.

## Selection and causality

Each outer window creates a fresh sequential native sampler with a recorded seed. Optuna TPE starts with five completed startup trials, then uses training objective observations for its density-based suggestions. Invalid cross-parameter combinations and insufficient-trade trials remain explicit rather than receiving invented scores. A small/pruned study may have little adaptive evidence; a TPE label is not a quality guarantee.

Every candidate in a window uses the same conservative warmup and training score period. No later-window price or test metric is sent to that window's sampler. Equal scores use trial order. Only the selected trial and fixed baseline are tested on the later window. Each test starts in cash and liquidates at its final close with configured fees and slippage; independent-window means are not a continuous portfolio return. Earlier tests can become training history in later windows. Repeated user studies can still overfit.

If no sampled candidate meets a window's training requirements, the report explicitly records `no_eligible_candidates`; that window has no selected algorithm or test score. Previously tested windows remain labeled evidence, not a completed full study.

The bounds are 2,000 retained candles, 24 trials per window, five windows, four distributions and 60,000 budgeted processed bars. Plugin prefix processing can cost more CPU than a single indicator evaluation; these bounds do not sandbox trusted Python or promise a hard execution timeout.

## Plugins, replay and cancellation

Plugins reuse the same fresh checked instances and immutable OHLCV prefixes as ordinary custom backtests. Their declared warmup must cover all permitted parameter values. Owner-installed code has backend process privileges; this interface is **not an OS sandbox**. No code is uploaded through a request, and agents cannot install or run plugins.

Reports retain the exact dataset, recipe, native sampler version/seed, trial decisions, source implementation revision, simulator revision and a fingerprint of complete training/test evidence. **Replay exact study** requires matching native sampler and simulator versions, matching installed plugin revision and reproduced evidence. An updated implementation needs a new study; the original stays readable. No pickle or native study database is deserialized. At most 100 artifacts are retained; list views show the latest 50, and older IDs remain readable through their job receipts.

Cancellation stops result interest and queued work. It cannot kill an executing trusted Python thread or undo an artifact already committed. A late calculation does not publish a successful cancelled job receipt. Review retained artifacts/jobs before intentionally submitting again after an interrupted response.

## Modules and HTTP

- `strategies/research/adaptive/contracts.py`: typed numeric distributions and pinned recipes.
- `engine.py`: native `TPESampler`/`RandomSampler`, ask/tell, pure preflight and chronological tests.
- `service.py`: artifact retention, source/version pins, preflight and exact replay.
- `strategies/plugins/engine.py`: shared causal immutable-prefix plugin decisions.
- `strategy.adaptive` / `strategy.plugin`: non-repeatable, non-restart-safe local job handlers. Preflight rejects missing packages, unavailable datasets, changed plugins or excessive work before admission.
- `/api/v1/strategies/adaptive/options`, `/adaptive`, `/adaptive/{id}` and `/adaptive/{id}/rerun`: configuration, saved evidence and explicit offline research actions.

Broker uses ordinary native `adaptive_report` and selected-page context. It reads source pins, trial scores, test metrics and bounded fills; it cannot queue, approve or deploy a strategy. Without an AI model, the selected study still has a deterministic read-only summary.

Tests use actual native Optuna sampling and real shared simulations. They verify reproducibility, future-price isolation, disjoint cash-reset tests, fees/P&L consistency, explicit invalid samples, no-eligible outcomes, typed bounds, immutable plugin inputs/revisions, provider-free replay and actual local job receipts. See the [Optuna 4.9 TPE API](https://optuna.readthedocs.io/en/v4.9.0/reference/samplers/generated/optuna.samplers.TPESampler.html) and [native ask/tell API](https://optuna.readthedocs.io/en/v4.9.0/reference/generated/optuna.study.Study.html#optuna.study.Study.ask).

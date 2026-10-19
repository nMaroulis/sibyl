# Extending Sibyl

Keep additions small: a domain function or service, a validated API contract, a thin route, a React view, and a useful agent tool when appropriate. Avoid starting services or making provider calls at import time.

## Exchange adapter

Add a supported ID to the configuration and model literals, add the provider to the Settings → Exchanges section, and verify its CCXT credential format, sandbox semantics, market-order behavior, symbol normalization, and rate limits. Do not assume every exchange has a sandbox or honors `clientOrderId`.

Public market quotes and private balances have separate adapter ownership. Preserve source labels and show provider failures explicitly. Expand supported quote valuation deliberately; do not silently mark unsupported assets as worthless.

## Strategy

Add a catalog entry, an ID in `StrategyId`, and a branch in `signals`. Return +1, −1, or 0 without future data. The shared backtester handles fills, costs, equity, and metrics. Test the new algorithm with known sequences and test signal invariance when future rows are appended.

Do not put provider execution inside a signal function. A paper job should remain incapable of spending exchange funds.

## Forecast model

Keep model loading lazy. Put the implementation behind a separate service boundary with a version, supported assets, feature requirements, training period, forecast horizon, and calibration metrics. Update the response contract and UI labels so a baseline and a trained model remain distinguishable. Large model dependencies should be optional extras.

## Research and retrieval

An embedding retriever, document corpus, or web search provider can be added as a bounded read-only service and exposed as a ProtoLink native tool. Record source URLs and retrieval provenance. Do not present generic model output as retrieved evidence.

## Agent

Compose `Agent` with an explicit role and typed tool functions, using the existing domain services. Do not expose credentials, arbitrary shell execution, withdrawal APIs, or exchange order submission to a general-purpose research agent. If adding operational agents later, design authorization and auditable action contracts before granting mutation capabilities.

## UI

Add a typed response to `lib/types.ts`, use the shared API client, and include a loading state, actionable error state, and empty state. Prefer reusable panels and form controls. Preserve source labels, keyboard access, reduced-motion behavior, and mobile layouts.

## Documentation

Add the user-facing guide and developer contract in `docs/docs/`, then register the page in `docs/sidebars.js`. Build Docusaurus with broken links treated as errors. Document the implemented behavior and limitations, rather than future plans as though they already exist.

# Portfolio valuation

`services/valuation.py` prices native holdings in **USDT**. `Portfolio` uses it for the overview and per-account balances; it never reads user watchlist membership. All work occurs inside one `Market.snapshot()` so credentials, feed labels and cache namespaces cannot change during a read.

## Conversion graph

The selected source's active spot catalog supplies directed edges. A native `BASE/QUOTE` gives `BASE → QUOTE` at the ticker price and `QUOTE → BASE` at its inverse. There is no network-wide symbol guessing, automatic provider fallback or stablecoin parity substitution.

Path selection is deterministic: direct/inverse markets first, then one bridge, then two bridges. The reviewed bridge set is USDC, USD, BTC, ETH, EUR and DAI. At most three candidate paths are tried, with at most three native legs per path. A failed direct quote can use another supported path from the same source. Cycles and repeated currencies are excluded.

A holding's USDT price is the product of the leg rates. For 24-hour movement, reconstruct each leg's previous price from its provider percentage, invert when required, and compose the previous rates too. Missing/invalid daily change yields `null`, not zero. Portfolio daily change uses current quantities and is suppressed when any holding/account or required change is unavailable. This is reference price movement, not investment P&L.

Only the denomination, USDT, has an identity rate of one without a quote. USD and all other stablecoins need an observed route. For example, CoinGecko USD prices use its observed USDT/USD price to convert into USDT. The API catalogs include reviewed IDs for USDT, USDC and DAI alongside the six existing crypto assets. Their discovery remains curated; choose an exchange feed for its broader native catalog. API identity references: [CoinGecko simple price](https://docs.coingecko.com/demo/reference/simple-price).

## Quality and budgets

`Market.valuation_ticker(symbol)` caches exact quotes and sanitized failures for 30 seconds, separately by frozen source/credential namespace. It never calls `provider_symbol()` or fetches mini-charts. `Valuation` memoizes shared legs across holdings and revalidates timestamps on every read, including cache hits.

Positive finite prices are required. Invalid/nonpositive or over-one-minute-future timestamps are rejected. Quotes older than five minutes are excluded. Explicit Demo fixtures are exempt from live age checks. A missing provider timestamp produces a usable `undated` quote with visible warnings and fetch time; its age is not asserted. Only active native pairs from the catalog can be used.

A valuation allows up to 80 unique quote lookups and starts no additional uncached-in-this-read leg after a twelve-second elapsed budget. Each in-flight adapter request still has its own finite transport timeout, so this is not a hard twelve-second HTTP deadline. Assets beyond the budget return `limited` and an exclusion reason. Failed legs are reused rather than repeatedly hitting the provider. Empty/USDT-only overview wallets do not load a public catalog. Account display-currency options may request additional conversion quotes within the same budget.

Mini-charts use at most twelve unique daily-history reads. They compose aligned closed-candle closes along the chosen route, including inversion. Missing dates are omitted with no forward filling. A chart failure/budget limit never invalidates a current usable quote. Quote-only feeds return no synthetic charts.

## API contract

`GET /api/v1/portfolio` retains total/holdings/allocation and adds:

- `currency: "USDT"`, `complete`, and `coverage: {priced, total}`.
- `valuation_note`, `history_kind: "illustrative" | "observed"`, and `history_note`.
- On each priced holding: `status`, `path`, `route`, `observed_at`, `reason: null`, and converted `change`/`sparkline`.
- On each unpriced holding: native `quantity`, null price, `status` (`unavailable`, `stale` or `limited`) and a safe `reason`. No unknown quantity is represented as a zero-valued holding.

Each route leg includes exact `symbol`, `from_asset`, `to_asset`, `inverse`, applied `rate`, `previous_rate`, provider `observed_at`, and `received_at`. Source/environment metadata applies to the whole result. An undated leg makes the composed observation undated. The oldest dated leg is the composed observation time when all legs are dated.

`GET /api/v1/portfolio/accounts` uses the same engine, preserves free/reserved/total quantities, and adds quote evidence per holding and `complete` per account. Failed account totals are `null`, with `status: "error"`. `quote_rates` only lists successfully priced display currencies; `quote_details` explains those rates. Combined production scopes exclude sandbox funds. With only test accounts active, a test-only combined scope is available; individual test accounts always have explicit separate scopes. The accounts panel follows the selected scope. Neither endpoint performs a trade.

## History and Demo

Complete reads save an observed value per UTC hour. Missing assets/accounts never insert or overwrite a point. History scope includes a valuation-version prefix, account mode, reference source and hash of selected account IDs. It does not mix older parity-based totals or different account sets. Source records are local observations, not reconstructed exchange returns.

With explicitly active Demo preview **and** Demo prices, the illustrative history composes aligned sample rates for current virtual quantities. If those series are unavailable, use observed complete history instead. The Demo fixture catalog includes ADA/BTC, USDC/USDT, DAI/USDT, USDT/USD and EUR/USD in addition to familiar markets. Initial paper balances include ADA, USDC and EUR; existing quantities are never reset. USDC's fixture is 0.997 USDT and USD's conversion is observed through a 1.002 USDT/USD fixture. These numbers are samples, not live market claims.

Opening inventory, exchange P&L, deposits/withdrawals and cash-flow-adjusted performance remain separate backlog items.

## Active account scopes

Both endpoints accept `scope=all`, `scope=exchange:binance`, or `scope=account:<saved-id>`. Only active accounts can resolve. A combined scope sums production accounts when present; otherwise it can combine test accounts without mixing environments. Native quantities combine before pricing, and each holding includes `accounts` with contributing account IDs, labels, exchanges and quantities. `venues` includes per-account priced totals, unpriced counts and test flags. No-active responses contain `active: false`, empty collections and no new history; they do not resolve a market feed or fetch credentials. See [account selection](accounts.md).

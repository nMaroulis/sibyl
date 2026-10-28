# Exchange clients

All market and account reads now pass through `ExchangeClient`. `CCXTClient` implements the shared transport and normalization. Twenty production provider classes and two dedicated test-environment classes inherit it; `DemoClient` implements the same interface offline. Domain services do not construct CCXT adapters themselves.

```text
Market / Portfolio / ExchangeTrading
              │
        ExchangeClient
         ├── CCXTClient → BinanceClient, KrakenClient, OKXClient, …
         └── DemoClient → deterministic fixtures + Store paper ledger
```

## Client contract

| Method                                                 | Result / behavior                                                           |
| ------------------------------------------------------ | --------------------------------------------------------------------------- |
| `load_markets()` / `market(symbol)`                    | Active spot instruments only; exact canonical symbols, precision and limits |
| `fetch_ticker(symbol)`                                 | Unified numeric fields; unknown/non-finite optional values become `None`    |
| `fetch_ohlcv(symbol, timeframe, limit)`                | Sorted, deduplicated `[timestamp, open, high, low, close, volume]` rows     |
| `fetch_order_book(symbol, limit)`                      | Sorted finite bids/asks; adapts discrete venue depth limits                 |
| `fetch_balance()`                                      | `total`, `free`, `used` maps; native asset quantities                       |
| `amount_to_precision(symbol, amount)`                  | Provider precision mode, including tick-size markets                        |
| `fetch_open_orders(symbol)`                            | One exact market's open orders, if supported by the installed SDK           |
| `fetch_my_trades(symbol, since, limit)`                | One bounded fill page; no complete-history guarantee                        |
| `fetch_trade_page(symbol, cursor, limit)`              | Reviewed resumable import page; unsupported providers fail explicitly       |
| `fetch_order(order_id, symbol)`                        | Read a known order, without submission or retry                             |
| `create_order(symbol, "market", side, amount, params)` | Reviewed providers only; base quantity, mandatory `clientOrderId`           |
| `close()`                                              | Close the HTTP session and drop transport credential references             |

Timestamps and `since` use UTC Unix **milliseconds**. Quantities and candle volume use **base-asset units**. Book depth and history limits are upper bounds; exchanges may return fewer rows. Candle pages can contain an open candle; `Market` filters it before analytics or strategy evaluation. Provider `info`, raw account metadata and credential fields never appear in normalized responses.

Clients reuse rate-limited transports with 12-second request timeouts and per-client reentrant locks. `Market` also serializes previews and manages bounded result caches. There are no automatic write retries. CCXT exceptions retain their types internally; HTTP errors and connection checks redact provider text.

## Implemented providers

Provider subclasses share market, balance, order-status, open-order and bounded trade-read methods. A method is unavailable where the installed SDK does not implement it (for example Upbit trade history). Individual methods remain subject to the installed SDK's capabilities, exchange availability and account permissions. `/api/v1/exchanges` reports `native`, `emulated` or `unavailable` separately. **Adapter implementation and automated fake-transport tests are not authenticated exchange acceptance tests.**

| Provider / ID                     | Credentials beyond key + secret          | Wallet scope                                       | Sandbox exposed | Manual market/GTC limit orders                   |
| --------------------------------- | ---------------------------------------- | -------------------------------------------------- | --------------- | ------------------------------------------------ |
| Binance / `binance`               | —                                        | Spot                                               | Yes             | Existing reviewed flow                           |
| Binance.US / `binanceus`          | Separate US credentials                  | Spot                                               | No              | Implemented · guarded manual flow                |
| Coinbase / `coinbase`             | CDP key name + supported PEM private key | Advanced Trade spot                                | No              | Existing reviewed flow                           |
| Kraken / `kraken`                 | —                                        | Spot                                               | No              | Existing reviewed flow                           |
| OKX / `okx`                       | Passphrase                               | Trading wallet                                     | Yes             | Implemented · guarded manual flow                |
| Bybit / `bybit`                   | —                                        | Unified account; shared collateral may be included | Yes             | Implemented · guarded manual flow                |
| KuCoin / `kucoin`                 | Passphrase                               | Classic spot trading wallet                        | No              | Implemented · guarded manual flow                |
| Gate / `gate`                     | —                                        | Spot                                               | Yes             | Pending                                          |
| Bitget / `bitget`                 | Passphrase                               | Classic spot wallet                                | No              | Pending                                          |
| MEXC / `mexc`                     | —                                        | Spot                                               | No              | Pending                                          |
| HTX / `htx`                       | —                                        | Spot                                               | No              | Pending                                          |
| Crypto.com Exchange / `cryptocom` | Exchange keys, separate from retail app  | Exchange wallet                                    | Yes             | Pending                                          |
| Bitstamp / `bitstamp`             | —                                        | Spot                                               | No              | Implemented · guarded manual flow                |
| Gemini / `gemini`                 | —                                        | Spot                                               | Yes             | GTC limit + cancel only; no native market orders |
| Bitfinex / `bitfinex`             | —                                        | Exchange wallet                                    | No              | Pending                                          |
| CoinEx / `coinex`                 | —                                        | Spot                                               | No              | Pending                                          |
| BitMart / `bitmart`               | API memo → CCXT `uid`                    | Spot                                               | No              | Pending                                          |
| Phemex / `phemex`                 | —                                        | Spot                                               | Yes             | Pending                                          |
| Poloniex / `poloniex`             | —                                        | Spot                                               | No              | Pending                                          |
| Upbit / `upbit`                   | —                                        | Default CCXT endpoint                              | No              | Pending                                          |
| Demo / `demo`                     | None                                     | Persistent workspace paper wallet                  | Offline         | Simulated immediate fills                        |

Sandbox availability is intentionally configured, not inferred from a generic exchange marketing page. It is applied before the first request, requires environment-specific keys and may have different instruments. Region-specific endpoints, unified-account variants and funding wallets need separate work; the selected scope is explicit in the catalog and connection form.

## Dedicated test clients

| ID / class                                   | CCXT transport     | Environment               | Credentials                       |
| -------------------------------------------- | ------------------ | ------------------------- | --------------------------------- |
| `binance-testnet` / `BinanceTestnetClient`   | `binance`          | Binance Spot Test Network | Testnet key + secret              |
| `coinbase-sandbox` / `CoinbaseSandboxClient` | `coinbaseexchange` | Coinbase Exchange Sandbox | Sandbox key + secret + passphrase |

These connection IDs are deliberately excluded from `SIBYL_MARKET_EXCHANGE`, which selects a production public-reference provider. Both constructors force sandbox routing before any request. The request model and Store persist `sandbox=true` for either ID, even when the input says false. Existing `binance` connections with `sandbox=true` remain supported. CCXT transport IDs are explicit catalog metadata rather than inferred from user strings.

The shared account, order-status and fill-page APIs work for the test clients. `Portfolio.overview()` excludes all sandbox balances from actual-funds totals; `Portfolio.accounts()` shows them individually with `sandbox=true` for inspection. The dedicated clients also support the guarded manual market-order flow. Coinbase Exchange uses native base `size` and UUID `client_oid`; it does not use Advanced Trade's CDP key or order configuration.

The Advanced Trade static sandbox is a different API and is not substituted for the Exchange test service. Provider outages and authentication errors propagate without production or offline-demo fallback. Public test-market checks fetched markets, tickers and books successfully on 2026-10-20. Scoped authenticated Binance Testnet order/strategy acceptance is recorded in the [acceptance results](exchange-acceptance.md); authenticated Coinbase Exchange Sandbox accounts/fills remain unverified.

## Verification snapshot

Public read checks on **2026-10-20**, using installed CCXT **4.5.64**, loaded active spot instruments and fetched a BTC ticker, five daily candles and five bid/ask levels successfully for **18 providers**. CoinEx returned HTTP 503 for its public market endpoint, and BitMart returned a network error for public spot-symbol discovery from this environment. Their implementations remain available, with those public checks unresolved. Neither failure produced demo substitution. This snapshot does not establish continuing uptime or validate private accounts, sandbox trading or orders.

Automated tests also exercise actual CCXT Coinbase request generation with the final transport replaced: both sides retain the reviewed base quantity in native `base_size`, and the stored client ID is sent as `client_order_id`. New intents use UUIDs compatible with Kraken's client-ID formats. References: [Coinbase create order](https://docs.cdp.coinbase.com/api-reference/advanced-trade-api/rest-api/orders/create-order), [Kraken add order](https://docs.kraken.com/api-reference/trading/add-order).

## Use a client

```python
from sibyl.exchanges import create_client

client = create_client("kraken")  # Public-only; construction makes no request.
try:
    markets = client.load_markets()
    ticker = client.fetch_ticker("BTC/USD")
finally:
    client.close()
```

The application resolves private credentials from `Store.credentials()` only when constructing the selected saved account. Do not send them to agents or frontend response contracts.

```python
from pathlib import Path
from sibyl.exchanges import create_client
from sibyl.storage import Store

# Use a disposable workspace for development experiments.
store = Store(Path("/tmp/sibyl-demo-example"))
demo = create_client("demo", store=store)
quote = demo.fetch_ticker("BTC/USDT")
fill = demo.create_order(
    "BTC/USDT", "market", "buy", 0.001,
    params={"clientOrderId": "example-paper-order-001"},
)
assert demo.fetch_order(fill["id"], "BTC/USDT")["status"] == "closed"
```

Demo fills use the existing paper ledger's transactional idempotency and 0.1% quote-asset fee. Reusing the same ID and order details returns the original fill, including after restart. Insufficient paper funds reject the fill. Resting GTC limits reserve virtual funds and match through managed-order checks; partial fills, latency and realistic liquidity are not simulated. See [order management](order-management.md). Price fixtures preserve the original deterministic sequence; they are not a realistic evolving exchange feed. Saved real connections are still real when explicitly checked in demo mode. Demo is never a fallback for failed live requests and is saved as a credential-free connection (`id=demo`). The backend connects and activates it only after an explicit Preview with Demo action. Fresh workspaces have no accounts active. Reconnecting restores the same wallet without resetting funds or duplicating balances.

## HTTP integration

- `GET /api/v1/exchanges`: provider metadata (including Demo), credential requirements, sandbox/execution policy, installed CCXT version and read capabilities. `not_configured` lists the remaining identifiers in the installed SDK; it includes products outside this spot scope.
- `GET /api/v1/connections/{id}/balances`: normalized per-account balances, source and sandbox flag.
- `GET /api/v1/connections/{id}/open-orders?symbol=BTC/USDT`: exact-market open orders.
- `GET /api/v1/connections/{id}/trades?symbol=BTC/USDT&since=0&limit=100`: bounded private fill page (`limit` 1–500), explicitly `complete_history: false`.

These routes have the same workspace access controls as other APIs. Account reads run against the selected saved connection, including Demo, regardless of public market mode. Portfolio aggregation selects saved demo connections in demo mode and saved real connections in live mode. They never submit/cancel orders, and do not provide arbitrary provider method or URL access. There is no public endpoint for mutating the demo client directly; use the existing paper order UI/API.

## Remaining implementation checklist

- [x] Shared base class, factory, explicit provider registry and runtime capability catalog.
- [x] Twenty production CCXT spot clients, two dedicated test-environment clients; offline client using the same interface and persistent paper wallet.
- [x] Provider-specific credential validation, encrypted passphrase/API memo storage, sandbox allowlist and transport cleanup.
- [x] Unified markets, quotes, candles, books, balances, order reads and bounded fill reads.
- [x] Backend-driven searchable connection UI and reference-exchange selection.
- [ ] Authenticated read acceptance tests for **every provider**, including sandbox accounts. No private accounts were used to develop this layer.
- [x] Review base-sized market/GTC limit submission and cancellation for Binance.US, OKX, Bybit UTA, KuCoin classic and Bitstamp; GTC limits/cancellation for Gemini. Test actual SDK request generation without network writes.
- [ ] Implement submission/cancellation for the remaining 11 production providers; their client-ID and base/quote semantics need separate review.
- [ ] Detailed fill/fee reconciliation, durable imports, client-ID recovery and account-wide discovery for OKX, Bybit, KuCoin, Bitstamp and Gemini; these are separate from cumulative status reads.
- [x] Durable selected-market fill imports for Demo, Binance/Binance.US/Testnet, Coinbase/Sandbox, Kraken, OKX, Bybit UTA, KuCoin classic and Bitget classic. Native-currency fees, pause/resume, incremental passes, available-history rescans and retained ranges appear in Account history. See [account synchronization](account-sync.md).
- [ ] Durable pagination for remaining providers, complete account-history coverage, order/cash-event reconciliation and exchange P&L. Caught up is not complete account history.
- [x] Resting GTC limits, reviewed cancellation, cumulative fill status and persisted polling for the existing execution allowlist and Demo.
- [ ] Cancel/replace and stop/OCO order flows.
- [ ] WebSocket subscriptions, reconnect/backoff handling and streaming order updates. Current reads are REST snapshots.
- [ ] Funding/earn/staking/subaccount wallets, transfers, derivatives and unified-account variants beyond the scopes above. Withdrawal APIs are not implemented.
- [x] Held-asset spot valuation through exact direct/inverse/bridge routes and observed stablecoin/fiat rates; see [portfolio valuation](portfolio-valuation.md). Broader aggregator catalogs and external FX sources remain future work.
- [ ] Historical candle pagination beyond a provider's single-page limit; explicit retention and import cursors.
- [ ] Region-specific deployments and endpoints (for example OKX US/EEA and Upbit regional variants).
- [ ] Additional venues. Useful next candidates include Bitvavo, WhiteBIT, Bitbank, bitFlyer, Bithumb, Coincheck, Luno, BTC Markets, Indodax, Bitrue, AscendEX and BingX. The catalog's `not_configured` array gives the complete installed-SDK remainder rather than presenting them as supported clients.

## Add another exchange

1. Add its identifier to `ExchangeId` and an `ExchangeSpec` in `catalog.py`. Validate its credentials and wallet scope against the installed CCXT provider and official exchange docs.
2. Add a documented `CCXTClient` subclass in `providers.py`, set account options/depth limits as needed, and register it in `CLIENTS`. Keep `market_orders=False` until order semantics are reviewed.
3. Add provider-specific assertions to `tests/test_exchange_clients.py`; its shared contract suite automatically exercises every registered class. Check sandbox routing before any network request.
4. Exercise public reads and authenticated read-only account access separately. Record failures honestly; never substitute fixtures for a real source.
5. Update this matrix. The Settings catalog and server configuration choices update from the backend automatically.

For providers outside CCXT, implement `ExchangeClient` directly, as the demo client does. Keep provider payloads inside the adapter. Reference: [CCXT official documentation](https://docs.ccxt.com/).

## Settings support details

Clicking a provider opens five feature categories before credential entry: Account overview, Spot trading, History & synchronization, Market data, and Automation & limits. Each feature is **Supported**, **Simulated**, **Not implemented** or **Unavailable**. Saved accounts have a **Features** button for reopening the same view. `support.py` assembles these app-level groups in `/api/v1/exchanges`; raw CCXT `has` flags remain separate. A provider API offering an operation does not enable it in Sibyl.

Spot submission now includes Binance.US, OKX, Bybit UTA, KuCoin classic and Bitstamp, alongside the original providers. Gemini supports GTC limits and cancellation, with market submission blocked. `ExchangeSpec.supports_order()` gates both the service and adapter, and Trade hides market orders for limit-only accounts. Reviewed quantities are always base units. OKX persists a 32-character alphanumeric client ID before submission and explicitly uses `tdMode=cash`, `tgtCcy=base_ccy`. Bybit uses UTA, `marketUnit=baseCoin` and no leverage. KuCoin pins classic spot mode instead of probing or silently switching to UTA. Bybit known-order status uses the acknowledged last-500-orders endpoint; older observations may be unavailable.

Native request-generation tests replace the final SDK transport and check buy/sell amounts, GTC prices, client IDs, cancellation and status reads. They never submit an order. Provider references: [Binance.US](https://docs.binance.us/), [OKX place order](https://www.okx.com/docs-v5/en/#order-book-trading-trade-post-place-order), [Bybit place order](https://bybit-exchange.github.io/docs/v5/order/create-order), [KuCoin classic orders](https://www.kucoin.com/docs-new/rest/spot-trading/orders/add-order), [Bitstamp](https://www.bitstamp.net/api/), [Gemini orders](https://developer.gemini.com/trading/rest-api/orders).

Binance.US also uses the reviewed Binance client-ID recovery and account-order discovery contracts. OKX, Bybit UTA and KuCoin classic now have durable imports and exact-order fill/fee reconciliation, with explicit retention limits. Bitget classic has durable fill imports but remains read-only for order submission. Bitstamp and Gemini still need durable imports and detailed reconciliation. Client-ID recovery and account-wide discovery remain pending for OKX, Bybit, KuCoin, Bitstamp and Gemini. An ambiguous submission is never retried: inspect it at the exchange. Funding covers production Binance/Kraken plus Bybit master-UID on-chain withdrawals. Optional sandboxes do not inherit funding support. See [import scope](account-sync.md), [reconciliation](order-reconciliation.md) and [funding](funding-history.md).

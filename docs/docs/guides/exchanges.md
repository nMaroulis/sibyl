# Exchange connections

Sibyl has 20 spot exchange clients and an offline demo client. **Settings → Exchanges** gets its searchable provider catalog from the Python backend. Multiple accounts per exchange are supported. Keys, passphrases and API memos are encrypted in your local workspace and cannot be retrieved through the API.

Supported providers: Binance, Binance.US, Coinbase, Kraken, OKX, Bybit, KuCoin, Gate, Bitget, MEXC, HTX, Crypto.com Exchange, Bitstamp, Gemini, Bitfinex, CoinEx, BitMart, Phemex and Poloniex, plus Upbit.

## Connect an account

1. Create an exchange API key dedicated to Sibyl with balance/account read access.
2. Find your provider in **Settings → Exchanges**, then enter an account label, key and secret.
3. OKX, KuCoin and Bitget also require an API passphrase. BitMart requires the API memo. Coinbase uses the supported CDP key name and PEM private key, rather than an ordinary secret string.
4. Where offered, select sandbox/testnet and use credentials created for that environment.
5. Save, then select **Check access** to make an actual read-only balance request.

Saving is not verification. Accounts display **Saved · unverified** until checked. Verification display lasts for the current page session; each check reads the exchange again. Failed checks do not substitute demo data. Geographic restrictions, account variants, IP allowlists, server time and provider outages can affect access.

## Develop with demo data

Choose **Preview with Demo** from Portfolio, Trade, or the smaller Demo section in Exchanges. No account is activated automatically at startup. The `DemoClient` supplies its persistent virtual wallet through the same client interface as exchanges. For fully offline reference prices, also select **Demo prices** in Market data. These choices are separate from the legacy `SIBYL_MODE` research default.

The preview is explicitly labeled in the header and account-dependent pages. Only one virtual wallet exists per workspace. Reconnecting or previewing again keeps quantities and paper trades. **Exit preview** deactivates it without deleting records. Demo stays unavailable while exchange accounts are active; activating an exchange automatically turns it off. Actual-funds order entry never lists Demo.

Checking saved exchange credentials is an explicit provider read, separate from activation. No provider failure falls back to Demo.

All exchange logos are bundled locally. Demo prices, seed quantities and wallet mutations belong to the Python backend; React displays API responses and has no hardcoded demo balances or prices.

## Live data and account scope

Connect and activate your exchange accounts in Settings. Choose any public feed in Market data or set `SIBYL_MARKET_EXCHANGE` for the initial feed. `SIBYL_MODE` does not activate accounts. Public prices use that reference exchange; private balances use each saved account independently. Settings → Market data can save these choices for restart, or generate an environment snippet for another workspace. Saved workspace choices override environment defaults.

Most clients read the spot trading wallet, excluding funding/earn/margin wallets. Bitfinex reads the exchange wallet, OKX the trading wallet, and KuCoin the classic trading account. Bybit reads its unified account, whose quantities can include shared collateral. Crypto.com Exchange is separate from the retail mobile app. See the [provider matrix](../developers/exchange-clients.md#implemented-providers) for exact scope and remaining account variants.

## Test environments and orders

**Binance Testnet** and **Coinbase Sandbox** have dedicated provider cards in Settings, with their own badges and setup links. They use external test services with account-specific virtual funds. They are distinct from the offline Demo wallet. Saving either dedicated provider always enables test routing on the server, even if a request supplies `sandbox: false`.

| Option           | API credentials                                     | Create keys / fund the test account                                        |
| ---------------- | --------------------------------------------------- | -------------------------------------------------------------------------- |
| Binance Testnet  | Spot testnet API key + secret                       | [Binance Spot Test Network](https://testnet.binance.vision/)               |
| Coinbase Sandbox | Coinbase Exchange sandbox key + secret + passphrase | [Coinbase Exchange Sandbox](https://public.sandbox.exchange.coinbase.com/) |

Coinbase Sandbox here uses the **Coinbase Exchange API**, with separate sandbox credentials. The production Coinbase card uses **Advanced Trade**, whose CDP keys are different. The [Advanced Trade sandbox](https://docs.cdp.coinbase.com/coinbase-app/advanced-trade-apis/sandbox) returns predefined mock accounts/orders; it is not the account-based Exchange sandbox integrated here. See [Coinbase's Exchange sandbox guide](https://docs.cdp.coinbase.com/exchange/introduction/sandbox).

After saving, use **Check access** to read the test account. Test accounts appear individually in Portfolio's **Account balances**, with a sandbox/test-funds label. Their quantities are excluded from live portfolio totals. Valuation uses the selected public quote mode, not a guaranteed execution price on the test service.

The original Binance card still accepts its testnet checkbox for existing workflows. Optional sandboxes also remain configured for OKX, Bybit, Gate, Crypto.com Exchange, Gemini and Phemex. Instruments and credentials can differ from production. Sandbox routing is applied before the first provider request; there is no production fallback.

Manual market orders for the two dedicated test providers use the existing 60-second preview, typed confirmation and server execution setting. This server setting currently guards all exchange submission, including test funds. No test or real orders are sent automatically when a connection is saved or checked. Production market orders remain limited to Binance, Coinbase and Kraken. Module agents have no submission or credential tools.

## Disconnect

Disconnect removes the encrypted record, clears account caches and closes the provider session. It does not close the exchange account or revoke its key. Revoke or rotate keys at the exchange when needed.

## Activation and combined views

Saving a connection activates it. Use its Active/Inactive control to include or exclude it without deleting credentials. Multiple active exchange accounts feed **Portfolio → All exchanges**; the picker also offers exchange and individual-account scopes. No accounts are active on a fresh workspace. Demo is an explicit optional preview and is automatically deactivated when an exchange account activates. It cannot activate while exchange accounts remain active. Inactive accounts stop new imports and cannot submit orders; retained history stays accessible.

## Verification and missing work

Contract tests exercise every client using controlled transports, and installed CCXT configuration is checked without account access. Authenticated exchange accounts and real orders have not been acceptance-tested. The [exchange client reference and checklist](../developers/exchange-clients.md#remaining-implementation-checklist) distinguish implemented adapters from missing execution, imports, streaming, account variants and additional venues.

Public reference prices can resolve a missing USDT pair through USD or USDC at approximate parity. Actual order symbols always remain exact. Portfolio uses a separate exact-pair conversion engine for actual holdings, with observed stablecoin/fiat rates and explicit unpriced coverage.

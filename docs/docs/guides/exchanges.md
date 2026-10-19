# Exchange connections

Sibyl uses [CCXT](https://docs.ccxt.com/) to normalize spot-account access for Binance, Coinbase, and Kraken. Credentials are stored on your own API server and encrypted before being written to SQLite.

## Connect an account

1. Create an exchange API key dedicated to Sibyl.
2. Enable balance/account read permissions. Keep trading and withdrawal permissions disabled for portfolio use.
3. In **Settings → Exchanges**, choose the exchange and enter an account label, API key, and secret.
4. For Coinbase Advanced Trade, use the current CDP key name and corresponding private key. Use a key type supported by your installed CCXT version.
5. Save the connection, then select **Check access** to make an actual read-only balance request.

Saving a connection is not verification. The UI labels it **Saved · unverified** until a successful check. Verification display is local to the current page session; each check reads the exchange again.

## Sandbox and permissions

The form exposes Binance testnet. The adapter calls `set_sandbox_mode(True)` before any provider request. Credentials must belong to that environment. Coinbase and Kraken do not have an equivalent universally supported spot sandbox here; production accounts must use appropriate permissions.

If you separately enable manual exchange orders, use a key with spot trading permissions. Withdrawals are never required. Oracle has no credential access or order-execution tool.

## Live portfolio data

Set `SIBYL_MODE=live` and restart the API. Private balances come from each connected account. The six-asset public watchlist uses `SIBYL_MARKET_EXCHANGE`; quote availability and geographic access differ by provider.

Provider failures are shown. Check the credential format, exchange region, account permissions, server clock, IP allowlist, and provider status when troubleshooting.

## Disconnect

Disconnect removes the encrypted record and its in-memory adapter. It does not close your exchange account or revoke the API key at the provider. Revoke or rotate the key at the exchange when you want to invalidate it.

## Adapter verification

Automated tests verify adapter configuration and execution using controlled fakes. Private Binance, Coinbase, and Kraken accounts have not been exercised as part of the repository build; verify each account using the UI before relying on connected data or orders.

Public reference quotes fall back from USDT to USD or USDC when the configured exchange lacks that pair. These quote currencies are approximated at parity for portfolio and chart comparison. Actual exchange orders always use the exact market symbol entered.

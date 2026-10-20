# Configuration

Settings are validated by `pydantic-settings`. Environment variables override `.env`; all application settings use the `SIBYL_` prefix. Restart the API after changing environment variables. A saved model profile in Settings takes precedence over the LLM environment defaults and applies without a restart.

| Variable                   | Default                           | Purpose                                                                                       |
| -------------------------- | --------------------------------- | --------------------------------------------------------------------------------------------- |
| `SIBYL_HOST`               | `127.0.0.1`                       | API bind address                                                                              |
| `SIBYL_PORT`               | `8000`                            | API port                                                                                      |
| `SIBYL_DATA_DIR`           | `.sibyl`                          | SQLite and local vault directory                                                              |
| `SIBYL_MODE`               | `demo`                            | `demo` paper balances or `live` connected account balances                                                       |
| `SIBYL_NEWS_MODE`          | `auto`                            | Follow account mode, or independently choose `demo` / `live` news |
| `SIBYL_NEWS_REFRESH_SECONDS` | `600`                          | Publisher collection interval, 60–86,400 seconds |
| `SIBYL_NEWS_RETENTION_DAYS` | `30`                            | News archive retention, 1–365 days, capped at 5,000 stories |
| `SIBYL_MARKET_EXCHANGE`    | `binance`                         | Default market feed, independent of account mode: any of the 20 exchange IDs in the [catalog](../developers/exchange-clients.md) |
| `SIBYL_CORS_ORIGINS`       | localhost and 127.0.0.1 port 5173 | JSON array of permitted browser origins                                                       |
| `SIBYL_API_TOKEN`          | empty                             | Bearer token for all versioned API routes                                                     |
| `SIBYL_ALLOW_LIVE_TRADING` | `false`                           | Enable reviewed manual exchange market orders                                                 |
| `SIBYL_LLM_PROVIDER`       | `none`                            | `none` or any provider in [Settings](../guides/settings.md)                                   |
| `SIBYL_LLM_MODEL`          | empty                             | Model name; provider default is used if omitted                                               |
| `SIBYL_LLM_BASE_URL`       | `http://127.0.0.1:11434`          | Model server URL for the environment-selected adapter                                         |

Example for connected balances with local inference:

```dotenv
SIBYL_MODE=live
SIBYL_MARKET_EXCHANGE=kraken
SIBYL_LLM_PROVIDER=ollama
SIBYL_LLM_MODEL=your-installed-model
SIBYL_LLM_BASE_URL=http://127.0.0.1:11434
```

Exchange credentials are added in **Settings → Exchanges**. Save model credentials in **Settings → AI models**, or supply provider environment variables such as `OPENAI_API_KEY` and `ANTHROPIC_API_KEY` to the API process.

## Network access

Without a token, bind the API to loopback. The application refuses non-loopback startup without a token. Browser requests must come from a permitted origin or the API's own origin; the local host check also limits tokenless access.

When setting an API token, enter it in the dashboard's **Settings → Workspace** section. The browser stores it in `sessionStorage`, not as an exchange credential. Use TLS and an authenticated reverse proxy if exposing the service beyond your computer. Sibyl does not implement multiple users or account-level access separation.

## State and backups

The workspace directory contains `sibyl.db` and `vault.key`. It stores encrypted exchange credentials, manual paper balances and orders, historical backtests, agent requests and responses, observed live portfolio snapshots, paper strategy jobs, and exchange order intents/results.

Back up the directory as a unit with the API stopped. The vault key is necessary to recover stored credentials. Existing state is not reset when toggling demo/live data. Paper and connected exchange funds remain separate.

## Configuration helper in Settings

[Settings](../guides/settings.md) groups accounts and configuration into five tabs: Exchanges, AI models, News, Market data, and Workspace. AI models saves an encrypted provider-specific profile, including an optional API key, and activates it immediately for new agent requests. Preset model choices and custom IDs are supported for every adapter. Stored profiles override environment LLM defaults after restart; provider environment keys remain a fallback when no saved key exists.

News saves enabled collectors and encrypted optional NewsAPI credentials immediately. Market data saves one default feed and encrypted provider-specific keys immediately, independently of account mode. Saved workspace choices override environment defaults. Public exchanges need no key; saved accounts retain their own environment. See [Market data sources](../developers/market-data.md). Workspace shows current runtime settings and manages browser-session access. Local model downloads, quantization, and deployment management are marked **Coming soon**.

## Public crypto research

The Crypto profiles tab fetches CoinPaprika and Wikipedia public data in either market mode. It needs internet access but no provider API key. Source caches are saved under `SIBYL_DATA_DIR/crypto-research/`. These public observations are separate from demo prices, trading balances, and exchange credentials. See the [Research guide](../guides/research.md).

## Public news

Choose public publisher feeds on News without changing exchange/account mode. `SIBYL_NEWS_MODE=live` also enables continuous feed collection while the API runs. Public excerpts and source health persist in `SIBYL_DATA_DIR/news.sqlite3`; no news API key is needed. Demo stories stay separate. See the [News backend](../developers/news.md).

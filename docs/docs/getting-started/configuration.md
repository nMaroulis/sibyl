# Configuration

Settings are validated by `pydantic-settings`. Environment variables override `.env`; all application settings use the `SIBYL_` prefix. Restart the API after changing them.

| Variable                   | Default                           | Purpose                                                      |
| -------------------------- | --------------------------------- | ------------------------------------------------------------ |
| `SIBYL_HOST`               | `127.0.0.1`                       | API bind address                                             |
| `SIBYL_PORT`               | `8000`                            | API port                                                     |
| `SIBYL_DATA_DIR`           | `.sibyl`                          | SQLite and local vault directory                             |
| `SIBYL_MODE`               | `demo`                            | `demo` fixtures or `live` provider data                      |
| `SIBYL_MARKET_EXCHANGE`    | `binance`                         | Public quotes: `binance`, `coinbase`, `kraken`               |
| `SIBYL_CORS_ORIGINS`       | localhost and 127.0.0.1 port 5173 | JSON array of permitted browser origins                      |
| `SIBYL_API_TOKEN`          | empty                             | Bearer token for all versioned API routes                    |
| `SIBYL_ALLOW_LIVE_TRADING` | `false`                           | Enable reviewed manual exchange market orders                |
| `SIBYL_LLM_PROVIDER`       | `none`                            | `none`, `ollama`, `openai`, `anthropic`, `openai-compatible` |
| `SIBYL_LLM_MODEL`          | empty                             | Model name; provider default is used if omitted              |
| `SIBYL_LLM_BASE_URL`       | `http://127.0.0.1:11434`          | Ollama or compatible model server URL                        |

Example for connected balances with local inference:

```dotenv
SIBYL_MODE=live
SIBYL_MARKET_EXCHANGE=kraken
SIBYL_LLM_PROVIDER=ollama
SIBYL_LLM_MODEL=your-installed-model
SIBYL_LLM_BASE_URL=http://127.0.0.1:11434
```

Exchange credentials are added in **Settings → Exchanges**, not in this configuration file. Hosted model credentials such as `OPENAI_API_KEY` and `ANTHROPIC_API_KEY` are provider environment variables.

## Network access

Without a token, bind the API to loopback. The application refuses non-loopback startup without a token. Browser requests must come from a permitted origin or the API's own origin; the local host check also limits tokenless access.

When setting an API token, enter it in the dashboard's **Settings → Workspace** section. The browser stores it in `sessionStorage`, not as an exchange credential. Use TLS and an authenticated reverse proxy if exposing the service beyond your computer. Sibyl does not implement multiple users or account-level access separation.

## State and backups

The workspace directory contains `sibyl.db` and `vault.key`. It stores encrypted exchange credentials, manual paper balances and orders, historical backtests, agent requests and responses, observed live portfolio snapshots, paper strategy jobs, and exchange order intents/results.

Back up the directory as a unit with the API stopped. The vault key is necessary to recover stored credentials. Existing state is not reset when toggling demo/live data. Paper and connected exchange funds remain separate.

## Configuration helper in Settings

[Settings](../guides/settings.md) groups accounts and configuration into four tabs: Exchanges, AI models, Other APIs, and Workspace. AI models generates a downloadable `sibyl-models.env` snippet for the provider, model name, and optional server URL. Other APIs generates `sibyl-data.env` for market mode and reference exchange. Workspace shows current server configuration and browser-session access.

The helpers do not change the running server or include credentials. Merge generated lines into the server's existing `.env`, supply provider credentials separately, then restart the API. Execution permissions remain separately configured. Local model downloads, quantization, and deployment management are marked **Coming soon**.

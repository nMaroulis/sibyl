# Authenticated exchange acceptance

## October 27, 2026 observations

Read-only balance checks succeeded on one configured Binance production account, one Binance Spot Testnet account and one Coinbase Advanced Trade production account. These checks establish balance access for those credentials at that time. They do not verify every wallet type, funding history, trading permission or deployment.

The actual **Binance Spot Test Network** then exercised Sibyl's native client and HTTP order lifecycle using virtual funds:

| Scenario                        | Observed result                                                                                                                         |
| ------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------- |
| Limit buy review and submission | A non-crossing GTC order opened with a retained native ID.                                                                              |
| Repeated confirmation           | Returned the same native order identity.                                                                                                |
| Cancellation                    | Native status became canceled; zero fills reconciled.                                                                                   |
| Market buy                      | Closed with one retained native fill and an explicitly reported zero BTC fee.                                                           |
| Client-ID lookup                | Found the submitted native buy using its persisted client order ID.                                                                     |
| Market sell                     | Sold the confirmed purchased units; closed with one retained fill and an explicitly reported zero USDT fee.                             |
| Reconciliation                  | Native quantities, costs and reported fees matched the retained ledger for all three orders. This is not final settlement verification. |
| Restart                         | All three retained order reports remained readable with submissions disabled.                                                           |

The two filled order reviews were about 12 virtual USDT each. All three test orders were terminal. No production order was submitted. The acceptance workspace was isolated from the main application's order records and execution flags.

Partial fills, late fee corrections, cancellation/fill races, induced lost network responses, production order execution, full imports and automated strategy behavior were **not** accepted by this manual-order run. The separate strategy observations below extend that scope. Deterministic tests remain separate from live venue acceptance.

## Repeat the test

`check_binance_testnet.py` accepts only the ID of a saved **dedicated Binance Testnet** connection. It decrypts that connection internally without printing or accepting secret values on the command line. It creates a new isolated workspace containing that one Testnet account and uses the actual API handlers. Native CCXT HTTP requests are pinned to `testnet.binance.vision`; no production keys or execution flags are changed.

```bash
uv run python scripts/check_binance_testnet.py \
  --account-id YOUR_SAVED_TESTNET_CONNECTION_ID \
  --workspace .sibyl/acceptance/NEW_TEST_RUN \
  --execute-testnet
```

This command explicitly authorizes one resting limit buy/cancel plus a market buy/sell using test funds. Each review must remain within 15 USDT reference notional. Market execution can differ from a review price. The sell is bounded to purchased units after reported base fees; unrelated holdings are not selected for sale.

The workspace path must be new. It retains the encrypted Testnet credentials, native intent/ledger data and `acceptance.json` with sanitized outcomes. Protect it like the main workspace. The JSON contains no keys or individual account balances. Uncertain submissions/cancellations stop the check and preserve evidence; no write is automatically replayed. Inspect the retained state and Testnet orders before another run.

Use [Binance's Spot Test Network](https://testnet.binance.vision/) for virtual-fund credentials. Coinbase's separate [Exchange Sandbox](https://docs.cdp.coinbase.com/exchange/introduction/sandbox) requires keys from its own interface, including the passphrase; CDP Portal sandbox keys target different APIs and were not used here.

## Automated strategy acceptance

The October 27 strategy check used real Testnet candles, a one-minute strategy and a **12 virtual USDT** allocation. It exercised the application's actual background worker and HTTP handlers. No candles, signals, balances, order responses or fills were fabricated.

| Scenario                         | Observed result                                                                                                                                                                                        |
| -------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Repeated start approval          | Retained the same run identity. The start primed the current closed candle.                                                                                                                            |
| Entry                            | A later real signal produced one price-capped native GTC buy. Native quantity and explicit fees reconciled.                                                                                            |
| Restart with a position          | Startup paused the previously running job and retained its owned units and original order.                                                                                                             |
| Shared capital                   | A second allocation of 6 USDT was refused against the 15 USDT shared limit and existing 12 USDT allocation.                                                                                            |
| Global halt                      | Paused the run and refused Resume, while retaining holdings.                                                                                                                                           |
| Separate exit approval           | Stop & cancel retained ownership; Close position submitted one owned-unit GTC sell. Repeated approval retained its identity.                                                                           |
| Exit accounting                  | Native fills/fees reconciled. The fee reserve and quantity precision left a small owned remainder; it was not silently discarded or sold again.                                                        |
| Disabled restart                 | The stopped run, both native orders and the global halt remained available with both execution flags disabled.                                                                                         |
| Deliberately lost entry response | A second run discarded its actual successful buy response. The strategy paused; one native client-ID lookup page recovered the same order, its executions reconciled, and no second buy was submitted. |

Both runs completed with one native buy and one native sell each. One entry had two individual executions; an intermediate open/partially-filled state was not accepted. These observations cover a small Binance Spot Testnet workflow. They do not establish production execution readiness, partial-fill behavior, late corrections, every strategy or other venues. Shared exposure and daily-loss rules have deterministic coverage; this check does not deliberately induce an exposure breach or daily-loss lock.

### Repeat the strategy check

```bash
uv run python scripts/check_binance_strategy_testnet.py \
  --account-id YOUR_SAVED_TESTNET_CONNECTION_ID \
  --workspace .sibyl/acceptance/NEW_STRATEGY_RUN \
  --execute-testnet
```

The command creates a new encrypted workspace containing only the selected dedicated Testnet account. It enables execution only there. Its transport gate admits **at most one BTC/USDT limit buy and one separately approved strategy-owned limit sell**, each bounded to 15 USDT at its limit price. Requests cannot reach production trading endpoints. Only credential-free GETs to the Binance public market endpoints used for shared-risk reference prices are allowed outside Testnet. This public reference feed is distinct from the Testnet execution price.

The initial closed-candle EMA direction chooses either the short-period EMA strategy or an RSI strategy. This is an acceptance fixture, not a strategy recommendation. The normal worker waits for a subsequent real signal; it does not force an entry. `--signal-wait` bounds that wait to 60–600 seconds (default 300). No entry, an unresolved submission or incomplete reconciliation produces an incomplete check with a retained workspace. The tool halts future signals on failure and never guesses a liquidation or repeats an uncertain write. Already approved order expiry can still cancel an outstanding remainder.

Add `--lose-entry-response` in a **new** workspace to discard the actual successful entry response deliberately. The expected path is an uncertain submission, strategy pause, exact client-ID recovery by native reads, fill reconciliation and no second buy. This is controlled response-loss injection around a real order, not a claim that a genuine network outage occurred. Do not delete retained state or start another check before inspecting any unresolved orders.

Sanitized outcomes are retained in `acceptance.json`; encrypted credentials and the order/fill ledger remain beside it. Protect the directory like the main workspace. The main workspace's flags, orders, agents and messaging configuration are not copied or changed. Partial fills, cancellation races, true connectivity failures, resets, third-currency fees and broader authenticated venue acceptance remain pending. See [Binance's Testnet environment and restrictions](https://github.com/binance/binance-spot-api-docs/blob/master/testnet/general-info.md).


## October 28 balance-check observations

The strict native balance reader and the checkpoint/compare HTTP routes were exercised against the saved dedicated Binance Spot Testnet account in a new isolated encrypted workspace. Two native account balance GETs completed, including Unicode asset identifiers. The saved-report GET made no additional provider request. The transport rejected every non-GET method and every production destination; zero exchange orders were created and both execution flags were disabled.

The isolated workspace deliberately had no history imports configured, so its comparison correctly reported missing evidence rather than claiming that balances were reconciled. This verifies the authenticated read and local report lifecycle, not full history coverage, production account acceptance or a complete ledger match. Provider update timestamps are retained as hints rather than treated as the time of the balance read. See [balance-check semantics](balance-checks.md).

## Recent funding sync — October 28, 2026

A single authenticated Binance production deposit-history pass over a 24-hour creation-time window completed in an isolated local workspace. The transport allowed only GET requests to Binance deposit history and server time; exactly one deposit-history request was made, with no writes. Pagination was exhausted for that window. Controls were disabled after the check, and the main workspace was not reconfigured. The local summary is `.sibyl/acceptance/recent-funding-20261028T091020Z/acceptance.json`; credentials and native financial records were not printed. This verifies that bounded read, not live correction transitions or complete funding history. Kraken/Bybit authenticated rolling reads and native correction scenarios remain unverified.

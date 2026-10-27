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

Partial fills, late fee corrections, cancellation/fill races, induced lost network responses, production order execution, full imports and automated strategy behavior were **not** accepted by this run. Deterministic tests cover application contracts for many of those cases; they remain separate from live venue acceptance.

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

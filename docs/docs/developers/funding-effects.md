# Funding balance effects

`accounting/funding/` keeps arithmetic (`rules.py`) separate from local review persistence (`reviews.py`). Provider observations in `funding_events` remain unchanged. Funding history attaches `balance_effect` at read time; Balance checks freezes the same derived evidence inside each observation and retains immutable reports.

## Provider rules

Kraken's posted ledger defines the balance change as **signed amount minus same-asset fee**, including signed rebates and fee-only entries. This follows [Kraken's ledger-field definition](https://support.kraken.com/articles/360001169383-how-to-interpret-ledger-history-fields). The adapter reads the authenticated default wallet and preserves distinct normalized asset codes. Unknown fees, mismatched fee assets or unknown wallet scope cannot use this rule.

Binance's [capital history](https://developers.binance.com/en/docs/catalog/core-trading-wallet/api/rest-api/capital) reports amount and transaction fee separately. Sibyl does not infer fee inclusion from example amounts. `walletType=0` identifies the configured Spot scope; `1` identifies Funding, outside that scope. Missing, unknown or malformed wallet types remain unknown. `completeTime` is retained as `posted_ms`, distinct from creation/application time. Older records without completion time cannot be placed in a balance-check interval.

Bybit withdrawal history does not retain the initiating `feeType` or establish the wallet effect on Sibyl's UNIFIED balance. It remains unresolved without local review. This batch does not add Bybit wallet transfers or infer completion time from last-update time.

Completed, explicitly zero-fee movements in a known configured wallet use their signed amount. Known outside-wallet records have zero effect on the configured wallet. Failed/cancelled records are not applied; pending/restricted/unknown records remain unresolved. These are quantity effects, not settlement verification or proof of complete history.

## Local review

In **Trade → Account history → Funding**, select **Review balance effect**. For eligible records the user verifies wallet scope, the amount convention and an evidence note. Outgoing amounts can represent total debit or principal with an additional fee. Incoming amounts can represent net credit or gross receipt before the fee. Missing same-asset fees require an explicit assertion, including zero if verified.

A decision cannot override known provider wallet/fee facts, cross-asset fees, negative fees or Kraken's documented rule. A gross/inclusive amount cannot be smaller than its included fee. Unsupported cases remain unresolved. Choosing outside scope does not assert a fee convention.

`funding_reviews` is append-only. Each decision binds a SHA-256 version of material normalized source facts and the exact prior review ID. Source changes invalidate an old decision; display-label changes do not. Concurrent or stale saves receive HTTP 409. Withdrawal appends an audit action; nothing rewrites the native record. The newest twenty decisions are displayed; older audit decisions stay stored.

A funding review does **not** confirm an own-account transfer, allocate acquisition lots, supply cost basis, change FIFO performance or establish an external cash flow. Those workflows retain their separate reviews.

## Balance checks and agents

Balance checks use `posted_ms` for funding interval boundaries, not creation time. Missing timing stays unresolved even if the amount convention is reviewed. Rescan old imports to retrieve newly normalized wallet/completion fields. A review/source change to activity already in a checkpoint leaves affected quantities unresolved; review it and capture a fresh starting point. Old reports remain historical evidence.

Calculation version 2 retains up to 100 attempted funding-effect observations plus counts by provenance. The Account UI labels applied local reviews separately. Funding table CSV includes effect, rule, wallet scope, review status and posting time. Completed movement/fee summaries continue to summarize original reported quantities, not the derived effects.

Accountant's ordinary ProtoLink tools read these effects and their provenance. They cannot create/withdraw reviews or move funds. User notes, credentials, addresses and raw provider payloads are not part of derived tool evidence.

## API

All paths below are relative to `/api/v1/account-ledger/funding`. They use existing workspace authentication and local-origin protections and return `Cache-Control: no-store`. No route contacts an exchange.

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/{event_id}/review` | Original normalized source, current effect and twenty audit decisions |
| POST | `/{event_id}/review` | Version-checked local assertion |
| POST | `/{event_id}/review/withdraw` | Version-checked withdrawal of a local assertion |

Saving requires `source_version`, `replace_id` (null initially), `wallet_scope`, `amount_convention` (null outside scope), optional `fee_quantity` and an evidence `note`. Withdrawal requires only the two version fields. Decimal fee assertions are stored as strings; existing normalized provider quantities remain finite JSON numbers.

Offline tests cover rules, rebates, fee-only entries, wallet mapping, explicit missing-fee assertions, contradiction rejection, source corrections, concurrent saves, withdrawal, audit retention, posting-time boundaries and read-only API behavior. Authenticated Kraken/Bybit funding acceptance remains pending; these tests do not establish live provider acceptance.

# Bitcoin explorer contracts

`blockchain/` owns read-only Bitcoin research. `identifiers.py` checks Base58Check and BIP 173/350 mainnet addresses and full hashes before any HTTP read; `normalize.py` validates observations and derives amounts; `bitcoin.py` owns fixed-origin bounded GET requests; `demo.py` supplies explicit synthetic fixtures. `Research.bitcoin` shares this service between FastAPI and the native Explorer agent. There are no new dependencies or chain workers.

## HTTP API

All paths below are relative to `/api/v1`. Existing workspace authorization and origin checks apply. Successful responses and sanitized provider errors use `Cache-Control: no-store`.

| Method | Path | Request / response |
| --- | --- | --- |
| GET | `/bitcoin` | Scope and Demo references; no provider access |
| POST | `/bitcoin/inspect` | `kind` (`transaction` or `address`), `value`, optional `demo`, `input_offset`, `output_offset` |
| POST | `/bitcoin/history` | `address`, optional confirmed `cursor`, `pending`, `demo` |

POST avoids identifier-bearing local access-log URLs. Only validated references become paths under fixed `https://mempool.space/api`. Clients cannot supply a destination URL, headers or credentials. The transport issues GET only, does not follow redirects, limits each decompressed response to 8 MiB and releases its per-operation HTTP client. Timeouts are finite, there are at most two concurrent lookup operations, and failures are not retried or replaced with Demo. HTTP 429 propagates with an explicit wait indication; provider bodies are never forwarded.

Transactions read exact detail and a separate tip height. Address inspection reads summary, tip and one confirmed page. Further history calls read one page and tip. Tip failures may retain the primary observation with unknown depth; rate limits halt the operation. Pages contain at most 25 confirmed or 50 pending rows. Duplicate IDs, repeated cursors, unrelated rows and mismatched statuses fail visibly. The UI retains at most 200 confirmed rows; the API remains page-oriented.

## Normalization

- Only JSON integer counts/amounts are accepted, excluding booleans and floats. Per-transaction values/totals stay within Bitcoin's maximum-money bound. Missing previous outputs remain explicitly unknown. Available input minus output totals must equal the reported fee; duplicate input outpoints and malformed coinbase combinations fail.
- Virtual size is `ceil(weight / 4)`. The reported fee rate is transaction fee / virtual size. No fee recommendation or confirmation-time estimate is inferred.
- Confirmed depth is tip − inclusion height + 1 only for consistent observations. Confirmed inclusion with a missing/behind tip has null depth, while an unconfirmed transaction has zero.
- Confirmed address balance is indexed funded minus spent satoshis; pending delta is calculated independently. Projected totals outside the monetary bound remain unavailable. Lifetime sums use decimal satoshi strings at the JSON boundary to preserve large integer turnover; ordinary transaction amounts remain exact safe integers.
- Full transaction evidence is checked before paging the twenty returned inputs/outputs. At most 10,000 inputs and outputs are supported, subject to the response-size bound. Raw scripts, witnesses, raw transactions and provider extension fields are omitted.
- Address-level activity does not infer identity, wallet ownership or payment recipients. Net change is unknown if missing previous outputs could affect it. History pages and summary/tip reads are separate provider observations, not a reorg-proof snapshot.

The service does not persist normal lookups, import them into account accounting, aggregate wallet addresses or expose broadcast/signing methods. JSON export is an explicit browser action. Native agent conversations/reports retain their evidence under existing application rules.

## Native ProtoLink tools

Explorer declares ordinary typed `bitcoin_lookup`, `bitcoin_address_history`, `bitcoin_blocks`, `blockchain_help` and `page_help` tools. The first tool reads private page references or explicit user/evidence IDs; with no selection it retains the recent-block snapshot behavior. Validated `bitcoin_txid`, `bitcoin_address` and `bitcoin_demo` page context reaches local consultations through existing ProtoLink request context. Specialists still cannot delegate or mutate state.

`bitcoin_lookup` supports input/output offsets; `bitcoin_address_history` accepts the returned confirmed cursor or a separate pending flag. Model-facing docstrings explain purpose, units and limits. The app adds no custom agent routing, execution wrappers or LLM orchestration.

## Tests and limitations

Tests exercise published witness checksum vectors, early rejection, exact amounts/fees, pagination, pending/coinbase/missing-prevout behavior, tip failure, malformed/mismatched provider observations, bounded responses/admission, sanitized rate limits, independent Demo and native ProtoLink context/evidence.

An October 29, 2026 public acceptance pass read the known genesis transaction and address through five allowlisted, credential-free mempool.space GETs. The transaction normalized as coinbase with 5,000,000,000 output satoshis and zero fee; the address returned indexed totals and a 25-row confirmed page. There were no private requests or broadcasts. This verifies the observed integration, not spendability, independent chain verification or complete historical coverage. Browser acceptance also exercised Demo transaction/address lookup, 25→29-row pagination, separate pending observations and native Ask Explorer evidence.

Read semantics follow [Esplora](https://github.com/Blockstream/esplora/blob/master/API.md) and [mempool.space](https://mempool.space/docs/api/rest); witness validation follows [BIP 173](https://github.com/bitcoin/bips/blob/master/bip-0173.mediawiki) and [BIP 350](https://github.com/bitcoin/bips/blob/master/bip-0350.mediawiki). The backend trusts this public indexer and does not independently verify proofs, follow an atomic chain snapshot or reconcile reorgs over retained history. Additional providers/networks, wallet aggregation, output-spend tracking and historical datasets remain pending.

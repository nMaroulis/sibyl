# Bitcoin explorer contracts

`blockchain/` owns read-only Bitcoin research. `identifiers.py` checks Base58Check and BIP 173/350 mainnet addresses and full hashes before any HTTP read; `normalize.py` validates observations and derives amounts; `bitcoin.py` owns fixed-origin bounded GET requests; `demo.py` supplies explicit synthetic fixtures. `Research.bitcoin` shares this service between FastAPI and the native Explorer agent. There are no new dependencies or chain workers.

## HTTP API

All paths below are relative to `/api/v1`. Existing workspace authorization and origin checks apply. Successful responses and sanitized provider errors use `Cache-Control: no-store`.

| Method | Path | Request / response |
| --- | --- | --- |
| GET | `/bitcoin` | Scope and Demo references; no provider access |
| POST | `/bitcoin/inspect` | `kind` (`transaction` or `address`), `value`, optional `demo`, `input_offset`, `output_offset` |
| POST | `/bitcoin/output-spends` | `transaction_id`, optional `output_offset`, `demo`; current twenty-output spending observation |
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

## Output-spend observations

`BitcoinExplorer.output_spends` validates the exact parent through the existing transaction normalizer, reads `GET /tx/:txid/outspends`, then a separate tip height. It requires the full array length to match the validated parent output count; every row is validated before paging, including off-page rows. There are three bounded GETs per page, rather than one request per output. Existing two-operation admission, fixed-origin GET-only transport, response-size limits and error sanitization apply. Invalid output offsets are rejected before the spend read.

`blockchain/spends.py` requires a real boolean `spent`, strict nonnegative spending input indexes, valid hashes and valid confirmation evidence. A self-referencing spend or an unspent row carrying spend details fails explicitly. Missing spender/status details remain `unknown`; they are never classified as pending or unspent. This is an indexer observation, not proof that the spending input actually consumes this outpoint or that an unspent output can be spent. Standalone output-spend checks never create a watch.

The UI isolates each transaction/output-page/source selection, aborts checks on unmount, keeps failed-refresh observations dated and exports spend checks separately. Demo derives spends by walking its existing transaction inputs, preserving actual graph links between the synthetic confirmed, pending and unspent examples.

## Durable output watches

`GET /api/v1/bitcoin/watches` lists local evidence. `POST /api/v1/bitcoin/watches` enables one exact transaction output and source, idempotent for the same reference. `POST /api/v1/bitcoin/watches/{watch_id}` accepts revision-checked `pause`, `resume` or `remove`. Request bodies hold public transaction identifiers. Control URLs use opaque local watch IDs. The separate Demo source needs no provider.

`blockchain/watches.py` registers at most 25 saved watches, normalizes one due read per supervised worker iteration, and uses the same public output-spends adapter with parent and spender inclusion evidence. Successful polls are scheduled at least 120 seconds apart per watch. Incomplete results back off up to 30 minutes. A rate-limit response delays mainnet reads across watches within the process. SQLite fences results against pause, resume and removal, and commits a changed checkpoint and its before/after inbox evidence together. Inbox export accepts `kind=bitcoin`. Notices stay local.

Ordinary restart retains the checkpoint. Backup recovery pauses restored watches and preserves their evidence. Explicit resume is available after recovery. Observations are sampled indexer reads. The system cannot reconstruct branches, detect every transient change or verify chain consensus locally.

## Native ProtoLink tools

Explorer declares ordinary typed `bitcoin_lookup`, `bitcoin_address_history`, `bitcoin_output_spends`, `bitcoin_blocks`, `blockchain_help` and `page_help` tools. The first tool reads private page references or explicit user/evidence IDs; with no selection it retains the recent-block snapshot behavior. Validated `bitcoin_txid`, `bitcoin_address` and `bitcoin_demo` page context reaches local consultations through existing ProtoLink request context. Specialists still cannot delegate or mutate state.

`bitcoin_output_spends` reads the selected transaction/output page from private `bitcoin_output_offset` context, or explicit validated references/offsets. It returns attributed states and spending links through the existing native client/runtime.

`bitcoin_lookup` supports input/output offsets; `bitcoin_address_history` accepts the returned confirmed cursor or a separate pending flag. Model-facing docstrings explain purpose, units and limits. The app adds no custom agent routing, execution wrappers or LLM orchestration.

## Tests and limitations

Tests exercise published witness checksum vectors, early rejection, exact amounts/fees, pagination, pending/coinbase/missing-prevout behavior, tip failure, malformed/mismatched provider observations, bounded responses/admission, sanitized rate limits, independent Demo and native ProtoLink context/evidence.

An October 29, 2026 public acceptance pass read the known genesis transaction and address through five allowlisted, credential-free mempool.space GETs. The transaction normalized as coinbase with 5,000,000,000 output satoshis and zero fee; the address returned indexed totals and a 25-row confirmed page. There were no private requests or broadcasts. This verifies the observed integration, not spendability, independent chain verification or complete historical coverage. Browser acceptance also exercised Demo transaction/address lookup, 25→29-row pagination, separate pending observations and native Ask Explorer evidence.

A November 5, 2026 output-spend acceptance pass made three credential-free mempool.space GETs for the public genesis transaction: parent detail, bulk output spends and tip height. The single 5,000,000,000-satoshi output returned `unspent`. This records the indexer's observation; it does not establish spendability. Isolated browser acceptance covered synthetic confirmed/pending/unspent checks, spending-transaction navigation, separate JSON export, failed-refresh labeling and mobile layout.

Read semantics follow [Esplora](https://github.com/Blockstream/esplora/blob/master/API.md) and [mempool.space](https://mempool.space/docs/api/rest); witness validation follows [BIP 173](https://github.com/bitcoin/bips/blob/master/bip-0173.mediawiki) and [BIP 350](https://github.com/bitcoin/bips/blob/master/bip-0350.mediawiki). The backend trusts this public indexer and does not independently verify proofs, follow an atomic chain snapshot or reconcile reorgs over retained history. Additional providers/networks, wallet aggregation and historical datasets remain pending.

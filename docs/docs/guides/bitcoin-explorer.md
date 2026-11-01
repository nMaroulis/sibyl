# Bitcoin transactions and addresses

Open **Research → Block explorer** to inspect a Bitcoin mainnet transaction ID or address. Paste the full reference and choose **Inspect**. You do not need an exchange connection, API key or language model. Existing recent-block charts remain below the lookup.

Public requests go from Sibyl's Python backend to **mempool.space**. The entered reference is visible to that public indexer. The lookup accepts public transaction hashes and checksummed mainnet addresses; it never needs a private key, seed phrase or exchange credentials. URLs and other networks are rejected before a request is sent.

## Inspect a transaction

The report shows:

- Inclusion status and observed confirmation depth, with block height and time when available.
- The fee in satoshis and **sat/vB**, using `ceil(weight / 4)` virtual bytes.
- Input and output counts, exact output totals, and available previous-output values.
- Twenty inputs and outputs per view, with next/previous page controls for larger transactions.
- Address links that open another lookup in place. Non-address scripts stay labeled as such.

One BTC is 100,000,000 satoshis. Input/output values are not rounded to cents. Cumulative address turnover is exported as decimal satoshi strings where necessary to preserve integers above JavaScript's exact numeric range.

A transaction's total outputs can include change and self-transfers. It is not the amount paid to one person, income or profit. Coinbase transactions create coins and have no previous input value; they are explicitly labeled. If previous outputs are missing, the input total is unavailable rather than inferred.

The inclusion block is the first confirmation. Where the provider supplies a usable tip, depth is `tip height − inclusion height + 1`. If the tip is unavailable or behind the observed inclusion, the count stays unknown. These reads are separate observations and do not prove finality or independently verify the chain. Refresh to obtain another observation; changes and reorganizations remain possible.

## Inspect an address

Address reports separate **confirmed balance**, **pending change**, and the resulting projected balance. A negative pending change is expected when unconfirmed transactions spend the address's funds. Inconsistent projected balances stay unavailable. Expand **Address totals** for cumulative confirmed received/spent output values.

An address is not a complete wallet, proof of ownership or an identity. These totals do not establish holdings across other addresses or accounts. Indexed unspent output value is not verified spendable balance: coinbase maturity, genesis restrictions and script spending conditions are not evaluated.

The initial activity table contains at most 25 confirmed transactions. **Load older confirmed transactions** follows the source's cursor, up to 200 displayed rows. A separate **Pending** control reads up to 50 unconfirmed transactions without a history cursor. Reaching that limit is explicitly marked as potentially incomplete. Transaction links open their details in place.

Net change concerns the selected address only, including its received outputs and spent previous outputs. Missing previous-output evidence makes net change unavailable. The transaction's whole fee is shown separately; it is not attributed to the address as a standalone wallet expense. History pages are not one frozen snapshot. If duplicate rows appear between pages, refresh the lookup before continuing.

## Demo, export and Explorer

The small **Demo transaction** and **Demo address** links use synthetic backend fixtures through the same validation and calculation pipeline. They do not activate an account or change market/research settings. Every result is labeled **Demo** and has no external mainnet reference link. Live failures never substitute these examples.

**Export observation** downloads the report and the confirmed/pending activity loaded in the page. It does not export a complete address history. Normal lookups stay in page memory and are not automatically written to an address database, browser storage or bookmark URL. POST bodies keep references out of Sibyl's local route URLs; upstream indexers and deployment infrastructure can have their own logging policies.

**Ask Explorer** includes the selected reference and its Demo/mainnet boundary. Native ProtoLink tools read the same normalized observations; Sibyl can consult Explorer too. Asking the agent can fetch a newer observation. Agent questions and tool evidence follow the application's existing local conversation/report persistence. Agents cannot broadcast transactions or infer address owners.

Additional chains, wallet aggregation, output-spend tracking, local chain verification and complete historical chain datasets remain in the [planning checklist](../developers/backend-roadmap.md).

Source contracts: [mempool.space API](https://mempool.space/docs/api/rest), [Esplora API](https://github.com/Blockstream/esplora/blob/master/API.md), and Bitcoin's [Bech32](https://github.com/bitcoin/bips/blob/master/bip-0173.mediawiki)/[Bech32m](https://github.com/bitcoin/bips/blob/master/bip-0350.mediawiki) address specifications.

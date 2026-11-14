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

## Check output spending

In a transaction’s **Outputs** section, select **Check output spends**. Sibyl reads current indexer observations for that output page separately from the earlier transaction lookup. No background watch is started. **Refresh checks** explicitly reads a new snapshot; if refresh fails, the previous dated observation remains labeled as not refreshed.

- **No spend reported:** the indexer reports the output as unspent. Script restrictions, coinbase maturity, ownership and wallet funds are not verified.
- **Spend pending:** a spending transaction is observed but unconfirmed. It can disappear or be replaced.
- **Spent · confirmed:** the source reports an included spending transaction. Its confirmation depth can remain unavailable if the separate tip read fails or disagrees.
- **Spend details unknown:** a spend is reported but its identifying details or status are incomplete. A failed request never means unspent.

Follow the spending transaction hash to inspect it in place; the spending input number identifies the linked outpoint. Outputs remain paged in groups of twenty. **Export spends** downloads the exact checked page, source, timestamp and limits as a separate JSON observation. Ordinary transaction export does not silently merge observations made at different times.

The Demo spend examples open deterministic confirmed and pending parent outputs; their links follow the same synthetic transaction graph. No actual lookup or exchange connection is required.

## Watch an output

Choose **Watch** on a checked output to follow that exact transaction and output number. **Output watches** shows the source, the last reliable observation, and controls to inspect, pause, resume or remove it.

Mainnet watches periodically send the transaction hash to mempool.space while Sibyl is running. Demo watches use a fixed synthetic graph. The first successful check establishes the baseline. Later checks can add a notice to **Alerts → Inbox** when a spender appears, disappears or changes, or when the parent or same spender enters, leaves or moves between blocks. Expand **Observed change evidence** in the inbox to compare the two observations. A block move is indexer evidence of changed inclusion and can indicate a reorganization. Confirmation depth alone does not trigger a notice.

Each watch is checked no sooner than two minutes after its previous check. Queueing and retries can delay it. If a read is missing or incomplete, Sibyl keeps the last reliable observation and displays the retry state. After restart or resume, it compares with that last observation. Changes that happen and reverse between checks may go unseen. Removing a watch stops future checks and keeps previously recorded inbox notices.

## Demo, export and Explorer

The small **Demo transaction** and **Demo address** links use synthetic backend fixtures through the same validation and calculation pipeline. They do not activate an account or change market/research settings. Every result is labeled **Demo** and has no external mainnet reference link. Live failures never substitute these examples.

**Export observation** downloads the report and the confirmed/pending activity loaded in the page. It does not export a complete address history. Normal lookups stay in page memory and are not automatically written to an address database, browser storage or bookmark URL. POST bodies keep references out of Sibyl's local route URLs; upstream indexers and deployment infrastructure can have their own logging policies.

**Ask Explorer** includes the selected reference and its Demo/mainnet boundary. Native ProtoLink tools read the same normalized observations; Sibyl can consult Explorer too. Asking the agent can fetch a newer observation. Agent questions and tool evidence follow the application's existing local conversation/report persistence. Agents cannot broadcast transactions or infer address owners.

Additional chains, wallet aggregation, local chain verification and complete historical chain datasets remain in the [planning checklist](../developers/backend-roadmap.md).

Source contracts: [mempool.space API](https://mempool.space/docs/api/rest), [Esplora API](https://github.com/Blockstream/esplora/blob/master/API.md), and Bitcoin's [Bech32](https://github.com/bitcoin/bips/blob/master/bip-0173.mediawiki)/[Bech32m](https://github.com/bitcoin/bips/blob/master/bip-0350.mediawiki) address specifications.

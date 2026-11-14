import { useRef, useState } from 'react';
import { ArrowLeft, ArrowRight, Download, ExternalLink, Search } from 'lucide-react';
import { number, post } from '../lib/api';
import type { BitcoinBlockReport } from '../lib/bitcoin-types';
import { AgentButton } from './agents';
import { Badge, Loading, Panel, PanelTitle } from './ui';

type BlockRequest = { height?: number; block_hash?: string; offset?: number; demo?: boolean };

export function BitcoinBlockInspector({
  demoHeight,
  inspectTransaction,
}: {
  demoHeight?: number;
  inspectTransaction: (id: string, demo: boolean) => void;
}) {
  const [draft, setDraft] = useState('');
  const [result, setResult] = useState<BitcoinBlockReport>();
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const active = useRef(false);
  const read = async (request: BlockRequest) => {
    if (active.current) return;
    active.current = true;
    setBusy(true);
    setError('');
    try {
      setResult(await post<BitcoinBlockReport>('/bitcoin/block', request));
    } catch (reason) {
      setError((reason as Error).message);
    } finally {
      active.current = false;
      setBusy(false);
    }
  };
  const block = result?.block;
  const demo = result?.source === 'demo';
  const page = (offset: number) => void read({ block_hash: block!.id, offset, demo });
  const exportPage = () => {
    const url = URL.createObjectURL(
      new Blob([JSON.stringify(result, null, 2)], { type: 'application/json' }),
    );
    const link = document.createElement('a');
    link.href = url;
    link.download = `sibyl-bitcoin-block-${block!.height}.json`;
    link.click();
    URL.revokeObjectURL(url);
  };
  const chain = result?.in_best_chain;
  return (
    <Panel className="bitcoin-inspector">
      <PanelTitle
        title="Historical block lookup"
        subtitle="Find a Bitcoin block and inspect its transactions."
        action={
          result && (
            <AgentButton
              compact
              module="explorer"
              context={{
                bitcoin_block_hash: result.block.id,
                bitcoin_block_offset: result.transaction_offset,
                bitcoin_demo: demo,
              }}
            />
          )
        }
      />
      <div className="bitcoin-content">
        <form
          className="bitcoin-search"
          onSubmit={(event) => {
            event.preventDefault();
            const value = draft.trim();
            if (/^[a-f0-9]{64}$/i.test(value)) void read({ block_hash: value });
            else if (/^[0-9]{1,9}$/.test(value) && Number(value) <= 100_000_000)
              void read({ height: Number(value) });
            else setError('Enter a block height or a 64-character hexadecimal block hash.');
          }}
        >
          <label htmlFor="bitcoin-block-reference">Block height or hash</label>
          <div>
            <Search size={16} aria-hidden="true" />
            <input
              id="bitcoin-block-reference"
              value={draft}
              maxLength={64}
              autoComplete="off"
              spellCheck={false}
              placeholder="e.g. 840000"
              onChange={(event) => setDraft(event.target.value)}
            />
            <button className="button primary" disabled={busy || !draft.trim()}>
              Find block
            </button>
          </div>
        </form>
        {demoHeight != null && (
          <p className="bitcoin-demo-links">
            <button
              className="text-button"
              disabled={busy}
              onClick={() => void read({ height: demoHeight, demo: true })}
            >
              Demo block
            </button>
          </p>
        )}
        {busy && <Loading />}
        {error && (
          <p className="form-error" role="alert">
            {error}
            {result && ' Showing the previous observation.'}
          </p>
        )}
        {result && block && (
          <section className="bitcoin-result" aria-label="Bitcoin block details" aria-busy={busy}>
            <div className="bitcoin-result-toolbar">
              <Badge tone={demo ? 'amber' : 'blue'}>
                {demo ? 'Demo · synthetic' : 'Bitcoin mainnet'}
              </Badge>
              <Badge tone={chain === true ? 'green' : 'amber'}>
                {chain === true
                  ? 'Best chain'
                  : chain === false
                    ? 'Outside the best chain'
                    : 'Chain status unavailable'}
              </Badge>
              <span>
                {result.source} · {new Date(result.observed_at).toLocaleString()}
              </span>
              <button className="text-button" disabled={busy} onClick={exportPage}>
                <Download size={13} /> Export block page
              </button>
              {result.url && (
                <a className="text-link" href={result.url} target="_blank" rel="noreferrer">
                  <ExternalLink size={12} /> mempool.space
                </a>
              )}
            </div>
            <code className="bitcoin-result-id">{block.id}</code>
            <div className="extended-metrics">
              <div>
                <small>Height</small>
                <strong>#{number(block.height, 0)}</strong>
              </div>
              <div>
                <small>Transactions</small>
                <strong>{number(block.tx_count, 0)}</strong>
              </div>
              <div>
                <small>Size / weight</small>
                <strong>{number(block.size, 0)} B</strong>
                <small>{number(block.weight, 0)} WU</small>
              </div>
            </div>
            <p className="footnote">
              Block time {new Date(block.timestamp * 1000).toLocaleString()}
              {block.parent_hash && !demo && (
                <>
                  {' '}
                  ·{' '}
                  <button
                    className="text-button"
                    disabled={busy}
                    onClick={() => void read({ block_hash: block.parent_hash! })}
                  >
                    Open parent block
                  </button>
                </>
              )}
            </p>
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>Index</th>
                    <th>Transaction</th>
                    <th>Inputs / outputs</th>
                    <th>Fee</th>
                  </tr>
                </thead>
                <tbody>
                  {result.items.map((item) => (
                    <tr key={item.txid}>
                      <td>{number(item.index, 0)}</td>
                      <td>
                        <button
                          className="bitcoin-reference text-button"
                          title={item.txid}
                          disabled={busy}
                          onClick={() => inspectTransaction(item.txid, demo)}
                        >
                          {item.txid.slice(0, 12)}…{item.txid.slice(-8)}
                        </button>
                        {item.coinbase && <small> Coinbase</small>}
                      </td>
                      <td>
                        {item.input_count} / {item.output_count}
                      </td>
                      <td>{number(item.fee_sats, 0)} sat</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="bitcoin-result-toolbar">
              <button
                className="text-button"
                disabled={busy || !result.transaction_offset}
                onClick={() => page(result.transaction_offset - 25)}
              >
                <ArrowLeft size={13} /> Previous transactions
              </button>
              <span>
                {result.transaction_offset + 1}–{result.transaction_offset + result.items.length} of{' '}
                {number(block.tx_count, 0)}
              </span>
              <button
                className="text-button"
                disabled={busy || result.next_offset == null}
                onClick={() => page(result.next_offset!)}
              >
                Next transactions <ArrowRight size={13} />
              </button>
            </div>
            <p className="bitcoin-method-note">{result.note}</p>
          </section>
        )}
      </div>
    </Panel>
  );
}

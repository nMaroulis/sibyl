import { useState } from 'react';
import { useResource } from '../lib/hooks';
import { AgentButton } from './agents';
import { Badge, ErrorState, Loading, Panel, PanelTitle } from './ui';

const PAGE = 25;
type Block = {
  source: string;
  height: number;
  block_hash: string;
  timestamp: string;
  gas_used: string;
  reported_finalized_head: boolean;
  transaction_count: number;
  transactions: string[];
};
type Transaction = {
  hash: string;
  from: string;
  to: string | null;
  value_wei: string;
  execution_gas_cost_wei: string | null;
  block_number: number | null;
  block_hash: string | null;
  execution_status: string;
};

/** Read exact public Ethereum block and receipt observations on explicit lookup. */
export function EthereumInspector() {
  const [type, setType] = useState<'blocks' | 'transactions'>('blocks');
  const [draft, setDraft] = useState('');
  const [block, setBlock] = useState('');
  const [offset, setOffset] = useState(0);
  const [transaction, setTransaction] = useState('');
  const blocks = useResource<Block>(
    `/ethereum/blocks/${encodeURIComponent(block)}?offset=${offset}`,
    0,
    !!block,
  );
  const transactions = useResource<Transaction>(
    `/ethereum/transactions/${encodeURIComponent(transaction)}`,
    0,
    !!transaction,
  );
  const row = blocks.data;
  const tx = transactions.data;
  const loadBlock = (reference: string) => {
    if (reference === block && !offset) blocks.retry();
    else {
      setOffset(0);
      setBlock(reference);
    }
  };
  const loadTransaction = (reference: string) => {
    if (reference === transaction) transactions.retry();
    else setTransaction(reference);
  };
  return (
    <Panel>
      <PanelTitle
        title="Ethereum mainnet"
        subtitle="Blocks and transaction receipts"
        action={<AgentButton module="explorer" compact />}
      />
      <form
        className="stock-search"
        onSubmit={(event) => {
          event.preventDefault();
          if (!draft.trim()) return;
          if (type === 'blocks') loadBlock(draft.trim());
          else loadTransaction(draft.trim());
        }}
      >
        <select
          aria-label="Ethereum lookup type"
          value={type}
          onChange={(event) => setType(event.target.value as typeof type)}
        >
          <option value="blocks">Block</option>
          <option value="transactions">Transaction</option>
        </select>
        <input
          value={draft}
          maxLength={66}
          aria-label="Ethereum lookup reference"
          placeholder={type === 'blocks' ? 'Block height or hash' : 'Transaction hash'}
          onChange={(event) => setDraft(event.target.value)}
        />
        <button className="button primary" type="submit" disabled={!draft.trim()}>
          Inspect
        </button>
        <button className="button secondary" type="button" onClick={() => loadBlock('finalized')}>
          Finalized head
        </button>
      </form>
      <p className="padded footnote">
        PublicNode supplies Ethereum mainnet observations. Receipt status and reported finality come
        from the RPC.
      </p>
      {block &&
        (blocks.error ? (
          <ErrorState message={blocks.error} retry={blocks.retry} />
        ) : blocks.loading ? (
          <Loading />
        ) : (
          row && (
            <>
              <div className="padded">
                <h3>Block {row.height}</h3>
                <div className="filter-pills">
                  {row.reported_finalized_head && <Badge>RPC-reported finalized head</Badge>}
                  <Badge>{new Date(row.timestamp).toLocaleString()}</Badge>
                  <Badge>{row.gas_used} gas used</Badge>
                </div>
                <p>
                  <code>{row.block_hash}</code>
                </p>
              </div>
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>Transaction hash</th>
                      <th />
                    </tr>
                  </thead>
                  <tbody>
                    {row.transactions.map((hash) => (
                      <tr key={hash}>
                        <td>
                          <code>{hash}</code>
                        </td>
                        <td>
                          <button className="text-link" onClick={() => loadTransaction(hash)}>
                            Read receipt
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <div className="filter-pills">
                <button
                  type="button"
                  disabled={offset === 0}
                  onClick={() => {
                    setBlock(row.block_hash);
                    setOffset(offset - PAGE);
                  }}
                >
                  Previous
                </button>
                <span>
                  {row.transaction_count ? offset + 1 : 0}–{offset + row.transactions.length} of{' '}
                  {row.transaction_count}
                </span>
                <button
                  type="button"
                  disabled={offset + PAGE >= row.transaction_count}
                  onClick={() => {
                    setBlock(row.block_hash);
                    setOffset(offset + PAGE);
                  }}
                >
                  Next
                </button>
              </div>
            </>
          )
        ))}
      {transaction &&
        (transactions.error ? (
          <ErrorState message={transactions.error} retry={transactions.retry} />
        ) : transactions.loading ? (
          <Loading />
        ) : (
          tx && (
            <div className="padded">
              <h3>Transaction receipt</h3>
              <p>
                <code>{tx.hash}</code>
              </p>
              <div className="filter-pills">
                <Badge>{tx.execution_status.replaceAll('_', ' ')}</Badge>
                {tx.block_hash && (
                  <button className="text-link" onClick={() => loadBlock(tx.block_hash!)}>
                    Open block {tx.block_number}
                  </button>
                )}
              </div>
              <p>
                From <code>{tx.from}</code> to <code>{tx.to ?? 'contract creation'}</code>
              </p>
              <p>
                Value <strong>{tx.value_wei} wei</strong>
              </p>
              {tx.execution_gas_cost_wei != null && (
                <p>
                  Execution gas cost <strong>{tx.execution_gas_cost_wei} wei</strong>. Separate blob
                  fees are excluded.
                </p>
              )}
            </div>
          )
        ))}
    </Panel>
  );
}

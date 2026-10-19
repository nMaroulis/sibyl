import { useState } from 'react';
import { RefreshCw } from 'lucide-react';
import { DataNote, ErrorState, Loading, Panel, PanelTitle } from './ui';
import { number } from '../lib/api';
import { useResource } from '../lib/hooks';
import type { Source } from '../lib/types';

type Book = Source & { symbol: string; bids: number[][]; asks: number[][]; spread: number | null };
export function OrderBook({ symbol }: { symbol: string }) {
  const [depth, setDepth] = useState(10);
  const [poll, setPoll] = useState(false);
  const book = useResource<Book>(
    `/markets/orderbook?symbol=${encodeURIComponent(symbol)}&depth=${depth}`,
    poll ? 10000 : 0,
  );
  const rows = Array.from(
    { length: Math.max(book.data?.bids.length ?? 0, book.data?.asks.length ?? 0) },
    (_, i) => ({ bid: book.data?.bids[i], ask: book.data?.asks[i] }),
  );
  const max = Math.max(1, ...rows.flatMap((row) => [row.bid?.[1] ?? 0, row.ask?.[1] ?? 0]));
  return (
    <Panel className="full-panel">
      <PanelTitle
        title="Order book"
        subtitle={`${symbol} · public snapshot, no execution`}
        action={
          <button className="button secondary tiny" onClick={book.retry}>
            <RefreshCw size={13} /> Refresh
          </button>
        }
      />
      <div className="workspace-controls">
        <label>
          Depth
          <select value={depth} onChange={(e) => setDepth(Number(e.target.value))}>
            {[5, 10, 25, 50].map((n) => (
              <option key={n} value={n}>
                {n} levels
              </option>
            ))}
          </select>
        </label>
        <label className="inline-check">
          <input type="checkbox" checked={poll} onChange={(e) => setPoll(e.target.checked)} />{' '}
          Refresh every 10 seconds
        </label>
        <span className="muted">
          Spread {book.data?.spread == null ? '—' : number(book.data.spread, 8)}{' '}
          {symbol.split('/')[1]}
        </span>
      </div>
      {book.loading ? (
        <Loading />
      ) : book.error ? (
        <ErrorState message={book.error} retry={book.retry} />
      ) : (
        <>
          <div className="table-scroll">
            <table className="book-table">
              <thead>
                <tr>
                  <th>Bid size</th>
                  <th>Bid price</th>
                  <th>Ask price</th>
                  <th>Ask size</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row, i) => (
                  <tr key={i}>
                    <td
                      style={{
                        background: `linear-gradient(to left, #edf6f1 ${((row.bid?.[1] ?? 0) / max) * 100}%, transparent 0)`,
                      }}
                    >
                      {row.bid ? number(row.bid[1], 6) : '—'}
                    </td>
                    <td className="positive">{row.bid ? number(row.bid[0], 8) : '—'}</td>
                    <td className="negative">{row.ask ? number(row.ask[0], 8) : '—'}</td>
                    <td
                      style={{
                        background: `linear-gradient(to right, #fbf0f1 ${((row.ask?.[1] ?? 0) / max) * 100}%, transparent 0)`,
                      }}
                    >
                      {row.ask ? number(row.ask[1], 6) : '—'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="chart-footnote">
            <DataNote source={book.data?.source} />
            <span>
              {book.data?.source === 'demo'
                ? 'Synthetic levels for demonstration'
                : `Observed ${new Date(book.data?.as_of ?? '').toLocaleTimeString()}`}
            </span>
          </div>
        </>
      )}
    </Panel>
  );
}

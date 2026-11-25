import { useEffect, useState } from 'react';
import { RefreshCw } from 'lucide-react';
import { Badge, DataNote, Empty, ErrorState, Loading, Panel, PanelTitle } from './ui';
import { getStream, number } from '../lib/api';
import { useResource } from '../lib/hooks';
import type { Source } from '../lib/types';

type Book = Source & {
  symbol: string;
  bids: number[][];
  asks: number[][];
  spread: number | null;
  stream_available?: boolean;
};
type BookEvent = (Book & { type: 'book' }) | { type: 'status'; state: string };
type UpdateMode = 'snapshot' | 'poll' | 'live';

/** Display the selected exchange's book or a clearly labeled, user-selected Binance comparison. */
export function OrderBook({
  symbol,
  source,
  sourceLabel,
  active = true,
}: {
  symbol: string;
  source?: string;
  sourceLabel?: string;
  active?: boolean;
}) {
  const [depth, setDepth] = useState(10);
  const [mode, setMode] = useState<UpdateMode>('snapshot');
  const [comparisonFor, setComparisonFor] = useState<string | null>(null);
  const accountSource = source ?? '';
  const comparison = comparisonFor === accountSource && source !== 'demo';
  const feed = comparison ? 'binance' : source;
  const bookSymbol = comparison ? symbol.split('/')[0] + '/USDT' : symbol;
  const [settledPair, setSettledPair] = useState(symbol);
  useEffect(() => {
    const timer = window.setTimeout(() => setSettledPair(symbol), 300);
    return () => window.clearTimeout(timer);
  }, [symbol]);
  const ready =
    active && !!feed && settledPair === symbol && /^[A-Z0-9]{1,12}\/[A-Z0-9]{1,12}$/.test(symbol);
  const query = new URLSearchParams({ symbol: bookSymbol, source: feed ?? '' }).toString();
  const [stream, setStream] = useState<{ query: string; state: string; book?: Book }>();
  const [attempt, setAttempt] = useState(0);
  const current = stream?.query === query ? stream : undefined;
  const snapshots = useResource<Book>(
    '/markets/orderbook?' + query + '&depth=50',
    mode === 'poll' || (mode === 'live' && current?.state !== 'live') ? 10000 : 0,
    ready,
  );
  const snapshot =
    ready && snapshots.data?.symbol === bookSymbol && snapshots.data.source === feed
      ? snapshots.data
      : undefined;
  const streaming = mode === 'live' && !!snapshot?.stream_available;
  useEffect(() => {
    if (!streaming) {
      setStream(undefined);
      return;
    }
    const controller = new AbortController();
    setStream({ query, state: 'connecting' });
    const update = (event: BookEvent) => {
      if (controller.signal.aborted) return;
      if (event.type === 'book') {
        if (event.symbol === bookSymbol && event.source === feed)
          setStream({ query, state: 'live', book: event });
      } else if (event.state !== 'live') {
        setStream({ query, state: event.state });
      }
    };
    void getStream<BookEvent>('/markets/orderbook/live?' + query, update, controller.signal)
      .catch(() => {})
      .finally(() => {
        if (!controller.signal.aborted) setStream({ query, state: 'unavailable' });
      });
    return () => controller.abort();
  }, [streaming, query, bookSymbol, feed, attempt]);
  const liveBook = streaming ? current?.book : undefined;
  const book = liveBook ?? snapshot;
  const refresh = () => {
    snapshots.retry();
    if (streaming) setAttempt((value) => value + 1);
  };
  const rows = Array.from(
    { length: Math.min(depth, Math.max(book?.bids.length ?? 0, book?.asks.length ?? 0)) },
    (_, i) => ({ bid: book?.bids[i], ask: book?.asks[i] }),
  );
  const max = Math.max(1, ...rows.flatMap((row) => [row.bid?.[1] ?? 0, row.ask?.[1] ?? 0]));
  return (
    <Panel className="full-panel">
      <PanelTitle
        title="Order book"
        subtitle={
          bookSymbol +
          ' · ' +
          (comparison ? 'Binance public spot' : (sourceLabel ?? 'Public spot depth'))
        }
        action={
          ready && (
            <button className="button secondary tiny" onClick={refresh}>
              <RefreshCw size={13} /> {streaming ? 'Reconnect' : 'Refresh'}
            </button>
          )
        }
      />
      <div className="workspace-controls orderbook-controls">
        {source !== 'demo' && (
          <label>
            Book source
            <select
              value={comparison ? 'binance' : 'account'}
              onChange={(event) =>
                setComparisonFor(event.target.value === 'binance' ? accountSource : null)
              }
            >
              <option value="account">{sourceLabel ?? 'Selected exchange account'}</option>
              <option value="binance">Binance · USDT comparison</option>
            </select>
          </label>
        )}
        <label>
          Updates
          <select
            disabled={!feed}
            value={mode === 'live' && !snapshot?.stream_available ? 'snapshot' : mode}
            onChange={(event) => setMode(event.target.value as UpdateMode)}
          >
            <option value="snapshot">Manual snapshot</option>
            <option value="poll">Every 10 seconds</option>
            <option value="live" disabled={!snapshot?.stream_available}>
              Live WebSocket
            </option>
          </select>
        </label>
        <label>
          Depth
          <select disabled={!feed} value={depth} onChange={(e) => setDepth(Number(e.target.value))}>
            {[5, 10, 25, 50].map((n) => (
              <option key={n} value={n}>
                {n} levels
              </option>
            ))}
          </select>
        </label>
        {streaming && (
          <Badge tone={liveBook ? 'blue' : 'sand'}>
            {liveBook
              ? 'Live WebSocket'
              : current?.state === 'unavailable'
                ? 'Live unavailable · snapshots'
                : 'Waiting for live depth · snapshots'}
          </Badge>
        )}
        <span className="muted">
          Spread {book?.spread == null ? '—' : number(book.spread, 8)} {bookSymbol.split('/')[1]}
        </span>
      </div>
      {comparison ? (
        <p className="orderbook-source-note">
          Comparison only. Orders still use {symbol} on the selected execution account.
        </p>
      ) : snapshot && !snapshot.stream_available && source !== 'demo' ? (
        <p className="orderbook-source-note">
          This exchange and pair use snapshots. Choose Binance for live comparison.
        </p>
      ) : null}
      {!feed ? (
        <Empty title="Choose an execution account">
          The book follows its exchange and market. You can also select Binance for comparison.
        </Empty>
      ) : !ready ? (
        <Empty title="Waiting for a spot pair">
          Use the exact base and quote, such as BTC/USDT.
        </Empty>
      ) : !book && snapshots.error ? (
        <ErrorState message={snapshots.error} retry={refresh} />
      ) : !book ? (
        <Loading />
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
            <DataNote source={book.source} />
            <span>
              {book.source === 'demo'
                ? 'Synthetic levels for demonstration'
                : book.as_of
                  ? 'Observed ' + new Date(book.as_of).toLocaleTimeString()
                  : undefined}
            </span>
          </div>
        </>
      )}
    </Panel>
  );
}

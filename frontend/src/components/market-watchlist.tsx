import { useState } from 'react';
import { Link } from 'react-router-dom';
import {
  ArrowUpRight,
  ArrowUpDown,
  Check,
  ChevronDown,
  ChevronUp,
  Plus,
  Star,
  X,
} from 'lucide-react';
import {
  AssetIcon,
  Change,
  DataNote,
  ErrorState,
  Loading,
  Panel,
  PanelTitle,
  useToast,
} from './ui';
import { MarketSelector, type SpotCatalog } from './market-controls';
import { number } from '../lib/api';
import type { WatchlistState } from '../lib/watchlist';
import type { MarketSource } from '../lib/types';

/** Inline watchlist editing keeps chart selection independent from saved market preferences. */
export function MarketWatchlist({
  watchlist,
  catalog,
  selected,
  source,
  onSelect,
}: {
  watchlist: WatchlistState;
  catalog?: SpotCatalog;
  selected: string;
  source: MarketSource;
  onSelect: (symbol: string) => void;
}) {
  const [adding, setAdding] = useState(false);
  const [candidate, setCandidate] = useState('');
  const [arranging, setArranging] = useState(false);
  const toast = useToast();
  const { symbols, items, config, busy } = watchlist;
  const full = symbols.length >= (config?.limit ?? 30);
  const showAdd = () => {
    setAdding((value) => !value);
    setCandidate(symbols.includes(selected) ? '' : selected);
  };
  async function add(event: React.FormEvent) {
    event.preventDefault();
    if (candidate && (await watchlist.add(candidate))) {
      toast(`${candidate} added to your watchlist.`);
      setCandidate('');
    }
  }
  return (
    <Panel className="full-panel market-watchlist">
      <div id="market-watchlist" className="watchlist-anchor" />
      <PanelTitle
        title="My watchlist"
        subtitle={`Saved for ${source.name} · ${symbols.length}/${config?.limit ?? 30} markets`}
        action={
          <div className="watchlist-heading-actions">
            <button
              type="button"
              className="text-button"
              disabled={busy || symbols.length < 2}
              aria-pressed={arranging}
              onClick={() => setArranging(!arranging)}
            >
              {arranging ? <Check size={13} /> : <ArrowUpDown size={13} />}
              {arranging ? 'Done' : 'Reorder'}
            </button>
            <button
              type="button"
              className="button secondary"
              disabled={busy || full || !catalog}
              aria-expanded={adding}
              onClick={showAdd}
            >
              <Plus size={14} /> Add market
            </button>
          </div>
        }
      />
      {adding && (
        <form className="watchlist-add-form" onSubmit={add}>
          <MarketSelector
            label="Add a market to your watchlist"
            value={candidate}
            onChange={setCandidate}
            catalog={catalog}
            exclude={symbols}
            disabled={busy}
          />
          <button className="button primary" type="submit" disabled={busy || !candidate || full}>
            {busy ? 'Saving…' : 'Add to watchlist'}
          </button>
          <button
            type="button"
            className="icon-button"
            aria-label="Close add market"
            onClick={() => setAdding(false)}
          >
            <X size={16} />
          </button>
        </form>
      )}
      {watchlist.error && (
        <p className="watchlist-error" role="alert">
          {watchlist.error}
        </p>
      )}
      {watchlist.loading ? (
        <Loading />
      ) : watchlist.configError ? (
        <ErrorState message={watchlist.configError} retry={watchlist.retry} />
      ) : !symbols.length ? (
        <div className="watchlist-empty">
          <Star size={25} />
          <h3>Your markets, at a glance.</h3>
          <p>Add any supported pair above. Your list stays saved for this feed.</p>
          <button
            className="button secondary"
            onClick={() => {
              setAdding(true);
              setCandidate(selected);
            }}
            disabled={!catalog}
          >
            <Plus size={14} /> Add your first market
          </button>
        </div>
      ) : (
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>Market</th>
                <th>Price / quote</th>
                <th>24h move</th>
                <th>Quote volume</th>
                <th>Updated</th>
                <th>
                  <span className="sr-only">Watchlist actions</span>
                </th>
              </tr>
            </thead>
            <tbody>
              {items.map((item, index) => (
                <tr key={item.symbol}>
                  <td>
                    <button
                      className="asset-name"
                      onClick={() => onSelect(item.symbol)}
                      disabled={item.status === 'unavailable'}
                    >
                      <AssetIcon asset={item.asset} color={item.color} />
                      <span className="watchlist-market-name">
                        <strong>{item.name}</strong>
                        <small>{item.symbol}</small>
                      </span>
                    </button>
                  </td>
                  <td>
                    {item.price == null ? '—' : number(item.price, item.price < 1 ? 8 : 2)}{' '}
                    <small className="muted">{item.quote}</small>
                  </td>
                  <td>
                    <Change value={item.change} />
                  </td>
                  <td>
                    {item.volume == null ? '—' : `${number(item.volume / 1e6)}M ${item.quote}`}
                  </td>
                  <td>
                    <span
                      className={
                        item.status === 'stale' || item.status === 'unavailable'
                          ? 'negative'
                          : 'muted'
                      }
                      title={
                        item.error ||
                        (item.observed_at
                          ? new Date(item.observed_at).toLocaleString()
                          : 'Provider did not supply a timestamp')
                      }
                    >
                      {item.status === 'loading'
                        ? 'Loading…'
                        : item.status === 'unavailable'
                          ? 'Unavailable'
                          : source.kind === 'demo'
                            ? 'Illustrative'
                            : item.observed_at
                              ? new Date(item.observed_at).toLocaleTimeString([], {
                                  hour: '2-digit',
                                  minute: '2-digit',
                                })
                              : 'Undated'}
                      {item.status === 'stale' ? ' · Stale' : ''}
                    </span>
                  </td>
                  <td>
                    <div className="watchlist-row-actions">
                      {arranging && (
                        <>
                          <button
                            className="icon-button"
                            aria-label={`Move ${item.symbol} up`}
                            disabled={busy || index === 0}
                            onClick={() => void watchlist.move(item.symbol, -1)}
                          >
                            <ChevronUp size={15} />
                          </button>
                          <button
                            className="icon-button"
                            aria-label={`Move ${item.symbol} down`}
                            disabled={busy || index === items.length - 1}
                            onClick={() => void watchlist.move(item.symbol, 1)}
                          >
                            <ChevronDown size={15} />
                          </button>
                        </>
                      )}
                      {item.status !== 'unavailable' &&
                        item.quote === 'USDT' &&
                        ['BTC', 'ETH', 'SOL', 'LINK', 'AVAX', 'DOT'].includes(item.asset) && (
                          <Link className="text-link" to={`/trade?asset=${item.asset}`}>
                            Trade <ArrowUpRight size={12} />
                          </Link>
                        )}
                      <button
                        className="icon-button watchlist-remove"
                        aria-label={`Remove ${item.symbol} from watchlist`}
                        title={`Remove ${item.symbol}`}
                        disabled={busy}
                        onClick={async () => {
                          if (await watchlist.remove(item.symbol))
                            toast(`${item.symbol} removed from your watchlist.`);
                        }}
                      >
                        <X size={14} />
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <div className="table-footer">
        <DataNote source={watchlist.quotes.data?.source || source.id} label={source.name} />
        <span className="muted">
          {busy ? 'Saving watchlist…' : 'Changes save automatically · each feed keeps its own list'}
        </span>
      </div>
      {watchlist.quotes.error && !!config && (
        <p className="watchlist-error" role="status">
          Prices could not refresh. Your saved markets are retained.{' '}
          <button className="text-button" onClick={watchlist.quotes.retry}>
            Retry quotes
          </button>
        </p>
      )}
    </Panel>
  );
}

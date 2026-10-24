import { useState } from 'react';
import { api } from './api';
import { useResource } from './hooks';
import type { MarketAsset, Source } from './types';

export type WatchlistConfig = Source & {
  symbols: string[];
  revision: number;
  updated_at: string;
  limit: number;
};
export type WatchlistQuotes = WatchlistConfig & { items: MarketAsset[]; warnings: string[] };
type CatalogItem = {
  symbol: string;
  base: string;
  quote: string;
  name?: string;
  color?: string | null;
};

/** Persist edits on the API; a slow quote refresh never restores a removed or reordered row. */
export function useWatchlist(source: string, catalog: CatalogItem[] = []) {
  const suffix = `source=${encodeURIComponent(source)}`;
  const preferences = useResource<WatchlistConfig>(`/markets/watchlist?${suffix}`);
  const quotes = useResource<WatchlistQuotes>(`/markets?${suffix}`, 60000);
  const [saved, setSaved] = useState<WatchlistConfig>();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const config = [preferences.data, quotes.data, saved]
    .filter((value): value is WatchlistConfig => !!value)
    .sort((a, b) => b.revision - a.revision)[0];
  const metadata = new Map(catalog.map((item) => [item.symbol, item]));
  const prices = new Map(quotes.data?.items.map((item) => [item.symbol, item]));
  const symbols = config?.symbols ?? [];
  const items: MarketAsset[] = symbols.map(
    (symbol) =>
      prices.get(symbol) ?? {
        symbol,
        asset: symbol.split('/')[0],
        quote: symbol.split('/')[1],
        name: metadata.get(symbol)?.name || symbol.split('/')[0],
        color: metadata.get(symbol)?.color || '#7994b3',
        price: null,
        change: null,
        volume: null,
        sparkline: [],
        observed_at: null,
        status: quotes.error ? 'unavailable' : 'loading',
        error: quotes.error || undefined,
      },
  );
  async function change(path: string, method: string, body?: unknown) {
    setBusy(true);
    setError('');
    try {
      const result = await api<WatchlistConfig>(path, {
        method,
        ...(body === undefined ? {} : { body: JSON.stringify(body) }),
      });
      setSaved(result);
      preferences.retry();
      quotes.retry();
      return true;
    } catch (reason) {
      setError((reason as Error).message);
      preferences.retry();
      return false;
    } finally {
      setBusy(false);
    }
  }
  return {
    config,
    symbols,
    items,
    busy,
    error,
    quotes,
    loading: !config && (preferences.loading || quotes.loading),
    configError: !config ? preferences.error || quotes.error : '',
    retry: () => {
      preferences.retry();
      quotes.retry();
    },
    add: (symbol: string) => change(`/markets/watchlist/items?${suffix}`, 'POST', { symbol }),
    remove: (symbol: string) =>
      change(`/markets/watchlist/items?${suffix}&symbol=${encodeURIComponent(symbol)}`, 'DELETE'),
    move: (symbol: string, direction: -1 | 1) => {
      const index = symbols.indexOf(symbol),
        next = index + direction;
      if (index < 0 || next < 0 || next >= symbols.length) return Promise.resolve(false);
      const reordered = [...symbols];
      [reordered[index], reordered[next]] = [reordered[next], reordered[index]];
      return change(`/markets/watchlist/order?${suffix}`, 'POST', { symbols: reordered });
    },
  };
}
export type WatchlistState = ReturnType<typeof useWatchlist>;

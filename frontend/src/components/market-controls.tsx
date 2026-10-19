import { useState } from 'react';
import { useResource } from '../lib/hooks';
import type { Source, Timeframe } from '../lib/types';

export type SpotCatalog = Source & {
  items: { symbol: string; base: string; quote: string }[];
  timeframes: Timeframe[];
};
export const timeframes: Timeframe[] = ['1m', '5m', '15m', '30m', '1h', '4h', '12h', '1d', '1w'];
export function TimeframeSelect({
  value,
  onChange,
}: {
  value: Timeframe;
  onChange: (value: Timeframe) => void;
}) {
  const catalog = useResource<SpotCatalog>('/markets/symbols');
  return (
    <label>
      Timeframe
      <select value={value} onChange={(e) => onChange(e.target.value as Timeframe)}>
        {[...new Set([value, ...(catalog.data?.timeframes ?? timeframes)])].map((frame) => (
          <option key={frame}>{frame}</option>
        ))}
      </select>
    </label>
  );
}

/** Bound the visible market list while retaining access to the provider's spot catalog. */
export function MarketSelector({
  value,
  onChange,
  disabled = false,
}: {
  value: string;
  onChange: (value: string) => void;
  disabled?: boolean;
}) {
  const catalog = useResource<SpotCatalog>('/markets/symbols');
  const [query, setQuery] = useState('');
  const items =
    catalog.data?.items
      .filter((item) => item.symbol.toLowerCase().includes(query.toLowerCase()))
      .slice(0, 100) ?? [];
  return (
    <div className="market-picker">
      <label>
        Find a spot market
        <input
          aria-label="Find a spot market"
          placeholder="BTC, ETH/BTC, /USD…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          disabled={disabled}
        />
      </label>
      <label>
        Market
        <select value={value} onChange={(e) => onChange(e.target.value)} disabled={disabled}>
          {!items.some((item) => item.symbol === value) && <option>{value}</option>}
          {items.map((item) => (
            <option key={item.symbol}>{item.symbol}</option>
          ))}
        </select>
      </label>
      {catalog.error && <small className="negative">{catalog.error}</small>}
    </div>
  );
}

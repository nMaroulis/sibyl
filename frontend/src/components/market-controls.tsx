import { useResource } from '../lib/hooks';
import { AssetIcon } from './ui';
import { SearchPicker } from './search-picker';
import type { Source, Timeframe } from '../lib/types';

export type SpotCatalog = Source & {
  items: { symbol: string; base: string; quote: string; name?: string; color?: string }[];
  timeframes: Timeframe[];
  candle_limits?: Partial<Record<Timeframe, number>>;
};
export const timeframes: Timeframe[] = ['1m', '5m', '15m', '30m', '1h', '4h', '12h', '1d', '1w'];
export function TimeframeSelect({
  value,
  onChange,
  catalog: supplied,
}: {
  value: Timeframe;
  onChange: (value: Timeframe) => void;
  catalog?: SpotCatalog;
}) {
  const resource = useResource<SpotCatalog>('/markets/symbols', 0, !supplied);
  const catalog = supplied ?? resource.data;
  return (
    <label>
      Timeframe
      <select value={value} onChange={(e) => onChange(e.target.value as Timeframe)}>
        {(catalog?.timeframes ?? timeframes).map((frame) => (
          <option key={frame}>{frame}</option>
        ))}
      </select>
    </label>
  );
}

/** Search the full backend spot catalog in a single picker; shortcuts never limit discovery. */
export function MarketSelector({
  value,
  onChange,
  disabled = false,
  catalog: supplied,
  label = 'Coin & pair',
  exclude = [],
}: {
  value: string;
  onChange: (value: string) => void;
  disabled?: boolean;
  catalog?: SpotCatalog;
  label?: string;
  exclude?: string[];
}) {
  const resource = useResource<SpotCatalog>('/markets/symbols', 0, !supplied);
  const catalog = supplied ?? resource.data;
  const popular = ['BTC', 'ETH', 'SOL', 'BNB', 'XRP', 'ADA', 'DOGE'];
  const quotes = ['USDT', 'USD', 'USDC', 'BTC', 'ETH'];
  const rank = (base: string, quote: string) => {
    const baseIndex = popular.indexOf(base),
      quoteIndex = quotes.indexOf(quote);
    return (quoteIndex < 0 ? 8 : quoteIndex) * 1000 + (baseIndex < 0 ? 100 : baseIndex);
  };
  const excluded = new Set(exclude);
  const items = [...(catalog?.items ?? [])]
    .filter((item) => !excluded.has(item.symbol))
    .sort(
      (a, b) => rank(a.base, a.quote) - rank(b.base, b.quote) || a.symbol.localeCompare(b.symbol),
    );
  return (
    <div className="market-picker">
      <SearchPicker
        label={label}
        value={value}
        disabled={disabled || !!resource.error}
        loading={!catalog && resource.loading}
        onChange={onChange}
        placeholder="Search BTC, Cardano, ADA/USDT…"
        hint="Search any supported spot market"
        groups={[
          {
            label: 'Spot markets',
            detail: catalog?.source_label || catalog?.source,
            options: items.map((item) => ({
              value: item.symbol,
              label: item.symbol,
              description: `${item.name || item.base} · quoted in ${item.quote}`,
              keywords: `${item.base} ${item.quote} ${item.name || ''}`,
              icon: <AssetIcon asset={item.base} color={item.color ?? undefined} />,
            })),
          },
        ]}
      />
      {resource.error && <small className="negative">{resource.error}</small>}
    </div>
  );
}

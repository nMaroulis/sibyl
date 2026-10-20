import { Link } from 'react-router-dom';
import { ArrowUpRight } from 'lucide-react';
import { MarketSourceMark } from './config-helper';
import { SearchPicker, type PickerGroup } from './search-picker';
import type { MarketSettings } from '../lib/types';

/** One option per feed; badges identify the actual workspace default without a duplicate row. */
export function MarketSourcePicker({
  settings,
  value,
  onChange,
}: {
  settings: MarketSettings;
  value: string;
  onChange: (source: string) => void;
}) {
  const groups: PickerGroup[] = [
    { label: 'Exchanges', detail: 'Public feeds · no key', options: [] },
    { label: 'Connected exchanges', detail: 'Your saved accounts', options: [] },
    { label: 'Market APIs', detail: 'Aggregated data', options: [] },
    { label: 'Demo', detail: 'Offline sample data', options: [] },
  ];
  for (const source of settings.catalog) {
    const group =
      source.kind === 'exchange'
        ? 0
        : source.kind === 'connection'
          ? 1
          : source.kind === 'api'
            ? 2
            : 3;
    groups[group].options.push({
      value: source.id,
      label: source.name,
      description:
        source.kind === 'demo'
          ? 'Simulated quotes, candles & order books'
          : !source.available
            ? 'Set up an API key in Settings'
            : source.environment === 'test'
              ? 'Connected account · Test environment'
              : source.kind === 'connection'
                ? 'Connected account · Production'
                : source.kind === 'exchange'
                  ? 'Spot quotes, charts & order books'
                  : source.candles
                    ? 'Live quotes & candle history'
                    : 'Live quotes only',
      keywords: `${source.provider} ${source.kind}`,
      icon: <MarketSourceMark source={source} />,
      badge:
        source.id === settings.active.id ? (
          <span className="picker-default-badge">Default</span>
        ) : undefined,
      disabled: !source.available,
    });
  }
  return (
    <SearchPicker
      label="Market feed"
      value={value}
      groups={groups.filter((group) => group.options.length)}
      onChange={onChange}
      placeholder="Find an exchange or API…"
      footer={
        <Link to="/settings?tab=market">
          Manage sources <ArrowUpRight size={12} />
        </Link>
      }
    />
  );
}

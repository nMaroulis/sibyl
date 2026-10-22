import { useState } from 'react';
import {
  ArrowUpRight,
  Bot,
  CandlestickChart,
  ChartNoAxesCombined,
  Check,
  CircleHelp,
  History,
  Wallet,
} from 'lucide-react';
import type { ExchangeProvider } from '../lib/types';
import { ExchangeMark } from './exchange-mark';

export const exchangeCategoryIcons = {
  account: Wallet,
  spot: ChartNoAxesCombined,
  history: History,
  market: CandlestickChart,
  limits: Bot,
};

const coverageLabels = {
  supported: 'All listed features implemented',
  partial: 'Some listed features implemented',
  unsupported: 'No listed features implemented',
  simulated: 'Simulated features',
};

/** The backend counts actual feature rows; cards never invent a provider rating. */
export function ExchangeProviderCard({
  provider,
  onOpen,
}: {
  provider: ExchangeProvider;
  onOpen: (category?: string) => void;
}) {
  const [dismissedTooltip, setDismissedTooltip] = useState<string>();
  const credentialLabel =
    provider.id === 'coinbase'
      ? 'CDP key & private key'
      : provider.passphrase
        ? 'Key, secret & passphrase'
        : provider.uid
          ? 'Key, secret & memo'
          : 'API key & secret';
  return (
    <article className={`exchange-provider-card ${provider.test_environment ? 'is-test' : ''}`}>
      <button
        className="exchange-provider-open"
        aria-label={`View ${provider.name} support`}
        onClick={() => onOpen()}
      >
        <span className="exchange-provider-emblem">
          <ExchangeMark exchange={provider.id} />
        </span>
        <span className="exchange-provider-name">
          <strong>{provider.name}</strong>
          <small>{credentialLabel}</small>
        </span>
        <ArrowUpRight className="exchange-provider-arrow" size={16} aria-hidden="true" />
        {provider.test_environment && (
          <span className="exchange-environment-tag">
            {provider.id === 'binance-testnet' ? 'Testnet' : 'Sandbox'}
          </span>
        )}
      </button>
      <div
        className="exchange-category-indicators"
        role="group"
        aria-label={`${provider.name} feature categories`}
      >
        {provider.support.map((group) => {
          const Icon =
            exchangeCategoryIcons[group.id as keyof typeof exchangeCategoryIcons] ?? CircleHelp;
          const { status, implemented, total } = group.summary;
          const tooltipId = `exchange-${provider.id}-${group.id}-coverage`;
          const description = `${coverageLabels[status]} · ${implemented} of ${total}`;
          return (
            <button
              key={group.id}
              className={`exchange-category-icon coverage-${status}`}
              aria-label={`${group.label}: ${description}`}
              aria-describedby={tooltipId}
              data-tooltip-dismissed={dismissedTooltip === group.id}
              onFocus={() => setDismissedTooltip(undefined)}
              onMouseEnter={() => setDismissedTooltip(undefined)}
              onKeyDown={(event) => {
                if (event.key === 'Escape') setDismissedTooltip(group.id);
              }}
              onClick={() => onOpen(group.id)}
            >
              <Icon size={17} strokeWidth={1.75} aria-hidden="true" />
              <span className="exchange-coverage-mark" aria-hidden="true">
                {status === 'supported' && <Check size={7} strokeWidth={3} />}
              </span>
              <span role="tooltip" id={tooltipId} className="exchange-category-tooltip">
                <strong>{group.label}</strong>
                <span>{description}</span>
              </span>
            </button>
          );
        })}
      </div>
    </article>
  );
}

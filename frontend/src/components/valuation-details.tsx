import { ChevronDown } from 'lucide-react';
import { number } from '../lib/api';
import type { ValuationQuote } from '../lib/types';

/** Reveal the exact reference pairs behind a holding without obscuring the table. */
export function ValuationDetails({ quote, source }: { quote: ValuationQuote; source: string }) {
  return (
    <details className="valuation-details">
      <summary>
        {quote.status === 'identity'
          ? 'Portfolio currency'
          : quote.price === null
            ? 'Pricing unavailable'
            : quote.path.join(' → ')}
        <ChevronDown size={11} aria-hidden="true" />
      </summary>
      <div className="valuation-evidence">
        <strong>{source}</strong>
        {quote.status === 'undated' && <span>Undated quote · age unverified</span>}
        {quote.status === 'identity' && <span>1 USDT = 1 USDT. No conversion required.</span>}
        {quote.reason && <span>{quote.reason}</span>}
        {quote.route.map((leg) => (
          <div key={`${leg.symbol}:${leg.inverse}`}>
            <strong>
              {leg.symbol}
              {leg.inverse ? ' · inverse' : ''}
            </strong>
            <span className="monetary">
              1 {leg.from_asset} = {number(leg.rate, 8)} {leg.to_asset}
            </span>
            <span>
              {leg.observed_at
                ? `Provider time: ${new Date(leg.observed_at).toLocaleString()}`
                : 'Provider time unavailable · quote age unverified'}
            </span>
            {leg.received_at && <span>Fetched: {new Date(leg.received_at).toLocaleString()}</span>}
          </div>
        ))}
      </div>
    </details>
  );
}

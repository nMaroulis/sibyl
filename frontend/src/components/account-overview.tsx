import { Link } from 'react-router-dom';
import {
  ArrowUpRight,
  ChartCandlestick,
  ChevronDown,
  CircleAlert,
  Layers3,
  Wallet,
  Waves,
} from 'lucide-react';
import { number } from '../lib/api';
import type { Portfolio } from '../lib/types';
import { Change } from './ui';
import './account-overview.css';

/** A compact account summary with coverage kept visible and detailed warnings on demand. */
export function AccountOverview({
  portfolio,
  runningStrategies,
}: {
  portfolio: Portfolio;
  runningStrategies?: number;
}) {
  const { coverage, warnings } = portfolio;
  const demo = portfolio.mode === 'demo';
  const coveragePercent = coverage.total ? (coverage.priced / coverage.total) * 100 : 0;
  return (
    <section className="account-overview" aria-label="Account summary">
      <div className="account-overview-metrics">
        <div className="account-overview-metric account-overview-total">
          <div className="account-overview-label">
            <Wallet size={14} aria-hidden="true" />
            {portfolio.complete ? 'Portfolio value' : 'Priced portfolio value'}
          </div>
          <div className="account-overview-value">
            <strong className="monetary">{number(portfolio.total)}</strong>
            <span>{portfolio.currency}</span>
            {!portfolio.complete && <span className="account-overview-partial">Partial</span>}
          </div>
          <div className="account-overview-meta">
            {portfolio.change == null ? (
              <span>Daily move unavailable</span>
            ) : (
              <>
                <Change value={portfolio.change} />
                <span>daily price move</span>
              </>
            )}
          </div>
        </div>
        <div className="account-overview-metric">
          <div className="account-overview-label">
            <ChartCandlestick size={14} aria-hidden="true" />
            {demo ? 'Paper cash & stablecoins' : 'Valuation price feed'}
          </div>
          <div className="account-overview-value account-overview-secondary">
            {demo ? (
              <>
                <strong className="monetary">{number(portfolio.cash)}</strong>
                <span>{portfolio.currency}</span>
              </>
            ) : (
              <Link to="/settings?tab=market" aria-label="Change price feed">
                {portfolio.source_label || portfolio.source}
                <ArrowUpRight size={14} aria-hidden="true" />
              </Link>
            )}
          </div>
          <div className="account-overview-meta">
            {demo ? (
              <Link to="/settings?tab=market">
                Prices: {portfolio.source_label || portfolio.source}
                <ArrowUpRight size={11} aria-hidden="true" />
              </Link>
            ) : (
              <span>Shared across accounts</span>
            )}
          </div>
        </div>
        <div className="account-overview-metric">
          <div className="account-overview-label">
            <Layers3 size={14} aria-hidden="true" /> Assets
          </div>
          <div className="account-overview-value account-overview-secondary">
            <strong>{coverage.total}</strong>
            <span>
              {portfolio.venues.length} {portfolio.venues.length === 1 ? 'account' : 'accounts'}
            </span>
          </div>
          <div className="account-overview-meta">
            <span className="account-overview-coverage" aria-hidden="true">
              <span style={{ width: `${coveragePercent}%` }} />
            </span>
            <span>
              {coverage.priced}/{coverage.total} priced
            </span>
          </div>
        </div>
        <div className="account-overview-metric">
          <div className="account-overview-label">
            <Waves size={14} aria-hidden="true" /> Running strategies
          </div>
          <div className="account-overview-value account-overview-secondary">
            <strong>{runningStrategies ?? '—'}</strong>
            <span>in workspace</span>
          </div>
          <div className="account-overview-meta">
            <Link to="/strategies">
              Open strategy studio <ArrowUpRight size={11} aria-hidden="true" />
            </Link>
          </div>
        </div>
      </div>
      {warnings.length > 0 && (
        <details className="account-overview-notices">
          <summary>
            <CircleAlert size={15} aria-hidden="true" />
            <span className="account-overview-notice-title">
              {portfolio.unpriced.length
                ? `${portfolio.unpriced.length} ${portfolio.unpriced.length === 1 ? 'asset excluded' : 'assets excluded'} from total`
                : 'Valuation needs attention'}
            </span>
            <span className="account-overview-notice-count">
              {warnings.length}
              <span className="sr-only"> valuation notices</span>
            </span>
            <span className="account-overview-review">Details</span>
            <ChevronDown className="account-overview-chevron" size={14} aria-hidden="true" />
          </summary>
          <div className="account-overview-notice-body">
            <ul>
              {warnings.map((warning) => (
                <li key={warning}>{warning}</li>
              ))}
            </ul>
            <a href="#valuation-notes">
              View valuation notes <ArrowUpRight size={12} aria-hidden="true" />
            </a>
          </div>
        </details>
      )}
    </section>
  );
}

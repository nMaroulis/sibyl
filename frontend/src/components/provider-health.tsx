import { useState } from 'react';
import { Link } from 'react-router-dom';
import { Activity, ArrowUpRight, ChevronDown, RefreshCw } from 'lucide-react';
import { Badge, ErrorState, Loading, Panel, PanelTitle } from './ui';
import { MarketSourceMark } from './config-helper';
import { useResource } from '../lib/hooks';
import { ProviderReadHistory } from './provider-read-history';
import {
  healthLabels,
  type ProviderHealth,
  type ProviderHealthReport,
} from '../lib/provider-health';

const when = (date: string | null) => (date ? new Date(date).toLocaleString() : 'No observed read');
const tone = (status: ProviderHealth['status']) =>
  status === 'healthy'
    ? ('lime' as const)
    : status === 'demo' || status === 'retrying' || status === 'stale'
      ? ('sand' as const)
      : status === 'degraded' || status === 'unavailable'
        ? ('rose' as const)
        : ('neutral' as const);

/** Diagnostics are local reads. Opening or refreshing this panel never probes providers. */
export function SourceHealthPanel({ active = true }: { active?: boolean }) {
  const report = useResource<ProviderHealthReport>('/providers/health', 10000, active);
  const [all, setAll] = useState(false);
  const [query, setQuery] = useState('');
  const [expanded, setExpanded] = useState<string | null>(null);
  const [environment, setEnvironment] = useState('all');
  const rows = (report.data?.items ?? []).filter(
    (s) =>
      (all || s.default || s.requests > 0 || s.queued > 0 || s.last_error || s.history_available) &&
      (environment === 'all' || s.environment === environment) &&
      `${s.name} ${s.provider}`.toLowerCase().includes(query.toLowerCase()),
  );
  return (
    <Panel className="source-health-panel">
      <PanelTitle
        title="Source health"
        subtitle="Observed reads, shared limits and local queues"
        action={
          <button className="text-button" onClick={report.retry} disabled={report.loading}>
            <RefreshCw size={13} /> Refresh diagnostics
          </button>
        }
      />
      <div className="source-health-body">
        {report.error && <ErrorState message={report.error} retry={report.retry} />}
        {!report.data && !report.error && <Loading />}
        {report.data && (
          <>
            <div className="source-health-stats">
              <div>
                <Activity size={15} />
                <strong>{report.data.in_flight}</strong>
                <span>HTTP reads in flight</span>
              </div>
              <div>
                <strong>{report.data.queued}</strong>
                <span>operations waiting</span>
              </div>
              <div>
                <strong>{report.data.jobs.candle_imports}</strong>
                <span>candle imports</span>
              </div>
              <div>
                <strong>{report.data.jobs.fill_imports + report.data.jobs.funding_imports}</strong>
                <span>account imports</span>
              </div>
            </div>
            <div className="source-health-filters">
              <label>
                Find a source
                <input
                  type="search"
                  value={query}
                  placeholder="Search source health…"
                  onChange={(e) => setQuery(e.target.value)}
                />
              </label>
              <label>
                Environment
                <select value={environment} onChange={(e) => setEnvironment(e.target.value)}>
                  <option value="all">All environments</option>
                  <option value="production">Production</option>
                  <option value="test">Test</option>
                  <option value="demo">Demo</option>
                </select>
              </label>
              <button className="button secondary" aria-pressed={all} onClick={() => setAll(!all)}>
                {all ? 'Show observed & default' : 'Show all sources'}
              </button>
            </div>
            {report.data.history_recording.dropped_observations > 0 && (
              <p className="source-health-error" role="status">
                Some read history could not be saved during this API session. Expand a source for
                details.
              </p>
            )}
            <div className="source-health-rows">
              {rows.map((s) => (
                <div key={s.id} className="source-health-entry">
                  <button
                    className="source-health-row"
                    aria-expanded={expanded === s.id}
                    onClick={() => setExpanded(expanded === s.id ? null : s.id)}
                  >
                    <MarketSourceMark source={s} />
                    <span className="source-health-identity">
                      <strong>
                        {s.name}
                        {s.default && <span className="picker-default-badge">Default</span>}
                      </strong>
                      <small>
                        {s.kind === 'connection' ? 'Saved account' : 'Market feed'} ·{' '}
                        {s.environment}
                      </small>
                    </span>
                    <span className="source-health-condition">
                      <Badge tone={tone(s.status)}>{healthLabels[s.status]}</Badge>
                      <small>
                        {s.retry_at
                          ? `Retry after ${new Date(s.retry_at).toLocaleTimeString()}`
                          : s.last_success_at
                            ? `Last read ${new Date(s.last_success_at).toLocaleTimeString()}`
                            : s.status === 'demo'
                              ? 'No external requests'
                              : s.history_available
                                ? 'Saved history · not checked this session'
                                : 'No successful transport read yet'}
                      </small>
                    </span>
                    <span className="source-health-latency">
                      {s.latency_ms === null ? '—' : `${Math.round(s.latency_ms)} ms`}
                      <small>{s.shared_queued} queued on provider</small>
                    </span>
                    <ChevronDown size={14} className={expanded === s.id ? 'expanded' : ''} />
                  </button>
                  {expanded === s.id && (
                    <div className="source-health-detail">
                      <div className="source-health-evidence">
                        <div>
                          <small>Transport requests · this session</small>
                          <strong>
                            {s.requests} · {s.failed_requests} failed
                          </strong>
                        </div>
                        <div>
                          <small>Read retries / deferrals</small>
                          <strong>
                            {s.read_retries} / {s.deferred}
                          </strong>
                        </div>
                        <div>
                          <small>Last successful read</small>
                          <strong>{when(s.last_success_at)}</strong>
                        </div>
                        <div>
                          <small>Latest quote sample</small>
                          <strong>
                            {s.data_status === 'synthetic'
                              ? 'Synthetic demo'
                              : s.quote
                                ? `${s.quote.symbol} · ${s.data_status}`
                                : 'Not observed'}
                          </strong>
                        </div>
                      </div>
                      {s.quote && (
                        <p className="footnote">
                          Provider quote time:{' '}
                          {s.quote.observed_at ? when(s.quote.observed_at) : 'Undated or invalid'}.
                          A fresh quote sample does not establish coverage for every market.
                        </p>
                      )}
                      {s.last_error && (
                        <p className="source-health-error" role="status">
                          {s.last_error.message}
                        </p>
                      )}
                      {s.errors.length > 0 && (
                        <details>
                          <summary>Recent read errors · {s.errors.length}</summary>
                          {s.errors.map((error, i) => (
                            <p className="footnote" key={i}>
                              {when(error.at)} · {error.message}
                            </p>
                          ))}
                        </details>
                      )}
                      {s.status === 'not_checked' && (
                        <p className="footnote">
                          This source has no successful observed network read in the current
                          process. A saved key or selectable card does not establish connectivity.
                        </p>
                      )}
                      <ProviderReadHistory source={s.id} demo={s.status === 'demo'} />
                      <Link
                        className="text-link"
                        to={
                          s.available
                            ? `/markets?source=${encodeURIComponent(s.id)}`
                            : s.kind === 'connection'
                              ? '/settings?tab=exchanges'
                              : '/settings?tab=market'
                        }
                      >
                        {s.available ? 'Open this feed' : 'Configure this source'}{' '}
                        <ArrowUpRight size={12} />
                      </Link>
                    </div>
                  )}
                </div>
              ))}
              {!rows.length && (
                <p className="muted">
                  No matching observed sources. Show all sources to include feeds that have not been
                  checked.
                </p>
              )}
            </div>
            <p className="footnote">
              Interactive reads take priority over queued background work. Limits are shared by
              provider and environment; existing in-flight operations finish first. At most{' '}
              {report.data.policy.max_inflight} HTTP reads run concurrently. Native exchange
              limiters remain enabled.
            </p>
            <p className="footnote">
              Connectivity and quote freshness are separate. Refresh reads local diagnostics only.
              Session metrics started {when(report.data.started_at)} and reset on API restart. Saved
              read history and import jobs persist. News and other research providers keep their own
              health reporting.
            </p>
          </>
        )}
      </div>
    </Panel>
  );
}

/** One compact, consistent status line for pages using the reference feed. */
export function SourceHealthSummary({ source }: { source: string }) {
  const report = useResource<ProviderHealthReport>(
    `/providers/health?source=${encodeURIComponent(source)}`,
    15000,
    !!source,
  );
  const s = report.data?.items[0];
  if (!s)
    return report.error ? (
      <p className="footnote">
        Feed diagnostics unavailable. <Link to="/settings?tab=market">Check source health</Link>
      </p>
    ) : null;
  return (
    <div className="source-health-summary">
      <Activity size={13} />
      <span>{s.name}</span>
      <Badge tone={tone(s.status)}>{healthLabels[s.status]}</Badge>
      {s.data_status === 'stale' && <Badge tone="sand">Latest quote sample stale</Badge>}
      {s.data_status === 'undated' && <Badge tone="sand">Undated quote sample</Badge>}
      {s.data_status === 'invalid' && <Badge tone="rose">Invalid quote sample</Badge>}
      {s.retry_at && <small>Retry after {new Date(s.retry_at).toLocaleTimeString()}</small>}
      <Link to="/settings?tab=market">
        Source health <ArrowUpRight size={11} />
      </Link>
    </div>
  );
}

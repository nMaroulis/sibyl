import { useState } from 'react';
import { History, RefreshCw } from 'lucide-react';
import { ErrorState, Loading } from './ui';
import { useResource } from '../lib/hooks';
import type { ProviderReadHistory as ReadHistory } from '../lib/provider-health';

const when = (at: string) => new Date(at).toLocaleString();
const ms = (value: number | null) => (value === null ? '—' : `${Math.round(value)} ms`);

/** Inspect saved traffic only; expanding this view never tests a provider or a key. */
export function ProviderReadHistory({ source, demo }: { source: string; demo: boolean }) {
  const [window, setWindow] = useState('24h');
  const history = useResource<ReadHistory>(
    `/providers/health/history?source=${encodeURIComponent(source)}&window=${window}`,
  );
  const [selected, setSelected] = useState<number | null>(null);
  const data = history.data;
  const peak = Math.max(1, ...(data?.series.map((point) => point.requests) ?? []));
  const hovered = selected === null ? undefined : data?.series[selected];
  return (
    <section className="provider-read-history" aria-label="Saved provider read history">
      <div className="provider-history-heading">
        <h4>
          <History size={14} />
          Saved read history
        </h4>
        <label>
          <span className="sr-only">Read history window</span>
          <select
            value={window}
            onChange={(event) => {
              setWindow(event.target.value);
              setSelected(null);
            }}
          >
            <option value="24h">24 hours</option>
            <option value="7d">7 days</option>
          </select>
        </label>
        <button
          className="icon-button"
          aria-label="Refresh saved read history"
          onClick={history.retry}
          disabled={history.loading}
        >
          <RefreshCw size={13} />
        </button>
      </div>
      {history.error ? (
        <ErrorState message={history.error} retry={history.retry} />
      ) : history.loading ? (
        <Loading />
      ) : (
        data && (
          <>
            {data.recording.dropped_observations > 0 && (
              <p className="source-health-error" role="status">
                {data.recording.dropped_observations} read observations could not be saved during
                this API session. History is partial.
              </p>
            )}
            {data.totals.requests ? (
              <>
                <div className="provider-history-stats">
                  <div>
                    <small>Observed HTTP reads</small>
                    <strong>{data.totals.requests.toLocaleString()}</strong>
                  </div>
                  <div>
                    <small>Read success</small>
                    <strong>{data.totals.success_rate}%</strong>
                  </div>
                  <div>
                    <small>Mean response time</small>
                    <strong>{ms(data.totals.mean_latency_ms)}</strong>
                  </div>
                  <div>
                    <small>Failed reads</small>
                    <strong>{data.totals.failures.toLocaleString()}</strong>
                  </div>
                </div>
                <div className="provider-history-chart">
                  <svg
                    viewBox={`0 0 ${data.series.length * 8} 68`}
                    preserveAspectRatio="none"
                    role="group"
                    tabIndex={0}
                    aria-label="Hourly observed HTTP reads. Green indicates successful reads, rose indicates failures. Use arrow keys to inspect an hour."
                    onFocus={() => setSelected(data.series.length - 1)}
                    onBlur={() => setSelected(null)}
                    onKeyDown={(event) => {
                      if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return;
                      event.preventDefault();
                      const index = selected ?? data.series.length - 1;
                      setSelected(
                        event.key === 'Home'
                          ? 0
                          : event.key === 'End'
                            ? data.series.length - 1
                            : Math.max(
                                0,
                                Math.min(
                                  data.series.length - 1,
                                  index + (event.key === 'ArrowLeft' ? -1 : 1),
                                ),
                              ),
                      );
                    }}
                  >
                    {data.series.map((point, index) => {
                      const height = (point.requests / peak) * 60;
                      const failedHeight = (point.failures / peak) * 60;
                      return (
                        <g
                          key={point.at}
                          role="img"
                          aria-label={`${when(point.at)}: ${point.successes} successful, ${point.failures} failed reads`}
                          onMouseEnter={() => setSelected(index)}
                          onMouseLeave={() => setSelected(null)}
                        >
                          <title>
                            {when(point.at)} ·{' '}
                            {point.requests
                              ? `${point.successes} succeeded, ${point.failures} failed · mean ${ms(point.mean_latency_ms)}`
                              : 'No observed reads'}
                          </title>
                          <rect
                            x={index * 8}
                            y={0}
                            width={7}
                            height={68}
                            fill={selected === index ? '#edf1f7' : 'transparent'}
                          />
                          {point.requests ? (
                            <>
                              <rect
                                x={index * 8}
                                y={64 - height}
                                width={6}
                                height={height}
                                rx={1}
                                fill="#a5c8bc"
                              />
                              {point.failures > 0 && (
                                <rect
                                  x={index * 8}
                                  y={64 - failedHeight}
                                  width={6}
                                  height={failedHeight}
                                  rx={1}
                                  fill="#d6a8b1"
                                />
                              )}
                            </>
                          ) : (
                            <rect x={index * 8} y={63} width={6} height={1} fill="#e2e7ef" />
                          )}
                        </g>
                      );
                    })}
                  </svg>
                  <div className="provider-history-axis">
                    <span>{new Date(data.start).toLocaleString()}</span>
                    <span>Now</span>
                  </div>
                  <p className="provider-history-hover" aria-live="polite">
                    {hovered
                      ? `${when(hovered.at)} · ${hovered.requests ? `${hovered.successes} succeeded / ${hovered.failures} failed · mean ${ms(hovered.mean_latency_ms)}` : 'No observed reads'}`
                      : 'Hover a bar, or focus the chart and use arrow keys. Gaps have no observed traffic.'}
                  </p>
                </div>
                <p className="footnote">
                  First read in this window: {data.totals.first_at && when(data.totals.first_at)}.
                  Peak response time: {ms(data.totals.max_latency_ms)}.
                </p>
              </>
            ) : (
              <p className="footnote">
                {demo
                  ? 'Demo makes no external requests, so it has no network history.'
                  : 'No retained HTTP reads in this window. Use this source normally to collect observations.'}
              </p>
            )}
            {data.recent_errors.length > 0 && (
              <details>
                <summary>Saved read errors · latest {data.recent_errors.length}</summary>
                {data.recent_errors.map((error, index) => (
                  <p className="footnote" key={index}>
                    {when(error.at)} · {error.message}
                  </p>
                ))}
              </details>
            )}
            <p className="footnote">
              Snapshot: {when(data.as_of)}. Hourly buckets, with a partial current hour. Saved
              across restarts for up to {data.retention_days} days, within storage limits. Includes
              earlier API sessions and credential profiles. Read success is observed traffic, not
              provider uptime or data freshness.
            </p>
          </>
        )
      )}
    </section>
  );
}

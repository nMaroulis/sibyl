import { WorkerIncidents } from './worker-incidents';
import { Link } from 'react-router-dom';
import { Activity, AlertCircle, ShieldCheck } from 'lucide-react';
import { useResource } from '../../lib/hooks';
import { post, refresh } from '../../lib/api';
import { Badge, ErrorState, Loading, Panel, PanelTitle, useToast } from '../ui';
import { useEffect, useState } from 'react';

export type Worker = {
  id: string;
  label: string;
  state: string;
  last_started_at: string | null;
  last_finished_at: string | null;
  last_duration_seconds: number | null;
  iterations: number;
  failures: number;
  last_error: string | null;
  elapsed_seconds: number | null;
};
type Health = {
  status: string;
  issue_count: number;
  started_at: string;
  observed_at: string;
  recovery_required: boolean;
  recovery_reviewed: boolean;
  scope: string;
  resources?: {
    cpu_percent: number | null;
    sample_seconds: number | null;
    rss_bytes: number | null;
    threads: number | null;
    database_bytes: number | null;
    volume_free_bytes: number | null;
    uptime_seconds: number;
    status: string;
    scope: string;
    unavailable: string[];
  };
  workers: Worker[];
  events: { id: number; name: string; kind: string; at: string; error: string | null }[];
};
const bytes = (value: number | null) =>
  value == null
    ? '—'
    : `${(value / 1024 / 1024).toLocaleString(undefined, { maximumFractionDigits: 1 })} MiB`;
const issue = (state: string) =>
  ['failed', 'stalled', 'overdue', 'retrying', 'stopped'].includes(state);
const time = (value: string | null) => (value ? new Date(value).toLocaleTimeString() : 'Not yet');

/** A quiet app-wide indication appears only for observed faults or recovery mode. */
export function WorkerHealthNotice() {
  const state = useResource<Health>('/workspace/health', 5000);
  const [now, setNow] = useState(Date.now());
  const [receivedAt, setReceivedAt] = useState(Date.now());
  useEffect(() => {
    if (state.data) setReceivedAt(Date.now());
  }, [state.data]);
  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 5000);
    return () => window.clearInterval(timer);
  }, []);
  const stale = now - receivedAt > 15000;
  if (!state.data && !state.error && !stale) return null;
  if (!stale && !state.error && !state.data?.issue_count && !state.data?.recovery_required)
    return null;
  return (
    <Link className="worker-health-notice" to="/settings?tab=workspace" role="status">
      <AlertCircle size={16} />
      <span>
        {state.error || stale
          ? 'Worker status unavailable or overdue'
          : state.data?.recovery_required
            ? 'Restored workspace · automatic work is paused for review'
            : `${state.data?.issue_count} background worker${state.data?.issue_count === 1 ? '' : 's'} need attention`}
      </span>
      <strong>View workspace →</strong>
    </Link>
  );
}

export function WorkerHealthPanel() {
  const result = useResource<Health>('/workspace/health', 5000);
  const [review, setReview] = useState('');
  const [busy, setBusy] = useState(false);
  const toast = useToast();
  const data = result.data;
  return (
    <Panel className="workspace-health">
      <PanelTitle
        title="Background activity"
        subtitle="Actual worker progress · checked every five seconds"
        action={
          <Badge tone={data?.issue_count ? 'rose' : 'neutral'}>
            <Activity size={13} />{' '}
            {data?.issue_count
              ? `${data.issue_count} need attention`
              : data?.status === 'paused'
                ? 'Recovery mode'
                : 'Observed progress'}
          </Badge>
        }
      />
      {result.error ? (
        <ErrorState message={result.error} retry={result.retry} />
      ) : result.loading ? (
        <Loading />
      ) : (
        <>
          {data?.recovery_required && (
            <div className="workspace-recovery">
              <ShieldCheck size={22} />
              <div>
                <h3>Review this restored workspace</h3>
                <p>
                  Automatic workers and exchange execution are paused. Accounts start inactive.
                  Check retained orders at the exchanges, strategy monitors, scheduled briefings and
                  Telegram settings before resuming. A backup cannot undo a trade.
                </p>
                {data.recovery_reviewed ? (
                  <p>
                    <strong>Review recorded. Restart Sibyl to start the workers.</strong>
                  </p>
                ) : (
                  <form
                    className="workspace-form"
                    onSubmit={async (event) => {
                      event.preventDefault();
                      setBusy(true);
                      try {
                        await post('/workspace/recovery/complete', { confirmation: review });
                        toast('Recovery reviewed. Restart Sibyl to start automatic workers.');
                        refresh();
                      } catch (error) {
                        toast((error as Error).message, true);
                      } finally {
                        setBusy(false);
                      }
                    }}
                  >
                    <label>
                      Type I REVIEWED THE RESTORED WORKSPACE
                      <input
                        value={review}
                        onChange={(event) => setReview(event.target.value)}
                        autoComplete="off"
                      />
                    </label>
                    <button
                      className="button"
                      disabled={busy || review !== 'I REVIEWED THE RESTORED WORKSPACE'}
                    >
                      Complete review · restart required
                    </button>
                  </form>
                )}
              </div>
            </div>
          )}
          {data?.resources && (
            <section className="process-resources" aria-label="Python process resources">
              <div className="resource-grid">
                {[
                  [
                    'CPU · one CPU = 100%',
                    data.resources.cpu_percent == null
                      ? data.resources.unavailable.includes('process_counters')
                        ? 'Unavailable'
                        : 'Collecting…'
                      : `${data.resources.cpu_percent}%`,
                  ],
                  ['Resident memory', bytes(data.resources.rss_bytes)],
                  ['Threads', data.resources.threads ?? '—'],
                  ['Database + WAL', bytes(data.resources.database_bytes)],
                  ['Free workspace volume', bytes(data.resources.volume_free_bytes)],
                  ['Process uptime', `${Math.floor(data.resources.uptime_seconds / 60)} min`],
                ].map(([name, value]) => (
                  <div key={name}>
                    <small>{name}</small>
                    <strong>{value}</strong>
                  </div>
                ))}
              </div>
              <p className="footnote">
                {data.resources.scope}{' '}
                {data.resources.sample_seconds != null &&
                  `CPU window: ${data.resources.sample_seconds}s.`}
                {data.resources.unavailable.length > 0 &&
                  ` Unavailable: ${data.resources.unavailable.join(', ')}.`}
              </p>
            </section>
          )}
          <details className="worker-details" open={data?.issue_count ? true : undefined}>
            <summary>Inspect {data?.workers.length ?? 0} supervised workers</summary>
            <div className="worker-grid">
              {data?.workers.map((worker) => (
                <article
                  className={`worker-tile ${issue(worker.state) ? 'needs-attention' : ''}`}
                  key={worker.id}
                >
                  <header>
                    <h3>{worker.label}</h3>
                    <Badge
                      tone={
                        issue(worker.state)
                          ? 'rose'
                          : worker.state === 'running'
                            ? 'purple'
                            : 'neutral'
                      }
                    >
                      {worker.state === 'running' && <span className="worker-pulse" />}
                      {worker.state}
                    </Badge>
                  </header>
                  <dl>
                    <div>
                      <dt>Last finished</dt>
                      <dd>{time(worker.last_finished_at)}</dd>
                    </div>
                    <div>
                      <dt>{worker.state === 'running' ? 'Elapsed' : 'Last duration'}</dt>
                      <dd>
                        {worker.state === 'running'
                          ? `${worker.elapsed_seconds ?? 0}s`
                          : worker.last_duration_seconds === null
                            ? '—'
                            : `${worker.last_duration_seconds}s`}
                      </dd>
                    </div>
                    <div>
                      <dt>Completed iterations</dt>
                      <dd>{worker.iterations}</dd>
                    </div>
                  </dl>
                  {worker.last_error && (
                    <p className="form-error">{worker.last_error} · review before restarting</p>
                  )}
                </article>
              ))}
            </div>
          </details>
          <WorkerIncidents />
          <details className="worker-history">
            <summary>Recent lifecycle and fault history</summary>
            <div>
              {data?.events.map((event) => (
                <p key={event.id}>
                  <span>{new Date(event.at).toLocaleString()}</span>
                  <strong>{event.name}</strong>
                  <span>
                    {event.kind}
                    {event.error ? ` · ${event.error}` : ''}
                  </span>
                </p>
              ))}
            </div>
          </details>
          <p className="footnote">
            {data?.scope} A stalled warning does not cancel an in-flight exchange operation. Fault
            details expose exception types only, never credentials or provider responses.
          </p>
        </>
      )}
    </Panel>
  );
}

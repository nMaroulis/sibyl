import { useState } from 'react';
import type { FormEvent } from 'react';
import { Archive, Clock3, Download, Pause, Play, Plus, Square } from 'lucide-react';
import { downloadFile, post, refresh } from '../../lib/api';
import { useResource } from '../../lib/hooks';
import type { Connection } from '../../lib/types';
import { Badge, Empty, ErrorState, Modal, Panel, PanelTitle, useToast } from '../ui';

type Job = {
  id: string;
  label: string;
  kind: string;
  state: string;
  revision: number;
  next_due: number | null;
  interval_seconds: number | null;
  skipped_occurrences: number;
  last_run_id: string | null;
  latest_run?: { state: string } | null;
};
type Run = {
  id: string;
  job_id: string;
  state: string;
  started_at: string | null;
  created_at: string;
  finished_at: string | null;
  result: unknown;
  error: string | null;
  recovered: boolean;
  duration_seconds?: number;
};
type Dataset = {
  id: string;
  symbol: string;
  count: number;
  timeframe: string;
  source: string;
  label?: string;
};
type Catalog = {
  items: Job[];
  handlers: {
    id: string;
    label: string;
    description: string;
    repeatable: boolean;
    creation_url?: string | null;
  }[];
  note: string;
  run_counts: Record<string, number>;
};

/** Manage real persisted schedules and receipts; opening this panel never starts a job. */
export function WorkspaceJobs() {
  const jobs = useResource<Catalog>('/workspace/jobs', 5000);
  const [creating, setCreating] = useState(false),
    [kind, setKind] = useState('workspace.health');
  const [selected, setSelected] = useState<Job>(),
    [busy, setBusy] = useState(false);
  const runs = useResource<{ items: Run[] }>(
    `/workspace/jobs/${selected?.id ?? ''}/runs`,
    3000,
    !!selected,
  );
  const connections = useResource<Connection[]>(
    '/connections',
    0,
    creating && kind === 'account.accounting',
  );
  const datasets = useResource<{ items: Dataset[] }>(
    '/market-history/datasets',
    0,
    creating && kind === 'forecast.train',
  );
  const toast = useToast();
  const act = async (job: Job, action: string) => {
    setBusy(true);
    try {
      await post(`/workspace/jobs/${job.id}/action`, { action, revision: job.revision });
      refresh();
    } catch (error) {
      toast((error as Error).message, true);
    } finally {
      setBusy(false);
    }
  };
  const start = async (job: Job) => {
    setBusy(true);
    try {
      await post(`/workspace/jobs/${job.id}/runs`, {
        request_id: crypto.randomUUID().replaceAll('-', ''),
      });
      setSelected(job);
      refresh();
      toast('Job queued. Open its run history to follow the result.');
    } catch (error) {
      toast((error as Error).message, true);
    } finally {
      setBusy(false);
    }
  };
  const create = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const label = String(form.get('label'));
    let args: Record<string, unknown> = {};
    if (kind === 'account.accounting')
      args = {
        account_id: form.get('account_id') ?? '',
        currency: form.get('currency'),
        source: form.get('source'),
        environment: form.get('environment'),
      };
    if (kind === 'forecast.recalibrate')
      args = { model_id: form.get('model_id'), revision: Number(form.get('policy_revision')) };
    if (kind === 'forecast.train') {
      const dataset = datasets.data?.items.find((item) => item.id === form.get('dataset_id'));
      if (!dataset) {
        toast('Choose a retained daily dataset first.', true);
        return;
      }
      args = {
        input_kind: 'saved_dataset',
        dataset_id: dataset.id,
        symbol: dataset.symbol,
        label,
        family: form.get('family'),
        feature_set: form.get('feature_set'),
        lags: 14,
        max_horizon: form.get('family') === 'mlp' ? 14 : 30,
        candles: dataset.count,
      };
    }
    setBusy(true);
    try {
      await post('/workspace/jobs', {
        label,
        kind,
        arguments: args,
        interval_seconds: kind === 'forecast.train' ? null : Number(form.get('interval')) || null,
        enabled: form.get('enabled') === 'on',
        missed: form.get('missed') ?? 'skip',
      });
      setCreating(false);
      refresh();
      toast('Job saved. Paused jobs run only when you choose Run once.');
    } catch (error) {
      toast((error as Error).message, true);
    } finally {
      setBusy(false);
    }
  };
  return (
    <Panel className="workspace-health">
      <PanelTitle
        title="Local jobs"
        subtitle="Durable schedules · saved outcomes"
        action={
          <button className="button secondary tiny" onClick={() => setCreating(true)}>
            <Plus size={14} />
            New job
          </button>
        }
      />
      <p className="footnote">
        Save one-off or recurring workspace tasks. Schedules run while the Python backend is open;
        missed intervals are handled explicitly.
      </p>
      {jobs.error && <ErrorState message={jobs.error} retry={jobs.retry} />}
      {jobs.data?.items.length ? (
        <div className="worker-health-list">
          {jobs.data.items.map((job) => (
            <div key={job.id} className="worker-health-row">
              <div>
                <strong>{job.label}</strong>
                <small className="muted">
                  {jobs.data?.handlers.find((handler) => handler.id === job.kind)?.label} ·{' '}
                  {job.interval_seconds ? `Every ${job.interval_seconds / 60} min` : 'One-off'}
                  {job.next_due && job.state === 'active'
                    ? ` · Next ${new Date(job.next_due * 1000).toLocaleString()}`
                    : ''}
                </small>
              </div>
              <Badge
                tone={
                  job.latest_run?.state === 'failed'
                    ? 'amber'
                    : job.state === 'active'
                      ? 'lime'
                      : 'neutral'
                }
              >
                {job.latest_run?.state === 'running'
                  ? 'Running'
                  : job.latest_run?.state === 'queued'
                    ? 'Queued'
                    : job.latest_run?.state === 'failed'
                      ? 'Last run failed'
                      : job.state === 'active'
                        ? 'Scheduled'
                        : job.state}
              </Badge>
              <div className="forecast-workspace-actions">
                <button
                  className="button secondary tiny"
                  disabled={busy}
                  onClick={() => start(job)}
                >
                  <Play size={12} />
                  Run once
                </button>
                <button
                  className="button secondary tiny"
                  disabled={busy}
                  onClick={() => act(job, job.state === 'active' ? 'pause' : 'resume')}
                >
                  {job.state === 'active' ? <Pause size={12} /> : <Clock3 size={12} />}
                  {job.state === 'active' ? 'Pause schedule' : 'Enable schedule'}
                </button>
                <button className="text-button" onClick={() => setSelected(job)}>
                  Runs
                </button>
                <button
                  className="text-button"
                  disabled={busy}
                  onClick={() => act(job, 'archive')}
                  aria-label={`Archive ${job.label}`}
                >
                  <Archive size={14} />
                </button>
              </div>
            </div>
          ))}
        </div>
      ) : (
        jobs.data && (
          <Empty title="No local jobs">
            Create a health check, retained accounting calculation or pinned forecast training job.
            New jobs are paused unless you explicitly enable them.
          </Empty>
        )
      )}
      <p className="footnote">{jobs.data?.note}</p>
      {creating && (
        <Modal title="New local job" onClose={() => setCreating(false)}>
          <form className="form-grid" onSubmit={create}>
            <label>
              Task
              <select value={kind} onChange={(event) => setKind(event.target.value)}>
                {jobs.data?.handlers
                  .filter((handler) => !handler.creation_url)
                  .map((handler) => (
                    <option key={handler.id} value={handler.id}>
                      {handler.label}
                    </option>
                  ))}
              </select>
              <small>
                {jobs.data?.handlers.find((handler) => handler.id === kind)?.description}
              </small>
            </label>
            <label>
              Name
              <input name="label" maxLength={80} required />
            </label>
            {kind === 'account.accounting' && (
              <>
                <label>
                  Account
                  <select name="account_id">
                    <option value="">All retained accounts</option>
                    {connections.data?.map((account) => (
                      <option key={account.id} value={account.id}>
                        {account.label}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  Environment
                  <select name="environment">
                    <option value="">Separate reports for each</option>
                    <option value="production">Production</option>
                    <option value="test">Test</option>
                    <option value="demo">Demo</option>
                  </select>
                </label>
                <label>
                  Reporting unit
                  <select name="currency">
                    {['USDT', 'USD', 'EUR', 'BTC', 'ETH'].map((unit) => (
                      <option key={unit}>{unit}</option>
                    ))}
                  </select>
                </label>
                <label>
                  Retained price source
                  <input
                    name="source"
                    defaultValue="binance"
                    pattern="[a-z0-9:-]{1,120}"
                    required
                  />
                  <small>
                    Use the exact retained feed ID shown in Market history. No prices are downloaded
                    by this job.
                  </small>
                </label>
              </>
            )}
            {kind === 'forecast.recalibrate' && (
              <>
                <label>
                  Parent model version ID
                  <input name="model_id" pattern="[a-f0-9]{32}" required />
                </label>
                <label>
                  Saved candidate policy revision
                  <input name="policy_revision" type="number" min="1" step="1" required />
                </label>
                <p className="footnote">
                  The model's current enabled policy controls candidate fitting. You can create this
                  job with the correct IDs directly from Forecasting → Drift &amp; candidate
                  recalibration.
                </p>
              </>
            )}
            {kind === 'forecast.train' && (
              <>
                <label>
                  Daily dataset
                  <select name="dataset_id" required>
                    <option value="">Choose retained input</option>
                    {datasets.data?.items
                      .filter((dataset) => dataset.timeframe === '1d')
                      .map((dataset) => (
                        <option key={dataset.id} value={dataset.id}>
                          {dataset.symbol} · {dataset.count} days ·{' '}
                          {dataset.label ?? dataset.source}
                        </option>
                      ))}
                  </select>
                </label>
                <label>
                  Model family
                  <select name="family">
                    <option value="ridge">Autoregressive ridge</option>
                    <option value="mlp">Small neural model</option>
                  </select>
                </label>
                <label>
                  Inputs
                  <select name="feature_set">
                    <option value="returns">Return lags</option>
                    <option value="returns_context">Returns and trailing context</option>
                  </select>
                </label>
                <p className="footnote">
                  This fits the pinned input once. It does not download new history or automatically
                  replace a forecast model. Interrupted fitting needs explicit review.
                </p>
              </>
            )}
            {kind !== 'forecast.train' && (
              <>
                <label>
                  Repeat
                  <select name="interval">
                    <option value="">One-off</option>
                    <option value="900">Every 15 minutes</option>
                    <option value="3600">Hourly</option>
                    <option value="86400">Daily</option>
                  </select>
                </label>
                <label>
                  Missed intervals
                  <select name="missed">
                    <option value="skip">Skip missed occurrences</option>
                    <option value="once">Run once after returning</option>
                  </select>
                </label>
              </>
            )}
            <label className="checkbox-label">
              <input name="enabled" type="checkbox" />
              Enable schedule after saving
            </label>
            <button className="button" disabled={busy} type="submit">
              {busy ? 'Saving…' : 'Save job'}
            </button>
          </form>
        </Modal>
      )}
      {selected && (
        <Modal title={`${selected.label} · runs`} onClose={() => setSelected(undefined)}>
          {runs.error && <ErrorState message={runs.error} retry={runs.retry} />}
          {runs.data?.items.length ? (
            runs.data.items.map((run) => (
              <div key={run.id} className="worker-health-row">
                <div>
                  <Badge
                    tone={
                      run.state === 'completed'
                        ? 'lime'
                        : run.state === 'failed'
                          ? 'amber'
                          : 'neutral'
                    }
                  >
                    {run.state}
                  </Badge>
                  <p>
                    {new Date(run.created_at).toLocaleString()}
                    {run.duration_seconds != null ? ` · ${run.duration_seconds}s` : ''}
                    {run.recovered ? ' · recovered read' : ''}
                  </p>
                  {run.error && <p className="form-error">{run.error}</p>}
                  {run.result != null && (
                    <details>
                      <summary>Inspect result</summary>
                      <pre className="data-preview">{JSON.stringify(run.result, null, 2)}</pre>
                    </details>
                  )}
                </div>
                <div className="forecast-workspace-actions">
                  {['queued', 'running'].includes(run.state) && (
                    <button
                      className="button secondary tiny"
                      onClick={async () => {
                        try {
                          await post(`/workspace/jobs/${selected.id}/runs/${run.id}/cancel`);
                          refresh();
                        } catch (error) {
                          toast((error as Error).message, true);
                        }
                      }}
                    >
                      <Square size={12} />
                      Cancel
                    </button>
                  )}
                  <button
                    className="text-button"
                    onClick={async () => {
                      try {
                        await downloadFile(
                          `/workspace/jobs/${selected.id}/runs/${run.id}`,
                          `sibyl-job-${run.id}.json`,
                        );
                      } catch (error) {
                        toast((error as Error).message, true);
                      }
                    }}
                  >
                    <Download size={13} />
                    Receipt
                  </button>
                </div>
              </div>
            ))
          ) : (
            <Empty title="No retained runs">
              Choose Run once or enable the schedule to start this task.
            </Empty>
          )}
        </Modal>
      )}
    </Panel>
  );
}

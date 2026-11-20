import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { Dices, Play, LoaderCircle, Download, RefreshCw, Trash2 } from 'lucide-react';
import { api, downloadFile, number, post, refresh } from '../../lib/api';
import { useResource } from '../../lib/hooks';
import { queueResearch, type ResearchJobRun } from '../../lib/research-jobs';
import type { Dataset } from '../../lib/market-history';
import type { Backtest, StrategyParams } from '../../lib/types';
import { Badge, ErrorState, useToast } from '../ui';
import { AgentButton } from '../agents';
import { BacktestChart } from './backtest-chart';

type Axis = {
  key: string;
  kind: 'int' | 'float';
  low: number;
  high: number;
  step?: number;
  log?: boolean;
};
type Plugin = {
  id: string;
  status: string;
  revision: string;
  spec?: {
    name: string;
    parameters: Record<string, { kind: 'int' | 'float'; minimum: number; maximum: number }>;
  };
};
type Options = {
  available: boolean;
  library_version: string | null;
  builtin: Record<string, Axis[]>;
  plugins: Plugin[];
  note: string;
};
type Trial = {
  number: number;
  values: Record<string, number>;
  state: string;
  score: number | null;
  metrics?: { return_pct: number; trades: number };
};
type Study = {
  id: string;
  status: string;
  created_at: string;
  dataset: Dataset;
  engine_revision: string;
  decision_fingerprint: string;
  plugin?: { id: string } | null;
  sampler: { name: string; version: string; seed: number; startup_trials: number };
  summary: {
    evaluated_windows: number;
    requested_windows: number;
    mean_return_pct: number | null;
    worst_return_pct: number | null;
    mean_fixed_return_pct: number | null;
  };
  folds: {
    index: number;
    train_end_exclusive: string;
    test_start: string;
    test_bars: number;
    selected: Trial | null;
    trials: Trial[];
    out_of_sample: Backtest | null;
  }[];
  note: string;
};
const title = (key: string) => key.replaceAll('_', ' ');

/** Optional native sampler workspace. Tests remain separate from selection and execution. */
export function AdaptiveWorkspace({
  dataset,
  parameters,
  demo,
}: {
  dataset?: Dataset;
  parameters: StrategyParams;
  demo: boolean;
}) {
  const [open, setOpen] = useState(false);
  const options = useResource<Options>('/strategies/adaptive/options', 0, open);
  const saved = useResource<{
    items: Pick<Study, 'id' | 'created_at' | 'status' | 'dataset' | 'sampler'>[];
  }>(`/strategies/adaptive?demo=${demo}`, 0, open);
  const [engine, setEngine] = useState('builtin');
  const plugin = options.data?.plugins.find(
    (item) => item.id === engine && item.status === 'ready',
  );
  const fields: Axis[] =
    engine === 'builtin'
      ? (options.data?.builtin[parameters.strategy] ?? [])
      : Object.entries(plugin?.spec?.parameters ?? {}).map(([key, value]) => ({
          key,
          kind: value.kind,
          low: value.minimum,
          high: value.maximum,
        }));
  const fieldIdentity = JSON.stringify(fields);
  const [axes, setAxes] = useState<Axis[]>([]);
  const [sampler, setSampler] = useState('tpe');
  const [trials, setTrials] = useState(12);
  const [folds, setFolds] = useState(3);
  const [seed, setSeed] = useState(42);
  const [objective, setObjective] = useState('return_pct');
  const [minimum, setMinimum] = useState(0);
  const [report, setReport] = useState<Study>();
  const [selectedFold, setSelectedFold] = useState(0);
  const [job, setJob] = useState<ResearchJobRun>();
  const run = useResource<ResearchJobRun>(
    `/workspace/jobs/${job?.job_id ?? ''}/runs/${job?.id ?? ''}`,
    1500,
    !!job && ['queued', 'running'].includes(job.state),
  );
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const toast = useToast();
  useEffect(() => {
    setAxes(fields.slice(0, 2));
  }, [fieldIdentity]);
  useEffect(() => {
    if (!run.data || run.data.id !== job?.id) return;
    setJob(run.data);
    if (run.data.state === 'completed' && run.data.result?.report_id) {
      void api<Study>(`/strategies/adaptive/${run.data.result.report_id}`)
        .then((value) => {
          setReport(value);
          setSelectedFold(0);
          saved.retry();
        })
        .catch((reason) => setError((reason as Error).message));
    }
  }, [run.data]);
  const pending = !!job && ['queued', 'running'].includes(job.state);
  const edit = (index: number, patch: Partial<Axis>) =>
    setAxes((current) => current.map((axis, i) => (i === index ? { ...axis, ...patch } : axis)));
  const act = async (action: () => Promise<unknown>) => {
    setBusy(true);
    setError('');
    try {
      await action();
    } catch (reason) {
      setError((reason as Error).message);
    } finally {
      setBusy(false);
    }
  };
  const fold = report?.folds[selectedFold];
  return (
    <details
      className="adaptive-workspace"
      open={open}
      onToggle={(event) => setOpen(event.currentTarget.open)}
    >
      <summary>
        <Dices size={17} />
        <span>
          <strong>Adaptive search</strong>
          <small>Numeric distributions · Bayesian TPE · trusted plugins</small>
        </span>
        <Badge>Advanced research</Badge>
      </summary>
      {open && (
        <div className="adaptive-content">
          {options.error && <ErrorState message={options.error} retry={options.retry} />}
          {options.data?.available === false && (
            <p className="inline-alert">
              Install the optional optimization package on the backend:{' '}
              <code>uv sync --extra optimization</code> or{' '}
              <code>pip install 'sibyl[optimization]'</code>. Saved reports remain readable.
            </p>
          )}
          <label>
            Saved adaptive studies
            <select
              aria-label="Saved adaptive studies"
              value={report?.id ?? ''}
              disabled={busy}
              onChange={(event) => {
                const id = event.target.value;
                if (!id) setReport(undefined);
                else
                  void act(async () => {
                    setReport(await api<Study>(`/strategies/adaptive/${id}`));
                    setSelectedFold(0);
                  });
              }}
            >
              <option value="">New study</option>
              {saved.data?.items.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.dataset.symbol} · {item.sampler.name.toUpperCase()} ·{' '}
                  {new Date(item.created_at).toLocaleDateString()} · {item.id.slice(0, 8)}
                </option>
              ))}
            </select>
          </label>
          {!dataset ? (
            <p className="footnote">
              Run a backtest or choose a retained dataset first. Adaptive search uses that exact
              input; it never fetches a new market source.
            </p>
          ) : (
            <form
              className="form-grid"
              onSubmit={(event) => {
                event.preventDefault();
                void act(async () => {
                  const distributions = Object.fromEntries(
                    axes.map(({ key, ...axis }) => [key, axis]),
                  );
                  const receipt = await queueResearch(
                    'strategy.adaptive',
                    `${engine === 'builtin' ? parameters.strategy : (plugin?.spec?.name ?? engine)} adaptive research`.slice(
                      0,
                      80,
                    ),
                    {
                      dataset_id: dataset.id,
                      parameters: {
                        ...parameters,
                        symbol: dataset.symbol,
                        timeframe: dataset.timeframe,
                        candles: dataset.count,
                      },
                      engine: engine === 'builtin' ? 'builtin' : 'plugin',
                      ...(plugin ? { plugin_id: plugin.id, plugin_revision: plugin.revision } : {}),
                      distributions,
                      sampler,
                      trials,
                      seed,
                      folds,
                      objective,
                      min_train_trades: minimum,
                    },
                  );
                  setJob(receipt);
                  toast('Research queued. You can keep using the workspace.');
                  refresh();
                });
              }}
            >
              <label>
                Algorithm
                <select
                  value={engine}
                  onChange={(event) => setEngine(event.target.value)}
                  disabled={pending}
                >
                  <option value="builtin">{title(parameters.strategy)} · built in</option>
                  {options.data?.plugins
                    .filter((item) => item.status === 'ready')
                    .map((item) => (
                      <option key={item.id} value={item.id}>
                        {item.spec?.name ?? item.id} · trusted plugin
                      </option>
                    ))}
                </select>
              </label>
              <label>
                Search method
                <select
                  value={sampler}
                  onChange={(event) => {
                    setSampler(event.target.value);
                    if (event.target.value === 'tpe' && trials < 8) setTrials(8);
                  }}
                >
                  <option value="tpe">Bayesian · native TPE</option>
                  <option value="random">Random distributions</option>
                </select>
              </label>
              <div className="adaptive-axes">
                {axes.map((axis, index) => (
                  <div className="adaptive-axis" key={index}>
                    <label>
                      Parameter
                      <select
                        value={axis.key}
                        onChange={(event) => {
                          const field = fields.find((item) => item.key === event.target.value);
                          if (field) edit(index, field);
                        }}
                      >
                        {fields
                          .filter(
                            (item) =>
                              item.key === axis.key ||
                              !axes.some((other) => other.key === item.key),
                          )
                          .map((item) => (
                            <option key={item.key} value={item.key}>
                              {title(item.key)}
                            </option>
                          ))}
                      </select>
                    </label>
                    <label>
                      From
                      <input
                        type="number"
                        step={axis.kind === 'int' ? 1 : 'any'}
                        value={axis.low}
                        onChange={(event) => edit(index, { low: Number(event.target.value) })}
                        required
                      />
                    </label>
                    <label>
                      To
                      <input
                        type="number"
                        step={axis.kind === 'int' ? 1 : 'any'}
                        value={axis.high}
                        onChange={(event) => edit(index, { high: Number(event.target.value) })}
                        required
                      />
                    </label>
                    <label>
                      Step · optional
                      <input
                        type="number"
                        step={axis.kind === 'int' ? 1 : 'any'}
                        value={axis.step ?? ''}
                        onChange={(event) =>
                          edit(index, {
                            step: event.target.value ? Number(event.target.value) : undefined,
                          })
                        }
                      />
                    </label>
                    <label className="adaptive-log">
                      <input
                        type="checkbox"
                        checked={axis.log ?? false}
                        onChange={(event) => edit(index, { log: event.target.checked })}
                      />{' '}
                      Log scale
                    </label>
                    <button
                      className="text-button"
                      type="button"
                      aria-label={`Remove ${title(axis.key)} distribution`}
                      disabled={axes.length === 1}
                      onClick={() => setAxes((current) => current.filter((_, i) => i !== index))}
                    >
                      Remove
                    </button>
                  </div>
                ))}
              </div>
              {axes.length < Math.min(4, fields.length) && (
                <button
                  className="text-button"
                  type="button"
                  onClick={() => {
                    const next = fields.find((item) => !axes.some((axis) => axis.key === item.key));
                    if (next) setAxes((current) => [...current, next]);
                  }}
                >
                  Add a distribution
                </button>
              )}
              <label>
                Trials per window
                <input
                  type="number"
                  min={sampler === 'tpe' ? 8 : 4}
                  max={24}
                  value={trials}
                  onChange={(event) => setTrials(Number(event.target.value))}
                  required
                />
              </label>
              <label>
                Later test windows
                <input
                  type="number"
                  min={1}
                  max={5}
                  value={folds}
                  onChange={(event) => setFolds(Number(event.target.value))}
                  required
                />
              </label>
              <label>
                Training objective
                <select value={objective} onChange={(event) => setObjective(event.target.value)}>
                  <option value="return_pct">Net return</option>
                  <option value="sharpe">Sharpe ratio</option>
                  <option value="max_drawdown">Lowest drawdown</option>
                </select>
              </label>
              <label>
                Minimum training trades
                <input
                  type="number"
                  min={0}
                  max={100}
                  value={minimum}
                  onChange={(event) => setMinimum(Number(event.target.value))}
                />
              </label>
              <label>
                Random seed
                <input
                  type="number"
                  min={0}
                  max={4294967295}
                  value={seed}
                  onChange={(event) => setSeed(Number(event.target.value))}
                  required
                />
              </label>
              <p className="footnote">
                First training prefix: 60% of the input. TPE starts with five completed startup
                trials; later choices use training scores only. Independent test windows include
                current cost/stop settings and begin in cash. Every sampled choice stays in the
                report.
              </p>
              <button
                className="button primary"
                type="submit"
                disabled={busy || pending || !axes.length || !options.data?.available}
              >
                {busy ? <LoaderCircle size={15} className="spin" /> : <Play size={15} />} Queue
                research study
              </button>
            </form>
          )}
          {job && (
            <div className="adaptive-job-status" role="status">
              <Badge tone={job.state === 'failed' ? 'rose' : 'neutral'}>
                {pending && <LoaderCircle size={12} className="spin" />}
                {job.state}
              </Badge>
              <span>
                {job.state === 'running'
                  ? 'Testing training prefixes and later windows. The complete trial report appears when finished.'
                  : (job.error ?? 'One-off research job · retained receipt in Workspace.')}
              </span>
              {pending && (
                <button
                  className="text-button"
                  onClick={() =>
                    void act(async () =>
                      setJob(
                        await post<ResearchJobRun>(
                          `/workspace/jobs/${job.job_id}/runs/${job.id}/cancel`,
                        ),
                      ),
                    )
                  }
                >
                  Cancel request
                </button>
              )}
              <Link className="text-link" to="/settings?tab=workspace">
                Job history →
              </Link>
            </div>
          )}
          {error && (
            <p className="form-error" role="alert">
              {error}
            </p>
          )}
          {report && (
            <section className="adaptive-report">
              <div className="adaptive-report-heading">
                <div>
                  <h3>{report.plugin ? title(report.plugin.id) : 'Adaptive strategy study'}</h3>
                  <small>
                    {report.dataset.symbol} · {report.dataset.source_label} · Optuna{' '}
                    {report.sampler.version} · seed {report.sampler.seed}
                  </small>
                </div>
                <Badge tone={report.status === 'completed' ? 'neutral' : 'rose'}>
                  {report.status === 'completed' ? 'Recorded tests' : 'No eligible candidates'}
                </Badge>
              </div>
              <div className="adaptive-summary">
                {[
                  ['Mean test return', report.summary.mean_return_pct],
                  ['Worst test return', report.summary.worst_return_pct],
                  ['Fixed-settings return', report.summary.mean_fixed_return_pct],
                ].map(([label, value]) => (
                  <div key={String(label)}>
                    <small>{label}</small>
                    <strong>
                      {value === null ? 'Unavailable' : `${number(Number(value), 2)}%`}
                    </strong>
                  </div>
                ))}
              </div>
              <label>
                Inspect window
                <select
                  aria-label="Inspect adaptive window"
                  value={selectedFold}
                  onChange={(event) => setSelectedFold(Number(event.target.value))}
                >
                  {report.folds.map((item, index) => (
                    <option value={index} key={item.index}>
                      Window {item.index} · test from{' '}
                      {new Date(item.test_start).toLocaleDateString()}
                    </option>
                  ))}
                </select>
              </label>
              {fold && (
                <>
                  <p className="footnote">
                    Training ends before {new Date(fold.train_end_exclusive).toLocaleDateString()}.{' '}
                    {fold.test_bars} later bars are held outside this window’s sampler.
                  </p>
                  <div className="table-wrap adaptive-trials">
                    <table>
                      <thead>
                        <tr>
                          <th>Trial</th>
                          <th>Sampled settings</th>
                          <th>Training state</th>
                          <th>Training score</th>
                          <th>Trades</th>
                        </tr>
                      </thead>
                      <tbody>
                        {fold.trials.map((trial) => (
                          <tr
                            key={trial.number}
                            className={
                              fold.selected?.number === trial.number
                                ? 'adaptive-selected-trial'
                                : ''
                            }
                          >
                            <td>
                              {trial.number + 1}
                              {fold.selected?.number === trial.number ? ' · Selected' : ''}
                            </td>
                            <td>
                              {Object.entries(trial.values)
                                .map(([key, value]) => `${title(key)} ${number(value, 3)}`)
                                .join(' · ')}
                            </td>
                            <td>{title(trial.state)}</td>
                            <td>{trial.score === null ? '—' : number(trial.score, 4)}</td>
                            <td>{trial.metrics?.trades ?? '—'}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                  {fold.out_of_sample && (
                    <BacktestChart key={`${report.id}-${fold.index}`} result={fold.out_of_sample} />
                  )}
                </>
              )}
              <AgentButton
                module="broker"
                context={{ adaptive_study_id: report.id, adaptive_window: selectedFold + 1 }}
              />
              <p className="footnote">{report.note}</p>
              <div className="toolbar">
                <button
                  className="button secondary tiny"
                  onClick={() =>
                    void act(() =>
                      downloadFile(
                        `/strategies/adaptive/${report.id}`,
                        `sibyl-adaptive-${report.id}.json`,
                      ),
                    )
                  }
                >
                  <Download size={13} /> Export trial evidence
                </button>
                <button
                  className="button secondary tiny"
                  disabled={busy || !options.data?.available}
                  onClick={() =>
                    void act(async () => {
                      setReport(await post<Study>(`/strategies/adaptive/${report.id}/rerun`, {}));
                      saved.retry();
                    })
                  }
                >
                  <RefreshCw size={13} /> Replay exact study
                </button>
                <button
                  className="text-button"
                  disabled={busy}
                  onClick={() =>
                    void act(async () => {
                      await api(`/strategies/adaptive/${report.id}`, { method: 'DELETE' });
                      setReport(undefined);
                      saved.retry();
                    })
                  }
                >
                  <Trash2 size={13} /> Remove artifact
                </button>
              </div>
            </section>
          )}
          <p className="footnote">
            {options.data?.note} Cancelling a request stops result interest; a local calculation
            already running can finish and retain an artifact. No successful late job receipt is
            published.
          </p>
        </div>
      )}
    </details>
  );
}

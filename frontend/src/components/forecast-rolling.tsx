import { useEffect, useRef, useState } from 'react';
import { Download, LoaderCircle, Play, RefreshCw } from 'lucide-react';
import { number, post, api } from '../lib/api';
import { useResource } from '../lib/hooks';
import type {
  ForecastModel,
  RollingHeader,
  RollingReport,
  RollingRequest,
} from '../lib/forecast-types';
import { Badge, ErrorState } from './ui';
import { ForecastPlot } from './forecast-plot';
import './forecast-rolling.css';

const date = (value: string) =>
  new Date(value).toLocaleDateString(undefined, {
    timeZone: 'UTC',
    day: 'numeric',
    month: 'short',
    year: 'numeric',
  });
const skill = (value: number | null) => (value == null ? '—' : `${number(value, 1)}%`);

/** Explicit offline research; each selected model owns its form, report and request state. */
export function ForecastRolling({
  model,
  evaluationId,
  select,
  disabled,
}: {
  model: ForecastModel;
  evaluationId: string;
  select: (id: string) => void;
  disabled: boolean;
}) {
  const [open, setOpen] = useState(!!evaluationId);
  const [settings, setSettings] = useState<RollingRequest>({
    horizon: Math.min(7, model.parameters.max_horizon),
    folds: 2,
    test_days: 60,
    calibration_days: 60,
    window: 'expanding',
  });
  const [trainingDays, setTrainingDays] = useState(180);
  const [busy, setBusy] = useState('');
  const [error, setError] = useState('');
  const alive = useRef(true);
  useEffect(() => {
    alive.current = true;
    return () => {
      alive.current = false;
    };
  }, []);
  useEffect(() => {
    if (evaluationId) setOpen(true);
  }, [evaluationId]);
  const history = useResource<{ items: RollingHeader[]; limit: number; workspace_limit: number }>(
    `/forecast-models/${model.id}/evaluations`,
    0,
    open,
  );
  const report = useResource<RollingReport>(
    `/forecast-models/evaluations/${evaluationId}`,
    0,
    open && !!evaluationId,
  );
  const selected = report.data?.model_id === model.id ? report.data : undefined;
  const run = async (request: RollingRequest) => {
    setBusy('run');
    setError('');
    try {
      const result = await post<RollingReport>(`/forecast-models/${model.id}/evaluations`, request);
      if (!alive.current) return;
      history.retry();
      select(result.id);
    } catch (reason) {
      if (alive.current) setError((reason as Error).message);
    } finally {
      if (alive.current) setBusy('');
    }
  };
  const exportReport = async () => {
    setBusy('export');
    setError('');
    try {
      const value = await api<RollingReport>(`/forecast-models/evaluations/${evaluationId}`);
      if (!alive.current) return;
      if (value.model_id !== model.id)
        throw Error('This evaluation belongs to a different model version.');
      const url = URL.createObjectURL(
        new Blob([JSON.stringify(value, null, 2)], { type: 'application/json' }),
      );
      const anchor = document.createElement('a');
      anchor.href = url;
      anchor.download = `chronos-rolling-${value.id}.json`;
      anchor.click();
      URL.revokeObjectURL(url);
    } catch (reason) {
      if (alive.current) setError((reason as Error).message);
    } finally {
      if (alive.current) setBusy('');
    }
  };
  const request: RollingRequest = {
    ...settings,
    ...(settings.window === 'rolling' ? { training_days: trainingDays } : {}),
  };
  const lags = model.parameters.lags ?? 0;
  const minimumTrain =
    model.parameters.family === 'arima'
      ? 120
      : lags +
        Math.max(60, 3 * (lags + (model.parameters.feature_set === 'returns_context' ? 6 : 0))) +
        settings.horizon;
  const availableTrain =
    model.dataset.count - settings.folds * settings.test_days - settings.calibration_days;
  const validNumbers =
    Number.isInteger(settings.folds) &&
    settings.folds >= 2 &&
    settings.folds <= 8 &&
    Number.isInteger(settings.test_days) &&
    settings.test_days <= 180 &&
    Number.isInteger(settings.calibration_days) &&
    settings.calibration_days <= 365 &&
    (settings.window !== 'rolling' ||
      (Number.isInteger(trainingDays) && trainingDays >= 120 && trainingDays <= 2000));
  const enough =
    validNumbers &&
    availableTrain >= minimumTrain &&
    Math.min(settings.test_days, settings.calibration_days) >= settings.horizon + 20 &&
    (settings.window !== 'rolling' ||
      (trainingDays >= minimumTrain && trainingDays <= availableTrain));
  return (
    <details
      className="forecast-rolling"
      open={open}
      onToggle={(event) => setOpen(event.currentTarget.open)}
    >
      <summary>
        <div>
          <strong>Rolling evaluation</strong>
          <span>Refit earlier windows, score later periods</span>
        </div>
        <Badge>Offline research</Badge>
      </summary>
      {open && (
        <div className="forecast-rolling-body">
          <p className="footnote">
            Uses this version’s frozen dataset and fixed recipe. Each fold fits fresh coefficients
            and calibration bands; your saved model remains unchanged.
          </p>
          <div className="forecast-rolling-form">
            <label>
              Evaluation horizon
              <select
                disabled={!!busy}
                value={settings.horizon}
                onChange={(event) =>
                  setSettings({ ...settings, horizon: Number(event.target.value) })
                }
              >
                {Array.from({ length: model.parameters.max_horizon }, (_, i) => i + 1).map((h) => (
                  <option value={h} key={h}>
                    {h} {h === 1 ? 'day' : 'days'}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Successive test windows
              <input
                disabled={!!busy}
                type="number"
                min={2}
                max={8}
                step={1}
                value={settings.folds}
                onChange={(event) =>
                  setSettings({ ...settings, folds: Number(event.target.value) })
                }
              />
            </label>
            <label>
              Test days per fold
              <input
                disabled={!!busy}
                type="number"
                min={21}
                max={180}
                step={1}
                value={settings.test_days}
                onChange={(event) =>
                  setSettings({ ...settings, test_days: Number(event.target.value) })
                }
              />
            </label>
            <label>
              Calibration days
              <input
                disabled={!!busy}
                type="number"
                min={21}
                max={365}
                step={1}
                value={settings.calibration_days}
                onChange={(event) =>
                  setSettings({ ...settings, calibration_days: Number(event.target.value) })
                }
              />
            </label>
          </div>
          <details className="forecast-rolling-window">
            <summary>Training window</summary>
            <label>
              Window policy
              <select
                disabled={!!busy}
                value={settings.window}
                onChange={(event) =>
                  setSettings({
                    ...settings,
                    window: event.target.value as RollingRequest['window'],
                  })
                }
              >
                <option value="expanding">Expanding · all earlier training history</option>
                <option value="rolling">Fixed window · recent training days</option>
              </select>
            </label>
            {settings.window === 'rolling' && (
              <label>
                Training days per fold
                <input
                  disabled={!!busy}
                  type="number"
                  min={120}
                  max={2000}
                  step={1}
                  value={trainingDays}
                  onChange={(event) => setTrainingDays(Number(event.target.value))}
                />
              </label>
            )}
          </details>
          <p className="footnote">
            {model.dataset.count} saved daily candles · at least {minimumTrain} training days
            required before calibration. Targets crossing a boundary are excluded.
          </p>
          {!enough && (
            <p className="form-error">
              Choose whole-day windows within the displayed limits. Use fewer folds, shorter windows
              or more input; calibration and testing each need at least horizon + 20 days.
            </p>
          )}
          <div className="forecast-rolling-actions">
            <button
              className="button secondary"
              disabled={disabled || !!busy || !enough}
              onClick={() => void run(request)}
            >
              {busy === 'run' ? <LoaderCircle size={14} className="spin" /> : <Play size={14} />}{' '}
              {busy === 'run' ? 'Evaluating windows…' : 'Run rolling evaluation'}
            </button>
            <small>No provider reads · latest 10 reports per model / 100 workspace-wide</small>
          </div>
          {error && (
            <p className="form-error" role="alert">
              {error}
            </p>
          )}
          {history.error && <ErrorState message={history.error} retry={history.retry} />}
          {!!history.data?.items.length && (
            <label className="forecast-rolling-history">
              Saved rolling evaluation
              <select value={evaluationId} onChange={(event) => select(event.target.value)}>
                <option value="">Choose a retained report…</option>
                {history.data.items.map((row) => (
                  <option value={row.id} key={row.id}>
                    {new Date(row.created_at).toLocaleString()} · {row.request.horizon}d ·{' '}
                    {row.request.folds} folds · {row.request.window} ·{' '}
                    {skill(row.aggregate.mae_skill_vs_naive_pct)} skill · {row.id.slice(0, 6)}
                  </option>
                ))}
              </select>
            </label>
          )}
          {evaluationId && report.loading && (
            <p className="footnote" role="status">
              Reading saved evaluation…
            </p>
          )}
          {report.error && <ErrorState message={report.error} retry={report.retry} />}
          {report.data && !selected && (
            <p className="form-error">
              This evaluation belongs to a different model version. Select one from this model’s
              retained reports.
            </p>
          )}
          {selected && (
            <>
              <div className="forecast-rolling-actions">
                <Badge tone={selected.environment === 'demo' ? 'purple' : 'neutral'}>
                  {selected.environment === 'demo' ? 'Demo · synthetic input' : selected.source}
                </Badge>
                <span className="footnote">
                  {date(selected.created_at)} · {selected.request.horizon}-day targets ·{' '}
                  {selected.result.engine}
                </span>
                <button
                  className="text-button"
                  disabled={disabled || !!busy}
                  onClick={() => void run(selected.request)}
                >
                  <RefreshCw size={12} /> Rerun exact evaluation
                </button>
                <button
                  className="text-button"
                  disabled={!!busy}
                  onClick={() => void exportReport()}
                >
                  <Download size={12} /> Export rolling evidence
                </button>
              </div>
              <p className="footnote">
                Saved plan: {selected.request.folds} × {selected.request.test_days}-day test windows
                · {selected.request.calibration_days} calibration days ·{' '}
                {selected.request.window === 'rolling'
                  ? `${selected.request.training_days}-day fixed training`
                  : 'expanding training'}
                .
              </p>
              <RollingResults key={selected.id} report={selected} />
            </>
          )}
        </div>
      )}
    </details>
  );
}

function RollingResults({ report }: { report: RollingReport }) {
  const [index, setIndex] = useState(0);
  const { result } = report;
  const fold = result.folds[index] ?? result.folds[0];
  return (
    <div className="forecast-rolling-results">
      <div className="forecast-rolling-metrics">
        <div>
          <small>Pooled MAE skill vs naïve</small>
          <strong>{skill(result.aggregate.mae_skill_vs_naive_pct)}</strong>
          <span>{result.aggregate.samples} held-out targets</span>
        </div>
        <div>
          <small>Observed band coverage</small>
          <strong>{skill(result.aggregate.coverage_pct)}</strong>
          <span>Nominal 90% · no future guarantee</span>
        </div>
        <div>
          <small>Folds beating naïve MAE</small>
          <strong>
            {result.aggregate.positive_skill_folds} / {result.folds.length}
          </strong>
          <span>Historical recipe evaluation</span>
        </div>
      </div>
      <div className="table-scroll">
        <table>
          <thead>
            <tr>
              <th>Window</th>
              <th>Targets</th>
              <th>Model MAE</th>
              <th>Naïve MAE</th>
              <th>Drift MAE</th>
              <th>Skill</th>
              <th>Coverage</th>
            </tr>
          </thead>
          <tbody>
            {result.folds.map((item) => (
              <tr key={item.index}>
                <td>
                  {date(item.partitions.test.start)} → {date(item.partitions.test.end)}
                </td>
                <td>{item.evaluation.samples}</td>
                <td>{number(item.evaluation.model.mae, 4)}</td>
                <td>{number(item.evaluation.naive.mae, 4)}</td>
                <td>{number(item.evaluation.drift.mae, 4)}</td>
                <td>{skill(item.evaluation.mae_skill_vs_naive_pct)}</td>
                <td>{skill(item.evaluation.coverage_pct)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <label className="forecast-rolling-fold">
        Inspect fold
        <select value={index} onChange={(event) => setIndex(Number(event.target.value))}>
          {result.folds.map((item, i) => (
            <option key={item.index} value={i}>
              Fold {item.index} · {date(item.partitions.test.start)} →{' '}
              {date(item.partitions.test.end)}
            </option>
          ))}
        </select>
      </label>
      <div className="forecast-partitions">
        {Object.entries(fold.partitions).map(([name, part]) => (
          <div key={name}>
            <strong>{name}</strong>
            <span>
              {date(part.start)} → {date(part.end)}
            </span>
            <small>{part.candles} candles · end exclusive</small>
          </div>
        ))}
      </div>
      <ForecastPlot points={fold.evaluation.trace} testing showDrift />
      <p className="footnote">
        Fold {fold.index}: RMSE {number(fold.evaluation.model.rmse, 4)} · MAPE{' '}
        {skill(fold.evaluation.model.mape_pct)} · mean band width{' '}
        {skill(fold.evaluation.mean_interval_width_pct)}. Errors are in{' '}
        {report.symbol.split('/')[1]} quote units.{' '}
        {fold.evaluation.overlapping_targets
          ? 'Multi-day target windows overlap.'
          : 'One-day targets.'}
      </p>
      <details className="forecast-rolling-notes">
        <summary>Interpretation & reproducibility</summary>
        {result.notes.map((note) => (
          <p key={note}>{note}</p>
        ))}
        <p>
          Result fingerprint: <code>{report.result_fingerprint}</code>
        </p>
      </details>
    </div>
  );
}

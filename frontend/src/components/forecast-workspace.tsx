import { ForecastPortability } from './forecast-portability';
import { useEffect, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import {
  ArrowUpRight,
  Download,
  FlaskConical,
  LoaderCircle,
  Play,
  RefreshCw,
  Sparkles,
} from 'lucide-react';
import { AgentButton } from './agents';
import { ForecastPlot } from './forecast-plot';
import { ForecastDrift } from './forecast-drift';
import { ForecastForward } from './forecast-forward';
import { ForecastRolling } from './forecast-rolling';
import { Badge, Empty, ErrorState, Loading, Panel, PanelTitle, useToast } from './ui';
import { api, number, post } from '../lib/api';
import { useResource } from '../lib/hooks';
import type {
  ForecastDataset,
  ForecastDetail,
  ForecastModel,
  ForecastOutput,
} from '../lib/forecast-types';

function downloadJSON(name: string, value: unknown) {
  const url = URL.createObjectURL(
    new Blob([JSON.stringify(value, null, 2)], { type: 'application/json' }),
  );
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = name;
  anchor.click();
  URL.revokeObjectURL(url);
}

function researchDate(value: string) {
  return new Date(value).toLocaleDateString(undefined, {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
    timeZone: 'UTC',
  });
}

/** Explicit train/evaluate/forecast steps; a saved model never starts trading. */
export function ForecastWorkspace() {
  const [search, setSearch] = useSearchParams();
  const [showArchived, setShowArchived] = useState(false);
  const models = useResource<{ items: ForecastModel[] }>(
    `/forecast-models?include_archived=${showArchived}`,
  );
  const selected = search.get('model') ?? models.data?.items[0]?.id ?? '';
  const metadata = models.data?.items.find((m) => m.id === selected);
  const selectedEvaluation = search.get('evaluation') ?? '';
  const [horizon, setHorizon] = useState(7);
  const activeHorizon = Math.min(horizon, metadata?.parameters.max_horizon ?? 30);
  const detail = useResource<ForecastDetail>(
    `/forecast-models/${encodeURIComponent(selected)}?horizon=${activeHorizon}`,
    0,
    !!selected,
  );
  const datasets = useResource<{ items: ForecastDataset[]; total: number }>(
    '/market-history/datasets',
  );
  const [trainingOpen, setTrainingOpen] = useState(false);
  const [label, setLabel] = useState('Daily autoregression');
  const [input, setInput] = useState<'current_feed' | 'saved_dataset'>('current_feed');
  const [datasetId, setDatasetId] = useState('');
  const [symbol, setSymbol] = useState('BTC/USDT');
  const [lags, setLags] = useState(14);
  const [family, setFamily] = useState<'ridge' | 'mlp'>('ridge');
  const [alpha, setAlpha] = useState(1);
  const [featureSet, setFeatureSet] = useState<'returns' | 'returns_context'>('returns');
  const [maxHorizon, setMaxHorizon] = useState(30);
  const [candles, setCandles] = useState(720);
  const [output, setOutput] = useState<ForecastOutput>();
  const [busy, setBusy] = useState('');
  const [error, setError] = useState('');
  const toast = useToast();
  const choose = (id: string) => {
    setSearch((p) => {
      p.set('tab', 'models');
      p.set('model', id);
      p.delete('evaluation');
      return p;
    });
    setOutput(undefined);
    setError('');
  };
  const availableDatasets =
    datasets.data?.items.filter(
      (d) => d.timeframe === '1d' && d.count >= 360 && d.count <= (family === 'mlp' ? 1000 : 5000),
    ) ?? [];
  const doTrain = async (demo = false) => {
    setBusy('train');
    setError('');
    try {
      const dataset = availableDatasets.find((d) => d.id === datasetId);
      const result = await post<ForecastDetail>('/forecast-models', {
        label: demo ? 'Demo · daily autoregression' : label,
        input_kind: demo ? 'demo' : input,
        ...(input === 'saved_dataset' && !demo ? { dataset_id: datasetId } : {}),
        symbol: input === 'saved_dataset' && !demo ? dataset?.symbol : symbol.toUpperCase().trim(),
        candles: input === 'saved_dataset' && !demo ? dataset?.count : candles,
        lags,
        family,
        alpha,
        max_horizon: maxHorizon,
        feature_set: featureSet,
      });
      models.retry();
      datasets.retry();
      choose(result.model.id);
      setTrainingOpen(false);
      toast('Model fitted. Independent test results and calibration evidence are saved.');
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy('');
    }
  };
  const action = async (kind: 'saved_input' | 'current_feed' | 'rerun' | 'export') => {
    setBusy(kind);
    setError('');
    try {
      if (kind === 'rerun') {
        const result = await post<ForecastDetail>(`/forecast-models/${selected}/rerun`);
        models.retry();
        choose(result.model.id);
        toast('New model version fitted from the exact original input.');
      } else if (kind === 'export') {
        const result = await api(`/forecast-models/${selected}/export`);
        downloadJSON(`chronos-model-${selected}.json`, result);
      } else {
        const result = await post<ForecastOutput>(`/forecast-models/${selected}/forecasts`, {
          input_kind: kind,
          horizon: activeHorizon,
        });
        setOutput(result);
        detail.retry();
        toast('Forecast saved with its exact observation window.');
      }
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy('');
    }
  };
  const report = detail.data;
  useEffect(() => {
    if (report?.model.archived) setShowArchived(true);
  }, [report?.model.id, report?.model.archived]);
  const evaluation = report?.evaluation.find((e) => e.horizon === activeHorizon);
  const activeOutput = output?.model_id === selected ? output : undefined;
  const forecastPoints = activeOutput
    ? [
        ...activeOutput.observations.candles.slice(-30).map((c) => ({
          timestamp: new Date(new Date(c.timestamp).getTime() + 86_400_000).toISOString(),
          actual: c.close,
        })),
        ...activeOutput.points,
      ]
    : [];
  const training = (
    <Panel className="forecast-training-panel">
      <PanelTitle
        title="Train a daily model"
        subtitle="Train a numerical price model · no LLM or additional ML dependencies"
        action={<Badge>60 / 20 / 20</Badge>}
      />
      <p className="footnote">
        Fit on earlier observations, calibrate on the next window, then measure untouched later
        targets. The test window never chooses coefficients or band widths.
      </p>
      <div className="forecast-training-grid">
        <label>
          Model label
          <input value={label} maxLength={80} onChange={(e) => setLabel(e.target.value)} />
        </label>
        <label>
          Research input
          <select value={input} onChange={(e) => setInput(e.target.value as typeof input)}>
            <option value="current_feed">Current market feed</option>
            <option value="saved_dataset">Saved daily dataset</option>
          </select>
        </label>
        {input === 'saved_dataset' ? (
          <label className="forecast-field-wide">
            Daily dataset
            <select value={datasetId} onChange={(e) => setDatasetId(e.target.value)}>
              <option value="">Choose a saved dataset…</option>
              {availableDatasets.map((d) => (
                <option value={d.id} key={d.id}>
                  {d.label} · {d.symbol} · {d.source_label} · {d.count} candles
                </option>
              ))}
            </select>
            <small>
              {datasets.error ||
                'Uses the entire immutable dataset. Ridge accepts 360–5,000 consecutive daily candles; the small neural model accepts up to 1,000.'}
            </small>
          </label>
        ) : (
          <>
            <label>
              Exact spot pair
              <input
                value={symbol}
                onChange={(e) => setSymbol(e.target.value)}
                placeholder="BTC/USDT"
              />
            </label>
            <label>
              Daily observations
              <select value={candles} onChange={(e) => setCandles(Number(e.target.value))}>
                {[360, 540, 720].map((n) => (
                  <option value={n} key={n}>
                    {n} candles
                  </option>
                ))}
              </select>
            </label>
          </>
        )}
      </div>
      <details className="forecast-advanced">
        <summary>Model settings & assumptions</summary>
        <div className="forecast-training-grid">
          <label>
            Numerical model
            <select
              value={family}
              onChange={(e) => {
                const next = e.target.value as typeof family;
                setFamily(next);
                if (next === 'mlp') setMaxHorizon((h) => Math.min(h, 14));
                setDatasetId('');
              }}
            >
              <option value="ridge">Ridge · linear autoregression</option>
              <option value="mlp">Small neural network · 8 tanh units</option>
            </select>
          </label>
          <label>
            Price features
            <select
              value={featureSet}
              onChange={(e) => setFeatureSet(e.target.value as typeof featureSet)}
            >
              <option value="returns">Daily return lags</option>
              <option value="returns_context">Returns + trend &amp; volatility</option>
            </select>
          </label>
          <label>
            Daily return lags
            <select value={lags} onChange={(e) => setLags(Number(e.target.value))}>
              {[5, 14, 30].map((n) => (
                <option key={n} value={n}>
                  {n} lags
                </option>
              ))}
            </select>
          </label>
          <label>
            Regularization penalty
            <input
              type="number"
              min="0.01"
              max="1000"
              step="0.1"
              value={alpha}
              onChange={(e) => setAlpha(Number(e.target.value))}
            />
          </label>
          <label>
            Maximum forecast horizon
            <select value={maxHorizon} onChange={(e) => setMaxHorizon(Number(e.target.value))}>
              {(family === 'mlp' ? [7, 14] : [7, 14, 30]).map((n) => (
                <option key={n} value={n}>
                  {n} days
                </option>
              ))}
            </select>
          </label>
        </div>
        <p className="footnote">
          Optional context adds mean return, volatility, downside RMS, positive-return share,
          drawdown and distance from the trailing mean, using only the same past window. Extra
          features are not guaranteed to improve results. The optional neural model uses 8 tanh
          units, a fixed seed and 120 full-batch Adam steps, with training-only scaling and a
          1,000-candle / 14-day limit. It may perform worse than ridge or the naïve baseline. Each
          horizon is fitted separately. No final full-data refit or automatic best-model selection.
          Repeated experiments can overfit the test period.
        </p>
      </details>
      <div className="forecast-workspace-actions">
        <button
          className="button primary"
          disabled={!!busy || (input === 'saved_dataset' && !datasetId)}
          onClick={() => void doTrain()}
        >
          {busy === 'train' ? (
            <LoaderCircle className="spin" size={15} />
          ) : (
            <FlaskConical size={15} />
          )}
          {busy === 'train' ? 'Fitting & evaluating…' : 'Train & evaluate'}
        </button>
        <Link className="text-link" to="/markets?tab=history">
          Prepare longer datasets <ArrowUpRight size={12} />
        </Link>
      </div>
      <p className="forecast-demo-option">
        Just exploring?{' '}
        <button className="text-button" disabled={!!busy} onClick={() => void doTrain(true)}>
          Try with Demo prices
        </button>{' '}
        · synthetic input through the same training engine.
      </p>
    </Panel>
  );
  return (
    <div className="forecast-model-workspace">
      <Panel className="forecast-model-picker">
        <PanelTitle
          title="Your trained models"
          subtitle="Versioned research · exact source and immutable input"
          action={
            <button
              className="button secondary"
              disabled={!!busy}
              onClick={() => setTrainingOpen(!trainingOpen)}
            >
              <FlaskConical size={14} />
              {trainingOpen ? 'Close setup' : 'Train model'}
            </button>
          }
        />
        {models.error ? (
          <ErrorState message={models.error} retry={models.retry} />
        ) : models.loading ? (
          <Loading />
        ) : models.data?.items.length ? (
          <label>
            Saved model version
            <select value={selected} onChange={(e) => choose(e.target.value)}>
              {models.data.items.map((m) => (
                <option key={m.id} value={m.id}>
                  {m.archived ? 'Archived · ' : ''}
                  {m.label} · v{m.version} · {m.symbol} ·{' '}
                  {m.environment === 'demo' ? 'Demo' : m.dataset.source_label} ·{' '}
                  {new Date(m.created_at).toLocaleString()}
                </option>
              ))}
            </select>
          </label>
        ) : (
          <Empty title="No models in this view">
            Choose a daily dataset or your current feed to fit a model and see its independent
            evaluation, or show archived versions from Model library. A language model is not
            required.
          </Empty>
        )}
      </Panel>
      <ForecastPortability
        model={report?.model}
        showArchived={showArchived}
        setShowArchived={(value) => {
          setShowArchived(value);
          if (!value && report?.model.archived) {
            setSearch((p) => {
              p.delete('model');
              p.delete('evaluation');
              return p;
            });
            setOutput(undefined);
          }
        }}
        changed={(id) => {
          models.retry();
          datasets.retry();
          detail.retry();
          if (id) choose(id);
        }}
      />
      {(trainingOpen || !models.data?.items.length) && training}
      {error && (
        <p className="form-error" role="alert">
          {error}
        </p>
      )}
      {selected &&
        (detail.loading ? (
          <Loading />
        ) : detail.error ? (
          <ErrorState message={detail.error} retry={detail.retry} />
        ) : (
          report && (
            <>
              <Panel>
                <PanelTitle
                  title={`${report.model.label} · version ${report.model.version}`}
                  subtitle={`${report.model.symbol} · ${report.model.dataset.source_label} · ${report.model.dataset.count} daily candles`}
                  action={
                    <AgentButton
                      module="chronos"
                      context={{
                        symbol: report.model.symbol,
                        horizon: activeHorizon,
                        forecast_model_id: selected,
                        ...(selectedEvaluation
                          ? { forecast_evaluation_id: selectedEvaluation }
                          : {}),
                        ...(activeOutput ? { forecast_run_id: activeOutput.id } : {}),
                      }}
                    />
                  }
                />
                <div className="forecast-model-attribution">
                  <Badge tone={report.model.environment === 'demo' ? 'amber' : 'blue'}>
                    {report.model.archived
                      ? 'Archived model'
                      : report.model.environment === 'imported'
                        ? 'Imported · unverified source'
                        : report.model.environment === 'demo'
                          ? 'Demo · synthetic training input'
                          : 'Trained · research model'}
                  </Badge>
                  <span>
                    {report.model.engine} · lags {report.model.parameters.lags} · penalty{' '}
                    {report.model.parameters.alpha} ·{' '}
                    {report.model.parameters.feature_set === 'returns_context'
                      ? 'Returns + 6 context features'
                      : 'Return lags only'}
                  </span>
                  <code title={report.model.fingerprint}>
                    {report.model.fingerprint.slice(0, 14)}…
                  </code>
                </div>
                {report.training && (
                  <details className="forecast-advanced">
                    <summary>Neural training evidence</summary>
                    <p className="footnote">
                      Training objective only · lower loss does not establish held-out skill. Fixed
                      iterations; the test window never chooses weights.
                    </p>
                    <div className="table-wrap">
                      <table>
                        <thead>
                          <tr>
                            <th>Horizon</th>
                            <th>Architecture</th>
                            <th>Optimizer</th>
                            <th>Initial loss</th>
                            <th>Final loss</th>
                          </tr>
                        </thead>
                        <tbody>
                          {report.training.map((fit) => (
                            <tr key={fit.horizon}>
                              <td>{fit.horizon}d</td>
                              <td>{fit.hidden_units} tanh units</td>
                              <td>
                                {fit.epochs} steps · {fit.optimizer}
                              </td>
                              <td>{number(fit.initial_loss, 5)}</td>
                              <td>{number(fit.final_loss, 5)}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </details>
                )}
                <div className="forecast-partitions">
                  {Object.entries(report.partitions).map(([key, value]) => (
                    <div key={key}>
                      <strong>{key}</strong>
                      <span>
                        {researchDate(value.start)} → {researchDate(value.end)}
                      </span>
                      <small>{value.candles} candles · end exclusive</small>
                    </div>
                  ))}
                </div>
                <div className="forecast-workspace-actions">
                  <label>
                    Evaluation / forecast horizon
                    <select
                      value={activeHorizon}
                      onChange={(e) => {
                        setHorizon(Number(e.target.value));
                        setOutput(undefined);
                      }}
                    >
                      {Array.from(
                        { length: report.model.parameters.max_horizon },
                        (_, i) => i + 1,
                      ).map((n) => (
                        <option key={n} value={n}>
                          {n} {n === 1 ? 'day' : 'days'}
                        </option>
                      ))}
                    </select>
                  </label>
                  <button
                    className="text-button"
                    disabled={!!busy}
                    onClick={() => void action('rerun')}
                  >
                    <RefreshCw size={13} />
                    Rerun exact training input
                  </button>
                  <button
                    className="text-button"
                    disabled={!!busy}
                    onClick={() => void action('export')}
                  >
                    <Download size={13} />
                    Export model & evidence
                  </button>
                </div>
              </Panel>
              {evaluation && (
                <Panel>
                  <PanelTitle
                    title="Independent test results"
                    subtitle={`${evaluation.samples} forecast origins · ${activeHorizon}-day targets${evaluation.overlapping_targets ? ' · overlapping target windows' : ''}`}
                    action={<Badge>Held out</Badge>}
                  />
                  <div className="forecast-metrics">
                    <div>
                      <small>MAE vs naïve</small>
                      <strong>
                        {evaluation.mae_skill_vs_naive_pct == null
                          ? '—'
                          : `${number(evaluation.mae_skill_vs_naive_pct, 1)}%`}
                      </strong>
                      <span>Positive means lower error; negative means worse</span>
                    </div>
                    <div>
                      <small>Observed band coverage</small>
                      <strong>{number(evaluation.coverage_pct, 1)}%</strong>
                      <span>
                        Nominal 90% · mean width {number(evaluation.mean_interval_width_pct, 1)}% of
                        actual target price
                      </span>
                    </div>
                    <div>
                      <small>Mean absolute percentage error</small>
                      <strong>{number(evaluation.model.mape_pct, 2)}%</strong>
                      <span>Error magnitude, not investment return</span>
                    </div>
                  </div>
                  <div className="table-wrap">
                    <table>
                      <thead>
                        <tr>
                          <th>Method</th>
                          <th>MAE · {report.model.symbol.split('/')[1]}</th>
                          <th>RMSE</th>
                          <th>MAPE</th>
                        </tr>
                      </thead>
                      <tbody>
                        {(['model', 'naive', 'drift'] as const).map((method) => (
                          <tr key={method}>
                            <td>
                              {
                                {
                                  model:
                                    report.model.parameters.family === 'mlp'
                                      ? 'Trained neural model'
                                      : 'Trained ridge model',
                                  naive: 'Naïve · last close',
                                  drift: 'Training-mean log drift',
                                }[method]
                              }
                            </td>
                            <td>{number(evaluation[method].mae, 4)}</td>
                            <td>{number(evaluation[method].rmse, 4)}</td>
                            <td>{number(evaluation[method].mape_pct, 2)}%</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                  <ForecastPlot points={report.test_trace} testing />
                  <p className="footnote">
                    Metrics use all test observations. The chart displays at most 400 samples. The
                    calibrated band is fixed before testing; time-series dependence prevents a
                    guaranteed future coverage rate.
                  </p>
                </Panel>
              )}
              {report.model.environment === 'imported' && (
                <p className="notice">
                  {report.model.imported_from?.method ??
                    'Imported source origin remains unverified after local refitting.'}{' '}
                  Imported models use saved input only and cannot become live tracking evidence.
                </p>
              )}
              <ForecastDrift key={`drift:${selected}`} modelId={selected} />
              <ForecastForward key={selected} modelId={selected} outputs={report.outputs} />
              <ForecastRolling
                key={selected}
                model={report.model}
                evaluationId={selectedEvaluation}
                disabled={!!busy}
                select={(id) =>
                  setSearch((p) => {
                    p.set('tab', 'models');
                    p.set('model', selected);
                    id ? p.set('evaluation', id) : p.delete('evaluation');
                    return p;
                  })
                }
              />
              <Panel>
                <PanelTitle
                  title="Produce a forecast"
                  subtitle="Uses the saved coefficients; no retraining or trading"
                  action={<Sparkles size={17} />}
                />
                <div className="forecast-workspace-actions">
                  <button
                    className="button primary"
                    disabled={!!busy || report.model.archived}
                    onClick={() => void action('saved_input')}
                  >
                    <Play size={14} />
                    Forecast saved input
                  </button>
                  <button
                    className="button secondary"
                    disabled={
                      !!busy || report.model.archived || report.model.environment === 'imported'
                    }
                    onClick={() => void action('current_feed')}
                  >
                    <RefreshCw size={14} />
                    Use latest matching feed
                  </button>
                  {busy && <span className="footnote">Working…</span>}
                </div>
                {activeOutput ? (
                  <>
                    <div className="forecast-model-attribution">
                      <Badge
                        tone={
                          activeOutput.stale || activeOutput.environment === 'demo'
                            ? 'amber'
                            : 'blue'
                        }
                      >
                        {activeOutput.environment === 'demo'
                          ? 'Demo forecast'
                          : 'Recorded forecast'}
                        {activeOutput.stale ? ' · older observations' : ''}
                      </Badge>
                      <span>
                        Origin: {new Date(activeOutput.origin).toLocaleString()} ·{' '}
                        {activeOutput.input_kind === 'saved_input'
                          ? 'Original saved input'
                          : 'Matching current feed'}
                      </span>
                    </div>
                    <ForecastPlot points={forecastPoints} />
                    <p className="footnote">
                      {activeOutput.shift.outside_training_range} of {activeOutput.shift.features}{' '}
                      model features fall outside observed training ranges. This is a descriptive
                      shift check, not a calibrated regime detector. {activeOutput.note}
                    </p>
                    <button
                      className="text-button"
                      onClick={() =>
                        downloadJSON(`chronos-forecast-${activeOutput.id}.json`, activeOutput)
                      }
                    >
                      <Download size={13} />
                      Export this forecast & observations
                    </button>
                  </>
                ) : (
                  <p className="footnote">
                    Saved input works offline. Latest feed reads only this model’s original source,
                    environment and exact pair. Inspect the observation date before interpreting the
                    result.
                  </p>
                )}
                {!!report.outputs.length && (
                  <details className="forecast-advanced">
                    <summary>Saved forecasts · latest {report.outputs.length}</summary>
                    <div className="forecast-output-list">
                      {report.outputs.map((run) => (
                        <button
                          className="text-button"
                          key={run.id}
                          disabled={!!busy}
                          onClick={async () => {
                            setError('');
                            try {
                              setOutput(
                                await api<ForecastOutput>(`/forecast-models/outputs/${run.id}`),
                              );
                              setHorizon(run.horizon);
                            } catch (e) {
                              setError((e as Error).message);
                            }
                          }}
                        >
                          {new Date(run.created_at).toLocaleString()} · {run.horizon} days ·{' '}
                          {run.input_kind === 'saved_input' ? 'saved input' : 'latest feed'}
                        </button>
                      ))}
                    </div>
                  </details>
                )}
              </Panel>
              <details className="forecast-method-notes">
                <summary>Method, interpretation & limitations</summary>
                {report.notes.map((note) => (
                  <p key={note}>{note}</p>
                ))}
              </details>
            </>
          )
        ))}
    </div>
  );
}

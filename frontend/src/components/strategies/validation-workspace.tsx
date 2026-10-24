import { useEffect, useState } from 'react';
import { ChevronDown, FlaskConical, Play } from 'lucide-react';
import { Badge, Panel } from '../ui';
import { ValidationResults } from './validation-results';
import { api, number, post, refresh } from '../../lib/api';
import { useResource } from '../../lib/hooks';
import type { Dataset } from '../../lib/market-history';
import type { StrategyParams } from '../../lib/types';
import type {
  ValidationOptions,
  ValidationReport,
  ValidationSummary,
} from '../../lib/strategy-validation';

const label = (key: string) => key.replaceAll('_', ' ');
const date = (value: string) => new Date(value).toLocaleDateString();

/** Optional research: train-only selection, then inspect persisted later-window executions. */
export function ValidationWorkspace({
  dataset,
  parameters,
  demo,
}: {
  dataset?: Dataset;
  parameters: StrategyParams;
  demo: boolean;
}) {
  const [open, setOpen] = useState(false);
  const options = useResource<ValidationOptions>('/strategies/validation/options', 0, open);
  const saved = useResource<ValidationSummary[]>(`/strategies/validations?demo=${demo}`, 0, open);
  const fields = options.data?.strategies[parameters.strategy] ?? [];
  const fieldKeys = fields.map((f) => f.key).join(',');
  const [search, setSearch] = useState(true);
  const [axes, setAxes] = useState<{ key: string; values: string }[]>([]);
  const [folds, setFolds] = useState(3);
  const [trainPct, setTrainPct] = useState(60);
  const [objective, setObjective] =
    useState<ValidationSummary['request']['objective']>('return_pct');
  const [minimum, setMinimum] = useState(0);
  const [report, setReport] = useState<ValidationReport>();
  const [busy, setBusy] = useState('');
  const [error, setError] = useState('');
  useEffect(() => {
    setAxes(
      (options.data?.strategies[parameters.strategy] ?? [])
        .slice(0, 2)
        .map((f) => ({ key: f.key, values: f.values.join(', ') })),
    );
  }, [parameters.strategy, fieldKeys]);
  const perform = async (kind: string, action: () => Promise<ValidationReport>) => {
    setBusy(kind);
    setError('');
    try {
      setReport(await action());
      refresh();
    } catch (reason) {
      setError((reason as Error).message);
    } finally {
      setBusy('');
    }
  };
  const run = () =>
    perform('run', async () => {
      if (!dataset) throw new Error('Choose a saved dataset or run a backtest first.');
      const grid: Record<string, number[]> = {};
      if (search)
        for (const axis of axes.filter((a) => a.key)) {
          const values = axis.values.split(',').map((v) => v.trim());
          if (values.some((v) => !v || !Number.isFinite(Number(v))))
            throw new Error('Enter comma-separated numeric values for each search parameter.');
          grid[axis.key] = values.map(Number);
        }
      return post<ValidationReport>('/strategies/validations', {
        dataset_id: dataset.id,
        parameters: {
          ...parameters,
          symbol: dataset.symbol,
          timeframe: dataset.timeframe,
          candles: dataset.count,
        },
        grid,
        folds,
        initial_train_pct: trainPct,
        objective,
        min_train_trades: minimum,
      });
    });
  return (
    <Panel className="full-panel">
      <details
        className="strategy-validation"
        onToggle={(event) => setOpen(event.currentTarget.open)}
      >
        <summary>
          <span className="validation-symbol">
            <FlaskConical size={20} />
          </span>
          <span>
            <strong>Validate on unseen data</strong>
            <small>Walk-forward tests and optional parameter search</small>
          </span>
          <Badge>Advanced research</Badge>
          <ChevronDown size={16} className="validation-chevron" />
        </summary>
        <div className="validation-content">
          <p className="validation-intro">
            Choose settings on earlier candles, then test the choice on the next window. Compare it
            with your fixed settings and buy &amp; hold on the same test prices.
          </p>
          <div className="validation-saved">
            <label>
              Saved validations
              <select
                aria-label="Open saved validation"
                disabled={!!busy}
                value={report?.id ?? ''}
                onChange={(event) => {
                  const id = event.target.value;
                  if (!id) setReport(undefined);
                  else
                    void perform('load', () =>
                      api<ValidationReport>(`/strategies/validations/${id}`),
                    );
                }}
              >
                <option value="">New validation</option>
                {report && !saved.data?.some((r) => r.id === report.id) && (
                  <option value={report.id}>
                    {report.dataset.symbol} · {report.id.slice(0, 8)}
                  </option>
                )}
                {saved.data?.map((r) => (
                  <option key={r.id} value={r.id}>
                    {r.request.parameters.strategy} · {r.dataset.symbol} · {date(r.created_at)} ·{' '}
                    {r.id.slice(0, 8)}
                  </option>
                ))}
              </select>
            </label>
          </div>
          {!dataset ? (
            <p className="inline-alert">
              Run a backtest or choose a saved dataset to validate its exact input. Saved
              validations can still be opened above.
            </p>
          ) : (
            <p className="validation-input">
              <Badge tone={dataset.source === 'demo' ? 'sand' : 'neutral'}>
                {dataset.source === 'demo' ? 'Synthetic Demo input' : dataset.source_label}
              </Badge>
              <span>
                {dataset.symbol} · {dataset.timeframe} · {number(dataset.count)} bars ·{' '}
                {parameters.strategy}
              </span>
              <code title={dataset.digest}>{dataset.digest.slice(0, 12)}…</code>
            </p>
          )}
          <form
            className="validation-form"
            onSubmit={(event) => {
              event.preventDefault();
              void run();
            }}
          >
            <div className="validation-setup">
              <label>
                Parameter selection
                <select
                  value={search ? 'search' : 'fixed'}
                  onChange={(e) => setSearch(e.target.value === 'search')}
                >
                  <option value="search">Compare a small parameter grid</option>
                  <option value="fixed">Keep my fixed settings</option>
                </select>
              </label>
              <label>
                Initial training window
                <select value={trainPct} onChange={(e) => setTrainPct(Number(e.target.value))}>
                  {[40, 50, 60, 70, 80].map((pct) => (
                    <option key={pct} value={pct}>
                      {pct}% of the dataset
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Later test windows
                <select value={folds} onChange={(e) => setFolds(Number(e.target.value))}>
                  {[1, 2, 3, 4, 5].map((n) => (
                    <option key={n} value={n}>
                      {n === 1 ? '1 chronological holdout' : `${n} expanding windows`}
                    </option>
                  ))}
                </select>
              </label>
            </div>
            {search && (
              <div className="validation-axes">
                {axes.map((axis, index) => (
                  <div className="form-row" key={index}>
                    <label>
                      Search parameter {index + 1}
                      <select
                        value={axis.key}
                        onChange={(event) => {
                          const field = fields.find((f) => f.key === event.target.value);
                          setAxes((old) =>
                            old.map((a, i) =>
                              i === index
                                ? { key: field?.key ?? '', values: field?.values.join(', ') ?? '' }
                                : a,
                            ),
                          );
                        }}
                      >
                        <option value="">None</option>
                        {fields
                          .filter((f) => !axes.some((a, i) => i !== index && a.key === f.key))
                          .map((f) => (
                            <option key={f.key} value={f.key}>
                              {label(f.key)}
                            </option>
                          ))}
                      </select>
                    </label>
                    <label>
                      Values · up to 4
                      <input
                        aria-label={`Search values ${index + 1}`}
                        value={axis.values}
                        disabled={!axis.key}
                        onChange={(e) =>
                          setAxes((old) =>
                            old.map((a, i) => (i === index ? { ...a, values: e.target.value } : a)),
                          )
                        }
                        placeholder="5, 9, 13"
                      />
                    </label>
                  </div>
                ))}
              </div>
            )}
            <details className="advanced-options">
              <summary>Selection rules &amp; limits</summary>
              <div className="form-row">
                <label>
                  Training objective
                  <select
                    value={objective}
                    onChange={(e) => setObjective(e.target.value as typeof objective)}
                  >
                    <option value="return_pct">Highest net return</option>
                    <option value="sharpe">Highest Sharpe ratio</option>
                    <option value="max_drawdown">Lowest maximum drawdown</option>
                  </select>
                </label>
                <label>
                  Minimum training round trips
                  <input
                    type="number"
                    min={0}
                    max={100}
                    value={minimum}
                    onChange={(e) => setMinimum(Number(e.target.value))}
                  />
                </label>
              </div>
              <p>
                At most 16 combinations, 5 windows and 60,000 processed bars. Each test needs 20
                candles. Candidates with no trades can qualify when the minimum is zero. All
                candidates must be valid; invalid combinations are never silently skipped.
              </p>
            </details>
            {(error || options.error || saved.error) && (
              <p className="form-error" role="alert">
                {error || options.error || saved.error}
              </p>
            )}
            <div className="validation-actions">
              <button className="button secondary" disabled={!dataset || !!busy || !options.data}>
                <Play size={14} />
                {busy === 'run' ? 'Testing chronological windows…' : 'Run walk-forward test'}
              </button>
              <span>Uses saved data only. No orders or strategy settings are changed.</span>
            </div>
          </form>
          {report && (
            <ValidationResults
              key={report.id}
              report={report}
              busy={busy}
              onError={setError}
              onRerun={() =>
                void perform('rerun', () =>
                  post<ValidationReport>(`/strategies/validations/${report.id}/rerun`),
                )
              }
            />
          )}
        </div>
      </details>
    </Panel>
  );
}

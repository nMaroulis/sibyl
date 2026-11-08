import { useState } from 'react';
import { FlaskConical, Download, RefreshCw, Trash2 } from 'lucide-react';
import { AgentButton } from '../agents';
import { Badge, ErrorState, Loading, Panel, PanelTitle } from '../ui';
import { BacktestChart } from './backtest-chart';
import { api, downloadFile, number, post } from '../../lib/api';
import { useResource } from '../../lib/hooks';
import type { Backtest, StrategyParams } from '../../lib/types';

type Plugin = {
  id: string;
  status: string;
  error: string | null;
  revision?: string;
  implementation?: { distribution: string; version: string };
  spec?: {
    name: string;
    description: string;
    warmup: number;
    parameters: Record<
      string,
      { label: string; kind: 'int' | 'float'; minimum: number; maximum: number; default: number }
    >;
  };
};
type CustomResult = Omit<Backtest, 'parameters'> & {
  parameters: Pick<
    StrategyParams,
    | 'symbol'
    | 'timeframe'
    | 'capital'
    | 'candles'
    | 'fee_bps'
    | 'slippage_bps'
    | 'stop_loss_pct'
    | 'take_profit_pct'
    | 'max_trades'
  > & { values: Record<string, number> };
  plugin: {
    id: string;
    name: string;
    revision: string;
    implementation: { distribution: string; version: string };
    spec?: { parameters: Record<string, { label: string }> };
  };
  signal_fingerprint: string;
  note: string;
};

/** A progressive research workspace; no browser code editor or job controls. */
export function CustomStrategies({
  params,
  datasetId,
  demo,
}: {
  params: StrategyParams;
  datasetId: string;
  demo: boolean;
}) {
  const [open, setOpen] = useState(false),
    [chosen, setChosen] = useState(''),
    [values, setValues] = useState<Record<string, number>>({});
  const [result, setResult] = useState<CustomResult>(),
    [busy, setBusy] = useState(''),
    [error, setError] = useState('');
  const catalog = useResource<{ items: Plugin[]; note: string }>('/strategies/plugins', 0, open);
  const history = useResource<{
    items: (Pick<CustomResult, 'id' | 'plugin' | 'symbol' | 'environment' | 'return_pct'> & {
      created_at: string;
    })[];
  }>('/strategies/plugins/backtests', 0, open);
  const ready = catalog.data?.items.filter((p) => p.status === 'ready') ?? [];
  const selected = ready.find((p) => p.id === chosen) ?? ready[0];
  const saved = history.data?.items.filter((r) => (r.environment === 'demo') === demo) ?? [];
  const act = async (kind: 'run' | 'rerun' | 'delete' | 'read', id?: string) => {
    setBusy(kind);
    setError('');
    try {
      if (kind === 'read')
        setResult(await api<CustomResult>(`/strategies/plugins/backtests/${id}`));
      else if (kind === 'delete') {
        await api(`/strategies/plugins/backtests/${id}`, { method: 'DELETE' });
        setResult(undefined);
        history.retry();
      } else {
        const data =
          kind === 'rerun'
            ? await post<CustomResult>(`/strategies/plugins/backtests/${id}/rerun`, {})
            : await post<CustomResult>('/strategies/plugins/backtests', {
                plugin_id: selected?.id,
                revision: selected?.revision,
                values,
                input_kind: datasetId ? 'saved_dataset' : demo ? 'demo' : 'current_feed',
                ...(datasetId ? { dataset_id: datasetId } : {}),
                symbol: params.symbol,
                timeframe: params.timeframe,
                candles: params.candles,
                capital: params.capital,
                fee_bps: params.fee_bps,
                slippage_bps: params.slippage_bps,
                stop_loss_pct: params.stop_loss_pct ?? null,
                take_profit_pct: params.take_profit_pct ?? null,
                max_trades: params.max_trades ?? null,
              });
        setResult(data);
        history.retry();
      }
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy('');
    }
  };
  return (
    <details
      className="strategy-advanced custom-strategy-research"
      onToggle={(e) => setOpen(e.currentTarget.open)}
    >
      <summary>Custom Python strategies</summary>
      <Panel>
        <PanelTitle
          title="Your custom research"
          subtitle="Installed local extensions · historical backtests only"
          action={<Badge>Advanced</Badge>}
        />
        <p className="footnote">
          Use the pair, interval, input, virtual capital, costs and close-based risk limits
          configured above. Custom parameters belong to the selected plugin. Signals see only their
          current/past candles and fill at the next open.
        </p>
        {catalog.loading ? (
          <Loading />
        ) : catalog.error ? (
          <ErrorState message={catalog.error} retry={catalog.retry} />
        ) : (
          <>
            <p className="footnote">
              {catalog.data?.note}{' '}
              <a
                href="https://nmaroulis.github.io/sibyl/developers/strategy-plugins/"
                target="_blank"
                rel="noreferrer"
              >
                Plugin setup & example ↗
              </a>
            </p>
            {!ready.length && (
              <p className="inline-alert">
                No custom strategies are enabled. Install a trusted package with a{' '}
                <code>sibyl.strategies</code> entry point, add its name to{' '}
                <code>SIBYL_STRATEGY_PLUGINS</code>, then restart the backend. Built-in algorithms
                are available above.
              </p>
            )}
            {catalog.data?.items
              .filter((p) => p.status !== 'ready')
              .map((p) => (
                <p className="footnote" key={p.id}>
                  {p.id} · {p.status}
                  {p.error ? ` · ${p.error}` : ''}
                </p>
              ))}
            {selected && (
              <>
                <div className="form-row">
                  <label>
                    Custom algorithm
                    <select
                      value={selected.id}
                      disabled={!!busy}
                      onChange={(e) => {
                        setChosen(e.target.value);
                        setValues({});
                      }}
                    >
                      {ready.map((p) => (
                        <option key={p.id} value={p.id}>
                          {p.spec!.name}
                        </option>
                      ))}
                    </select>
                  </label>
                  {Object.entries(selected.spec!.parameters).map(([key, p]) => (
                    <label key={`${selected.id}:${key}`}>
                      {p.label}
                      <input
                        type="number"
                        min={p.minimum}
                        max={p.maximum}
                        step={p.kind === 'int' ? 1 : 'any'}
                        value={values[key] ?? p.default}
                        disabled={!!busy}
                        onChange={(e) => setValues({ ...values, [key]: Number(e.target.value) })}
                      />
                    </label>
                  ))}
                </div>
                <p className="footnote">
                  {selected.spec!.description} · {selected.spec!.warmup} warmup bars ·{' '}
                  {selected.implementation?.distribution} {selected.implementation?.version} ·
                  revision {selected.revision?.slice(0, 12)}…
                </p>
                <button
                  className="button secondary"
                  disabled={!!busy || params.candles > 2000}
                  onClick={() => void act('run')}
                >
                  <FlaskConical size={14} />
                  {busy === 'run' ? 'Backtesting…' : 'Backtest custom strategy'}
                </button>
                {params.candles > 2000 && (
                  <p className="footnote">Select a saved input of at most 2,000 candles.</p>
                )}
              </>
            )}
          </>
        )}
        {!!saved.length && (
          <label>
            Saved custom backtest
            <select
              value={result?.id ?? ''}
              disabled={!!busy}
              onChange={(e) => void act('read', e.target.value)}
            >
              <option value="">Choose a result…</option>
              {saved.map((r) => (
                <option value={r.id} key={r.id}>
                  {r.plugin.name} · {r.symbol} · {r.environment} ·{' '}
                  {new Date(r.created_at).toLocaleString()}
                </option>
              ))}
            </select>
          </label>
        )}
        {history.error && <ErrorState message={history.error} retry={history.retry} />}
        {error && (
          <p className="form-error" role="alert">
            {error}
          </p>
        )}
        {result && (
          <section aria-label="Custom backtest results">
            <PanelTitle
              title={result.plugin.name}
              subtitle={`${result.symbol} · ${result.dataset?.source_label} · ${result.plugin.implementation.distribution} ${result.plugin.implementation.version}`}
              action={
                <AgentButton
                  module="broker"
                  context={{ backtest_id: result.id, symbol: result.symbol }}
                />
              }
            />
            <div className="strategy-alert-tags">
              <Badge tone={result.source === 'demo' ? 'demo' : 'neutral'}>
                {result.source === 'demo' ? 'Demo · synthetic input' : 'Historical research'}
              </Badge>
              <Badge>Revision {result.plugin.revision.slice(0, 12)}…</Badge>
            </div>
            <div className="forecast-metrics">
              <div>
                <small>Net return</small>
                <strong>{number(result.return_pct, 2)}%</strong>
                <span>After simulated fees/slippage</span>
              </div>
              <div>
                <small>Maximum drawdown</small>
                <strong>{number(result.max_drawdown, 2)}%</strong>
                <span>Observed historical path</span>
              </div>
              <div>
                <small>Round trips</small>
                <strong>{result.trades}</strong>
                <span>
                  {number(result.fees, 4)} {result.symbol.split('/')[1]} fees
                </span>
              </div>
            </div>
            <details>
              <summary>Saved parameters &amp; execution costs</summary>
              <p className="footnote">
                These settings belong to this recorded result. The controls above configure a new
                experiment; exact-input reruns use these saved settings.
              </p>
              <div className="risk-evidence-summary">
                {Object.entries(result.parameters.values).map(([key, value]) => (
                  <div key={key}>
                    <small>{result.plugin.spec?.parameters[key]?.label ?? key}</small>
                    <strong>{number(value, 4)}</strong>
                  </div>
                ))}
              </div>
              <p className="footnote">
                {result.parameters.candles} candles · {result.parameters.timeframe} · initial
                capital {number(result.parameters.capital, 2)} · fees {result.parameters.fee_bps}{' '}
                bps · slippage {result.parameters.slippage_bps} bps per fill.
              </p>
              <p className="footnote">
                Stop loss{' '}
                {result.parameters.stop_loss_pct == null
                  ? 'off'
                  : `${result.parameters.stop_loss_pct}%`}{' '}
                · take profit{' '}
                {result.parameters.take_profit_pct == null
                  ? 'off'
                  : `${result.parameters.take_profit_pct}%`}{' '}
                · trade cap {result.parameters.max_trades ?? 'none'}. Input fingerprint{' '}
                {result.dataset?.digest.slice(0, 16)}…
              </p>
            </details>
            <BacktestChart key={result.id} result={result} />
            <p className="footnote">{result.note}</p>
            <details>
              <summary>Executed round trips · {result.round_trips?.length ?? 0}</summary>
              <div className="table-wrap" style={{ maxHeight: 340, overflowY: 'auto' }}>
                <table>
                  <thead>
                    <tr>
                      <th>Entry</th>
                      <th>Exit</th>
                      <th>Net P&L</th>
                      <th>Return</th>
                      <th>Exit reason</th>
                    </tr>
                  </thead>
                  <tbody>
                    {result.round_trips?.map((t) => (
                      <tr key={t.id}>
                        <td>{new Date(t.entry_time).toLocaleString()}</td>
                        <td>{new Date(t.exit_time).toLocaleString()}</td>
                        <td>{number(t.pnl, 4)}</td>
                        <td>{number(t.return_pct, 2)}%</td>
                        <td>{t.reason}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </details>
            <div className="workspace-actions">
              <button
                className="text-button"
                disabled={!!busy}
                onClick={() => void act('rerun', result.id)}
              >
                <RefreshCw size={13} />
                Rerun exact custom input
              </button>
              <button
                className="text-button"
                onClick={() =>
                  void downloadFile(
                    `/strategies/plugins/backtests/${result.id}`,
                    `sibyl-custom-backtest-${result.id}.json`,
                  )
                }
              >
                <Download size={13} />
                Export custom evidence
              </button>
              <button
                className="text-button negative"
                disabled={!!busy}
                onClick={() => void act('delete', result.id)}
              >
                <Trash2 size={13} />
                Remove saved result
              </button>
            </div>
          </section>
        )}
      </Panel>
    </details>
  );
}

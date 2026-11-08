import './account-returns.css';
import { useState } from 'react';
import { Download, Pause, Play, RefreshCw, Radar } from 'lucide-react';
import { AgentButton } from './agents';
import { ForecastPlot } from './forecast-plot';
import { Badge, Empty, ErrorState, Loading, Modal, Panel, PanelTitle, useToast } from './ui';
import { api, number, post, refresh } from '../lib/api';
import { useResource } from '../lib/hooks';
import type { ForecastOutput } from '../lib/forecast-types';

type Metrics = { mae: number; rmse: number; mape_pct: number };
type Point = {
  horizon: number;
  timestamp: string;
  value: number;
  lower: number;
  upper: number;
  naive: number;
  drift: number;
  state: string;
  observation: { actual: number; version: number; checked_at: string } | null;
};
type Tracking = {
  id: string;
  revision: number;
  source: string;
  environment: string;
  symbol: string;
  created_at: string;
  accepted_at: string;
  status: string;
  points: Point[];
  observed: number;
  pending: number;
  metrics: Metrics | null;
  naive: Metrics | null;
  coverage_pct: number | null;
  mae_skill_vs_naive_pct: number | null;
  note: string;
  checked_at: string | null;
  error: string | null;
};
type Scorecard = {
  items: Tracking[];
  by_horizon: {
    horizon: number;
    samples: number;
    model: Metrics;
    naive: Metrics;
    drift: Metrics;
    coverage_pct: number;
  }[];
};

/** Actual forward evidence stays separate from held-out/rolling historical evaluation. */
export function ForecastForward({
  modelId,
  outputs,
}: {
  modelId: string;
  outputs: Omit<ForecastOutput, 'points' | 'observations'>[];
}) {
  const state = useResource<Scorecard>(`/forecast-models/${modelId}/tracking`, 15000);
  const [selected, setSelected] = useState(''),
    [busy, setBusy] = useState('');
  const [removing, setRemoving] = useState(false);
  const toast = useToast();
  const rows = state.data?.items ?? [];
  const item = rows.find((r) => r.id === selected) || rows[0];
  const act = async (path: string, body: unknown = {}) => {
    setBusy(path);
    try {
      await post(path, body);
      refresh();
    } catch (e) {
      toast((e as Error).message, true);
    } finally {
      setBusy('');
    }
  };
  const eligible = outputs.filter(
    (o) =>
      o.input_kind === 'current_feed' &&
      o.environment !== 'demo' &&
      o.environment !== 'imported' &&
      o.source !== 'demo' &&
      !rows.some((r) => r.id === o.id),
  );
  return (
    <Panel className="forecast-forward">
      <PanelTitle
        title="Live forecast scorecard"
        subtitle="Saved before the target · exact source · observed closed daily prices"
        action={<Radar size={18} />}
      />
      <p className="returns-note">
        Track explicitly saved current-feed predictions, then compare them with later closes.
        Historical saved-input and Demo forecasts are excluded. The worker checks retained candles
        hourly; refresh the matching feed here or retain newer candles in Markets.
      </p>
      {state.error ? (
        <ErrorState message={state.error} retry={state.retry} />
      ) : state.loading ? (
        <Loading />
      ) : (
        <>
          {!!eligible.length && (
            <details>
              <summary>Track a saved current-feed forecast</summary>
              <div className="returns-actions">
                {eligible.map((o) => (
                  <button
                    className="button small"
                    disabled={!!busy}
                    key={o.id}
                    onClick={() => void act(`/forecast-models/outputs/${o.id}/track`)}
                  >
                    <Radar size={13} />
                    {new Date(o.created_at).toLocaleString()} · {o.horizon} days
                  </button>
                ))}
              </div>
            </details>
          )}
          {!rows.length ? (
            <Empty title="No prospective forecasts tracked">
              Save a forecast using Current feed above, then select it here. Tracking preserves its
              original output beyond the recent-history limit. Missing observations are never filled
              with synthetic prices.
            </Empty>
          ) : (
            <>
              <label className="returns-period-picker">
                Tracked forecast · original save time
                <select value={item?.id || ''} onChange={(e) => setSelected(e.target.value)}>
                  {rows.map((r) => (
                    <option key={r.id} value={r.id}>
                      {new Date(r.accepted_at).toLocaleString()} · {r.observed} observed /{' '}
                      {r.points.length} targets
                    </option>
                  ))}
                </select>
              </label>
              {item && (
                <>
                  <div className="returns-actions">
                    <Badge>{item.status}</Badge>
                    <span>
                      {item.source} · {item.environment} · {item.symbol}
                    </span>
                    <AgentButton
                      module="chronos"
                      context={{
                        forecast_model_id: modelId,
                        forecast_run_id: item.id,
                        forecast_tracking: true,
                      }}
                    />
                    <button
                      className="button small"
                      disabled={!!busy}
                      onClick={() =>
                        void act(`/forecast-models/outputs/${item.id}/tracking/action`, {
                          revision: item.revision,
                          action: item.status === 'paused' ? 'resume' : 'pause',
                        })
                      }
                    >
                      {item.status === 'paused' ? <Play size={13} /> : <Pause size={13} />}
                      {item.status === 'paused' ? 'Resume' : 'Pause'}
                    </button>
                    <button
                      className="button small"
                      disabled={!!busy || item.status === 'paused'}
                      onClick={() =>
                        void act(`/forecast-models/outputs/${item.id}/tracking/check?refresh=true`)
                      }
                    >
                      <RefreshCw size={13} />
                      {busy ? 'Checking…' : 'Refresh matching feed'}
                    </button>
                    <button
                      className="text-button"
                      onClick={() => {
                        const url = URL.createObjectURL(
                          new Blob([JSON.stringify(item, null, 2)], { type: 'application/json' }),
                        );
                        const a = document.createElement('a');
                        a.href = url;
                        a.download = `forecast-outcomes-${item.id}.json`;
                        a.click();
                        URL.revokeObjectURL(url);
                      }}
                    >
                      <Download size={13} /> Export
                    </button>
                    <button className="text-button" onClick={() => setRemoving(true)}>
                      Remove tracking…
                    </button>
                  </div>
                  <div className="returns-metrics">
                    {[
                      ['Targets observed', `${item.observed} / ${item.points.length}`],
                      [
                        'MAE vs naïve',
                        item.metrics && item.naive
                          ? `${number(item.metrics.mae)} / ${number(item.naive.mae)}`
                          : 'Awaiting actuals',
                      ],
                      [
                        'Band coverage',
                        item.coverage_pct === null
                          ? 'Awaiting actuals'
                          : number(item.coverage_pct) + '%',
                      ],
                    ].map(([label, value]) => (
                      <div key={label}>
                        <small>{label}</small>
                        <strong className="monetary">{value}</strong>
                      </div>
                    ))}
                  </div>
                  <ForecastPlot
                    testing
                    showDrift
                    points={item.points.map((p) => ({
                      timestamp: p.timestamp,
                      predicted: p.value,
                      lower: p.lower,
                      upper: p.upper,
                      actual: p.observation?.actual,
                      naive: p.naive,
                      drift: p.drift,
                    }))}
                  />
                  <div className="table-scroll">
                    <table>
                      <thead>
                        <tr>
                          <th>Horizon</th>
                          <th>Target · UTC</th>
                          <th>Forecast</th>
                          <th>Actual / status</th>
                          <th>Version</th>
                        </tr>
                      </thead>
                      <tbody>
                        {item.points.map((p) => (
                          <tr key={p.horizon}>
                            <td>{p.horizon}d</td>
                            <td>
                              {new Date(p.timestamp).toLocaleDateString(undefined, {
                                timeZone: 'UTC',
                              })}
                            </td>
                            <td>{number(p.value)}</td>
                            <td>
                              {p.observation
                                ? number(p.observation.actual)
                                : p.state.replaceAll('_', ' ')}
                            </td>
                            <td>{p.observation?.version || '—'}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                  {item.error && <p className="form-error">{item.error}</p>}
                  <p className="returns-note">
                    {item.note} Last archive check:{' '}
                    {item.checked_at ? new Date(item.checked_at).toLocaleString() : 'not checked'}.
                  </p>
                </>
              )}
              {!!state.data?.by_horizon?.length && (
                <details>
                  <summary>Across tracked forecasts · compare equal horizons</summary>
                  <div className="table-scroll">
                    <table>
                      <thead>
                        <tr>
                          <th>Horizon</th>
                          <th>Unique target days</th>
                          <th>Model MAE</th>
                          <th>Naïve MAE</th>
                          <th>Drift MAE</th>
                          <th>Coverage</th>
                        </tr>
                      </thead>
                      <tbody>
                        {state.data.by_horizon.map((h) => (
                          <tr key={h.horizon}>
                            <td>{h.horizon}d</td>
                            <td>{h.samples}</td>
                            <td>{number(h.model.mae)}</td>
                            <td>{number(h.naive.mae)}</td>
                            <td>{number(h.drift.mae)}</td>
                            <td>{number(h.coverage_pct)}%</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                  <p className="returns-note">
                    Repeated forecasts for the same target use the earliest original save;
                    operator-selected tracked forecasts can overlap and are not an unbiased model
                    leaderboard. Larger samples and independent evaluations are still needed.
                  </p>
                </details>
              )}
            </>
          )}
        </>
      )}
      {item && removing && (
        <Modal title="Remove forecast tracking?" onClose={() => !busy && setRemoving(false)}>
          <p>
            This removes tracked actuals and correction receipts. Export first to retain them. The
            original saved forecast remains in recent history and is no longer protected from normal
            cleanup.
          </p>
          <button
            className="button primary"
            disabled={!!busy}
            onClick={async () => {
              setBusy('remove');
              try {
                await api(
                  `/forecast-models/outputs/${item.id}/tracking?revision=${item.revision}`,
                  { method: 'DELETE' },
                );
                setRemoving(false);
                setSelected('');
                refresh();
              } catch (e) {
                toast((e as Error).message, true);
              } finally {
                setBusy('');
              }
            }}
          >
            Remove tracked outcomes
          </button>
        </Modal>
      )}
    </Panel>
  );
}

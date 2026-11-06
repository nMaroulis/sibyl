import { useEffect, useState } from 'react';
import { Activity } from 'lucide-react';
import { AgentButton } from './agents';
import { Badge, Change, Panel } from './ui';
import { ValueChart } from './charts';
import { api, downloadFile, number, post } from '../lib/api';
import { useResource } from '../lib/hooks';
import type { Portfolio } from '../lib/types';

type Summary = {
  id: string;
  scope: string;
  created_at: string;
  selected_assets: string[];
  requested_days: number;
  source: { source: string; source_label: string };
};
type Study = Summary & {
  observations: number;
  start: string;
  end: string;
  history_lag_days: number;
  discarded_earlier_closes: number;
  daily_volatility_pct: number;
  annualized_volatility_pct: number;
  historical_var_95_pct: number;
  expected_shortfall_95_pct: number;
  tail_observations: number;
  max_drawdown_pct: number;
  hypothetical_return_pct: number;
  diversification_ratio: number | null;
  entire_account_basket: boolean;
  share_of_priced_value_pct: number;
  coverage_note: string;
  valuation_complete: boolean;
  excluded_unpriced: string[];
  failed_accounts: string[];
  assumptions: string[];
  fingerprint: string;
  assets: {
    asset: string;
    weight_pct: number;
    annualized_volatility_pct: number;
    variance_contribution_pct: number | null;
  }[];
  correlation: (number | null)[][];
  daily_returns: { timestamp: string; return_pct: number; index: number }[];
};

/** Explicit selected-basket research, visibly separate from measured account returns. */
export function PortfolioRisk({ portfolio, scope }: { portfolio: Portfolio; scope: string }) {
  const [open, setOpen] = useState(false);
  const [selected, setSelected] = useState(() =>
    portfolio.holdings.slice(0, 6).map((h) => h.asset),
  );
  const holdingAssets = portfolio.holdings.map((h) => h.asset).join(',');
  useEffect(() => {
    const available = new Set(holdingAssets.split(','));
    setSelected((previous) => previous.filter((asset) => available.has(asset)));
  }, [holdingAssets]);
  const [days, setDays] = useState(90);
  const [id, setId] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [remove, setRemove] = useState(false);
  const [pathOpen, setPathOpen] = useState(false);
  const saved = useResource<{ items: Summary[] }>(
    `/account/risk?scope=${encodeURIComponent(scope)}`,
    0,
    open,
  );
  const detail = useResource<Study>(`/account/risk/${id}`, 0, open && !!id);
  const report = detail.data;
  const calculate = async () => {
    setBusy(true);
    setError('');
    try {
      const result = await post<Study>('/account/risk', { scope, assets: selected, days });
      setId(result.id);
      saved.retry();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };
  return (
    <Panel className="full-panel">
      <details className="portfolio-risk" onToggle={(e) => setOpen(e.currentTarget.open)}>
        <summary>
          <Activity size={18} />
          <strong>Historical basket risk</strong>
          <Badge>Advanced analysis</Badge>
        </summary>
        <p>
          Explore how a basket with today's holding weights behaved over past daily prices. This
          hypothetical, daily-rebalanced basket is separate from your account's measured
          performance.
        </p>
        <div className="form-row">
          <label>
            Price-history window
            <select value={days} onChange={(e) => setDays(Number(e.target.value))}>
              {[30, 60, 90, 180, 365].map((n) => (
                <option key={n} value={n}>
                  Up to {n} days
                </option>
              ))}
            </select>
          </label>
          <label>
            Saved risk study
            <select
              value={id}
              onChange={(e) => {
                setId(e.target.value);
                setRemove(false);
              }}
            >
              <option value="">New study</option>
              {saved.data?.items.map((r) => (
                <option key={r.id} value={r.id}>
                  {r.selected_assets.join(' · ')} · {new Date(r.created_at).toLocaleDateString()} ·{' '}
                  {r.id.slice(0, 8)}
                </option>
              ))}
            </select>
          </label>
        </div>
        {!portfolio.holdings.length && (
          <p className="inline-alert">
            No priced holdings are available in this scope. Check the valuation feed and account
            access before calculating a study.
          </p>
        )}
        <div className="risk-asset-choices" role="group" aria-label="Risk basket assets">
          {portfolio.holdings.map((asset) => (
            <button
              className={selected.includes(asset.asset) ? 'selected' : ''}
              aria-pressed={selected.includes(asset.asset)}
              disabled={!selected.includes(asset.asset) && selected.length >= 8}
              key={asset.asset}
              onClick={() =>
                setSelected((old) =>
                  old.includes(asset.asset)
                    ? old.filter((a) => a !== asset.asset)
                    : [...old, asset.asset],
                )
              }
            >
              {asset.asset}
              <small>{number(asset.allocation, 1)}%</small>
            </button>
          ))}
        </div>
        <p className="footnote">
          Select up to eight currently held assets. Weights are renormalized within this basket; the
          backend reads current holdings and the configured price feed only when you calculate. All
          conversion legs need a common consecutive daily history. No gaps or stablecoin parity are
          assumed.
        </p>
        <button
          className="button secondary tiny"
          disabled={busy || !selected.length}
          onClick={() => void calculate()}
        >
          {busy ? 'Reading history & calculating…' : 'Calculate & save risk study'}
        </button>
        {(error || saved.error || detail.error) && (
          <p className="form-error" role="alert">
            {error || saved.error || detail.error}
          </p>
        )}
        {report && (
          <section className="risk-study" aria-label="Basket risk results">
            <header>
              <Badge tone={report.source.source === 'demo' ? 'sand' : 'blue'}>
                {report.source.source === 'demo'
                  ? 'Demo reference history'
                  : report.source.source_label}
              </Badge>
              <Badge>
                {report.entire_account_basket ? 'Full observed basket' : 'Selected subset'}
              </Badge>
              <AgentButton
                module="accountant"
                context={{ risk_study_id: report.id, portfolio_scope: scope }}
              />
            </header>
            <p>
              {report.observations} consecutive daily returns ·{' '}
              {new Date(report.start).toLocaleDateString()} –{' '}
              {new Date(report.end).toLocaleDateString()} (exclusive)
            </p>
            <p className="footnote">
              {report.coverage_note} {number(report.share_of_priced_value_pct)}% of known priced
              value.{' '}
              {!report.valuation_complete &&
                'Account valuation was incomplete; this is not whole-account risk.'}
            </p>
            {report.history_lag_days > 2 && (
              <p className="inline-alert">
                History ends {report.history_lag_days} days before the latest completed day. These
                are dated historical statistics.
              </p>
            )}
            <div className="risk-metrics">
              <div>
                <small>Annualized volatility</small>
                <strong>{number(report.annualized_volatility_pct)}%</strong>
              </div>
              <div>
                <small>Historical 95% VaR · daily</small>
                <strong>{number(report.historical_var_95_pct)}%</strong>
              </div>
              <div>
                <small>Historical tail mean loss</small>
                <strong>{number(report.expected_shortfall_95_pct)}%</strong>
              </div>
              <div>
                <small>Basket maximum drawdown</small>
                <strong>{number(report.max_drawdown_pct)}%</strong>
              </div>
            </div>
            <p className="footnote">
              Historical tails use {report.tail_observations} observed days. Negative loss figures
              indicate gains in that sample. These statistics do not predict future risk or maximum
              loss.
            </p>
            <details>
              <summary>Weights, correlations &amp; variance contributions</summary>
              <div className="table-scroll">
                <table>
                  <thead>
                    <tr>
                      <th>Asset</th>
                      <th>Basket weight</th>
                      <th>Annualized volatility</th>
                      <th>Share of variance</th>
                    </tr>
                  </thead>
                  <tbody>
                    {report.assets.map((row) => (
                      <tr key={row.asset}>
                        <td>{row.asset}</td>
                        <td>{number(row.weight_pct)}%</td>
                        <td>{number(row.annualized_volatility_pct)}%</td>
                        <td>
                          {row.variance_contribution_pct == null
                            ? 'Undefined'
                            : `${number(row.variance_contribution_pct)}%`}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <p className="footnote">
                Variance contributions can be negative for offsetting assets. Undefined correlations
                indicate a constant series, not zero dependence.
              </p>
              <div className="table-scroll">
                <table>
                  <thead>
                    <tr>
                      <th>Daily return correlation</th>
                      {report.assets.map((a) => (
                        <th key={a.asset}>{a.asset}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {report.correlation.map((row, i) => (
                      <tr key={i}>
                        <th>{report.assets[i].asset}</th>
                        {row.map((value, j) => (
                          <td key={j}>{value == null ? '—' : number(value, 3)}</td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </details>
            <details onToggle={(e) => setPathOpen(e.currentTarget.open)}>
              <summary>
                Hypothetical basket path · <Change value={report.hypothetical_return_pct} />
              </summary>
              {pathOpen && (
                <ValueChart
                  currency={false}
                  unit="index"
                  data={report.daily_returns.map((p) => ({
                    timestamp: p.timestamp,
                    value: p.index,
                  }))}
                />
              )}
              <p className="footnote">
                Index rebased to 100 before the first observed return. Daily rebalancing is
                frictionless; these are not actual historical holdings or investment returns.
              </p>
            </details>
            <details>
              <summary>Method &amp; retained input evidence</summary>
              <ul>
                {report.assumptions.map((note) => (
                  <li key={note}>{note}</li>
                ))}
              </ul>
              <p>
                {report.discarded_earlier_closes} earlier shared closes were excluded to avoid
                bridging a later gap. Fingerprint <code>{report.fingerprint}</code>.
              </p>
            </details>
            <div className="workspace-actions">
              <button
                className="text-button"
                onClick={() =>
                  void downloadFile(
                    `/account/risk/${report.id}`,
                    `sibyl-basket-risk-${report.id}.json`,
                  ).catch((e) => setError((e as Error).message))
                }
              >
                Export full study
              </button>
              <button
                className="text-button"
                disabled={busy}
                onClick={() => {
                  if (!remove) {
                    setRemove(true);
                    return;
                  }
                  setBusy(true);
                  void api(`/account/risk/${report.id}`, { method: 'DELETE' })
                    .then(() => {
                      setId('');
                      setRemove(false);
                      saved.retry();
                    })
                    .catch((e) => setError((e as Error).message))
                    .finally(() => setBusy(false));
                }}
              >
                {remove ? 'Confirm study removal' : 'Remove saved study'}
              </button>
              {remove && (
                <button className="text-button" onClick={() => setRemove(false)}>
                  Keep study
                </button>
              )}
            </div>
          </section>
        )}
      </details>
    </Panel>
  );
}

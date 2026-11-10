import { useState } from 'react';
import { Link } from 'react-router-dom';
import { Layers3, Plus, RefreshCw, Trash2, X } from 'lucide-react';
import { AgentButton } from '../agents';
import { MarketSelector, TimeframeSelect, type SpotCatalog } from '../market-controls';
import { SearchPicker } from '../search-picker';
import { Badge, Empty, ErrorState, Loading, Panel, PanelTitle, useToast } from '../ui';
import { api, downloadFile, exportCSV, number, post } from '../../lib/api';
import { useResource } from '../../lib/hooks';
import { frameSeconds, type Dataset } from '../../lib/market-history';
import type { PortfolioLeg, PortfolioRecipe, PortfolioResult } from '../../lib/portfolio-research';
import { PortfolioChart } from './portfolio-chart';
import './portfolio-research.css';
const base = '/strategies/portfolios';
const seed = (): PortfolioRecipe => ({
  title: 'My portfolio study',
  input_kind: 'current_feed',
  legs: [
    { symbol: 'BTC/USDT', weight_pct: 60 },
    { symbol: 'ETH/USDT', weight_pct: 30 },
  ],
  capital: 10000,
  timeframe: '1d',
  candles: 180,
  fee_bps: 10,
  slippage_bps: 5,
  rule: 'interval',
  interval_bars: 30,
  drift_pct: 5,
});

/** Fixed target allocation research with explicit input provenance and progressively disclosed costs. */
export function PortfolioResearch({ demo, canRun }: { demo: boolean; canRun: boolean }) {
  const [recipe, setRecipe] = useState<PortfolioRecipe>(seed);
  const [savedInput, setSavedInput] = useState(false);
  const catalog = useResource<SpotCatalog>(
    `/markets/symbols${demo ? '?source=demo' : ''}`,
    0,
    canRun && !savedInput,
  );
  const inputs = useResource<{ datasets: Dataset[] }>(`${base}/inputs`, 0, savedInput);
  const history = useResource<{ items: PortfolioResult[] }>(
    `${base}${canRun ? `?demo=${demo}` : ''}`,
  );
  const [result, setResult] = useState<PortfolioResult>();
  const [busy, setBusy] = useState(''),
    [error, setError] = useState(''),
    [confirmDelete, setConfirmDelete] = useState(false);
  const [page, setPage] = useState(0);
  const toast = useToast();
  const total = recipe.legs.reduce((sum, leg) => sum + leg.weight_pct, 0);
  const quote = recipe.legs[0].symbol.split('/')[1];
  const available =
    inputs.data?.datasets.filter((d) => (d.source === 'demo') === demo && d.count <= 2000) ?? [];
  const first = available.find((d) => d.id === recipe.legs[0].dataset_id);
  const chosen = recipe.legs.map((l) => available.find((d) => d.id === l.dataset_id));
  const common = chosen.every(Boolean)
    ? Math.floor(
        (Math.min(...chosen.map((d) => Date.parse(d!.end))) -
          Math.max(...chosen.map((d) => Date.parse(d!.start)))) /
          (frameSeconds[recipe.timeframe] * 1000),
      )
    : 0;
  const valid =
    canRun &&
    (savedInput ||
      (!!catalog.data &&
        recipe.legs.every((l) => catalog.data!.items.some((s) => s.symbol === l.symbol)))) &&
    recipe.legs.length >= 2 &&
    total <= 100 &&
    recipe.legs.every((l) => l.weight_pct > 0 && l.symbol && l.symbol.split('/')[1] === quote) &&
    new Set(recipe.legs.map((l) => l.symbol)).size === recipe.legs.length &&
    (!savedInput ||
      (chosen.every(Boolean) &&
        common >= 60 &&
        common <= 2000 &&
        chosen.every(
          (d) =>
            d!.source === first?.source &&
            d!.environment === first?.environment &&
            d!.timeframe === recipe.timeframe,
        )));
  const set = <K extends keyof PortfolioRecipe>(key: K, value: PortfolioRecipe[K]) =>
    setRecipe((old) => ({ ...old, [key]: value }));
  const leg = (index: number, patch: Partial<PortfolioLeg>) =>
    setRecipe((old) => ({
      ...old,
      legs: old.legs.map((l, i) => (i === index ? { ...l, ...patch } : l)),
    }));
  const act = async (action: 'run' | 'read' | 'rerun' | 'delete', id?: string) => {
    setBusy(action);
    setError('');
    try {
      if (action === 'delete') {
        await api(`${base}/${id}`, { method: 'DELETE' });
        setResult(undefined);
        setConfirmDelete(false);
      } else {
        const next =
          action === 'read'
            ? await api<PortfolioResult>(`${base}/${id}`)
            : action === 'rerun'
              ? await post<PortfolioResult>(`${base}/${id}/rerun`)
              : await post<PortfolioResult>(base, {
                  ...recipe,
                  input_kind: savedInput ? 'saved_datasets' : demo ? 'demo' : 'current_feed',
                  legs: recipe.legs.map((l) => ({
                    ...l,
                    ...(!savedInput ? { dataset_id: undefined } : {}),
                  })),
                });
        setResult(next);
        setPage(0);
        setConfirmDelete(false);
        if (action !== 'read')
          toast(
            action === 'rerun'
              ? 'Portfolio study reproduced from exact saved inputs.'
              : 'Portfolio backtest complete. Inputs and results saved.',
          );
      }
      history.retry();
      inputs.retry();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy('');
    }
  };
  return (
    <div className="portfolio-research">
      <div className="portfolio-research-intro">
        <Layers3 size={22} />
        <div>
          <h2>Test the whole mix.</h2>
          <p>Set target weights, rebalance through history, and see where the costs go.</p>
        </div>
        <Badge tone={demo ? 'sand' : 'blue'}>
          {demo ? 'Demo · synthetic prices' : 'Historical simulation'}
        </Badge>
      </div>
      <div className="portfolio-research-grid">
        <Panel>
          <PanelTitle
            title="Your allocation"
            subtitle="2–8 assets · same quote currency · residual cash"
          />
          {!canRun && (
            <p className="inline-alert">
              Connect an exchange account or activate Demo to create a study. Saved studies remain
              available. <Link to="/settings?tab=exchanges">Open account settings ↗</Link>
            </p>
          )}
          {canRun ? (
            <form
              className="form"
              onSubmit={(e) => {
                e.preventDefault();
                void act('run');
              }}
            >
              <label>
                Study title
                <input
                  value={recipe.title}
                  maxLength={100}
                  onChange={(e) => set('title', e.target.value)}
                />
              </label>
              <label>
                Historical input
                <select
                  aria-label="Historical input"
                  value={savedInput ? 'saved' : 'current'}
                  onChange={(e) => setSavedInput(e.target.value === 'saved')}
                >
                  <option value="current">
                    {demo ? 'Synthetic Demo prices' : 'Current market feed'} · exact inputs saved
                  </option>
                  <option value="saved">Immutable saved datasets · offline</option>
                </select>
              </label>
              {!savedInput && (
                <p className="footnote">
                  {catalog.data?.source_label || 'Selected market feed'} ·{' '}
                  <Link to="/settings?tab=market">Market data settings ↗</Link>
                </p>
              )}
              {(savedInput ? inputs.error : catalog.error) && (
                <ErrorState
                  message={savedInput ? inputs.error : catalog.error}
                  retry={savedInput ? inputs.retry : catalog.retry}
                />
              )}
              {recipe.legs.map((l, i) => (
                <div className="portfolio-leg" key={i}>
                  <div>
                    {savedInput ? (
                      <SearchPicker
                        label={`Dataset for asset ${i + 1}`}
                        value={l.dataset_id || ''}
                        onChange={(id) => {
                          const d = available.find((x) => x.id === id);
                          if (d) {
                            leg(i, { dataset_id: id, symbol: d.symbol });
                            if (i === 0) set('timeframe', d.timeframe);
                          }
                        }}
                        placeholder="Choose a retained dataset"
                        groups={[
                          {
                            label: 'Immutable inputs',
                            options: available
                              .filter(
                                (d) =>
                                  i === 0 ||
                                  !first ||
                                  (d.source === first.source &&
                                    d.environment === first.environment &&
                                    d.timeframe === first.timeframe &&
                                    d.symbol.split('/')[1] === quote),
                              )
                              .map((d) => ({
                                value: d.id,
                                label: d.symbol,
                                description: `${d.source_label} · ${d.timeframe} · ${d.count} bars · ${d.start.slice(0, 10)}`,
                                keywords: d.label,
                              })),
                          },
                        ]}
                      />
                    ) : catalog.data ? (
                      <MarketSelector
                        value={l.symbol}
                        onChange={(symbol) => leg(i, { symbol })}
                        catalog={
                          i === 0
                            ? catalog.data
                            : {
                                ...catalog.data,
                                items: catalog.data.items.filter((s) => s.quote === quote),
                              }
                        }
                        label={`Asset ${i + 1}`}
                        exclude={recipe.legs.filter((_, j) => j !== i).map((x) => x.symbol)}
                      />
                    ) : (
                      <Loading />
                    )}
                  </div>
                  <label>
                    Weight %
                    <input
                      aria-label={`Asset ${i + 1} weight`}
                      type="number"
                      min=".01"
                      max="100"
                      step=".01"
                      value={l.weight_pct}
                      onChange={(e) => leg(i, { weight_pct: Number(e.target.value) })}
                    />
                  </label>
                  <button
                    className="icon-button"
                    type="button"
                    disabled={recipe.legs.length <= 2}
                    aria-label={`Remove asset ${i + 1}`}
                    onClick={() =>
                      set(
                        'legs',
                        recipe.legs.filter((_, j) => j !== i),
                      )
                    }
                  >
                    <X size={14} />
                  </button>
                </div>
              ))}
              <div className="portfolio-allocation-actions">
                <Badge tone={total > 100 ? 'sand' : 'blue'}>
                  {number(100 - total, 2)}% quote cash · {quote || 'choose a quote'}
                </Badge>
                <button
                  type="button"
                  className="text-button"
                  onClick={() => {
                    const weight = Math.round((100 / recipe.legs.length) * 100) / 100;
                    set(
                      'legs',
                      recipe.legs.map((l, i) => ({
                        ...l,
                        weight_pct:
                          i === recipe.legs.length - 1
                            ? Math.round((100 - weight * i) * 100) / 100
                            : weight,
                      })),
                    );
                  }}
                >
                  Equal weights
                </button>
                <button
                  type="button"
                  className="text-button"
                  disabled={recipe.legs.length >= 8}
                  onClick={() => {
                    const next = catalog.data?.items.find(
                      (s) => s.quote === quote && !recipe.legs.some((l) => l.symbol === s.symbol),
                    );
                    set('legs', [...recipe.legs, { symbol: next?.symbol || '', weight_pct: 5 }]);
                  }}
                >
                  <Plus size={13} />
                  Add asset
                </button>
              </div>
              {total > 100 && (
                <p className="form-error">
                  Weights exceed 100%. Reduce allocations to keep the study unleveraged.
                </p>
              )}
              {savedInput ? (
                <p className="footnote">
                  {common > 0
                    ? `${common} common candles from the selected inputs.`
                    : 'Choose one compatible dataset for every asset.'}{' '}
                  Inputs must share the source, timeframe and exact quote. No missing-price filling.
                </p>
              ) : (
                <div className="form-row">
                  <TimeframeSelect
                    value={recipe.timeframe}
                    onChange={(v) => set('timeframe', v)}
                    catalog={catalog.data}
                  />
                  <label>
                    Closed candles
                    <input
                      type="number"
                      min="60"
                      max="2000"
                      value={recipe.candles}
                      onChange={(e) => set('candles', Number(e.target.value))}
                    />
                  </label>
                </div>
              )}
              <div className="form-row">
                <label>
                  Starting capital · {quote}
                  <input
                    type="number"
                    min="100"
                    max="100000000"
                    value={recipe.capital}
                    onChange={(e) => set('capital', Number(e.target.value))}
                  />
                </label>
                <label>
                  Rebalance when
                  <select
                    value={recipe.rule}
                    onChange={(e) => set('rule', e.target.value as PortfolioRecipe['rule'])}
                  >
                    <option value="interval">A fixed candle interval passes</option>
                    <option value="drift">An allocation drifts from target</option>
                  </select>
                </label>
              </div>
              {recipe.rule === 'interval' ? (
                <label>
                  Rebalance every · candles
                  <input
                    type="number"
                    min="1"
                    max="500"
                    value={recipe.interval_bars}
                    onChange={(e) => set('interval_bars', Number(e.target.value))}
                  />
                </label>
              ) : (
                <label>
                  Maximum weight deviation · percentage points
                  <input
                    type="number"
                    min=".1"
                    max="50"
                    step=".1"
                    value={recipe.drift_pct}
                    onChange={(e) => set('drift_pct', Number(e.target.value))}
                  />
                </label>
              )}
              <details className="portfolio-cost-settings">
                <summary>Costs & simulation assumptions</summary>
                <div className="form-row">
                  <label>
                    Fee · basis points per fill
                    <input
                      type="number"
                      min="0"
                      max="200"
                      step=".1"
                      value={recipe.fee_bps}
                      onChange={(e) => set('fee_bps', Number(e.target.value))}
                    />
                  </label>
                  <label>
                    Adverse slippage · basis points
                    <input
                      type="number"
                      min="0"
                      max="200"
                      step=".1"
                      value={recipe.slippage_bps}
                      onChange={(e) => set('slippage_bps', Number(e.target.value))}
                    />
                  </label>
                </div>
                <p className="footnote">
                  Previous-close drift triggers next-open sizing/fills. Fractional units, no venue
                  limits or liquidity constraints. Cash earns zero. Both portfolios pay final-close
                  liquidation costs. This study does not place orders or start a strategy.
                </p>
              </details>
              <button className="button primary" type="submit" disabled={!!busy || !valid}>
                {busy === 'run' ? 'Capturing inputs & simulating…' : 'Run portfolio backtest'}
              </button>
            </form>
          ) : (
            <p className="footnote">
              Choose an account mode above to configure new inputs. Existing studies can be
              inspected and replayed offline.
            </p>
          )}
        </Panel>
        <div>
          <Panel>
            <PanelTitle
              title="Saved portfolio studies"
              subtitle="Exact inputs · retained decisions · offline reruns"
            />
            {history.loading ? (
              <Loading />
            ) : history.error ? (
              <ErrorState message={history.error} retry={history.retry} />
            ) : !history.data?.items.length ? (
              <Empty title="Start with your own mix">
                Your studies will appear here with their original prices, costs and target weights.
              </Empty>
            ) : (
              <div className="portfolio-saved-list">
                {history.data.items.map((r) => (
                  <button
                    key={r.id}
                    className={result?.id === r.id ? 'is-selected' : ''}
                    disabled={!!busy}
                    onClick={() => void act('read', r.id)}
                  >
                    <div>
                      <strong>{r.title}</strong>
                      <span>
                        {r.parameters.legs.length} assets · {r.window.count} bars · {r.timeframe}
                      </span>
                    </div>
                    <span>
                      {number(r.return_pct, 2)}%
                      <small>{r.environment === 'demo' ? 'Demo' : r.source_label}</small>
                    </span>
                  </button>
                ))}
              </div>
            )}
          </Panel>
          <Panel className="portfolio-method">
            <Badge>One common clock</Badge>
            <h3>A fair comparison starts with the same prices.</h3>
            <p>
              Rebalanced, buy-and-hold and cash portfolios share the same initial capital and common
              window. Missing dates stay missing; targets do not imply future returns.
            </p>
            <p>
              Open a saved study to inspect every simulated fill, rebalancing event and source
              receipt.
            </p>
          </Panel>
        </div>
      </div>
      {error && (
        <p className="form-error" role="alert">
          {error}
        </p>
      )}
      {result && (
        <Panel className="portfolio-results">
          <PanelTitle
            title={result.title}
            subtitle={`${result.source_label} · ${result.window.count} common ${result.timeframe} candles · ${result.quote}`}
            action={<AgentButton module="broker" context={{ backtest_id: result.id }} />}
          />
          <div className="inline-badges">
            <Badge tone={result.source === 'demo' ? 'sand' : 'blue'}>
              {result.source === 'demo' ? 'Demo · synthetic data' : 'Historical simulation'}
            </Badge>
            <Badge>{result.parameters.legs.length} assets</Badge>
            {result.rerun_of && <Badge>Exact-input rerun</Badge>}
          </div>
          <div className="portfolio-result-stats">
            <div>
              <span>Final equity · {result.quote}</span>
              <strong>{number(result.final_equity, 2)}</strong>
            </div>
            <div>
              <span>Portfolio return</span>
              <strong>{number(result.return_pct, 2)}%</strong>
            </div>
            <div>
              <span>Maximum drawdown</span>
              <strong>{number(result.max_drawdown, 2)}%</strong>
            </div>
            <div>
              <span>Vs buy & hold · percentage points</span>
              <strong>{number(result.excess_return_pct, 2)}</strong>
            </div>
          </div>
          <PortfolioChart key={result.id} result={result} />
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Historical portfolio</th>
                  <th>Final equity · {result.quote}</th>
                  <th>Return</th>
                  <th>Max drawdown</th>
                  <th>Fees · {result.quote}</th>
                </tr>
              </thead>
              <tbody>
                {[
                  ['Rebalanced', result],
                  ['Buy & hold', result.benchmarks.buy_hold],
                  ['Cash · zero interest', result.benchmarks.cash],
                ].map(([label, value]) => {
                  const m = value as typeof result;
                  return (
                    <tr key={String(label)}>
                      <td>{String(label)}</td>
                      <td>{number(m.final_equity, 2)}</td>
                      <td>{number(m.return_pct, 2)}%</td>
                      <td>{number(m.max_drawdown, 2)}%</td>
                      <td>{number(m.fees, 4)}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          <details className="portfolio-evidence">
            <summary>Risk, costs & source receipts</summary>
            <div className="portfolio-evidence-metrics">
              <span>
                Sharpe{' '}
                <strong>{result.sharpe == null ? 'Undefined' : number(result.sharpe, 3)}</strong>
              </span>
              <span>
                Sortino{' '}
                <strong>{result.sortino == null ? 'Undefined' : number(result.sortino, 3)}</strong>
              </span>
              <span>
                Annualized volatility{' '}
                <strong>{number(result.annualized_volatility_pct ?? 0, 2)}%</strong>
              </span>
              <span>
                Rebalances <strong>{result.rebalance_count}</strong>
              </span>
              <span>
                Rebalance gross turnover{' '}
                <strong>{number(result.rebalance_turnover_pct, 2)}%</strong>
              </span>
              <span>
                Slippage cost · {result.quote} <strong>{number(result.slippage_cost, 4)}</strong>
              </span>
            </div>
            <p className="footnote">
              Turnover sums traded mark value / pre-trade NAV for rebalances only; initial and final
              fills are excluded. Sharpe/Sortino use a zero target, timeframe annualization and
              observed simulated returns.
            </p>
            <p className="footnote">{result.assumptions}</p>
            <p className="footnote">
              {result.window.start} → {result.window.end} (exclusive){' '}
              {result.window.trimmed ? '· individual inputs trimmed to the common overlap' : ''}
            </p>
            {result.datasets.map((d) => (
              <p className="footnote" key={d.id}>
                <strong>{d.symbol}</strong> · {d.source_label} · {d.count} retained bars · input{' '}
                {d.digest.slice(0, 16)}…
              </p>
            ))}
            <p className="footnote">
              Engine {result.engine_revision} · decisions {result.decision_fingerprint.slice(0, 16)}
              …
            </p>
          </details>
          <details className="portfolio-evidence">
            <summary>Simulated buys & sells · {result.fills.length} fills</summary>
            <p className="footnote">
              Execution times use your local timezone. Scroll the table sideways to inspect
              quantities, prices, fees and reasons.
            </p>
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>Execution time</th>
                    <th>Asset</th>
                    <th>Side</th>
                    <th>Quantity</th>
                    <th>Price · {result.quote}</th>
                    <th>Fee</th>
                    <th>Reason</th>
                  </tr>
                </thead>
                <tbody>
                  {result.fills.slice(page * 50, (page + 1) * 50).map((f, i) => (
                    <tr key={i}>
                      <td>
                        {new Date(f.execution_at).toLocaleString()}
                        <small>{f.phase}</small>
                      </td>
                      <td>{f.symbol}</td>
                      <td>
                        <Badge tone={f.side === 'buy' ? 'lime' : 'sand'}>{f.side}</Badge>
                      </td>
                      <td>{number(f.quantity, 8)}</td>
                      <td>{number(f.price, 6)}</td>
                      <td>{number(f.fee, 6)}</td>
                      <td>{f.reason}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="portfolio-actions">
              <button
                className="text-button"
                disabled={page === 0}
                onClick={() => setPage((p) => p - 1)}
              >
                Previous
              </button>
              <span>
                {Math.min(page * 50 + 1, result.fills.length)}–
                {Math.min((page + 1) * 50, result.fills.length)} of {result.fills.length}
              </span>
              <button
                className="text-button"
                disabled={(page + 1) * 50 >= result.fills.length}
                onClick={() => setPage((p) => p + 1)}
              >
                Next 50
              </button>
            </div>
          </details>
          <div className="portfolio-actions">
            <button
              className="button secondary tiny"
              disabled={!!busy}
              onClick={() => void act('rerun', result.id)}
            >
              <RefreshCw size={13} />
              {busy === 'rerun' ? 'Replaying…' : 'Rerun exact inputs'}
            </button>
            <button
              className="text-button"
              onClick={() =>
                void downloadFile(
                  `${base}/${result.id}`,
                  `sibyl-portfolio-${result.id}.json`,
                ).catch((e) => setError(e.message))
              }
            >
              Export full study
            </button>
            <button
              className="text-button"
              onClick={() =>
                exportCSV(`sibyl-portfolio-fills-${result.id}.csv`, [
                  [
                    'Execution time',
                    'Candle timestamp',
                    'Asset',
                    'Side',
                    'Quantity',
                    'Price',
                    'Fee',
                    'Slippage cost',
                    'Reason',
                  ],
                  ...result.fills.map((f) => [
                    f.execution_at,
                    f.timestamp,
                    f.symbol,
                    f.side,
                    f.quantity,
                    f.price,
                    f.fee,
                    f.slippage_cost,
                    f.reason,
                  ]),
                ])
              }
            >
              Export fills CSV
            </button>
            <button
              className="text-button"
              disabled={!!busy}
              onClick={() => {
                if (!confirmDelete) setConfirmDelete(true);
                else void act('delete', result.id);
              }}
            >
              <Trash2 size={12} />
              {confirmDelete ? 'Confirm delete study' : 'Delete study'}
            </button>
            {confirmDelete && (
              <button className="text-button" onClick={() => setConfirmDelete(false)}>
                Keep study
              </button>
            )}
          </div>
        </Panel>
      )}
    </div>
  );
}

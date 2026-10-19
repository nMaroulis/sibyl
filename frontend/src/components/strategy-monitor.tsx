import { useCallback, useEffect, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import {
  ArrowLeft,
  Download,
  Pause,
  Play,
  RefreshCw,
  Square,
  Radio,
  Activity,
  List,
  SlidersHorizontal,
} from 'lucide-react';
import {
  Badge,
  Change,
  DataNote,
  ErrorState,
  Loading,
  Modal,
  Panel,
  PanelTitle,
  useToast,
} from './ui';
import { SectionTabs, SectionPanel } from './section-tabs';
import { AgentButton } from './agents';
import { StrategyChart } from './strategy-chart';
import { DecisionJournal } from './strategy-journal';
import { exportCSV, number, post, refresh } from '../lib/api';
import { date, formatted, monitorURL, runName, tone } from '../lib/strategy-monitor';
import { useResource } from '../lib/hooks';
import type { Job, Strategy, StrategyMonitorData } from '../lib/types';
export { StrategyList } from './strategy-run-list';

/** Detail view of one real persisted run; browser refresh never ticks the strategy. */
export function StrategyMonitor({
  jobId,
  jobs,
  catalog,
}: {
  jobId: string;
  jobs: Job[];
  catalog: Strategy[];
}) {
  const navigate = useNavigate();
  const [live, setLive] = useState(true);
  const [limit, setLimit] = useState(300);
  const [mode, setMode] = useState<'price' | 'equity' | 'drawdown'>('price');
  const [showSlippage, setShowSlippage] = useState(false);
  const [showSkips, setShowSkips] = useState(false);
  const [tab, setTab] = useState('overview');
  const [busy, setBusy] = useState('');
  const [stop, setStop] = useState(false);
  const closeStop = useCallback(() => setStop(false), []);
  const [clock, setClock] = useState(Date.now());
  const monitor = useResource<StrategyMonitorData>(
    `/strategies/jobs/${encodeURIComponent(jobId)}?limit=${limit}`,
    live ? 5000 : 0,
  );
  const toast = useToast();
  useEffect(() => {
    const timer = window.setInterval(() => setClock(Date.now()), 5000);
    return () => clearInterval(timer);
  }, []);
  const job = monitor.data?.job;
  const control = async (action: 'pause' | 'resume' | 'stop') => {
    setBusy(action);
    try {
      await post(`/strategies/jobs/${encodeURIComponent(jobId)}/${action}`);
      setStop(false);
      refresh();
      toast(
        action === 'stop'
          ? 'Paper strategy stopped. Its position and history are retained.'
          : action === 'pause'
            ? 'Paper strategy paused.'
            : 'Paper strategy resumed.',
      );
    } catch (error) {
      toast((error as Error).message, true);
    } finally {
      setBusy('');
    }
  };
  if (!job || !monitor.data)
    return monitor.loading ? (
      <Loading />
    ) : (
      <ErrorState message={monitor.error} retry={monitor.retry} />
    );
  const data = monitor.data;
  const quote = job.parameters.symbol.split('/')[1],
    base = job.parameters.symbol.split('/')[0];
  const precision = ['BTC', 'ETH'].includes(quote) ? 8 : 2;
  const terminal = ['completed', 'stopped'].includes(job.status);
  const age = job.observed_at
    ? Math.max(0, Math.round((clock - Date.parse(job.observed_at)) / 1000))
    : null;
  const stale = live && job.status === 'running' && (age == null || age > 90);
  const awaitingFirstTick = clock - Date.parse(job.updated_at ?? job.created_at) < 45000;
  const latest = data.markers.filter((row) => row.fill_price != null).slice(-1)[0];
  const returns = job.completed_returns ?? [];
  const metrics = job.metrics;
  return (
    <div className="strategy-monitor-detail">
      <div className="monitor-breadcrumb">
        <Link className="text-link" to={monitorURL()}>
          <ArrowLeft size={14} /> All strategy runs
        </Link>
        <label className="sr-only" htmlFor="switch-strategy">
          Switch strategy run
        </label>
        <select
          id="switch-strategy"
          value={jobId}
          onChange={(e) => {
            navigate(monitorURL(e.target.value));
          }}
        >
          {!jobs.some((item) => item.id === jobId) && (
            <option value={jobId}>{runName(job, catalog)}</option>
          )}
          {jobs.map((item) => (
            <option key={item.id} value={item.id}>
              {runName(item, catalog)} · {item.parameters.symbol} · {item.id.slice(0, 8)}
            </option>
          ))}
        </select>
      </div>
      <Panel className="monitor-run-header">
        <div>
          <div className="monitor-run-topline">
            <span
              className={`monitor-status-dot ${job.status === 'running' && !stale ? 'active' : ''}`}
            />
            <Badge tone={tone(job.status)}>{job.status}</Badge>
            <Badge>Paper execution</Badge>
            <DataNote source={job.source} />
          </div>
          <h2>{runName(job, catalog)}</h2>
          <p>
            {job.parameters.symbol} <span>·</span> {job.parameters.timeframe ?? '1d'} candles{' '}
            <span>·</span> Run {job.id.slice(0, 8)}
          </p>
          <small>
            Started {date(job.created_at)} · Last worker check {date(job.checked_at)}
          </small>
        </div>
        <div className="monitor-run-actions">
          <AgentButton module="broker" context={{ job_id: job.id }} compact />
          {!terminal && (
            <>
              <button
                className="button secondary"
                disabled={!!busy}
                onClick={() => control(job.status === 'running' ? 'pause' : 'resume')}
              >
                {job.status === 'running' ? <Pause size={14} /> : <Play size={14} />}{' '}
                {busy || (job.status === 'running' ? 'Pause' : 'Resume')}
              </button>
              <button
                className="button secondary monitor-stop"
                disabled={!!busy}
                onClick={() => setStop(true)}
              >
                <Square size={12} /> Stop
              </button>
            </>
          )}
        </div>
      </Panel>
      {monitor.error && (
        <div className="inline-alert" role="alert">
          Could not refresh: {monitor.error}. Showing the last received snapshot.
          <button className="text-button" onClick={monitor.retry}>
            Retry
          </button>
        </div>
      )}
      {!live && (
        <div className="monitor-notice">
          Auto-refresh is off. This pauses your view, not the strategy. Use Refresh to read the
          latest state.
        </div>
      )}
      {job.error && (
        <div className="inline-alert" role="alert">
          Worker: {job.error}
        </div>
      )}
      {stale && !job.error && (
        <div className="monitor-notice">
          {age == null || awaitingFirstTick
            ? 'Waiting for the next successful worker observation.'
            : 'The last price observation is over 90 seconds old. Check that the API worker is running.'}
        </div>
      )}
      {terminal && (
        <div className="monitor-notice">
          This run is {job.status}. Its virtual position is retained and the valuation is frozen at
          its final worker observation. Start a new run to evaluate again.
        </div>
      )}
      {job.status === 'paused' && (
        <div className="monitor-notice">
          Evaluation and price sampling are paused. Your virtual position is retained; Resume
          continues from the latest closed candle.
        </div>
      )}
      {!job.statistics_complete && (
        <div className="monitor-notice">
          This run predates detailed monitoring. New observations and decisions are journaled from{' '}
          {date(job.monitoring_since)}. Earlier retained fills are shown below; missing reference
          prices and lifetime statistics stay unavailable.
        </div>
      )}
      <div className="monitor-summary-grid">
        <Panel>
          <small>Paper equity · {quote}</small>
          <strong>{number(job.equity, precision)}</strong>
          <Change value={(job.equity / job.parameters.capital - 1) * 100} />
        </Panel>
        <Panel>
          <small>Total P&L · {quote}</small>
          <strong className={job.equity >= job.parameters.capital ? 'positive' : 'negative'}>
            {number(job.equity - job.parameters.capital, precision)}
          </strong>
          <span>Marked at last observed quote</span>
        </Panel>
        <Panel>
          <small>Available cash · {quote}</small>
          <strong>{number(job.cash, precision)}</strong>
          <span>Initial {number(job.parameters.capital, precision)}</span>
        </Panel>
        <Panel>
          <small>Open position · {base}</small>
          <strong>{number(job.quantity, 8)}</strong>
          <span>{job.quantity > 0 ? 'Long spot position' : 'No open position'}</span>
        </Panel>
      </div>
      <div className="monitor-section-tabs">
        <SectionTabs
          id="strategy-run"
          label="Run sections"
          compact
          items={[
            { id: 'overview', label: 'Live view', icon: Activity },
            {
              id: 'activity',
              label: 'Decision journal',
              icon: List,
              detail: String(data.event_count),
            },
            { id: 'parameters', label: 'Run parameters', icon: SlidersHorizontal },
          ]}
          value={tab}
          onChange={setTab}
        />
        <label className="monitor-live-toggle">
          <input type="checkbox" checked={live} onChange={(e) => setLive(e.target.checked)} />{' '}
          <Radio size={13} /> {live ? 'Auto-refresh · 5s' : 'Auto-refresh off'}
        </label>
        <button className="icon-button" aria-label="Refresh strategy monitor" onClick={refresh}>
          <RefreshCw size={15} />
        </button>
      </div>
      <SectionPanel id="strategy-run" value={tab}>
        {tab === 'overview' ? (
          <>
            <Panel className="full-panel">
              <PanelTitle
                title={
                  mode === 'price'
                    ? `Price & execution · ${quote}`
                    : mode === 'equity'
                      ? `Paper equity · ${quote}`
                      : 'Drawdown in the displayed window · %'
                }
                subtitle={`${data.observations.length} observed samples · latest price ${formatted(job.reference_price, precision)} ${quote}`}
                action={
                  <div className="filter-pills">
                    {(['price', 'equity', 'drawdown'] as const).map((value) => (
                      <button
                        className={mode === value ? 'selected' : ''}
                        key={value}
                        onClick={() => setMode(value)}
                      >
                        {value[0].toUpperCase() + value.slice(1)}
                      </button>
                    ))}
                  </div>
                }
              />
              <div className="monitor-chart-controls">
                <label>
                  Observation window
                  <select value={limit} onChange={(e) => setLimit(Number(e.target.value))}>
                    <option value={100}>Latest 100 samples</option>
                    <option value={300}>Latest 300 samples</option>
                    <option value={1000}>Latest 1,000 samples</option>
                    <option value={2000}>Latest 2,000 samples</option>
                  </select>
                </label>
                {mode === 'price' && (
                  <>
                    <label>
                      <input
                        type="checkbox"
                        checked={showSlippage}
                        onChange={(e) => setShowSlippage(e.target.checked)}
                      />{' '}
                      Show simulated slippage
                    </label>
                    <label>
                      <input
                        type="checkbox"
                        checked={showSkips}
                        onChange={(e) => setShowSkips(e.target.checked)}
                      />{' '}
                      Show skipped signals
                    </label>
                  </>
                )}
                <button
                  className="text-button"
                  disabled={!data.observations.length}
                  onClick={() =>
                    exportCSV(`sibyl-${job.id.slice(0, 8)}-observations.csv`, [
                      [
                        'Timestamp',
                        'Reference price',
                        'Paper equity',
                        'Cash',
                        'Position',
                        'Symbol',
                        'Quote',
                        'Source',
                      ],
                      ...data.observations.map((row) => [
                        row.timestamp,
                        row.price,
                        row.equity,
                        row.cash,
                        row.position,
                        job.source,
                      ]),
                    ])
                  }
                >
                  <Download size={12} /> Export displayed samples
                </button>
              </div>
              <StrategyChart
                monitor={data}
                mode={mode}
                showSkips={showSkips}
                showSlippage={showSlippage}
              />
              <div className="chart-footnote">
                <span className="monitor-legend">
                  <i className="legend-buy" /> BUY <i className="legend-sell" /> SELL{' '}
                  {showSkips && (
                    <>
                      <i className="legend-skip" /> Skipped signal
                    </>
                  )}
                </span>
                <span>
                  {age == null ? 'No quote observed yet' : `Price observed ${age}s ago`} · Worker
                  checks every {data.worker_interval}s
                </span>
              </div>
              <p className="footnote padded">
                The worker records quotes every 30 seconds and makes at most one decision per newly
                closed {job.parameters.timeframe ?? '1d'} candle. Refreshing this page does not
                execute the strategy. Slippage is simulated fill minus reference price: positive is
                adverse for buys, negative is adverse for sells.
              </p>
            </Panel>
            <div className="monitor-insight-grid">
              <Panel>
                <PanelTitle
                  title="Recorded performance"
                  subtitle="Closed-candle risk metrics · zero risk-free rate"
                />
                <div className="extended-metrics">
                  {[
                    ['Sharpe', metrics?.sharpe],
                    ['Sortino', metrics?.sortino],
                    ['Calmar', metrics?.calmar],
                    ['Max drawdown (%)', metrics?.max_drawdown],
                    ['Profit factor · return ratio', metrics?.profit_factor],
                    [
                      'Win rate (%)',
                      returns.length
                        ? (returns.filter((v) => v > 0).length / returns.length) * 100
                        : null,
                    ],
                    ['Average win (%)', metrics?.average_win],
                    ['Average loss (%)', metrics?.average_loss],
                  ].map(([name, value]) => (
                    <div key={String(name)}>
                      <small>{name}</small>
                      <strong>{formatted(value as number | null | undefined)}</strong>
                    </div>
                  ))}
                </div>
                <p className="footnote padded">
                  Risk ratios use up to 720 retained closed-candle equity observations. Profit
                  factor uses round-trip percentage returns. Gaps and short samples affect these
                  estimates.
                </p>
              </Panel>
              <Panel>
                <PanelTitle title="Execution details" subtitle="Your isolated virtual account" />
                <div className="stat-list">
                  <div>
                    <span>Recorded realized P&L · {quote}</span>
                    <strong>
                      {formatted(job.statistics_complete ? job.realized_pnl : null, precision)}
                    </strong>
                  </div>
                  <div>
                    <span>Entry cost incl. fees · {quote}</span>
                    <strong>
                      {formatted(job.quantity > 0 ? job.entry_cost : null, precision)}
                    </strong>
                  </div>
                  <div>
                    <span>Total simulated fees · {quote}</span>
                    <strong>
                      {formatted(job.statistics_complete ? job.fees_paid : null, precision)}
                    </strong>
                  </div>
                  <div>
                    <span>Completed round trips</span>
                    <strong>
                      {job.round_trips ?? returns.length} /{' '}
                      {job.parameters.max_trades ?? 'unlimited'}
                    </strong>
                  </div>
                  <div>
                    <span>Last filled action</span>
                    <strong>{latest?.action ?? '—'}</strong>
                  </div>
                  <div>
                    <span>Last evaluated candle</span>
                    <strong>{date(job.last_candle)}</strong>
                  </div>
                </div>
              </Panel>
            </div>
          </>
        ) : tab === 'activity' ? (
          <DecisionJournal jobId={job.id} interval={live ? 5000 : 0} quote={quote} />
        ) : (
          <Panel className="full-panel">
            <PanelTitle
              title="Parameters at launch"
              subtitle="Fixed for this run. Build another strategy to try a different configuration."
            />
            <dl className="monitor-parameters">
              {Object.entries(job.parameters).map(([key, value]) => (
                <div key={key}>
                  <dt>{key.replaceAll('_', ' ')}</dt>
                  <dd>{value == null ? 'Off / default' : String(value)}</dd>
                </div>
              ))}
              <div>
                <dt>Source</dt>
                <dd>{job.source}</dd>
              </div>
              <div>
                <dt>Run ID</dt>
                <dd>{job.id}</dd>
              </div>
            </dl>
          </Panel>
        )}
      </SectionPanel>
      {data.legacy_fills.length > 0 && (
        <Panel className="full-panel">
          <PanelTitle
            title="Earlier retained fills"
            subtitle="Recorded before the detailed journal; reference prices and slippage may be unavailable"
            action={
              <button
                className="button secondary tiny"
                onClick={() =>
                  exportCSV(`sibyl-${job.id.slice(0, 8)}-earlier-fills.csv`, [
                    ['Time', 'Side', 'Fill price', 'Quantity', 'Fee'],
                    ...data.legacy_fills.map((row) => [
                      row.timestamp,
                      row.side,
                      row.price,
                      row.quantity,
                      row.fee ?? '',
                    ]),
                  ])
                }
              >
                <Download size={12} /> Export earlier fills
              </button>
            }
          />
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Time</th>
                  <th>Action</th>
                  <th>Fill price · {quote}</th>
                  <th>Quantity</th>
                  <th>Fee</th>
                </tr>
              </thead>
              <tbody>
                {data.legacy_fills.map((fill, i) => (
                  <tr key={i}>
                    <td>{date(fill.timestamp)}</td>
                    <td>
                      <Badge>{fill.side}</Badge>
                    </td>
                    <td>{formatted(fill.price, 8)}</td>
                    <td>{formatted(fill.quantity, 8)}</td>
                    <td>{formatted(fill.fee, 6)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Panel>
      )}
      {stop && (
        <Modal title="Stop this paper strategy?" onClose={closeStop}>
          <p className="monitor-stop-copy">
            This permanently stops evaluation for this run. Its {number(job.quantity, 8)} {base}{' '}
            virtual position and history are retained. It does not sell the position, and its
            displayed valuation will stop updating.
          </p>
          <div className="modal-actions">
            <button className="button secondary" disabled={!!busy} onClick={() => setStop(false)}>
              Cancel
            </button>
            <button className="button primary" disabled={!!busy} onClick={() => control('stop')}>
              {busy ? 'Stopping…' : 'Stop paper strategy'}
            </button>
          </div>
        </Modal>
      )}
    </div>
  );
}

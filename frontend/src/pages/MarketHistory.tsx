import { useMemo, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import {
  ArrowLeft,
  Database,
  Download,
  History,
  Pause,
  Play,
  RefreshCw,
  Save,
  Trash2,
} from 'lucide-react';
import {
  Badge,
  ErrorState,
  Loading,
  Modal,
  PageTitle,
  Panel,
  PanelTitle,
  useToast,
} from '../components/ui';
import { SectionPanel, SectionTabs } from '../components/section-tabs';
import { Candlesticks } from '../components/candlesticks';
import { MarketSourcePicker } from '../components/market-source-picker';
import { downloadFile, post, refresh } from '../lib/api';
import { useResource } from '../lib/hooks';
import {
  frameSeconds,
  type CandleHistory,
  type Dataset,
  type DatasetList,
  type Series,
} from '../lib/market-history';
import type { MarketSettings, Timeframe } from '../lib/types';

const stamp = (value: string | null) => (value ? new Date(value).toLocaleString() : 'None yet');
const utcInput = (ms: number) => new Date(ms).toISOString().slice(0, 16);
const wholeNow = (frame: Timeframe) => {
  const step = frameSeconds[frame] * 1000,
    anchor = frame === '1w' ? 345600000 : 0;
  return Math.floor((Date.now() - anchor) / step) * step + anchor;
};

/** Local history reads never open an exchange client. Imports are explicit, checkpointed jobs. */
export function MarketHistoryPage({ settings }: { settings: MarketSettings }) {
  const [params, setParams] = useSearchParams();
  const source = params.get('source') || settings.active.id;
  const symbol = params.get('symbol') || 'BTC/USDT';
  const requestedFrame = params.get('timeframe') as Timeframe;
  const timeframe: Timeframe = requestedFrame in frameSeconds ? requestedFrame : '1d';
  const series = useResource<{ items: Series[]; total: number; truncated: boolean }>(
    '/market-history/series',
  );
  const choose = (values: Record<string, string>) => {
    const next = new URLSearchParams(params);
    Object.entries(values).forEach(([k, v]) => next.set(k, v));
    setParams(next);
  };
  const back = new URLSearchParams(params);
  back.delete('view');
  back.delete('historyTab');
  const tab = params.get('historyTab') === 'datasets' ? 'datasets' : 'candles';
  return (
    <>
      <PageTitle
        title="Market history"
        description="Keep the observations. Know the gaps. Revisit the same experiment."
        action={
          <Link className="button secondary" to={`/markets?${back}`}>
            <ArrowLeft size={14} /> Markets
          </Link>
        }
      />
      <SectionTabs
        id="market-history"
        label="Market history workspace"
        value={tab}
        onChange={(value) => choose({ historyTab: value })}
        items={[
          { id: 'candles', label: 'Retained candles', icon: History },
          { id: 'datasets', label: 'Saved datasets', icon: Database },
        ]}
      />
      <SectionPanel id="market-history" value={tab}>
        {tab === 'datasets' ? (
          <SavedDatasets />
        ) : (
          <>
            <div className="history-source-controls">
              <MarketSourcePicker
                settings={settings}
                value={source}
                allowUnavailable
                onChange={(value) => choose({ source: value })}
              />
              <label>
                Retained series
                <select
                  value={
                    series.data?.items.find(
                      (s) =>
                        s.source === source && s.symbol === symbol && s.timeframe === timeframe,
                    )?.id || ''
                  }
                  onChange={(e) => {
                    const s = series.data?.items.find((s) => s.id === e.target.value);
                    if (s) choose({ source: s.source, symbol: s.symbol, timeframe: s.timeframe });
                  }}
                >
                  <option value="">Choose retained data…</option>
                  {series.data?.items.map((s) => (
                    <option key={s.id} value={s.id}>
                      {s.source_label} · {s.symbol} · {s.timeframe} · {s.retained.toLocaleString()}{' '}
                      bars
                    </option>
                  ))}
                </select>
              </label>
            </div>
            {series.error && <ErrorState message={series.error} retry={series.retry} />}
            {series.data?.truncated && (
              <p className="footnote">
                Showing the latest 1,000 retained series. Enter an exact source and pair to inspect
                another.
              </p>
            )}
            <HistoryRange
              key={`${source}:${symbol}:${timeframe}`}
              source={source}
              symbol={symbol}
              timeframe={timeframe}
              choose={choose}
            />
          </>
        )}
      </SectionPanel>
    </>
  );
}

function HistoryRange({
  source,
  symbol,
  timeframe,
  choose,
}: {
  source: string;
  symbol: string;
  timeframe: Timeframe;
  choose: (v: Record<string, string>) => void;
}) {
  const [draftPair, setDraftPair] = useState(symbol);
  const [start, setStart] = useState(
    utcInput(wholeNow(timeframe) - 180 * frameSeconds[timeframe] * 1000),
  );
  const [end, setEnd] = useState(utcInput(wholeNow(timeframe)));
  const [range, setRange] = useState({ start, end });
  const [label, setLabel] = useState('');
  const [busy, setBusy] = useState('');
  const [error, setError] = useState('');
  const [saved, setSaved] = useState<Dataset>();
  const [pruning, setPruning] = useState(false);
  const [before, setBefore] = useState(start);
  const [confirmation, setConfirmation] = useState('');
  const [mode, setMode] = useState<'candles' | 'line'>('candles');
  const toast = useToast();
  const query = new URLSearchParams({
    source,
    symbol,
    timeframe,
    start: `${range.start}:00Z`,
    end: `${range.end}:00Z`,
  });
  const history = useResource<CandleHistory>(`/market-history?${query}`, 5000);
  const data = history.data,
    coverage = data?.coverage,
    job = data?.job;
  const active = !!job && ['queued', 'running', 'retrying'].includes(job.status);
  const chartData = useMemo(() => data?.candles ?? [], [data?.revision, data?.start, data?.end]);
  const request = {
    source,
    symbol,
    timeframe,
    start: `${range.start}:00Z`,
    end: `${range.end}:00Z`,
  };
  const rangeChecked =
    !!job &&
    ['complete', 'gaps'].includes(job.status) &&
    job.start_ms === Date.parse(request.start) &&
    job.end_ms === Date.parse(request.end);
  const mutate = async (kind: string, path: string, body: unknown) => {
    setBusy(kind);
    setError('');
    try {
      const result = await post(path, body);
      refresh();
      return result;
    } catch (reason) {
      setError((reason as Error).message);
      return undefined;
    } finally {
      setBusy('');
    }
  };
  return (
    <>
      <Panel className="history-panel">
        <PanelTitle
          title="Your retained market data"
          subtitle="Exact source and pair · closed UTC intervals · no substituted prices"
        />
        <form
          className="history-range-controls"
          onSubmit={(event) => {
            event.preventDefault();
            if (draftPair.trim().toUpperCase() !== symbol)
              choose({ symbol: draftPair.trim().toUpperCase() });
            else {
              setRange({ start, end });
              setSaved(undefined);
            }
          }}
        >
          <label>
            Exact spot pair
            <input
              value={draftPair}
              maxLength={25}
              placeholder="BTC/USDT"
              onChange={(e) => setDraftPair(e.target.value)}
            />
          </label>
          <label>
            Timeframe
            <select value={timeframe} onChange={(e) => choose({ timeframe: e.target.value })}>
              {Object.keys(frameSeconds).map((f) => (
                <option key={f}>{f}</option>
              ))}
            </select>
          </label>
          <label>
            From · UTC
            <input
              type="datetime-local"
              required
              value={start}
              onChange={(e) => setStart(e.target.value)}
            />
          </label>
          <label>
            Until · UTC, exclusive
            <input
              type="datetime-local"
              required
              value={end}
              max={utcInput(Date.now())}
              onChange={(e) => setEnd(e.target.value)}
            />
          </label>
          <button className="button secondary" type="submit">
            Inspect range
          </button>
        </form>
        <p className="footnote">
          Range inspection reads local storage only. Whole intervals inside your chosen dates are
          used; at most 50,000 per range.
        </p>
        {history.error && <ErrorState message={history.error} retry={history.retry} />}
        {!data && !history.error && <Loading />}
        {data && (
          <>
            <div className="history-status-heading">
              <strong>
                {data.source_label} · {symbol} · {timeframe}
              </strong>
              <Badge tone={source === 'demo' ? 'sand' : 'neutral'}>
                {source === 'demo'
                  ? 'Demo · synthetic'
                  : data.environment === 'test'
                    ? 'Test environment'
                    : 'Production feed'}
              </Badge>
              {!data.available && <Badge tone="sand">Retained data only</Badge>}
            </div>
            <div className="history-stat-grid">
              <div>
                <small>In this range</small>
                <strong>
                  {coverage?.stored.toLocaleString() ?? 0}{' '}
                  <span>/ {coverage?.expected.toLocaleString() ?? 0}</span>
                </strong>
              </div>
              <div>
                <small>Missing intervals</small>
                <strong>{coverage?.missing.toLocaleString() ?? '—'}</strong>
              </div>
              <div>
                <small>Retained in this series</small>
                <strong>{data.retained.toLocaleString()}</strong>
              </div>
              <div>
                <small>Coverage</small>
                <strong>{coverage?.complete ? 'Complete' : 'Incomplete'}</strong>
              </div>
            </div>
            <p className="footnote">
              Retained extent: {stamp(data.oldest)} — {stamp(data.newest)}. Latest closed interval
              ends {stamp(data.latest_closed_end)}. Displayed dates use your local timezone; range
              fields use UTC.
            </p>
            {data.range_truncated && (
              <p className="footnote">
                Coverage is limited to the most recent 50,000 intervals. Choose a narrower range to
                inspect older data.
              </p>
            )}
            <div className="history-actions">
              <button
                className="button primary"
                disabled={
                  !!busy || active || !data.available || !data.backfill.supported || rangeChecked
                }
                onClick={() => mutate('import', '/market-history/imports', request)}
              >
                <Download size={14} />
                {busy === 'import'
                  ? 'Queuing…'
                  : rangeChecked
                    ? 'Range checked'
                    : 'Import this range'}
              </button>
              <button
                className="text-button"
                onClick={() => setPruning(true)}
                disabled={!data.retained}
              >
                <Trash2 size={13} /> Manage retention
              </button>
            </div>
            <p className="footnote">
              {data.backfill.note} No-trade periods, listing dates and provider history limits can
              all leave gaps.
            </p>
            {job && (
              <div className="history-job">
                <div>
                  <Badge
                    tone={
                      job.status === 'complete'
                        ? 'lime'
                        : job.status === 'error'
                          ? 'rose'
                          : 'neutral'
                    }
                  >
                    {job.status}
                  </Badge>
                  <strong>Saved import</strong>
                  <small>
                    {stamp(job.start)} → {stamp(job.end)}
                  </small>
                </div>
                <progress
                  aria-label="Historical windows checked"
                  value={job.cursor - job.start_ms}
                  max={job.end_ms - job.start_ms}
                />
                <div className="history-job-footer">
                  <span>
                    {job.pages} windows checked · {job.observations.toLocaleString()} observations
                    received · checkpoint {stamp(new Date(job.cursor).toISOString())}
                  </span>
                  {active ? (
                    <button
                      disabled={!!busy}
                      className="text-button"
                      onClick={() =>
                        mutate('pause', `/market-history/imports/${job.id}/action`, {
                          action: 'pause',
                        })
                      }
                    >
                      <Pause size={13} /> Pause
                    </button>
                  ) : (
                    <>
                      {['paused', 'error'].includes(job.status) && (
                        <button
                          disabled={!!busy}
                          className="text-button"
                          onClick={() =>
                            mutate('resume', `/market-history/imports/${job.id}/action`, {
                              action: 'resume',
                            })
                          }
                        >
                          <Play size={13} /> Resume
                        </button>
                      )}
                      <button
                        disabled={!!busy}
                        className="text-button"
                        onClick={() =>
                          mutate('rescan', `/market-history/imports/${job.id}/action`, {
                            action: 'rescan',
                          })
                        }
                      >
                        <RefreshCw size={13} /> Rescan saved range
                      </button>
                    </>
                  )}
                </div>
                {job.error && (
                  <p className="footnote" role="status">
                    {job.error}
                    {job.status === 'retrying' &&
                      ` Next attempt after ${new Date(job.next_attempt * 1000).toLocaleTimeString()}.`}
                  </p>
                )}
              </div>
            )}
            {coverage && coverage.missing > 0 && (
              <details className="advanced-options">
                <summary>
                  {coverage.gap_ranges} missing ranges · {coverage.missing.toLocaleString()}{' '}
                  intervals
                </summary>
                <p className="footnote">
                  Prices are never interpolated. A saved dataset requires a complete, consecutive
                  range.
                </p>
                <div className="history-gap-list">
                  {coverage.gaps.map((g) => (
                    <div key={g.start}>
                      <span>
                        {stamp(g.start)} → {stamp(g.end)}
                      </span>
                      <strong>{g.candles.toLocaleString()} bars</strong>
                    </div>
                  ))}
                </div>
                {coverage.gaps_truncated && (
                  <p className="footnote">
                    Showing the first 100 gap ranges. Narrow the dates to inspect more.
                  </p>
                )}
              </details>
            )}
            {chartData.length > 0 && (
              <>
                <div className="history-status-heading">
                  <strong>Retained preview</strong>
                  <div className="filter-pills">
                    {(['candles', 'line'] as const).map((m) => (
                      <button
                        key={m}
                        className={mode === m ? 'selected' : ''}
                        onClick={() => setMode(m)}
                      >
                        {m === 'line' ? 'Line' : 'Candles'}
                      </button>
                    ))}
                  </div>
                </div>
                <Candlesticks
                  key={`${source}:${symbol}:${timeframe}`}
                  data={chartData}
                  bands={false}
                  mode={mode}
                  intervalSeconds={frameSeconds[timeframe]}
                />
                <p className="footnote">
                  {data.preview_truncated
                    ? 'Showing the latest 2,000 stored bars in the range; coverage above includes the entire range.'
                    : 'Showing all retained bars in the inspected range.'}{' '}
                  Amber markers indicate missing intervals; price lines break at gaps. Bars are
                  evenly spaced by observation.
                </p>
              </>
            )}
            {!chartData.length && (
              <div className="chart-empty">
                No retained candles in this range. Import it to begin collecting history.
              </div>
            )}
            <div className="history-save-row">
              <label>
                Dataset label
                <input
                  value={label}
                  maxLength={100}
                  placeholder={`${symbol} · ${timeframe}`}
                  onChange={(e) => setLabel(e.target.value)}
                />
              </label>
              <button
                className="button secondary"
                disabled={
                  !!busy ||
                  !coverage?.complete ||
                  coverage.expected < 60 ||
                  coverage.expected > 20000
                }
                onClick={async () => {
                  const result = await mutate('save', '/market-history/datasets', {
                    ...request,
                    label,
                  });
                  if (result) {
                    setSaved(result as Dataset);
                    toast('Immutable dataset saved. Its candles will not change.');
                  }
                }}
              >
                <Save size={14} /> Save dataset
              </button>
            </div>
            <p className="footnote">
              Save 60–20,000 consecutive candles. The copied input includes its source, exact pair,
              timeframe and SHA-256 fingerprint; later imports or pruning cannot alter it.
            </p>
            {saved && (
              <p className="history-saved">
                Saved “{saved.label}”.{' '}
                <Link to={`/strategies?dataset=${saved.id}`}>Backtest this dataset →</Link>
              </p>
            )}
          </>
        )}
        {error && (
          <p role="alert" className="form-error">
            {error}
          </p>
        )}
      </Panel>
      {pruning && (
        <Modal
          title="Manage candle retention"
          onClose={() => {
            setPruning(false);
            setConfirmation('');
          }}
        >
          <div className="form">
            <p>
              Remove mutable {symbol} · {timeframe} observations from {data?.source_label} before
              the cutoff. Saved datasets remain available. Pause an active import first.
            </p>
            <label>
              Remove observations before · UTC
              <input
                type="datetime-local"
                value={before}
                onChange={(e) => setBefore(e.target.value)}
              />
            </label>
            <label>
              Type PRUNE {symbol}
              <input
                autoComplete="off"
                value={confirmation}
                onChange={(e) => setConfirmation(e.target.value)}
              />
            </label>
            <button
              className="button secondary"
              disabled={!!busy || active || confirmation !== `PRUNE ${symbol}` || !before}
              onClick={async () => {
                const result = await mutate('prune', '/market-history/retention', {
                  source,
                  symbol,
                  timeframe,
                  before: `${before}:00Z`,
                  confirmation,
                });
                if (result) {
                  setPruning(false);
                  setConfirmation('');
                  toast('Older mutable candles removed. Saved datasets retained.');
                }
              }}
            >
              Prune older observations
            </button>
            {error && (
              <p className="form-error" role="alert">
                {error}
              </p>
            )}
          </div>
        </Modal>
      )}
    </>
  );
}

function SavedDatasets() {
  const [offset, setOffset] = useState(0);
  const list = useResource<DatasetList>(`/market-history/datasets?offset=${offset}`);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState('');
  return (
    <Panel className="history-panel">
      <PanelTitle
        title="Saved research inputs"
        subtitle="Immutable candles · source provenance · repeatable backtests"
      />
      {list.error ? (
        <ErrorState message={list.error} retry={list.retry} />
      ) : !list.data ? (
        <Loading />
      ) : (
        <>
          {!list.data.total && (
            <div className="chart-empty">
              Save a complete range from Retained candles, or run a current-feed backtest. Its exact
              input will appear here.
            </div>
          )}
          <div className="history-datasets">
            {list.data.items.map((d) => (
              <article key={d.id}>
                <div>
                  <h3>{d.label}</h3>
                  <p>
                    {d.source_label} · {d.symbol} · {d.timeframe} · {d.count.toLocaleString()}{' '}
                    candles
                  </p>
                  <small>
                    {stamp(d.start)} → {stamp(d.end)} (exclusive)
                  </small>
                  <code title={d.digest}>SHA-256 {d.digest.slice(0, 16)}…</code>
                </div>
                <div>
                  <Badge tone={d.source === 'demo' ? 'sand' : 'neutral'}>
                    {d.source === 'demo' ? 'Synthetic demo' : d.environment}
                  </Badge>
                  <Link className="button secondary" to={`/strategies?dataset=${d.id}`}>
                    Backtest
                  </Link>
                  <button
                    className="text-button"
                    disabled={!!busy}
                    onClick={async () => {
                      setBusy(d.id);
                      setError('');
                      try {
                        await downloadFile(
                          `/market-history/datasets/${d.id}`,
                          `sibyl-dataset-${d.id.slice(0, 12)}.json`,
                        );
                      } catch (e) {
                        setError((e as Error).message);
                      } finally {
                        setBusy('');
                      }
                    }}
                  >
                    <Download size={13} /> {busy === d.id ? 'Exporting…' : 'Full dataset JSON'}
                  </button>
                </div>
              </article>
            ))}
          </div>
          {list.data.total > 50 && (
            <div className="history-pagination">
              <button
                className="button secondary"
                disabled={!offset}
                onClick={() => setOffset(Math.max(0, offset - 50))}
              >
                Previous
              </button>
              <span>
                {offset + 1}–{Math.min(offset + 50, list.data.total)} of {list.data.total}
              </span>
              <button
                className="button secondary"
                disabled={offset + 50 >= list.data.total}
                onClick={() => setOffset(offset + 50)}
              >
                Next
              </button>
            </div>
          )}
        </>
      )}
      {error && (
        <p className="form-error" role="alert">
          {error}
        </p>
      )}
      <p className="footnote">
        Snapshots are retained separately from the mutable archive. Identical inputs are
        deduplicated. Up to 1,000 snapshots per local workspace.
      </p>
    </Panel>
  );
}

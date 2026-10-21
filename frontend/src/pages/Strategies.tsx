import { useEffect, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { ChevronRight, FlaskConical, Play, Radio } from 'lucide-react';
import {
  Badge,
  Change,
  DataNote,
  Empty,
  ErrorState,
  Loading,
  PageTitle,
  Panel,
  PanelTitle,
  useToast,
} from '../components/ui';
import { SectionTabs, SectionPanel } from '../components/section-tabs';
import { StrategyList, StrategyMonitor } from '../components/strategy-monitor';
import { AgentButton } from '../components/agents';
import { MarketSelector, TimeframeSelect } from '../components/market-controls';
import { ComingSoon } from '../components/coming-soon';
import { ValueChart } from '../components/charts';
import { downloadFile, exportCSV, number, post, refresh } from '../lib/api';
import { useResource } from '../lib/hooks';
import type { Dataset, DatasetList } from '../lib/market-history';
import type { Backtest, Job, Run, Strategy, StrategyParams } from '../lib/types';

export function StrategiesPage() {
  const [search, setSearch] = useSearchParams();
  const selectedView = search.get('view'),
    selectedJob = search.get('job');
  useEffect(() => {
    window.scrollTo({ top: 0, behavior: 'instant' });
  }, [selectedView, selectedJob]);
  const catalog = useResource<Strategy[]>('/strategies');
  const jobs = useResource<Job[]>('/strategies/jobs', 30000);
  const history = useResource<Run[]>('/runs?kind=backtest');
  const [draftParams, setParams] = useState<StrategyParams>({
    strategy: 'ema',
    symbol: 'BTC/USDT',
    capital: 10000,
    candles: 180,
    fee_bps: 10,
    slippage_bps: 5,
    window: 20,
    timeframe: '1d',
    fast_period: 9,
    slow_period: 21,
    rsi_period: 14,
    band_std: 2,
    volume_multiplier: 1.5,
    macd_fast_period: 12,
    macd_slow_period: 26,
    macd_signal_period: 9,
    adx_period: 14,
    atr_period: 14,
    cmf_period: null,
    tsi_short_period: 13,
    tsi_long_period: 25,
  });
  const datasetId = search.get('dataset') || '';
  const datasets = useResource<DatasetList>('/market-history/datasets');
  const selectedDataset = useResource<Dataset>(
    `/market-history/datasets/${datasetId}/metadata`,
    0,
    !!datasetId,
  );
  const dataset = selectedDataset.data;
  const params: StrategyParams =
    datasetId && dataset
      ? {
          ...draftParams,
          symbol: dataset.symbol,
          timeframe: dataset.timeframe,
          candles: dataset.count,
        }
      : draftParams;
  const chooseDataset = (id: string) => {
    const next = new URLSearchParams(search);
    id ? next.set('dataset', id) : next.delete('dataset');
    setSearch(next);
    setResult(undefined);
    setError('');
  };
  const [result, setResult] = useState<Backtest>();
  const [busy, setBusy] = useState('');
  const [error, setError] = useState('');
  const toast = useToast();
  const update = (key: keyof StrategyParams, value: number | string | null) => {
    setParams((old) => ({ ...old, [key]: value }));
    setResult(undefined);
  };
  const run = async (kind: 'backtest' | 'jobs') => {
    setBusy(kind);
    setError('');
    try {
      if (kind === 'backtest') {
        const response = await post<Backtest>(
          datasetId ? '/strategies/backtest/dataset' : '/strategies/backtest',
          datasetId ? { ...params, dataset_id: datasetId } : params,
        );
        setResult(response);
        toast('Backtest complete. Results saved to your workspace.');
      } else {
        const job = await post<Job>('/strategies/jobs', params);
        setSearch({ view: 'monitor', job: job.id });
        toast('Paper strategy started with isolated virtual capital.');
      }
      refresh();
    } catch (reason) {
      setError((reason as Error).message);
    } finally {
      setBusy('');
    }
  };
  const activeResult =
    result ??
    (history.data?.find((run) => !datasetId || (run.payload as Backtest).dataset?.id === datasetId)
      ?.payload as Backtest | undefined);
  const view = selectedView === 'monitor' ? 'monitor' : 'build';
  const tabs = (
    <SectionTabs
      id="strategies"
      label="Strategy workspace"
      items={[
        { id: 'build', label: 'Build & backtest', icon: FlaskConical },
        {
          id: 'monitor',
          label: 'Monitor',
          icon: Radio,
          detail: `${jobs.data?.filter((job) => job.status === 'running').length ?? 0} running`,
        },
      ]}
      value={view}
      onChange={(value) => setSearch(value === 'monitor' ? { view: 'monitor' } : {})}
    />
  );
  if (search.get('view') === 'monitor')
    return (
      <>
        <PageTitle
          title="Strategy monitor"
          description="Open a run. See its decisions, observed prices, and paper performance."
        />
        {tabs}
        <SectionPanel id="strategies" value={view}>
          {search.get('job') ? (
            <StrategyMonitor
              key={search.get('job')!}
              jobId={search.get('job')!}
              jobs={jobs.data ?? []}
              catalog={catalog.data ?? []}
            />
          ) : jobs.loading ? (
            <Loading />
          ) : jobs.error ? (
            <ErrorState message={jobs.error} retry={jobs.retry} />
          ) : (
            <StrategyList jobs={jobs.data ?? []} catalog={catalog.data ?? []} />
          )}
        </SectionPanel>
      </>
    );
  return (
    <>
      <PageTitle
        eyebrow="THOUGHTFUL BY DESIGN"
        title="Strategy studio"
        description="A little space to try your next idea."
        action={
          <AgentButton
            module="broker"
            context={
              datasetId
                ? { symbol: params.symbol, timeframe: params.timeframe }
                : { parameters: params }
            }
          />
        }
      />
      {tabs}
      <SectionPanel id="strategies" value={view}>
        {catalog.error && <ErrorState message={catalog.error} retry={catalog.retry} />}
        <div className="strategy-catalog">
          {catalog.data?.map((strategy, i) => (
            <button
              key={strategy.id}
              className={`panel strategy-card ${params.strategy === strategy.id ? 'strategy-selected' : ''}`}
              onClick={() => update('strategy', strategy.id)}
            >
              <div>
                <span className="strategy-number">0{i + 1}</span>
                <span className="strategy-glyph">{['⌁', '↗', '≋', '⋈', 'ϟ', '✳'][i]}</span>
              </div>
              <Badge tone={params.strategy === strategy.id ? 'lime' : 'neutral'}>
                {strategy.tag}
              </Badge>
              <h3>{strategy.name}</h3>
              <p>{strategy.description}</p>
              <span className="strategy-card-bottom">
                {strategy.risk} risk <ChevronRight size={15} />
              </span>
            </button>
          ))}
        </div>
        <div className="strategy-workspace">
          <Panel>
            <PanelTitle
              title="Make it your own"
              subtitle="Configurable closed candles · long only · spot simulation"
            />
            <form
              className="form strategy-form"
              onSubmit={(event) => {
                event.preventDefault();
                run('backtest');
              }}
            >
              <label>
                Research input
                <select value={datasetId} onChange={(event) => chooseDataset(event.target.value)}>
                  <option value="">Current feed · save exact input automatically</option>
                  {datasetId && !datasets.data?.items.some((d) => d.id === datasetId) && (
                    <option value={datasetId}>{dataset?.label || 'Loading saved dataset…'}</option>
                  )}
                  {datasets.data?.items.map((d) => (
                    <option key={d.id} value={d.id}>
                      {d.label} · {d.source_label} · {d.count.toLocaleString()} bars
                    </option>
                  ))}
                </select>
              </label>
              <p className="footnote">
                <Link to="/markets?view=history&historyTab=datasets">Browse all datasets</Link> ·
                Saved inputs work offline. Pair, timeframe and candle count are fixed; strategy
                parameters remain editable.
              </p>
              {dataset && datasetId && (
                <div className="history-input-caption">
                  <Badge tone={dataset.source === 'demo' ? 'sand' : 'neutral'}>
                    {dataset.source === 'demo' ? 'Synthetic demo' : dataset.environment}
                  </Badge>
                  <span>
                    {dataset.source_label} · {new Date(dataset.start).toLocaleDateString()} —{' '}
                    {new Date(dataset.end).toLocaleDateString()} (exclusive)
                  </span>
                </div>
              )}
              {selectedDataset.error && datasetId && (
                <ErrorState message={selectedDataset.error} retry={selectedDataset.retry} />
              )}
              {datasets.error && <ErrorState message={datasets.error} retry={datasets.retry} />}
              <label>
                Strategy
                <select
                  value={params.strategy}
                  onChange={(event) => update('strategy', event.target.value)}
                >
                  {catalog.data?.map((strategy) => (
                    <option key={strategy.id} value={strategy.id}>
                      {strategy.name}
                    </option>
                  ))}
                </select>
              </label>
              <div className="form-row">
                {datasetId ? (
                  <label>
                    Saved pair
                    <input value={params.symbol} readOnly />
                  </label>
                ) : (
                  <MarketSelector
                    value={params.symbol}
                    onChange={(value) => update('symbol', value)}
                  />
                )}
                <label>
                  Virtual capital · {params.symbol.split('/')[1]}
                  <input
                    type="number"
                    min="100"
                    max="10000000"
                    value={params.capital}
                    onChange={(event) => update('capital', Number(event.target.value))}
                  />
                </label>
              </div>
              <div className="form-row">
                <label>
                  Observations
                  <select
                    value={params.candles}
                    disabled={!!datasetId}
                    onChange={(event) => update('candles', Number(event.target.value))}
                  >
                    {datasetId && (
                      <option value={params.candles}>
                        {params.candles.toLocaleString()} saved candles
                      </option>
                    )}
                    <option value={90}>90 candles</option>
                    <option value={180}>180 candles</option>
                    <option value={365}>365 candles</option>
                    <option value={720}>720 candles</option>
                  </select>
                </label>
                <label>
                  Bollinger / CMF window
                  <input
                    type="number"
                    min="5"
                    max="120"
                    value={params.window}
                    onChange={(event) => update('window', Number(event.target.value))}
                  />
                </label>
              </div>
              {datasetId ? (
                <label>
                  Saved timeframe
                  <input value={params.timeframe} readOnly />
                </label>
              ) : (
                <TimeframeSelect
                  value={params.timeframe ?? '1d'}
                  onChange={(value) => update('timeframe', value)}
                />
              )}
              <details className="advanced-options" open>
                <summary>Indicator parameters</summary>
                <div className="form-row">
                  {(['fast_period', 'slow_period', 'rsi_period'] as const).map((key) => (
                    <label key={key}>
                      {
                        {
                          fast_period: 'Fast EMA',
                          slow_period: 'Slow EMA',
                          rsi_period: 'RSI period',
                        }[key]
                      }
                      <input
                        type="number"
                        min={key === 'slow_period' ? 3 : 2}
                        max={key === 'slow_period' ? 200 : 100}
                        value={params[key]}
                        onChange={(e) => update(key, Number(e.target.value))}
                      />
                    </label>
                  ))}
                </div>
                <div className="form-row">
                  {(['rsi_lower', 'rsi_upper', 'band_std', 'volume_multiplier'] as const).map(
                    (key) => (
                      <label key={key}>
                        {
                          {
                            rsi_lower: 'RSI buy threshold',
                            rsi_upper: 'RSI sell threshold',
                            band_std: 'Band deviations',
                            volume_multiplier: 'Volume multiplier',
                          }[key]
                        }
                        <input
                          type="number"
                          step="any"
                          min={key === 'rsi_lower' ? 1 : key === 'rsi_upper' ? 51 : 0.5}
                          max={
                            key === 'rsi_lower'
                              ? 49
                              : key === 'rsi_upper'
                                ? 99
                                : key === 'band_std'
                                  ? 5
                                  : 10
                          }
                          placeholder={
                            key === 'rsi_lower'
                              ? params.strategy === 'impulse-breakout'
                                ? '35'
                                : '30'
                              : key === 'rsi_upper'
                                ? params.strategy === 'impulse-breakout'
                                  ? '65'
                                  : '70'
                                : ''
                          }
                          value={params[key] ?? ''}
                          onChange={(e) =>
                            update(key, e.target.value === '' ? null : Number(e.target.value))
                          }
                        />
                      </label>
                    ),
                  )}
                </div>
                <p className="footnote">
                  Only parameters used by the chosen algorithm affect its signals. Leave RSI
                  thresholds blank for the algorithm defaults.
                </p>
              </details>
              <details className="advanced-options">
                <summary>MACD, ADX, ATR, CMF & TSI periods</summary>
                <div className="form-row">
                  {(
                    [
                      'macd_fast_period',
                      'macd_slow_period',
                      'macd_signal_period',
                      'adx_period',
                      'atr_period',
                      'cmf_period',
                      'tsi_short_period',
                      'tsi_long_period',
                    ] as const
                  ).map((key) => (
                    <label key={key}>
                      {
                        {
                          macd_fast_period: 'MACD fast',
                          macd_slow_period: 'MACD slow',
                          macd_signal_period: 'MACD signal',
                          adx_period: 'ADX period',
                          atr_period: 'ATR period',
                          cmf_period: 'CMF period',
                          tsi_short_period: 'TSI short',
                          tsi_long_period: 'TSI long',
                        }[key]
                      }
                      <input
                        type="number"
                        min={key === 'macd_slow_period' || key === 'tsi_long_period' ? 3 : 2}
                        max={
                          key === 'macd_slow_period' || key === 'tsi_long_period'
                            ? 200
                            : key === 'cmf_period'
                              ? 120
                              : 100
                        }
                        value={params[key] ?? ''}
                        placeholder={key === 'cmf_period' ? 'Use rolling window' : ''}
                        onChange={(e) =>
                          update(key, e.target.value === '' ? null : Number(e.target.value))
                        }
                      />
                    </label>
                  ))}
                </div>
                <p className="footnote">
                  These control the multi-factor strategies. Fast MACD and short TSI periods must be
                  smaller than their slow / long periods. The sample must exceed every configured
                  period.
                </p>
              </details>
              <details className="advanced-options">
                <summary>Risk exits & run limits</summary>
                <div className="form-row">
                  {(['stop_loss_pct', 'take_profit_pct', 'max_trades'] as const).map((key) => (
                    <label key={key}>
                      {
                        {
                          stop_loss_pct: 'Stop loss · %',
                          take_profit_pct: 'Take profit · %',
                          max_trades: 'Maximum round trips',
                        }[key]
                      }
                      <input
                        type="number"
                        step={key === 'max_trades' ? 1 : 'any'}
                        min={key === 'max_trades' ? 1 : 0.01}
                        max={
                          key === 'stop_loss_pct' ? 90 : key === 'take_profit_pct' ? 1000 : 10000
                        }
                        placeholder="No limit"
                        value={params[key] ?? ''}
                        onChange={(e) =>
                          update(key, e.target.value === '' ? null : Number(e.target.value))
                        }
                      />
                    </label>
                  ))}
                </div>
                <p className="footnote">
                  Risk thresholds are evaluated at the close. Backtests exit at the next open; paper
                  jobs use the next observed quote. These are not intrabar exchange stop orders.
                </p>
              </details>
              <details className="advanced-options">
                <summary>Execution assumptions</summary>
                <div className="form-row">
                  <label>
                    Fee · basis points
                    <input
                      type="number"
                      min="0"
                      max="200"
                      value={params.fee_bps}
                      onChange={(event) => update('fee_bps', Number(event.target.value))}
                    />
                  </label>
                  <label>
                    Slippage · basis points
                    <input
                      type="number"
                      min="0"
                      max="200"
                      value={params.slippage_bps}
                      onChange={(event) => update('slippage_bps', Number(event.target.value))}
                    />
                  </label>
                </div>
                <p className="footnote">
                  Applied to each fill. 10 basis points = 0.1%. Signals use closed candles.
                </p>
              </details>
              {error && (
                <p className="form-error" role="alert">
                  {error}
                </p>
              )}
              <button
                className="button primary full-width"
                type="submit"
                disabled={!!busy || (!!datasetId && !dataset)}
              >
                <FlaskConical size={15} />
                {busy === 'backtest' ? 'Testing your idea…' : 'Run backtest'}
              </button>
              <button
                className="button secondary full-width"
                type="button"
                disabled={!!busy || !!datasetId}
                onClick={() => run('jobs')}
              >
                <Play size={14} />
                {busy === 'jobs' ? 'Starting…' : 'Start paper strategy'}
              </button>
              <p className="footnote">
                {datasetId && 'Choose current-feed input to start a paper strategy. '}
                Each paper strategy has its own virtual account. Evaluated every 30 seconds; trades
                at most once per new closed candle.
              </p>
            </form>
          </Panel>
          <Panel className="backtest-panel">
            <PanelTitle
              title="The idea, in numbers"
              subtitle={
                activeResult
                  ? `${activeResult.symbol} · ${catalog.data?.find((s) => s.id === activeResult.strategy)?.name ?? activeResult.strategy}`
                  : 'Your next experiment starts here'
              }
              action={activeResult && <Badge tone="lime">Backtest</Badge>}
            />
            {activeResult ? (
              <>
                {activeResult.dataset && (
                  <div className="history-result-input">
                    <Badge tone={activeResult.dataset.source === 'demo' ? 'sand' : 'neutral'}>
                      {activeResult.dataset.source === 'demo'
                        ? 'Synthetic demo input'
                        : 'Saved input'}
                    </Badge>
                    <strong>
                      {activeResult.dataset.source_label} ·{' '}
                      {activeResult.dataset.count.toLocaleString()} bars
                    </strong>
                    <code title={activeResult.dataset.digest}>
                      {activeResult.dataset.digest.slice(0, 16)}…
                    </code>
                    <button
                      className="text-button"
                      onClick={() => chooseDataset(activeResult.dataset!.id)}
                    >
                      Reuse input
                    </button>
                    <button
                      className="text-button"
                      onClick={async () => {
                        try {
                          await downloadFile(
                            `/market-history/datasets/${activeResult.dataset!.id}`,
                            `sibyl-dataset-${activeResult.dataset!.id.slice(0, 12)}.json`,
                          );
                        } catch (e) {
                          setError((e as Error).message);
                        }
                      }}
                    >
                      Export input
                    </button>
                    <small>
                      Recorded engine {activeResult.engine_version || 'unknown'}. Same input and
                      settings can be rerun with the same engine.
                    </small>
                  </div>
                )}
                <div className="backtest-metrics">
                  <div>
                    <small>Total return</small>
                    <strong>
                      <Change value={activeResult.return_pct} />
                    </strong>
                  </div>
                  <div>
                    <small>Max drawdown</small>
                    <strong>{activeResult.max_drawdown.toFixed(2)}%</strong>
                  </div>
                  <div>
                    <small>Sharpe ratio</small>
                    <strong>{activeResult.sharpe.toFixed(2)}</strong>
                  </div>
                  <div>
                    <small>Round trips</small>
                    <strong>{activeResult.trades}</strong>
                  </div>
                </div>
                <ValueChart data={activeResult.curve} height={250} currency={false} />
                <div className="backtest-summary">
                  <span>
                    Final equity{' '}
                    <strong>
                      {number(
                        activeResult.final_equity,
                        ['BTC', 'ETH'].includes(activeResult.symbol.split('/')[1]) ? 8 : 2,
                      )}
                    </strong>
                  </span>
                  <span>
                    Buy & hold <strong>{activeResult.benchmark_pct.toFixed(2)}%</strong>
                  </span>
                  <span>
                    Fees{' '}
                    <strong>
                      {number(
                        activeResult.fees,
                        ['BTC', 'ETH'].includes(activeResult.symbol.split('/')[1]) ? 8 : 2,
                      )}
                    </strong>
                  </span>
                  <span>
                    Win rate <strong>{activeResult.win_rate.toFixed(1)}%</strong>
                  </span>
                </div>
                {activeResult.metrics && (
                  <>
                    <div className="extended-metrics">
                      {(
                        [
                          'sortino',
                          'calmar',
                          'profit_factor',
                          'average_win',
                          'average_loss',
                          'best_trade',
                          'worst_trade',
                        ] as const
                      ).map((key) => (
                        <div key={key}>
                          <small>{key.replaceAll('_', ' ')}</small>
                          <strong>
                            {activeResult.metrics![key] == null
                              ? '—'
                              : number(activeResult.metrics![key]!, 2)}
                            {key.includes('win') || key.includes('loss') || key.includes('trade')
                              ? '%'
                              : ''}
                          </strong>
                        </div>
                      ))}
                    </div>
                    <details className="fill-details">
                      <summary>Drawdown from peak · %</summary>
                      <ValueChart
                        currency={false}
                        height={160}
                        color="#c98290"
                        data={activeResult.curve.map((p, i) => ({
                          timestamp: p.timestamp,
                          value: activeResult.metrics!.drawdown_curve[i + 1] ?? 0,
                        }))}
                      />
                    </details>
                  </>
                )}
                <div className="chart-footnote">
                  <span>
                    {activeResult.timeframe ?? '1d'} · Values in {activeResult.symbol.split('/')[1]}
                  </span>
                  <button
                    className="text-button"
                    onClick={() =>
                      exportCSV('sibyl-backtest-fills.csv', [
                        ['Time', 'Side', 'Price', 'Quantity', 'Fee', 'Reason'],
                        ...activeResult.fills.map((f) => [
                          f.timestamp,
                          f.side,
                          f.price,
                          f.quantity,
                          f.fee ?? 0,
                          f.reason ?? 'Strategy signal',
                        ]),
                      ])
                    }
                  >
                    Export fills
                  </button>
                  <button
                    className="text-button"
                    onClick={() =>
                      exportCSV('sibyl-backtest-equity.csv', [
                        ['Time', 'Equity', 'Drawdown (%)'],
                        ...activeResult.curve.map((p, i) => [
                          p.timestamp,
                          p.value,
                          activeResult.metrics?.drawdown_curve[i + 1] ?? '',
                        ]),
                      ])
                    }
                  >
                    Export equity
                  </button>
                </div>
                <p className="footnote padded">
                  {activeResult.execution} Historical simulations do not estimate future returns.
                </p>
                <details className="fill-details">
                  <summary>Inspect {activeResult.fills.length} simulated fills</summary>
                  {activeResult.fills.length > 200 && (
                    <p className="footnote padded">
                      Showing the latest 200 fills. Export fills above for the complete history.
                    </p>
                  )}
                  <div className="table-scroll">
                    <table>
                      <thead>
                        <tr>
                          <th>Time</th>
                          <th>Side</th>
                          <th>Price</th>
                          <th>Quantity</th>
                        </tr>
                      </thead>
                      <tbody>
                        {activeResult.fills.slice(-200).map((fill, i) => (
                          <tr key={i}>
                            <td>{new Date(fill.timestamp).toLocaleDateString()}</td>
                            <td>{fill.side}</td>
                            <td>{number(fill.price, 8)}</td>
                            <td>{number(fill.quantity, 6)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </details>
                <div className="chart-footnote">
                  <DataNote source={activeResult.source} />
                  <select
                    aria-label="View saved backtest"
                    value={activeResult.id}
                    onChange={(event) =>
                      setResult(
                        history.data?.find((run) => run.id === event.target.value)
                          ?.payload as Backtest,
                      )
                    }
                  >
                    {history.data?.map((run) => (
                      <option value={run.id} key={run.id}>
                        {(run.payload as Backtest).strategy} ·{' '}
                        {new Date(run.created_at).toLocaleTimeString()}
                      </option>
                    ))}
                  </select>
                </div>
              </>
            ) : busy === 'backtest' ? (
              <Loading />
            ) : (
              <Empty title="Curiosity is a good strategy">
                Choose an algorithm, set your assumptions, and run a historical simulation.
              </Empty>
            )}
          </Panel>
        </div>
        {jobs.error ? (
          <ErrorState message={jobs.error} retry={jobs.retry} />
        ) : (
          <StrategyList jobs={jobs.data ?? []} catalog={catalog.data ?? []} />
        )}
        <ComingSoon module="strategies" />
      </SectionPanel>
    </>
  );
}

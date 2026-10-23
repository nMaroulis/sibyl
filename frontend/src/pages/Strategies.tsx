import { useEffect, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { FlaskConical, Play, Radio } from 'lucide-react';
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
import { AccountContext, AccountSetup, useAccounts } from '../components/account-selection';
import { MarketSelector, TimeframeSelect } from '../components/market-controls';
import type { SpotCatalog } from '../components/market-controls';
import { BacktestChart } from '../components/strategies/backtest-chart';
import { ExchangeStrategySetup } from '../components/strategies/exchange-execution';
import { ExecutionControls } from '../components/strategies/execution-controls';
import { ValidationWorkspace } from '../components/strategies/validation-workspace';
import { ComingSoon } from '../components/coming-soon';
import { ValueChart } from '../components/charts';
import { downloadFile, exportCSV, number, post, refresh } from '../lib/api';
import { useResource } from '../lib/hooks';
import type { Dataset, DatasetList } from '../lib/market-history';
import type { AccountSelection, Backtest, Job, Run, Strategy, StrategyParams } from '../lib/types';

/** Share the same explicit account/Demo boundary as Account and Trade. */
export function StrategiesPage() {
  const accounts = useAccounts();
  if (accounts.loading) return <Loading />;
  if (accounts.error || !accounts.data)
    return (
      <ErrorState
        message={accounts.error || 'Account selection unavailable.'}
        retry={accounts.retry}
      />
    );
  return <StrategyWorkspace key={accounts.data.signature} selection={accounts.data} />;
}

function StrategyWorkspace({ selection }: { selection: AccountSelection }) {
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
  const demoInput = selection.mode === 'demo';
  const demoCatalog = useResource<SpotCatalog>('/markets/symbols?source=demo', 0, demoInput);
  const [compareId, setCompareId] = useState('');
  const datasets = useResource<DatasetList>('/market-history/datasets');
  const selectedDataset = useResource<Dataset>(
    `/market-history/datasets/${datasetId}/metadata`,
    0,
    !!datasetId,
  );
  const dataset = selectedDataset.data;
  const datasetMatchesMode = !datasetId || (!!dataset && (dataset.source === 'demo') === demoInput);
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
    next.delete('input');
    id ? next.set('dataset', id) : next.delete('dataset');
    setSearch(next);
    setResult(undefined);
    setError('');
  };
  // Saved links cannot silently switch the active workspace into or out of Demo.
  useEffect(() => {
    if (search.has('input') || (dataset && !datasetMatchesMode)) {
      const next = new URLSearchParams(search);
      next.delete('input');
      if (dataset && !datasetMatchesMode) next.delete('dataset');
      setSearch(next, { replace: true });
    }
  }, [search, setSearch, dataset, datasetMatchesMode]);
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
          datasetId
            ? '/strategies/backtest/dataset'
            : demoInput
              ? '/strategies/backtest/demo'
              : '/strategies/backtest',
          datasetId ? { ...params, dataset_id: datasetId } : params,
        );
        setResult(response);
        toast('Backtest complete. Results saved to your workspace.');
      } else {
        const job = await post<Job>(
          demoInput ? '/strategies/jobs/demo' : '/strategies/jobs',
          params,
        );
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
  const savedRuns = (history.data ?? [])
    .map((run) => ({ ...(run.payload as Backtest), id: run.id }))
    .filter((run) => (run.source === 'demo') === demoInput);
  const savedDatasets = datasets.data?.items.filter((d) => (d.source === 'demo') === demoInput);
  const accountContext = (
    <AccountContext
      selection={selection}
      demoDescription={
        selectedView === 'monitor'
          ? 'The Demo account is active. Each saved run keeps its original data and execution mode.'
          : 'Prices are synthetic and strategies use virtual funds. Activating an exchange account turns Demo off automatically.'
      }
    />
  );
  const activeResult = result;
  const comparisons = activeResult?.dataset
    ? savedRuns.filter(
        (run) =>
          run.id !== activeResult.id &&
          run.dataset?.digest === activeResult.dataset?.digest &&
          run.initial_capital === activeResult.initial_capital,
      )
    : [];
  const comparison = comparisons.find((run) => run.id === compareId);
  const rerun = async () => {
    if (!activeResult) return;
    setBusy('rerun');
    setError('');
    try {
      setResult(await post<Backtest>(`/strategies/backtests/${activeResult.id}/rerun`, {}));
      refresh();
      toast('Recomputed from the original saved input and parameters.');
    } catch (reason) {
      setError((reason as Error).message);
    } finally {
      setBusy('');
    }
  };
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
          description="Open a run. See its decisions, orders, and recorded performance."
        />
        {accountContext}
        {tabs}
        <ExecutionControls />
        <SectionPanel id="strategies" value={view}>
          {!selection.active_ids.length && (
            <p className="inline-alert">
              No accounts are active. Saved strategy runs remain available.{' '}
              <Link to="/settings?tab=exchanges">Connect exchange accounts ↗</Link>
            </p>
          )}
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
  if (!selection.active_ids.length)
    return (
      <>
        <PageTitle
          title="Strategy studio"
          description="Build, test and understand your trading ideas."
        />
        {tabs}
        <ExecutionControls />
        <SectionPanel id="strategies" value={view}>
          <AccountSetup
            selection={selection}
            page="strategy workspace"
            description="Connect one or many exchange accounts to open your strategy workspace. Backtest with market data, monitor paper runs, and review supported exchange strategies before starting them."
          />
        </SectionPanel>
      </>
    );
  return (
    <>
      <PageTitle
        eyebrow="THOUGHTFUL BY DESIGN"
        title="Strategy studio"
        description="Build, test and understand your trading ideas."
        action={
          <AgentButton
            module="broker"
            context={
              activeResult
                ? {
                    symbol: activeResult.symbol,
                    timeframe: activeResult.timeframe,
                    backtest_id: activeResult.id,
                  }
                : datasetId
                  ? { symbol: params.symbol, timeframe: params.timeframe }
                  : { parameters: params }
            }
          />
        }
      />
      {accountContext}
      {tabs}
      <ExecutionControls />
      <SectionPanel id="strategies" value={view}>
        {catalog.error && <ErrorState message={catalog.error} retry={catalog.retry} />}
        <div className="strategy-studio-intro">
          <div>
            <Badge tone="blue">Historical research</Badge>
            <h2>Start with a clear idea.</h2>
            <p>
              Choose an algorithm and data, test it, then inspect every decision. Expand the
              settings when you need more control.
            </p>
          </div>
          {demoInput && <Badge tone="sand">Demo preview</Badge>}
        </div>
        <div className="strategy-workspace">
          <Panel>
            <PanelTitle
              title="Configure your strategy"
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
                  <option value="">
                    {demoInput ? 'Synthetic preview data' : 'Current market feed'} · exact input
                    saved
                  </option>
                  {datasetId && !savedDatasets?.some((d) => d.id === datasetId) && (
                    <option value={datasetId}>{dataset?.label || 'Loading saved dataset…'}</option>
                  )}
                  {savedDatasets?.map((d) => (
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
              <p className="footnote">
                {catalog.data?.find((strategy) => strategy.id === params.strategy)?.description}
              </p>
              <div className="form-row">
                {datasetId ? (
                  <label>
                    Saved pair
                    <input value={params.symbol} readOnly />
                  </label>
                ) : (
                  <MarketSelector
                    catalog={demoInput ? demoCatalog.data : undefined}
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
              </div>
              {datasetId ? (
                <label>
                  Saved timeframe
                  <input value={params.timeframe} readOnly />
                </label>
              ) : (
                <TimeframeSelect
                  catalog={demoInput ? demoCatalog.data : undefined}
                  value={params.timeframe ?? '1d'}
                  onChange={(value) => update('timeframe', value)}
                />
              )}
              <details className="advanced-options">
                <summary>Indicator parameters</summary>{' '}
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
                disabled={!!busy || !datasetMatchesMode}
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
                {datasetId && 'Choose the current feed to start a paper strategy. '}
                Each paper strategy has its own virtual account. Evaluated every 30 seconds; trades
                at most once per new closed candle.
              </p>
            </form>
            {!demoInput && (
              <ExchangeStrategySetup
                parameters={params}
                onStarted={(job) => setSearch({ view: 'monitor', job: job.id })}
              />
            )}
          </Panel>
          <Panel className="backtest-panel">
            <div className="backtest-history-selector">
              <label>
                Saved experiments
                <select
                  aria-label="Open saved experiment"
                  value={activeResult?.id ?? ''}
                  onChange={(e) => setResult(savedRuns.find((run) => run.id === e.target.value))}
                >
                  <option value="">New experiment</option>
                  {savedRuns.map((run) => (
                    <option key={run.id} value={run.id}>
                      {run.strategy} · {run.symbol} · {run.source === 'demo' ? 'Demo' : run.source}{' '}
                      · {run.id.slice(0, 8)}
                    </option>
                  ))}
                </select>
              </label>
            </div>
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
                      Recorded engine {activeResult.engine_version || 'unknown'} /{' '}
                      {activeResult.engine_revision || 'legacy'}. Reruns reuse the exact input and
                      settings with the current engine.
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
                <div className="backtest-run-controls">
                  <button
                    className="button secondary tiny"
                    disabled={!!busy || !activeResult.dataset}
                    onClick={rerun}
                  >
                    <Play size={13} />
                    {busy === 'rerun' ? 'Recomputing…' : 'Rerun exact input'}
                  </button>
                  <button
                    className="button ghost tiny"
                    onClick={() => {
                      setParams(activeResult.parameters);
                      chooseDataset(activeResult.dataset?.id ?? '');
                    }}
                  >
                    Load settings
                  </button>
                  <label>
                    Compare with
                    <select value={compareId} onChange={(e) => setCompareId(e.target.value)}>
                      <option value="">No comparison</option>
                      {comparisons.map((run) => (
                        <option key={run.id} value={run.id}>
                          {run.strategy} · {run.id.slice(0, 8)}
                        </option>
                      ))}
                    </select>
                  </label>
                </div>
                <BacktestChart
                  key={activeResult.id}
                  result={activeResult}
                  comparison={comparison}
                />
                {comparison && (
                  <div className="backtest-comparison">
                    <strong>Same input & initial capital</strong>
                    <span>
                      Return {number(activeResult.return_pct - comparison.return_pct, 2)} percentage
                      points
                    </span>
                    <span>
                      Drawdown {number(activeResult.max_drawdown - comparison.max_drawdown, 2)}{' '}
                      percentage points
                    </span>
                    <span>
                      Round trips {activeResult.trades} vs {comparison.trades}
                    </span>
                  </div>
                )}
                {activeResult.summary && (
                  <div className="extended-metrics">
                    {[
                      [
                        'Net profit',
                        `${number(activeResult.summary.net_profit, 2)} ${activeResult.symbol.split('/')[1]}`,
                      ],
                      ['Exposure', `${number(activeResult.summary.exposure_pct, 1)}%`],
                      [
                        'Profit factor · P&L',
                        activeResult.summary.profit_factor == null
                          ? '—'
                          : number(activeResult.summary.profit_factor, 2),
                      ],
                      [
                        'Expectancy / trade',
                        activeResult.summary.expectancy == null
                          ? '—'
                          : `${number(activeResult.summary.expectancy, 2)} ${activeResult.symbol.split('/')[1]}`,
                      ],
                      ['Evaluated candles', String(activeResult.summary.evaluated_bars)],
                      ['Warm-up candles', String(activeResult.summary.warmup_bars)],
                    ].map(([label, value]) => (
                      <div key={label}>
                        <small>{label}</small>
                        <strong>{value}</strong>
                      </div>
                    ))}
                  </div>
                )}
                {activeResult.round_trips && (
                  <details className="fill-details">
                    <summary>
                      Trade-by-trade performance · {activeResult.round_trips.length} round trips
                    </summary>
                    {activeResult.round_trips.length > 200 && (
                      <p className="footnote padded">
                        Showing the latest 200 round trips. Export the complete trade record below.
                      </p>
                    )}
                    <button
                      className="text-button padded"
                      onClick={() =>
                        exportCSV('sibyl-backtest-round-trips.csv', [
                          [
                            'Entry',
                            'Exit',
                            'Quantity',
                            'Entry price',
                            'Exit price',
                            'Net P&L',
                            'Return (%)',
                            'Holding seconds',
                            'Exit reason',
                          ],
                          ...activeResult.round_trips!.map((t) => [
                            t.entry_time,
                            t.exit_time,
                            t.quantity,
                            t.entry_price,
                            t.exit_price,
                            t.pnl,
                            t.return_pct,
                            t.holding_seconds,
                            t.reason,
                          ]),
                        ])
                      }
                    >
                      Export all round trips
                    </button>
                    <div className="table-scroll">
                      <table>
                        <thead>
                          <tr>
                            <th>Entry → Exit</th>
                            <th>Entry / exit price</th>
                            <th>Net P&L</th>
                            <th>Return</th>
                            <th>Exit reason</th>
                          </tr>
                        </thead>
                        <tbody>
                          {activeResult.round_trips.slice(-200).map((t) => (
                            <tr key={t.id}>
                              <td>
                                {new Date(t.entry_time).toLocaleString()}
                                <br />
                                {new Date(t.exit_time).toLocaleString()}
                              </td>
                              <td>
                                {number(t.entry_price, 4)} / {number(t.exit_price, 4)}
                              </td>
                              <td className={t.pnl >= 0 ? 'positive' : 'negative'}>
                                {number(t.pnl, 4)}
                              </td>
                              <td>
                                <Change value={t.return_pct} />
                              </td>
                              <td>{t.reason}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </details>
                )}
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
                    <details className="advanced-options result-advanced">
                      <summary>More risk & trade metrics</summary>
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
                    </details>
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
                      setResult(savedRuns.find((run) => run.id === event.target.value))
                    }
                  >
                    {savedRuns.map((run) => (
                      <option value={run.id} key={run.id}>
                        {run.strategy} · {run.symbol} · {run.id.slice(0, 8)}
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
        <ValidationWorkspace
          dataset={activeResult?.dataset ?? dataset}
          parameters={activeResult?.parameters ?? params}
          demo={demoInput}
        />
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

import '../styles/strategy-setup.css';
import { PortfolioResearch } from '../components/strategies/portfolio-research';
import { CustomStrategies } from '../components/strategies/custom-strategies';
import { BenchmarkComparison } from '../components/strategies/benchmark-comparison';
import { useEffect, useRef, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { FlaskConical, Layers3, Play, Radio, ScrollText } from 'lucide-react';
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
import type { SpotCatalog } from '../components/market-controls';
import { BacktestChart } from '../components/strategies/backtest-chart';
import { BacktestLimitEvidence } from '../components/strategies/backtest-limit-evidence';
import {
  BacktestPerformance,
  BacktestReportAsk,
  InlineBacktestReport,
} from '../components/strategies/backtest-results';
import {
  StrategyRunPicker,
  type StrategyRunMode,
} from '../components/strategies/strategy-run-picker';
import { StrategyPicker } from '../components/strategies/strategy-picker';
import { StrategyField } from '../components/strategies/strategy-field';
import {
  StrategySignalSettings,
  type ParameterHelp,
} from '../components/strategies/strategy-signal-settings';
import {
  StrategyAccountPicker,
  type StrategyExecutionOptions,
} from '../components/strategies/strategy-account-picker';
import { ExchangeStrategySetup } from '../components/strategies/exchange-execution';
import {
  maximumStrategyAmount,
  StrategyMarketSettings,
} from '../components/strategies/strategy-market-settings';
import {
  backtestDatesStatus,
  maximumLookback,
  type BacktestDateRange,
} from '../components/strategies/strategy-backtest-dates';
import {
  hasCustomRiskSettings,
  hasInvalidRiskSettings,
  StrategyRiskSettings,
} from '../components/strategies/strategy-risk-settings';
import { ExecutionControls } from '../components/strategies/execution-controls';
import { ValidationWorkspace } from '../components/strategies/validation-workspace';
import { ComingSoon } from '../components/coming-soon';
import { downloadFile, exportCSV, number, post, refresh } from '../lib/api';
import { useResource } from '../lib/hooks';
import type { Dataset } from '../lib/market-history';
import type {
  AccountSelection,
  Backtest,
  Job,
  Run,
  Strategy,
  StrategyOrderLimits,
  StrategyParams,
} from '../lib/types';

const defaultOrderLimits = { max_order_quote: 500, max_loss_pct: 10 };

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
  const selectedBacktest = search.get('backtest') ?? '';
  useEffect(() => {
    window.scrollTo({ top: 0, behavior: 'instant' });
  }, [selectedView, selectedJob]);
  const handoff = search.get('handoff');
  const view =
    selectedView === 'monitor'
      ? 'monitor'
      : selectedView === 'portfolio'
        ? 'portfolio'
        : selectedView === 'experiments'
          ? 'experiments'
          : 'build';
  const [accountChoice, setAccountChoice] = useState('');
  const [backtestDates, setBacktestDates] = useState<BacktestDateRange>();
  const [useRiskOverrides, setUseRiskOverrides] = useState(false);
  const [orderLimits, setOrderLimits] = useState<StrategyOrderLimits>(defaultOrderLimits);
  const [action, setAction] = useState<StrategyRunMode>(handoff ? 'deploy' : 'backtest');
  const catalog = useResource<Strategy[]>('/strategies');
  const jobs = useResource<Job[]>('/strategies/jobs', 30000);
  const history = useResource<Run[]>('/runs?kind=backtest');
  const [configuredParams, setParams] = useState<StrategyParams>({
    strategy: 'ema',
    symbol: 'BTC/USDT',
    capital: 1000,
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
  const draftParams = {
    ...configuredParams,
    candles: Math.min(configuredParams.candles, maximumLookback),
    ...(!useRiskOverrides && { stop_loss_pct: null, take_profit_pct: null, max_trades: null }),
  };
  const amount = draftParams.capital;
  const validOrderLimits =
    orderLimits.max_order_quote > 0 &&
    orderLimits.max_order_quote <= amount &&
    orderLimits.max_loss_pct > 0 &&
    orderLimits.max_loss_pct <= 90;
  const datasetId = search.get('dataset') || '';
  const canChooseDates = action === 'backtest' && !datasetId;
  const dateRange = canChooseDates ? backtestDates : undefined;
  const invalidDates =
    dateRange && !!backtestDatesStatus(dateRange, draftParams.timeframe ?? '1d').error;
  const demoInput = selection.mode === 'demo';
  const execution = useResource<StrategyExecutionOptions>(
    '/strategies/exchange/options',
    0,
    view === 'build' && !demoInput && selection.active_ids.length > 0,
  );
  const parameterHelp = useResource<ParameterHelp>('/strategies/parameters', 0, view === 'build');
  const help = parameterHelp.data ?? {};
  const invalidRisk = hasInvalidRiskSettings(draftParams);
  const accounts = (execution.data?.accounts ?? []).filter((row) => row.active);
  const account = accounts.find((row) => row.id === accountChoice);
  useEffect(() => {
    if (!handoff || demoInput || view !== 'build') return;
    const prior = execution.data?.handoff_sources.find((item) => item.id === handoff);
    if (
      !prior ||
      !execution.data?.accounts.some((row) => row.id === prior.connection_id && row.active)
    )
      return;
    setAccountChoice(prior.connection_id);
    setParams((current) => ({ ...current, symbol: prior.symbol }));
    setAction('deploy');
  }, [handoff, execution.data, demoInput, view]);
  const scopeChosen = demoInput || !!account || accountChoice === 'workspace-feed';
  const source = demoInput ? 'demo' : account ? 'connection:' + account.id : undefined;
  const marketSuffix = source ? '?source=' + encodeURIComponent(source) : '';
  const market = useResource<SpotCatalog>(
    '/markets/symbols' + marketSuffix,
    0,
    view === 'build' && scopeChosen,
  );
  const marketCatalog = !source || market.data?.source === source ? market.data : undefined;
  const pairSelected = !!marketCatalog?.items.some((row) => row.symbol === draftParams.symbol);
  const frameSelected = !!marketCatalog?.timeframes.includes(draftParams.timeframe ?? '1d');
  const exactMarket = pairSelected && frameSelected && !market.loading && !market.error;
  const selectedAlgorithm = catalog.data?.find((item) => item.id === draftParams.strategy);
  const [compareId, setCompareId] = useState('');
  const selectedDataset = useResource<Dataset>(
    `/market-history/datasets/${datasetId}/metadata`,
    0,
    !!datasetId,
  );
  const dataset = selectedDataset.data?.id === datasetId ? selectedDataset.data : undefined;
  const datasetMatchesMode = !datasetId || (!!dataset && (dataset.source === 'demo') === demoInput);
  const backtestDataset = action === 'backtest' && datasetMatchesMode ? dataset : undefined;
  const params: StrategyParams = backtestDataset
    ? {
        ...draftParams,
        symbol: backtestDataset.symbol,
        timeframe: backtestDataset.timeframe,
        candles: backtestDataset.count,
      }
    : draftParams;
  const quote = params.symbol.split('/')[1];
  const balancePath = '/connections/' + encodeURIComponent(account?.id ?? '') + '/balances';
  const balances = useResource<{ items: { asset: string; free: number | null }[] }>(
    balancePath,
    30000,
    view === 'build' && !!account,
  );
  const observedBalances =
    balances.dataPath === balancePath && !balances.error ? balances.data?.items : undefined;
  const quoteBalance = observedBalances?.find((item) => item.asset === quote);
  const free = quoteBalance ? quoteBalance.free : observedBalances ? 0 : null;
  const available = free !== null && Number.isFinite(free) && free >= 0 ? free : undefined;
  const exceedsBalance = available !== undefined && amount > available;
  const amountError =
    !Number.isFinite(amount) || amount > maximumStrategyAmount
      ? 'Enter an amount of up to 10,000,000.'
      : action === 'deploy' && amount <= 0
        ? 'Enter a positive amount for deployment.'
        : action !== 'deploy' && amount < 100
          ? 'Enter at least 100 in the quote currency for a simulation.'
          : '';
  const backtestParams: StrategyParams = { ...params, backtest_limits: orderLimits };
  const chooseDataset = (id: string, openBuilder = false) => {
    const next = new URLSearchParams(search);
    next.delete('input');
    if (openBuilder) {
      next.delete('view');
      next.delete('handoff');
      setAction('backtest');
      if (!demoInput && !accountChoice) setAccountChoice('workspace-feed');
    }
    id ? next.set('dataset', id) : next.delete('dataset');
    setBacktestDates(undefined);
    setSearch(next);
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
  const reportRef = useRef<HTMLElement>(null);
  const revealedReport = useRef('');
  useEffect(() => {
    const report = reportRef.current;
    if (
      view !== 'build' ||
      action !== 'backtest' ||
      !result ||
      !report ||
      revealedReport.current === result.id
    )
      return;
    revealedReport.current = result.id;
    report.focus({ preventScroll: true });
    report.scrollIntoView({
      block: 'start',
      behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches
        ? 'instant'
        : 'smooth',
    });
  }, [view, action, result]);
  const [busy, setBusy] = useState('');
  const [error, setError] = useState('');
  const toast = useToast();
  const update = (key: keyof StrategyParams, value: number | string | null) => {
    setParams((old) => ({ ...old, [key]: value }));
    if (key === 'symbol' && handoff) {
      const next = new URLSearchParams(search);
      next.delete('handoff');
      setSearch(next);
    }
    setError('');
  };
  const run = async (kind: 'backtest' | 'jobs') => {
    if (invalidRisk || amountError || invalidDates || !validOrderLimits) return;
    setBusy(kind);
    setError('');
    try {
      if (kind === 'backtest') {
        const response = await post<Backtest>(
          dateRange
            ? '/strategies/backtest/range' + marketSuffix
            : datasetId
              ? '/strategies/backtest/dataset'
              : demoInput
                ? '/strategies/backtest/demo'
                : '/strategies/backtest' + marketSuffix,
          dateRange
            ? {
                ...backtestParams,
                candles: maximumLookback,
                start: new Date(dateRange.start + 'Z').toISOString(),
                end: new Date(dateRange.end + 'Z').toISOString(),
              }
            : datasetId
              ? { ...backtestParams, dataset_id: datasetId }
              : backtestParams,
        );
        setResult(response);
        setCompareId('');
        toast('Backtest saved · ' + response.id.slice(0, 8));
      } else {
        const job = await post<Job>(
          demoInput ? '/strategies/jobs/demo' : '/strategies/jobs' + marketSuffix,
          { ...draftParams, order_limits: orderLimits },
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
  const savedRuns = (history.data ?? []).map((run) => ({
    ...(run.payload as Backtest),
    id: run.id,
  }));
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
  const localExperiment =
    result?.id === selectedBacktest ? result : savedRuns.find((run) => run.id === selectedBacktest);
  const savedExperiment = useResource<Backtest>(
    '/strategies/backtests/' + encodeURIComponent(selectedBacktest),
    0,
    view === 'experiments' && !!selectedBacktest && !localExperiment,
  );
  const activeResult =
    localExperiment ??
    (savedExperiment.data?.id === selectedBacktest ? savedExperiment.data : undefined);

  const experimentLocation = (id: string) => {
    const next = new URLSearchParams(search);
    next.set('view', 'experiments');
    next.set('backtest', id);
    next.delete('handoff');
    next.delete('job');
    return next;
  };
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
      const replay = await post<Backtest>(`/strategies/backtests/${activeResult.id}/rerun`, {});
      setResult(replay);
      setCompareId('');
      setSearch(experimentLocation(replay.id));
      refresh();
      toast('Recomputed from the original saved input and parameters.');
    } catch (reason) {
      setError((reason as Error).message);
    } finally {
      setBusy('');
    }
  };
  const tabs = (
    <SectionTabs
      id="strategies"
      label="Strategy workspace"
      items={[
        { id: 'build', label: 'Build strategy', icon: FlaskConical },
        { id: 'experiments', label: 'Experiments', icon: ScrollText },
        { id: 'portfolio', label: 'Portfolio lab', icon: Layers3 },
        {
          id: 'monitor',
          label: 'Monitor',
          icon: Radio,
          detail: `${jobs.data?.filter((job) => job.status === 'running').length ?? 0} running`,
        },
      ]}
      value={view}
      onChange={(value) => {
        const next = new URLSearchParams(search);
        next.delete('job');
        next.delete('handoff');
        if (value === 'build') next.delete('view');
        else next.set('view', value);
        if (value === 'experiments' && !selectedBacktest && result) next.set('backtest', result.id);
        setError('');
        setSearch(next);
      }}
    />
  );
  if (selectedView === 'portfolio')
    return (
      <>
        <PageTitle
          title="Portfolio lab"
          description="Research target allocations and rebalancing across assets."
        />
        {accountContext}
        {tabs}
        <SectionPanel id="strategies" value={view}>
          {!selection.active_ids.length && (
            <AccountSetup
              selection={selection}
              page="portfolio research"
              description="Connect one or many accounts, or use the small Demo preview option to explore synthetic portfolio research. Saved studies remain readable."
            />
          )}
          <PortfolioResearch demo={demoInput} canRun={selection.active_ids.length > 0} />
        </SectionPanel>
      </>
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
  if (view === 'build' && !selection.active_ids.length)
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
        title={view === 'experiments' ? 'Strategy experiments' : 'Strategy studio'}
        description={
          view === 'experiments'
            ? 'Review saved backtests, compare results, and validate on unseen data.'
            : 'Choose an account, configure a strategy and market, then decide how to run it.'
        }
        action={
          <AgentButton
            module="broker"
            context={
              view === 'experiments' && activeResult
                ? {
                    symbol: activeResult.symbol,
                    timeframe: activeResult.timeframe,
                    backtest_id: activeResult.id,
                  }
                : { parameters: action === 'backtest' ? backtestParams : params }
            }
          />
        }
      />
      {accountContext}
      {tabs}
      {view === 'build' && <ExecutionControls />}
      <SectionPanel id="strategies" value={view}>
        {catalog.error && <ErrorState message={catalog.error} retry={catalog.retry} />}
        {view === 'build' && (
          <div className="strategy-builder">
            <Panel>
              <PanelTitle title="1. Choose an account" />
              <div className="form strategy-builder-fields">
                {execution.error && (
                  <ErrorState message={execution.error} retry={execution.retry} />
                )}
                <StrategyAccountPicker
                  accounts={accounts}
                  demo={demoInput}
                  loading={execution.loading}
                  value={accountChoice}
                  onChange={(id) => {
                    if (id === accountChoice) return;
                    setAccountChoice(id);
                    if (handoff) {
                      const next = new URLSearchParams(search);
                      next.delete('handoff');
                      setSearch(next);
                    }
                    setError('');
                  }}
                />
                {account && (
                  <p className="footnote">
                    {account.provider_name} supplies the default market data for this setup.
                  </p>
                )}
              </div>
            </Panel>
            {scopeChosen && (
              <>
                <Panel>
                  <PanelTitle title="2. Configure the strategy" />
                  <div className="form strategy-builder-fields">
                    <StrategyPicker
                      strategies={catalog.data ?? []}
                      value={draftParams.strategy}
                      onChange={(value) => update('strategy', value)}
                    />
                    {parameterHelp.error && (
                      <ErrorState message={parameterHelp.error} retry={parameterHelp.retry} />
                    )}
                    <StrategySignalSettings
                      params={draftParams}
                      update={update}
                      algorithm={selectedAlgorithm}
                      help={help}
                    />
                  </div>
                </Panel>
                <Panel>
                  <PanelTitle title="3. Set market and amount" />
                  <div className="form strategy-builder-fields">
                    {!backtestDataset && market.error && (
                      <ErrorState message={market.error} retry={market.retry} />
                    )}
                    {!backtestDataset && market.loading && (
                      <p className="footnote">Loading spot pairs and intervals…</p>
                    )}
                    {action === 'backtest' && datasetId && !dataset && (
                      <div>
                        {selectedDataset.error ? (
                          <ErrorState
                            message={selectedDataset.error}
                            retry={selectedDataset.retry}
                          />
                        ) : (
                          <p className="footnote" role="status">
                            Loading saved dataset…
                          </p>
                        )}
                        <button
                          type="button"
                          className="text-button"
                          onClick={() => chooseDataset('')}
                        >
                          Use latest candles
                        </button>
                      </div>
                    )}
                    <StrategyMarketSettings
                      catalog={marketCatalog}
                      dataset={backtestDataset}
                      onUseLatest={() => chooseDataset('')}
                      dates={dateRange}
                      onDatesChange={
                        canChooseDates
                          ? (dates) => {
                              setBacktestDates(dates);
                              setError('');
                            }
                          : undefined
                      }
                      params={draftParams}
                      update={update}
                      deploy={action === 'deploy'}
                      help={help}
                      amountError={amountError}
                      funding={
                        account
                          ? { available, loading: balances.loading, exceedsBalance }
                          : undefined
                      }
                    />
                    <StrategyRiskSettings
                      params={configuredParams}
                      quote={quote}
                      limits={orderLimits}
                      onLimitsChange={setOrderLimits}
                      enabled={useRiskOverrides}
                      onToggle={(enabled) => {
                        setUseRiskOverrides(enabled);
                        setError('');
                      }}
                      onValue={update}
                      help={help}
                    />
                    {invalidRisk && (
                      <p className="form-error" role="status">
                        Correct the out-of-range value under Custom exits.
                      </p>
                    )}
                  </div>
                </Panel>
                <Panel>
                  <PanelTitle title="4. Choose how to run" />
                  <StrategyRunPicker
                    value={action}
                    account={account}
                    onChange={(mode) => {
                      setAction(mode);
                      setError('');
                    }}
                  />
                  {action !== 'deploy' && (
                    <form
                      className="form strategy-builder-fields"
                      onSubmit={(event) => {
                        event.preventDefault();
                        void run(action === 'paper' ? 'jobs' : 'backtest');
                      }}
                    >
                      {action === 'backtest' && account?.sandbox && !datasetId && (
                        <p className="monitor-notice">
                          Test accounts can have shorter price histories. If you need more candles,
                          choose a shorter timeframe in step 3 or use a production feed in step 1.
                          Backtests use simulated funds.
                        </p>
                      )}
                      <fieldset className="strategy-simulation-settings">
                        <legend>Simulation settings</legend>
                        <div className="strategy-market-grid">
                          {(
                            [
                              ['fee_bps', 'Fee · basis points'],
                              ['slippage_bps', 'Slippage · basis points'],
                            ] as const
                          ).map(([key, label]) => (
                            <StrategyField key={key} label={label} caption={help[key]}>
                              <input
                                type="number"
                                min="0"
                                max="200"
                                step="any"
                                value={draftParams[key]}
                                onChange={(event) => update(key, Number(event.target.value))}
                              />
                            </StrategyField>
                          ))}
                          {action === 'backtest' && (
                            <StrategyField
                              label="Reference portfolio cadence · candles"
                              caption={help.benchmark_interval}
                            >
                              <input
                                type="number"
                                min={1}
                                max={365}
                                value={draftParams.benchmark_interval ?? 20}
                                onChange={(event) =>
                                  update('benchmark_interval', Number(event.target.value))
                                }
                              />
                            </StrategyField>
                          )}
                        </div>
                      </fieldset>
                      {error && (
                        <p className="form-error" role="alert">
                          {error}
                        </p>
                      )}
                      <button
                        className="button primary exchange-run-review"
                        type="submit"
                        disabled={
                          !!busy ||
                          invalidRisk ||
                          !!amountError ||
                          invalidDates ||
                          !validOrderLimits ||
                          (action === 'backtest' && datasetId ? !datasetMatchesMode : !exactMarket)
                        }
                      >
                        {action === 'backtest' ? <FlaskConical size={15} /> : <Play size={15} />}
                        {busy
                          ? action === 'backtest'
                            ? dateRange
                              ? 'Preparing dates and running backtest…'
                              : 'Running backtest…'
                            : 'Starting paper strategy…'
                          : action === 'backtest'
                            ? 'Run backtest'
                            : 'Start paper strategy'}
                      </button>
                    </form>
                  )}
                  {action === 'deploy' && (!account?.supported || !execution.data) && (
                    <div className="form strategy-builder-fields">
                      <p className="monitor-notice">
                        Choose an active account that supports exchange strategies in step 1 to
                        deploy. <Link to="/settings?tab=exchanges">Manage exchanges</Link>
                      </p>
                    </div>
                  )}
                  {account?.supported && execution.data && (
                    <div hidden={action !== 'deploy'}>
                      <ExchangeStrategySetup
                        key={account.id}
                        account={account}
                        parameters={draftParams}
                        limits={orderLimits}
                        options={execution.data}
                        canDeploy={
                          exactMarket &&
                          !invalidRisk &&
                          !amountError &&
                          !exceedsBalance &&
                          validOrderLimits
                        }
                        preferredHandoff={handoff ?? undefined}
                        help={help}
                        onStarted={(job) => setSearch({ view: 'monitor', job: job.id })}
                      />
                    </div>
                  )}
                </Panel>
                {action === 'backtest' && result && (
                  <section
                    ref={reportRef}
                    tabIndex={-1}
                    aria-labelledby="inline-backtest-title"
                    className="panel backtest-panel builder-backtest-report"
                  >
                    <InlineBacktestReport
                      result={result}
                      algorithm={
                        catalog.data?.find((item) => item.id === result.strategy)?.name ??
                        result.strategy
                      }
                      experimentLink={'?' + experimentLocation(result.id)}
                    />
                  </section>
                )}
              </>
            )}
          </div>
        )}
        {view === 'experiments' && (
          <>
            {history.error && <ErrorState message={history.error} retry={history.retry} />}
            {savedExperiment.error && !localExperiment && (
              <ErrorState message={savedExperiment.error} retry={savedExperiment.retry} />
            )}
            {error && (
              <p className="form-error padded" role="alert">
                {error}
              </p>
            )}
            <Panel className="backtest-panel">
              <div className="backtest-history-selector">
                <label>
                  Saved experiments
                  <select
                    aria-label="Open saved experiment"
                    value={selectedBacktest}
                    onChange={(e) => {
                      const next = new URLSearchParams(search);
                      const id = e.currentTarget.value;
                      if (id) next.set('backtest', id);
                      else next.delete('backtest');
                      setCompareId('');
                      setError('');
                      setSearch(next);
                    }}
                  >
                    <option value="">Choose a saved experiment</option>
                    {selectedBacktest && !savedRuns.some((run) => run.id === selectedBacktest) && (
                      <option value={selectedBacktest}>
                        {activeResult ? `${activeResult.strategy} · ${activeResult.symbol} · ` : ''}
                        {selectedBacktest.slice(0, 8)}
                      </option>
                    )}
                    {savedRuns.map((run) => (
                      <option key={run.id} value={run.id}>
                        {run.strategy} · {run.symbol} ·{' '}
                        {run.source === 'demo' ? 'Demo' : run.source} · {run.id.slice(0, 8)}
                      </option>
                    ))}
                  </select>
                </label>
                <Link className="text-button" to="/markets?view=history&historyTab=datasets">
                  Browse saved datasets
                </Link>
              </div>
              <PanelTitle
                title={activeResult ? 'Backtest results' : 'Saved backtests'}
                subtitle={
                  activeResult
                    ? `${activeResult.symbol} · ${catalog.data?.find((s) => s.id === activeResult.strategy)?.name ?? activeResult.strategy}`
                    : 'Your next experiment starts here'
                }
                action={activeResult && <BacktestReportAsk result={activeResult} />}
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
                        disabled={
                          (activeResult.dataset.source === 'demo') !== demoInput ||
                          !selection.active_ids.length
                        }
                        onClick={() => chooseDataset(activeResult.dataset!.id, true)}
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
                  <BacktestPerformance result={activeResult} />
                  <BacktestLimitEvidence result={activeResult} />
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
                      disabled={!selection.active_ids.length}
                      onClick={() => {
                        setUseRiskOverrides(hasCustomRiskSettings(activeResult.parameters));
                        const { backtest_limits: limits, ...settings } = activeResult.parameters;
                        setParams(settings);
                        setOrderLimits(
                          limits ?? {
                            ...defaultOrderLimits,
                            max_order_quote: Math.min(
                              defaultOrderLimits.max_order_quote,
                              settings.capital,
                            ),
                          },
                        );
                        const savedInput = activeResult.dataset;
                        const matches = savedInput && (savedInput.source === 'demo') === demoInput;
                        chooseDataset(matches ? savedInput.id : '', true);
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
                  <BenchmarkComparison result={activeResult} />
                  {comparison && (
                    <div className="backtest-comparison">
                      <strong>Same input & initial capital</strong>
                      <span>
                        Return {number(activeResult.return_pct - comparison.return_pct, 2)}{' '}
                        percentage points
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
                  {activeResult.round_trips && (
                    <details className="fill-details">
                      <summary>
                        Trade-by-trade performance · {activeResult.round_trips.length} round trips
                      </summary>
                      {activeResult.round_trips.length > 200 && (
                        <p className="footnote padded">
                          Showing the latest 200 round trips. Export the complete trade record
                          below.
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
                  <div className="chart-footnote">
                    <span>
                      {activeResult.timeframe ?? '1d'} · Values in{' '}
                      {activeResult.symbol.split('/')[1]}
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
                  </div>
                </>
              ) : history.loading || (selectedBacktest && savedExperiment.loading) ? (
                <Loading />
              ) : (
                <Empty title="Choose an experiment to inspect">
                  Run a backtest in Build strategy to save its results here.
                </Empty>
              )}
            </Panel>
            <ValidationWorkspace
              dataset={activeResult?.dataset ?? dataset}
              parameters={activeResult?.parameters ?? params}
              demo={activeResult ? activeResult.source === 'demo' : demoInput}
            />
            {selection.active_ids.length > 0 && (
              <CustomStrategies params={params} datasetId={datasetId} demo={demoInput} />
            )}
          </>
        )}
        <ComingSoon module="strategies" />
      </SectionPanel>
    </>
  );
}

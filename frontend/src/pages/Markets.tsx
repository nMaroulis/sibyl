import { useState, type ReactNode } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { ArrowUpRight, Download, CandlestickChart, Network, SlidersHorizontal } from 'lucide-react';
import {
  AssetIcon,
  Badge,
  Change,
  DataNote,
  ErrorState,
  Loading,
  PageTitle,
  Panel,
  PanelTitle,
} from '../components/ui';
import { SectionTabs, SectionPanel } from '../components/section-tabs';
import { AgentButton } from '../components/agents';
import { IndicatorChart, Sparkline } from '../components/charts';
import { Candlesticks } from '../components/candlesticks';
import { MarketSelector, TimeframeSelect, type SpotCatalog } from '../components/market-controls';
import { MarketSourceMark } from '../components/config-helper';
import { ComingSoon } from '../components/coming-soon';
import { exportCSV, number } from '../lib/api';
import { useResource } from '../lib/hooks';
import type {
  Analysis,
  MarketAsset,
  MarketSettings,
  MarketSource,
  Source,
  Timeframe,
} from '../lib/types';

type Correlation = Source & { symbols: string[]; matrix: number[][]; observations: number };
export function Markets() {
  const [params, setParams] = useSearchParams();
  const settings = useResource<MarketSettings>('/settings/market');
  if (settings.error) return <ErrorState message={settings.error} retry={settings.retry} />;
  if (!settings.data) return <Loading />;
  const sourceId = params.get('source') || settings.data.active.id;
  const selected = settings.data.catalog.find((s) => s.id === sourceId) ?? settings.data.active;
  const feedControl = (
    <div className="market-feed-bar">
      <MarketSourceMark source={selected} />
      <label>
        Market feed
        <select
          aria-label="Market feed"
          value={params.get('source') || ''}
          onChange={(e) => {
            const next = new URLSearchParams(params);
            e.target.value ? next.set('source', e.target.value) : next.delete('source');
            next.delete('symbol');
            next.delete('asset');
            setParams(next);
          }}
        >
          <option value="">Workspace default · {settings.data.active.name}</option>
          {(['demo', 'connection', 'exchange', 'api'] as const).map((kind) => (
            <optgroup
              key={kind}
              label={
                {
                  demo: 'Offline',
                  connection: 'Connected accounts',
                  exchange: 'Public exchanges · no key',
                  api: 'Market APIs',
                }[kind]
              }
            >
              {settings
                .data!.catalog.filter((s) => s.kind === kind)
                .map((s) => (
                  <option key={s.id} value={s.id} disabled={!s.available}>
                    {s.name}
                    {s.environment === 'test' ? ' · Test environment' : ''}
                    {!s.available ? ' · Set up API key' : ''}
                  </option>
                ))}
            </optgroup>
          ))}
        </select>
      </label>
      <Badge
        tone={
          selected.kind === 'demo' ? 'purple' : selected.environment === 'test' ? 'sand' : 'blue'
        }
      >
        {selected.kind === 'demo'
          ? 'Offline demo'
          : selected.environment === 'test'
            ? 'Test feed'
            : selected.candles
              ? 'Quotes & candles'
              : 'Quotes only'}
      </Badge>
      <Link className="text-link" to="/settings?tab=market">
        <SlidersHorizontal size={14} /> Source settings
      </Link>
    </div>
  );
  return (
    <MarketsView key={sourceId} sourceId={sourceId} source={selected} feedControl={feedControl} />
  );
}

/** A source change remounts this workspace, clearing all previous feed selections. */
function MarketsView({
  sourceId,
  source,
  feedControl,
}: {
  sourceId: string;
  source: MarketSource;
  feedControl: ReactNode;
}) {
  const [params, setParams] = useSearchParams();
  const suffix = `source=${encodeURIComponent(sourceId)}`;
  const catalog = useResource<SpotCatalog>(`/markets/symbols?${suffix}`);
  const wanted = params.get('symbol') || `${params.get('asset') || 'BTC'}/USDT`;
  const pairs = catalog.data?.items ?? [];
  const symbol = pairs.some((p) => p.symbol === wanted)
    ? wanted
    : pairs.find((p) => p.symbol === 'BTC/USDT')?.symbol ||
      pairs.find((p) => p.symbol === 'BTC/USD')?.symbol ||
      pairs[0]?.symbol ||
      wanted;
  const [chosenFrame, setTimeframe] = useState<Timeframe>('1d');
  const frames = catalog.data?.timeframes ?? [];
  const timeframe = frames.includes(chosenFrame)
    ? chosenFrame
    : frames.includes('1d')
      ? '1d'
      : frames[0] || '1d';
  const [chosenLimit, setLimit] = useState(180);
  const maxLimit = Math.min(720, catalog.data?.candle_limits?.[timeframe] ?? 720);
  const limit = Math.min(chosenLimit, maxLimit);
  const hasCandles = !!catalog.data?.capabilities?.candles && frames.length > 0;
  const [bands, setBands] = useState(true);
  const [view, setView] = useState('candles');
  const [tab, setTab] = useState('technical');
  const [method, setMethod] = useState('pearson');
  const [transform, setTransform] = useState('log_returns');
  const [draft, setDraft] = useState('');
  const [symbols, setSymbols] = useState('');
  const defaults = ['BTC', 'ETH', 'SOL', 'LINK']
    .map((base) => pairs.find((p) => p.base === base && p.quote === symbol.split('/')[1])?.symbol)
    .filter(Boolean)
    .join(',');
  const comparisons = symbols || defaults;
  const market = useResource<Source & { items: MarketAsset[]; warnings: string[] }>(
    `/markets?${suffix}`,
    60000,
  );
  const analysis = useResource<Analysis>(
    `/markets/analysis?symbol=${encodeURIComponent(symbol)}&timeframe=${timeframe}&limit=${limit}&${suffix}`,
    60000,
    hasCandles && pairs.length > 0,
  );
  const corr = useResource<Correlation>(
    `/markets/correlation?symbols=${encodeURIComponent(comparisons)}&timeframe=${timeframe}&limit=${limit}&method=${method}&transform=${transform}&${suffix}`,
    0,
    hasCandles && tab === 'correlation' && comparisons.split(',').length >= 2,
  );
  const select = (value: string) => {
    const next = new URLSearchParams(params);
    next.set('symbol', value);
    next.delete('asset');
    setParams(next);
  };
  const context = { symbol, timeframe, limit, market_source: sourceId };
  return (
    <>
      <PageTitle
        title="Markets"
        description="Explore price, momentum, and the relationships between your markets."
        action={<AgentButton module="analyst" context={context} />}
      />
      {feedControl}
      <div className="market-ticker-grid">
        {market.data?.items.slice(0, 4).map((item) => (
          <button
            key={item.asset}
            className={`panel market-ticker ${symbol === item.symbol ? 'ticker-selected' : ''}`}
            onClick={() => select(item.symbol)}
          >
            <div className="ticker-label">
              <AssetIcon asset={item.asset} color={item.color} />
              <strong>{item.name}</strong>
              <span>{item.asset}</span>
            </div>
            <div className="ticker-value">
              {number(item.price)} <small>{item.quote}</small>
              <Change value={item.change} />
            </div>
            {item.sparkline.length > 1 && (
              <Sparkline data={item.sparkline} color={item.color} width={140} />
            )}
            {item.status === 'stale' && <Badge tone="sand">Stale quote</Badge>}
          </button>
        ))}
      </div>
      {market.data?.warnings.map((warning) => (
        <p key={warning} className="footnote">
          {warning}
        </p>
      ))}
      {catalog.error && <ErrorState message={catalog.error} retry={catalog.retry} />}
      {!catalog.data && !catalog.error && <Loading />}
      {catalog.data && !hasCandles && (
        <Panel className="market-quotes-only">
          <PanelTitle title="A quotes-only feed" subtitle={source.name} />
          <p>
            This provider supplies current reference prices. Choose a public exchange or
            CryptoCompare above for candle charts, indicators and correlations.
          </p>
          <DataNote source={sourceId} label={source.name} />
        </Panel>
      )}
      {hasCandles && (
        <div className="market-analysis-grid">
          <Panel>
            <PanelTitle
              title={symbol.replace('/', ' / ')}
              subtitle="Closed candles · spot market"
            />
            <div className="workspace-controls">
              <MarketSelector value={symbol} onChange={select} catalog={catalog.data} />
              <TimeframeSelect value={timeframe} onChange={setTimeframe} catalog={catalog.data} />
              <label>
                Observations
                <select value={limit} onChange={(e) => setLimit(Number(e.target.value))}>
                  {[...new Set([90, 180, 365, 720, maxLimit])]
                    .filter((n) => n <= maxLimit && n >= 60)
                    .sort((a, b) => a - b)
                    .map((n) => (
                      <option key={n} value={n}>
                        {n} candles
                      </option>
                    ))}
                </select>
              </label>
            </div>
            <SectionTabs
              id="market-analysis"
              label="Market analysis"
              compact
              items={[
                { id: 'technical', label: 'Price & indicators', icon: CandlestickChart },
                { id: 'correlation', label: 'Correlations', icon: Network },
              ]}
              value={tab}
              onChange={setTab}
            />
            <SectionPanel id="market-analysis" value={tab}>
              {tab === 'technical' ? (
                analysis.loading ? (
                  <Loading />
                ) : analysis.error || !analysis.data ? (
                  <ErrorState message={analysis.error} retry={analysis.retry} />
                ) : (
                  <>
                    <div className="market-chart-heading">
                      <div>
                        <strong>
                          {number(analysis.data.price, analysis.data.price < 1 ? 6 : 2)}
                        </strong>
                        <small>{symbol.split('/')[1]}</small>
                        <Badge tone={analysis.data.trend === 'Bullish' ? 'lime' : 'rose'}>
                          {analysis.data.trend} EMA
                        </Badge>
                      </div>
                      <div className="filter-pills">
                        <button
                          className={view === 'candles' ? 'selected' : ''}
                          onClick={() => setView('candles')}
                        >
                          Candles
                        </button>
                        <button
                          className={view === 'line' ? 'selected' : ''}
                          onClick={() => setView('line')}
                        >
                          Line
                        </button>
                        <button
                          className={bands ? 'selected' : ''}
                          onClick={() => setBands(!bands)}
                          aria-pressed={bands}
                        >
                          Indicators
                        </button>
                      </div>
                    </div>
                    {view === 'candles' ? (
                      <Candlesticks data={analysis.data.candles} bands={bands} />
                    ) : (
                      <IndicatorChart
                        data={analysis.data.candles.map((row) => ({ ...row }))}
                        bands={bands}
                      />
                    )}
                    <div className="chart-footnote">
                      <DataNote source={analysis.data.source} label={analysis.data.source_label} />
                      <button
                        className="text-button"
                        onClick={() =>
                          exportCSV('sibyl-candles.csv', [
                            [
                              'Time',
                              'Open',
                              'High',
                              'Low',
                              'Close',
                              'Volume',
                              'Symbol',
                              'Timeframe',
                            ],
                            ...analysis.data!.candles.map((c) => [
                              c.timestamp,
                              c.open,
                              c.high,
                              c.low,
                              c.close,
                              c.volume,
                              symbol,
                              timeframe,
                            ]),
                          ])
                        }
                      >
                        <Download size={12} /> Export OHLCV
                      </button>
                    </div>
                  </>
                )
              ) : (
                <>
                  <form
                    className="correlation-controls"
                    onSubmit={(e) => {
                      e.preventDefault();
                      setSymbols(
                        (draft || defaults)
                          .toUpperCase()
                          .split(',')
                          .map((s) => s.trim())
                          .filter(Boolean)
                          .join(','),
                      );
                    }}
                  >
                    <label>
                      Compare markets · 2–8 symbols
                      <input
                        value={draft || defaults}
                        onChange={(e) => setDraft(e.target.value)}
                        maxLength={350}
                      />
                    </label>
                    <div className="workspace-controls">
                      <label>
                        Method
                        <select value={method} onChange={(e) => setMethod(e.target.value)}>
                          <option value="pearson">Pearson</option>
                          <option value="spearman">Spearman ranks</option>
                        </select>
                      </label>
                      <label>
                        Data
                        <select value={transform} onChange={(e) => setTransform(e.target.value)}>
                          <option value="log_returns">Log returns</option>
                          <option value="prices">Price levels</option>
                          <option value="changes">Absolute changes</option>
                        </select>
                      </label>
                      <button className="button secondary" type="submit">
                        Compare
                      </button>
                    </div>
                  </form>
                  {corr.loading ? (
                    <Loading />
                  ) : corr.error || !corr.data ? (
                    <ErrorState message={corr.error} retry={corr.retry} />
                  ) : (
                    <div className="correlation-container">
                      <p className="muted">
                        {corr.data.observations} aligned observations · {timeframe}
                      </p>
                      <div className="table-scroll">
                        <table className="correlation-table">
                          <thead>
                            <tr>
                              <th />
                              {corr.data.symbols.map((s) => (
                                <th key={s}>{s}</th>
                              ))}
                            </tr>
                          </thead>
                          <tbody>
                            {corr.data.symbols.map((s, i) => (
                              <tr key={s}>
                                <th>{s}</th>
                                {corr.data!.matrix[i].map((v, j) => (
                                  <td
                                    key={j}
                                    style={{
                                      background: `rgba(${v >= 0 ? '91,143,211' : '197,108,128'},${0.05 + Math.abs(v) * 0.35})`,
                                    }}
                                  >
                                    {v.toFixed(2)}
                                  </td>
                                ))}
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                      <p className="footnote">
                        Correlation changes with the window and transformation. Association does not
                        establish causation.
                      </p>
                      <DataNote source={corr.data.source} label={corr.data.source_label} />
                    </div>
                  )}
                </>
              )}
            </SectionPanel>
          </Panel>
          <div className="market-side-stack">
            <Panel>
              <PanelTitle
                title="Technical snapshot"
                subtitle={`${timeframe} · ${limit} observations requested`}
              />
              {analysis.data && (
                <div className="stat-list">
                  <div>
                    <span>RSI · 14 periods</span>
                    <strong>{analysis.data.rsi.toFixed(1)}</strong>
                  </div>
                  <div className="rsi-meter">
                    <span style={{ left: `${analysis.data.rsi}%` }} />
                  </div>
                  <div>
                    <span>Annualized volatility</span>
                    <strong>{analysis.data.volatility.toFixed(1)}%</strong>
                  </div>
                  <div>
                    <span>Sample high</span>
                    <strong>{number(analysis.data.high, analysis.data.high < 1 ? 6 : 2)}</strong>
                  </div>
                  <div>
                    <span>Sample low</span>
                    <strong>{number(analysis.data.low, analysis.data.low < 1 ? 6 : 2)}</strong>
                  </div>
                  <div>
                    <span>Sample return</span>
                    <Change value={analysis.data.period_return} />
                  </div>
                </div>
              )}
            </Panel>
            <div className="quiet-callout">
              <span className="four-point">✳</span>
              <h3>Keep the context.</h3>
              <p>Ask your analyst about this market and the exact chart window you selected.</p>
              <AgentButton module="analyst" context={context} compact>
                Discuss this window
              </AgentButton>
            </div>
          </div>
        </div>
      )}
      <Panel className="full-panel">
        <PanelTitle title="Market watchlist" subtitle={`Reference quotes · ${source.name}`} />
        {market.loading && !market.data ? (
          <Loading />
        ) : market.error ? (
          <ErrorState message={market.error} retry={market.retry} />
        ) : (
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Asset</th>
                  <th>Price / quote</th>
                  <th>24h move</th>
                  <th>Quote volume</th>
                  <th>Updated</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {market.data?.items.map((item) => (
                  <tr key={item.asset}>
                    <td>
                      <button className="asset-name" onClick={() => select(item.symbol)}>
                        <AssetIcon asset={item.asset} color={item.color} />
                        <strong>{item.name}</strong>
                      </button>
                    </td>
                    <td>
                      {number(item.price)} <small className="muted">{item.quote}</small>
                    </td>
                    <td>
                      <Change value={item.change} />
                    </td>
                    <td>
                      {item.volume == null ? '—' : `${number(item.volume / 1e6)}M ${item.quote}`}
                    </td>
                    <td>
                      <span
                        className={item.status === 'stale' ? 'negative' : 'muted'}
                        title={
                          item.observed_at
                            ? new Date(item.observed_at).toLocaleString()
                            : 'Provider did not supply a timestamp'
                        }
                      >
                        {sourceId === 'demo'
                          ? 'Illustrative'
                          : item.observed_at
                            ? new Date(item.observed_at).toLocaleTimeString([], {
                                hour: '2-digit',
                                minute: '2-digit',
                              })
                            : 'Undated'}
                        {item.status === 'stale' ? ' · Stale' : ''}
                      </span>
                    </td>
                    <td>
                      <Link className="text-link" to={`/trade?asset=${item.asset}`}>
                        Trade <ArrowUpRight size={13} />
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <div className="table-footer">
          <DataNote
            source={market.data?.source || sourceId}
            label={market.data?.source_label || source.name}
          />
          <span className="muted">
            {source.environment === 'test' ? 'Test environment · ' : ''}
            {source.kind === 'demo'
              ? 'Backend sample data'
              : 'Cached quotes · refresh every minute · missing values shown as —'}
          </span>
        </div>
      </Panel>
      <ComingSoon module="markets" />
    </>
  );
}

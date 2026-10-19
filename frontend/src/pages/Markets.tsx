import { useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { ArrowUpRight, Download, CandlestickChart, Network } from 'lucide-react';
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
import { MarketSelector, TimeframeSelect } from '../components/market-controls';
import { ComingSoon } from '../components/coming-soon';
import { exportCSV, number } from '../lib/api';
import { useResource } from '../lib/hooks';
import type { Analysis, MarketAsset, Source, Timeframe } from '../lib/types';

type Correlation = Source & { symbols: string[]; matrix: number[][]; observations: number };
export function Markets() {
  const [params, setParams] = useSearchParams();
  const symbol = params.get('symbol') || `${params.get('asset') || 'BTC'}/USDT`;
  const [timeframe, setTimeframe] = useState<Timeframe>('1d');
  const [limit, setLimit] = useState(180);
  const [bands, setBands] = useState(true);
  const [view, setView] = useState('candles');
  const [tab, setTab] = useState('technical');
  const [method, setMethod] = useState('pearson');
  const [transform, setTransform] = useState('log_returns');
  const [draft, setDraft] = useState('BTC/USDT, ETH/USDT, SOL/USDT, LINK/USDT');
  const [symbols, setSymbols] = useState('BTC/USDT,ETH/USDT,SOL/USDT,LINK/USDT');
  const market = useResource<Source & { items: MarketAsset[] }>('/markets', 60000);
  const analysis = useResource<Analysis>(
    `/markets/analysis?symbol=${encodeURIComponent(symbol)}&timeframe=${timeframe}&limit=${limit}`,
  );
  const corr = useResource<Correlation>(
    `/markets/correlation?symbols=${encodeURIComponent(symbols)}&timeframe=${timeframe}&limit=${limit}&method=${method}&transform=${transform}`,
  );
  const select = (value: string) => setParams({ symbol: value });
  const context = { symbol, timeframe, limit };
  return (
    <>
      <PageTitle
        title="Markets"
        description="Explore price, momentum, and the relationships between your markets."
        action={<AgentButton module="analyst" context={context} />}
      />
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
              {number(item.price)} <small>USDT</small>
              <Change value={item.change} />
            </div>
            <Sparkline data={item.sparkline} color={item.color} width={140} />
          </button>
        ))}
      </div>
      <div className="market-analysis-grid">
        <Panel>
          <PanelTitle title={symbol.replace('/', ' / ')} subtitle="Closed candles · spot market" />
          <div className="workspace-controls">
            <MarketSelector value={symbol} onChange={select} />
            <TimeframeSelect value={timeframe} onChange={setTimeframe} />
            <label>
              Observations
              <select value={limit} onChange={(e) => setLimit(Number(e.target.value))}>
                {[90, 180, 365, 720].map((n) => (
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
                    <DataNote source={analysis.data.source} />
                    <button
                      className="text-button"
                      onClick={() =>
                        exportCSV('sibyl-candles.csv', [
                          ['Time', 'Open', 'High', 'Low', 'Close', 'Volume', 'Symbol', 'Timeframe'],
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
                      draft
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
                      value={draft}
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
                    <DataNote source={corr.data.source} />
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
      <Panel className="full-panel">
        <PanelTitle title="Market watchlist" subtitle="Daily reference prices · USDT quotes" />
        {market.error ? (
          <ErrorState message={market.error} retry={market.retry} />
        ) : (
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Asset</th>
                  <th>Price · USDT</th>
                  <th>24h move</th>
                  <th>Quote volume</th>
                  <th>History</th>
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
                    <td>{number(item.price)}</td>
                    <td>
                      <Change value={item.change} />
                    </td>
                    <td>{number(item.volume / 1e6)}M</td>
                    <td>
                      <Sparkline data={item.sparkline} color={item.color} />
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
          <DataNote source={market.data?.source} />
        </div>
      </Panel>
      <ComingSoon module="markets" />
    </>
  );
}

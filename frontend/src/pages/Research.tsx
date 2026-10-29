import { useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import {
  Area,
  CartesianGrid,
  ComposedChart,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import {
  ArrowUpRight,
  BookOpen,
  Box,
  ExternalLink,
  FlaskConical,
  Search,
  TrendingUp,
} from 'lucide-react';
import {
  Badge,
  DataNote,
  Empty,
  ErrorState,
  Loading,
  PageTitle,
  Panel,
  PanelTitle,
} from '../components/ui';
import { AgentButton } from '../components/agents';
import { NewsWorkspace } from '../components/news-workspace';
import { ForecastWorkspace } from '../components/forecast-workspace';
import { BitcoinInspector } from '../components/bitcoin-inspector';
import { CryptoLibraryView } from '../components/crypto-library';
import { SectionTabs, SectionPanel } from '../components/section-tabs';
import { ComingSoon } from '../components/coming-soon';
import { ValueChart } from '../components/charts';
import { exportCSV, money, number, shortDate } from '../lib/api';
import { useResource } from '../lib/hooks';
import type { Analysis, Block, Forecast, Knowledge, Source, Stock } from '../lib/types';

export function ForecastPage() {
  const [search, setSearch] = useSearchParams();
  const tab = search.get('tab') === 'baseline' ? 'baseline' : 'models';
  return (
    <>
      <PageTitle
        title="Forecasting"
        description="Train, evaluate and inspect reproducible daily forecasts."
      />
      <SectionTabs
        id="forecast"
        label="Forecasting workspaces"
        value={tab}
        items={[
          { id: 'models', label: 'Trained models', icon: FlaskConical },
          { id: 'baseline', label: 'Statistical baseline', icon: TrendingUp },
        ]}
        onChange={(value) =>
          setSearch((p) => {
            p.set('tab', value);
            return p;
          })
        }
      />
      <SectionPanel id="forecast" value={tab}>
        {tab === 'models' ? <ForecastWorkspace /> : <ForecastBaseline />}
      </SectionPanel>
      <ComingSoon module="forecast" />
    </>
  );
}

function ForecastBaseline() {
  const [asset, setAsset] = useState('BTC');
  const [horizon, setHorizon] = useState(14);
  const result = useResource<Forecast>(
    `/forecast?symbol=${encodeURIComponent(`${asset}/USDT`)}&horizon=${horizon}`,
  );
  const history = useResource<Analysis>(
    `/markets/analysis?symbol=${encodeURIComponent(`${asset}/USDT`)}&limit=90`,
  );
  const data = result.data;
  const last = data?.points[data.points.length - 1];
  const points = [
    ...(history.data?.candles.slice(-30).map((candle) => ({
      timestamp: candle.timestamp,
      observed: candle.close,
    })) ?? []),
    ...(data?.points.map((point) => ({
      timestamp: point.timestamp,
      projected: point.value,
      interval: [point.lower, point.upper],
    })) ?? []),
  ];
  return (
    <>
      <Panel className="full-panel">
        <PanelTitle
          title="Forecast workspace"
          subtitle="Chronos · log-return statistical baseline"
          action={
            <>
              <Badge tone="purple">Untrained baseline</Badge>
              <AgentButton module="chronos" context={{ symbol: `${asset}/USDT`, horizon }} />
            </>
          }
        />
        <div className="forecast-controls">
          <label>
            Market
            <select value={asset} onChange={(event) => setAsset(event.target.value)}>
              {['BTC', 'ETH', 'SOL', 'LINK'].map((symbol) => (
                <option key={symbol}>{symbol}</option>
              ))}
            </select>
          </label>
          <label>
            Forecast horizon
            <select value={horizon} onChange={(event) => setHorizon(Number(event.target.value))}>
              <option value={7}>7 days</option>
              <option value={14}>14 days</option>
              <option value={30}>30 days</option>
            </select>
          </label>
          <div className="chart-legend">
            <span className="little-dot" style={{ background: '#4675d2' }} />
            Observed <span className="little-dot" style={{ background: '#cf9a61' }} />
            Baseline & model interval
          </div>
        </div>
        {result.error ? (
          <ErrorState message={result.error} retry={result.retry} />
        ) : result.loading || history.loading ? (
          <Loading />
        ) : history.error ? (
          <ErrorState message={history.error} retry={history.retry} />
        ) : (
          <div className="forecast-chart">
            <ResponsiveContainer width="100%" height="100%">
              <ComposedChart data={points} margin={{ top: 20, right: 10, left: 10, bottom: 10 }}>
                <CartesianGrid stroke="var(--chart-grid)" vertical={false} strokeDasharray="3 5" />
                <XAxis
                  dataKey="timestamp"
                  tickFormatter={shortDate}
                  minTickGap={55}
                  axisLine={false}
                  tickLine={false}
                  tick={{ fill: 'var(--muted)', fontSize: 11 }}
                />
                <YAxis
                  domain={['auto', 'auto']}
                  orientation="right"
                  width={75}
                  tickFormatter={(value) => money(Number(value), 0)}
                  axisLine={false}
                  tickLine={false}
                  tick={{ fill: 'var(--muted)', fontSize: 10 }}
                />
                <Tooltip
                  contentStyle={{
                    background: 'var(--surface-raised)',
                    border: '1px solid var(--border)',
                    borderRadius: 10,
                  }}
                  labelFormatter={(value) => shortDate(String(value))}
                  formatter={(value) =>
                    Array.isArray(value)
                      ? `${money(Number(value[0]))} – ${money(Number(value[1]))}`
                      : money(Number(value))
                  }
                />
                <Area
                  type="monotone"
                  dataKey="interval"
                  name="Approximate 95% model band"
                  fill="#cf9a61"
                  fillOpacity={0.15}
                  stroke="none"
                />
                <Line
                  dataKey="observed"
                  name="Observed price"
                  stroke="#4675d2"
                  dot={false}
                  strokeWidth={2}
                />
                <Line
                  dataKey="projected"
                  name="Baseline"
                  stroke="#cf9a61"
                  strokeWidth={2}
                  dot={false}
                  strokeDasharray="5 4"
                />
              </ComposedChart>
            </ResponsiveContainer>
          </div>
        )}
        <div className="chart-footnote">
          <DataNote source={data?.source} />
          <span>Drift and volatility estimated from up to 90 daily returns</span>
        </div>
      </Panel>
      {data && last && (
        <div className="forecast-summary-grid">
          <Panel>
            <small>Last observed close</small>
            <strong>{money(data.last_price)}</strong>
            <span>{asset} / USDT</span>
          </Panel>
          <Panel>
            <small>Day {horizon} baseline</small>
            <strong>{money(last.value)}</strong>
            <span>Constant log-return drift assumption</span>
          </Panel>
          <Panel>
            <small>Approximate model interval</small>
            <strong>
              {money(last.lower, 0)} – {money(last.upper, 0)}
            </strong>
            <span>95% theoretical band · uncalibrated</span>
          </Panel>
        </div>
      )}
      <div className="quiet-callout horizontal-callout">
        <span className="four-point">✳</span>
        <div>
          <h3>Uncertainty belongs in the picture.</h3>
          <p>
            {data?.note ?? 'A statistical baseline is a starting point, not a trading signal.'} This
            model assumes constant volatility and does not account for news, regime changes, or
            liquidity shocks.
          </p>
        </div>
        <AgentButton module="chronos" context={{ symbol: `${asset}/USDT`, horizon }} compact>
          Explore the assumptions
        </AgentButton>
      </div>
    </>
  );
}

export function News() {
  return <NewsWorkspace />;
}

function KnowledgeView() {
  const entries = useResource<Knowledge[]>('/knowledge');
  const [query, setQuery] = useState('');
  const filtered = entries.data?.filter((entry) =>
    `${entry.term} ${entry.text} ${entry.category}`.toLowerCase().includes(query.toLowerCase()),
  );
  return (
    <>
      <div className="research-topline">
        <div className="search-field">
          <Search size={16} />
          <input
            aria-label="Search knowledge"
            placeholder="RSI, diversification, API keys…"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
          />
        </div>
        <AgentButton module="wiki" context={{ query: query.slice(0, 200) }} />
      </div>
      {entries.loading ? (
        <Loading />
      ) : entries.error ? (
        <ErrorState message={entries.error} retry={entries.retry} />
      ) : (
        <div className="knowledge-grid">
          {filtered?.map((entry) => (
            <Panel className="knowledge-card" key={entry.term}>
              <Badge tone="purple">{entry.category}</Badge>
              <h3>{entry.term}</h3>
              <p>{entry.text}</p>
              <a className="text-link" href={entry.url} target="_blank" rel="noreferrer">
                Reference <ExternalLink size={12} />
              </a>
            </Panel>
          ))}
        </div>
      )}
      {filtered?.length === 0 && (
        <Empty title="A question worth asking">
          No glossary entries match. Try a broader term.
        </Empty>
      )}
      <p className="footnote">
        A curated local glossary with keyword search. External references provide further context;
        Sibyl-specific formulas are documented here.
      </p>
      <ComingSoon module="knowledge" />
    </>
  );
}

function ExplorerView() {
  const [count, setCount] = useState(10);
  const blocks = useResource<Source & { items: Block[] }>(`/blocks?count=${count}`, 60000);
  const rows = blocks.data?.items ?? [];
  const average = (key: 'size' | 'tx_count') =>
    rows.reduce((sum, row) => sum + row[key], 0) / Math.max(1, rows.length);
  return (
    <>
      <BitcoinInspector />
      <Panel>
        <PanelTitle
          title="Bitcoin block explorer"
          subtitle="A window onto the chain"
          action={<AgentButton module="explorer" compact />}
        />
        <div className="workspace-controls">
          <label>
            Recent blocks
            <select value={count} onChange={(e) => setCount(Number(e.target.value))}>
              {[10, 25, 50, 100].map((n) => (
                <option key={n}>{n}</option>
              ))}
            </select>
          </label>
          <button
            className="button secondary"
            onClick={() =>
              exportCSV('sibyl-bitcoin-blocks.csv', [
                ['Height', 'Timestamp', 'Transactions', 'Bytes', 'ID'],
                ...rows.map((row) => [
                  row.height,
                  new Date(row.timestamp * 1000).toISOString(),
                  row.tx_count,
                  row.size,
                  row.id,
                ]),
              ])
            }
            disabled={!rows.length}
          >
            Export blocks
          </button>
        </div>
        {blocks.loading ? (
          <Loading />
        ) : blocks.error ? (
          <ErrorState message={blocks.error} retry={blocks.retry} />
        ) : (
          <>
            <div className="extended-metrics">
              <div>
                <small>Mean transactions / block</small>
                <strong>{number(average('tx_count'), 0)}</strong>
              </div>
              <div>
                <small>Mean size</small>
                <strong>{number(average('size') / 1e6)} MB</strong>
              </div>
              <div>
                <small>Observed mean interval</small>
                <strong>
                  {rows.length > 1
                    ? `${number(Math.abs(rows[0].timestamp - rows[rows.length - 1].timestamp) / (rows.length - 1) / 60)} min`
                    : '—'}
                </strong>
              </div>
            </div>
            <div className="block-volume-chart">
              <ValueChart
                currency={false}
                height={180}
                data={[...rows].reverse().map((row) => ({
                  timestamp: new Date(row.timestamp * 1000).toISOString(),
                  value: row.tx_count,
                }))}
              />
              <p className="footnote padded">
                Transactions per displayed block · ordered by block height
              </p>
            </div>
            <div className="block-grid">
              {blocks.data?.items.slice(0, 5).map((block, i) => (
                <div className="block-card" key={block.id}>
                  <Box size={30} />
                  <small>{i === 0 ? 'LATEST DISPLAYED' : `${i} BLOCKS EARLIER`}</small>
                  <strong>#{number(block.height, 0)}</strong>
                  <span>{number(block.tx_count, 0)} transactions</span>
                </div>
              ))}
            </div>
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>Height</th>
                    <th>Time</th>
                    <th>Transactions</th>
                    <th>Size</th>
                    <th>Reference</th>
                  </tr>
                </thead>
                <tbody>
                  {blocks.data?.items.map((block) => (
                    <tr key={block.id}>
                      <td>#{number(block.height, 0)}</td>
                      <td>{new Date(block.timestamp * 1000).toLocaleString()}</td>
                      <td>{number(block.tx_count, 0)}</td>
                      <td>{number(block.size / 1e6)} MB</td>
                      <td>
                        {blocks.data?.source === 'demo' ? (
                          <Badge>Sample</Badge>
                        ) : (
                          <a
                            className="text-link"
                            href={`https://mempool.space/block/${encodeURIComponent(block.id)}`}
                            target="_blank"
                            rel="noreferrer"
                          >
                            View block <ExternalLink size={12} />
                          </a>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="chart-footnote">
              <DataNote source={blocks.data?.source} />
              <span>
                {blocks.data?.source === 'demo'
                  ? 'Synthetic sample blocks'
                  : 'Bitcoin mainnet · provider observations'}
              </span>
            </div>
          </>
        )}
      </Panel>
      <ComingSoon module="explorer" />
    </>
  );
}

function StocksView() {
  const [symbol, setSymbol] = useState('AAPL');
  const [draft, setDraft] = useState('AAPL');
  const stock = useResource<Stock>(`/stocks/${encodeURIComponent(symbol)}`);
  return (
    <>
      <div className="research-topline">
        <form
          className="stock-search"
          onSubmit={(event) => {
            event.preventDefault();
            setSymbol(draft.toUpperCase());
          }}
        >
          <input
            aria-label="Equity ticker"
            required
            maxLength={10}
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            placeholder="Equity ticker"
          />
          <button className="button primary" type="submit">
            Explore <ArrowUpRight size={14} />
          </button>
        </form>
        <div className="filter-pills">
          {['AAPL', 'MSFT', 'NVDA', 'COIN'].map((item) => (
            <button
              className={symbol === item ? 'selected' : ''}
              key={item}
              onClick={() => {
                setSymbol(item);
                setDraft(item);
              }}
            >
              {item}
            </button>
          ))}
        </div>
      </div>
      <Panel>
        <PanelTitle
          title={stock.data?.name ?? symbol}
          subtitle="A wider market lens · adjusted daily history"
          action={<AgentButton module="stocks" context={{ equity_symbol: symbol }} compact />}
        />
        {stock.loading ? (
          <Loading />
        ) : stock.error ? (
          <ErrorState message={stock.error} retry={stock.retry} />
        ) : (
          stock.data && (
            <>
              <div className="market-chart-heading">
                <strong>{money(stock.data.price)}</strong>
                <Badge>
                  {stock.data.symbol} · {stock.data.currency}
                </Badge>
              </div>
              <ValueChart
                data={stock.data.history}
                height={320}
                currency={stock.data.currency === 'USD'}
              />
              <div className="extended-metrics">
                <div>
                  <small>Period return</small>
                  <strong>{number(stock.data.statistics.period_return)}%</strong>
                </div>
                <div>
                  <small>Annualized volatility</small>
                  <strong>{number(stock.data.statistics.volatility)}%</strong>
                </div>
                <div>
                  <small>Maximum drawdown</small>
                  <strong>{number(stock.data.statistics.max_drawdown)}%</strong>
                </div>
                <div>
                  <small>Observed high / low</small>
                  <strong>
                    {number(stock.data.statistics.high)} / {number(stock.data.statistics.low)}
                  </strong>
                </div>
              </div>
              {stock.data.profile && (
                <div className="company-profile">
                  <h3>Company profile</h3>
                  <div className="filter-pills">
                    {[
                      stock.data.profile.sector,
                      stock.data.profile.industry,
                      stock.data.profile.country,
                    ]
                      .filter(Boolean)
                      .map((item) => (
                        <Badge key={item}>{item}</Badge>
                      ))}
                  </div>
                  <p>{stock.data.profile.description}</p>
                  <div className="extended-metrics">
                    {stock.data.profile.market_cap != null && (
                      <div>
                        <small>Market capitalization</small>
                        <strong>
                          {number(stock.data.profile.market_cap)} {stock.data.currency}
                        </strong>
                      </div>
                    )}
                    {stock.data.profile.trailing_pe != null && (
                      <div>
                        <small>Trailing P/E</small>
                        <strong>{number(stock.data.profile.trailing_pe)}</strong>
                      </div>
                    )}
                  </div>
                </div>
              )}
              {stock.data.profile_warning && (
                <p className="footnote padded">{stock.data.profile_warning}</p>
              )}
              <div className="chart-footnote">
                <DataNote source={stock.data.source} />
                <span>{stock.data.statistics.observations} observed sessions</span>
              </div>
            </>
          )
        )}
      </Panel>
      <ComingSoon module="stocks" />
    </>
  );
}

export function ResearchPage() {
  const [params, setParams] = useSearchParams();
  const selected = params.get('tab') ?? 'knowledge';
  const tab = ['knowledge', 'crypto', 'explorer', 'stocks'].includes(selected)
    ? selected
    : 'knowledge';
  const setTab = (value: string) =>
    setParams((previous) => {
      const next = new URLSearchParams(previous);
      next.set('tab', value);
      return next;
    });
  return (
    <>
      <PageTitle
        eyebrow="FOLLOW YOUR CURIOSITY"
        title="Research"
        description="Crypto concepts, project profiles, Bitcoin activity and equity research."
      />
      <SectionTabs
        id="research"
        label="Research sections"
        items={[
          { id: 'knowledge', label: 'Crypto knowledge', icon: BookOpen },
          { id: 'crypto', label: 'Crypto profiles', icon: BookOpen },
          { id: 'explorer', label: 'Block explorer', icon: Box },
          { id: 'stocks', label: 'Equities', icon: TrendingUp },
        ]}
        value={tab}
        onChange={setTab}
      />
      <SectionPanel id="research" value={tab}>
        {tab === 'knowledge' ? (
          <KnowledgeView />
        ) : tab === 'crypto' ? (
          <CryptoLibraryView />
        ) : tab === 'explorer' ? (
          <ExplorerView />
        ) : (
          <StocksView />
        )}
      </SectionPanel>
    </>
  );
}

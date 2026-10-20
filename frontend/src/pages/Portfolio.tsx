import { useState } from 'react';
import { Link } from 'react-router-dom';
import {
  ArrowDownLeft,
  ArrowUpRight,
  Download,
  Layers3,
  Plus,
  ShieldCheck,
  Sparkles,
  Wallet,
  Waves,
} from 'lucide-react';
import {
  AssetIcon,
  Change,
  DataNote,
  Empty,
  ErrorState,
  Loading,
  PageTitle,
  Panel,
  PanelTitle,
} from '../components/ui';
import { AccountBalances } from '../components/account-balances';
import { AgentButton } from '../components/agents';
import { Sparkline, ValueChart } from '../components/charts';
import { exportCSV, money, number } from '../lib/api';
import { useResource } from '../lib/hooks';
import type { Connection, Job, Order, Portfolio } from '../lib/types';
const colors = ['#4675d2', '#8b9cc5', '#61a99a', '#d5aa65', '#a491c4'];

export function PortfolioPage() {
  const { data, error, loading, retry } = useResource<Portfolio>('/portfolio', 60000);
  const { data: jobs } = useResource<Job[]>('/strategies/jobs', 30000);
  const { data: orders } = useResource<Order[]>('/orders');
  const { data: connections } = useResource<Connection[]>('/connections');
  const [range, setRange] = useState('1M');
  const [sort, setSort] = useState<'value' | 'change'>('value');
  if (loading) return <Loading />;
  if (error || !data)
    return <ErrorState message={error || 'Portfolio unavailable.'} retry={retry} />;
  const chartData = data.history.slice(
    -({ '1W': 7, '1M': 30, '3M': 90, ALL: data.history.length }[range] ?? 30),
  );
  const activeJobs = jobs?.filter((job) => job.status === 'running').length ?? 0;
  const holdings = [...data.holdings].sort((a, b) => b[sort] - a[sort]);
  const exportHoldings = () =>
    exportCSV('sibyl-holdings.csv', [
      ['Asset', 'Quantity', 'Price (USDT)', 'Value (USDT)', 'Allocation (%)', 'Source'],
      ...holdings.map((h) => [h.asset, h.quantity, h.price, h.value, h.allocation, data.source]),
    ]);
  return (
    <>
      <PageTitle
        title="Portfolio"
        description="Your assets, balances, and allocations."
        action={
          <>
            <AgentButton module="accountant" />
            <button className="button secondary" onClick={exportHoldings}>
              <Download size={15} />
              Export
            </button>
            <Link className="button primary" to="/settings?tab=exchanges">
              <Plus size={16} />
              Connect account
            </Link>
          </>
        }
      />
      {data.warnings.map((warning) => (
        <div className="inline-alert" key={warning}>
          {warning}
        </div>
      ))}
      <div className="summary-grid">
        <Panel className="summary-card">
          <div className="summary-label">
            Portfolio value
            <Wallet size={17} />
          </div>
          <strong className="summary-value monetary">{money(data.total)}</strong>
          <div className="summary-detail">
            <Change value={data.change} />
            <span>daily price move</span>
          </div>
        </Panel>
        <Panel className="summary-card">
          <div className="summary-label">
            {data.mode === 'demo' ? 'Available paper cash' : 'Data source'}
            <ShieldCheck size={17} />
          </div>
          <strong className={`summary-value ${data.mode === 'demo' ? 'monetary' : ''}`}>
            {data.mode === 'demo' ? money(data.cash) : data.source}
          </strong>
          <div className="summary-detail">
            <span>
              {data.mode === 'demo'
                ? 'Separate virtual trading balance'
                : 'Read-only connected balances'}
            </span>
          </div>
        </Panel>
        <Panel className="summary-card">
          <div className="summary-label">
            Assets
            <Layers3 size={17} />
          </div>
          <strong className="summary-value">{data.holdings.length}</strong>
          <div className="summary-detail">
            <span>{connections?.length ?? 0} accounts connected</span>
          </div>
        </Panel>
        <Panel className="summary-card">
          <div className="summary-label">
            Paper strategies
            <Waves size={17} />
          </div>
          <strong className="summary-value">
            {activeJobs}
            <small> running</small>
          </strong>
          <div className="summary-detail">
            <Link to="/strategies">
              Open strategy studio
              <ArrowUpRight size={12} />
            </Link>
          </div>
        </Panel>
      </div>
      <div className="dashboard-chart-grid">
        <Panel className="performance-panel">
          <PanelTitle
            title="Portfolio value"
            subtitle={
              data.mode === 'demo'
                ? 'Historical valuation of current paper holdings'
                : 'Observed account value'
            }
            action={
              <div className="segmented small">
                {['1W', '1M', '3M', 'ALL'].map((period) => (
                  <button
                    className={range === period ? 'selected' : ''}
                    key={period}
                    onClick={() => setRange(period)}
                  >
                    {period}
                  </button>
                ))}
              </div>
            }
          />
          <ValueChart data={chartData} color="#4675d2" height={265} />
          <div className="chart-footnote">
            <DataNote source={data.source} />
            <span>
              {data.mode === 'demo'
                ? 'Illustrative prices · not historical investment returns'
                : 'Account values include deposits and withdrawals'}
            </span>
          </div>
        </Panel>
        <Panel className="allocation-panel">
          <PanelTitle title="Allocation" subtitle="Share of priced portfolio" />
          <div className="allocation-track">
            {data.holdings.map((holding, i) => (
              <span
                key={holding.asset}
                style={{ width: `${holding.allocation}%`, background: colors[i % colors.length] }}
              />
            ))}
          </div>
          <div className="allocation-list">
            {data.holdings.map((holding, i) => (
              <div key={holding.asset}>
                <span>
                  <i style={{ background: colors[i % colors.length] }} />
                  {holding.name}
                </span>
                <strong>{holding.allocation.toFixed(1)}%</strong>
              </div>
            ))}
          </div>
        </Panel>
      </div>
      <div className="dashboard-lower-grid">
        <Panel className="holdings-panel">
          <PanelTitle
            title="Holdings"
            subtitle="Balances valued in USDT"
            action={
              <select
                className="subtle-select"
                aria-label="Sort assets"
                value={sort}
                onChange={(event) => setSort(event.target.value as 'value' | 'change')}
              >
                <option value="value">By value</option>
                <option value="change">By price move</option>
              </select>
            }
          />
          {holdings.length ? (
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>Asset</th>
                    <th>Price</th>
                    <th>Daily change</th>
                    <th className="spark-column">30 days</th>
                    <th className="align-right">Balance</th>
                  </tr>
                </thead>
                <tbody>
                  {holdings.map((holding, i) => (
                    <tr key={holding.asset}>
                      <td>
                        <Link
                          className="asset-name"
                          to={
                            holding.asset === 'USDT' ? '/trade' : `/markets?asset=${holding.asset}`
                          }
                        >
                          <AssetIcon asset={holding.asset} color={colors[i % colors.length]} />
                          <span>
                            <strong>{holding.name}</strong>
                            <small>{holding.asset}</small>
                          </span>
                        </Link>
                      </td>
                      <td className="monetary">{money(holding.price)}</td>
                      <td>
                        <Change value={holding.change} />
                      </td>
                      <td className="spark-column">
                        <Sparkline
                          data={holding.sparkline}
                          color={holding.change >= 0 ? '#6c9f90' : '#c4878a'}
                          width={85}
                        />
                      </td>
                      <td className="align-right">
                        <strong className="monetary">{money(holding.value)}</strong>
                        <small className="holding-quantity monetary">
                          {number(holding.quantity, 6)} {holding.asset}
                        </small>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <Empty title="No priced assets">
              Connect an account in Settings to view its holdings.
            </Empty>
          )}
          <div className="table-footer">
            <ShieldCheck size={13} />
            <span>
              {data.mode === 'demo'
                ? 'Paper balances · exchange funds stay separate'
                : 'Read-only exchange balances'}
            </span>
            <Link to="/trade">
              Trade
              <ArrowUpRight size={12} />
            </Link>
          </div>
        </Panel>
        <div className="dashboard-side-stack">
          <Panel className="oracle-summary">
            <PanelTitle title="Portfolio assistant" action={<Sparkles size={16} />} />
            <p>
              Ask Accountant to explain your allocation, concentration, and the balances shown here.
            </p>
            <AgentButton module="accountant" className="portfolio-agent-action" />
            <small>Dedicated module agent · ProtoLink</small>
          </Panel>
          <Panel className="recent-activity">
            <PanelTitle
              title="Recent activity"
              action={
                <Link className="text-link" to="/trade">
                  See all
                </Link>
              }
            />
            {orders?.length ? (
              orders.slice(0, 3).map((order) => (
                <div className="activity-row" key={order.id}>
                  <span className="activity-icon">
                    <ArrowDownLeft size={16} />
                  </span>
                  <div>
                    <strong>
                      Paper {order.side} · {order.symbol}
                    </strong>
                    <small>{new Date(order.created_at).toLocaleString()}</small>
                  </div>
                  <strong className="monetary">{money(order.notional)}</strong>
                </div>
              ))
            ) : (
              <div className="compact-empty">
                No paper trades yet.
                <Link className="text-link" to="/trade">
                  Open trading
                  <ArrowUpRight size={12} />
                </Link>
              </div>
            )}
          </Panel>
        </div>
      </div>
      <Panel className="full-panel">
        <PanelTitle title="Valuation notes" />
        <p className="muted">
          {data.history_note} USD stablecoins are approximated at 1 USDT. Daily changes apply to
          current holdings and do not measure investment returns.
        </p>
        {data.unpriced.length > 0 && (
          <p className="inline-alert">
            Excluded from the priced total:{' '}
            {data.unpriced.map((asset) => `${number(asset.quantity)} ${asset.asset}`).join(', ')}.
            No supported quote is available.
          </p>
        )}
      </Panel>
      <AccountBalances />
    </>
  );
}

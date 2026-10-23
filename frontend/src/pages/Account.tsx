import { useEffect, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
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
  Badge,
  Change,
  DataNote,
  Empty,
  ErrorState,
  Loading,
  PageTitle,
  Panel,
  PanelTitle,
} from '../components/ui';
import { SourceHealthSummary } from '../components/provider-health';
import { AccountBalances } from '../components/account-balances';
import { ExchangeMark } from '../components/exchange-mark';
import { AgentButton } from '../components/agents';
import { ValuationDetails } from '../components/valuation-details';
import {
  AccountContext,
  AccountSetup,
  PortfolioAccounts,
  PortfolioScope,
  useAccounts,
} from '../components/account-selection';
import { Sparkline, ValueChart } from '../components/charts';
import { exportCSV, money, number } from '../lib/api';
import { useResource } from '../lib/hooks';
import type { AccountSelection, Job, Order, Portfolio } from '../lib/types';
const colors = ['#4675d2', '#8b9cc5', '#61a99a', '#d5aa65', '#a491c4'];

export function AccountPage() {
  const accounts = useAccounts();
  const [params, setParams] = useSearchParams();
  useEffect(() => {
    const requested = params.get('scope');
    if (accounts.data && requested && !accounts.data.scopes.some((item) => item.id === requested)) {
      const next = new URLSearchParams(params);
      next.delete('scope');
      setParams(next, { replace: true });
    }
  }, [accounts.data?.signature, params, setParams]);
  if (accounts.loading) return <Loading />;
  if (accounts.error || !accounts.data)
    return (
      <ErrorState
        message={accounts.error || 'Account selection unavailable.'}
        retry={accounts.retry}
      />
    );
  if (!accounts.data.active_ids.length)
    return (
      <>
        <PageTitle title="Account" description="All your exchange accounts, together." />
        <AccountSetup selection={accounts.data} />
      </>
    );
  const requested = params.get('scope') || 'all';
  const scope = accounts.data.scopes.some((item) => item.id === requested) ? requested : 'all';
  return (
    <PortfolioWorkspace
      key={`${accounts.data.signature}:${scope}`}
      selection={accounts.data}
      scope={scope}
      select={(value) => {
        const next = new URLSearchParams(params);
        value === 'all' ? next.delete('scope') : next.set('scope', value);
        setParams(next);
      }}
    />
  );
}

function PortfolioWorkspace({
  selection,
  scope,
  select,
}: {
  selection: AccountSelection;
  scope: string;
  select: (scope: string) => void;
}) {
  const { data, error, loading, retry } = useResource<Portfolio>(
    `/account?scope=${encodeURIComponent(scope)}`,
    60000,
  );
  const { data: jobs } = useResource<Job[]>('/strategies/jobs', 30000);
  const { data: orders } = useResource<Order[]>('/orders');
  const [range, setRange] = useState('1M');
  const [sort, setSort] = useState<'value' | 'change'>('value');
  if (loading) return <Loading />;
  if (error || !data) return <ErrorState message={error || 'Account unavailable.'} retry={retry} />;
  const chartData = data.history.slice(
    -({ '1W': 7, '1M': 30, '3M': 90, ALL: data.history.length }[range] ?? 30),
  );
  const activeJobs = jobs?.filter((job) => job.status === 'running').length ?? 0;
  const holdings = [...data.holdings].sort(
    (a, b) => (b[sort] ?? -Infinity) - (a[sort] ?? -Infinity),
  );
  const exportHoldings = () =>
    exportCSV('sibyl-holdings.csv', [
      [
        'Asset',
        'Quantity',
        'Price (USDT)',
        'Value (USDT)',
        'Allocation (%)',
        'Source',
        'Pricing status',
        'Conversion path',
        'Provider time',
        'Reason',
        'View scope',
        'Account quantities',
      ],
      ...holdings.map((h) => [
        h.asset,
        h.quantity,
        h.price,
        h.value,
        h.allocation,
        data.source,
        h.status,
        h.path.join(' → '),
        h.observed_at ?? '',
        '',
        scope,
        h.accounts
          .map((account) => `${account.account}: ${account.quantity} ${h.asset}`)
          .join('; '),
      ]),
      ...data.unpriced.map((h) => [
        h.asset,
        h.quantity,
        '',
        '',
        '',
        data.source,
        h.status,
        '',
        '',
        h.reason ?? '',
        scope,
        '',
      ]),
    ]);
  return (
    <>
      <PageTitle
        title="Account"
        description="Your assets, balances, and allocations."
        action={
          <>
            <AgentButton module="accountant" context={{ portfolio_scope: scope }} />
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
      <SourceHealthSummary source={data.source} />
      <AccountContext selection={{ ...selection, mode: data.mode }} />
      <PortfolioScope selection={selection} scope={scope} onChange={select} />
      <PortfolioAccounts portfolio={data} select={select} />
      {data.warnings.map((warning) => (
        <div className="inline-alert" key={warning}>
          {warning}
        </div>
      ))}
      <div className="summary-grid">
        <Panel className="summary-card">
          <div className="summary-label">
            {data.complete ? 'Portfolio value' : 'Priced portfolio value'}
            <Wallet size={17} />
          </div>
          <strong className="summary-value monetary">
            {number(data.total)} <small>{data.currency}</small>
          </strong>
          <div className="summary-detail">
            <Change value={data.change} />
            <span>daily price move</span>
          </div>
        </Panel>
        <Panel className="summary-card">
          <div className="summary-label">
            {data.mode === 'demo' ? 'Paper cash & stablecoins' : 'Pricing source'}
            <ShieldCheck size={17} />
          </div>
          <strong className={`summary-value ${data.mode === 'demo' ? 'monetary' : ''}`}>
            {data.mode === 'demo' ? (
              <>
                {number(data.cash)} <small>{data.currency}</small>
              </>
            ) : (
              data.source_label || data.source
            )}
          </strong>
          <div className="summary-detail">
            <span>
              {data.mode === 'demo'
                ? 'Reference value of virtual cash holdings'
                : 'Read-only connected balances'}
            </span>
          </div>
        </Panel>
        <Panel className="summary-card">
          <div className="summary-label">
            Assets
            <Layers3 size={17} />
          </div>
          <strong className="summary-value">{data.coverage.total}</strong>
          <div className="summary-detail">
            <span>
              {data.coverage.priced}/{data.coverage.total} priced · {data.venues.length}{' '}
              {data.venues.length === 1 ? 'account in this view' : 'accounts combined'}
            </span>
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
            title={`Portfolio value · ${data.currency}`}
            subtitle={
              data.history_kind === 'illustrative'
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
          {chartData.length ? (
            <ValueChart data={chartData} color="#4675d2" height={265} unit={data.currency} />
          ) : (
            <Empty title="No complete history yet">
              A history point is recorded when account reads and pricing coverage are complete.
            </Empty>
          )}
          <div className="chart-footnote">
            <DataNote source={data.source} label={data.source_label} />
            <span>
              {data.history_kind === 'illustrative'
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
                    <th>Price · {data.currency}</th>
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
                            holding.route.length
                              ? `/markets?symbol=${encodeURIComponent(holding.route[0].symbol)}&source=${encodeURIComponent(data.source)}`
                              : '/trade'
                          }
                        >
                          <AssetIcon asset={holding.asset} color={colors[i % colors.length]} />
                          <span>
                            <strong>{holding.name}</strong>
                            <small>{holding.asset}</small>
                          </span>
                        </Link>
                        <details className="holding-contributors">
                          <summary>
                            {holding.accounts.length}{' '}
                            {holding.accounts.length === 1 ? 'account' : 'accounts'}
                          </summary>
                          <div>
                            {holding.accounts.map((account) => (
                              <span key={account.account_id}>
                                <ExchangeMark exchange={account.exchange} size={14} />{' '}
                                {account.account}:{' '}
                                <b className="monetary">
                                  {number(account.quantity, 8)} {holding.asset}
                                </b>
                              </span>
                            ))}
                          </div>
                        </details>
                      </td>
                      <td>
                        <span className="monetary">
                          {number(holding.price, holding.price < 10 ? 8 : 2)}
                        </span>
                        {holding.status === 'undated' && <Badge tone="sand">Undated</Badge>}
                        <ValuationDetails
                          quote={holding}
                          source={data.source_label || data.source}
                        />
                      </td>
                      <td>
                        <Change value={holding.change} />
                      </td>
                      <td className="spark-column">
                        {holding.sparkline.length > 1 ? (
                          <Sparkline
                            data={holding.sparkline}
                            color={(holding.change ?? 0) >= 0 ? '#6c9f90' : '#c4878a'}
                            width={85}
                          />
                        ) : (
                          <span className="muted">—</span>
                        )}
                      </td>
                      <td className="align-right">
                        <strong className="monetary">
                          {number(holding.value)} <small>{data.currency}</small>
                        </strong>
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
            <PanelTitle title="Account assistant" action={<Sparkles size={16} />} />
            <p>
              Ask Accountant to explain your allocation, concentration, and the balances shown here.
            </p>
            <AgentButton
              module="accountant"
              context={{ portfolio_scope: scope }}
              className="portfolio-agent-action"
            />
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
          {data.valuation_note} {data.history_note}
        </p>
        <div className="valuation-coverage">
          <Badge tone={data.complete ? 'lime' : 'sand'}>
            {data.complete ? 'Complete coverage' : 'Partial valuation'}
          </Badge>
          <span>
            {data.coverage.priced} of {data.coverage.total} held assets priced
          </span>
          <Link className="text-link" to="/settings?tab=market">
            Market data settings <ArrowUpRight size={12} />
          </Link>
        </div>
        {data.unpriced.length > 0 && (
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Unpriced asset</th>
                  <th>Quantity</th>
                  <th>Reason · excluded from total</th>
                </tr>
              </thead>
              <tbody>
                {data.unpriced.map((asset) => (
                  <tr key={asset.asset}>
                    <td>
                      <strong>{asset.asset}</strong>
                    </td>
                    <td className="monetary">{number(asset.quantity, 8)}</td>
                    <td>{asset.reason}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>
      <AccountBalances scope={scope} />
    </>
  );
}

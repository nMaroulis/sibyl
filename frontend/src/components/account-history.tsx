import { useEffect, useState } from 'react';
import type { FormEvent } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import {
  ArrowUpRight,
  ChartNoAxesCombined,
  ArrowDownUp,
  ChevronLeft,
  ChevronRight,
  Download,
  ListOrdered,
  Pause,
  RefreshCw,
} from 'lucide-react';
import { exportCSV, number, post, refresh, shortDate } from '../lib/api';
import { useResource } from '../lib/hooks';
import type { Connection } from '../lib/types';
import { ExchangeMark } from './exchange-mark';
import { Badge, Empty, ErrorState, Loading, Panel, PanelTitle, useToast } from './ui';
import { AccountPerformance } from './account-performance';
import { FundingHistory } from './funding-history';
import { SectionTabs, SectionPanel } from './section-tabs';

const historyViews = [
  { id: 'fills', label: 'Fills & imports', icon: ListOrdered },
  { id: 'performance', label: 'Performance', icon: ChartNoAxesCombined },
  { id: 'funding', label: 'Funding', icon: ArrowDownUp },
];

type SyncAccount = Connection & {
  environment: string;
  history_import: string | null;
};
type SyncJob = {
  account_id: string;
  account: string;
  exchange: string;
  environment: string;
  symbol: string;
  status: string;
  record_count: number;
  pages: number;
  inserted: number;
  updated: number;
  last_success_at: string | null;
  caught_up_at: string | null;
  error: string | null;
  retry_at?: string | null;
};
type SyncStatus = { accounts: SyncAccount[]; jobs: SyncJob[]; scope: string };
type Fill = {
  id: string;
  trade_id: string;
  order_id: string | null;
  account_id: string;
  account: string;
  exchange: string;
  environment: string;
  symbol: string;
  side: string;
  created_at: string;
  quantity: number;
  price: number;
  quote: string;
  notional: number | null;
  fees: { currency: string | null; cost: number | null }[];
  fees_known: boolean;
};
type Ledger = {
  items: Fill[];
  total: number;
  has_more: boolean;
  fee_totals: Record<string, number>;
  missing_fee_count: number;
  note: string;
};
const activeStatuses = ['queued', 'running', 'retrying'];
const statusLabel: Record<string, string> = {
  queued: 'Queued',
  running: 'Importing',
  retrying: 'Waiting to retry',
  caught_up: 'Caught up',
  paused: 'Paused',
  error: 'Needs attention',
  disconnected: 'Disconnected',
};
const feeText = (fill: Fill) =>
  fill.fees.length
    ? fill.fees
        .map(
          (fee) =>
            `${fee.cost == null ? '—' : number(fee.cost, 8)} ${fee.currency ?? '(currency unavailable)'}`,
        )
        .join(' · ')
    : 'Unavailable';

/** Queue exact-market reads; credentials and provider cursors never enter this form. */
function ImportMarket({ account, done }: { account: SyncAccount; done: () => void }) {
  const markets = useResource<{ symbols: string[] }>(
    `/connections/${account.id}/markets`,
    0,
    account.active,
  );
  const [symbol, setSymbol] = useState('');
  const [busy, setBusy] = useState(false);
  const toast = useToast();
  useEffect(() => {
    if (markets.data) {
      const available = markets.data.symbols;
      setSymbol(
        (current) =>
          current ||
          (available.includes('BTC/USDT')
            ? 'BTC/USDT'
            : available.includes('BTC/USD')
              ? 'BTC/USD'
              : (available[0] ?? '')),
      );
    }
  }, [markets.data]);
  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true);
    try {
      await post(`/connections/${account.id}/sync`, { symbols: [symbol] });
      done();
      refresh();
      toast('History import queued. Progress is saved as each page arrives.');
    } catch (error) {
      toast((error as Error).message, true);
    } finally {
      setBusy(false);
    }
  };
  if (!account.active)
    return (
      <p className="inline-alert">
        Activate this saved account in <Link to="/settings?tab=exchanges">Settings</Link> to import
        more history. Retained records remain available.
      </p>
    );
  return markets.error ? (
    <ErrorState message={markets.error} retry={markets.retry} />
  ) : (
    <form className="workspace-controls account-import-form" onSubmit={submit}>
      <label>
        Spot market
        <input
          list="account-import-markets"
          value={symbol}
          onChange={(event) => setSymbol(event.target.value.toUpperCase())}
          placeholder={markets.loading ? 'Loading markets…' : 'BTC/USDT'}
          maxLength={25}
          disabled={markets.loading || busy}
          required
        />
        <datalist id="account-import-markets">
          {markets.data?.symbols.map((pair) => (
            <option value={pair} key={pair} />
          ))}
        </datalist>
      </label>
      <button
        className="button primary"
        type="submit"
        disabled={busy || markets.loading || !markets.data?.symbols.includes(symbol)}
      >
        <RefreshCw size={14} className={busy ? 'spin' : ''} />
        {busy ? 'Queuing…' : 'Sync market history'}
      </button>
      <p className="footnote">
        Imports run in the background. Sync again later to collect new fills.
      </p>
    </form>
  );
}

/** Persistent account fills, explicit coverage, and user-controlled import progress. */
export function AccountHistory({ active = true }: { active?: boolean }) {
  const sync = useResource<SyncStatus>('/account-sync', active ? 3000 : 0);
  const [params, setParams] = useSearchParams();
  const accountId = params.get('account') ?? '';
  const symbol = params.get('market') ?? '';
  const side = params.get('side') ?? '';
  const environment = params.get('environment') ?? '';
  const performance = params.get('history_view') === 'performance';
  const funding = params.get('history_view') === 'funding';
  const historyView = funding ? 'funding' : performance ? 'performance' : 'fills';
  const retainedMarkets = useResource<{
    symbols: string[];
    accounts?: { id: string; label: string }[];
  }>('/account-ledger/performance/markets', 0, active);
  const offset = Math.min(1_000_000, Math.max(0, Number(params.get('offset')) || 0));
  const change = (values: Record<string, string>, reset = true) => {
    setParams((old) => {
      const next = new URLSearchParams(old);
      if (reset) next.delete('offset');
      for (const [key, value] of Object.entries(values))
        value ? next.set(key, value) : next.delete(key);
      return next;
    });
  };
  const query = new URLSearchParams({
    account_id: accountId,
    side,
    environment,
    offset: String(offset),
    limit: '50',
  });
  if (symbol) query.set('symbol', symbol);
  const ledger = useResource<Ledger>(
    `/account-ledger/fills?${query}`,
    active && !performance && !funding ? 5000 : 0,
    active && !performance && !funding,
  );
  const [busy, setBusy] = useState('');
  const toast = useToast();
  const action = async (item: SyncJob, pause: boolean) => {
    const key = `${item.account_id}:${item.symbol}`;
    setBusy(key);
    try {
      await post(
        pause
          ? `/connections/${item.account_id}/sync/pause?symbol=${encodeURIComponent(item.symbol)}`
          : `/connections/${item.account_id}/sync`,
        pause ? {} : { symbols: [item.symbol] },
      );
      sync.retry();
      ledger.retry();
      toast(
        pause ? 'Import paused. Retained fills and progress are saved.' : 'History import queued.',
      );
    } catch (error) {
      toast((error as Error).message, true);
    } finally {
      setBusy('');
    }
  };
  const accounts = sync.data?.accounts ?? [];
  const selected = accounts.find((item) => item.id === accountId);
  const jobs = sync.data?.jobs.filter((item) => !accountId || item.account_id === accountId) ?? [];
  const retired = [
    ...new Map(
      [
        ...(sync.data?.jobs ?? []),
        ...(retainedMarkets.data?.accounts ?? []).map((item) => ({
          account_id: item.id,
          account: item.label,
        })),
      ]
        .filter((item) => !accounts.some((account) => account.id === item.account_id))
        .map((item) => [item.account_id, item]),
    ).values(),
  ];
  const symbols = [
    ...new Set([
      ...(sync.data?.jobs.map((item) => item.symbol) ?? []),
      ...(retainedMarkets.data?.symbols ?? []),
    ]),
  ].sort();
  const accountChooser = (
    <label>
      Account
      <select value={accountId} onChange={(event) => change({ account: event.target.value })}>
        <option value="">All retained accounts</option>
        {accounts.map((account) => (
          <option key={account.id} value={account.id}>
            {account.label} · {account.environment}
          </option>
        ))}
        {retired.map((item) => (
          <option key={item.account_id} value={item.account_id}>
            {item.account} · disconnected
          </option>
        ))}
        {accountId &&
          !accounts.some((item) => item.id === accountId) &&
          !retired.some((item) => item.account_id === accountId) && (
            <option value={accountId}>Selected retained account</option>
          )}
      </select>
    </label>
  );
  const rows = ledger.data?.items ?? [];
  return (
    <>
      <SectionTabs
        id="account-history"
        label="Account history views"
        items={historyViews}
        value={historyView}
        onChange={(value) => change({ history_view: value })}
        compact
      />
      <SectionPanel id="account-history" value={historyView}>
        {funding ? (
          <FundingHistory active={active} />
        ) : (
          <>
            {!performance && (
              <Panel className="full-panel">
                <PanelTitle
                  title="Import account history"
                  subtitle="Retained spot fills, with their original order IDs and fees"
                  action={
                    <Link className="text-link" to="/settings?tab=exchanges">
                      Manage accounts <ArrowUpRight size={13} />
                    </Link>
                  }
                />
                {sync.error ? (
                  <ErrorState message={sync.error} retry={sync.retry} />
                ) : sync.loading ? (
                  <Loading />
                ) : (
                  <>
                    <div className="workspace-controls">
                      {accountChooser}
                      {selected && (
                        <Badge tone={selected.environment === 'production' ? 'blue' : 'purple'}>
                          {selected.environment === 'demo'
                            ? 'Demo funds'
                            : selected.environment === 'test'
                              ? 'Test funds'
                              : 'Production account · read only'}
                        </Badge>
                      )}
                    </div>
                    {!performance &&
                      (selected?.history_import ? (
                        <ImportMarket key={selected.id} account={selected} done={sync.retry} />
                      ) : (
                        <p className="footnote padded">
                          {selected
                            ? 'History import is coming soon for this exchange. Balance and recent-fill reads remain available.'
                            : accountId
                              ? 'This account is disconnected. Its retained history remains readable.'
                              : 'Choose a connected account to import an exact spot market.'}
                        </p>
                      ))}
                    {!performance && (
                      <p className="footnote padded">
                        {sync.data?.scope} Demo, test and production records stay labeled. Importing
                        never places orders.
                      </p>
                    )}
                  </>
                )}
              </Panel>
            )}
            {!performance && jobs.length > 0 && (
              <Panel className="full-panel">
                <PanelTitle
                  title="Import progress"
                  subtitle="Checkpoints survive restarts. Pause stops after any page already in progress."
                />
                <div className="account-import-jobs">
                  {jobs.map((item) => (
                    <div className="account-import-job" key={`${item.account_id}:${item.symbol}`}>
                      <span className="provider-logo small-logo">
                        <ExchangeMark exchange={item.exchange} />
                      </span>
                      <div className="account-import-description">
                        <strong>
                          {item.symbol}{' '}
                          <small>
                            {item.account} · {item.environment}
                          </small>
                        </strong>
                        <p>
                          {item.record_count} retained fills · {item.pages} pages checked ·{' '}
                          {item.updated} updates
                        </p>
                        {item.last_success_at && (
                          <p>
                            Last successful page {shortDate(item.last_success_at)}
                            {item.caught_up_at
                              ? ` · Last pass completed ${shortDate(item.caught_up_at)}`
                              : ''}
                          </p>
                        )}
                        {item.error && (
                          <p className="negative">
                            {item.error}
                            {item.status === 'retrying' && item.retry_at
                              ? ` Retry after ${new Date(item.retry_at).toLocaleTimeString()}.`
                              : ''}
                          </p>
                        )}
                      </div>
                      <Badge
                        tone={
                          item.status === 'error'
                            ? 'rose'
                            : item.status === 'caught_up'
                              ? 'lime'
                              : 'neutral'
                        }
                      >
                        {statusLabel[item.status] ?? item.status}
                      </Badge>
                      {accounts.some((account) => account.id === item.account_id) && (
                        <button
                          className="button secondary tiny"
                          disabled={
                            !!busy ||
                            (!activeStatuses.includes(item.status) &&
                              !accounts.find((account) => account.id === item.account_id)?.active)
                          }
                          onClick={() => action(item, activeStatuses.includes(item.status))}
                        >
                          {activeStatuses.includes(item.status) ? (
                            <Pause size={13} />
                          ) : (
                            <RefreshCw size={13} />
                          )}
                          {busy === `${item.account_id}:${item.symbol}`
                            ? 'Updating…'
                            : activeStatuses.includes(item.status)
                              ? 'Pause'
                              : item.status === 'caught_up'
                                ? 'Sync again'
                                : 'Resume'}
                        </button>
                      )}
                    </div>
                  ))}
                </div>
              </Panel>
            )}
            <Panel className="full-panel">
              <PanelTitle
                title={performance ? 'Report filters' : 'Account fill ledger'}
                subtitle={
                  performance
                    ? 'All retained fills within this selection contribute to the report'
                    : 'Actual reported fills; exchange previews remain in Executions'
                }
                action={
                  performance ? (
                    <Link className="text-link" to="/settings?tab=exchanges">
                      Manage accounts <ArrowUpRight size={13} />
                    </Link>
                  ) : (
                    <button
                      className="button secondary tiny"
                      disabled={!rows.length}
                      onClick={() =>
                        exportCSV('sibyl-account-fills-page.csv', [
                          [
                            'Time',
                            'Account',
                            'Exchange',
                            'Environment',
                            'Market',
                            'Side',
                            'Quantity',
                            'Price',
                            'Notional',
                            'Quote',
                            'Fees',
                            'Fees complete',
                            'Trade ID',
                            'Order ID',
                          ],
                          ...rows.map((item) => [
                            item.created_at,
                            item.account,
                            item.exchange,
                            item.environment,
                            item.symbol,
                            item.side,
                            item.quantity,
                            item.price,
                            item.notional ?? '',
                            item.quote,
                            feeText(item),
                            item.fees_known ? 'yes' : 'no',
                            item.trade_id,
                            item.order_id ?? '',
                          ]),
                        ])
                      }
                    >
                      <Download size={13} /> Export this page
                    </button>
                  )
                }
              />
              {performance && sync.error && <ErrorState message={sync.error} retry={sync.retry} />}
              <div className="workspace-controls">
                {performance && accountChooser}
                <label>
                  Market
                  <select
                    value={symbol}
                    onChange={(event) => change({ market: event.target.value })}
                  >
                    <option value="">All retained markets</option>
                    {symbols.map((pair) => (
                      <option key={pair}>{pair}</option>
                    ))}
                  </select>
                </label>
                {!performance && (
                  <label>
                    Side
                    <select value={side} onChange={(event) => change({ side: event.target.value })}>
                      <option value="">All sides</option>
                      <option value="buy">Buy</option>
                      <option value="sell">Sell</option>
                    </select>
                  </label>
                )}
                <label>
                  Environment
                  <select
                    value={environment}
                    onChange={(event) => change({ environment: event.target.value })}
                  >
                    <option value="">All environments</option>
                    <option value="demo">Demo funds</option>
                    <option value="test">Test funds</option>
                    <option value="production">Production</option>
                  </select>
                </label>
                {!performance && (
                  <button
                    className="button secondary tiny"
                    onClick={() => {
                      ledger.retry();
                      sync.retry();
                    }}
                  >
                    <RefreshCw size={13} /> Refresh ledger
                  </button>
                )}
              </div>
              {!performance && (
                <>
                  {ledger.error ? (
                    <ErrorState message={ledger.error} retry={ledger.retry} />
                  ) : ledger.loading ? (
                    <Loading />
                  ) : (
                    <>
                      <div className="account-ledger-summary">
                        <strong>{ledger.data?.total ?? 0} matching fills</strong>
                        <span>
                          Reported fees:{' '}
                          {Object.entries(ledger.data?.fee_totals ?? {})
                            .map(([currency, value]) => `${number(value, 8)} ${currency}`)
                            .join(' · ') || 'Unavailable'}
                        </span>
                        {!!ledger.data?.missing_fee_count && (
                          <span>
                            {ledger.data.missing_fee_count} fills with incomplete fee data
                          </span>
                        )}
                      </div>
                      {rows.length ? (
                        <div className="table-scroll">
                          <table>
                            <thead>
                              <tr>
                                <th>Executed</th>
                                <th>Account</th>
                                <th>Market / side</th>
                                <th>Quantity</th>
                                <th>Price</th>
                                <th>Notional</th>
                                <th>Fees / rebates</th>
                                <th>Provider IDs</th>
                              </tr>
                            </thead>
                            <tbody>
                              {rows.map((item) => (
                                <tr key={item.id}>
                                  <td>{new Date(item.created_at).toLocaleString()}</td>
                                  <td>
                                    {item.account}
                                    <small className="table-subline">
                                      {item.exchange} · {item.environment}
                                    </small>
                                  </td>
                                  <td>
                                    {item.symbol}
                                    <small className="table-subline">{item.side}</small>
                                  </td>
                                  <td>{number(item.quantity, 8)}</td>
                                  <td>
                                    {number(item.price, 8)} {item.quote}
                                  </td>
                                  <td>
                                    {item.notional == null
                                      ? 'Unavailable'
                                      : `${number(item.notional, 8)} ${item.quote}`}
                                  </td>
                                  <td>
                                    {feeText(item)}
                                    {!item.fees_known && (
                                      <small className="table-subline">Incomplete fee data</small>
                                    )}
                                  </td>
                                  <td className="account-ledger-ids">
                                    Fill {item.trade_id}
                                    <small className="table-subline">
                                      {item.order_id
                                        ? `Order ${item.order_id}`
                                        : 'Order ID unavailable'}
                                    </small>
                                  </td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                      ) : (
                        <Empty title="No retained fills in this selection">
                          Choose an account and sync a spot market. Demo imports use your existing
                          manual paper fills.
                        </Empty>
                      )}
                      <nav className="news-pagination" aria-label="Account fill pages">
                        <button
                          className="button secondary tiny"
                          disabled={offset === 0}
                          onClick={() =>
                            change({ offset: String(Math.max(0, offset - 50)) }, false)
                          }
                        >
                          <ChevronLeft size={14} /> Previous
                        </button>
                        <span>Page {Math.floor(offset / 50) + 1}</span>
                        <button
                          className="button secondary tiny"
                          disabled={!ledger.data?.has_more}
                          onClick={() => change({ offset: String(offset + 50) }, false)}
                        >
                          Next <ChevronRight size={14} />
                        </button>
                      </nav>
                    </>
                  )}
                  <p className="footnote padded">
                    {ledger.data?.note} Fee totals cover the full filtered selection, in each native
                    currency. Negative fees are rebates.
                  </p>
                </>
              )}
            </Panel>
            {performance && (
              <AccountPerformance
                accountId={accountId}
                symbol={symbol}
                environment={environment}
                accounts={accounts}
                active={active}
              />
            )}
          </>
        )}
      </SectionPanel>
    </>
  );
}

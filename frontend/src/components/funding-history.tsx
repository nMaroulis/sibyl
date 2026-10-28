import { useState } from 'react';
import type { FormEvent } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import {
  ArrowUpRight,
  ChevronLeft,
  ChevronRight,
  Download,
  Link2,
  Pause,
  RefreshCw,
  X,
} from 'lucide-react';
import { exportCSV, number, post, refresh } from '../lib/api';
import { useResource } from '../lib/hooks';
import type { Connection } from '../lib/types';
import { Badge, Empty, ErrorState, Loading, Panel, PanelTitle, useToast } from './ui';
import { ExchangeMark } from './exchange-mark';
import { AgentButton } from './agents';
import type { AgentContext } from '../lib/types';
import { TransferReconciliation } from './transfer-reconciliation';
import { FundingEffectCell } from './funding-effect';
import type { FundingEffect } from './funding-effect';

type Stream = 'deposit' | 'withdrawal' | 'transfer';
type FundingAccount = Connection & {
  environment: string;
  funding_streams: Stream[];
  funding_note: string;
};
type FundingJob = {
  account_id: string;
  account: string;
  exchange: string;
  environment: string;
  stream: Stream;
  start_ms: number;
  end_ms: number;
  status: string;
  record_count: number;
  pages: number;
  updated: number;
  error: string | null;
  retry_at?: string | null;
  caught_up_at?: string | null;
};
type Sync = { accounts: FundingAccount[]; jobs: FundingJob[]; scope: string; demo_note: string };
type Movement = {
  id: string;
  native_id: string;
  reference: string | null;
  account_id: string;
  account: string;
  exchange: string;
  environment: string;
  asset: string;
  kind: Stream;
  direction: string;
  quantity: number;
  created_at: string;
  posted_ms?: number | null;
  status: string;
  internal: boolean;
  amount_basis: string;
  fee: { currency: string | null; cost: number | null };
  fee_known: boolean;
  balance_effect?: FundingEffect;
  first_seen_at?: string;
  last_seen_at?: string;
  reconciliation?: { status: string; link_id: string; counterpart_account: string } | null;
};
type Funding = {
  example?: boolean;
  items: Movement[];
  total: number;
  has_more: boolean;
  note: string;
  summaries: {
    account_id: string;
    account: string;
    environment: string;
    asset: string;
    kind: Stream;
    direction: string;
    quantity: number;
    count: number;
  }[];
  fees: { account_id: string; environment: string; currency: string; quantity: number }[];
};
const names: Record<Stream, string> = {
  deposit: 'Deposits',
  withdrawal: 'Withdrawals',
  transfer: 'Transfers',
};
const running = ['queued', 'running', 'retrying'];
const localDate = (time: number) => {
  const date = new Date(time);
  return new Date(time - date.getTimezoneOffset() * 60000).toISOString().slice(0, 19);
};
const time = (date: string | number) => new Date(date).toLocaleString();
const fee = (row: Movement) =>
  row.fee_known ? `${number(row.fee.cost!, 8)} ${row.fee.currency}` : 'Unavailable';

/** Retained funding observations; imports read history and never initiate a money movement. */
export function FundingHistory({ active }: { active: boolean }) {
  const [params, setParams] = useSearchParams();
  const accountId = params.get('account') || '';
  const asset = params.get('fund_asset') || '';
  const kind = params.get('fund_kind') || '';
  const status = params.get('fund_status') || '';
  const environment = params.get('environment') || '';
  const transferMode = params.get('fund_view') === 'transfers';
  const offset = Math.min(1_000_000, Math.max(0, Number(params.get('fund_offset')) || 0));
  const change = (values: Record<string, string>, reset = true) =>
    setParams((old) => {
      const next = new URLSearchParams(old);
      if (reset) next.delete('fund_offset');
      Object.entries(values).forEach(([key, value]) =>
        value ? next.set(key, value) : next.delete(key),
      );
      return next;
    });
  const sync = useResource<Sync>('/funding-sync', active ? 3000 : 0, active);
  const [example, setExample] = useState(false);
  const query = new URLSearchParams({
    account_id: accountId,
    asset,
    kind,
    status,
    environment,
    offset: String(offset),
    limit: '50',
  });
  const data = useResource<Funding>(
    example ? '/account-ledger/funding/example' : `/account-ledger/funding?${query}`,
    active && !example && !transferMode ? 5000 : 0,
    active && !transferMode,
  );
  const [busy, setBusy] = useState('');
  const toast = useToast();
  const accounts = sync.data?.accounts ?? [];
  const selected = accounts.find((item) => item.id === accountId);
  const jobs = (sync.data?.jobs ?? []).filter(
    (item) => !accountId || item.account_id === accountId,
  );
  const retired = [
    ...new Map(
      (sync.data?.jobs ?? [])
        .filter((item) => !accounts.some((account) => account.id === item.account_id))
        .map((item) => [item.account_id, item]),
    ).values(),
  ];
  const control = async (job: FundingJob) => {
    const pause = running.includes(job.status);
    setBusy(`${job.account_id}:${job.stream}`);
    try {
      await post(
        pause
          ? `/connections/${job.account_id}/funding-sync/pause?stream=${job.stream}`
          : `/connections/${job.account_id}/funding-sync`,
        pause
          ? undefined
          : {
              streams: [job.stream],
              start: new Date(job.start_ms).toISOString(),
              end: new Date(job.end_ms).toISOString(),
            },
      );
      refresh();
      toast(
        pause
          ? 'Funding import paused.'
          : 'Saved range queued. Completed ranges are rescanned for corrections.',
      );
    } catch (reason) {
      toast((reason as Error).message, true);
    } finally {
      setBusy('');
    }
  };
  if (transferMode)
    return (
      <TransferReconciliation
        active={active}
        accounts={[
          ...accounts.map((item) => ({ id: item.id, label: item.label })),
          ...retired.map((item) => ({ id: item.account_id, label: `${item.account} · retained` })),
        ]}
      />
    );
  return (
    <>
      <Panel className="full-panel">
        <PanelTitle
          title="Funding history"
          subtitle="Read-only deposits, withdrawals and transfers; separate from trade fills"
          action={
            <div className="performance-actions">
              <button
                className="button secondary tiny"
                onClick={() => change({ fund_view: 'transfers' })}
              >
                <Link2 size={13} /> Reconcile transfers
              </button>
              <AgentButton
                module="accountant"
                compact
                context={{
                  funding_view: true,
                  funding_account_id: accountId,
                  funding_asset: asset,
                  funding_kind: kind as AgentContext['funding_kind'],
                  funding_status: status as AgentContext['funding_status'],
                  funding_environment: environment as AgentContext['funding_environment'],
                  funding_example: example,
                }}
              >
                Ask about funding
              </AgentButton>
              <button className="button secondary tiny" onClick={() => setExample(!example)}>
                {example && <X size={13} />}
                {example ? 'Close example' : 'View example'}
              </button>
              <Link className="text-link" to="/settings?tab=exchanges">
                Manage accounts <ArrowUpRight size={13} />
              </Link>
            </div>
          }
        />
        {example ? (
          <div className="performance-example">
            <Badge tone="purple">Example movements</Badge>
            <span>
              Sample records only. Filters do not apply, and no account, balance or ledger data is
              changed.
            </span>
          </div>
        ) : (
          <>
            <div className="workspace-controls">
              <label>
                Account
                <select
                  value={accountId}
                  onChange={(event) => change({ account: event.target.value })}
                >
                  <option value="">All retained accounts</option>
                  {accounts.map((item) => (
                    <option key={item.id} value={item.id}>
                      {item.label} · {item.environment}
                      {!item.active ? ' · inactive' : ''}
                    </option>
                  ))}
                  {retired.map((item) => (
                    <option key={item.account_id} value={item.account_id}>
                      {item.account} · disconnected
                    </option>
                  ))}
                </select>
              </label>
              {selected && (
                <Badge tone={selected.environment === 'production' ? 'blue' : 'purple'}>
                  {selected.environment === 'demo'
                    ? 'Demo preview'
                    : selected.environment === 'test'
                      ? 'Test funds'
                      : 'Production · read only'}
                </Badge>
              )}
            </div>
            {sync.error ? (
              <ErrorState message={sync.error} retry={sync.retry} />
            ) : sync.loading ? (
              <Loading />
            ) : selected ? (
              !selected.active ? (
                <p className="footnote padded">
                  Activate this account in Settings before importing. Retained records remain
                  readable.
                </p>
              ) : !selected.funding_streams.length ? (
                <p className="footnote padded">{selected.funding_note}</p>
              ) : (
                <>
                  <FundingImport key={selected.id} account={selected} done={refresh} />
                  {selected.funding_note && (
                    <p className="footnote padded">{selected.funding_note}</p>
                  )}
                  {selected.exchange === 'demo' && (
                    <p className="footnote padded">{sync.data?.demo_note}</p>
                  )}
                </>
              )
            ) : (
              <p className="footnote padded">
                Choose an active account to import an explicit range. Binance supports crypto
                deposits/withdrawals; Kraken supports deposit, withdrawal and transfer ledger
                entries; Bybit supports master-UID on-chain withdrawals. Other providers are coming
                soon.
              </p>
            )}
          </>
        )}
      </Panel>
      {!example && !!jobs.length && (
        <Panel className="full-panel">
          <PanelTitle
            title="Funding import progress"
            subtitle="One range per stream. Pause before changing an active range; rescan to refresh older statuses."
          />
          <div className="account-import-jobs">
            {jobs.map((item) => (
              <div className="account-import-job" key={`${item.account_id}:${item.stream}`}>
                <span className="provider-logo small-logo">
                  <ExchangeMark exchange={item.exchange} />
                </span>
                <div className="account-import-description">
                  <strong>
                    {names[item.stream]}{' '}
                    <small>
                      {item.account} · {item.environment}
                    </small>
                  </strong>
                  <p>
                    {time(item.start_ms)} → {time(item.end_ms)}
                  </p>
                  <p>
                    {item.pages} pages in this pass · {item.record_count} retained across all ranges
                    · {item.updated} updates
                  </p>
                  {item.error && (
                    <p className="negative">
                      {item.error}
                      {item.retry_at ? ` Retry after ${time(item.retry_at)}.` : ''}
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
                  {item.status === 'caught_up' ? 'Range fetched' : item.status.replaceAll('_', ' ')}
                </Badge>
                {accounts.some((account) => account.id === item.account_id) && (
                  <button
                    className="button secondary tiny"
                    disabled={
                      !!busy ||
                      (!running.includes(item.status) &&
                        !accounts.find((account) => account.id === item.account_id)?.active)
                    }
                    onClick={() => control(item)}
                  >
                    {running.includes(item.status) ? <Pause size={13} /> : <RefreshCw size={13} />}
                    {busy === `${item.account_id}:${item.stream}`
                      ? 'Updating…'
                      : running.includes(item.status)
                        ? 'Pause'
                        : item.status === 'caught_up'
                          ? 'Rescan range'
                          : 'Resume'}
                  </button>
                )}
              </div>
            ))}
          </div>
        </Panel>
      )}
      <Panel className="full-panel funding-records">
        <PanelTitle
          title={example ? 'Example funding ledger' : 'Retained funding ledger'}
          subtitle="Native amounts and fees retain their original units"
          action={
            <div className="performance-actions">
              <button className="button secondary tiny" onClick={data.retry}>
                <RefreshCw size={13} /> Refresh
              </button>
              <button
                className="button secondary tiny"
                disabled={!data.data?.items.length}
                onClick={() =>
                  exportCSV(example ? 'sibyl-funding-example.csv' : 'sibyl-funding-page.csv', [
                    [
                      'Time',
                      'Balance posting time',
                      'Account',
                      'Exchange',
                      'Environment',
                      'Kind',
                      'Direction',
                      'Asset',
                      'Reported quantity',
                      'Status',
                      'Fee currency',
                      'Fee amount',
                      'Fee known',
                      'Internal at venue',
                      'Amount basis',
                      'Native ID',
                      'Reference',
                      'Wallet balance change',
                      'Balance effect provenance',
                      'Balance effect rule',
                      'Wallet scope',
                      'Review status',
                      'Scope',
                    ],
                    ...(data.data?.items ?? []).map((row) => [
                      row.created_at,
                      row.posted_ms ? new Date(row.posted_ms).toISOString() : '',
                      row.account,
                      row.exchange,
                      row.environment,
                      row.kind,
                      row.direction,
                      row.asset,
                      row.quantity,
                      row.status,
                      row.fee.currency ?? '',
                      row.fee.cost ?? '',
                      row.fee_known ? 'yes' : 'no',
                      row.internal ? 'yes' : 'no',
                      row.amount_basis,
                      row.native_id,
                      row.reference ?? '',
                      row.balance_effect?.quantity ?? '',
                      row.balance_effect?.provenance ?? '',
                      row.balance_effect?.rule ?? '',
                      row.balance_effect?.wallet_scope ?? 'unknown',
                      row.balance_effect?.review_status ?? '',
                      data.data!.note,
                    ]),
                  ])
                }
              >
                <Download size={13} /> Export this page
              </button>
            </div>
          }
        />
        {!example && (
          <div className="workspace-controls">
            <label>
              Asset
              <input
                aria-label="Funding asset"
                value={asset}
                maxLength={20}
                placeholder="All assets"
                onChange={(event) =>
                  change({
                    fund_asset: event.target.value.toUpperCase().replace(/[^A-Z0-9.]/g, ''),
                  })
                }
              />
            </label>
            <label>
              Movement
              <select value={kind} onChange={(event) => change({ fund_kind: event.target.value })}>
                <option value="">All movements</option>
                {Object.entries(names).map(([key, label]) => (
                  <option key={key} value={key}>
                    {label}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Status
              <select
                value={status}
                onChange={(event) => change({ fund_status: event.target.value })}
              >
                <option value="">All statuses</option>
                {['completed', 'pending', 'restricted', 'failed', 'cancelled', 'unknown'].map(
                  (value) => (
                    <option key={value}>{value}</option>
                  ),
                )}
              </select>
            </label>
            <label>
              Environment
              <select
                value={environment}
                onChange={(event) => change({ environment: event.target.value })}
              >
                <option value="">All environments</option>
                <option value="production">Production</option>
                <option value="test">Test funds</option>
                <option value="demo">Demo preview</option>
              </select>
            </label>
          </div>
        )}
        {data.error ? (
          <ErrorState message={data.error} retry={data.retry} />
        ) : data.loading ? (
          <Loading />
        ) : (
          <>
            {!!data.data?.summaries.length && (
              <div className="funding-summary">
                <h3>Completed reported movements</h3>
                <p>
                  Each account, environment, asset and direction stays separate. These are
                  quantities, not net cash flows or profit.
                </p>
                <div className="funding-summary-grid">
                  {data.data.summaries.map((row) => (
                    <div
                      key={`${row.account_id}:${row.environment}:${row.asset}:${row.kind}:${row.direction}`}
                    >
                      <small>
                        {row.account} · {row.environment}
                      </small>
                      <strong>
                        {number(row.quantity, 8)} {row.asset}
                      </strong>
                      <span>
                        {names[row.kind]} · {row.direction === 'in' ? 'received' : 'sent'} ·{' '}
                        {row.count} {row.count === 1 ? 'record' : 'records'}
                      </span>
                    </div>
                  ))}
                </div>
                {!!data.data.fees.length && (
                  <p>
                    Reported completed fees / rebates:{' '}
                    {data.data.fees
                      .map(
                        (row) =>
                          `${row.account_id === 'example' ? 'Example' : accounts.find((account) => account.id === row.account_id)?.label || 'Retained account'} / ${row.environment}: ${number(row.quantity, 8)} ${row.currency}`,
                      )
                      .join(' · ')}
                    . Missing fees remain unavailable.
                  </p>
                )}
              </div>
            )}
            {data.data?.items.length ? (
              <>
                <div className="table-scroll">
                  <table>
                    <thead>
                      <tr>
                        <th>Time / account</th>
                        <th>Movement</th>
                        <th>Reported amount</th>
                        <th>Status</th>
                        <th>Reported fee</th>
                        <th>Wallet balance effect</th>
                        <th>Source record</th>
                      </tr>
                    </thead>
                    <tbody>
                      {data.data.items.map((row) => (
                        <tr key={row.id}>
                          <td>
                            <strong>{time(row.created_at)}</strong>
                            <small>
                              {row.account} ·{' '}
                              {row.exchange === 'demo'
                                ? 'Demo'
                                : `${row.exchange} · ${row.environment}`}
                            </small>
                          </td>
                          <td>
                            {names[row.kind]}
                            <small>
                              {row.direction === 'in' ? 'Received' : 'Sent'}
                              {row.internal ? ' · internal at venue' : ''}
                            </small>
                            {row.reconciliation && (
                              <small>
                                <button
                                  className="text-link"
                                  onClick={() =>
                                    change({
                                      fund_view: 'transfers',
                                      fund_link: row.reconciliation!.link_id,
                                    })
                                  }
                                >
                                  {row.reconciliation.status === 'needs_review'
                                    ? 'Transfer link needs review'
                                    : 'User-confirmed transfer'}{' '}
                                  <ArrowUpRight size={10} />
                                </button>
                              </small>
                            )}
                            {!row.reconciliation && row.status === 'completed' && !example && (
                              <small>Transfer classification unreviewed</small>
                            )}
                          </td>
                          <td>
                            <strong>
                              {number(row.quantity, 8)} {row.asset}
                            </strong>
                          </td>
                          <td>
                            <Badge
                              tone={
                                row.status === 'completed'
                                  ? 'lime'
                                  : row.status === 'failed'
                                    ? 'rose'
                                    : 'neutral'
                              }
                            >
                              {row.status}
                            </Badge>
                          </td>
                          <td>{fee(row)}</td>
                          <td>
                            <FundingEffectCell
                              id={row.id}
                              asset={row.asset}
                              effect={row.balance_effect}
                              example={example}
                            />
                          </td>
                          <td>
                            <details>
                              <summary>
                                {row.native_id.length > 18
                                  ? `${row.native_id.slice(0, 15)}…`
                                  : row.native_id}
                              </summary>
                              <p>ID: {row.native_id}</p>
                              {row.reference && <p>Reference: {row.reference}</p>}
                              <p>Amount basis: {row.amount_basis.replaceAll('_', ' ')}</p>
                              {row.last_seen_at && <p>Last observed: {time(row.last_seen_at)}</p>}
                              <p>
                                Balance posting time:{' '}
                                {row.posted_ms
                                  ? time(row.posted_ms)
                                  : 'Unavailable; Balance checks cannot place this movement in time.'}
                              </p>
                              <p>
                                Balance effects keep provider rules and local reviews distinct.
                                Internal-at-venue does not establish that both accounts belong to
                                you.
                              </p>
                            </details>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <p className="footnote padded">
                  {data.data.total} matching retained records. Completed summaries cover the full
                  filtered selection; the table and CSV contain this page.
                </p>
              </>
            ) : (
              <Empty title="No retained funding records">
                Import a range for a supported account, or view the isolated example. Demo seed
                balances do not create deposit transactions.
              </Empty>
            )}
            {!example && (
              <nav className="news-pagination" aria-label="Funding pages">
                <button
                  className="button secondary tiny"
                  disabled={!offset}
                  onClick={() => change({ fund_offset: String(Math.max(0, offset - 50)) }, false)}
                >
                  <ChevronLeft size={14} /> Previous
                </button>
                <span>Page {Math.floor(offset / 50) + 1}</span>
                <button
                  className="button secondary tiny"
                  disabled={!data.data?.has_more}
                  onClick={() => change({ fund_offset: String(offset + 50) }, false)}
                >
                  Next <ChevronRight size={14} />
                </button>
              </nav>
            )}
          </>
        )}
        <p className="footnote padded">
          {data.data?.note || sync.data?.scope} A fetched range is not proof of complete account
          history. Revisit old ranges to capture late records and status changes.
        </p>
      </Panel>
    </>
  );
}

/** Freeze an explicit historical UTC range on submit; never start automatic account-wide scans. */
function FundingImport({ account, done }: { account: FundingAccount; done: () => void }) {
  const [start, setStart] = useState(() => localDate(Date.now() - 30 * 86400000));
  const [end, setEnd] = useState(() => localDate(Date.now() - 60000));
  const [streams, setStreams] = useState<Stream[]>(account.funding_streams);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError('');
    try {
      await post(`/connections/${account.id}/funding-sync`, {
        streams,
        start: new Date(start).toISOString(),
        end: new Date(end).toISOString(),
      });
      done();
    } catch (reason) {
      setError((reason as Error).message);
    } finally {
      setBusy(false);
    }
  };
  return (
    <form onSubmit={submit} className="funding-import-form">
      <div className="funding-streams" aria-label="Funding streams">
        {account.funding_streams.map((stream) => (
          <button
            type="button"
            className={streams.includes(stream) ? 'selected' : ''}
            aria-pressed={streams.includes(stream)}
            key={stream}
            disabled={busy}
            onClick={() =>
              setStreams((old) =>
                old.includes(stream) ? old.filter((item) => item !== stream) : [...old, stream],
              )
            }
          >
            {names[stream]}
          </button>
        ))}
      </div>
      <div className="workspace-controls">
        <label>
          From (local time)
          <input
            required
            type="datetime-local"
            step="1"
            value={start}
            onChange={(event) => setStart(event.target.value)}
            disabled={busy}
          />
        </label>
        <label>
          To (local time)
          <input
            required
            type="datetime-local"
            step="1"
            value={end}
            onChange={(event) => setEnd(event.target.value)}
            disabled={busy}
          />
        </label>
        <button className="button primary" disabled={busy || !streams.length}>
          {busy ? 'Queuing…' : 'Import range'}
        </button>
      </div>
      <p className="footnote padded">
        Choose a range shorter than 90 days. Import older ranges separately. This reads history and
        never deposits, withdraws or transfers funds.
      </p>
      {error && <ErrorState message={error} />}
    </form>
  );
}

import { useCallback, useEffect, useRef, useState } from 'react';
import type { FormEvent } from 'react';
import { Download, Pencil, Plus, RefreshCw, X } from 'lucide-react';
import { api, exportCSV, number, post, refresh } from '../lib/api';
import { useResource } from '../lib/hooks';
import type { Connection } from '../lib/types';
import { Badge, Empty, ErrorState, Loading, Modal, Panel, PanelTitle, useToast } from './ui';
import { ExchangeMark } from './exchange-mark';
import { ValueChart } from './charts';
import { AgentButton } from './agents';

type Opening = {
  account_id: string;
  symbol: string;
  quantity: string;
  total_cost: string | null;
  as_of: string;
  updated_at: string;
};
type Disposal = {
  id: string;
  trade_id: string;
  timestamp: string;
  quantity: number | null;
  known_quantity: number | null;
  unknown_quantity: number | null;
  matched_cost: number | null;
  matched_proceeds: number | null;
  pnl_before_other_fees: number | null;
};
type PerformanceRow = {
  account_id: string;
  account: string;
  exchange: string;
  environment: string;
  symbol: string;
  base: string;
  quote: string;
  active: boolean;
  first_fill_at?: string | null;
  fill_count: number;
  disposal_count: number;
  net_known: boolean;
  realized_before_other_fees: number | null;
  net_matched_realized: number | null;
  unknown_sold_quantity: number | null;
  matched_sold_quantity: number | null;
  open_quantity: number | null;
  known_open_cost: number | null;
  unknown_open_quantity: number | null;
  fee_totals: Record<string, number | null>;
  issues: string[];
  disposals: Disposal[];
  curve: { timestamp: string; value: number | null }[];
  opening: Opening | null;
  opening_applied: boolean;
  unrealized: number | null;
  mark_price: number | null;
  balance_quantity: number | null;
  mark_status: string;
  mark_note: string;
  mark_source?: { source: string; label?: string; exchange?: string };
  mark_routes?: Record<
    string,
    {
      symbol: string;
      inverse: boolean;
      rate: number;
      observed_at: string | null;
      received_at?: string;
    }[]
  >;
};
type Performance = {
  example?: boolean;
  items: PerformanceRow[];
  fill_count: number;
  note: string;
  as_of: string;
  totals: {
    environment: string;
    quote: string;
    markets: number;
    matched_realized: number | null;
    net_matched_realized: number | null;
    unrealized: number | null;
  }[];
};
const amount = (value: number | null, currency: string, digits = 4) =>
  value == null ? 'Unavailable' : `${number(value, digits)} ${currency}`;
const dateTime = (value: string) => new Date(value).toLocaleString();

/** Read local FIFO on refresh; balance/price reads occur only after the explicit marks action. */
export function AccountPerformance({
  accountId,
  symbol,
  environment,
  accounts,
  active,
}: {
  accountId: string;
  symbol: string;
  environment: string;
  accounts: Connection[];
  active: boolean;
}) {
  const query = new URLSearchParams({ account_id: accountId, environment });
  if (symbol) query.set('symbol', symbol);
  const path = `/account-ledger/performance?${query}`;
  const resource = useResource<Performance>(path, 0, active);
  const [example, setExample] = useState(false);
  const sample = useResource<Performance>(
    '/account-ledger/performance/example',
    0,
    active && example,
  );
  const [marked, setMarked] = useState<{ path: string; data: Performance }>();
  const [marking, setMarking] = useState(false);
  const [editing, setEditing] = useState<PerformanceRow | 'new'>();
  const closeEditor = useCallback(() => setEditing(undefined), []);
  const controller = useRef<AbortController | undefined>(undefined);
  const toast = useToast();
  useEffect(() => {
    controller.current?.abort();
    setMarked(undefined);
    setMarking(false);
    return () => controller.current?.abort();
  }, [path, resource.data, active, example]);
  useEffect(() => {
    setExample(false);
  }, [path]);
  const current = example ? sample : resource;
  const report = example ? sample.data : marked?.path === path ? marked.data : resource.data;
  const mark = async () => {
    controller.current?.abort();
    const request = new AbortController();
    controller.current = request;
    setMarking(true);
    try {
      const data = await api<Performance>(`${path}&mark=true`, { signal: request.signal });
      if (!request.signal.aborted) setMarked({ path, data });
    } catch (error) {
      if (!request.signal.aborted) toast((error as Error).message, true);
    } finally {
      if (!request.signal.aborted) setMarking(false);
    }
  };
  const download = () => {
    if (!report) return;
    exportCSV(example ? 'sibyl-fifo-example.csv' : 'sibyl-market-fifo-summary.csv', [
      [
        'Account',
        'Environment',
        'Market',
        'Fills',
        'Matched P&L before other fees',
        'Net matched P&L',
        'Quote',
        'Unknown sold quantity',
        'Open quantity',
        'Known open cost',
        'Unknown open quantity',
        'Unrealized',
        'Mark status',
        'Fees in native units',
        'Issues',
        'Report time',
        'Scope',
      ],
      ...report.items.map((row) => [
        row.account,
        row.environment,
        row.symbol,
        row.fill_count,
        row.realized_before_other_fees ?? '',
        row.net_matched_realized ?? '',
        row.quote,
        row.unknown_sold_quantity ?? '',
        row.open_quantity ?? '',
        row.known_open_cost ?? '',
        row.unknown_open_quantity ?? '',
        row.unrealized ?? '',
        row.mark_status,
        JSON.stringify(row.fee_totals),
        row.issues.join(' '),
        report.as_of,
        report.note,
      ]),
    ]);
  };
  return (
    <>
      <Panel className="full-panel performance-panel">
        <PanelTitle
          title="Account performance"
          subtitle="FIFO over retained fills, grouped by account and exact market"
          action={
            <div className="performance-actions">
              <AgentButton
                module="accountant"
                compact
                context={{
                  performance_view: true,
                  performance_account_id: accountId,
                  performance_environment: environment as '' | 'demo' | 'test' | 'production',
                  performance_example: example,
                  ...(symbol ? { symbol } : {}),
                }}
              >
                Ask about this report
              </AgentButton>
              <button
                className="button secondary tiny"
                onClick={() => {
                  setExample(!example);
                  setMarked(undefined);
                }}
              >
                {example ? <X size={13} /> : null}
                {example ? 'Close example' : 'View example'}
              </button>
              {!example && (
                <button
                  className="button secondary tiny"
                  disabled={!accounts.length}
                  onClick={() => setEditing('new')}
                >
                  <Plus size={13} /> Opening inventory
                </button>
              )}
              <button
                className="button secondary tiny"
                disabled={!report?.items.length}
                onClick={download}
              >
                <Download size={13} /> Export summary
              </button>
            </div>
          }
        />
        {example && (
          <div className="performance-example" role="status">
            <Badge tone="purple">Example calculation</Badge>
            <span>
              Four sample fills and an opening lot. This does not use or change your accounts.
            </span>
          </div>
        )}
        <div className="performance-intro">
          <p>
            Results use all retained buys and sells for the selected account, market and
            environment. Fill-table side and page filters do not apply. Unknown-cost sales are
            excluded from matched P&amp;L.
          </p>
          {!example && (
            <div className="performance-actions">
              <button className="button secondary tiny" onClick={resource.retry}>
                <RefreshCw size={13} /> Recalculate
              </button>
              <button
                className="button secondary tiny"
                disabled={marking || !report?.items.length}
                onClick={mark}
              >
                <RefreshCw size={13} className={marking ? 'spin' : ''} />{' '}
                {marking ? 'Checking balances…' : 'Refresh current marks'}
              </button>
            </div>
          )}
        </div>
        {current.error ? (
          <ErrorState message={current.error} retry={current.retry} />
        ) : current.loading ? (
          <Loading />
        ) : !report?.items.length ? (
          <Empty title="No cost-basis history yet">
            Import a market in Fills & imports, or add opening inventory with its optional cost.
            View the example to explore a calculation.
          </Empty>
        ) : (
          <>
            <div className="performance-totals">
              {report.totals.map((total) => (
                <div className="performance-total" key={`${total.environment}:${total.quote}`}>
                  <div>
                    <Badge tone={total.environment === 'production' ? 'blue' : 'purple'}>
                      {total.environment}
                    </Badge>
                    <span>
                      {total.markets} {total.markets === 1 ? 'market' : 'markets'} · {total.quote}
                    </span>
                  </div>
                  <small>Net matched realized P&amp;L</small>
                  <strong
                    className={
                      total.net_matched_realized == null
                        ? ''
                        : total.net_matched_realized >= 0
                          ? 'positive'
                          : 'negative'
                    }
                  >
                    {amount(total.net_matched_realized, total.quote)}
                  </strong>
                  <span>
                    Before other fees / unresolved coverage:{' '}
                    {amount(total.matched_realized, total.quote)}
                  </span>
                  <span>Current unrealized: {amount(total.unrealized, total.quote)}</span>
                </div>
              ))}
            </div>
            <div className="performance-markets">
              {report.items.map((row) => (
                <MarketPerformance
                  key={`${example}:${row.account_id}:${row.symbol}`}
                  row={row}
                  editable={!example && accounts.some((account) => account.id === row.account_id)}
                  edit={() => setEditing(row)}
                />
              ))}
            </div>
            <p className="footnote padded">
              Calculated {dateTime(report.as_of)} · {report.fill_count} retained fills.{' '}
              {report.note}
            </p>
          </>
        )}
      </Panel>
      {editing && (
        <OpeningEditor
          accounts={accounts}
          accountId={accountId}
          symbol={symbol}
          row={editing === 'new' ? undefined : editing}
          onClose={closeEditor}
          saved={() => {
            setEditing(undefined);
            setMarked(undefined);
            refresh();
          }}
        />
      )}
    </>
  );
}

function MarketPerformance({
  row,
  editable,
  edit,
}: {
  row: PerformanceRow;
  editable: boolean;
  edit: () => void;
}) {
  const curve = row.curve.filter(
    (item): item is { timestamp: string; value: number } => item.value != null,
  );
  return (
    <article className="performance-market">
      <header>
        <span className="provider-logo small-logo">
          <ExchangeMark exchange={row.exchange} />
        </span>
        <div>
          <h3>{row.symbol}</h3>
          <p>
            {row.account} · {row.environment} · {row.fill_count} fills
          </p>
        </div>
        <Badge tone={row.net_known ? 'lime' : 'rose'}>
          {row.net_known ? 'Matched lots' : 'Provisional'}
        </Badge>
        {editable && (
          <button className="button secondary tiny" onClick={edit}>
            <Pencil size={12} /> Opening basis
          </button>
        )}
      </header>
      <div className="performance-metrics">
        <div>
          <span>Matched realized before other fees</span>
          <strong>{amount(row.realized_before_other_fees, row.quote)}</strong>
        </div>
        <div>
          <span>Open inventory</span>
          <strong>{amount(row.open_quantity, row.base, 8)}</strong>
        </div>
        <div>
          <span>Known open cost</span>
          <strong>{amount(row.known_open_cost, row.quote)}</strong>
        </div>
        <div>
          <span>Current unrealized</span>
          <strong>{amount(row.unrealized, row.quote)}</strong>
        </div>
      </div>
      {row.opening && (
        <p className="performance-basis">
          <Badge>{row.opening_applied ? 'Opening lot applied' : 'Opening lot ignored'}</Badge>{' '}
          {row.opening.quantity} {row.base} ·{' '}
          {row.opening.total_cost == null
            ? 'Cost unknown'
            : `${row.opening.total_cost} ${row.quote} total cost`}{' '}
          · {dateTime(row.opening.as_of)}
        </p>
      )}
      {!!row.issues.length && (
        <ul className="performance-issues">
          {row.issues.map((issue) => (
            <li key={issue}>{issue}</li>
          ))}
        </ul>
      )}
      <p className="performance-mark-note">
        {row.mark_note}{' '}
        {row.mark_source && (
          <>
            Feed: {row.mark_source.label || row.mark_source.exchange || row.mark_source.source}.
            Status: {row.mark_status}.{' '}
          </>
        )}
        {row.mark_price != null && (
          <>
            Reference: {amount(row.mark_price, row.quote, 8)} per {row.base}.{' '}
          </>
        )}
        {row.balance_quantity != null && (
          <>Observed balance: {amount(row.balance_quantity, row.base, 8)}.</>
        )}
      </p>
      <details className="performance-evidence">
        <summary>
          Calculation details{' '}
          <span>{row.disposal_count} disposals · fees &amp; matching evidence</span>
        </summary>
        <div className="performance-detail-body">
          <p>
            Reported fees / rebates:{' '}
            {Object.entries(row.fee_totals)
              .map(([currency, fee]) => amount(fee, currency, 8))
              .join(' · ') || 'Unavailable'}
            . Unknown-cost sold: {amount(row.unknown_sold_quantity, row.base, 8)}. Unknown-cost
            open: {amount(row.unknown_open_quantity, row.base, 8)}.
          </p>
          {row.mark_routes && (
            <div className="performance-routes">
              {Object.entries(row.mark_routes).map(([asset, legs]) => (
                <p key={asset}>
                  <strong>{asset} conversion:</strong>{' '}
                  {legs.length
                    ? legs
                        .map(
                          (leg) =>
                            `${leg.symbol}${leg.inverse ? ' (inverse)' : ''} × ${number(leg.rate, 8)} · ${leg.observed_at ? dateTime(leg.observed_at) : 'Provider timestamp unavailable'}`,
                        )
                        .join(' → ')
                    : 'Denomination identity'}
                </p>
              ))}
            </div>
          )}
          {!!curve.length && (
            <>
              <h4>Cumulative matched P&amp;L before other fees</h4>
              <ValueChart data={curve} unit={row.quote} currency={false} height={190} />
              <p className="footnote">
                Latest {curve.length} disposal points; each point retains cumulative earlier
                matches. This is not an account return curve.
              </p>
            </>
          )}
          {!!row.disposals.length && (
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>Disposal</th>
                    <th>Consumed / unknown</th>
                    <th>Matched cost</th>
                    <th>Matched proceeds</th>
                    <th>Matched P&amp;L</th>
                  </tr>
                </thead>
                <tbody>
                  {row.disposals.map((item) => (
                    <tr key={item.id}>
                      <td>
                        <strong>{dateTime(item.timestamp)}</strong>
                        <small>Fill {item.trade_id}</small>
                      </td>
                      <td>
                        {amount(item.quantity, row.base, 8)}
                        <small>{amount(item.unknown_quantity, row.base, 8)} unknown</small>
                      </td>
                      <td>{amount(item.matched_cost, row.quote)}</td>
                      <td>{amount(item.matched_proceeds, row.quote)}</td>
                      <td>{amount(item.pnl_before_other_fees, row.quote)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <p className="footnote">
            Latest {row.disposals.length} of {row.disposal_count} disposals shown. Quote fees adjust
            cost/proceeds; base fees adjust received/consumed quantity. Other fee currencies are not
            converted.
          </p>
        </div>
      </details>
    </article>
  );
}

/** Edit user assertions without rewriting imported execution facts; every change is audited. */
function OpeningEditor({
  accounts,
  accountId,
  symbol,
  row,
  onClose,
  saved,
}: {
  accounts: Connection[];
  accountId: string;
  symbol: string;
  row?: PerformanceRow;
  onClose: () => void;
  saved: () => void;
}) {
  const [account, setAccount] = useState(row?.account_id || accountId || accounts[0]?.id || '');
  const [pair, setPair] = useState(row?.symbol || symbol || 'BTC/USDT');
  const [quantity, setQuantity] = useState(row?.opening?.quantity || '');
  const [cost, setCost] = useState(row?.opening?.total_cost || '');
  const initialDate =
    row?.opening?.as_of ||
    (row?.first_fill_at
      ? new Date(new Date(row.first_fill_at).getTime() - 1000).toISOString()
      : new Date(Date.now() - 86400000).toISOString());
  const localDate = (date: string) => {
    const value = new Date(date);
    return new Date(value.getTime() - value.getTimezoneOffset() * 60000).toISOString().slice(0, 19);
  };
  const [date, setDate] = useState(localDate(initialDate));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const dismiss = useCallback(() => {
    if (!busy) onClose();
  }, [busy, onClose]);
  const audit = useResource<{
    items: { changed_at: string; action: string; before: Opening | null; after: Opening | null }[];
  }>(
    `/connections/${encodeURIComponent(account)}/opening-inventory/audit?symbol=${encodeURIComponent(pair.toUpperCase())}`,
    0,
    !!row && !!account,
  );
  const save = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError('');
    try {
      await post(`/connections/${encodeURIComponent(account)}/opening-inventory`, {
        symbol: pair.trim().toUpperCase(),
        quantity,
        total_cost: cost.trim() === '' ? null : cost,
        as_of: new Date(date).toISOString(),
      });
      saved();
    } catch (reason) {
      setError((reason as Error).message);
    } finally {
      setBusy(false);
    }
  };
  const remove = async () => {
    setBusy(true);
    setError('');
    try {
      await api(
        `/connections/${encodeURIComponent(account)}/opening-inventory?symbol=${encodeURIComponent(pair)}`,
        { method: 'DELETE' },
      );
      saved();
    } catch (reason) {
      setError((reason as Error).message);
    } finally {
      setBusy(false);
    }
  };
  const quote = pair.split('/')[1] || 'quote currency';
  return (
    <Modal
      title="Opening inventory & cost basis"
      onClose={dismiss}
      className="opening-inventory-modal"
    >
      <p className="muted">
        Enter the inventory held immediately before the first retained fill in this exact market.
        Total cost is in {quote}. Leave cost blank if unknown; enter 0 only for a known zero cost.
      </p>
      <form onSubmit={save} className="opening-inventory-form">
        <label>
          Account
          <select
            required
            disabled={!!row || busy}
            value={account}
            onChange={(event) => setAccount(event.target.value)}
          >
            {accounts.map((item) => (
              <option key={item.id} value={item.id}>
                {item.label}
              </option>
            ))}
          </select>
        </label>
        <label>
          Exact spot market
          <input
            required
            disabled={!!row || busy}
            value={pair}
            onChange={(event) => setPair(event.target.value.toUpperCase())}
            placeholder="BTC/USDT"
            pattern="[A-Z0-9]{1,12}/[A-Z0-9]{1,12}"
          />
        </label>
        <label>
          Opening quantity
          <input
            required
            disabled={busy}
            type="number"
            step="any"
            min="0.000000000000000001"
            value={quantity}
            onChange={(event) => setQuantity(event.target.value)}
          />
        </label>
        <label>
          Total cost in {quote} (optional)
          <input
            disabled={busy}
            type="number"
            min="0"
            step="any"
            value={cost}
            onChange={(event) => setCost(event.target.value)}
            placeholder="Unknown"
          />
        </label>
        <label className="opening-date">
          As of (your local time)
          <input
            required
            disabled={busy}
            type="datetime-local"
            step="1"
            value={date}
            onChange={(event) => setDate(event.target.value)}
          />
        </label>
        {error && (
          <div className="opening-date">
            <ErrorState message={error} />
          </div>
        )}
        <p className="footnote opening-date">
          This is your assertion, not an exchange record. Transfers and cross-market inventory still
          require reconciliation. A newly imported earlier fill can invalidate this opening date.
          Updates retain a local audit trail.
        </p>
        <div className="performance-actions opening-date">
          {row?.opening && (
            <button type="button" className="button secondary" disabled={busy} onClick={remove}>
              Remove opening lot
            </button>
          )}
          <button className="button primary" disabled={busy || !account}>
            {busy ? 'Saving…' : 'Save opening inventory'}
          </button>
        </div>
      </form>
      {audit.error && <ErrorState message={audit.error} retry={audit.retry} />}
      {!!audit.data?.items.length && (
        <details className="performance-evidence">
          <summary>Recent basis changes</summary>
          <div className="performance-detail-body">
            {audit.data.items.map((item, index) => (
              <p key={index}>
                {dateTime(item.changed_at)} · {item.action} ·{' '}
                {(item.after || item.before)?.quantity} {pair.split('/')[0]} · total cost{' '}
                {(item.after || item.before)?.total_cost ?? 'unknown'} {quote}
              </p>
            ))}
          </div>
        </details>
      )}
    </Modal>
  );
}

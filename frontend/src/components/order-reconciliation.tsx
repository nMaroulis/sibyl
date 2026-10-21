import { useState } from 'react';
import { Link } from 'react-router-dom';
import { Pause, Play, RefreshCw } from 'lucide-react';
import { number, post, refresh } from '../lib/api';
import { useResource } from '../lib/hooks';
import { Badge, Empty, ErrorState, Loading, Modal } from './ui';
import type { ManagedOrder } from './order-monitor';

export type Reconciliation = {
  status: string;
  fill_count: number;
  quantity: number | null;
  native_filled: number | null;
  quantity_difference: number | null;
  notional: number | null;
  average: number | null;
  cost_difference: number | null;
  native_cost: number | null;
  fees: { currency: string; cost: number | null }[];
  unknown_fee_fills: number;
  note: string;
  sync: {
    state?: string;
    enabled?: boolean;
    caught_up?: boolean;
    pages?: number;
    checked_at?: string;
    error?: string;
    terminal_passes?: number;
  };
};
type Fill = {
  id: string;
  trade_id: string;
  created_at: string;
  quantity: number;
  price: number;
  fees_known: boolean;
  fees: { currency: string | null; cost: number | null }[];
};
type Detail = {
  order: ManagedOrder;
  reconciliation: Reconciliation;
  fills: Fill[];
  has_more: boolean;
};

export const reconciliationLabel = (status?: string) =>
  ({
    matched: 'Observed fills match',
    missing_fills: 'Missing executions',
    fees_missing: 'Fees incomplete',
    mismatch: 'Evidence differs',
    pending: 'Tracking executions',
    unverified: 'Aggregate unavailable',
    limit_reached: 'Evidence limit reached',
    not_checked: 'Not checked',
  })[status || 'not_checked'] || status;
const display = (value?: number | null) => (value == null ? '—' : number(value, 8));
const syncLabel = (state?: string) =>
  ({
    idle: 'Waiting for the next check',
    queued: 'Execution checks queued',
    complete: 'Scheduled checks finished',
    paused: 'Fill checks paused',
    waiting_account: 'Waiting for account activation',
    error: 'Check needs attention',
    unsupported: 'Checks unavailable',
  })[state || ''] || 'No execution check yet';

/** Inspect native executions in place; opening the dialog only reads retained evidence. */
export function OrderReconciliation({
  identity,
  example,
  onClose,
}: {
  identity: string;
  example: boolean;
  onClose: () => void;
}) {
  const detail = useResource<Detail>(
    `/exchange-orders/${example ? 'example/' : ''}${identity}/reconciliation`,
    example ? 0 : 5000,
  );
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const act = async (tracking?: boolean) => {
    if (example) return;
    setBusy(true);
    setError('');
    try {
      await post(
        `/exchange-orders/${identity}/reconcile${tracking == null ? '' : '/tracking'}`,
        tracking == null ? {} : { enabled: tracking },
      );
      refresh();
    } catch (reason) {
      setError((reason as Error).message);
    } finally {
      setBusy(false);
    }
  };
  const record = detail.data;
  const result = record?.reconciliation;
  const base = record?.order.request.symbol.split('/')[0];
  const quote = record?.order.request.symbol.split('/')[1];
  return (
    <Modal title="Order & executions" onClose={onClose} className="order-reconciliation-dialog">
      {detail.error ? (
        <ErrorState message={detail.error} retry={detail.retry} />
      ) : !record || !result ? (
        <Loading />
      ) : (
        <div className="order-reconciliation-body">
          <div className="order-reconciliation-heading">
            <div>
              <h3>
                {record.order.request.symbol} · {record.order.request.side}
              </h3>
              <p className="muted">
                {record.order.account} · {record.order.environment} · {record.order.status}
              </p>
            </div>
            <Badge
              tone={
                ['mismatch', 'missing_fills', 'limit_reached'].includes(result.status)
                  ? 'rose'
                  : 'neutral'
              }
            >
              {reconciliationLabel(result.status)}
            </Badge>
          </div>
          {example && (
            <p className="inline-alert">
              Illustrative evidence. No account or ledger records are changed.
            </p>
          )}
          <div className="order-reconciliation-metrics">
            <div>
              <span>Native filled · {base}</span>
              <strong>{display(result.native_filled)}</strong>
            </div>
            <div>
              <span>Imported executions · {base}</span>
              <strong>{display(result.quantity)}</strong>
            </div>
            <div>
              <span>Quantity difference · {base}</span>
              <strong>{display(result.quantity_difference)}</strong>
            </div>
            <div>
              <span>Native cost · {quote}</span>
              <strong>{display(result.native_cost)}</strong>
            </div>
            <div>
              <span>Reported cost · {quote}</span>
              <strong>{display(result.notional)}</strong>
            </div>
            <div>
              <span>Cost difference · {quote}</span>
              <strong>{display(result.cost_difference)}</strong>
            </div>
          </div>
          <div className="order-reconciliation-actions">
            <button
              className="button secondary"
              disabled={busy || example || !record.order.exchange_order_id}
              onClick={() => act()}
            >
              <RefreshCw size={14} />{' '}
              {busy
                ? 'Checking…'
                : result.sync.caught_up === false && (result.sync.pages ?? 0) > 0
                  ? 'Continue execution check'
                  : 'Check executions'}
            </button>
            {result.sync.state && (
              <button
                className="button secondary"
                disabled={busy || example}
                onClick={() => act(!result.sync.enabled)}
              >
                {result.sync.enabled ? <Pause size={14} /> : <Play size={14} />}
                {result.sync.enabled ? 'Pause fill checks' : 'Resume fill checks'}
              </button>
            )}
            <Link className="text-button" to="/trade?tab=history" onClick={onClose}>
              Account history ↗
            </Link>
          </div>
          {(error || result.sync.error) && (
            <p className="form-error" role="alert">
              {error || result.sync.error}
            </p>
          )}
          {!record.order.exchange_order_id && (
            <p className="inline-alert">
              No native order ID is confirmed. Check the venue using the client order ID before
              creating another order.
            </p>
          )}
          <p className="footnote">
            {result.fill_count} retained {result.fill_count === 1 ? 'execution' : 'executions'} ·{' '}
            {example
              ? 'Illustrative record'
              : result.sync.enabled === false &&
                  ['idle', 'queued'].includes(result.sync.state || '')
                ? 'Automatic fill checks off'
                : syncLabel(result.sync.state)}
            {result.sync.checked_at
              ? ` · Last checked ${new Date(result.sync.checked_at).toLocaleString()}`
              : ''}
          </p>
          {record.fills.length ? (
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>Time / native fill ID</th>
                    <th>Quantity · {base}</th>
                    <th>Price · {quote}</th>
                    <th>Reported fees</th>
                  </tr>
                </thead>
                <tbody>
                  {record.fills.map((fill) => (
                    <tr key={fill.id}>
                      <td>
                        {new Date(fill.created_at).toLocaleString()}
                        <small className="table-subline">{fill.trade_id}</small>
                      </td>
                      <td>{display(fill.quantity)}</td>
                      <td>{display(fill.price)}</td>
                      <td>
                        {fill.fees.length
                          ? fill.fees
                              .map(
                                (fee) => `${display(fee.cost)} ${fee.currency || 'unknown asset'}`,
                              )
                              .join(' · ')
                          : 'Unknown'}
                        {!fill.fees_known && (
                          <small className="table-subline">Incomplete fee evidence</small>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <Empty title="No retained executions">
              Checks import native executions when available. Aggregate filled quantities alone
              never create ledger entries.
            </Empty>
          )}
          <p className="footnote">
            Reported fees:{' '}
            {result.fees.length
              ? result.fees.map((fee) => `${display(fee.cost)} ${fee.currency}`).join(' · ')
              : 'None reported'}
            .
            {result.unknown_fee_fills > 0
              ? ` ${result.unknown_fee_fills} ${result.unknown_fee_fills === 1 ? 'execution has' : 'executions have'} incomplete fees.`
              : ''}
            {record.has_more
              ? ' First 200 executions shown; totals cover the bounded retained selection.'
              : ''}
          </p>
          <p className="footnote">
            {result.note} Keep the account active for background updates, or recheck later.
          </p>
          <p className="footnote">
            Native order ID: <code>{record.order.exchange_order_id || 'Unconfirmed'}</code>
            <br />
            Client order ID: <code>{record.order.client_order_id}</code>
          </p>
        </div>
      )}
    </Modal>
  );
}

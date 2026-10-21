import { useState } from 'react';
import { Pause, Play, RefreshCw, X } from 'lucide-react';
import { useResource } from '../lib/hooks';
import { number, post, refresh } from '../lib/api';
import type { OrderInput } from '../lib/types';
import { Badge, Empty, ErrorState, Modal, Panel, PanelTitle, useToast } from './ui';
import { OrderReconciliation, reconciliationLabel } from './order-reconciliation';
import type { Reconciliation } from './order-reconciliation';

export type ManagedOrder = {
  id: string;
  request: OrderInput & {
    connection_id: string;
    order_type?: 'market' | 'limit';
    limit_price?: number;
  };
  account: string;
  exchange: string;
  sandbox: boolean;
  environment?: string;
  mode?: string;
  status: string;
  price: number;
  notional: number;
  confirmation: string;
  expires_at: string;
  client_order_id: string;
  exchange_order_id?: string;
  message?: string;
  filled?: number;
  remaining?: number;
  average?: number;
  tracking?: boolean;
  refreshed_at?: string;
  sync_error?: string;
  cancel_state?: string;
  cancel_message?: string;
  reconciliation?: Reconciliation;
};
type CancelReview = {
  id: string;
  intent_id: string;
  symbol: string;
  account: string;
  environment: string;
  confirmation: string;
  expires_at: string;
  filled?: number;
  remaining?: number;
};
const terminal = new Set(['closed', 'canceled', 'expired', 'rejected']);
const display = (value?: number) => (value == null ? '—' : number(value, 8));

/** Native cumulative status is kept separate from imported execution records. */
export function OrderMonitor({ active = true }: { active?: boolean }) {
  const [example, setExample] = useState(false);
  const orders = useResource<ManagedOrder[]>(
    example ? '/exchange-orders/example' : '/exchange-orders',
    5000,
    active,
  );
  const [busy, setBusy] = useState('');
  const [review, setReview] = useState<CancelReview>();
  const [inspected, setInspected] = useState<string>();
  const [phrase, setPhrase] = useState('');
  const [error, setError] = useState('');
  const toast = useToast();
  const act = async (order: ManagedOrder, action: 'refresh' | 'tracking' | 'cancel/preview') => {
    if (example) return;
    setBusy(order.id);
    setError('');
    try {
      const result = await post<ManagedOrder | CancelReview>(
        `/exchange-orders/${order.id}/${action}`,
        action === 'tracking' ? { enabled: !order.tracking } : {},
      );
      if (action === 'cancel/preview') {
        setReview(result as CancelReview);
        setPhrase('');
      }
      refresh();
    } catch (reason) {
      toast((reason as Error).message, true);
    } finally {
      setBusy('');
    }
  };
  const cancel = async () => {
    if (!review || example) return;
    setBusy(review.intent_id);
    setError('');
    try {
      const result = await post<ManagedOrder>(`/exchange-orders/${review.intent_id}/cancel`, {
        cancel_id: review.id,
        confirmation: phrase,
      });
      toast(
        result.cancel_message || 'Cancellation status updated.',
        result.cancel_state === 'unknown',
      );
      setReview(undefined);
      refresh();
    } catch (reason) {
      setError((reason as Error).message);
    } finally {
      setBusy('');
    }
  };
  const submitted = orders.data?.filter((order) => order.status !== 'preview') ?? [];
  return (
    <Panel className="full-panel order-monitor">
      <PanelTitle
        title="Order monitor"
        subtitle="Order status, execution evidence & reported fees"
        action={
          <button
            className="button secondary tiny"
            onClick={() => {
              setExample(!example);
              setReview(undefined);
              setInspected(undefined);
            }}
          >
            {example ? 'Return to my orders' : 'View example'}
          </button>
        }
      />
      {example && (
        <div className="order-example-note">
          <Badge>Illustrative example</Badge>
          <span>Read-only sample. No account, balances or orders are changed.</span>
        </div>
      )}
      {orders.error ? (
        <ErrorState message={orders.error} retry={orders.retry} />
      ) : submitted.length ? (
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>Account / market</th>
                <th>Order</th>
                <th>Filled / remaining</th>
                <th>Average fill</th>
                <th>Status</th>
                <th>Executions</th>
                <th>Manage</th>
              </tr>
            </thead>
            <tbody>
              {submitted.map((order) => (
                <tr key={order.id}>
                  <td>
                    <strong>{order.account}</strong>
                    <small className="table-subline">
                      {order.environment || (order.sandbox ? 'test' : 'production')} ·{' '}
                      {order.request.symbol}
                    </small>
                  </td>
                  <td>
                    {order.request.side} · {order.request.order_type || 'market'}
                    <small className="table-subline">
                      {number(order.request.quantity, 8)}
                      {order.request.order_type === 'limit'
                        ? ` @ ${number(order.request.limit_price ?? order.price, 8)} · GTC`
                        : ''}
                    </small>
                  </td>
                  <td>
                    {display(order.filled)} / {display(order.remaining)}
                    <small className="table-subline">{order.request.symbol.split('/')[0]}</small>
                  </td>
                  <td>
                    {display(order.average)}
                    <small className="table-subline">{order.request.symbol.split('/')[1]}</small>
                  </td>
                  <td>
                    <Badge tone={order.status === 'unknown' ? 'rose' : 'neutral'}>
                      {order.status === 'open' && (order.filled ?? 0) > 0
                        ? 'Partially filled'
                        : order.status}
                    </Badge>
                    <small className="table-subline">
                      {order.cancel_state
                        ? `Cancel: ${order.cancel_state}`
                        : order.tracking
                          ? 'Tracking on'
                          : terminal.has(order.status)
                            ? 'Final observation'
                            : 'Tracking paused'}
                    </small>
                    {order.refreshed_at && (
                      <small
                        className="table-subline"
                        title={new Date(order.refreshed_at).toLocaleString()}
                      >
                        Checked {new Date(order.refreshed_at).toLocaleTimeString()}
                      </small>
                    )}
                  </td>
                  <td>
                    <button className="text-button" onClick={() => setInspected(order.id)}>
                      {reconciliationLabel(order.reconciliation?.status)} ↗
                    </button>
                    <small className="table-subline">
                      {order.reconciliation?.fill_count ?? 0} retained fills
                    </small>
                  </td>
                  <td>
                    <div className="order-actions">
                      <button
                        className="icon-button"
                        aria-label={`Check ${order.request.symbol} order`}
                        title="Read native status"
                        disabled={
                          !!busy ||
                          example ||
                          (!order.exchange_order_id && order.exchange !== 'demo')
                        }
                        onClick={() => act(order, 'refresh')}
                      >
                        <RefreshCw size={14} />
                      </button>
                      {!terminal.has(order.status) && (
                        <>
                          <button
                            className="icon-button"
                            aria-label={`${order.tracking ? 'Pause' : 'Resume'} order tracking`}
                            disabled={!!busy || example}
                            onClick={() => act(order, 'tracking')}
                          >
                            {order.tracking ? <Pause size={14} /> : <Play size={14} />}
                          </button>
                          {['open', 'pending', 'submitted'].includes(order.status) && (
                            <button
                              className="button secondary tiny"
                              disabled={!!busy || example}
                              onClick={() => act(order, 'cancel/preview')}
                            >
                              <X size={13} /> Cancel…
                            </button>
                          )}
                        </>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {submitted
            .filter(
              (order) => order.sync_error || order.cancel_message || order.status === 'unknown',
            )
            .map((order) => (
              <p className="footnote padded" key={order.id}>
                <strong>
                  {order.account} · {order.request.symbol}:
                </strong>{' '}
                {order.sync_error || order.cancel_message || order.message}
                <br />
                Client order ID: <code>{order.client_order_id}</code>
              </p>
            ))}
        </div>
      ) : (
        <Empty title="No submitted orders yet">
          Submit a reviewed market or GTC limit order to follow its status here, or view an example.
        </Empty>
      )}
      <p className="footnote padded">
        Only orders submitted here are monitored. Status checks run on the server about every 20
        seconds while tracking and the account are active; failures back off. Cumulative fills are
        observations. Execution checks import exact-order fills into Account history without
        duplicating history imports. Open the execution evidence to compare quantities and reported
        fees.
      </p>
      {inspected && (
        <OrderReconciliation
          key={inspected}
          identity={inspected}
          example={example}
          onClose={() => setInspected(undefined)}
        />
      )}
      {review && (
        <Modal
          title="Review cancellation"
          onClose={() => {
            if (!busy) setReview(undefined);
          }}
        >
          <form
            className="form"
            onSubmit={(event) => {
              event.preventDefault();
              cancel();
            }}
          >
            <div className="order-preview">
              <div>
                <span>Account</span>
                <strong>
                  {review.account} · {review.environment}
                </strong>
              </div>
              <div>
                <span>Market</span>
                <strong>{review.symbol}</strong>
              </div>
              <div>
                <span>Filled / remaining</span>
                <strong>
                  {display(review.filled)} / {display(review.remaining)}
                </strong>
              </div>
            </div>
            <p className="muted">
              A fill can arrive before cancellation completes. A cancellation acknowledgment alone
              does not confirm that the order is canceled.
            </p>
            <label>
              Type {review.confirmation}
              <input
                autoComplete="off"
                value={phrase}
                onChange={(event) => setPhrase(event.target.value)}
                required
                disabled={!!busy}
              />
            </label>
            {error && (
              <p role="alert" className="form-error">
                {error}
              </p>
            )}
            <button
              className="button rose-button"
              disabled={!!busy || phrase !== review.confirmation}
            >
              {busy ? 'Requesting…' : 'Request cancellation'}
            </button>
            <small className="muted">
              Review expires at {new Date(review.expires_at).toLocaleTimeString()}. This command is
              sent at most once.
            </small>
          </form>
        </Modal>
      )}
    </Panel>
  );
}

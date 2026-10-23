import { useState } from 'react';
import { Link } from 'react-router-dom';
import { ChevronLeft, ChevronRight, Pause, Play, RefreshCw, X } from 'lucide-react';
import { useResource } from '../lib/hooks';
import { number, post, refresh } from '../lib/api';
import type { OrderInput } from '../lib/types';
import { Badge, Empty, ErrorState, Loading, Modal, Panel, PanelTitle, useToast } from './ui';
import { OrderReconciliation, reconciliationLabel } from './order-reconciliation';
import type { Reconciliation } from './order-reconciliation';
import { OrderDiscovery } from './order-discovery';

export type ManagedOrder = {
  id: string;
  request: Omit<OrderInput, 'quantity'> & {
    quantity: number | null;
    connection_id: string;
    order_type?: string;
    limit_price?: number;
  };
  account: string;
  exchange: string;
  sandbox: boolean;
  environment?: string;
  mode?: string;
  status: string;
  price: number | null;
  notional: number | null;
  origin?: 'sibyl' | 'strategy' | 'imported';
  strategy_job_id?: string;
  read_only?: boolean;
  time_in_force?: string | null;
  confirmation: string;
  expires_at: string;
  client_order_id: string | null;
  exchange_order_id?: string;
  message?: string;
  filled?: number | null;
  remaining?: number | null;
  average?: number | null;
  tracking?: boolean;
  refreshed_at?: string;
  created_at?: string;
  order_created_at?: string | null;
  sync_error?: string;
  cancel_state?: string;
  cancel_message?: string;
  reconciliation?: Reconciliation;
  recovery?: {
    supported: boolean;
    eligible: boolean;
    state: string;
    message: string;
    pages?: number;
    passes?: number;
    checked_at?: string;
    recovered_at?: string;
  };
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
const display = (value?: number | null) => (value == null ? '—' : number(value, 8));

/** Native cumulative status is kept separate from imported execution records. */
export function OrderMonitor({ active = true }: { active?: boolean }) {
  const [example, setExample] = useState(false);
  const [account, setAccount] = useState('');
  const [exchange, setExchange] = useState('');
  const [origin, setOrigin] = useState('');
  const [status, setStatus] = useState('');
  const [offset, setOffset] = useState(0);
  const query = new URLSearchParams({
    account_id: account,
    exchange,
    origin,
    status,
    offset: String(offset),
  });
  const orders = useResource<
    | ManagedOrder[]
    | {
        items: ManagedOrder[];
        total: number;
        has_more: boolean;
        accounts: { id: string; label: string; exchange: string }[];
      }
  >(example ? '/exchange-orders/example' : `/exchange-orders/monitor?${query}`, 5000, active);
  const [busy, setBusy] = useState('');
  const [review, setReview] = useState<CancelReview>();
  const [inspected, setInspected] = useState<string>();
  const [phrase, setPhrase] = useState('');
  const [error, setError] = useState('');
  const toast = useToast();
  const act = async (
    order: ManagedOrder,
    action: 'refresh' | 'tracking' | 'cancel/preview' | 'recover',
  ) => {
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
      } else if (action === 'recover') {
        const outcome = result as ManagedOrder;
        toast(
          outcome.recovery?.message || outcome.message || 'Lookup updated.',
          ['error', 'mismatch', 'ambiguous', 'unsupported'].includes(outcome.recovery?.state || ''),
        );
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
  const records = Array.isArray(orders.data) ? orders.data : (orders.data?.items ?? []);
  const accounts = Array.isArray(orders.data) ? [] : (orders.data?.accounts ?? []);
  const total = Array.isArray(orders.data) ? orders.data.length : (orders.data?.total ?? 0);
  const submitted = records.filter((order) => order.status !== 'preview');
  const filter = (setter: (value: string) => void, value: string) => {
    setter(value);
    setOffset(0);
  };

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
      {!example && (
        <>
          <OrderDiscovery active={active} />
          <div className="workspace-controls order-monitor-filters">
            <label>
              Exchange
              <select
                value={exchange}
                onChange={(event) => {
                  filter(setExchange, event.target.value);
                  setAccount('');
                }}
              >
                <option value="">All exchanges</option>
                {[...new Set(accounts.map((row) => row.exchange))].map((value) => (
                  <option key={value} value={value}>
                    {value}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Account
              <select value={account} onChange={(event) => filter(setAccount, event.target.value)}>
                <option value="">All accounts</option>
                {accounts
                  .filter((row) => !exchange || row.exchange === exchange)
                  .map((row) => (
                    <option key={row.id} value={row.id}>
                      {row.label}
                    </option>
                  ))}
              </select>
            </label>
            <label>
              Origin
              <select value={origin} onChange={(event) => filter(setOrigin, event.target.value)}>
                <option value="">All origins</option>
                <option value="sibyl">Manual Sibyl orders</option>
                <option value="strategy">Automated strategies</option>
                <option value="imported">Imported · read-only</option>
              </select>
            </label>
            <label>
              Status
              <select value={status} onChange={(event) => filter(setStatus, event.target.value)}>
                <option value="">All statuses</option>
                <option value="active">Active / uncertain</option>
                <option value="terminal">Finished</option>
              </select>
            </label>
          </div>
        </>
      )}
      {orders.error ? (
        <ErrorState message={orders.error} retry={orders.retry} />
      ) : orders.loading && !orders.data ? (
        <Loading />
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
                      <Badge>
                        {order.origin === 'imported'
                          ? 'Imported · read-only'
                          : order.origin === 'strategy'
                            ? 'Strategy'
                            : 'Manual Sibyl'}
                      </Badge>
                    </small>
                    {order.strategy_job_id && (
                      <small className="table-subline">
                        <Link to={`/strategies?view=monitor&job=${order.strategy_job_id}`}>
                          Open strategy ↗
                        </Link>
                      </small>
                    )}
                    <small className="table-subline">
                      {order.environment || (order.sandbox ? 'test' : 'production')} ·{' '}
                      {order.request.symbol}
                    </small>
                  </td>
                  <td>
                    {order.request.side} · {order.request.order_type || 'market'}
                    <small className="table-subline">
                      {display(order.request.quantity)}
                      {order.request.order_type === 'limit'
                        ? ` @ ${display(order.request.limit_price ?? order.price)}${order.origin === 'imported' ? (order.time_in_force ? ` · ${order.time_in_force}` : '') : ' · GTC'}`
                        : ''}
                    </small>
                    {(order.order_created_at || order.created_at) && (
                      <small className="table-subline">
                        {order.origin === 'imported' && !order.order_created_at
                          ? 'First seen'
                          : 'Created'}{' '}
                        {new Date(order.order_created_at || order.created_at!).toLocaleString()}
                      </small>
                    )}
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
                      {!order.exchange_order_id && order.recovery?.eligible ? (
                        <button
                          className="button secondary tiny"
                          disabled={!!busy || example || !order.recovery.supported}
                          onClick={() => act(order, 'recover')}
                          title="Read existing orders by the saved client ID; never resubmit"
                        >
                          <RefreshCw size={14} />{' '}
                          {order.recovery.state === 'searching'
                            ? 'Continue lookup'
                            : 'Recover order'}
                        </button>
                      ) : (
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
                      )}
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
                          {order.origin !== 'imported' &&
                            ['open', 'pending', 'submitted'].includes(order.status) && (
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
                Client order ID: <code>{order.client_order_id || 'Not reported'}</code>
              </p>
            ))}
        </div>
      ) : (
        <Empty
          title={
            account || exchange || origin || status
              ? 'No orders match these filters'
              : 'No retained orders yet'
          }
        >
          Sync exchange orders to discover existing orders, submit a reviewed order in Sibyl, or
          view an example.
        </Empty>
      )}
      {!example && total > 0 && (
        <div className="order-monitor-pagination">
          <span>
            {offset + 1}–{Math.min(offset + 25, total)} of {total} orders
          </span>
          <button
            className="icon-button"
            aria-label="Previous orders"
            disabled={!offset}
            onClick={() => setOffset(Math.max(0, offset - 25))}
          >
            <ChevronLeft size={16} />
          </button>
          <button
            className="icon-button"
            aria-label="Next orders"
            disabled={Array.isArray(orders.data) || !orders.data?.has_more}
            onClick={() => setOffset(offset + 25)}
          >
            <ChevronRight size={16} />
          </button>
        </div>
      )}
      <p className="footnote padded">
        Sibyl submissions and imported spot orders share native execution IDs in Account history.
        Imported orders are read-only; manage them at the exchange. Discovery covers open orders and
        a bounded recent range, with provider-specific limits. Missing orders are never assumed
        canceled. Individual status checks run about every 20 seconds while tracking and the account
        are active; failures back off. Quantity matches and reported fees do not imply final
        settlement.
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

import { useState } from 'react';
import { Link } from 'react-router-dom';
import { ArrowUpRight, KeyRound, ShieldCheck } from 'lucide-react';
import { Badge, Empty, ErrorState, Panel, PanelTitle, useToast } from './ui';
import { money, number, post, refresh } from '../lib/api';
import { useResource } from '../lib/hooks';
import type { Connection, OrderInput, System } from '../lib/types';

type ExchangeIntent = {
  id: string;
  request: OrderInput & { connection_id: string };
  account: string;
  exchange: string;
  sandbox: boolean;
  status: string;
  price: number;
  notional: number;
  confirmation: string;
  expires_at: string;
  client_order_id: string;
  exchange_order_id?: string;
  message?: string;
  filled?: number;
};

/** Exchange execution is a separate reviewed flow, guarded by server configuration. */
export function ExchangeExecution() {
  const system = useResource<System>('/system');
  const connections = useResource<Connection[]>('/connections');
  const realConnections =
    connections.data?.filter((connection) => connection.exchange !== 'demo') ?? [];
  const orders = useResource<ExchangeIntent[]>('/exchange-orders');
  const [connectionId, setConnectionId] = useState('');
  const [symbol, setSymbol] = useState('BTC/USDT');
  const [side, setSide] = useState<'buy' | 'sell'>('buy');
  const [quantity, setQuantity] = useState('0.001');
  const [intent, setIntent] = useState<ExchangeIntent>();
  const [confirmation, setConfirmation] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const toast = useToast();
  const reset = () => {
    setIntent(undefined);
    setConfirmation('');
    setError('');
  };
  const preview = async () => {
    setBusy(true);
    setError('');
    try {
      const result = await post<ExchangeIntent>('/exchange-orders/preview', {
        connection_id: connectionId,
        symbol: symbol.trim().toUpperCase(),
        side,
        quantity: Number(quantity),
        idempotency_key: crypto.randomUUID(),
      });
      setIntent(result);
      refresh();
    } catch (reason) {
      setError((reason as Error).message);
    } finally {
      setBusy(false);
    }
  };
  const execute = async () => {
    if (!intent) return;
    setBusy(true);
    setError('');
    try {
      const result = await post<ExchangeIntent>(`/exchange-orders/${intent.id}/confirm`, {
        confirmation,
      });
      setIntent(result);
      refresh();
      toast(
        result.message || `Exchange order ${result.status}.`,
        ['unknown', 'rejected', 'submitting'].includes(result.status),
      );
    } catch (reason) {
      setError((reason as Error).message);
    } finally {
      setBusy(false);
    }
  };
  return (
    <Panel className="full-panel">
      <PanelTitle
        title="Exchange execution"
        subtitle="Actual exchange funds · requires explicit server enablement"
        action={
          <Badge tone={system.data?.allow_live_trading ? 'rose' : 'neutral'}>
            {system.data?.allow_live_trading ? 'Enabled' : 'Disabled by default'}
          </Badge>
        }
      />
      {system.data?.allow_live_trading ? (
        realConnections.length ? (
          <div className="exchange-execution-grid">
            <form
              className="form"
              onSubmit={(event) => {
                event.preventDefault();
                if (intent?.status === 'preview') execute();
                else preview();
              }}
            >
              <label>
                Account
                <select
                  required
                  value={connectionId}
                  disabled={busy}
                  onChange={(event) => {
                    setConnectionId(event.target.value);
                    reset();
                  }}
                >
                  <option value="">Choose a connected account</option>
                  {realConnections.map((connection) => (
                    <option value={connection.id} key={connection.id}>
                      {connection.label} · {connection.sandbox ? 'sandbox' : 'production'}
                    </option>
                  ))}
                </select>
              </label>
              <div className="form-row">
                <label>
                  Market
                  <input
                    required
                    value={symbol}
                    disabled={busy}
                    onChange={(event) => {
                      setSymbol(event.target.value);
                      reset();
                    }}
                    placeholder="BTC/USDT"
                  />
                </label>
                <label>
                  Side
                  <select
                    value={side}
                    disabled={busy}
                    onChange={(event) => {
                      setSide(event.target.value as 'buy' | 'sell');
                      reset();
                    }}
                  >
                    <option value="buy">Buy</option>
                    <option value="sell">Sell</option>
                  </select>
                </label>
              </div>
              <label>
                Base asset quantity
                <input
                  required
                  type="number"
                  min="0.00000001"
                  step="any"
                  value={quantity}
                  disabled={busy}
                  onChange={(event) => {
                    setQuantity(event.target.value);
                    reset();
                  }}
                />
              </label>
              {intent?.status === 'preview' && (
                <>
                  <div className="order-preview">
                    <div>
                      <span>Account</span>
                      <strong>
                        {intent.account} · {intent.sandbox ? 'sandbox' : 'production'}
                      </strong>
                    </div>
                    <div>
                      <span>Reference price</span>
                      <strong>{money(intent.price)}</strong>
                    </div>
                    <div>
                      <span>Reference notional</span>
                      <strong>
                        {number(intent.notional)} {intent.request.symbol.split('/')[1]}
                      </strong>
                    </div>
                    <small>
                      Exchange fees apply. Market fills can differ from the reference price. Preview
                      expires at {new Date(intent.expires_at).toLocaleTimeString()}.
                    </small>
                  </div>
                  <label>
                    Type {intent.confirmation} to confirm
                    <input
                      required
                      value={confirmation}
                      autoComplete="off"
                      onChange={(event) => setConfirmation(event.target.value)}
                    />
                  </label>
                </>
              )}
              {intent && intent.status !== 'preview' && (
                <div className="inline-alert">
                  <span>{intent.message || `Status: ${intent.status}`}</span>
                </div>
              )}
              {error && (
                <p role="alert" className="form-error">
                  {error}
                </p>
              )}
              {(!intent || intent.status === 'preview') && (
                <button
                  className="button rose-button"
                  disabled={
                    busy || (intent?.status === 'preview' && confirmation !== intent.confirmation)
                  }
                  type="submit"
                >
                  <KeyRound size={14} />
                  {busy
                    ? 'Working…'
                    : intent
                      ? 'Confirm exchange market order'
                      : 'Review exchange order'}
                </button>
              )}
              {intent && (
                <button type="button" className="text-button" disabled={busy} onClick={reset}>
                  Prepare a new order
                </button>
              )}
            </form>
            <div className="exchange-review-notes">
              <ShieldCheck size={24} />
              <h3>A deliberate step.</h3>
              <p>
                Review the account, production or sandbox environment, market, side, and quantity
                before confirming. This flow uses your exchange balance and requires a
                trading-enabled key.
              </p>
              <p>
                On an uncertain submission, check your exchange first. Sibyl will not automatically
                retry an exchange order.
              </p>
              <p>Paper strategies and Oracle agents cannot place exchange orders.</p>
            </div>
          </div>
        ) : (
          <Empty title="Connect an exchange first">
            <Link className="text-link" to="/settings?tab=exchanges">
              Add an account <ArrowUpRight size={13} />
            </Link>
          </Empty>
        )
      ) : (
        <div className="execution-disabled">
          <ShieldCheck size={21} />
          <div>
            <strong>Exchange execution is switched off.</strong>
            <p>
              Enable it in server configuration when you’re ready to use a trading-enabled key.
              Paper trading works independently.
            </p>
          </div>
          <Link className="text-link" to="/settings?tab=workspace">
            Configuration <ArrowUpRight size={13} />
          </Link>
        </div>
      )}
      {orders.error && <ErrorState message={orders.error} retry={orders.retry} />}
      {!!orders.data?.length && (
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>Account / market</th>
                <th>Side / quantity</th>
                <th>State</th>
                <th>Client order ID</th>
              </tr>
            </thead>
            <tbody>
              {orders.data.map((order) => (
                <tr key={order.id}>
                  <td>
                    {order.account}
                    <small className="holding-quantity">
                      {order.request.symbol} · {order.sandbox ? 'sandbox' : 'production'}
                    </small>
                  </td>
                  <td>
                    {order.request.side} {number(order.request.quantity, 8)}
                  </td>
                  <td>
                    <Badge
                      tone={
                        ['unknown', 'submitting', 'rejected'].includes(order.status)
                          ? 'rose'
                          : 'neutral'
                      }
                    >
                      {order.status}
                    </Badge>
                  </td>
                  <td>
                    <code>{order.client_order_id}</code>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Panel>
  );
}

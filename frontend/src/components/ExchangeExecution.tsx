import { useState } from 'react';
import { Link } from 'react-router-dom';
import { ArrowUpRight, KeyRound, ShieldCheck } from 'lucide-react';
import { Badge, Empty, Panel, PanelTitle, useToast } from './ui';
import { number, post, refresh } from '../lib/api';
import { useResource } from '../lib/hooks';
import type { Connection, ExchangeCatalog, System } from '../lib/types';
import { OrderMonitor, type ManagedOrder } from './order-monitor';

/** Explicit review for native spot orders and the separate virtual GTC wallet. */
export function ExchangeExecution({
  demo = false,
  active = true,
}: {
  demo?: boolean;
  active?: boolean;
}) {
  const system = useResource<System>('/system');
  const connections = useResource<Connection[]>('/connections');
  const catalog = useResource<ExchangeCatalog>('/exchanges');
  const eligible =
    connections.data?.filter(
      (c) =>
        c.active &&
        (demo ? c.exchange === 'demo' : c.exchange !== 'demo') &&
        catalog.data?.items.some(
          (provider) =>
            provider.id === c.exchange && (demo ? provider.limit_orders : provider.market_orders),
        ),
    ) ?? [];
  const [connectionId, setConnectionId] = useState('');
  const [symbol, setSymbol] = useState('BTC/USDT');
  const [side, setSide] = useState<'buy' | 'sell'>('buy');
  const [quantity, setQuantity] = useState('0.001');
  const [orderType, setOrderType] = useState<'market' | 'limit'>(demo ? 'limit' : 'market');
  const [limitPrice, setLimitPrice] = useState('50000');
  const [intent, setIntent] = useState<ManagedOrder>();
  const [confirmation, setConfirmation] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const toast = useToast();
  const accountId = connectionId || (demo ? eligible[0]?.id : '');
  const reset = () => {
    setIntent(undefined);
    setConfirmation('');
    setError('');
  };
  const submit = async () => {
    setBusy(true);
    setError('');
    try {
      const result =
        intent?.status === 'preview'
          ? await post<ManagedOrder>(`/exchange-orders/${intent.id}/confirm`, { confirmation })
          : await post<ManagedOrder>('/exchange-orders/preview', {
              connection_id: accountId,
              symbol: symbol.trim().toUpperCase(),
              side,
              quantity: Number(quantity),
              order_type: orderType,
              ...(orderType === 'limit' ? { limit_price: Number(limitPrice) } : {}),
              idempotency_key: crypto.randomUUID(),
            });
      setIntent(result);
      refresh();
      if (result.status !== 'preview')
        toast(
          result.message || `Order ${result.status}.`,
          ['unknown', 'rejected'].includes(result.status),
        );
    } catch (reason) {
      setError((reason as Error).message);
    } finally {
      setBusy(false);
    }
  };
  const enabled = demo || system.data?.allow_live_trading;
  return (
    <>
      <Panel className="full-panel">
        <PanelTitle
          title={demo ? 'Paper limit orders' : 'Exchange execution'}
          subtitle={
            demo
              ? 'Resting GTC orders · shared Demo wallet'
              : 'Reviewed spot market & GTC limit orders'
          }
          action={
            <Badge tone={enabled && !demo ? 'rose' : 'neutral'}>
              {demo
                ? 'Demo · virtual funds'
                : enabled
                  ? 'Execution enabled'
                  : 'Disabled by default'}
            </Badge>
          }
        />
        {enabled ? (
          eligible.length ? (
            <div className="exchange-execution-grid">
              <form
                className="form"
                onSubmit={(event) => {
                  event.preventDefault();
                  submit();
                }}
              >
                <label>
                  Account
                  <select
                    required
                    value={accountId || ''}
                    disabled={busy}
                    onChange={(event) => {
                      setConnectionId(event.target.value);
                      reset();
                    }}
                  >
                    <option value="">Choose an active account</option>
                    {eligible.map((c) => (
                      <option key={c.id} value={c.id}>
                        {c.label} · {demo ? 'Demo' : c.sandbox ? 'test' : 'production'}
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
                <div className="form-row">
                  <label>
                    Order type
                    <select
                      value={orderType}
                      disabled={busy || demo}
                      onChange={(event) => {
                        setOrderType(event.target.value as 'market' | 'limit');
                        reset();
                      }}
                    >
                      {!demo && <option value="market">Market</option>}
                      <option value="limit">Limit · GTC</option>
                    </select>
                  </label>
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
                </div>
                {orderType === 'limit' && (
                  <label>
                    Limit price · {symbol.split('/')[1] || 'quote currency'}
                    <input
                      required
                      type="number"
                      min="0.00000001"
                      step="any"
                      value={limitPrice}
                      disabled={busy}
                      onChange={(event) => {
                        setLimitPrice(event.target.value);
                        reset();
                      }}
                    />
                  </label>
                )}
                {intent?.status === 'preview' && (
                  <>
                    <div className="order-preview">
                      <div>
                        <span>Account</span>
                        <strong>
                          {intent.account} · {intent.environment}
                        </strong>
                      </div>
                      <div>
                        <span>{orderType === 'limit' ? 'Limit price' : 'Reference price'}</span>
                        <strong>
                          {number(intent.price, 8)} {intent.request.symbol.split('/')[1]}
                        </strong>
                      </div>
                      <div>
                        <span>
                          {orderType === 'limit' ? 'Order notional' : 'Reference notional'}
                        </span>
                        <strong>
                          {number(intent.notional, 8)} {intent.request.symbol.split('/')[1]}
                        </strong>
                      </div>
                      <small>
                        {demo
                          ? '0.1% paper fee. Available funds are reserved on confirmation.'
                          : 'Exchange fees apply. Buys require a 1% free-balance buffer.'}{' '}
                        Review expires at {new Date(intent.expires_at).toLocaleTimeString()}.{' '}
                        {orderType === 'limit'
                          ? 'Once submitted, GTC remains open until filled or canceled.'
                          : 'Market fills may differ from this quote.'}
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
                    className={`button ${demo ? 'primary' : 'rose-button'}`}
                    disabled={
                      busy || (intent?.status === 'preview' && confirmation !== intent.confirmation)
                    }
                    type="submit"
                  >
                    <KeyRound size={14} />
                    {busy
                      ? 'Working…'
                      : intent
                        ? `Confirm ${demo ? 'paper' : 'exchange'} ${orderType} order`
                        : `Review ${demo ? 'paper limit' : 'exchange'} order`}
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
                <h3>{demo ? 'Room to let an order rest.' : 'Review, submit, follow.'}</h3>
                <p>
                  {demo
                    ? 'A buy reserves quote currency plus its paper fee. A sell reserves the base asset. Market orders cannot spend those funds until the limit fills or is canceled.'
                    : 'Review your account, environment, market, side, quantity and price. Native execution is enabled only for Binance, Coinbase Advanced, Kraken and the Binance / Coinbase test environments.'}
                </p>
                <p>
                  {demo
                    ? 'The Demo bid/ask feed advances orders when checked or tracked. Crossing fills the entire quantity at your limit; this is a simple simulation without liquidity or queue modeling.'
                    : 'Track cumulative fills and request cancellation below. Unknown submissions or cancellations are never automatically retried. Check the native order and displayed client ID before placing another.'}
                </p>
                <p>
                  Tracking survives a server restart. Agents and strategy jobs cannot place these
                  orders.
                </p>
              </div>
            </div>
          ) : (
            <Empty title="Activate a supported account first">
              <Link className="text-link" to="/settings?tab=exchanges">
                Manage accounts <ArrowUpRight size={13} />
              </Link>
            </Empty>
          )
        ) : (
          <div className="execution-disabled">
            <ShieldCheck size={21} />
            <div>
              <strong>Exchange execution is switched off.</strong>
              <p>
                Enable it in server configuration to submit new orders. Existing status checks and
                reviewed cancellations remain available.
              </p>
            </div>
            <Link className="text-link" to="/settings?tab=workspace">
              Configuration <ArrowUpRight size={13} />
            </Link>
          </div>
        )}
      </Panel>
      <OrderMonitor active={active} />
    </>
  );
}

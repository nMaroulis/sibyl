import { useState } from 'react';
import { GitBranch, Repeat2 } from 'lucide-react';
import { Modal, Badge, useToast } from '../ui';
import { number, post, refresh } from '../../lib/api';
import type { ManagedOrder } from '../order-monitor';

type Group = {
  id: string;
  status: string;
  confirmation: string;
  expires_at: string;
  environment: string;
  account: string;
  orders: ManagedOrder[];
  message?: string;
};

/** Native linked alternatives. Kept in a disclosure so ordinary order entry stays focused. */
export function OCOForm({
  accountId,
  symbol,
  side,
  quantity,
}: {
  accountId: string;
  symbol: string;
  side: 'buy' | 'sell';
  quantity: string;
}) {
  const [take, setTake] = useState(''),
    [stop, setStop] = useState(''),
    [limit, setLimit] = useState('');
  const [group, setGroup] = useState<Group>(),
    [phrase, setPhrase] = useState('');
  const [busy, setBusy] = useState(false),
    [error, setError] = useState('');
  const reset = () => {
    setGroup(undefined);
    setPhrase('');
    setError('');
  };
  const submit = async () => {
    setBusy(true);
    setError('');
    try {
      const result =
        group?.status === 'preview'
          ? await post<Group>(`/exchange-order-lists/${group.id}/confirm`, { confirmation: phrase })
          : await post<Group>('/exchange-order-lists/preview', {
              connection_id: accountId,
              symbol,
              side,
              quantity: Number(quantity),
              take_profit_price: Number(take),
              trigger_price: Number(stop),
              limit_price: Number(limit),
              idempotency_key: crypto.randomUUID(),
            });
      setGroup(result);
      refresh();
    } catch (reason) {
      setError((reason as Error).message);
    } finally {
      setBusy(false);
    }
  };
  return (
    <details className="advanced-order-disclosure">
      <summary>
        <GitBranch size={17} />
        <span>
          Linked take-profit & stop-loss <small>Native OCO · two alternative limits</small>
        </span>
      </summary>
      <div className="advanced-order-content">
        <p>
          {side === 'sell' ? 'Sell' : 'Buy'} {quantity} {symbol.split('/')[0]} on the account
          selected above. The exchange links the two legs and reserves one quantity. Activation of
          one cancels the other; either limit can remain unfilled.
        </p>
        <form
          onSubmit={(event) => {
            event.preventDefault();
            void submit();
          }}
        >
          <div className="workspace-controls">
            {[
              [take, setTake, 'Take-profit trigger / limit'],
              [stop, setStop, 'Stop trigger'],
              [limit, setLimit, 'Stop limit'],
            ].map(([value, setter, label]) => (
              <label key={label as string}>
                {label as string} · {symbol.split('/')[1]}
                <input
                  type="number"
                  min="0.00000001"
                  step="any"
                  required
                  value={value as string}
                  disabled={busy}
                  onChange={(event) => {
                    (setter as (value: string) => void)(event.target.value);
                    reset();
                  }}
                />
              </label>
            ))}
          </div>
          {group && (
            <div className="order-preview">
              <Badge tone={group.environment === 'test' ? 'sand' : 'rose'}>
                {group.environment}
              </Badge>
              <strong>
                {group.account} · {group.status}
              </strong>
              <p>
                {group.message ||
                  'Two saved leg identities share this list. Track both in the order monitor.'}
              </p>
              {group.status === 'preview' && (
                <label>
                  Type {group.confirmation}
                  <input
                    required
                    value={phrase}
                    onChange={(event) => setPhrase(event.target.value)}
                    autoComplete="off"
                  />
                </label>
              )}
            </div>
          )}
          {error && (
            <p role="alert" className="form-error">
              {error}
            </p>
          )}
          {!group || group.status === 'preview' ? (
            <button
              className="button secondary"
              disabled={busy || (!!group && phrase !== group.confirmation)}
            >
              {busy ? 'Checking…' : group ? 'Confirm native OCO' : 'Review linked orders'}
            </button>
          ) : (
            <button className="text-button" type="button" onClick={reset}>
              New review
            </button>
          )}
        </form>
      </div>
    </details>
  );
}

/** Native STOP_ON_FAILURE is not atomic: the old order can cancel while the new one fails. */
export function ReplaceOrder({ order, close }: { order: ManagedOrder; close: () => void }) {
  const [quantity, setQuantity] = useState(String(order.request.quantity ?? ''));
  const [price, setPrice] = useState(String(order.request.limit_price ?? order.price ?? ''));
  const [review, setReview] = useState<ManagedOrder>(),
    [phrase, setPhrase] = useState('');
  const [busy, setBusy] = useState(false),
    [error, setError] = useState('');
  const toast = useToast();
  const submit = async () => {
    setBusy(true);
    setError('');
    try {
      const result = review
        ? await post<ManagedOrder>(`/exchange-orders/${review.id}/confirm`, {
            confirmation: phrase,
          })
        : await post<ManagedOrder>(`/exchange-orders/${order.id}/replace/preview`, {
            quantity: Number(quantity),
            limit_price: Number(price),
            idempotency_key: crypto.randomUUID(),
          });
      setReview(result);
      refresh();
      if (result.status !== 'preview') {
        toast(result.message || `Replacement ${result.status}.`, result.status === 'unknown');
        close();
      }
    } catch (reason) {
      setError((reason as Error).message);
    } finally {
      setBusy(false);
    }
  };
  return (
    <Modal title="Replace an unfilled limit" onClose={close}>
      <form
        className="form"
        onSubmit={(event) => {
          event.preventDefault();
          void submit();
        }}
      >
        <p>
          {order.account} · {order.environment} · {order.request.symbol}
        </p>
        <p>
          Only wholly unfilled manual limits are eligible. If the original fills first, the native
          replacement is refused. Cancellation may succeed while the new order fails; inspect both
          records before taking another action.
        </p>
        <label>
          New total base quantity
          <input
            type="number"
            min="0.00000001"
            step="any"
            required
            value={quantity}
            disabled={!!review || busy}
            onChange={(event) => setQuantity(event.target.value)}
          />
        </label>
        <label>
          New limit price
          <input
            type="number"
            min="0.00000001"
            step="any"
            required
            value={price}
            disabled={!!review || busy}
            onChange={(event) => setPrice(event.target.value)}
          />
        </label>
        {review && (
          <>
            <p>
              New notional: {number(review.notional ?? 0, 8)}. Review expires at{' '}
              {new Date(review.expires_at).toLocaleTimeString()}.
            </p>
            <label>
              Type {review.confirmation}
              <input
                value={phrase}
                onChange={(event) => setPhrase(event.target.value)}
                autoComplete="off"
                required
              />
            </label>
          </>
        )}
        {error && (
          <p role="alert" className="form-error">
            {error}
          </p>
        )}
        <button
          className="button primary"
          disabled={busy || (!!review && phrase !== review.confirmation)}
        >
          <Repeat2 size={15} />
          {busy ? 'Checking…' : review ? 'Confirm cancel / replace' : 'Review replacement'}
        </button>
      </form>
    </Modal>
  );
}

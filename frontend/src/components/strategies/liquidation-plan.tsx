import { useState } from 'react';
import { ListOrdered, Square } from 'lucide-react';
import { Link } from 'react-router-dom';
import { number, post, refresh } from '../../lib/api';
import { useResource } from '../../lib/hooks';
import type { Job } from '../../lib/types';
import { Badge, ErrorState, Loading, Modal, useToast } from '../ui';

type Policy = {
  max_orders: number;
  max_order_base: number | null;
  duration_minutes: number;
  price_limit_bps: number;
  max_spread_bps: number;
  fee_reserve_bps: number;
  order_lifetime_seconds: number;
};

type Plan = {
  id: string;
  status: string;
  message: string;
  owned_quantity: number;
  max_orders: number;
  max_order_base: number | null;
  duration_minutes: number;
  minimum_price: number;
  first_order_quantity: number;
  expires_at: string;
  ends_at?: string;
  confirmation: string;
  policy: Policy;
};
type SavedPlan = Plan & {
  orders: { id: string; status: string; price: number; filled: number | null }[];
};

const defaultPolicy: Policy = {
  max_orders: 3,
  max_order_base: null,
  duration_minutes: 20,
  price_limit_bps: 25,
  max_spread_bps: 50,
  fee_reserve_bps: 100,
  order_lifetime_seconds: 120,
};

/** Review a sell envelope once, then observe each linked order from the worker. */
export function LiquidationPlan({ job, live }: { job: Job; live: boolean }) {
  const path = `/strategies/exchange/jobs/${encodeURIComponent(job.id)}/liquidation`;
  const state = useResource<SavedPlan | null>(path, live ? 5000 : 0);
  const current = state.data;
  const [open, setOpen] = useState(false);
  const [review, setReview] = useState<Plan>();
  const [confirmation, setConfirmation] = useState('');
  const [policy, setPolicy] = useState(defaultPolicy);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const toast = useToast();
  const [base, quote] = job.parameters.symbol.split('/');
  const stage = async (action: 'preview' | 'approve' | 'stop') => {
    setError('');
    setBusy(true);
    try {
      if (action === 'preview') {
        setReview(await post<Plan>(`${path}/preview`, policy));
        setConfirmation('');
      } else {
        if (action === 'approve' && review) {
          await post(`${path}/${review.id}/confirm`, { confirmation });
          toast('Liquidation authorized');
        }
        if (action === 'stop' && current) {
          await post(`${path}/${current.id}/stop`);
          toast('Future sells stopped');
        }
        setReview(undefined);
        refresh();
      }
    } catch (reason) {
      setError((reason as Error).message);
    } finally {
      setBusy(false);
    }
  };
  if (!current && job.quantity <= 1e-12) return null;
  return (
    <>
      <button
        className="button secondary"
        onClick={() => {
          setReview(undefined);
          setError('');
          setOpen(true);
        }}
      >
        <ListOrdered size={14} />
        {current?.status === 'active'
          ? `Liquidation · ${current.orders.length}/${current.max_orders}`
          : 'Liquidation plan'}
      </button>
      {open && (
        <Modal
          title={review ? 'Review liquidation plan' : 'Strategy liquidation'}
          onClose={() => !busy && setOpen(false)}
        >
          <div className="form strategy-close-form">
            <Badge tone={job.environment === 'test' ? 'sand' : 'rose'}>
              {job.environment === 'test' ? 'Exchange test funds' : 'Real exchange funds'}
            </Badge>
            <p>
              <strong>{job.account}</strong> · {job.parameters.symbol}
            </p>
            {state.error && <ErrorState message={state.error} retry={state.retry} />}
            {state.loading && <Loading />}
            {error && (
              <p className="form-error" role="alert">
                {error}
              </p>
            )}
            {current && !review && (
              <>
                <div className="inline-alert">
                  <strong>{current.status}</strong> · {current.message}
                  <small className="table-subline">
                    {current.orders.length}/{current.max_orders} orders · Minimum{' '}
                    {number(current.minimum_price, 8)} {quote}
                    {current.ends_at && ` · Ends ${new Date(current.ends_at).toLocaleTimeString()}`}
                  </small>
                </div>
                {current.orders.map((order, index) => (
                  <div key={order.id} className="workspace-controls">
                    <Badge>
                      Sell {index + 1} · {order.status}
                    </Badge>
                    <span>
                      {order.filled == null
                        ? 'Fill pending'
                        : `${number(order.filled, 8)} ${base} filled`}
                    </span>
                    <Link to="/trade?tab=executions" title={order.id}>
                      Trade ↗
                    </Link>
                  </div>
                ))}
                {current.status === 'active' && (
                  <button
                    className="button secondary"
                    disabled={busy}
                    onClick={() => void stage('stop')}
                  >
                    <Square size={12} /> Stop future sells
                  </button>
                )}
              </>
            )}
            {review ? (
              <>
                <dl>
                  <dt>Owned position at approval</dt>
                  <dd>
                    {number(review.owned_quantity, 8)} {base}
                  </dd>
                  <dt>First sell</dt>
                  <dd>
                    Up to {number(review.first_order_quantity, 8)} {base}
                  </dd>
                  <dt>Fixed limit price</dt>
                  <dd>
                    {number(review.minimum_price, 8)} {quote}
                  </dd>
                  {review.max_order_base != null && (
                    <>
                      <dt>Maximum size per sell</dt>
                      <dd>
                        {number(review.max_order_base, 8)} {base}
                      </dd>
                    </>
                  )}
                  <dt>Order and time limits</dt>
                  <dd>
                    {review.max_orders} sells · {review.duration_minutes} minutes ·{' '}
                    {review.policy.order_lifetime_seconds}s per order
                  </dd>
                  <dt>Spread limit and base-fee reserve</dt>
                  <dd>
                    {review.policy.max_spread_bps} bps spread · {review.policy.fee_reserve_bps} bps
                    reserve
                  </dd>
                </dl>
                <p className="footnote">
                  Each order must reconcile before the next. Residual units may remain. This review
                  expires at {new Date(review.expires_at).toLocaleTimeString()}.
                </p>
                <label>
                  Type <strong>{review.confirmation}</strong>
                  <input
                    autoComplete="off"
                    value={confirmation}
                    onChange={(e) => setConfirmation(e.target.value)}
                  />
                </label>
                <div className="workspace-controls">
                  <button
                    className="button secondary"
                    disabled={busy}
                    onClick={() => setReview(undefined)}
                  >
                    Back
                  </button>
                  <button
                    className="button primary"
                    disabled={busy || confirmation !== review.confirmation}
                    onClick={() => void stage('approve')}
                  >
                    Approve sell sequence
                  </button>
                </div>
              </>
            ) : (
              current?.status !== 'active' &&
              job.quantity > 1e-12 &&
              !state.loading &&
              !state.error && (
                <form
                  className="form"
                  onSubmit={(e) => {
                    e.preventDefault();
                    void stage('preview');
                  }}
                >
                  <p className="footnote">
                    Set the limits for a sequence of sells from this stopped run. A fresh exchange
                    quote sets the fixed price floor.
                  </p>
                  <div className="workspace-controls">
                    <label>
                      Maximum orders
                      <input
                        required
                        type="number"
                        min={2}
                        max={5}
                        value={policy.max_orders}
                        onChange={(e) =>
                          setPolicy({ ...policy, max_orders: Number(e.target.value) })
                        }
                      />
                    </label>
                    <label>
                      Plan duration (min)
                      <input
                        required
                        type="number"
                        min={5}
                        max={60}
                        value={policy.duration_minutes}
                        onChange={(e) =>
                          setPolicy({ ...policy, duration_minutes: Number(e.target.value) })
                        }
                      />
                    </label>
                  </div>
                  <label>
                    Maximum size per sell ({base})
                    <input
                      type="number"
                      min={0}
                      max={1000000}
                      step="any"
                      placeholder="Use native limits"
                      value={policy.max_order_base ?? ''}
                      onChange={(e) =>
                        setPolicy({
                          ...policy,
                          max_order_base: e.target.value === '' ? null : Number(e.target.value),
                        })
                      }
                    />
                  </label>
                  <details>
                    <summary>Order safeguards</summary>
                    <div className="form">
                      <label>
                        Price allowance below bid (bps)
                        <input
                          type="number"
                          required
                          min={1}
                          max={200}
                          value={policy.price_limit_bps}
                          onChange={(e) =>
                            setPolicy({ ...policy, price_limit_bps: Number(e.target.value) })
                          }
                        />
                      </label>
                      <label>
                        Max spread (bps)
                        <input
                          type="number"
                          required
                          min={1}
                          max={500}
                          value={policy.max_spread_bps}
                          onChange={(e) =>
                            setPolicy({ ...policy, max_spread_bps: Number(e.target.value) })
                          }
                        />
                      </label>
                      <label>
                        Base-fee reserve (bps)
                        <input
                          type="number"
                          required
                          min={10}
                          max={500}
                          value={policy.fee_reserve_bps}
                          onChange={(e) =>
                            setPolicy({ ...policy, fee_reserve_bps: Number(e.target.value) })
                          }
                        />
                      </label>
                      <label>
                        Order expiry (seconds)
                        <input
                          type="number"
                          required
                          min={60}
                          max={300}
                          value={policy.order_lifetime_seconds}
                          onChange={(e) =>
                            setPolicy({ ...policy, order_lifetime_seconds: Number(e.target.value) })
                          }
                        />
                      </label>
                    </div>
                  </details>
                  <button className="button primary" type="submit" disabled={busy}>
                    {busy ? 'Checking exchange…' : 'Review sell sequence'}
                  </button>
                </form>
              )
            )}
          </div>
        </Modal>
      )}
    </>
  );
}

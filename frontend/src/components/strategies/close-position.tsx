import { useState } from 'react';
import { Link } from 'react-router-dom';
import { ArrowDownToLine, RefreshCw } from 'lucide-react';
import { Badge, Modal, useToast } from '../ui';
import { useResource } from '../../lib/hooks';
import { number, post, refresh } from '../../lib/api';
import type { Job } from '../../lib/types';

type Policy = {
  price_limit_bps: number;
  max_spread_bps: number;
  fee_reserve_bps: number;
  order_lifetime_seconds: number | null;
};
type Context = {
  ready: boolean;
  reason: string | null;
  quantity: number;
  account: string;
  exchange: string;
  environment: string;
  symbol: string;
};
type Review = Pick<Context, 'account' | 'exchange' | 'environment' | 'symbol'> & {
  id: string;
  confirmation: string;
  expires_at: string;
  owned_quantity: number;
  quantity: number;
  limit_price: number;
  reference_bid: number;
  base_fee_reserve: number;
  proceeds_before_fees: number;
  quote_fee_allowance: number;
  residual_before_fees: number;
  residual_is_dust: boolean;
  policy: Policy;
};

/** Explicit one-order exit review. Viewing it never stops, cancels or sells anything. */
export function ClosePosition({ job }: { job: Job }) {
  const [open, setOpen] = useState(false);
  const [review, setReview] = useState<Review>();
  const [confirmation, setConfirmation] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [policy, setPolicy] = useState<Policy>({
    price_limit_bps: 25,
    max_spread_bps: 50,
    fee_reserve_bps: 100,
    order_lifetime_seconds: 300,
  });
  const context = useResource<Context>(
    `/strategies/exchange/jobs/${job.id}/close-position`,
    5000,
    open,
  );
  const toast = useToast();
  const [base, quote] = job.parameters.symbol.split('/');
  const inspect = async () => {
    setBusy(true);
    setError('');
    try {
      setReview(await post<Review>(`/strategies/exchange/jobs/${job.id}/close-preview`, policy));
      setConfirmation('');
    } catch (reason) {
      setError((reason as Error).message);
    } finally {
      setBusy(false);
    }
  };
  const approve = async () => {
    if (!review) return;
    setBusy(true);
    setError('');
    try {
      const result = await post<Job>(`/strategies/exchange/close-reviews/${review.id}/confirm`, {
        confirmation,
      });
      setOpen(false);
      setReview(undefined);
      refresh();
      const failed = ['unknown', 'interrupted', 'rejected'].includes(
        result.close_position?.state ?? '',
      );
      toast(
        failed
          ? result.close_position!.message
          : 'Exit approval recorded. Follow the native order and remaining position in the monitor.',
        failed,
      );
    } catch (reason) {
      setError((reason as Error).message);
    } finally {
      setBusy(false);
    }
  };
  if (job.quantity <= 1e-12 && !job.close_position) return null;
  return (
    <>
      <button
        className="button secondary"
        onClick={() => {
          setReview(undefined);
          setConfirmation('');
          setError('');
          setOpen(true);
        }}
      >
        <ArrowDownToLine size={14} />{' '}
        {job.quantity <= 1e-12 ||
        (job.close_position &&
          !['reconciled', 'rejected', 'interrupted'].includes(job.close_position.state))
          ? 'View exit'
          : 'Close position'}
      </button>
      {open && (
        <Modal
          title={review ? 'Review position exit' : 'Close strategy position'}
          onClose={() => !busy && setOpen(false)}
        >
          <div className="form strategy-close-form">
            <Badge tone={job.environment === 'test' ? 'sand' : 'rose'}>
              {job.environment === 'test' ? 'Exchange test funds' : 'Real exchange funds'}
            </Badge>
            <p>
              <strong>{job.account}</strong> · {job.exchange} · {job.parameters.symbol}
            </p>
            {context.loading && <p className="footnote">Checking retained ownership…</p>}
            {context.error && (
              <p className="form-error" role="alert">
                {context.error}
              </p>
            )}
            {review ? (
              <>
                <div className="strategy-close-quote">
                  <div>
                    <small>Strategy-owned · {base}</small>
                    <strong>{number(review.owned_quantity, 8)}</strong>
                  </div>
                  <div>
                    <small>Sell quantity · {base}</small>
                    <strong>{number(review.quantity, 8)}</strong>
                  </div>
                  <div>
                    <small>
                      Limit floor · {quote} / {base}
                    </small>
                    <strong>{number(review.limit_price, 8)}</strong>
                  </div>
                  <div>
                    <small>Proceeds at floor, before fees · {quote}</small>
                    <strong>{number(review.proceeds_before_fees, 8)}</strong>
                  </div>
                  <div>
                    <small>Base-fee reserve · {base}</small>
                    <strong>{number(review.base_fee_reserve, 8)}</strong>
                  </div>
                  <div>
                    <small>Residual before fees · {base}</small>
                    <strong>{number(review.residual_before_fees, 8)}</strong>
                  </div>
                </div>
                <p className="monitor-notice">
                  Approves one GTC limit sell, sized from this strategy’s native fills. The original
                  entry-order value cap and loss latch do not apply to this separately reviewed
                  exit. It can remain open or fill partially. No additional sell or replacement is
                  automatic.
                </p>
                <p className="footnote">
                  {review.residual_is_dust
                    ? 'The estimated residual is below the current tradable minimum. '
                    : 'A fee reserve, precision or native size cap can leave tradable units. '}
                  Remaining units stay owned; further tradable sells need a fresh review. Actual
                  fees are set by the exchange; the buffer is not a fee quote. A quote-fee allowance
                  of {number(review.quote_fee_allowance, 8)} {quote} is illustrative and may reduce
                  proceeds if fees use that currency.
                </p>
                <p className="footnote">
                  Residual ownership keeps this account/pair assigned to the stopped run. Dust
                  cannot be sold below native minimums; ownership handoff to another run is not
                  available yet.
                </p>
                <p className="footnote">
                  {review.policy.order_lifetime_seconds == null
                    ? 'No automatic expiry. '
                    : `Request cancellation after ${review.policy.order_lifetime_seconds} seconds, subject to backend availability and account/live-order permission. `}
                  The earlier Stop &amp; cancel approval does not cancel this new exit. Unknown
                  writes are never replayed. Review expires{' '}
                  {new Date(review.expires_at).toLocaleTimeString()}.
                </p>
                <label>
                  Type <strong>{review.confirmation}</strong>
                  <input
                    value={confirmation}
                    onChange={(event) => setConfirmation(event.target.value)}
                    autoComplete="off"
                  />
                </label>
                <div className="strategy-close-actions">
                  <button
                    className="button secondary"
                    disabled={busy}
                    onClick={() => {
                      setReview(undefined);
                      setError('');
                    }}
                  >
                    Back to options
                  </button>
                  <button
                    className="button primary"
                    disabled={busy || confirmation !== review.confirmation}
                    onClick={approve}
                  >
                    {busy ? 'Submitting exit…' : 'Approve & submit sell'}
                  </button>
                </div>
              </>
            ) : (
              context.data && (
                <>
                  <p>
                    Retained position:{' '}
                    <strong>
                      {number(context.data.quantity, 8)} {base}
                    </strong>
                    . Closing uses this run’s acquired units and leaves unrelated account holdings
                    alone.
                  </p>
                  {!context.data.ready ? (
                    <>
                      <p className="monitor-notice">{context.data.reason}</p>
                      <p className="footnote">
                        For an active run, return to its header and use Stop &amp; cancel orders.
                        Cancellation and fill checks continue in the background. This dialog updates
                        readiness every five seconds.
                      </p>
                      <div className="strategy-close-actions">
                        <button className="button secondary" onClick={() => setOpen(false)}>
                          Back to run
                        </button>
                        <Link className="text-link" to="/trade?tab=executions">
                          Inspect orders in Trade →
                        </Link>
                        <button
                          className="icon-button"
                          aria-label="Refresh closing readiness"
                          onClick={context.retry}
                        >
                          <RefreshCw size={14} />
                        </button>
                      </div>
                    </>
                  ) : (
                    <>
                      <p className="footnote">
                        Review one price-capped exit from a fresh exchange book and free balance. A
                        fee reserve or venue limit can leave units behind. Viewing a review places
                        no order.
                      </p>
                      <label>
                        Cancel unfilled exit after
                        <select
                          value={policy.order_lifetime_seconds ?? ''}
                          onChange={(event) =>
                            setPolicy({
                              ...policy,
                              order_lifetime_seconds: event.target.value
                                ? Number(event.target.value)
                                : null,
                            })
                          }
                        >
                          <option value="">No automatic expiry · GTC</option>
                          <option value="60">1 minute</option>
                          <option value="300">5 minutes</option>
                          <option value="900">15 minutes</option>
                          <option value="3600">1 hour</option>
                          <option value="86400">1 day</option>
                        </select>
                      </label>
                      <details className="advanced-options">
                        <summary>Exit limits &amp; fee reserve</summary>
                        <label>
                          Sell price allowance · bps
                          <input
                            type="number"
                            min="1"
                            max="200"
                            value={policy.price_limit_bps}
                            onChange={(event) =>
                              setPolicy({ ...policy, price_limit_bps: Number(event.target.value) })
                            }
                          />
                        </label>
                        <label>
                          Maximum spread · bps
                          <input
                            type="number"
                            min="1"
                            max="500"
                            value={policy.max_spread_bps}
                            onChange={(event) =>
                              setPolicy({ ...policy, max_spread_bps: Number(event.target.value) })
                            }
                          />
                        </label>
                        <label>
                          Base-fee reserve · bps
                          <input
                            type="number"
                            min="10"
                            max="500"
                            value={policy.fee_reserve_bps}
                            onChange={(event) =>
                              setPolicy({ ...policy, fee_reserve_bps: Number(event.target.value) })
                            }
                          />
                        </label>
                      </details>
                      <button className="button primary" disabled={busy} onClick={inspect}>
                        {busy ? 'Reading exchange…' : 'Review exit order'}
                      </button>
                    </>
                  )}
                </>
              )
            )}
            {error && (
              <p className="form-error" role="alert">
                {error}
              </p>
            )}
          </div>
        </Modal>
      )}
    </>
  );
}

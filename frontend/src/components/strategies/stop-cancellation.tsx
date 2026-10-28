import { useState } from 'react';
import { Square } from 'lucide-react';
import { Badge, Modal, useToast } from '../ui';
import { number, post, refresh } from '../../lib/api';
import type { Job } from '../../lib/types';

type Review = {
  id: string;
  account: string;
  exchange: string;
  symbol: string;
  environment: string;
  quantity: number;
  confirmation: string;
  expires_at: string;
  orders: {
    id: string;
    status: string;
    filled?: number;
    remaining?: number;
    exchange_order_id?: string;
  }[];
};

/** Separate explicit approval: stop the run and cancel its orders, retaining every holding. */
export function StopCancellation({ job }: { job: Job }) {
  const [review, setReview] = useState<Review>();
  const [confirmation, setConfirmation] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const toast = useToast();
  const inspect = async () => {
    setBusy(true);
    setError('');
    try {
      setReview(await post<Review>(`/strategies/exchange/jobs/${job.id}/stop-cancel-review`));
      setConfirmation('');
    } catch (reason) {
      toast((reason as Error).message, true);
    } finally {
      setBusy(false);
    }
  };
  const approve = async () => {
    if (!review) return;
    setBusy(true);
    setError('');
    try {
      await post<Job>(`/strategies/exchange/stop-reviews/${review.id}/confirm`, { confirmation });
      setReview(undefined);
      refresh();
      toast(
        'Strategy stopped. Outstanding-order cancellation is queued; check its native outcome.',
      );
    } catch (reason) {
      setError((reason as Error).message);
    } finally {
      setBusy(false);
    }
  };
  if (job.stop_cancellation) return null;
  return (
    <>
      <button className="button secondary monitor-stop" disabled={busy} onClick={inspect}>
        <Square size={12} /> {busy ? 'Reading run…' : 'Stop & cancel orders'}
      </button>
      {review && (
        <Modal
          title="Stop & cancel this run’s orders?"
          onClose={() => !busy && setReview(undefined)}
        >
          <div className="form">
            <Badge tone={review.environment === 'test' ? 'sand' : 'rose'}>
              {review.environment === 'test' ? 'Exchange test funds' : 'Real exchange funds'}
            </Badge>
            <p>
              <strong>{review.account}</strong> · {review.exchange} · {review.symbol}
            </p>
            <p>
              Stops new submissions permanently before queuing this run’s outstanding orders for
              cancellation. A submission already in flight may finish first and is included. This
              does not sell the {number(review.quantity, 8)} {review.symbol.split('/')[0]}{' '}
              strategy-owned position.
            </p>
            <p className="monitor-notice">
              Cancellation is requested by the backend worker, not confirmed by this approval.
              Active account access and the backend live-trading flag are required. Unknown
              cancellation attempts are observed but never automatically repeated; resolve them in
              Trade. Fills racing cancellation remain owned.
            </p>
            {review.orders.length ? (
              <div className="table-scroll">
                <table>
                  <thead>
                    <tr>
                      <th>Order</th>
                      <th>Recorded state</th>
                      <th>Filled / remaining</th>
                    </tr>
                  </thead>
                  <tbody>
                    {review.orders.map((order) => (
                      <tr key={order.id}>
                        <td>
                          <code>{order.id.slice(0, 12)}</code>
                        </td>
                        <td>{order.status}</td>
                        <td>
                          {order.filled == null ? '—' : number(order.filled, 8)} /{' '}
                          {order.remaining == null ? '—' : number(order.remaining, 8)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <p className="footnote">
                No outstanding orders are recorded right now. Any in-flight submission is checked
                after stopping.
              </p>
            )}
            <p className="footnote">
              Review expires {new Date(review.expires_at).toLocaleTimeString()}.
            </p>
            <label>
              Type <strong>{review.confirmation}</strong>
              <input
                value={confirmation}
                onChange={(event) => setConfirmation(event.target.value)}
                autoComplete="off"
              />
            </label>
            {error && (
              <p className="form-error" role="alert">
                {error}
              </p>
            )}
            <button
              className="button primary"
              disabled={busy || confirmation !== review.confirmation}
              onClick={approve}
            >
              {busy ? 'Stopping…' : 'Stop & request cancellation'}
            </button>
          </div>
        </Modal>
      )}
    </>
  );
}

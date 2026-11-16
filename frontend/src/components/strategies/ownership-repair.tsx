import { useState } from 'react';
import { FileCheck2 } from 'lucide-react';
import { Link } from 'react-router-dom';
import { number, post, refresh } from '../../lib/api';
import { useResource } from '../../lib/hooks';
import { monitorURL } from '../../lib/strategy-monitor';
import { ErrorState, Loading, Modal, useToast } from '../ui';

type Repair = {
  id: string;
  confirmation: string;
  approved_at?: string;
  runs: {
    job_id: string;
    symbol: string;
    status: string;
    quantity: number;
    entry_cost: number;
    realized_pnl: number;
  }[];
  adjustments: {
    event_id: string;
    job_id: string;
    action: string;
    previous_cost_basis: number;
    cost_basis: number;
  }[];
};

export function OwnershipRepairDialog({
  jobId,
  receiptId,
  close,
}: {
  jobId: string;
  receiptId?: string;
  close: () => void;
}) {
  const path = `/strategies/exchange/jobs/${encodeURIComponent(jobId)}/ownership`;
  const review = useResource<Repair>(
    receiptId ? `${path}/repairs/${encodeURIComponent(receiptId)}` : `${path}/repair`,
  );
  const [confirmation, setConfirmation] = useState('');
  const [busy, setBusy] = useState(false);
  const toast = useToast();
  const data = review.data;
  const quote = data?.runs[0]?.symbol.split('/')[1];
  const approve = async () => {
    if (!data) return;
    setBusy(true);
    try {
      await post(`${path}/repair`, { review_id: data.id, confirmation });
      toast('Ownership basis repaired');
      refresh();
      close();
    } catch (error) {
      toast((error as Error).message, true);
      setConfirmation('');
      review.retry();
    } finally {
      setBusy(false);
    }
  };
  return (
    <Modal
      title={receiptId ? 'Ownership repair receipt' : 'Review ownership repair'}
      onClose={() => !busy && close()}
    >
      {review.error && <ErrorState message={review.error} retry={review.retry} />}
      {review.loading && !data && <Loading />}
      {data && (
        <div className="form">
          <p className="footnote">
            {data.approved_at ? `Approved ${new Date(data.approved_at).toLocaleString()}. ` : ''}
            Original receipt quantities and cash-flow values are retained. The repair recalculates
            cost basis and realized trade P&amp;L.
          </p>
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Run</th>
                  <th>Owned units</th>
                  <th>Repaired basis · {quote}</th>
                  <th>Realized P&amp;L · {quote}</th>
                </tr>
              </thead>
              <tbody>
                {data.runs.map((run) => (
                  <tr key={run.job_id}>
                    <td>
                      <Link to={monitorURL(run.job_id)} onClick={close}>
                        {run.job_id.slice(0, 8)} ↗
                      </Link>
                    </td>
                    <td>{number(run.quantity, 8)}</td>
                    <td>{number(run.entry_cost, 8)}</td>
                    <td>{number(run.realized_pnl, 8)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <details>
            <summary>Replayed receipts ({data.adjustments.length})</summary>
            <ul>
              {data.adjustments.map((row) => (
                <li key={row.event_id}>
                  {row.job_id.slice(0, 8)} · {row.action.replaceAll('_', ' ')} ·{' '}
                  {number(row.previous_cost_basis, 8)} → {number(row.cost_basis, 8)} {quote}
                </li>
              ))}
            </ul>
          </details>
          {!receiptId && (
            <>
              <label>
                Type <strong>{data.confirmation}</strong>
                <input
                  value={confirmation}
                  autoComplete="off"
                  onChange={(e) => setConfirmation(e.target.value)}
                />
              </label>
              <button
                className="button primary"
                disabled={busy || !!review.error || confirmation !== data.confirmation}
                onClick={() => void approve()}
              >
                <FileCheck2 size={15} /> {busy ? 'Saving…' : 'Approve basis repair'}
              </button>
            </>
          )}
        </div>
      )}
    </Modal>
  );
}

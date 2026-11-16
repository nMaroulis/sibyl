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
  allow_quantity_changes?: boolean;
  repair_releases?: boolean;
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
    previous_quantity?: number;
    quantity?: number;
    previous_reference_value?: number;
    reference_value?: number;
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
  const [allowQuantity, setAllowQuantity] = useState(false);
  const [repairReleases, setRepairReleases] = useState(false);
  const review = useResource<Repair>(
    receiptId
      ? `${path}/repairs/${encodeURIComponent(receiptId)}`
      : `${path}/repair?allow_quantity_changes=${allowQuantity}&repair_releases=${repairReleases}`,
  );
  const [confirmation, setConfirmation] = useState('');
  const [busy, setBusy] = useState(false);
  const toast = useToast();
  const data =
    receiptId ||
    ((review.data?.allow_quantity_changes ?? false) === allowQuantity &&
      (review.data?.repair_releases ?? false) === repairReleases)
      ? review.data
      : undefined;
  const [base, quote] = data?.runs[0]?.symbol.split('/') ?? [];
  const approve = async () => {
    if (!data) return;
    setBusy(true);
    try {
      await post(`${path}/repair`, {
        review_id: data.id,
        confirmation,
        allow_quantity_changes: allowQuantity,
        repair_releases: repairReleases,
      });
      toast(
        repairReleases
          ? 'Ownership release repair approved'
          : allowQuantity
            ? 'Ownership quantities and basis repaired'
            : 'Ownership basis repaired',
      );
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
      {!receiptId && (
        <label className="monitor-live-toggle">
          <input
            type="checkbox"
            checked={allowQuantity}
            disabled={busy}
            onChange={(event) => {
              setAllowQuantity(event.target.checked);
              setConfirmation('');
            }}
          />
          Recalculate handed-off units
        </label>
      )}
      {!receiptId && (
        <div>
          <label className="monitor-live-toggle">
            <input
              type="checkbox"
              checked={repairReleases}
              disabled={busy}
              onChange={(event) => {
                setRepairReleases(event.target.checked);
                setConfirmation('');
              }}
            />
            Fix underfunded releases
          </label>
          <p className="footnote">
            Use the units available at each original release, up to the quantity originally
            approved.
          </p>
        </div>
      )}
      {review.error && <ErrorState message={review.error} retry={review.retry} />}
      {review.loading && !data && <Loading />}
      {data && (
        <div className="form">
          <p className="footnote">
            {data.approved_at ? `Approved ${new Date(data.approved_at).toLocaleString()}. ` : ''}
            {data.repair_releases
              ? 'The repair recalculates the enabled ownership quantities using the units available and each receipt’s original reference price.'
              : data.allow_quantity_changes
                ? 'The repair carries corrected units and uses each handoff’s original reference price to recalculate its paired cash flows.'
                : 'The repair preserves receipt quantities and reference cash flows while recalculating basis and realized trade P&L.'}
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
                  {number(row.previous_cost_basis, 8)} → {number(row.cost_basis, 8)} {quote} basis
                  {row.previous_quantity != null &&
                    row.quantity != null &&
                    row.previous_quantity !== row.quantity && (
                      <small className="table-subline">
                        {number(row.previous_quantity, 8)} → {number(row.quantity, 8)} {base} ·{' '}
                        {number(row.previous_reference_value ?? 0, 8)} →{' '}
                        {number(row.reference_value ?? 0, 8)} {quote} reference flow
                      </small>
                    )}
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
                <FileCheck2 size={15} />{' '}
                {busy
                  ? 'Saving…'
                  : repairReleases
                    ? 'Approve release repair'
                    : allowQuantity
                      ? 'Approve quantity repair'
                      : 'Approve basis repair'}
              </button>
            </>
          )}
        </div>
      )}
    </Modal>
  );
}

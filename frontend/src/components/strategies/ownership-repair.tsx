import { useState } from 'react';
import { FileCheck2 } from 'lucide-react';
import { Link } from 'react-router-dom';
import { number, post, refresh } from '../../lib/api';
import { useResource } from '../../lib/hooks';
import { monitorURL } from '../../lib/strategy-monitor';
import { ErrorState, Loading, Modal, useToast } from '../ui';

type FundingAssertion = {
  fill_id: string;
  note: string;
  cost_basis?: number;
  acquisition_fill_id?: string;
};

type Acquisition = {
  fill_id: string;
  trade_id: string;
  order_id: string;
  timestamp_ms: number;
  origin: 'venue_discovered' | 'sibyl_manual';
};

type SaleFunding = {
  job_id: string;
  fill_id: string;
  order_id: string;
  timestamp_ms: number;
  quantity: number;
  reference_value: number;
  acquisition_candidates?: (Acquisition & { estimated_basis: number })[];
};

type Repair = {
  id: string | null;
  confirmation: string | null;
  symbol?: string;
  approved_at?: string;
  allow_quantity_changes?: boolean;
  repair_releases?: boolean;
  review_sale_funding?: boolean;
  funding_requirements?: SaleFunding[];
  funding_changes?: (SaleFunding & {
    cost_basis: number;
    note: string;
    status: 'approved' | 'retired';
    acquisition?: Acquisition;
  })[];
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
  const [fundSales, setFundSales] = useState(false);
  const [assertions, setAssertions] = useState<
    Record<string, { basis: string; note: string; source: string; customId: string }>
  >({});
  const [fundedPreview, setFundedPreview] = useState<Repair>();
  const review = useResource<Repair>(
    receiptId
      ? `${path}/repairs/${encodeURIComponent(receiptId)}`
      : `${path}/repair?allow_quantity_changes=${allowQuantity}&repair_releases=${repairReleases}&review_sale_funding=${fundSales}`,
  );
  const [confirmation, setConfirmation] = useState('');
  const [busy, setBusy] = useState(false);
  const toast = useToast();
  const candidate = fundedPreview ?? review.data;
  const data =
    receiptId ||
    ((candidate?.allow_quantity_changes ?? false) === allowQuantity &&
      (candidate?.repair_releases ?? false) === repairReleases &&
      (candidate?.review_sale_funding ?? false) === fundSales)
      ? candidate
      : undefined;
  const [base, quote] = (data?.symbol ?? data?.runs[0]?.symbol)?.split('/') ?? [];
  const requirements = data?.funding_requirements ?? [];
  const options = {
    allow_quantity_changes: allowQuantity,
    repair_releases: repairReleases,
    review_sale_funding: fundSales,
    sale_funding: requirements.flatMap<FundingAssertion>((row) => {
      const input = assertions[row.fill_id];
      if (!input?.note.trim()) return [];
      const buyId = input.source === 'other' ? input.customId.trim() : input.source;
      const fields = { fill_id: row.fill_id, note: input.note.trim() };
      if (input.source) return buyId ? [{ ...fields, acquisition_fill_id: buyId }] : [];
      return input.basis.trim() ? [{ ...fields, cost_basis: Number(input.basis) }] : [];
    }),
  };
  const resetPreview = () => {
    setConfirmation('');
    setFundedPreview(undefined);
  };
  const preview = async () => {
    setBusy(true);
    try {
      setFundedPreview(await post<Repair>(`${path}/repair-preview`, options));
      setConfirmation('');
    } catch (error) {
      toast((error as Error).message, true);
      resetPreview();
      review.retry();
    } finally {
      setBusy(false);
    }
  };
  const approve = async () => {
    if (!data?.id) return;
    setBusy(true);
    try {
      await post(`${path}/repair`, {
        review_id: data.id,
        confirmation,
        ...options,
      });
      toast(
        fundSales
          ? 'Historical sale funding approved'
          : repairReleases
            ? 'Ownership release repair approved'
            : allowQuantity
              ? 'Ownership quantities and basis repaired'
              : 'Ownership basis repaired',
      );
      refresh();
      close();
    } catch (error) {
      toast((error as Error).message, true);
      resetPreview();
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
              resetPreview();
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
                resetPreview();
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
      {!receiptId && (
        <label className="monitor-live-toggle">
          <input
            type="checkbox"
            checked={fundSales}
            disabled={busy}
            onChange={(event) => {
              setFundSales(event.target.checked);
              setAssertions({});
              resetPreview();
            }}
          />
          Review sale funding
        </label>
      )}
      {review.error && <ErrorState message={review.error} retry={review.retry} />}
      {!receiptId && requirements.length > 0 && (
        <form
          className="form"
          onSubmit={(event) => {
            event.preventDefault();
            void preview();
          }}
        >
          <p className="footnote">
            Confirm that the missing units came from unmanaged holdings in this exchange account.
            Link a reconciled buy or enter an asserted cost. Record why the units were available in
            either case.
          </p>
          {requirements.map((sale) => {
            const input = assertions[sale.fill_id] ?? {
              basis: '',
              note: '',
              source: '',
              customId: '',
            };
            const candidates =
              review.data?.funding_requirements?.find((row) => row.fill_id === sale.fill_id)
                ?.acquisition_candidates ?? [];
            const changeInput = (patch: Partial<typeof input>) => {
              setAssertions({ ...assertions, [sale.fill_id]: { ...input, ...patch } });
              resetPreview();
            };
            return (
              <fieldset key={sale.fill_id} className="form">
                <legend>
                  {number(sale.quantity, 8)} {base} shortfall · fill {sale.fill_id.slice(0, 8)}
                </legend>
                <p className="footnote">
                  Run {sale.job_id.slice(0, 8)} · order {sale.order_id} ·{' '}
                  {new Date(sale.timestamp_ms).toLocaleString()}
                </p>
                <label>
                  Acquisition basis
                  <select
                    value={input.source}
                    disabled={busy}
                    onChange={(event) => changeInput({ source: event.target.value })}
                  >
                    <option value="">Enter a cost assertion</option>
                    {candidates.map((buy) => (
                      <option value={buy.fill_id} key={buy.fill_id}>
                        {buy.origin === 'venue_discovered'
                          ? 'Venue-discovered buy'
                          : 'Recorded Sibyl buy'}
                        {' · '}
                        {new Date(buy.timestamp_ms).toLocaleDateString()}
                        {' · '}
                        {number(buy.estimated_basis, 8)} {quote} · order {buy.order_id}
                      </option>
                    ))}
                    <option value="other">Link another retained buy fill</option>
                  </select>
                </label>
                {input.source === 'other' && (
                  <label>
                    Retained buy fill ID
                    <input
                      required
                      maxLength={80}
                      value={input.customId}
                      disabled={busy}
                      onChange={(event) => changeInput({ customId: event.target.value })}
                    />
                  </label>
                )}
                {!input.source && (
                  <label>
                    Asserted acquisition cost ({quote})
                    <input
                      required
                      type="number"
                      step="any"
                      min={0}
                      max={1e12}
                      value={input.basis}
                      disabled={busy}
                      onChange={(event) => changeInput({ basis: event.target.value })}
                    />
                  </label>
                )}
                <label>
                  Origin of these units
                  <input
                    required
                    maxLength={300}
                    value={input.note}
                    disabled={busy}
                    onChange={(event) => {
                      changeInput({ note: event.target.value });
                    }}
                  />
                </label>
              </fieldset>
            );
          })}
          <button
            className="button secondary"
            type="submit"
            disabled={busy || options.sale_funding.length !== requirements.length}
          >
            Review funded sales
          </button>
        </form>
      )}
      {review.loading && !data && <Loading />}
      {data?.id && (
        <div className="form">
          <p className="footnote">
            {data.approved_at ? `Approved ${new Date(data.approved_at).toLocaleString()}. ` : ''}
            {data.review_sale_funding
              ? 'The same sale consumes the historical funding. Linked purchases support the acquisition cost. Availability from unmanaged holdings remains your assertion.'
              : data.repair_releases
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
          {!!data.funding_changes?.length && (
            <details open>
              <summary>Historical sale funding ({data.funding_changes.length})</summary>
              <ul>
                {data.funding_changes.map((sale) => (
                  <li key={sale.fill_id}>
                    {sale.status === 'retired'
                      ? 'Retired'
                      : sale.acquisition
                        ? 'Linked buy'
                        : 'Asserted'}{' '}
                    · {number(sale.quantity, 8)} {base} · fill {sale.fill_id.slice(0, 8)}
                    <small className="table-subline">
                      {number(sale.cost_basis, 8)} {quote} basis · {number(sale.reference_value, 8)}{' '}
                      {quote} reference flow
                    </small>
                    {sale.acquisition && (
                      <small className="table-subline">
                        Buy order {sale.acquisition.order_id} · trade {sale.acquisition.trade_id}
                      </small>
                    )}
                    <small className="table-subline">{sale.note}</small>
                  </li>
                ))}
              </ul>
            </details>
          )}
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
                disabled={
                  busy || !!review.error || !data.confirmation || confirmation !== data.confirmation
                }
                onClick={() => void approve()}
              >
                <FileCheck2 size={15} />{' '}
                {busy
                  ? 'Saving…'
                  : fundSales
                    ? 'Approve sale funding'
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

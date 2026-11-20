import { useState } from 'react';
import { CircleCheck, FileCheck2 } from 'lucide-react';
import { Link } from 'react-router-dom';
import { number, post, refresh } from '../../lib/api';
import { useResource } from '../../lib/hooks';
import { ErrorState, Loading, Modal, useToast } from '../ui';

type FeeFill = {
  fill_id: string;
  timestamp_ms: number;
  rows: {
    asset: string;
    native_fee: number;
    quote_fee: number | null;
    legs: {
      symbol: string;
      timeframe: string;
      candle_close_ms: number;
      inverse: boolean;
      rate: string;
    }[];
  }[];
};

type FeeReview = {
  source: string;
  environment: string;
  quote: string;
  pending_count: number;
  batch_quote?: number;
  review_id: string | null;
  reason: string | null;
  rows: FeeFill[];
};

function FeeRows({ fills, quote }: { fills: FeeFill[]; quote: string }) {
  return (
    <div className="table-scroll">
      <table>
        <thead>
          <tr>
            <th>Native fee or rebate</th>
            <th>Fill time</th>
            <th>Estimated value</th>
            <th>Historical candles</th>
          </tr>
        </thead>
        <tbody>
          {fills.flatMap((fill) =>
            fill.rows.map((row, index) => (
              <tr key={`${fill.fill_id}:${index}`}>
                <td>
                  {number(row.native_fee, 8)} {row.asset}
                </td>
                <td>{new Date(fill.timestamp_ms).toLocaleString()}</td>
                <td>
                  {row.quote_fee == null ? 'Price missing' : `${number(row.quote_fee, 8)} ${quote}`}
                </td>
                <td>
                  {row.legs.map((leg) => (
                    <small className="table-subline" key={leg.symbol}>
                      {leg.symbol} · {leg.timeframe} ·{' '}
                      {new Date(leg.candle_close_ms).toLocaleString()}
                      {leg.inverse ? ' · inverse' : ''}
                    </small>
                  ))}
                </td>
              </tr>
            )),
          )}
        </tbody>
      </table>
    </div>
  );
}

export function RunFeeReview({ path }: { path: string }) {
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const resource = useResource<FeeReview>(`${path}/fee-review`, 0, open);
  const data = resource.data;
  const toast = useToast();
  async function apply(reviewId: string) {
    setBusy(true);
    try {
      await post(`${path}/fee-review`, { review_id: reviewId });
      toast('Historical fee prices approved');
      refresh();
      setOpen(false);
    } catch (error) {
      toast((error as Error).message, true);
      resource.retry();
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <button className="button secondary tiny" onClick={() => setOpen(true)}>
        <FileCheck2 size={14} /> Review fee prices
      </button>
      {open && (
        <Modal title="Review historical fee prices" onClose={() => setOpen(false)}>
          {resource.error && <ErrorState message={resource.error} retry={resource.retry} />}
          {!data && !resource.error && <Loading />}
          {data && (
            <>
              <p className="footnote">
                {data.environment === 'test' ? 'Test funds. ' : 'Production funds. '}
                Approved prices count toward strategy profit and loss limits after approval. Your
                quote balance stays unchanged. Resume is a separate action.
              </p>
              {data.reason && <p className="inline-alert">{data.reason}</p>}
              {data.rows.length > 0 && <FeeRows fills={data.rows} quote={data.quote} />}
              {data.pending_count > data.rows.length && data.rows.length > 0 && (
                <p className="footnote">
                  Reviewing {data.rows.length} of {data.pending_count} fills awaiting pricing.
                </p>
              )}
              <div className="workspace-controls">
                {data.rows.some((fill) => fill.rows.some((row) => row.quote_fee == null)) && (
                  <Link to={`/markets?view=history&source=${encodeURIComponent(data.source)}`}>
                    Open this account’s candle history ↗
                  </Link>
                )}
                {data.review_id && (
                  <button
                    className="button primary"
                    disabled={busy}
                    onClick={() => void apply(data.review_id!)}
                  >
                    <CircleCheck size={15} />
                    {busy ? 'Saving…' : `Approve ${number(data.batch_quote ?? 0, 8)} ${data.quote}`}
                  </button>
                )}
                {data.pending_count === 0 && (
                  <p>All other-asset fees on this run have approved prices.</p>
                )}
              </div>
            </>
          )}
        </Modal>
      )}
    </>
  );
}

export function RunFeeReceipt({
  jobId,
  receiptId,
  close,
}: {
  jobId: string;
  receiptId: string;
  close: () => void;
}) {
  const receipt = useResource<{ rows: FeeFill[]; quote: string; approved_at: string }>(
    `/strategies/exchange/jobs/${encodeURIComponent(jobId)}/fee-review/${encodeURIComponent(receiptId)}`,
  );
  return (
    <Modal title="Approved fee prices" onClose={close}>
      {receipt.error && <ErrorState message={receipt.error} retry={receipt.retry} />}
      {!receipt.data && !receipt.error && <Loading />}
      {receipt.data && (
        <>
          <p className="footnote">Approved {new Date(receipt.data.approved_at).toLocaleString()}</p>
          <FeeRows fills={receipt.data.rows} quote={receipt.data.quote} />
        </>
      )}
    </Modal>
  );
}

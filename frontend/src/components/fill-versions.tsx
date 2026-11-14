import { useState } from 'react';
import { number } from '../lib/api';
import { useResource } from '../lib/hooks';
import { Empty, ErrorState, Loading, Modal } from './ui';

type Observation = {
  revision: number;
  kind: string;
  observed_at: string;
  payload: {
    quantity: number;
    price: number;
    notional: number | null;
    fees: { currency: string | null; cost: number | null }[];
  };
};

/** Read actual normalized observations; original provider payloads and credentials are absent. */
export function FillVersions({ identity, onClose }: { identity: string; onClose: () => void }) {
  const [offset, setOffset] = useState(0);
  const state = useResource<{ items: Observation[]; total: number }>(
    `/account-books/fills/${identity}/versions?offset=${offset}`,
  );
  return (
    <Modal title="Fill observation history" onClose={onClose}>
      <p className="footnote">
        Identical imports add no revisions. A retained baseline records what was available when
        auditing began; it does not reconstruct unseen older provider changes.
      </p>
      {state.loading && <Loading />}
      {state.error && <ErrorState message={state.error} retry={state.retry} />}
      {state.data?.items.length ? (
        <>
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Revision / kind</th>
                  <th>Observed</th>
                  <th>Quantity</th>
                  <th>Price</th>
                  <th>Notional</th>
                  <th>Fees / rebates</th>
                </tr>
              </thead>
              <tbody>
                {state.data.items.map((row) => (
                  <tr key={row.revision}>
                    <td>
                      {row.revision}
                      <small className="table-subline">{row.kind.replaceAll('_', ' ')}</small>
                    </td>
                    <td>{new Date(row.observed_at).toLocaleString()}</td>
                    <td>{number(row.payload.quantity, 8)}</td>
                    <td>{number(row.payload.price, 8)}</td>
                    <td>
                      {row.payload.notional == null ? 'Unknown' : number(row.payload.notional, 8)}
                    </td>
                    <td>
                      {row.payload.fees.map((fee, index) => (
                        <span key={index}>
                          {fee.cost == null ? 'Unknown' : number(fee.cost, 8)}{' '}
                          {fee.currency ?? 'unknown unit'}{' '}
                        </span>
                      ))}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="performance-actions">
            <button
              className="button secondary tiny"
              disabled={!offset}
              onClick={() => setOffset(Math.max(0, offset - 50))}
            >
              Newer
            </button>
            <small>
              {offset + 1}–{Math.min(offset + 50, state.data.total)} of {state.data.total}{' '}
              observations
            </small>
            <button
              className="button secondary tiny"
              disabled={offset + 50 >= state.data.total}
              onClick={() => setOffset(offset + 50)}
            >
              Older
            </button>
          </div>
        </>
      ) : (
        state.data && (
          <Empty title="No retained revisions yet">
            The next import creates a labeled baseline for legacy fills. Future material corrections
            are retained separately.
          </Empty>
        )
      )}
    </Modal>
  );
}

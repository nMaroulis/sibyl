import { useState } from 'react';
import { createPortal } from 'react-dom';
import { History } from 'lucide-react';
import { useResource } from '../lib/hooks';
import { Badge, Empty, ErrorState, Loading, Modal } from './ui';

type Version = {
  id: string;
  observed_at: string;
  origin: string;
  first_observation: boolean;
  before_asset?: string | null;
  after_asset?: string | null;
  changes: { field: string; before: unknown; after: unknown }[];
};
type Evidence = {
  account: string;
  asset: string;
  environment: string;
  entries: Version[];
  total: number;
  note: string;
};
const labels: Record<string, string> = {
  kind: 'Movement',
  asset: 'Asset',
  direction: 'Direction',
  status: 'Status',
  quantity: 'Reported amount',
  fee: 'Reported fee',
  fee_known: 'Fee available',
  posted_ms: 'Balance posting time',
  timestamp_ms: 'Source time',
  amount_basis: 'Amount basis',
  wallet_scope: 'Wallet scope',
  internal: 'Internal at venue',
  reference: 'Reference',
};
function value(field: string, data: unknown, asset: string): string {
  if (data === null || data === undefined) return 'Unavailable';
  if (field.endsWith('_ms') && typeof data === 'number') return new Date(data).toLocaleString();
  if (typeof data === 'boolean') return data ? 'Yes' : 'No';
  if (field === 'quantity') return `${data} ${asset}`;
  if (field === 'direction') return data === 'in' ? 'Received' : 'Sent';
  if (field === 'fee' && typeof data === 'object') {
    const fee = data as { currency: string | null; cost: number | null };
    return `${fee.cost ?? 'Unavailable'} ${fee.currency || ''}`;
  }
  return typeof data === 'string' ? data.replaceAll('_', ' ') : String(data);
}

/** Read-only local observations; opening this view cannot refresh the exchange. */
export function FundingVersionsButton({ id, count }: { id: string; count?: number }) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button className="text-link" onClick={() => setOpen(true)}>
        <History size={12} /> Observed versions{count !== undefined ? ` (${count})` : ''}
      </button>
      {open &&
        createPortal(
          <Modal
            title="Observed funding changes"
            onClose={() => setOpen(false)}
            className="funding-versions-modal"
          >
            <Versions id={id} />
          </Modal>,
          document.body,
        )}
    </>
  );
}
function Versions({ id }: { id: string }) {
  const data = useResource<Evidence>(`/account-ledger/funding/${encodeURIComponent(id)}/versions`);
  if (data.error) return <ErrorState message={data.error} retry={data.retry} />;
  if (!data.data) return <Loading />;
  return (
    <div className="funding-versions-content">
      <p className="muted">
        {data.data.account} · {data.data.environment} · {data.data.asset}
      </p>
      {!data.data.entries.length ? (
        <Empty title="No observed versions yet">
          This record predates local version tracking. A future import or update can record observed
          changes.
        </Empty>
      ) : (
        data.data.entries.map((entry) => (
          <article key={entry.id}>
            <header>
              <strong>{new Date(entry.observed_at).toLocaleString()}</strong>
              <Badge tone={entry.first_observation ? 'neutral' : 'peach'}>
                {entry.first_observation ? 'First observed' : 'Source change'}
              </Badge>
            </header>
            <small>
              {entry.origin === 'recent_sync'
                ? 'Recent history sync'
                : entry.origin === 'pending_update'
                  ? 'Pending update'
                  : 'History import'}
            </small>
            {entry.first_observation ? (
              <details className="funding-initial-snapshot">
                <summary>Initial observed values · {entry.changes.length} fields</summary>
                <VersionTable entry={entry} asset={data.data!.asset} />
              </details>
            ) : (
              <VersionTable entry={entry} asset={data.data!.asset} />
            )}
          </article>
        ))
      )}
      <p className="footnote">
        {data.data.total} saved {data.data.total === 1 ? 'version' : 'versions'} · newest 20 shown.{' '}
        {data.data.note}
      </p>
    </div>
  );
}

function VersionTable({ entry, asset }: { entry: Version; asset: string }) {
  return (
    <div className="table-scroll">
      <table>
        <thead>
          <tr>
            <th>Field</th>
            {!entry.first_observation && <th>Previously observed</th>}
            <th>Observed now</th>
          </tr>
        </thead>
        <tbody>
          {entry.changes.map((change) => (
            <tr key={change.field}>
              <th>{labels[change.field] || change.field}</th>
              {!entry.first_observation && (
                <td>{value(change.field, change.before, entry.before_asset || asset)}</td>
              )}
              <td>{value(change.field, change.after, entry.after_asset || asset)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

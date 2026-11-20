import { useEffect, useState } from 'react';
import { Download, History } from 'lucide-react';
import { downloadFile, post } from '../../lib/api';
import { useResource } from '../../lib/hooks';
import { ErrorState, Panel, useToast } from '../ui';

type Retention = {
  policy: { enabled: boolean; days: number; revision: number };
  preview: {
    cutoff: string;
    eligible: number;
    unread_protected: number;
    delivery_protected: number;
    batch_limit: number;
  };
  runs: { at: string; deleted: number; manual: boolean }[];
  scope: string;
};
/** Exporting never acknowledges notices. Pruning is an explicit, separately reviewed policy. */
export function NotificationHistoryControls({ changed }: { changed: () => void }) {
  const status = useResource<Retention>('/notifications/retention');
  const [kind, setKind] = useState('all');
  const [start, setStart] = useState('');
  const [end, setEnd] = useState('');
  const [enabled, setEnabled] = useState(false);
  const [days, setDays] = useState(90);
  const [busy, setBusy] = useState('');
  const [error, setError] = useState('');
  const toast = useToast();
  useEffect(() => {
    if (status.data) {
      setEnabled(status.data.policy.enabled);
      setDays(status.data.policy.days);
    }
  }, [status.data]);
  const action = async (kind: 'json' | 'csv' | 'save' | 'clear') => {
    setBusy(kind);
    setError('');
    try {
      if (kind === 'json' || kind === 'csv') {
        const params = new URLSearchParams({ format: kind, kind: selectedKind });
        if (start) params.set('start', new Date(`${start}T00:00:00Z`).toISOString());
        if (end) params.set('end', new Date(`${end}T00:00:00Z`).toISOString());
        await downloadFile(`/notifications/export?${params}`, `sibyl-notifications.${kind}`);
        toast(
          'History exported. Up to 2,000 newest matching notices; narrow the dates for larger histories.',
        );
      } else if (status.data) {
        if (kind === 'save') {
          await post('/notifications/retention', {
            enabled,
            days,
            revision: status.data.policy.revision,
          });
          toast(
            enabled
              ? 'Automatic cleanup enabled for old read notices.'
              : 'Automatic cleanup disabled.',
          );
        } else {
          const result = await post<{ result: { deleted: number } }>(
            '/notifications/retention/clear',
            { revision: status.data.policy.revision },
          );
          toast(`${result.result.deleted} eligible read notices removed.`);
          changed();
        }
        status.retry();
      }
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy('');
    }
  };
  const selectedKind = kind;
  const dirty =
    !!status.data && (enabled !== status.data.policy.enabled || days !== status.data.policy.days);
  return (
    <Panel className="notification-history-controls">
      <details>
        <summary>
          <History size={15} />
          History export & retention
        </summary>
        <p className="footnote">
          Export local evidence, or opt in to cleanup. Automatic cleanup is off by default.
        </p>
        <div className="history-control-grid">
          <label>
            Notification kind
            <select value={kind} onChange={(e) => setKind(e.target.value)}>
              {[
                'all',
                'price',
                'risk',
                'strategy',
                'connection',
                'order',
                'workspace',
                'bitcoin',
              ].map((k) => (
                <option key={k} value={k}>
                  {k === 'all' ? 'All kinds' : k}
                </option>
              ))}
            </select>
          </label>
          <label>
            From · UTC
            <input type="date" value={start} onChange={(e) => setStart(e.target.value)} />
          </label>
          <label>
            Before · UTC
            <input type="date" value={end} onChange={(e) => setEnd(e.target.value)} />
          </label>
        </div>
        <div className="forecast-workspace-actions">
          {(['json', 'csv'] as const).map((format) => (
            <button
              key={format}
              className="button secondary tiny"
              disabled={!!busy}
              onClick={() => void action(format)}
            >
              <Download size={13} />
              Export {format.toUpperCase()}
            </button>
          ))}
        </div>
        <p className="footnote">
          Maximum 2,000 newest notices per export. JSON reports matched totals and truncation; split
          large histories by date. Exports can contain private account evidence.
        </p>
        {status.error ? (
          <ErrorState message={status.error} retry={status.retry} />
        ) : (
          status.data && (
            <>
              <div className="history-retention-settings">
                <label className="inline-check">
                  <input
                    type="checkbox"
                    checked={enabled}
                    onChange={(e) => setEnabled(e.target.checked)}
                  />
                  Automatically clear old read notices
                </label>
                <label>
                  Keep at least · days
                  <input
                    type="number"
                    min={7}
                    max={3650}
                    value={days}
                    onChange={(e) => setDays(Number(e.target.value))}
                  />
                </label>
                <button
                  className="button secondary tiny"
                  disabled={!!busy || !dirty || days < 7 || days > 3650}
                  onClick={() => void action('save')}
                >
                  Save retention policy
                </button>
              </div>
              <p className="footnote">
                {status.data.preview.eligible} eligible before{' '}
                {new Date(status.data.preview.cutoff).toLocaleDateString()}. Protected:{' '}
                {status.data.preview.unread_protected} unread ·{' '}
                {status.data.preview.delivery_protected} with unfinished delivery.{' '}
                {status.data.scope}
              </p>
              <button
                className="text-button"
                disabled={!!busy || dirty || !status.data.preview.eligible}
                onClick={() => void action('clear')}
              >
                Clear up to {status.data.preview.batch_limit} eligible read notices
              </button>
              {status.data.runs[0] && (
                <p className="footnote">
                  Last cleanup: {new Date(status.data.runs[0].at).toLocaleString()} ·{' '}
                  {status.data.runs[0].deleted} removed.
                </p>
              )}
            </>
          )
        )}
        {error && (
          <p className="form-error" role="alert">
            {error}
          </p>
        )}
      </details>
    </Panel>
  );
}

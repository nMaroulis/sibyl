import { useState } from 'react';
import { Download, ShieldCheck } from 'lucide-react';
import { Badge, Panel, PanelTitle } from '../ui';
import { downloadFile, post } from '../../lib/api';
import { useResource } from '../../lib/hooks';

type Report = {
  generated_at: string;
  database: { status: string; duration_ms: number; note: string };
  worker_observation: string;
  privacy: string;
  scope: string;
};

/** Checks happen only on request; downloading never triggers another check. */
export function WorkspaceDiagnostics() {
  const saved = useResource<{ report: Report | null }>('/workspace/diagnostics');
  const [report, setReport] = useState<Report>(),
    [busy, setBusy] = useState(false),
    [error, setError] = useState('');
  const current = report ?? saved.data?.report;
  return (
    <Panel className="workspace-health">
      <PanelTitle
        title="Workspace health report"
        subtitle="Read-only database check · private-content-free diagnostics"
        action={
          current && (
            <Badge tone={current.database.status === 'passed' ? 'lime' : 'amber'}>
              Database · {current.database.status.replaceAll('_', ' ')}
            </Badge>
          )
        }
      />
      <p className="footnote">
        Check SQLite’s basic structure and collect runtime versions, numeric resource counters and
        aggregate worker states. Reports exclude credentials, account details, paths and workspace
        content.
      </p>
      <div className="forecast-workspace-actions">
        <button
          className="button secondary"
          disabled={busy}
          onClick={async () => {
            setBusy(true);
            setError('');
            try {
              setReport(await post<Report>('/workspace/diagnostics', {}));
            } catch (e) {
              setError((e as Error).message);
            } finally {
              setBusy(false);
            }
          }}
        >
          <ShieldCheck size={14} />
          {busy ? 'Checking workspace…' : 'Run health check'}
        </button>
        <button
          className="text-button"
          disabled={!current || busy}
          onClick={async () => {
            setError('');
            try {
              await downloadFile('/workspace/diagnostics/export', 'sibyl-health-report.json');
            } catch (e) {
              setError((e as Error).message);
            }
          }}
        >
          <Download size={14} />
          Download health report
        </button>
      </div>
      {(error || saved.error) && (
        <p className="form-error" role="alert">
          {error || saved.error}
        </p>
      )}
      {current && (
        <div role="status">
          <p>{current.database.note}</p>
          <p className="footnote">
            Checked {new Date(current.generated_at).toLocaleString()} ·{' '}
            {current.database.duration_ms} ms · worker observation {current.worker_observation}.{' '}
            {current.scope}
          </p>
        </div>
      )}
      <p className="footnote">
        The quick check has a two-second execution budget and a short lock wait. It does not repair
        data or verify balances, credentials or every SQLite invariant. The last report stays in
        memory until restart; review it before sharing.
      </p>
    </Panel>
  );
}

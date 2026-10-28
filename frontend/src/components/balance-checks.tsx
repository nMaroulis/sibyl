import { useState } from 'react';
import { Link } from 'react-router-dom';
import { ChevronDown, Download, RefreshCw, ScanLine } from 'lucide-react';
import { exportCSV, number, post } from '../lib/api';
import { useResource } from '../lib/hooks';
import { Badge, Empty, ErrorState, Loading, Panel } from './ui';
import { ExpandableRows } from './expandable-rows';
import { ExchangeMark } from './exchange-mark';

type Account = {
  id: string;
  name: string;
  exchange: string;
  sandbox: boolean;
  environment: string;
};
type Row = {
  asset: string;
  opening: number;
  trade_change: number;
  funding_change: number;
  observed: number;
  expected: number | null;
  difference: number | null;
  tolerance: number;
  status: string;
  issues: string[];
};
type Report = {
  id: string;
  checkpoint_id: string;
  account: string;
  environment: string;
  observed_at: string;
  starting_at: string;
  status: string;
  rows: Row[];
  differences: number;
  incomplete: number;
  activity: { fills: number; funding: number };
  funding_effect_counts?: Record<string, number>;
  notes: string[];
  note: string;
};
type Saved = {
  checkpoint: { id: string; observed_at: string; wallet_scope: string } | null;
  latest: Report | null;
  history: Pick<
    Report,
    | 'id'
    | 'checkpoint_id'
    | 'account'
    | 'environment'
    | 'observed_at'
    | 'starting_at'
    | 'status'
    | 'differences'
    | 'incomplete'
  >[];
  configuration_changed: boolean;
};
const quantity = (value: number | null) =>
  value === null
    ? '—'
    : value !== 0 && Math.abs(value) < 1e-8
      ? value.toExponential(4)
      : number(value, 10);
const label = (status: string) =>
  ({
    observed_match: 'Observed match',
    difference: 'Difference',
    differences: 'Differences to review',
    incomplete: 'Missing evidence',
  })[status] ?? status;

/** Opening this panel only reads saved evidence. Provider reads require an explicit button. */
export function BalanceChecks({ scope }: { scope: string }) {
  const [open, setOpen] = useState(false);
  const [selected, setSelected] = useState('');
  const options = useResource<{ accounts: Account[] }>(
    `/account/balance-checks?scope=${encodeURIComponent(scope)}`,
  );
  const account =
    options.data?.accounts.find((row) => row.id === selected) ?? options.data?.accounts[0];
  return (
    <Panel className="balance-checks-panel">
      <details onToggle={(event) => setOpen(event.currentTarget.open)}>
        <summary className="balance-checks-summary">
          <span className="balance-checks-mark">
            <ScanLine size={20} />
          </span>
          <span>
            <strong>Balance checks</strong>
            <small>Compare observed quantities with imported activity</small>
          </span>
          <ChevronDown size={18} className="balance-checks-chevron" />
        </summary>
        {open && (
          <div className="balance-checks-body">
            {options.loading ? (
              <Loading />
            ) : options.error ? (
              <ErrorState message={options.error} retry={options.retry} />
            ) : account ? (
              <>
                <div className="workspace-controls">
                  <label>
                    Account
                    <select
                      value={account.id}
                      onChange={(event) => setSelected(event.target.value)}
                    >
                      {options.data?.accounts.map((row) => (
                        <option key={row.id} value={row.id}>
                          {row.name}
                          {row.sandbox
                            ? ' · Test funds'
                            : row.environment === 'demo'
                              ? ' · Demo'
                              : ''}
                        </option>
                      ))}
                    </select>
                  </label>
                  <Link to="/trade?tab=history" className="text-link">
                    Manage imported history
                  </Link>
                </div>
                <SavedBalanceChecks key={account.id} account={account} />
              </>
            ) : (
              <Empty title="No active account">
                Connect an exchange account or explicitly enable Demo preview.
              </Empty>
            )}
          </div>
        )}
      </details>
    </Panel>
  );
}

function SavedBalanceChecks({ account }: { account: Account }) {
  const resource = useResource<Saved>(`/account/balance-checks/${account.id}`);
  const [changed, setChanged] = useState<Saved>();
  const [busy, setBusy] = useState('');
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [reportId, setReportId] = useState('');
  const saved = changed ?? resource.data;
  const historical = useResource<Report>(
    `/account/balance-checks/${account.id}/reports/${reportId || 'none'}`,
    0,
    !!reportId && reportId !== saved?.latest?.id,
  );
  if (resource.loading) return <Loading />;
  if (resource.error || !saved)
    return (
      <ErrorState message={resource.error || 'Saved checks unavailable.'} retry={resource.retry} />
    );
  const report = reportId && reportId !== saved.latest?.id ? historical.data : saved.latest;
  const run = async (kind: 'checkpoint' | 'compare') => {
    setBusy(kind);
    setError('');
    setNotice('');
    try {
      const next = await post<Saved>(
        `/account/balance-checks/${account.id}/${kind}`,
        kind === 'checkpoint'
          ? { replace_id: saved.checkpoint?.id ?? null }
          : { checkpoint_id: saved.checkpoint?.id },
      );
      setChanged(next);
      setReportId('');
      setNotice(
        kind === 'checkpoint'
          ? 'Starting balances captured. Subsequent comparisons use this checkpoint.'
          : 'Comparison saved. Review any differences or missing evidence below.',
      );
    } catch (reason) {
      setError((reason as Error).message);
    } finally {
      setBusy('');
    }
  };
  return (
    <>
      <div className="balance-checks-toolbar">
        <span className="account-brand">
          <ExchangeMark exchange={account.exchange} size={20} />
          <strong>{account.name}</strong>
          {account.environment !== 'production' && (
            <Badge tone={account.environment === 'demo' ? 'demo' : 'purple'}>
              {account.environment === 'demo' ? 'Demo' : 'Test funds'}
            </Badge>
          )}
        </span>
        <div className="button-group">
          <button
            className="button secondary tiny"
            disabled={!!busy}
            onClick={() => {
              setChanged(undefined);
              resource.retry();
            }}
            title="Refresh saved evidence"
          >
            <RefreshCw size={14} />
          </button>
          <button
            className="button secondary tiny"
            disabled={!!busy}
            onClick={() => run('checkpoint')}
          >
            {busy === 'checkpoint'
              ? 'Reading balances…'
              : saved.checkpoint
                ? 'New starting point'
                : 'Capture starting balances'}
          </button>
          {saved.checkpoint && (
            <button
              className="button tiny"
              disabled={!!busy || saved.configuration_changed}
              onClick={() => run('compare')}
            >
              {busy === 'compare' ? 'Comparing…' : 'Compare balances'}
            </button>
          )}
        </div>
      </div>
      {saved.checkpoint ? (
        <p className="footnote">
          {saved.checkpoint.wallet_scope}. Starting point:{' '}
          {new Date(saved.checkpoint.observed_at).toLocaleString()}. Each comparison reads current
          balances; it does not change exchange funds.
        </p>
      ) : (
        <p className="footnote">
          Capture a starting point, then compare later balances with imported trades and funding.
          Older holdings are kept as opening quantities, without inventing their cost basis.
        </p>
      )}
      {saved.configuration_changed && (
        <div className="inline-alert">
          The saved account credentials or wallet scope changed. Review the account and capture a
          new starting point.
        </div>
      )}
      {error && (
        <div className="inline-alert" role="alert">
          {error}{' '}
          <button
            className="text-link"
            onClick={() => {
              setChanged(undefined);
              resource.retry();
            }}
          >
            Refresh saved state
          </button>
        </div>
      )}
      {notice && (
        <p className="balance-checks-notice" role="status">
          {notice}
        </p>
      )}
      {!!saved.history.length && (
        <label className="balance-checks-history">
          Saved checks
          <select
            value={reportId || saved.latest?.id || ''}
            onChange={(event) => setReportId(event.target.value)}
          >
            {!saved.latest && <option value="">Choose an earlier check…</option>}
            {saved.history.map((item) => (
              <option value={item.id} key={item.id}>
                {new Date(item.observed_at).toLocaleString()} · {label(item.status)}
              </option>
            ))}
          </select>
        </label>
      )}
      {reportId && reportId !== saved.latest?.id && historical.loading && <Loading />}
      {historical.error && <ErrorState message={historical.error} retry={historical.retry} />}
      {report && (
        <>
          <div className="balance-checks-result">
            <div>
              <Badge
                tone={
                  report.status === 'differences'
                    ? 'rose'
                    : report.status === 'incomplete'
                      ? 'sand'
                      : 'mint'
                }
              >
                {label(report.status)}
              </Badge>
              <small>
                Saved {new Date(report.observed_at).toLocaleString()} · starting{' '}
                {new Date(report.starting_at).toLocaleString()}
              </small>
            </div>
            <button
              className="button secondary tiny"
              disabled={!report.rows.length}
              onClick={() =>
                exportCSV('sibyl-balance-check.csv', [
                  [
                    'Account',
                    'Environment',
                    'Asset',
                    'Opening',
                    'Known trade change',
                    'Known funding change',
                    'Expected',
                    'Observed',
                    'Difference',
                    'Tolerance',
                    'Status',
                    'Issues',
                    'Starting point',
                    'Checked at',
                  ],
                  ...report.rows.map((row) => [
                    report.account,
                    report.environment,
                    row.asset,
                    row.opening,
                    row.trade_change,
                    row.funding_change,
                    row.expected ?? '',
                    row.observed,
                    row.difference ?? '',
                    row.tolerance,
                    row.status,
                    row.issues.join('; '),
                    report.starting_at,
                    report.observed_at,
                  ]),
                ])
              }
            >
              <Download size={13} /> Export check
            </button>
          </div>
          {report.notes.map((note) => (
            <p className="footnote" key={note}>
              {note}
            </p>
          ))}
          {report.rows.length ? (
            <ExpandableRows key={report.id} total={report.rows.length} label="assets">
              {(visible: number) => (
                <div className="table-scroll">
                  <table>
                    <thead>
                      <tr>
                        <th>Asset</th>
                        <th>Opening</th>
                        <th>Known trade change</th>
                        <th>Known funding change</th>
                        <th>Expected</th>
                        <th>Observed</th>
                        <th>Difference</th>
                        <th>Status</th>
                      </tr>
                    </thead>
                    <tbody>
                      {report.rows.slice(0, visible).map((row) => (
                        <tr key={row.asset}>
                          <td>
                            <strong>{row.asset}</strong>
                            {row.issues
                              .filter((issue) => !report.notes.includes(issue))
                              .map((issue) => (
                                <small className="table-subline" key={issue}>
                                  {issue}
                                </small>
                              ))}
                          </td>
                          <td className="monetary">{quantity(row.opening)}</td>
                          <td className="monetary">{quantity(row.trade_change)}</td>
                          <td className="monetary">{quantity(row.funding_change)}</td>
                          <td className="monetary">{quantity(row.expected)}</td>
                          <td className="monetary">{quantity(row.observed)}</td>
                          <td
                            className="monetary"
                            title={`Numeric tolerance: ${quantity(row.tolerance)} ${row.asset}`}
                          >
                            {quantity(row.difference)}
                          </td>
                          <td>
                            <Badge
                              tone={
                                row.status === 'difference'
                                  ? 'rose'
                                  : row.status === 'incomplete'
                                    ? 'sand'
                                    : 'mint'
                              }
                            >
                              {label(row.status)}
                            </Badge>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </ExpandableRows>
          ) : (
            <Empty title="No retained quantities">
              This check found no nonzero asset quantities.
            </Empty>
          )}
          <p className="footnote">
            {report.activity.fills} new trade executions · {report.activity.funding} funding
            observations applied. {report.note}
            {!!report.funding_effect_counts?.user_review && (
              <>
                {' '}
                Includes {report.funding_effect_counts.user_review} local funding{' '}
                {report.funding_effect_counts.user_review === 1 ? 'review' : 'reviews'}; these are
                user assertions, not provider facts.
              </>
            )}
          </p>
        </>
      )}
    </>
  );
}

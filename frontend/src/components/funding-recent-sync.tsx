import { useState } from 'react';
import { ChevronDown, History, RefreshCw } from 'lucide-react';
import { post, refresh } from '../lib/api';
import { useResource } from '../lib/hooks';
import { Badge, ErrorState, Loading, Panel, useToast } from './ui';

type Stream = 'deposit' | 'withdrawal' | 'transfer';
type ScanReport = {
  id: string;
  start_ms: number;
  end_ms: number;
  completed_at: string;
  pages: number;
  inserted: number;
  updated: number;
  concurrent_changes: number;
  not_returned: number;
  not_returned_preview: {
    id: string;
    asset: string | null;
    native_id: string | null;
    status: string | null;
  }[];
  gap: { start_ms: number; end_ms: number } | null;
};
export type RecentFundingPolicy = {
  account_id: string;
  stream: Stream;
  revision: string;
  enabled: boolean;
  interval_minutes: number;
  lookback_days: number;
  status: string;
  last_checked_at: string | null;
  next_scan_at: string | null;
  inserted: number;
  updated: number;
  pages: number;
  passes: number;
  uncovered_gap_count: number;
  uncovered_gaps: { start_ms: number; end_ms: number }[];
  error: string | null;
  retry_at: string | null;
  last_report: ScanReport | null;
};
const names: Record<Stream, string> = {
  deposit: 'Deposits',
  withdrawal: 'Withdrawals',
  transfer: 'Transfers',
};
const date = (value: string | number) => new Date(value).toLocaleString();

/** Optional rolling-window imports; pending checks and explicit historical imports stay independent. */
export function FundingRecentSync({
  account,
  policies,
}: {
  account: { id: string; active: boolean; recent_sync_streams: Stream[] };
  policies: RecentFundingPolicy[];
}) {
  const [open, setOpen] = useState(false);
  const matching = policies.filter((item) => item.account_id === account.id);
  const attention = matching.some(
    (item) => item.status === 'error' || item.uncovered_gap_count > 0,
  );
  if (!account.recent_sync_streams?.length) return null;
  return (
    <Panel className="full-panel funding-recent-panel">
      <button className="funding-recent-toggle" aria-expanded={open} onClick={() => setOpen(!open)}>
        <span className="funding-pending-symbol">
          <History size={18} />
        </span>
        <span>
          <strong>Recent history sync</strong>
          <small>Find new funding and revisit later status or fee corrections</small>
        </span>
        <Badge
          tone={attention ? 'peach' : matching.some((item) => item.enabled) ? 'lime' : 'neutral'}
        >
          {attention
            ? 'Needs review'
            : matching.some((item) => item.enabled)
              ? 'Updates on'
              : 'Optional · off'}
        </Badge>
        <ChevronDown size={17} className={open ? 'is-open' : ''} />
      </button>
      {open && (
        <>
          <div className="funding-pending-options">
            {account.recent_sync_streams.map((stream) => {
              const policy = matching.find((item) => item.stream === stream);
              return (
                <RecentStream
                  key={`${account.id}:${stream}:${policy?.revision || 'new'}`}
                  account={account}
                  stream={stream}
                  policy={policy}
                />
              );
            })}
          </div>
          <p className="footnote padded">
            Scans revisit the selected creation-time window, ending one minute behind now. Older
            history, provider retention and records arriving outside that window can leave gaps.
            Missing entries are preserved. Pausing imports or deactivating the account turns sync
            off; manual import ranges are kept.
          </p>
        </>
      )}
    </Panel>
  );
}

function RecentStream({
  account,
  stream,
  policy,
}: {
  account: { id: string; active: boolean };
  stream: Stream;
  policy?: RecentFundingPolicy;
}) {
  const [days, setDays] = useState(policy?.lookback_days || 7);
  const [minutes, setMinutes] = useState(policy?.interval_minutes || 60);
  const [busy, setBusy] = useState(false);
  const [historyOpen, setHistoryOpen] = useState(false);
  const toast = useToast();
  async function save(enabled: boolean, checkNow = false, lookback = days, interval = minutes) {
    setBusy(true);
    try {
      await post(`/connections/${encodeURIComponent(account.id)}/funding-scans/${stream}`, {
        enabled,
        check_now: checkNow,
        lookback_days: lookback,
        interval_minutes: interval,
        replace_revision: policy?.revision || null,
      });
      refresh();
      toast(
        checkNow
          ? 'Recent history scan queued.'
          : enabled
            ? 'Recent funding sync enabled.'
            : 'Recent funding sync turned off. Imported history preserved.',
      );
    } catch (reason) {
      toast((reason as Error).message, true);
      refresh();
    } finally {
      setBusy(false);
    }
  }
  const report = policy?.last_report;
  return (
    <section className="funding-pending-option">
      <div className="funding-pending-heading">
        <div>
          <strong>{names[stream]}</strong>
          <small>
            {policy
              ? `${policy.inserted} new · ${policy.updated} ${policy.updated === 1 ? 'update' : 'updates'} · ${policy.passes} finished ${policy.passes === 1 ? 'scan' : 'scans'}`
              : 'No background imports until enabled'}
          </small>
        </div>
        <Badge tone={policy?.status === 'error' ? 'peach' : policy?.enabled ? 'lime' : 'neutral'}>
          {policy?.status === 'error' ? 'Needs attention' : policy?.enabled ? 'On' : 'Off'}
        </Badge>
      </div>
      <div className="funding-recent-fields">
        <label>
          Revisit
          <select
            aria-label={`${names[stream]} history lookback`}
            disabled={busy || !account.active}
            value={days}
            onChange={(e) => {
              const value = Number(e.target.value);
              setDays(value);
              if (policy?.enabled) void save(true, false, value, minutes);
            }}
          >
            <option value={1}>Last 24 hours</option>
            <option value={7}>Last 7 days</option>
            <option value={30}>Last 30 days</option>
          </select>
        </label>
        <label>
          Scan every
          <select
            aria-label={`${names[stream]} history interval`}
            disabled={busy || !account.active}
            value={minutes}
            onChange={(e) => {
              const value = Number(e.target.value);
              setMinutes(value);
              if (policy?.enabled) void save(true, false, days, value);
            }}
          >
            <option value={15}>15 minutes</option>
            <option value={60}>1 hour</option>
            <option value={360}>6 hours</option>
          </select>
        </label>
      </div>
      <div className="performance-actions">
        <button
          className={`button ${policy?.enabled ? 'secondary' : 'primary'} tiny`}
          disabled={busy || (!account.active && !policy?.enabled)}
          onClick={() => void save(!policy?.enabled)}
        >
          {busy ? 'Saving…' : policy?.enabled ? 'Turn off' : 'Enable recent sync'}
        </button>
        {policy?.enabled && (
          <button
            className="button secondary tiny"
            disabled={busy || !account.active}
            onClick={() => void save(true, true)}
          >
            <RefreshCw size={12} /> Scan now
          </button>
        )}
      </div>
      {policy && (
        <p className="funding-pending-state">
          {['queued', 'running'].includes(policy.status)
            ? `Reading the frozen window · ${policy.pages} pages committed.`
            : policy.status === 'retrying'
              ? 'Provider read waiting for retry.'
              : policy.last_checked_at
                ? `Last finished ${date(policy.last_checked_at)}.`
                : 'No finished history scan yet.'}
          {policy.enabled && policy.next_scan_at && (
            <> Next opportunity {date(policy.next_scan_at)}.</>
          )}
          {policy.retry_at && <> Retry after {date(policy.retry_at)}.</>}
        </p>
      )}
      {policy?.error && (
        <p role="status" className="field-warning">
          {policy.error}
        </p>
      )}
      {!!policy?.uncovered_gap_count && (
        <div className="field-warning">
          <strong>
            {policy.uncovered_gap_count}{' '}
            {policy.uncovered_gap_count === 1 ? 'interval has' : 'intervals have'} not been fetched
            in a completed window.
          </strong>
          <p>
            Import these dates manually or widen the lookback. Provider retention still limits what
            can be returned.
          </p>
          <ul>
            {policy.uncovered_gaps.map((gap) => (
              <li key={gap.start_ms}>
                {date(gap.start_ms)} → {date(gap.end_ms)}
              </li>
            ))}
          </ul>
          {policy.uncovered_gap_count > policy.uncovered_gaps.length && (
            <small>Newest 10 shown.</small>
          )}
        </div>
      )}
      {report && (
        <details
          className="funding-pending-attention"
          onToggle={(event) => setHistoryOpen(event.currentTarget.open)}
        >
          <summary>Latest window &amp; saved scans</summary>
          <p>
            {date(report.start_ms)} → {date(report.end_ms)} · {report.inserted} new ·{' '}
            {report.updated} updated
          </p>
          {!!report.not_returned && (
            <p className="field-warning">
              {report.not_returned} retained records were not returned in this pass. Their values
              remain unchanged.
            </p>
          )}
          {report.not_returned_preview?.map((item) => (
            <p key={item.id}>
              <code>{item.native_id || item.id.slice(0, 12)}</code> ·{' '}
              {item.asset || 'Asset unavailable'} · {item.status || 'Record unavailable'}
            </p>
          ))}
          {!!report.concurrent_changes && (
            <p>{report.concurrent_changes} concurrent source changes were preserved.</p>
          )}
          {report.gap && (
            <p className="field-warning">
              Time outside the lookback: {date(report.gap.start_ms)} → {date(report.gap.end_ms)}.
              Import that range manually.
            </p>
          )}
          {historyOpen && <ScanHistory accountId={account.id} stream={stream} />}
          <small>
            Newest 20 scans retained. A finished scan is not complete history or final settlement
            verification.
          </small>
        </details>
      )}
      {!account.active && (
        <p className="footnote">Activate this account in Settings to enable recent sync.</p>
      )}
    </section>
  );
}

function ScanHistory({ accountId, stream }: { accountId: string; stream: Stream }) {
  const data = useResource<{ items: ScanReport[] }>(
    `/connections/${encodeURIComponent(accountId)}/funding-scans/${stream}/reports`,
  );
  if (data.error) return <ErrorState message={data.error} retry={data.retry} />;
  if (!data.data) return <Loading />;
  return (
    <ul className="funding-scan-history">
      {data.data.items.map((item) => (
        <li key={item.id}>
          {date(item.completed_at)} · {item.inserted} new / {item.updated} updated /{' '}
          {item.not_returned} not returned
        </li>
      ))}
    </ul>
  );
}

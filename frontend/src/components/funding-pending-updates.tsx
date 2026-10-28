import { useState } from 'react';
import { Clock3, RefreshCw, Radar } from 'lucide-react';
import { post, refresh } from '../lib/api';
import { Badge, Panel, PanelTitle, useToast } from './ui';

type Stream = 'deposit' | 'withdrawal' | 'transfer';
export type FundingUpdatePolicy = {
  account_id: string;
  stream: Stream;
  revision: string;
  enabled: boolean;
  interval_minutes: number;
  status: string;
  pending_count: number;
  needs_review: number;
  last_checked_at: string | null;
  last_success_at: string | null;
  next_check_at: string | null;
  retry_at: string | null;
  error: string | null;
  checked: number;
  updated: number;
  attention: {
    id: string;
    native_id: string;
    asset: string;
    status: string;
    missing_checks: number;
  }[];
};
const names: Record<Stream, string> = {
  deposit: 'Deposits',
  withdrawal: 'Withdrawals',
  transfer: 'Transfers',
};
const date = (value: string) => new Date(value).toLocaleString();

/** Background reads are explicit opt-ins, separate from the user's manual import cursor. */
export function FundingPendingUpdates({
  account,
  policies,
  inspect,
}: {
  account: { id: string; active: boolean; pending_update_streams: Stream[] };
  policies: FundingUpdatePolicy[];
  inspect: (asset: string, status: string) => void;
}) {
  if (!account.pending_update_streams?.length) return null;
  return (
    <Panel className="full-panel funding-pending-panel">
      <PanelTitle
        title="Pending updates"
        subtitle="Optional background checks for unfinished records you have already imported"
      />
      <div className="funding-pending-options">
        {account.pending_update_streams.map((stream) => {
          const policy = policies.find(
            (item) => item.account_id === account.id && item.stream === stream,
          );
          return (
            <PendingStream
              key={`${account.id}:${stream}:${policy?.revision || 'new'}`}
              account={account}
              stream={stream}
              policy={policy}
              inspect={inspect}
            />
          );
        })}
      </div>
      <p className="footnote padded">
        Only existing pending, restricted or unknown records are revisited. Unreturned records keep
        their original status; after five exhausted checks they need review. Pausing an import or
        deactivating the account turns these updates off. Use recent history sync or manual range
        imports for completed corrections and new funding.
      </p>
    </Panel>
  );
}

function PendingStream({
  account,
  stream,
  policy,
  inspect,
}: {
  account: { id: string; active: boolean };
  stream: Stream;
  policy?: FundingUpdatePolicy;
  inspect: (asset: string, status: string) => void;
}) {
  const [interval, setInterval] = useState(policy?.interval_minutes || 5);
  const [busy, setBusy] = useState(false);
  const toast = useToast();
  async function save(enabled: boolean, checkNow = false, minutes = interval) {
    setBusy(true);
    try {
      await post(`/connections/${encodeURIComponent(account.id)}/funding-refresh/${stream}`, {
        enabled,
        interval_minutes: minutes,
        replace_revision: policy?.revision || null,
        check_now: checkNow,
      });
      refresh();
      toast(
        checkNow
          ? 'Pending checks queued. Exchange rate limits still apply.'
          : enabled
            ? 'Pending updates enabled for this account.'
            : 'Pending updates turned off. Imported records preserved.',
      );
    } catch (reason) {
      toast((reason as Error).message, true);
      refresh();
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="funding-pending-option">
      <div className="funding-pending-heading">
        <span className="funding-pending-symbol">
          <Radar size={18} />
        </span>
        <div>
          <strong>{names[stream]}</strong>
          <small>
            {policy
              ? `${policy.pending_count} unfinished · ${policy.updated} source ${policy.updated === 1 ? 'update' : 'updates'} retained`
              : 'Off until you enable it'}
          </small>
        </div>
        <Badge
          tone={
            policy?.status === 'error' || policy?.needs_review
              ? 'peach'
              : policy?.enabled
                ? 'lime'
                : 'neutral'
          }
        >
          {policy?.status === 'error' ? 'Needs attention' : policy?.enabled ? 'Updates on' : 'Off'}
        </Badge>
      </div>
      <div className="funding-pending-controls">
        <label>
          <Clock3 size={13} /> Check interval
          <select
            aria-label={`${names[stream]} pending check interval`}
            disabled={busy || !account.active}
            value={interval}
            onChange={(event) => {
              const value = Number(event.target.value);
              setInterval(value);
              if (policy?.enabled) void save(true, false, value);
            }}
          >
            <option value={5}>5 minutes</option>
            <option value={15}>15 minutes</option>
            <option value={60}>1 hour</option>
          </select>
        </label>
        <button
          className={`button ${policy?.enabled ? 'secondary' : 'primary'} tiny`}
          disabled={busy || (!account.active && !policy?.enabled)}
          onClick={() => void save(!policy?.enabled)}
        >
          {busy ? 'Saving…' : policy?.enabled ? 'Turn off' : 'Enable updates'}
        </button>
        {policy?.enabled && (
          <button
            className="button secondary tiny"
            disabled={busy || !account.active}
            onClick={() => void save(true, true)}
          >
            <RefreshCw size={12} /> Check now
          </button>
        )}
      </div>
      {policy && (
        <p className="funding-pending-state">
          {policy.status === 'running' || policy.status === 'queued'
            ? 'Checking a bounded source window…'
            : policy.status === 'retrying'
              ? 'Provider read waiting for retry.'
              : policy.last_checked_at
                ? `Last complete check ${date(policy.last_checked_at)}.`
                : 'No complete pending check yet.'}
          {policy.enabled && policy.next_check_at && (
            <> Next opportunity {date(policy.next_check_at)}.</>
          )}
          {policy.retry_at && <> Retry after {date(policy.retry_at)}.</>}
        </p>
      )}
      {policy?.error && (
        <p className="field-warning" role="status">
          {policy.error}
        </p>
      )}
      {!!policy?.needs_review && (
        <details className="funding-pending-attention">
          <summary>
            {policy.needs_review} {policy.needs_review === 1 ? 'record needs' : 'records need'}{' '}
            review
          </summary>
          <p>
            These records were absent from five exhausted source windows. They have not been marked
            completed or cancelled. Check the exchange and your history range. Check now explicitly
            retries them.
          </p>
          {policy.attention.map((item) => (
            <button
              className="text-link"
              key={item.id}
              onClick={() => inspect(item.asset, item.status)}
              title={item.native_id}
            >
              {item.asset} · {item.native_id.slice(0, 18)}
              {item.native_id.length > 18 ? '…' : ''} · {item.status}
            </button>
          ))}
          {policy.needs_review > policy.attention.length && (
            <small>Newest 10 shown. Filter unfinished funding to inspect the rest.</small>
          )}
        </details>
      )}
      {!account.active && (
        <p className="footnote">
          Activate this account in Settings before enabling pending updates.
        </p>
      )}
    </section>
  );
}

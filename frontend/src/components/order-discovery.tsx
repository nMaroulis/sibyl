import { useId, useState } from 'react';
import { Link } from 'react-router-dom';
import { Pause, RefreshCw } from 'lucide-react';
import { useResource } from '../lib/hooks';
import { post, refresh } from '../lib/api';
import { Badge, ErrorState, useToast } from './ui';
import { ExchangeMark } from './exchange-mark';

type DiscoveryJob = {
  account_id: string;
  account: string;
  exchange: string;
  environment: string;
  state: string;
  enabled: boolean;
  complete: boolean;
  days: number;
  symbols: string[];
  pages: number;
  retained_orders: number;
  skipped: number;
  deferred: number;
  error: string | null;
  last_success_at: string | null;
  completed_at: string | null;
};
type Discovery = {
  accounts: {
    id: string;
    label: string;
    exchange: string;
    environment: string;
    active: boolean;
    supported: boolean;
    history_requires_symbols: boolean;
  }[];
  jobs: DiscoveryJob[];
  note: string;
};
const stateLabel: Record<string, string> = {
  queued: 'Queued',
  running: 'Reading orders',
  retrying: 'Waiting to retry',
  idle: 'Pass finished · watching',
  paused: 'Discovery paused',
  waiting_account: 'Account inactive',
  disconnected: 'Disconnected',
  error: 'Needs attention',
  limited: 'Coverage limit reached',
};

/** Explicit read-only synchronization, separate from the order-submission controls. */
export function OrderDiscovery({ active }: { active: boolean }) {
  const formId = useId();
  const pairNoteId = useId();
  const resource = useResource<Discovery>('/exchange-orders/discovery', 5000, active);
  const [expanded, setExpanded] = useState(false);
  const [account, setAccount] = useState('');
  const [symbols, setSymbols] = useState('');
  const [days, setDays] = useState(1);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const toast = useToast();
  const accounts = resource.data?.accounts.filter((row) => row.active && row.supported) ?? [];
  const binance = accounts.some(
    (row) => (!account || row.id === account) && row.history_requires_symbols,
  );
  const start = async (job?: DiscoveryJob) => {
    setBusy(true);
    setError('');
    try {
      await post('/exchange-orders/discovery', {
        account_id: job?.account_id ?? account,
        symbols:
          job?.symbols ??
          symbols
            .toUpperCase()
            .split(/[\s,]+/)
            .filter(Boolean),
        days: job?.days ?? days,
      });
      refresh();
      toast('Order discovery queued. Imported orders remain read-only.');
      setExpanded(false);
    } catch (reason) {
      setError((reason as Error).message);
    } finally {
      setBusy(false);
    }
  };
  const pause = async (job: DiscoveryJob) => {
    setBusy(true);
    setError('');
    try {
      await post(`/exchange-orders/discovery/${encodeURIComponent(job.account_id)}/pause`);
      refresh();
    } catch (reason) {
      setError((reason as Error).message);
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="order-discovery">
      <div className="order-discovery-heading">
        <div>
          <strong>Orders across your exchanges</strong>
          <p className="muted">
            Discover open orders and recent history, including orders placed outside Sibyl.
          </p>
        </div>
        <button
          className="button secondary tiny"
          aria-expanded={expanded}
          aria-controls={formId}
          onClick={() => setExpanded(!expanded)}
        >
          <RefreshCw size={14} /> Sync exchange orders
        </button>
      </div>
      {expanded && (
        <div id={formId}>
          {resource.error ? (
            <ErrorState message={resource.error} retry={resource.retry} />
          ) : !accounts.length ? (
            <p className="inline-alert">
              Activate a supported exchange account or Demo in{' '}
              <Link to="/settings?tab=exchanges">Settings ↗</Link>. Binance, Coinbase, Kraken and
              their dedicated test/demo clients support discovery.
            </p>
          ) : (
            <form
              className="workspace-controls"
              onSubmit={(event) => {
                event.preventDefault();
                start();
              }}
            >
              <label>
                Accounts
                <select
                  value={account}
                  onChange={(event) => setAccount(event.target.value)}
                  disabled={busy}
                >
                  <option value="">All active supported accounts</option>
                  {accounts.map((row) => (
                    <option value={row.id} key={row.id}>
                      {row.label} · {row.environment}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Recent history
                <select
                  value={days}
                  onChange={(event) => setDays(Number(event.target.value))}
                  disabled={busy}
                >
                  <option value={1}>Last 24 hours</option>
                  <option value={3}>Last 3 days</option>
                  <option value={7}>Last 7 days</option>
                </select>
              </label>
              {binance && (
                <label className="order-discovery-pairs">
                  Binance history pairs · optional
                  <input
                    value={symbols}
                    onChange={(event) => setSymbols(event.target.value)}
                    placeholder="BTC/USDT, ETH/USDT"
                    disabled={busy}
                    aria-describedby={pairNoteId}
                    maxLength={320}
                  />
                </label>
              )}
              <button className="button" disabled={busy}>
                {busy ? 'Queuing…' : 'Start read-only sync'}
              </button>
              <p className="footnote" id={pairNoteId}>
                Open orders cover all supported spot pairs.{' '}
                {binance &&
                  'Binance recent history needs up to 12 exact pairs; leave this blank for open orders only on Binance. '}
                Enabled discovery checks again about every five minutes while the account is active.
                Individual order tracking is separate.
              </p>
            </form>
          )}
        </div>
      )}
      {error && (
        <p className="form-error" role="alert">
          {error}
        </p>
      )}
      {!!resource.data?.jobs.length && (
        <div className="order-discovery-jobs">
          {resource.data.jobs.map((job) => (
            <div className="order-discovery-job" key={job.account_id}>
              <ExchangeMark exchange={job.exchange} size={28} />
              <div>
                <strong>
                  {job.account} <Badge>{job.environment}</Badge>
                </strong>
                <small>
                  {stateLabel[job.state] || job.state} · {job.retained_orders} imported ·{' '}
                  {job.pages} pages this pass
                  {job.last_success_at
                    ? ` · Read ${new Date(job.last_success_at).toLocaleTimeString()}`
                    : ''}
                </small>
                {job.exchange.startsWith('binance') && (
                  <small>
                    Recent history:{' '}
                    {job.symbols.length
                      ? job.symbols.join(', ')
                      : 'not selected · open orders only'}
                  </small>
                )}
                {job.skipped > 0 && (
                  <small>
                    {job.skipped} observations excluded: unsupported/delisted or margin instruments.
                  </small>
                )}
                {job.deferred > 0 && (
                  <small>
                    Some client IDs match uncertain Sibyl submissions. Use Recover order on those
                    rows.
                  </small>
                )}
                {job.error && <small className="negative">{job.error}</small>}
              </div>
              <button
                className="button secondary tiny"
                disabled={busy || job.state === 'disconnected'}
                onClick={() => (job.enabled ? pause(job) : start(job))}
              >
                {job.enabled ? (
                  <>
                    <Pause size={13} /> Pause discovery
                  </>
                ) : (
                  <>
                    <RefreshCw size={13} /> Resume
                  </>
                )}
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

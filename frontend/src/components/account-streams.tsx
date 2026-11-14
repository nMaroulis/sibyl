import { useState } from 'react';
import { Radio, Play, Pause, LoaderCircle } from 'lucide-react';
import { api, refresh } from '../lib/api';
import { useResource } from '../lib/hooks';
import { Badge, ErrorState, useToast } from './ui';
import { ExchangeMark } from './exchange-mark';

type Stream = {
  account_id: string;
  account: string;
  exchange: string;
  active: boolean;
  supported: boolean;
  sandbox: boolean;
  revision: string;
  state: string;
  enabled: boolean;
  error?: string;
  signals?: number;
  connections?: number;
  last_signal_at?: string;
  last_wakeup_at?: string;
  last_wakeup?: { status: number; fills: number; discovery: number };
};
type State = { accounts: Stream[]; scope: string; limit: number };
const status = (value: string) =>
  ({
    off: 'Off',
    queued: 'Starting',
    subscribing: 'Waiting for order signals',
    observed: 'Signals observed',
    retrying: 'Reconnecting',
    attention: 'Check access',
    inactive: 'Account inactive',
    paused: 'Paused',
    credentials_changed: 'Keys changed',
  })[value] ?? value;

/** Private events accelerate separately enabled REST reads; no stream-driven execution. */
export function AccountStreams() {
  const resource = useResource<State>('/account-streams', 5000);
  const [busy, setBusy] = useState('');
  const toast = useToast();
  const accounts = resource.data?.accounts.filter((row) => row.supported) ?? [];
  if (!accounts.length && !resource.error) return null;
  return (
    <details className="account-streams">
      <summary>
        <Radio size={15} /> Live order updates <span>Optional · REST-backed</span>
      </summary>
      {resource.error ? (
        <ErrorState message={resource.error} retry={resource.retry} />
      ) : (
        <>
          <p className="footnote">
            Enable private order signals for a saved active account. Existing order/fill tracking
            and discovery need their own controls; paused readers stay paused. This never places or
            cancels an order.
          </p>
          <div className="account-stream-list">
            {accounts.map((row) => (
              <article key={row.account_id}>
                <ExchangeMark exchange={row.exchange} size={25} />
                <div>
                  <strong>{row.account}</strong>
                  <small>
                    {row.signals ?? 0} distinct order signals
                    {row.connections ? ` · ${row.connections} connection attempts` : ''}
                  </small>
                  {row.last_signal_at && (
                    <small>Last signal {new Date(row.last_signal_at).toLocaleString()}</small>
                  )}
                  {row.last_wakeup_at && (
                    <small>
                      REST reads scheduled {new Date(row.last_wakeup_at).toLocaleTimeString()} ·
                      status {row.last_wakeup?.status ?? 0} / fills {row.last_wakeup?.fills ?? 0} /
                      discovery {row.last_wakeup?.discovery ?? 0}
                    </small>
                  )}
                  {row.error && <small className="form-error">{row.error}</small>}
                </div>
                <Badge
                  tone={
                    row.state === 'attention' || row.state === 'credentials_changed'
                      ? 'rose'
                      : 'neutral'
                  }
                >
                  {status(row.state)}
                </Badge>
                <button
                  type="button"
                  className="button secondary tiny"
                  disabled={!!busy || (!row.active && !row.enabled)}
                  onClick={async () => {
                    setBusy(row.account_id);
                    try {
                      await api(`/account-streams/${row.account_id}`, {
                        method: 'PUT',
                        body: JSON.stringify({ revision: row.revision, enabled: !row.enabled }),
                      });
                      toast(
                        row.enabled
                          ? 'Private order signals paused.'
                          : 'Private order observer enabled. REST tracking remains independent.',
                      );
                      resource.retry();
                      refresh();
                    } catch (error) {
                      toast((error as Error).message, true);
                    } finally {
                      setBusy('');
                    }
                  }}
                >
                  {busy === row.account_id ? (
                    <LoaderCircle size={13} className="spin" />
                  ) : row.enabled ? (
                    <Pause size={13} />
                  ) : (
                    <Play size={13} />
                  )}
                  {row.enabled ? 'Pause' : 'Enable signals'}
                </button>
              </article>
            ))}
          </div>
          <p className="footnote">{resource.data?.scope}</p>
        </>
      )}
    </details>
  );
}

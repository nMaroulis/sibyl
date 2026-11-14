import { useState } from 'react';
import { ArrowUpRight, Check, Edit3, Mail, Pause, Play, RefreshCw, Unplug } from 'lucide-react';
import { Badge, Modal, useToast } from '../ui';
import { SecretField } from '../secret-field';
import type { MessagingChannel } from '../messaging-settings';
import { api, post, refresh } from '../../lib/api';
import { useResource } from '../../lib/hooks';

type Channel = MessagingChannel & {
  configured?: boolean;
  revision?: string;
  settings?: Record<string, string | number>;
  updates?: Record<string, number>;
  delivery?: Record<string, number>;
  last_message_at?: number;
};
type Receipt = {
  id: string;
  state: string;
  target: string;
  attempts: number;
  created_at: number;
  provider_id?: string;
  error?: string;
};

/** Write-only connection editing, clear live controls and actual provider acceptance receipts. */
export function PrivateChannelSetup({ channel, done }: { channel: Channel; done: () => void }) {
  const [editing, setEditing] = useState(false),
    [busy, setBusy] = useState(''),
    [error, setError] = useState('');
  const [secrets, setSecrets] = useState<Record<string, string>>({}),
    [showReceipts, setShowReceipts] = useState(false);
  const receipts = useResource<{ items: Receipt[]; note: string }>(
    `/settings/messaging/channels/${channel.id}/receipts`,
    0,
    showReceipts,
  );
  const toast = useToast();
  const action = async (action: 'check' | 'enable' | 'pause' | 'disconnect') => {
    if (!channel.revision) return;
    setBusy(action);
    setError('');
    try {
      await post(`/settings/messaging/channels/${channel.id}/action`, {
        action,
        revision: channel.revision,
      });
      done();
      refresh();
      if (action === 'disconnect') setEditing(true);
      toast(
        action === 'check'
          ? 'Connection identity checked.'
          : action === 'enable'
            ? 'Private messaging enabled.'
            : action === 'pause'
              ? 'New receive and reply work paused.'
              : 'Local connection removed.',
      );
    } catch (reason) {
      setError((reason as Error).message);
    } finally {
      setBusy('');
    }
  };
  const save = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setBusy('save');
    setError('');
    const data = new FormData(event.currentTarget),
      settings: Record<string, string | number> = {};
    for (const field of channel.fields)
      settings[field.id] =
        field.type === 'password'
          ? (secrets[field.id] ?? '')
          : field.type === 'number'
            ? Number(data.get(field.id))
            : String(data.get(field.id) ?? '');
    try {
      await api(`/settings/messaging/channels/${channel.id}`, {
        method: 'PUT',
        body: JSON.stringify({ revision: channel.revision ?? null, settings }),
      });
      setEditing(false);
      setSecrets({});
      done();
      refresh();
      toast('Connection saved locally and encrypted. Check it, then enable private replies.');
    } catch (reason) {
      setError((reason as Error).message);
    } finally {
      setBusy('');
    }
  };
  const accepted = channel.delivery?.sent ?? 0,
    waiting = (channel.delivery?.pending ?? 0) + (channel.delivery?.sending ?? 0);
  return (
    <section className={`messaging-card ${channel.enabled ? 'private-channel-active' : ''}`}>
      <div className="messaging-card-heading">
        <span className={`channel-icon channel-${channel.id}`}>
          {channel.id === 'email' ? (
            <Mail size={27} />
          ) : (
            <img src={`/messaging/${channel.id}.svg`} width={27} height={27} alt="" />
          )}
        </span>
        <div>
          <h3>{channel.name}</h3>
          <small>
            {channel.enabled
              ? 'Private replies enabled'
              : channel.configured
                ? 'Credentials saved locally'
                : 'Not connected'}
          </small>
        </div>
        <Badge tone={channel.enabled ? 'sage' : 'neutral'}>
          {channel.enabled ? (
            <>
              <span className="channel-running-dot" />
              Running
            </>
          ) : channel.connected ? (
            'Checked'
          ) : channel.configured ? (
            'Saved'
          ) : (
            'Available'
          )}
        </Badge>
      </div>
      <p>{channel.description}</p>
      {channel.enabled && (
        <div className="channel-live-state">
          <span className="channel-running-dot" />
          <div>
            <strong>Listening for your private messages</strong>
            <small>
              {channel.last_poll_at
                ? `Receiver checked ${new Date(channel.last_poll_at * 1000).toLocaleTimeString()}`
                : 'Waiting for the first receiver check'}{' '}
              · {accepted} reply parts accepted · {waiting} queued
            </small>
          </div>
        </div>
      )}
      {!editing && channel.configured && (
        <>
          <div className="channel-saved-identity">
            <Check size={16} />
            <div>
              <strong>{channel.bot_username || 'Saved connection'}</strong>
              <small>
                {String(
                  channel.settings?.allowed_user_id ??
                    channel.settings?.allowed_sender_aci ??
                    channel.settings?.allowed_sender ??
                    'Bound private recipient',
                )}{' '}
                · credentials hidden
              </small>
            </div>
          </div>
          <div className="inline-actions">
            <button
              className="button secondary tiny"
              disabled={!!busy || channel.enabled}
              onClick={() => {
                setEditing(true);
                setSecrets({});
              }}
            >
              <Edit3 size={13} />
              Edit connection
            </button>
            <button
              className="button secondary tiny"
              disabled={!!busy || channel.enabled}
              onClick={() => action('check')}
            >
              <RefreshCw size={13} />
              {busy === 'check' ? 'Checking…' : 'Check connection'}
            </button>
            {channel.enabled ? (
              <button
                className="button secondary tiny"
                disabled={!!busy}
                onClick={() => action('pause')}
              >
                <Pause size={14} />
                Pause replies
              </button>
            ) : (
              <button
                className="button primary tiny"
                disabled={!!busy}
                onClick={() => action('enable')}
              >
                <Play size={14} />
                {busy === 'enable' ? 'Enabling…' : 'Enable private replies'}
              </button>
            )}
          </div>
        </>
      )}
      {!channel.configured && !editing && (
        <button className="button secondary tiny" onClick={() => setEditing(true)}>
          Set up {channel.name}
        </button>
      )}
      {editing && (
        <Modal
          title={`${channel.configured ? 'Edit' : 'Connect'} ${channel.name}`}
          onClose={() => setEditing(false)}
        >
          <form className="form messaging-fields" onSubmit={save}>
            {channel.fields.map((field) => (
              <div key={field.id}>
                {field.type === 'password' ? (
                  <SecretField
                    label={field.label}
                    value={secrets[field.id] ?? ''}
                    onChange={(value) => setSecrets({ ...secrets, [field.id]: value })}
                  />
                ) : (
                  <label>
                    {field.label}
                    {field.type === 'select' ? (
                      <select
                        name={field.id}
                        defaultValue={String(
                          channel.settings?.[field.id] ?? field.options?.[0] ?? '',
                        )}
                      >
                        {field.options?.map((option) => (
                          <option key={option}>{option}</option>
                        ))}
                      </select>
                    ) : (
                      <input
                        name={field.id}
                        type={field.type}
                        required
                        defaultValue={channel.settings?.[field.id] ?? ''}
                        placeholder={field.placeholder}
                        autoComplete="off"
                      />
                    )}
                  </label>
                )}
                {field.help && <small>{field.help}</small>}
              </div>
            ))}
            <p className="footnote">
              Credentials stay encrypted in this backend’s local vault. Saving keeps the channel
              paused. Editing requires complete replacement credentials; saved secrets are never
              returned to this form.
            </p>
            <div className="inline-actions">
              <button className="button primary tiny" disabled={!!busy}>
                {busy === 'save' ? 'Saving…' : 'Save connection'}
              </button>
              {channel.configured && (
                <button
                  className="button secondary tiny"
                  type="button"
                  onClick={() => setEditing(false)}
                >
                  Cancel
                </button>
              )}
            </div>
          </form>
        </Modal>
      )}
      {error && (
        <p role="alert" className="form-error">
          {error}
        </p>
      )}
      {channel.error && <p className="monitor-notice">{channel.error}</p>}
      <div className="messaging-card-footer">
        <p>{channel.setup_note}</p>
        <a className="text-link" href={channel.docs_url} target="_blank" rel="noreferrer">
          Provider setup guide <ArrowUpRight size={12} />
        </a>
      </div>
      {channel.configured && (
        <div className="inline-actions">
          <button className="text-button" onClick={() => setShowReceipts(true)}>
            Reply receipts ↗
          </button>
          <button
            className="text-button"
            disabled={!!busy || channel.enabled}
            onClick={() => action('disconnect')}
          >
            <Unplug size={12} />
            Remove connection
          </button>
        </div>
      )}
      {showReceipts && (
        <Modal title={`${channel.name} reply receipts`} onClose={() => setShowReceipts(false)}>
          <p className="footnote">{receipts.data?.note ?? 'Loading actual send outcomes…'}</p>
          {receipts.error && <p role="alert">{receipts.error}</p>}
          {receipts.data?.items.map((row) => (
            <div className="worker-health-row" key={row.id}>
              <div>
                <strong>{row.state}</strong>
                <small>
                  {new Date(row.created_at * 1000).toLocaleString()} · {row.target}
                </small>
                {row.error && <p className="footnote">{row.error}</p>}
              </div>
              <Badge>{row.attempts} attempts</Badge>
            </div>
          ))}
        </Modal>
      )}
    </section>
  );
}

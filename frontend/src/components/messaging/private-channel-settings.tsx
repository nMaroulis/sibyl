import { useState } from 'react';
import { ArrowUpRight, Check, Edit3, Mail, Unplug } from 'lucide-react';
import { Badge, Modal, useToast } from '../ui';
import { SecretField } from '../secret-field';
import { ChannelActivity } from './channel-activity';
import { ChannelControls } from './channel-controls';
import type { ChannelAction } from './channel-controls';
import type { MessagingChannel } from '../messaging-settings';
import { api, post, refresh } from '../../lib/api';
import { useResource } from '../../lib/hooks';

type Channel = MessagingChannel & {
  revision?: string;
  settings?: Record<string, string | number>;
  delivery?: Record<string, number>;
  updates?: Record<string, number>;
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
  const action = async (action: ChannelAction | 'disconnect') => {
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
        {
          check: 'Connection identity checked.',
          enable: 'Private messaging enabled.',
          pause: 'New receive and reply work paused.',
          stop: 'Listener stopped. Queued conversation work was cleared.',
          disconnect: 'Local connection removed.',
        }[action],
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
  const updates = channel.updates ?? {};
  const delivery = channel.delivery ?? {};
  const received = Object.values(updates).reduce((sum, count) => sum + count, 0);
  const waiting =
    (updates.queued ?? 0) +
    (updates.processing ?? 0) +
    (delivery.pending ?? 0) +
    (delivery.sending ?? 0);
  return (
    <section
      className={`messaging-card ${channel.configured ? 'private-channel-active' : ''}`}
      aria-labelledby={`messaging-${channel.id}-title`}
    >
      <div className="messaging-card-heading">
        <span className={`channel-icon channel-${channel.id}`}>
          {channel.id === 'email' ? (
            <Mail size={27} />
          ) : (
            <img src={`/messaging/${channel.id}.svg`} width={27} height={27} alt="" />
          )}
        </span>
        <div>
          <h3 id={`messaging-${channel.id}-title`}>{channel.name}</h3>
          <small>
            {channel.enabled
              ? 'Private replies enabled'
              : channel.configured
                ? 'Credentials saved locally'
                : 'Not connected'}
          </small>
        </div>
        {!channel.configured && <Badge>Available</Badge>}
      </div>
      <p>{channel.description}</p>
      {channel.configured && (
        <ChannelActivity
          channelId={channel.id}
          channelName={channel.name}
          enabled={channel.enabled}
          stopped={channel.stopped}
          paused={channel.has_started}
          logs={channel.logs}
          lastReceive={channel.last_poll_at}
          webhook={channel.id === 'whatsapp'}
          attention={!!channel.error}
          working={Boolean(updates.processing || delivery.sending)}
          counts={[
            { label: 'Messages received', value: received },
            { label: 'Parts accepted', value: delivery.sent ?? 0 },
            { label: 'In progress', value: waiting },
          ]}
          controls={
            <ChannelControls
              name={channel.name}
              enabled={channel.enabled}
              started={channel.has_started}
              stopped={channel.stopped}
              busy={busy}
              editing={editing}
              action={(kind) => void action(kind)}
            />
          }
        />
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
          {!channel.enabled && (
            <div className="inline-actions">
              <button
                className="button secondary tiny"
                disabled={!!busy}
                onClick={() => {
                  setEditing(true);
                  setSecrets({});
                }}
              >
                <Edit3 size={13} />
                Edit connection
              </button>
            </div>
          )}
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

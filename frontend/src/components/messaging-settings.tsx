import { MessageCircle, ArrowUpRight, Mail } from 'lucide-react';
import { Link } from 'react-router-dom';
import { useState } from 'react';
import { api, post, refresh } from '../lib/api';
import { useResource } from '../lib/hooks';
import { Badge, ErrorState, Loading, useToast } from './ui';

type Channel = {
  id: string;
  name: string;
  description: string;
  docs_url: string;
  setup_note: string;
  connected: boolean;
  status: 'unavailable' | 'available';
  enabled?: boolean;
  has_token?: boolean;
  allowed_user_id?: number;
  bot_username?: string;
  error?: string;
  fields: {
    id: string;
    label: string;
    type: 'text' | 'password' | 'tel' | 'email' | 'url' | 'number' | 'select';
    placeholder: string;
    options?: string[];
    group?: string;
    help?: string;
  }[];
};
type Settings = {
  channels: Channel[];
  telegram?: {
    updates: Record<string, number>;
    delivery: Record<string, number>;
    llm_ready: boolean;
  };
};

/** Show app icons and future setup fields; unavailable clients collect nothing. */
export function MessagingSettings() {
  const resource = useResource<Settings>('/settings/messaging', 5000);
  return (
    <div className="messaging-settings">
      <div className="messaging-intro">
        <span className="messaging-intro-icon">
          <MessageCircle size={25} />
        </span>
        <div>
          <h2>Sibyl, wherever you are.</h2>
          <p>
            Talk to Sibyl through Telegram using the same AI agents and conversations as the app.
          </p>
        </div>
      </div>
      <p className="messaging-unavailable-note" id="messaging-unavailable-note">
        <strong>Telegram is available.</strong> Other apps and email remain coming soon. Telegram
        can relay workspace information through your bot and selected AI provider; only enable it
        for your own private user ID.
      </p>
      {resource.loading ? (
        <Loading />
      ) : resource.error ? (
        <ErrorState message={resource.error} retry={resource.retry} />
      ) : (
        <div className="messaging-grid">
          {resource.data?.channels
            .slice()
            .sort((a, b) => Number(b.status === 'available') - Number(a.status === 'available'))
            .map((channel) =>
              channel.id === 'telegram' ? (
                <TelegramSetup
                  key={channel.id}
                  channel={channel}
                  health={resource.data?.telegram}
                  done={resource.retry}
                />
              ) : (
                <ChannelSetup key={channel.id} channel={channel} />
              ),
            )}
        </div>
      )}
      <p className="footnote">
        Messaging will use Sibyl’s configured AI model.{' '}
        <Link className="text-link" to="/settings?tab=models">
          AI model settings <ArrowUpRight size={12} />
        </Link>
      </p>
    </div>
  );
}

function TelegramSetup({
  channel,
  health,
  done,
}: {
  channel: Channel;
  health?: Settings['telegram'];
  done: () => void;
}) {
  const [token, setToken] = useState('');
  const [user, setUser] = useState(String(channel.allowed_user_id ?? ''));
  const [busy, setBusy] = useState('');
  const [error, setError] = useState('');
  const toast = useToast();
  const action = async (kind: string) => {
    setBusy(kind);
    setError('');
    try {
      if (kind === 'save')
        await post('/settings/messaging/telegram', {
          allowed_user_id: Number(user),
          ...(token.trim() ? { bot_token: token.trim() } : {}),
        });
      else if (kind === 'disconnect')
        await api('/settings/messaging/telegram', { method: 'DELETE' });
      else await post(`/settings/messaging/telegram/${kind}`, {});
      setToken('');
      done();
      refresh();
      toast(
        kind === 'enable'
          ? 'Telegram polling enabled. Open your private bot chat to talk to Sibyl.'
          : 'Telegram connection updated.',
      );
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy('');
    }
  };
  return (
    <section className="messaging-card telegram-live-card">
      <div className="messaging-card-heading">
        <span className="channel-icon channel-telegram">
          <img src="/messaging/telegram.svg" width="27" height="27" alt="" />
        </span>
        <div>
          <h3>Telegram</h3>
          <small>
            {channel.bot_username ? `@${channel.bot_username}` : 'Your private Sibyl bot'}
          </small>
        </div>
        <Badge tone={channel.enabled ? 'lime' : 'blue'}>
          {channel.enabled ? 'Listening' : 'Available'}
        </Badge>
      </div>
      <p>{channel.setup_note}</p>
      <div className="messaging-fields">
        <label>
          Bot token
          <input
            type="password"
            autoComplete="off"
            placeholder={
              channel.has_token ? 'Saved locally · leave blank to keep' : 'Token from @BotFather'
            }
            value={token}
            disabled={channel.enabled || !!busy}
            onChange={(e) => setToken(e.target.value)}
          />
        </label>
        <label>
          Your numeric Telegram user ID
          <input
            type="text"
            inputMode="numeric"
            placeholder="Your ID, not a username"
            value={user}
            disabled={channel.enabled || !!busy}
            onChange={(e) => setUser(e.target.value)}
          />
          <small>
            Only messages from this ID in its private chat are accepted. Groups, forwarded messages
            and other users are ignored.
          </small>
        </label>
      </div>
      {!health?.llm_ready && (
        <p className="inline-alert">
          Configure an <Link to="/settings?tab=models">AI model</Link> before enabling Telegram.
        </p>
      )}
      {(error || channel.error) && (
        <p className="form-error" role="alert">
          {error || channel.error}
        </p>
      )}
      <div className="telegram-actions">
        <button
          className="button primary"
          disabled={
            !!busy || channel.enabled || !/^\d+$/.test(user) || (!token && !channel.has_token)
          }
          onClick={() => action('save')}
        >
          Save connection
        </button>
        <button
          className="button secondary"
          disabled={!!busy || !channel.has_token}
          onClick={() => action('check')}
        >
          {busy === 'check' ? 'Checking…' : 'Check bot'}
        </button>
        <button
          className="button secondary"
          disabled={!!busy || !channel.has_token || (!channel.enabled && !health?.llm_ready)}
          onClick={() => action(channel.enabled ? 'pause' : 'enable')}
        >
          {channel.enabled ? 'Pause Telegram' : 'Enable Telegram'}
        </button>
        {channel.has_token && (
          <button
            className="text-button negative"
            disabled={!!busy}
            onClick={() => action('disconnect')}
          >
            Disconnect
          </button>
        )}
      </div>
      {health && (
        <div className="telegram-delivery-status">
          <span>{health.delivery.sent ?? 0} reply chunks sent</span>
          <span>{health.updates.queued ?? 0} questions queued</span>
          {!!health.delivery.uncertain && (
            <strong>
              {health.delivery.uncertain} deliveries uncertain — check Telegram; these will not
              retry automatically.
            </strong>
          )}
          {!!health.updates.interrupted && (
            <strong>{health.updates.interrupted} interrupted questions — send them again.</strong>
          )}
        </div>
      )}
      <div className="messaging-card-footer">
        <p>
          Create a bot with BotFather, save its token and your ID, check it, then enable. Open the
          bot’s private chat and press Start. /new resets context; /status checks model readiness.
          Tokens are locally encrypted; chat history is stored locally with Sibyl conversations.
        </p>
        <a className="text-link" href={channel.docs_url} target="_blank" rel="noreferrer">
          Bot setup guide <ArrowUpRight size={12} />
        </a>
      </div>
    </section>
  );
}

function ChannelSetup({ channel }: { channel: Channel }) {
  const groups = Array.from(new Set(channel.fields.map((field) => field.group ?? '')));
  const fields = (group: string) =>
    channel.fields
      .filter((field) => (field.group ?? '') === group)
      .map((field) => (
        <label key={field.id}>
          {field.label}
          {field.type === 'select' ? (
            <select
              name={`${channel.id}-${field.id}`}
              disabled
              value=""
              aria-describedby={field.help ? `${channel.id}-${field.id}-help` : undefined}
            >
              <option value="">{field.placeholder}</option>
              {field.options?.map((option) => (
                <option key={option} value={option}>
                  {option}
                </option>
              ))}
            </select>
          ) : (
            <input
              type={field.type}
              name={`${channel.id}-${field.id}`}
              placeholder={field.placeholder}
              autoComplete="off"
              disabled
              value=""
              readOnly
              aria-describedby={field.help ? `${channel.id}-${field.id}-help` : undefined}
            />
          )}
          {field.help && <small id={`${channel.id}-${field.id}-help`}>{field.help}</small>}
        </label>
      ));
  return (
    <section className="messaging-card" aria-labelledby={`messaging-${channel.id}-title`}>
      <div className="messaging-card-heading">
        <span className={`channel-icon channel-${channel.id}`}>
          {channel.id === 'email' ? (
            <Mail size={27} aria-hidden="true" />
          ) : (
            <img
              src={`/messaging/${channel.id}.svg`}
              width="27"
              height="27"
              alt=""
              aria-hidden="true"
            />
          )}
        </span>
        <div>
          <h3 id={`messaging-${channel.id}-title`}>{channel.name}</h3>
          <small>Not connected</small>
        </div>
        <Badge>Unavailable</Badge>
      </div>
      <p>{channel.description}</p>
      <fieldset className="messaging-fields" disabled aria-describedby="messaging-unavailable-note">
        <legend className="sr-only">{channel.name} setup requirements</legend>
        {groups.map((group) =>
          group ? (
            <details className="messaging-field-group" key={group} open={group === 'Mailbox'}>
              <summary>{group}</summary>
              {fields(group)}
            </details>
          ) : (
            <div key="fields">{fields(group)}</div>
          ),
        )}
      </fieldset>
      <div className="messaging-card-footer">
        <p>{channel.setup_note}</p>
        <a className="text-link" href={channel.docs_url} target="_blank" rel="noreferrer">
          Setup guide <ArrowUpRight size={12} />
        </a>
      </div>
    </section>
  );
}

import { MessageCircle, ArrowUpRight, Mail, TriangleAlert } from 'lucide-react';
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
      {resource.data?.telegram?.llm_ready === false && (
        <div className="messaging-model-warning" role="status">
          <TriangleAlert size={20} aria-hidden="true" />
          <div>
            <strong>No AI model is active</strong>
            <p>
              You can set up and enable messaging now. Add an AI model when you’re ready for Sibyl
              to answer questions.
            </p>
          </div>
          <Link className="text-link" to="/settings?tab=models">
            AI model settings <ArrowUpRight size={13} />
          </Link>
        </div>
      )}
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
      {resource.data?.telegram?.llm_ready && (
        <p className="footnote">
          Messaging will use Sibyl’s configured AI model.{' '}
          <Link className="text-link" to="/settings?tab=models">
            AI model settings <ArrowUpRight size={12} />
          </Link>
        </p>
      )}
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
  const userId = Number(user.trim());
  const validUser =
    /^\d+$/.test(user.trim()) && Number.isSafeInteger(userId) && userId > 0 && userId <= 2 ** 52;
  const validToken = /^\d{5,20}:[A-Za-z0-9_-]{20,200}$/.test(token.trim());
  const unsaved = !!token.trim() || user.trim() !== String(channel.allowed_user_id ?? '');
  const userHelp =
    user.trim() && !validUser
      ? 'Enter your personal numeric ID, not a bot link, username, phone number or bot token.'
      : 'Your personal account ID. The number before the colon in a bot token belongs to the bot.';
  const action = async (kind: string) => {
    if (kind === 'save') {
      if ((!token.trim() && !channel.has_token) || (token.trim() && !validToken)) {
        setError(
          'Enter the complete bot token from BotFather, including the colon. Do not enter the t.me link.',
        );
        return;
      }
      if (!validUser) {
        setError('Enter your own numeric Telegram user ID before saving this connection.');
        return;
      }
    }
    setBusy(kind);
    setError('');
    try {
      if (kind === 'save')
        await post('/settings/messaging/telegram', {
          allowed_user_id: userId,
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
      <form
        aria-label="Telegram connection"
        onSubmit={(event) => {
          event.preventDefault();
          void action('save');
        }}
        noValidate
      >
        <div className="messaging-fields">
          <label>
            Bot token
            <input
              type="password"
              autoComplete="off"
              aria-describedby="telegram-token-help"
              placeholder={
                channel.has_token ? 'Saved locally · leave blank to keep' : 'Token from @BotFather'
              }
              value={token}
              disabled={channel.enabled || !!busy}
              onChange={(e) => setToken(e.target.value)}
            />
            <small id="telegram-token-help">
              Paste the full token from BotFather. Your bot’s t.me link is only used to open its
              chat.
            </small>
          </label>
          <label>
            Your numeric Telegram user ID
            <input
              type="text"
              inputMode="numeric"
              autoComplete="off"
              aria-describedby="telegram-user-help"
              aria-invalid={!!user.trim() && !validUser}
              placeholder="Your ID, not a username"
              value={user}
              disabled={channel.enabled || !!busy}
              onChange={(e) => setUser(e.target.value)}
            />
            <small id="telegram-user-help">{userHelp}</small>
          </label>
        </div>
        <details className="telegram-id-help">
          <summary>Where do I find my personal user ID?</summary>
          <p>
            In Telegram, open{' '}
            <a href="https://t.me/userinfobot" target="_blank" rel="noreferrer">
              @userinfobot
            </a>{' '}
            (an optional third-party lookup), press Start and copy the numeric Id it reports. Only
            your personal ID goes here; do not send that bot your BotFather token.
          </p>
          <p>
            You can also read <code>message.from.id</code> from a private message to your own bot
            using Telegram’s{' '}
            <a
              href="https://core.telegram.org/bots/api#getupdates"
              target="_blank"
              rel="noreferrer"
            >
              getUpdates API
            </a>{' '}
            before enabling Sibyl.
          </p>
        </details>
        {(error || channel.error) && (
          <p className="form-error" role="alert">
            {error || channel.error}
          </p>
        )}
        <div className="telegram-actions">
          <button className="button primary" type="submit" disabled={!!busy || channel.enabled}>
            {busy === 'save' ? 'Saving…' : 'Save connection'}
          </button>
          <button
            className="button secondary"
            type="button"
            disabled={!!busy || !channel.has_token || (!channel.enabled && unsaved)}
            aria-describedby="telegram-action-help"
            onClick={() => action('check')}
          >
            {busy === 'check' ? 'Checking…' : 'Check bot'}
          </button>
          <button
            className="button secondary"
            type="button"
            disabled={!!busy || !channel.has_token || (!channel.enabled && unsaved)}
            aria-describedby="telegram-action-help"
            onClick={() => action(channel.enabled ? 'pause' : 'enable')}
          >
            {channel.enabled ? 'Pause Telegram' : 'Enable Telegram'}
          </button>
          {channel.has_token && (
            <button
              className="text-button negative"
              type="button"
              disabled={!!busy}
              onClick={() => action('disconnect')}
            >
              Disconnect
            </button>
          )}
        </div>
        <p className="telegram-action-help" id="telegram-action-help">
          {channel.enabled
            ? 'Pause Telegram to edit the connection. Only your configured user’s private messages are accepted.'
            : !channel.has_token
              ? 'Save your token and personal user ID to unlock Check bot and Enable Telegram.'
              : unsaved
                ? 'Save your changes before checking or enabling this connection.'
                : 'Connection saved. Check the bot, then enable Telegram and press Start in its private chat.'}
        </p>
      </form>
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

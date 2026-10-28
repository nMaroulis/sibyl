import { useEffect, useState } from 'react';
import {
  ArrowUpRight,
  Check,
  Clock3,
  KeyRound,
  LoaderCircle,
  MessageCircle,
  Pause,
  Pencil,
  Play,
  Radio,
  Send,
  ShieldCheck,
  Unplug,
  X,
} from 'lucide-react';
import { api, post, refresh } from '../lib/api';
import { useToast } from './ui';
import type { MessagingChannel, MessagingSettingsData } from './messaging-settings';

type Action = 'save' | 'check' | 'enable' | 'pause' | 'disconnect';

/** Separate encrypted setup from the polling controls; display only observed activity. */
export function TelegramSetup({
  channel,
  health,
  done,
}: {
  channel: MessagingChannel;
  health?: MessagingSettingsData['telegram'];
  done: () => void;
}) {
  const [editing, setEditing] = useState(!channel.has_token);
  const [token, setToken] = useState('');
  const [user, setUser] = useState(String(channel.allowed_user_id ?? ''));
  const [busy, setBusy] = useState<Action | ''>('');
  const [error, setError] = useState('');
  const toast = useToast();
  const saved = !!channel.has_token;
  const enabled = !!channel.enabled;
  const editorOpen = editing || !saved;
  const userId = Number(user.trim());
  const validUser =
    /^\d+$/.test(user.trim()) && Number.isSafeInteger(userId) && userId > 0 && userId <= 2 ** 52;
  const validToken = /^\d{5,20}:[A-Za-z0-9_-]{20,200}$/.test(token.trim());
  const problem = error || channel.error;
  const updates = health?.updates ?? {};
  const delivery = health?.delivery ?? {};
  const received =
    health?.summary?.messages_received ??
    Object.entries(updates).reduce(
      (sum, [state, count]) => (state === 'ignored' ? sum : sum + count),
      0,
    );
  const waiting =
    (updates.queued ?? 0) + (updates.processing ?? 0) + (health?.summary?.replies_waiting ?? 0);
  const mode = !saved
    ? 'setup'
    : enabled
      ? channel.error
        ? 'attention'
        : 'running'
      : channel.has_started
        ? 'paused'
        : 'ready';
  const stateLabel = {
    setup: 'Not connected',
    ready: 'Ready to start',
    paused: 'Paused',
    running: 'Listening',
    attention: 'Needs attention',
  }[mode];
  const working = enabled && ((updates.processing ?? 0) > 0 || (delivery.sending ?? 0) > 0);

  useEffect(() => {
    if (!editing) setUser(String(channel.allowed_user_id ?? ''));
  }, [channel.allowed_user_id, editing]);

  const action = async (kind: Action) => {
    if (busy) return;
    if (kind === 'save') {
      if ((!token.trim() && !saved) || (token.trim() && !validToken)) {
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
      if (kind === 'save') {
        await post('/settings/messaging/telegram', {
          allowed_user_id: userId,
          ...(token.trim() ? { bot_token: token.trim() } : {}),
        });
        setEditing(false);
      } else if (kind === 'disconnect') {
        await api('/settings/messaging/telegram', { method: 'DELETE' });
        setEditing(true);
        setUser('');
      } else {
        await post(`/settings/messaging/telegram/${kind}`, {});
      }
      setToken('');
      done();
      refresh();
      toast(
        {
          save: 'Telegram credentials saved and encrypted.',
          check: 'Bot identity checked successfully.',
          enable: 'Telegram is listening. Open your bot’s private chat to talk to Sibyl.',
          pause: 'Telegram paused. Your credentials and conversation are kept.',
          disconnect: 'Telegram disconnected. Local conversation history is kept.',
        }[kind],
      );
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy('');
    }
  };
  const cancelEdit = () => {
    setEditing(false);
    setToken('');
    setUser(String(channel.allowed_user_id ?? ''));
    setError('');
  };

  return (
    <section
      className={`messaging-card telegram-live-card telegram-mode-${mode}`}
      aria-labelledby="telegram-title"
    >
      <div className="messaging-card-heading">
        <span className="channel-icon channel-telegram">
          <img src="/messaging/telegram.svg" width="27" height="27" alt="" />
        </span>
        <div>
          <h3 id="telegram-title">Telegram</h3>
          <small>
            {channel.bot_username ? `@${channel.bot_username}` : 'Your private Sibyl bot'}
          </small>
        </div>
        <span className={`telegram-state-pill ${mode}`} role="status">
          <span className="telegram-status-dot" aria-hidden="true" />
          {stateLabel}
        </span>
      </div>

      <div className="telegram-runtime">
        <span className={`telegram-runtime-orb ${working ? 'working' : ''}`} aria-hidden="true">
          {enabled ? <Radio size={24} /> : <Pause size={23} />}
        </span>
        <div className="telegram-runtime-copy">
          <strong>
            {enabled
              ? channel.error
                ? 'Your connection needs attention'
                : working
                  ? 'Sibyl is working on your message'
                  : 'Listening for your messages'
              : channel.has_started
                ? 'Telegram is paused'
                : saved
                  ? 'Your bot is ready to connect'
                  : 'Connect your personal bot'}
          </strong>
          <p>
            {enabled
              ? channel.error
                ? 'Review the connection message below. Listening remains enabled.'
                : 'Your Python backend is running this connection. Only your private account is accepted.'
              : saved
                ? 'Start listening when you’re ready. Your saved credentials stay encrypted.'
                : 'Save your bot token and personal user ID below to unlock the controls.'}
          </p>
          {channel.last_poll_at && (
            <small>
              Last Telegram poll ·{' '}
              {new Date(channel.last_poll_at * 1000).toLocaleTimeString([], {
                hour: '2-digit',
                minute: '2-digit',
                second: '2-digit',
              })}
            </small>
          )}
        </div>
        <div className="telegram-runtime-controls">
          <button
            className={`button ${enabled ? 'secondary' : 'primary'}`}
            type="button"
            disabled={!!busy || !saved || (!enabled && editorOpen)}
            onClick={() => void action(enabled ? 'pause' : 'enable')}
          >
            {busy === 'enable' || busy === 'pause' ? (
              <LoaderCircle size={15} className="spin" />
            ) : enabled ? (
              <Pause size={15} />
            ) : (
              <Play size={15} />
            )}
            {busy === 'enable'
              ? 'Starting…'
              : busy === 'pause'
                ? 'Pausing…'
                : enabled
                  ? 'Pause Telegram'
                  : channel.has_started
                    ? 'Resume Telegram'
                    : 'Enable Telegram'}
          </button>
          {enabled && channel.bot_username && (
            <a
              className="text-link"
              href={`https://t.me/${encodeURIComponent(channel.bot_username)}`}
              target="_blank"
              rel="noreferrer"
            >
              Open bot <ArrowUpRight size={12} />
            </a>
          )}
        </div>
      </div>

      {saved && !editorOpen && (
        <div className="telegram-saved-connection">
          <span className="telegram-vault-icon">
            <ShieldCheck size={20} aria-hidden="true" />
          </span>
          <div>
            <strong>Credentials saved</strong>
            <small>
              Encrypted bot token · private user ••••{' '}
              {String(channel.allowed_user_id ?? '').slice(-4)}
            </small>
          </div>
          <span className={`telegram-check-state ${channel.connected ? 'verified' : ''}`}>
            {channel.connected ? <Check size={13} /> : <Clock3 size={13} />}
            {channel.connected ? 'Bot checked' : 'Not checked yet'}
          </span>
          <div className="telegram-connection-actions">
            <button
              className="button secondary"
              type="button"
              disabled={!!busy}
              onClick={() => void action('check')}
            >
              {busy === 'check' ? (
                <LoaderCircle size={14} className="spin" />
              ) : (
                <ShieldCheck size={14} />
              )}
              {busy === 'check' ? 'Checking…' : 'Check bot'}
            </button>
            <button
              className="text-button"
              type="button"
              disabled={!!busy}
              onClick={() => {
                setUser(String(channel.allowed_user_id ?? ''));
                setEditing(true);
              }}
            >
              <Pencil size={13} />
              Edit credentials
            </button>
          </div>
        </div>
      )}

      {editorOpen && (
        <form
          className="telegram-credentials-editor"
          aria-label="Telegram connection"
          onSubmit={(event) => {
            event.preventDefault();
            void action('save');
          }}
          noValidate
        >
          <div className="telegram-editor-heading">
            <span>
              <KeyRound size={16} />
              {saved ? 'Edit saved credentials' : 'Connect Telegram'}
            </span>
            {saved && (
              <button className="text-button" type="button" disabled={!!busy} onClick={cancelEdit}>
                <X size={14} />
                Close
              </button>
            )}
          </div>
          {enabled && (
            <p className="telegram-edit-notice">
              Pause Telegram above to change credentials. The saved token is never displayed.
            </p>
          )}
          <div className="messaging-fields">
            <label>
              Bot token
              <input
                type="password"
                autoComplete="off"
                aria-describedby="telegram-token-help"
                placeholder={
                  saved ? 'Encrypted token saved · leave blank to keep' : 'Token from @BotFather'
                }
                value={token}
                disabled={enabled || !!busy}
                onChange={(e) => setToken(e.target.value)}
              />
              <small id="telegram-token-help">
                {saved
                  ? 'Enter a replacement only when rotating the token. Leave blank to keep the saved token.'
                  : 'Paste the full token from BotFather, including the colon. The t.me link opens your bot’s chat.'}
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
                disabled={enabled || !!busy}
                onChange={(e) => setUser(e.target.value)}
              />
              <small id="telegram-user-help">
                {user.trim() && !validUser
                  ? 'Use your personal numeric ID, not a username, phone number or bot token.'
                  : 'Your personal account ID. The token’s number before the colon belongs to the bot.'}
              </small>
            </label>
          </div>
          <details className="telegram-id-help">
            <summary>Where do I find my personal user ID?</summary>
            <p>
              In Telegram, open{' '}
              <a href="https://t.me/userinfobot" target="_blank" rel="noreferrer">
                @userinfobot
              </a>{' '}
              (an optional third-party lookup), press Start and copy the numeric Id it reports. Do
              not send it your BotFather token.
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
          <div className="telegram-actions">
            <button className="button primary" type="submit" disabled={!!busy || enabled}>
              {busy === 'save' ? (
                <LoaderCircle size={14} className="spin" />
              ) : (
                <ShieldCheck size={14} />
              )}
              {busy === 'save' ? 'Saving…' : saved ? 'Save changes' : 'Save connection'}
            </button>
            {saved && (
              <button
                className="button secondary"
                type="button"
                disabled={!!busy}
                onClick={cancelEdit}
              >
                Cancel
              </button>
            )}
            {saved && (
              <button
                className="text-button negative telegram-disconnect"
                type="button"
                disabled={!!busy}
                onClick={() => void action('disconnect')}
              >
                <Unplug size={14} />
                Disconnect
              </button>
            )}
          </div>
        </form>
      )}
      {problem && (
        <p className="form-error" role="alert">
          {problem}
        </p>
      )}

      <dl className="telegram-activity" aria-label="Telegram activity">
        <div>
          <dt>
            <MessageCircle size={14} />
            Messages received
          </dt>
          <dd>{received.toLocaleString()}</dd>
          <small>Your accepted messages and commands</small>
        </div>
        <div>
          <dt>
            <Send size={14} />
            Replies delivered
          </dt>
          <dd>{health?.summary ? health.summary.replies_delivered.toLocaleString() : '—'}</dd>
          <small>
            {(delivery.sent ?? 0).toLocaleString()} message parts sent · long replies may split
          </small>
        </div>
        <div>
          <dt>
            <Clock3 size={14} />
            In progress
          </dt>
          <dd>{waiting.toLocaleString()}</dd>
          <small>
            {updates.processing
              ? 'Answering your message'
              : `${updates.queued ?? 0} messages queued · ${health?.summary?.replies_waiting ?? 0} replies waiting`}
          </small>
        </div>
      </dl>
      {(!!delivery.uncertain ||
        !!delivery.failed ||
        !!delivery.blocked ||
        !!updates.interrupted ||
        !!updates.failed) && (
        <div className="telegram-delivery-review" role="status">
          {!!delivery.uncertain && (
            <span>
              {delivery.uncertain} reply parts have uncertain delivery. Check your chat; these are
              not automatically resent.
            </span>
          )}
          {!!delivery.failed && <span>{delivery.failed} reply parts failed.</span>}
          {!!delivery.blocked && (
            <span>
              {delivery.blocked} reply parts are blocked after an earlier delivery problem.
            </span>
          )}
          {!!updates.interrupted && (
            <span>{updates.interrupted} requests were interrupted. Send them again if needed.</span>
          )}
          {!!updates.failed && <span>{updates.failed} requests could not be answered.</span>}
        </div>
      )}
      <div className="messaging-card-footer telegram-footer">
        <p>
          {saved
            ? 'Pause keeps your credentials and conversation. Disconnect removes the saved token. An in-flight reply may still finish.'
            : channel.setup_note}
        </p>
        <a className="text-link" href={channel.docs_url} target="_blank" rel="noreferrer">
          Setup guide <ArrowUpRight size={12} />
        </a>
      </div>
    </section>
  );
}

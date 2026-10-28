import { MessageCircle, ArrowUpRight, Mail, TriangleAlert } from 'lucide-react';
import { Link } from 'react-router-dom';
import { useResource } from '../lib/hooks';
import { Badge, ErrorState, Loading } from './ui';
import { TelegramSetup } from './telegram-settings';

export type MessagingChannel = {
  id: string;
  name: string;
  description: string;
  docs_url: string;
  setup_note: string;
  connected: boolean;
  status: 'unavailable' | 'available';
  enabled?: boolean;
  has_started?: boolean;
  last_checked_at?: number;
  last_poll_at?: number;
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
export type MessagingSettingsData = {
  channels: MessagingChannel[];
  telegram?: {
    updates: Record<string, number>;
    delivery: Record<string, number>;
    llm_ready: boolean;
    summary?: { messages_received: number; replies_delivered: number; replies_waiting: number };
  };
};

/** Show app icons and future setup fields; unavailable clients collect nothing. */
export function MessagingSettings() {
  const resource = useResource<MessagingSettingsData>('/settings/messaging', 5000);
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

function ChannelSetup({ channel }: { channel: MessagingChannel }) {
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

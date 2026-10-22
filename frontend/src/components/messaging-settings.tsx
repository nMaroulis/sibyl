import { MessageCircle, ArrowUpRight, Mail } from 'lucide-react';
import { Link } from 'react-router-dom';
import { useResource } from '../lib/hooks';
import { Badge, ErrorState, Loading } from './ui';

type Channel = {
  id: string;
  name: string;
  description: string;
  docs_url: string;
  setup_note: string;
  connected: false;
  status: 'unavailable';
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
type Settings = { channels: Channel[] };

/** Show app icons and future setup fields; unavailable clients collect nothing. */
export function MessagingSettings() {
  const resource = useResource<Settings>('/settings/messaging');
  return (
    <div className="messaging-settings">
      <div className="messaging-intro">
        <span className="messaging-intro-icon">
          <MessageCircle size={25} />
        </span>
        <div>
          <h2>Sibyl, wherever you are.</h2>
          <p>Once available, you’ll be able to talk to Sibyl through these apps or email.</p>
        </div>
      </div>
      <p className="messaging-unavailable-note" id="messaging-unavailable-note">
        <strong>Messaging integrations are currently unavailable.</strong> These are the setup
        fields you’ll need when they’re ready.
      </p>
      {resource.loading ? (
        <Loading />
      ) : resource.error ? (
        <ErrorState message={resource.error} retry={resource.retry} />
      ) : (
        <div className="messaging-grid">
          {resource.data?.channels.map((channel) => (
            <ChannelSetup key={channel.id} channel={channel} />
          ))}
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

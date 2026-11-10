import { useEffect, useState } from 'react';
import { CheckCircle2, Cloud, KeyRound, LoaderCircle } from 'lucide-react';
import { post, refresh } from '../lib/api';
import type { SemanticStatus } from '../lib/semantic-types';
import { SecretField } from './secret-field';

/** Explicit remote-text permission and an independent encrypted key, never a chat-provider fallback. */
export function LibraryHostedSetup({
  provider,
  current,
  busy,
  setBusy,
  saved,
}: {
  provider: 'openai' | 'mistral';
  current: SemanticStatus;
  busy: string;
  setBusy: (value: string) => void;
  saved: () => void;
}) {
  const spec = current.hosted?.items.find((row) => row.id === provider);
  const active = current.profile.provider === provider;
  const [model, setModel] = useState('');
  const [key, setKey] = useState('');
  const [edit, setEdit] = useState(false);
  const [consent, setConsent] = useState(false);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  useEffect(() => {
    setModel(active ? current.profile.model || spec?.models[0] || '' : spec?.models[0] || '');
    setKey('');
    setEdit(!active || !current.has_api_key);
    setConsent(active && current.profile.remote_consent === true);
    setError('');
    setMessage('');
  }, [provider, current.revision]);
  const save = async () => {
    if (busy) return;
    setBusy('hosted-save');
    setError('');
    setMessage('');
    try {
      await post('/library/semantic/hosted-settings', {
        provider,
        model,
        revision: current.revision,
        remote_consent: consent,
        ...(edit ? { api_key: key.trim() } : {}),
      });
      setKey('');
      setEdit(false);
      setMessage('Hosted model checked and saved. Choose which sources to index below.');
      saved();
      refresh();
    } catch (reason) {
      setError((reason as Error).message);
    } finally {
      setBusy('');
    }
  };
  return (
    <div className="library-hosted-setup">
      <div className="library-semantic-fields">
        <label>
          Embedding model
          <select
            aria-label="Hosted embedding model"
            value={model}
            disabled={!!busy}
            onChange={(event) => setModel(event.target.value)}
          >
            {spec?.models.map((name) => (
              <option key={name} value={name}>
                {name}
              </option>
            ))}
          </select>
        </label>
        {edit ? (
          <SecretField
            label={`${spec?.label || provider} embedding API key`}
            value={key}
            onChange={setKey}
            disabled={!!busy}
          />
        ) : (
          <div className="embedding-key-saved">
            <KeyRound size={17} />
            <div>
              <strong>API key saved</strong>
              <small>Encrypted locally · separate from chat models</small>
            </div>
            <button
              type="button"
              className="text-button"
              disabled={!!busy}
              onClick={() => {
                setKey('');
                setEdit(true);
              }}
            >
              Edit key
            </button>
          </div>
        )}
      </div>
      <div className="embedding-remote-consent">
        <Cloud size={18} aria-hidden="true" />
        <div>
          <strong>Hosted processing · {spec?.label || provider}</strong>
          <p>
            Checking sends a fixed compatibility phrase. Indexing sends selected library passages;
            semantic/hybrid searches and retrieval evaluations send their query text, including
            agent searches. Provider charges and data policies apply. Disabling cannot recall text
            already sent.
          </p>
          {active && current.profile.remote_consent ? (
            <p className="embedding-consent-active">
              <CheckCircle2 size={14} aria-hidden="true" /> Permission enabled. Use Disable semantic
              search below to revoke it.
            </p>
          ) : (
            <label>
              <input
                type="checkbox"
                checked={consent}
                disabled={!!busy}
                onChange={(event) => setConsent(event.target.checked)}
              />
              <span>I allow this text to be sent to {spec?.label || provider}.</span>
            </label>
          )}
        </div>
      </div>
      {!spec?.available && (
        <p className="footnote">
          The optional OpenAI-compatible SDK is required for both hosted providers. Install it in
          the backend environment: <code>{current.hosted?.install}</code>, then restart Sibyl.
        </p>
      )}
      <div className="library-semantic-actions">
        <button
          type="button"
          className="button secondary"
          disabled={!!busy || !spec?.available || !model || !consent || (edit && !key.trim())}
          onClick={() => void save()}
        >
          {busy === 'hosted-save' ? (
            <LoaderCircle className="spin" size={14} />
          ) : (
            <Cloud size={14} />
          )}{' '}
          Check &amp; save hosted model
        </button>
        {edit && active && current.has_api_key && (
          <button
            type="button"
            className="text-button"
            disabled={!!busy}
            onClick={() => {
              setEdit(false);
              setKey('');
            }}
          >
            Keep saved key
          </button>
        )}
      </div>
      <p className="footnote">
        Saving clears the semantic index. Original documents and keyword search stay available.
      </p>
      {error && (
        <p className="form-error" role="alert">
          {error}
        </p>
      )}
      {message && (
        <p className="footnote" role="status">
          {message}
        </p>
      )}
    </div>
  );
}

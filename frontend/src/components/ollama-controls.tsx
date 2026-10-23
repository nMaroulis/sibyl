import { useCallback, useEffect, useState } from 'react';
import { ArrowUpRight, Play, RefreshCw, Square } from 'lucide-react';
import { post } from '../lib/api';
import { Badge } from './ui';

type Status = {
  installed: boolean;
  local: boolean;
  status: string;
  version: string | null;
  models: { name: string; parameter_size?: string }[];
  loaded_models: string[];
  selected_model_installed: boolean;
  managed: boolean;
  can_start: boolean;
  can_stop: boolean;
  error: string | null;
  pull_command: string | null;
  note: string;
  install_url: string;
  setup_url: string;
};

/** Check the actual selected server; starting is always an explicit local-only action. */
export function OllamaControls({
  endpoint,
  model,
  onModel,
}: {
  endpoint: string;
  model: string;
  onModel: (model: string) => void;
}) {
  const [status, setStatus] = useState<Status>();
  const [busy, setBusy] = useState('');
  const [error, setError] = useState('');
  const check = useCallback(async () => {
    try {
      setStatus(await post<Status>('/settings/ollama/check', { base_url: endpoint, model }));
      setError('');
    } catch (e) {
      setError((e as Error).message);
    }
  }, [endpoint, model]);
  useEffect(() => {
    setStatus(undefined);
    const id = setTimeout(() => {
      void check();
    }, 400);
    return () => clearTimeout(id);
  }, [check]);
  useEffect(() => {
    if (!status?.managed || status.status !== 'starting') return;
    const id = setInterval(() => {
      void check();
    }, 2000);
    return () => clearInterval(id);
  }, [status?.managed, status?.status, check]);
  const action = async (kind: string) => {
    setBusy(kind);
    setError('');
    try {
      setStatus(await post<Status>(`/settings/ollama/${kind}`, { base_url: endpoint, model }));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy('');
    }
  };
  return (
    <section className="ollama-controls" aria-label="Ollama server status">
      <div className="ollama-status-heading">
        <div>
          <strong>Your Ollama server</strong>
          <small>
            {status?.version ? `Version ${status.version}` : 'On the Python backend machine'}
          </small>
        </div>
        <Badge tone={status?.status === 'running' ? 'lime' : 'neutral'}>
          {status?.status.replaceAll('_', ' ') ?? 'Checking…'}
        </Badge>
      </div>
      {status && (
        <p>
          {status.installed
            ? 'Ollama CLI detected locally.'
            : 'Ollama CLI was not found on the backend machine.'}{' '}
          {status.managed
            ? 'This server was started by Sibyl.'
            : status.status === 'running'
              ? 'Using your existing server.'
              : ''}
        </p>
      )}
      <div className="ollama-actions">
        <button
          type="button"
          className="button secondary tiny"
          disabled={!!busy}
          onClick={() => action('check')}
        >
          <RefreshCw size={13} className={busy === 'check' ? 'spin' : ''} />
          Check status
        </button>
        {status?.can_start && (
          <button
            type="button"
            className="button primary tiny"
            disabled={!!busy}
            onClick={() => action('start')}
          >
            <Play size={13} />
            {busy === 'start' ? 'Starting…' : 'Start Ollama'}
          </button>
        )}
        {status?.can_stop && (
          <button
            type="button"
            className="button secondary tiny"
            disabled={!!busy}
            onClick={() => action('stop')}
          >
            <Square size={12} />
            Stop local server
          </button>
        )}
      </div>
      {status?.status === 'running' && (
        <>
          <label>
            Models installed on this server
            <select
              value={status.models.some((m) => m.name === model) ? model : ''}
              onChange={(e) => e.target.value && onModel(e.target.value)}
            >
              <option value="">Choose an installed model</option>
              {status.models.map((m) => (
                <option value={m.name} key={m.name}>
                  {m.name}
                  {m.parameter_size ? ` · ${m.parameter_size}` : ''}
                </option>
              ))}
            </select>
          </label>
          <p className="footnote">
            {status.selected_model_installed
              ? 'Selected model is installed. Connection checks do not test inference or tool-calling quality.'
              : 'Selected model is not installed on this server.'}{' '}
            {status.loaded_models.length
              ? `Loaded in memory: ${status.loaded_models.join(', ')}.`
              : 'No model is currently loaded; Ollama loads it when needed.'}
          </p>
        </>
      )}
      {(error || (status?.error && status.status !== 'starting')) && (
        <p className="form-error" role="status">
          {error || status?.error}
        </p>
      )}
      <details>
        <summary>Install Ollama or add a model</summary>
        <p>
          Install Ollama on the computer running Sibyl’s Python backend, open it, then check again.
          For a remote server, install and start it there.
        </p>
        <p>
          <a
            className="text-link"
            href="https://ollama.com/download"
            target="_blank"
            rel="noreferrer"
          >
            Download Ollama <ArrowUpRight size={12} />
          </a>{' '}
          ·{' '}
          <a
            className="text-link"
            href="https://docs.ollama.com/quickstart"
            target="_blank"
            rel="noreferrer"
          >
            Setup instructions <ArrowUpRight size={12} />
          </a>
        </p>
        {status?.pull_command && (
          <p>
            Download the selected model yourself in a terminal:
            <br />
            <code>{status.pull_command}</code>
          </p>
        )}
        <p className="footnote">
          Sibyl starts only an installed server on a local loopback address. Model downloads and
          installation are separate. Existing Ollama processes are never stopped here.
        </p>
      </details>
    </section>
  );
}

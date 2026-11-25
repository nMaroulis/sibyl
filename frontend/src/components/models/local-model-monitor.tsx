import { useEffect, useState } from 'react';
import { Activity, ArrowUpRight, Play, RefreshCw, Square } from 'lucide-react';
import { api, post } from '../../lib/api';
import { MonitorTrace } from '../monitor-trace';
import '../../styles/model-settings.css';

const catalogProviders = ['ollama', 'lmstudio', 'vllm', 'llama.cpp-server'];

export function supportsModelMonitor(provider: string) {
  return catalogProviders.includes(provider);
}

type Phase =
  'running' | 'starting' | 'unreachable' | 'not_installed' | 'unauthorized' | 'catalog_unavailable';
type RuntimeStatus = {
  status: Phase;
  version?: string | null;
  models: { name: string; parameter_size?: string }[];
  loaded_models?: string[];
  loaded_models_checked?: boolean;
  managed?: boolean;
  can_start?: boolean;
  can_stop?: boolean;
  error?: string | null;
  pull_command?: string | null;
};
type Observation = { at: number; elapsed: number; phase: Phase };
const phases: Record<Phase, string> = {
  running: 'Reachable',
  starting: 'Starting',
  unreachable: 'Unreachable',
  not_installed: 'Ollama not found',
  unauthorized: 'Check credentials',
  catalog_unavailable: 'Catalog unavailable',
};

const HISTORY_LENGTH = 24;

export function sameModel(first: string, second: string, ollama: boolean) {
  if (!ollama) return first === second;
  const canonical = (model: string) =>
    model.split('/').at(-1)?.includes(':') ? model : `${model}:latest`;
  return canonical(first) === canonical(second);
}

/** Check model availability in the active Settings tab without asking the model to generate. */
export function LocalModelMonitor({
  deployment,
  provider,
  name,
  model,
  visible,
  onCatalog,
}: {
  deployment: string;
  provider: string;
  name: string;
  model: string;
  visible: boolean;
  onCatalog: (models: string[] | null) => void;
}) {
  const ollama = provider === 'ollama';
  const runtime = `/settings/llm/deployments/${deployment}/runtime`;
  const [status, setStatus] = useState<RuntimeStatus>();
  const [checks, setChecks] = useState<Observation[]>([]);
  const [busy, setBusy] = useState<'start' | 'stop'>();
  const [checking, setChecking] = useState(false);
  const [request, setRequest] = useState(0);
  const [error, setError] = useState('');
  useEffect(() => {
    if (!visible || busy) return;
    const controller = new AbortController();
    let timer: number | undefined;
    async function check() {
      const start = performance.now();
      let phase: Phase | undefined;
      try {
        const result = await api<RuntimeStatus>(runtime, { signal: controller.signal });
        if (controller.signal.aborted) return;
        setStatus(result);
        onCatalog(result.status === 'running' ? result.models.map((entry) => entry.name) : null);
        setError('');
        phase = result.status;
      } catch (reason) {
        if (controller.signal.aborted) return;
        setStatus(undefined);
        onCatalog(null);
        setError((reason as Error).message);
      } finally {
        if (!controller.signal.aborted) {
          setChecking(false);
          if (phase) {
            const sample = {
              at: Date.now(),
              elapsed: Math.round(performance.now() - start),
              phase,
            };
            setChecks((items) => [...items.slice(-(HISTORY_LENGTH - 1)), sample]);
          }
          timer = window.setTimeout(() => void check(), phase === 'starting' ? 2000 : 6000);
        }
      }
    }
    timer = window.setTimeout(() => void check(), 0);
    return () => {
      controller.abort();
      window.clearTimeout(timer);
    };
  }, [busy, model, onCatalog, request, runtime, visible]);

  async function action(kind: 'start' | 'stop') {
    setBusy(kind);
    setError('');
    try {
      setStatus(await post<RuntimeStatus>(`${runtime}/${kind}`, {}));
    } catch (reason) {
      setError((reason as Error).message);
    } finally {
      setBusy(undefined);
    }
  }

  const running = status?.status === 'running';
  const latest = checks.at(-1);
  const loaded = status?.loaded_models ?? [];
  const loadedKnown = status?.loaded_models_checked ?? !!status?.loaded_models;
  const names = status?.models.map((item) => item.name) ?? [];
  const missing = !!model && !names.some((name) => sameModel(model, name, ollama));
  const bins = [
    ...Array.from({ length: HISTORY_LENGTH - checks.length }, () => ({ count: 0 })),
    ...checks.map((sample) => ({
      count: sample.phase === 'running' ? 2 : 1,
      attention: sample.phase !== 'running' && sample.phase !== 'starting',
    })),
  ];

  return (
    <section
      className="channel-activity-panel model-runtime-monitor"
      aria-label={`${name} server status`}
    >
      <div className="channel-activity-header">
        <div className="channel-activity-title">
          <span className="channel-activity-header-icon" aria-hidden="true">
            <Activity size={16} />
          </span>
          <div>
            <h4>Runtime monitor</h4>
            <p>
              {status?.version
                ? `Version ${status.version}`
                : ollama
                  ? status?.managed
                    ? 'Sibyl-managed server'
                    : 'Ollama server'
                  : 'Model catalog'}
              {latest && (
                <>
                  {' '}
                  · Checked{' '}
                  {new Date(latest.at).toLocaleTimeString([], {
                    hour: '2-digit',
                    minute: '2-digit',
                    second: '2-digit',
                  })}
                </>
              )}
            </p>
          </div>
        </div>
        <span
          className="channel-activity-state"
          data-live={running}
          data-attention={!!error || (!!status && !running && status.status !== 'starting')}
          role="status"
        >
          <i aria-hidden="true" />
          {status ? phases[status.status] : error ? 'Check failed' : 'Checking…'}
        </span>
      </div>
      <div className="channel-activity-controls">
        {status?.can_start && (
          <button
            type="button"
            className="button primary tiny"
            disabled={!!busy}
            onClick={() => void action('start')}
          >
            <Play size={13} /> {busy === 'start' ? 'Starting…' : 'Start Ollama'}
          </button>
        )}
        {status?.can_stop && (
          <button
            type="button"
            className="button secondary tiny"
            disabled={!!busy}
            onClick={() => void action('stop')}
          >
            <Square size={12} /> {busy === 'stop' ? 'Stopping…' : 'Stop local server'}
          </button>
        )}
        <button
          type="button"
          className="button secondary tiny"
          disabled={!!busy || checking}
          onClick={() => {
            setChecking(true);
            setRequest((value) => value + 1);
          }}
        >
          <RefreshCw size={13} className={checking ? 'spin' : undefined} />
          Check status
        </button>
      </div>

      <dl className="channel-activity-counts" aria-label="Runtime checks">
        <div>
          <dt>{ollama ? 'Installed' : 'In catalog'}</dt>
          <dd>{running ? names.length : '—'}</dd>
        </div>
        {ollama && (
          <div>
            <dt>Loaded</dt>
            <dd>{running && loadedKnown ? loaded.length : '—'}</dd>
          </div>
        )}
        <div>
          <dt>Latest check</dt>
          <dd>{latest ? `${latest.elapsed} ms` : '—'}</dd>
        </div>
      </dl>
      <MonitorTrace bins={bins} live={running} />
      <div className="channel-activity-trace-range">
        <span>Recent checks</span>
        <span>This visit</span>
      </div>

      {running && (
        <div className="model-runtime-catalog">
          {missing && <p className="form-error">This model is absent from the catalog · {model}</p>}
          {ollama && loadedKnown && (
            <p>
              {loaded.length
                ? `Loaded · ${loaded.join(', ')}`
                : 'No models are loaded. Ollama loads them on demand.'}
            </p>
          )}
          {ollama && !loadedKnown && <p>Loaded-model status is unavailable.</p>}
          {names.length > 0 && (
            <details>
              <summary>{ollama ? 'Installed models' : 'Reported models'}</summary>
              <ul>
                {names.map((name) => (
                  <li key={name}>{name}</li>
                ))}
              </ul>
            </details>
          )}
        </div>
      )}
      {(error || (status?.error && status.status !== 'starting')) && (
        <p className="form-error" role="status">
          {error || status?.error}
        </p>
      )}
      {ollama && status?.status === 'not_installed' && (
        <details className="model-runtime-install">
          <summary>Install Ollama or add a model</summary>
          <p>Install and open Ollama on the machine hosting your model server.</p>
          <p>
            <a
              className="text-link"
              href="https://ollama.com/download"
              target="_blank"
              rel="noreferrer"
            >
              Download Ollama <ArrowUpRight size={12} />
            </a>
            {' · '}
            <a
              className="text-link"
              href="https://docs.ollama.com/quickstart"
              target="_blank"
              rel="noreferrer"
            >
              Setup guide <ArrowUpRight size={12} />
            </a>
          </p>
          {status?.pull_command && <code>{status.pull_command}</code>}
        </details>
      )}
    </section>
  );
}

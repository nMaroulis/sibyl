import { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { Cpu, LoaderCircle, RefreshCw, Play, Square } from 'lucide-react';
import { api, post, refresh } from '../lib/api';
import type { SemanticCoverage, SemanticStatus } from '../lib/semantic-types';
import { Badge, ErrorState, Panel } from './ui';
import { ProviderMark } from './provider-mark';
import { LibraryHostedSetup } from './library-hosted-setup';
import './library-semantic.css';

const presets = ['embeddinggemma:latest', 'nomic-embed-text:latest', 'mxbai-embed-large:latest'];

/** Local or explicitly consented hosted embedding setup and explicit bounded indexing; leaving the page stops future batches. */
export function LibrarySemantic({
  state,
  retry,
}: {
  state: { data?: SemanticStatus; error: string; loading: boolean };
  retry: () => void;
}) {
  const [provider, setProvider] = useState<'ollama' | 'openai' | 'mistral'>('ollama');
  const [endpoint, setEndpoint] = useState('http://127.0.0.1:11434');
  const [model, setModel] = useState(presets[0]);
  const [custom, setCustom] = useState(false);
  const [models, setModels] = useState<{ name: string; remote: boolean }[]>([]);
  const [scope, setScope] = useState<'document' | 'news' | 'all'>('document');
  const [busy, setBusy] = useState('');
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const [progress, setProgress] = useState<SemanticCoverage>();
  const [stopping, setStopping] = useState(false);
  const stop = useRef(false),
    alive = useRef(true);
  useEffect(() => {
    alive.current = true;
    return () => {
      alive.current = false;
      stop.current = true;
    };
  }, []);
  useEffect(() => {
    const profile = state.data?.profile;
    setProvider(profile?.provider || 'ollama');
    const local = !profile?.provider;
    setEndpoint(local ? profile?.endpoint || 'http://127.0.0.1:11434' : 'http://127.0.0.1:11434');
    setModel(local ? profile?.model || presets[0] : presets[0]);
    setCustom(local && !!profile?.model && !presets.includes(profile.model));
    setProgress(undefined);
  }, [state.data?.revision]);
  const current = state.data;
  const coverage = (busy === 'index' ? progress : undefined) ?? current?.coverage[scope];
  const actions = async (kind: 'models' | 'save' | 'clear' | 'disable') => {
    if (!current || busy) return;
    setBusy(kind);
    setError('');
    setMessage('');
    try {
      if (kind === 'models') {
        const result = await post<{ items: typeof models }>('/library/semantic/models', {
          endpoint: endpoint.trim(),
        });
        if (!alive.current) return;
        setModels(result.items);
        setMessage(
          `${result.items.length} model names reported. Saving checks embedding capability and local execution.`,
        );
      } else if (kind === 'save') {
        await post('/library/semantic/settings', {
          endpoint: endpoint.trim(),
          model: model.trim(),
          revision: current.revision,
        });
        if (alive.current)
          setMessage(
            'Local embedding model checked and saved. Index passages to enable semantic search.',
          );
      } else if (kind === 'clear') {
        await post('/library/semantic/clear', { revision: current.revision });
        if (alive.current)
          setMessage('Semantic vectors cleared. Sources and keyword search are retained.');
      } else {
        await api(`/library/semantic?revision=${current.revision}`, { method: 'DELETE' });
        if (alive.current)
          setMessage('Semantic search disabled. Sources and keyword search are retained.');
      }
      if (alive.current) {
        retry();
        if (kind !== 'models') refresh();
      }
    } catch (reason) {
      if (alive.current) {
        setError((reason as Error).message);
        retry();
      }
    } finally {
      if (alive.current) setBusy('');
    }
  };
  const build = async () => {
    if (!current?.configured || busy) return;
    setBusy('index');
    setError('');
    setMessage('');
    setStopping(false);
    stop.current = false;
    const revision = current.revision,
      kind = scope;
    let finished = false;
    try {
      // Explicit run budget, with a durable checkpoint after each successful HTTP batch.
      for (let batch = 0; batch < 160 && !stop.current; batch++) {
        const result = await post<{
          added: number;
          skipped_changed: number;
          status: SemanticStatus;
        }>('/library/semantic/index', { revision, kind, limit: 32 });
        if (!alive.current) return;
        const next = result.status.coverage[kind];
        setProgress(next);
        if (next.missing === 0) {
          finished = true;
          break;
        }
        if (!result.added)
          throw Error(
            'Sources changed during indexing. Review the current coverage and continue when ready.',
          );
      }
      if (alive.current)
        setMessage(
          finished
            ? 'This scope is indexed. Select Semantic or Hybrid in the search controls.'
            : stop.current
              ? 'Stopped after the current batch. Completed vectors are retained; continue when ready.'
              : 'Run budget reached. Completed vectors are retained; continue indexing when ready.',
        );
    } catch (reason) {
      if (alive.current) setError((reason as Error).message);
    } finally {
      if (alive.current) {
        setBusy('');
        setStopping(false);
        retry();
        refresh();
      }
    }
  };
  const choices = [
    ...new Set([...presets, ...models.filter((row) => !row.remote).map((row) => row.name)]),
  ];
  return (
    <Panel className="library-semantic">
      <details>
        <summary>
          <Cpu size={17} aria-hidden="true" />
          <div>
            <strong>Semantic search</strong>
            <span>
              {current?.configured
                ? `${current.coverage.all.indexed} / ${current.coverage.all.total} passages indexed · ${current.profile.model}`
                : 'Local or hosted embeddings · keyword search works now'}
            </span>
          </div>
          <Badge>
            {current?.profile.provider ? 'Hosted' : current?.configured ? 'Local' : 'Optional'}
          </Badge>
        </summary>
        <div className="library-semantic-body">
          <p>
            Find passages with related wording, or combine meaning and keywords. Choose local Ollama
            or a hosted embedding provider. Embedding models and keys are independent of chat
            models; keyword search needs neither.
          </p>
          {state.error ? (
            <ErrorState message={state.error} retry={retry} />
          ) : state.loading ? (
            <p role="status">Reading index configuration…</p>
          ) : (
            <>
              <div
                className="embedding-provider-cards"
                role="group"
                aria-label="Embedding provider"
              >
                {(['ollama', 'openai', 'mistral'] as const).map((name) => (
                  <button
                    key={name}
                    type="button"
                    className={`embedding-provider-card ${provider === name ? 'selected' : ''}`}
                    aria-pressed={provider === name}
                    disabled={!!busy}
                    onClick={() => {
                      setProvider(name);
                      setError('');
                      setMessage('');
                    }}
                  >
                    <ProviderMark provider={name} size={25} />
                    <span>
                      <strong>
                        {name === 'ollama' ? 'Ollama' : name === 'openai' ? 'OpenAI' : 'Mistral'}
                      </strong>
                      <small>
                        {name === 'ollama'
                          ? 'Local · installed models'
                          : 'Hosted · text leaves this machine'}
                      </small>
                    </span>
                  </button>
                ))}
              </div>
              {provider === 'ollama' ? (
                <>
                  <div className="library-semantic-fields">
                    <label>
                      Local Ollama endpoint
                      <input
                        value={endpoint}
                        disabled={!!busy}
                        maxLength={200}
                        onChange={(event) => setEndpoint(event.target.value)}
                      />
                    </label>
                    <label>
                      Embedding model
                      <select
                        value={custom ? '__custom' : model}
                        disabled={!!busy}
                        onChange={(event) => {
                          setCustom(event.target.value === '__custom');
                          if (event.target.value !== '__custom') setModel(event.target.value);
                        }}
                      >
                        {choices.map((name) => (
                          <option key={name} value={name}>
                            {name}
                            {models.some((row) => row.name === name && !row.remote)
                              ? ' · installed'
                              : ''}
                          </option>
                        ))}
                        <option value="__custom">Custom installed model…</option>
                      </select>
                    </label>
                    {custom && (
                      <label>
                        Custom embedding model
                        <input
                          value={model}
                          disabled={!!busy}
                          maxLength={180}
                          onChange={(event) => setModel(event.target.value)}
                        />
                      </label>
                    )}
                  </div>
                  <div className="library-semantic-actions">
                    <button
                      className="button secondary"
                      disabled={!!busy || !model.trim()}
                      onClick={() => void actions('save')}
                    >
                      {busy === 'save' ? (
                        <LoaderCircle size={14} className="spin" />
                      ) : (
                        <Cpu size={14} />
                      )}{' '}
                      Check & save model
                    </button>
                    <button
                      className="text-button"
                      disabled={!!busy}
                      onClick={() => void actions('models')}
                    >
                      <RefreshCw size={12} /> Check installed models
                    </button>
                    <Link className="text-link" to="/settings?tab=models">
                      Ollama setup
                    </Link>
                  </div>
                  <p className="footnote">
                    Install an embedding model yourself, for example{' '}
                    <code>ollama pull embeddinggemma</code>. This screen does not download models.
                    Loopback HTTP endpoints and models advertised as local only. Saving a model
                    resets semantic vectors; sources and keyword search stay available.
                  </p>
                </>
              ) : (
                current && (
                  <LibraryHostedSetup
                    provider={provider}
                    current={current}
                    busy={busy}
                    setBusy={setBusy}
                    saved={retry}
                  />
                )
              )}
              {current?.configured && provider !== (current.profile.provider || 'ollama') && (
                <p className="footnote">
                  Save this provider before indexing. Your active index still uses{' '}
                  {current.profile.model}.
                </p>
              )}
              {current?.configured && provider === (current.profile.provider || 'ollama') && (
                <div className="library-semantic-index">
                  <div className="library-semantic-index-heading">
                    <strong>Passage index</strong>
                    <span>
                      {current.profile.model} · {current.profile.dimensions} dimensions
                      {current.profile.model_digest
                        ? ` · digest ${current.profile.model_digest.slice(0, 10)}…`
                        : ' · hosted model alias'}
                    </span>
                  </div>
                  <label>
                    Index sources
                    <select
                      disabled={!!busy}
                      value={scope}
                      onChange={(event) => {
                        setScope(event.target.value as typeof scope);
                        setProgress(undefined);
                      }}
                    >
                      <option value="document">My documents</option>
                      <option value="news">Retained news excerpts</option>
                      <option value="all">All retained sources</option>
                    </select>
                  </label>
                  <div className="library-semantic-progress" role="status">
                    <span>
                      {coverage?.indexed ?? 0} / {coverage?.total ?? 0} passages indexed
                    </span>
                    <small>{coverage?.missing ?? 0} remaining</small>
                  </div>
                  <div className="library-semantic-track" aria-hidden="true">
                    <span
                      style={{
                        width: coverage?.total
                          ? `${(coverage.indexed / coverage.total) * 100}%`
                          : '0%',
                      }}
                    />
                  </div>
                  <div className="library-semantic-actions">
                    <button
                      className="button secondary"
                      disabled={!!busy || !coverage?.missing}
                      onClick={() => void build()}
                    >
                      {busy === 'index' ? (
                        <LoaderCircle className="spin" size={14} />
                      ) : (
                        <Play size={14} />
                      )}{' '}
                      {busy === 'index'
                        ? 'Indexing passages…'
                        : coverage?.indexed
                          ? 'Continue indexing'
                          : 'Index passages'}
                    </button>
                    {busy === 'index' && (
                      <button
                        className="text-button"
                        disabled={stopping}
                        onClick={() => {
                          stop.current = true;
                          setStopping(true);
                        }}
                      >
                        <Square size={12} />
                        {stopping ? 'Stopping after this batch…' : 'Stop after this batch'}
                      </button>
                    )}
                    <button
                      className="text-button"
                      disabled={!!busy || !current.coverage.all.indexed}
                      onClick={() => void actions('clear')}
                    >
                      Clear index
                    </button>
                    <button
                      className="text-button"
                      disabled={!!busy}
                      onClick={() => void actions('disable')}
                    >
                      Disable semantic search
                    </button>
                  </div>
                  <p className="footnote">
                    Up to 32 passages per atomic batch; 5,000 vectors / 64 MiB total. Leaving the
                    page stops future batches. Deleted or reindexed sources lose their vectors.{' '}
                    {current.profile.provider
                      ? 'Hosted model updates may require clearing and rebuilding this index.'
                      : 'Text goes only to the local Ollama endpoint. Model or server-version changes require checking and rebuilding the index.'}
                  </p>
                </div>
              )}
            </>
          )}
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
      </details>
    </Panel>
  );
}

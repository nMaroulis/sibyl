import { useEffect, useState } from 'react';
import {
  ArrowUpRight,
  Check,
  Cloud,
  KeyRound,
  Laptop,
  LoaderCircle,
  ShieldCheck,
  Trash2,
} from 'lucide-react';
import { api, post, refresh } from '../lib/api';
import { useResource } from '../lib/hooks';
import type { ModelProvider, ModelWorkspace } from '../lib/types';
import { Badge, ErrorState, Loading, Modal, Panel, PanelTitle, useToast } from './ui';
import { OllamaControls } from './ollama-controls';
import { ProviderMark } from './provider-mark';
import { AgentModelSettings } from './agent-model-settings';

type Draft = { model: string; custom: boolean; base_url: string; key: string };

/** Configure the real ProtoLink runtime; provider secrets stay in the server vault. */
export function ModelSettings() {
  const resource = useResource<ModelWorkspace>('/settings/llm');
  if (resource.loading && !resource.data) return <Loading />;
  if (resource.error || !resource.data)
    return (
      <ErrorState
        message={resource.error || 'Model settings unavailable.'}
        retry={resource.retry}
      />
    );
  return <ModelEditor data={resource.data} />;
}

function ModelEditor({ data }: { data: ModelWorkspace }) {
  const [workspace, setWorkspace] = useState(data);
  const initialProvider = data.providers.find((provider) => provider.id === data.active_provider)!;
  const [choices, setChoices] = useState({
    api: initialProvider.kind === 'api' ? initialProvider.id : 'openai',
    local: initialProvider.kind === 'local' ? initialProvider.id : 'ollama',
  });
  const [kind, setKind] = useState<'api' | 'local'>(
    initialProvider.kind === 'local' ? 'local' : 'api',
  );
  const selected = choices[kind];
  const [drafts, setDrafts] = useState<Record<string, Draft>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [remove, setRemove] = useState(false);
  const toast = useToast();
  useEffect(() => {
    setWorkspace(data);
  }, [data]);
  const provider = workspace.providers.find((p) => p.id === selected)!;
  const profile = workspace.profiles[selected];
  const fallbackModel = profile.model || provider.models[0] || '';
  const draft = drafts[selected] ?? {
    model: fallbackModel,
    custom: !provider.models.includes(fallbackModel),
    base_url: profile.base_url || provider.base_url,
    key: '',
  };
  const active = workspace.providers.find((p) => p.id === workspace.active_provider)!;
  const update = (patch: Partial<Draft>) =>
    setDrafts((old) => ({ ...old, [selected]: { ...draft, ...patch } }));
  const select = (next: ModelProvider) => {
    setChoices((old) => ({ ...old, [next.kind]: next.id }));
    setError('');
  };
  const switchKind = (value: 'api' | 'local') => {
    setKind(value);
    const next = workspace.providers.find((provider) => provider.id === choices[value])!;
    select(next);
  };
  const saved = (result: ModelWorkspace, message: string) => {
    setWorkspace(result);
    setDrafts((old) =>
      Object.fromEntries(Object.entries(old).map(([id, value]) => [id, { ...value, key: '' }])),
    );
    refresh();
    toast(message);
  };
  const save = async (activate = true) => {
    setBusy(true);
    setError('');
    try {
      const result = await post<ModelWorkspace>('/settings/llm', {
        provider: selected,
        activate,
        model: draft.model.trim(),
        base_url: provider.base_url ? draft.base_url.trim() : '',
        ...(draft.key.trim() ? { api_key: draft.key.trim() } : {}),
      });
      saved(
        result,
        activate
          ? `Workspace default saved. Agents without overrides will use ${provider.name}.`
          : `${provider.name} profile saved. Workspace default unchanged.`,
      );
    } catch (reason) {
      setError((reason as Error).message);
    } finally {
      setBusy(false);
    }
  };
  const toolMode = async () => {
    setBusy(true);
    setError('');
    try {
      saved(
        await post<ModelWorkspace>('/settings/llm', { provider: 'none' }),
        'Workspace default set to tool mode. Agent overrides and provider profiles are kept.',
      );
    } catch (reason) {
      setError((reason as Error).message);
    } finally {
      setBusy(false);
    }
  };
  const removeKey = async () => {
    setBusy(true);
    setError('');
    try {
      const result = await api<ModelWorkspace>(`/settings/llm/${selected}/key`, {
        method: 'DELETE',
      });
      saved(
        result,
        result.active_provider === 'none' && workspace.active_provider === selected
          ? 'Saved key removed. The workspace default returned to tool mode; affected overrides need setup.'
          : 'Saved key removed.',
      );
      setRemove(false);
    } catch (reason) {
      setError((reason as Error).message);
    } finally {
      setBusy(false);
    }
  };
  return (
    <>
      <Panel className="llm-current">
        <span className={`provider-mark provider-${active.id}`}>
          <ProviderMark provider={active.id} />
        </span>
        <div>
          <small>Workspace default</small>
          <strong>
            {active.name}
            {workspace.active_model && <span> / {workspace.active_model}</span>}
          </strong>
          <p>
            {active.id === 'none'
              ? workspace.agents.some((agent) => !agent.inherited)
                ? 'Agents following this default use factual tool snapshots. Custom model assignments stay active.'
                : 'Your module tools are ready. Add a model for conversational reasoning.'
              : 'Used by agents without a custom model assignment.'}
          </p>
        </div>
        <Badge tone="lime">
          {active.id === 'none'
            ? 'Tools ready'
            : active.id === 'mock'
              ? 'Simulated model'
              : 'Selected'}
        </Badge>
        {active.id !== 'none' && (
          <button className="text-button" type="button" disabled={busy} onClick={toolMode}>
            Use tool mode
          </button>
        )}
      </Panel>
      <AgentModelSettings
        workspace={workspace}
        onSaved={(result, message) => {
          setWorkspace(result);
          refresh();
          toast(message);
        }}
      />
      <div className="llm-setup-layout">
        <Panel className="llm-provider-picker">
          <PanelTitle
            title="Choose your provider"
            subtitle="Hosted intelligence or a model close to home"
          />
          <div className="llm-kind-switch" role="group" aria-label="Model location">
            <button
              type="button"
              aria-pressed={kind === 'api'}
              disabled={busy}
              onClick={() => switchKind('api')}
            >
              <Cloud size={15} /> API
            </button>
            <button
              type="button"
              aria-pressed={kind === 'local'}
              disabled={busy}
              onClick={() => switchKind('local')}
            >
              <Laptop size={15} /> Local
            </button>
          </div>
          <div
            className="llm-provider-grid"
            role="group"
            aria-label={`${kind === 'api' ? 'API' : 'Local'} model providers`}
          >
            {workspace.providers
              .filter((p) => p.kind === kind)
              .map((p) => (
                <button
                  type="button"
                  key={p.id}
                  aria-pressed={selected === p.id}
                  disabled={busy}
                  onClick={() => select(p)}
                >
                  <span className={`provider-mark provider-${p.id}`}>
                    <ProviderMark provider={p.id} />
                  </span>
                  <span>
                    {p.name}
                    <small>
                      {p.id === workspace.active_provider
                        ? 'Default provider'
                        : workspace.profiles[p.id].saved
                          ? 'Saved'
                          : p.id === 'mock'
                            ? 'Testing only'
                            : p.id === 'llama.cpp-local'
                              ? 'GGUF file'
                              : p.kind === 'local'
                                ? 'Model server'
                                : 'API provider'}
                    </small>
                  </span>
                  {selected === p.id && <Check size={14} className="llm-provider-check" />}
                </button>
              ))}
          </div>
          <p className="llm-provider-note">
            All {workspace.providers.filter((p) => p.id !== 'none').length} ProtoLink providers.
            Your saved setup stays with each provider.
          </p>
        </Panel>
        <Panel className="llm-model-panel">
          <div className="llm-model-heading">
            <span className={`provider-mark provider-${selected}`}>
              <ProviderMark provider={selected} size={27} />
            </span>
            <div>
              <h2>{provider.name}</h2>
              <p>{provider.description}</p>
            </div>
            {selected === workspace.active_provider && <Badge>Default provider</Badge>}
          </div>
          <form
            className="form"
            onSubmit={(event) => {
              event.preventDefault();
              void save(true);
            }}
          >
            <label>
              Model
              <select
                value={draft.custom ? '__custom__' : draft.model}
                disabled={busy}
                onChange={(event) =>
                  event.target.value === '__custom__'
                    ? update({
                        custom: true,
                        model: provider.models.includes(draft.model) ? '' : draft.model,
                      })
                    : update({ model: event.target.value, custom: false })
                }
              >
                {provider.models.map((model) => (
                  <option key={model} value={model}>
                    {model}
                  </option>
                ))}
                <option value="__custom__">
                  {selected === 'llama.cpp-local' ? 'Custom GGUF file…' : 'Custom model…'}
                </option>
              </select>
            </label>
            {draft.custom && (
              <label>
                {selected === 'llama.cpp-local' ? 'GGUF file path' : 'Custom model ID'}
                <input
                  required
                  maxLength={500}
                  disabled={busy}
                  value={draft.model}
                  onChange={(event) => update({ model: event.target.value })}
                  placeholder={
                    selected === 'llama.cpp-local'
                      ? '/absolute/server/path/model.gguf'
                      : 'Exact model ID from your provider'
                  }
                  autoComplete="off"
                  spellCheck={false}
                />
              </label>
            )}
            <p className="footnote llm-model-hint">
              {selected === 'llama.cpp-local'
                ? 'Choose a GGUF file that already exists on the Python server.'
                : kind === 'local'
                  ? 'Presets are examples. Use the exact ID of a model already loaded or installed on your server.'
                  : selected === 'openai-compatible'
                    ? 'Use the model ID exposed by your endpoint.'
                    : 'Presets are suggestions; availability depends on your provider account.'}{' '}
              {provider.docs_url && (
                <a className="text-link" href={provider.docs_url} target="_blank" rel="noreferrer">
                  Provider guide <ArrowUpRight size={11} />
                </a>
              )}
            </p>
            {!!provider.base_url && (
              <label>
                Server URL
                <input
                  type="url"
                  required
                  maxLength={2048}
                  disabled={busy}
                  value={draft.base_url}
                  onChange={(event) => update({ base_url: event.target.value })}
                  placeholder={provider.base_url}
                  autoComplete="off"
                  spellCheck={false}
                />
              </label>
            )}
            {selected === 'ollama' && (
              <OllamaControls
                endpoint={draft.base_url}
                model={draft.model}
                onModel={(model) => update({ model, custom: !provider.models.includes(model) })}
              />
            )}
            {!['mock', 'llama.cpp-local'].includes(selected) && (
              <div className="llm-key-field">
                <label>
                  {provider.requires_key ? 'API key' : 'API key · optional'}
                  <input
                    type="password"
                    maxLength={8192}
                    required={provider.requires_key && !profile.has_api_key}
                    disabled={busy}
                    value={draft.key}
                    onChange={(event) => update({ key: event.target.value })}
                    placeholder={
                      profile.has_api_key
                        ? 'Key configured · enter a new key to replace it'
                        : `Paste your ${provider.name} key`
                    }
                    autoComplete="new-password"
                    spellCheck={false}
                  />
                </label>
                <div className="llm-key-status">
                  <span>
                    {profile.has_api_key ? <ShieldCheck size={13} /> : <KeyRound size={13} />}{' '}
                    {profile.key_source === 'saved'
                      ? 'Key saved in your encrypted vault'
                      : profile.key_source === 'environment'
                        ? 'Using a key from the server environment'
                        : provider.requires_key
                          ? 'A key is required for this provider'
                          : 'Only needed if your server requires authentication'}
                  </span>
                  {profile.key_source === 'saved' && (
                    <button
                      type="button"
                      className="text-button"
                      disabled={busy}
                      onClick={() => setRemove(true)}
                    >
                      <Trash2 size={12} /> Remove saved key
                    </button>
                  )}
                </div>
              </div>
            )}
            {!provider.installed && (
              <div className="llm-dependency-note">
                <strong>One server dependency to install</strong>
                <p>
                  Run <code>uv sync --extra {provider.extra}</code> to enable this adapter. You can
                  save its configuration now.
                </p>
              </div>
            )}
            {selected === 'mock' && (
              <p className="inline-alert">
                This runtime returns a simulated response for testing. It does not provide model
                analysis.
              </p>
            )}
            {error && (
              <p className="form-error" role="alert">
                {error}
              </p>
            )}
            <div className="llm-save-row">
              <button className="button primary" type="submit" disabled={busy}>
                {busy ? <LoaderCircle size={15} className="spin" /> : <Check size={15} />}{' '}
                {busy ? 'Saving…' : 'Save as workspace default'}
              </button>
              <button
                type="button"
                className="button secondary"
                disabled={
                  busy ||
                  !draft.model.trim() ||
                  (provider.requires_key && !profile.has_api_key && !draft.key.trim())
                }
                onClick={() => void save(false)}
              >
                Save profile only
              </button>
            </div>
            <p className="footnote">
              Keys are encrypted on your server and never returned to the browser. Saving does not
              contact the provider or verify access.
            </p>
          </form>
        </Panel>
      </div>
      {remove && (
        <Modal
          title={`Remove ${provider.name} key?`}
          onClose={() => {
            if (!busy) setRemove(false);
          }}
        >
          <p className="muted">
            The saved key will be removed from this workspace and all agents using this provider.
            Overrides remain selected and need setup until you re-enter it to use this provider
            again. A separately configured environment key remains available.
          </p>
          <div className="modal-actions">
            <button
              type="button"
              className="button secondary"
              disabled={busy}
              onClick={() => setRemove(false)}
            >
              Cancel
            </button>
            <button type="button" className="button primary" disabled={busy} onClick={removeKey}>
              {busy ? 'Removing…' : 'Remove key'}
            </button>
          </div>
          {error && (
            <p className="form-error" role="alert">
              {error}
            </p>
          )}
        </Modal>
      )}
    </>
  );
}

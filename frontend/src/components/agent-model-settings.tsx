import { useState } from 'react';
import { Check, ChevronDown, Settings2, Sparkles } from 'lucide-react';
import { post, refresh } from '../lib/api';
import type { AgentModelSelection, ModelWorkspace } from '../lib/types';
import { Badge, Modal, Panel, PanelTitle } from './ui';
import { ProviderMark } from './provider-mark';

type Review = { agent: AgentModelSelection; revision: number };

/** Optional overrides share provider credentials, without changing native agent declarations. */
export function AgentModelSettings({
  workspace,
  onSaved,
}: {
  workspace: ModelWorkspace;
  onSaved: (workspace: ModelWorkspace, message: string) => void;
}) {
  const [expanded, setExpanded] = useState(() =>
    workspace.agents.some((agent) => !agent.inherited),
  );
  const [review, setReview] = useState<Review>();
  const [provider, setProvider] = useState('');
  const [model, setModel] = useState('');
  const [custom, setCustom] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const overrides = workspace.agents.filter((agent) => !agent.inherited).length;
  const definition = workspace.providers.find((item) => item.id === provider);
  const profile = workspace.profiles[provider];
  const configured =
    !definition ||
    ['none', 'mock'].includes(provider) ||
    profile?.saved ||
    (workspace.source === 'environment' && workspace.active_provider === provider);
  const missingKey = definition?.requires_key && !profile?.has_api_key;
  const changed = review && workspace.agent_revision !== review.revision;
  const open = (agent: AgentModelSelection) => {
    setReview({ agent, revision: workspace.agent_revision });
    setProvider(agent.selection?.provider ?? '');
    setModel(agent.selection?.model ?? '');
    setCustom(
      !!agent.selection?.model &&
        !workspace.providers
          .find((item) => item.id === agent.selection?.provider)
          ?.models.includes(agent.selection.model),
    );
    setError('');
  };
  const chooseProvider = (value: string) => {
    const next = workspace.providers.find((item) => item.id === value);
    const nextModel = ['none', 'mock'].includes(value)
      ? ''
      : workspace.profiles[value]?.model || next?.models[0] || '';
    setProvider(value);
    setModel(nextModel);
    setCustom(!!next && !next.models.includes(nextModel));
    setError('');
  };
  const save = async () => {
    if (!review) return;
    setBusy(true);
    setError('');
    try {
      const result = await post<ModelWorkspace>(`/settings/llm/agents/${review.agent.id}`, {
        revision: review.revision,
        provider: provider || null,
        model: provider ? model.trim() : '',
      });
      onSaved(
        result,
        `${review.agent.name} ${provider ? 'model saved' : 'now follows the workspace default'}. Applies to new requests.`,
      );
      setReview(undefined);
    } catch (e) {
      setError((e as Error).message);
      refresh();
    } finally {
      setBusy(false);
    }
  };
  return (
    <Panel className="agent-model-panel">
      <PanelTitle
        title="Agent models"
        subtitle={
          overrides
            ? `${overrides} custom ${overrides === 1 ? 'assignment' : 'assignments'} · other agents follow the workspace default`
            : 'All agents follow the workspace default. Customize only where you need to.'
        }
        action={
          <button
            className="button secondary tiny"
            aria-expanded={expanded}
            aria-controls="agent-model-grid"
            onClick={() => setExpanded(!expanded)}
          >
            <Settings2 size={14} /> {expanded ? 'Collapse' : 'Customize agents'}{' '}
            <ChevronDown size={13} />
          </button>
        }
      />
      {expanded && (
        <>
          <p className="footnote agent-model-intro">
            Sibyl and each specialist can use a different provider or model. Overrides share that
            provider’s saved endpoint and encrypted key. Save provider profiles below first.
            Configuration checks do not verify model access or server availability.
          </p>
          <div className="agent-model-grid" id="agent-model-grid">
            {workspace.agents.map((agent) => (
              <article className="agent-model-card" key={agent.id}>
                <div className="agent-model-card-heading">
                  <span className={`provider-mark provider-${agent.provider}`}>
                    <ProviderMark provider={agent.provider} />
                  </span>
                  <strong>{agent.name}</strong>
                  <Badge tone={agent.simulated ? 'sand' : 'neutral'}>
                    {agent.inherited ? 'Default' : 'Custom'}
                  </Badge>
                </div>
                <p>
                  {workspace.providers.find((item) => item.id === agent.provider)?.name}
                  {agent.model && ` · ${agent.model}`}
                </p>
                <div className="agent-model-card-footer">
                  <span className={agent.provider !== 'none' && !agent.ready ? 'needs-setup' : ''}>
                    {agent.simulated
                      ? 'Simulated responses'
                      : agent.provider === 'none'
                        ? 'Tools only'
                        : agent.ready
                          ? 'Configuration ready'
                          : 'Needs setup'}
                  </span>
                  <button
                    className="text-button"
                    onClick={() => open(agent)}
                    aria-label={`Configure ${agent.name} model`}
                  >
                    Configure
                  </button>
                </div>
              </article>
            ))}
          </div>
          <p className="footnote agent-model-intro">
            New requests freeze the team’s configuration, including delegated consultations. Saving
            a change affects subsequent requests. Tool-only specialists still expose their tools,
            but cannot complete delegated reasoning tasks. An unavailable override never silently
            switches to another provider. Messages and tool evidence can be shared with selected
            providers, including when Sibyl delegates.
          </p>
        </>
      )}
      {review && (
        <Modal title={`${review.agent.name} model`} onClose={() => !busy && setReview(undefined)}>
          <form
            className="form"
            onSubmit={(event) => {
              event.preventDefault();
              void save();
            }}
          >
            <label>
              Model provider
              <select
                value={provider}
                onChange={(event) => chooseProvider(event.target.value)}
                disabled={busy}
              >
                <option value="">Follow workspace default</option>
                {(['api', 'local', 'tools'] as const).map((kind) => (
                  <optgroup
                    key={kind}
                    label={
                      kind === 'api'
                        ? 'API providers'
                        : kind === 'local'
                          ? 'Local providers'
                          : 'Tools'
                    }
                  >
                    {workspace.providers
                      .filter((item) => item.kind === kind)
                      .map((item) => (
                        <option key={item.id} value={item.id}>
                          {item.name}
                          {!['none', 'mock'].includes(item.id) &&
                          !workspace.profiles[item.id].saved &&
                          !(
                            workspace.source === 'environment' &&
                            workspace.active_provider === item.id
                          )
                            ? ' · save profile first'
                            : ''}
                        </option>
                      ))}
                  </optgroup>
                ))}
              </select>
            </label>
            {!provider ? (
              <p className="monitor-notice">
                This agent follows the current workspace default, including future changes to that
                default.
              </p>
            ) : (
              <div className="agent-model-provider-note">
                <span className={`provider-mark provider-${provider}`}>
                  <ProviderMark provider={provider} />
                </span>
                <p>
                  {definition?.name}
                  {profile?.base_url && <small>Shared endpoint: {profile.base_url}</small>}
                </p>
              </div>
            )}
            {!!provider && !['none', 'mock'].includes(provider) && (
              <>
                <label>
                  Model
                  <select
                    value={custom ? '__custom__' : model}
                    disabled={busy}
                    onChange={(event) => {
                      if (event.target.value === '__custom__') {
                        setCustom(true);
                        setModel('');
                      } else {
                        setCustom(false);
                        setModel(event.target.value);
                      }
                    }}
                  >
                    {definition?.models.map((value) => (
                      <option key={value}>{value}</option>
                    ))}
                    <option value="__custom__">
                      {provider === 'llama.cpp-local' ? 'Custom GGUF file…' : 'Custom model…'}
                    </option>
                  </select>
                </label>
                {custom && (
                  <label>
                    {provider === 'llama.cpp-local' ? 'GGUF file path' : 'Custom model ID'}
                    <input
                      required
                      value={model}
                      onChange={(event) => setModel(event.target.value)}
                      maxLength={500}
                      disabled={busy}
                      autoComplete="off"
                      spellCheck={false}
                    />
                  </label>
                )}
                <p className="footnote">
                  Presets are suggestions. Use a model available to your account or already
                  installed on the selected server. The provider profile’s key and endpoint apply to
                  every agent assigned to it.
                </p>
              </>
            )}
            {(!configured || missingKey) && (
              <p className="monitor-notice">
                {missingKey ? 'Add this provider’s key' : 'Save this provider profile'} in the
                provider settings below before assigning it. You can save a profile without changing
                the workspace default.
              </p>
            )}
            {provider === 'mock' && (
              <p className="monitor-notice">Mock produces simulated answers for testing.</p>
            )}
            {provider === 'none' && (
              <p className="monitor-notice">
                Direct module requests return read-only snapshots. Native tool calls remain
                available; reasoning requests are unavailable. Sibyl requires a model and will be
                unavailable in tool mode.
              </p>
            )}
            {changed && (
              <p className="form-error" role="alert">
                Agent assignments changed. Close and reopen this dialog before saving.
              </p>
            )}
            {error && (
              <p className="form-error" role="alert">
                {error}
              </p>
            )}
            <button
              className="button primary full-width"
              disabled={
                busy ||
                !configured ||
                missingKey ||
                !!changed ||
                (!!provider && !['none', 'mock'].includes(provider) && !model.trim())
              }
            >
              <Check size={14} /> {busy ? 'Saving…' : 'Save agent model'}
            </button>
            <p className="footnote">
              <Sparkles size={12} /> Applies to new requests. Messages and tool evidence may be sent
              to the selected provider.
            </p>
          </form>
        </Modal>
      )}
    </Panel>
  );
}

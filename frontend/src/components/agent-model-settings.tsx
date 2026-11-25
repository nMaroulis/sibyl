import { useState } from 'react';
import { Check, ChevronDown, Settings2 } from 'lucide-react';
import { post, refresh } from '../lib/api';
import type { AgentModelSelection, ModelWorkspace } from '../lib/types';
import { Badge, Modal, Panel, PanelTitle } from './ui';
import { ProviderMark } from './provider-mark';

type Review = { agent: AgentModelSelection; revision: number };

/** Route individual agents to a named connection and its selected model. */
export function AgentModelSettings({
  workspace,
  onSaved,
}: {
  workspace: ModelWorkspace;
  onSaved: (workspace: ModelWorkspace, message: string) => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const [review, setReview] = useState<Review>();
  const [value, setValue] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const overrides = workspace.agents.filter((agent) => !agent.inherited).length;
  const selected = workspace.deployments.find((deployment) => deployment.id === value);
  const original = review?.agent.selection?.deployment ?? review?.agent.selection?.provider ?? '';
  const changed = review && workspace.agent_revision !== review.revision;

  function open(agent: AgentModelSelection) {
    setReview({ agent, revision: workspace.agent_revision });
    setValue(agent.selection?.deployment ?? agent.selection?.provider ?? '');
    setError('');
  }

  async function save() {
    if (!review) return;
    setBusy(true);
    setError('');
    try {
      const result = await post<ModelWorkspace>(`/settings/llm/agents/${review.agent.id}`, {
        revision: review.revision,
        ...(value === 'none'
          ? { provider: 'none' }
          : value
            ? { deployment: value }
            : { provider: null }),
      });
      onSaved(result, `${review.agent.name} model updated.`);
      setReview(undefined);
    } catch (reason) {
      setError((reason as Error).message);
      refresh();
    } finally {
      setBusy(false);
    }
  }

  return (
    <Panel className="agent-model-panel">
      <PanelTitle
        title="Agent models"
        subtitle={
          overrides
            ? `${overrides} custom ${overrides === 1 ? 'assignment' : 'assignments'}`
            : 'All agents follow the workspace default.'
        }
        action={
          <button
            className="button secondary tiny"
            type="button"
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
        <div className="agent-model-grid" id="agent-model-grid">
          {workspace.agents.map((agent) => {
            const reference = agent.inherited
              ? workspace.active_deployment
              : (agent.selection?.deployment ?? agent.provider);
            const deployment = workspace.deployments.find((item) => item.id === reference);
            return (
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
                  {deployment?.name || 'Tool mode'}
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
                    type="button"
                    onClick={() => open(agent)}
                    aria-label={`Configure ${agent.name} model`}
                  >
                    Configure
                  </button>
                </div>
              </article>
            );
          })}
        </div>
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
              Deployment
              <select
                value={value}
                disabled={busy}
                onChange={(event) => {
                  setValue(event.target.value);
                  setError('');
                }}
              >
                <option value="">Follow workspace default</option>
                {workspace.deployments.map((deployment) => (
                  <option key={deployment.id} value={deployment.id} disabled={!deployment.model}>
                    {deployment.name}
                    {deployment.model ? ` · ${deployment.model}` : ' · Choose a model first'}
                  </option>
                ))}
                <option value="none">Tool mode</option>
              </select>
            </label>
            {selected?.reason && <p className="monitor-notice">{selected.reason}</p>}
            {changed && (
              <p className="form-error" role="alert">
                Agent assignments changed. Reopen this dialog before saving.
              </p>
            )}
            {error && (
              <p className="form-error" role="alert">
                {error}
              </p>
            )}
            <button
              className="button primary full-width"
              disabled={busy || !!changed || value === original || (!!selected && !selected.model)}
            >
              <Check size={14} /> {busy ? 'Saving…' : 'Save agent model'}
            </button>
          </form>
        </Modal>
      )}
    </Panel>
  );
}

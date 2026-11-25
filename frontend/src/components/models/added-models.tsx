import { useState } from 'react';
import { Check, Cloud, KeyRound, Pencil, Power, RefreshCw, Trash2 } from 'lucide-react';
import { post } from '../../lib/api';
import type { ModelDeployment, ModelProvider, ModelWorkspace } from '../../lib/types';
import { Badge, Panel, PanelTitle } from '../ui';
import { ProviderMark } from '../provider-mark';
import { LocalModelMonitor, sameModel, supportsModelMonitor } from './local-model-monitor';
import { DeploymentActivity } from './deployment-activity';
import { ModelChoice } from './model-choice';
import type { ModelDraft } from './model-choice';

type CheckResult = { status: string; detail: string };

function ModelCheck({ deployment }: { deployment: ModelDeployment }) {
  const [result, setResult] = useState<CheckResult>();
  const [checking, setChecking] = useState(false);

  async function check() {
    setChecking(true);
    setResult(undefined);
    try {
      setResult(await post<CheckResult>(`/settings/llm/deployments/${deployment.id}/check`, {}));
    } catch (error) {
      setResult({ status: 'failed', detail: (error as Error).message });
    } finally {
      setChecking(false);
    }
  }

  return (
    <div className="added-model-check">
      <button
        type="button"
        className="button secondary tiny"
        disabled={checking || !deployment.model}
        onClick={() => void check()}
      >
        <RefreshCw size={13} className={checking ? 'spin' : undefined} />
        {checking ? 'Checking…' : 'Check status'}
      </button>
      {result && (
        <span
          className="added-model-check-result"
          data-ok={['ready', 'configured'].includes(result.status)}
          role="status"
        >
          {result.status === 'ready' && <Check size={13} />}
          {result.detail}
        </span>
      )}
    </div>
  );
}

type CardActions = {
  onEdit: (deployment: ModelDeployment, provider: ModelProvider) => void;
  onDelete: (deployment: ModelDeployment) => void;
  onDefault: (deployment?: ModelDeployment) => void;
  onModel: (deployment: ModelDeployment, model: string) => Promise<void>;
};

function DeploymentCard({
  deployment,
  provider,
  visible,
  busy,
  onEdit,
  onDelete,
  onDefault,
  onModel,
}: CardActions & {
  deployment: ModelDeployment;
  provider: ModelProvider;
  visible: boolean;
  busy: boolean;
}) {
  const [catalog, setCatalog] = useState<string[] | null>();
  const [choosing, setChoosing] = useState(false);
  const [draft, setDraft] = useState<ModelDraft>();
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const missingKey = provider.requires_key && deployment.key_source === 'none';
  const activationHint = !deployment.model
    ? 'Choose a model to activate this deployment.'
    : missingKey
      ? 'Add an API key to activate this deployment.'
      : 'Use this model as the workspace default.';
  const ollama = provider.id === 'ollama';
  const installed = catalog ?? [];
  const options = [
    ...new Set(
      ollama ? installed : [...installed, ...provider.models, ...deployment.legacy_models],
    ),
  ].filter(Boolean);
  const model = draft?.model ?? deployment.model;
  const listedModel = options.find((option) => sameModel(option, model, ollama));
  const selection = {
    model: draft?.custom ? model : (listedModel ?? model),
    custom: !!draft?.custom || (!!model && !listedModel),
  };

  async function saveModel() {
    setSaving(true);
    setError('');
    try {
      await onModel(deployment, selection.model.trim());
      setChoosing(false);
    } catch (reason) {
      setError((reason as Error).message);
    } finally {
      setSaving(false);
    }
  }

  return (
    <article
      className="added-model-card"
      data-kind={provider.kind}
      data-workspace-default={deployment.default}
      id={`added-model-${deployment.id}`}
      aria-label={deployment.name}
    >
      <header>
        <span className={`provider-mark provider-${provider.id}`}>
          <ProviderMark provider={provider.id} size={20} />
        </span>
        <div className="added-model-provider">
          <div className="added-model-heading">
            <h3>{deployment.name}</h3>
            {deployment.default ? (
              <Badge tone="lime">
                <Check size={11} aria-hidden="true" /> Active in workspace
              </Badge>
            ) : deployment.agents.length ? (
              <Badge tone="purple">Agent only</Badge>
            ) : (
              <Badge>Inactive</Badge>
            )}
          </div>
          {(deployment.base_url || !deployment.name.startsWith(provider.name)) && (
            <small title={deployment.base_url}>{deployment.base_url || provider.name}</small>
          )}
        </div>
        <div className="added-model-admin">
          {!deployment.default && (
            <button
              className="button primary tiny"
              type="button"
              disabled={busy || saving || !deployment.model || missingKey}
              title={activationHint}
              aria-description={activationHint}
              onClick={() => onDefault(deployment)}
            >
              <Power size={13} aria-hidden="true" /> Activate model
            </button>
          )}
          <button
            className="button secondary tiny"
            type="button"
            disabled={busy || saving}
            aria-label={`Edit ${deployment.name}`}
            onClick={() => onEdit(deployment, provider)}
          >
            <Pencil size={12} /> Edit
          </button>
          {deployment.removable && (
            <button
              className="button secondary tiny added-model-delete"
              type="button"
              disabled={busy || saving}
              aria-label={`Delete ${deployment.name}`}
              onClick={() => onDelete(deployment)}
            >
              <Trash2 size={12} /> Delete
            </button>
          )}
        </div>
      </header>

      {(provider.kind === 'api' || deployment.key_source !== 'none') && (
        <div className="added-model-credential">
          <KeyRound size={13} aria-hidden="true" /> <span>API key</span>
          {deployment.key_source === 'environment' ? (
            <span>Server environment</span>
          ) : deployment.key_preview ? (
            <code aria-label="Masked saved API key">{deployment.key_preview}</code>
          ) : (
            <span>{provider.requires_key ? 'Required' : 'None configured'}</span>
          )}
        </div>
      )}
      {provider.id === 'ollama' && deployment.context_window && (
        <small className="added-model-context">
          {deployment.context_window.toLocaleString()} token context window
        </small>
      )}

      <div className="added-model-row">
        <div className="added-model-name">
          <strong>{deployment.model || 'No model selected'}</strong>
          {!!deployment.agents.length && (
            <span className="added-model-assignments">
              {deployment.agents.length}{' '}
              {deployment.agents.length === 1 ? 'agent assigned' : 'agents assigned'}
            </span>
          )}
        </div>
        <div className="added-model-actions">
          <button
            className="button secondary tiny"
            type="button"
            disabled={busy || saving}
            aria-expanded={choosing}
            onClick={() => {
              setDraft(undefined);
              setChoosing(!choosing);
              setError('');
            }}
          >
            {deployment.model ? 'Change model' : 'Choose model'}
          </button>
          {(provider.kind === 'api' || provider.id === 'llama.cpp-local') && deployment.model && (
            <ModelCheck key={deployment.model} deployment={deployment} />
          )}
        </div>
      </div>
      {deployment.model && deployment.reason && !missingKey && (
        <p className="added-model-setup">{deployment.reason}</p>
      )}
      {choosing && (
        <form
          className="form added-model-picker"
          onSubmit={(event) => {
            event.preventDefault();
            void saveModel();
          }}
        >
          <ModelChoice
            provider={provider}
            options={options}
            draft={selection}
            disabled={busy || saving}
            update={setDraft}
          />
          {ollama && !installed.length && (
            <p className="footnote">
              {catalog === undefined
                ? 'Checking installed models…'
                : catalog === null
                  ? 'The model list is unavailable. You can enter a custom model ID.'
                  : 'No models are installed on this Ollama server.'}
            </p>
          )}
          {error && (
            <p className="form-error" role="alert">
              {error}
            </p>
          )}
          <button
            className="button primary tiny"
            type="submit"
            disabled={busy || saving || !selection.model.trim()}
          >
            <Check size={13} /> {saving ? 'Saving…' : 'Save model'}
          </button>
        </form>
      )}

      {provider.kind === 'api' && (
        <DeploymentActivity deployment={deployment.id} model={deployment.model} visible={visible} />
      )}
      {supportsModelMonitor(provider.id) && (
        <LocalModelMonitor
          deployment={deployment.id}
          provider={provider.id}
          name={deployment.name}
          model={deployment.model}
          visible={visible}
          onCatalog={setCatalog}
        />
      )}
    </article>
  );
}

export function AddedModels({
  workspace,
  visible,
  busy,
  revisions,
  ...actions
}: CardActions & {
  workspace: ModelWorkspace;
  visible: boolean;
  busy: boolean;
  revisions: Record<string, number>;
}) {
  const deployments = [...workspace.deployments].sort(
    (a, b) => Number(b.default) - Number(a.default),
  );
  return (
    <Panel className="added-models-panel">
      <PanelTitle
        title="Added models"
        subtitle={workspace.active_deployment ? undefined : 'Workspace default · Tool mode'}
        action={
          workspace.active_deployment && (
            <button
              className="text-button added-model-tool-mode"
              type="button"
              disabled={busy}
              onClick={() => actions.onDefault()}
            >
              Use tool mode
            </button>
          )
        }
      />
      {!deployments.length && (
        <div className="added-models-empty">
          <Cloud aria-hidden="true" size={18} />
          <p>Choose a provider below to add your first deployment.</p>
        </div>
      )}
      <div className="added-models-list">
        {deployments.map((deployment) => {
          const provider = workspace.providers.find((item) => item.id === deployment.provider);
          return (
            provider && (
              <DeploymentCard
                key={JSON.stringify([
                  deployment.id,
                  revisions[deployment.id] ?? 0,
                  deployment.base_url,
                  deployment.key_source,
                  deployment.key_preview,
                ])}
                deployment={deployment}
                provider={provider}
                visible={visible}
                busy={busy}
                {...actions}
              />
            )
          );
        })}
      </div>
    </Panel>
  );
}

import { useEffect, useRef, useState } from 'react';
import { Cloud, Laptop, Plus } from 'lucide-react';
import { api, post, refresh } from '../lib/api';
import { useResource } from '../lib/hooks';
import type { ModelDeployment, ModelProvider, ModelWorkspace } from '../lib/types';
import { ErrorState, Loading, Modal, Panel, PanelTitle, useToast } from './ui';
import { ProviderMark } from './provider-mark';
import { AgentModelSettings } from './agent-model-settings';
import { AddedModels } from './models/added-models';
import { ProviderEditor } from './models/provider-editor';
import type { Draft } from './models/provider-editor';

type ProviderKind = 'api' | 'local';
const deploymentsPath = '/settings/llm/deployments';

export function ModelSettings({ visible }: { visible: boolean }) {
  const resource = useResource<ModelWorkspace>('/settings/llm');
  if (resource.loading && !resource.data) return <Loading />;
  if (resource.error || !resource.data)
    return (
      <ErrorState
        message={resource.error || 'Model settings unavailable.'}
        retry={resource.retry}
      />
    );
  return <ModelEditor data={resource.data} visible={visible} />;
}

function makeDraft(
  provider: ModelProvider,
  workspace: ModelWorkspace,
  deployment?: ModelDeployment,
): Draft {
  const base = `${provider.name} ${provider.kind === 'api' ? 'API ' : ''}model`;
  const names = new Set(
    workspace.deployments
      .filter((item) => item.provider === provider.id)
      .map((item) => item.name.toLowerCase()),
  );
  let name = base;
  for (let number = 1; names.has(name.toLowerCase()); number += 1) name = `${base} (${number})`;
  return {
    name: deployment?.name ?? name,
    model: '',
    custom: false,
    base_url: deployment?.base_url || provider.base_url,
    context_window: deployment?.context_window ?? (provider.id === 'ollama' ? 32768 : null),
    max_output_tokens: deployment?.max_output_tokens ?? null,
    key: '',
  };
}

function ModelEditor({ data, visible }: { data: ModelWorkspace; visible: boolean }) {
  const [workspace, setWorkspace] = useState(data);
  const [kind, setKind] = useState<ProviderKind>(
    data.providers.find((provider) => provider.id === data.active_provider)?.kind === 'local'
      ? 'local'
      : 'api',
  );
  const [selected, setSelected] = useState<string>();
  const [drafts, setDrafts] = useState<Record<string, Draft>>({});
  const [editing, setEditing] = useState<{ deployment: ModelDeployment; draft: Draft }>();
  const [deleting, setDeleting] = useState<ModelDeployment>();
  const [revisions, setRevisions] = useState<Record<string, number>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [actionError, setActionError] = useState('');
  const heading = useRef<HTMLHeadingElement>(null);
  const toast = useToast();
  useEffect(() => setWorkspace(data), [data]);

  const adding = workspace.providers.find((item) => item.id === selected);
  const provider = editing
    ? workspace.providers.find((item) => item.id === editing.deployment.provider)
    : adding;
  const draft = editing?.draft ?? (adding ? drafts[adding.id] : undefined);

  function openAdd(next: ModelProvider) {
    setSelected(next.id);
    setError('');
    setDrafts((previous) => ({
      ...previous,
      [next.id]: previous[next.id] ?? makeDraft(next, workspace),
    }));
    requestAnimationFrame(() => {
      heading.current?.focus({ preventScroll: true });
      heading.current?.scrollIntoView({ block: 'nearest' });
    });
  }

  function updateDraft(patch: Partial<Draft>) {
    if (editing) setEditing({ ...editing, draft: { ...editing.draft, ...patch } });
    else if (adding && draft) setDrafts((old) => ({ ...old, [adding.id]: { ...draft, ...patch } }));
  }

  function saved(result: ModelWorkspace, message: string) {
    setWorkspace(result);
    refresh();
    toast(message);
  }

  async function save() {
    if (!draft || !provider || busy) return;
    setBusy(true);
    setError('');
    const identity = editing?.deployment.id;
    try {
      const result = await api<ModelWorkspace>(
        identity ? `${deploymentsPath}/${identity}` : deploymentsPath,
        {
          method: identity ? 'PUT' : 'POST',
          body: JSON.stringify({
            provider: provider.id,
            name: draft.name.trim(),
            model: draft.model.trim(),
            base_url: draft.base_url.trim(),
            ...((provider.kind === 'api' || provider.id === 'ollama') && {
              context_window: draft.context_window,
            }),
            ...(provider.supports_output_limit && { max_output_tokens: draft.max_output_tokens }),
            ...(draft.key.trim() ? { api_key: draft.key.trim() } : {}),
          }),
        },
      );
      if (identity) {
        setRevisions((previous) => ({ ...previous, [identity]: (previous[identity] ?? 0) + 1 }));
        setEditing(undefined);
        saved(result, 'Connection updated.');
      } else {
        const added = result.deployments.find(
          (item) => !workspace.deployments.some((previous) => previous.id === item.id),
        );
        setSelected(undefined);
        setDrafts((old) => ({ ...old, [provider.id]: makeDraft(provider, result) }));
        saved(result, 'Deployment added.');
        requestAnimationFrame(() => {
          if (added)
            document
              .getElementById(`added-model-${added.id}`)
              ?.scrollIntoView({ block: 'nearest' });
        });
      }
    } catch (reason) {
      setError((reason as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function changeDefault(deployment?: ModelDeployment) {
    setBusy(true);
    setActionError('');
    try {
      const result = deployment
        ? await post<ModelWorkspace>(`${deploymentsPath}/${deployment.id}/default`, {})
        : await post<ModelWorkspace>('/settings/llm/default', { provider: 'none' });
      saved(
        result,
        deployment
          ? `${deployment.name} is now the default.`
          : 'Workspace default set to tool mode.',
      );
    } catch (reason) {
      setActionError((reason as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function chooseModel(deployment: ModelDeployment, model: string) {
    const result = await api<ModelWorkspace>(`${deploymentsPath}/${deployment.id}/model`, {
      method: 'PUT',
      body: JSON.stringify({ model }),
    });
    saved(result, 'Model saved.');
  }

  async function remove() {
    if (!deleting || busy) return;
    setBusy(true);
    setError('');
    try {
      saved(
        await api<ModelWorkspace>(`${deploymentsPath}/${deleting.id}`, { method: 'DELETE' }),
        'Deployment deleted.',
      );
      setDeleting(undefined);
    } catch (reason) {
      setError((reason as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const editor = provider && draft && (
    <ProviderEditor
      provider={provider}
      deployment={editing?.deployment}
      draft={draft}
      busy={busy}
      error={error}
      update={updateDraft}
      save={() => void save()}
    />
  );

  return (
    <div className="model-settings-workspace">
      <AddedModels
        workspace={workspace}
        visible={visible}
        busy={busy}
        revisions={revisions}
        onEdit={(deployment, item) => {
          setEditing({ deployment, draft: makeDraft(item, workspace, deployment) });
          setError('');
        }}
        onDelete={(deployment) => {
          setDeleting(deployment);
          setError('');
        }}
        onDefault={(deployment) => void changeDefault(deployment)}
        onModel={chooseModel}
      />
      {actionError && (
        <p className="form-error" role="alert">
          {actionError}
        </p>
      )}
      <Panel className="llm-provider-picker">
        <PanelTitle title="Add a deployment" subtitle="Choose your provider." />
        <div className="llm-kind-switch" role="group" aria-label="Model location">
          {(['api', 'local'] as const).map((item) => (
            <button
              type="button"
              key={item}
              aria-pressed={kind === item}
              disabled={busy}
              onClick={() => {
                if (kind === item) return;
                setKind(item);
                setSelected(undefined);
                setError('');
              }}
            >
              {item === 'api' ? <Cloud size={15} /> : <Laptop size={15} />}
              {item === 'api' ? 'API' : 'Local'}
            </button>
          ))}
        </div>
        <div
          className="llm-provider-grid"
          role="group"
          aria-label={`${kind === 'api' ? 'API' : 'Local'} model providers`}
        >
          {workspace.providers
            .filter((item) => item.kind === kind)
            .map((item) => {
              const count = workspace.deployments.filter(
                (deployment) => deployment.provider === item.id,
              ).length;
              return (
                <button
                  type="button"
                  key={item.id}
                  aria-pressed={selected === item.id}
                  disabled={busy}
                  onClick={() => openAdd(item)}
                >
                  <span className={`provider-mark provider-${item.id}`}>
                    <ProviderMark provider={item.id} />
                  </span>
                  <span>
                    {item.name}
                    {count > 0 && <small>{count} added</small>}
                  </span>
                  <Plus size={14} className="llm-provider-check" aria-hidden="true" />
                </button>
              );
            })}
        </div>
        {adding && (
          <div className="model-add-form">
            <div className="model-add-heading">
              <h3 tabIndex={-1} ref={heading}>
                Add {adding.name}
              </h3>
              <button
                className="text-button"
                type="button"
                disabled={busy}
                onClick={() => setSelected(undefined)}
              >
                Cancel
              </button>
            </div>
            {!editing && !deleting && editor}
          </div>
        )}
      </Panel>
      <AgentModelSettings workspace={workspace} onSaved={saved} />
      {visible && editing && (
        <Modal
          title={`Edit ${editing.deployment.name}`}
          onClose={() => !busy && setEditing(undefined)}
        >
          {editor}
        </Modal>
      )}
      {visible && deleting && (
        <Modal
          title={`Delete ${deleting.name}?`}
          onClose={() => !busy && setDeleting(undefined)}
          initialFocus=".modal-actions .secondary"
        >
          <p className="muted">This deletes the deployment and its saved credentials.</p>
          {deleting.default && (
            <p className="muted">The workspace default will return to tool mode.</p>
          )}
          {deleting.agents.length > 0 && (
            <p className="muted">
              Agents assigned to this deployment will follow the workspace default.
            </p>
          )}
          {error && (
            <p className="form-error" role="alert">
              {error}
            </p>
          )}
          <div className="modal-actions">
            <button
              type="button"
              className="button secondary"
              disabled={busy}
              onClick={() => setDeleting(undefined)}
            >
              Cancel
            </button>
            <button
              type="button"
              className="button rose-button"
              disabled={busy}
              onClick={() => void remove()}
            >
              {busy ? 'Deleting…' : 'Delete deployment'}
            </button>
          </div>
        </Modal>
      )}
    </div>
  );
}

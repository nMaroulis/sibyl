import { ArrowUpRight, Check, LoaderCircle, Plus } from 'lucide-react';
import type { ModelDeployment, ModelProvider } from '../../lib/types';
import { ModelChoice } from './model-choice';
import type { ModelDraft } from './model-choice';

export type Draft = ModelDraft & {
  name: string;
  base_url: string;
  key: string;
  context_window: number | null;
  max_output_tokens: number | null;
};

export function ProviderEditor({
  provider,
  deployment,
  draft,
  busy,
  error,
  update,
  save,
}: {
  provider: ModelProvider;
  deployment?: ModelDeployment;
  draft: Draft;
  busy: boolean;
  error: string;
  update: (patch: Partial<Draft>) => void;
  save: () => void;
}) {
  const needsKey = provider.requires_key && (!deployment || deployment.key_source === 'none');
  const supportsKey = !['mock', 'llama.cpp-local'].includes(provider.id);
  const publishedContext =
    deployment?.auto_context_window ?? provider.context_windows?.[draft.model];
  const ollama = provider.id === 'ollama';
  return (
    <form
      className="form model-provider-form"
      onSubmit={(event) => {
        event.preventDefault();
        save();
      }}
    >
      <label>
        Deployment name
        <input
          required
          maxLength={80}
          disabled={busy}
          value={draft.name}
          onChange={(event) => update({ name: event.target.value })}
        />
      </label>
      {supportsKey && (
        <label>
          {provider.requires_key ? 'API key' : 'API key · optional'}
          <input
            type="password"
            maxLength={8192}
            required={needsKey}
            disabled={busy}
            value={draft.key}
            onChange={(event) => update({ key: event.target.value })}
            placeholder={
              deployment?.key_source && deployment.key_source !== 'none'
                ? 'Enter a replacement key'
                : `Paste your ${provider.name} key`
            }
            autoComplete="new-password"
            spellCheck={false}
          />
        </label>
      )}
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
            autoComplete="off"
            spellCheck={false}
          />
        </label>
      )}
      {!deployment && (
        <ModelChoice provider={provider} draft={draft} disabled={busy} optional update={update} />
      )}
      {(ollama || provider.kind === 'api') && (
        <details className="model-provider-advanced">
          <summary>Advanced</summary>
          <div className="model-advanced-fields">
            <label>
              Context window · tokens
              <input
                type="number"
                min={ollama ? 4096 : 2049}
                max={ollama ? 131072 : 2147483647}
                step={1}
                required={ollama}
                disabled={busy}
                placeholder="Auto"
                value={draft.context_window ?? ''}
                onChange={(event) =>
                  update({
                    context_window: event.target.value === '' ? null : Number(event.target.value),
                  })
                }
              />
              {!ollama && (
                <small className="footnote">
                  {publishedContext
                    ? `Auto · ${publishedContext.toLocaleString()} tokens`
                    : 'Auto uses the published limit when known. Enter a value for a custom endpoint.'}
                </small>
              )}
            </label>
            {provider.supports_output_limit && (
              <label>
                Max output tokens
                <input
                  type="number"
                  min={provider.id === 'openai' ? 16 : 1}
                  max={2147483647}
                  step={1}
                  disabled={busy}
                  placeholder="Adapter default"
                  value={draft.max_output_tokens ?? ''}
                  onChange={(event) =>
                    update({
                      max_output_tokens:
                        event.target.value === '' ? null : Number(event.target.value),
                    })
                  }
                />
                <small className="footnote">Upper limit per model response.</small>
              </label>
            )}
          </div>
        </details>
      )}
      {!provider.installed && (
        <p className="footnote">
          Enable this adapter on the server with <code>uv sync --extra {provider.extra}</code>.
        </p>
      )}
      {error && (
        <p className="form-error" role="alert">
          {error}
        </p>
      )}
      <div className="model-provider-footer">
        <button className="button primary" type="submit" disabled={busy}>
          {busy ? (
            <LoaderCircle size={14} className="spin" />
          ) : deployment ? (
            <Check size={14} />
          ) : (
            <Plus size={14} />
          )}
          {busy ? 'Saving…' : deployment ? 'Save connection' : 'Add deployment'}
        </button>
        {provider.docs_url && (
          <a className="text-link" href={provider.docs_url} target="_blank" rel="noreferrer">
            Provider guide <ArrowUpRight size={11} />
          </a>
        )}
      </div>
    </form>
  );
}

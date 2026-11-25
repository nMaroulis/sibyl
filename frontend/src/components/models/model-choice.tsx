import type { ModelProvider } from '../../lib/types';

export type ModelDraft = { model: string; custom: boolean };

export function ModelChoice({
  provider,
  options = provider.models,
  draft,
  disabled,
  optional = false,
  update,
}: {
  provider: ModelProvider;
  options?: string[];
  draft: ModelDraft;
  disabled: boolean;
  optional?: boolean;
  update: (draft: ModelDraft) => void;
}) {
  const embedded = provider.id === 'llama.cpp-local';
  return (
    <>
      <label>
        {optional ? 'Model · optional' : 'Model'}
        <select
          value={draft.custom ? '__custom__' : draft.model}
          disabled={disabled}
          onChange={(event) => {
            const value = event.target.value;
            update({ model: value === '__custom__' ? '' : value, custom: value === '__custom__' });
          }}
        >
          <option value="" disabled={!optional}>
            {optional ? 'Choose later' : 'Choose a model'}
          </option>
          {options.map((model) => (
            <option key={model}>{model}</option>
          ))}
          <option value="__custom__">{embedded ? 'Custom GGUF file…' : 'Custom model…'}</option>
        </select>
      </label>
      {draft.custom && (
        <label>
          {embedded ? 'GGUF file path' : 'Custom model ID'}
          <input
            required
            maxLength={500}
            disabled={disabled}
            value={draft.model}
            onChange={(event) => update({ ...draft, model: event.target.value })}
            placeholder={embedded ? '/path/to/model.gguf' : 'Exact model ID'}
            autoComplete="off"
            spellCheck={false}
          />
        </label>
      )}
    </>
  );
}

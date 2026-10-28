import type { ChangeEvent, ClipboardEvent } from 'react';
import { useId, useState } from 'react';
import { Eye, EyeOff, KeyRound } from 'lucide-react';

/** Display only the ends of an entered credential; the original value is submitted. */
export function SecretField({
  label,
  value,
  onChange,
  multiline = false,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  multiline?: boolean;
}) {
  const id = useId();
  const [revealed, setRevealed] = useState(false);
  const [preview, setPreview] = useState(true);
  const material = value.replace(/-----[^\n]+-----/g, '').replace(/\s/g, '');
  const masked =
    material.length > 12 ? `${material.slice(0, 4)}  ••••••••  ${material.slice(-4)}` : '••••••••';
  const overlay = !revealed && Boolean(value) && (preview || multiline);
  const common = {
    id,
    required: true,
    value,
    autoComplete: 'off',
    spellCheck: false,
    onChange: (event: ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) =>
      onChange(event.target.value),
    onFocus: () => setPreview(false),
    onBlur: () => setPreview(true),
    onKeyDown: () => setPreview(false),
    onPaste: (event: ClipboardEvent<HTMLInputElement | HTMLTextAreaElement>) => {
      event.preventDefault();
      onChange(event.clipboardData.getData('text').trim());
      setPreview(true);
    },
  };
  return (
    <div className="credential-field">
      <label htmlFor={id}>{label}</label>
      <div
        className={`credential-entry ${overlay ? 'has-preview' : ''} ${multiline && !revealed ? 'hidden-multiline' : ''}`}
      >
        {multiline ? (
          <textarea {...common} rows={3} />
        ) : (
          <input {...common} type={revealed ? 'text' : 'password'} />
        )}
        {overlay && (
          <span className="credential-preview" aria-hidden="true">
            {masked}
          </span>
        )}
        <button
          type="button"
          className="credential-visibility"
          aria-label={`${revealed ? 'Hide' : 'Show'} ${label}`}
          aria-pressed={revealed}
          onClick={() => {
            setRevealed(!revealed);
            setPreview(true);
          }}
        >
          {revealed ? <EyeOff size={16} /> : <Eye size={16} />}
        </button>
      </div>
      {value && (
        <small className="credential-receipt">
          <KeyRound size={11} /> {multiline ? 'Private key entered' : 'Credential entered'} ·{' '}
          {revealed ? 'Visible' : material.length > 12 ? 'Middle hidden' : 'Hidden'}
        </small>
      )}
    </div>
  );
}

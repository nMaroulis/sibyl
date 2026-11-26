import { CircleHelp } from 'lucide-react';
import { useId, useState, type ReactNode } from 'react';

/** A single disclosure for the explanation of one strategy control. */
export function StrategyHelp({ label, caption }: { label: string; caption?: string }) {
  const [open, setOpen] = useState(false);
  const id = useId();
  if (!caption) return null;
  return (
    <div className="strategy-field-help">
      <button
        type="button"
        aria-label={'Help for ' + label}
        aria-expanded={open}
        aria-controls={open ? id : undefined}
        onClick={() => setOpen(!open)}
      >
        <CircleHelp size={14} aria-hidden="true" />
      </button>
      {open && <small id={id}>{caption}</small>}
    </div>
  );
}

/** Keep input validation visible and field explanations opt-in. */
export function StrategyField({
  label,
  caption,
  children,
}: {
  label: string;
  caption?: string;
  children: ReactNode;
}) {
  return (
    <div className="strategy-field">
      <label>
        <span>{label}</span>
        {children}
      </label>
      <StrategyHelp label={label} caption={caption} />
    </div>
  );
}

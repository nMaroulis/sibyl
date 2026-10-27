import { useId, useRef, useState } from 'react';
import type { ReactNode } from 'react';
import { ChevronDown, ChevronUp } from 'lucide-react';

/** Keep long account sections compact without changing totals, filters or exports. */
export function ExpandableRows({
  total,
  label,
  children,
}: {
  total: number;
  label: string;
  children: (visible: number) => ReactNode;
}) {
  const [limit, setLimit] = useState(10);
  const id = useId();
  const more = useRef<HTMLButtonElement>(null);
  const visible = Math.min(total, limit);
  const collapse = () => {
    setLimit(10);
    requestAnimationFrame(() => {
      more.current?.focus({ preventScroll: true });
      more.current?.scrollIntoView({
        block: 'nearest',
        behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth',
      });
    });
  };
  return (
    <div className="expandable-rows" role="group" aria-label={label}>
      <div id={id}>{children(visible)}</div>
      {total > 10 && (
        <div className="expandable-row-controls">
          <small aria-live="polite">
            {visible} of {total} {label}
          </small>
          <button
            ref={more}
            className="reveal-more"
            aria-controls={id}
            aria-expanded={limit > 10}
            onClick={() => (visible < total ? setLimit((value) => value + 10) : collapse())}
          >
            {visible < total ? <ChevronDown size={14} /> : <ChevronUp size={14} />}
            {visible < total ? `Show ${Math.min(10, total - visible)} more` : 'Show less'}
          </button>
          {limit > 10 && visible < total && (
            <button className="reveal-less" aria-controls={id} onClick={collapse}>
              <ChevronUp size={13} /> Show less
            </button>
          )}
        </div>
      )}
    </div>
  );
}

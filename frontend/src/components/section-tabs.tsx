import { useLayoutEffect, useRef } from 'react';
import type { ReactNode } from 'react';
import type { LucideIcon } from 'lucide-react';

export type SectionTab = { id: string; label: string; icon: LucideIcon; detail?: string };

/** A horizontal counterpart to the floating navigation dock, with keyboard tab selection. */
export function SectionTabs({
  id,
  label,
  items,
  value,
  onChange,
  compact = false,
}: {
  id: string;
  label: string;
  items: SectionTab[];
  value: string;
  onChange: (value: string) => void;
  compact?: boolean;
}) {
  const rail = useRef<HTMLDivElement>(null);
  useLayoutEffect(() => {
    const element = rail.current;
    if (!element) return;
    const measure = () => {
      const active = element.querySelector<HTMLElement>('[aria-selected="true"]');
      if (!active) return;
      element.style.setProperty('--section-x', `${active.offsetLeft}px`);
      element.style.setProperty('--section-width', `${active.offsetWidth}px`);
      element.dataset.ready = 'true';
    };
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(element);
    for (const button of element.querySelectorAll('button')) observer.observe(button);
    return () => observer.disconnect();
  }, [value, items]);
  return (
    <div className={`section-tabs-wrap ${compact ? 'section-tabs-compact' : ''}`}>
      <div className="section-tabs" ref={rail} role="tablist" aria-label={label}>
        <span className="section-selection" aria-hidden="true" />
        {items.map((item, index) => (
          <button
            key={item.id}
            id={`${id}-tab-${item.id}`}
            role="tab"
            type="button"
            aria-selected={value === item.id}
            aria-controls={`${id}-panel`}
            tabIndex={value === item.id ? 0 : -1}
            onClick={() => onChange(item.id)}
            onKeyDown={(event) => {
              const keys: Record<string, number> = {
                ArrowRight: (index + 1) % items.length,
                ArrowLeft: (index - 1 + items.length) % items.length,
                Home: 0,
                End: items.length - 1,
              };
              if (!(event.key in keys)) return;
              event.preventDefault();
              const next = keys[event.key];
              onChange(items[next].id);
              const button =
                rail.current?.querySelectorAll<HTMLButtonElement>('[role="tab"]')[next];
              button?.focus({ preventScroll: true });
              if (button && rail.current) {
                const container = rail.current;
                if (button.offsetLeft < container.scrollLeft)
                  container.scrollLeft = button.offsetLeft;
                else if (
                  button.offsetLeft + button.offsetWidth >
                  container.scrollLeft + container.clientWidth
                )
                  container.scrollLeft =
                    button.offsetLeft + button.offsetWidth - container.clientWidth;
              }
            }}
          >
            <item.icon size={16} />
            <span>{item.label}</span>
            {item.detail && <small>{item.detail}</small>}
          </button>
        ))}
      </div>
    </div>
  );
}

/** Reveal the selected section without scaling text or resetting preserved form state. */
export function SectionPanel({
  id,
  value,
  children,
  className = '',
}: {
  id: string;
  value: string;
  children: ReactNode;
  className?: string;
}) {
  const panel = useRef<HTMLDivElement>(null);
  useLayoutEffect(() => {
    const element = panel.current;
    if (!element || window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
    const animation = element.animate(
      [
        { opacity: 0.55, transform: 'translateY(6px)' },
        { opacity: 1, transform: 'translateY(0)' },
      ],
      { duration: 260, easing: 'cubic-bezier(.2,.8,.2,1)' },
    );
    return () => animation.cancel();
  }, [value]);
  return (
    <div
      className={`section-panel ${className}`}
      id={`${id}-panel`}
      role="tabpanel"
      aria-labelledby={`${id}-tab-${value}`}
      ref={panel}
    >
      {children}
    </div>
  );
}

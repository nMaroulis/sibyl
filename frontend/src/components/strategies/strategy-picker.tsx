import { useId, useLayoutEffect, useRef, useState } from 'react';
import {
  Activity,
  ChartNoAxesCombined,
  Check,
  ChevronDown,
  Gauge,
  Layers3,
  MoveUpRight,
  Waves,
} from 'lucide-react';
import type { Strategy } from '../../lib/types';

const icons = {
  ema: ChartNoAxesCombined,
  rsi: Gauge,
  bollinger: Waves,
  'bollinger-surge': Layers3,
  'impulse-breakout': MoveUpRight,
  'quantum-momentum': Activity,
};

function algorithmIcon(id: string) {
  return icons[id as keyof typeof icons] ?? Activity;
}

/** Keep a single selection surface aligned to the checked radio as the layout changes. */
function useSelectionSurface(value: string, optionCount: number) {
  const grid = useRef<HTMLDivElement>(null);
  const surface = useRef<HTMLSpanElement>(null);
  useLayoutEffect(() => {
    const container = grid.current;
    const highlight = surface.current;
    if (!container || !highlight) return;

    const place = () => {
      const card = container.querySelector<HTMLInputElement>('input:checked')?.parentElement;
      highlight.hidden = !card;
      if (!card) return;
      highlight.style.width = card.offsetWidth + 'px';
      highlight.style.height = card.offsetHeight + 'px';
      highlight.style.transform = `translate(${card.offsetLeft}px, ${card.offsetTop}px)`;
    };

    place();
    const observer = new ResizeObserver(place);
    observer.observe(container);
    return () => observer.disconnect();
  }, [value, optionCount]);
  return { grid, surface };
}

/** Show all algorithms and reveal the full signal rules when the user wants to compare. */
export function StrategyPicker({
  strategies,
  value,
  onChange,
}: {
  strategies: Strategy[];
  value: string;
  onChange: (value: string) => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const id = useId();
  const { grid, surface } = useSelectionSurface(value, strategies.length);
  const selected = strategies.find((item) => item.id === value);
  const Icon = algorithmIcon(value);
  if (!strategies.length) return null;

  return (
    <fieldset className="strategy-picker">
      <legend className="sr-only">Strategy algorithm</legend>
      <div className="strategy-picker-stage" data-algorithm={selected?.id}>
        <div className="strategy-picker-grid" ref={grid}>
          <span className="strategy-picker-selection" ref={surface} aria-hidden="true" />
          {strategies.map((item) => {
            const Mark = algorithmIcon(item.id);
            return (
              <label className="strategy-picker-card" key={item.id}>
                <input
                  className="sr-only"
                  type="radio"
                  name="strategy-algorithm"
                  value={item.id}
                  aria-label={item.name}
                  aria-describedby={`${id}-${item.id}-tag`}
                  checked={item.id === value}
                  onChange={() => onChange(item.id)}
                />
                <span className="strategy-picker-icon">
                  <Mark size={17} aria-hidden="true" />
                </span>
                <span className="strategy-picker-copy">
                  <strong>{item.name}</strong>
                  <span id={`${id}-${item.id}-tag`}>{item.tag}</span>
                </span>
                <Check className="strategy-picker-check" size={15} aria-hidden="true" />
              </label>
            );
          })}
        </div>

        <section className="strategy-picker-preview" aria-labelledby={id + '-preview'}>
          <Icon className="strategy-preview-mark" size={142} strokeWidth={1} aria-hidden="true" />
          <div className="strategy-preview-copy" key={selected?.id}>
            <h3 id={id + '-preview'}>{selected?.name ?? 'Choose an algorithm'}</h3>
            {selected && <p>{selected.guide?.idea ?? selected.description}</p>}
          </div>
          <button
            className="strategy-compare-button"
            type="button"
            aria-expanded={expanded}
            aria-controls={id + '-comparison'}
            onClick={() => setExpanded(!expanded)}
          >
            {expanded ? 'Hide comparison' : 'Compare algorithms'}{' '}
            <ChevronDown size={14} aria-hidden="true" />
          </button>
        </section>
      </div>
      <div
        className="strategy-picker-comparison"
        id={id + '-comparison'}
        data-open={expanded}
        inert={!expanded}
      >
        <div>
          <ul className="strategy-comparison-grid">
            {strategies.map((item) => (
              <li key={item.id} data-selected={item.id === value}>
                <h3>{item.name}</h3>
                {item.guide ? (
                  <dl>
                    <dt>Entry</dt>
                    <dd>{item.guide.entry}</dd>
                    <dt>Exit</dt>
                    <dd>{item.guide.exit}</dd>
                    <dt>Trade-off</dt>
                    <dd>{item.guide.tradeoff}</dd>
                  </dl>
                ) : (
                  <p>{item.description}</p>
                )}
              </li>
            ))}
          </ul>
        </div>
      </div>
    </fieldset>
  );
}

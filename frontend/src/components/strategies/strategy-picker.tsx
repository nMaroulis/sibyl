import { useState } from 'react';
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

/** Select a built-in algorithm and optionally expand the catalog to read each description. */
export function StrategyPicker({
  strategies,
  value,
  onChange,
}: {
  strategies: Strategy[];
  value: string;
  onChange: (value: string) => void;
}) {
  const [details, setDetails] = useState(false);
  if (!strategies.length) return null;

  return (
    <fieldset className={'strategy-picker' + (details ? ' is-expanded' : '')}>
      <legend className="sr-only">Strategy algorithm</legend>
      <div className="strategy-picker-heading">
        <h2>Choose an algorithm</h2>
        <button
          className="button secondary tiny"
          type="button"
          aria-expanded={details}
          aria-controls="strategy-algorithms"
          onClick={() => setDetails(!details)}
        >
          {details ? 'Fewer details' : 'More details'} <ChevronDown size={14} aria-hidden="true" />
        </button>
      </div>
      <div className="strategy-picker-grid" id="strategy-algorithms">
        {strategies.map((item) => {
          const Icon = icons[item.id as keyof typeof icons] ?? Activity;
          const selected = item.id === value;
          return (
            <label className="strategy-picker-card" key={item.id}>
              <input
                className="sr-only"
                type="radio"
                name="strategy-algorithm"
                value={item.id}
                checked={selected}
                onChange={() => onChange(item.id)}
              />
              <span className="strategy-picker-icon">
                <Icon size={18} aria-hidden="true" />
              </span>
              <span className="strategy-picker-copy">
                <strong>{item.name}</strong>
                <small>{item.tag}</small>
                {details && <span>{item.description}</span>}
              </span>
              {selected && <Check className="strategy-picker-check" size={16} aria-hidden="true" />}
            </label>
          );
        })}
      </div>
    </fieldset>
  );
}

import { useId } from 'react';
import { FlaskConical, Play, ShieldCheck } from 'lucide-react';
import { Badge } from '../ui';
import type { StrategyAccount } from './strategy-account-picker';

const modes = [
  {
    id: 'deploy',
    label: 'Deploy strategy',
    icon: ShieldCheck,
    description: 'Review and approve before the strategy can place spot orders.',
  },
  {
    id: 'backtest',
    label: 'Backtest',
    icon: FlaskConical,
    description: 'Evaluate the strategy on historical candles with simulated funds.',
  },
  {
    id: 'paper',
    label: 'Paper strategy',
    icon: Play,
    description: 'Follow incoming prices with a virtual balance.',
  },
] as const;

export type StrategyRunMode = (typeof modes)[number]['id'];

/** Select a run mode and explain what it does next to its settings. */
export function StrategyRunPicker({
  value,
  account,
  onChange,
}: {
  value: StrategyRunMode;
  account?: StrategyAccount;
  onChange: (value: StrategyRunMode) => void;
}) {
  const fundsId = useId();
  const selected = modes.find((mode) => mode.id === value) ?? modes[1];
  const Icon = selected.icon;
  const funds = account?.supported
    ? account.sandbox
      ? { text: 'Test funds', tone: 'sand' }
      : { text: 'Capital at risk', tone: 'rose' }
    : { text: account ? 'Unsupported account' : 'Account required', tone: 'neutral' };

  return (
    <fieldset className="strategy-run-picker">
      <legend className="sr-only">Run mode</legend>
      <div className="strategy-run-glass" data-mode={value}>
        <span className="strategy-run-lens" aria-hidden="true" />
        {modes.map(({ id, label, icon: Mark }) => (
          <label className="strategy-run-option" key={id}>
            <input
              className="sr-only"
              type="radio"
              name="strategy-run-mode"
              value={id}
              aria-label={label}
              aria-describedby={id === 'deploy' ? fundsId : undefined}
              checked={id === value}
              onChange={() => onChange(id)}
            />
            <span className="strategy-run-label">
              <Mark size={15} aria-hidden="true" />
              <span>{label}</span>
            </span>
            {id === 'deploy' && (
              <span className="strategy-run-funds" id={fundsId}>
                <Badge tone={funds.tone}>{funds.text}</Badge>
              </span>
            )}
          </label>
        ))}
      </div>
      <p className="strategy-run-description">
        <Icon size={14} aria-hidden="true" />
        {selected.description}
      </p>
    </fieldset>
  );
}

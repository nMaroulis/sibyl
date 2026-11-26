import { FlaskConical, Play, ShieldCheck } from 'lucide-react';
import { Badge } from '../ui';
import type { StrategyAccount } from './strategy-account-picker';

const modes = [
  { id: 'deploy', label: 'Deploy strategy', icon: ShieldCheck },
  { id: 'backtest', label: 'Backtest', icon: FlaskConical },
  { id: 'paper', label: 'Paper strategy', icon: Play },
] as const;

export type StrategyRunMode = (typeof modes)[number]['id'];

/** Pick one launch mode without changing the strategy draft. */
export function StrategyRunPicker({
  value,
  account,
  onChange,
}: {
  value: StrategyRunMode;
  account?: StrategyAccount;
  onChange: (value: StrategyRunMode) => void;
}) {
  return (
    <fieldset className="strategy-run-picker">
      <legend className="sr-only">Run mode</legend>
      <div className="strategy-run-tray">
        {modes.map(({ id, label, icon: Icon }) => (
          <label className="strategy-run-option" key={id}>
            <input
              className="sr-only"
              type="radio"
              name="strategy-run-mode"
              value={id}
              checked={id === value}
              onChange={() => onChange(id)}
            />
            <span className="strategy-run-option-top">
              <Icon size={17} aria-hidden="true" />
              <span className="strategy-run-indicator" aria-hidden="true" />
            </span>
            <strong>{label}</strong>
            {id === 'deploy' ? (
              <Badge tone={!account?.supported ? 'neutral' : account.sandbox ? 'sand' : 'rose'}>
                {!account?.supported
                  ? account
                    ? 'Unsupported account'
                    : 'Account required'
                  : account.sandbox
                    ? 'Test funds'
                    : 'Capital at risk'}
              </Badge>
            ) : (
              <small aria-hidden="true">
                {id === 'backtest' ? 'Historical prices' : 'Virtual funds · live prices'}
              </small>
            )}
          </label>
        ))}
      </div>
    </fieldset>
  );
}

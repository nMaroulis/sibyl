import type { StrategyOrderLimits, StrategyParams } from '../../lib/types';
import { StrategyField } from './strategy-field';
import type { ParameterHelp } from './strategy-signal-settings';

const riskFields = [
  { key: 'stop_loss_pct', label: 'Stop loss', defaultMode: 'Off', maximum: 90, percent: true },
  {
    key: 'take_profit_pct',
    label: 'Take profit',
    defaultMode: 'Off',
    maximum: 1000,
    percent: true,
  },
  {
    key: 'max_trades',
    label: 'Completed exit limit',
    defaultMode: 'Auto',
    maximum: 10000,
    percent: false,
  },
] as const;

type RiskKey = (typeof riskFields)[number]['key'];

/** Restore the custom controls when loading a saved run with risk limits. */
export function hasCustomRiskSettings(params: StrategyParams): boolean {
  return riskFields.some(({ key }) => params[key] != null);
}

/** Blank rules use their defaults. Validate any value the user entered. */
export function hasInvalidRiskSettings(params: StrategyParams): boolean {
  return riskFields.some(({ key, maximum, percent }) => {
    const value = params[key];
    return (
      value != null &&
      (!Number.isFinite(value) ||
        value <= 0 ||
        value > maximum ||
        (!percent && !Number.isInteger(value)))
    );
  });
}

/** One place for shared sizing, loss guards and optional position exits. */
export function StrategyRiskSettings({
  params,
  quote,
  limits,
  onLimitsChange,
  enabled,
  onToggle,
  onValue,
  help,
}: {
  params: StrategyParams;
  quote: string;
  limits: StrategyOrderLimits;
  onLimitsChange: (limits: StrategyOrderLimits) => void;
  enabled: boolean;
  onToggle: (enabled: boolean) => void;
  onValue: (key: RiskKey, value: number | null) => void;
  help: ParameterHelp;
}) {
  return (
    <fieldset className="advanced-options strategy-risk-settings">
      <legend>Risk &amp; order limits</legend>
      <div className="form-row">
        <StrategyField label={'Maximum order value · ' + quote} caption={help.max_order_quote}>
          <input
            type="number"
            min={0}
            max={params.capital}
            step="any"
            value={limits.max_order_quote || ''}
            onChange={(event) =>
              onLimitsChange({ ...limits, max_order_quote: Number(event.currentTarget.value) })
            }
          />
          {(limits.max_order_quote <= 0 || limits.max_order_quote > params.capital) && (
            <small className="negative">Use a positive order cap at or below the amount.</small>
          )}
        </StrategyField>
        <StrategyField label="Pause at allocated loss · %" caption={help.max_loss_pct}>
          <input
            type="number"
            min={0}
            max={90}
            step="any"
            value={limits.max_loss_pct || ''}
            onChange={(event) =>
              onLimitsChange({ ...limits, max_loss_pct: Number(event.currentTarget.value) })
            }
          />
          {(limits.max_loss_pct <= 0 || limits.max_loss_pct > 90) && (
            <small className="negative">Enter a loss threshold above 0% and at most 90%.</small>
          )}
        </StrategyField>
      </div>
      <label className="interface-label-switch strategy-risk-switch">
        <span>Custom exits</span>
        <input
          type="checkbox"
          role="switch"
          checked={enabled}
          onChange={(event) => onToggle(event.currentTarget.checked)}
        />
      </label>
      {enabled && (
        <div className="strategy-risk-fields">
          {riskFields.map(({ key, label, defaultMode, maximum, percent }) => (
            <StrategyField key={key} label={percent ? label + ' · %' : label} caption={help[key]}>
              <input
                type="number"
                min={percent ? 0 : 1}
                max={maximum}
                step={percent ? 'any' : 1}
                placeholder={defaultMode}
                value={params[key] ?? ''}
                onChange={(event) => {
                  const { value, valueAsNumber } = event.currentTarget;
                  onValue(key, value === '' ? null : valueAsNumber);
                }}
              />
            </StrategyField>
          ))}
        </div>
      )}
    </fieldset>
  );
}

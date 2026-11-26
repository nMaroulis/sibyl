import type { Strategy, StrategyParams } from '../../lib/types';
import { StrategyField } from './strategy-field';

export type ParameterHelp = Partial<Record<string, string>>;

type Field = readonly [
  key: Exclude<keyof StrategyParams, 'backtest_limits'>,
  label: string,
  min: number,
  max: number,
  step?: 'any',
  optional?: boolean,
];
const indicators: Field[] = [
  ['window', 'Bollinger / CMF window', 5, 120],
  ['fast_period', 'Fast EMA', 2, 100],
  ['slow_period', 'Slow EMA', 3, 200],
  ['rsi_period', 'RSI period', 2, 100],
  ['rsi_lower', 'RSI buy threshold', 1, 49, 'any', true],
  ['rsi_upper', 'RSI sell threshold', 51, 99, 'any', true],
  ['band_std', 'Band deviations', 0.5, 5, 'any'],
  ['volume_multiplier', 'Volume multiplier', 0.5, 10, 'any'],
  ['macd_fast_period', 'MACD fast period', 2, 100],
  ['macd_slow_period', 'MACD slow period', 3, 200],
  ['macd_signal_period', 'MACD signal period', 2, 100],
  ['adx_period', 'ADX period', 2, 100],
  ['atr_period', 'ATR period', 2, 100],
  ['cmf_period', 'CMF period', 2, 120, undefined, true],
  ['tsi_short_period', 'TSI short period', 2, 100],
  ['tsi_long_period', 'TSI long period', 3, 200],
];
/** Show the signal parameters used by the selected algorithm. */
export function StrategySignalSettings({
  params,
  update,
  algorithm,
  help,
}: {
  params: StrategyParams;
  update: (key: keyof StrategyParams, value: number | string | null) => void;
  algorithm?: Strategy;
  help: ParameterHelp;
}) {
  const relevant = indicators.filter(
    ([key]) => !algorithm?.parameters || algorithm.parameters.includes(key),
  );
  const field = ([key, label, min, max, step, optional]: Field) => {
    const defaults =
      key === 'rsi_lower'
        ? params.strategy === 'impulse-breakout'
          ? '35'
          : '30'
        : key === 'rsi_upper'
          ? params.strategy === 'impulse-breakout'
            ? '65'
            : '70'
          : key === 'cmf_period'
            ? 'Use rolling window'
            : 'Optional';
    return (
      <StrategyField key={key} label={label} caption={help[key]}>
        <input
          type="number"
          min={min}
          max={max}
          step={step}
          value={params[key] ?? ''}
          placeholder={optional ? defaults : undefined}
          onChange={(event) =>
            update(key, optional && !event.target.value ? null : Number(event.target.value))
          }
        />
      </StrategyField>
    );
  };
  return (
    <details className="advanced-options strategy-signal-options">
      <summary>Advanced algorithm settings</summary>
      <div className="strategy-signal-fields">
        <div className="strategy-parameter-group">
          <h3>Signal indicators</h3>
          <div className="form-row">{relevant.map(field)}</div>
        </div>
      </div>
    </details>
  );
}

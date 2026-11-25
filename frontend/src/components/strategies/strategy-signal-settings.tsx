import type { StrategyParams } from '../../lib/types';

/** Shared indicator and signal-exit parameters for research and exchange runs. */
export function StrategySignalSettings({
  params,
  update,
  exchange = false,
}: {
  params: StrategyParams;
  update: (key: keyof StrategyParams, value: number | string | null) => void;
  exchange?: boolean;
}) {
  return (
    <details className="advanced-options strategy-signal-options">
      <summary>Algorithm settings</summary>
      <div className="strategy-signal-fields">
        <details className="advanced-options">
          <summary>Indicator parameters</summary>{' '}
          <label>
            Bollinger / CMF window
            <input
              type="number"
              min="5"
              max="120"
              value={params.window}
              onChange={(event) => update('window', Number(event.target.value))}
            />
          </label>
          <div className="form-row">
            {(['fast_period', 'slow_period', 'rsi_period'] as const).map((key) => (
              <label key={key}>
                {
                  {
                    fast_period: 'Fast EMA',
                    slow_period: 'Slow EMA',
                    rsi_period: 'RSI period',
                  }[key]
                }
                <input
                  type="number"
                  min={key === 'slow_period' ? 3 : 2}
                  max={key === 'slow_period' ? 200 : 100}
                  value={params[key]}
                  onChange={(e) => update(key, Number(e.target.value))}
                />
              </label>
            ))}
          </div>
          <div className="form-row">
            {(['rsi_lower', 'rsi_upper', 'band_std', 'volume_multiplier'] as const).map((key) => (
              <label key={key}>
                {
                  {
                    rsi_lower: 'RSI buy threshold',
                    rsi_upper: 'RSI sell threshold',
                    band_std: 'Band deviations',
                    volume_multiplier: 'Volume multiplier',
                  }[key]
                }
                <input
                  type="number"
                  step="any"
                  min={key === 'rsi_lower' ? 1 : key === 'rsi_upper' ? 51 : 0.5}
                  max={
                    key === 'rsi_lower'
                      ? 49
                      : key === 'rsi_upper'
                        ? 99
                        : key === 'band_std'
                          ? 5
                          : 10
                  }
                  placeholder={
                    key === 'rsi_lower'
                      ? params.strategy === 'impulse-breakout'
                        ? '35'
                        : '30'
                      : key === 'rsi_upper'
                        ? params.strategy === 'impulse-breakout'
                          ? '65'
                          : '70'
                        : ''
                  }
                  value={params[key] ?? ''}
                  onChange={(e) =>
                    update(key, e.target.value === '' ? null : Number(e.target.value))
                  }
                />
              </label>
            ))}
          </div>
          <p className="footnote">
            Only parameters used by the chosen algorithm affect its signals. Leave RSI thresholds
            blank for the algorithm defaults.
          </p>
        </details>
        <details className="advanced-options">
          <summary>MACD, ADX, ATR, CMF & TSI periods</summary>
          <div className="form-row">
            {(
              [
                'macd_fast_period',
                'macd_slow_period',
                'macd_signal_period',
                'adx_period',
                'atr_period',
                'cmf_period',
                'tsi_short_period',
                'tsi_long_period',
              ] as const
            ).map((key) => (
              <label key={key}>
                {
                  {
                    macd_fast_period: 'MACD fast',
                    macd_slow_period: 'MACD slow',
                    macd_signal_period: 'MACD signal',
                    adx_period: 'ADX period',
                    atr_period: 'ATR period',
                    cmf_period: 'CMF period',
                    tsi_short_period: 'TSI short',
                    tsi_long_period: 'TSI long',
                  }[key]
                }
                <input
                  type="number"
                  min={key === 'macd_slow_period' || key === 'tsi_long_period' ? 3 : 2}
                  max={
                    key === 'macd_slow_period' || key === 'tsi_long_period'
                      ? 200
                      : key === 'cmf_period'
                        ? 120
                        : 100
                  }
                  value={params[key] ?? ''}
                  placeholder={key === 'cmf_period' ? 'Use rolling window' : ''}
                  onChange={(e) =>
                    update(key, e.target.value === '' ? null : Number(e.target.value))
                  }
                />
              </label>
            ))}
          </div>
          <p className="footnote">
            These control the multi-factor strategies. Fast MACD and short TSI periods must be
            smaller than their slow / long periods. The sample must exceed every configured period.
          </p>
        </details>
        <details className="advanced-options">
          <summary>Risk exits & run limits</summary>
          <div className="form-row">
            {(['stop_loss_pct', 'take_profit_pct', 'max_trades'] as const).map((key) => (
              <label key={key}>
                {
                  {
                    stop_loss_pct: 'Stop loss · %',
                    take_profit_pct: 'Take profit · %',
                    max_trades: exchange ? 'Maximum exit orders' : 'Maximum round trips',
                  }[key]
                }
                <input
                  type="number"
                  step={key === 'max_trades' ? 1 : 'any'}
                  min={key === 'max_trades' ? 1 : 0.01}
                  max={key === 'stop_loss_pct' ? 90 : key === 'take_profit_pct' ? 1000 : 10000}
                  placeholder="No limit"
                  value={params[key] ?? ''}
                  onChange={(e) =>
                    update(key, e.target.value === '' ? null : Number(e.target.value))
                  }
                />
              </label>
            ))}
          </div>
          <p className="footnote">
            {exchange
              ? 'Risk exits use closed candles and submit reviewed price-capped limits.'
              : 'Risk exits use closed candles. Backtests fill at the next open, and paper runs use the next observed quote.'}
          </p>
        </details>
      </div>
    </details>
  );
}

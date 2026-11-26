import { candleBoundary, frameSeconds, utcInput } from '../../lib/market-history';
import type { Timeframe } from '../../lib/types';

export const minimumLookback = 60;
export const maximumLookback = 720;

export type BacktestDateRange = { start: string; end: string };

export function initialBacktestDates(timeframe: Timeframe, candles: number): BacktestDateRange {
  const end = candleBoundary(Date.now(), timeframe);
  return { start: utcInput(end - candles * frameSeconds[timeframe] * 1000), end: utcInput(end) };
}

export function backtestDatesStatus(range: BacktestDateRange, timeframe: Timeframe) {
  const start = Date.parse(range.start + 'Z');
  const end = Date.parse(range.end + 'Z');
  if (!Number.isFinite(start) || !Number.isFinite(end) || start >= end) {
    return { error: 'Enter an end time after the start.', count: 0 };
  }
  if (end > Date.now()) return { error: 'Choose an end time in the past.', count: 0 };
  const step = frameSeconds[timeframe] * 1000;
  const first = candleBoundary(start + step - 1, timeframe);
  const last = candleBoundary(end, timeframe);
  const count = Math.max(0, (last - first) / step);
  return {
    count,
    error:
      count < minimumLookback || count > maximumLookback
        ? `Choose dates with ${minimumLookback}–${maximumLookback} whole candles.`
        : '',
  };
}

/** Edit the exact UTC range used by a historical simulation. */
export function StrategyBacktestDates({
  range,
  timeframe,
  onChange,
}: {
  range: BacktestDateRange;
  timeframe: Timeframe;
  onChange: (range: BacktestDateRange) => void;
}) {
  const { count, error } = backtestDatesStatus(range, timeframe);
  return (
    <fieldset className="strategy-backtest-dates">
      <legend>Backtest dates · UTC</legend>
      <div className="form-row">
        <label>
          From
          <input
            type="datetime-local"
            value={range.start}
            max={range.end || utcInput(Date.now())}
            onChange={(event) => onChange({ ...range, start: event.currentTarget.value })}
          />
        </label>
        <label>
          Until
          <input
            type="datetime-local"
            value={range.end}
            min={range.start}
            max={utcInput(Date.now())}
            onChange={(event) => onChange({ ...range, end: event.currentTarget.value })}
          />
        </label>
      </div>
      <p className={error ? 'negative' : 'muted'} role="status">
        {count.toLocaleString()} whole candles · end time excluded.
        {error && ' ' + error}
      </p>
    </fieldset>
  );
}

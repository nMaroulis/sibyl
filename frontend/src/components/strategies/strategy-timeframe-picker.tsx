import { CalendarDays, Clock3, Timer } from 'lucide-react';
import type { Timeframe } from '../../lib/types';
import { SearchPicker } from '../search-picker';

const labels: Record<Timeframe, string> = {
  '1m': '1 minute',
  '5m': '5 minutes',
  '15m': '15 minutes',
  '30m': '30 minutes',
  '1h': '1 hour',
  '4h': '4 hours',
  '12h': '12 hours',
  '1d': '1 day',
  '1w': '1 week',
};

const groups = [
  { label: 'Minutes', suffix: 'm', icon: Timer },
  { label: 'Hours', suffix: 'h', icon: Clock3 },
  { label: 'Days & weeks', suffix: null, icon: CalendarDays },
] as const;

/** Select a candle interval offered by the active strategy feed. */
export function StrategyTimeframePicker({
  frames,
  value,
  onChange,
}: {
  frames: Timeframe[];
  value: Timeframe | '';
  onChange: (value: Timeframe) => void;
}) {
  return (
    <SearchPicker
      label="Timeframe"
      value={value}
      className="strategy-timeframe-picker"
      menuClassName="strategy-timeframe-menu"
      disabled={!frames.length}
      messages={{
        prompt: 'Choose a candle interval',
        empty: 'No matching intervals for this feed.',
      }}
      placeholder="Find an interval…"
      groups={groups.map(({ label, suffix, icon: Icon }) => ({
        label,
        options: frames
          .filter((frame) => (suffix ? frame.endsWith(suffix) : /[dw]$/.test(frame)))
          .map((frame) => ({
            value: frame,
            label: labels[frame],
            keywords: frame,
            icon: (
              <span className="strategy-timeframe-icon">
                <Icon size={16} aria-hidden="true" />
              </span>
            ),
            badge: <span className="picker-default-badge">{frame}</span>,
          })),
      }))}
      onChange={(next) => {
        const frame = frames.find((item) => item === next);
        if (frame) onChange(frame);
      }}
    />
  );
}

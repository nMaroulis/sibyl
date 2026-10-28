import {
  CartesianGrid,
  Line,
  LineChart,
  ReferenceDot,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import type { StrategyMonitorData } from '../lib/types';
import { number } from '../lib/api';

/** Plot only observed quotes and persisted decisions, preserving actual timestamps. */
export function StrategyChart({
  monitor,
  mode,
  showSkips,
  showSlippage,
}: {
  monitor: StrategyMonitorData;
  mode: 'price' | 'equity' | 'drawdown';
  showSkips: boolean;
  showSlippage: boolean;
}) {
  const rows = monitor.observations;
  let peak = rows[0]?.equity ?? 0;
  const points = rows.map((row) => {
    peak = Math.max(peak, row.equity);
    return {
      time: Date.parse(row.timestamp),
      value:
        mode === 'price'
          ? row.price
          : mode === 'equity'
            ? row.equity
            : peak > 0
              ? (row.equity / peak - 1) * 100
              : 0,
    };
  });
  const markers = monitor.markers.filter(
    (row) => row.fill_price != null || (showSkips && row.action.startsWith('SKIP_')),
  );
  if (!rows.length)
    return (
      <div className="chart-empty monitor-chart-empty">
        <strong>Waiting for the first observation</strong>
        <span>
          The next successful worker check will add real price and equity samples. Earlier prices
          are not reconstructed.
        </span>
      </div>
    );
  const dates = points.map((row) => row.time);
  if (mode === 'price') markers.forEach((row) => dates.push(Date.parse(row.timestamp)));
  const min = Math.min(...dates),
    max = Math.max(...dates);
  const day = max - min > 172800000;
  const timeLabel = (value: number) =>
    new Date(value).toLocaleString(
      [],
      day
        ? { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }
        : { hour: '2-digit', minute: '2-digit', second: '2-digit' },
    );
  return (
    <div
      className="strategy-live-chart"
      role="img"
      aria-label={`${mode} chart for this strategy, ${rows.length} observed samples`}
    >
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={points} margin={{ top: 30, right: 12, left: 4, bottom: 10 }}>
          <CartesianGrid vertical={false} stroke="var(--chart-grid)" strokeDasharray="3 5" />
          <XAxis
            dataKey="time"
            type="number"
            domain={[min - 1000, max === min ? max + 1000 : max + 1000]}
            tickFormatter={timeLabel}
            minTickGap={55}
            tick={{ fontSize: 10, fill: 'var(--muted)' }}
            axisLine={false}
            tickLine={false}
          />
          <YAxis
            orientation="right"
            domain={['auto', 'auto']}
            width={85}
            tickFormatter={(v) =>
              `${number(Number(v), Number(v) < 1 ? 6 : 2)}${mode === 'drawdown' ? '%' : ''}`
            }
            tick={{ fontSize: 10, fill: 'var(--muted)' }}
            axisLine={false}
            tickLine={false}
          />
          <Tooltip
            labelFormatter={(v) => new Date(Number(v)).toLocaleString()}
            formatter={(v) => [
              number(Number(v), 6),
              mode === 'drawdown'
                ? 'Drawdown (%)'
                : mode === 'price'
                  ? 'Observed price'
                  : 'Paper equity',
            ]}
            contentStyle={{ borderRadius: 12, border: '1px solid var(--border)', fontSize: 12 }}
          />
          <Line
            dataKey="value"
            name={mode}
            stroke={mode === 'drawdown' ? '#c07888' : '#6688c8'}
            strokeWidth={2}
            dot={points.length === 1 ? { r: 4 } : false}
            activeDot={{ r: 4 }}
            isAnimationActive={false}
            type="linear"
          />
          {mode === 'price' &&
            markers.map((event) => {
              const skipped = event.action.startsWith('SKIP_');
              const buy = event.action.endsWith('BUY');
              const color = skipped ? '#9ca4b4' : buy ? '#3d947c' : '#cc7885';
              const price = event.fill_price ?? event.reference_price;
              if (price == null) return null;
              const time = Date.parse(event.timestamp);
              return (
                <g key={event.id}>
                  {showSlippage && !skipped && event.reference_price != null && (
                    <>
                      <ReferenceLine
                        segment={[
                          { x: time, y: event.reference_price },
                          { x: time, y: price },
                        ]}
                        stroke="#b399c9"
                        strokeWidth={2}
                        ifOverflow="extendDomain"
                      />
                      <ReferenceDot
                        x={time}
                        y={event.reference_price}
                        r={3}
                        fill="white"
                        stroke="#a28ab9"
                        ifOverflow="extendDomain"
                      />
                    </>
                  )}
                  <ReferenceDot
                    x={time}
                    y={price}
                    r={5}
                    fill={skipped ? 'white' : color}
                    stroke={color}
                    strokeWidth={2}
                    ifOverflow="extendDomain"
                    label={{
                      value: skipped ? 'skip' : buy ? 'BUY' : 'SELL',
                      position: buy ? 'bottom' : 'top',
                      fill: color,
                      fontSize: 10,
                    }}
                  />
                </g>
              );
            })}
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

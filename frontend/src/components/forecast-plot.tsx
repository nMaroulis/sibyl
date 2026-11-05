import {
  Area,
  CartesianGrid,
  ComposedChart,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { number, shortDate } from '../lib/api';
import type { ForecastChartPoint } from '../lib/forecast-types';

/** Plot bounded view samples; server metrics always use the full held-out selection. */
export function ForecastPlot({
  points,
  testing = false,
  showDrift = false,
}: {
  points: ForecastChartPoint[];
  testing?: boolean;
  showDrift?: boolean;
}) {
  const stride = Math.max(1, Math.ceil((points.length - 1) / 399));
  const plotted = points
    .filter((_, index) => index % stride === 0 || index === points.length - 1)
    .map((p) => ({
      ...p,
      prediction: p.predicted ?? p.value,
      interval: p.lower == null ? undefined : [p.lower, p.upper],
    }));
  return (
    <div
      className="forecast-chart"
      role="img"
      aria-label={
        testing
          ? 'Held-out actual and predicted daily prices with naive benchmark'
          : 'Observed prices and trained forecast with empirical bands'
      }
    >
      <ResponsiveContainer width="100%" height="100%">
        <ComposedChart data={plotted} margin={{ top: 15, right: 12, bottom: 8, left: 8 }}>
          <CartesianGrid stroke="var(--chart-grid)" vertical={false} strokeDasharray="3 5" />
          <XAxis
            dataKey="timestamp"
            tickFormatter={shortDate}
            minTickGap={65}
            tick={{ fontSize: 10, fill: 'var(--muted)' }}
            axisLine={false}
            tickLine={false}
          />
          <YAxis
            domain={['auto', 'auto']}
            orientation="right"
            width={85}
            tickFormatter={(v) => number(Number(v), 2)}
            tick={{ fontSize: 10, fill: 'var(--muted)' }}
            axisLine={false}
            tickLine={false}
          />
          <Tooltip
            labelFormatter={(v) => shortDate(String(v))}
            contentStyle={{ borderRadius: 12, border: '1px solid var(--border)' }}
            formatter={(v) =>
              Array.isArray(v)
                ? v.map((x) => number(Number(x), 4)).join(' – ')
                : number(Number(v), 4)
            }
          />
          <Area
            type="linear"
            dataKey="interval"
            name="Nominal 90% empirical band"
            fill="#809ce7"
            fillOpacity={0.14}
            stroke="none"
            isAnimationActive={false}
          />
          <Line
            dataKey="actual"
            name="Observed close"
            stroke="#516480"
            strokeWidth={1.8}
            dot={false}
            isAnimationActive={false}
          />
          <Line
            dataKey="prediction"
            name="Trained model"
            stroke="#607fda"
            strokeWidth={2}
            dot={false}
            isAnimationActive={false}
          />
          {testing && (
            <Line
              dataKey="naive"
              name="Naive last-close benchmark"
              stroke="#bf9872"
              strokeDasharray="4 4"
              dot={false}
              isAnimationActive={false}
            />
          )}
          {showDrift && (
            <Line
              type="linear"
              dataKey="drift"
              name="Training-drift benchmark"
              stroke="#77a699"
              strokeDasharray="3 3"
              dot={false}
              isAnimationActive={false}
            />
          )}
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}

import { useId, useMemo } from 'react';
import {
  Area,
  AreaChart,
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { money, number, shortDate } from '../lib/api';

const tooltip = {
  background: 'var(--surface-raised)',
  border: '1px solid var(--border)',
  borderRadius: 10,
  color: 'var(--text)',
  fontSize: 12,
};

export function ValueChart({
  data,
  color = '#4675d2',
  height = 250,
  currency = true,
  unit,
}: {
  data: { timestamp: string; value: number }[];
  color?: string;
  height?: number;
  currency?: boolean;
  unit?: string;
}) {
  const id = useId().replaceAll(':', '');
  // Keep each bucket's extrema and the endpoints; calculations/exports retain full data.
  const plotted = useMemo(() => {
    if (data.length <= 1200) return data;
    const chosen = new Set([0, data.length - 1]);
    const width = Math.ceil(data.length / 500);
    for (let start = 0; start < data.length; start += width) {
      let low = start,
        high = start;
      for (let i = start + 1; i < Math.min(data.length, start + width); i++) {
        if (data[i].value < data[low].value) low = i;
        if (data[i].value > data[high].value) high = i;
      }
      chosen.add(low);
      chosen.add(high);
    }
    return [...chosen].sort((a, b) => a - b).map((i) => data[i]);
  }, [data]);
  const intraday =
    data.length > 1 &&
    new Date(data[data.length - 1].timestamp).getTime() - new Date(data[0].timestamp).getTime() <
      172800000;
  const labelDate = (value: string) =>
    intraday
      ? new Date(value).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
      : shortDate(value);
  if (!data.length)
    return (
      <div className="chart-empty" style={{ height }}>
        History will appear as observations are collected.
      </div>
    );
  return (
    <div className="value-chart" style={{ height }}>
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={plotted} margin={{ top: 20, right: 10, bottom: 0, left: 5 }}>
          <defs>
            <linearGradient id={id} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={color} stopOpacity={0.22} />
              <stop offset="100%" stopColor={color} stopOpacity={0} />
            </linearGradient>
          </defs>
          <CartesianGrid vertical={false} stroke="var(--chart-grid)" strokeDasharray="3 5" />
          <XAxis
            dataKey="timestamp"
            tickFormatter={labelDate}
            axisLine={false}
            tickLine={false}
            minTickGap={45}
            tick={{ fill: 'var(--muted)', fontSize: 10 }}
            dy={10}
          />
          <YAxis
            orientation="right"
            domain={['auto', 'auto']}
            tickFormatter={(value) =>
              unit
                ? Number(value) >= 1000
                  ? `${(Number(value) / 1000).toFixed(1)}k`
                  : number(Number(value))
                : currency
                  ? Number(value) >= 1000
                    ? `$${(Number(value) / 1000).toFixed(1)}k`
                    : money(Number(value), 2)
                  : Number(value).toFixed(0)
            }
            axisLine={false}
            tickLine={false}
            tick={{ fill: 'var(--muted)', fontSize: 10 }}
            width={54}
          />
          <Tooltip
            contentStyle={tooltip}
            labelFormatter={(value) => labelDate(String(value))}
            formatter={(value) => [
              unit
                ? `${number(Number(value))} ${unit}`
                : currency
                  ? money(Number(value))
                  : Number(value).toFixed(2),
              'Value',
            ]}
          />
          <Area
            type="monotone"
            dataKey="value"
            stroke={color}
            strokeWidth={2}
            fill={`url(#${id})`}
            isAnimationActive={false}
          />
        </AreaChart>
      </ResponsiveContainer>
      {plotted.length < data.length && (
        <small className="chart-sampling-note">
          Display sampled to {plotted.length.toLocaleString()} points, preserving bucket extrema.
          Metrics and exports use all {data.length.toLocaleString()} observations.
        </small>
      )}
    </div>
  );
}

export function Sparkline({
  data,
  color = '#4675d2',
  width = 100,
}: {
  data: number[];
  color?: string;
  width?: number;
}) {
  return (
    <div style={{ width, height: 32 }} aria-hidden="true">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data.map((value) => ({ value }))}>
          <Line
            type="monotone"
            dataKey="value"
            stroke={color}
            strokeWidth={1.6}
            dot={false}
            isAnimationActive={false}
          />
          <YAxis hide domain={['auto', 'auto']} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

export function IndicatorChart({
  data,
  bands,
}: {
  data: Record<string, unknown>[];
  bands: boolean;
}) {
  return (
    <div className="indicator-chart">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data} margin={{ top: 15, right: 12, left: 4, bottom: 0 }}>
          <CartesianGrid vertical={false} stroke="var(--chart-grid)" strokeDasharray="3 5" />
          <XAxis
            dataKey="timestamp"
            tickFormatter={shortDate}
            minTickGap={60}
            tick={{ fill: 'var(--muted)', fontSize: 10 }}
            axisLine={false}
            tickLine={false}
          />
          <YAxis
            domain={['auto', 'auto']}
            orientation="right"
            width={65}
            tickFormatter={(value) => number(Number(value), Number(value) < 1 ? 6 : 2)}
            tick={{ fill: 'var(--muted)', fontSize: 10 }}
            axisLine={false}
            tickLine={false}
          />
          <Tooltip
            contentStyle={tooltip}
            formatter={(value) => number(Number(value), Number(value) < 1 ? 6 : 2)}
            labelFormatter={(value) => shortDate(String(value))}
          />
          <Line
            type="monotone"
            dataKey="close"
            name="Price"
            stroke="#4675d2"
            dot={false}
            strokeWidth={2}
          />
          {bands && (
            <>
              <Line
                dataKey="upper"
                name="Upper band"
                stroke="#d5a568"
                dot={false}
                strokeDasharray="3 4"
              />
              <Line
                dataKey="lower"
                name="Lower band"
                stroke="#d5a568"
                dot={false}
                strokeDasharray="3 4"
              />
              <Line dataKey="ema_fast" name="EMA 9" stroke="#70a697" dot={false} strokeWidth={1} />
            </>
          )}
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

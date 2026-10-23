import { useState } from 'react';
import {
  Brush,
  CartesianGrid,
  Line,
  LineChart,
  ReferenceDot,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import type { Backtest } from '../../lib/types';
import { number } from '../../lib/api';

/** Inspect exact historical prices and executions; no smoothing between trade markers. */
export function BacktestChart({ result, comparison }: { result: Backtest; comparison?: Backtest }) {
  const [mode, setMode] = useState<'price' | 'equity' | 'drawdown'>(
    result.price_series ? 'price' : 'equity',
  );
  const [selected, setSelected] = useState<number | null>(null);
  const equity = new Map(result.curve.map((p) => [p.timestamp, p.value]));
  const benchmark = new Map(result.benchmark_curve?.map((p) => [p.timestamp, p.value]) ?? []);
  const compared = new Map(comparison?.curve.map((p) => [p.timestamp, p.value]) ?? []);
  const drawdown = new Map(
    result.curve.map((p, i) => [p.timestamp, result.metrics?.drawdown_curve[i + 1] ?? 0]),
  );
  const points = (
    result.price_series ?? result.curve.map((p) => ({ timestamp: p.timestamp, close: p.value }))
  ).map((p) => ({
    time: Date.parse(p.timestamp),
    value:
      mode === 'price'
        ? p.close
        : mode === 'equity'
          ? equity.get(p.timestamp)
          : drawdown.get(p.timestamp),
    benchmark: mode === 'equity' ? benchmark.get(p.timestamp) : undefined,
    comparison: mode === 'equity' ? compared.get(p.timestamp) : undefined,
  }));
  const quote = result.symbol.split('/')[1];
  const [range, setRange] = useState({ startIndex: 0, endIndex: Math.max(0, points.length - 1) });
  const visibleFills = result.fills
    .map((f, index) => ({ ...f, index }))
    .filter(
      (f) =>
        Date.parse(f.timestamp) >= (points[range.startIndex]?.time ?? 0) &&
        Date.parse(f.timestamp) <= (points[range.endIndex]?.time ?? Infinity),
    );
  const fill = selected == null ? undefined : result.fills[selected];
  return (
    <div className="backtest-chart-workspace">
      <div className="backtest-chart-toolbar" role="group" aria-label="Backtest chart mode">
        {(['price', 'equity', 'drawdown'] as const).map((m) => (
          <button
            key={m}
            type="button"
            className={`button tiny ${mode === m ? 'secondary' : 'ghost'}`}
            disabled={m === 'price' && !result.price_series}
            aria-pressed={mode === m}
            onClick={() => setMode(m)}
          >
            {m === 'price' ? 'Price & trades' : m === 'equity' ? 'Equity & benchmark' : 'Drawdown'}
          </button>
        ))}
        <span className="footnote">
          {mode === 'price'
            ? 'Green buys · coral sells · click a trade'
            : mode === 'equity'
              ? 'Blue strategy · dashed buy & hold'
              : 'Decline from the equity peak'}
        </span>
      </div>
      <div
        className="backtest-execution-chart"
        role="group"
        aria-label={`${mode} chart with ${result.fills.length} historical executions`}
      >
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={points} margin={{ top: 28, right: 12, left: 2, bottom: 5 }}>
            <CartesianGrid vertical={false} stroke="var(--chart-grid)" strokeDasharray="3 5" />
            <XAxis
              dataKey="time"
              type="number"
              domain={['dataMin', 'dataMax']}
              tickFormatter={(v) =>
                new Date(v).toLocaleDateString([], { month: 'short', day: 'numeric' })
              }
              minTickGap={50}
              tick={{ fontSize: 10, fill: 'var(--muted)' }}
              axisLine={false}
              tickLine={false}
            />
            <YAxis
              orientation="right"
              domain={['auto', 'auto']}
              width={72}
              tickFormatter={(v) => number(v, Math.abs(v) < 1 ? 5 : 2)}
              tick={{ fontSize: 10, fill: 'var(--muted)' }}
              axisLine={false}
              tickLine={false}
            />
            <Tooltip
              labelFormatter={(v) => new Date(Number(v)).toLocaleString()}
              formatter={(v, n) => [
                `${number(Number(v), 4)} ${mode === 'drawdown' ? '%' : quote}`,
                n === 'value' ? 'Strategy' : n,
              ]}
              contentStyle={{ borderRadius: 12, border: '1px solid var(--border)', fontSize: 12 }}
            />
            <Line
              dataKey="value"
              stroke={mode === 'drawdown' ? '#be7485' : '#547bd1'}
              dot={false}
              activeDot={false}
              strokeWidth={2}
              isAnimationActive={false}
              type="linear"
              connectNulls={false}
            />
            {mode === 'equity' && (
              <Line
                dataKey="benchmark"
                name="Buy & hold"
                stroke="#b3a285"
                strokeDasharray="5 5"
                dot={false}
                isAnimationActive={false}
              />
            )}
            {mode === 'equity' && comparison && (
              <Line
                dataKey="comparison"
                name="Comparison"
                stroke="#a389c9"
                dot={false}
                isAnimationActive={false}
              />
            )}
            {mode === 'price' &&
              visibleFills
                .filter(
                  (_, i) =>
                    visibleFills.length <= 400 || i % Math.ceil(visibleFills.length / 400) === 0,
                )
                .map((f) => (
                  <ReferenceDot
                    key={f.index}
                    x={Date.parse(f.timestamp)}
                    y={f.price}
                    r={selected === f.index ? 7 : 4}
                    fill={f.side === 'buy' ? '#38967b' : '#ce7b88'}
                    stroke="white"
                    strokeWidth={2}
                    ifOverflow="extendDomain"
                    shape={({ cx, cy }) => (
                      <g
                        role="button"
                        tabIndex={0}
                        aria-label={`Inspect ${f.side} execution ${f.index + 1}`}
                        onClick={() => setSelected(f.index)}
                        onKeyDown={(event) => {
                          if (event.key === 'Enter' || event.key === ' ') {
                            event.preventDefault();
                            setSelected(f.index);
                          }
                        }}
                        style={{ cursor: 'pointer' }}
                      >
                        <circle cx={cx} cy={cy} r={12} fill="transparent" />
                        <circle
                          cx={cx}
                          cy={cy}
                          r={selected === f.index ? 7 : 4}
                          fill={f.side === 'buy' ? '#38967b' : '#ce7b88'}
                          stroke="white"
                          strokeWidth={2}
                        />
                      </g>
                    )}
                  />
                ))}
            <Brush
              onChange={(value) => {
                if (value.startIndex != null && value.endIndex != null)
                  setRange({ startIndex: value.startIndex, endIndex: value.endIndex });
              }}
              dataKey="time"
              height={20}
              stroke="var(--border)"
              tickFormatter={(v) =>
                new Date(v).toLocaleDateString([], { month: 'short', day: 'numeric' })
              }
              travellerWidth={7}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
      {fill && (
        <div className="backtest-selected-fill">
          <strong className={fill.side === 'buy' ? 'positive' : 'negative'}>
            {fill.side.toUpperCase()}
          </strong>
          <span>{new Date(fill.timestamp).toLocaleString()}</span>
          <span>
            {number(fill.quantity, 8)} at {number(fill.price, 6)} {quote}
          </span>
          <span>
            Fee {number(fill.fee ?? 0, 6)} {quote}
          </span>
          <span>{fill.reason ?? 'Strategy entry signal'}</span>
        </div>
      )}
      {result.fills.length > 400 && (
        <p className="footnote padded">
          Markers are sampled to at most 400 for a responsive chart. The trade table and exports
          retain every execution.
        </p>
      )}
      {!result.price_series && (
        <p className="footnote padded">
          This older run has no retained price trace. Rerun its saved input to generate trade
          overlays.
        </p>
      )}
    </div>
  );
}

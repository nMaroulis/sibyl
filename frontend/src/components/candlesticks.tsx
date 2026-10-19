import { useState } from 'react';
import type { Candle } from '../lib/types';
import { number } from '../lib/api';

/** Scalable OHLC chart with pointer and keyboard inspection of every closed candle. */
export function Candlesticks({ data, bands }: { data: Candle[]; bands: boolean }) {
  const [index, setIndex] = useState<number>();
  if (!data.length) return <div className="chart-empty">No closed candles available.</div>;
  const width = 1000,
    height = 330,
    left = 14,
    right = 84,
    top = 18,
    bottom = 30;
  const max = Math.max(
    ...data.map((row) => Math.max(row.high, bands ? (row.upper ?? row.high) : row.high)),
  );
  const min = Math.min(
    ...data.map((row) => Math.min(row.low, bands ? (row.lower ?? row.low) : row.low)),
  );
  const range = max - min || max * 0.01 || 1;
  const y = (v: number) => top + ((max - v) / range) * (height - top - bottom);
  const step = (width - left - right) / data.length;
  const x = (i: number) => left + (i + 0.5) * step;
  const selected = index === undefined ? data.length - 1 : Math.min(index, data.length - 1);
  const candle = data[selected];
  const path = (key: 'upper' | 'lower' | 'ema_fast') =>
    data
      .map((row, i) =>
        row[key] === null
          ? ''
          : `${i === 0 || data[i - 1][key] === null ? 'M' : 'L'}${x(i)},${y(row[key]!)}`,
      )
      .join(' ');
  return (
    <div className="candle-chart">
      <div className="ohlc-readout">
        <time>{new Date(candle.timestamp).toLocaleString()}</time>
        {(['open', 'high', 'low', 'close'] as const).map((key) => (
          <span key={key}>
            {key[0].toUpperCase()} <b>{number(candle[key], candle[key] < 1 ? 6 : 2)}</b>
          </span>
        ))}
        <span>
          Vol <b>{number(candle.volume)}</b>
        </span>
      </div>
      <svg
        viewBox={`0 0 ${width} ${height}`}
        role="img"
        aria-label={`OHLC candlestick chart, ${data.length} closed candles`}
        onPointerMove={(e) => {
          const rect = e.currentTarget.getBoundingClientRect();
          setIndex(
            Math.max(
              0,
              Math.min(
                data.length - 1,
                Math.floor((((e.clientX - rect.left) / rect.width) * width - left) / step),
              ),
            ),
          );
        }}
      >
        {Array.from({ length: 5 }, (_, i) => {
          const value = min + (range * i) / 4;
          return (
            <g key={i}>
              <line
                x1={left}
                x2={width - right}
                y1={y(value)}
                y2={y(value)}
                stroke="var(--chart-grid)"
                strokeDasharray="3 5"
              />
              <text x={width - right + 12} y={y(value) + 4} fill="var(--muted)" fontSize="11">
                {number(value, value < 1 ? 6 : 2)}
              </text>
            </g>
          );
        })}
        {data.map((row, i) => {
          const color = row.close >= row.open ? '#4b9b89' : '#cf7d88';
          return (
            <g key={row.timestamp}>
              <line
                x1={x(i)}
                x2={x(i)}
                y1={y(row.high)}
                y2={y(row.low)}
                stroke={color}
                strokeWidth={Math.max(0.6, Math.min(1.2, step / 2))}
              />
              <rect
                x={x(i) - step * 0.3}
                y={Math.min(y(row.open), y(row.close))}
                width={Math.max(0.6, step * 0.6)}
                height={Math.max(0.7, Math.abs(y(row.open) - y(row.close)))}
                rx=".5"
                fill={color}
              />
            </g>
          );
        })}
        {bands && (
          <>
            <path d={path('upper')} fill="none" stroke="#c49b60" strokeWidth="1" />
            <path d={path('lower')} fill="none" stroke="#c49b60" strokeWidth="1" />
            <path d={path('ema_fast')} fill="none" stroke="#7489c3" strokeWidth="1.5" />
          </>
        )}
        <line
          x1={x(selected)}
          x2={x(selected)}
          y1={top}
          y2={height - bottom}
          stroke="var(--muted)"
          strokeDasharray="3 4"
          opacity=".5"
        />
        {[0, Math.floor(data.length / 2), data.length - 1].map((i) => (
          <text
            key={i}
            x={x(i)}
            y={height - 8}
            textAnchor={i === 0 ? 'start' : i === data.length - 1 ? 'end' : 'middle'}
            fill="var(--muted)"
            fontSize="11"
          >
            {new Date(data[i].timestamp).toLocaleString(undefined, {
              month: 'short',
              day: 'numeric',
              hour: '2-digit',
              minute: '2-digit',
            })}
          </text>
        ))}
      </svg>
      <label className="candle-scrubber">
        Inspect candle
        <input
          type="range"
          min="0"
          max={data.length - 1}
          value={selected}
          onChange={(e) => setIndex(Number(e.target.value))}
          aria-label="Inspect candle"
        />
      </label>
    </div>
  );
}

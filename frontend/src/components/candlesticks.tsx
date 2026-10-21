import { memo, useEffect, useId, useMemo, useRef, useState } from 'react';
import { Download, RotateCcw, ChartColumn, ZoomIn, ZoomOut } from 'lucide-react';
import type { Candle } from '../lib/types';
import { exportCSV, number } from '../lib/api';

export type ChartCandle = Pick<Candle, 'timestamp' | 'open' | 'high' | 'low' | 'close' | 'volume'> &
  Partial<Pick<Candle, 'upper' | 'lower' | 'ema_fast'>>;
const W = 1000,
  H = 360,
  L = 12,
  R = 86,
  T = 18,
  B = 32;
const date = (value: string) =>
  new Date(value).toLocaleString([], {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });

/** Memoized marks never rerender just because the inspection cursor moves. */
const Marks = memo(function Marks({
  data,
  bands,
  mode,
  volume,
  low,
  high,
  bottom,
  interval,
}: {
  data: ChartCandle[];
  bands: boolean;
  mode: string;
  volume: boolean;
  low: number;
  high: number;
  bottom: number;
  interval: number;
}) {
  const range = high - low,
    step = (W - L - R) / data.length;
  const x = (i: number) => L + (i + 0.5) * step,
    y = (v: number) => T + ((high - v) / range) * (bottom - T);
  const line = (field: 'close' | 'upper' | 'lower' | 'ema_fast') => {
    let started = false;
    return data
      .map((row, i) => {
        if (i && Date.parse(row.timestamp) - Date.parse(data[i - 1].timestamp) > interval * 1.5)
          started = false;
        const value = row[field];
        if (value == null || !Number.isFinite(value)) {
          started = false;
          return '';
        }
        const point = `${started ? 'L' : 'M'}${x(i).toFixed(2)},${y(value).toFixed(2)}`;
        started = true;
        return point;
      })
      .join(' ');
  };
  const vmax = Math.max(1, ...data.map((row) => row.volume));
  return (
    <g>
      {data.map((row, i) =>
        i > 0 && Date.parse(row.timestamp) - Date.parse(data[i - 1].timestamp) > interval * 1.5 ? (
          <line
            key={`gap-${row.timestamp}`}
            x1={x(i) - step / 2}
            x2={x(i) - step / 2}
            y1={T}
            y2={bottom}
            stroke="#c49b60"
            strokeDasharray="2 4"
          >
            <title>Missing candle intervals</title>
          </line>
        ) : null,
      )}
      {Array.from({ length: 5 }, (_, i) => {
        const value = low + (range * i) / 4;
        return (
          <g key={i}>
            <line
              x1={L}
              x2={W - R}
              y1={y(value)}
              y2={y(value)}
              stroke="var(--chart-grid)"
              strokeDasharray="3 5"
            />
            <text x={W - R + 10} y={y(value) + 4} fill="var(--muted)" fontSize="11">
              {number(value, value < 1 ? 8 : 2)}
            </text>
          </g>
        );
      })}
      {mode === 'candles' ? (
        data.map((row, i) => {
          const color = row.close >= row.open ? '#4b9b89' : '#cf7d88';
          return (
            <g key={row.timestamp}>
              <line
                x1={x(i)}
                x2={x(i)}
                y1={y(row.high)}
                y2={y(row.low)}
                stroke={color}
                strokeWidth={Math.max(0.7, Math.min(1.3, step / 2))}
              />
              <rect
                x={x(i) - step * 0.3}
                y={Math.min(y(row.open), y(row.close))}
                width={Math.max(0.65, step * 0.6)}
                height={Math.max(0.8, Math.abs(y(row.open) - y(row.close)))}
                rx=".5"
                fill={color}
              />
            </g>
          );
        })
      ) : (
        <path d={line('close')} fill="none" stroke="#4675d2" strokeWidth="2" />
      )}
      {bands && (
        <>
          <path d={line('upper')} fill="none" stroke="#c49b60" strokeWidth="1" opacity=".8" />
          <path d={line('lower')} fill="none" stroke="#c49b60" strokeWidth="1" opacity=".8" />
          <path d={line('ema_fast')} fill="none" stroke="#7489c3" strokeWidth="1.5" />
        </>
      )}
      {volume && (
        <g>
          <line x1={L} x2={W - R} y1={bottom + 10} y2={bottom + 10} stroke="var(--chart-grid)" />
          {data.map((row, i) => (
            <rect
              key={row.timestamp}
              x={x(i) - step * 0.3}
              y={H - B - (row.volume / vmax) * 38}
              width={Math.max(0.6, step * 0.6)}
              height={(row.volume / vmax) * 38}
              fill={row.close >= row.open ? '#4b9b8966' : '#cf7d8866'}
            />
          ))}
          <text x={W - R + 10} y={H - B - 12} fontSize="10" fill="var(--muted)">
            Volume
          </text>
        </g>
      )}
      {[...new Set([0, Math.floor(data.length / 2), data.length - 1])].map((i) => (
        <text
          key={i}
          x={x(i)}
          y={H - 9}
          textAnchor={i === 0 ? 'start' : i === data.length - 1 ? 'end' : 'middle'}
          fill="var(--muted)"
          fontSize="10"
        >
          {date(data[i].timestamp)}
        </text>
      ))}
    </g>
  );
});

/** Bounded SVG viewport: zoom/pan/inspect cached data without network calls or animation. */
export function Candlesticks({
  data,
  bands,
  mode = 'candles',
  intervalSeconds,
}: {
  data: ChartCandle[];
  bands: boolean;
  mode?: 'candles' | 'line';
  intervalSeconds?: number;
}) {
  const [count, setCount] = useState(180);
  const [endStamp, setEndStamp] = useState<string | null>(null);
  const [selected, setSelected] = useState<number>();
  const [volume, setVolume] = useState(true);
  const [dragging, setDragging] = useState(false);
  const drag = useRef<{ x: number; end: number; width: number; moved: boolean } | null>(null);
  const pending = useRef<number | undefined>(undefined);
  const svg = useRef<SVGSVGElement>(null);
  const instructions = useId();
  const maxCount = Math.min(600, data.length),
    minCount = Math.min(12, data.length);
  const end = useMemo(() => {
    if (endStamp === null) return data.length - 1;
    let low = 0,
      high = data.length - 1;
    while (low <= high) {
      const mid = (low + high) >>> 1;
      if (data[mid].timestamp <= endStamp) low = mid + 1;
      else high = mid - 1;
    }
    return Math.max(0, high);
  }, [data, endStamp]);
  const interval = useMemo(
    () =>
      intervalSeconds
        ? intervalSeconds * 1000
        : Math.min(
            ...data
              .slice(1, 600)
              .map((row, i) => Date.parse(row.timestamp) - Date.parse(data[i].timestamp)),
          ),
    [data, intervalSeconds],
  );
  const size = Math.max(minCount, Math.min(count, maxCount));
  const last = Math.max(size - 1, end),
    first = Math.max(0, last - size + 1);
  const visible = useMemo(() => data.slice(first, last + 1), [data, first, last]);
  const scale = useMemo(() => {
    if (!visible.length) return { low: 0, high: 1 };
    const lo = Math.min(
      ...visible.map((row) => Math.min(row.low, bands ? (row.lower ?? row.low) : row.low)),
    );
    const hi = Math.max(
      ...visible.map((row) => Math.max(row.high, bands ? (row.upper ?? row.high) : row.high)),
    );
    const pad = (hi - lo || hi * 0.01 || 1) * 0.07;
    return { low: lo - pad, high: hi + pad };
  }, [visible, bands]);
  const overview = useMemo(() => {
    if (!data.length) return '';
    const lo = Math.min(...data.map((row) => row.close)),
      hi = Math.max(...data.map((row) => row.close)),
      span = hi - lo || 1;
    const samples = Math.min(160, data.length);
    const points: string[] = [];
    for (let index = 0; index < samples; index++) {
      const i = Math.round((index * (data.length - 1)) / Math.max(1, samples - 1));
      points.push(
        `${points.length ? 'L' : 'M'}${(i / (data.length - 1 || 1)) * 1000},${27 - ((data[i].close - lo) / span) * 23}`,
      );
    }
    return points.join(' ');
  }, [data]);
  useEffect(
    () => () => {
      if (pending.current !== undefined) cancelAnimationFrame(pending.current);
    },
    [],
  );
  if (!visible.length) return <div className="chart-empty">No closed candles available.</div>;
  const selectedIndex =
    selected === undefined ? visible.length - 1 : Math.min(selected, visible.length - 1);
  const candle = visible[selectedIndex];
  const bottom = volume ? H - B - 60 : H - B;
  const step = (W - L - R) / visible.length;
  const x = L + (selectedIndex + 0.5) * step;
  const y = T + ((scale.high - candle.close) / (scale.high - scale.low)) * (bottom - T);
  const pan = (endIndex: number) => {
    const target = Math.max(size - 1, Math.min(data.length - 1, endIndex));
    setEndStamp(target === data.length - 1 ? null : data[target].timestamp);
    setSelected(undefined);
  };
  const zoom = (factor: number) => {
    setCount(Math.max(minCount, Math.min(maxCount, Math.round(size * factor))));
    setSelected(undefined);
  };
  const reset = () => {
    setCount(180);
    setEndStamp(null);
    setSelected(undefined);
  };
  return (
    <div className="candle-chart interactive-candles">
      <div className="chart-interaction-toolbar">
        <div className="chart-range-pills" role="group" aria-label="Visible candle range">
          {[30, 90, 180]
            .filter((n) => n < data.length)
            .map((n) => (
              <button
                key={n}
                type="button"
                aria-pressed={size === n}
                onClick={() => {
                  setCount(n);
                  setSelected(undefined);
                }}
              >
                {n} bars
              </button>
            ))}
          <button
            type="button"
            aria-pressed={size === maxCount}
            onClick={() => {
              setCount(maxCount);
              setSelected(undefined);
            }}
          >
            {data.length <= 600 ? 'All' : `${maxCount} bars`}
          </button>
        </div>
        <div className="chart-toolbar-actions">
          <button
            type="button"
            className="icon-button"
            title="Zoom in"
            aria-label="Zoom chart in"
            disabled={size <= minCount}
            onClick={() => zoom(0.7)}
          >
            <ZoomIn size={15} />
          </button>
          <button
            type="button"
            className="icon-button"
            title="Zoom out"
            aria-label="Zoom chart out"
            disabled={size >= maxCount}
            onClick={() => zoom(1.4)}
          >
            <ZoomOut size={15} />
          </button>
          <button
            type="button"
            className={`icon-button ${volume ? 'selected' : ''}`}
            title="Toggle volume"
            aria-label="Show volume"
            aria-pressed={volume}
            onClick={() => setVolume(!volume)}
          >
            <ChartColumn size={15} />
          </button>
          <button
            type="button"
            className="icon-button"
            title="Reset to latest"
            aria-label="Reset chart view"
            onClick={reset}
          >
            <RotateCcw size={14} />
          </button>
          <button
            type="button"
            className="icon-button"
            title="Export visible OHLCV"
            aria-label="Export visible candles"
            onClick={() =>
              exportCSV('sibyl-chart-view.csv', [
                ['Time', 'Open', 'High', 'Low', 'Close', 'Base volume'],
                ...visible.map((row) => [
                  row.timestamp,
                  row.open,
                  row.high,
                  row.low,
                  row.close,
                  row.volume,
                ]),
              ])
            }
          >
            <Download size={14} />
          </button>
        </div>
      </div>
      <div className="ohlc-readout">
        <time>{new Date(candle.timestamp).toLocaleString()}</time>
        {(['open', 'high', 'low', 'close'] as const).map((key) => (
          <span key={key}>
            {key[0].toUpperCase()} <b>{number(candle[key], candle[key] < 1 ? 8 : 2)}</b>
          </span>
        ))}
        <span>
          Vol <b>{number(candle.volume)}</b>
        </span>
      </div>
      <svg
        ref={svg}
        viewBox={`0 0 ${W} ${H}`}
        role="img"
        tabIndex={0}
        aria-label={`${mode === 'line' ? 'Price line' : 'OHLC candlestick'} chart, ${visible.length} of ${data.length} closed candles`}
        aria-describedby={instructions}
        className={dragging ? 'dragging' : ''}
        onPointerDown={(event) => {
          if (event.button !== 0) return;
          drag.current = {
            x: event.clientX,
            end: last,
            width: event.currentTarget.getBoundingClientRect().width,
            moved: false,
          };
          event.currentTarget.setPointerCapture(event.pointerId);
        }}
        onPointerMove={(event) => {
          const clientX = event.clientX;
          if (pending.current !== undefined) cancelAnimationFrame(pending.current);
          pending.current = requestAnimationFrame(() => {
            const element = svg.current;
            if (!element) return;
            const current = drag.current;
            if (current && Math.abs(clientX - current.x) > 5) {
              current.moved = true;
              setDragging(true);
              pan(
                current.end -
                  Math.round(((((clientX - current.x) / current.width) * W) / (W - L - R)) * size),
              );
            } else if (!current?.moved) {
              const rect = element.getBoundingClientRect();
              const next = Math.max(
                0,
                Math.min(
                  visible.length - 1,
                  Math.floor((((clientX - rect.left) / rect.width) * W - L) / step),
                ),
              );
              setSelected((previous) => (previous === next ? previous : next));
            }
          });
        }}
        onPointerUp={(event) => {
          drag.current = null;
          setDragging(false);
          if (event.currentTarget.hasPointerCapture(event.pointerId))
            event.currentTarget.releasePointerCapture(event.pointerId);
        }}
        onPointerCancel={() => {
          drag.current = null;
          setDragging(false);
        }}
        onDoubleClick={reset}
        onKeyDown={(event) => {
          if (event.key === '+' || event.key === '=') {
            event.preventDefault();
            zoom(0.7);
          } else if (event.key === '-') {
            event.preventDefault();
            zoom(1.4);
          } else if (event.key === 'ArrowLeft' || event.key === 'ArrowRight') {
            event.preventDefault();
            const direction = event.key === 'ArrowLeft' ? -1 : 1;
            if (event.shiftKey) pan(last + direction * Math.max(1, Math.floor(size / 5)));
            else setSelected(Math.max(0, Math.min(visible.length - 1, selectedIndex + direction)));
          } else if (event.key === 'Home' || event.key === 'End') {
            event.preventDefault();
            if (event.shiftKey) pan(event.key === 'Home' ? size - 1 : data.length - 1);
            else setSelected(event.key === 'Home' ? 0 : visible.length - 1);
          } else if (event.key === 'Escape') {
            setSelected(undefined);
          }
        }}
      >
        <Marks
          data={visible}
          bands={bands}
          mode={mode}
          volume={volume}
          low={scale.low}
          high={scale.high}
          bottom={bottom}
          interval={interval}
        />
        <g pointerEvents="none">
          <line
            x1={x}
            x2={x}
            y1={T}
            y2={H - B}
            stroke="var(--muted)"
            strokeDasharray="3 4"
            opacity=".5"
          />
          <line
            x1={L}
            x2={W - R}
            y1={y}
            y2={y}
            stroke="var(--muted)"
            strokeDasharray="3 4"
            opacity=".35"
          />
          <circle cx={x} cy={y} r="3" fill="#4675d2" stroke="white" strokeWidth="1.5" />
          <rect x={W - R + 3} y={y - 10} width={R - 7} height="20" rx="5" fill="#4675d2" />
          <text x={W - R + 9} y={y + 4} fontSize="10" fill="white">
            {number(candle.close, candle.close < 1 ? 8 : 2)}
          </text>
        </g>
      </svg>
      <div className="chart-history-navigator">
        <svg viewBox="0 0 1000 32" aria-hidden="true">
          <path d={overview} fill="none" stroke="#9aaac7" strokeWidth="1.4" />
          <rect
            x={(first / Math.max(1, data.length)) * 1000}
            y="1"
            width={(visible.length / data.length) * 1000}
            height="30"
            fill="#4675d218"
            stroke="#4675d277"
            rx="4"
          />
        </svg>
        <input
          type="range"
          aria-label="Chart window position"
          min={Math.max(0, size - 1)}
          max={data.length - 1}
          value={last}
          disabled={size >= data.length}
          onChange={(event) => pan(Number(event.target.value))}
        />
      </div>
      <div className="chart-inspection-footer">
        <span>
          {date(visible[0].timestamp)} — {date(visible[visible.length - 1].timestamp)} ·{' '}
          {visible.length} / {data.length} bars {endStamp === null ? '· latest' : ''}
        </span>
        <span id={instructions}>Drag to pan · +/− zoom · arrows inspect · Shift+arrows pan</span>
      </div>
      <label className="candle-scrubber">
        Inspect candle
        <input
          type="range"
          min="0"
          max={visible.length - 1}
          value={selectedIndex}
          onChange={(event) => setSelected(Number(event.target.value))}
          aria-label="Inspect candle"
        />
      </label>
    </div>
  );
}

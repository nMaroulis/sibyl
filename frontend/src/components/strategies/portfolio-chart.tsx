import { useMemo, useState } from 'react';
import {
  Area,
  Brush,
  CartesianGrid,
  ComposedChart,
  Line,
  ReferenceDot,
  ReferenceArea,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { number, shortDate } from '../../lib/api';
import type { PortfolioResult } from '../../lib/portfolio-research';
const colors = [
  '#4675d2',
  '#9982d4',
  '#4da79b',
  '#d5a04e',
  '#ce7e9a',
  '#7c9bc0',
  '#9caa66',
  '#b5917b',
];

/** Mount one lightweight chart at a time; range selection preserves full stored/exported data. */
export function PortfolioChart({ result }: { result: PortfolioResult }) {
  const [mode, setMode] = useState<'equity' | 'drawdown' | 'weights' | 'trades'>('equity');
  const [asset, setAsset] = useState(result.parameters.legs[0].symbol);
  const symbols = result.parameters.legs.map((leg) => leg.symbol);
  const [range, setRange] = useState<[number, number]>([0, result.curve.length - 1]);
  const [drag, setDrag] = useState<[number, number] | null>(null);
  const visibleFills = result.fills.filter(
    (f) => f.symbol === asset && f.bar >= range[0] && f.bar <= range[1],
  );
  const stride = Math.max(1, Math.ceil(visibleFills.length / 160));
  const markers = visibleFills.filter((_, i) => i % stride === 0 || i === visibleFills.length - 1);
  const data = useMemo(
    () =>
      result.curve.map((row, i) => ({
        timestamp: row.timestamp,
        portfolio: mode === 'drawdown' ? row.drawdown_pct : row.value,
        hold:
          mode === 'drawdown'
            ? result.benchmarks.buy_hold.curve[i].drawdown_pct
            : result.benchmarks.buy_hold.curve[i].value,
        cash: mode === 'weights' ? result.allocations[i].cash_pct : result.initial_capital,
        price: result.price_series[asset][i].value,
        ...Object.fromEntries(
          symbols.map((symbol, j) => [`asset${j}`, result.allocations[i].weights[symbol]]),
        ),
      })),
    [result, mode, asset],
  );
  return (
    <div className="portfolio-chart">
      <div className="portfolio-chart-modes" role="group" aria-label="Portfolio chart view">
        {(['equity', 'drawdown', 'weights', 'trades'] as const).map((view) => (
          <button
            key={view}
            className={`button tiny ${view === mode ? 'secondary' : 'ghost'}`}
            aria-pressed={view === mode}
            onClick={() => setMode(view)}
          >
            {
              {
                equity: 'Equity & benchmarks',
                drawdown: 'Drawdown',
                weights: 'Asset allocation',
                trades: 'Price & trades',
              }[view]
            }
          </button>
        ))}
        {(range[0] !== 0 || range[1] !== result.curve.length - 1) && (
          <button
            className="button tiny ghost"
            onClick={() => setRange([0, result.curve.length - 1])}
          >
            Reset zoom
          </button>
        )}
        {mode === 'trades' && (
          <select
            aria-label="Trade chart asset"
            value={asset}
            onChange={(e) => setAsset(e.target.value)}
          >
            {symbols.map((s) => (
              <option key={s}>{s}</option>
            ))}
          </select>
        )}
      </div>
      <div style={{ height: 340, minWidth: 0 }}>
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart
            data={data}
            margin={{ top: 20, right: 18, bottom: 5, left: 0 }}
            onMouseDown={(event) => {
              const i = data.findIndex((row) => row.timestamp === event.activeLabel);
              if (i >= 0) setDrag([i, i]);
            }}
            onMouseMove={(event) => {
              if (drag) {
                const i = data.findIndex((row) => row.timestamp === event.activeLabel);
                if (i >= 0) setDrag([drag[0], i]);
              }
            }}
            onMouseUp={() => {
              if (drag && Math.abs(drag[0] - drag[1]) >= 2)
                setRange([Math.min(...drag), Math.max(...drag)]);
              setDrag(null);
            }}
            onMouseLeave={() => setDrag(null)}
          >
            <CartesianGrid vertical={false} stroke="var(--chart-grid)" strokeDasharray="3 5" />
            <XAxis
              dataKey="timestamp"
              tickFormatter={shortDate}
              minTickGap={45}
              axisLine={false}
              tickLine={false}
              tick={{ fontSize: 10, fill: 'var(--muted)' }}
            />
            <YAxis
              orientation="right"
              domain={mode === 'weights' ? [0, 100] : ['auto', 'auto']}
              tickFormatter={(v) => number(v, mode === 'weights' ? 0 : 2)}
              axisLine={false}
              tickLine={false}
              tick={{ fontSize: 10, fill: 'var(--muted)' }}
              width={72}
            />
            <Tooltip
              labelFormatter={(v) => new Date(String(v)).toLocaleString()}
              formatter={(v, name) => [
                `${number(Number(v), 4)}${mode === 'weights' || mode === 'drawdown' ? '%' : ` ${result.quote}`}`,
                name,
              ]}
              contentStyle={{ borderRadius: 12, border: '1px solid var(--border)', fontSize: 11 }}
            />
            {mode === 'weights' ? (
              <>
                {symbols.map((s, i) => (
                  <Area
                    key={s}
                    type="linear"
                    dataKey={`asset${i}`}
                    name={s.split('/')[0]}
                    stackId="weights"
                    stroke={colors[i]}
                    fill={colors[i]}
                    fillOpacity={0.6}
                    isAnimationActive={false}
                  />
                ))}
                <Area
                  type="linear"
                  dataKey="cash"
                  name={`Cash · ${result.quote}`}
                  stackId="weights"
                  stroke="#a7b2c7"
                  fill="#c4cede"
                  fillOpacity={0.7}
                  isAnimationActive={false}
                />
              </>
            ) : mode === 'trades' ? (
              <>
                <Line
                  type="linear"
                  dataKey="price"
                  name={asset}
                  dot={false}
                  stroke="#4675d2"
                  strokeWidth={2}
                  isAnimationActive={false}
                />
                {markers.map((f, i) => (
                  <ReferenceDot
                    key={i}
                    x={f.timestamp}
                    y={f.price}
                    r={4}
                    fill={f.side === 'buy' ? '#35a680' : '#d97a88'}
                    stroke="white"
                    ifOverflow="extendDomain"
                  />
                ))}
              </>
            ) : (
              <>
                <Line
                  type="linear"
                  dataKey="portfolio"
                  name="Rebalanced"
                  dot={false}
                  stroke="#4675d2"
                  strokeWidth={2.2}
                  isAnimationActive={false}
                />
                <Line
                  type="linear"
                  dataKey="hold"
                  name="Buy & hold"
                  dot={false}
                  stroke="#a18bcc"
                  strokeWidth={1.6}
                  isAnimationActive={false}
                />
                {mode === 'equity' && (
                  <Line
                    dataKey="cash"
                    name="Cash · zero interest"
                    dot={false}
                    stroke="#9daabc"
                    strokeDasharray="4 4"
                    isAnimationActive={false}
                  />
                )}
              </>
            )}
            {drag && (
              <ReferenceArea
                x1={data[Math.min(...drag)].timestamp}
                x2={data[Math.max(...drag)].timestamp}
                fill="#8eace9"
                fillOpacity={0.16}
              />
            )}
            <Brush
              startIndex={range[0]}
              endIndex={range[1]}
              onChange={(bounds) =>
                setRange([bounds.startIndex ?? 0, bounds.endIndex ?? data.length - 1])
              }
              dataKey="timestamp"
              height={22}
              travellerWidth={8}
              stroke="#c7d4ee"
              fill="#f5f8ff"
              tickFormatter={shortDate}
            />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
      <p className="footnote">
        Drag across the plot or move the range handles to zoom.{' '}
        {mode === 'trades'
          ? `Green markers buy, rose markers sell at simulated prices; ${markers.length}/${visibleFills.length} markers shown in this range. All fills/times/costs are retained below and in exports.`
          : mode === 'weights'
            ? 'Close-marked allocations before the planned final liquidation; cash includes the quote reserve.'
            : 'Identical input window and initial capital. Buy & hold pays the same configured entry/exit costs.'}{' '}
        Candle timestamps label interval opens.
      </p>
    </div>
  );
}

import { useState } from 'react';
import {
  CartesianGrid,
  ReferenceLine,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { Download } from 'lucide-react';
import { number } from '../../lib/api';
import type { Source } from '../../lib/types';

export type Regression = {
  observations: number;
  reference: string;
  note: string;
  point_limit: number;
  items: {
    reference: string;
    target: string;
    observations: number;
    status: string;
    beta: number | null;
    intercept_pct: number | null;
    r_squared: number | null;
    residual_rms_pct: number | null;
    points: { timestamp: string; x: number; y: number }[];
  }[];
};

/** Regression is explicitly descriptive and always uses contemporaneous log returns. */
export function ReturnRelationships({
  data,
  source,
  timeframe,
}: {
  data?: Regression;
  source: Source;
  timeframe: string;
}) {
  const [target, setTarget] = useState('');
  if (!data) return null;
  const item = data.items.find((row) => row.target === target) ?? data.items[0];
  const minimum = Math.min(...(item?.points.map((p) => p.x) ?? [0]));
  const maximum = Math.max(...(item?.points.map((p) => p.x) ?? [0]));
  return (
    <details className="return-relationships">
      <summary>Return regression · reference {data.reference}</summary>
      <p className="footnote">{data.note}</p>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Target</th>
              <th>Beta</th>
              <th>Intercept / interval</th>
              <th>R²</th>
              <th>Residual RMS</th>
            </tr>
          </thead>
          <tbody>
            {data.items.map((row) => (
              <tr key={row.target}>
                <td>{row.target}</td>
                <td>{row.beta == null ? '—' : number(row.beta, 3)}</td>
                <td>{row.intercept_pct == null ? '—' : `${number(row.intercept_pct, 4)}%`}</td>
                <td>{row.r_squared == null ? '—' : number(row.r_squared, 3)}</td>
                <td>
                  {row.residual_rms_pct == null
                    ? row.status.replaceAll('_', ' ')
                    : `${number(row.residual_rms_pct, 3)}%`}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {!!data.items.length && (
        <label>
          Inspect return pair
          <select value={item?.target ?? ''} onChange={(e) => setTarget(e.target.value)}>
            {data.items.map((row) => (
              <option key={row.target} value={row.target}>
                {row.target} vs {row.reference}
              </option>
            ))}
          </select>
        </label>
      )}
      {item?.status === 'observed' && (
        <>
          <div
            className="return-scatter"
            role="img"
            aria-label={`${item.target} against ${item.reference} log returns with fitted line`}
          >
            <ResponsiveContainer width="100%" height="100%">
              <ScatterChart margin={{ top: 15, right: 15, bottom: 15, left: 8 }}>
                <CartesianGrid stroke="var(--chart-grid)" strokeDasharray="3 5" />
                <XAxis
                  dataKey="x"
                  type="number"
                  name={item.reference}
                  unit="%"
                  tick={{ fontSize: 10 }}
                  tickFormatter={(v) => number(v, 1)}
                />
                <YAxis
                  dataKey="y"
                  type="number"
                  name={item.target}
                  unit="%"
                  tick={{ fontSize: 10 }}
                  tickFormatter={(v) => number(v, 1)}
                />
                <Tooltip
                  cursor={{ strokeDasharray: '3 3' }}
                  formatter={(value, name) => [`${number(Number(value), 3)}%`, name]}
                />
                <Scatter
                  name="Observed log returns"
                  data={item.points}
                  fill="#7094d0"
                  fillOpacity={0.55}
                  isAnimationActive={false}
                />
                <ReferenceLine
                  stroke="#ad88b4"
                  segment={[
                    { x: minimum, y: item.intercept_pct! + item.beta! * minimum },
                    { x: maximum, y: item.intercept_pct! + item.beta! * maximum },
                  ]}
                  ifOverflow="extendDomain"
                />
              </ScatterChart>
            </ResponsiveContainer>
          </div>
          <p className="footnote">
            {item.observations} aligned return observations. Plot shows the latest{' '}
            {item.points.length}; coefficients use the complete aligned sample. Both axes are log
            returns in percent per candle. This intercept is not CAPM alpha.
          </p>
        </>
      )}
      <button
        className="text-button"
        onClick={() => {
          const url = URL.createObjectURL(
            new Blob(
              [
                JSON.stringify(
                  {
                    schema: 1,
                    exported_at: new Date().toISOString(),
                    source: source.source,
                    source_label: source.source_label,
                    provider: source.provider,
                    environment: source.environment,
                    timeframe,
                    ...data,
                  },
                  null,
                  2,
                ),
              ],
              { type: 'application/json' },
            ),
          );
          const anchor = document.createElement('a');
          anchor.href = url;
          anchor.download = 'sibyl-return-regression.json';
          anchor.click();
          URL.revokeObjectURL(url);
        }}
      >
        <Download size={13} />
        Export regression evidence
      </button>
    </details>
  );
}

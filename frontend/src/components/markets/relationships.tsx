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
import { ErrorState } from '../ui';

export type Regression = {
  observations: number;
  available_observations: number;
  robust: boolean;
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
    theil_sen?: {
      beta: number;
      intercept_pct: number;
      median_absolute_residual_pct: number;
      ols_median_absolute_residual_pct: number;
    };
    points: { timestamp: string; x: number; y: number }[];
  }[];
};

/** Regression is explicitly descriptive and always uses contemporaneous log returns. */
export function ReturnRelationships({
  data,
  source,
  timeframe,
  robust,
  onRobust,
  error,
  retry,
}: {
  data?: Regression;
  source?: Source;
  timeframe: string;
  robust: boolean;
  onRobust: (value: boolean) => void;
  error: string;
  retry: () => void;
}) {
  const [target, setTarget] = useState('');
  const item = data?.items.find((row) => row.target === target) ?? data?.items[0];
  const minimum = Math.min(...(item?.points.map((p) => p.x) ?? [0]));
  const maximum = Math.max(...(item?.points.map((p) => p.x) ?? [0]));
  return (
    <details className="return-relationships">
      <summary>Return regression{data?.reference && ` · reference ${data.reference}`}</summary>
      <label className="return-robust-toggle">
        <input
          type="checkbox"
          checked={robust}
          onChange={(event) => onRobust(event.target.checked)}
        />
        Compare with Theil–Sen
      </label>
      {error ? (
        <ErrorState message={error} retry={retry} />
      ) : !data || !source || data.robust !== robust ? (
        <p className="footnote" aria-live="polite">
          Loading aligned returns…
        </p>
      ) : (
        <>
          <p className="footnote">{data.note}</p>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Target</th>
                  <th>{data.robust ? 'OLS beta' : 'Beta'}</th>
                  {data.robust && <th>Theil–Sen beta</th>}
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
                    {data.robust && <td>{row.theil_sen ? number(row.theil_sen.beta, 3) : '—'}</td>}
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
                    {item.theil_sen && (
                      <ReferenceLine
                        stroke="var(--accent)"
                        strokeDasharray="5 4"
                        segment={[
                          {
                            x: minimum,
                            y: item.theil_sen.intercept_pct + item.theil_sen.beta * minimum,
                          },
                          {
                            x: maximum,
                            y: item.theil_sen.intercept_pct + item.theil_sen.beta * maximum,
                          },
                        ]}
                        ifOverflow="extendDomain"
                      />
                    )}
                  </ScatterChart>
                </ResponsiveContainer>
              </div>
              {item.theil_sen && (
                <p className="footnote">
                  <strong>Solid</strong> OLS · <strong>Dashed</strong> Theil–Sen · Median absolute
                  residual {number(item.theil_sen.ols_median_absolute_residual_pct, 3)}% OLS
                  {' / '}
                  {number(item.theil_sen.median_absolute_residual_pct, 3)}% Theil–Sen
                </p>
              )}
              <p className="footnote">
                Fitted on {item.observations} of {data.available_observations ?? item.observations}{' '}
                aligned returns. Plot shows {item.points.length}. Both axes use log returns in
                percent per candle.
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
        </>
      )}
    </details>
  );
}

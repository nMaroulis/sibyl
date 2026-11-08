import { useState } from 'react';
import { Download, FlaskConical } from 'lucide-react';
import { AgentButton } from '../agents';
import { Badge } from '../ui';
import { number, post } from '../../lib/api';
import type { Source, Timeframe } from '../../lib/types';

type LagResult = Source & {
  lags: number;
  observations: number;
  discarded_earlier_returns: number;
  start: string | null;
  last_target: string | null;
  training_end_exclusive: string | null;
  hypotheses: number;
  adjustment: string;
  assumptions: string[];
  items: {
    reference: string;
    target: string;
    status: string;
    reason: string | null;
    f_statistic: number | null;
    p_value: number | null;
    adjusted_p_value: number | null;
    training_samples: number;
    residual_diagnostic?: { serial_correlation_flag: boolean };
    held_out: null | {
      samples: number;
      own_lags_mae_pct: number;
      augmented_mae_pct: number;
      zero_return_mae_pct: number;
      skill_vs_own_lags_pct: number | null;
    };
  }[];
};
const probability = (value: number | null) =>
  value == null ? '—' : value < 0.0001 ? '< 0.0001' : number(value, 4);

/** Explicit numerical research; matrix transforms never change its log-return inputs. */
export function GrangerAnalysis({
  symbols,
  source,
  timeframe,
  limit,
}: {
  symbols: string[];
  source: Source;
  timeframe: Timeframe;
  limit: number;
}) {
  const [lags, setLags] = useState(2),
    [busy, setBusy] = useState(false),
    [error, setError] = useState('');
  const [result, setResult] = useState<LagResult>();
  return (
    <details className="return-relationships lag-analysis">
      <summary>Lag predictability · Granger analysis</summary>
      <p className="footnote">
        Does one market’s past add linear information beyond another market’s own past? Uses
        consecutive log returns, one chosen lag order and an independent later window. This does not
        identify causation or a trading signal.
      </p>
      <div className="workspace-controls">
        <label>
          Lag order
          <select
            value={lags}
            onChange={(e) => {
              setLags(Number(e.target.value));
              setResult(undefined);
            }}
            disabled={busy}
          >
            {[1, 2, 3, 4, 5].map((p) => (
              <option key={p} value={p}>
                {p} {p === 1 ? 'candle' : 'candles'} · {timeframe}
              </option>
            ))}
          </select>
        </label>
        <button
          className="button secondary"
          disabled={busy}
          onClick={async () => {
            setBusy(true);
            setError('');
            try {
              setResult(
                await post<LagResult>('/markets/granger', {
                  symbols,
                  source: source.source,
                  timeframe,
                  limit,
                  lags,
                }),
              );
            } catch (e) {
              setError((e as Error).message);
            } finally {
              setBusy(false);
            }
          }}
        >
          <FlaskConical size={14} />
          {busy ? 'Calculating…' : 'Run lag analysis'}
        </button>
      </div>
      {error && (
        <p className="form-error" role="alert">
          {error}
        </p>
      )}
      {result && (
        <>
          <div className="strategy-alert-tags">
            <Badge tone={result.source === 'demo' ? 'demo' : 'neutral'}>
              {result.source_label}
            </Badge>
            <Badge>{result.observations} consecutive returns</Badge>
            <Badge>70% fit / 30% holdout</Badge>
          </div>
          <p className="footnote">
            {result.start && new Date(result.start).toLocaleString()} →{' '}
            {result.last_target && new Date(result.last_target).toLocaleString()} · training ends
            before{' '}
            {result.training_end_exclusive &&
              new Date(result.training_end_exclusive).toLocaleString()}
            . {result.discarded_earlier_returns} earlier returns excluded at a gap.{' '}
            {result.hypotheses} planned directions · {result.adjustment}.
          </p>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Past reference → target</th>
                  <th>Training F</th>
                  <th>Nominal p</th>
                  <th>Adjusted p</th>
                  <th>Held-out MAE improvement</th>
                </tr>
              </thead>
              <tbody>
                {result.items.map((row) => (
                  <tr key={`${row.reference}:${row.target}`}>
                    <td>
                      {row.reference} → {row.target}
                    </td>
                    <td>{row.f_statistic == null ? '—' : number(row.f_statistic, 3)}</td>
                    <td>{probability(row.p_value)}</td>
                    <td>{probability(row.adjusted_p_value)}</td>
                    <td>
                      {row.held_out?.skill_vs_own_lags_pct == null
                        ? row.reason || 'Unavailable'
                        : `${number(row.held_out.skill_vs_own_lags_pct, 1)}% vs own lags`}
                      {row.residual_diagnostic?.serial_correlation_flag && (
                        <small>
                          Residual serial-dependence flag · classical inference needs caution
                        </small>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <details>
            <summary>Held-out errors & assumptions</summary>
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Direction</th>
                    <th>Test targets</th>
                    <th>Own lags MAE</th>
                    <th>+ Reference lags MAE</th>
                    <th>Zero return MAE</th>
                  </tr>
                </thead>
                <tbody>
                  {result.items
                    .filter((row) => row.held_out)
                    .map((row) => (
                      <tr key={`${row.reference}:${row.target}`}>
                        <td>
                          {row.reference} → {row.target}
                        </td>
                        <td>{row.held_out!.samples}</td>
                        <td>{number(row.held_out!.own_lags_mae_pct, 4)}%</td>
                        <td>{number(row.held_out!.augmented_mae_pct, 4)}%</td>
                        <td>{number(row.held_out!.zero_return_mae_pct, 4)}%</td>
                      </tr>
                    ))}
                </tbody>
              </table>
            </div>
            {result.assumptions.map((note) => (
              <p className="footnote" key={note}>
                {note}
              </p>
            ))}
          </details>
          <div className="workspace-actions">
            <button
              className="text-button"
              onClick={() => {
                const url = URL.createObjectURL(
                  new Blob([JSON.stringify(result, null, 2)], { type: 'application/json' }),
                );
                const a = document.createElement('a');
                a.href = url;
                a.download = 'sibyl-granger-analysis.json';
                a.click();
                URL.revokeObjectURL(url);
              }}
            >
              <Download size={13} />
              Export lag evidence
            </button>
            <AgentButton
              module="analyst"
              context={{
                symbol: symbols[0],
                comparison_symbols: symbols,
                market_source: source.source,
                timeframe,
                limit,
                granger_lags: lags,
              }}
            />
          </div>
        </>
      )}
    </details>
  );
}

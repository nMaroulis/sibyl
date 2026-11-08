import { Badge, Change } from '../ui';
import { BacktestChart } from './backtest-chart';
import { number } from '../../lib/api';
import type { Backtest } from '../../lib/types';

export type Deployment = {
  method: string;
  note: string;
  adaptive: Omit<Backtest, 'id' | 'source'> & {
    transitions: {
      index: number;
      timestamp: string;
      cash: number;
      quantity: number;
      equity_at_open: number;
    }[];
  };
  fixed: Omit<Backtest, 'id' | 'source'>;
};

/** One persistent hypothetical account; independent fold returns remain separate above. */
export function ContinuousReplay({
  result,
  id,
  source,
}: {
  result: Deployment;
  id: string;
  source: string;
}) {
  return (
    <details className="continuous-replay" open>
      <summary>
        <strong>Continuous walk-forward replay</strong>
        <Badge>One cash &amp; asset balance</Badge>
      </summary>
      <p>{result.note}</p>
      <div className="validation-summary">
        <div>
          <small>Adaptive return</small>
          <strong>
            <Change value={result.adaptive.return_pct} />
          </strong>
        </div>
        <div>
          <small>Fixed-settings return</small>
          <strong>
            <Change value={result.fixed.return_pct} />
          </strong>
        </div>
        <div>
          <small>Fees on actual fills</small>
          <strong>{number(result.adaptive.fees)}</strong>
        </div>
        <div>
          <small>Round trips</small>
          <strong>{result.adaptive.trades}</strong>
        </div>
      </div>
      <BacktestChart
        result={{ ...result.adaptive, id, source }}
        comparison={{ ...result.fixed, id: `${id}-fixed`, source }}
      />
      <details>
        <summary>Balances entering each parameter window</summary>
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>Window</th>
                <th>First open</th>
                <th>Cash carried</th>
                <th>Units carried</th>
                <th>Equity at open</th>
              </tr>
            </thead>
            <tbody>
              {result.adaptive.transitions.map((row) => (
                <tr key={row.index}>
                  <td>{row.index}</td>
                  <td>{new Date(row.timestamp).toLocaleString()}</td>
                  <td>{number(row.cash)}</td>
                  <td>{number(row.quantity, 8)}</td>
                  <td>{number(row.equity_at_open)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
    </details>
  );
}

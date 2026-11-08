import type { Backtest } from '../../lib/types';
import { number, percent } from '../../lib/api';

/** References share exactly the run's evaluated prices, clock and capital. */
export function BenchmarkComparison({ result }: { result: Backtest }) {
  if (!result.benchmarks) return null;
  const items = Object.values(result.benchmarks);
  return (
    <details className="benchmark-comparison" open>
      <summary>Reference portfolios · same input & costs</summary>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Reference</th>
              <th>Return</th>
              <th>Max drawdown</th>
              <th>Sharpe</th>
              <th>Fees · {result.symbol.split('/')[1]}</th>
              <th>Fills</th>
            </tr>
          </thead>
          <tbody>
            {items.map((item) => (
              <tr key={item.kind}>
                <td>
                  <strong>{item.label}</strong>
                  {item.cadence_bars && <small>Every {item.cadence_bars} candles</small>}
                </td>
                <td>{percent(item.return_pct)}</td>
                <td>{number(item.max_drawdown, 2)}%</td>
                <td>{item.sharpe == null ? '—' : number(item.sharpe, 2)}</td>
                <td>{number(item.fees, 4)}</td>
                <td>{item.execution_count}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="footnote">
        {items[0]?.assumptions} Select a reference in the equity chart to inspect its path.
        Installments split initial cash equally across scheduled purchases; 50/50 rebalances toward
        equal asset/cash value before costs.
      </p>
    </details>
  );
}

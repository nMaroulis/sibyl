import { ArrowRight, ArrowUpRight, Check } from 'lucide-react';
import { Link } from 'react-router-dom';
import { number, percent, quoteAmount } from '../../lib/api';
import type { Backtest } from '../../lib/types';
import { AgentButton } from '../agents';
import { Change } from '../ui';
import { BacktestChart } from './backtest-chart';
import { BacktestLimitEvidence } from './backtest-limit-evidence';

function metric(value: number | null | undefined, suffix = '') {
  return value == null || !Number.isFinite(value) ? '—' : number(value, 2) + suffix;
}

/** Display comparable cash, equity and risk metrics in both backtest views. */
export function BacktestPerformance({ result }: { result: Backtest }) {
  const quote = result.symbol.split('/')[1];
  const amount = (value: number) => quoteAmount(value, quote);
  const pnl = result.final_equity - result.initial_capital;
  const position = result.execution_limits?.open_position;
  const { metrics, summary } = result;
  const headline = [
    ['Total return', <Change key="return" value={result.return_pct} />],
    ['Max drawdown', metric(result.max_drawdown, '%')],
    ['Sharpe ratio', metric(result.sharpe)],
    ['Win rate', result.trades ? metric(result.win_rate, '%') : '—'],
    ['Round trips', number(result.trades, 0)],
    ['Fees paid', amount(result.fees)],
  ] as const;
  const details = [
    ['Buy & hold return', percent(result.benchmark_pct)],
    ['Sortino ratio', metric(metrics?.sortino)],
    ['Calmar ratio', metric(metrics?.calmar)],
    ['Profit factor', metric(summary?.profit_factor ?? (summary ? null : metrics?.profit_factor))],
    ['Annualized return', metric(summary?.annualized_return_pct, '%')],
    ['Expectancy per trade', summary?.expectancy == null ? '—' : amount(summary.expectancy)],
    ['Average win', metric(metrics?.average_win, '%')],
    ['Average loss', metric(metrics?.average_loss, '%')],
    ['Best trade', metric(metrics?.best_trade, '%')],
    ['Worst trade', metric(metrics?.worst_trade, '%')],
    ['Time invested', metric(summary?.exposure_pct, '%')],
    ['Turnover', metric(summary?.turnover, '×')],
    ['Evaluated candles', summary ? number(summary.evaluated_bars, 0) : '—'],
    ['Warm-up candles', summary ? number(summary.warmup_bars, 0) : '—'],
  ] as const;

  return (
    <div className="backtest-performance" role="group" aria-label="Backtest performance">
      <dl className="backtest-balance-flow">
        <div>
          <dt>Starting capital</dt>
          <dd>{amount(result.initial_capital)}</dd>
        </div>
        <ArrowRight className="backtest-balance-arrow" size={18} aria-hidden="true" />
        <div>
          <dt>Ending equity</dt>
          <dd>{amount(result.final_equity)}</dd>
        </div>
        <div className="backtest-net-result">
          <dt>Net P&amp;L</dt>
          <dd className={pnl === 0 ? undefined : pnl > 0 ? 'positive' : 'negative'}>
            {pnl > 0 ? '+' : ''}
            {amount(pnl)}
          </dd>
        </div>
      </dl>
      {position && result.execution_limits && (
        <p className="backtest-ending-breakdown">
          Ending equity includes {amount(result.execution_limits.ending_cash)} cash and{' '}
          {amount(position.market_value)} in marked holdings.
        </p>
      )}
      <dl className="backtest-metrics backtest-key-metrics">
        {headline.map(([label, value]) => (
          <div key={label}>
            <dt>{label}</dt>
            <dd>{value}</dd>
          </div>
        ))}
      </dl>
      <details className="backtest-more-metrics">
        <summary>More performance metrics</summary>
        <dl className="backtest-metrics backtest-key-metrics">
          {details.map(([label, value]) => (
            <div key={label}>
              <dt>{label}</dt>
              <dd>{value}</dd>
            </div>
          ))}
        </dl>
      </details>
    </div>
  );
}

export function BacktestReportAsk({ result }: { result: Backtest }) {
  return (
    <AgentButton
      module="broker"
      compact
      context={{ backtest_id: result.id, symbol: result.symbol, timeframe: result.timeframe }}
    >
      Ask Broker about this run
    </AgentButton>
  );
}

/** Confirm the immutable run ID and show the report where the user launched it. */
export function InlineBacktestReport({
  result,
  algorithm,
  experimentLink,
}: {
  result: Backtest;
  algorithm: string;
  experimentLink: string;
}) {
  return (
    <>
      <header className="backtest-receipt">
        <div>
          <h2 id="inline-backtest-title">Backtest results</h2>
          <p>
            {algorithm} · {result.symbol} · {result.timeframe ?? '1d'}
          </p>
        </div>
        <div className="backtest-receipt-actions">
          <BacktestReportAsk result={result} />
          <Link className="button secondary tiny" to={experimentLink}>
            View in Experiments <ArrowUpRight size={14} aria-hidden="true" />
          </Link>
        </div>
        <div className="backtest-receipt-id" role="status">
          <Check size={14} aria-hidden="true" />
          <span>Saved</span>
          <code aria-label="Saved backtest ID">{result.id}</code>
        </div>
      </header>
      <BacktestPerformance result={result} />
      <BacktestLimitEvidence result={result} />
      <BacktestChart key={result.id} result={result} />
    </>
  );
}

import { ShieldCheck } from 'lucide-react';
import type { Backtest } from '../../lib/types';
import { number, quoteAmount } from '../../lib/api';
import { Badge } from '../ui';

/** Show the simulated order limits and any position carried to the final mark. */
export function BacktestLimitEvidence({ result }: { result: Backtest }) {
  const limits = result.execution_limits;
  if (!limits) return null;
  const [base, quote] = result.symbol.split('/');
  const { loss_pause: pause, open_position: position } = limits;
  const money = (value: number) => quoteAmount(value, quote);
  return (
    <div className="backtest-limit-evidence">
      <div className="backtest-limit-heading">
        <h3>
          <ShieldCheck size={16} aria-hidden="true" /> Simulated order limits
        </h3>
        <Badge tone={pause ? 'sand' : 'neutral'}>
          {pause ? 'Loss pause triggered' : 'Loss pause clear'}
        </Badge>
      </div>
      <dl>
        <div>
          <dt>Order cap</dt>
          <dd>{money(limits.max_order_quote)}</dd>
        </div>
        <div>
          <dt>Loss threshold</dt>
          <dd>{limits.max_loss_pct}%</dd>
        </div>
        <div>
          <dt>Capped orders</dt>
          <dd>{limits.capped_orders}</dd>
        </div>
        <div>
          <dt>Partial exits</dt>
          <dd>{limits.partial_exits}</dd>
        </div>
        <div>
          <dt>Ending cash</dt>
          <dd>{money(limits.ending_cash)}</dd>
        </div>
        <div>
          <dt>Realized P&amp;L</dt>
          <dd>{money(limits.realized_pnl)}</dd>
        </div>
      </dl>
      {pause && (
        <p>
          Submissions paused at the close on{' '}
          <time dateTime={pause.timestamp}>{new Date(pause.timestamp).toLocaleString()}</time>.
          Equity was {money(pause.equity)} against a {money(pause.threshold)} threshold.
        </p>
      )}
      {position && (
        <p>
          <strong>Open at end</strong> · {number(position.quantity, 8)} {base} valued at{' '}
          {money(position.market_value)} · Unrealized P&amp;L {money(position.unrealized_pnl)}.
        </p>
      )}
    </div>
  );
}

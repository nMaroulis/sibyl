import { Link } from 'react-router-dom';
import { Badge, Panel, PanelTitle } from '../ui';
import { number } from '../../lib/api';
import type { Job } from '../../lib/types';

/** Retained order identities and native fee currencies, independent of paper metrics. */
export function ExchangeRunEvidence({ job }: { job: Job }) {
  const quote = job.parameters.symbol.split('/')[1];
  return (
    <Panel className="full-panel strategy-exchange-evidence">
      <PanelTitle
        title="Exchange execution"
        subtitle={`${job.account} · ${job.exchange} · ${job.environment}`}
        action={<Badge>{job.execution_state?.replaceAll('_', ' ')}</Badge>}
      />
      <p className="footnote padded">
        Only this run’s native fills contribute to its allocated cash and position. Other account
        holdings, deposits and manual orders are excluded. Budgets do not reserve exchange funds.
        Base fees reduce owned units; quote fees reduce cash. Valuation uses the last observed
        exchange midpoint.
      </p>
      {job.stop_cancellation && (
        <p className="monitor-notice">
          Stop &amp; cancel was approved. New submissions are stopped; cancellation outcomes and
          native fill evidence are shown below. Selling holdings requires a separate exit approval.
        </p>
      )}
      {job.close_position && (
        <section className="strategy-close-progress" aria-label="Reviewed position exit">
          <div>
            <strong>Reviewed position exit</strong>
            <Badge
              tone={
                ['unknown', 'interrupted', 'rejected'].includes(job.close_position.state)
                  ? 'sand'
                  : 'neutral'
              }
            >
              {job.close_position.state}
            </Badge>
          </div>
          <p>{job.close_position.message}</p>
          <small>
            Order {job.close_position.intent_id.slice(0, 12)} · Filled{' '}
            {job.close_position.filled == null ? '—' : number(job.close_position.filled, 8)} /{' '}
            {number(job.close_position.requested ?? 0, 8)} {job.parameters.symbol.split('/')[0]} ·
            Remaining owned {number(job.quantity, 8)} · Realized P&amp;L{' '}
            {number(job.realized_pnl ?? 0, 8)} {quote}
          </small>
        </section>
      )}
      {(job.accounting_incomplete || Object.keys(job.unvalued_fees ?? {}).length > 0) && (
        <p className="monitor-notice">
          Accounting is incomplete or fees use another currency. No further orders are allowed until
          the native evidence can be fully accounted for. Displayed equity excludes unvalued fee
          currencies.
        </p>
      )}
      {job.risk_locked && (
        <p className="monitor-notice">
          The loss guard is latched for this approval. The run cannot resume. Manage existing orders
          and holdings in Trade.
        </p>
      )}
      {job.dust_position && (
        <p className="footnote padded">
          A residual position is below this market’s tradable minimum. It remains owned and valued;
          a later entry may add to it.
        </p>
      )}
      <div className="extended-metrics">
        <div>
          <small>Native fills</small>
          <strong>{job.native_fill_count ?? 0}</strong>
        </div>
        <div>
          <small>Strategy order cap · {quote}</small>
          <strong>{number(job.risk?.max_order_quote ?? 0, 8)}</strong>
        </div>
        <div>
          <small>Loss pause</small>
          <strong>{job.risk?.max_loss_pct}%</strong>
        </div>
        <div>
          <small>Orders / rolling 24h</small>
          <strong>{job.risk?.max_orders_per_day}</strong>
        </div>
        <div>
          <small>Strategy order lifetime</small>
          <strong>
            {job.risk?.order_lifetime_seconds == null
              ? 'GTC · no expiry'
              : `${job.risk.order_lifetime_seconds}s`}
          </strong>
        </div>
      </div>
      <p className="footnote padded">
        Reported fees:{' '}
        {Object.entries(job.fee_assets ?? {})
          .map(([asset, value]) => `${number(value, 8)} ${asset}`)
          .join(' · ') || 'No native fees imported yet'}
        . Completed exits can be partial reductions; their returns use the cost basis of the units
        actually disposed, with residual basis retained.
      </p>
      {!!job.orders?.length && (
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>Order</th>
                <th>State</th>
                <th>Native / client ID</th>
                <th>Filled / requested</th>
                <th>Expiry / cancellation</th>
              </tr>
            </thead>
            <tbody>
              {job.orders.map((order) => (
                <tr key={order.id}>
                  <td>
                    {order.request.side.toUpperCase()}
                    {order.strategy_action === 'close' && (
                      <>
                        {' '}
                        <Badge>Exit</Badge>
                      </>
                    )}
                    <br />
                    <code>{order.id.slice(0, 12)}</code>
                  </td>
                  <td>
                    <Badge>{order.strategy_abandoned ? 'Not submitted' : order.status}</Badge>
                  </td>
                  <td>
                    <code>{order.exchange_order_id || 'Not confirmed'}</code>
                    <br />
                    <small>{order.client_order_id}</small>
                  </td>
                  <td>
                    {order.filled == null ? '—' : number(order.filled, 8)} /{' '}
                    {number(order.request.quantity, 8)}
                  </td>
                  <td>
                    {order.strategy_cancellation ? (
                      <>
                        <Badge
                          tone={
                            ['blocked', 'unknown'].includes(order.strategy_cancellation.state)
                              ? 'sand'
                              : 'neutral'
                          }
                        >
                          {order.strategy_cancellation.state.replaceAll('_', ' ')}
                        </Badge>
                        <small className="table-subline">
                          {order.strategy_cancellation.message}
                        </small>
                        <small className="table-subline">
                          Checked{' '}
                          {new Date(order.strategy_cancellation.checked_at).toLocaleString()}
                          {order.strategy_cancellation.terminal_checks != null &&
                            ` · ${order.strategy_cancellation.terminal_checks}/3 matching status checks`}
                        </small>
                      </>
                    ) : order.strategy_abandoned ||
                      ['closed', 'canceled', 'expired', 'rejected'].includes(order.status) ? (
                      <small>No pending cancellation</small>
                    ) : order.strategy_expires_at ? (
                      <small>
                        Cancellation due {new Date(order.strategy_expires_at).toLocaleString()}
                      </small>
                    ) : (
                      'No automatic expiry'
                    )}
                    {order.cancel_state && !order.strategy_cancellation && (
                      <small className="table-subline">Cancellation: {order.cancel_state}</small>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <p className="footnote padded">
        <Link to="/trade?tab=executions">Manage and reconcile exchange orders in Trade →</Link> ·
        Pause/Stop prevent future submissions; approved expiry still runs. Stop &amp; cancel has a
        separate review and retains holdings. Close position requires its own sell approval. Native
        orders can fill until confirmed terminal.
      </p>
    </Panel>
  );
}

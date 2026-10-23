import { useState } from 'react';
import { Link } from 'react-router-dom';
import { ArrowUpRight, ShieldCheck } from 'lucide-react';
import { Badge, Modal } from '../ui';
import { useResource } from '../../lib/hooks';
import { number, post, refresh } from '../../lib/api';
import type { Connection, Job, StrategyParams } from '../../lib/types';

type Risk = {
  max_order_quote: number;
  max_loss_pct: number;
  max_orders_per_day: number;
  max_spread_bps: number;
  price_limit_bps: number;
  fee_reserve_bps: number;
  order_lifetime_seconds: number | null;
};
type Options = {
  enabled: boolean;
  accounts: (Connection & { supported: boolean })[];
  providers: { id: string; name: string }[];
};
type Review = {
  id: string;
  account: string;
  exchange: string;
  environment: string;
  confirmation: string;
  expires_at: string;
  execution: string;
  request: { parameters: StrategyParams; risk: Risk };
};

/** A collapsed execution setup keeps research simple and requires a separate scoped approval. */
export function ExchangeStrategySetup({
  parameters,
  onStarted,
}: {
  parameters: StrategyParams;
  onStarted: (job: Job) => void;
}) {
  const [open, setOpen] = useState(false);
  const [account, setAccount] = useState('');
  const [pair, setPair] = useState('');
  const [timeframe, setTimeframe] = useState('');
  const [budget, setBudget] = useState(1000);
  const [risk, setRisk] = useState<Risk>({
    max_order_quote: 500,
    max_loss_pct: 10,
    max_orders_per_day: 6,
    max_spread_bps: 50,
    price_limit_bps: 25,
    fee_reserve_bps: 100,
    order_lifetime_seconds: 300,
  });
  const [review, setReview] = useState<Review>();
  const [confirmation, setConfirmation] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const options = useResource<Options>('/strategies/exchange/options', 0, open);
  const markets = useResource<{ symbols: string[]; timeframes: string[] }>(
    `/strategies/exchange/markets/${account}`,
    0,
    open && !!account,
  );
  const symbol = pair || parameters.symbol;
  const interval = timeframe || parameters.timeframe || '1d';
  const quote = symbol.split('/')[1];
  const accounts = options.data?.accounts.filter((row) => row.active && row.supported) ?? [];
  const reviewRun = async () => {
    setBusy(true);
    setError('');
    try {
      const result = await post<Review>('/strategies/exchange/preview', {
        connection_id: account,
        parameters: {
          ...parameters,
          symbol,
          timeframe: interval,
          capital: budget,
          candles: Math.min(parameters.candles, 720),
        },
        risk,
      });
      setConfirmation('');
      setReview(result);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };
  const approve = async () => {
    if (!review) return;
    setBusy(true);
    setError('');
    try {
      const job = await post<Job>(`/strategies/exchange/reviews/${review.id}/start`, {
        confirmation,
      });
      setReview(undefined);
      refresh();
      onStarted(job);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };
  return (
    <details
      className="advanced-options strategy-exchange-setup"
      onToggle={(e) => setOpen(e.currentTarget.open)}
    >
      <summary>
        <ShieldCheck size={15} /> Run on a connected exchange
      </summary>
      <div className="form exchange-setup-fields">
        <p className="footnote">
          Use the algorithm and indicator settings above with a real exchange account. Prices and
          candles come from that exact exchange, independently of the backtest input. Demo paper
          runs remain separate.
        </p>
        {options.loading && <p className="footnote">Checking execution support…</p>}
        {(options.error || markets.error) && (
          <p className="form-error" role="alert">
            {options.error || markets.error}
          </p>
        )}
        {options.data && !accounts.length && (
          <p className="monitor-notice">
            Connect and activate a supported exchange account to use automated execution. You can
            connect several accounts.{' '}
            <Link to="/settings?tab=exchanges">
              Open exchange settings <ArrowUpRight size={12} />
            </Link>
          </p>
        )}
        {options.data && !options.data.enabled && (
          <p className="monitor-notice">
            Execution is disabled on this backend. Both <code>SIBYL_ALLOW_LIVE_TRADING=true</code>{' '}
            and <code>SIBYL_ALLOW_STRATEGY_EXECUTION=true</code> are required, including for
            exchange test environments. Restart the backend after changing them.
          </p>
        )}
        <label>
          Execution account
          <select
            value={account}
            onChange={(e) => {
              setAccount(e.target.value);
              setPair('');
              setTimeframe('');
              setError('');
            }}
          >
            <option value="">Choose an active account</option>
            {accounts.map((row) => (
              <option key={row.id} value={row.id}>
                {row.label} · {row.exchange} · {row.sandbox ? 'Test funds' : 'Real funds'}
              </option>
            ))}
          </select>
        </label>
        {!!account && (
          <>
            <label>
              Exact exchange pair
              <select
                value={markets.data?.symbols.includes(symbol) ? symbol : ''}
                onChange={(e) => setPair(e.target.value)}
                disabled={markets.loading}
              >
                <option value="">Choose a pair on this exchange</option>
                {markets.data?.symbols.map((value) => (
                  <option value={value} key={value}>
                    {value}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Execution timeframe
              <select
                value={markets.data?.timeframes.includes(interval) ? interval : ''}
                onChange={(e) => setTimeframe(e.target.value)}
                disabled={markets.loading}
              >
                <option value="">Choose an interval</option>
                {markets.data?.timeframes
                  .filter((value) =>
                    ['1m', '5m', '15m', '30m', '1h', '4h', '12h', '1d', '1w'].includes(value),
                  )
                  .map((value) => (
                    <option key={value}>{value}</option>
                  ))}
              </select>
            </label>
            <label>
              Allocated budget · {quote}
              <input
                type="number"
                min="0"
                step="any"
                value={budget}
                onChange={(e) => setBudget(Number(e.target.value))}
              />
            </label>
            <label>
              Maximum order value · {quote}
              <input
                type="number"
                min="0"
                step="any"
                value={risk.max_order_quote}
                onChange={(e) => setRisk({ ...risk, max_order_quote: Number(e.target.value) })}
              />
            </label>
            <label>
              Pause at allocated loss · %
              <input
                type="number"
                min="0.1"
                max="90"
                step="any"
                value={risk.max_loss_pct}
                onChange={(e) => setRisk({ ...risk, max_loss_pct: Number(e.target.value) })}
              />
            </label>
            <label>
              Cancel unfilled orders after
              <select
                value={risk.order_lifetime_seconds ?? ''}
                onChange={(event) =>
                  setRisk({
                    ...risk,
                    order_lifetime_seconds: event.target.value ? Number(event.target.value) : null,
                  })
                }
              >
                <option value="">No automatic expiry · GTC</option>
                <option value={60}>1 minute</option>
                <option value={300}>5 minutes</option>
                <option value={900}>15 minutes</option>
                <option value={3600}>1 hour</option>
                <option value={86400}>1 day</option>
              </select>
            </label>
            <p className="footnote">
              Best-effort cancellation by the running backend, not exchange-native expiry. Partial
              fills remain owned. An approved expiry continues while paused or stopped and after
              restart, subject to account access and execution flags.
            </p>
            <details className="advanced-options">
              <summary>Execution limits</summary>
              {(
                [
                  ['max_orders_per_day', 'Orders per rolling 24 hours', 1, 100],
                  ['max_spread_bps', 'Maximum spread · basis points', 1, 500],
                  ['price_limit_bps', 'Limit price allowance · basis points', 1, 200],
                  ['fee_reserve_bps', 'Fee reserve · basis points', 10, 500],
                ] as const
              ).map(([key, label, min, max]) => (
                <label key={key}>
                  {label}
                  <input
                    type="number"
                    min={min}
                    max={max}
                    value={risk[key]}
                    onChange={(e) => setRisk({ ...risk, [key]: Number(e.target.value) })}
                  />
                </label>
              ))}
            </details>
            <p className="footnote">
              Price-capped GTC limits can remain open. One unresolved order blocks the run. Budgets
              are tracked locally and do not reserve exchange funds. Pause/Stop disable future
              orders. Approved expiry can still cancel outstanding orders. Stop &amp; cancel has its
              own review; no control sells positions. Loss guards are not guaranteed stop orders.
            </p>
            <button
              className="button secondary full-width"
              type="button"
              disabled={
                busy ||
                !options.data?.enabled ||
                markets.loading ||
                !!markets.error ||
                !markets.data?.symbols.includes(symbol) ||
                !markets.data?.timeframes.includes(interval) ||
                budget <= 0 ||
                risk.max_order_quote <= 0 ||
                risk.max_order_quote > budget
              }
              onClick={reviewRun}
            >
              <ShieldCheck size={14} />{' '}
              {busy ? 'Checking the account…' : 'Review exchange strategy'}
            </button>
          </>
        )}
        {!!options.data && (
          <p className="footnote">
            Implemented: {options.data.providers.map((row) => row.name).join(', ')}. Account
            permissions and exchange availability are checked when reviewing.
          </p>
        )}
        {error && !review && (
          <p className="form-error" role="alert">
            {error}
          </p>
        )}
      </div>
      {review && (
        <Modal
          title="Approve automated exchange execution"
          onClose={() => !busy && setReview(undefined)}
        >
          <div className="form">
            <Badge tone={review.environment === 'test' ? 'sand' : 'rose'}>
              {review.environment === 'test' ? 'Exchange test funds' : 'Real exchange funds'}
            </Badge>
            <p>
              <strong>{review.account}</strong> · {review.exchange}
              <br />
              {review.request.parameters.strategy} · {review.request.parameters.symbol} ·{' '}
              {review.request.parameters.timeframe}
            </p>
            <p>
              Budget:{' '}
              <strong>
                {number(review.request.parameters.capital, 8)}{' '}
                {review.request.parameters.symbol.split('/')[1]}
              </strong>
              . Each order is capped at {number(review.request.risk.max_order_quote, 8)} in that
              quote asset, excluding fees. At most {review.request.risk.max_orders_per_day} order
              attempts per rolling 24 hours.
            </p>
            <p className="footnote">
              {review.request.risk.order_lifetime_seconds == null
                ? 'No automatic order expiry. '
                : `Cancellation will be requested after ${review.request.risk.order_lifetime_seconds} seconds from each submission attempt. This is best-effort local policy, not guaranteed native expiry. `}
              Loss pause {review.request.risk.max_loss_pct}% · spread limit{' '}
              {review.request.risk.max_spread_bps} bps · price allowance{' '}
              {review.request.risk.price_limit_bps} bps · fee reserve{' '}
              {review.request.risk.fee_reserve_bps} bps. {review.execution}
            </p>
            <p className="monitor-notice">
              This approval allows future orders within this fixed scope without confirming each
              one. The run waits for the next closed candle. Backend restarts pause new submissions.
              Existing holdings are not adopted; dust stays visible. Missing fees or fees outside
              the base/quote assets block further orders.
            </p>
            {review.request.parameters.max_trades != null && (
              <p className="footnote">
                This run stops new submissions after {review.request.parameters.max_trades}{' '}
                completed exit orders, including partial reductions. Residual holdings remain owned.
              </p>
            )}
            <p className="footnote">
              Review expires {new Date(review.expires_at).toLocaleTimeString()}. Manage open orders
              and holdings in Trade. Keep other bots/manual activity separate from this allocated
              budget.
            </p>
            <label>
              Type <strong>{review.confirmation}</strong>
              <input
                value={confirmation}
                onChange={(e) => setConfirmation(e.target.value)}
                autoComplete="off"
              />
            </label>
            {error && (
              <p className="form-error" role="alert">
                {error}
              </p>
            )}
            <button
              className="button primary full-width"
              disabled={busy || confirmation !== review.confirmation}
              onClick={approve}
            >
              {busy ? 'Starting…' : 'Approve & start strategy'}
            </button>
          </div>
        </Modal>
      )}
    </details>
  );
}

import { useState } from 'react';
import { Link } from 'react-router-dom';
import { ArrowUpRight, ShieldCheck } from 'lucide-react';
import { Badge, Modal } from '../ui';
import { number, post, refresh } from '../../lib/api';
import type { Job, StrategyOrderLimits, StrategyParams } from '../../lib/types';
import type { StrategyAccount, StrategyExecutionOptions } from './strategy-account-picker';
import type { ParameterHelp } from './strategy-signal-settings';
import { StrategyField } from './strategy-field';
import type { LimitPolicy } from '../../lib/portfolio-limits';

type Risk = StrategyOrderLimits & {
  risk_per_entry_pct?: number | null;
  max_orders_per_day: number;
  max_spread_bps: number;
  price_limit_bps: number;
  fee_reserve_bps: number;
  order_lifetime_seconds: number | null;
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
  shared_limits: LimitPolicy;
  handoff?: { source_id: string; quantity: number; cost_basis: number; reference_value: number };
};

/** Review and deploy the already selected account, algorithm and exact market. */
export function ExchangeStrategySetup({
  account,
  parameters,
  limits,
  options,
  canDeploy,
  preferredHandoff,
  help,
  onStarted,
}: {
  account: StrategyAccount;
  parameters: StrategyParams;
  limits: StrategyOrderLimits;
  options: StrategyExecutionOptions;
  canDeploy: boolean;
  preferredHandoff?: string;
  help: ParameterHelp;
  onStarted: (job: Job) => void;
}) {
  const [chosenHandoff, setHandoff] = useState(preferredHandoff ?? '');
  const [risk, setRisk] = useState<Omit<Risk, keyof StrategyOrderLimits>>({
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
  const { symbol } = parameters;
  const handoffSources = options.handoff_sources.filter(
    (source) => source.connection_id === account.id && source.symbol === symbol,
  );
  const handoff = handoffSources.some((source) => source.id === chosenHandoff) ? chosenHandoff : '';
  const needsStopLoss = risk.risk_per_entry_pct != null && !parameters.stop_loss_pct;
  const reviewRun = async () => {
    setBusy(true);
    setError('');
    try {
      const result = await post<Review>('/strategies/exchange/preview', {
        connection_id: account.id,
        handoff_from: handoff || null,
        parameters,
        risk: { ...risk, ...limits },
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
    <div className="strategy-exchange-setup">
      <div className="form exchange-setup-fields">
        {!options.server_enabled && (
          <div className="execution-disabled">
            <span className="execution-disabled-icon">
              <ShieldCheck size={20} aria-hidden="true" />
            </span>
            <div className="execution-disabled-copy">
              <strong>Exchange strategy execution is off</strong>
              <p>Turn it on to review and approve a strategy for a connected exchange.</p>
            </div>
            <Link className="button secondary execution-settings-link" to="/settings?tab=workspace">
              Open Workspace settings <ArrowUpRight size={14} />
            </Link>
          </div>
        )}
        {options.controls.halted && (
          <p className="monitor-notice">
            Global halt is active. Release it using the controls above before reviewing a new
            exchange strategy.
          </p>
        )}
        <details className="advanced-options">
          <summary>Advanced execution</summary>
          <StrategyField label="Existing strategy position" caption={help.handoff_from}>
            <select
              aria-label="Position handoff source"
              value={handoff}
              onChange={(e) => setHandoff(e.target.value)}
            >
              <option value="">Start without adopting existing units</option>
              {handoffSources.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.id.slice(0, 8)} · {number(s.quantity, 8)} {symbol.split('/')[0]}
                </option>
              ))}
            </select>
          </StrategyField>
          <StrategyField label="Cancel unfilled orders after" caption={help.order_lifetime_seconds}>
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
          </StrategyField>

          <StrategyField
            label="Modeled entry risk · % of strategy equity · optional"
            caption={help.risk_per_entry_pct}
          >
            <input
              type="number"
              min="0.01"
              max="10"
              step="any"
              value={risk.risk_per_entry_pct ?? ''}
              onChange={(event) =>
                setRisk({
                  ...risk,
                  risk_per_entry_pct: event.target.value ? Number(event.target.value) : null,
                })
              }
            />
            {needsStopLoss && (
              <small className="negative">
                Set a stop loss under Custom exits to use this sizing rule.
              </small>
            )}
          </StrategyField>
          {(
            [
              ['max_orders_per_day', 'Orders per rolling 24 hours', 1, 100],
              ['max_spread_bps', 'Maximum spread · basis points', 1, 500],
              ['price_limit_bps', 'Limit price allowance · basis points', 1, 200],
              ['fee_reserve_bps', 'Fee reserve · basis points', 10, 500],
            ] as const
          ).map(([key, label, min, max]) => (
            <StrategyField key={key} label={label} caption={help[key]}>
              <input
                type="number"
                min={min}
                max={max}
                value={risk[key]}
                onChange={(e) => setRisk({ ...risk, [key]: Number(e.target.value) })}
              />
            </StrategyField>
          ))}
        </details>
        <p className="footnote">
          Candles and prices come from the selected exchange. Each approval is scoped to this
          account, pair and budget.
        </p>
        <button
          className="button primary exchange-run-review"
          type="button"
          disabled={busy || !options.enabled || !canDeploy || needsStopLoss}
          onClick={reviewRun}
        >
          <ShieldCheck size={14} /> {busy ? 'Checking the account…' : 'Review deployment'}
        </button>
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
              {review.request.risk.fee_reserve_bps} bps.{' '}
              {review.request.risk.risk_per_entry_pct != null && (
                <>
                  Modeled entry risk: {review.request.risk.risk_per_entry_pct}% of strategy equity
                  using the configured stop distance.{' '}
                </>
              )}
              {review.execution}
            </p>
            {review.handoff && (
              <p className="monitor-notice">
                Handoff from {review.handoff.source_id.slice(0, 8)}:{' '}
                {number(review.handoff.quantity, 8)} base units · carried basis{' '}
                {number(review.handoff.cost_basis, 8)} · reference capital flow{' '}
                {number(review.handoff.reference_value, 8)} in the pair’s quote asset. The source
                stays stopped; this run receives ownership atomically. Lifetime return statistics
                remain unavailable after this change.
              </p>
            )}
            <p className="monitor-notice">
              This approval allows future orders within this fixed scope without confirming each
              one. The run waits for the next closed candle. Backend restarts pause new submissions.
              {review.handoff
                ? 'Only the explicitly reviewed source position is carried; '
                : 'Existing holdings are not adopted; '}
              dust stays visible. Missing fees or fees outside the base/quote assets block further
              orders.
            </p>
            {review.request.parameters.max_trades != null && (
              <p className="footnote">
                This run stops new submissions after {review.request.parameters.max_trades}{' '}
                completed exit orders, including partial reductions. Residual holdings remain owned.
              </p>
            )}
            <p className="footnote">
              {review.shared_limits.enabled
                ? `Shared limits across this funds environment: ${number(review.shared_limits.max_allocated ?? 0, 2)} USDT allocated capital, ${number(review.shared_limits.max_exposure ?? 0, 2)} USDT gross exposure and ${number(review.shared_limits.max_daily_loss ?? 0, 2)} USDT observed daily loss.`
                : 'Shared portfolio limits are off for this funds environment. Configure them using Portfolio limits above the workspace.'}{' '}
              Per-run limits still apply. Changing shared policy invalidates this unused review.
            </p>
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
    </div>
  );
}

import { useState } from 'react';
import { Link } from 'react-router-dom';
import { Layers3, RefreshCw, ShieldAlert } from 'lucide-react';
import { Badge, Modal, useToast } from '../ui';
import { ExpandableRows } from '../expandable-rows';
import { MarketSourcePicker } from '../market-source-picker';
import { useResource } from '../../lib/hooks';
import { number, post, refresh } from '../../lib/api';
import type { MarketSettings } from '../../lib/types';
import type { PortfolioLimits, PortfolioLimitState } from '../../lib/portfolio-limits';

/** Compact shared controls expand into dated evidence and deliberately saved policy. */
export function PortfolioLimitsButton() {
  const resource = useResource<PortfolioLimits>('/strategies/exchange/limits', 10000);
  const [open, setOpen] = useState(false);
  const [environment, setEnvironment] = useState<'production' | 'test'>('production');
  const settings = useResource<MarketSettings>('/settings/market', 0, open);
  const state = resource.data?.policies.find((policy) => policy.environment === environment);
  const locked = resource.data?.policies.some((policy) => policy.locked);
  return (
    <>
      <button className="button secondary tiny" onClick={() => setOpen(true)}>
        {locked ? <ShieldAlert size={14} /> : <Layers3 size={14} />}
        Portfolio limits{locked ? ' · Locked' : ''}
      </button>
      {open && (
        <Modal title="Portfolio strategy limits" onClose={() => setOpen(false)}>
          <div className="form portfolio-limits">
            <p>One shared budget and risk policy across your exchange strategies.</p>
            <div className="segmented limit-environments" aria-label="Funds environment">
              {(['production', 'test'] as const).map((value) => (
                <button
                  key={value}
                  className={environment === value ? 'selected' : ''}
                  aria-pressed={environment === value}
                  onClick={() => setEnvironment(value)}
                >
                  {value === 'production' ? 'Production' : 'Exchange test funds'}
                </button>
              ))}
            </div>
            <p className="footnote">
              Production and test funds are assessed separately. Manual trades, unrelated holdings
              and paper runs are outside these limits.
            </p>
            {resource.error && (
              <p role="alert" className="form-error">
                {resource.error}{' '}
                <button className="text-button" onClick={resource.retry}>
                  Retry
                </button>
              </p>
            )}
            {!state && !resource.error && <p className="footnote">Loading shared controls…</p>}
            {state && resource.data && (
              <LimitDetails
                key={`${environment}:${state.revision}`}
                state={state}
                current={resource.data}
                settings={settings.data}
                onRefresh={resource.retry}
                onNavigate={() => setOpen(false)}
              />
            )}
          </div>
        </Modal>
      )}
    </>
  );
}

function LimitDetails({
  state,
  current,
  settings,
  onRefresh,
  onNavigate,
}: {
  state: PortfolioLimitState;
  current: PortfolioLimits;
  settings?: MarketSettings;
  onRefresh: () => void;
  onNavigate: () => void;
}) {
  const [policy, setPolicy] = useState(state.policy);
  const [confirmation, setConfirmation] = useState('');
  const [release, setRelease] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const toast = useToast();
  const sample = state.sample;
  const act = async (action: 'save' | 'check' | 'release') => {
    setBusy(true);
    setError('');
    try {
      await post(
        `/strategies/exchange/limits/${state.environment}${action === 'save' ? '' : `/${action}`}`,
        action === 'save'
          ? { ...policy, revision: state.revision, confirmation }
          : action === 'release'
            ? { revision: state.revision, confirmation: release }
            : {},
      );
      refresh();
      onRefresh();
      toast(
        action === 'save'
          ? 'Shared limits saved. Affected runs stay paused for your review.'
          : action === 'release'
            ? 'Loss lock released. Runs remain paused.'
            : 'Portfolio assessment updated.',
      );
    } catch (reason) {
      setError((reason as Error).message);
      onRefresh();
    } finally {
      setBusy(false);
    }
  };
  const utcDay = new Date().toISOString().slice(0, 10);
  return (
    <>
      <div className="limit-status">
        <Badge
          tone={state.locked ? 'rose' : state.fresh && state.policy.enabled ? 'sage' : 'neutral'}
        >
          {state.locked
            ? 'Loss lock active'
            : !state.policy.enabled
              ? 'Shared limits off'
              : state.fresh
                ? 'Assessed'
                : 'Assessment needed'}
        </Badge>
        <button
          className="button secondary tiny"
          disabled={busy || !state.policy.enabled}
          onClick={() => act('check')}
        >
          <RefreshCw size={13} /> {busy ? 'Working…' : 'Refresh assessment'}
        </button>
      </div>
      {state.error && (
        <p role="alert" className="monitor-notice">
          {state.error} Automatic orders are blocked.
        </p>
      )}
      {sample && (
        <>
          <div className="limit-metrics">
            {(
              [
                ['Allocated capital', sample.allocated, state.policy.max_allocated],
                ['Gross exposure', sample.exposure, state.policy.max_exposure],
                ['Observed daily loss', sample.daily_loss, state.policy.max_daily_loss],
                [
                  `${sample.window_hours ?? 24}h observed loss`,
                  sample.window_loss ?? 0,
                  state.policy.max_window_loss,
                ],
              ] as const
            ).map(([label, value, cap]) => (
              <div className={cap && value >= cap ? 'at-limit' : ''} key={label}>
                <span>{label}</span>
                <strong>{number(value, 2)}</strong>
                <small>{cap == null ? 'No shared cap' : `of ${number(cap, 2)} USDT`}</small>
                {cap != null && (
                  <meter min={0} max={cap} value={Math.min(value, cap)} aria-label={label} />
                )}
              </div>
            ))}
          </div>
          <p className="footnote">
            Reference USDT · {sample.source.source_label} · assessed{' '}
            {new Date(sample.as_of).toLocaleString()}
            {!state.fresh && ' · stale or unavailable'}. Exposure includes{' '}
            {number(sample.position, 2)} held + {number(sample.pending_buys, 2)} outstanding buys.
          </p>
          <p className="footnote">
            UTC day {sample.day} · net observed P&amp;L {number(sample.daily_pnl, 2)} USDT. Includes
            unrealized changes and known native fees. First complete assessment this UTC period:{' '}
            {new Date(sample.period_started_at).toLocaleString()}. Later days carry the last
            observed mark; this is not an exact midnight valuation or whole-account return.
          </p>
          {sample.window_started_at && (
            <p className="footnote">
              Rolling window starts at the observed mark{' '}
              {new Date(sample.window_started_at).toLocaleString()}. Gaps carry the preceding mark;
              this is sampled strategy P&amp;L, not an exact window return.
            </p>
          )}
          {!!sample.assets?.length && (
            <details className="advanced-options">
              <summary>Exposure by account &amp; asset</summary>
              <div className="limit-metrics">
                {sample.accounts.map((row) => (
                  <div key={row.id}>
                    <span>{row.label}</span>
                    <strong>{number(row.exposure, 2)}</strong>
                    <small>
                      {state.policy.max_account_exposure == null
                        ? 'No account cap'
                        : `of ${number(state.policy.max_account_exposure, 2)} USDT`}
                    </small>
                  </div>
                ))}
                {sample.assets.map((row) => (
                  <div key={row.asset}>
                    <span>{row.asset}</span>
                    <strong>{number(row.exposure, 2)}</strong>
                    <small>
                      {state.policy.max_asset_exposure == null
                        ? 'No asset cap'
                        : `of ${number(state.policy.max_asset_exposure, 2)} USDT`}
                    </small>
                  </div>
                ))}
              </div>
            </details>
          )}
          {!!sample.runs.length && (
            <details className="advanced-options">
              <summary>Contributions · {sample.runs.length} retained runs</summary>
              <ExpandableRows total={sample.runs.length} label="runs">
                {(count) => (
                  <div className="table-wrap">
                    <table className="data-table limit-run-table">
                      <thead>
                        <tr>
                          <th>Run</th>
                          <th>Allocated</th>
                          <th>Held</th>
                          <th>Pending buys</th>
                        </tr>
                      </thead>
                      <tbody>
                        {sample.runs.slice(0, count).map((row) => (
                          <tr key={row.id}>
                            <td>
                              <Link
                                onClick={onNavigate}
                                to={`/strategies?view=monitor&job=${row.id}`}
                              >
                                {row.symbol} ↗
                              </Link>
                              <small>
                                {row.account} · {row.status}
                              </small>
                            </td>
                            <td>{number(row.allocated, 2)}</td>
                            <td>{number(row.position, 2)}</td>
                            <td>{number(row.pending_buys, 2)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </ExpandableRows>
            </details>
          )}
          <details className="advanced-options">
            <summary>Reference prices &amp; paths</summary>
            <ul className="limit-price-list">
              {Object.entries(sample.rates).map(([asset, rate]) => (
                <li key={asset}>
                  <strong>{asset}</strong>
                  <span>{number(rate.price, 8)} USDT</span>
                  <small>
                    {rate.path.join(' → ')} ·{' '}
                    {rate.observed_at
                      ? new Date(rate.observed_at).toLocaleString()
                      : 'Denomination identity'}
                  </small>
                </li>
              ))}
            </ul>
          </details>
        </>
      )}
      {state.locked && (
        <div className="limit-lock form">
          <strong>
            {state.window_locked_until ? 'Rolling-loss' : 'Daily-loss'} limit reached ·{' '}
            {state.tripped_day}
          </strong>
          <p>
            Affected exchange strategies are paused. Existing orders can still fill. Review orders
            and holdings before taking action; no liquidation or cancellation was requested.
          </p>
          {(
            state.window_locked_until
              ? new Date(state.window_locked_until).getTime() <= Date.now()
              : state.tripped_day && state.tripped_day < utcDay
          ) ? (
            <>
              <label>
                Type {current.release_confirmation}
                <input
                  value={release}
                  onChange={(e) => setRelease(e.target.value)}
                  autoComplete="off"
                />
              </label>
              <button
                className="button secondary"
                disabled={busy || release !== current.release_confirmation}
                onClick={() => act('release')}
              >
                Assess &amp; release · keep runs paused
              </button>
            </>
          ) : (
            <p className="footnote">
              This lock can be reviewed after its recorded release time (next UTC day for daily
              loss, or after the rolling window). Restarting or raising limits does not clear it.
              Separately reviewed exits and cancellations remain available.
            </p>
          )}
        </div>
      )}
      <details className="advanced-options" open={!state.policy.enabled}>
        <summary>{state.policy.enabled ? 'Edit shared policy' : 'Set shared limits'}</summary>
        <form
          className="form"
          onSubmit={(e) => {
            e.preventDefault();
            act('save');
          }}
        >
          <label className="checkbox-label">
            <input
              type="checkbox"
              checked={policy.enabled}
              disabled={state.locked}
              onChange={(e) => setPolicy({ ...policy, enabled: e.target.checked })}
            />
            Enable limits for{' '}
            {state.environment === 'test' ? 'exchange test funds' : 'production funds'}
          </label>
          {settings && (
            <MarketSourcePicker
              settings={{
                ...settings,
                catalog: settings.catalog.filter(
                  (source) => source.environment === 'production' && source.id !== 'demo',
                ),
              }}
              value={policy.source}
              onChange={(source) => setPolicy({ ...policy, source })}
            />
          )}
          {(
            [
              ['max_allocated', 'Maximum allocated capital'],
              ['max_exposure', 'Maximum gross exposure'],
              ['max_daily_loss', 'Maximum daily loss'],
              ['max_account_exposure', 'Maximum exposure per account · optional'],
              ['max_asset_exposure', 'Maximum exposure per base asset · optional'],
              ['max_window_loss', 'Maximum rolling-window loss · optional'],
            ] as const
          ).map(([key, label]) => (
            <label key={key}>
              {label} · reference USDT
              <input
                type="number"
                min="0.00000001"
                max="1000000000000"
                step="any"
                required={
                  policy.enabled &&
                  ['max_allocated', 'max_exposure', 'max_daily_loss'].includes(key)
                }
                value={policy[key] ?? ''}
                onChange={(e) =>
                  setPolicy({
                    ...policy,
                    [key]: e.target.value === '' ? null : Number(e.target.value),
                  })
                }
              />
            </label>
          ))}
          <label>
            Rolling-loss window
            <select
              value={policy.loss_window_hours ?? 24}
              onChange={(event) =>
                setPolicy({ ...policy, loss_window_hours: Number(event.target.value) })
              }
            >
              {[1, 4, 12, 24, 48, 72, 168].map((hours) => (
                <option value={hours} key={hours}>
                  {hours} hours
                </option>
              ))}
            </select>
          </label>
          <p className="footnote">
            Account and asset caps include held positions and outstanding buys across retained runs.
            A rolling-loss breach pauses runs and stays locked for its recorded window; release also
            requires a fresh assessment below the cap. UTC daily limits remain independent.
          </p>
          <p className="footnote">
            Allocated capital includes active/paused approvals and terminal runs retaining positions
            or unresolved orders. Outstanding buys consume exposure; pending sells do not release
            it. New buys are refused at the exposure cap; automatic sells retain their other checks.
          </p>
          <p className="monitor-notice">
            Saving changes pauses affected runs and invalidates unused start reviews. Assess, then
            Resume each deliberately. Limits do not reserve exchange funds or guarantee a maximum
            loss.
          </p>
          <label>
            Type {current.save_confirmation}
            <input
              value={confirmation}
              autoComplete="off"
              onChange={(e) => setConfirmation(e.target.value)}
            />
          </label>
          <button
            className="button primary full-width"
            disabled={busy || confirmation !== current.save_confirmation}
          >
            Save shared limits · pause affected runs
          </button>
        </form>
      </details>
      {error && (
        <p className="form-error" role="alert">
          {error}
        </p>
      )}
      <details className="advanced-options">
        <summary>Policy &amp; lock history</summary>
        {!state.history.length && <p className="footnote">No policy changes recorded yet.</p>}
        <ol className="strategy-control-history">
          {state.history.map((entry) => (
            <li key={entry.id}>
              <div>
                <strong>{entry.action.replaceAll('_', ' ')}</strong>
                <time>{new Date(entry.timestamp).toLocaleString()}</time>
              </div>
              <p>
                {entry.reason} {entry.paused_job_ids.length} runs paused.
              </p>
            </li>
          ))}
        </ol>
        <p className="footnote">Newest 20 events shown; 200 retained per environment.</p>
      </details>
    </>
  );
}

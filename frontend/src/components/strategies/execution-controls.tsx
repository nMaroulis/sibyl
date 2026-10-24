import { useState } from 'react';
import { Link } from 'react-router-dom';
import { CirclePause, ShieldCheck, SlidersHorizontal } from 'lucide-react';
import { Badge, Modal, useToast } from '../ui';
import { post, refresh } from '../../lib/api';
import { useResource } from '../../lib/hooks';
import type { StrategyControl } from '../../lib/strategy-controls';

/** A workspace-wide pause with durable history and a deliberate, separate release. */
export function ExecutionControls() {
  const resource = useResource<StrategyControl>('/strategies/exchange/controls', 5000);
  const [review, setReview] = useState<StrategyControl>();
  const [confirmation, setConfirmation] = useState('');
  const [reason, setReason] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const toast = useToast();
  const state = resource.data;
  const change = async (action: 'halt' | 'release', snapshot: StrategyControl) => {
    setBusy(true);
    setError('');
    try {
      await post('/strategies/exchange/controls', {
        action,
        revision: snapshot.revision,
        confirmation: action === 'release' ? confirmation : '',
        reason: action === 'release' ? reason : 'Halted from the strategy workspace.',
      });
      setReview(undefined);
      refresh();
      toast(
        action === 'halt'
          ? 'Exchange automation halted. Existing orders and holdings remain at the exchange.'
          : 'Halt released. Runs stay paused until you review and Resume each one.',
      );
    } catch (e) {
      setError((e as Error).message);
      resource.retry();
    } finally {
      setBusy(false);
    }
  };
  const open = () => {
    if (!state) return;
    setReview(state);
    setConfirmation('');
    setReason('');
    setError('');
  };
  return (
    <section
      className={`strategy-controls ${state?.halted ? 'is-halted' : ''}`}
      aria-label="Exchange automation controls"
    >
      <div className="strategy-control-summary">
        <span className="strategy-control-symbol">
          {state?.halted ? <CirclePause size={20} /> : <ShieldCheck size={20} />}
        </span>
        <div>
          <strong>{state?.halted ? 'Exchange automation halted' : 'Exchange automation'}</strong>
          <p>
            {state?.halted
              ? 'New strategy orders are blocked across all accounts. Existing orders and holdings remain live.'
              : state?.server_enabled
                ? 'One control to pause strategy submissions across every exchange account.'
                : 'Strategy submissions are disabled by backend settings. Paper research is available.'}
          </p>
        </div>
      </div>
      <div className="strategy-control-actions">
        <Badge tone={state?.halted ? 'rose' : 'neutral'}>
          {!state
            ? 'Checking…'
            : state.halted
              ? 'Halt active'
              : `${state.exchange_runs.running ?? 0} running`}
        </Badge>
        {state && !state.halted && (
          <button
            className="button secondary tiny monitor-stop"
            disabled={busy || !!resource.error}
            onClick={() => change('halt', state)}
          >
            <CirclePause size={14} /> {busy ? 'Requesting halt…' : 'Halt automation'}
          </button>
        )}
        <button className="button secondary tiny" disabled={!state || busy} onClick={open}>
          <SlidersHorizontal size={13} /> {state?.halted ? 'Review & release' : 'Controls'}
        </button>
      </div>
      {(resource.error || (error && !review)) && (
        <p className="form-error" role="alert">
          {resource.error || error}{' '}
          <button className="text-button" onClick={resource.retry}>
            Refresh controls
          </button>
        </p>
      )}
      {review && (
        <Modal title="Exchange automation controls" onClose={() => !busy && setReview(undefined)}>
          <div className="form">
            <Badge tone={state?.halted ? 'rose' : 'neutral'}>
              {state?.halted ? 'Global halt active' : 'Global halt released'}
            </Badge>
            <p>
              A halt blocks new automated strategy orders and pauses running exchange strategies,
              including test environments. It survives a backend restart.
            </p>
            <p className="monitor-notice">
              Already admitted orders can finish before the halt returns. Venue orders may still
              fill. Approved expiry and cancellation policies continue; manual Trade orders and
              separately reviewed position exits remain available. Paper runs are unaffected.
            </p>
            {state?.reason && <p className="footnote">Latest note: {state.reason}</p>}
            {review.revision !== state?.revision && (
              <p className="form-error" role="alert">
                Controls changed while this dialog was open. Close and reopen it to review the
                current state.
              </p>
            )}
            {review.halted && (
              <>
                <p>
                  Releasing allows new reviews and individual Resumes. Every paused run stays
                  paused; old start reviews and unsent signal orders remain invalid.
                </p>
                <label>
                  Release note · optional
                  <input
                    value={reason}
                    maxLength={240}
                    onChange={(e) => setReason(e.target.value)}
                  />
                </label>
                <label>
                  Type <strong>{review.release_confirmation}</strong>
                  <input
                    value={confirmation}
                    onChange={(e) => setConfirmation(e.target.value)}
                    autoComplete="off"
                  />
                </label>
                <button
                  className="button primary full-width"
                  disabled={
                    busy ||
                    !!resource.error ||
                    review.revision !== state?.revision ||
                    confirmation !== review.release_confirmation
                  }
                  onClick={() => change('release', review)}
                >
                  {busy ? 'Releasing…' : 'Release halt · keep runs paused'}
                </button>
              </>
            )}
            {error && (
              <p className="form-error" role="alert">
                {error}
              </p>
            )}
            <details className="advanced-options" open>
              <summary>Control history</summary>
              <p className="footnote">
                Newest {review.history_limit} changes · newest {review.history_retention} retained
                locally. Times are shown in your local time. This history does not confirm native
                order outcomes.
              </p>
              {!state?.history.length && (
                <p className="footnote">No control changes recorded yet.</p>
              )}
              <ol className="strategy-control-history">
                {state?.history.map((entry) => (
                  <li key={entry.revision}>
                    <div>
                      <strong>
                        {entry.action === 'halt' ? 'Automation halted' : 'Halt released'}
                      </strong>
                      <time>{new Date(entry.changed_at).toLocaleString()}</time>
                    </div>
                    <p>
                      {entry.action === 'halt'
                        ? `${entry.paused_count} exchange runs paused.`
                        : 'No runs resumed automatically.'}{' '}
                      {entry.reason}
                    </p>
                    {!!entry.paused_job_ids.length && (
                      <div className="strategy-control-job-links">
                        {entry.paused_job_ids.map((id) => (
                          <Link
                            key={id}
                            to={`/strategies?view=monitor&job=${encodeURIComponent(id)}`}
                            onClick={() => setReview(undefined)}
                          >
                            Run {id.slice(0, 8)} ↗
                          </Link>
                        ))}
                      </div>
                    )}
                  </li>
                ))}
              </ol>
            </details>
          </div>
        </Modal>
      )}
    </section>
  );
}

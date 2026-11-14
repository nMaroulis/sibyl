import { useState } from 'react';
import { ArrowDownLeft, ArrowUpRight, Layers3, RefreshCw, Scale } from 'lucide-react';
import { Link } from 'react-router-dom';
import { Badge, Modal, Panel } from '../ui';
import { useResource } from '../../lib/hooks';
import { number, post, refresh } from '../../lib/api';
import type { Job } from '../../lib/types';
import '../../styles/position-ownership.css';

type Receipt = {
  id: string;
  action: string;
  quantity: number;
  cost_basis: number;
  reference_value: number;
  created_at: string;
  note: string;
  peer_id?: string;
};
type Check = {
  total: number;
  free: number;
  strategy_owned: number;
  unassigned: number;
  shortfall: number;
  dust: boolean;
  amount_min?: number;
  cost_min?: number;
  observed_at: string;
  current: boolean;
  coverage_incomplete: boolean;
  owners: { id: string; symbol: string; quantity: number; status: string }[];
  unattributed_fills: {
    id: string;
    symbol: string;
    side: string;
    quantity: number;
    created_at: string;
  }[];
};
type State = {
  quantity: number;
  entry_cost: number;
  net_reference_flow: number;
  stale: boolean;
  history: Receipt[];
  event_count: number;
  check?: Check;
};
type Review = {
  id: string;
  confirmation: string;
  cost_basis: number;
  reference_bid: number;
  native_total: number;
  native_free: number;
  expires_at: string;
  request: { action: string; quantity: number; cost_basis?: number; note: string };
};

/** Native balances are fetched only on request; every local attribution has its own typed review. */
export function PositionOwnership({ job }: { job: Job }) {
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState<'adopt' | 'release'>();
  const [quantity, setQuantity] = useState('');
  const [basis, setBasis] = useState('');
  const [note, setNote] = useState('');
  const [busy, setBusy] = useState('');
  const [error, setError] = useState('');
  const [review, setReview] = useState<Review>();
  const [confirmation, setConfirmation] = useState('');
  const state = useResource<State>(`/strategies/exchange/jobs/${job.id}/ownership`, 5000, open);
  const data = state.data;
  const check = data?.check;
  const [base, quote] = job.parameters.symbol.split('/');
  const terminal = ['stopped', 'completed'].includes(job.status);
  const act = async (action: 'check' | 'preview' | 'confirm') => {
    setBusy(action);
    setError('');
    try {
      if (action === 'check') await post(`/strategies/exchange/jobs/${job.id}/ownership/check`, {});
      if (action === 'preview') {
        const value = await post<Review>(`/strategies/exchange/jobs/${job.id}/ownership/preview`, {
          action: editing,
          quantity: Number(quantity),
          cost_basis: editing === 'adopt' ? Number(basis) : null,
          note,
        });
        setReview(value);
        setConfirmation('');
      }
      if (action === 'confirm' && review) {
        await post(`/strategies/exchange/ownership-reviews/${review.id}/confirm`, { confirmation });
        setReview(undefined);
        setEditing(undefined);
        refresh();
      }
      state.retry();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy('');
    }
  };
  const edit = (action: 'adopt' | 'release') => {
    setEditing(action);
    setQuantity('');
    setBasis('');
    setNote('');
    setError('');
    setReview(undefined);
  };
  return (
    <Panel className="full-panel position-ownership">
      <div className="ownership-heading">
        <button className="ownership-expand" aria-expanded={open} onClick={() => setOpen(!open)}>
          <span className="ownership-icon">
            <Layers3 size={18} />
          </span>
          <span>
            <strong>Position ownership</strong>
            <small>Native balances, residuals & reviewed attribution</small>
          </span>
        </button>
        {job.ownership_stale && <Badge tone="sand">Evidence changed</Badge>}
        <button
          className="button secondary tiny"
          disabled={!!busy}
          onClick={() => {
            setOpen(true);
            void act('check');
          }}
        >
          <RefreshCw size={13} className={busy === 'check' ? 'spin' : ''} />
          {busy === 'check' ? 'Checking…' : 'Check exchange balance'}
        </button>
      </div>
      {open && (
        <div className="ownership-body">
          {(error || state.error) && (
            <p className="form-error" role="alert">
              {error || state.error}
            </p>
          )}
          {data?.stale && (
            <p className="monitor-notice">
              An earlier native fill or source handoff changed. Execution is blocked. Inspect the
              linked source and Trade evidence; this receipt cannot silently rewrite corrected
              history.
            </p>
          )}
          {check ? (
            <>
              <div className="ownership-facts">
                {[
                  ['Exchange total', check.total],
                  ['All strategy owners', check.strategy_owned],
                  ['Unassigned units', check.unassigned],
                  ['This run', data?.quantity ?? job.quantity],
                ].map(([label, value]) => (
                  <div key={String(label)}>
                    <small>{label}</small>
                    <strong>
                      {number(Number(value), 8)} <span>{base}</span>
                    </strong>
                  </div>
                ))}
              </div>
              <div className="ownership-check-caption">
                <Badge
                  tone={check.shortfall > 1e-10 || check.coverage_incomplete ? 'sand' : 'neutral'}
                >
                  {check.shortfall > 1e-10
                    ? `${number(check.shortfall, 8)} ${base} shortfall`
                    : check.coverage_incomplete
                      ? 'Incomplete ownership evidence'
                      : 'No observed shortfall'}
                </Badge>
                <Badge>
                  {check.dust
                    ? 'Below tradable minimum / precision'
                    : data?.quantity
                      ? 'Above observed dust limits'
                      : 'No position'}
                </Badge>
                <small>
                  Checked {new Date(check.observed_at).toLocaleString()}
                  {!check.current && ' · Ledger changed; check again'}
                </small>
              </div>
              <p className="footnote">
                Free: {number(check.free, 8)} {base}. Native minimums:{' '}
                {check.amount_min == null
                  ? 'amount not reported'
                  : `${number(check.amount_min, 8)} ${base}`}{' '}
                ·{' '}
                {check.cost_min == null
                  ? 'notional not reported'
                  : `${number(check.cost_min, 8)} ${quote}`}
                . Dust uses the exact exchange pair, amount precision and observed bid; a sell still
                requires its separate review.
              </p>
              {!!check.unattributed_fills.length && (
                <details className="advanced-options">
                  <summary>
                    {check.unattributed_fills.length} recent fills outside strategy orders
                  </summary>
                  <p className="footnote">
                    These may explain balance changes, but do not establish which run owns them.
                    History import coverage can be incomplete.
                  </p>
                  {check.unattributed_fills.map((f) => (
                    <p className="ownership-history-row" key={f.id}>
                      <span>
                        {f.side.toUpperCase()} {number(f.quantity, 8)} · {f.symbol}
                      </span>
                      <small>{new Date(f.created_at).toLocaleString()}</small>
                    </p>
                  ))}
                </details>
              )}
            </>
          ) : (
            <p className="footnote">
              Check the exchange to compare balances with all strategy owners of {base} on this
              account. Excess units can be manual holdings or transfers; Sibyl does not infer their
              origin.
            </p>
          )}
          <div className="ownership-actions">
            <button
              className="button secondary tiny"
              disabled={!!busy || job.status !== 'paused' || !!data?.stale}
              onClick={() => edit('adopt')}
            >
              <ArrowDownLeft size={14} />
              Adopt existing units
            </button>
            <button
              className="button secondary tiny"
              disabled={!!busy || !terminal || !data?.quantity || !!data?.stale}
              onClick={() => edit('release')}
            >
              <ArrowUpRight size={14} />
              Release to unmanaged
            </button>
            {terminal && !!data?.quantity && (
              <Link
                className="text-link"
                to={`/strategies?view=studio&handoff=${encodeURIComponent(job.id)}`}
              >
                Hand off to a new run →
              </Link>
            )}
          </div>
          <p className="footnote">
            Pause to adopt free, unassigned units with an asserted total cost basis. Stop to release
            recorded units. These change local attribution only: no sale, transfer, quote proceeds
            or automatic resume. A handoff carries original basis during a new run’s approval.
          </p>
          {!!data?.history.length && (
            <details className="advanced-options">
              <summary>
                {data.event_count} ownership receipt{data.event_count === 1 ? '' : 's'}
              </summary>
              {[...data.history].reverse().map((r) => (
                <div className="ownership-receipt" key={r.id}>
                  <div>
                    <Badge>{r.action.replaceAll('_', ' ')}</Badge>
                    <small>{new Date(r.created_at).toLocaleString()}</small>
                  </div>
                  <p>
                    {number(r.quantity, 8)} {base} · basis {number(r.cost_basis, 8)} {quote} ·
                    reference flow {number(r.reference_value, 8)} {quote}
                  </p>
                  <small>{r.note}</small>
                  {r.peer_id && (
                    <Link
                      className="text-link"
                      to={`/strategies?view=monitor&job=${encodeURIComponent(r.peer_id)}`}
                    >
                      Related run {r.peer_id.slice(0, 8)} →
                    </Link>
                  )}
                </div>
              ))}
            </details>
          )}
        </div>
      )}
      {editing && (
        <Modal
          title={
            review
              ? 'Review local ownership change'
              : editing === 'adopt'
                ? 'Adopt existing account units'
                : 'Release strategy ownership'
          }
          onClose={() => {
            if (!busy) {
              setEditing(undefined);
              setReview(undefined);
              setError('');
            }
          }}
        >
          <div className="form">
            <p className="footnote">
              <Scale size={14} /> {job.account} · {job.parameters.symbol}. This records attribution
              without moving exchange funds.
            </p>
            {error && (
              <p className="form-error" role="alert">
                {error}
              </p>
            )}
            {review ? (
              <>
                <div className="ownership-review">
                  <strong>
                    {review.request.action === 'adopt' ? 'Adopt' : 'Release'}{' '}
                    {number(review.request.quantity, 8)} {base}
                  </strong>
                  <span>
                    Total {review.request.action === 'adopt' ? 'asserted' : 'carried'} basis:{' '}
                    {number(review.cost_basis, 8)} {quote}
                  </span>
                  <span>
                    Reference bid: {number(review.reference_bid, 8)} {quote}
                  </span>
                  <small>{review.request.note}</small>
                </div>
                <p className="monitor-notice">
                  No exchange order will be placed and cash stays unchanged. Local capital-flow
                  adjustments keep this change out of trading profit. Lifetime percentage returns
                  remain unavailable after attribution. Review expires{' '}
                  {new Date(review.expires_at).toLocaleTimeString()}.
                </p>
                <label>
                  Type <strong>{review.confirmation}</strong>
                  <input
                    autoComplete="off"
                    value={confirmation}
                    onChange={(e) => setConfirmation(e.target.value)}
                  />
                </label>
                <div className="ownership-actions">
                  <button
                    className="button secondary"
                    disabled={!!busy}
                    onClick={() => setReview(undefined)}
                  >
                    Back
                  </button>
                  <button
                    className="button primary"
                    disabled={!!busy || confirmation !== review.confirmation}
                    onClick={() => void act('confirm')}
                  >
                    {busy === 'confirm' ? 'Recording…' : 'Confirm local change'}
                  </button>
                </div>
              </>
            ) : (
              <>
                <label>
                  Quantity · {base}
                  <input
                    aria-label="Ownership quantity"
                    type="number"
                    min="0"
                    step="any"
                    value={quantity}
                    onChange={(e) => setQuantity(e.target.value)}
                  />
                </label>
                {editing === 'adopt' && (
                  <label>
                    Asserted total cost basis · {quote}
                    <input
                      aria-label="Ownership total cost basis"
                      type="number"
                      min="0"
                      step="any"
                      value={basis}
                      onChange={(e) => setBasis(e.target.value)}
                    />
                    <small>
                      Total acquisition cost of these units, not the price per coin. This is your
                      assertion, not verified exchange history.
                    </small>
                  </label>
                )}
                <label>
                  Reason
                  <textarea
                    value={note}
                    onChange={(e) => setNote(e.target.value)}
                    maxLength={500}
                  />
                </label>
                <p className="footnote">
                  The review reads fresh balances, all base-asset owners and the exact pair’s book.
                  Pending orders, uncertain fees or changed evidence block the change.
                </p>
                <button
                  className="button primary"
                  disabled={
                    !!busy ||
                    !(Number(quantity) > 0) ||
                    !note.trim() ||
                    (editing === 'adopt' && (basis === '' || Number(basis) < 0))
                  }
                  onClick={() => void act('preview')}
                >
                  {busy === 'preview' ? 'Checking native evidence…' : 'Review ownership change'}
                </button>
              </>
            )}
          </div>
        </Modal>
      )}
    </Panel>
  );
}

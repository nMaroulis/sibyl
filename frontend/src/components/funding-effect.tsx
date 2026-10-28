import { useState } from 'react';
import { createPortal } from 'react-dom';
import type { FormEvent } from 'react';
import { Link } from 'react-router-dom';
import { ArrowUpRight, History, ScanLine } from 'lucide-react';
import { post, refresh } from '../lib/api';
import { useResource } from '../lib/hooks';
import { Badge, ErrorState, Loading, Modal, useToast } from './ui';

export type FundingEffect = {
  source_version: string;
  quantity: string | null;
  provenance: string;
  rule: string | null;
  source_url: string | null;
  wallet_scope: string;
  review_id: string | null;
  review_status: string | null;
  reviewable: boolean;
  reason: string;
};
type Decision = {
  wallet_scope: string;
  amount_convention: string | null;
  fee_quantity: string | null;
};
type Review = {
  id: string;
  action: string;
  source_version: string;
  decision: Decision | null;
  note: string;
  created_at: string;
};
type ReviewState = {
  event: {
    id: string;
    account: string;
    environment: string;
    asset: string;
    quantity: number;
    posted_ms?: number | null;
    direction: string;
    wallet_scope?: string;
    fee_known: boolean;
    fee: { currency: string | null; cost: number | null };
  };
  balance_effect: FundingEffect;
  history: Review[];
};

/** A separate local assertion; original provider amounts and fees remain visible. */
export function FundingEffectCell({
  id,
  asset,
  effect,
  example,
}: {
  id: string;
  asset: string;
  effect?: FundingEffect;
  example: boolean;
}) {
  const [open, setOpen] = useState(false);
  if (!effect) return <span className="muted">Unavailable</span>;
  const reviewed = effect.provenance === 'user_review';
  return (
    <>
      <strong className="monetary">
        {effect.quantity === null
          ? 'Unresolved'
          : `${Number(effect.quantity) > 0 ? '+' : ''}${effect.quantity} ${asset}`}
      </strong>
      <small>
        <Badge tone={reviewed ? 'peach' : effect.quantity !== null ? 'lime' : 'neutral'}>
          {reviewed
            ? 'Your review'
            : effect.provenance === 'provider'
              ? 'Provider rule'
              : effect.provenance === 'not_applied'
                ? 'Not applied'
                : effect.reviewable
                  ? 'Needs review'
                  : 'Unresolved'}
        </Badge>
      </small>
      <small>
        {effect.wallet_scope === 'outside'
          ? 'Outside configured wallet'
          : effect.wallet_scope === 'configured'
            ? 'Configured wallet'
            : 'Wallet unknown'}
      </small>
      {effect.quantity === null && <small className="funding-effect-reason">{effect.reason}</small>}
      {effect.source_url && (
        <small>
          <a href={effect.source_url} target="_blank" rel="noreferrer">
            Rule source <ArrowUpRight size={10} />
          </a>
        </small>
      )}
      {!example && (effect.reviewable || effect.review_id) && (
        <button className="text-link funding-review-link" onClick={() => setOpen(true)}>
          <ScanLine size={12} />{' '}
          {effect.review_status === 'stale'
            ? 'Review changed source'
            : effect.review_id
              ? 'View review'
              : 'Review balance effect'}
        </button>
      )}
      {example && effect.reviewable && (
        <small>Local reviews are available on imported records.</small>
      )}
      {open &&
        createPortal(
          <Modal
            title="Review funding balance effect"
            onClose={() => setOpen(false)}
            className="funding-review-modal"
          >
            <ReviewDialog id={id} />
          </Modal>,
          document.body,
        )}
    </>
  );
}

function ReviewDialog({ id }: { id: string }) {
  const state = useResource<ReviewState>(
    `/account-ledger/funding/${encodeURIComponent(id)}/review`,
  );
  return state.error ? (
    <ErrorState message={state.error} retry={state.retry} />
  ) : !state.data ? (
    <Loading />
  ) : (
    <ReviewForm
      key={`${state.data.balance_effect.source_version}:${state.data.balance_effect.review_id}`}
      state={state.data}
      reload={state.retry}
    />
  );
}

function ReviewForm({ state, reload }: { state: ReviewState; reload: () => void }) {
  const { event, balance_effect: effect, history } = state;
  const latest = history[0];
  const decision = effect.review_status === 'current' ? latest?.decision : null;
  const [scope, setScope] = useState(
    decision?.wallet_scope || (event.wallet_scope !== 'unknown' ? event.wallet_scope || '' : ''),
  );
  const [convention, setConvention] = useState(decision?.amount_convention || '');
  const [fee, setFee] = useState(decision?.fee_quantity || '');
  const [note, setNote] = useState(effect.review_status === 'current' ? latest?.note || '' : '');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const toast = useToast();
  const outside = scope === 'outside';
  async function submit(withdraw = false) {
    setBusy(true);
    setError('');
    try {
      await post(
        `/account-ledger/funding/${encodeURIComponent(event.id)}/review${withdraw ? '/withdraw' : ''}`,
        {
          source_version: effect.source_version,
          replace_id: effect.review_id,
          ...(!withdraw
            ? {
                wallet_scope: scope,
                amount_convention: outside ? null : convention,
                fee_quantity: outside || event.fee_known ? null : fee,
                note,
              }
            : {}),
        },
      );
      toast(
        withdraw
          ? 'Review withdrawn. Original exchange data preserved.'
          : 'Local balance review saved. No funds moved.',
      );
      refresh();
      reload();
    } catch (reason) {
      setError((reason as Error).message);
    } finally {
      setBusy(false);
    }
  }
  function save(e: FormEvent) {
    e.preventDefault();
    void submit();
  }
  return (
    <div className="funding-review-content">
      <p className="muted">
        {event.account} · {event.environment} · {event.direction === 'out' ? 'Sent' : 'Received'}{' '}
        {event.quantity} {event.asset}
      </p>
      <div className="funding-review-evidence">
        <ScanLine size={19} />
        <div>
          <strong>
            {effect.quantity === null
              ? 'Balance effect unresolved'
              : `${effect.quantity} ${event.asset}`}
          </strong>
          <p>{effect.reason}</p>
        </div>
      </div>
      {effect.review_status === 'stale' && (
        <p role="status" className="field-warning">
          The exchange record changed. The previous decision is retained for reference and is no
          longer applied.
        </p>
      )}
      <p>
        Your choice applies only to this record in Balance checks. It does not establish an
        own-account transfer, cost basis or investment return. Verify the wallet and fee against
        your exchange statement.
      </p>
      {!event.posted_ms && (
        <p className="footnote">
          The provider's balance-posting time is unavailable. You can review the amount convention,
          but Balance checks will keep its timing unresolved. Rescan the imported range to retrieve
          any newer provider fields.
        </p>
      )}
      {effect.reviewable && (
        <form onSubmit={save} className="funding-review-form">
          <label>
            Wallet affected
            <select
              required
              value={scope}
              disabled={
                busy || (event.wallet_scope !== undefined && event.wallet_scope !== 'unknown')
              }
              onChange={(e) => setScope(e.target.value)}
            >
              <option value="" disabled>
                Choose a wallet scope
              </option>
              <option value="configured">The wallet Sibyl reads for this account</option>
              <option value="outside">Another wallet, outside this account's balance scope</option>
            </select>
          </label>
          {!outside && (
            <>
              <label>
                What does the reported amount represent?
                <select
                  required
                  value={convention}
                  disabled={busy}
                  onChange={(e) => setConvention(e.target.value)}
                >
                  <option value="" disabled>
                    Choose the verified convention
                  </option>
                  {event.direction === 'out' ? (
                    <>
                      <option value="total_debit">Total removed, including the fee</option>
                      <option value="principal">Amount sent; the fee was charged on top</option>
                    </>
                  ) : (
                    <>
                      <option value="net_credit">Amount credited, after any fee</option>
                      <option value="gross_receipt">Amount before the fee was deducted</option>
                    </>
                  )}
                </select>
              </label>
              {event.fee_known ? (
                <p>
                  Reported fee:{' '}
                  <strong>
                    {event.fee.cost} {event.fee.currency}
                  </strong>
                  . This provider fact cannot be overridden.
                </p>
              ) : (
                <label>
                  Verified fee in {event.asset}
                  <input
                    type="number"
                    min="0"
                    step="any"
                    required
                    value={fee}
                    disabled={busy}
                    onChange={(e) => setFee(e.target.value)}
                  />
                  <small>
                    Enter zero only if you verified there was no fee. This is saved as your
                    assertion.
                  </small>
                </label>
              )}
            </>
          )}
          <label>
            Evidence reviewed
            <textarea
              required
              maxLength={1000}
              rows={3}
              value={note}
              disabled={busy}
              onChange={(e) => setNote(e.target.value)}
              placeholder="For example, the wallet statement showing the debit and fee. Do not include credentials."
            />
          </label>
          <button className="button primary" type="submit" disabled={busy}>
            Save local review
          </button>
        </form>
      )}
      {error && (
        <div role="alert" className="field-warning">
          {error}{' '}
          <button className="text-link" onClick={reload}>
            Reload record
          </button>
        </div>
      )}
      {latest && latest.action !== 'withdraw' && (
        <button className="button secondary" disabled={busy} onClick={() => void submit(true)}>
          Withdraw this review
        </button>
      )}
      {!!history.length && (
        <details className="funding-review-audit">
          <summary>
            <History size={14} /> Review history
          </summary>
          {history.map((item) => (
            <article key={item.id}>
              <strong>
                {item.action === 'withdraw' ? 'Review withdrawn' : 'Local review'} ·{' '}
                {new Date(item.created_at).toLocaleString()}
              </strong>
              {item.decision && (
                <p>
                  {item.decision.wallet_scope === 'outside'
                    ? 'Outside configured wallet'
                    : item.decision.amount_convention?.replaceAll('_', ' ')}
                  {item.decision.fee_quantity !== null
                    ? ` · asserted fee ${item.decision.fee_quantity} ${event.asset}`
                    : ''}
                </p>
              )}
              {item.note && <p>{item.note}</p>}
            </article>
          ))}
          <small>Newest 20 decisions shown. All decisions remain stored locally.</small>
        </details>
      )}
      <p className="footnote">
        Existing saved balance reports remain unchanged.{' '}
        <Link to="/account">Run a new balance check</Link> to use the current review.
      </p>
    </div>
  );
}

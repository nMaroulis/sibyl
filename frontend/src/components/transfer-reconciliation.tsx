import { useCallback, useEffect, useState } from 'react';
import type { FormEvent } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import {
  ArrowLeft,
  ArrowRight,
  ChevronLeft,
  ChevronRight,
  Link2,
  Plus,
  RefreshCw,
  X,
} from 'lucide-react';
import { api, number, post, refresh } from '../lib/api';
import { useResource } from '../lib/hooks';
import type { AgentContext } from '../lib/types';
import { AgentButton } from './agents';
import { ExchangeMark } from './exchange-mark';
import { TransferFeeAllocation } from './transfer-fee-allocation';
import type { FeeAllocationPlan, FeeReview } from './transfer-fee-allocation';
import { Badge, Empty, ErrorState, Loading, Modal, Panel, PanelTitle } from './ui';

type Observation = {
  id: string;
  native_id: string;
  reference: string | null;
  account_id: string;
  account: string;
  exchange: string;
  environment: string;
  kind: string;
  direction: string;
  asset: string;
  quantity: number;
  created_at: string;
  status: string;
  internal: boolean;
  amount_basis: string;
  fee: { currency: string | null; cost: number | null };
  fee_known: boolean;
  fingerprint: string;
  reconciliation?: { status: string; link_id: string } | null;
};
type Pair = {
  outgoing: Observation;
  incoming: Observation;
  valid: boolean;
  issues: string[];
  warnings: string[];
  asset: string;
  amount_difference: number;
  equal_amounts: boolean;
  note_required: boolean;
  difference_matches_outgoing_fee: boolean;
  time_gap_ms: number;
  alternatives?: number;
  reasons?: string[];
};
type TransferLink = {
  id: string;
  status: 'confirmed' | 'needs_review' | 'removed';
  created_at: string;
  updated_at: string;
  review_note: string;
  reviewed: Pair;
  current: Pair | null;
  changed_sides: string[];
  cost_basis_applied: boolean;
  allocation?: FeeAllocationPlan | null;
  audit?: { action: string; created_at: string; after?: { review_note?: string } | null }[];
};
type Report = {
  example?: boolean;
  items: TransferLink[];
  total: number;
  has_more: boolean;
  candidates: Pair[];
  scanned_events: number;
  eligible_events: number;
  scan_limited: boolean;
  event_limit: number;
  candidate_limit: number;
  scope: string;
  note: string;
};
type Review =
  | { kind: 'pair'; pair: Pair; example: boolean }
  | { kind: 'link'; id: string; link?: TransferLink; example: boolean }
  | { kind: 'manual' };
const stamp = (value: string) => new Date(value).toLocaleString();
const amount = (value: number, asset: string) => `${number(value, 8)} ${asset}`;

/** Local transfer matching and explicit assertions; no exchange mutation or cost-basis inference. */
export function TransferReconciliation({
  active,
  accounts,
}: {
  active: boolean;
  accounts: { id: string; label: string }[];
}) {
  const [params, setParams] = useSearchParams();
  const account = params.get('account') || '';
  const asset = params.get('fund_asset') || '';
  const environment = params.get('environment') || '';
  const removed = params.get('fund_removed') === '1';
  const offset = Math.min(1_000_000, Math.max(0, Number(params.get('transfer_offset')) || 0));
  const requested = params.get('fund_link');
  const [example, setExample] = useState(false);
  const [review, setReview] = useState<Review>();
  const change = (values: Record<string, string>, reset = true) =>
    setParams((old) => {
      const next = new URLSearchParams(old);
      if (reset) next.delete('transfer_offset');
      Object.entries(values).forEach(([key, value]) =>
        value ? next.set(key, value) : next.delete(key),
      );
      return next;
    });
  useEffect(() => {
    if (requested) {
      setExample(false);
      setReview({ kind: 'link', id: requested, example: false });
    }
  }, [requested]);
  const close = useCallback(() => {
    setReview(undefined);
    setParams(
      (old) => {
        if (!old.has('fund_link')) return old;
        const next = new URLSearchParams(old);
        next.delete('fund_link');
        return next;
      },
      { replace: true },
    );
  }, [setParams]);
  const query = new URLSearchParams({
    account_id: account,
    asset,
    environment,
    include_removed: String(removed),
    limit: '25',
    offset: String(offset),
  });
  const report = useResource<Report>(
    example ? '/account-ledger/transfers/example' : `/account-ledger/transfers?${query}`,
    active && !example ? 10000 : 0,
    active,
  );
  const data = report.data;
  const saved = () => {
    close();
    refresh();
  };
  return (
    <>
      <Panel className="full-panel">
        <PanelTitle
          title="Transfer reconciliation"
          subtitle="Review movements between your own accounts"
          action={
            <div className="performance-actions">
              <button
                className="button secondary tiny"
                onClick={() => change({ fund_view: '', fund_link: '' })}
              >
                <ArrowLeft size={13} /> Movements
              </button>
              <AgentButton
                module="accountant"
                compact
                context={{
                  transfer_view: true,
                  funding_account_id: account,
                  funding_asset: asset,
                  funding_environment: environment as AgentContext['funding_environment'],
                  transfer_example: example,
                }}
              >
                Ask about transfers
              </AgentButton>
              {!example && (
                <Link
                  className="button secondary tiny"
                  to={`/trade?${new URLSearchParams({ tab: 'history', history_view: 'performance', ...(account ? { account } : {}), ...(environment ? { environment } : {}) })}`}
                >
                  Cost basis in Performance <ArrowRight size={13} />
                </Link>
              )}
              <button className="button secondary tiny" onClick={() => setExample(!example)}>
                {example && <X size={13} />}
                {example ? 'Close example' : 'View example'}
              </button>
              {!example && (
                <button
                  className="button primary tiny"
                  onClick={() => setReview({ kind: 'manual' })}
                >
                  <Plus size={13} /> Match records
                </button>
              )}
            </div>
          }
        />
        {example ? (
          <div className="performance-example">
            <Badge tone="purple">Example reconciliation</Badge>
            <span>
              Competing BTC matches, an ETH suggestion and a saved USDT link. No account records or
              links are created.
            </span>
          </div>
        ) : (
          <div className="workspace-controls">
            <label>
              Account
              <select value={account} onChange={(event) => change({ account: event.target.value })}>
                <option value="">All retained accounts</option>
                {accounts.map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.label}
                  </option>
                ))}
                {account && !accounts.some((item) => item.id === account) && (
                  <option value={account}>Selected retained account</option>
                )}
              </select>
            </label>
            <label>
              Asset
              <input
                value={asset}
                placeholder="All assets"
                maxLength={20}
                onChange={(event) =>
                  change({
                    fund_asset: event.target.value
                      .toUpperCase()
                      .replace(/[^A-Z0-9.]/g, '')
                      .replace(/^\.+/, ''),
                  })
                }
              />
            </label>
            <label>
              Environment
              <select
                value={environment}
                onChange={(event) => change({ environment: event.target.value })}
              >
                <option value="">All environments</option>
                <option value="production">Production</option>
                <option value="test">Test funds</option>
                <option value="demo">Demo</option>
              </select>
            </label>
            <button
              className="button secondary tiny"
              aria-pressed={removed}
              onClick={() => change({ fund_removed: removed ? '' : '1' })}
            >
              {removed ? 'Hide removed links' : 'Include removed links'}
            </button>
            <button className="button secondary tiny" onClick={report.retry}>
              <RefreshCw size={13} /> Refresh
            </button>
          </div>
        )}
        <p className="footnote padded">
          {data?.note ||
            'Links are your own-account transfer assertions. Source records, fees and cost basis remain separate. Unmatched records are unreviewed, not automatically external funding.'}
        </p>
      </Panel>
      {report.error ? (
        <ErrorState message={report.error} retry={report.retry} />
      ) : report.loading ? (
        <Loading />
      ) : (
        <>
          <Panel className="full-panel">
            <PanelTitle
              title="Possible matches"
              subtitle="Suggestions use asset, amounts and timing. Review ownership and both source records."
              action={<Badge>{data?.candidates.length || 0} suggestions</Badge>}
            />
            <div className="transfer-candidates">
              {data?.candidates.length ? (
                data.candidates.map((item) => (
                  <article
                    className="transfer-candidate"
                    key={`${item.outgoing.id}:${item.incoming.id}`}
                  >
                    <div className="transfer-pair">
                      <ObservationCard event={item.outgoing} label="Outgoing" />
                      <span className="transfer-direction">
                        <ArrowRight size={19} />
                      </span>
                      <ObservationCard event={item.incoming} label="Incoming" />
                    </div>
                    <div className="transfer-candidate-footer">
                      <div>
                        <div className="transfer-reasons">
                          {item.reasons?.map((reason) => (
                            <Badge key={reason}>{reason}</Badge>
                          ))}
                          {(item.alternatives || 0) > 1 && (
                            <Badge tone="rose">{item.alternatives} competing suggestions</Badge>
                          )}
                        </div>
                        <p>
                          {item.equal_amounts
                            ? 'Equal reported amounts do not prove a transfer.'
                            : `Reported difference: ${amount(item.amount_difference, item.asset)}. Fee inclusion is not established.`}
                        </p>
                      </div>
                      <button
                        className="button secondary"
                        onClick={() => setReview({ kind: 'pair', pair: item, example })}
                      >
                        Review pair <ArrowRight size={13} />
                      </button>
                    </div>
                  </article>
                ))
              ) : (
                <Empty title="No suggestions in this scan">
                  Import both sides of a movement, narrow the asset filter, or use Match records to
                  search older observations. An empty scan does not establish external funding.
                </Empty>
              )}
            </div>
            <p className="footnote padded">
              Scanned {data?.scanned_events || 0} of {data?.eligible_events || 0} eligible
              observations; up to {data?.candidate_limit || 40} suggestions.{' '}
              {data?.scan_limited && (
                <strong>The scan is limited. Filter by asset or search records manually. </strong>
              )}
              {data?.scope}
            </p>
          </Panel>
          <Panel className="full-panel">
            <PanelTitle
              title="Saved transfer links"
              subtitle="Source corrections flag a link for review. Removing a link preserves its history."
              action={<Badge>{data?.total || 0} links</Badge>}
            />
            <div className="transfer-saved">
              {data?.items.length ? (
                data.items.map((link) => (
                  <article className="transfer-saved-row" key={link.id}>
                    <span className="transfer-link-icon">
                      <Link2 size={18} />
                    </span>
                    <div>
                      <strong>
                        {link.reviewed.outgoing.account} <ArrowRight size={12} />{' '}
                        {link.reviewed.incoming.account}
                      </strong>
                      <p>
                        {amount(link.reviewed.outgoing.quantity, link.reviewed.asset)} sent ·{' '}
                        {amount(link.reviewed.incoming.quantity, link.reviewed.asset)} received ·{' '}
                        {link.reviewed.outgoing.environment}
                      </p>
                      {link.review_note && <p>{link.review_note}</p>}
                      <small>
                        Reviewed {stamp(link.updated_at)} · Cost basis checked in Performance
                      </small>
                    </div>
                    <Badge
                      tone={
                        link.status === 'confirmed'
                          ? 'lime'
                          : link.status === 'needs_review'
                            ? 'rose'
                            : 'neutral'
                      }
                    >
                      {link.status === 'needs_review'
                        ? 'Needs review'
                        : link.status === 'confirmed'
                          ? 'User confirmed'
                          : 'Removed'}
                    </Badge>
                    <button
                      className="button secondary tiny"
                      onClick={() => setReview({ kind: 'link', id: link.id, link, example })}
                    >
                      {link.status === 'removed' ? 'Review & restore' : 'Open review'}
                    </button>
                  </article>
                ))
              ) : (
                <Empty title="No saved transfer links">
                  Review a suggested pair or manually select two completed movements. A link
                  classifies the records without moving money. Performance checks whether original
                  lots can carry over.
                </Empty>
              )}
            </div>
            {!example && (
              <nav className="news-pagination" aria-label="Transfer link pages">
                <button
                  className="button secondary tiny"
                  disabled={!offset}
                  onClick={() =>
                    change({ transfer_offset: String(Math.max(0, offset - 25)) }, false)
                  }
                >
                  <ChevronLeft size={13} /> Previous
                </button>
                <span>Page {Math.floor(offset / 25) + 1}</span>
                <button
                  className="button secondary tiny"
                  disabled={!data?.has_more}
                  onClick={() => change({ transfer_offset: String(offset + 25) }, false)}
                >
                  Next <ChevronRight size={13} />
                </button>
              </nav>
            )}
          </Panel>
        </>
      )}
      {review?.kind === 'manual' && (
        <ManualPair
          onClose={close}
          asset={asset}
          environment={environment}
          accountId={account}
          selected={(pair) => setReview({ kind: 'pair', pair, example: false })}
        />
      )}
      {review && review.kind !== 'manual' && (
        <PairReview selection={review} onClose={close} saved={saved} />
      )}
    </>
  );
}

function ObservationCard({ event, label }: { event: Observation; label: string }) {
  return (
    <div className="transfer-observation">
      <div className="transfer-observation-heading">
        <span className="provider-logo small-logo">
          <ExchangeMark exchange={event.exchange} />
        </span>
        <div>
          <small>
            {label} · {event.environment}
          </small>
          <strong>{event.account}</strong>
        </div>
        <Badge>{event.status}</Badge>
      </div>
      <b>{amount(event.quantity, event.asset)}</b>
      <p>
        {stamp(event.created_at)} · {event.kind}
      </p>
      <p>
        Reported fee:{' '}
        {event.fee_known ? amount(event.fee.cost!, event.fee.currency!) : 'Unavailable'}
      </p>
      <details>
        <summary>Source record</summary>
        <p>
          {event.exchange} · {event.native_id}
        </p>
        {event.reference && <p>Reference: {event.reference}</p>}
        <p>Amount basis: {event.amount_basis.replaceAll('_', ' ')}</p>
        <p>
          {event.internal
            ? 'The venue marks this activity internal; that does not establish ownership of the other account.'
            : 'No internal-at-venue marker is present.'}
        </p>
      </details>
    </div>
  );
}

/** Freeze the exact facts displayed; a concurrent source correction requires another review. */
function PairReview({
  selection,
  onClose,
  saved,
}: {
  selection: Exclude<Review, { kind: 'manual' }>;
  onClose: () => void;
  saved: () => void;
}) {
  const [data, setData] = useState<{ pair: Pair | null; link?: TransferLink }>();
  const [note, setNote] = useState(
    selection.kind === 'link' ? selection.link?.review_note || '' : '',
  );
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [revision, setRevision] = useState(0);
  const [feeReview, setFeeReview] = useState<FeeReview>({
    enabled: false,
    ready: true,
    allocation: null,
  });
  const dismiss = useCallback(() => {
    if (!busy) onClose();
  }, [busy, onClose]);
  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError('');
    setFeeReview({ enabled: false, ready: true, allocation: null });
    if (selection.example) {
      setData(
        selection.kind === 'pair'
          ? { pair: selection.pair }
          : { pair: selection.link!.current || selection.link!.reviewed, link: selection.link },
      );
      setLoading(false);
      return;
    }
    const fetch =
      selection.kind === 'pair'
        ? api<Pair>('/account-ledger/transfers/preview', {
            method: 'POST',
            body: JSON.stringify({
              outgoing_id: selection.pair.outgoing.id,
              incoming_id: selection.pair.incoming.id,
            }),
            signal: controller.signal,
          }).then((pair) => ({ pair }))
        : api<TransferLink>(`/account-ledger/transfers/${selection.id}`, {
            signal: controller.signal,
          }).then((link) => ({ pair: link.current, link }));
    fetch
      .then((result) => {
        if (!controller.signal.aborted) {
          setData(result);
          if ('link' in result && result.link && revision === 0) setNote(result.link.review_note);
        }
      })
      .catch((reason) => {
        if (!controller.signal.aborted) setError(reason.message);
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [selection, revision]);
  const evidence = data?.pair;
  const displayed = evidence || data?.link?.reviewed;
  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!evidence || selection.example || (feeReview.enabled && !feeReview.ready)) return;
    setBusy(true);
    setError('');
    try {
      await post(
        selection.kind === 'link'
          ? `/account-ledger/transfers/${selection.id}/review`
          : '/account-ledger/transfers',
        {
          outgoing_id: evidence.outgoing.id,
          incoming_id: evidence.incoming.id,
          outgoing_fingerprint: evidence.outgoing.fingerprint,
          incoming_fingerprint: evidence.incoming.fingerprint,
          note,
          allocation: feeReview.enabled ? feeReview.allocation : null,
        },
      );
      saved();
    } catch (reason) {
      setError((reason as Error).message);
    } finally {
      setBusy(false);
    }
  };
  const remove = async () => {
    if (selection.kind !== 'link' || selection.example) return;
    setBusy(true);
    setError('');
    try {
      await api(`/account-ledger/transfers/${selection.id}`, { method: 'DELETE' });
      saved();
    } catch (reason) {
      setError((reason as Error).message);
    } finally {
      setBusy(false);
    }
  };
  return (
    <Modal
      title={
        data?.link?.status === 'removed'
          ? 'Review & restore transfer link'
          : 'Review own-account transfer'
      }
      onClose={dismiss}
      className="transfer-review-modal"
    >
      {selection.example && (
        <div className="performance-example">
          <Badge tone="purple">Example only</Badge>
          <span>No link can be saved from this example.</span>
        </div>
      )}
      {loading ? (
        <Loading />
      ) : (
        <>
          {data?.link?.status === 'needs_review' && (
            <p className="transfer-review-alert">
              Source facts changed: {data.link.changed_sides.join(' and ')}. Review the current
              records below before confirming again. Saved evidence remains in the history.
            </p>
          )}
          {!evidence && data?.link && (
            <p className="transfer-review-alert">
              A current source record is missing. The saved evidence is shown below; this link can
              be removed, but cannot be reconfirmed.
            </p>
          )}
          {displayed && (
            <>
              <div className="transfer-pair">
                <ObservationCard
                  event={displayed.outgoing}
                  label={evidence ? 'Current outgoing' : 'Saved outgoing'}
                />
                <span className="transfer-direction">
                  <ArrowRight size={18} />
                </span>
                <ObservationCard
                  event={displayed.incoming}
                  label={evidence ? 'Current incoming' : 'Saved incoming'}
                />
              </div>
              <div className="transfer-comparison">
                <strong>
                  Reported outgoing − incoming:{' '}
                  {amount(displayed.amount_difference, displayed.asset)}
                </strong>
                <span>This difference is not an inferred transfer fee.</span>
              </div>
            </>
          )}
          {!!evidence?.issues.length && (
            <ul className="performance-issues">
              {evidence.issues.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          )}
          {!!evidence?.warnings.length && (
            <ul className="performance-issues">
              {evidence.warnings.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          )}
          <form onSubmit={submit} className="transfer-review-form">
            {evidence?.valid && (
              <TransferFeeAllocation
                key={`${evidence.outgoing.fingerprint}:${evidence.incoming.fingerprint}:${revision}`}
                outgoing={evidence.outgoing}
                incoming={evidence.incoming}
                saved={
                  data?.link && !data.link.changed_sides.length ? data.link.allocation : undefined
                }
                example={selection.example}
                disabled={busy}
                onChange={setFeeReview}
                reload={() => setRevision((value) => value + 1)}
              />
            )}
            <label>
              {evidence?.note_required || feeReview.enabled
                ? 'Explain amounts, timing and any distinct fee charges (required)'
                : 'Review note (optional)'}
              <textarea
                disabled={busy || selection.example}
                maxLength={1000}
                minLength={evidence?.note_required || feeReview.enabled ? 8 : undefined}
                required={evidence?.note_required || feeReview.enabled}
                value={note}
                onChange={(event) => setNote(event.target.value)}
                placeholder="What did you check to identify these two records?"
                rows={3}
              />
            </label>
            <p className="footnote">
              Confirm that these movements are between accounts you own. This saves a local
              classification and preserves source amounts and fees. Performance can carry original
              lots for eligible zero-fee pairs and reviewed, balanced same-asset fee allocations.
              Other cases stay provisional. Fee inventory cost stays separate from trading P&amp;L.
            </p>
            <div className="performance-actions">
              {data?.link && data.link.status !== 'removed' && !selection.example && (
                <button className="button secondary" type="button" disabled={busy} onClick={remove}>
                  Remove link
                </button>
              )}
              <button
                className="button primary"
                disabled={
                  busy ||
                  loading ||
                  selection.example ||
                  !evidence?.valid ||
                  ((!!evidence.note_required || feeReview.enabled) && note.trim().length < 8) ||
                  (feeReview.enabled && !feeReview.ready)
                }
              >
                {selection.example
                  ? 'Example · no link saved'
                  : busy
                    ? 'Saving…'
                    : data?.link?.status === 'removed'
                      ? 'Restore link'
                      : data?.link
                        ? 'Reconfirm link'
                        : 'Confirm own-account transfer'}
              </button>
            </div>
          </form>
          {data?.link && (
            <details className="performance-evidence">
              <summary>Saved evidence & review history</summary>
              <div className="performance-detail-body">
                <p>
                  Saved {stamp(data.link.updated_at)} ·{' '}
                  {data.link.review_note || 'No note supplied'}
                </p>
                <p>
                  Reviewed amounts:{' '}
                  {amount(data.link.reviewed.outgoing.quantity, data.link.reviewed.asset)} outgoing
                  / {amount(data.link.reviewed.incoming.quantity, data.link.reviewed.asset)}{' '}
                  incoming.
                </p>
                {data.link.audit?.map((item, index) => (
                  <p key={index}>
                    {stamp(item.created_at)} · {item.action}
                    {item.after?.review_note ? ` · ${item.after.review_note}` : ''}
                  </p>
                ))}
                <details>
                  <summary>Inspect saved source snapshots</summary>
                  <pre className="transfer-json">{JSON.stringify(data.link.reviewed, null, 2)}</pre>
                </details>
                <p className="footnote">
                  Latest 50 explicit review actions. Removed links remain restorable when their
                  records are available and unclaimed.
                </p>
              </div>
            </details>
          )}
        </>
      )}
      {error && <ErrorState message={error} retry={() => setRevision((value) => value + 1)} />}
      {!selection.example && !loading && (
        <button
          className="text-link transfer-reload"
          disabled={busy}
          onClick={() => setRevision((value) => value + 1)}
        >
          <RefreshCw size={12} /> Reload current source records
        </button>
      )}
    </Modal>
  );
}

function ManualPair({
  onClose,
  selected,
  accountId,
  asset,
  environment,
}: {
  onClose: () => void;
  selected: (pair: Pair) => void;
  accountId: string;
  asset: string;
  environment: string;
}) {
  const [outgoing, setOutgoing] = useState<Observation>();
  const [incoming, setIncoming] = useState<Observation>();
  const [allAccounts, setAllAccounts] = useState(!accountId);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const dismiss = useCallback(() => {
    if (!busy) onClose();
  }, [busy, onClose]);
  const prepare = async () => {
    if (!outgoing || !incoming) return;
    setBusy(true);
    setError('');
    try {
      selected(
        await post<Pair>('/account-ledger/transfers/preview', {
          outgoing_id: outgoing.id,
          incoming_id: incoming.id,
        }),
      );
    } catch (reason) {
      setError((reason as Error).message);
    } finally {
      setBusy(false);
    }
  };
  return (
    <Modal
      title="Choose two retained funding records"
      className="transfer-review-modal"
      onClose={dismiss}
    >
      <p className="muted transfer-help">
        Search by account, asset or native record ID. This search includes older observations
        outside the suggestion scan. Each record can belong to one active link.
      </p>
      {accountId && (
        <button
          className="text-link transfer-search-scope"
          disabled={busy}
          onClick={() => {
            setAllAccounts(!allAccounts);
            setOutgoing(undefined);
            setIncoming(undefined);
          }}
        >
          {allAccounts
            ? 'Limit outgoing records to the selected account'
            : 'Search outgoing records across all accounts'}
        </button>
      )}
      <div className="transfer-manual-grid">
        <RecordPicker
          label="Outgoing record"
          direction="out"
          accountId={allAccounts ? '' : accountId}
          asset={asset}
          environment={environment}
          value={outgoing}
          choose={(value) => {
            setOutgoing(value);
            setIncoming(undefined);
          }}
        />
        <RecordPicker
          label="Incoming record"
          direction="in"
          accountId=""
          asset={outgoing?.asset || asset}
          environment={outgoing?.environment || environment}
          value={incoming}
          choose={setIncoming}
          excludedAccount={outgoing?.account_id}
        />
      </div>
      {error && <ErrorState message={error} />}
      <div className="performance-actions transfer-manual-actions">
        <button
          className="button primary"
          disabled={busy || !outgoing || !incoming}
          onClick={prepare}
        >
          {busy ? 'Loading review…' : 'Review selected pair'}
          <ArrowRight size={13} />
        </button>
      </div>
    </Modal>
  );
}

function RecordPicker({
  label,
  direction,
  accountId,
  asset,
  environment,
  value,
  choose,
  excludedAccount,
}: {
  label: string;
  direction: 'in' | 'out';
  accountId: string;
  asset: string;
  environment: string;
  value?: Observation;
  choose: (value: Observation | undefined) => void;
  excludedAccount?: string;
}) {
  const [query, setQuery] = useState('');
  const [offset, setOffset] = useState(0);
  useEffect(() => {
    setOffset(0);
  }, [accountId, asset, environment]);
  const params = new URLSearchParams({
    direction,
    account_id: accountId,
    asset,
    environment,
    q: query,
    limit: '10',
    offset: String(offset),
  });
  const records = useResource<{ items: Observation[]; total: number; has_more: boolean }>(
    `/account-ledger/transfers/events?${params}`,
    0,
    !value,
  );
  return (
    <section className="transfer-record-picker">
      <h3>{label}</h3>
      {value ? (
        <>
          <ObservationCard event={value} label={label} />
          <button className="text-link" onClick={() => choose(undefined)}>
            Choose a different record
          </button>
        </>
      ) : (
        <>
          <label className="sr-only">Search {label.toLowerCase()}</label>
          <input
            aria-label={`Search ${label.toLowerCase()}`}
            value={query}
            maxLength={120}
            placeholder="Account, asset or native ID…"
            onChange={(event) => {
              setQuery(event.target.value);
              setOffset(0);
            }}
          />
          {records.error ? (
            <ErrorState message={records.error} retry={records.retry} />
          ) : records.loading ? (
            <Loading />
          ) : (
            <>
              <div className="transfer-record-results">
                {records.data?.items.length ? (
                  records.data.items.map((item) => (
                    <button
                      className="transfer-record-option"
                      key={item.id}
                      disabled={!!item.reconciliation || item.account_id === excludedAccount}
                      onClick={() => choose(item)}
                    >
                      <strong>
                        {item.account} · {amount(item.quantity, item.asset)}
                      </strong>
                      <span>
                        {stamp(item.created_at)} · {item.exchange} · {item.environment}
                      </span>
                      <small>
                        {item.native_id}
                        {item.reconciliation
                          ? ` · ${item.reconciliation.status === 'needs_review' ? 'Existing link needs review' : 'Already linked'}`
                          : item.account_id === excludedAccount
                            ? ' · Same account'
                            : ''}
                      </small>
                    </button>
                  ))
                ) : (
                  <p className="footnote">
                    No eligible records. Try a native ID from the funding ledger or import the other
                    side.
                  </p>
                )}
              </div>
              <nav className="news-pagination">
                <button
                  className="button secondary tiny"
                  disabled={!offset}
                  onClick={() => setOffset(Math.max(0, offset - 10))}
                >
                  Previous
                </button>
                <span>{records.data?.total || 0} records</span>
                <button
                  className="button secondary tiny"
                  disabled={!records.data?.has_more}
                  onClick={() => setOffset(offset + 10)}
                >
                  Next
                </button>
              </nav>
            </>
          )}
        </>
      )}
    </section>
  );
}

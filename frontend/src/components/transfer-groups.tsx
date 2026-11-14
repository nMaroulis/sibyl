import { useSearchParams } from 'react-router-dom';
import { useEffect, useRef, useState } from 'react';
import { ArrowRight, GitMerge, Plus, RefreshCw, Trash2, X } from 'lucide-react';
import { api, number, post, refresh } from '../lib/api';
import { useResource } from '../lib/hooks';
import { Badge, Empty, ErrorState, Loading, Modal, Panel, PanelTitle } from './ui';

type Event = {
  id: string;
  group_fingerprint: string;
  native_id: string;
  account: string;
  account_id: string;
  direction: 'in' | 'out';
  asset: string;
  environment: string;
  quantity: number;
  created_at: string;
  fee: { currency: string | null; cost: number | null };
  fee_known: boolean;
  reconciliation?: { link_id: string };
};
type Leg = { event: Event; amount: string; fee: string };
type RequestLeg = {
  event_id: string;
  source_version: string;
  amount: string;
  fee_quantity: string | null;
};
type Edge = { outgoing_id: string; incoming_id: string; quantity: string };
type Preview = {
  asset: string;
  environment: string;
  source_debit: string;
  destination_credit: string;
  fee_quantity: string;
  review_fingerprint: string;
  lot_order: string;
  warnings: string[];
  note: string;
  outgoing: {
    event: Event;
    amount: string;
    fee: string;
    wallet_quantity: string;
    principal: string;
  }[];
  incoming: {
    event: Event;
    amount: string;
    fee: string;
    wallet_quantity: string;
    principal: string;
  }[];
  edges: Edge[];
  reservations: { event_id: string; link_id: string }[];
};
type Group = {
  id: string;
  revision: number;
  status: string;
  review_note: string;
  reviewed: Preview;
  changed_members: string[];
  request: {
    outgoing: RequestLeg[];
    incoming: RequestLeg[];
    edges: Edge[];
    distinct_fees_confirmed: boolean;
  };
  current_members?: Event[];
  audit?: { action: string; created_at: string }[];
};
const base = '/account-ledger/transfer-groups';

/** Explicit local reviews, separate from pair heuristics and live exchange operations. */
export function TransferGroups({
  active,
  account,
  asset,
  environment,
  includeRemoved,
}: {
  active: boolean;
  account: string;
  asset: string;
  environment: string;
  includeRemoved: boolean;
}) {
  const [params, setParams] = useSearchParams();
  const requested = params.get('fund_group');
  const close = () => {
    setSelection(undefined);
    if (requested)
      setParams(
        (old) => {
          const next = new URLSearchParams(old);
          next.delete('fund_group');
          return next;
        },
        { replace: true },
      );
  };
  useEffect(() => {
    if (!active || !requested) return;
    let cancelled = false;
    api<Group>(`${base}/${requested}`)
      .then((value) => {
        if (!cancelled) setSelection(value);
      })
      .catch((reason) => {
        if (!cancelled) setError(reason.message);
      });
    return () => {
      cancelled = true;
    };
  }, [requested, active]);
  const [offset, setOffset] = useState(0);
  const [selection, setSelection] = useState<Group | 'new'>();
  const [error, setError] = useState('');
  const query = new URLSearchParams({
    account_id: account,
    asset,
    environment,
    include_removed: String(includeRemoved),
    limit: '10',
    offset: String(offset),
  });
  const data = useResource<{ items: Group[]; total: number; has_more: boolean }>(
    `${base}?${query}`,
    0,
    active,
  );
  const open = async (group: Group) => {
    setError('');
    try {
      setSelection(await api<Group>(`${base}/${group.id}`));
    } catch (reason) {
      setError((reason as Error).message);
    }
  };
  return (
    <Panel className="full-panel transfer-groups">
      <PanelTitle
        title="Split & merged transfers"
        subtitle="Explicitly allocate one withdrawal to several deposits, or merge several withdrawals."
        action={
          <button className="button secondary tiny" onClick={() => setSelection('new')}>
            <Plus size={14} /> Create group
          </button>
        }
      />
      <p className="footnote padded">
        Carry acquisition lots in Performance → Across pairs. Every source record stays unchanged;
        ownership, wallet scope and the allocation are your reviewed assertions.
      </p>
      {error && <p className="form-error">{error}</p>}
      {data.error ? (
        <ErrorState message={data.error} retry={data.retry} />
      ) : data.loading ? (
        <Loading />
      ) : (
        <>
          <div className="transfer-saved">
            {data.data?.items.length ? (
              data.data.items.map((group) => (
                <article className="transfer-saved-row" key={group.id}>
                  <span className="transfer-link-icon">
                    <GitMerge size={18} />
                  </span>
                  <div>
                    <strong>
                      {group.reviewed.asset} · {group.reviewed.outgoing.length} sources{' '}
                      <ArrowRight size={12} /> {group.reviewed.incoming.length} receipts
                    </strong>
                    <p>
                      {number(Number(group.reviewed.source_debit), 8)} →{' '}
                      {number(Number(group.reviewed.destination_credit), 8)} ·{' '}
                      {group.reviewed.environment}
                    </p>
                    <small>{group.review_note}</small>
                  </div>
                  <Badge tone={group.status === 'needs_review' ? 'warning' : undefined}>
                    {group.status.replaceAll('_', ' ')}
                  </Badge>
                  <button className="button secondary tiny" onClick={() => void open(group)}>
                    Review
                  </button>
                </article>
              ))
            ) : (
              <Empty title="No transfer groups">
                For a simple two-record transfer, use Match records above. Import funding history
                before creating a group.
              </Empty>
            )}
          </div>
          {!!data.data?.total && (
            <nav className="news-pagination">
              <button
                className="button secondary tiny"
                disabled={!offset}
                onClick={() => setOffset(Math.max(0, offset - 10))}
              >
                Previous
              </button>
              <span>{data.data.total} groups</span>
              <button
                className="button secondary tiny"
                disabled={!data.data.has_more}
                onClick={() => setOffset(offset + 10)}
              >
                Next
              </button>
            </nav>
          )}
        </>
      )}
      {selection && (
        <GroupReview
          key={selection === 'new' ? 'new' : `${selection.id}:${selection.revision}`}
          selection={selection}
          asset={asset}
          environment={environment}
          onClose={close}
          saved={() => {
            close();
            refresh();
          }}
        />
      )}
    </Panel>
  );
}

function GroupReview({
  selection,
  asset,
  environment,
  onClose,
  saved,
}: {
  selection: Group | 'new';
  asset: string;
  environment: string;
  onClose: () => void;
  saved: () => void;
}) {
  const old = selection === 'new' ? undefined : selection;
  const initial = (side: 'outgoing' | 'incoming'): Leg[] =>
    old
      ? old.request[side].map((leg) => ({
          event:
            old.current_members?.find((row) => row.id === leg.event_id) ||
            old.reviewed[side].find((row) => row.event.id === leg.event_id)!.event,
          amount: leg.amount,
          fee: leg.fee_quantity || '',
        }))
      : [];
  const [outgoing, setOutgoing] = useState<Leg[]>(() => initial('outgoing'));
  const [incoming, setIncoming] = useState<Leg[]>(() => initial('incoming'));
  const [edges, setEdges] = useState<Record<string, string>>(() =>
    Object.fromEntries(
      (old?.request.edges || []).map((edge) => [
        `${edge.outgoing_id}:${edge.incoming_id}`,
        edge.quantity,
      ]),
    ),
  );
  const [distinct, setDistinct] = useState(old?.request.distinct_fees_confirmed || false);
  const [ownership, setOwnership] = useState(false);
  const [wallets, setWallets] = useState(false);
  const [note, setNote] = useState(old?.review_note || '');
  const [preview, setPreview] = useState<Preview>();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [removeReview, setRemoveReview] = useState(false);
  const [picking, setPicking] = useState<'out' | 'in'>();
  const invalidate = () => {
    setPreview(undefined);
    setError('');
    setOwnership(false);
    setWallets(false);
  };
  const request = () => ({
    outgoing: outgoing.map(legRequest),
    incoming: incoming.map(legRequest),
    distinct_fees_confirmed: distinct,
    edges: outgoing.flatMap((out) =>
      incoming.flatMap((inc) => {
        const quantity = edges[`${out.event.id}:${inc.event.id}`]?.trim();
        return quantity && Number(quantity) !== 0
          ? [{ outgoing_id: out.event.id, incoming_id: inc.event.id, quantity }]
          : [];
      }),
    ),
  });
  const act = async (kind: 'preview' | 'confirm' | 'remove') => {
    setBusy(true);
    setError('');
    try {
      if (kind === 'preview') setPreview(await post<Preview>(`${base}/preview`, request()));
      else if (kind === 'remove' && old) {
        await api(`${base}/${old.id}?revision=${old.revision}`, { method: 'DELETE' });
        saved();
      } else {
        await post(old ? `${base}/${old.id}/review` : base, {
          ...request(),
          revision: old?.revision || 0,
          review_fingerprint: preview?.review_fingerprint,
          note,
          own_accounts_confirmed: ownership,
          configured_wallets_confirmed: wallets,
        });
        saved();
      }
    } catch (reason) {
      setError((reason as Error).message);
      if (kind !== 'remove') setPreview(undefined);
    } finally {
      setBusy(false);
    }
  };
  const legs = (side: 'outgoing' | 'incoming') => {
    const rows = side === 'outgoing' ? outgoing : incoming;
    const setRows = side === 'outgoing' ? setOutgoing : setIncoming;
    return (
      <section className="transfer-group-legs">
        <h3>
          {side === 'outgoing' ? 'Sources' : 'Receipts'} <small>{rows.length}/8</small>
        </h3>
        {rows.map((leg, index) => (
          <article className="transfer-group-leg" key={leg.event.id}>
            <div>
              <strong>
                {index + 1}. {leg.event.account} · {number(leg.event.quantity, 8)} {leg.event.asset}
              </strong>
              <small>
                {new Date(leg.event.created_at).toLocaleString()} · {leg.event.native_id}
              </small>
            </div>
            <label>
              Reported amount
              <select
                value={leg.amount}
                disabled={busy}
                onChange={(event) => {
                  invalidate();
                  setRows(
                    rows.map((row, i) =>
                      i === index ? { ...row, amount: event.target.value } : row,
                    ),
                  );
                }}
              >
                {side === 'outgoing' ? (
                  <>
                    <option value="total_debit">Includes fee · total debit</option>
                    <option value="principal">Excludes fee · principal</option>
                  </>
                ) : (
                  <>
                    <option value="net_credit">Net credit · after fee</option>
                    <option value="gross_receipt">Gross receipt · before fee</option>
                  </>
                )}
              </select>
            </label>
            {leg.event.fee_known ? (
              <p className="footnote">
                Reported fee: {leg.event.fee.cost} {leg.event.fee.currency}
              </p>
            ) : (
              <label>
                Verified missing fee ({leg.event.asset})
                <input
                  aria-label={`Verified missing fee ${side} ${index + 1}`}
                  inputMode="decimal"
                  placeholder="Explicit quantity, including 0"
                  value={leg.fee}
                  disabled={busy}
                  onChange={(event) => {
                    invalidate();
                    setRows(
                      rows.map((row, i) =>
                        i === index ? { ...row, fee: event.target.value } : row,
                      ),
                    );
                  }}
                />
              </label>
            )}
            {!old && (
              <button
                className="icon-button"
                aria-label={`Remove ${side} ${index + 1}`}
                disabled={busy}
                onClick={() => {
                  invalidate();
                  setRows(rows.filter((_, i) => i !== index));
                }}
              >
                <X size={14} />
              </button>
            )}
          </article>
        ))}
        {!old && (
          <button
            className="button secondary tiny"
            disabled={busy || rows.length >= 8}
            onClick={() => setPicking(side === 'outgoing' ? 'out' : 'in')}
          >
            <Plus size={14} /> Add {side === 'outgoing' ? 'source' : 'receipt'}
          </button>
        )}
      </section>
    );
  };
  return (
    <Modal
      title={old ? 'Review transfer group' : 'Create transfer group'}
      onClose={onClose}
      className="transfer-review-modal transfer-group-modal"
    >
      <p className="footnote">
        Select 3–16 completed funding records in one asset and environment. Every source must
        precede every receipt. Fees must be nonnegative and in the transferred asset.
      </p>
      {old && (
        <p className="footnote">
          <Badge tone={old.status === 'needs_review' ? 'warning' : undefined}>
            {old.status.replaceAll('_', ' ')}
          </Badge>{' '}
          Revision {old.revision} ·{' '}
          {old.changed_members.length
            ? 'Source facts changed. Current available records are shown below; review all quantities again.'
            : 'Source versions checked.'}
        </p>
      )}
      <div className="transfer-group-columns">
        {legs('outgoing')}
        {legs('incoming')}
      </div>
      {!!outgoing.length && !!incoming.length && (
        <section className="transfer-group-matrix">
          <h3>Allocate principal</h3>
          <p className="footnote">
            Enter the amount from each source arriving at each receipt before its receipt fee.
            Blank/zero means no edge. Rows must equal dispatched principal; columns must equal gross
            arrivals. Column order defines source FIFO slicing.
          </p>
          <div className="table-scroll">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Source → receipt</th>
                  {incoming.map((row, i) => (
                    <th key={row.event.id}>
                      {i + 1}. {row.event.account}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {outgoing.map((out, o) => (
                  <tr key={out.event.id}>
                    <th>
                      {o + 1}. {out.event.account}
                    </th>
                    {incoming.map((inc, i) => (
                      <td key={inc.event.id}>
                        <input
                          aria-label={`Source ${o + 1} to receipt ${i + 1}`}
                          inputMode="decimal"
                          placeholder="0"
                          maxLength={90}
                          disabled={busy}
                          value={edges[`${out.event.id}:${inc.event.id}`] || ''}
                          onChange={(event) => {
                            invalidate();
                            setEdges({
                              ...edges,
                              [`${out.event.id}:${inc.event.id}`]: event.target.value,
                            });
                          }}
                        />
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}
      <label className="checkbox-field">
        <input
          type="checkbox"
          checked={distinct}
          disabled={busy}
          onChange={(event) => {
            invalidate();
            setDistinct(event.target.checked);
          }}
        />{' '}
        Any nonzero fees are distinct charges, not repeated displays of the same fee.
      </label>
      <button
        className="button secondary"
        disabled={busy || outgoing.length + incoming.length < 3}
        onClick={() => void act('preview')}
      >
        <RefreshCw size={14} /> {busy ? 'Checking…' : 'Preview allocation'}
      </button>
      {preview && (
        <section className="transfer-group-preview">
          <h3>Exact allocation review</h3>
          <div className="transfer-group-totals">
            <span>
              Source debit
              <strong>
                {preview.source_debit} {preview.asset}
              </strong>
            </span>
            <span>
              Destination credit
              <strong>
                {preview.destination_credit} {preview.asset}
              </strong>
            </span>
            <span>
              Distinct fees
              <strong>
                {preview.fee_quantity} {preview.asset}
              </strong>
            </span>
          </div>
          {preview.warnings.map((text) => (
            <p className="form-warning" key={text}>
              {text}
            </p>
          ))}
          {preview.reservations.some((row) => row.link_id !== old?.id) && (
            <p className="form-error">
              Some records already belong to another pair/group. Remove that review before reusing
              them.
            </p>
          )}
          <p className="footnote">
            {preview.lot_order} {preview.note}
          </p>
          <label>
            Review note
            <textarea
              maxLength={1000}
              rows={2}
              value={note}
              disabled={busy}
              onChange={(event) => setNote(event.target.value)}
              placeholder="Evidence for ownership, amount inclusion, fees and this allocation…"
            />
          </label>
          <label className="checkbox-field">
            <input
              type="checkbox"
              checked={ownership}
              disabled={busy}
              onChange={(event) => setOwnership(event.target.checked)}
            />{' '}
            I reviewed the evidence: these are transfers between my own accounts.
          </label>
          <label className="checkbox-field">
            <input
              type="checkbox"
              checked={wallets}
              disabled={busy}
              onChange={(event) => setWallets(event.target.checked)}
            />{' '}
            All legs affect the configured wallets, using the amount conventions shown.
          </label>
          <button
            className="button primary"
            disabled={
              busy ||
              !ownership ||
              !wallets ||
              note.trim().length < 8 ||
              preview.reservations.some((row) => row.link_id !== old?.id)
            }
            onClick={() => void act('confirm')}
          >
            {old ? 'Confirm reviewed revision' : 'Confirm transfer group'}
          </button>
        </section>
      )}
      {error && (
        <p className="form-error" role="alert">
          {error}
        </p>
      )}
      {!!old?.audit?.length && (
        <details className="transfer-group-audit">
          <summary>Review history · {old.audit.length} actions</summary>
          {old.audit.map((row, index) => (
            <p className="footnote" key={index}>
              {row.action} · {new Date(row.created_at).toLocaleString()}
            </p>
          ))}
        </details>
      )}
      {old && old.status !== 'removed' && (
        <div className="transfer-group-remove">
          {removeReview ? (
            <>
              <p>
                Withdraw this group and release all member records? The audit history stays saved.
              </p>
              <button
                className="button secondary tiny"
                disabled={busy}
                onClick={() => setRemoveReview(false)}
              >
                Keep group
              </button>
              <button
                className="button danger tiny"
                disabled={busy}
                onClick={() => void act('remove')}
              >
                Withdraw revision {old.revision}
              </button>
            </>
          ) : (
            <button className="text-link" disabled={busy} onClick={() => setRemoveReview(true)}>
              <Trash2 size={13} /> Withdraw group
            </button>
          )}
        </div>
      )}
      {picking && (
        <GroupPicker
          direction={picking}
          asset={outgoing[0]?.event.asset || incoming[0]?.event.asset || asset}
          environment={
            outgoing[0]?.event.environment || incoming[0]?.event.environment || environment
          }
          excluded={[...outgoing, ...incoming].map((row) => row.event.id)}
          close={() => setPicking(undefined)}
          choose={(event) => {
            invalidate();
            const leg = {
              event,
              amount: picking === 'out' ? 'total_debit' : 'net_credit',
              fee: '',
            };
            if (picking === 'out') setOutgoing([...outgoing, leg]);
            else setIncoming([...incoming, leg]);
            setPicking(undefined);
          }}
        />
      )}
    </Modal>
  );
}

const legRequest = (leg: Leg): RequestLeg => ({
  event_id: leg.event.id,
  source_version: leg.event.group_fingerprint,
  amount: leg.amount,
  fee_quantity: leg.fee.trim() || null,
});

function GroupPicker({
  direction,
  asset,
  environment,
  excluded,
  close,
  choose,
}: {
  direction: 'in' | 'out';
  asset: string;
  environment: string;
  excluded: string[];
  close: () => void;
  choose: (event: Event) => void;
}) {
  const search = useRef<HTMLInputElement>(null);
  useEffect(() => {
    search.current?.focus();
  }, []);
  const [q, setQ] = useState('');
  const [offset, setOffset] = useState(0);
  const query = new URLSearchParams({
    direction,
    asset,
    environment,
    q,
    limit: '10',
    offset: String(offset),
  });
  const data = useResource<{ items: Event[]; total: number; has_more: boolean }>(
    `/account-ledger/transfers/events?${query}`,
  );
  return (
    <div className="transfer-group-picker" role="region" aria-label="Choose group record">
      <header>
        <h3>Choose {direction === 'out' ? 'source' : 'receipt'}</h3>
        <button className="icon-button" aria-label="Close record picker" onClick={close}>
          <X size={16} />
        </button>
      </header>
      <input
        ref={search}
        aria-label="Search group records"
        placeholder="Account, asset or native ID…"
        maxLength={120}
        value={q}
        onChange={(event) => {
          setQ(event.target.value);
          setOffset(0);
        }}
      />
      {data.error ? (
        <ErrorState message={data.error} retry={data.retry} />
      ) : data.loading ? (
        <Loading />
      ) : (
        <>
          <div className="transfer-record-results">
            {data.data?.items.map((row) => (
              <button
                key={row.id}
                className="transfer-record-option"
                disabled={!!row.reconciliation || excluded.includes(row.id)}
                onClick={() => choose(row)}
              >
                <strong>
                  {row.account} · {number(row.quantity, 8)} {row.asset}
                </strong>
                <span>
                  {new Date(row.created_at).toLocaleString()} · {row.environment}
                </span>
                <small>
                  {row.native_id}
                  {row.reconciliation
                    ? ' · Already reserved'
                    : excluded.includes(row.id)
                      ? ' · Selected'
                      : ''}
                </small>
              </button>
            ))}
            {!data.data?.items.length && (
              <p className="footnote">
                No eligible records. Import completed funding history or change the search.
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
            <span>{data.data?.total || 0} records</span>
            <button
              className="button secondary tiny"
              disabled={!data.data?.has_more}
              onClick={() => setOffset(offset + 10)}
            >
              Next
            </button>
          </nav>
        </>
      )}
    </div>
  );
}

import { useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { Download, Plus, Flag, CheckCircle2 } from 'lucide-react';
import { AgentButton } from './agents';
import { ExpandableRows } from './expandable-rows';
import { Badge, Empty, ErrorState, Loading, Modal, Panel, PanelTitle, useToast } from './ui';
import { number, post, refresh } from '../lib/api';
import { useResource } from '../lib/hooks';
import './account-returns.css';

type Result = {
  opening: number;
  closing: number;
  net_external_flow: number;
  gain: number;
  weighted_capital: number;
  return_pct: number | null;
  return_note: string | null;
};
type Review = { classification: string; value: string; occurred_at: string; note: string };
type Flow = {
  event: {
    id: string;
    account_id: string;
    account: string;
    asset: string;
    quantity: number;
    direction: string;
    status: string;
    timestamp_ms: number;
    posted_ms: number | null;
    provenance?: string;
  };
  source_version: string;
  review: Review | null;
  review_current: boolean;
  transfer: { status: string } | null;
};
type Snapshot = {
  total: number;
  as_of: string;
  started_at: string;
  accounts: { id: string; label: string }[];
};
type Period = {
  id: string;
  label: string;
  revision: number;
  source: string;
  environment: string;
  closing: Record<string, Snapshot> | null;
  opening: Record<string, Snapshot>;
  account_ids: string[];
  result: Result | null;
  account_results: (Result & { account_id: string; label: string })[];
  flows: Flow[];
  blockers: string[];
  note: string;
  evidence_fingerprint: string;
  coverage: { confirmed: boolean; note: string; evidence_fingerprint: string } | null;
  audit: { created_at: string; action: string; revision: number }[];
};
type Header = {
  id: string;
  label: string;
  closing: boolean;
  environment: string;
  created_at: string;
};
const localTime = (value: string) => {
  const d = new Date(value);
  return new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 19);
};
const download = (id: string, data: unknown) => {
  const u = URL.createObjectURL(
    new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' }),
  );
  const a = document.createElement('a');
  a.href = u;
  a.download = `account-return-${id}.json`;
  a.click();
  URL.revokeObjectURL(u);
};

/** Fresh measurement boundaries and reviewed cash flows, kept separate from current value and FIFO. */
export function AccountReturns({ scope }: { scope: string }) {
  const [params, setParams] = useSearchParams();
  const periods = useResource<{ items: Header[] }>(
    '/account-returns?scope=' + encodeURIComponent(scope),
  );
  const selected = params.get('period') || periods.data?.items[0]?.id || '';
  const detail = useResource<Period>('/account-returns/' + selected, 15000, !!selected);
  const row = detail.data;
  const [create, setCreate] = useState(false),
    [label, setLabel] = useState('Account performance');
  const [removing, setRemoving] = useState(false);
  const [busy, setBusy] = useState(''),
    [editing, setEditing] = useState<Flow>(),
    [manual, setManual] = useState(false),
    [coverage, setCoverage] = useState(false);
  const toast = useToast();
  const act = async (path: string, body: unknown) => {
    setBusy(path);
    try {
      const result = await post<Period>(path, body);
      refresh();
      return result;
    } catch (e) {
      toast((e as Error).message, true);
      return undefined;
    } finally {
      setBusy('');
    }
  };
  const choose = (id: string) =>
    setParams((previous) => {
      const next = new URLSearchParams(previous);
      next.set('period', id);
      return next;
    });
  return (
    <Panel className="account-returns">
      <details>
        <summary>
          Investment performance <Badge>Cash-flow adjusted</Badge>
        </summary>
        <div className="account-returns-body">
          <PanelTitle
            title="Investment gains, separate from money moving in"
            subtitle="Measured periods · USDT reference values · Modified Dietz estimate"
            action={
              <button className="button secondary small" onClick={() => setCreate(true)}>
                <Plus size={14} /> Start period
              </button>
            }
          />
          <p className="returns-note">
            Start with a fresh opening valuation for this account view. Later, capture its closing
            valuation, review external cash flows and confirm funding coverage. Old chart points and
            FIFO profit are separate evidence.
          </p>
          {periods.error ? (
            <ErrorState message={periods.error} retry={periods.retry} />
          ) : periods.loading ? (
            <Loading />
          ) : !periods.data?.items.length ? (
            <Empty title="Begin a measured performance period">
              Choose one account, an exchange or all accounts above. The account set and price feed
              are frozen for each period. Missing prices prevent a misleading starting value.
            </Empty>
          ) : (
            <>
              <label className="returns-period-picker">
                Performance period
                <select
                  aria-label="Performance period"
                  value={selected}
                  onChange={(e) => choose(e.target.value)}
                >
                  {periods.data.items.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.label} · {new Date(p.created_at).toLocaleDateString()} ·{' '}
                      {p.closing ? 'Closed' : 'Measuring'}
                      {p.environment === 'demo' ? ' · Demo' : ''}
                    </option>
                  ))}
                </select>
              </label>
              {detail.error ? (
                <ErrorState message={detail.error} retry={detail.retry} />
              ) : !row ? (
                <Loading />
              ) : (
                <>
                  <div className="returns-actions">
                    <Badge tone={row.environment === 'demo' ? 'demo' : 'neutral'}>
                      {row.environment}
                    </Badge>
                    <span>
                      {row.account_ids.length} pinned accounts · {row.source}
                    </span>
                    <AgentButton module="accountant" context={{ return_period_id: row.id }} />
                    <button className="text-button" onClick={() => download(row.id, row)}>
                      <Download size={13} /> Export evidence
                    </button>
                    <button className="text-button" onClick={() => setRemoving(true)}>
                      Remove period…
                    </button>
                  </div>
                  {row.result ? (
                    <>
                      <div className="returns-metrics">
                        {[
                          ['Investment gain', `${number(row.result.gain)} USDT`],
                          ['Net external flow', `${number(row.result.net_external_flow)} USDT`],
                          [
                            'Period return',
                            row.result.return_pct === null
                              ? 'Unavailable'
                              : `${number(row.result.return_pct)}%`,
                          ],
                        ].map(([name, value]) => (
                          <div key={name}>
                            <small>{name}</small>
                            <strong className="monetary">{value}</strong>
                          </div>
                        ))}
                      </div>
                      {row.result.return_note && (
                        <p className="returns-note">{row.result.return_note}</p>
                      )}
                      {row.account_results.length > 1 && (
                        <div className="table-scroll">
                          <table>
                            <thead>
                              <tr>
                                <th>Account</th>
                                <th>Gain · USDT</th>
                                <th>External flow</th>
                                <th>Period return</th>
                              </tr>
                            </thead>
                            <tbody>
                              {row.account_results.map((a) => (
                                <tr key={a.account_id}>
                                  <td>{a.label}</td>
                                  <td>{number(a.gain)}</td>
                                  <td>{number(a.net_external_flow)}</td>
                                  <td>
                                    {a.return_pct === null
                                      ? 'Unavailable'
                                      : number(a.return_pct) + '%'}
                                  </td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                      )}
                    </>
                  ) : (
                    <div className="returns-blockers">
                      <strong>Return not available yet</strong>
                      <ul>
                        {row.blockers.map((text) => (
                          <li key={text}>{text}</li>
                        ))}
                      </ul>
                    </div>
                  )}
                  <div className="returns-actions">
                    {!row.closing ? (
                      <button
                        className="button secondary"
                        disabled={!!busy}
                        onClick={() =>
                          void act(`/account-returns/${row.id}/close`, { revision: row.revision })
                        }
                      >
                        <Flag size={14} />
                        {busy ? 'Capturing…' : 'Capture closing valuation'}
                      </button>
                    ) : (
                      <>
                        <button className="button small" onClick={() => setManual(true)}>
                          Add missing external flow
                        </button>
                        <button className="button small" onClick={() => setCoverage(true)}>
                          <CheckCircle2 size={14} /> Review coverage
                        </button>
                        <Link className="text-link" to="/trade?tab=history">
                          Import funding / review transfers →
                        </Link>
                      </>
                    )}
                  </div>
                  <details>
                    <summary>Valuation boundaries</summary>
                    {row.account_ids.map((id) => (
                      <p className="returns-note" key={id}>
                        {row.opening[id].accounts[0].label}: {number(row.opening[id].total)} USDT at{' '}
                        {new Date(row.opening[id].as_of).toLocaleString()}
                        {row.closing && (
                          <>
                            {' '}
                            → {number(row.closing[id].total)} USDT at{' '}
                            {new Date(row.closing[id].as_of).toLocaleString()}
                          </>
                        )}
                      </p>
                    ))}
                  </details>
                  {!!row.flows.length && (
                    <ExpandableRows total={row.flows.length} label="cash-flow observations">
                      {(visible) => (
                        <div className="table-scroll">
                          <table>
                            <thead>
                              <tr>
                                <th>Funding observation</th>
                                <th>Classification / value</th>
                                <th>Review</th>
                              </tr>
                            </thead>
                            <tbody>
                              {row.flows.slice(0, visible).map((flow) => (
                                <tr key={flow.event.id}>
                                  <td>
                                    <strong>{flow.event.account}</strong>
                                    <br />
                                    {flow.event.direction === 'in' ? '+' : '−'}
                                    {number(flow.event.quantity, 8)} {flow.event.asset}
                                    <br />
                                    <small>
                                      {flow.event.provenance === 'user_assertion'
                                        ? 'Manual USDT value assertion'
                                        : flow.event.status + ' · imported funding'}
                                    </small>
                                  </td>
                                  <td>
                                    {flow.review_current && flow.review
                                      ? `${flow.review.classification.replace('_', ' ')} · ${number(Number(flow.review.value))} USDT`
                                      : 'Needs review'}
                                    <br />
                                    <small>
                                      {flow.transfer?.status === 'confirmed'
                                        ? 'Confirmed own-account link'
                                        : ''}
                                    </small>
                                  </td>
                                  <td>
                                    {flow.event.provenance === 'user_assertion' ? (
                                      <button
                                        className="text-button"
                                        disabled={!!busy}
                                        onClick={() =>
                                          void act(
                                            `/account-returns/${row.id}/manual/${flow.event.id}/remove`,
                                            { revision: row.revision },
                                          )
                                        }
                                      >
                                        Remove assertion
                                      </button>
                                    ) : (
                                      <button
                                        className="button tiny"
                                        disabled={!row.closing}
                                        onClick={() => setEditing(flow)}
                                      >
                                        Review
                                      </button>
                                    )}
                                  </td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                      )}
                    </ExpandableRows>
                  )}
                  <p className="returns-note">{row.note}</p>
                  <details>
                    <summary>Recent review history · {row.audit.length}</summary>
                    {row.audit.map((a, i) => (
                      <p className="returns-note" key={i}>
                        {new Date(a.created_at).toLocaleString()} · {a.action.replaceAll('_', ' ')}{' '}
                        · revision {a.revision}
                      </p>
                    ))}
                  </details>
                </>
              )}
            </>
          )}
        </div>
      </details>
      {create && (
        <Modal title="Start a performance period" onClose={() => !busy && setCreate(false)}>
          <form
            className="workspace-form"
            onSubmit={async (e) => {
              e.preventDefault();
              const result = await act('/account-returns', { scope, label });
              if (result) {
                choose(result.id);
                setCreate(false);
                toast('Opening valuation saved.');
              }
            }}
          >
            <p>
              Capture fresh, fully priced spot balances for this view. This does not trade or move
              funds.
            </p>
            <label>
              Period name
              <input
                required
                maxLength={80}
                value={label}
                onChange={(e) => setLabel(e.target.value)}
              />
            </label>
            <button className="button primary" disabled={!!busy}>
              {busy ? 'Reading balances and prices…' : 'Capture opening valuation'}
            </button>
          </form>
        </Modal>
      )}
      {row && editing && (
        <FlowEditor
          period={row}
          flow={editing}
          busy={!!busy}
          save={async (body) => {
            if (await act(`/account-returns/${row.id}/flows/${editing.event.id}`, body))
              setEditing(undefined);
          }}
          close={() => setEditing(undefined)}
        />
      )}
      {row && manual && (
        <ManualEditor
          period={row}
          busy={!!busy}
          save={async (body) => {
            if (await act(`/account-returns/${row.id}/manual`, body)) setManual(false);
          }}
          close={() => setManual(false)}
        />
      )}
      {row && coverage && (
        <CoverageEditor
          period={row}
          busy={!!busy}
          save={async (body) => {
            if (await act(`/account-returns/${row.id}/coverage`, body)) setCoverage(false);
          }}
          close={() => setCoverage(false)}
        />
      )}
      {row && removing && (
        <Modal title="Remove saved performance period?" onClose={() => !busy && setRemoving(false)}>
          <p>
            Export evidence first if you need it. This removes the saved valuations and local review
            history. Native funding, fills and exchange accounts stay unchanged.
          </p>
          <button
            className="button primary"
            disabled={!!busy}
            onClick={async () => {
              if (await act(`/account-returns/${row.id}/remove`, { revision: row.revision })) {
                setRemoving(false);
                setParams((previous) => {
                  const next = new URLSearchParams(previous);
                  next.delete('period');
                  return next;
                });
                periods.retry();
              }
            }}
          >
            Remove saved period
          </button>
        </Modal>
      )}
    </Panel>
  );
}
function FlowEditor({
  period,
  flow,
  busy,
  save,
  close,
}: {
  period: Period;
  flow: Flow;
  busy: boolean;
  save: (body: unknown) => Promise<void>;
  close: () => void;
}) {
  const [kind, setKind] = useState(flow.review?.classification || 'external'),
    [value, setValue] = useState(flow.review?.value || ''),
    [at, setAt] = useState(
      localTime(
        flow.review?.occurred_at ||
          new Date(flow.event.posted_ms || flow.event.timestamp_ms).toISOString(),
      ),
    ),
    [note, setNote] = useState(flow.review?.note || '');
  return (
    <Modal title="Review cash-flow treatment" onClose={() => !busy && close()}>
      <form
        className="workspace-form"
        onSubmit={(e) => {
          e.preventDefault();
          void save({
            revision: period.revision,
            source_version: flow.source_version,
            classification: kind,
            value,
            occurred_at: new Date(at).toISOString(),
            note,
          });
        }}
      >
        <p>
          This records your accounting assertion. Verify wallet scope in Funding first. Historical
          principal values exclude fees; income and fees belong in performance.
        </p>
        <label>
          Classification
          <select value={kind} onChange={(e) => setKind(e.target.value)}>
            <option value="external">External contribution / withdrawal</option>
            <option value="own_transfer">Confirmed own-account transfer</option>
            <option value="performance">Investment income / performance effect</option>
            <option value="outside">Outside the measured wallet</option>
          </select>
        </label>
        <label>
          Historical principal value · USDT
          <input
            type="number"
            min="0"
            step="any"
            required
            value={value}
            onChange={(e) => setValue(e.target.value)}
          />
        </label>
        <label>
          Actual wallet movement time · local
          <input
            type="datetime-local"
            step="1"
            required
            value={at}
            onChange={(e) => setAt(e.target.value)}
          />
        </label>
        <label>
          Evidence / explanation
          <textarea
            required
            maxLength={1000}
            value={note}
            onChange={(e) => setNote(e.target.value)}
          />
        </label>
        <button className="button primary" disabled={busy}>
          Save reviewed treatment
        </button>
      </form>
    </Modal>
  );
}
function ManualEditor({
  period,
  busy,
  save,
  close,
}: {
  period: Period;
  busy: boolean;
  save: (body: unknown) => Promise<void>;
  close: () => void;
}) {
  const [account, setAccount] = useState(period.account_ids[0]),
    [direction, setDirection] = useState('in'),
    [value, setValue] = useState(''),
    [at, setAt] = useState(''),
    [note, setNote] = useState('');
  return (
    <Modal title="Add a missing external cash flow" onClose={() => !busy && close()}>
      <form
        className="workspace-form"
        onSubmit={(e) => {
          e.preventDefault();
          void save({
            revision: period.revision,
            account_id: account,
            direction,
            value,
            occurred_at: new Date(at).toISOString(),
            note,
          });
        }}
      >
        <p>
          A manual USDT principal-value assertion, separate from exchange records. Add only missing
          external flows; do not duplicate imported funding or transfers inside this account set.
        </p>
        <label>
          Account
          <select value={account} onChange={(e) => setAccount(e.target.value)}>
            {period.account_ids.map((id) => (
              <option key={id} value={id}>
                {period.opening[id].accounts[0].label}
              </option>
            ))}
          </select>
        </label>
        <label>
          Direction
          <select value={direction} onChange={(e) => setDirection(e.target.value)}>
            <option value="in">Contribution in</option>
            <option value="out">Withdrawal out</option>
          </select>
        </label>
        <label>
          Historical principal value · USDT
          <input
            type="number"
            min="0.00000001"
            step="any"
            required
            value={value}
            onChange={(e) => setValue(e.target.value)}
          />
        </label>
        <label>
          Movement time · local
          <input
            type="datetime-local"
            step="1"
            required
            value={at}
            onChange={(e) => setAt(e.target.value)}
          />
        </label>
        <label>
          Source / reason this flow is missing
          <textarea
            required
            maxLength={1000}
            value={note}
            onChange={(e) => setNote(e.target.value)}
          />
        </label>
        <button className="button primary" disabled={busy}>
          Add manual assertion
        </button>
      </form>
    </Modal>
  );
}
function CoverageEditor({
  period,
  busy,
  save,
  close,
}: {
  period: Period;
  busy: boolean;
  save: (body: unknown) => Promise<void>;
  close: () => void;
}) {
  const [confirmed, setConfirmed] = useState(false),
    [note, setNote] = useState('');
  return (
    <Modal title="Review funding coverage" onClose={() => !busy && close()}>
      <form
        className="workspace-form"
        onSubmit={(e) => {
          e.preventDefault();
          void save({
            revision: period.revision,
            evidence_fingerprint: period.evidence_fingerprint,
            confirmed,
            note,
          });
        }}
      >
        <p>
          Check every selected spot wallet over the whole period, including fiat funding, rewards,
          unsupported streams and missing transfers. Import completion is not proof of coverage.
          Remove duplicate manual entries if their native observations arrive later.
        </p>
        <label>
          <input
            type="checkbox"
            checked={confirmed}
            onChange={(e) => setConfirmed(e.target.checked)}
          />{' '}
          I reviewed all funding, classifications, timestamps and principal values, with no missing
          or duplicate flows.
        </label>
        <label>
          Evidence supporting coverage
          <textarea
            required
            maxLength={1000}
            value={note}
            onChange={(e) => setNote(e.target.value)}
          />
        </label>
        <button className="button primary" disabled={busy}>
          {confirmed ? 'Confirm reviewed coverage' : 'Mark coverage incomplete'}
        </button>
      </form>
    </Modal>
  );
}

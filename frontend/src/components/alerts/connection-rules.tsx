import { useState } from 'react';
import { Link } from 'react-router-dom';
import { Archive, ArrowUpRight, Pause, Pencil, Play, Plus, Radio, Undo2 } from 'lucide-react';
import { Badge, Empty, ErrorState, Loading, Modal, Panel, PanelTitle, useToast } from '../ui';
import { MarketSourceMark } from '../config-helper';
import { NotificationText } from '../notifications';
import { post, refresh } from '../../lib/api';
import { useResource } from '../../lib/hooks';
import { date } from '../../lib/strategy-monitor';
import {
  connectionSettingsURL,
  operationLabel,
  type ConnectionAlert,
  type ConnectionRulesData,
  type ConnectionAlertExample,
  type ConnectionSource,
} from '../../lib/connection-alerts';

/** Watch actual read outcomes without adding probes or changing a user's chosen feeds. */
export function ConnectionRules({
  example,
  initialSource,
}: {
  example: boolean;
  initialSource: string;
}) {
  const [archived, setArchived] = useState(false),
    [offset, setOffset] = useState(0);
  const [creating, setCreating] = useState(false),
    [editing, setEditing] = useState<ConnectionAlert>();
  const [busy, setBusy] = useState('');
  const toast = useToast();
  const rules = useResource<ConnectionRulesData>(
    `/connection-alerts?include_archived=${archived}&offset=${offset}`,
    5000,
    !example,
  );
  const sample = useResource<ConnectionAlertExample>('/connection-alerts/example', 0, example);
  const data = example ? sample.data?.rules : rules.data;
  const error = example ? sample.error : rules.error;
  const act = async (rule: ConnectionAlert, action: string) => {
    setBusy(rule.id);
    try {
      await post(`/connection-alerts/${rule.id}/action`, { action, revision: rule.revision });
      refresh();
    } catch (reason) {
      toast((reason as Error).message, true);
      refresh();
    } finally {
      setBusy('');
    }
  };
  return (
    <>
      <Panel className="full-panel">
        <PanelTitle
          title="Connection alerts"
          subtitle={`${data?.count ?? 0} of ${data?.limit ?? 50} non-archived rules · recorded reads only`}
          action={
            <button
              className="button primary small"
              disabled={example || !data || data.count >= data.limit}
              onClick={() => setCreating(true)}
            >
              <Plus size={14} /> New connection alert
            </button>
          }
        />
        <div className="strategy-alert-intro">
          <Radio size={18} />
          <p>
            Know when reads need attention. Watch consecutive transport failures from a source, and
            successful reads when they resume. Each operation is tracked separately. These alerts
            observe activity in Sibyl; they don’t poll a connection.
          </p>
        </div>
        <div className="strategy-alert-filters">
          <label className="alert-archive-toggle">
            <input
              type="checkbox"
              disabled={example}
              checked={archived}
              onChange={(e) => {
                setArchived(e.target.checked);
                setOffset(0);
              }}
            />{' '}
            Include archived
          </label>
          <Link className="text-button" to="/settings?tab=market">
            Source health <ArrowUpRight size={12} />
          </Link>
        </div>
        {data?.recording.status === 'partial' && (
          <p className="inline-alert padded">
            Some read evidence could not be saved. Gaps restart consecutive counts; alerts may miss
            a failure or recovery.
          </p>
        )}
        {error ? (
          <ErrorState message={error} retry={example ? sample.retry : rules.retry} />
        ) : !data ? (
          <Loading />
        ) : data.items.length ? (
          <div className="price-rule-list">
            {data.items.map((rule) => {
              const incidents = Object.entries(rule.operations).filter(
                ([, state]) => state.incident,
              );
              return (
                <article className="price-rule-card strategy-alert-card" key={rule.id}>
                  <div className="price-rule-heading">
                    <span className="activity-icon">
                      <MarketSourceMark source={rule.source_info} />
                    </span>
                    <div>
                      <h3>{rule.label || rule.source_info.name}</h3>
                      <p>
                        {rule.source_info.name} ·{' '}
                        {rule.source_info.kind === 'connection'
                          ? 'Saved exchange account'
                          : rule.source_info.kind === 'exchange'
                            ? 'Public exchange'
                            : 'Data API'}{' '}
                        · {rule.source_info.environment}
                      </p>
                      <div className="strategy-alert-tags">
                        <Badge tone={rule.status === 'armed' ? 'lime' : 'neutral'}>
                          {rule.status === 'armed' ? 'Watching reads' : rule.status}
                        </Badge>
                        {!!incidents.length && (
                          <Badge tone="peach">
                            {incidents.length} recorded incident{incidents.length === 1 ? '' : 's'}
                          </Badge>
                        )}
                      </div>
                    </div>
                  </div>
                  <div className="strategy-alert-groups">
                    <span>{rule.failures_required} consecutive failed reads</span>
                    <span>
                      {rule.notify_recovery
                        ? `Recovery after ${rule.successes_required} successful reads`
                        : 'Recovery notices off'}
                    </span>
                  </div>
                  {!!incidents.length && (
                    <div className="connection-alert-incidents">
                      {incidents.map(([op, state]) => (
                        <div key={op}>
                          <strong>{operationLabel(op)}</strong>
                          <span>
                            {state.successes
                              ? `${state.successes}/${rule.successes_required} confirming successful reads`
                              : 'Awaiting successful reads'}
                          </span>
                          <small>Last observed {date(state.at)}</small>
                        </div>
                      ))}
                    </div>
                  )}
                  {rule.tracking_note && (
                    <p className="footnote connection-alert-note">{rule.tracking_note}</p>
                  )}
                  <div className="price-rule-evidence">
                    <span>{rule.notifications} notifications retained</span>
                    <span>Last check {date(rule.last_checked_at)}</span>
                    <span>Last observed read {date(rule.last_event_at)}</span>
                  </div>
                  <div className="price-rule-footer">
                    <span className="muted">Last armed {date(rule.armed_at)}</span>
                    <div className="price-rule-actions">
                      {!example && (
                        <Link className="text-button" to={connectionSettingsURL(rule.source)}>
                          Source settings <ArrowUpRight size={12} />
                        </Link>
                      )}
                      {rule.status === 'archived' ? (
                        <button
                          className="button secondary tiny"
                          disabled={!!busy || example}
                          onClick={() => act(rule, 'restore')}
                        >
                          <Undo2 size={13} /> Restore paused
                        </button>
                      ) : (
                        <>
                          <button
                            className="icon-button"
                            disabled={!!busy || example}
                            aria-label={`Edit ${rule.label || rule.source_info.name} connection alert`}
                            title="Edit; saves paused"
                            onClick={() => setEditing(rule)}
                          >
                            <Pencil size={14} />
                          </button>
                          <button
                            className="button secondary tiny"
                            disabled={!!busy || example}
                            onClick={() => act(rule, rule.status === 'armed' ? 'pause' : 'arm')}
                          >
                            {rule.status === 'armed' ? <Pause size={13} /> : <Play size={13} />}
                            {rule.status === 'armed' ? 'Pause alert' : 'Resume alert'}
                          </button>
                          <button
                            className="icon-button"
                            disabled={!!busy || example}
                            aria-label={`Archive ${rule.label || rule.source_info.name} connection alert`}
                            title="Archive alert; retain notifications"
                            onClick={() => act(rule, 'archive')}
                          >
                            <Archive size={14} />
                          </button>
                        </>
                      )}
                    </div>
                  </div>
                </article>
              );
            })}
          </div>
        ) : (
          <Empty title="Keep an eye on your sources">
            Create a watch for a public market feed, data API or saved exchange account. No account
            or AI model is required. Existing read history is not replayed.
          </Empty>
        )}
        {data && !example && (offset > 0 || data.total > 50) && (
          <div className="alert-pagination">
            <button
              className="button secondary tiny"
              disabled={!offset}
              onClick={() => setOffset(Math.max(0, offset - 50))}
            >
              Previous rules
            </button>
            <span>
              {offset + 1}–{Math.min(offset + 50, data.total)} of {data.total}
            </span>
            <button
              className="button secondary tiny"
              disabled={offset + 50 >= data.total}
              onClick={() => setOffset(offset + 50)}
            >
              Next rules
            </button>
          </div>
        )}
        <p className="footnote padded">
          No recent reads means no current connection assessment. Counts restart after a
          session/profile change, a recording gap or more than five minutes between reads.
          Unsupported requests aren’t connection failures. Recovery confirms successful transport
          reads of the same operation, not fully validated data or account readiness. Delivery stays
          in-app.
        </p>
      </Panel>
      {example && sample.data && (
        <Panel className="strategy-alert-example">
          <PanelTitle
            title="Example notification"
            subtitle="Illustrative only · no connection has been tested"
          />
          <div className="notification-copy">
            <NotificationText item={sample.data.inbox.items[0]} />
          </div>
        </Panel>
      )}
      {(creating || editing) && data && (
        <Modal
          title={editing ? 'Edit connection alert' : 'New connection alert'}
          onClose={() => {
            setCreating(false);
            setEditing(undefined);
          }}
        >
          <ConnectionForm
            key={editing?.id || 'new'}
            rule={editing}
            sources={data.sources}
            initialSource={initialSource}
            onSaved={() => {
              setCreating(false);
              setEditing(undefined);
              setOffset(0);
              refresh();
              toast(
                editing
                  ? 'Changes saved paused. Resume when ready.'
                  : 'Watching future read evidence.',
              );
            }}
          />
        </Modal>
      )}
    </>
  );
}

function ConnectionForm({
  rule,
  sources,
  initialSource,
  onSaved,
}: {
  rule?: ConnectionAlert;
  sources: ConnectionSource[];
  initialSource: string;
  onSaved: () => void;
}) {
  const choices =
    rule && !sources.some((s) => s.id === rule.source) ? [...sources, rule.source_info] : sources;
  const [source, setSource] = useState(
    rule?.source ||
      (choices.some((s) => s.id === initialSource) ? initialSource : choices[0]?.id || ''),
  );
  const [failures, setFailures] = useState(rule?.failures_required || 3),
    [successes, setSuccesses] = useState(rule?.successes_required || 2);
  const [recovery, setRecovery] = useState(rule?.notify_recovery ?? true),
    [label, setLabel] = useState(rule?.label || '');
  const [busy, setBusy] = useState(false),
    [error, setError] = useState('');
  const selected = choices.find((s) => s.id === source);
  return (
    <form
      className="form price-alert-form"
      onSubmit={async (e) => {
        e.preventDefault();
        setBusy(true);
        setError('');
        try {
          await post(rule ? `/connection-alerts/${rule.id}/edit` : '/connection-alerts', {
            source,
            failures_required: failures,
            successes_required: successes,
            notify_recovery: recovery,
            label,
            ...(rule ? { revision: rule.revision } : {}),
          });
          onSaved();
        } catch (reason) {
          setError((reason as Error).message);
          refresh();
        } finally {
          setBusy(false);
        }
      }}
    >
      <label>
        Source
        <select required disabled={busy} value={source} onChange={(e) => setSource(e.target.value)}>
          {choices.map((s) => (
            <option value={s.id} key={s.id}>
              {s.name} · {s.environment}
              {!s.available ? ' · unavailable' : ''}
            </option>
          ))}
        </select>
      </label>
      {selected && (
        <div className="connection-alert-source">
          <MarketSourceMark source={selected} />
          <span>
            {selected.kind === 'connection'
              ? 'Saved account reads'
              : selected.kind === 'exchange'
                ? 'Public exchange reads'
                : 'Data API reads'}
            <small>{selected.id}</small>
          </span>
          <Badge>{selected.environment}</Badge>
        </div>
      )}
      <div className="form-row">
        <label>
          Failed reads before notifying
          <select
            disabled={busy}
            value={failures}
            onChange={(e) => setFailures(Number(e.target.value))}
          >
            {Array.from({ length: 10 }, (_, i) => (
              <option value={i + 1} key={i}>
                {i + 1} consecutive {i ? 'reads' : 'read'}
              </option>
            ))}
          </select>
        </label>
        <label>
          Successful reads to confirm recovery
          <select
            disabled={busy}
            value={successes}
            onChange={(e) => setSuccesses(Number(e.target.value))}
          >
            {Array.from({ length: 5 }, (_, i) => (
              <option value={i + 1} key={i}>
                {i + 1} consecutive {i ? 'reads' : 'read'}
              </option>
            ))}
          </select>
        </label>
      </div>
      <label className="alert-archive-toggle">
        <input
          type="checkbox"
          disabled={busy}
          checked={recovery}
          onChange={(e) => setRecovery(e.target.checked)}
        />{' '}
        Notify when successful reads resume
      </label>
      <label>
        <span>
          Name <small>Optional</small>
        </span>
        <input
          maxLength={80}
          disabled={busy}
          value={label}
          onChange={(e) => setLabel(e.target.value)}
          placeholder="My market feed"
        />
      </label>
      <p className="footnote">
        Watches future recorded transport reads, separately for each operation. This does not poll a
        provider, activate an account or change your selected feed. Demo is offline; use View
        example to explore.{' '}
        {rule && 'Changes save paused. Resume starts a fresh observation window.'}
      </p>
      {error && (
        <p className="form-error" role="alert">
          {error}
        </p>
      )}
      <button className="button primary" disabled={busy || !source}>
        <Radio size={14} />
        {busy ? 'Saving…' : rule ? 'Save paused' : 'Watch read failures'}
      </button>
    </form>
  );
}

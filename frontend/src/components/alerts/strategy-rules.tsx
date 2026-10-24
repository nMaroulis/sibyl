import { useState } from 'react';
import { Link } from 'react-router-dom';
import { Archive, ArrowUpRight, Bell, Pause, Pencil, Play, Plus, Undo2, Waves } from 'lucide-react';
import { Badge, Empty, ErrorState, Loading, Modal, Panel, PanelTitle, useToast } from '../ui';
import { NotificationText, type Inbox } from '../notifications';
import { post, refresh } from '../../lib/api';
import { useResource } from '../../lib/hooks';
import { date, monitorURL } from '../../lib/strategy-monitor';
import type { Job } from '../../lib/types';
import type {
  StrategyAlert,
  StrategyAlertGroup,
  StrategyAlertRules,
} from '../../lib/strategy-alerts';

export type StrategyAlertExample = { rules: StrategyAlertRules; inbox: Inbox };

/** Durable journal subscriptions, with examples kept separate from real local rules. */
export function StrategyRules({ example, jobId }: { example: boolean; jobId: string }) {
  const [archived, setArchived] = useState(false),
    [offset, setOffset] = useState(0);
  const [creating, setCreating] = useState(false),
    [editing, setEditing] = useState<StrategyAlert>();
  const [busy, setBusy] = useState('');
  const toast = useToast();
  const rules = useResource<StrategyAlertRules>(
    `/strategy-alerts?include_archived=${archived}&offset=${offset}${jobId ? `&job_id=${encodeURIComponent(jobId)}` : ''}`,
    5000,
    !example,
  );
  const sample = useResource<StrategyAlertExample>('/strategy-alerts/example', 0, example);
  const jobs = useResource<Job[]>('/strategies/jobs', 0, creating || !!editing);
  const data = example ? sample.data?.rules : rules.data;
  const error = example ? sample.error : rules.error;
  const action = async (rule: StrategyAlert, action: string) => {
    setBusy(rule.id);
    try {
      await post(`/strategy-alerts/${rule.id}/action`, { action, revision: rule.revision });
      refresh();
    } catch (error) {
      toast((error as Error).message, true);
      refresh();
    } finally {
      setBusy('');
    }
  };
  return (
    <>
      <Panel className="full-panel">
        <PanelTitle
          title="Strategy alerts"
          subtitle={
            jobId && !example
              ? `Showing ${data?.total ?? 0} for this run · ${data?.count ?? 0} of ${data?.limit ?? 50} workspace rules`
              : `${data?.count ?? 0} of ${data?.limit ?? 50} non-archived rules · future journal events from selected runs`
          }
          action={
            <button
              className="button primary small"
              disabled={example || !data || data.count >= data.limit}
              onClick={() => setCreating(true)}
            >
              <Plus size={14} /> New strategy alert
            </button>
          }
        />
        <div className="strategy-alert-intro">
          <Waves size={18} />
          <p>
            Know when a run needs attention. Watch pauses, evaluation errors and recovery, or its
            lifecycle. Notifications stay in Sibyl and link to the exact run. Pausing an alert only
            pauses notifications.
          </p>
        </div>
        <div className="strategy-alert-filters">
          <label className="alert-archive-toggle">
            <input
              type="checkbox"
              checked={archived}
              disabled={example}
              onChange={(e) => {
                setArchived(e.target.checked);
                setOffset(0);
              }}
            />{' '}
            Include archived
          </label>
          {jobId && !example && (
            <Link className="text-button" to="/alerts?tab=strategies">
              Show all strategy alerts
            </Link>
          )}
        </div>
        {error ? (
          <ErrorState message={error} retry={example ? sample.retry : rules.retry} />
        ) : !data ? (
          <Loading />
        ) : data.items.length ? (
          <div className="price-rule-list">
            {data.items.map((rule) => (
              <article className="price-rule-card strategy-alert-card" key={rule.id}>
                <div className="price-rule-heading">
                  <span className="activity-icon">
                    <Waves size={18} />
                  </span>
                  <div>
                    <h3>{rule.label || rule.run.name}</h3>
                    <p>
                      {rule.run.name} · {rule.run.symbol} · {rule.run.timeframe} · run{' '}
                      {rule.job_id.slice(0, 8)}
                    </p>
                    <div className="strategy-alert-tags">
                      <Badge>
                        {rule.run.mode === 'paper' ? 'Paper execution' : 'Exchange execution'}
                      </Badge>
                      {rule.run.environment === 'demo' ? (
                        <Badge tone="demo">Demo</Badge>
                      ) : rule.run.environment === 'test' ? (
                        <Badge tone="peach">Test environment</Badge>
                      ) : null}
                      <Badge tone={rule.status === 'armed' ? 'lime' : 'neutral'}>
                        {rule.status === 'armed' ? 'Watching' : rule.status}
                      </Badge>
                    </div>
                  </div>
                </div>
                <div className="strategy-alert-groups">
                  {rule.events.map((group) => (
                    <span key={group}>
                      <Bell size={12} />
                      {data.groups.find((g) => g.id === group)?.name ?? group}
                    </span>
                  ))}
                </div>
                <div className="price-rule-evidence">
                  <span>
                    {rule.notifications} notification{rule.notifications === 1 ? '' : 's'} retained
                  </span>
                  <span>Last check {date(rule.last_checked_at)}</span>
                  <span>Last journal event {date(rule.last_event_at)}</span>
                  <span>
                    {rule.run.source_label}
                    {rule.run.account ? ` · ${rule.run.account}` : ''}
                  </span>
                </div>
                <div className="price-rule-footer">
                  <span className="muted">Last armed {date(rule.armed_at)}</span>
                  <div className="price-rule-actions">
                    <Link
                      className={`text-button ${example ? 'disabled-link' : ''}`}
                      aria-disabled={example}
                      tabIndex={example ? -1 : undefined}
                      to={example ? '#' : monitorURL(rule.job_id)}
                      onClick={(e) => {
                        if (example) e.preventDefault();
                      }}
                    >
                      Open monitor <ArrowUpRight size={12} />
                    </Link>
                    {rule.status === 'archived' ? (
                      <button
                        className="button secondary tiny"
                        disabled={!!busy || example}
                        onClick={() => action(rule, 'restore')}
                      >
                        <Undo2 size={13} /> Restore paused
                      </button>
                    ) : (
                      <>
                        <button
                          className="icon-button"
                          aria-label={`Edit ${rule.label || rule.run.name} strategy alert`}
                          title="Edit; saves paused"
                          disabled={!!busy || example}
                          onClick={() => setEditing(rule)}
                        >
                          <Pencil size={14} />
                        </button>
                        <button
                          className="button secondary tiny"
                          disabled={!!busy || example}
                          onClick={() => action(rule, rule.status === 'armed' ? 'pause' : 'arm')}
                        >
                          {rule.status === 'armed' ? <Pause size={13} /> : <Play size={13} />}{' '}
                          {rule.status === 'armed' ? 'Pause alert' : 'Resume alert'}
                        </button>
                        <button
                          className="icon-button"
                          aria-label={`Archive ${rule.label || rule.run.name} strategy alert`}
                          title="Archive alert; retain notifications"
                          disabled={!!busy || example}
                          onClick={() => action(rule, 'archive')}
                        >
                          <Archive size={14} />
                        </button>
                      </>
                    )}
                  </div>
                </div>
              </article>
            ))}
          </div>
        ) : (
          <Empty title="Stay close to your strategies">
            Create an alert for a saved paper or exchange run. Existing journal history is not
            replayed. <Link to="/strategies?view=monitor">Open your strategy runs ↗</Link>
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
          Only committed journal events generate notifications. Manual and safety pauses both count.
          Armed rules catch up after a restart; creating, editing or resuming a rule starts fresh.
          These alerts do not detect silent worker outages, change execution, cancel orders or close
          positions.
        </p>
      </Panel>
      {example && sample.data && (
        <Panel className="strategy-alert-example">
          <PanelTitle
            title="Example notification"
            subtitle="Illustrative journal evidence · no run or rule was created"
          />
          <div className="notification-copy">
            <NotificationText item={sample.data.inbox.items[0]} />
          </div>
        </Panel>
      )}
      {(creating || editing) && (
        <Modal
          title={editing ? 'Edit strategy alert' : 'New strategy alert'}
          className="price-alert-dialog"
          onClose={() => {
            setCreating(false);
            setEditing(undefined);
          }}
        >
          {jobs.error ? (
            <ErrorState message={jobs.error} retry={jobs.retry} />
          ) : !jobs.data ? (
            <Loading />
          ) : (
            <StrategyRuleForm
              key={editing?.id || 'new'}
              rule={editing}
              jobs={jobs.data}
              initialJobId={jobId}
              groups={data?.groups ?? []}
              onSaved={() => {
                setCreating(false);
                setEditing(undefined);
                setOffset(0);
                refresh();
                toast(
                  editing
                    ? 'Strategy alert saved paused. Resume it when ready.'
                    : 'Watching future strategy events.',
                );
              }}
            />
          )}
        </Modal>
      )}
    </>
  );
}

function StrategyRuleForm({
  rule,
  jobs,
  initialJobId,
  groups,
  onSaved,
}: {
  rule?: StrategyAlert;
  jobs: Job[];
  initialJobId: string;
  groups: StrategyAlertRules['groups'];
  onSaved: () => void;
}) {
  const [jobId, setJobId] = useState(rule?.job_id || initialJobId || jobs[0]?.id || '');
  const [events, setEvents] = useState<StrategyAlertGroup[]>(rule?.events || ['attention']);
  const [label, setLabel] = useState(rule?.label || '');
  const [busy, setBusy] = useState(false),
    [error, setError] = useState('');
  return (
    <form
      className="form strategy-alert-form"
      onSubmit={async (e) => {
        e.preventDefault();
        setBusy(true);
        setError('');
        try {
          await post(rule ? `/strategy-alerts/${rule.id}/edit` : '/strategy-alerts', {
            job_id: jobId,
            events,
            label,
            ...(rule ? { revision: rule.revision } : {}),
          });
          onSaved();
        } catch (e) {
          setError((e as Error).message);
        } finally {
          setBusy(false);
        }
      }}
    >
      <label>
        Strategy run
        <select value={jobId} onChange={(e) => setJobId(e.target.value)} required disabled={busy}>
          <option value="">Choose a saved run</option>
          {jobs.map((job) => (
            <option key={job.id} value={job.id}>
              {job.parameters.strategy} · {job.parameters.symbol} · {job.parameters.timeframe} ·{' '}
              {job.status} · {job.mode === 'exchange' ? `Exchange · ${job.environment}` : 'Paper'} ·{' '}
              {job.id.slice(0, 8)}
            </option>
          ))}
        </select>
      </label>
      {!jobs.length && (
        <p className="inline-alert">
          There are no saved strategy runs.{' '}
          <Link to="/strategies?view=monitor">Open Strategies</Link> to get started.
        </p>
      )}
      <label>
        Alert name <span className="muted">Optional</span>
        <input
          value={label}
          onChange={(e) => setLabel(e.target.value)}
          maxLength={80}
          placeholder="e.g. My trend strategy"
          disabled={busy}
        />
      </label>
      <fieldset className="strategy-alert-event-choices">
        <legend>Notify me about</legend>
        {groups.map((group) => (
          <label key={group.id} className={events.includes(group.id) ? 'selected' : ''}>
            <input
              type="checkbox"
              checked={events.includes(group.id)}
              disabled={busy}
              onChange={(e) =>
                setEvents(
                  e.target.checked
                    ? [...events, group.id]
                    : events.filter((item) => item !== group.id),
                )
              }
            />
            <span>
              <strong>{group.name}</strong>
              <small>{group.description}</small>
            </span>
          </label>
        ))}
      </fieldset>
      <p className="footnote">
        {rule
          ? 'Saving leaves this alert paused. Resume starts at the current journal tail.'
          : 'Only future journal events are watched. Existing errors and lifecycle history will not notify immediately.'}{' '}
        This changes notifications only; it never starts, pauses or trades a strategy.
      </p>
      {error && (
        <div className="inline-alert" role="alert">
          {error}
        </div>
      )}
      <button className="button primary" disabled={busy || !jobId || !events.length}>
        {busy ? 'Saving…' : rule ? 'Save paused' : 'Watch strategy events'}
      </button>
    </form>
  );
}

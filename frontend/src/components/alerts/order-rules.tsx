import '../account-returns.css';
import { useState } from 'react';
import { Link } from 'react-router-dom';
import { Archive, Pause, Pencil, Play, Plus, Undo2 } from 'lucide-react';
import { Badge, Empty, ErrorState, Loading, Modal, Panel, PanelTitle, useToast } from '../ui';
import { AlertDeliveryButton } from './delivery';
import { useResource } from '../../lib/hooks';
import { post, refresh } from '../../lib/api';
import type { AccountSelection } from '../../lib/types';

type Rule = {
  id: string;
  account_id: string;
  source_label: string;
  environment: string;
  label: string;
  events: string[];
  revision: number;
  status: string;
  notifications: number;
  last_checked_at: string | null;
  error: string | null;
};
type Data = {
  items: Rule[];
  total: number;
  groups: { id: string; name: string }[];
  offset: number;
  limit: number;
};
/** Future-only local observations; no subscription adds provider polling or execution permissions. */
export function OrderRules({ example }: { example: boolean }) {
  const [archived, setArchived] = useState(false),
    [offset, setOffset] = useState(0),
    [editing, setEditing] = useState<Rule | null | undefined>();
  const [busy, setBusy] = useState('');
  const toast = useToast();
  const state = useResource<Data>(
    `/order-alerts?include_archived=${archived}&offset=${offset}`,
    5000,
    !example,
  );
  const accounts = useResource<AccountSelection>('/accounts', 0, !example);
  const act = async (rule: Rule, action: string) => {
    setBusy(rule.id);
    try {
      await post(`/order-alerts/${rule.id}/action`, { revision: rule.revision, action });
      refresh();
    } catch (e) {
      toast((e as Error).message, true);
      refresh();
    } finally {
      setBusy('');
    }
  };
  return (
    <Panel className="full-panel">
      <PanelTitle
        title="Order & fill notifications"
        subtitle="Per account · retained observations · future-only subscriptions"
        action={
          <button
            className="button primary small"
            disabled={example || !accounts.data?.accounts.length}
            onClick={() => setEditing(null)}
          >
            <Plus size={13} /> New execution alert
          </button>
        }
      />
      <p className="returns-note">
        Watch partial fills, completed orders, cancellations, imported execution corrections and
        execution problems. These alerts read records Sibyl already observes; they do not enable
        tracking, submit orders or add exchange polling. Older imported fills are labeled as
        imported evidence. An order total and its individual fills can produce separate
        observations.
      </p>
      {example ? (
        <Empty title="Explore using a Demo account">
          <Link to="/settings?tab=exchanges">Activate Demo in exchange settings</Link> to create
          real subscriptions for its simulated order observations. No sample rule is silently saved.
        </Empty>
      ) : state.error ? (
        <ErrorState message={state.error} retry={state.retry} />
      ) : state.loading ? (
        <Loading />
      ) : (
        <>
          <label className="returns-actions">
            <input
              type="checkbox"
              checked={archived}
              onChange={(e) => {
                setArchived(e.target.checked);
                setOffset(0);
              }}
            />{' '}
            Include archived
          </label>
          {!state.data?.items.length ? (
            <Empty title="No execution subscriptions">
              Add one for a saved account. Existing journal entries are skipped when creating,
              editing or resuming a subscription.
            </Empty>
          ) : (
            <div className="strategy-alert-rules">
              {state.data.items.map((rule) => (
                <article className="panel padded" key={rule.id}>
                  <div className="returns-actions">
                    <strong>{rule.label || rule.source_label}</strong>
                    <Badge tone={rule.environment === 'demo' ? 'demo' : 'neutral'}>
                      {rule.environment}
                    </Badge>
                    <Badge>{rule.status}</Badge>
                  </div>
                  <p className="returns-note">
                    {rule.events
                      .map((id) => state.data?.groups.find((g) => g.id === id)?.name || id)
                      .join(' · ')}
                    <br />
                    {rule.notifications} retained notifications · last checked{' '}
                    {rule.last_checked_at
                      ? new Date(rule.last_checked_at).toLocaleString()
                      : 'not yet'}
                  </p>
                  {rule.error && <p className="form-error">{rule.error}</p>}
                  <div className="returns-actions">
                    {rule.status === 'archived' ? (
                      <button
                        className="button tiny"
                        disabled={!!busy}
                        onClick={() => void act(rule, 'restore')}
                      >
                        <Undo2 size={12} /> Restore paused
                      </button>
                    ) : (
                      <>
                        <button
                          className="button tiny"
                          disabled={!!busy}
                          onClick={() => void act(rule, rule.status === 'armed' ? 'pause' : 'arm')}
                        >
                          {rule.status === 'armed' ? <Pause size={12} /> : <Play size={12} />}{' '}
                          {rule.status === 'armed' ? 'Pause' : 'Resume'}
                        </button>
                        <button className="button tiny" onClick={() => setEditing(rule)}>
                          <Pencil size={12} /> Edit
                        </button>
                        <AlertDeliveryButton kind="order" rule={rule.id} />
                        <button
                          className="text-button"
                          disabled={!!busy}
                          onClick={() => void act(rule, 'archive')}
                        >
                          <Archive size={12} /> Archive
                        </button>
                      </>
                    )}
                  </div>
                </article>
              ))}
            </div>
          )}
          <div className="returns-actions">
            <button
              className="button small"
              disabled={!offset}
              onClick={() => setOffset((v) => Math.max(0, v - 50))}
            >
              Previous
            </button>
            <span>
              {Math.min(offset + 50, state.data?.total || 0)} of {state.data?.total || 0} rules
            </span>
            <button
              className="button small"
              disabled={offset + 50 >= (state.data?.total || 0)}
              onClick={() => setOffset((v) => v + 50)}
            >
              Next
            </button>
            <Link to="/alerts?tab=inbox" className="text-link">
              Open notification inbox →
            </Link>
          </div>
        </>
      )}
      {editing !== undefined && accounts.data && state.data && (
        <Editor
          rule={editing}
          accounts={accounts.data.accounts}
          groups={state.data.groups}
          close={() => setEditing(undefined)}
        />
      )}
    </Panel>
  );
}
function Editor({
  rule,
  accounts,
  groups,
  close,
}: {
  rule: Rule | null;
  accounts: AccountSelection['accounts'];
  groups: Data['groups'];
  close: () => void;
}) {
  const [account, setAccount] = useState(rule?.account_id || accounts[0]?.id || ''),
    [label, setLabel] = useState(rule?.label || ''),
    [events, setEvents] = useState(rule?.events || ['fills', 'cancellations', 'attention']),
    [busy, setBusy] = useState(false),
    [error, setError] = useState('');
  return (
    <Modal
      title={rule ? 'Edit execution alert' : 'New execution alert'}
      onClose={() => !busy && close()}
    >
      <form
        className="workspace-form"
        onSubmit={async (e) => {
          e.preventDefault();
          setBusy(true);
          setError('');
          try {
            await post(rule ? `/order-alerts/${rule.id}/edit` : '/order-alerts', {
              account_id: account,
              label,
              events,
              ...(rule ? { revision: rule.revision } : {}),
            });
            refresh();
            close();
          } catch (reason) {
            setError((reason as Error).message);
          } finally {
            setBusy(false);
          }
        }}
      >
        <label>
          Account
          <select value={account} onChange={(e) => setAccount(e.target.value)}>
            {accounts.map((a) => (
              <option key={a.id} value={a.id}>
                {a.label} · {a.exchange}
                {a.sandbox ? ' · Test' : ''}
              </option>
            ))}
          </select>
        </label>
        <label>
          Name
          <input maxLength={80} value={label} onChange={(e) => setLabel(e.target.value)} />
        </label>
        <fieldset>
          <legend>Notify me about</legend>
          {groups.map((g) => (
            <label className="returns-actions" key={g.id}>
              <input
                type="checkbox"
                checked={events.includes(g.id)}
                onChange={(e) =>
                  setEvents(e.target.checked ? [...events, g.id] : events.filter((x) => x !== g.id))
                }
              />
              {g.name}
            </label>
          ))}
        </fieldset>
        <p className="returns-note">
          {rule
            ? 'Saving pauses this rule. Resume to start a new future-only baseline.'
            : 'Starts after existing observations. Telegram delivery is selected separately after saving.'}
        </p>
        {error && <p className="form-error">{error}</p>}
        <button className="button primary" disabled={busy || !account || !events.length}>
          {busy ? 'Saving…' : 'Save subscription'}
        </button>
      </form>
    </Modal>
  );
}

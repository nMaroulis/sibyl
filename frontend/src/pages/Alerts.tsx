import { useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import {
  Archive,
  ArrowUpRight,
  Bell,
  CheckCheck,
  Inbox as InboxIcon,
  ListChecks,
  Pause,
  Pencil,
  Play,
  Plus,
  RefreshCw,
  Undo2,
} from 'lucide-react';
import {
  Badge,
  Empty,
  ErrorState,
  Loading,
  Modal,
  PageTitle,
  Panel,
  PanelTitle,
  useToast,
} from '../components/ui';
import { SectionPanel, SectionTabs } from '../components/section-tabs';
import { MarketSelector, type SpotCatalog } from '../components/market-controls';
import { MarketSourcePicker } from '../components/market-source-picker';
import {
  conditionLabel,
  NotificationText,
  type Inbox,
  type PriceCondition,
} from '../components/notifications';
import { number, post, refresh } from '../lib/api';
import { useResource } from '../lib/hooks';
import type { MarketSettings } from '../lib/types';

type PriceRule = {
  id: string;
  label: string;
  source: string;
  source_label: string;
  environment: string;
  symbol: string;
  condition: PriceCondition;
  repeat: 'once' | 'after_reset';
  cooldown_seconds: number;
  cooldown_until: number;
  waiting_reset: boolean;
  baseline_at: string | null;
  evaluation_note: string | null;
  revision: number;
  threshold: number;
  status: 'armed' | 'paused' | 'triggered' | 'archived';
  cycle: number;
  created_at: string;
  triggered_at: string | null;
  last_checked_at: string | null;
  last_price: number | null;
  observed_at: string | null;
  next_check: number;
  failures: number;
  error: string | null;
};
type Rules = {
  items: PriceRule[];
  limit: number;
  count: number;
  total: number;
  offset: number;
  page_size: number;
};
type Example = { rules: Rules; inbox: Inbox };
const sections = [
  { id: 'rules', label: 'Price rules', icon: ListChecks },
  { id: 'inbox', label: 'Inbox', icon: InboxIcon },
];
const ruleState = (rule: PriceRule) =>
  rule.status !== 'armed'
    ? rule.status
    : rule.waiting_reset
      ? 'Waiting for reset'
      : rule.cooldown_until > Date.now() / 1000
        ? 'Cooling down'
        : rule.condition.startsWith('crosses_') && !rule.baseline_at
          ? 'Awaiting first quote'
          : 'Watching';

/** Local alerts work with public prices independently of accounts or an LLM. */
export function Alerts() {
  const [params, setParams] = useSearchParams();
  const tab = params.get('tab') === 'inbox' ? 'inbox' : 'rules';
  const [showArchived, setArchived] = useState(false);
  const [example, setExample] = useState(false);
  const [creating, setCreating] = useState(false);
  const [editing, setEditing] = useState<PriceRule>();
  const [busy, setBusy] = useState('');
  const [offset, setOffset] = useState(0);
  const [ruleOffset, setRuleOffset] = useState(0);
  const rules = useResource<Rules>(
    `/alerts?include_archived=${showArchived}&offset=${ruleOffset}`,
    10000,
    !example,
  );
  const inbox = useResource<Inbox>(`/notifications?limit=20&offset=${offset}`, 10000, !example);
  const sample = useResource<Example>('/alerts/example', 0, example);
  const settings = useResource<MarketSettings>('/settings/market', 0, creating || !!editing);
  const toast = useToast();
  const ruleData = example ? sample.data?.rules : rules.data;
  const inboxData = example ? sample.data?.inbox : inbox.data;
  const action = async (id: string, kind: string) => {
    if (example) return;
    setBusy(id);
    try {
      await post(
        `/alerts/${id}/${kind === 'check' ? 'check' : 'action'}`,
        kind === 'check' ? {} : { action: kind },
      );
      refresh();
    } catch (reason) {
      toast((reason as Error).message, true);
    } finally {
      setBusy('');
    }
  };
  const read = async (id?: string) => {
    if (example) return;
    setBusy(id || 'all');
    try {
      await post(id ? `/notifications/${id}/read` : '/notifications/read-all', {});
      refresh();
    } catch (reason) {
      toast((reason as Error).message, true);
    } finally {
      setBusy('');
    }
  };
  const error = example ? sample.error : tab === 'rules' ? rules.error : inbox.error;
  const retry = example ? sample.retry : tab === 'rules' ? rules.retry : inbox.retry;
  return (
    <>
      <PageTitle
        title="Alerts"
        description="A little less watching. A heads-up when a price reaches your level."
        action={
          <>
            <button
              className="button secondary"
              onClick={() => {
                setExample(!example);
                setOffset(0);
                setRuleOffset(0);
              }}
            >
              {example ? 'Return to my alerts' : 'View example'}
            </button>
            <button
              className="button primary"
              onClick={() => {
                setExample(false);
                setCreating(true);
              }}
            >
              <Plus size={15} /> New price alert
            </button>
          </>
        }
      />
      <div className="alert-delivery-note">
        <Bell size={17} />
        <span>
          <strong>In-app notifications</strong> · One-time or repeat alerts with reset and cooldown.
          The Sibyl API must be running to check prices. No connected account or AI model is needed.
        </span>
      </div>
      {example && (
        <div className="alert-example-banner">
          <Badge tone="demo">Illustrative example</Badge>
          <span>Sample rules and notifications. No settings, accounts or records are changed.</span>
        </div>
      )}
      <SectionTabs
        id="alerts"
        label="Alert sections"
        items={sections}
        value={tab}
        onChange={(value) =>
          setParams((previous) => {
            const next = new URLSearchParams(previous);
            next.set('tab', value);
            return next;
          })
        }
      />
      <SectionPanel id="alerts" value={tab}>
        {error ? (
          <ErrorState message={error} retry={retry} />
        ) : tab === 'rules' ? (
          <Panel className="full-panel">
            <PanelTitle
              title="Your price rules"
              subtitle={`${ruleData?.count ?? 0} of ${ruleData?.limit ?? 50} non-archived rules · each rule uses its selected feed`}
              action={
                <label className="alert-archive-toggle">
                  <input
                    type="checkbox"
                    checked={showArchived}
                    onChange={(event) => {
                      setArchived(event.target.checked);
                      setRuleOffset(0);
                    }}
                    disabled={example}
                  />{' '}
                  Include archived
                </label>
              }
            />
            {!ruleData ? (
              <Loading />
            ) : ruleData.items.length ? (
              <div className="price-rule-list">
                {ruleData.items.map((rule) => (
                  <article className="price-rule-card" key={rule.id}>
                    <div className="price-rule-heading">
                      <span className="activity-icon">
                        <Bell size={18} />
                      </span>
                      <div>
                        <h3>{rule.label || `${rule.symbol} price alert`}</h3>
                        <p>
                          {rule.symbol} · {conditionLabel(rule.condition)}{' '}
                          <strong>
                            {number(rule.threshold, 8)} {rule.symbol.split('/')[1]}
                          </strong>
                        </p>
                        <p className="price-rule-frequency">
                          {rule.repeat === 'after_reset'
                            ? `Repeats after reset · ${number(rule.cooldown_seconds / 60, 2)} min cooldown`
                            : 'One-time notification'}
                        </p>
                      </div>
                      <Badge tone={rule.status === 'armed' ? 'lime' : 'neutral'}>
                        {ruleState(rule)}
                      </Badge>
                    </div>
                    {rule.status === 'armed' && rule.evaluation_note && (
                      <p className="price-rule-note">
                        {rule.evaluation_note}
                        {rule.cooldown_until > Date.now() / 1000
                          ? ` Cooldown ends ${new Date(rule.cooldown_until * 1000).toLocaleTimeString()}.`
                          : ''}
                      </p>
                    )}
                    <div className="price-rule-evidence">
                      <span>
                        {rule.source_label}{' '}
                        {rule.environment === 'demo' ? (
                          <Badge tone="demo">Demo</Badge>
                        ) : rule.environment === 'test' ? (
                          <Badge>Test feed</Badge>
                        ) : (
                          <Badge>Live feed</Badge>
                        )}
                      </span>
                      <span>
                        Last price:{' '}
                        <strong>
                          {rule.last_price == null
                            ? '—'
                            : `${number(rule.last_price, 8)} ${rule.symbol.split('/')[1]}`}
                        </strong>
                      </span>
                      <span>
                        {rule.last_checked_at
                          ? `Checked ${new Date(rule.last_checked_at).toLocaleString()}`
                          : 'Awaiting first check'}
                      </span>
                    </div>
                    {rule.error && (
                      <p className="alert-rule-error" role="status">
                        {rule.error}{' '}
                        {rule.status === 'armed' && rule.next_check > 0
                          ? `Next attempt after ${new Date(rule.next_check * 1000).toLocaleTimeString()}.`
                          : ''}{' '}
                        <Link to="/settings?tab=market">Market settings</Link>
                      </p>
                    )}
                    <div className="price-rule-footer">
                      <span>
                        {rule.triggered_at
                          ? `Last notified ${new Date(rule.triggered_at).toLocaleString()}`
                          : rule.observed_at
                            ? `Provider time ${new Date(rule.observed_at).toLocaleString()}`
                            : 'Fresh timestamped quotes only'}{' '}
                        · cycle {rule.cycle}
                      </span>
                      <div className="order-actions">
                        {rule.status === 'archived' ? (
                          <button
                            className="button secondary tiny"
                            disabled={!!busy || example}
                            onClick={() => action(rule.id, 'restore')}
                          >
                            <Undo2 size={13} /> Restore paused
                          </button>
                        ) : (
                          <>
                            <button
                              className="icon-button"
                              aria-label={`Edit ${rule.label || rule.symbol} alert`}
                              title="Edit rule · saves paused"
                              disabled={!!busy || example}
                              onClick={() => setEditing(rule)}
                            >
                              <Pencil size={14} />
                            </button>
                            {rule.status === 'armed' ? (
                              <>
                                <button
                                  className="icon-button"
                                  aria-label={`Check ${rule.symbol} alert`}
                                  title="Check if due; respects cooldown"
                                  disabled={!!busy || example}
                                  onClick={() => action(rule.id, 'check')}
                                >
                                  <RefreshCw size={14} />
                                </button>
                                <button
                                  className="button secondary tiny"
                                  disabled={!!busy || example}
                                  onClick={() => action(rule.id, 'pause')}
                                >
                                  <Pause size={13} /> Pause
                                </button>
                              </>
                            ) : (
                              <button
                                className="button secondary tiny"
                                disabled={!!busy || example}
                                onClick={() => action(rule.id, 'arm')}
                              >
                                <Play size={13} />{' '}
                                {rule.status === 'triggered' ? 'Rearm' : 'Resume'}
                              </button>
                            )}
                            <button
                              className="icon-button"
                              aria-label={`Archive ${rule.label || rule.symbol} alert`}
                              title="Archive rule; restore it later"
                              disabled={!!busy || example}
                              onClick={() => action(rule.id, 'archive')}
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
              <Empty title="A level worth waiting for">
                <span>
                  Create an alert for any pair on your selected feed. Public feeds work without an
                  exchange account, or choose Demo to explore.
                </span>
              </Empty>
            )}
            {!example && ruleData && (ruleOffset > 0 || ruleData.total > 50) && (
              <div className="alert-pagination">
                <button
                  className="button secondary tiny"
                  disabled={!ruleOffset}
                  onClick={() => setRuleOffset(Math.max(0, ruleOffset - 50))}
                >
                  Previous rules
                </button>
                <span>
                  {ruleData.items.length
                    ? `${ruleOffset + 1}–${Math.min(ruleOffset + 50, ruleData.total)} of ${ruleData.total}`
                    : 'No rules on this page'}
                </span>
                <button
                  className="button secondary tiny"
                  disabled={ruleOffset + 50 >= ruleData.total}
                  onClick={() => setRuleOffset(ruleOffset + 50)}
                >
                  Next rules
                </button>
              </div>
            )}
            <p className="footnote padded">
              Level alerts can notify on their first fresh quote. Crossing alerts wait for a new
              observed crossing. Repeat alerts require a price reset and cooldown; moves during
              cooldown are skipped. Checks run about every 30 seconds and back off on errors. Missed
              crossings are not reconstructed. Delivery stays in-app.
            </p>
          </Panel>
        ) : (
          <Panel className="full-panel">
            <PanelTitle
              title="Notification inbox"
              subtitle={`${inboxData?.unread ?? 0} unread · ${inboxData?.total ?? 0} retained`}
              action={
                <button
                  className="button secondary tiny"
                  disabled={!!busy || example || !inboxData?.unread}
                  onClick={() => read()}
                >
                  <CheckCheck size={14} /> Mark all read
                </button>
              }
            />
            {!inboxData ? (
              <Loading />
            ) : inboxData.items.length ? (
              <div className="alert-inbox-list">
                {inboxData.items.map((item) => (
                  <article
                    className={`alert-inbox-item ${item.read_at ? '' : 'unread'}`}
                    key={item.id}
                  >
                    <span className="activity-icon">
                      <Bell size={17} />
                    </span>
                    <div className="notification-copy">
                      <NotificationText item={item} />
                      <small>
                        Provider time {new Date(item.observed_at).toLocaleString()} · cycle{' '}
                        {item.cycle}
                      </small>
                    </div>
                    {item.read_at ? (
                      <Badge>Read</Badge>
                    ) : (
                      <button
                        className="text-button"
                        disabled={!!busy || example}
                        onClick={() => read(item.id)}
                      >
                        Mark read
                      </button>
                    )}
                  </article>
                ))}
              </div>
            ) : (
              <Empty title="All quiet for now">
                Triggered price rules will leave a record here, even if the browser was closed.
              </Empty>
            )}
            {!!inboxData?.total && !example && (
              <div className="alert-pagination">
                <button
                  className="button secondary tiny"
                  disabled={!offset}
                  onClick={() => setOffset(Math.max(0, offset - 20))}
                >
                  Previous
                </button>
                <span>
                  {offset + 1}–{Math.min(offset + 20, inboxData.total)} of {inboxData.total}
                </span>
                <button
                  className="button secondary tiny"
                  disabled={offset + 20 >= inboxData.total}
                  onClick={() => setOffset(offset + 20)}
                >
                  Next
                </button>
              </div>
            )}
          </Panel>
        )}
      </SectionPanel>
      {(creating || editing) && (
        <Modal
          className="price-alert-dialog"
          title={editing ? 'Edit price alert' : 'New price alert'}
          onClose={() => {
            setCreating(false);
            setEditing(undefined);
          }}
        >
          {settings.error ? (
            <ErrorState message={settings.error} retry={settings.retry} />
          ) : settings.data ? (
            <PriceRuleForm
              key={editing?.id || 'new'}
              rule={editing}
              settings={settings.data}
              initialSource={editing?.source || params.get('source') || settings.data.active.id}
              initialSymbol={editing?.symbol || params.get('symbol') || 'BTC/USDT'}
              onSaved={() => {
                setCreating(false);
                refresh();
                toast(
                  editing
                    ? 'Changes saved. Your alert is paused; resume when ready.'
                    : 'Price alert saved.',
                );
                setEditing(undefined);
                setRuleOffset(0);
                setParams((previous) => {
                  const next = new URLSearchParams(previous);
                  next.set('tab', 'rules');
                  return next;
                });
              }}
            />
          ) : (
            <Loading />
          )}
        </Modal>
      )}
    </>
  );
}

function PriceRuleForm({
  rule,
  settings,
  initialSource,
  initialSymbol,
  onSaved,
}: {
  rule?: PriceRule;
  settings: MarketSettings;
  initialSource: string;
  initialSymbol: string;
  onSaved: () => void;
}) {
  const [source, setSource] = useState(initialSource);
  const [symbol, setSymbol] = useState(initialSymbol);
  const [condition, setCondition] = useState(rule?.condition || 'above');
  const [threshold, setThreshold] = useState(rule ? String(rule.threshold) : '');
  const [label, setLabel] = useState(rule?.label || '');
  const [repeat, setRepeat] = useState(rule?.repeat || 'once');
  const [cooldown, setCooldown] = useState(rule?.cooldown_seconds || 300);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const catalog = useResource<SpotCatalog>(`/markets/symbols?source=${encodeURIComponent(source)}`);
  const sameMarket = !!rule && source === rule.source && symbol === rule.symbol;
  const supported = sameMarket || !!catalog.data?.items.some((item) => item.symbol === symbol);
  const demo = source === 'demo';
  const create = async () => {
    setBusy(true);
    setError('');
    try {
      await post(rule ? `/alerts/${rule.id}/edit` : '/alerts', {
        source,
        symbol,
        condition,
        threshold: Number(threshold),
        label,
        repeat,
        cooldown_seconds: cooldown,
        ...(rule ? { revision: rule.revision } : {}),
      });
      onSaved();
    } catch (reason) {
      setError((reason as Error).message);
      refresh();
    } finally {
      setBusy(false);
    }
  };
  return (
    <form
      className="form price-alert-form"
      onSubmit={(event) => {
        event.preventDefault();
        create();
      }}
    >
      <MarketSourcePicker
        settings={settings}
        value={source}
        allowUnavailable={!!rule}
        onChange={(value) => {
          setSource(value);
          setSymbol('');
        }}
      />
      {catalog.data ? (
        <MarketSelector
          catalog={catalog.data}
          value={symbol}
          label="Exact market pair"
          onChange={setSymbol}
          disabled={busy}
        />
      ) : sameMarket ? (
        <p className="inline-alert">
          Saved pair: <strong>{symbol}</strong>. You can update its settings even while this feed is
          unavailable.
        </p>
      ) : (
        !catalog.error && <Loading />
      )}
      {catalog.error && !sameMarket && (
        <p className="form-error" role="alert">
          {catalog.error}
        </p>
      )}
      <div className="form-row">
        <label>
          Notify when price
          <select
            value={condition}
            disabled={busy}
            onChange={(event) => setCondition(event.target.value as PriceCondition)}
          >
            <option value="above">At or above</option>
            <option value="below">At or below</option>
            <option value="crosses_above">Crosses to or above</option>
            <option value="crosses_below">Crosses to or below</option>
          </select>
        </label>
        <label>
          Threshold · {symbol.split('/')[1] || 'quote currency'}
          <input
            type="number"
            required
            min="0.00000001"
            max="1000000000000000"
            step="any"
            value={threshold}
            disabled={busy}
            onChange={(event) => setThreshold(event.target.value)}
          />
        </label>
      </div>
      <div className="form-row">
        <label>
          Frequency
          <select
            value={repeat}
            disabled={busy}
            onChange={(event) => setRepeat(event.target.value as 'once' | 'after_reset')}
          >
            <option value="once">One time</option>
            <option value="after_reset">Repeat after price resets</option>
          </select>
        </label>
        {repeat === 'after_reset' && (
          <label>
            Minimum time between notifications
            <select
              value={cooldown}
              disabled={busy}
              onChange={(event) => setCooldown(Number(event.target.value))}
            >
              {![60, 300, 900, 3600, 21600, 86400].includes(cooldown) && (
                <option value={cooldown}>{cooldown} seconds · saved</option>
              )}
              <option value={60}>1 minute</option>
              <option value={300}>5 minutes</option>
              <option value={900}>15 minutes</option>
              <option value={3600}>1 hour</option>
              <option value={21600}>6 hours</option>
              <option value={86400}>1 day</option>
            </select>
          </label>
        )}
      </div>
      <label>
        <span>
          Name <small>Optional</small>
        </span>
        <input
          maxLength={80}
          value={label}
          disabled={busy}
          onChange={(event) => setLabel(event.target.value)}
          placeholder="A level I’m watching"
        />
      </label>
      <div className="alert-delivery-note">
        <Badge tone={demo ? 'demo' : 'neutral'}>
          {demo ? 'Demo · simulated prices' : 'In-app only'}
        </Badge>
        <span>
          {condition.startsWith('crosses_')
            ? 'The first quote sets a starting point; only a later observed crossing can notify. '
            : 'A level alert can notify on its first fresh quote. '}
          {repeat === 'after_reset'
            ? 'Repeats need a reset and a new move after cooldown; moves during cooldown are skipped. '
            : 'One notification, then the rule stops. '}
          {rule ? 'Changes save paused; past notifications stay unchanged.' : 'Delivery is in-app.'}
        </span>
      </div>
      {error && (
        <p className="form-error" role="alert">
          {error}
        </p>
      )}
      <div className="price-alert-actions">
        <button
          className="button primary"
          disabled={
            busy || !supported || !Number.isFinite(Number(threshold)) || Number(threshold) <= 0
          }
        >
          <Bell size={14} />
          {busy ? 'Saving…' : rule ? 'Save paused' : 'Create price alert'}
        </button>
        <Link className="text-link" to="/settings?tab=market">
          Manage market sources <ArrowUpRight size={12} />
        </Link>
      </div>
    </form>
  );
}

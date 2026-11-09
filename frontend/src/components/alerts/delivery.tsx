import { createContext, useContext, useState, type ReactNode } from 'react';
import { Link } from 'react-router-dom';
import { BellRing, History, Send, Mail } from 'lucide-react';
import { ErrorState, Loading, Modal, useToast } from '../ui';
import { useResource } from '../../lib/hooks';
import { post, refresh } from '../../lib/api';
import { DeliveryReceipt, type MessageDelivery } from '../messaging/delivery-receipt';
import {
  PrivateDestinationPicker,
  bindingKey,
  targetKey,
  channelName,
  type NotificationChannel as Channel,
  type NotificationTarget as Target,
} from '../messaging/notification-targets';
import '../../styles/alert-delivery.css';

const policyKey = (policy: Policy) =>
  bindingKey(policy.channel || 'telegram', policy.delivery_binding || policy.telegram_binding);
type Kind = 'price' | 'risk' | 'strategy' | 'connection' | 'order';
type Policy = {
  rule_id: string;
  kind: Kind;
  enabled: boolean;
  revision: number;
  cooldown_seconds: number;
  expiry_seconds: number;
  channel: Channel;
  delivery_binding: {
    bot_id: number | string;
    recipient_id: number | string;
    target_id?: string;
    connection_revision?: string;
  } | null;
  telegram_binding: { bot_id: number; recipient_id: number; bot_username: string } | null;
};
type HistoryData = { items: MessageDelivery[]; total: number; offset: number; limit: number };
type Detail = {
  policy: Policy;
  rule: { id: string; revision: number; status: string; label: string };
  history: HistoryData;
};
const DeliveryContext = createContext<
  { rule_id: string; kind: Kind; enabled: boolean; channel: Channel }[]
>([]);

/** One bounded indicators request for all visible rules; editors load private details on demand. */
export function AlertDeliveryScope({ children }: { children: ReactNode }) {
  const policies = useResource<
    { rule_id: string; kind: Kind; enabled: boolean; channel: Channel }[]
  >('/alert-delivery/policies', 5000);
  return (
    <DeliveryContext.Provider value={policies.data ?? []}>{children}</DeliveryContext.Provider>
  );
}

export function AlertDeliveryButton({
  kind,
  rule,
  disabled = false,
}: {
  kind: Kind;
  rule: string;
  disabled?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const active = useContext(DeliveryContext).find(
    (item) => item.rule_id === rule && item.kind === kind && item.enabled,
  );
  return (
    <>
      <button
        className={`button tiny alert-delivery-button ${active ? 'selected' : ''}`}
        disabled={disabled}
        aria-label={`Delivery settings for ${kind} alert`}
        onClick={() => setOpen(true)}
      >
        {active?.channel === 'email' ? (
          <Mail size={13} />
        ) : active ? (
          <img
            src={`/messaging/${active.channel || 'telegram'}.svg`}
            alt=""
            width="13"
            height="13"
          />
        ) : (
          <Send size={13} />
        )}
        {active ? `${channelName(active.channel || 'telegram')} selected` : 'Delivery'}
      </button>
      {open && <DeliveryDialog kind={kind} rule={rule} onClose={() => setOpen(false)} />}
    </>
  );
}

function DeliveryDialog({
  kind,
  rule,
  onClose,
}: {
  kind: Kind;
  rule: string;
  onClose: () => void;
}) {
  const detail = useResource<Detail>(`/alert-delivery/${kind}/${rule}`);
  const settings = useResource<{ items: Target[] }>('/message-deliveries/targets');
  return (
    <Modal title="Alert delivery" onClose={onClose} className="alert-delivery-dialog">
      {detail.error || settings.error ? (
        <ErrorState
          message={detail.error || settings.error}
          retry={() => {
            detail.retry();
            settings.retry();
          }}
        />
      ) : !detail.data || !settings.data ? (
        <Loading />
      ) : (
        <DeliveryEditor
          key={detail.data.policy.revision}
          detail={detail.data}
          targets={settings.data.items}
          onChanged={() => {
            detail.retry();
            settings.retry();
            refresh();
          }}
        />
      )}
    </Modal>
  );
}

function DeliveryEditor({
  detail,
  targets,
  onChanged,
}: {
  detail: Detail;
  targets: Target[];
  onChanged: () => void;
}) {
  const { policy, rule } = detail;
  const [key, setKey] = useState(policy.enabled ? policyKey(policy) : '');
  const selected = targets.find((row) => !!row.target && targetKey(row) === key);
  const [cooldown, setCooldown] = useState(policy.cooldown_seconds / 60);
  const [expiry, setExpiry] = useState(policy.expiry_seconds / 60);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [history, setHistory] = useState(false);
  const toast = useToast();
  const save = async (pause = false) => {
    if (busy) return;
    setBusy(true);
    setError('');
    try {
      if (!pause && key && !selected)
        throw new Error(
          'The checked recipient changed. Select its current card or choose Local only.',
        );
      const choice = pause ? undefined : selected;
      await post(`/alert-delivery/${policy.kind}/${policy.rule_id}`, {
        revision: policy.revision,
        rule_revision: rule.revision,
        enabled: !!choice,
        channel: choice?.channel || policy.channel || 'telegram',
        telegram_target: choice?.channel === 'telegram' ? choice.target : null,
        private_target: choice && choice.channel !== 'telegram' ? choice.target : null,
        cooldown_seconds: cooldown * 60,
        expiry_seconds: expiry * 60,
      });
      toast(
        choice
          ? `${choice.label} selected for future alerts. Existing notices stay local.`
          : 'External delivery paused. In-app alerts stay on.',
      );
      onChanged();
    } catch (reason) {
      setError((reason as Error).message);
    } finally {
      setBusy(false);
    }
  };
  return (
    <>
      <p className="muted">
        Keep every alert in Sibyl and optionally send future events from this rule to one checked
        private connection. No AI model is required.
      </p>
      <div className="alert-local-delivery">
        <BellRing size={17} />
        <span>
          <strong>Local inbox</strong>
          <small>All trigger evidence stays in Sibyl.</small>
        </span>
        <span className="alert-always-on">Always on</span>
      </div>
      <form
        onSubmit={(event) => {
          event.preventDefault();
          void save();
        }}
      >
        <PrivateDestinationPicker
          targets={targets}
          value={key}
          onChange={setKey}
          disabled={busy || rule.status === 'archived'}
          label="Private alert destination"
        />
        {key && !selected && (
          <p className="inline-alert">
            The checked connection changed. Review and select its current recipient to resume
            delivery.
          </p>
        )}
        {selected && !selected.enabled && (
          <p className="inline-alert">
            {selected.label} is paused. Enable it in Messaging settings; alerts recorded while
            paused stay local.
          </p>
        )}
        {selected?.channel === 'whatsapp' && (
          <p className="inline-alert">
            {selected.note}
            {!selected.window_open && ' The reply window is currently closed.'}
          </p>
        )}
        {rule.status !== 'armed' && (
          <p className="footnote">
            {rule.status === 'triggered'
              ? 'This one-time alert has triggered. A queued message can finish; rearm the rule for future alerts.'
              : `This rule is ${rule.status}. Restore or resume the rule to monitor future events.`}
          </p>
        )}
        <div className="alert-delivery-fields">
          <label>
            Minimum interval
            <input
              type="number"
              min={1}
              max={1440}
              step={1}
              required
              value={cooldown}
              disabled={busy}
              onChange={(event) => setCooldown(Number(event.target.value))}
            />
            <small>Minutes between queued messages</small>
          </label>
          <label>
            Delivery window
            <input
              type="number"
              min={1}
              max={60}
              step={1}
              required
              value={expiry}
              disabled={busy}
              onChange={(event) => setExpiry(Number(event.target.value))}
            />
            <small>Minutes from the original observation</small>
          </label>
        </div>
        <p className="footnote">
          Cooldown suppresses extra messages rather than delaying them. Enabling or resuming never
          sends existing inbox entries. Selected alert content may include private account research
          and passes through the chosen provider.
        </p>
        <Link className="text-link" to="/settings?tab=messaging">
          Manage messaging connections ↗
        </Link>
        {error && (
          <p className="inline-alert" role="alert">
            {error}{' '}
            <button type="button" className="text-link" onClick={onChanged}>
              Reload current settings
            </button>
          </p>
        )}
        <div className="form-actions">
          {policy.enabled && (
            <button
              type="button"
              className="button"
              disabled={busy}
              onClick={() => void save(true)}
            >
              Pause external delivery
            </button>
          )}
          <button
            className="button primary"
            type="submit"
            disabled={busy || (rule.status === 'archived' && !!key)}
          >
            {busy ? 'Saving…' : 'Save delivery'}
          </button>
        </div>
      </form>
      <button className="text-button alert-history-toggle" onClick={() => setHistory(!history)}>
        <History size={14} />
        {history ? 'Hide' : 'Show'} delivery history
      </button>
      {history && <AlertDeliveryHistory ruleId={policy.rule_id} />}
    </>
  );
}

/** Safe receipts are separate from trigger/read state, so acknowledging a notice never resends it. */
export function AlertDeliveryHistory({ ruleId }: { ruleId?: string }) {
  const [offset, setOffset] = useState(0);
  const data = useResource<HistoryData>(
    `/alert-delivery/history?offset=${offset}${ruleId ? `&rule_id=${ruleId}` : ''}`,
    3000,
  );
  return data.error ? (
    <ErrorState message={data.error} retry={data.retry} />
  ) : !data.data ? (
    <Loading />
  ) : (
    <div className="alert-delivery-history">
      {data.data.items.length ? (
        data.data.items.map((item) => (
          <section key={item.id}>
            <DeliveryReceipt delivery={item} />
          </section>
        ))
      ) : (
        <p className="muted">
          No delivery attempts yet. Only future events with a private destination selected appear
          here.
        </p>
      )}
      {data.data.total > 20 && (
        <div className="form-actions">
          <button
            className="button tiny"
            disabled={!offset}
            onClick={() => setOffset(Math.max(0, offset - 20))}
          >
            Previous
          </button>
          <span>
            {offset + 1}–{Math.min(offset + 20, data.data.total)} of {data.data.total}
          </span>
          <button
            className="button tiny"
            disabled={offset + 20 >= data.data.total}
            onClick={() => setOffset(offset + 20)}
          >
            Next
          </button>
        </div>
      )}
      <p className="footnote">
        Unconfirmed sends are never automatically repeated. Check your chat before requesting
        another notification. Pending sends expire; pausing cannot undo an HTTP request already in
        flight.
      </p>
    </div>
  );
}

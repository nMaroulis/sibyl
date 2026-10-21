import { useEffect, useRef, useState } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { ArrowUpRight, Bell, CheckCheck, Sparkles, Waves } from 'lucide-react';
import type { Run } from '../lib/types';
import { number, post, refresh } from '../lib/api';
import { useResource } from '../lib/hooks';
import { Badge, useToast } from './ui';

export type PriceCondition = 'above' | 'below' | 'crosses_above' | 'crosses_below';
export const conditionLabel = (condition: PriceCondition, past = false) =>
  ({
    above: 'at or above',
    below: 'at or below',
    crosses_above: `${past ? 'crossed' : 'crosses'} to or above`,
    crosses_below: `${past ? 'crossed' : 'crosses'} to or below`,
  })[condition];

export type AlertNotification = {
  id: string;
  rule_id: string;
  label: string;
  symbol: string;
  condition: PriceCondition;
  repeat?: 'once' | 'after_reset';
  rule_revision?: number;
  threshold: number;
  price: number;
  source: string;
  source_label: string;
  environment: string;
  observed_at: string;
  created_at: string;
  read_at: string | null;
  cycle: number;
};
export type Inbox = {
  items: AlertNotification[];
  total: number;
  unread: number;
  limit: number;
  offset: number;
  delivery: string;
};

/** Describe observed evidence without implying a trade or an external notification. */
export function NotificationText({ item }: { item: AlertNotification }) {
  return (
    <>
      <strong>{item.label || `${item.symbol} price alert`}</strong>
      <span>
        {item.symbol} was {number(item.price, 8)} {item.symbol.split('/')[1]} ·{' '}
        {conditionLabel(item.condition, true)} {number(item.threshold, 8)}
      </span>
      <small>
        {item.source_label} · {new Date(item.created_at).toLocaleString()}{' '}
        {item.environment === 'demo' && <Badge tone="demo">Demo</Badge>}
      </small>
    </>
  );
}

/** Persisted alert unread state shares the bell with the existing run activity. */
export function NotificationBell({ runs }: { runs?: Run[] }) {
  const inbox = useResource<Inbox>('/notifications?limit=3', 15000);
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const location = useLocation();
  const wrap = useRef<HTMLDivElement>(null);
  const button = useRef<HTMLButtonElement>(null);
  const toast = useToast();
  useEffect(() => setOpen(false), [location.pathname, location.search]);
  useEffect(() => {
    if (!open) return;
    const outside = (event: PointerEvent) => {
      if (event.target instanceof Node && !wrap.current?.contains(event.target)) setOpen(false);
    };
    const escape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        setOpen(false);
        button.current?.focus();
      }
    };
    document.addEventListener('pointerdown', outside);
    document.addEventListener('keydown', escape);
    return () => {
      document.removeEventListener('pointerdown', outside);
      document.removeEventListener('keydown', escape);
    };
  }, [open]);
  const readAll = async () => {
    setBusy(true);
    try {
      await post('/notifications/read-all', {});
      refresh();
    } catch (reason) {
      toast((reason as Error).message, true);
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="notification-wrap" ref={wrap}>
      <button
        ref={button}
        className="icon-button"
        aria-label={
          inbox.data?.unread
            ? `Notifications, ${inbox.data.unread} unread`
            : 'Notifications and activity'
        }
        aria-expanded={open}
        onClick={() => setOpen(!open)}
      >
        <Bell size={18} />
        {!!inbox.data?.unread && <span className="notification-dot" />}
      </button>
      {open && (
        <div className="notification-menu" role="region" aria-label="Notifications and activity">
          <div className="notification-heading">
            <strong>Notifications</strong>
            {!!inbox.data?.unread && (
              <button className="text-button" disabled={busy} onClick={readAll}>
                <CheckCheck size={13} /> Mark all read
              </button>
            )}
          </div>
          {inbox.error ? (
            <p className="negative">
              Notification inbox unavailable.{' '}
              <button className="text-button" onClick={inbox.retry}>
                Retry
              </button>
            </p>
          ) : inbox.data?.items.length ? (
            inbox.data.items.map((item) => (
              <Link
                className={item.read_at ? '' : 'notification-unread'}
                key={item.id}
                to="/alerts?tab=inbox"
              >
                <span className="activity-icon">
                  <Bell size={15} />
                </span>
                <span className="notification-copy">
                  <NotificationText item={item} />
                </span>
              </Link>
            ))
          ) : (
            <p>No price alerts yet. Create a rule to follow a market.</p>
          )}
          <Link className="notification-manage" to="/alerts">
            Alerts & inbox <ArrowUpRight size={13} />
          </Link>
          <strong className="notification-activity-title">Recent activity</strong>
          {runs?.length ? (
            runs.slice(0, 3).map((run) => (
              <Link key={run.id} to={run.kind === 'agent' ? '/oracle' : '/strategies'}>
                <span className="activity-icon">
                  {run.kind === 'agent' ? <Sparkles size={15} /> : <Waves size={15} />}
                </span>
                <span>
                  {run.kind === 'agent' ? 'Agent snapshot recorded' : 'Backtest completed'}
                  <small>{new Date(run.created_at).toLocaleString()}</small>
                </span>
              </Link>
            ))
          ) : (
            <p>Your agent runs and backtests will appear here.</p>
          )}
        </div>
      )}
    </div>
  );
}

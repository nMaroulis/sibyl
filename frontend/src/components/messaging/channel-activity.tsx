import { useEffect, useId, useState } from 'react';
import type { ReactNode } from 'react';
import {
  Activity,
  BellRing,
  CalendarClock,
  ChevronDown,
  ChevronRight,
  MessageCircle,
  ShieldCheck,
} from 'lucide-react';
import { useResource } from '../../lib/hooks';
import { MessageLogDialog } from './message-log';
import { ChannelLogs } from './channel-logs';
import type { MessageLogStorage } from './channel-logs';
import { MonitorTrace } from '../monitor-trace';

const kinds = {
  message: { label: 'Message received', icon: MessageCircle },
  alert: { label: 'Alert delivery', icon: BellRing },
  briefing: { label: 'Briefing delivery', icon: CalendarClock },
  check: { label: 'Connection checked', icon: ShieldCheck },
} as const;

const outcomes: Record<string, { label: string; tone: string }> = {
  queued: { label: 'Message queued', tone: 'progress' },
  processing: { label: 'Answering', tone: 'progress' },
  completed: { label: 'Processed', tone: 'neutral' },
  pending: { label: 'Delivery queued', tone: 'progress' },
  sending: { label: 'Sending', tone: 'progress' },
  retrying: { label: 'Waiting to retry', tone: 'warning' },
  sent: { label: 'Provider accepted', tone: 'success' },
  partial: { label: 'Partial delivery', tone: 'warning' },
  failed: { label: 'Failed', tone: 'warning' },
  blocked: { label: 'Blocked', tone: 'warning' },
  uncertain: { label: 'Unconfirmed', tone: 'warning' },
  interrupted: { label: 'Interrupted', tone: 'warning' },
  withdrawn: { label: 'Withdrawn', tone: 'neutral' },
  skipped: { label: 'Skipped', tone: 'neutral' },
  verified: { label: 'Verified', tone: 'success' },
};

export type ChannelActivityEvent = {
  id: string;
  kind: keyof typeof kinds;
  at: number;
  state: string;
  accepted_parts?: number;
  total_parts?: number;
};

const VISIBLE_EVENTS = 3;
const ranges = [
  ['1h', '1h'],
  ['1d', '1d'],
  ['1w', '1w'],
  ['30d', '30d'],
  ['all', 'All time'],
] as const;
type TimelineWindow = (typeof ranges)[number][0];
type ActivityTimeline = {
  window: TimelineWindow;
  start: number;
  bins: { count: number; attention: boolean }[];
  events: ChannelActivityEvent[];
};

function ActivityTime({ at, compact = false }: { at: number; compact?: boolean }) {
  const date = new Date(at * 1000);
  const earlier = date.toDateString() !== new Date().toDateString();
  return (
    <time dateTime={date.toISOString()} title={date.toLocaleString()}>
      {earlier && `${date.toLocaleDateString([], { month: 'short', day: 'numeric' })} · `}
      {date.toLocaleTimeString([], {
        hour: '2-digit',
        minute: '2-digit',
        second: compact ? undefined : '2-digit',
      })}
    </time>
  );
}

function ReceiverAge({ at }: { at: number }) {
  const [now, setNow] = useState(Date.now);
  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, []);
  const seconds = Math.max(0, Math.floor(now / 1000 - at));
  const date = new Date(at * 1000);
  return (
    <time dateTime={date.toISOString()} title={date.toLocaleString()}>
      {seconds < 5
        ? 'just now'
        : seconds < 60
          ? `${seconds}s ago`
          : seconds < 3600
            ? `${Math.floor(seconds / 60)}m ago`
            : seconds < 86400
              ? `${Math.floor(seconds / 3600)}h ago`
              : `${Math.floor(seconds / 86400)}d ago`}
    </time>
  );
}

/** The sweep indicates an active listener independently of recorded traffic. */
function ActivityTrace({ timeline, live }: { timeline: ActivityTimeline; live: boolean }) {
  return (
    <div className="channel-activity-trace" aria-hidden="true">
      <MonitorTrace bins={timeline.bins} live={live} />
      <div className="channel-activity-trace-range">
        <ActivityTime at={timeline.start} compact />
        <span>Now</span>
      </div>
    </div>
  );
}

/** A live signal and expandable timeline of the channel's recorded events. */
export function ChannelActivity({
  channelName,
  channelId,
  enabled = false,
  paused = false,
  stopped = false,
  logs,
  lastReceive,
  counts,
  controls,
  webhook = false,
  attention = false,
  working = false,
}: {
  channelName: string;
  channelId: string;
  enabled?: boolean;
  paused?: boolean;
  stopped?: boolean;
  logs?: MessageLogStorage;
  lastReceive?: number;
  counts: { label: string; value: number | undefined }[];
  controls?: ReactNode;
  webhook?: boolean;
  attention?: boolean;
  working?: boolean;
}) {
  const [window, setWindow] = useState<TimelineWindow>('all');
  const { data, error, retry } = useResource<ActivityTimeline>(
    `/settings/messaging/channels/${encodeURIComponent(channelId)}/timeline?window=${window}`,
    5000,
  );
  const timeline = data?.window === window ? data : undefined;
  const events = timeline?.events ?? [];
  const total = timeline?.bins.reduce((count, bin) => count + bin.count, 0);
  const [expanded, setExpanded] = useState(false);
  const timelineId = useId();
  const [message, setMessage] = useState<string>();
  const needsAttention = enabled && attention;
  const live = enabled && !needsAttention;
  const status = needsAttention
    ? 'Needs attention'
    : live
      ? 'Live'
      : stopped
        ? 'Stopped'
        : paused
          ? 'Paused'
          : 'Ready';
  const visibleEvents = expanded ? events : events.slice(0, VISIBLE_EVENTS);
  const earlierCount = events.length - VISIBLE_EVENTS;
  return (
    <section className="channel-activity-panel" aria-label={`${channelName} activity monitor`}>
      <div className="channel-activity-header">
        <div className="channel-activity-title">
          <span className="channel-activity-header-icon" aria-hidden="true">
            <Activity size={16} />
          </span>
          <div>
            <h4>{enabled ? 'Live activity' : 'Activity monitor'}</h4>
            <p>
              {working && live ? (
                'Handling a message'
              ) : lastReceive ? (
                <>
                  {webhook ? 'Webhook received' : 'Receiver checked'}{' '}
                  <ReceiverAge at={lastReceive} />
                </>
              ) : !enabled ? (
                'Receiver idle'
              ) : webhook ? (
                'Waiting for the first webhook'
              ) : (
                'Waiting for the first receiver check'
              )}
            </p>
          </div>
        </div>
        <span
          className="channel-activity-state"
          data-live={live}
          data-attention={needsAttention}
          role="status"
        >
          <i aria-hidden="true" />
          {status}
        </span>
      </div>

      {controls}
      <dl className="channel-activity-counts" aria-label={`${channelName} counts`}>
        {counts.map(({ label, value }) => (
          <div key={label}>
            <dt>{label}</dt>
            <dd>{value?.toLocaleString() ?? '—'}</dd>
          </div>
        ))}
      </dl>
      <div className="channel-activity-range-bar">
        <div className="channel-activity-range-options" role="group" aria-label="Timeline range">
          {ranges.map(([value, label]) => (
            <button
              key={value}
              type="button"
              aria-pressed={window === value}
              onClick={() => {
                setWindow(value);
                setExpanded(false);
              }}
            >
              {label}
            </button>
          ))}
        </div>
        {total != null && (
          <small>
            {total.toLocaleString()} {total === 1 ? 'event' : 'events'}
          </small>
        )}
      </div>
      {timeline && <ActivityTrace timeline={timeline} live={live} />}
      {error && (
        <p className="channel-activity-empty" role="status">
          Timeline could not refresh.{' '}
          <button type="button" className="text-button" onClick={retry}>
            Retry
          </button>
        </p>
      )}

      {events.length ? (
        <ol className="channel-activity-timeline" aria-label="Latest events" id={timelineId}>
          {visibleEvents.map((event) => {
            const { icon: Icon, label } = kinds[event.kind];
            const outcome = outcomes[event.state] ?? { label: 'Recorded', tone: 'neutral' };
            const content = (
              <>
                <span className="channel-activity-node" aria-hidden="true">
                  <Icon size={13} />
                </span>
                <span className="channel-activity-event">
                  <strong>{label}</strong>
                  <small>
                    <span>{outcome.label}</span>
                    {(event.total_parts ?? 0) > 1 && (
                      <span>
                        {event.accepted_parts} of {event.total_parts} reply parts accepted
                      </span>
                    )}
                  </small>
                </span>
                <ActivityTime at={event.at} />
                {event.kind === 'message' && <ChevronRight size={14} aria-hidden="true" />}
              </>
            );
            return (
              <li key={event.id} data-tone={outcome.tone}>
                {event.kind === 'message' ? (
                  <button
                    type="button"
                    className="channel-activity-entry"
                    aria-haspopup="dialog"
                    aria-label={`View message log from ${new Date(event.at * 1000).toLocaleString()}`}
                    onClick={() => setMessage(event.id)}
                  >
                    {content}
                  </button>
                ) : (
                  <div className="channel-activity-entry">{content}</div>
                )}
              </li>
            );
          })}
        </ol>
      ) : (
        !error && (
          <p className="channel-activity-empty">
            {timeline ? 'No activity in this range.' : 'Loading timeline…'}
          </p>
        )
      )}
      {earlierCount > 0 && (
        <div className="channel-activity-footer">
          <button
            type="button"
            className="channel-activity-more"
            aria-expanded={expanded}
            aria-controls={timelineId}
            onClick={() => setExpanded((value) => !value)}
          >
            <ChevronDown size={15} aria-hidden="true" />
            {expanded
              ? 'Show fewer events'
              : `Show ${earlierCount} earlier ${earlierCount === 1 ? 'event' : 'events'}`}
          </button>
        </div>
      )}
      {logs && <ChannelLogs channel={channelId} name={channelName} storage={logs} />}
      {message && (
        <MessageLogDialog
          channel={channelId}
          message={message}
          close={() => setMessage(undefined)}
        />
      )}
    </section>
  );
}

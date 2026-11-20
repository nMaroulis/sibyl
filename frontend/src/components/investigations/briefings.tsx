import { Mail } from 'lucide-react';
import { channelName } from '../messaging/notification-targets';
import { scheduledChannel } from './briefing-types';
import { useEffect, useState } from 'react';
import {
  Archive,
  CalendarClock,
  History,
  LoaderCircle,
  Pause,
  Pencil,
  Play,
  Plus,
} from 'lucide-react';
import { Badge, ErrorState, useToast } from '../ui';
import { useResource } from '../../lib/hooks';
import { post } from '../../lib/api';
import { BriefingForm } from './briefing-form';
import { BriefingHistory } from './briefing-history';
import { briefingPending, calendarDate, weekdays } from './briefing-types';
import type { BriefingOccurrence, BriefingSchedule } from './briefing-types';
import '../../styles/briefings.css';

export function Briefings({
  investigation,
  ready,
  onChanged,
  onStarted,
}: {
  investigation: string;
  ready: boolean;
  onChanged: () => void;
  onStarted: (run: string) => void;
}) {
  const policies = useResource<BriefingSchedule[]>(
    `/investigations/${investigation}/schedules?archived=true`,
  );
  const current = policies.data?.find((item) => item.status !== 'archived');
  const detail = useResource<BriefingSchedule>(
    `/briefing-schedules/${current?.id}`,
    3000,
    Boolean(current),
  );
  const policy = detail.data?.id === current?.id ? detail.data : current;
  const latest = detail.data?.id === current?.id ? detail.data?.occurrences?.[0] : undefined;
  const [editing, setEditing] = useState(false);
  const [history, setHistory] = useState(false);
  const [busy, setBusy] = useState('');
  const [error, setError] = useState('');
  const [requested, setRequested] = useState('');
  const toast = useToast();
  useEffect(() => onChanged(), [latest?.id, latest?.status, latest?.run_id, onChanged]);
  useEffect(() => {
    if (requested && latest?.id === requested && latest.run_id) {
      onStarted(latest.run_id);
      setRequested('');
    }
  }, [requested, latest?.id, latest?.run_id, onStarted]);
  const action = async (name: 'pause' | 'resume' | 'archive') => {
    if (!policy || busy) return;
    setBusy(name);
    setError('');
    try {
      await post(`/briefing-schedules/${policy.id}/actions`, {
        action: name,
        revision: policy.revision,
      });
      policies.retry();
      detail.retry();
      onChanged();
      toast(
        name === 'archive'
          ? 'Schedule archived. Its history is retained.'
          : name === 'pause'
            ? 'Future briefings and unsent deliveries are paused.'
            : 'Schedule resumed from its next future time.',
      );
    } catch (reason) {
      setError((reason as Error).message);
      detail.retry();
    } finally {
      setBusy('');
    }
  };
  const run = async () => {
    if (!policy || busy) return;
    setBusy('run');
    setError('');
    try {
      const occurrence = await post<BriefingOccurrence>(
        `/briefing-schedules/${policy.id}/run-now`,
        { revision: policy.revision, request_id: crypto.randomUUID().replaceAll('-', '') },
      );
      setRequested(occurrence.id);
      detail.retry();
      onChanged();
      toast(
        scheduledChannel(policy)
          ? `Briefing queued with your selected ${channelName(scheduledChannel(policy)!)} delivery.`
          : 'Briefing queued. The calendar time is unchanged.',
      );
    } catch (reason) {
      setError((reason as Error).message);
    } finally {
      setBusy('');
    }
  };
  return (
    <div className="briefings-widget">
      {editing && (
        <BriefingForm
          investigation={investigation}
          initial={policy}
          ready={ready}
          onClose={() => setEditing(false)}
          onSaved={() => {
            setEditing(false);
            policies.retry();
            detail.retry();
            toast(policy ? 'Briefing schedule updated.' : 'Briefing schedule saved.');
          }}
        />
      )}
      {history && policies.data?.length && (
        <BriefingHistory
          schedules={policies.data}
          selected={policy?.id ?? policies.data[0].id}
          onClose={() => setHistory(false)}
        />
      )}
      {policies.error ? (
        <ErrorState message={policies.error} retry={policies.retry} />
      ) : policy ? (
        <div className={`briefing-strip ${policy.status}`}>
          <span className="briefing-calendar-icon">
            <CalendarClock size={20} />
          </span>
          <div className="briefing-strip-copy">
            <div>
              <strong>
                {policy.frequency === 'daily'
                  ? 'Daily briefing'
                  : `${weekdays[policy.weekday]} briefing`}{' '}
                · {policy.local_time}
              </strong>
              <Badge tone={policy.status === 'armed' ? 'lime' : 'neutral'}>
                {briefingPending(latest) ? (
                  <>
                    <LoaderCircle size={10} className="spin" />
                    {latest?.status === 'waiting' ? 'Queued' : 'Researching'}
                  </>
                ) : policy.status === 'armed' ? (
                  'Scheduled'
                ) : (
                  'Paused'
                )}
              </Badge>
              {scheduledChannel(policy) && (
                <span className="briefing-channel-tag">
                  {scheduledChannel(policy) === 'email' ? (
                    <Mail size={13} />
                  ) : (
                    <img
                      src={`/messaging/${scheduledChannel(policy)}.svg`}
                      width="13"
                      height="13"
                      alt=""
                    />
                  )}
                  {channelName(scheduledChannel(policy)!)}
                </span>
              )}
            </div>
            <p>
              {policy.next_run_at
                ? `Next ${calendarDate(policy.next_run_at, policy.timezone)} · ${policy.timezone}`
                : `Future briefings paused · ${policy.timezone}`}
            </p>
            {latest?.delivery && (
              <button
                className="briefing-delivery-status"
                data-state={latest.delivery.status}
                onClick={() => setHistory(true)}
              >
                {(latest.delivery?.channel || scheduledChannel(policy)) === 'email' ? (
                  <Mail size={11} />
                ) : (
                  <img
                    src={`/messaging/${latest.delivery?.channel || scheduledChannel(policy) || 'telegram'}.svg`}
                    width="11"
                    height="11"
                    alt=""
                  />
                )}
                {latest.delivery.status === 'sent'
                  ? 'Briefing sent'
                  : latest.delivery.status === 'sending'
                    ? 'Sending briefing…'
                    : latest.delivery.status === 'pending'
                      ? 'Briefing delivery queued'
                      : latest.delivery.status === 'retrying'
                        ? 'Waiting for delivery'
                        : 'Delivery ' + latest.delivery.status}
                {latest.delivery.total_parts > 0 &&
                  ` · ${latest.delivery.sent_parts}/${latest.delivery.total_parts} parts`}
              </button>
            )}
            {latest && ['blocked', 'failed', 'missed', 'interrupted'].includes(latest.status) && (
              <button className="briefing-attention" onClick={() => setHistory(true)}>
                Latest briefing {latest.status} · view details
              </button>
            )}
          </div>
          <div className="briefing-controls">
            <button
              className="button"
              disabled={!!busy || !ready || policy.status !== 'armed' || briefingPending(latest)}
              onClick={() => void run()}
            >
              <Play size={12} />
              {scheduledChannel(policy) ? 'Run & deliver' : 'Run now'}
            </button>
            <button
              className="icon-button"
              aria-label="Edit briefing schedule"
              disabled={!!busy}
              onClick={() => setEditing(true)}
            >
              <Pencil size={14} />
            </button>
            <button
              className="icon-button"
              aria-label={
                policy.status === 'armed' ? 'Pause briefing schedule' : 'Resume briefing schedule'
              }
              disabled={!!busy}
              onClick={() => void action(policy.status === 'armed' ? 'pause' : 'resume')}
            >
              {policy.status === 'armed' ? <Pause size={14} /> : <Play size={14} />}
            </button>
            <button
              className="icon-button"
              aria-label="Briefing history"
              onClick={() => setHistory(true)}
            >
              <History size={15} />
            </button>
            <button
              className="icon-button"
              aria-label="Archive briefing schedule"
              disabled={!!busy}
              onClick={() => void action('archive')}
            >
              <Archive size={14} />
            </button>
          </div>
        </div>
      ) : (
        !policies.loading && (
          <div className="briefing-add">
            <CalendarClock size={18} />
            <div>
              <strong>Make it a regular briefing.</strong>
              <span>Daily or weekly, with an optional private destination.</span>
            </div>
            {!!policies.data?.length && (
              <button
                className="icon-button"
                aria-label="Archived briefing history"
                onClick={() => setHistory(true)}
              >
                <History size={15} />
              </button>
            )}
            <button className="button" onClick={() => setEditing(true)}>
              <Plus size={14} />
              Schedule
            </button>
          </div>
        )
      )}
      {error && (
        <p className="inline-alert" role="alert">
          {error}
        </p>
      )}
      {detail.error && (
        <p className="footnote" role="alert">
          Schedule status could not be read.{' '}
          <button className="text-link" onClick={detail.retry}>
            Try again
          </button>
        </p>
      )}
    </div>
  );
}

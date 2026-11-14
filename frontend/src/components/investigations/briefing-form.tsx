import { useId, useState } from 'react';
import { Link } from 'react-router-dom';
import { CalendarClock, CalendarDays, Sun } from 'lucide-react';
import { Modal } from '../ui';
import { useResource } from '../../lib/hooks';
import { post } from '../../lib/api';
import {
  PrivateDestinationPicker,
  targetKey,
  bindingKey,
  type NotificationTarget,
} from '../messaging/notification-targets';
import type { BriefingInput, BriefingSchedule } from './briefing-types';
import { weekdays, scheduledChannel } from './briefing-types';

const commonZones = [
  'UTC',
  'Europe/Zurich',
  'Europe/London',
  'Europe/Athens',
  'Europe/Berlin',
  'America/New_York',
  'America/Chicago',
  'America/Los_Angeles',
  'America/Toronto',
  'Asia/Tokyo',
  'Asia/Singapore',
  'Asia/Hong_Kong',
  'Asia/Dubai',
  'Australia/Sydney',
];

/** An explicit calendar and recipient selection; saving never starts inference immediately. */
export function BriefingForm({
  investigation,
  initial,
  ready,
  onClose,
  onSaved,
}: {
  investigation: string;
  initial?: BriefingSchedule;
  ready: boolean;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [original] = useState(initial);
  const formatHelp = useId();
  const settings = useResource<{ items: NotificationTarget[] }>('/message-deliveries/targets');
  const [destination, setDestination] = useState(
    initial
      ? bindingKey(scheduledChannel(initial), initial.delivery_binding || initial.telegram_binding)
      : '',
  );
  const selected = settings.data?.items.find(
    (row) => !!row.target && targetKey(row) === destination,
  );
  const [values, setValues] = useState<BriefingInput>({
    frequency: initial?.frequency ?? 'daily',
    local_time: initial?.local_time ?? '08:00',
    timezone: initial?.timezone ?? Intl.DateTimeFormat().resolvedOptions().timeZone ?? 'UTC',
    weekday: initial?.weekday ?? 0,
    channel: initial ? scheduledChannel(initial) : null,
    message_format: initial?.message_format ?? initial?.telegram_format ?? 'text',
    delivery_format: initial?.delivery_format ?? 'summary',
    keep_reports: initial?.keep_reports ?? 20,
  });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const save = async (paused = false) => {
    if (busy) return;
    setBusy(true);
    setError('');
    try {
      if (destination && !selected)
        throw new Error(
          'The checked connection changed. Select its current private destination or choose Local only.',
        );
      const payload = {
        ...values,
        channel: selected?.channel || null,
        message_format: selected?.channel === 'telegram' ? values.message_format : 'text',
        telegram_target: selected?.channel === 'telegram' ? selected.target : null,
        private_target: selected && selected.channel !== 'telegram' ? selected.target : null,
        ...(original ? { revision: original.revision } : { enabled: !paused }),
      };
      await post(
        original
          ? `/briefing-schedules/${original.id}`
          : `/investigations/${investigation}/schedules`,
        payload,
      );
      onSaved();
    } catch (reason) {
      setError((reason as Error).message);
      settings.retry();
    } finally {
      setBusy(false);
    }
  };
  return (
    <Modal
      title={original ? 'Edit briefing schedule' : 'Schedule a briefing'}
      onClose={() => !busy && onClose()}
      className="briefing-form-dialog"
      initialFocus="input[type=time]"
    >
      <p className="muted">
        A fresh investigation at a time that suits you. The backend needs to be running.
      </p>
      <form
        onSubmit={(event) => {
          event.preventDefault();
          void save();
        }}
      >
        <div className="briefing-frequency" role="group" aria-label="Briefing frequency">
          <button
            type="button"
            aria-pressed={values.frequency === 'daily'}
            disabled={busy}
            onClick={() => setValues({ ...values, frequency: 'daily' })}
          >
            <Sun size={16} />
            Daily
          </button>
          <button
            type="button"
            aria-pressed={values.frequency === 'weekly'}
            disabled={busy}
            onClick={() => setValues({ ...values, frequency: 'weekly' })}
          >
            <CalendarDays size={16} />
            Weekly
          </button>
        </div>
        <div className="form-grid">
          <label>
            Local time
            <input
              type="time"
              required
              value={values.local_time}
              onChange={(event) => setValues({ ...values, local_time: event.target.value })}
              disabled={busy}
            />
          </label>
          <label>
            Time zone
            <input
              required
              list="briefing-timezones"
              value={values.timezone}
              onChange={(event) => setValues({ ...values, timezone: event.target.value })}
              placeholder="Europe/Zurich"
              disabled={busy}
            />
            <datalist id="briefing-timezones">
              {[...new Set([values.timezone, ...commonZones])].map((zone) => (
                <option key={zone} value={zone} />
              ))}
            </datalist>
          </label>
          {values.frequency === 'weekly' && (
            <label>
              Day
              <select
                value={values.weekday}
                onChange={(event) => setValues({ ...values, weekday: Number(event.target.value) })}
                disabled={busy}
              >
                {weekdays.map((day, index) => (
                  <option key={day} value={index}>
                    {day}
                  </option>
                ))}
              </select>
            </label>
          )}
        </div>
        <p className="footnote">
          Daylight-saving changes follow this time zone. Nonexistent local times are skipped; a
          repeated hour runs once. Missed times do not create catch-up reports.
        </p>
        {settings.error ? (
          <p className="inline-alert">
            {settings.error}{' '}
            <button type="button" className="text-link" onClick={settings.retry}>
              Reload destinations
            </button>
          </p>
        ) : (
          <PrivateDestinationPicker
            targets={settings.data?.items || []}
            value={destination}
            disabled={busy}
            label="Private briefing destination"
            onChange={(key) => {
              setDestination(key);
              const choice = settings.data?.items.find((row) => targetKey(row) === key);
              if (choice?.channel !== 'telegram')
                setValues((current) => ({ ...current, message_format: 'text' }));
            }}
          />
        )}
        {destination && !selected && (
          <p className="inline-alert">
            The saved private connection changed or is unavailable. Select its current checked card
            or choose Local only; it will not be replaced automatically.
          </p>
        )}
        {selected && (
          <>
            {selected.channel === 'telegram' && (
              <label className="briefing-format">
                Delivery format
                <select
                  aria-label="Delivery format"
                  aria-describedby={formatHelp}
                  value={values.message_format}
                  disabled={busy}
                  onChange={(event) =>
                    setValues({
                      ...values,
                      message_format: event.target.value as BriefingInput['message_format'],
                    })
                  }
                >
                  <option value="text">Text messages</option>
                  <option value="document">One text document · up to 64 KiB</option>
                </select>
                <small id={formatHelp}>
                  Documents preserve selected content; oversized documents stay local with a
                  delivery error.
                </small>
              </label>
            )}
            <label className="briefing-format">
              Message content
              <select
                aria-label="Message content"
                value={values.delivery_format}
                disabled={busy}
                onChange={(event) =>
                  setValues({
                    ...values,
                    delivery_format: event.target.value as BriefingInput['delivery_format'],
                  })
                }
              >
                <option value="summary">Summary & uncertainty</option>
                <option value="full">Full briefing</option>
              </select>
            </label>
            <p className="footnote">
              Private account research may pass through {selected.label}. Text follows its message
              limits; the full report remains in Sibyl.
            </p>
            {!selected.enabled && (
              <p className="inline-alert">
                {selected.label} is paused. Briefings accepted while this connection is paused stay
                local, even if you enable it before the report finishes.
              </p>
            )}
            {selected.channel === 'whatsapp' && (
              <p className="inline-alert">
                {selected.note} A closed window at acceptance keeps that briefing local; no
                templates or delayed sends are used.
              </p>
            )}
          </>
        )}
        <p className="footnote">
          Reports are always saved locally. A connection pause, replacement or recipient change
          after acceptance cannot redirect a running briefing.
        </p>
        <Link className="text-link" to="/settings?tab=messaging">
          Manage messaging ↗
        </Link>
        <details className="briefing-retention">
          <summary>
            Report retention <span>Keep {values.keep_reports} scheduled versions</span>
          </summary>
          <label>
            Scheduled versions to retain
            <input
              type="number"
              required
              min={5}
              max={40}
              value={values.keep_reports}
              onChange={(event) =>
                setValues({ ...values, keep_reports: Number(event.target.value) })
              }
              disabled={busy}
            />
          </label>
          <p className="footnote">
            Older scheduled versions and their untouched generated chats are removed. Manual reports
            and conversations you have continued are kept.
          </p>
        </details>
        {!ready && (
          <p className="inline-alert">
            You can save the schedule now. Briefings will be blocked until you{' '}
            <Link to="/settings?tab=models">configure an AI model</Link>.
          </p>
        )}
        {error && (
          <p className="inline-alert" role="alert">
            {error}
          </p>
        )}
        <div className="form-actions">
          {!original && (
            <button
              type="button"
              className="button"
              disabled={busy}
              onClick={() => void save(true)}
            >
              Save paused
            </button>
          )}
          <button type="submit" className="button primary" disabled={busy}>
            <CalendarClock size={15} />
            {busy ? 'Saving…' : original ? 'Save schedule' : 'Create schedule'}
          </button>
        </div>
      </form>
    </Modal>
  );
}

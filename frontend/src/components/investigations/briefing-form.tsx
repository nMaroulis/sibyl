import { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { CalendarClock, CalendarDays, Sun } from 'lucide-react';
import { Modal } from '../ui';
import { useResource } from '../../lib/hooks';
import { post } from '../../lib/api';
import type { MessagingSettingsData } from '../messaging-settings';
import type { BriefingInput, BriefingSchedule } from './briefing-types';
import { weekdays } from './briefing-types';

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
  const settings = useResource<MessagingSettingsData>('/settings/messaging');
  const channel = settings.data?.channels.find((item) => item.id === 'telegram');
  const [values, setValues] = useState<BriefingInput>({
    frequency: initial?.frequency ?? 'daily',
    local_time: initial?.local_time ?? '08:00',
    timezone: initial?.timezone ?? Intl.DateTimeFormat().resolvedOptions().timeZone ?? 'UTC',
    weekday: initial?.weekday ?? 0,
    telegram: initial?.telegram ?? false,
    delivery_format: initial?.delivery_format ?? 'summary',
    keep_reports: initial?.keep_reports ?? 20,
  });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [targetNotice, setTargetNotice] = useState('');
  const target = useRef('');
  useEffect(() => {
    if (!channel) return;
    const current =
      channel.bot_id && channel.allowed_user_id
        ? `${channel.bot_id}:${channel.allowed_user_id}`
        : '';
    const previous = original?.telegram_binding
      ? `${original.telegram_binding.bot_id}:${original.telegram_binding.recipient_id}`
      : '';
    if (
      (target.current && target.current !== current) ||
      (!target.current && original?.telegram && previous !== current)
    ) {
      setValues((value) => ({ ...value, telegram: false }));
      setTargetNotice(
        'The checked Telegram connection changed. Choose its current private recipient below to enable delivery.',
      );
    }
    target.current = current;
  }, [channel?.bot_id, channel?.allowed_user_id]);
  const save = async (paused = false) => {
    if (busy) return;
    setBusy(true);
    setError('');
    try {
      const payload = {
        ...values,
        telegram_target: values.telegram
          ? { bot_id: channel?.bot_id, user_id: channel?.allowed_user_id }
          : null,
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
        <label className={`briefing-telegram-choice ${values.telegram ? 'selected' : ''}`}>
          <img src="/messaging/telegram.svg" width="26" height="26" alt="" />
          <span>
            <strong>Deliver to Telegram</strong>
            <small>
              {channel?.briefings_ready
                ? `@${channel.bot_username} · private user ${channel.allowed_user_id}`
                : 'Check your saved bot in Settings → Messaging first.'}
            </small>
          </span>
          <input
            type="checkbox"
            checked={values.telegram}
            onChange={(event) => setValues({ ...values, telegram: event.target.checked })}
            disabled={busy || (!channel?.briefings_ready && !values.telegram)}
          />
        </label>
        {targetNotice && <p className="footnote">{targetNotice}</p>}
        {values.telegram ? (
          <>
            <label className="briefing-format">
              Message content
              <select
                value={values.delivery_format}
                onChange={(event) =>
                  setValues({
                    ...values,
                    delivery_format: event.target.value as BriefingInput['delivery_format'],
                  })
                }
                disabled={busy}
              >
                <option value="summary">Summary & uncertainty</option>
                <option value="full">Full briefing</option>
              </select>
            </label>
            <p className="footnote">
              Briefings can contain private account research. Only this checked bot and private user
              are authorized.{' '}
              {!channel?.enabled && 'Telegram is paused; reports stay local until it is enabled.'}
            </p>
          </>
        ) : (
          <p className="footnote">
            Reports are saved in Sibyl. <Link to="/settings?tab=messaging">Manage Telegram ↗</Link>
          </p>
        )}
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

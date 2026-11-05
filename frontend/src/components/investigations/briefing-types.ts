export type BriefingInput = {
  frequency: 'daily' | 'weekly';
  local_time: string;
  timezone: string;
  weekday: number;
  telegram: boolean;
  delivery_format: 'summary' | 'full';
  keep_reports: number;
};
export type BriefingDelivery = {
  id: string;
  status: string;
  sent_parts: number;
  total_parts: number;
  preview: string;
  error: string | null;
  parts: {
    part: number;
    state: string;
    attempts: number;
    native_id: number | null;
    error: string | null;
  }[];
};
export type BriefingOccurrence = {
  id: string;
  status: string;
  trigger: 'manual' | 'calendar';
  requested_at: string;
  scheduled_for: string | null;
  finished_at: string | null;
  error: string | null;
  run_id: string | null;
  report_available: boolean;
  telegram_requested: boolean;
  delivery_error: string | null;
  delivery: BriefingDelivery | null;
};
export type BriefingSchedule = BriefingInput & {
  id: string;
  investigation_id: string;
  revision: number;
  status: 'armed' | 'paused' | 'archived';
  next_run_at: string | null;
  telegram_binding: { bot_id: number; recipient_id: number; bot_username: string } | null;
  occurrences?: BriefingOccurrence[];
};
export const briefingPending = (item?: BriefingOccurrence) =>
  Boolean(item && ['waiting', 'running'].includes(item.status));
export const weekdays = [
  'Monday',
  'Tuesday',
  'Wednesday',
  'Thursday',
  'Friday',
  'Saturday',
  'Sunday',
];
export const briefingLabel = (state: string) =>
  ({
    waiting: 'Queued',
    running: 'Researching',
    completed: 'Report ready',
    failed: 'Failed',
    missed: 'Missed',
    blocked: 'Setup needed',
    interrupted: 'Interrupted',
    cancelled: 'Cancelled',
    pending: 'Delivery queued',
    sending: 'Sending',
    retrying: 'Waiting for Telegram',
    sent: 'Delivered',
    uncertain: 'Unconfirmed',
    partial: 'Partially delivered',
    skipped: 'Not sent',
  })[state] ?? state;
export function calendarDate(when: string | null, zone: string) {
  if (!when) return '—';
  const date = new Date(when);
  if (!Number.isFinite(date.getTime())) return 'Unavailable';
  try {
    return new Intl.DateTimeFormat(undefined, {
      timeZone: zone,
      weekday: 'short',
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    }).format(date);
  } catch {
    return date.toISOString();
  }
}

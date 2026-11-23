import { Check, Mail } from 'lucide-react';
import '../../styles/message-destinations.css';

export type NotificationChannel =
  'telegram' | 'discord' | 'slack' | 'signal' | 'whatsapp' | 'email';
export type NotificationBinding = {
  bot_id: number | string;
  recipient_id: number | string;
  connection_revision?: string;
  target_id?: string;
  bot_username?: string;
};
export type NotificationTarget = {
  channel: NotificationChannel;
  label: string;
  checked: boolean;
  enabled: boolean;
  account_label: string;
  recipient: string;
  window_open: boolean;
  note: string;
  target: {
    bot_id: number | string;
    user_id?: number;
    channel?: NotificationChannel;
    revision?: string;
    recipient_id?: string;
    target_id?: string;
  } | null;
};
export const channelName = (value: string) =>
  value === 'whatsapp' ? 'WhatsApp' : value[0].toUpperCase() + value.slice(1);
export const targetKey = (row: NotificationTarget) =>
  row.target
    ? JSON.stringify([
        row.channel,
        String(row.target.bot_id),
        String(row.target.user_id ?? row.target.recipient_id),
        row.target.revision || '',
        row.target.target_id || '',
      ])
    : '';
export const bindingKey = (
  channel: NotificationChannel | null | undefined,
  binding: NotificationBinding | null | undefined,
) =>
  channel && binding
    ? JSON.stringify([
        channel,
        String(binding.bot_id),
        String(binding.recipient_id),
        binding.connection_revision || '',
        binding.target_id || '',
      ])
    : '';

/** One checked private destination; the consent key never follows a replacement automatically. */
export function PrivateDestinationPicker({
  targets,
  value,
  onChange,
  disabled = false,
  label = 'Private message destination',
}: {
  targets: NotificationTarget[];
  value: string;
  onChange: (key: string) => void;
  disabled?: boolean;
  label?: string;
}) {
  return (
    <>
      <div className="message-target-heading">
        <strong>Optional private destination</strong>
        <button
          type="button"
          className="text-link"
          disabled={disabled}
          onClick={() => onChange('')}
        >
          {value ? 'Use local only' : 'Local only selected'}
        </button>
      </div>
      <div
        className="message-destination-grid"
        role="radiogroup"
        aria-label={label}
        onKeyDown={(event) => {
          if (
            !['ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown', 'Home', 'End'].includes(event.key)
          )
            return;
          const buttons = [
            ...event.currentTarget.querySelectorAll<HTMLButtonElement>(
              'button[role="radio"]:not(:disabled)',
            ),
          ];
          if (!buttons.length) return;
          const index = buttons.indexOf(document.activeElement as HTMLButtonElement);
          const next =
            event.key === 'Home'
              ? 0
              : event.key === 'End'
                ? buttons.length - 1
                : (index +
                    (['ArrowLeft', 'ArrowUp'].includes(event.key) ? -1 : 1) +
                    buttons.length) %
                  buttons.length;
          event.preventDefault();
          buttons[next].focus();
          buttons[next].click();
        }}
      >
        {targets.map((row) => (
          <button
            type="button"
            role="radio"
            aria-checked={!!row.target && value === targetKey(row)}
            className={`message-destination ${row.target && value === targetKey(row) ? 'selected' : ''}`}
            key={row.channel}
            disabled={disabled || !row.checked}
            onClick={() => onChange(targetKey(row))}
          >
            {row.channel === 'email' ? (
              <Mail size={25} />
            ) : (
              <img src={`/messaging/${row.channel}.svg`} alt="" width="25" height="25" />
            )}
            <span>
              <strong>{row.label}</strong>
              <small>{row.checked ? row.account_label : 'Set up & check in Messaging'}</small>
              {row.checked && <small className="message-recipient">{row.recipient}</small>}
            </span>
            {row.checked && value === targetKey(row) ? (
              <Check size={15} />
            ) : (
              row.checked && (
                <em>{!row.enabled ? 'Paused' : !row.window_open ? 'Window closed' : 'Enabled'}</em>
              )
            )}
          </button>
        ))}
      </div>
    </>
  );
}

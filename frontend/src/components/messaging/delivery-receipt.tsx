import { useState } from 'react';
import { Mail } from 'lucide-react';
import { DeliveryInspector } from './delivery-review';
import { Badge } from '../ui';

export type MessageDelivery = {
  id: string;
  kind?: string;
  channel?: string;
  rule_id?: string;
  alert_kind?: string;
  created_at?: string;
  status: string;
  sent_parts: number;
  total_parts: number;
  preview: string;
  reviews?: { decision: string; note: string; at: string; native_confirmation: false }[];
  error: string | null;
  parts: {
    format?: 'text' | 'document';
    filename?: string | null;
    part: number;
    state: string;
    attempts: number;
    native_id: number | null;
    provider_id?: string | null;
    error: string | null;
  }[];
};
const labels: Record<string, string> = {
  sent: 'Sent',
  pending: 'Queued',
  sending: 'Sending',
  retrying: 'Rate limited',
  uncertain: 'Unconfirmed',
  failed: 'Failed',
  partial: 'Partially delivered',
  skipped: 'Not sent',
};

/** Display provider-confirmed outcomes, never treating queue admission as successful delivery. */
export function DeliveryReceipt({ delivery }: { delivery: MessageDelivery }) {
  const [review, setReview] = useState(false);
  return (
    <div className="message-delivery-receipt">
      {delivery.kind === 'alert' && (
        <strong className="message-delivery-title">
          {delivery.preview.split('\n')[0].replace(/^Sibyl alert · /, '')}
        </strong>
      )}
      <header>
        <span className="message-delivery-channel">
          {delivery.channel === 'email' ? (
            <Mail size={13} />
          ) : (
            <img
              src={`/messaging/${delivery.channel || 'telegram'}.svg`}
              alt=""
              width="13"
              height="13"
            />
          )}
          {delivery.channel === 'whatsapp'
            ? 'WhatsApp'
            : (delivery.channel || 'telegram').replace(/^./, (value) => value.toUpperCase())}
        </span>
        <Badge
          tone={
            delivery.status === 'sent'
              ? 'lime'
              : ['uncertain', 'failed', 'partial'].includes(delivery.status)
                ? 'rose'
                : 'neutral'
          }
        >
          {labels[delivery.status] ?? delivery.status}
        </Badge>
        <span>
          {delivery.total_parts
            ? `${delivery.sent_parts}/${delivery.total_parts} parts confirmed`
            : 'No message parts queued'}
        </span>
        {delivery.created_at && <time>{new Date(delivery.created_at).toLocaleString()}</time>}
      </header>
      {delivery.error && <p>{delivery.error}</p>}
      <details>
        <summary>Message & delivery details</summary>
        <p className="message-preview">
          {delivery.preview}
          {delivery.preview.length >= 240 ? '…' : ''}
        </p>
        {delivery.preview.length >= 240 && <small>Message preview · first 240 characters</small>}
        {delivery.parts.map((part) => (
          <div key={part.part} className="message-delivery-part">
            <span>
              {part.format === 'document' ? `Document · ${part.filename}` : `Part ${part.part + 1}`}
            </span>
            <Badge>{part.state}</Badge>
            <small>
              {part.attempts} attempt{part.attempts === 1 ? '' : 's'}
              {part.provider_id
                ? ` · Provider ID ${part.provider_id}`
                : part.native_id
                  ? ` · Telegram ${part.native_id}`
                  : ''}
            </small>
            {part.error && <p>{part.error}</p>}
          </div>
        ))}
      </details>
      {!!delivery.reviews?.length && <small>User reviewed · native outcome retained</small>}
      <button className="text-button" onClick={() => setReview(true)}>
        Review delivery →
      </button>
      {review && <DeliveryInspector id={delivery.id} onClose={() => setReview(false)} />}
    </div>
  );
}

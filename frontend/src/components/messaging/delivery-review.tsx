import { useState } from 'react';
import { post } from '../../lib/api';
import { useResource } from '../../lib/hooks';
import { Badge, Modal, useToast } from '../ui';
import type { MessageDelivery } from './delivery-receipt';

type Detail = MessageDelivery & {
  bot_username?: string;
  recipient_id?: number;
  can_withdraw: boolean;
  can_acknowledge: boolean;
  text_parts: { part: number; text: string }[];
  review_token: string;
  note: string;
};
const base = '/settings/messaging/telegram/deliveries';

/** Manual review is separate from native confirmation and cannot resend a message. */
export function DeliveryInspector({ id, onClose }: { id: string; onClose: () => void }) {
  const state = useResource<Detail>(`${base}/${id}`, 2500);
  const [note, setNote] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const toast = useToast();
  const delivery = state.data;
  const decide = async (decision: 'withdraw' | 'received' | 'dismissed') => {
    if (!delivery) return;
    setBusy(true);
    setError('');
    try {
      await post(`${base}/${id}/review`, { token: delivery.review_token, decision, note });
      state.retry();
      setNote('');
      toast(
        decision === 'withdraw'
          ? 'Unsent remainder withdrawn.'
          : 'Your review was saved. Native outcomes remain unchanged.',
      );
    } catch (e) {
      setError((e as Error).message);
      state.retry();
    } finally {
      setBusy(false);
    }
  };
  return (
    <Modal title="Review Telegram delivery" onClose={onClose}>
      {(error || state.error) && (
        <p className="form-error" role="alert">
          {error || state.error}
        </p>
      )}
      {!delivery ? (
        <p>Loading receipt…</p>
      ) : (
        <div className="delivery-inspector">
          <header>
            <Badge>{delivery.status}</Badge>
            <span>
              {delivery.sent_parts}/{delivery.total_parts} parts confirmed
            </span>
          </header>
          <p>
            Bot {delivery.bot_username ? `@${delivery.bot_username}` : 'not recorded'} · private
            recipient {delivery.recipient_id ?? 'not recorded'}
          </p>
          {delivery.error && <p className="inline-alert">{delivery.error}</p>}
          {delivery.text_parts.map((part) => (
            <section key={part.part}>
              <strong>Part {part.part + 1}</strong>
              <pre>{part.text}</pre>
              <small>
                {delivery.parts.find((p) => p.part === part.part)?.state} · Telegram message{' '}
                {delivery.parts.find((p) => p.part === part.part)?.native_id ?? 'unconfirmed'}
              </small>
            </section>
          ))}
          {!delivery.text_parts.length && <p>No text was queued. Preview: {delivery.preview}</p>}
          <p className="footnote">{delivery.note} A confirmed send cannot be recalled here.</p>
          {(delivery.can_withdraw || delivery.can_acknowledge) && (
            <label>
              Review note (optional)
              <textarea
                value={note}
                maxLength={500}
                onChange={(e) => setNote(e.target.value)}
                rows={2}
              />
            </label>
          )}
          <div className="workspace-actions">
            {delivery.can_withdraw && (
              <button
                className="button secondary tiny"
                disabled={busy}
                onClick={() => void decide('withdraw')}
              >
                Withdraw unsent remainder
              </button>
            )}
            {delivery.can_acknowledge && (
              <>
                <button
                  className="button secondary tiny"
                  disabled={busy}
                  onClick={() => void decide('received')}
                >
                  I received it in Telegram
                </button>
                <button
                  className="text-button"
                  disabled={busy}
                  onClick={() => void decide('dismissed')}
                >
                  Dismiss review
                </button>
              </>
            )}
            <button className="text-button" disabled={busy} onClick={() => state.retry()}>
              Refresh outcome
            </button>
          </div>
          {delivery.status === 'sending' && (
            <p className="footnote">
              A part is already being sent. Wait for its outcome before reviewing.
            </p>
          )}
          {!!delivery.reviews?.length && (
            <div className="delivery-review-log">
              <strong>User review history</strong>
              {delivery.reviews.map((review, i) => (
                <p key={i}>
                  <Badge>
                    {review.decision === 'received'
                      ? 'User reports received'
                      : review.decision === 'dismissed'
                        ? 'Review dismissed'
                        : 'Unsent remainder withdrawn'}
                  </Badge>
                  <time>{new Date(review.at).toLocaleString()}</time>
                  {review.note && <span>{review.note}</span>}
                </p>
              ))}
            </div>
          )}
        </div>
      )}
    </Modal>
  );
}

/** Compact entry point for alerts and scheduled briefings, including earlier bot connections. */
export function TelegramDeliveryReview() {
  const [open, setOpen] = useState(false);
  const [kind, setKind] = useState<'alert' | 'briefing' | 'reply'>('alert');
  const [offset, setOffset] = useState(0);
  const [id, setId] = useState('');
  const receipts = useResource<{ items: MessageDelivery[]; total: number }>(
    `${base}?kind=${kind}&offset=${offset}`,
    3000,
    open,
  );
  return (
    <details className="telegram-history-review" onToggle={(e) => setOpen(e.currentTarget.open)}>
      <summary>Review Telegram deliveries</summary>
      <p className="footnote">
        Inspect exact queued text, confirmed parts and user reviews, including conversation replies.
      </p>
      <label>
        Delivery type
        <select
          value={kind}
          onChange={(e) => {
            setKind(e.target.value as typeof kind);
            setOffset(0);
          }}
        >
          <option value="alert">Alerts</option>
          <option value="reply">Conversation replies</option>
          <option value="briefing">Scheduled briefings</option>
        </select>
      </label>
      {receipts.error && <p className="form-error">{receipts.error}</p>}
      {receipts.data?.items.map((delivery) => (
        <button
          className="delivery-review-row"
          key={delivery.id}
          onClick={() => setId(delivery.id)}
        >
          <span>
            <strong>{delivery.preview.split('\n')[0] || 'Notification'}</strong>
            <small>
              {delivery.created_at && new Date(delivery.created_at).toLocaleString()} ·{' '}
              {delivery.sent_parts}/{delivery.total_parts} confirmed
            </small>
          </span>
          <Badge
            tone={['uncertain', 'failed', 'partial'].includes(delivery.status) ? 'rose' : 'neutral'}
          >
            {delivery.status}
          </Badge>
          {!!delivery.reviews?.length && (
            <Badge>
              {delivery.reviews.at(-1)?.decision === 'received'
                ? 'User reports received'
                : 'User reviewed'}
            </Badge>
          )}
          <span>Review →</span>
        </button>
      ))}
      {receipts.data?.total === 0 && (
        <p>
          No {kind === 'alert' ? 'alert' : kind === 'reply' ? 'conversation reply' : 'briefing'}{' '}
          deliveries have been queued.
        </p>
      )}
      {(offset > 0 || (receipts.data?.total ?? 0) > offset + 20) && (
        <div className="workspace-actions">
          <button className="text-button" disabled={!offset} onClick={() => setOffset(offset - 20)}>
            Previous
          </button>
          <span>
            {offset + 1}–{Math.min(offset + 20, receipts.data?.total ?? 0)} of{' '}
            {receipts.data?.total}
          </span>
          <button
            className="text-button"
            disabled={(receipts.data?.total ?? 0) <= offset + 20}
            onClick={() => setOffset(offset + 20)}
          >
            Next
          </button>
        </div>
      )}
      {id && (
        <DeliveryInspector
          id={id}
          onClose={() => {
            setId('');
            receipts.retry();
          }}
        />
      )}
    </details>
  );
}

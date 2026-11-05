import { useState } from 'react';
import { Link } from 'react-router-dom';
import { ArrowUpRight, Clock3, Send } from 'lucide-react';
import { Badge, ErrorState, Loading, Modal } from '../ui';
import { useResource } from '../../lib/hooks';
import { briefingLabel, calendarDate } from './briefing-types';
import type { BriefingSchedule } from './briefing-types';

/** Calendar outcomes and actual Telegram confirmations, including skipped and ambiguous writes. */
export function BriefingHistory({
  schedules,
  selected,
  onClose,
}: {
  schedules: BriefingSchedule[];
  selected: string;
  onClose: () => void;
}) {
  const [identity, setIdentity] = useState(selected);
  const detail = useResource<BriefingSchedule>(`/briefing-schedules/${identity}`, 2000);
  const policy = detail.data?.id === identity ? detail.data : undefined;
  return (
    <Modal title="Briefing history" onClose={onClose} className="briefing-history-dialog">
      {schedules.length > 1 && (
        <label className="briefing-history-picker">
          Calendar
          <select value={identity} onChange={(event) => setIdentity(event.target.value)}>
            {schedules.map((item) => (
              <option key={item.id} value={item.id}>
                {item.frequency} · {item.local_time} · {item.timezone}
                {item.status === 'archived' ? ' · archived' : ''}
              </option>
            ))}
          </select>
        </label>
      )}
      <p className="muted">
        Reports, missed times and delivery outcomes. Each briefing is submitted once; unconfirmed
        sends are never automatically repeated.
      </p>
      {detail.error ? (
        <ErrorState message={detail.error} retry={detail.retry} />
      ) : !policy ? (
        <Loading />
      ) : !policy.occurrences?.length ? (
        <p className="muted">
          No briefing occurrences yet. The next calendar time is shown on the schedule.
        </p>
      ) : (
        <div className="briefing-history-list">
          {policy.occurrences.map((item) => (
            <section key={item.id}>
              <header>
                <span>
                  <Clock3 size={13} />
                  {calendarDate(item.scheduled_for || item.requested_at, policy.timezone)}
                  <small>{item.trigger === 'manual' ? 'Run now' : 'Scheduled'}</small>
                </span>
                <Badge
                  tone={
                    item.status === 'completed'
                      ? 'lime'
                      : ['failed', 'blocked'].includes(item.status)
                        ? 'rose'
                        : 'neutral'
                  }
                >
                  {briefingLabel(item.status)}
                </Badge>
              </header>
              {item.error && <p>{item.error}</p>}
              {item.run_id &&
                (item.report_available ? (
                  <Link
                    className="text-link"
                    to={`/sibyl?tab=investigations&investigation=${policy.investigation_id}&run=${item.run_id}`}
                    onClick={onClose}
                  >
                    Open report
                    <ArrowUpRight size={12} />
                  </Link>
                ) : (
                  <p className="footnote">This report is outside its retained version history.</p>
                ))}
              {item.delivery ? (
                <div className="briefing-delivery">
                  <div>
                    <Send size={13} />
                    <strong>{briefingLabel(item.delivery.status)}</strong>
                    <span>
                      {item.delivery.total_parts
                        ? `${item.delivery.sent_parts}/${item.delivery.total_parts} parts confirmed`
                        : 'No message parts queued'}
                    </span>
                  </div>
                  {item.delivery.error && <p>{item.delivery.error}</p>}
                  <details>
                    <summary>Delivery details</summary>
                    <p>{item.delivery.preview}</p>
                    {item.delivery.parts.map((part) => (
                      <div key={part.part} className="briefing-part">
                        <span>Part {part.part + 1}</span>
                        <Badge>{part.state}</Badge>
                        <small>
                          {part.attempts} attempt{part.attempts === 1 ? '' : 's'}
                          {part.native_id ? ` · Telegram ${part.native_id}` : ''}
                        </small>
                        {part.error && <p>{part.error}</p>}
                      </div>
                    ))}
                  </details>
                </div>
              ) : item.delivery_error ? (
                <p className="footnote">{item.delivery_error}</p>
              ) : (
                item.status === 'completed' && (
                  <p className="footnote">
                    {item.telegram_requested
                      ? 'No delivery receipt is available.'
                      : 'Saved locally · Telegram delivery was not requested.'}
                  </p>
                )
              )}
            </section>
          ))}
        </div>
      )}
      <p className="footnote">
        Times are shown in {policy?.timezone ?? 'the schedule’s time zone'}. One missed entry can
        summarize an offline interval. Pausing stops future reports and unsent messages; an already
        admitted report or send can finish.
      </p>
    </Modal>
  );
}

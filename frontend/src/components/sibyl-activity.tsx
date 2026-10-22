import { useEffect, useState } from 'react';
import { Check, ChevronDown, LoaderCircle, Square, X } from 'lucide-react';
import { Badge, ErrorState, Loading } from './ui';
import { useResource } from '../lib/hooks';

export type Consultation = {
  agent_id: string;
  name: string;
  question: string;
  answer?: string;
  status: string;
  evidence?: unknown;
  error?: string;
  started_at?: string;
  finished_at?: string;
};
export type SibylActivity = {
  id: string;
  session_id: string;
  question: string;
  status:
    'queued' | 'running' | 'cancelling' | 'completed' | 'cancelled' | 'failed' | 'interrupted';
  phase: string;
  provider: string;
  model: string;
  created_at: string;
  finished_at: string | null;
  error: string | null;
  delegations: Consultation[];
};
export const activeRequest = (item?: SibylActivity | null) =>
  Boolean(item && ['queued', 'running', 'cancelling'].includes(item.status));
const labels: Record<string, string> = {
  queued: 'Waiting for an available slot',
  thinking: 'Sibyl is thinking',
  discovering: 'Discovering specialists',
  consulting: 'Consulting your specialists',
  cancelling: 'Stopping this request',
  completed: 'Completed',
  cancelled: 'Stopped',
  failed: 'Failed',
  interrupted: 'Interrupted by restart',
};

/** Show actual tool lifecycle events, without exposing private model reasoning. */
export function SibylProgress({
  activity,
  stopping,
  stop,
}: {
  activity?: SibylActivity | null;
  stopping: boolean;
  stop?: () => void;
}) {
  const status = activity?.status;
  return (
    <div className="sibyl-live-progress" role="status" aria-live="polite">
      <div className="sibyl-progress-heading">
        <span>
          <LoaderCircle size={13} className="spin" />
          {stopping
            ? 'Stopping this request'
            : (labels[activity?.phase ?? 'thinking'] ?? 'Sibyl is thinking')}
        </span>
        {stop && (
          <button type="button" onClick={stop} disabled={stopping || status === 'cancelling'}>
            <Square size={10} />
            {stopping || status === 'cancelling' ? 'Stopping…' : 'Stop'}
          </button>
        )}
      </div>
      {activity && activity.delegations.length > 0 && (
        <div className="sibyl-progress-team">
          {activity.delegations.map((item, index) => (
            <span key={index} data-status={item.status}>
              {item.status === 'running' ? (
                <LoaderCircle className="spin" size={11} />
              ) : item.status === 'completed' ? (
                <Check size={11} />
              ) : (
                <X size={11} />
              )}
              {item.name}
              <small>
                {item.status === 'running'
                  ? 'Working'
                  : item.status === 'completed'
                    ? 'Done'
                    : item.status === 'unavailable'
                      ? 'Unavailable'
                      : 'Stopped'}
              </small>
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

/** Fetch detailed observations only when a user opens a retained attempt. */
export function SibylRequestHistory({
  session,
  onUseQuestion,
}: {
  session: string;
  onUseQuestion: (question: string) => void;
}) {
  const history = useResource<SibylActivity[]>(`/sibyl/conversations/${session}/requests`);
  const [selected, setSelected] = useState('');
  const detail = useResource<SibylActivity>(
    `/sibyl/conversations/${session}/requests/${selected}`,
    0,
    Boolean(selected),
  );
  useEffect(() => setSelected(''), [session]);
  return (
    <div className="sibyl-request-history">
      <p className="muted">
        Recent requests, including stopped and interrupted attempts. Completed consultations stay
        available here.
      </p>
      {history.error ? (
        <ErrorState message={history.error} retry={history.retry} />
      ) : history.loading ? (
        <Loading />
      ) : !history.data?.length ? (
        <p className="muted">No requests in this conversation yet.</p>
      ) : (
        history.data.map((item) => (
          <section key={item.id}>
            <button
              className="sibyl-request-summary"
              onClick={() => setSelected(selected === item.id ? '' : item.id)}
              aria-expanded={selected === item.id}
            >
              <span>
                <strong>{item.question}</strong>
                <small>
                  {new Date(item.created_at).toLocaleString()} · {item.provider}
                  {item.model ? ` / ${item.model}` : ''}
                </small>
              </span>
              <Badge
                tone={
                  item.status === 'completed'
                    ? 'lime'
                    : item.status === 'failed'
                      ? 'rose'
                      : 'neutral'
                }
              >
                {labels[item.status] ?? item.status}
              </Badge>
              <ChevronDown size={14} />
            </button>
            {selected === item.id && (
              <div className="sibyl-request-detail">
                {detail.error ? (
                  <ErrorState message={detail.error} retry={detail.retry} />
                ) : detail.loading || detail.data?.id !== selected ? (
                  <Loading />
                ) : (
                  <>
                    {detail.data.error && <p>{detail.data.error}</p>}
                    {detail.data.delegations.length === 0 && (
                      <p className="muted">No specialist consultations were recorded.</p>
                    )}
                    {detail.data.delegations.map((entry, index) => (
                      <div key={index}>
                        <h4>
                          {entry.name}
                          <Badge>{entry.status}</Badge>
                        </h4>
                        <p className="muted">{entry.question}</p>
                        {entry.answer && <p>{entry.answer}</p>}
                        {entry.error && <p>{entry.error}</p>}
                        {entry.evidence !== undefined && (
                          <details>
                            <summary>Source observations</summary>
                            <pre>{JSON.stringify(entry.evidence, null, 2)}</pre>
                          </details>
                        )}
                      </div>
                    ))}
                    {!activeRequest(item) && (
                      <button className="button" onClick={() => onUseQuestion(item.question)}>
                        Use this question
                      </button>
                    )}
                  </>
                )}
              </div>
            )}
          </section>
        ))
      )}
    </div>
  );
}

import { Link } from 'react-router-dom';
import { useResource } from '../../lib/hooks';
import { ErrorState, Loading, Modal } from '../ui';

type ReplyPart = {
  part: number;
  state: string;
  attempts: number;
  next_attempt: number;
  error?: string | null;
  format?: string;
};
type MessageLog = {
  received_at: number;
  state: string;
  started_at?: number | null;
  finished_at?: number | null;
  failure?: { code: string; provider?: string; estimated_tokens?: number; prompt_tokens?: number };
  parts: ReplyPart[];
  selected_model?: { provider: string; id: string };
};

const processingLabels: Record<string, string> = {
  queued: 'Waiting to be processed',
  processing: 'Processing the message',
  completed: 'Processing completed',
  failed: 'Processing failed',
  interrupted: 'Processing interrupted',
  withdrawn: 'Stopped before processing',
};

const partLabels: Record<string, string> = {
  pending: 'Queued for delivery',
  sending: 'Sending',
  sent: 'Accepted by provider',
  failed: 'Delivery failed',
  blocked: 'Blocked by an earlier part',
  uncertain: 'Delivery unconfirmed',
  skipped: 'Skipped',
  withdrawn: 'Withdrawn',
};

const failureCopy: Record<string, { title: string; next: string; settings?: boolean }> = {
  context_limit: {
    title: 'The request exceeded Sibyl’s context allowance',
    next: 'Start a fresh conversation with /new or shorten the request.',
    settings: true,
  },
  provider_unreachable: {
    title: 'The model service could not be reached',
    next: 'Check that the model service is running and reachable from Sibyl’s backend, then send the message again.',
    settings: true,
  },
  model_not_ready: {
    title: 'Sibyl’s model was not ready',
    next: 'Check the model and provider setup before sending the message again.',
    settings: true,
  },
  invalid_model_output: {
    title: 'The model returned an invalid agent action',
    next: 'Try the request with the same or a more capable model. Repeated failures can mean the model struggles with tool calls.',
    settings: true,
  },
  queue_full: {
    title: 'The agent queue was full',
    next: 'Send the message again when Sibyl finishes other requests.',
  },
  queue_timeout: {
    title: 'The request expired in the agent queue',
    next: 'Send the message again when Sibyl finishes other requests.',
  },
  timeout: {
    title: 'The model request timed out',
    next: 'Check that the model service is responsive and try a shorter request.',
  },
  conversation_missing: {
    title: 'A conversation or record was missing',
    next: 'Start a fresh conversation with /new and send the message again.',
  },
  processing_failed: {
    title: 'Sibyl could not finish processing',
    next: 'The run did not record a more specific reason. Check the model provider before sending it again.',
    settings: true,
  },
  reason_unavailable: {
    title: 'The original failure reason is unavailable',
    next: 'This message has no retained diagnostic that explains why processing stopped.',
  },
};

function LogTime({ at }: { at: number }) {
  const date = new Date(at * 1000);
  return <time dateTime={date.toISOString()}>{date.toLocaleString()}</time>;
}

function FailureDetail({ failure }: { failure: NonNullable<MessageLog['failure']> }) {
  const copy = failureCopy[failure.code] ?? failureCopy.reason_unavailable;
  return (
    <div className="channel-log-diagnostic">
      <strong>
        {failure.code === 'provider_unreachable' && failure.provider === 'ollama'
          ? 'Ollama could not be reached'
          : copy.title}
      </strong>
      {failure.estimated_tokens != null && failure.prompt_tokens != null && (
        <p>
          Prompt estimate {failure.estimated_tokens.toLocaleString()} tokens · allowance{' '}
          {failure.prompt_tokens.toLocaleString()} tokens.
        </p>
      )}
      <p>
        {copy.next}
        {failure.code === 'context_limit' &&
          failure.provider === 'ollama' &&
          ' You can also increase Ollama’s context window if your model and available memory allow it.'}
      </p>
      {copy.settings && (
        <Link className="text-link" to="/settings?tab=models">
          AI model settings
        </Link>
      )}
    </div>
  );
}

export function MessageLogDialog({
  channel,
  message,
  close,
}: {
  channel: string;
  message: string;
  close: () => void;
}) {
  const sequence = message.slice('message-'.length);
  const { data, error, loading, retry } = useResource<MessageLog>(
    `/settings/messaging/channels/${encodeURIComponent(channel)}/activity/${encodeURIComponent(sequence)}`,
    5000,
  );
  return (
    <Modal title="Message log" className="channel-message-log" onClose={close}>
      {loading ? (
        <Loading />
      ) : error ? (
        <ErrorState message={error} retry={retry} />
      ) : data ? (
        <>
          <ol className="channel-message-log-stages">
            <li>
              <strong>Message received</strong>
              <LogTime at={data.received_at} />
            </li>
            {data.started_at != null && data.state !== 'processing' && (
              <li>
                <strong>Processing started</strong>
                <LogTime at={data.started_at} />
              </li>
            )}
            <li>
              <strong>{processingLabels[data.state] ?? 'Processing recorded'}</strong>
              {data.finished_at != null ? (
                <LogTime at={data.finished_at} />
              ) : data.state === 'processing' && data.started_at != null ? (
                <LogTime at={data.started_at} />
              ) : null}
            </li>
          </ol>
          {data.selected_model && (
            <p className="footnote">
              Selected model · {data.selected_model.provider} / {data.selected_model.id}
            </p>
          )}
          {data.failure && <FailureDetail failure={data.failure} />}
          <h3>Reply delivery</h3>
          {data.parts.length ? (
            <ul className="channel-message-log-parts">
              {data.parts.map((part) => (
                <li key={part.part}>
                  <strong>
                    {part.format === 'document' ? 'Document' : `Part ${part.part + 1}`}
                  </strong>
                  <span>{partLabels[part.state] ?? 'Outcome recorded'}</span>
                  <small>
                    {part.attempts} {part.attempts === 1 ? 'attempt' : 'attempts'}
                  </small>
                  {part.error && <p>{part.error}</p>}
                  {part.state === 'pending' && part.next_attempt > Date.now() / 1000 && (
                    <p>Retry scheduled for {new Date(part.next_attempt * 1000).toLocaleString()}</p>
                  )}
                </li>
              ))}
            </ul>
          ) : (
            <p className="footnote">No reply parts have been recorded for this message.</p>
          )}
        </>
      ) : null}
    </Modal>
  );
}

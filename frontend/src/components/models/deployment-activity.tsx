import { useState } from 'react';
import { ChevronDown, History, RefreshCw } from 'lucide-react';
import { useResource } from '../../lib/hooks';
import { Badge, ErrorState, Loading } from '../ui';

type Activity = {
  report_limit: number;
  requests: number;
  failed: number;
  calls: number;
  reported_tokens: number | null;
  estimated_tokens: number | null;
  unknown_calls: number;
  context_window: number | null;
  context_mode: 'auto' | 'manual';
  max_output_tokens: number | null;
  recent: {
    id: string;
    at: string;
    source: string;
    agent: string;
    models: string[];
    status: string;
  }[];
};

const sources: Record<string, string> = {
  app: 'Sibyl app',
  telegram: 'Telegram',
  whatsapp: 'WhatsApp',
  discord: 'Discord',
  slack: 'Slack',
  signal: 'Signal',
  email: 'Email',
  investigation: 'Research',
};

const outcomes: Record<string, string> = {
  completed: 'Completed',
  failed: 'Failed',
  rejected: 'Rejected',
  canceled: 'Canceled',
  recorded: 'Recorded',
};

export function DeploymentActivity({
  deployment,
  model,
  visible,
}: {
  deployment: string;
  model: string;
  visible: boolean;
}) {
  const [open, setOpen] = useState(false);
  const { data, loading, error, retry } = useResource<Activity>(
    `/settings/llm/deployments/${encodeURIComponent(deployment)}/activity`,
    0,
    open && visible,
  );
  return (
    <details
      className="deployment-activity"
      onToggle={(event) => setOpen(event.currentTarget.open)}
    >
      <summary>
        <History size={15} aria-hidden="true" /> Request activity
        <ChevronDown size={13} aria-hidden="true" />
      </summary>
      {loading ? (
        <Loading />
      ) : error ? (
        <ErrorState message={error} retry={retry} />
      ) : data ? (
        <div className="deployment-activity-content">
          <div className="deployment-activity-heading">
            <p className="footnote">
              Deployment activity from the latest {data.report_limit} saved Sibyl runs.
            </p>
            <button type="button" className="text-button" onClick={retry}>
              <RefreshCw size={12} /> Refresh
            </button>
          </div>
          <dl className="deployment-activity-stats">
            <div>
              <dt>Requests</dt>
              <dd>{data.requests}</dd>
            </div>
            <div>
              <dt>Failed</dt>
              <dd>{data.failed}</dd>
            </div>
            <div>
              <dt>Model calls</dt>
              <dd>{data.calls}</dd>
            </div>
            {data.reported_tokens != null && (
              <div>
                <dt>Reported tokens</dt>
                <dd>{data.reported_tokens.toLocaleString()}</dd>
              </div>
            )}
            {data.estimated_tokens != null && (
              <div>
                <dt>Estimated tokens</dt>
                <dd>{data.estimated_tokens.toLocaleString()}</dd>
              </div>
            )}
            {data.context_window != null && (
              <div>
                <dt>Model context</dt>
                <dd>
                  {data.context_mode === 'auto' ? 'Auto' : 'Custom'} ·{' '}
                  {data.context_window.toLocaleString()} tokens
                </dd>
              </div>
            )}
            {data.max_output_tokens != null && (
              <div>
                <dt>Max output</dt>
                <dd>{data.max_output_tokens.toLocaleString()} tokens</dd>
              </div>
            )}
          </dl>
          {data.recent.length ? (
            <ul className="deployment-activity-rows">
              {data.recent.map((item) => (
                <li key={item.id}>
                  <span>
                    <strong>{sources[item.source] ?? sources.app}</strong>
                    {(item.models.length > 1 || item.models.some((id) => id !== model)) && (
                      <small>{item.models.join(', ')}</small>
                    )}
                  </span>
                  <time dateTime={item.at}>
                    {new Date(item.at).toLocaleString([], {
                      dateStyle: 'short',
                      timeStyle: 'short',
                    })}
                  </time>
                  <Badge
                    tone={
                      item.status === 'completed'
                        ? 'lime'
                        : item.status === 'failed'
                          ? 'rose'
                          : 'neutral'
                    }
                  >
                    {outcomes[item.status] ?? 'Recorded'}
                  </Badge>
                </li>
              ))}
            </ul>
          ) : (
            <p className="footnote">No recent requests are attributed to this deployment yet.</p>
          )}
          {data.unknown_calls > 0 && (
            <p className="footnote">
              Token counts are unavailable for {data.unknown_calls} model{' '}
              {data.unknown_calls === 1 ? 'call' : 'calls'}.
            </p>
          )}
        </div>
      ) : null}
    </details>
  );
}

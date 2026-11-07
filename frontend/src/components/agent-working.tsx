import { useEffect, useState } from 'react';
import type { AgentActivity } from '../lib/types';

/** Request-level progress stays visible after individual tools have finished.
 * Tool events establish activity, not model tokens or an estimated finish time.
 */
export function AgentWorking({
  name,
  items,
  startedAt,
}: {
  name: string;
  items: AgentActivity[];
  startedAt?: number;
}) {
  const [mountedAt] = useState(Date.now);
  const [now, setNow] = useState(Date.now);
  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, []);
  const seconds = Math.max(0, Math.floor((now - (startedAt ?? mountedAt)) / 1000));
  const elapsed =
    seconds < 60
      ? `${seconds}s`
      : `${Math.floor(seconds / 60)}m ${String(seconds % 60).padStart(2, '0')}s`;
  const actions = items.filter((item) => item.type === 'activity');
  const running = actions.some((item) => item.status === 'running');
  const label = running
    ? `${name} is using tools`
    : actions.length
      ? `${name} is preparing your answer`
      : `${name} is working on your request`;
  return (
    <div className="agent-working">
      <div className="agent-working-heading">
        <span role="status" aria-live="polite">
          <i className="agent-working-glow" aria-hidden="true" />
          {label}
        </span>
        <time aria-live="off" aria-label={`Elapsed request time: ${elapsed}`}>
          {elapsed}
        </time>
      </div>
      <p>
        {actions.length && !running
          ? 'The tool steps have finished so far; the reply is still being prepared. More checks may follow.'
          : running
            ? 'Tool activity appears below. Your reply is not finished yet.'
            : 'Waiting for the agent’s reply. Tool activity will appear below when available.'}
      </p>
      {seconds >= 30 && (
        <small>Some models take longer between steps. You can stop this request at any time.</small>
      )}
    </div>
  );
}

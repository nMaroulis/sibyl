import { useState } from 'react';
import { Check, ChevronDown, Circle, LoaderCircle, Timer, X } from 'lucide-react';
import { useResource } from '../lib/hooks';
import type { AgentActivity } from '../lib/types';

export const mergeActivity = (items: AgentActivity[], next: AgentActivity) => {
  const id = (item: AgentActivity) => item.activity_id ?? item.event_id;
  return [...items.filter((item) => id(item) !== id(next)), next].slice(-12);
};

/** Render SDK-classified actions; approved/requested actions are not completed effects. */
export function AgentActivityTrail({ items }: { items: AgentActivity[] }) {
  const actions = items.filter((item) => item.type === 'tool' || item.type === 'consultation');
  return (
    <div className="agent-run-activity" aria-label="Agent activity" aria-live="polite">
      {actions.map((item) => (
        <span key={item.activity_id ?? item.event_id} data-status={item.status}>
          {item.status === 'started' ? (
            <LoaderCircle size={13} className="spin" />
          ) : item.status === 'completed' ? (
            <Check size={13} />
          ) : item.status === 'requested' ? (
            <Circle size={13} />
          ) : (
            <X size={13} />
          )}
          <strong>{item.agent_name?.replace(/^sibyl-/, '')}</strong>
          <span>
            {item.type === 'consultation' ? 'Consultation · ' : ''}
            {(item.name ?? item.summary).replace(/^sibyl-/, '').replaceAll('_', ' ')}
          </span>
          <small>{item.status === 'started' ? 'Working' : item.status}</small>
        </span>
      ))}
    </div>
  );
}

type Usage = {
  calls: number;
  reported_calls: number;
  estimated_calls: number;
  unknown_calls: number;
  reported: { total_tokens: number | null };
  estimated: { total_tokens: number | null };
  unpriced_calls: number;
};

type Details = {
  usage: { tree: Usage; root: Usage; children: Usage };
  calls: {
    agent: string;
    provider: string | null;
    model: string | null;
    latency_ms: number | null;
    input_tokens: number | null;
    output_tokens: number | null;
    total_tokens: number | null;
    estimated: boolean;
    source: string;
    cost: { total: number; currency: string; estimated: boolean } | null;
  }[];
  tools: {
    id: string;
    agent: string;
    tool: string;
    outcome: string;
    duration_seconds: number | null;
  }[];
};
const count = (value: number | null) => (value === null ? 'Unavailable' : value.toLocaleString());
const duration = (value: number | null) => (value === null ? '—' : `${value.toFixed(2)}s`);

/** Fetch the safe native summary on demand, without downloading prompts or raw chunks. */
export function AgentRunDetails({ runId }: { runId?: string }) {
  const [open, setOpen] = useState(false);
  const report = useResource<Details>(`/agents/runs/${runId}/summary`, 0, open && Boolean(runId));
  if (!runId) return null;
  const data = report.data;
  return (
    <details className="agent-run-details" onToggle={(event) => setOpen(event.currentTarget.open)}>
      <summary>
        <Timer size={13} /> Run details <ChevronDown size={13} />
      </summary>
      {open && (
        <div>
          {report.error ? (
            <p role="alert">
              {report.error}{' '}
              <button className="text-link" onClick={report.retry}>
                Try reading again
              </button>
            </p>
          ) : !data ? (
            <p>Loading run details…</p>
          ) : (
            <>
              <p className="footnote">
                {data.calls.length ? (
                  <>
                    {data.usage.tree.calls} model calls
                    {data.usage.tree.reported_calls > 0 &&
                      ` · ${count(data.usage.tree.reported.total_tokens)} provider-reported tokens (${data.usage.tree.reported_calls} calls)`}
                    {data.usage.tree.estimated_calls > 0 &&
                      ` · ${count(data.usage.tree.estimated.total_tokens)} estimated tokens (${data.usage.tree.estimated_calls} calls)`}
                    {data.usage.tree.unknown_calls > 0 &&
                      ` · Usage unavailable for ${data.usage.tree.unknown_calls} calls`}
                    {' · '}
                    {data.usage.root.calls} root / {data.usage.children.calls} delegated calls
                  </>
                ) : (
                  'No completed model calls were recorded.'
                )}
              </p>
              {data.tools.length > 0 && (
                <ul className="agent-run-tools">
                  {data.tools.map((tool) => (
                    <li key={tool.id}>
                      {tool.outcome === 'completed' ? <Check size={12} /> : <Circle size={12} />}
                      <span>
                        {tool.agent?.replace(/^sibyl-/, '')} · {tool.tool.replaceAll('_', ' ')}
                      </span>
                      <small>
                        {tool.outcome} · {duration(tool.duration_seconds)}
                      </small>
                    </li>
                  ))}
                </ul>
              )}
              {data.calls.length > 0 && (
                <div className="agent-run-calls">
                  {data.calls.map((call, i) => (
                    <section key={i}>
                      <strong>
                        {call.agent?.replace(/^sibyl-/, '')}{' '}
                        <small>
                          {call.provider || 'Unknown provider'} · {call.model || 'Unknown model'}
                        </small>
                      </strong>
                      <span>
                        Input {count(call.input_tokens)} · Output {count(call.output_tokens)} ·{' '}
                        {call.input_tokens === null &&
                        call.output_tokens === null &&
                        call.total_tokens === null
                          ? 'Usage unavailable'
                          : call.estimated
                            ? 'Estimated'
                            : 'Provider reported'}{' '}
                        · {duration(call.latency_ms === null ? null : call.latency_ms / 1000)}
                      </span>
                      <span>
                        {call.cost
                          ? `${call.cost.estimated ? 'Estimated cost' : 'Reported cost'}: ${call.cost.total.toLocaleString(undefined, { maximumFractionDigits: 8 })} ${call.cost.currency}`
                          : 'Cost unavailable'}
                      </span>
                    </section>
                  ))}
                </div>
              )}
              <p className="footnote">
                Token estimates are not billing records. Costs appear only when available in the
                native provider metrics.
              </p>
            </>
          )}
        </div>
      )}
    </details>
  );
}

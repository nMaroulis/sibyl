import { ArrowUpRight, Braces, Sparkles } from 'lucide-react';
import { AgentButton } from '../components/agents';
import { Badge, ErrorState, Loading, PageTitle, Panel } from '../components/ui';
import { useResource } from '../lib/hooks';
import type { Agent, ModuleId } from '../lib/types';

/** A directory of independent specialists; conversations live over the current page. */
export function Oracle() {
  const agents = useResource<Agent[]>('/agents');
  return (
    <>
      <PageTitle
        title="Module agents"
        description="A dedicated specialist for each part of your workspace."
        action={
          <Badge tone="purple">
            <Sparkles size={12} />
            Powered by ProtoLink
          </Badge>
        }
      />
      <div className="agent-directory-note">
        <Sparkles size={18} />
        <p>
          Use the Ask button inside any module to talk to its agent in place. Each agent has its own
          instructions and read-only tools.
        </p>
      </div>
      {agents.loading ? (
        <Loading />
      ) : agents.error ? (
        <ErrorState message={agents.error} retry={agents.retry} />
      ) : (
        <div className="agent-directory-grid">
          {agents.data?.map((agent) => (
            <Panel className="agent-directory-card" key={agent.id}>
              <div className="agent-directory-card-top">
                <span className="agent-avatar">
                  <Sparkles size={21} />
                </span>
                <Badge tone="purple">{agent.mode === 'llm' ? agent.provider : 'Tool mode'}</Badge>
              </div>
              <h2>{agent.name}</h2>
              <p>{agent.description}</p>
              <div className="agent-directory-tool">
                <Braces size={13} />
                <code>{agent.tool}</code>
              </div>
              <AgentButton module={agent.id as ModuleId} />
              <small>
                ProtoLink agent
                <ArrowUpRight size={11} />
              </small>
            </Panel>
          ))}
        </div>
      )}
    </>
  );
}

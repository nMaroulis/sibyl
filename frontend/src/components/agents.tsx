import { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react';
import type { ReactNode } from 'react';
import { ArrowUp, ArrowUpRight, Braces, History, Plus, Sparkles, Square } from 'lucide-react';
import { Badge, ErrorState, Modal } from './ui';
import { postStream } from '../lib/api';
import { AgentActivityTrail, AgentRunDetails, mergeActivity } from './agent-run';
import { useResource } from '../lib/hooks';
import type { Agent, AgentActivity, AgentContext, AgentReply, ModuleId, Run } from '../lib/types';

type Selection = { module: ModuleId; context: AgentContext };
type Thread = {
  replies: AgentReply[];
  draft: string;
  sessionId?: string;
  pending?: string;
  error?: string;
  activity?: AgentActivity[];
};
const emptyThread = (): Thread => ({ replies: [], draft: '' });
const names: Record<ModuleId, string> = {
  oracle: 'Oracle',
  accountant: 'Accountant',
  analyst: 'Analyst',
  broker: 'Broker',
  chronos: 'Chronos',
  reporter: 'Reporter',
  technician: 'Technician',
  wiki: 'Wiki',
  explorer: 'Explorer',
  stocks: 'Equity Analyst',
};
const prompts: Record<ModuleId, string[]> = {
  oracle: ['Summarize my portfolio.', 'Explain my largest concentration.'],
  accountant: [
    'Explain my allocation and concentration.',
    'How are paper and connected balances separated?',
  ],
  analyst: [
    'Explain the indicators for this market.',
    'What does the observed volatility tell me?',
  ],
  broker: [
    'Explain the selected strategy and parameters.',
    'Which simulation assumptions should I review?',
  ],
  chronos: [
    'Explain this baseline and its uncertainty.',
    'What assumptions does this forecast make?',
  ],
  reporter: ['Summarize the source material.', 'Which claims need more context?'],
  technician: ['Explain my connection status.', 'Which API permissions does Sibyl need?'],
  wiki: ['Explain this concept in simple terms.', 'How should I interpret RSI?'],
  explorer: ['Explain the recent Bitcoin blocks.', 'How do transaction confirmations work?'],
  stocks: ['Summarize the selected equity quote.', 'Explain the scope of this price history.'],
};
const AgentActions = createContext<(module: ModuleId, context?: AgentContext) => void>(() => {});

/** Stable identity keeps different markets and module conversations isolated. */
function threadKey(module: string, context: AgentContext) {
  return (
    module +
    ':' +
    JSON.stringify(context, (_key, value) =>
      value && typeof value === 'object' && !Array.isArray(value)
        ? Object.fromEntries(
            Object.entries(value)
              .filter(([, item]) => item !== null && item !== undefined)
              .sort(([a], [b]) => a.localeCompare(b)),
          )
        : value,
    )
  );
}

/** Open a module agent in place; no route changes or execution side effects. */
export function AgentButton({
  module,
  context = {},
  children,
  compact = false,
  className = '',
}: {
  module: ModuleId;
  context?: AgentContext;
  children?: ReactNode;
  compact?: boolean;
  className?: string;
}) {
  const open = useContext(AgentActions);
  return (
    <button
      type="button"
      className={`agent-trigger ${compact ? 'compact' : ''} ${className}`}
      aria-haspopup="dialog"
      onClick={() => open(module, context)}
    >
      <span className="agent-trigger-icon">
        <Sparkles size={15} aria-hidden="true" />
      </span>
      <span>{children ?? `Ask ${names[module]}`}</span>
      <ArrowUpRight size={13} className="agent-trigger-arrow" aria-hidden="true" />
    </button>
  );
}

/** Keep per-selection sessions and drafts alive when the page's agent dialog closes. */
export function AgentProvider({ children }: { children: ReactNode }) {
  const catalog = useResource<Agent[]>('/agents');
  const runs = useResource<Run[]>('/runs?kind=agent');
  const [active, setActive] = useState<Selection>();
  const [threads, setThreads] = useState<Record<string, Thread>>({});
  const threadsRef = useRef(threads);
  threadsRef.current = threads;
  const pending = useRef(new Set<string>());
  const controllers = useRef(new Map<string, AbortController>());
  useEffect(
    () => () => {
      controllers.current.forEach((controller) => controller.abort());
    },
    [],
  );
  const open = useCallback(
    (module: ModuleId, context: AgentContext = {}) => setActive({ module, context }),
    [],
  );
  const close = useCallback(() => setActive(undefined), []);
  const key = active ? threadKey(active.module, active.context) : '';
  const thread = threads[key] ?? emptyThread();
  const update = (target: string, patch: Partial<Thread>) =>
    setThreads((old) => ({ ...old, [target]: { ...(old[target] ?? emptyThread()), ...patch } }));
  const send = async (message: string) => {
    if (!active || !message.trim() || pending.current.has(key)) return;
    const selection = active,
      target = key;
    pending.current.add(target);
    const controller = new AbortController();
    controllers.current.set(target, controller);
    update(target, { pending: message, draft: '', error: '', activity: [] });
    try {
      const reply = await postStream<AgentReply>(
        '/agents/ask/stream',
        {
          module: selection.module,
          context: selection.context,
          message,
          session_id: threadsRef.current[target]?.sessionId,
        },
        (event) =>
          setThreads((old) => ({
            ...old,
            [target]: {
              ...(old[target] ?? emptyThread()),
              activity: mergeActivity(old[target]?.activity ?? [], event),
            },
          })),
        controller.signal,
      );
      setThreads((old) => ({
        ...old,
        [target]: {
          ...(old[target] ?? emptyThread()),
          replies: [...(old[target]?.replies ?? []), reply],
          sessionId: reply.session_id,
          pending: undefined,
          error: '',
        },
      }));
      runs.retry();
    } catch (reason) {
      update(target, {
        pending: undefined,
        draft: message,
        error: controller.signal.aborted
          ? 'Stopped waiting. Any completed answer remains in recent conversations.'
          : (reason as Error).message,
      });
      runs.retry();
    } finally {
      pending.current.delete(target);
      controllers.current.delete(target);
    }
  };
  const restore = (reply: AgentReply) => {
    if (!active || thread.pending) return;
    const context = reply.context ?? {};
    const target = threadKey(reply.module, context);
    const replies = (runs.data ?? [])
      .map((run) => ({ ...(run.payload as AgentReply), id: run.id, created_at: run.created_at }))
      .filter((item) => item.module === reply.module && item.session_id === reply.session_id)
      .reverse();
    setThreads((old) => ({
      ...old,
      [target]: { replies, draft: '', sessionId: reply.session_id },
    }));
    setActive({ module: reply.module as ModuleId, context });
  };
  return (
    <AgentActions.Provider value={open}>
      {children}
      {active && (
        <AgentDialog
          selection={active}
          agent={catalog.data?.find((item) => item.id === active.module)}
          catalogError={catalog.error}
          retry={catalog.retry}
          thread={thread}
          history={(runs.data ?? [])
            .map((run) => ({
              ...(run.payload as AgentReply),
              id: run.id,
              created_at: run.created_at,
            }))
            .filter((reply) => threadKey(reply.module, reply.context ?? {}) === key)
            .slice(0, 5)}
          onClose={close}
          onSend={send}
          onStop={() => controllers.current.get(key)?.abort()}
          onDraft={(draft) => update(key, { draft })}
          onReset={() => {
            if (!pending.current.has(key)) setThreads((old) => ({ ...old, [key]: emptyThread() }));
          }}
          onRestore={restore}
        />
      )}
    </AgentActions.Provider>
  );
}

function AgentDialog({
  selection,
  agent,
  catalogError,
  retry,
  thread,
  history,
  onClose,
  onSend,
  onDraft,
  onReset,
  onRestore,
  onStop,
}: {
  selection: Selection;
  agent?: Agent;
  catalogError: string;
  retry: () => void;
  thread: Thread;
  history: AgentReply[];
  onClose: () => void;
  onSend: (message: string) => void;
  onDraft: (value: string) => void;
  onReset: () => void;
  onRestore: (reply: AgentReply) => void;
  onStop: () => void;
}) {
  const body = useRef<HTMLDivElement>(null);
  const name = agent?.name ?? names[selection.module];
  const context = selection.context;
  useEffect(() => {
    const element = body.current;
    if (element)
      element.scrollTo({
        top: element.scrollHeight,
        behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches
          ? 'instant'
          : 'smooth',
      });
  }, [thread.replies.length, thread.pending]);
  return (
    <Modal
      title={`Ask ${name}`}
      onClose={onClose}
      className="agent-dialog"
      backdropClassName="agent-overlay"
      initialFocus="textarea"
    >
      <div className="agent-dialog-intro">
        <span className="agent-avatar">
          <Sparkles size={22} />
        </span>
        <div>
          <strong>{agent?.tagline ?? 'Your module specialist'}</strong>
          <p>{agent?.description ?? 'Loading module tools…'}</p>
        </div>
      </div>
      <div className="agent-toolbar">
        <div>
          <Badge tone="purple">
            {agent?.mode === 'tools'
              ? 'Tool mode'
              : agent?.model_ready === false
                ? 'Needs setup'
                : (agent?.provider ?? 'Loading…')}
          </Badge>
          <span>ProtoLink · read-only{agent?.model ? ` · ${agent.model}` : ''}</span>
        </div>
        <button className="text-button" onClick={onReset} disabled={!!thread.pending}>
          <Plus size={13} />
          New conversation
        </button>
      </div>
      <div className="agent-selection-context">
        <span>
          {context.parameters?.symbol ??
            context.symbol ??
            context.equity_symbol ??
            context.crypto_id?.split('-')[0].toUpperCase() ??
            (context.performance_view ? 'Retained market FIFO' : undefined) ??
            (context.funding_view ? 'Retained funding history' : undefined) ??
            (context.transfer_view ? 'Transfer reconciliation' : undefined) ??
            (context.news_mode
              ? context.news_mode === 'live'
                ? 'Public news'
                : 'Demo briefings'
              : undefined) ??
            'Module workspace'}
        </span>
        {context.parameters && (
          <span>
            {context.parameters.strategy} · {context.parameters.candles} candles ·{' '}
            {context.parameters.capital.toLocaleString()} {context.parameters.symbol.split('/')[1]}{' '}
            · {context.parameters.timeframe ?? '1d'}
          </span>
        )}
        {context.timeframe && (
          <span>
            {context.timeframe} · {context.limit ?? 180} candles
          </span>
        )}
        {context.job_id && <span>Run {context.job_id.slice(0, 8)}</span>}
        {context.horizon && <span>{context.horizon}-day baseline</span>}
        {context.article_id && <span>Selected story</span>}
        {context.news_asset && <span>Mentions {context.news_asset}</span>}
        {context.news_publisher && <span>{context.news_publisher}</span>}
        {context.news_sentiment && <span>{context.news_sentiment} wording</span>}
        {context.news_days !== undefined && (
          <span>{context.news_days ? `${context.news_days}-day window` : 'All retained'}</span>
        )}
        {context.query && <span>Search: {context.query}</span>}
        {context.performance_view && (
          <span>
            {context.performance_example
              ? context.performance_transfer_example
                ? context.performance_fee_example
                  ? 'Transfer fee allocation example'
                  : 'Transfer carryover example'
                : 'Example calculation'
              : context.performance_environment || 'All environments'}
          </span>
        )}
        {context.funding_view && (
          <span>
            {context.funding_example
              ? 'Example movements'
              : `${context.funding_asset || 'All assets'} · ${context.funding_environment || 'All environments'}`}
          </span>
        )}
        {context.transfer_view && (
          <span>
            {context.transfer_example
              ? 'Example reconciliation'
              : `${context.funding_asset || 'All assets'} · ${context.funding_environment || 'All environments'}`}
          </span>
        )}
      </div>
      <div className="agent-dialog-body" ref={body}>
        {catalogError && <ErrorState message={catalogError} retry={retry} />}
        {!thread.replies.length && !thread.pending && (
          <div className="agent-dialog-welcome">
            <span className="agent-welcome-symbol">
              <Sparkles size={27} />
            </span>
            <h3>Stay here. Ask away.</h3>
            <p>
              {context.transfer_view ||
              context.funding_view ||
              context.performance_view ||
              context.parameters ||
              context.job_id ||
              context.symbol ||
              context.equity_symbol ||
              context.article_id ||
              context.query
                ? 'Your page selection is included. The agent reads its own module tools for the evidence.'
                : 'Ask this module’s specialist without leaving your workspace.'}
            </p>
            <div className="agent-suggestions">
              {(context.transfer_view
                ? [
                    'Explain these suggestions and possible ambiguities.',
                    'Which cost-basis gaps remain after a transfer is confirmed?',
                  ]
                : context.funding_view
                  ? [
                      'Summarize these movements and their coverage.',
                      'Explain fees, internal transfers and pending records.',
                    ]
                  : context.performance_view
                    ? [
                        'Explain the matched results and missing coverage.',
                        'How do fees and opening inventory affect this calculation?',
                      ]
                    : context.crypto_id
                      ? [
                          'Summarize this project and its history.',
                          'Explain its network and token supply.',
                        ]
                      : prompts[selection.module]
              ).map((prompt) => (
                <button key={prompt} onClick={() => onSend(prompt)} disabled={!agent}>
                  <span>{prompt}</span>
                  <ArrowUpRight size={14} />
                </button>
              ))}
            </div>
          </div>
        )}
        {thread.replies.map((reply) => (
          <div className="agent-dialog-turn" key={reply.id}>
            <div className="agent-question">{reply.question}</div>
            <div className="agent-answer">
              <div className="agent-answer-meta">
                <Sparkles size={14} />
                <strong>{name}</strong>
                <Badge tone="purple">
                  {reply.mode === 'tools' ? 'Tool snapshot' : reply.provider}
                </Badge>
              </div>
              <p>{reply.answer}</p>
              {reply.mode === 'llm' && reply.observations?.length === 0 ? (
                <small className="muted">Answered without reading workspace data.</small>
              ) : (
                <details className="evidence-details">
                  <summary>
                    <Braces size={13} />
                    Inspect{' '}
                    {reply.observations && reply.observations.length > 1
                      ? `${reply.observations.length} tool observations`
                      : `${reply.tool} evidence`}
                  </summary>
                  <pre>
                    {JSON.stringify(
                      reply.observations && reply.observations.length > 1
                        ? reply.observations
                        : reply.evidence,
                      null,
                      2,
                    )}
                  </pre>
                </details>
              )}
              <small>
                {new Date(reply.created_at).toLocaleTimeString()} · Saved locally
                {reply.mode !== 'tools' && reply.model ? ` · ${reply.model}` : ''}
              </small>
              <AgentRunDetails runId={reply.run_id} />
            </div>
          </div>
        ))}
        {thread.pending && (
          <div className="agent-dialog-turn">
            <div className="agent-question">{thread.pending}</div>
            <div className="agent-thinking" role="status">
              <AgentActivityTrail items={thread.activity ?? []} />
              <button className="button" onClick={onStop}>
                <Square size={12} /> Stop
              </button>
            </div>
          </div>
        )}
        {thread.error && (
          <div className="form-error" role="alert">
            {thread.error}
          </div>
        )}
      </div>
      {!!history.length && (
        <details className="agent-dialog-history">
          <summary>
            <History size={13} />
            Recent conversations in this context
          </summary>
          {history.map((reply) => (
            <button key={reply.id} disabled={!!thread.pending} onClick={() => onRestore(reply)}>
              <span>{reply.question}</span>
              <small>{new Date(reply.created_at).toLocaleDateString()}</small>
            </button>
          ))}
        </details>
      )}
      <form
        className="agent-dialog-composer"
        onSubmit={(event) => {
          event.preventDefault();
          onSend(thread.draft);
        }}
      >
        <textarea
          aria-label={`Message ${name}`}
          placeholder={`Ask ${name} about this page…`}
          maxLength={4000}
          rows={2}
          value={thread.draft}
          onChange={(event) => onDraft(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) {
              event.preventDefault();
              onSend(thread.draft);
            }
          }}
        />
        <div>
          <span>
            {agent?.model_ready === false && agent.mode !== 'tools'
              ? `${agent.model_reason} Open AI model settings to update this agent.`
              : agent?.mode === 'llm'
                ? `Evidence and messages are sent to ${agent.provider}.`
                : 'Tool mode returns factual snapshots. Configure a model for conversation.'}
          </span>
          <button
            type="submit"
            className="agent-send"
            aria-label="Send message"
            disabled={!thread.draft.trim() || !!thread.pending || !agent}
          >
            <ArrowUp size={18} />
          </button>
        </div>
      </form>
    </Modal>
  );
}

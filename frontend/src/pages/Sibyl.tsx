import { useEffect, useRef, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import {
  ArrowUp,
  ArrowUpRight,
  Check,
  ChevronDown,
  History,
  LoaderCircle,
  MessageCircle,
  Plus,
  ClipboardList,
  Trash2,
} from 'lucide-react';
import { SibylProgress, SibylRequestHistory, activeRequest } from '../components/sibyl-activity';
import type { SibylActivity, Consultation } from '../components/sibyl-activity';
import { SibylMark } from '../components/sibyl-mark';
import { Badge, ErrorState, Loading, Modal } from '../components/ui';
import { api, post } from '../lib/api';
import { useResource } from '../lib/hooks';
import type { Agent } from '../lib/types';

type Status = {
  ready: boolean;
  network_ready: boolean;
  reason: string;
  provider: string;
  model: string;
  simulated: boolean;
  specialists: number;
};
type Reply = {
  id: string;
  session_id: string;
  question: string;
  answer: string;
  provider: string;
  model: string;
  mode: string;
  created_at: string;
  delegations: Consultation[];
};
type Chat = { id: string; title: string; turns: Reply[]; pending?: boolean };
const starters = [
  {
    label: 'See the bigger picture',
    text: 'Help me understand my portfolio allocation and the risks I should pay attention to.',
    hint: 'Account & perspective',
  },
  {
    label: 'Connect the dots',
    text: 'Compare the latest Bitcoin market indicators with the available Bitcoin news. Explain what is known and what is uncertain.',
    hint: 'Markets & news',
  },
  {
    label: 'Think through a strategy',
    text: 'Help me understand the strategies available in this workspace and their paper trading limitations.',
    hint: 'Strategies & research',
  },
];

/** Sibyl chooses collaborators on the backend; the interface displays actual consultations. */
export function Sibyl() {
  const status = useResource<Status>('/sibyl', 30000);
  const catalog = useResource<Agent[]>('/agents');
  const chats = useResource<Chat[]>('/sibyl/conversations');
  const [params, setParams] = useSearchParams();
  const session = params.get('chat') ?? '';
  const conversation = useResource<Chat>(`/sibyl/conversations/${session}`, 0, Boolean(session));
  const [draft, setDraft] = useState('');
  const [pending, setPending] = useState('');
  const [error, setError] = useState('');
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [following, setFollowing] = useState(false);
  const [stopping, setStopping] = useState(false);
  const [requestId, setRequestId] = useState('');
  const activity = useResource<SibylActivity | null>(
    `/sibyl/conversations/${session}/activity`,
    following || pending ? 1000 : 0,
    Boolean(session),
  );
  const currentActivity = activity.data?.session_id === session ? activity.data : undefined;
  const visibleActivity =
    pending && currentActivity?.id !== requestId ? undefined : currentActivity;
  const stoppableId = activeRequest(visibleActivity) ? visibleActivity?.id : undefined;
  useEffect(() => {
    setFollowing(activeRequest(currentActivity));
  }, [currentActivity?.id, currentActivity?.status]);
  useEffect(() => {
    if (currentActivity && !activeRequest(currentActivity)) {
      conversation.retry();
      chats.retry();
    }
  }, [currentActivity?.id, currentActivity?.status, conversation.retry, chats.retry]);
  const [latest, setLatest] = useState<Reply>();
  const busy = useRef(false);
  const end = useRef<HTMLDivElement>(null);
  const input = useRef<HTMLTextAreaElement>(null);
  const turns = [...(conversation.data?.id === session ? conversation.data.turns : [])];
  if (latest?.session_id === session && !turns.some((turn) => turn.id === latest.id))
    turns.push(latest);
  useEffect(() => {
    if (turns.length || pending)
      end.current?.scrollIntoView({
        behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth',
        block: 'nearest',
      });
  }, [turns.length, pending]);
  const ready = Boolean(status.data?.ready);
  const working = Boolean(
    pending ||
    activeRequest(currentActivity) ||
    (conversation.data?.id === session && conversation.data.pending && !currentActivity),
  );
  const send = async (message: string) => {
    if (!ready || busy.current || working || !message.trim()) return;
    busy.current = true;
    setPending(message.trim());
    setDraft('');
    setError('');
    const nextRequest = crypto.randomUUID().replaceAll('-', '');
    setRequestId(nextRequest);
    try {
      let target = session;
      if (!target) {
        const chat = await post<Chat>('/sibyl/conversations');
        target = chat.id;
        setParams({ chat: target });
      }
      const reply = await post<
        Reply | { status: 'cancelled'; request_id: string; session_id: string }
      >('/sibyl/ask', {
        message: message.trim(),
        session_id: target,
        request_id: nextRequest,
      });
      if ('status' in reply && reply.status === 'cancelled') setDraft(message);
      else setLatest(reply as Reply);
      conversation.retry();
      chats.retry();
    } catch (reason) {
      setError((reason as Error).message);
      setDraft(message);
    } finally {
      busy.current = false;
      setPending('');
      setStopping(false);
      activity.retry();
      conversation.retry();
    }
  };
  const stop = async () => {
    const id = stoppableId;
    if (!session || !id || stopping) return;
    setStopping(true);
    try {
      await post(`/sibyl/conversations/${session}/cancel`, { request_id: id });
    } catch (reason) {
      setError((reason as Error).message);
    } finally {
      activity.retry();
      conversation.retry();
      setStopping(false);
    }
  };
  const newChat = () => {
    if (!busy.current && !working) {
      setParams({});
      setDraft('');
      setError('');
      setLatest(undefined);
      setDeleteOpen(false);
      setFollowing(false);
      setStopping(false);
      setRequestId('');
      input.current?.focus();
    }
  };
  const remove = async () => {
    if (!session || busy.current || working) return;
    try {
      await api(`/sibyl/conversations/${session}`, { method: 'DELETE' });
      newChat();
      chats.retry();
    } catch (reason) {
      setError((reason as Error).message);
    }
  };
  return (
    <div className="sibyl-page">
      {historyOpen && session && (
        <Modal
          title="Request history"
          className="sibyl-history-dialog"
          onClose={() => setHistoryOpen(false)}
        >
          <SibylRequestHistory
            session={session}
            onUseQuestion={(question) => {
              setDraft(question);
              setHistoryOpen(false);
              input.current?.focus();
            }}
          />
        </Modal>
      )}
      {deleteOpen && (
        <Modal title="Delete this conversation?" onClose={() => setDeleteOpen(false)}>
          <p className="muted">
            This permanently removes the chat and its consultation evidence from this workspace.
            Separately saved specialist runs are retained.
          </p>
          <div className="form-actions">
            <button className="button" onClick={() => setDeleteOpen(false)}>
              Keep conversation
            </button>
            <button className="button danger" onClick={() => void remove()} disabled={working}>
              Delete conversation
            </button>
          </div>
        </Modal>
      )}

      <header className="sibyl-page-heading">
        <div className="sibyl-wordmark">
          <SibylMark small />
          <div>
            <h1>Sibyl</h1>
            <p>Your connected intelligence</p>
          </div>
        </div>
        <div className="sibyl-page-actions">
          <Link to="/settings?tab=messaging" className="button">
            <MessageCircle size={15} />
            <span>Messaging</span>
          </Link>
          <button className="button" onClick={newChat} disabled={working}>
            <Plus size={15} />
            New chat
          </button>
        </div>
      </header>
      {status.error && <ErrorState message={status.error} retry={status.retry} />}
      <div className="sibyl-room">
        <section className="sibyl-conversation" aria-label="Conversation with Sibyl">
          <div className="sibyl-conversation-toolbar">
            <span>
              <span className={`sibyl-presence ${ready ? 'ready' : ''}`} />
              {status.loading
                ? 'Connecting…'
                : ready
                  ? status.data?.simulated
                    ? 'Simulated model'
                    : 'Ready to think with you'
                  : 'Model setup needed'}
            </span>
            <div className="sibyl-chat-picker">
              <History size={14} />
              <select
                aria-label="Saved conversations"
                value={session}
                disabled={working}
                onChange={(event) => {
                  setParams(event.target.value ? { chat: event.target.value } : {});
                  setError('');
                  setDraft('');
                }}
              >
                <option value="">New conversation</option>
                {session && !chats.data?.some((chat) => chat.id === session) && (
                  <option value={session}>Current conversation</option>
                )}
                {chats.data?.map((chat) => (
                  <option key={chat.id} value={chat.id}>
                    {chat.title}
                  </option>
                ))}
              </select>
              {session && (
                <button
                  className="icon-button"
                  aria-label="Request history"
                  title="Request history"
                  onClick={() => setHistoryOpen(true)}
                >
                  <ClipboardList size={14} />
                </button>
              )}
              {session && (
                <button
                  className="icon-button"
                  aria-label="Delete conversation"
                  title="Delete this local conversation"
                  onClick={() => setDeleteOpen(true)}
                  disabled={working}
                >
                  <Trash2 size={14} />
                </button>
              )}
            </div>
          </div>
          <div className={`sibyl-chat-scroll ${turns.length || working ? 'has-messages' : ''}`}>
            {session && conversation.loading ? (
              <Loading />
            ) : conversation.error ? (
              <ErrorState message={conversation.error} retry={conversation.retry} />
            ) : !turns.length && !working ? (
              <div className="sibyl-welcome">
                <div className="sibyl-halo">
                  <SibylMark />
                </div>
                <span className="sibyl-eyebrow">A fresh perspective, together.</span>
                <h2>
                  Your workspace.
                  <br />
                  <span>A world of connections.</span>
                </h2>
                <p>
                  One conversation. The right specialists.
                  <br />
                  Ask Sibyl to bring the pieces together.
                </p>
                {ready && (
                  <div className="sibyl-starters">
                    {starters.map((starter) => (
                      <button
                        key={starter.label}
                        disabled={!ready}
                        onClick={() => {
                          setDraft(starter.text);
                          input.current?.focus();
                        }}
                      >
                        <span>{starter.hint}</span>
                        <strong>
                          {starter.label}
                          <ArrowUpRight size={14} />
                        </strong>
                      </button>
                    ))}
                  </div>
                )}
              </div>
            ) : (
              <div
                className="sibyl-messages"
                role="log"
                aria-label="Sibyl messages"
                aria-live="polite"
              >
                {turns.map((turn) => (
                  <div className="sibyl-turn" key={turn.id}>
                    <div className="sibyl-user-message">
                      <span>You</span>
                      <p>{turn.question}</p>
                    </div>
                    <div className="sibyl-answer">
                      <div className="sibyl-answer-label">
                        <SibylMark small />
                        <strong>Sibyl</strong>
                        <span>
                          {turn.provider}
                          {turn.model ? ` · ${turn.model}` : ''}
                          {turn.mode === 'mock' ? ' · Simulated' : ''}
                        </span>
                      </div>
                      <div className="sibyl-answer-text">{turn.answer}</div>
                      {turn.delegations.length > 0 && (
                        <details className="sibyl-consultations">
                          <summary>
                            <span className="sibyl-mini-avatars">
                              {Array.from(new Set(turn.delegations.map((item) => item.name))).map(
                                (name) => (
                                  <span key={name}>{name[0]}</span>
                                ),
                              )}
                            </span>
                            <span>
                              {
                                turn.delegations.filter((item) => item.status === 'completed')
                                  .length
                              }{' '}
                              of {turn.delegations.length} consultations completed
                            </span>
                            <ChevronDown size={14} />
                          </summary>
                          <div>
                            {turn.delegations.map((item, i) => (
                              <section key={i}>
                                <h4>
                                  {item.status === 'completed' && <Check size={13} />}
                                  {item.name}
                                  <Badge>
                                    {item.status === 'completed' ? 'Consulted' : 'Unavailable'}
                                  </Badge>
                                </h4>
                                <p className="footnote">
                                  {item.mode === 'tools'
                                    ? 'Direct tool call'
                                    : [item.provider, item.model].filter(Boolean).join(' · ')}
                                  {item.provider === 'mock' ? ' · Simulated' : ''}
                                </p>
                                <p className="muted">{item.question}</p>
                                <p>{item.answer || item.error}</p>
                                {item.evidence !== undefined && (
                                  <details>
                                    <summary>Source observations</summary>
                                    <pre>{JSON.stringify(item.evidence, null, 2)}</pre>
                                  </details>
                                )}
                              </section>
                            ))}
                          </div>
                        </details>
                      )}
                    </div>
                  </div>
                ))}
                {working && (
                  <div className="sibyl-turn">
                    {(pending || currentActivity?.question) && (
                      <div className="sibyl-user-message">
                        <span>You</span>
                        <p>{pending || currentActivity?.question}</p>
                      </div>
                    )}
                    <SibylProgress
                      activity={visibleActivity}
                      stopping={stopping}
                      stop={session && stoppableId ? () => void stop() : undefined}
                    />
                  </div>
                )}
              </div>
            )}
            <div ref={end} />
          </div>
          <div className="sibyl-compose-area">
            {!working &&
              currentActivity &&
              ['cancelled', 'failed', 'interrupted'].includes(currentActivity.status) && (
                <div className="sibyl-request-outcome" role="status">
                  <span>
                    {currentActivity.status === 'cancelled'
                      ? 'Request stopped.'
                      : currentActivity.status === 'interrupted'
                        ? 'The application restarted before this answer finished.'
                        : 'This request could not finish.'}{' '}
                    Completed consultations are kept in request history.
                  </span>
                  <button type="button" onClick={() => setHistoryOpen(true)}>
                    View history
                  </button>
                </div>
              )}
            {status.data && !ready && (
              <div className="sibyl-setup-note">
                <SibylMark small />
                <div>
                  <strong>Give Sibyl a model to think with</strong>
                  <p>{status.data.reason}</p>
                </div>
                <Link className="button primary" to="/settings?tab=models">
                  Set up AI
                  <ArrowUpRight size={14} />
                </Link>
              </div>
            )}
            {status.data?.simulated && (
              <p className="sibyl-model-note">
                Mock mode produces simulated replies. Choose an API or local model for real
                reasoning.
              </p>
            )}
            {error && (
              <div className="inline-alert" role="alert">
                {error}
              </div>
            )}
            {ready && (
              <form
                className="sibyl-composer"
                onSubmit={(event) => {
                  event.preventDefault();
                  void send(draft);
                }}
              >
                <textarea
                  ref={input}
                  aria-label="Message Sibyl"
                  placeholder={
                    ready
                      ? 'Ask anything about your workspace…'
                      : 'Connect an AI model to start a conversation'
                  }
                  value={draft}
                  maxLength={4000}
                  rows={2}
                  disabled={!ready || working || Boolean(session && conversation.error)}
                  onChange={(event) => setDraft(event.target.value)}
                  onKeyDown={(event) => {
                    if (
                      event.key === 'Enter' &&
                      !event.shiftKey &&
                      !event.nativeEvent.isComposing
                    ) {
                      event.preventDefault();
                      void send(draft);
                    }
                  }}
                />
                <div>
                  <span>
                    <SibylMark small />
                    {ready ? 'Made thoughtful by your specialists' : 'Powered by ProtoLink'}
                  </span>
                  <button
                    type="submit"
                    aria-label="Send to Sibyl"
                    disabled={
                      !ready || working || !draft.trim() || Boolean(session && conversation.error)
                    }
                  >
                    {working ? <LoaderCircle className="spin" size={18} /> : <ArrowUp size={20} />}
                  </button>
                </div>
              </form>
            )}
            <p className="sibyl-fineprint">
              Read-only assistance · Check sources and important details · Conversations stay in
              this workspace
            </p>
          </div>
        </section>
        <aside className="sibyl-team">
          <div className="sibyl-team-title">
            <span className="sibyl-eyebrow">In your corner</span>
            <Badge>{status.data?.specialists ?? 10} agents</Badge>
          </div>
          <h3>
            A little expertise.
            <br />A bigger picture.
          </h3>
          <p>Sibyl finds the right people for your question.</p>
          <div className="sibyl-team-list">
            {catalog.data?.map((agent) => (
              <div key={agent.id}>
                <span>{agent.name[0]}</span>
                <div>
                  <strong>{agent.name}</strong>
                  <small>{agent.tagline}</small>
                </div>
                <span
                  className={`sibyl-team-dot ${status.data?.network_ready ? 'online' : ''}`}
                  title={status.data?.network_ready ? 'Registered in ProtoLink' : 'Starting'}
                />
              </div>
            ))}
          </div>
          <Link className="text-link" to="/oracle">
            Meet your specialists
            <ArrowUpRight size={13} />
          </Link>
          <div className="sibyl-channel-note">
            <MessageCircle size={18} />
            <strong>Take the conversation with you.</strong>
            <p>WhatsApp, Telegram & more are on the way.</p>
            <Link to="/settings?tab=messaging">
              Explore channels
              <ArrowUpRight size={12} />
            </Link>
          </div>
        </aside>
      </div>
    </div>
  );
}

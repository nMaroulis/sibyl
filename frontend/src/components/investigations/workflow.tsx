import { useState } from 'react';
import { Check, MessageCircle, Play, ShieldCheck, X } from 'lucide-react';
import { post } from '../../lib/api';
import { Badge } from '../ui';
import type { ResearchRun } from './types';

export type NativeWorkflow = {
  status: string;
  message?: string;
  interruption: null | {
    kind: 'input' | 'approval' | 'yield';
    request_id: string;
    fingerprint: string;
    request: {
      question?: string;
      options?: string[];
      action?: { name: string; payload?: { arguments?: { title?: string; text?: string } } };
    };
  };
  uncertain_actions: { action_id: string; name: string; state: string }[];
};

/** Render native questions and the complete approved note; IDs only correlate responses. */
export function WorkflowControls({ run, onChanged }: { run: ResearchRun; onChanged: () => void }) {
  const [answer, setAnswer] = useState(''),
    [busy, setBusy] = useState(''),
    [error, setError] = useState('');
  const view = run.workflow,
    pending = view?.interruption;
  if (!run.durable) return null;
  if (run.status !== 'input_required')
    return (
      <p className="footnote">
        <ShieldCheck size={13} /> Native research checkpoints ·{' '}
        {run.status === 'running'
          ? 'Working through the next bounded research slice'
          : 'Retained execution evidence'}
      </p>
    );
  const request = pending?.request,
    note = request?.action?.payload?.arguments;
  const uncertain = !!view?.uncertain_actions?.length;
  const verifyNote = async (actionId: string) => {
    setBusy('verify');
    setError('');
    try {
      await post(
        `/investigations/${run.investigation_id}/runs/${run.id}/verify-note/${encodeURIComponent(actionId)}`,
      );
      onChanged();
    } catch (reason) {
      setError((reason as Error).message);
    } finally {
      setBusy('');
    }
  };
  const act = async (kind: 'continue' | 'answer' | 'approve' | 'reject') => {
    setBusy(kind);
    setError('');
    try {
      await post(`/investigations/${run.investigation_id}/runs/${run.id}/resume`, {
        kind,
        request_id: pending?.request_id ?? null,
        fingerprint: pending?.fingerprint ?? null,
        ...(kind === 'answer' ? { answer } : {}),
      });
      setAnswer('');
      onChanged();
    } catch (reason) {
      setError((reason as Error).message);
    } finally {
      setBusy('');
    }
  };
  return (
    <section className="workflow-waiting" aria-live="polite">
      <div className="inline-actions">
        <Badge tone="lavender">Progress saved</Badge>
        <strong>
          {pending?.kind === 'approval'
            ? 'Review a local research note'
            : pending?.kind === 'input'
              ? 'Sibyl needs your input'
              : 'Ready for the next research slice'}
        </strong>
      </div>
      {view?.message && <p>{view.message}</p>}
      {pending?.kind === 'input' && (
        <form
          className="form"
          onSubmit={(event) => {
            event.preventDefault();
            act('answer');
          }}
        >
          <p>{request?.question}</p>
          {!!request?.options?.length && (
            <div className="inline-actions">
              {request.options.map((option) => (
                <button
                  className="button secondary tiny"
                  type="button"
                  key={option}
                  onClick={() => setAnswer(option)}
                >
                  {option}
                </button>
              ))}
            </div>
          )}
          <label>
            Your answer
            <textarea
              value={answer}
              maxLength={4000}
              rows={3}
              onChange={(event) => setAnswer(event.target.value)}
              required
            />
          </label>
          <button className="button primary tiny" disabled={!!busy || !answer.trim() || uncertain}>
            <MessageCircle size={14} />
            {busy === 'answer' ? 'Continuing…' : 'Answer & continue'}
          </button>
        </form>
      )}
      {pending?.kind === 'approval' && (
        <>
          <p>
            This saves the exact AI draft below to your local research library. It does not place
            orders or send a message.
          </p>
          <article className="workflow-note-preview">
            <h3>{note?.title}</h3>
            <p>{note?.text}</p>
          </article>
          <div className="inline-actions">
            <button
              className="button primary tiny"
              disabled={
                !!busy ||
                uncertain ||
                request?.action?.name !== 'save_research_note' ||
                !note?.title ||
                !note?.text
              }
              onClick={() => act('approve')}
            >
              <Check size={14} />
              {busy === 'approve' ? 'Continuing…' : 'Approve this local note'}
            </button>
            <button
              className="button secondary tiny"
              disabled={!!busy || uncertain}
              onClick={() => act('reject')}
            >
              <X size={14} />
              Decline & stop
            </button>
          </div>
        </>
      )}
      {(!pending || pending.kind === 'yield') && (
        <>
          <p>
            Sibyl retained its work and model selections. Continue explicitly with the remaining
            native budget; completed actions are not rerun.
          </p>
          <button
            className="button primary tiny"
            disabled={!!busy || uncertain || view?.status === 'incompatible'}
            onClick={() => act('continue')}
          >
            <Play size={14} />
            {busy === 'continue' ? 'Continuing…' : 'Continue research'}
          </button>
        </>
      )}
      {uncertain &&
        view?.uncertain_actions
          .filter((action) => action.name === 'save_research_note')
          .map((action) => (
            <button
              className="button secondary tiny"
              disabled={!!busy}
              key={action.action_id}
              onClick={() => verifyNote(action.action_id)}
            >
              Verify exact saved note
            </button>
          ))}
      {uncertain && (
        <p className="monitor-notice">
          A native action has an uncertain result. Inspect the saved research library before
          continuing; Sibyl will not replay it automatically.
        </p>
      )}
      {error && (
        <p className="form-error" role="alert">
          {error}
        </p>
      )}
      <p className="footnote">
        You can leave this page or restart between waits. Questions and note approvals are separate;
        an answer is not permission for another action.
      </p>
    </section>
  );
}

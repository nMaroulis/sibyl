import { useDeferredValue } from 'react';
import { ChatMarkdown } from './chat-markdown';

/** Reparse accumulated Markdown, including open fences/tables, without injecting HTML. */
export function StreamingAnswer({ text }: { text: string }) {
  const markdown = useDeferredValue(text);
  if (!text) return null;
  return (
    <div
      className="agent-stream-answer"
      aria-label="Reply in progress"
      aria-busy="true"
      aria-live="off"
    >
      <ChatMarkdown>{markdown}</ChatMarkdown>
      <span className="agent-stream-cursor" aria-hidden="true" />
    </div>
  );
}

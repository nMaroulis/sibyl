import { useState } from 'react';
import { ChevronRight, List, Trash2 } from 'lucide-react';
import { api, refresh } from '../../lib/api';
import { useResource } from '../../lib/hooks';
import { ErrorState, Loading, Modal, useToast } from '../ui';
import type { ChannelActivityEvent } from './channel-activity';
import { MessageLogDialog } from './message-log';

export type MessageLogStorage = { entries: number; bytes: number; revision: string | null };

const PAGE_SIZE = 20;

function bytesLabel(bytes: number) {
  if (bytes < 1024) return `${bytes.toLocaleString()} B`;
  if (bytes < 1024 ** 2) return `${(bytes / 1024).toFixed(1)} KiB`;
  return `${(bytes / 1024 ** 2).toFixed(1)} MiB`;
}

export function ChannelLogs({
  channel,
  name,
  storage,
}: {
  channel: string;
  name: string;
  storage: MessageLogStorage;
}) {
  const [view, setView] = useState<'list' | 'clear'>();
  const [message, setMessage] = useState<string>();
  const [offset, setOffset] = useState(0);
  const [clearing, setClearing] = useState(false);
  const [clearError, setClearError] = useState('');
  const toast = useToast();
  const base = `/settings/messaging/channels/${encodeURIComponent(channel)}/logs`;
  const list = useResource<MessageLogStorage & { items: ChannelActivityEvent[] }>(
    `${base}?limit=${PAGE_SIZE}&offset=${offset}`,
    0,
    view === 'list' && !message,
  );
  const clear = async () => {
    if (!storage.revision || clearing) return;
    setClearing(true);
    setClearError('');
    try {
      const result = await api<MessageLogStorage & { cleared: number }>(
        `${base}?revision=${encodeURIComponent(storage.revision)}`,
        { method: 'DELETE' },
      );
      refresh();
      setView(undefined);
      toast(
        result.cleared === 0
          ? 'No settled message logs to clear.'
          : `Cleared ${result.cleared} message ${result.cleared === 1 ? 'log' : 'logs'}.`,
      );
    } catch (reason) {
      setClearError((reason as Error).message);
    } finally {
      setClearing(false);
    }
  };
  const size = `${storage.entries.toLocaleString()} ${storage.entries === 1 ? 'entry' : 'entries'} · ${bytesLabel(storage.bytes)} in DB`;
  return (
    <>
      <div className="channel-log-toolbar">
        <button
          type="button"
          className="text-button"
          onClick={() => {
            setOffset(0);
            setView('list');
          }}
        >
          <List size={14} aria-hidden="true" /> Message logs
        </button>
        <small>{size}</small>
        <button
          type="button"
          className="text-button channel-log-clear"
          disabled={!storage.entries || !storage.revision || clearing}
          onClick={() => {
            setClearError('');
            setView('clear');
          }}
        >
          <Trash2 size={13} aria-hidden="true" /> Clear logs
        </button>
      </div>
      {view === 'list' &&
        (message ? (
          <MessageLogDialog
            channel={channel}
            message={message}
            close={() => setMessage(undefined)}
          />
        ) : (
          <Modal
            title={`${name} message logs`}
            className="channel-message-log"
            onClose={() => setView(undefined)}
          >
            {list.loading ? (
              <Loading />
            ) : list.error ? (
              <ErrorState message={list.error} retry={list.retry} />
            ) : list.data ? (
              <>
                {list.data.items.length ? (
                  <ul className="channel-log-history">
                    {list.data.items.map((event) => (
                      <li key={event.id}>
                        <button type="button" onClick={() => setMessage(event.id)}>
                          <span>{new Date(event.at * 1000).toLocaleString()}</span>
                          <span>{event.state === 'sent' ? 'Provider accepted' : event.state}</span>
                          <ChevronRight size={14} aria-hidden="true" />
                        </button>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="footnote">No message logs for this page.</p>
                )}
                {(offset > 0 || offset + PAGE_SIZE < list.data.entries) && (
                  <div className="inline-actions channel-log-page">
                    <button
                      type="button"
                      className="button secondary tiny"
                      disabled={offset === 0}
                      onClick={() => setOffset(offset - PAGE_SIZE)}
                    >
                      Newer
                    </button>
                    <button
                      type="button"
                      className="button secondary tiny"
                      disabled={offset + PAGE_SIZE >= list.data.entries}
                      onClick={() => setOffset(offset + PAGE_SIZE)}
                    >
                      Older
                    </button>
                  </div>
                )}
              </>
            ) : null}
          </Modal>
        ))}
      {view === 'clear' && (
        <Modal
          title={`Clear ${name} message logs?`}
          onClose={() => {
            if (!clearing) setView(undefined);
          }}
        >
          <p className="channel-stop-note">
            This deletes settled diagnostics for the current connection. Active messages, reply
            receipts, and conversations stay available. SQLite can reuse the freed space.
          </p>
          {clearError && (
            <p role="alert" className="form-error">
              {clearError}
            </p>
          )}
          <div className="inline-actions">
            <button
              type="button"
              className="button secondary"
              disabled={clearing}
              onClick={() => setView(undefined)}
            >
              Cancel
            </button>
            <button
              type="button"
              className="button rose-button"
              disabled={clearing}
              onClick={() => void clear()}
            >
              {clearing ? 'Clearing…' : 'Clear logs'}
            </button>
          </div>
        </Modal>
      )}
    </>
  );
}

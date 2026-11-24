import { useState } from 'react';
import type { ReactNode } from 'react';
import { Activity, CircleCheck, LoaderCircle, Pause, Play, Square } from 'lucide-react';
import { Modal } from '../ui';

export type ChannelAction = 'enable' | 'pause' | 'stop' | 'check';

export function ChannelControls({
  name,
  enabled,
  started,
  stopped,
  busy,
  editing,
  verified,
  action,
  children,
}: {
  name: string;
  enabled?: boolean;
  started?: boolean;
  stopped?: boolean;
  busy: string;
  editing?: boolean;
  verified?: boolean;
  action: (kind: ChannelAction) => void;
  children?: ReactNode;
}) {
  const [confirmStop, setConfirmStop] = useState(false);
  const mode = enabled ? 'pause' : 'enable';
  const primaryLabel = enabled ? 'Pause' : started && !stopped ? 'Resume' : 'Start';
  const PrimaryIcon = enabled ? Pause : Play;
  return (
    <>
      <div className="channel-activity-controls" role="group" aria-label={`${name} controls`}>
        <button
          type="button"
          className={`button ${enabled ? 'secondary' : 'primary'} tiny`}
          disabled={!!busy || (!enabled && editing)}
          aria-label={`${primaryLabel} ${name}`}
          onClick={() => action(mode)}
        >
          {busy === mode ? <LoaderCircle size={13} className="spin" /> : <PrimaryIcon size={13} />}
          {primaryLabel}
        </button>
        {(enabled || (started && !stopped)) && (
          <button
            type="button"
            className="button secondary tiny"
            disabled={!!busy}
            aria-label={`Stop ${name}`}
            onClick={() => setConfirmStop(true)}
          >
            {busy === 'stop' ? <LoaderCircle size={13} className="spin" /> : <Square size={12} />}
            Stop
          </button>
        )}
        <button
          type="button"
          className="button secondary tiny"
          disabled={!!busy}
          aria-label={`Check ${name} status`}
          aria-description={verified ? 'Connection verified.' : undefined}
          onClick={() => action('check')}
        >
          {busy === 'check' ? (
            <LoaderCircle size={13} className="spin" aria-hidden="true" />
          ) : verified ? (
            <CircleCheck size={13} className="channel-check-verified" aria-hidden="true" />
          ) : (
            <Activity size={13} aria-hidden="true" />
          )}
          Check status
        </button>
        {children}
      </div>
      {confirmStop && (
        <Modal title={`Stop ${name}?`} onClose={() => setConfirmStop(false)}>
          <p className="channel-stop-note">
            Stop clears queued messages and unsent reply parts. Saved credentials and history stay
            available. A send already submitted can finish.
          </p>
          <div className="inline-actions">
            <button
              type="button"
              className="button secondary"
              onClick={() => setConfirmStop(false)}
            >
              Cancel
            </button>
            <button
              type="button"
              className="button rose-button"
              onClick={() => {
                setConfirmStop(false);
                action('stop');
              }}
            >
              Stop listener
            </button>
          </div>
        </Modal>
      )}
    </>
  );
}

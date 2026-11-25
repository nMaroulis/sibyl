import type { CSSProperties } from 'react';
import '../styles/messaging-activity.css';

export type MonitorSample = { count: number; attention?: boolean };

/** Render observed samples and the shared live sweep. */
export function MonitorTrace({ bins, live }: { bins: MonitorSample[]; live: boolean }) {
  return (
    <div
      className="channel-activity-trace-track"
      data-live={live}
      aria-hidden="true"
      style={{ '--trace-ticks': bins.length } as CSSProperties}
    >
      {bins.map(({ count, attention }, index) => (
        <i
          key={index}
          data-recorded={count > 0}
          data-attention={!!attention}
          style={{ '--tick-count': count } as CSSProperties}
        />
      ))}
    </div>
  );
}

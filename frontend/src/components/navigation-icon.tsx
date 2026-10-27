import { useId } from 'react';
import type { ReactNode } from 'react';
import type { LucideIcon } from 'lucide-react';
import { SibylMark } from './sibyl-mark';

/** Filled counterparts preserve the meaning of the dock's existing line icons. */
const solidShapes: Record<string, ReactNode> = {
  '/account': (
    <path
      fillRule="evenodd"
      d="M5 4a3 3 0 0 0-3 3v11a3 3 0 0 0 3 3h14a3 3 0 0 0 3-3V9a3 3 0 0 0-3-3H6a1 1 0 0 1 0-2h12V2H5v2Zm12 7a3 3 0 0 0 0 6h3v-6h-3Zm0 2a1 1 0 1 1 0 2 1 1 0 0 1 0-2Z"
    />
  ),
  '/markets': (
    <>
      <path
        d="M5 3v18M12 2v18M19 5v17"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.6"
        strokeLinecap="round"
      />
      <rect x="3" y="7" width="4" height="8" rx="1.2" />
      <rect x="10" y="5" width="4" height="7" rx="1.2" />
      <rect x="17" y="10" width="4" height="8" rx="1.2" />
    </>
  ),
  '/trade': (
    <path d="M7.1 2.4a1.2 1.2 0 0 1 1.8 0l4 4.4a1.1 1.1 0 0 1-1.6 1.5L9.2 6v14a1.2 1.2 0 0 1-2.4 0V6L4.7 8.3a1.1 1.1 0 1 1-1.6-1.5l4-4.4Zm9.8 19.2a1.2 1.2 0 0 1-1.8 0l-4-4.4a1.1 1.1 0 0 1 1.6-1.5l2.1 2.3V4a1.2 1.2 0 0 1 2.4 0v14l2.1-2.3a1.1 1.1 0 0 1 1.6 1.5l-4 4.4Z" />
  ),
  '/strategies': (
    <>
      {[0, 6, 12].map((y) => (
        <path
          key={y}
          transform={`translate(0 ${y})`}
          d="M2 5.6c2.4 0 2.4-2.4 5-2.4s2.6 2.4 5 2.4 2.4-2.4 5-2.4 2.6 2.4 5 2.4v2.2c-3.3 0-3.3-2.4-5-2.4s-1.7 2.4-5 2.4-3.3-2.4-5-2.4-1.7 2.4-5 2.4V5.6Z"
        />
      ))}
    </>
  ),
  '/forecast': (
    <path
      fillRule="evenodd"
      d="M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20Zm4.6 5.4-3.1 6.1-6.1 3.1 3.1-6.1 6.1-3.1Z"
    />
  ),
  '/oracle': (
    <path d="M13 2c1.2 6.1 2.9 7.8 9 9-6.1 1.2-7.8 2.9-9 9-1.2-6.1-2.9-7.8-9-9 6.1-1.2 7.8-2.9 9-9ZM4.5 15.3c.5 2.2 1 2.7 3.2 3.2-2.2.5-2.7 1-3.2 3.2-.5-2.2-1-2.7-3.2-3.2 2.2-.5 2.7-1 3.2-3.2Z" />
  ),
  '/alerts': (
    <path d="M12 2a6 6 0 0 0-6 6v3.6c0 1.6-.6 3.1-1.7 4.2A1.3 1.3 0 0 0 5.2 18h13.6a1.3 1.3 0 0 0 .9-2.2A6 6 0 0 1 18 11.6V8a6 6 0 0 0-6-6Zm-2.8 18a3 3 0 0 0 5.6 0H9.2Z" />
  ),
  '/research': (
    <path d="M3 3c3.5-.8 5.7-.3 8 1.3V22c-2.3-1.6-4.5-2.1-8-1.3a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1Zm18 0c-3.5-.8-5.7-.3-8 1.3V22c2.3-1.6 4.5-2.1 8-1.3a1 1 0 0 0 1-1V4a1 1 0 0 0-1-1Z" />
  ),
  '/settings': (
    <>
      <path
        d="M3 5h18M3 12h18M3 19h18"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.6"
        strokeLinecap="round"
      />
      <rect x="6" y="2" width="4" height="6" rx="2" />
      <rect x="14" y="9" width="4" height="6" rx="2" />
      <rect x="7" y="16" width="4" height="6" rx="2" />
    </>
  ),
  more: (
    <>
      {[
        [3, 3],
        [14, 3],
        [3, 14],
        [14, 14],
      ].map(([x, y]) => (
        <rect key={`${x}:${y}`} x={x} y={y} width="7" height="7" rx="2" />
      ))}
    </>
  ),
};
solidShapes['/roadmap'] = solidShapes['/forecast'];

/** Crossfade to solid geometry on selection; do not fill arbitrary open SVG paths. */
export function NavigationIcon({ path, icon: Icon }: { path: string; icon: LucideIcon }) {
  const globeMask = useId();
  if (path === '/sibyl') return <SibylMark small />;
  if (path !== '/news' && !solidShapes[path]) return <Icon size={21} aria-hidden="true" />;
  return (
    <>
      <Icon className="dock-icon-outline" size={21} aria-hidden="true" />
      <svg
        className="dock-icon-solid"
        viewBox="0 0 24 24"
        width="21"
        height="21"
        fill="currentColor"
        aria-hidden="true"
      >
        {path === '/news' ? (
          <>
            <defs>
              <mask id={globeMask}>
                <rect width="24" height="24" fill="white" />
                <path
                  d="M2 12h20M12 2c-5.4 4.8-5.4 15.2 0 20M12 2c5.4 4.8 5.4 15.2 0 20"
                  fill="none"
                  stroke="black"
                  strokeWidth="1.4"
                />
              </mask>
            </defs>
            <circle cx="12" cy="12" r="10" mask={`url(#${globeMask})`} />
          </>
        ) : (
          solidShapes[path]
        )}
      </svg>
    </>
  );
}

import { ArrowUpRight, RefreshCw } from 'lucide-react';
import { Badge, Panel, PanelTitle } from './ui';
import { useResource } from '../lib/hooks';
import { shortDate } from '../lib/api';
import type { FearGreedIndex } from '../lib/types';

function arc(start: number, end: number) {
  const point = (angle: number) =>
    `${100 + 77 * Math.cos((angle * Math.PI) / 180)} ${98 - 77 * Math.sin((angle * Math.PI) / 180)}`;
  return `M ${point(start)} A 77 77 0 0 1 ${point(end)}`;
}

/** The attributed Bitcoin mood index is independent from per-article language polarity. */
export function FearGreedCard({ mode }: { mode?: 'demo' | 'live' }) {
  const index = useResource<FearGreedIndex>(
    `/news/fear-greed${mode ? `?mode=${mode}` : ''}`,
    60000,
  );
  const data = index.data;
  const current = data?.current;
  return (
    <Panel className="fear-greed-card">
      <PanelTitle
        title="Fear & Greed"
        subtitle="Bitcoin market mood"
        action={
          data?.mode === 'demo' ? (
            <Badge tone="purple">Demo</Badge>
          ) : data?.status === 'stale' ? (
            <Badge tone="sand">Stale</Badge>
          ) : undefined
        }
      />
      {current ? (
        <>
          <div className="fear-greed-reading">
            <svg
              className="fear-greed-gauge"
              viewBox="0 0 200 125"
              role="img"
              aria-label={`${current.value} out of 100, ${current.classification}`}
            >
              {['#d7a0aa', '#e4b994', '#dfd7af', '#b8c5a1', '#82afa0'].map((color, i) => (
                <path
                  key={color}
                  d={arc(180 - i * 36 - 2, 180 - (i + 1) * 36 + 2)}
                  fill="none"
                  stroke={color}
                  strokeWidth={13}
                  strokeLinecap="round"
                />
              ))}
              <g transform={`rotate(${current.value * 1.8 - 90} 100 98)`}>
                <path
                  d="M 100 98 L 100 36"
                  stroke="#526078"
                  strokeWidth={2.5}
                  strokeLinecap="round"
                />
              </g>
              <circle cx="100" cy="98" r="5" fill="#526078" />
              <text x="20" y="121" textAnchor="middle">
                0
              </text>
              <text x="180" y="121" textAnchor="middle">
                100
              </text>
            </svg>
            <div className="fear-greed-value">
              <strong>
                {current.value}
                <small>/100</small>
              </strong>
              <span>{current.classification}</span>
              <time dateTime={current.timestamp}>{shortDate(current.timestamp)} · daily index</time>
            </div>
          </div>
          <div className="fear-greed-comparisons">
            {(
              [
                ['yesterday', 'Yesterday'],
                ['last_week', 'Last week'],
                ['last_month', '29 days ago'],
              ] as const
            ).map(([key, label]) => (
              <div key={key}>
                <small>{label}</small>
                <strong>{data?.comparisons[key]?.value ?? '—'}</strong>
              </div>
            ))}
          </div>
          <p className="fear-greed-credit">
            {data?.mode === 'demo' ? (
              'Sibyl demo · illustrative values and dates'
            ) : (
              <a href={data?.source_url} target="_blank" rel="noreferrer">
                Source: Alternative.me <ArrowUpRight size={12} />
              </a>
            )}
          </p>
          {(data?.error || data?.status === 'stale') && (
            <p className="footnote padded">
              Last available observation. The source could not provide a fresh update.
            </p>
          )}
        </>
      ) : (
        <div className="fear-greed-empty">
          <p>
            {index.loading ? 'Loading the daily index…' : 'The index is currently unavailable.'}
          </p>
          <button className="text-link" onClick={index.retry}>
            <RefreshCw size={13} /> Retry
          </button>
          {data?.mode !== 'demo' && (
            <a
              href="https://alternative.me/crypto/fear-and-greed-index/"
              target="_blank"
              rel="noreferrer"
            >
              Alternative.me <ArrowUpRight size={12} />
            </a>
          )}
        </div>
      )}
    </Panel>
  );
}

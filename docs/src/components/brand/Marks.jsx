import React, { useId } from 'react';
import useBaseUrl from '@docusaurus/useBaseUrl';

/** Local integration artwork, with official DeepSeek and simplified inline AI marks. */
export function ProviderMark({ name }) {
  const assets = useBaseUrl('/img/integrations/');
  const gradientId = `provider-${useId().replace(/:/g, '')}`;
  const files = {
    Binance: 'binance.jpg',
    Coinbase: 'coinbase.png',
    Kraken: 'kraken.jpg',
    Bybit: 'bybit.png',
    DeepSeek: 'deepseek.svg',
  };
  if (files[name])
    return <img src={`${assets}${files[name]}`} width="30" height="30" alt="" draggable="false" />;
  const props = { viewBox: '0 0 32 32', width: 30, height: 30, fill: 'none', 'aria-hidden': true };
  if (name === 'OpenAI')
    return (
      <svg {...props} viewBox="0 0 40 40">
        <g stroke="currentColor" strokeWidth="2.2">
          {[0, 60, 120, 180, 240, 300].map((angle) => (
            <path
              key={angle}
              transform={`rotate(${angle} 20 20)`}
              d="M20 7c8-5 17 5 10 12l-10 6-6-4V10z"
            />
          ))}
        </g>
      </svg>
    );
  if (name === 'Anthropic')
    return (
      <svg {...props} fill="currentColor">
        <path d="M13 5 2 27h5l2.2-5h9.3l2.2 5h5L15 5h-2Zm-2 13 3-7 3 7h-6ZM22 5h5l5 22h-5L22 5Z" />
      </svg>
    );
  if (name === 'Gemini')
    return (
      <svg {...props}>
        <defs>
          <linearGradient
            id={gradientId}
            x1="0"
            y1="0"
            x2="32"
            y2="32"
            gradientUnits="userSpaceOnUse"
          >
            <stop stopColor="#4285f4" />
            <stop offset=".5" stopColor="#8b71cb" />
            <stop offset="1" stopColor="#e7788e" />
          </linearGradient>
        </defs>
        <path
          d="M16 1C18 10 22 14 31 16 22 18 18 22 16 31 14 22 10 18 1 16 10 14 14 10 16 1Z"
          fill={`url(#${gradientId})`}
        />
      </svg>
    );
  if (name === 'xAI')
    return (
      <svg {...props} stroke="currentColor" strokeWidth="2.4">
        <path d="m6 5 20 22M24 4 6 27M15 17l-6-7M21 21l5 6M26 3v10" />
      </svg>
    );
  if (name === 'Hugging Face')
    return (
      <span className="sibyl-provider-emoji" aria-hidden="true">
        🤗
      </span>
    );
  if (name === 'LM Studio')
    return (
      <svg
        {...props}
        stroke="#8e75cf"
        strokeWidth="2.6"
        strokeLinecap="round"
        strokeLinejoin="round"
      >
        <path d="M3 8v16h9M16 24V8l6 9 7-9v16" />
      </svg>
    );
  if (name === 'vLLM')
    return (
      <svg {...props} fill="#5e78bf">
        <path d="M2 8h6l6 15L24 8h6L15 29h-5L2 8Z" />
        <path d="m18 3-5 7h5l5-7h-5Z" fill="#eab773" />
      </svg>
    );
  return (
    <svg
      {...props}
      stroke="currentColor"
      strokeWidth="1.7"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d="M10 16C7 8 9 2 12 3c2 1 2 6 2 10h4c0-4 0-9 2-10 3-1 5 5 2 13 4 2 5 8 2 11-4 4-12 4-16 0-3-3-2-9 2-11Z" />
      <path d="M12 21h.1M20 21h.1M14 25c1 1 3 1 4 0" strokeWidth="2.5" />
    </svg>
  );
}

const paths = {
  arrow: 'M6 18 18 6M6 6h12v12',
  account: 'M4 7h15a2 2 0 0 1 2 2v11H5a2 2 0 0 1-2-2V6a3 3 0 0 1 3-3h12v4M21 11h-6v5h6M17 13.5h.01',
  markets: 'M4 18 9 12l4 3 7-10M4 4v16h16',
  strategies: 'M5 4v5a3 3 0 0 0 3 3h8a3 3 0 0 1 3 3v5M19 4v3a5 5 0 0 1-5 5M3 4h4M17 4h4M17 20h4',
  spark: 'm12 3 2.5 6.5L21 12l-6.5 2.5L12 21l-2.5-6.5L3 12l6.5-2.5L12 3Z',
  code: 'm8 6-6 6 6 6m8-12 6 6-6 6M14 3l-4 18',
  news: 'M5 3h14v18H5V3ZM8 7h8M8 11h8M8 15h3m2 0h3m-8 3h3m2 0h3',
  forecast: 'M3 18c4 0 3-12 7-12s2 9 6 9 3-6 5-6M3 21h18',
  research: 'M10 18a7 7 0 1 0 0-14 7 7 0 0 0 0 14Zm5-2 6 6M7 11h6m-3-3v6',
  shield: 'm12 3 8 3v6c0 4-5 7-8 9-3-2-8-5-8-9V6l8-3Zm-4 9 3 3 5-6',
  message: 'M21 11a8 8 0 0 1-8 8H8l-5 3V11a9 9 0 0 1 18 0ZM7 10h10M7 14h6',
  mail: 'M3 5h18v14H3V5Zm0 1 9 7 9-7',
  server: 'M4 3h16v7H4V3Zm0 11h16v7H4v-7ZM7 6.5h.01M7 17.5h.01M11 6.5h6M11 17.5h6',
  chip: 'M7 7h10v10H7V7Zm3 3h4v4h-4v-4M9 3v4m6-4v4M9 17v4m6-4v4M3 9h4m-4 6h4m10-6h4m-4 6h4',
};

export function GuideIcon({ name, className = '' }) {
  return (
    <svg
      className={className}
      width="22"
      height="22"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.6"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d={paths[name] || paths.spark} />
    </svg>
  );
}

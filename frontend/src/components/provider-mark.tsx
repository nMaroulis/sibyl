import { useId } from 'react';
import { Cable, Cpu, FlaskConical, Server, Sparkles } from 'lucide-react';

/** Local and inline provider marks; no remote requests or credential-bearing URLs. */
export function ProviderMark({ provider, size = 24 }: { provider: string; size?: number }) {
  const gradientId = useId();
  const props = {
    width: size,
    height: size,
    viewBox: '0 0 32 32',
    fill: 'none',
    'aria-hidden': true as const,
  };
  switch (provider) {
    case 'openai':
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
    case 'anthropic':
      return (
        <svg {...props} fill="currentColor">
          <path d="M13 5 2 27h5l2.2-5h9.3l2.2 5h5L15 5h-2Zm-2 13 3-7 3 7h-6ZM22 5h5l5 22h-5L22 5Z" />
        </svg>
      );
    case 'gemini':
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
    case 'deepseek':
      return (
        <img
          src="/brand/deepseek.svg"
          width={size}
          height={size}
          alt=""
          aria-hidden="true"
          draggable={false}
          style={{ objectFit: 'contain' }}
        />
      );
    case 'grok':
      return (
        <svg {...props} stroke="currentColor" strokeWidth="2.4">
          <path d="m6 5 20 22M24 4 6 27M15 17l-6-7M21 21l5 6" />
          <path d="M26 3v10" strokeWidth="3" />
        </svg>
      );
    case 'huggingface':
      return (
        <span className="provider-emoji" aria-hidden="true" style={{ fontSize: size }}>
          🤗
        </span>
      );
    case 'ollama':
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
    case 'lmstudio':
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
    case 'vllm':
      return (
        <svg {...props} fill="#5e78bf">
          <path d="M2 8h6l6 15L24 8h6L15 29h-5L2 8Z" />
          <path d="m18 3-5 7h5l5-7h-5Z" fill="#eab773" />
        </svg>
      );
    case 'llama.cpp-server':
      return <Server size={size} aria-hidden="true" />;
    case 'llama.cpp-local':
      return <Cpu size={size} aria-hidden="true" />;
    case 'openai-compatible':
      return <Cable size={size} aria-hidden="true" />;
    case 'mock':
      return <FlaskConical size={size} aria-hidden="true" />;
    default:
      return <Sparkles size={size} aria-hidden="true" />;
  }
}

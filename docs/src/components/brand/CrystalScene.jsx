import React, { useEffect, useId, useState } from 'react';
import { ProviderMark } from './Marks';

const orbit = [
  { name: 'Binance', angle: -145 },
  { name: 'Anthropic', angle: -80 },
  { name: 'Coinbase', angle: -20 },
  { name: 'OpenAI', angle: 45 },
  { name: 'Ollama', angle: 105 },
  { name: 'Kraken', angle: 172 },
];

/** Decorative glass and transform-only motion, with pause and reduced-motion controls. */
export default function CrystalScene() {
  const prefix = `crystal-${useId().replace(/:/g, '')}`;
  const [paused, setPaused] = useState(false);
  const [reduced, setReduced] = useState(false);
  useEffect(() => {
    const preference = window.matchMedia('(prefers-reduced-motion: reduce)');
    const update = () => setReduced(preference.matches);
    update();
    preference.addEventListener('change', update);
    return () => preference.removeEventListener('change', update);
  }, []);
  const id = (key) => `${prefix}-${key}`;
  const paint = (key) => `url(#${id(key)})`;
  return (
    <div className="crystal-scene" data-paused={paused || reduced}>
      <div className="crystal-art" aria-hidden="true">
        <div className="crystal-halo" />
        <div className="crystal-orbit-ring crystal-orbit-ring-one" />
        <div className="crystal-orbit-ring crystal-orbit-ring-two" />
        <svg className="crystal-ball" viewBox="0 0 600 600" fill="none">
          <defs>
            <radialGradient id={id('glass')} cx=".3" cy=".22" r=".92">
              <stop stopColor="#fff" />
              <stop offset=".25" stopColor="#e9efff" />
              <stop offset=".6" stopColor="#c3d4f5" />
              <stop offset=".83" stopColor="#9db9e8" />
              <stop offset="1" stopColor="#7997d3" />
            </radialGradient>
            <radialGradient id={id('mist')} cx=".7" cy=".75" r=".7">
              <stop stopColor="#b0e0ec" stopOpacity=".8" />
              <stop offset=".55" stopColor="#a5a7e5" stopOpacity=".12" />
              <stop offset="1" stopColor="#fff" stopOpacity="0" />
            </radialGradient>
            <radialGradient id={id('light')} cx=".3" cy=".12" r=".76">
              <stop stopColor="#fff" stopOpacity=".95" />
              <stop offset=".7" stopColor="#fff" stopOpacity="0" />
            </radialGradient>
            <linearGradient
              id={id('base')}
              x1="220"
              y1="430"
              x2="375"
              y2="494"
              gradientUnits="userSpaceOnUse"
            >
              <stop stopColor="#fff" />
              <stop offset=".4" stopColor="#dce5f6" />
              <stop offset=".7" stopColor="#b4c6e4" />
              <stop offset="1" stopColor="#f2f5fc" />
            </linearGradient>
            <linearGradient
              id={id('signal')}
              x1="145"
              y1="324"
              x2="456"
              y2="264"
              gradientUnits="userSpaceOnUse"
            >
              <stop stopColor="#fff" stopOpacity="0" />
              <stop offset=".38" stopColor="#fff" stopOpacity=".85" />
              <stop offset=".65" stopColor="#6e8dd4" stopOpacity=".65" />
              <stop offset="1" stopColor="#fff" stopOpacity="0" />
            </linearGradient>
            <clipPath id={id('clip')}>
              <circle cx="300" cy="280" r="158" />
            </clipPath>
            <filter id={id('shadow')} x="-.5" y="-1" width="2" height="3">
              <feGaussianBlur stdDeviation="13" />
            </filter>
          </defs>
          <ellipse
            cx="300"
            cy="496"
            rx="104"
            ry="12"
            fill="#7592c5"
            opacity=".17"
            filter={paint('shadow')}
          />
          <g className="crystal-float">
            <path
              d="M254 424c5 17 9 32-4 43l-25 14c-5 3-2 8 5 10 32 8 108 8 140 0 7-2 10-7 5-10l-25-14c-13-11-9-26-4-43H254Z"
              fill={paint('base')}
            />
            <ellipse cx="300" cy="431" rx="83" ry="19" fill="#c3d2ed" />
            <circle cx="300" cy="280" r="158" fill={paint('glass')} />
            <circle cx="300" cy="280" r="158" fill={paint('mist')} />
            <g clipPath={paint('clip')}>
              <path
                d="M130 343c48-55 77 43 125-21s71-25 99-65 62 31 116-30"
                stroke={paint('signal')}
                strokeWidth="2.1"
              />
              <path
                d="M111 356c70-32 94 36 148-3s91 29 135-10 51-23 85-9"
                stroke="#fff"
                strokeOpacity=".33"
                strokeWidth="1"
              />
              <ellipse
                cx="303"
                cy="280"
                rx="183"
                ry="57"
                transform="rotate(-32 303 280)"
                stroke="#fff"
                strokeOpacity=".18"
              />
              <circle cx="255" cy="322" r="4" fill="#fff" fillOpacity=".8" />
              <circle cx="354" cy="257" r="3" fill="#fff" fillOpacity=".8" />
              <path
                d="m300 206 5.5 14.5L320 226l-14.5 5.5L300 246l-5.5-14.5L280 226l14.5-5.5L300 206Z"
                fill="#fff"
                fillOpacity=".82"
              />
              <text
                x="300"
                y="285"
                textAnchor="middle"
                fill="#4c6fae"
                fontFamily="DM Sans, sans-serif"
                fontSize="29"
                fontWeight="500"
                letterSpacing="4"
              >
                sibyl
              </text>
              <text
                x="300"
                y="307"
                textAnchor="middle"
                fill="#5d7ba9"
                fontFamily="DM Sans, sans-serif"
                fontSize="9"
                letterSpacing="2.4"
              >
                CLARITY, CONNECTED
              </text>
            </g>
            <circle cx="300" cy="280" r="157.5" stroke="#fff" strokeOpacity=".65" />
            <ellipse
              cx="257"
              cy="186"
              rx="73"
              ry="33"
              transform="rotate(-27 257 186)"
              fill={paint('light')}
            />
            <path
              d="M169 268c0-57 34-110 86-128"
              stroke="#fff"
              strokeOpacity=".7"
              strokeWidth="2"
              strokeLinecap="round"
            />
            <path
              d="M218 433c39 22 125 23 164 0"
              stroke="#f8fbff"
              strokeWidth="3"
              strokeLinecap="round"
            />
            <path
              d="M236 485c31 6 97 6 128 0"
              stroke="#fff"
              strokeOpacity=".85"
              strokeWidth="1.5"
            />
          </g>
        </svg>
        {orbit.map(({ name, angle }) => (
          <div
            className="crystal-orbiter"
            key={name}
            style={{ '--angle': `${angle}deg`, '--counter-angle': `${-angle}deg` }}
          >
            <span className={`crystal-provider crystal-provider-${name.toLowerCase()}`}>
              <ProviderMark name={name} />
            </span>
            <span className="crystal-provider-name">{name}</span>
          </div>
        ))}
        <span className="crystal-speck crystal-speck-one" />
        <span className="crystal-speck crystal-speck-two" />
      </div>
      <div className="crystal-scene-footer">
        <span>
          <i /> A world of signals. One Sibyl.
        </span>
        <button
          type="button"
          disabled={reduced}
          onClick={() => setPaused(!paused)}
          aria-label={
            reduced
              ? 'Animation disabled by reduced motion preference'
              : paused
                ? 'Play animation'
                : 'Pause animation'
          }
        >
          <svg width="12" height="12" viewBox="0 0 12 12" aria-hidden="true">
            {paused || reduced ? (
              <path d="m4 2 6 4-6 4V2Z" fill="currentColor" />
            ) : (
              <path d="M4 2v8m4-8v8" stroke="currentColor" strokeWidth="1.5" />
            )}
          </svg>
          {reduced ? 'Reduced motion' : paused ? 'Play motion' : 'Pause motion'}
        </button>
      </div>
    </div>
  );
}

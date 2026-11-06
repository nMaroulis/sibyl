import { useEffect, useState } from 'react';
import { getStream } from './api';
import type { ChartCandle } from '../components/candlesticks';

type Event = {
  type: 'status' | 'ticker' | 'candle';
  source: string;
  state?: string;
  observed_at?: string;
  time_basis?: string;
  candle?: ChartCandle;
  price?: number;
  closed?: boolean;
};
type Live = {
  state: string;
  candle?: ChartCandle;
  price?: number;
  observed_at?: string;
  time_basis?: string;
  error?: string;
};

/** Exact selection changes discard prior data. Only display evidence enters this hook. */
export function useLiveMarket(source: string, symbol: string, timeframe: string, enabled: boolean) {
  const [live, setLive] = useState<Live>({ state: 'rest' });
  useEffect(() => {
    let disposed = false,
      controller: AbortController | undefined,
      retry: number | undefined;
    let received = Date.now(),
      failures = 0;
    setLive({ state: enabled ? 'connecting' : 'rest' });
    const connect = async () => {
      if (disposed || document.hidden || !enabled) return;
      controller = new AbortController();
      try {
        await getStream<Event>(
          `/markets/live?${new URLSearchParams({ source, symbol, timeframe })}`,
          (event) => {
            if (disposed || event.source !== source) return;
            received = Date.now();
            failures = 0;
            setLive((previous) =>
              event.type === 'status'
                ? { ...previous, state: event.state || 'connecting' }
                : {
                    ...previous,
                    state: 'live',
                    observed_at: event.observed_at,
                    time_basis: event.time_basis,
                    ...(event.candle ? { candle: event.candle, price: event.candle.close } : {}),
                    ...(event.price ? { price: event.price } : {}),
                    error: undefined,
                  },
            );
          },
          controller.signal,
        );
        if (!controller.signal.aborted)
          throw new Error('Live connection ended. REST snapshots remain active.');
      } catch (reason) {
        if (!disposed && !controller.signal.aborted) {
          setLive((previous) => ({
            ...previous,
            state: 'reconnecting',
            error: (reason as Error).message,
          }));
          retry = window.setTimeout(connect, Math.min(30000, 2000 * 2 ** Math.min(failures++, 4)));
        }
      }
    };
    const visibility = () => {
      controller?.abort();
      clearTimeout(retry);
      if (document.hidden) setLive((previous) => ({ ...previous, state: 'paused' }));
      else void connect();
    };
    const watchdog = window.setInterval(() => {
      if (enabled && Date.now() - received > 20000)
        setLive((previous) =>
          previous.state === 'live' ? { ...previous, state: 'stale' } : previous,
        );
    }, 5000);
    document.addEventListener('visibilitychange', visibility);
    void connect();
    return () => {
      disposed = true;
      controller?.abort();
      clearTimeout(retry);
      clearInterval(watchdog);
      document.removeEventListener('visibilitychange', visibility);
    };
  }, [source, symbol, timeframe, enabled]);
  return live;
}

/** Append/update the forming candle without manufacturing indicator values or filling gaps. */
export function previewCandles(closed: ChartCandle[], forming?: ChartCandle) {
  if (!forming || !closed.length) return closed;
  const timestamp = Date.parse(forming.timestamp),
    last = Date.parse(closed.at(-1)!.timestamp);
  if (timestamp < last) return closed;
  return [
    ...(timestamp === last ? closed.slice(0, -1) : closed),
    { ...forming, live_preview: true },
  ].slice(-closed.length - 1);
}

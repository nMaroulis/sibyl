import { useCallback, useEffect, useRef, useState } from 'react';
import { api } from './api';

/** Fetch on navigation, manual refresh, and optional polling; ignore stale responses. */
export function useResource<T>(path: string, interval = 0, enabled = true) {
  const [data, setData] = useState<T>();
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const [revision, setRevision] = useState(0);
  const retry = useCallback(() => setRevision((value) => value + 1), []);
  const generation = useRef(0);
  const resourcePath = useRef<string | undefined>(undefined);
  useEffect(() => {
    const id = ++generation.current;
    if (resourcePath.current !== path) {
      setData(undefined);
      setLoading(true);
      resourcePath.current = path;
    } else if (!data) {
      setLoading(true);
    }
    setError('');
    if (!enabled) {
      setData(undefined);
      setLoading(false);
      return;
    }
    let latestRequest = 0;
    let controller: AbortController | undefined;
    const fetchData = () => {
      controller?.abort();
      controller = new AbortController();
      const requestId = ++latestRequest;
      api<T>(path, { signal: controller.signal })
        .then((result) => {
          if (generation.current === id && requestId === latestRequest) {
            setData(result);
            setError('');
          }
        })
        .catch((reason) => {
          if (
            reason.name !== 'AbortError' &&
            generation.current === id &&
            requestId === latestRequest
          ) {
            setError(reason.message);
          }
        })
        .finally(() => {
          if (generation.current === id && requestId === latestRequest) setLoading(false);
        });
    };
    fetchData();
    const timer = interval ? window.setInterval(fetchData, interval) : undefined;
    window.addEventListener('sibyl-refresh', fetchData);
    return () => {
      generation.current++;
      controller?.abort();
      clearInterval(timer);
      window.removeEventListener('sibyl-refresh', fetchData);
    };
  }, [path, interval, revision, enabled]);
  return { data, error, loading, retry };
}

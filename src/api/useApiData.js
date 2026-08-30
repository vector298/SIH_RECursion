import { useCallback, useEffect, useRef, useState } from 'react';
import { useBackend } from './BackendContext';

/**
 * Fetch data for a screen, with the sample corpus as the offline fallback.
 *
 * Returns `live: true` only when the rows genuinely came from the API, so a
 * screen can label what the viewer is looking at instead of quietly presenting
 * fixtures as real records.
 *
 * @param {(signal: AbortSignal) => Promise<any>} fetcher
 * @param {any} fallback          sample data used when the API is unreachable
 * @param {any[]} deps            re-fetch when these change
 */
export function useApiData(fetcher, fallback, deps = []) {
  const { online, status } = useBackend();
  const [state, setState] = useState({ data: fallback, loading: true, error: null, live: false });
  const [nonce, setNonce] = useState(0);
  const fetcherRef = useRef(fetcher);
  fetcherRef.current = fetcher;

  useEffect(() => {
    // Still probing: hold the loading state rather than flashing sample data.
    if (status === 'checking') return;

    if (!online) {
      setState({ data: fallback, loading: false, error: null, live: false });
      return;
    }

    const controller = new AbortController();
    let cancelled = false;
    setState((s) => ({ ...s, loading: true }));

    fetcherRef.current(controller.signal)
      .then((data) => {
        if (!cancelled) setState({ data, loading: false, error: null, live: true });
      })
      .catch((err) => {
        if (cancelled || err.name === 'AbortError') return;
        // Show the fallback, but say the request failed — silently substituting
        // fixtures for a failed call is how a demo misleads its audience.
        setState({ data: fallback, loading: false, error: err.message || 'Request failed', live: false });
      });

    return () => { cancelled = true; controller.abort(); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [online, status, nonce, ...deps]);

  const refresh = useCallback(() => setNonce((n) => n + 1), []);
  return { ...state, refresh };
}

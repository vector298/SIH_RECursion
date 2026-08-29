import { createContext, useContext, useEffect, useMemo, useState } from 'react';
import { getHealth } from './client';

/**
 * Probes the API once on load and tells the rest of the app whether it is
 * looking at live computed results or the offline sample corpus.
 *
 * Screens read `online` and switch source; the top bar shows which mode is in
 * effect and, when live, which model backends are actually loaded — so nobody
 * demonstrates a fallback descriptor believing it is ArcFace.
 */
const BackendContext = createContext({
  status: 'checking',
  online: false,
  health: null,
  recheck: () => {},
});

export function BackendProvider({ children }) {
  const [status, setStatus] = useState('checking');   // checking | online | offline
  const [health, setHealth] = useState(null);
  const [nonce, setNonce] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    let cancelled = false;

    getHealth(controller.signal)
      .then((body) => {
        if (cancelled) return;
        setHealth(body);
        setStatus('online');
      })
      .catch(() => {
        if (!cancelled) setStatus('offline');
      });

    return () => { cancelled = true; controller.abort(); };
  }, [nonce]);

  const value = useMemo(() => ({
    status,
    online: status === 'online',
    health,
    recheck: () => setNonce((n) => n + 1),
  }), [status, health]);

  return <BackendContext.Provider value={value}>{children}</BackendContext.Provider>;
}

export const useBackend = () => useContext(BackendContext);

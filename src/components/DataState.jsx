import { Loader2, TriangleAlert, Database } from 'lucide-react';

/**
 * The banner that tells a viewer what they are actually looking at.
 *
 * A demo that shows fixtures without saying so is worse than one that shows an
 * error, so every screen backed by `useApiData` renders this.
 */
export function SourceBanner({ live, loading, error, count, noun = 'records' }) {
  if (loading) {
    return (
      <div className="row gap-10" style={{ fontSize: 12, color: 'var(--muted)' }}>
        <Loader2 size={13} className="spin" color="var(--cyan)" />
        Loading from the case index…
      </div>
    );
  }

  if (error) {
    return (
      <div className="row gap-10" style={{
        padding: '10px 13px', borderRadius: 10,
        border: '1px solid rgba(255,95,112,.28)', background: 'var(--red-dim)',
      }}>
        <TriangleAlert size={14} strokeWidth={2} color="#ff8e9b" style={{ flexShrink: 0 }} />
        <span style={{ fontSize: 12.5 }}>
          <strong>Showing sample data.</strong> The request failed: {error}
        </span>
      </div>
    );
  }

  if (!live) {
    return (
      <div className="row gap-10" style={{
        padding: '10px 13px', borderRadius: 10,
        border: '1px solid rgba(255,177,86,.24)', background: 'rgba(255,177,86,.06)',
      }}>
        <TriangleAlert size={14} strokeWidth={2} color="#ffb156" style={{ flexShrink: 0 }} />
        <span style={{ fontSize: 12.5, color: 'var(--text-2)' }}>
          <strong>Sample data.</strong> These {noun} are fixtures — start the API to see the real index.
        </span>
      </div>
    );
  }

  return (
    <div className="row gap-8" style={{ fontSize: 11.5, color: 'var(--dim)' }}>
      <Database size={12} strokeWidth={2} color="var(--green)" />
      <span className="mono" style={{ letterSpacing: '.08em' }}>
        LIVE{count != null ? ` · ${count.toLocaleString('en-IN')} ${noun}` : ''}
      </span>
    </div>
  );
}

export function EmptyState({ title, hint }) {
  return (
    <div className="panel panel-pad" style={{ textAlign: 'center', padding: 40 }}>
      <div style={{ fontSize: 14, fontWeight: 600 }}>{title}</div>
      {hint && <p className="page-sub" style={{ margin: '8px auto 0' }}>{hint}</p>}
    </div>
  );
}

export function LoadingRows({ rows = 3, height = 120 }) {
  return (
    <div className="stack gap-12" aria-busy="true">
      {Array.from({ length: rows }, (_, i) => (
        <div key={i} style={{
          height, borderRadius: 16, border: '1px solid var(--line)',
          background: 'linear-gradient(100deg, rgba(20,31,52,.5) 30%, rgba(30,45,74,.6) 50%, rgba(20,31,52,.5) 70%)',
          backgroundSize: '220% 100%',
          animation: `shimmer 1.6s ${i * 0.12}s linear infinite`,
        }} />
      ))}
    </div>
  );
}

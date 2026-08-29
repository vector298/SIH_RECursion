import { useEffect, useRef, useState, useMemo } from 'react';

/* ------------------------------------------------------------------
   Reveal — fade/slide in when the element enters the viewport
------------------------------------------------------------------ */
export function Reveal({ children, delay = 0, as: Tag = 'div', className = '', ...rest }) {
  const ref = useRef(null);
  const [seen, setSeen] = useState(false);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const io = new IntersectionObserver(
      ([e]) => { if (e.isIntersecting) { setSeen(true); io.disconnect(); } },
      { threshold: 0.12, rootMargin: '0px 0px -40px 0px' }
    );
    io.observe(el);
    return () => io.disconnect();
  }, []);
  return (
    <Tag ref={ref} className={`reveal ${seen ? 'in' : ''} ${className}`}
         style={{ animationDelay: `${delay}ms` }} {...rest}>
      {children}
    </Tag>
  );
}

/* ------------------------------------------------------------------
   useInView — boolean hook
------------------------------------------------------------------ */
export function useInView(threshold = 0.2) {
  const ref = useRef(null);
  const [inView, setInView] = useState(false);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const io = new IntersectionObserver(([e]) => { if (e.isIntersecting) { setInView(true); io.disconnect(); } }, { threshold });
    io.observe(el);
    return () => io.disconnect();
  }, [threshold]);
  return [ref, inView];
}

/* ------------------------------------------------------------------
   Counter — eased number count-up, starts when visible
------------------------------------------------------------------ */
export function Counter({ to, duration = 1400, decimals = 0, prefix = '', suffix = '', className = '' }) {
  const [ref, inView] = useInView(0.3);
  const [v, setV] = useState(0);
  useEffect(() => {
    if (!inView) return;
    let raf, t0;
    const step = (t) => {
      if (!t0) t0 = t;
      const p = Math.min(1, (t - t0) / duration);
      const e = 1 - Math.pow(1 - p, 3);
      setV(to * e);
      if (p < 1) raf = requestAnimationFrame(step);
    };
    raf = requestAnimationFrame(step);
    return () => cancelAnimationFrame(raf);
  }, [inView, to, duration]);
  const shown = decimals
    ? v.toFixed(decimals)
    : Math.round(v).toLocaleString('en-IN');
  return <span ref={ref} className={`num ${className}`}>{prefix}{shown}{suffix}</span>;
}

/* ------------------------------------------------------------------
   Confidence colour scale
------------------------------------------------------------------ */
export function confColor(c) {
  if (c >= 85) return '#35dfa0';
  if (c >= 70) return '#35d6ff';
  if (c >= 55) return '#ffb156';
  return '#ff5f70';
}
export function confLabel(c) {
  if (c >= 85) return 'HIGH';
  if (c >= 70) return 'MODERATE';
  if (c >= 55) return 'LOW';
  return 'WEAK';
}

/* ------------------------------------------------------------------
   ConfidenceRing — animated circular indicator
------------------------------------------------------------------ */
export function ConfidenceRing({ value = 0, size = 96, stroke = 6, label = 'CONFIDENCE', showLabel = true, delay = 0 }) {
  const [ref, inView] = useInView(0.3);
  const [v, setV] = useState(0);
  useEffect(() => {
    if (!inView) return;
    const id = setTimeout(() => {
      let raf, t0;
      const step = (t) => {
        if (!t0) t0 = t;
        const p = Math.min(1, (t - t0) / 1500);
        const e = 1 - Math.pow(1 - p, 3);
        setV(value * e);
        if (p < 1) raf = requestAnimationFrame(step);
      };
      raf = requestAnimationFrame(step);
    }, delay);
    return () => clearTimeout(id);
  }, [inView, value, delay]);

  const r = (size - stroke) / 2;
  const c = 2 * Math.PI * r;
  const col = confColor(v);
  const uid = useMemo(() => 'cr' + Math.random().toString(36).slice(2, 8), []);

  return (
    <div ref={ref} style={{ position: 'relative', width: size, height: size, flexShrink: 0 }}>
      <svg width={size} height={size} style={{ transform: 'rotate(-90deg)' }}>
        <defs>
          <linearGradient id={uid} x1="0" y1="0" x2="1" y2="1">
            <stop offset="0%" stopColor={col} stopOpacity="0.55" />
            <stop offset="100%" stopColor={col} />
          </linearGradient>
        </defs>
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="rgba(126,165,224,.12)" strokeWidth={stroke} />
        <circle
          cx={size / 2} cy={size / 2} r={r} fill="none"
          stroke={`url(#${uid})`} strokeWidth={stroke} strokeLinecap="round"
          strokeDasharray={c} strokeDashoffset={c - (c * v) / 100}
          style={{ filter: `drop-shadow(0 0 7px ${col}88)` }}
        />
      </svg>
      <div style={{
        position: 'absolute', inset: 0, display: 'flex', flexDirection: 'column',
        alignItems: 'center', justifyContent: 'center', gap: 1,
      }}>
        <div className="num" style={{ fontSize: size * 0.27, fontWeight: 600, color: col, lineHeight: 1 }}>
          {Math.round(v)}<span style={{ fontSize: size * 0.14, opacity: .7 }}>%</span>
        </div>
        {showLabel && (
          <div className="mono" style={{ fontSize: Math.max(7, size * 0.082), letterSpacing: '.14em', color: 'var(--dim)' }}>
            {label}
          </div>
        )}
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------
   EvidenceBar — labelled score bar
------------------------------------------------------------------ */
export function EvidenceBar({ label, value, tone, delay = 0, hint }) {
  const [ref, inView] = useInView(0.25);

  // A null score means the source produced no evidence — which is different
  // from scoring zero, and must not be drawn as an empty bar that reads as
  // "this evidence is against".
  if (value == null) {
    return (
      <div ref={ref} className="stack gap-6" title="This source had nothing to compare on one or both records.">
        <div className="kv">
          <span className="k">{label}</span>
          <span className="mono" style={{ fontSize: 10, color: 'var(--faint)', letterSpacing: '.1em' }}>
            NO DATA
          </span>
        </div>
        <div className="meter" style={{ background: 'transparent', border: '1px dashed rgba(126,165,224,.22)', height: 4 }} />
      </div>
    );
  }

  const col = tone || confColor(value);
  return (
    <div ref={ref} className="stack gap-6" title={hint}>
      <div className="kv">
        <span className="k">{label}</span>
        <span className="v" style={{ color: col }}>{value}%</span>
      </div>
      <div className="meter">
        <i style={{
          width: inView ? `${value}%` : 0,
          transitionDelay: `${delay}ms`,
          background: `linear-gradient(90deg, ${col}66, ${col})`,
          boxShadow: `0 0 10px -2px ${col}`,
        }} />
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------
   Sparkline
------------------------------------------------------------------ */
export function Sparkline({ data = [], color = '#35d6ff', w = 74, h = 24 }) {
  const min = Math.min(...data), max = Math.max(...data);
  const span = max - min || 1;
  const pts = data.map((d, i) => [ (i / (data.length - 1)) * w, h - ((d - min) / span) * (h - 3) - 1.5 ]);
  const path = pts.map((p, i) => `${i ? 'L' : 'M'}${p[0].toFixed(1)},${p[1].toFixed(1)}`).join(' ');
  const area = `${path} L${w},${h} L0,${h} Z`;
  const uid = useMemo(() => 'sp' + Math.random().toString(36).slice(2, 8), []);
  return (
    <svg width={w} height={h} style={{ display: 'block', overflow: 'visible' }}>
      <defs>
        <linearGradient id={uid} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity=".28" />
          <stop offset="100%" stopColor={color} stopOpacity="0" />
        </linearGradient>
      </defs>
      <path d={area} fill={`url(#${uid})`} />
      <path d={path} fill="none" stroke={color} strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
      <circle cx={pts[pts.length - 1][0]} cy={pts[pts.length - 1][1]} r="2.2" fill={color}
              style={{ filter: `drop-shadow(0 0 5px ${color})` }} />
    </svg>
  );
}

/* ------------------------------------------------------------------
   Badge
------------------------------------------------------------------ */
const BADGE_TONE = {
  'HIGH PRIORITY': 'badge-red',
  'ACTIVE': 'badge-cyan',
  'MATCH FOUND': 'badge-green',
  'UNDER REVIEW': 'badge-amber',
  'UNIDENTIFIED': 'badge-violet',
};
export function Badge({ children, tone, dot = false, className = '' }) {
  const cls = tone ? `badge-${tone}` : (BADGE_TONE[children] || 'badge-gray');
  return (
    <span className={`badge ${cls} ${className}`}>
      {dot && <i className="dot pulse-dot" />}
      {children}
    </span>
  );
}

/* ------------------------------------------------------------------
   Tooltip — lightweight hover popover
------------------------------------------------------------------ */
export function Tip({ children, content, side = 'top', width = 240 }) {
  const [on, setOn] = useState(false);
  return (
    <span
      style={{ position: 'relative', display: 'inline-flex' }}
      onMouseEnter={() => setOn(true)} onMouseLeave={() => setOn(false)}
      onFocus={() => setOn(true)} onBlur={() => setOn(false)}
    >
      {children}
      {on && (
        <span style={{
          position: 'absolute', zIndex: 60, width,
          [side === 'top' ? 'bottom' : 'top']: 'calc(100% + 9px)',
          left: '50%', transform: 'translateX(-50%)',
          background: 'rgba(10,17,30,.97)', border: '1px solid var(--line-2)',
          borderRadius: 10, padding: '9px 11px', fontSize: 11.5, lineHeight: 1.5,
          color: 'var(--text-2)', boxShadow: 'var(--shadow-2)',
          backdropFilter: 'blur(10px)', pointerEvents: 'none',
          animation: 'scaleIn .16s var(--ease-out)',
        }}>{content}</span>
      )}
    </span>
  );
}

/* ------------------------------------------------------------------
   HumanLoop notice — repeated across the product
------------------------------------------------------------------ */
export function HumanLoopNotice({ compact = false }) {
  return (
    <div className="row gap-10" style={{
      padding: compact ? '8px 12px' : '12px 15px',
      borderRadius: 10,
      background: 'linear-gradient(90deg, rgba(255,177,86,.11), rgba(255,177,86,.03))',
      border: '1px solid rgba(255,177,86,.26)',
    }}>
      <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="#ffb156" strokeWidth="2"
           strokeLinecap="round" strokeLinejoin="round" style={{ flexShrink: 0 }}>
        <path d="M12 9v4M12 17h.01M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" />
      </svg>
      <div className="grow">
        <div className="mono" style={{ fontSize: 10, letterSpacing: '.15em', color: '#ffc98a', fontWeight: 600 }}>
          AI PRIORITISATION · OFFICER VERIFICATION REQUIRED
        </div>
        {!compact && (
          <div style={{ fontSize: 11.5, color: 'var(--muted)', marginTop: 3 }}>
            Ranked output is decision support only. Nothing on this screen constitutes a confirmed identification.
          </div>
        )}
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------
   StageChip — small labelled pill
------------------------------------------------------------------ */
export function Field({ label, children }) {
  return (
    <div className="field">
      <span className="label">{label}</span>
      {children}
    </div>
  );
}

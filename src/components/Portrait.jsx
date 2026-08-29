import { useMemo } from 'react';

/* Deterministic pseudo-random from an integer seed */
function rng(seed) {
  let s = seed * 9301 + 49297;
  return () => { s = (s * 9301 + 49297) % 233280; return s / 233280; };
}

/**
 * Portrait — an abstract, anonymised subject rendering.
 * Intentionally not a photograph: the platform handles real biometric
 * imagery, and a demonstration build should never display invented faces.
 * Optional landmark overlay represents the facial-embedding stage.
 */
export default function Portrait({
  seed = 1, size = 96, landmarks = false, quality, radius = 12, className = '', tone,
}) {
  const uid = useMemo(() => 'p' + seed + Math.random().toString(36).slice(2, 6), [seed]);
  const r = useMemo(() => rng(seed), [seed]);
  const g = useMemo(() => {
    const headW = 25 + r() * 9;
    const headH = 32 + r() * 9;
    const cy = 38 + r() * 5;
    const shoulder = 24 + r() * 10;
    const hair = 0.24 + r() * 0.3;
    const base = tone === 'candidate' ? 258 : 202;
    const hue = base + (r() - 0.5) * 34;
    const w = headW, h = headH;
    const head =
      `M${50 - w / 2},${cy - h / 6} ` +
      `C${50 - w / 2},${cy - h / 2 - 2} ${50 + w / 2},${cy - h / 2 - 2} ${50 + w / 2},${cy - h / 6} ` +
      `C${50 + w / 2},${cy + h / 3} ${50 + w / 4},${cy + h / 2} 50,${cy + h / 2} ` +
      `C${50 - w / 4},${cy + h / 2} ${50 - w / 2},${cy + h / 3} ${50 - w / 2},${cy - h / 6} Z`;
    const cap =
      `M${50 - w / 2},${cy - h / 6 + h * hair} ` +
      `C${50 - w / 2},${cy - h / 2 - 3} ${50 + w / 2},${cy - h / 2 - 3} ${50 + w / 2},${cy - h / 6 + h * hair} ` +
      `C${50 + w / 3},${cy - h / 6 + h * hair - 4} ${50 - w / 3},${cy - h / 6 + h * hair - 4} ${50 - w / 2},${cy - h / 6 + h * hair} Z`;
    const pts = Array.from({ length: 9 }, () => [
      50 + (r() - 0.5) * headW * 1.15,
      cy + (r() - 0.5) * headH * 1.0,
    ]);
    return { headW, headH, cy, shoulder, hue, pts, head, cap };
  }, [r, tone]);

  return (
    <div className={className} style={{
      position: 'relative', width: size,
      ...(typeof size === 'number' ? { height: size } : { aspectRatio: '1 / 1' }),
      flexShrink: 0,
      borderRadius: radius, overflow: 'hidden',
      border: '1px solid var(--line-2)',
      background: 'linear-gradient(160deg, #16233c, #0a1120)',
    }}>
      <svg viewBox="0 0 100 100" width="100%" height="100%" style={{ display: 'block' }}>
        <defs>
          <linearGradient id={`${uid}-b`} x1="0" y1="0" x2="0.7" y2="1">
            <stop offset="0%" stopColor={`hsl(${g.hue} 42% 26%)`} />
            <stop offset="100%" stopColor={`hsl(${g.hue + 12} 48% 11%)`} />
          </linearGradient>
          <linearGradient id={`${uid}-f`} x1="0.2" y1="0" x2="0.9" y2="1">
            <stop offset="0%" stopColor={`hsl(${g.hue - 6} 40% 62%)`} stopOpacity=".85" />
            <stop offset="60%" stopColor={`hsl(${g.hue} 45% 40%)`} stopOpacity=".8" />
            <stop offset="100%" stopColor={`hsl(${g.hue + 10} 50% 22%)`} stopOpacity=".9" />
          </linearGradient>
          <radialGradient id={`${uid}-v`} cx="50%" cy="34%" r="72%">
            <stop offset="55%" stopColor="#000" stopOpacity="0" />
            <stop offset="100%" stopColor="#000" stopOpacity=".55" />
          </radialGradient>
          <pattern id={`${uid}-g`} width="10" height="10" patternUnits="userSpaceOnUse">
            <path d="M10 0H0V10" fill="none" stroke="rgba(126,180,235,.13)" strokeWidth=".5" />
          </pattern>
        </defs>

        <rect width="100" height="100" fill={`url(#${uid}-b)`} />
        <rect width="100" height="100" fill={`url(#${uid}-g)`} />

        {/* shoulders */}
        <path
          d={`M ${50 - g.shoulder * 1.5} 100 Q 50 ${100 - g.shoulder} ${50 + g.shoulder * 1.5} 100 Z`}
          fill={`url(#${uid}-f)`} opacity=".92"
        />
        {/* neck */}
        <rect x={50 - g.headW * 0.2} y={g.cy + g.headH / 2 - 5} width={g.headW * 0.4} height="16" rx="4"
              fill={`url(#${uid}-f)`} opacity=".78" />
        {/* head + hair */}
        <path d={g.head} fill={`url(#${uid}-f)`} />
        <path d={g.cap} fill={`hsl(${g.hue + 14} 46% 15%)`} opacity=".72" />

        <rect width="100" height="100" fill={`url(#${uid}-v)`} />

        {landmarks && (
          <g>
            {g.pts.map((p, i) => (
              <g key={i}>
                {i > 0 && (
                  <line x1={g.pts[i - 1][0]} y1={g.pts[i - 1][1]} x2={p[0]} y2={p[1]}
                        stroke="rgba(53,214,255,.45)" strokeWidth=".45" />
                )}
                <circle cx={p[0]} cy={p[1]} r="1.15" fill="#35d6ff" opacity=".95" />
              </g>
            ))}
            <ellipse cx="50" cy={g.cy} rx={g.headW / 2 + 3} ry={g.headH / 2 + 3}
                     fill="none" stroke="rgba(53,214,255,.35)" strokeWidth=".55" strokeDasharray="3 3" />
          </g>
        )}

        {/* reticle corners */}
        <g stroke="rgba(126,180,235,.34)" strokeWidth=".8" fill="none">
          <path d="M4 12V4h8" /><path d="M88 4h8v8" /><path d="M96 88v8h-8" /><path d="M12 96H4v-8" />
        </g>
      </svg>

      {typeof quality === 'number' && (
        <div className="mono" style={{
          position: 'absolute', left: 5, bottom: 5,
          fontSize: 8.5, letterSpacing: '.08em', padding: '2px 5px', borderRadius: 4,
          background: 'rgba(4,8,16,.78)', border: '1px solid var(--line)',
          color: quality >= 0.85 ? '#7cecc0' : quality >= 0.7 ? '#8ce6ff' : '#ffc98a',
        }}>
          Q {quality.toFixed(2)}
        </div>
      )}
    </div>
  );
}

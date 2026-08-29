import { useMemo } from 'react';
import IndiaMap, { project } from './IndiaMap';

const CITIES = [
  { lon: 77.2090, lat: 28.6139, k: 'm' },  // New Delhi
  { lon: 73.8567, lat: 18.5204, k: 'm' },  // Pune
  { lon: 79.0882, lat: 21.1458, k: 'u' },  // Nagpur
  { lon: 77.5946, lat: 12.9716, k: 'm' },  // Bengaluru
  { lon: 78.4867, lat: 17.3850, k: 'u' },  // Hyderabad
  { lon: 80.2707, lat: 13.0827, k: 'u' },  // Chennai
  { lon: 85.1376, lat: 25.5941, k: 'm' },  // Patna
  { lon: 80.6480, lat: 16.5062, k: 'u' },  // Vijayawada
  { lon: 88.3639, lat: 22.5726, k: 'm' },  // Kolkata
  { lon: 76.2673, lat:  9.9312, k: 'u' },  // Kochi
  { lon: 72.5714, lat: 23.0225, k: 'm' },  // Ahmedabad
  { lon: 91.7362, lat: 26.1445, k: 'u' },  // Guwahati
];
const NODES = CITIES.map((c) => ({ ...c, ...project(c.lon, c.lat) }));
const ARCS = [[3, 5], [1, 2], [0, 6], [4, 9], [10, 1], [7, 8], [11, 8]];

export default function HeroVisual() {
  const vec = useMemo(() => Array.from({ length: 28 }, (_, i) => 18 + ((Math.sin(i * 1.7) + 1) / 2) * 78), []);

  const arc = (a, b) => {
    const A = NODES[a], B = NODES[b];
    const mx = (A.x + B.x) / 2, my = (A.y + B.y) / 2;
    const dx = B.x - A.x, dy = B.y - A.y;
    const len = Math.hypot(dx, dy);
    const cx = mx - dy * 0.26, cy = my + dx * 0.26;
    return { d: `M${A.x},${A.y} Q${cx},${cy} ${B.x},${B.y}`, len };
  };

  return (
    <div className="anim-4" style={{ position: 'relative' }}>
      <div className="panel ticked scanbox" style={{
        padding: 0, overflow: 'hidden', borderRadius: 22,
        aspectRatio: '1 / 1.02',
      }}>
        <i className="scanline" />

        {/* frame chrome */}
        <div className="row between" style={{
          padding: '11px 14px', borderBottom: '1px solid var(--line)',
          background: 'rgba(6,11,20,.5)', position: 'relative', zIndex: 3,
        }}>
          <span className="eyebrow hot">LIVE INDEX · CROSS-STATE</span>
          <span className="row gap-8">
            <span className="badge badge-cyan"><i className="dot pulse-dot" />12,482 RECORDS</span>
          </span>
        </div>

        <svg viewBox="0 0 100 100" style={{ position: 'absolute', inset: 0, width: '100%', height: '100%' }}>
          <defs>
            <radialGradient id="hg" cx="40%" cy="52%" r="55%">
              <stop offset="0%" stopColor="rgba(53,214,255,.16)" />
              <stop offset="100%" stopColor="transparent" />
            </radialGradient>
            <linearGradient id="arcg" x1="0" y1="0" x2="1" y2="1">
              <stop offset="0%" stopColor="rgba(53,214,255,.05)" />
              <stop offset="50%" stopColor="rgba(53,214,255,.7)" />
              <stop offset="100%" stopColor="rgba(120,140,255,.1)" />
            </linearGradient>
            <pattern id="hgrid" width="6" height="6" patternUnits="userSpaceOnUse">
              <path d="M6 0H0V6" fill="none" stroke="rgba(126,165,224,.09)" strokeWidth=".25" />
            </pattern>
          </defs>

          <rect width="100" height="100" fill="url(#hgrid)" />
          <rect width="100" height="100" fill="url(#hg)" />

          {/* latitude arcs */}
          <g stroke="rgba(126,165,224,.11)" strokeWidth=".22" fill="none">
            {[18, 34, 50, 66, 82].map((y) => (
              <path key={y} d={`M2,${y} Q50,${y - 5} 98,${y}`} />
            ))}
          </g>

          <g transform="translate(11.5,9.5) scale(0.84)">
            <IndiaMap states fill="rgba(30,84,138,.2)" stroke="rgba(130,190,245,.4)" />
            {/* connection arcs */}
            {ARCS.map(([a, b], i) => {
              const { d, len } = arc(a, b);
              return (
                <g key={i}>
                  <path d={d} fill="none" stroke="url(#arcg)" strokeWidth=".45" strokeLinecap="round"
                        strokeDasharray={len * 1.3} strokeDashoffset={len * 1.3}
                        style={{ animation: `drawArc 1.6s ${0.9 + i * 0.16}s var(--ease-out) forwards` }} />
                  <circle r=".85" fill="#35d6ff" opacity=".95">
                    <animateMotion dur={`${3.6 + i * 0.4}s`} repeatCount="indefinite" begin={`${1.4 + i * 0.3}s`} path={d} />
                    <animate attributeName="opacity" values="0;1;1;0" dur={`${3.6 + i * 0.4}s`} repeatCount="indefinite" begin={`${1.4 + i * 0.3}s`} />
                  </circle>
                </g>
              );
            })}
            {/* nodes */}
            {NODES.map((n, i) => {
              const col = n.k === 'm' ? '#35d6ff' : '#8b7dff';
              return (
                <g key={i} style={{ animation: `fadeIn .5s ${0.5 + i * 0.06}s both` }}>
                  <circle cx={n.x} cy={n.y} r="2.6" fill="none" stroke={col} strokeWidth=".28" opacity=".5">
                    <animate attributeName="r" values="1.4;4.2" dur="3.4s" repeatCount="indefinite" begin={`${i * 0.28}s`} />
                    <animate attributeName="opacity" values=".65;0" dur="3.4s" repeatCount="indefinite" begin={`${i * 0.28}s`} />
                  </circle>
                  <circle cx={n.x} cy={n.y} r="1.05" fill={col} style={{ filter: `drop-shadow(0 0 2px ${col})` }} />
                </g>
              );
            })}
          </g>
        </svg>

        {/* overlay: embedding card */}
        <div className="panel" style={{
          position: 'absolute', top: 66, right: 16, width: 176, padding: 12, zIndex: 4,
          animation: 'fadeUp .8s .95s var(--ease-out) both, floatY 8s 2s ease-in-out infinite',
        }}>
          <div className="eyebrow" style={{ fontSize: 9 }}>FACIAL EMBEDDING</div>
          <div className="vecbar mt-8">
            {vec.map((v, i) => (
              <span key={i} style={{ height: `${v}%`, animationDelay: `${1.2 + i * 0.02}s`, opacity: 0.35 + v / 220 }} />
            ))}
          </div>
          <div className="row between mt-8">
            <span className="mono" style={{ fontSize: 9, color: 'var(--dim)' }}>512-D</span>
            <span className="mono" style={{ fontSize: 9, color: '#7cecc0' }}>GENERATED</span>
          </div>
        </div>

        {/* overlay: ranking card */}
        <div className="panel" style={{
          position: 'absolute', left: 16, bottom: 16, width: 208, padding: 13, zIndex: 4,
          animation: 'fadeUp .8s 1.25s var(--ease-out) both',
        }}>
          <div className="row between">
            <span className="eyebrow" style={{ fontSize: 9 }}>TOP CANDIDATE</span>
            <span className="mono" style={{ fontSize: 9, color: 'var(--dim)' }}>#01</span>
          </div>
          <div className="row gap-10 mt-8" style={{ alignItems: 'baseline' }}>
            <span className="num" style={{ fontSize: 27, fontWeight: 600, color: '#35dfa0' }}>92<span style={{ fontSize: 14, opacity: .7 }}>%</span></span>
            <span className="mono" style={{ fontSize: 9, letterSpacing: '.14em', color: 'var(--dim)' }}>CONFIDENCE</span>
          </div>
          <div className="stack gap-6 mt-8">
            {[['Face', 94, '#35d6ff'], ['Marks', 89, '#8b7dff'], ['Demographic', 91, '#35dfa0']].map(([l, v, c], i) => (
              <div key={l}>
                <div className="kv"><span className="k" style={{ fontSize: 10 }}>{l}</span><span className="v" style={{ fontSize: 10.5 }}>{v}%</span></div>
                <div className="meter" style={{ marginTop: 3 }}>
                  <i style={{ width: `${v}%`, background: c, animation: `growW 1s ${1.5 + i * 0.15}s var(--ease-out) both` }} />
                </div>
              </div>
            ))}
          </div>
          <div className="mono" style={{
            fontSize: 8.5, letterSpacing: '.1em', color: '#ffc98a', marginTop: 10,
            paddingTop: 8, borderTop: '1px solid var(--line)',
          }}>
            ⚠ OFFICER VERIFICATION REQUIRED
          </div>
        </div>
      </div>

      <style>{`@keyframes drawArc { to { stroke-dashoffset: 0; } }`}</style>
    </div>
  );
}

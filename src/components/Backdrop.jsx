import { useMemo } from 'react';

/* Faint contour / node field sitting behind the whole application. */
export default function Backdrop() {
  const { nodes, links, contours } = useMemo(() => {
    let s = 4242;
    const rand = () => { s = (s * 9301 + 49297) % 233280; return s / 233280; };
    const nodes = Array.from({ length: 26 }, (_, i) => ({
      id: i, x: rand() * 100, y: rand() * 100, r: 0.55 + rand() * 1.1, d: rand() * 6,
    }));
    const links = [];
    nodes.forEach((a, i) => {
      nodes.slice(i + 1).forEach((b) => {
        const dx = a.x - b.x, dy = (a.y - b.y) * 0.55;
        if (Math.hypot(dx, dy) < 15) links.push([a, b]);
      });
    });
    const contours = Array.from({ length: 6 }, (_, i) => {
      const y = 12 + i * 15;
      const pts = Array.from({ length: 9 }, (_, j) => `${j * 12.5},${(y + Math.sin(j * 0.9 + i) * 6).toFixed(1)}`);
      return `M ${pts.join(' L ')}`;
    });
    return { nodes, links, contours };
  }, []);

  return (
    <div className="backdrop" aria-hidden="true">
      <svg viewBox="0 0 100 100" preserveAspectRatio="none" style={{ opacity: 0.5 }}>
        <g stroke="rgba(90,150,220,.16)" strokeWidth="0.12" fill="none">
          {contours.map((d, i) => <path key={i} d={d} />)}
        </g>
      </svg>
      <svg viewBox="0 0 100 100" preserveAspectRatio="none">
        <g stroke="rgba(53,214,255,.10)" strokeWidth="0.07">
          {links.map(([a, b], i) => <line key={i} x1={a.x} y1={a.y} x2={b.x} y2={b.y} />)}
        </g>
        <g fill="rgba(53,214,255,.5)">
          {nodes.map((n) => (
            <circle key={n.id} cx={n.x} cy={n.y} r={n.r * 0.16}>
              <animate attributeName="opacity" values="0.15;0.75;0.15" dur={`${5 + n.d}s`}
                       repeatCount="indefinite" begin={`${n.d}s`} />
            </circle>
          ))}
        </g>
      </svg>
    </div>
  );
}

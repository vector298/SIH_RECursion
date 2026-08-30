import {
  TrendingUp, TrendingDown, UserSearch, ScanFace, GitCompareArrows,
  TriangleAlert, ShieldCheck, Timer, Activity,
} from 'lucide-react';
import { Counter, Sparkline } from './ui';

const ICONS = { UserSearch, ScanFace, GitCompareArrows, TriangleAlert, ShieldCheck, Timer, Activity };

const TONES = {
  cyan:   { solid: '#35d6ff', line: 'rgba(53,214,255,.32)',  glow: 'rgba(53,214,255,.14)' },
  violet: { solid: '#8b7dff', line: 'rgba(139,125,255,.32)', glow: 'rgba(139,125,255,.14)' },
  red:    { solid: '#ff5f70', line: 'rgba(255,95,112,.32)',  glow: 'rgba(255,95,112,.13)' },
  green:  { solid: '#35dfa0', line: 'rgba(53,223,160,.32)',  glow: 'rgba(53,223,160,.13)' },
  amber:  { solid: '#ffb156', line: 'rgba(255,177,86,.32)',  glow: 'rgba(255,177,86,.14)' },
};

export default function MetricCard({ metric, delay = 0 }) {
  const t = TONES[metric.tone] || TONES.cyan;
  const Icon = ICONS[metric.icon] || Activity;
  const up = (metric.trend ?? 0) >= 0;
  // For investigation time, a fall is the good direction.
  const good = metric.id === 'avgtime' || metric.id === 'high' ? !up : up;
  const trendCol = good ? '#35dfa0' : '#ff8e9b';

  return (
    <div className="metric" style={{
      '--tone-solid': t.solid, '--tone-line': t.line, '--tone-glow': t.glow,
      animation: `fadeUp .6s ${delay}ms var(--ease-out) both`,
    }}>
      <div style={{ position: 'relative', zIndex: 1 }}>
        <div className="row between">
          <span className="mi"><Icon size={15} strokeWidth={1.9} /></span>
          {/* A sparkline next to a live count would imply a history the system
              does not yet record. Absent data draws nothing. */}
          {metric.spark ? <Sparkline data={metric.spark} color={t.solid} w={58} h={20} /> : null}
        </div>
        <div className="mv mt-12">
          {metric.value == null
            ? <span className="num" style={{ color: 'var(--faint)' }}>—</span>
            : <Counter to={metric.value} suffix={metric.suffix || ''} duration={1500 + delay} />}
        </div>
        <div className="row between mt-8" style={{ alignItems: 'flex-end', gap: 8 }}>
          <span className="ml">{metric.label}</span>
          {metric.trend != null ? (
            <span className="trend" style={{ color: trendCol, flexShrink: 0 }}>
              {up ? <TrendingUp size={11} strokeWidth={2.2} /> : <TrendingDown size={11} strokeWidth={2.2} />}
              {Math.abs(metric.trend).toFixed(1)}%
            </span>
          ) : metric.note ? (
            <span className="mono" style={{ fontSize: 9, color: 'var(--faint)', letterSpacing: '.1em', flexShrink: 0 }}>
              {metric.note}
            </span>
          ) : null}
        </div>
      </div>
    </div>
  );
}

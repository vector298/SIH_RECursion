import { Plus, ArrowRight, Radar, CircleHelp, Clock3, Database } from 'lucide-react';
import { METRICS, CASES, TIMELINE } from '../data/sample';
import MetricCard from '../components/MetricCard';
import CaseCard from '../components/CaseCard';
import { Reveal, Badge, HumanLoopNotice, ConfidenceRing } from '../components/ui';

export default function Dashboard({ go }) {
  const active = CASES.slice(0, 4);

  return (
    <div className="stack gap-32">
      {/* header */}
      <div className="row between wrap gap-16">
        <div>
          <span className="eyebrow hot">COMMAND CENTER</span>
          <h1 className="page-title mt-8">Investigation Command Center</h1>
          <p className="page-sub">Cross-state case intelligence and AI-assisted matching.</p>
        </div>
        <div className="row gap-10 wrap">
          <button className="btn" onClick={() => go('match')}>
            <Radar size={15} strokeWidth={2} /> Run matching
          </button>
          <button className="btn btn-primary" onClick={() => go('newcase')}>
            <Plus size={15} strokeWidth={2.4} /> New case
          </button>
        </div>
      </div>

      {/* metrics */}
      <div className="metric-grid">
        {METRICS.map((m, i) => <MetricCard key={m.id} metric={m} delay={i * 70} />)}
      </div>

      {/* main split */}
      <div className="dash-split">
        <div className="stack gap-16">
          <div className="row between wrap gap-12">
            <span className="section-title">Active Investigations</span>
            <button className="btn btn-sm btn-ghost" onClick={() => go('cases')}>
              View all cases <ArrowRight size={13} strokeWidth={2.2} />
            </button>
          </div>
          <div className="case-grid">
            {active.map((c, i) => <CaseCard key={c.id} c={c} go={go} delay={i * 80} />)}
          </div>
        </div>

        <aside className="stack gap-16 dash-rail">
          <Reveal>
            <div className="panel ticked panel-pad stack gap-14">
              <div className="row between">
                <span className="section-title" style={{ fontSize: 12 }}>Needs your decision</span>
                <Badge tone="amber" dot>2 OPEN</Badge>
              </div>

              <div className="stack gap-10" style={{
                padding: 13, borderRadius: 11, border: '1px solid rgba(255,177,86,.24)',
                background: 'linear-gradient(160deg, rgba(255,177,86,.09), rgba(255,177,86,.02))',
              }}>
                <div className="row gap-8">
                  <CircleHelp size={14} strokeWidth={2} color="#ffb156" />
                  <span className="mono" style={{ fontSize: 9.5, letterSpacing: '.14em', color: '#ffc98a' }}>
                    ADAPTIVE INVESTIGATION
                  </span>
                </div>
                <div style={{ fontSize: 12.5, lineHeight: 1.55 }}>
                  Two candidates on <span className="mono" style={{ color: 'var(--cyan)' }}>CASE-2026-0147</span> are
                  within 3 confidence points. A targeted question can separate them.
                </div>
                <button className="btn btn-sm" style={{ alignSelf: 'flex-start' }}
                        onClick={() => go('compare', { id: 'CASE-2026-0304' })}>
                  Answer question <ArrowRight size={12} strokeWidth={2.4} />
                </button>
              </div>

              <div className="row gap-14" style={{ padding: '4px 2px' }}>
                <ConfidenceRing value={92} size={74} stroke={5} label="TOP" />
                <div className="stack gap-6 grow">
                  <div className="mono" style={{ fontSize: 10.5, color: 'var(--cyan)' }}>CASE-2026-0147</div>
                  <div style={{ fontSize: 12, color: 'var(--muted)', lineHeight: 1.5 }}>
                    6 candidates ranked. Highest-confidence lead awaiting physical verification.
                  </div>
                  <button className="btn btn-sm btn-ghost" style={{ alignSelf: 'flex-start' }}
                          onClick={() => go('match', { id: 'CASE-2026-0147' })}>
                    Review ranking
                  </button>
                </div>
              </div>

              <HumanLoopNotice compact />
            </div>
          </Reveal>

          <Reveal delay={90}>
            <div className="panel panel-pad stack gap-12">
              <span className="section-title" style={{ fontSize: 12 }}>Index status</span>
              {[
                ['National record index', '12,482', Database, '#35d6ff'],
                ['Unidentified persons', '3,096', Database, '#8b7dff'],
                ['Bureaus synchronised', '28 / 28', Clock3, '#35dfa0'],
                ['Last full re-rank', '11 min ago', Clock3, '#7d90ae'],
              ].map(([l, v, Icon, c]) => (
                <div className="kv" key={l}>
                  <span className="k row gap-7"><Icon size={11} strokeWidth={2} color={c} /> {l}</span>
                  <span className="v" style={{ color: c }}>{v}</span>
                </div>
              ))}
            </div>
          </Reveal>

          <Reveal delay={160}>
            <div className="panel panel-pad stack gap-12">
              <span className="section-title" style={{ fontSize: 12 }}>Recent activity</span>
              <div className="tl" style={{ paddingLeft: 22 }}>
                {TIMELINE.slice(-4).reverse().map((t) => (
                  <div key={t.title} className="tl-item" data-pending={!!t.pending}
                       style={{ '--tl-c': { cyan: '#35d6ff', violet: '#8b7dff', amber: '#ffb156', green: '#35dfa0', gray: '#7d90ae' }[t.tone], paddingBottom: 14 }}>
                    <div style={{ fontSize: 12.5, fontWeight: 500 }}>{t.title}</div>
                    <div className="mono" style={{ fontSize: 9.5, color: 'var(--faint)', marginTop: 2 }}>{t.t}</div>
                  </div>
                ))}
              </div>
            </div>
          </Reveal>
        </aside>
      </div>
    </div>
  );
}

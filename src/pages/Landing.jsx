import { useRef } from 'react';
import { ArrowRight, ChevronDown, Layers, Filter, ScanFace, Scale, UserCheck } from 'lucide-react';
import HeroVisual from '../components/HeroVisual';
import { Logo } from '../components/TopNav';
import { Reveal } from '../components/ui';

const STEPS = [
  { n: '01', Icon: Layers, t: 'Centralised index', d: 'Missing and unidentified person records from every state bureau in one uncertainty-aware schema — exact values, ranges and unknowns all first-class.' },
  { n: '02', Icon: Filter, t: 'Hard search first', d: 'Cheap deterministic filters cut 12,482 records to a few hundred before any model runs, so expensive comparison happens only where it can matter.' },
  { n: '03', Icon: ScanFace, t: 'Multi-source evidence', d: 'Semantic comparison of free-text identification marks, facial embeddings, demographic intervals and time-aware age reasoning — each scored separately.' },
  { n: '04', Icon: Scale, t: 'Quality-weighted fusion', d: 'Image quality down-weights facial evidence it cannot support. Missing fields stay neutral instead of eliminating a candidate.' },
  { n: '05', Icon: UserCheck, t: 'The officer decides', d: 'The system ranks and explains. When candidates are close it asks a targeted question. It never asserts an identification.' },
];

export default function Landing({ go }) {
  const hiwRef = useRef(null);

  return (
    <div style={{ position: 'relative', zIndex: 1 }}>
      <div className="landing-brand">
        <Logo size={24} />
        <span className="mono" style={{ fontSize: 13, fontWeight: 600 }}>
          CASE<span style={{ color: 'var(--cyan)' }}>//</span>INTEL
        </span>
        <span className="badge badge-gray" style={{ marginLeft: 8 }}>RESTRICTED · DEMONSTRATION BUILD</span>
      </div>

      <section className="landing">
        <div className="stack gap-24">
          <div className="anim-1 row gap-10">
            <span className="badge badge-cyan"><i className="dot pulse-dot" />NATIONAL CASE INDEX ONLINE</span>
          </div>

          <div className="stack gap-16">
            <h1 className="hero-title anim-1">CASE<br />INTELLIGENCE</h1>
            <div className="hero-rule anim-2" />
            <p className="hero-sub anim-2">
              AI-assisted intelligence for missing and unidentified person investigations.
            </p>
          </div>

          <p className="hero-support anim-3">
            Centralize cases. Resolve uncertainty. Rank potential matches.<br />Let investigators decide.
          </p>

          <div className="row gap-12 wrap anim-4">
            <button className="btn btn-primary btn-lg" onClick={() => go('dashboard')}>
              Enter Investigation Portal <ArrowRight size={15} strokeWidth={2.2} />
            </button>
            <button className="btn btn-lg btn-ghost"
                    onClick={() => hiwRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })}>
              Explore How It Works <ChevronDown size={15} strokeWidth={2.2} />
            </button>
          </div>

          <div className="hero-stats anim-5 mt-8">
            {[['12,482', 'Records indexed'], ['28', 'State bureaus'], ['1,364', 'Cases resolved'], ['0', 'Automated identifications']].map(([n, l]) => (
              <div className="hero-stat" key={l}>
                <div className="n">{n}</div>
                <div className="l">{l}</div>
              </div>
            ))}
          </div>

          <p className="anim-6" style={{ fontSize: 11.5, color: 'var(--faint)', maxWidth: '52ch', lineHeight: 1.6 }}>
            All case data shown in this build is fictional. The platform produces ranked
            investigative leads for trained officers; it does not confirm identity.
          </p>
        </div>

        <HeroVisual />
      </section>

      <section className="hiw" ref={hiwRef}>
        <Reveal className="stack gap-8" style={{ marginBottom: 26 }}>
          <span className="eyebrow hot">HOW IT WORKS</span>
          <h2 style={{ fontSize: 'clamp(22px,3vw,30px)' }}>From an uncertain report to a ranked, explainable shortlist</h2>
          <p className="page-sub">
            Every stage narrows the search or adds evidence. Nothing is discarded because a field was left blank.
          </p>
        </Reveal>

        <div className="hiw-grid">
          {STEPS.map((s, i) => (
            <Reveal key={s.n} delay={i * 80}>
              <div className="hiw-card hoverable" style={{ height: '100%' }}>
                <div className="row between">
                  <span className="n">{s.n}</span>
                  <s.Icon size={16} strokeWidth={1.8} color="var(--cyan)" />
                </div>
                <div style={{ fontSize: 14.5, fontWeight: 600, marginTop: 12 }}>{s.t}</div>
                <p style={{ fontSize: 12.5, color: 'var(--muted)', marginTop: 7, lineHeight: 1.6 }}>{s.d}</p>
              </div>
            </Reveal>
          ))}
        </div>

        <Reveal delay={120}>
          <div className="panel panel-pad mt-24 row between wrap gap-16">
            <div>
              <div className="eyebrow">READY</div>
              <div style={{ fontSize: 16, fontWeight: 600, marginTop: 4 }}>Open the Investigation Command Center</div>
            </div>
            <button className="btn btn-primary" onClick={() => go('dashboard')}>
              Enter Investigation Portal <ArrowRight size={15} strokeWidth={2.2} />
            </button>
          </div>
        </Reveal>
      </section>
    </div>
  );
}

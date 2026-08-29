import { useMemo } from 'react';
import { ArrowDown, Equal, X as XIcon, Clock, Sigma, ScanFace, Blocks } from 'lucide-react';
import Portrait from '../components/Portrait';
import { Reveal, useInView, EvidenceBar, Badge, Tip } from '../components/ui';

export default function Method() {
  return (
    <div className="stack gap-24 page-enter">
      <Uncertainty />
      <div className="grid" style={{ gridTemplateColumns: 'repeat(auto-fit,minmax(420px,1fr))', gap: 18 }}>
        <Semantic />
        <Facial />
      </div>
      <TimeAware />
    </div>
  );
}

/* ================================================================ */
function Uncertainty() {
  const rows = [
    { k: 'Age', v: '23–27 years', state: 'RANGE', note: 'Interval overlap is scored proportionally — a candidate aged 24–30 scores partial, not zero.' },
    { k: 'Height', v: '165–172 cm', state: 'RANGE', note: 'Wide intervals contribute less evidence than tight ones, but still contribute.' },
    { k: 'Sex', v: 'Female', state: 'EXACT', note: 'Exact categorical values are usable in the hard-search stage as a cheap deterministic filter.' },
    { k: 'Location', v: 'Unknown', state: 'UNKNOWN', note: 'No geographic evidence available. Contributes nothing — and removes nothing.' },
    { k: 'Blood type', v: 'Unknown', state: 'UNKNOWN', note: 'Frequently missing at intake. Treated as absent evidence, never as a mismatch.' },
  ];
  const tone = { EXACT: 'green', RANGE: 'cyan', UNKNOWN: 'gray' };

  return (
    <Reveal>
      <div className="panel ticked panel-pad stack gap-18">
        <div className="row between wrap gap-12">
          <div>
            <span className="section-title"><Blocks size={13} strokeWidth={2} style={{ marginLeft: -2 }} /> Uncertainty-aware data</span>
            <p style={{ fontSize: 13, color: 'var(--muted)', marginTop: 8, maxWidth: '72ch', lineHeight: 1.6 }}>
              Real reports are incomplete. The system does not assume every field is exact — each attribute
              carries its own certainty state, and missing information never automatically eliminates a candidate.
            </p>
          </div>
        </div>

        <div className="grid" style={{ gridTemplateColumns: 'repeat(auto-fit,minmax(230px,1fr))', gap: 13 }}>
          {rows.map((r, i) => (
            <div key={r.k} className="panel flat hoverable" style={{
              padding: 14, animation: `fadeUp .5s ${i * 70}ms var(--ease-out) both`,
              borderColor: r.state === 'UNKNOWN' ? 'rgba(126,165,224,.16)' : undefined,
              borderStyle: r.state === 'UNKNOWN' ? 'dashed' : 'solid',
            }}>
              <div className="row between">
                <span className="label">{r.k}</span>
                <Badge tone={tone[r.state]}>{r.state}</Badge>
              </div>
              <div className="mono mt-12" style={{
                fontSize: 15, color: r.state === 'UNKNOWN' ? 'var(--faint)' : 'var(--text)',
              }}>{r.v}</div>
              <p style={{ fontSize: 11, color: 'var(--dim)', marginTop: 9, lineHeight: 1.55 }}>{r.note}</p>
            </div>
          ))}
        </div>

        <div className="row gap-12 wrap" style={{
          padding: '12px 14px', borderRadius: 11,
          border: '1px solid rgba(53,223,160,.22)', background: 'rgba(53,223,160,.05)',
        }}>
          <span className="badge badge-green">DESIGN RULE</span>
          <span style={{ fontSize: 12.5, color: 'var(--text-2)', flex: 1, minWidth: 260 }}>
            Absence of evidence is not evidence of mismatch. A record with four unknown fields simply carries
            less total evidence — its confidence is lower, but it stays in the ranking.
          </span>
        </div>
      </div>
    </Reveal>
  );
}

/* ================================================================ */
function Semantic() {
  const [ref, inView] = useInView(0.25);
  const vecA = useMemo(() => Array.from({ length: 26 }, (_, i) => 22 + ((Math.sin(i * 1.24) + 1) / 2) * 74), []);
  const vecB = useMemo(() => Array.from({ length: 26 }, (_, i) => 22 + ((Math.sin(i * 1.24 + 0.28) + 1) / 2) * 71), []);

  return (
    <div ref={ref} className="panel ticked panel-pad stack gap-16">
      <div>
        <span className="section-title"><Sigma size={13} strokeWidth={2} style={{ marginLeft: -2 }} /> Semantic free-text matching</span>
        <p style={{ fontSize: 12.5, color: 'var(--muted)', marginTop: 8, lineHeight: 1.6 }}>
          Two officers describing the same scar rarely use the same words. Descriptions are embedded and
          compared in vector space, so wording differences do not cost evidence.
        </p>
      </div>

      <div className="grid" style={{ gridTemplateColumns: '1fr 1fr', gap: 12 }}>
        {[['Description A', 'CASE-2026-0147', '3 cm horizontal scar above the left eyebrow'],
          ['Description B', 'CASE-2026-0304', 'Small linear scar just over the left eyebrow']].map(([t, id, txt], i) => (
          <div key={t} className="panel flat" style={{ padding: 13, animation: inView ? `fadeUp .5s ${i * 130}ms var(--ease-out) both` : 'none', opacity: inView ? 1 : 0 }}>
            <div className="row between">
              <span className="label">{t}</span>
              <span className="mono" style={{ fontSize: 9, color: 'var(--faint)' }}>{id}</span>
            </div>
            <p style={{ fontSize: 12.5, marginTop: 9, lineHeight: 1.55, color: 'var(--text-2)' }}>“{txt}”</p>
          </div>
        ))}
      </div>

      <Flow label="EMBED" />

      <div className="grid" style={{ gridTemplateColumns: '1fr 1fr', gap: 12 }}>
        {[vecA, vecB].map((v, k) => (
          <div key={k} className="panel flat" style={{ padding: 12 }}>
            <div className="row between">
              <span className="embed-chip">768-D</span>
              <span className="mono" style={{ fontSize: 9, color: 'var(--faint)' }}>{k ? 'B' : 'A'}</span>
            </div>
            <div className="vecbar mt-8">
              {v.map((h, i) => (
                <span key={i} style={{
                  height: `${h}%`,
                  animation: inView ? `growBar .6s ${400 + i * 18}ms var(--ease-out) both` : 'none',
                  opacity: inView ? 1 : 0,
                }} />
              ))}
            </div>
          </div>
        ))}
      </div>

      <Flow label="COSINE SIMILARITY" />

      <div className="panel flat" style={{ padding: 15, borderColor: 'rgba(53,214,255,.28)', background: 'rgba(53,214,255,.05)' }}>
        <div className="row between wrap gap-12">
          <div>
            <div className="eyebrow hot">IDENTIFICATION-MARK EVIDENCE</div>
            <div style={{ fontSize: 11.5, color: 'var(--muted)', marginTop: 5 }}>
              cos(θ) = 0.91 · different wording, same mark
            </div>
          </div>
          <div className="num" style={{ fontSize: 30, fontWeight: 600, color: '#35dfa0', lineHeight: 1 }}>
            91<span style={{ fontSize: 15, opacity: .7 }}>%</span>
          </div>
        </div>
        <div className="meter mt-12">
          <i style={{ width: inView ? '91%' : 0, background: 'linear-gradient(90deg,#35dfa066,#35dfa0)', transitionDelay: '900ms' }} />
        </div>
      </div>
    </div>
  );
}

/* ================================================================ */
function Facial() {
  const [ref, inView] = useInView(0.25);
  const faceSim = 94, qA = 92, qB = 81, finalQ = 81;
  const finalEvidence = Math.round((faceSim * finalQ) / 100);

  return (
    <div ref={ref} className="panel ticked panel-pad stack gap-16">
      <div>
        <span className="section-title"><ScanFace size={13} strokeWidth={2} style={{ marginLeft: -2 }} /> Facial comparison & quality weighting</span>
        <p style={{ fontSize: 12.5, color: 'var(--muted)', marginTop: 8, lineHeight: 1.6 }}>
          A high similarity score computed from a blurred, poorly lit photograph is not strong evidence.
          Image quality caps how much the facial stage is allowed to influence the ranking.
        </p>
      </div>

      <div className="row gap-16 wrap center" style={{ padding: '4px 0' }}>
        <div className="stack gap-8" style={{ alignItems: 'center' }}>
          <Portrait seed={147} size={104} landmarks quality={qA / 100} radius={13} />
          <span className="mono" style={{ fontSize: 9.5, color: 'var(--dim)' }}>MISSING PERSON</span>
        </div>
        <div className="stack gap-6" style={{ alignItems: 'center', minWidth: 96 }}>
          <div className="num" style={{ fontSize: 26, fontWeight: 600, color: '#35d6ff', lineHeight: 1 }}>{faceSim}%</div>
          <div className="mono" style={{ fontSize: 9, letterSpacing: '.13em', color: 'var(--dim)' }}>FACE SIMILARITY</div>
          <svg width="96" height="20" style={{ overflow: 'visible', marginTop: 2 }}>
            <line x1="2" y1="10" x2="94" y2="10" stroke="rgba(53,214,255,.4)" strokeWidth="1" strokeDasharray="3 3" />
            <circle r="3" fill="#35d6ff" style={{ filter: 'drop-shadow(0 0 5px #35d6ff)' }}>
              <animate attributeName="cx" values="2;94;2" dur="4s" repeatCount="indefinite" />
              <animate attributeName="cy" values="10;10;10" dur="4s" repeatCount="indefinite" />
            </circle>
          </svg>
        </div>
        <div className="stack gap-8" style={{ alignItems: 'center' }}>
          <Portrait seed={304} size={104} landmarks quality={qB / 100} radius={13} tone="candidate" />
          <span className="mono" style={{ fontSize: 9.5, color: 'var(--dim)' }}>CANDIDATE</span>
        </div>
      </div>

      <div className="stack gap-10">
        <EvidenceBar label="Missing person image quality" value={qA} />
        <EvidenceBar label="Candidate image quality" value={qB} />
      </div>

      <div className="panel flat" style={{ padding: 15 }}>
        <div className="eyebrow">EVIDENCE CALCULATION</div>
        <div className="row gap-12 wrap mt-12" style={{ alignItems: 'center' }}>
          <Calc n={`${faceSim}%`} l="Face similarity" c="#35d6ff" />
          <XIcon size={14} strokeWidth={2.4} color="var(--dim)" />
          <Calc n={`${finalQ}%`} l="Limiting quality" c="#ffb156" />
          <Equal size={14} strokeWidth={2.4} color="var(--dim)" />
          <Calc n={`${finalEvidence}%`} l="Facial evidence" c="#35dfa0" big />
        </div>
        <p style={{ fontSize: 11.5, color: 'var(--dim)', marginTop: 12, lineHeight: 1.6 }}>
          The lower of the two image qualities governs. Low-quality images reduce the influence of facial
          similarity rather than being discarded — the evidence is kept, but weighted honestly.
        </p>
      </div>
    </div>
  );
}

function Calc({ n, l, c, big }) {
  return (
    <div className="stack gap-3" style={{ alignItems: 'center', minWidth: 78 }}>
      <span className="num" style={{ fontSize: big ? 24 : 20, fontWeight: 600, color: c, lineHeight: 1 }}>{n}</span>
      <span className="mono" style={{ fontSize: 8.5, letterSpacing: '.11em', color: 'var(--dim)', textAlign: 'center' }}>{l.toUpperCase()}</span>
    </div>
  );
}

function Flow({ label }) {
  return (
    <div className="row gap-10 center" style={{ padding: '2px 0' }}>
      <span style={{ height: 1, flex: 1, background: 'linear-gradient(90deg,transparent,var(--line-2))' }} />
      <span className="row gap-6 mono" style={{ fontSize: 9, letterSpacing: '.15em', color: 'var(--dim)' }}>
        <ArrowDown size={11} strokeWidth={2.4} /> {label}
      </span>
      <span style={{ height: 1, flex: 1, background: 'linear-gradient(270deg,transparent,var(--line-2))' }} />
    </div>
  );
}

/* ================================================================ */
const YEARS = [2018, 2020, 2022, 2024, 2026];

function TimeAware() {
  const [ref, inView] = useInView(0.2);
  const reportYear = 2019, reportAge = 8, now = 2026;
  const expected = reportAge + (now - reportYear);

  const decay = [
    { k: 'Distinguishing marks', w: 96, note: 'Scars, tattoos and birthmarks are stable — weight is retained almost fully.' },
    { k: 'Facial structure', w: 74, note: 'Bone structure persists, but a child’s face changes substantially over seven years.' },
    { k: 'Height', w: 34, note: 'Dynamic during growth years — weight decays sharply with elapsed time.' },
    { k: 'Build / body type', w: 26, note: 'Highly variable. Contributes little on long-duration cases.' },
    { k: 'Clothing & appearance', w: 9, note: 'Effectively no evidential value seven years after the report.' },
  ];

  return (
    <Reveal>
      <div ref={ref} className="panel ticked panel-pad stack gap-20">
        <div>
          <span className="section-title"><Clock size={13} strokeWidth={2} style={{ marginLeft: -2 }} /> Time-aware matching</span>
          <p style={{ fontSize: 13, color: 'var(--muted)', marginTop: 8, maxWidth: '78ch', lineHeight: 1.6 }}>
            A case filed in 2019 is not searched with 2019 attributes. Age is projected forward, and attributes
            that change with time carry progressively less weight the longer a case stays open.
          </p>
        </div>

        {/* timeline */}
        <div style={{ position: 'relative', padding: '30px 0 8px' }}>
          <div style={{
            position: 'absolute', left: 0, right: 0, top: 52, height: 2, borderRadius: 2,
            background: 'linear-gradient(90deg, rgba(126,165,224,.25), var(--cyan))',
          }} />
          <div className="row between" style={{ position: 'relative' }}>
            {YEARS.map((y, i) => {
              const age = reportAge + (y - reportYear);
              const past = y >= reportYear;
              return (
                <div key={y} className="stack gap-8" style={{
                  alignItems: 'center', flex: 1,
                  animation: inView ? `fadeUp .5s ${i * 110}ms var(--ease-out) both` : 'none',
                  opacity: inView ? 1 : 0,
                }}>
                  <div className="mono" style={{ fontSize: 10, letterSpacing: '.1em', color: past ? 'var(--text-2)' : 'var(--faint)' }}>
                    {past ? `AGE ${age}` : '—'}
                  </div>
                  <span style={{
                    width: y === now ? 13 : 9, height: y === now ? 13 : 9, borderRadius: 99,
                    background: y === now ? '#35d6ff' : past ? 'rgba(53,214,255,.55)' : 'var(--bg-3)',
                    border: '2px solid ' + (past ? 'rgba(53,214,255,.7)' : 'var(--line-2)'),
                    boxShadow: y === now ? '0 0 14px #35d6ff' : 'none',
                  }} />
                  <div className="mono" style={{ fontSize: 11, color: y === now ? 'var(--cyan)' : 'var(--dim)' }}>{y}</div>
                </div>
              );
            })}
          </div>
        </div>

        <div className="grid" style={{ gridTemplateColumns: 'repeat(auto-fit,minmax(280px,1fr))', gap: 16 }}>
          <div className="panel flat" style={{ padding: 15 }}>
            <div className="eyebrow">AGE PROJECTION · CASE-2026-0231</div>
            <div className="row between wrap gap-14 mt-16" style={{ alignItems: 'center' }}>
              <div className="stack gap-3">
                <span className="num" style={{ fontSize: 26, fontWeight: 600 }}>{reportAge}</span>
                <span className="mono" style={{ fontSize: 9, letterSpacing: '.11em', color: 'var(--dim)' }}>REPORTED · {reportYear}</span>
              </div>
              <ArrowDown size={16} strokeWidth={2.2} color="var(--cyan)" style={{ transform: 'rotate(-90deg)' }} />
              <div className="stack gap-3">
                <span className="num" style={{ fontSize: 26, fontWeight: 600, color: 'var(--cyan)' }}>{expected}</span>
                <span className="mono" style={{ fontSize: 9, letterSpacing: '.11em', color: 'var(--dim)' }}>EXPECTED · {now}</span>
              </div>
              <Tip content="Candidate records are compared against the projected age interval, not the age recorded at intake. Without this, every long-duration child case would fail demographic filtering.">
                <span className="badge badge-cyan" style={{ cursor: 'help' }}>CHILD GROWTH ADAPTATION</span>
              </Tip>
            </div>
            <p style={{ fontSize: 11.5, color: 'var(--dim)', marginTop: 14, lineHeight: 1.6 }}>
              The search interval widens with elapsed time to absorb growth variance — an 8-year-old reported
              in 2019 is matched against candidates aged roughly 14–16 today.
            </p>
          </div>

          <div className="panel flat" style={{ padding: 15 }}>
            <div className="row between">
              <span className="eyebrow">ATTRIBUTE WEIGHT AFTER 7 YEARS</span>
              <span className="badge badge-gray">RELATIVE</span>
            </div>
            <div className="stack gap-11 mt-16">
              {decay.map((d, i) => (
                <Tip key={d.k} content={d.note} width={260}>
                  <div style={{ width: '100%' }}>
                    <EvidenceBar label={d.k} value={d.w} delay={i * 90}
                                 tone={d.w > 70 ? '#35dfa0' : d.w > 30 ? '#ffb156' : '#ff5f70'} />
                  </div>
                </Tip>
              ))}
            </div>
          </div>
        </div>
      </div>
    </Reveal>
  );
}

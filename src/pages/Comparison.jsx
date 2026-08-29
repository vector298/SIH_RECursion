import { useState } from 'react';
import {
  ArrowLeft, Check, X, FileQuestion, Sparkles, ShieldAlert, CircleHelp,
  TrendingUp, TrendingDown, Minus, Info,
} from 'lucide-react';
import { CASES, CANDIDATES } from '../data/sample';
import Portrait from '../components/Portrait';
import {
  ConfidenceRing, EvidenceBar, Badge, HumanLoopNotice, Reveal, confColor, confLabel, Tip,
} from '../components/ui';

const EVIDENCE_ROWS = [
  { k: 'face', label: 'FACIAL EVIDENCE', hint: 'Cosine similarity between face embeddings, capped by the lower of the two image-quality scores.' },
  { k: 'marks', label: 'IDENTIFICATION MARKS', hint: 'Semantic similarity between free-text descriptions of scars, tattoos and birthmarks, plus structured field agreement.' },
  { k: 'demographic', label: 'AGE COMPATIBILITY', hint: 'Overlap between the two age intervals after time-aware projection. Partial overlap scores partially.' },
  { k: 'location', label: 'LOCATION COMPATIBILITY', hint: 'Geographic plausibility given elapsed time and known transit corridors — not a hard radius.' },
  { k: 'time', label: 'TIME COMPATIBILITY', hint: 'Whether the candidate record could plausibly correspond to this case given the reporting and recovery dates.' },
];

export default function Comparison({ go, params }) {
  const candidate = CANDIDATES.find((c) => c.id === params?.id) || CANDIDATES[0];
  const subject = CASES[0];
  const candCase = CASES.find((c) => c.id === candidate.id);
  const [decision, setDecision] = useState(null);

  return (
    <div className="stack gap-24">
      <div className="row between wrap gap-16">
        <div>
          <button className="btn btn-sm btn-ghost" onClick={() => go('match', { id: subject.id })}>
            <ArrowLeft size={13} strokeWidth={2.2} /> Back to ranking
          </button>
          <h1 className="page-title mt-12">Match Comparison</h1>
          <p className="page-sub">
            <span className="mono" style={{ color: 'var(--cyan)' }}>{subject.id}</span>
            {' '}compared against{' '}
            <span className="mono" style={{ color: 'var(--violet, #8b7dff)' }}>{candidate.id}</span>
          </p>
        </div>
        <div className="row gap-14" style={{ alignItems: 'center' }}>
          <ConfidenceRing value={candidate.confidence} size={96} stroke={6} label="OVERALL" />
          <div className="stack gap-6">
            <Badge tone={candidate.confidence >= 85 ? 'green' : 'cyan'}>{confLabel(candidate.confidence)} CONFIDENCE</Badge>
            <Badge tone="amber">POTENTIAL MATCH</Badge>
            <span className="mono" style={{ fontSize: 9.5, color: 'var(--faint)', letterSpacing: '.1em' }}>
              RANK #{String(candidate.rank).padStart(2, '0')} OF {CANDIDATES.length}
            </span>
          </div>
        </div>
      </div>

      <HumanLoopNotice />

      {/* split comparison */}
      <div className="compare-grid">
        <SideCard title="Missing person" c={subject} seed={147} align="left" />

        <div className="panel ticked panel-pad stack gap-11">
          <div className="row between">
            <span className="eyebrow hot">EVIDENCE BY CATEGORY</span>
            <Tip content="Each category is scored independently, then fused with weights that account for reliability and elapsed time. No single source can carry a match on its own.">
              <Info size={13} strokeWidth={2} color="var(--dim)" style={{ cursor: 'help' }} />
            </Tip>
          </div>

          {EVIDENCE_ROWS.map((r, i) => {
            const v = candidate.scores[r.k];
            const col = confColor(v);
            return (
              <Tip key={r.k} content={r.hint} width={250}>
                <div className="evi-row" style={{ width: '100%', animation: `fadeUp .5s ${i * 80}ms var(--ease-out) both` }}>
                  <div className="grow" style={{ minWidth: 0 }}>
                    <div className="mono" style={{ fontSize: 9.5, letterSpacing: '.12em', color: 'var(--muted)' }}>{r.label}</div>
                    <div className="meter" style={{ marginTop: 6 }}>
                      <i style={{ width: `${v}%`, background: `linear-gradient(90deg,${col}55,${col})`, animation: `growW 1s ${300 + i * 90}ms var(--ease-out) both` }} />
                    </div>
                  </div>
                  <span className="num" style={{ fontSize: 16, fontWeight: 600, color: col }}>{v}%</span>
                </div>
              </Tip>
            );
          })}

          <div className="row between" style={{
            marginTop: 4, padding: '13px 14px', borderRadius: 11,
            border: '1px solid rgba(53,223,160,.26)', background: 'linear-gradient(120deg, rgba(53,223,160,.1), rgba(53,223,160,.02))',
          }}>
            <div>
              <div className="mono" style={{ fontSize: 9.5, letterSpacing: '.13em', color: '#7cecc0' }}>OVERALL CONFIDENCE</div>
              <div style={{ fontSize: 10.5, color: 'var(--dim)', marginTop: 3 }}>weighted evidence fusion</div>
            </div>
            <span className="num" style={{ fontSize: 27, fontWeight: 600, color: '#35dfa0', lineHeight: 1 }}>
              {candidate.confidence}<span style={{ fontSize: 14, opacity: .7 }}>%</span>
            </span>
          </div>

          <div className="stack gap-8" style={{ paddingTop: 8 }}>
            <span className="eyebrow" style={{ fontSize: 9 }}>LINKED ATTRIBUTES</span>
            <ConnectorArt />
            <span style={{ fontSize: 10.5, color: 'var(--faint)', lineHeight: 1.5 }}>
              Three attribute pairs carried measurable evidence between these records.
            </span>
          </div>
        </div>

        <SideCard title="Candidate" c={candCase} candidate={candidate} seed={candidate.seed} align="right" />
      </div>

      {/* explanation */}
      <Reveal>
        <div className="panel ticked panel-pad stack gap-16">
          <div className="row between wrap gap-12">
            <span className="section-title"><Sparkles size={13} strokeWidth={2} style={{ marginLeft: -2 }} /> Why this candidate ranked highly</span>
            <Badge tone="violet">AI-GENERATED EXPLANATION</Badge>
          </div>

          <div className="grid" style={{ gridTemplateColumns: 'repeat(auto-fit,minmax(300px,1fr))', gap: 13 }}>
            <div className="stack gap-9">
              {candidate.evidence.map((e, i) => (
                <div key={i} className="row gap-10" style={{
                  padding: '10px 12px', borderRadius: 9, background: 'rgba(53,223,160,.05)',
                  border: '1px solid rgba(53,223,160,.18)', animation: `fadeUp .5s ${i * 80}ms var(--ease-out) both`,
                }}>
                  <Check size={13} strokeWidth={2.6} color="#35dfa0" style={{ flexShrink: 0, marginTop: 2 }} />
                  <span style={{ fontSize: 12.5, lineHeight: 1.55, color: 'var(--text-2)' }}>{e}</span>
                </div>
              ))}
            </div>
            <div className="stack gap-9">
              <span className="eyebrow">COUNTER-EVIDENCE & GAPS</span>
              {candidate.concerns.map((e, i) => (
                <div key={i} className="row gap-10" style={{
                  padding: '10px 12px', borderRadius: 9, background: 'rgba(255,177,86,.05)',
                  border: '1px solid rgba(255,177,86,.2)',
                }}>
                  <ShieldAlert size={13} strokeWidth={2.2} color="#ffb156" style={{ flexShrink: 0, marginTop: 2 }} />
                  <span style={{ fontSize: 12.5, lineHeight: 1.55, color: 'var(--text-2)' }}>{e}</span>
                </div>
              ))}
              <div className="row gap-10" style={{
                padding: '11px 13px', borderRadius: 10, marginTop: 4,
                background: 'rgba(126,165,224,.05)', border: '1px dashed var(--line-2)',
              }}>
                <CircleHelp size={13} strokeWidth={2.2} color="var(--dim)" style={{ flexShrink: 0, marginTop: 2 }} />
                <span style={{ fontSize: 12, lineHeight: 1.55, color: 'var(--muted)' }}>
                  <strong style={{ color: 'var(--text-2)' }}>AI recommendation — human verification required.</strong>{' '}
                  This ranking is an investigative lead. Physical or documentary verification by a trained
                  officer is required before any identification is recorded.
                </span>
              </div>
            </div>
          </div>

          {/* decision actions */}
          <div className="row between wrap gap-14" style={{ paddingTop: 14, borderTop: '1px solid var(--line)' }}>
            <div className="mono" style={{ fontSize: 10, letterSpacing: '.13em', color: 'var(--dim)' }}>
              OFFICER ACTION · {decision ? decision.toUpperCase() + ' RECORDED' : 'AWAITING DECISION'}
            </div>
            <div className="row gap-10 wrap">
              <button className="btn btn-ok" data-on={decision === 'verified'} onClick={() => setDecision('verified')}>
                <Check size={14} strokeWidth={2.4} /> Verify candidate
              </button>
              <button className="btn btn-danger" onClick={() => setDecision('rejected')}>
                <X size={14} strokeWidth={2.4} /> Reject candidate
              </button>
              <button className="btn" onClick={() => setDecision('evidence requested')}>
                <FileQuestion size={14} strokeWidth={2.1} /> Request more evidence
              </button>
            </div>
          </div>

          {decision && (
            <div className="row gap-10" style={{
              padding: '11px 13px', borderRadius: 10, animation: 'fadeUp .4s var(--ease-out) both',
              background: decision === 'verified' ? 'rgba(53,223,160,.08)' : 'rgba(126,165,224,.06)',
              border: `1px solid ${decision === 'verified' ? 'rgba(53,223,160,.3)' : 'var(--line-2)'}`,
            }}>
              <Check size={14} strokeWidth={2.4} color={decision === 'verified' ? '#35dfa0' : 'var(--muted)'} />
              <span style={{ fontSize: 12.5 }}>
                Officer decision recorded against <span className="mono" style={{ color: 'var(--cyan)' }}>{candidate.id}</span>.
                {decision === 'verified' && ' Case flagged for physical verification — identity remains unconfirmed until that step completes.'}
                {decision === 'rejected' && ' Candidate removed from the active shortlist and recorded as negative evidence.'}
                {decision === 'evidence requested' && ' Request dispatched to the originating bureau for additional imagery and mark details.'}
              </span>
            </div>
          )}
        </div>
      </Reveal>

      <AdaptiveInvestigation />
    </div>
  );
}

/* ---------------------------------------------------------------- */
function SideCard({ title, c, candidate, seed, align }) {
  if (!c && !candidate) return null;
  const rows = c ? [
    ['Case status', c.status],
    ['Case number', c.id],
    ['Age', c.ageMode === 'range' ? `${c.ageMin}–${c.ageMax} yrs` : `${c.ageExact} yrs`],
    ['Sex', c.sex],
    ['Height', c.heightMode === 'range' ? `${c.heightMin}–${c.heightMax} cm` : `${c.heightExact} cm`],
    ['Build', c.build],
    ['Blood type', c.bloodType],
    ['Last known', c.location],
    ['Date', c.lastSeen],
  ] : [
    ['Case status', 'UNIDENTIFIED'],
    ['Case number', candidate.id],
    ['Age', `${candidate.ageText} yrs`],
    ['Last known', candidate.location],
    ['Date', candidate.date],
  ];
  const marks = c?.marks || [];

  return (
    <div className="panel ticked panel-pad stack gap-16">
      <div className="row between">
        <span className="eyebrow">{title.toUpperCase()}</span>
        <Badge tone={align === 'left' ? 'cyan' : 'violet'}>{align === 'left' ? 'SUBJECT' : 'CANDIDATE'}</Badge>
      </div>

      <div className="row gap-14" style={{ alignItems: 'center' }}>
        <Portrait seed={seed} size={92} landmarks radius={12}
                  quality={c?.imageQuality} tone={align === 'right' ? 'candidate' : undefined} />
        <div className="stack gap-5 grow" style={{ minWidth: 0 }}>
          <div style={{ fontSize: 15.5, fontWeight: 600 }}>
            {c?.nameKnown ? c.name : <span style={{ color: 'var(--muted)', fontStyle: 'italic', fontWeight: 500 }}>Identity unknown</span>}
          </div>
          <span className="mono" style={{ fontSize: 11, color: 'var(--cyan)' }}>{c?.id || candidate.id}</span>
          {c && <span style={{ alignSelf: 'flex-start' }}><Badge>{c.status}</Badge></span>}
        </div>
      </div>

      <div className="stack gap-8">
        {rows.map(([k, v]) => (
          <div className="kv" key={k}>
            <span className="k">{k}</span>
            <span className="v" style={{ color: v === 'Unknown' || v === 'Identity unknown' ? 'var(--faint)' : 'var(--text)' }}>{v}</span>
          </div>
        ))}
      </div>

      {!!marks.length && (
        <div className="stack gap-8" style={{ paddingTop: 13, borderTop: '1px solid var(--line)' }}>
          <span className="eyebrow">IDENTIFICATION MARKS</span>
          {marks.map((m, i) => (
            <div key={i} className="stack gap-4" style={{
              padding: '9px 11px', borderRadius: 9, background: 'rgba(4,8,16,.4)', border: '1px solid var(--line)',
            }}>
              <div className="row gap-7 wrap">
                <Badge tone="cyan">{m.kind.toUpperCase()}</Badge>
                <span className="mono" style={{ fontSize: 10.5, color: 'var(--muted)' }}>
                  {m.side} {m.location} · {m.size} · {m.shape}
                </span>
              </div>
              <span style={{ fontSize: 11.5, color: 'var(--text-2)' }}>“{m.text}”</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function ConnectorArt() {
  return (
    <svg viewBox="0 0 100 30" style={{ width: '100%', height: 44, overflow: 'visible' }}>
      <defs>
        <linearGradient id="cg" x1="0" y1="0" x2="1" y2="0">
          <stop offset="0%" stopColor="rgba(53,214,255,.9)" />
          <stop offset="50%" stopColor="rgba(53,214,255,.35)" />
          <stop offset="100%" stopColor="rgba(139,125,255,.9)" />
        </linearGradient>
      </defs>
      {[6, 15, 24].map((y, i) => {
        const d = `M1,${y} Q50,${y + (i - 1) * 7} 99,${y}`;
        return (
          <g key={y}>
            <path d={d} fill="none" stroke="url(#cg)" strokeWidth=".7" strokeDasharray="2.5 2" opacity=".75" />
            <circle cx="1" cy={y} r="1.3" fill="#35d6ff" />
            <circle cx="99" cy={y} r="1.3" fill="#8b7dff" />
            <circle r="1.1" fill="#fff" opacity=".9">
              <animateMotion dur={`${2.8 + i * 0.7}s`} repeatCount="indefinite" path={d} />
            </circle>
          </g>
        );
      })}
    </svg>
  );
}

/* ---------------------------------------------------------------- */
const AI_BEFORE = [
  { id: 'A', ref: 'CASE-2026-0304', v: 84, seed: 304 },
  { id: 'B', ref: 'CASE-2026-0271', v: 82, seed: 271 },
  { id: 'C', ref: 'CASE-2026-0259', v: 80, seed: 259 },
];
const AI_AFTER = { A: 91, B: 76, C: 72 };

function AdaptiveInvestigation() {
  const [answer, setAnswer] = useState(null);
  const list = AI_BEFORE.map((c) => ({ ...c, v: answer ? AI_AFTER[c.id] : c.v }))
    .sort((a, b) => b.v - a.v);

  return (
    <Reveal>
      <div className="panel ticked panel-pad stack gap-18" style={{ borderColor: 'rgba(255,177,86,.24)' }}>
        <div className="row between wrap gap-12">
          <div>
            <span className="section-title"><CircleHelp size={13} strokeWidth={2} style={{ marginLeft: -2 }} /> Adaptive Investigation</span>
            <p style={{ fontSize: 12.5, color: 'var(--muted)', marginTop: 8, maxWidth: '76ch', lineHeight: 1.6 }}>
              When several candidates sit within a few confidence points, the system stops guessing and asks
              the officer one targeted question whose answer will actually separate them.
            </p>
          </div>
          <Badge tone={answer ? 'green' : 'amber'} dot={!answer}>{answer ? 'EVIDENCE UPDATED' : 'AWAITING OFFICER INPUT'}</Badge>
        </div>

        <div className="panel flat" style={{ padding: 16, background: 'linear-gradient(150deg, rgba(255,177,86,.07), rgba(10,17,30,.6))', borderColor: 'rgba(255,177,86,.22)' }}>
          <span className="eyebrow" style={{ color: '#ffc98a' }}>TARGETED QUESTION</span>
          <div style={{ fontSize: 15.5, fontWeight: 500, marginTop: 9, lineHeight: 1.45 }}>
            Which candidate has a 3 cm linear scar above the <em>left</em> eyebrow?
          </div>
          <p style={{ fontSize: 11.5, color: 'var(--dim)', marginTop: 8, lineHeight: 1.6 }}>
            This mark is recorded on the subject case but is only partially described on two candidate records.
            A direct answer resolves the ambiguity that the models cannot.
          </p>

          <div className="grid mt-16" style={{ gridTemplateColumns: 'repeat(auto-fit,minmax(150px,1fr))', gap: 11 }}>
            {AI_BEFORE.map((c) => (
              <button key={c.id} className="choice" data-on={answer === c.id} onClick={() => setAnswer(c.id)}
                      style={{ padding: 14 }}>
                <div className="row gap-11">
                  <Portrait seed={c.seed} size={44} radius={9} tone="candidate" />
                  <div className="stack gap-3">
                    <span style={{ fontSize: 13.5, fontWeight: 600 }}>Candidate {c.id}</span>
                    <span className="mono" style={{ fontSize: 9.5, color: 'var(--dim)' }}>{c.ref}</span>
                  </div>
                </div>
                {answer === c.id && <div className="mt-12"><Badge tone="green"><Check size={9} strokeWidth={3} />OFFICER CONFIRMED</Badge></div>}
              </button>
            ))}
          </div>
        </div>

        {/* before / after */}
        <div className="grid" style={{ gridTemplateColumns: 'repeat(auto-fit,minmax(260px,1fr))', gap: 16 }}>
          <div className="panel flat" style={{ padding: 15 }}>
            <span className="eyebrow">BEFORE · MODEL EVIDENCE ONLY</span>
            <div className="stack gap-11 mt-16">
              {AI_BEFORE.map((c) => (
                <EvidenceBar key={c.id} label={`Candidate ${c.id} · ${c.ref}`} value={c.v} tone="#7d90ae" />
              ))}
            </div>
          </div>

          <div className="panel flat" style={{ padding: 15, borderColor: answer ? 'rgba(53,223,160,.28)' : undefined }}>
            <div className="row between">
              <span className="eyebrow" style={{ color: answer ? '#7cecc0' : undefined }}>
                {answer ? 'AFTER OFFICER VERIFICATION' : 'AFTER · AWAITING ANSWER'}
              </span>
              {answer && <Badge tone="green">RE-RANKED</Badge>}
            </div>
            <div className="stack gap-11 mt-16">
              {list.map((c) => {
                const before = AI_BEFORE.find((x) => x.id === c.id).v;
                const delta = c.v - before;
                return (
                  <div key={c.id} className="row gap-10" style={{ alignItems: 'flex-end' }}>
                    <div className="grow">
                      <EvidenceBar label={`Candidate ${c.id} · ${c.ref}`} value={c.v} />
                    </div>
                    <span className="mono row gap-3" style={{
                      fontSize: 10.5, width: 46, justifyContent: 'flex-end',
                      color: delta > 0 ? '#35dfa0' : delta < 0 ? '#ff8e9b' : 'var(--faint)',
                    }}>
                      {delta > 0 ? <TrendingUp size={11} /> : delta < 0 ? <TrendingDown size={11} /> : <Minus size={11} />}
                      {delta ? `${delta > 0 ? '+' : ''}${delta}` : '—'}
                    </span>
                  </div>
                );
              })}
            </div>
            {answer && (
              <p style={{ fontSize: 11.5, color: 'var(--muted)', marginTop: 14, lineHeight: 1.6 }}>
                Officer testimony is recorded as high-reliability evidence and propagated through the fusion
                step. The shortlist re-ranks immediately — and the decision remains the officer's.
              </p>
            )}
          </div>
        </div>
      </div>
    </Reveal>
  );
}

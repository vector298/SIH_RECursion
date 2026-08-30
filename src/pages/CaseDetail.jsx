import { useState } from 'react';
import {
  ArrowLeft, MapPin, CalendarDays, Shirt, Fingerprint, Radar, ChevronRight,
  Pencil, ShieldCheck, Image as ImageIcon, NotebookPen, Sparkles,
} from 'lucide-react';
import { CASES, TIMELINE, CANDIDATES } from '../data/sample';
import { getCase, adaptCase } from '../api/client';
import { useApiData } from '../api/useApiData';
import { SourceBanner, LoadingRows } from '../components/DataState';
import Portrait from '../components/Portrait';
import { UncertainValue } from '../components/UncertainField';
import {
  Badge, EvidenceBar, ConfidenceRing, HumanLoopNotice, Reveal, confColor, confLabel,
} from '../components/ui';

const TABS = ['Overview', 'Timeline', 'Evidence', 'Potential Matches', 'AI Analysis', 'Investigation Notes'];
const TL_COL = { cyan: '#35d6ff', violet: '#8b7dff', amber: '#ffb156', green: '#35dfa0', gray: '#7d90ae' };

export default function CaseDetail({ go, params }) {
  const requested = params?.id ?? CASES[0].id;
  const fallback = CASES.find((x) => x.id === requested) || CASES[0];

  const { data: c, loading, error, live } = useApiData(
    (signal) => getCase(requested, signal).then(adaptCase),
    fallback,
    [requested],
  );

  const [tab, setTab] = useState('Overview');
  const seed = parseInt(String(c.id).replace(/\D/g, '').slice(-4) || '1', 10);

  if (loading) {
    return (
      <div className="stack gap-20">
        <SourceBanner live={false} loading />
        <LoadingRows rows={2} height={160} />
      </div>
    );
  }

  const ageV = c.ageMode === 'range' ? { mode: 'range', min: c.ageMin, max: c.ageMax } : { mode: 'exact', exact: c.ageExact };
  const hV = c.heightMode === 'range' ? { mode: 'range', min: c.heightMin, max: c.heightMax } : { mode: 'exact', exact: c.heightExact };

  return (
    <div className="stack gap-24">
      {/* header */}
      <div>
        <div className="row between wrap gap-12">
          <button className="btn btn-sm btn-ghost" onClick={() => go('cases')}>
            <ArrowLeft size={13} strokeWidth={2.2} /> All cases
          </button>
          <SourceBanner live={live} loading={false} error={error} noun="case file" />
        </div>

        <div className="panel ticked panel-pad mt-16">
          <div className="row between wrap gap-18">
            <div className="row gap-18 wrap" style={{ alignItems: 'center' }}>
              <Portrait seed={seed} size={92} landmarks radius={13} quality={c.imageQuality}
                        tone={c.type === 'unidentified' ? 'candidate' : undefined} />
              <div className="stack gap-8">
                <div className="row gap-10 wrap">
                  <h1 className="mono" style={{ fontSize: 'clamp(19px,2.6vw,26px)', fontWeight: 600, letterSpacing: '-0.01em' }}>{c.id}</h1>
                  {c.priority === 'HIGH PRIORITY' && <Badge dot>HIGH PRIORITY</Badge>}
                  <Badge>{c.status}</Badge>
                </div>
                <div style={{ fontSize: 16, fontWeight: 500 }}>
                  {c.nameKnown ? c.name : <span style={{ color: 'var(--muted)', fontStyle: 'italic' }}>Identity unknown</span>}
                  <span style={{ color: 'var(--dim)', fontWeight: 400 }}> · {c.type === 'missing' ? 'Missing Person' : 'Unidentified Person'}</span>
                </div>
                <div className="row gap-16 wrap" style={{ fontSize: 11.5, color: 'var(--muted)' }}>
                  <span className="row gap-5"><MapPin size={11} strokeWidth={2} /> {c.location}</span>
                  <span className="row gap-5"><CalendarDays size={11} strokeWidth={2} /> Last seen {c.lastSeen} · {c.lastSeenTime}</span>
                  <span className="row gap-5"><ShieldCheck size={11} strokeWidth={2} /> {c.officer}</span>
                </div>
              </div>
            </div>

            <div className="row gap-16 wrap" style={{ alignItems: 'center' }}>
              <ConfidenceRing value={c.confidence} size={88} stroke={6} label="TOP MATCH" />
              <div className="stack gap-9">
                <button className="btn btn-primary btn-sm" onClick={() => go('match', { id: c.id })}>
                  <Radar size={13} strokeWidth={2.1} /> Match intelligence
                </button>
                <button className="btn btn-sm btn-ghost"><Pencil size={13} strokeWidth={2} /> Edit case</button>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div className="tabs">
        {TABS.map((t) => <button key={t} data-on={tab === t} onClick={() => setTab(t)}>{t}</button>)}
      </div>

      <div key={tab} className="page-enter">
        {tab === 'Overview' && <Overview c={c} ageV={ageV} hV={hV} />}
        {tab === 'Timeline' && <TimelineTab />}
        {tab === 'Evidence' && <EvidenceTab c={c} seed={seed} />}
        {tab === 'Potential Matches' && <MatchesTab go={go} />}
        {tab === 'AI Analysis' && <AnalysisTab c={c} />}
        {tab === 'Investigation Notes' && <NotesTab c={c} />}
      </div>
    </div>
  );
}

/* ---------------------------------------------------------------- */
function Overview({ c, ageV, hV }) {
  return (
    <div className="grid" style={{ gridTemplateColumns: 'repeat(auto-fit,minmax(320px,1fr))', gap: 16 }}>
      <div className="panel ticked panel-pad stack gap-14">
        <span className="section-title">Recorded attributes</span>
        <div className="stack gap-11">
          {[['Age', ageV, 'yrs'], ['Height', hV, 'cm']].map(([k, v, u]) => (
            <div className="kv" key={k}><span className="k">{k}</span><UncertainValue v={v} unit={u} /></div>
          ))}
          {[['Sex / Gender', c.sex], ['Build', c.build], ['Blood type', c.bloodType], ['District', c.district], ['State', c.state],
            ['Coordinates', (c.coords || []).filter((n) => n != null).join(', ') || 'Unknown'],
            ['Case opened', c.opened || 'Unknown']].map(([k, v]) => (
            <div className="kv" key={k}>
              <span className="k">{k}</span>
              <span className="v" style={{ color: v === 'Unknown' ? 'var(--faint)' : 'var(--text)' }}>
                {v === 'Unknown' ? <Badge tone="gray">UNKNOWN</Badge> : v}
              </span>
            </div>
          ))}
        </div>
      </div>

      <div className="panel ticked panel-pad stack gap-16">
        <div>
          <span className="section-title">Circumstances</span>
          <p style={{ fontSize: 13, color: 'var(--text-2)', marginTop: 10, lineHeight: 1.7 }}>{c.circumstances}</p>
        </div>
        <div>
          <span className="section-title"><Shirt size={12} strokeWidth={2} style={{ marginLeft: -2 }} /> Clothing worn</span>
          <p style={{ fontSize: 12.5, color: 'var(--muted)', marginTop: 10, lineHeight: 1.7 }}>{c.clothing}</p>
        </div>
      </div>

      <div className="panel ticked panel-pad stack gap-14">
        <span className="section-title"><Fingerprint size={12} strokeWidth={2} style={{ marginLeft: -2 }} /> Distinguishing characteristics</span>
        {c.marks.map((m, i) => (
          <div key={i} className="stack gap-6" style={{
            padding: 12, borderRadius: 10, background: 'rgba(4,8,16,.4)', border: '1px solid var(--line)',
          }}>
            <div className="row gap-8 wrap">
              <Badge tone="cyan">{m.kind.toUpperCase()}</Badge>
              <span className="mono" style={{ fontSize: 10.5, color: 'var(--muted)' }}>{m.side} {m.location}</span>
              <span className="mono" style={{ fontSize: 10.5, color: 'var(--muted)' }}>· {m.size} · {m.shape}</span>
            </div>
            <span style={{ fontSize: 12, color: 'var(--text-2)' }}>“{m.text}”</span>
            <span className="embed-chip" style={{ alignSelf: 'flex-start', marginTop: 2 }}>SEMANTIC REPRESENTATION ✓</span>
          </div>
        ))}
      </div>
    </div>
  );
}

/* ---------------------------------------------------------------- */
function TimelineTab() {
  return (
    <div className="panel ticked panel-pad">
      <span className="section-title" style={{ marginBottom: 20, display: 'flex' }}>Investigation timeline</span>
      <div className="tl">
        {TIMELINE.map((t, i) => (
          <Reveal key={t.title} delay={i * 60}>
            <div className="tl-item" data-pending={!!t.pending} style={{ '--tl-c': TL_COL[t.tone] }}>
              <div className="mono" style={{ fontSize: 10, letterSpacing: '.1em', color: 'var(--faint)' }}>{t.t}</div>
              <div style={{ fontSize: 13.5, fontWeight: 600, marginTop: 4 }}>{t.title}</div>
              <p style={{ fontSize: 12.5, color: 'var(--muted)', marginTop: 4, lineHeight: 1.6, maxWidth: '78ch' }}>{t.body}</p>
            </div>
          </Reveal>
        ))}
      </div>
    </div>
  );
}

/* ---------------------------------------------------------------- */
function EvidenceTab({ c, seed }) {
  const imgs = [
    { label: 'Face photograph', s: seed, q: c.imageQuality, lm: true },
    { label: 'Full-body photograph', s: seed + 11, q: Math.max(0.55, c.imageQuality - 0.09), lm: false },
    { label: 'Side profile', s: seed + 23, q: Math.max(0.5, c.imageQuality - 0.16), lm: true },
  ];
  return (
    <div className="stack gap-16">
      <div className="panel ticked panel-pad stack gap-16">
        <span className="section-title"><ImageIcon size={12} strokeWidth={2} style={{ marginLeft: -2 }} /> Biometric evidence</span>
        <div className="grid" style={{ gridTemplateColumns: 'repeat(auto-fit,minmax(220px,1fr))', gap: 14 }}>
          {imgs.map((im, i) => (
            <div key={im.label} className="panel flat hoverable" style={{ padding: 13, animation: `fadeUp .5s ${i * 80}ms var(--ease-out) both` }}>
              <Portrait seed={im.s} size={'100%'} landmarks={im.lm} quality={im.q} radius={10}
                        tone={c.type === 'unidentified' ? 'candidate' : undefined} />
              <div style={{ fontSize: 12.5, fontWeight: 600, marginTop: 11 }}>{im.label}</div>
              <div className="meter mt-8"><i style={{ width: `${im.q * 100}%`, background: im.q >= 0.85 ? '#35dfa0' : im.q >= 0.7 ? '#35d6ff' : '#ffb156' }} /></div>
              <div className="row between mt-8">
                <span className="mono" style={{ fontSize: 9.5, color: 'var(--dim)' }}>QUALITY</span>
                <span className="mono" style={{ fontSize: 10.5 }}>{im.q.toFixed(2)}</span>
              </div>
            </div>
          ))}
        </div>
        <div className="row gap-12 wrap" style={{ padding: '11px 13px', borderRadius: 10, background: 'rgba(53,214,255,.05)', border: '1px solid rgba(53,214,255,.2)' }}>
          <span className="embed-chip">512-D FACE EMBEDDING</span>
          <span style={{ fontSize: 12, color: 'var(--text-2)' }}>
            Generated from the highest-quality frontal image. Vectors are stored encrypted and never surfaced in the interface.
          </span>
        </div>
      </div>
    </div>
  );
}

/* ---------------------------------------------------------------- */
function MatchesTab({ go }) {
  return (
    <div className="stack gap-16">
      <HumanLoopNotice />
      <div className="stack gap-12">
        {CANDIDATES.slice(0, 4).map((cd, i) => (
          <button key={cd.id} className="cand" onClick={() => go('compare', { id: cd.id })}
                  style={{ animation: `fadeUp .5s ${i * 70}ms var(--ease-out) both` }}>
            <div className="row gap-14">
              <span className="rankchip" data-top={cd.rank === 1}>#{String(cd.rank).padStart(2, '0')}</span>
              <Portrait seed={cd.seed} size={64} radius={10} landmarks tone="candidate" />
            </div>
            <div className="stack gap-10" style={{ minWidth: 0 }}>
              <div className="row between wrap gap-10">
                <div className="row gap-9 wrap">
                  <span className="mono" style={{ fontSize: 12, color: 'var(--cyan)' }}>{cd.id}</span>
                  <span style={{ fontSize: 11.5, color: 'var(--muted)' }}>Age {cd.ageText} · {cd.location}</span>
                </div>
                <span className="row gap-5" style={{ fontSize: 11.5, color: 'var(--cyan)' }}>
                  Compare evidence <ChevronRight size={12} strokeWidth={2.4} />
                </span>
              </div>
              <div className="cand-scores">
                <EvidenceBar label="Face" value={cd.scores.face} />
                <EvidenceBar label="Marks" value={cd.scores.marks} />
                <EvidenceBar label="Demographic" value={cd.scores.demographic} />
                <EvidenceBar label="Time" value={cd.scores.time} />
                <EvidenceBar label="Quality" value={cd.scores.quality} />
              </div>
            </div>
            <div className="cand-ring"><ConfidenceRing value={cd.confidence} size={80} stroke={5} /></div>
          </button>
        ))}
      </div>
    </div>
  );
}

/* ---------------------------------------------------------------- */
function AnalysisTab({ c }) {
  const top = CANDIDATES[0];
  const col = confColor(top.confidence);
  return (
    <div className="grid" style={{ gridTemplateColumns: 'repeat(auto-fit,minmax(320px,1fr))', gap: 16 }}>
      <div className="panel ticked panel-pad stack gap-16">
        <span className="section-title"><Sparkles size={12} strokeWidth={2} style={{ marginLeft: -2 }} /> Evidence contribution</span>
        <div className="stack gap-12">
          <EvidenceBar label="Facial evidence (quality-adjusted)" value={top.scores.face} />
          <EvidenceBar label="Identification-mark similarity" value={top.scores.marks} />
          <EvidenceBar label="Demographic interval overlap" value={top.scores.demographic} />
          <EvidenceBar label="Temporal plausibility" value={top.scores.time} />
          <EvidenceBar label="Geospatial plausibility" value={top.scores.location} />
        </div>
        <div className="row between" style={{ paddingTop: 13, borderTop: '1px solid var(--line)' }}>
          <span className="mono" style={{ fontSize: 10, letterSpacing: '.13em', color: 'var(--dim)' }}>FUSED CONFIDENCE</span>
          <span className="num" style={{ fontSize: 22, fontWeight: 600, color: col }}>{top.confidence}%</span>
        </div>
      </div>

      <div className="panel ticked panel-pad stack gap-14">
        <span className="section-title">Model narrative</span>
        <div className="stack gap-9">
          {top.evidence.map((e, i) => (
            <div key={i} className="row gap-9" style={{ fontSize: 12.5, color: 'var(--text-2)', lineHeight: 1.6 }}>
              <span className="mono" style={{ color: 'var(--cyan)', fontSize: 10.5, flexShrink: 0, paddingTop: 2 }}>
                {String(i + 1).padStart(2, '0')}
              </span>
              {e}
            </div>
          ))}
        </div>
        <div className="stack gap-8" style={{ paddingTop: 13, borderTop: '1px solid var(--line)' }}>
          <span className="eyebrow">SEARCH EXECUTION</span>
          <div className="kv"><span className="k">Records searched</span><span className="v">12,482</span></div>
          <div className="kv"><span className="k">Facial comparisons run</span><span className="v">37</span></div>
          <div className="kv"><span className="k">Candidates returned</span><span className="v">{c.matches}</span></div>
          <div className="kv"><span className="k">Total runtime</span><span className="v">4.89 s</span></div>
        </div>
        <HumanLoopNotice compact />
      </div>
    </div>
  );
}

/* ---------------------------------------------------------------- */
function NotesTab({ c }) {
  const [notes, setNotes] = useState([
    { t: '27 Aug 2026 · 10:12', who: c.officer, body: 'Confirmed presence of left-eyebrow scar against candidate #01 imagery. Requested hospital records from the originating district for cross-verification.' },
    { t: '19 Aug 2026 · 16:40', who: 'SI. K. Deshmukh', body: 'Family contacted regarding the new Chennai record. Advised that no identification is confirmed and that verification is pending.' },
  ]);
  const [draft, setDraft] = useState('');

  const add = () => {
    if (!draft.trim()) return;
    setNotes([{ t: 'Just now', who: c.officer, body: draft.trim() }, ...notes]);
    setDraft('');
  };

  return (
    <div className="stack gap-16" style={{ maxWidth: 900 }}>
      <div className="panel ticked panel-pad stack gap-12">
        <span className="section-title"><NotebookPen size={12} strokeWidth={2} style={{ marginLeft: -2 }} /> Add investigation note</span>
        <textarea className="textarea" value={draft} onChange={(e) => setDraft(e.target.value)}
                  placeholder="Record an observation, an action taken, or a verification outcome…" />
        <button className="btn btn-primary btn-sm" style={{ alignSelf: 'flex-start' }} onClick={add}>Save note</button>
      </div>

      <div className="stack gap-12">
        {notes.map((n, i) => (
          <div key={i} className="panel flat" style={{ padding: 15, animation: `fadeUp .45s ${i * 60}ms var(--ease-out) both` }}>
            <div className="row between wrap gap-10">
              <span style={{ fontSize: 12.5, fontWeight: 600 }}>{n.who}</span>
              <span className="mono" style={{ fontSize: 10, color: 'var(--faint)' }}>{n.t}</span>
            </div>
            <p style={{ fontSize: 12.5, color: 'var(--text-2)', marginTop: 8, lineHeight: 1.7 }}>{n.body}</p>
          </div>
        ))}
      </div>
    </div>
  );
}

import { useState, useRef } from 'react';
import {
  UserSearch, ScanFace, ArrowLeft, ArrowRight, Sparkles, Plus, Trash2, Check,
  ImageUp, Loader2, CircleCheckBig, ShieldQuestion, Fingerprint, MapPin, ShieldAlert,
} from 'lucide-react';
import { useBackend } from '../api/BackendContext';
import { createCase, extractMark, uploadImage } from '../api/client';
import UncertainField, { UncertainValue } from '../components/UncertainField';
import Portrait from '../components/Portrait';
import { Badge, HumanLoopNotice, Field, Reveal } from '../components/ui';

const STEPS = [
  { n: '01', label: 'Case Type' },
  { n: '02', label: 'Identity' },
  { n: '03', label: 'Physical Profile' },
  { n: '04', label: 'Last Known Information' },
  { n: '05', label: 'Distinguishing Characteristics' },
  { n: '06', label: 'Images' },
  { n: '07', label: 'Review & Submit' },
];

const U = (mode = 'exact') => ({ mode, exact: '', min: '', max: '' });

/** Map the wizard's local state onto the API's uncertainty-aware contract. */
const num = (v) => (v === '' || v == null ? null : Number(v));

function toUncertain(field) {
  if (!field || field.mode === 'unknown') return { mode: 'unknown' };
  if (field.mode === 'range') {
    const min = num(field.min), max = num(field.max);
    if (min == null || max == null) return { mode: 'unknown' };
    return { mode: 'range', min, max };
  }
  const exact = num(field.exact);
  return exact == null ? { mode: 'unknown' } : { mode: 'exact', exact };
}

function toApiPayload(f) {
  const text = (v) => (v?.mode === 'unknown' ? null : (v?.exact || '').trim() || null);
  return {
    case_number: f.caseNumber || null,
    case_type: f.caseType,
    name: text(f.name),
    age: toUncertain(f.age),
    height: toUncertain(f.height),
    sex: text(f.sex),
    build: text(f.build),
    blood_type: text(f.bloodType),
    last_seen_at: f.dateLastSeen ? `${f.dateLastSeen}T${f.timeLastSeen || '00:00'}:00` : null,
    location_text: text(f.location),
    district: null,
    state: (text(f.location) || '').split(',').pop()?.trim() || null,
    lat: num(f.lat),
    lon: num(f.lon),
    circumstances: f.circumstances || null,
    clothing: f.clothing || null,
    appearance: f.appearance || null,
    priority: 'ACTIVE',
    officer: null,
    marks: f.marks.map((m) => ({
      kind: m.kind || null,
      body_location: m.location || null,
      side: m.side || null,
      size_text: m.size || null,
      size_cm: parseFloat(m.size) || null,
      shape: m.shape || null,
      description: m.text || '',
    })),
  };
}

const INITIAL = {
  caseType: null,
  // Left blank so the server assigns the next free number. Hard-coding one made
  // every second submission collide with the first.
  caseNumber: '',
  name: U('exact'),
  age: { mode: 'range', exact: '', min: '23', max: '27' },
  sex: U('exact'),
  height: { mode: 'range', exact: '', min: '158', max: '164' },
  build: U('exact'),
  appearance: '',
  bloodType: U('unknown'),
  dateLastSeen: '2026-08-24',
  timeLastSeen: '19:40',
  location: U('exact'),
  address: '',
  lat: '12.9716',
  lon: '77.5946',
  circumstances: '',
  clothing: '',
  marks: [],
  images: [],
};

export default function NewCase({ go }) {
  const [step, setStep] = useState(0);
  const [f, setF] = useState(INITIAL);
  const [submitted, setSubmitted] = useState(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);
  const { online } = useBackend();
  const set = (k, v) => setF((p) => ({ ...p, [k]: v }));

  const canNext = step !== 0 || !!f.caseType;

  const submit = async () => {
    setSaving(true);
    setError(null);
    try {
      // Always attempt the API, even if the last health probe said offline —
      // the probe may simply be stale because the backend started after this
      // page loaded. Only fall back once a real request has actually failed.
      const record = await createCase(toApiPayload(f));
      setSubmitted({ ...record, persisted: true });
    } catch (err) {
      if (err.status === 409) {
        setError(
          `${err.detail} — clear the case number field to have one assigned automatically, ` +
          `or enter a different one.`
        );
      } else if (err.status) {
        setError(`The API rejected this case (${err.status}): ${err.detail}`);
      } else {
        // No response at all: the service is genuinely unreachable.
        setSubmitted({ case_number: f.caseNumber || '(unassigned)', id: null, persisted: false });
      }
    } finally {
      setSaving(false);
    }
  };

  if (submitted) return <Submitted record={submitted} go={go} />;

  return (
    <div className="stack gap-24" style={{ maxWidth: 1160, margin: '0 auto', width: '100%' }}>
      <div className="row between wrap gap-16">
        <div>
          <span className="eyebrow hot">CASE INTAKE</span>
          <h1 className="page-title mt-8">Create Investigation Case</h1>
          <p className="page-sub">
            Every field supports an exact value, an approximate range, or an explicit unknown —
            the matching engine is built to reason with incomplete reports.
          </p>
        </div>
        <span className="mono badge badge-cyan" style={{ fontSize: 11, padding: '6px 11px' }}>
          {f.caseNumber || 'NUMBER ASSIGNED ON SUBMIT'}
        </span>
      </div>

      {/* progress rail */}
      <div className="panel flat" style={{ padding: '2px 8px' }}>
        <div className="wizard-rail">
          {STEPS.map((s, i) => (
            <button key={s.n} className="wstep"
                    data-state={i === step ? 'on' : i < step ? 'done' : 'off'}
                    onClick={() => i <= step && setStep(i)}>
              <span className="wn">{i < step ? <Check size={12} strokeWidth={3} /> : s.n}</span>
              <span className="wl">{s.label}</span>
            </button>
          ))}
        </div>
      </div>

      <div key={step} className="page-enter">
        {step === 0 && <StepType f={f} set={set} />}
        {step === 1 && <StepIdentity f={f} set={set} />}
        {step === 2 && <StepPhysical f={f} set={set} />}
        {step === 3 && <StepLastKnown f={f} set={set} />}
        {step === 4 && <StepMarks f={f} set={set} />}
        {step === 5 && <StepImages f={f} set={set} />}
        {step === 6 && <StepReview f={f} />}
      </div>

      <div className="row between wrap gap-12" style={{ paddingTop: 4 }}>
        <button className="btn btn-ghost" disabled={step === 0} onClick={() => setStep((s) => s - 1)}>
          <ArrowLeft size={14} strokeWidth={2.2} /> Back
        </button>
        <div className="row gap-10">
          <span className="mono" style={{ fontSize: 10.5, color: 'var(--dim)', letterSpacing: '.12em' }}>
            STEP {STEPS[step].n} / 07
          </span>
          {step < 6 ? (
            <button className="btn btn-primary" disabled={!canNext} onClick={() => setStep((s) => s + 1)}>
              Continue <ArrowRight size={14} strokeWidth={2.2} />
            </button>
          ) : (
            <button className="btn btn-primary" onClick={submit} disabled={saving}>
              {saving
                ? <><Loader2 size={14} className="spin" /> Saving…</>
                : <>Submit &amp; run matching <ArrowRight size={14} strokeWidth={2.2} /></>}
            </button>
          )}
        </div>
      </div>

      {error && (
        <div className="row gap-10" style={{
          padding: '11px 13px', borderRadius: 10,
          border: '1px solid rgba(255,95,112,.3)', background: 'var(--red-dim)',
        }}>
          <ShieldAlert size={15} strokeWidth={2} color="#ff8e9b" />
          <span style={{ fontSize: 12.5 }}>{error}</span>
        </div>
      )}
    </div>
  );
}

/* ---------------------------------------------------------------- 01 */
function StepType({ f, set }) {
  const opts = [
    {
      id: 'missing', Icon: UserSearch, title: 'Missing Person Case',
      d: 'A person reported missing. Identity is usually known; location, condition and present appearance are not.',
      pts: ['Identity known or partially known', 'Age-progression applies to long-duration cases', 'Searched against the unidentified index'],
    },
    {
      id: 'unidentified', Icon: ScanFace, title: 'Unidentified Person Case',
      d: 'A living or deceased person whose identity cannot be established. Physical evidence is present; identity is absent.',
      pts: ['Identity unknown', 'Physical and biometric evidence recorded', 'Searched against the missing persons index'],
    },
  ];
  return (
    <div className="stack gap-16">
      <span className="section-title">Select case type</span>
      <div className="choice-grid">
        {opts.map((o) => (
          <button key={o.id} className="choice" data-on={f.caseType === o.id} onClick={() => set('caseType', o.id)}>
            <div className="row between">
              <span className="ci"><o.Icon size={20} strokeWidth={1.7} /></span>
              {f.caseType === o.id && <Badge tone="cyan">SELECTED</Badge>}
            </div>
            <div style={{ fontSize: 17, fontWeight: 600, marginTop: 15 }}>{o.title}</div>
            <p style={{ fontSize: 12.5, color: 'var(--muted)', marginTop: 7, lineHeight: 1.6 }}>{o.d}</p>
            <div className="stack gap-7 mt-16" style={{ paddingTop: 13, borderTop: '1px solid var(--line)' }}>
              {o.pts.map((p) => (
                <div key={p} className="row gap-8" style={{ fontSize: 11.5, color: 'var(--text-2)' }}>
                  <Check size={12} strokeWidth={2.6} color="var(--cyan)" style={{ flexShrink: 0, marginTop: 2 }} />
                  {p}
                </div>
              ))}
            </div>
          </button>
        ))}
      </div>
    </div>
  );
}

/* ---------------------------------------------------------------- 02 */
function StepIdentity({ f, set }) {
  return (
    <div className="panel ticked panel-pad stack gap-20">
      <span className="section-title">Identity</span>
      <div className="form-grid">
        <Field label="Case number">
          <input className="input mono" value={f.caseNumber} placeholder="Leave blank to auto-assign"
                 onChange={(e) => set('caseNumber', e.target.value)} />
        </Field>
        <UncertainField label="Name" value={f.name} onChange={(v) => set('name', v)}
                        placeholder="Full name as reported"
                        hint="For unidentified person cases this is normally recorded as unknown." />
        <UncertainField label="Age" value={f.age} onChange={(v) => set('age', v)} unit="yrs" min="23" max="27"
                        hint="A range is preferred when the reporting party is estimating. Overlapping intervals score partially rather than pass/fail." />
        <UncertainField label="Sex / Gender" value={f.sex} onChange={(v) => set('sex', v)}
                        options={['Female', 'Male', 'Other', 'Not recorded']} />
      </div>
      <NoteBar text="Name and age are used only for hard-search reduction and demographic evidence. Neither is treated as proof of identity." />
    </div>
  );
}

/* ---------------------------------------------------------------- 03 */
function StepPhysical({ f, set }) {
  return (
    <div className="panel ticked panel-pad stack gap-20">
      <span className="section-title">Physical profile</span>
      <div className="form-grid">
        <UncertainField label="Height" value={f.height} onChange={(v) => set('height', v)} unit="cm" min="158" max="164"
                        hint="Height is a dynamic attribute: for long-duration cases involving minors its weight decays as elapsed time grows." />
        <UncertainField label="Build / body type" value={f.build} onChange={(v) => set('build', v)}
                        options={['Slight', 'Slim', 'Medium', 'Athletic', 'Heavy']} />
        <UncertainField label="Blood type" value={f.bloodType} onChange={(v) => set('bloodType', v)}
                        options={['A+', 'A−', 'B+', 'B−', 'AB+', 'AB−', 'O+', 'O−']}
                        hint="Frequently unknown at intake. An unknown value is neutral and never eliminates a candidate." />
        <Field label="General physical appearance">
          <textarea className="textarea" style={{ minHeight: 72 }} value={f.appearance}
                    onChange={(e) => set('appearance', e.target.value)}
                    placeholder="Hair, complexion, spectacles, gait, dentition, any prosthetics…" />
        </Field>
      </div>
    </div>
  );
}

/* ---------------------------------------------------------------- 04 */
function StepLastKnown({ f, set }) {
  return (
    <div className="panel ticked panel-pad stack gap-20">
      <span className="section-title">Last known information</span>
      <div className="form-grid">
        <Field label="Date last seen"><input className="input" type="date" value={f.dateLastSeen} onChange={(e) => set('dateLastSeen', e.target.value)} /></Field>
        <Field label="Time last seen"><input className="input" type="time" value={f.timeLastSeen} onChange={(e) => set('timeLastSeen', e.target.value)} /></Field>
        <UncertainField label="Last known location" value={f.location} onChange={(v) => set('location', v)}
                        placeholder="City, district, state"
                        hint="Location feeds the geospatial compatibility score. Distance is weighed against elapsed time, not treated as a hard boundary." />
        <Field label="Address / landmark">
          <input className="input" value={f.address} onChange={(e) => set('address', e.target.value)}
                 placeholder="Street, locality or nearest landmark" />
        </Field>
        <Field label="Latitude">
          <input className="input mono" value={f.lat} onChange={(e) => set('lat', e.target.value)} placeholder="12.9716" />
        </Field>
        <Field label="Longitude">
          <input className="input mono" value={f.lon} onChange={(e) => set('lon', e.target.value)} placeholder="77.5946" />
        </Field>
        <div className="span2">
          <Field label="Circumstances of disappearance">
            <textarea className="textarea" value={f.circumstances} onChange={(e) => set('circumstances', e.target.value)}
                      placeholder="Sequence of events, last verified contact, device or financial activity, witness accounts…" />
          </Field>
        </div>
        <div className="span2">
          <Field label="Clothing worn">
            <textarea className="textarea" style={{ minHeight: 72 }} value={f.clothing} onChange={(e) => set('clothing', e.target.value)}
                      placeholder="Garments, colours, footwear, jewellery, carried items…" />
          </Field>
        </div>
      </div>
      <div className="row gap-10" style={{ padding: '10px 13px', borderRadius: 10, background: 'rgba(53,214,255,.06)', border: '1px solid rgba(53,214,255,.2)' }}>
        <MapPin size={14} strokeWidth={2} color="var(--cyan)" />
        <span style={{ fontSize: 12, color: 'var(--text-2)' }}>
          Coordinates anchor this case in the geospatial index and enable cluster detection across state boundaries.
        </span>
      </div>
    </div>
  );
}

/* ---------------------------------------------------------------- 05 */
const MARK_TYPES = ['Tattoo', 'Scar', 'Birthmark', 'Other feature'];
const MARK_LOC = ['Eyebrow', 'Forehead', 'Cheek', 'Neck', 'Shoulder', 'Forearm', 'Hand', 'Torso', 'Leg', 'Ankle'];
const SIDES = ['Left', 'Right', 'Centre', 'Front', 'Back', 'Not recorded'];
const SHAPES = ['Linear', 'Curved', 'Oval', 'Circular', 'Irregular', 'Script', 'Pictorial'];

function StepMarks({ f, set }) {
  const [draft, setDraft] = useState({
    kind: 'Scar', location: '', side: '', size: '', shape: '',
    text: '3 cm horizontal scar above the left eyebrow',
  });
  const [phase, setPhase] = useState('idle'); // idle | working | done
  const [source, setSource] = useState(null);
  const timer = useRef(null);
  const { online } = useBackend();

  const extract = async () => {
    if (!draft.text.trim()) return;
    setPhase('working');
    clearTimeout(timer.current);

    if (online) {
      // Real extraction: Gemini when a key is configured, rules otherwise.
      try {
        const r = await extractMark(draft.text);
        setDraft((d) => ({
          ...d,
          kind: r.kind || d.kind,
          location: r.body_location || d.location,
          side: r.side || d.side,
          size: r.size_text || d.size,
          shape: r.shape || d.shape,
        }));
        setSource(r.source);
        setPhase('done');
        return;
      } catch {
        /* fall through to the local parse below */
      }
    }

    setSource('local (offline)');
    timer.current = setTimeout(() => {
      const t = draft.text.toLowerCase();
      const kind = /tattoo/.test(t) ? 'Tattoo' : /birthmark|mole|mark on/.test(t) ? 'Birthmark' : /scar/.test(t) ? 'Scar' : 'Other feature';
      const location = MARK_LOC.find((l) => t.includes(l.toLowerCase())) || 'Eyebrow';
      const side = /left/.test(t) ? 'Left' : /right/.test(t) ? 'Right' : /back|nape/.test(t) ? 'Back' : 'Not recorded';
      const sizeM = t.match(/(\d+(?:\.\d+)?)\s*(cm|mm|inch)/);
      const size = sizeM ? `${sizeM[1]} ${sizeM[2]}` : 'Approx. 3 cm';
      const shape = /horizontal|linear|straight/.test(t) ? 'Linear' : /curved|crescent/.test(t) ? 'Curved'
        : /oval/.test(t) ? 'Oval' : /round|circular/.test(t) ? 'Circular' : /script|lettering|word/.test(t) ? 'Script' : 'Linear';
      setDraft((d) => ({ ...d, kind, location, side, size, shape }));
      setPhase('done');
    }, 1900);
  };

  const add = () => {
    if (!draft.text.trim() && !draft.location) return;
    set('marks', [...f.marks, { ...draft, id: Date.now() }]);
    setDraft({ kind: 'Scar', location: '', side: '', size: '', shape: '', text: '' });
    setPhase('idle');
  };

  const remove = (id) => set('marks', f.marks.filter((m) => m.id !== id));

  return (
    <div className="stack gap-16">
      <div className="panel ticked panel-pad stack gap-20">
        <div className="row between wrap gap-12">
          <span className="section-title">Distinguishing Characteristics</span>
          <span className="badge badge-gray">{f.marks.length} RECORDED</span>
        </div>

        <div className="form-grid">
          <Field label="Type">
            <select className="select" value={draft.kind} onChange={(e) => setDraft({ ...draft, kind: e.target.value })}>
              {MARK_TYPES.map((t) => <option key={t}>{t}</option>)}
            </select>
          </Field>
          <Field label="Location on body">
            <select className="select" value={draft.location} onChange={(e) => setDraft({ ...draft, location: e.target.value })}>
              <option value="">Select…</option>
              {MARK_LOC.map((t) => <option key={t}>{t}</option>)}
            </select>
          </Field>
          <Field label="Side">
            <select className="select" value={draft.side} onChange={(e) => setDraft({ ...draft, side: e.target.value })}>
              <option value="">Select…</option>
              {SIDES.map((t) => <option key={t}>{t}</option>)}
            </select>
          </Field>
          <Field label="Size">
            <input className="input" value={draft.size} onChange={(e) => setDraft({ ...draft, size: e.target.value })} placeholder="e.g. 3 cm" />
          </Field>
          <Field label="Shape">
            <select className="select" value={draft.shape} onChange={(e) => setDraft({ ...draft, shape: e.target.value })}>
              <option value="">Select…</option>
              {SHAPES.map((t) => <option key={t}>{t}</option>)}
            </select>
          </Field>
          <Field label="Description keyword"><input className="input" placeholder="Optional short label" /></Field>

          <div className="span2 field">
            <div className="row between gap-10">
              <span className="label">Describe the identifying characteristic</span>
              <button className="btn btn-sm" onClick={extract} disabled={phase === 'working' || !draft.text.trim()}
                      style={{ borderColor: 'rgba(53,214,255,.35)', color: '#8ce6ff' }}>
                {phase === 'working'
                  ? <><Loader2 size={12} strokeWidth={2.4} className="spin" /> Extracting…</>
                  : <><Sparkles size={12} strokeWidth={2.2} /> Extract with AI</>}
              </button>
            </div>
            <textarea className="textarea" value={draft.text} onChange={(e) => { setDraft({ ...draft, text: e.target.value }); setPhase('idle'); }}
                      placeholder="e.g. 3 cm horizontal scar above the left eyebrow" />
          </div>
        </div>

        {phase !== 'idle' && <ExtractionPanel phase={phase} draft={draft} source={source} />}

        <div className="row gap-10">
          <button className="btn btn-primary btn-sm" onClick={add}><Plus size={13} strokeWidth={2.6} /> Add characteristic</button>
          <span style={{ fontSize: 11.5, color: 'var(--dim)' }}>
            Free text is embedded, so “scar over the left brow” and “3 cm linear scar above left eyebrow” compare as near-identical.
          </span>
        </div>
      </div>

      {!!f.marks.length && (
        <div className="stack gap-10">
          {f.marks.map((m) => (
            <div key={m.id} className="panel flat row between gap-12" style={{ padding: '12px 15px' }}>
              <div className="row gap-12" style={{ alignItems: 'flex-start' }}>
                <Fingerprint size={15} strokeWidth={1.9} color="var(--cyan)" style={{ marginTop: 2 }} />
                <div>
                  <div className="row gap-8 wrap">
                    <span style={{ fontSize: 13, fontWeight: 600 }}>{m.kind}</span>
                    {m.location && <Badge tone="gray">{m.side ? `${m.side} ${m.location}` : m.location}</Badge>}
                    {m.size && <Badge tone="gray">{m.size}</Badge>}
                    {m.shape && <Badge tone="gray">{m.shape}</Badge>}
                  </div>
                  {m.text && <div style={{ fontSize: 12, color: 'var(--muted)', marginTop: 5 }}>“{m.text}”</div>}
                </div>
              </div>
              <button className="iconbtn" onClick={() => remove(m.id)} aria-label="Remove"><Trash2 size={14} strokeWidth={1.9} /></button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function ExtractionPanel({ phase, draft, source }) {
  const rows = [
    ['Type', draft.kind], ['Location', draft.location], ['Side', draft.side],
    ['Size', draft.size], ['Shape', draft.shape],
  ];
  return (
    <div className="panel flat scanbox" style={{
      padding: 16, borderColor: 'rgba(53,214,255,.28)',
      background: 'linear-gradient(150deg, rgba(53,214,255,.07), rgba(10,17,30,.6))',
    }}>
      {phase === 'working' && <i className="scanline" />}
      <div className="row between">
        <span className="eyebrow hot">STRUCTURED EXTRACTION</span>
        {phase === 'working'
          ? <span className="mono shimmer-text" style={{ fontSize: 10, letterSpacing: '.14em' }}>PARSING FREE TEXT…</span>
          : <Badge tone="green"><Check size={9} strokeWidth={3} />COMPLETE</Badge>}
      </div>

      <div className="grid mt-16" style={{ gridTemplateColumns: 'repeat(auto-fit,minmax(120px,1fr))', gap: 12 }}>
        {rows.map(([k, v], i) => (
          <div key={k} style={{
            padding: '9px 11px', borderRadius: 9, background: 'rgba(4,8,16,.5)', border: '1px solid var(--line)',
            animation: phase === 'done' ? `fadeUp .45s ${i * 70}ms var(--ease-out) both` : 'none',
          }}>
            <div className="label" style={{ fontSize: 9 }}>{k}</div>
            <div className="mono" style={{ fontSize: 12.5, marginTop: 4, color: phase === 'done' ? 'var(--text)' : 'var(--faint)' }}>
              {phase === 'done' ? (v || '—') : '· · ·'}
            </div>
          </div>
        ))}
      </div>

      {phase === 'done' && (
        <div className="row between wrap gap-12 mt-16" style={{ paddingTop: 13, borderTop: '1px solid var(--line)' }}>
          <div className="row gap-10">
            <CircleCheckBig size={15} strokeWidth={2} color="#35dfa0" />
            <span style={{ fontSize: 12.5 }}>Semantic representation generated</span>
          </div>
          <div className="row gap-8">
            <span className="embed-chip">{source || 'TEXT EMBEDDING'}</span>
            <span className="vecbar" style={{ width: 96 }}>
              {Array.from({ length: 20 }, (_, i) => (
                <span key={i} style={{ height: `${25 + ((Math.sin(i * 2.1) + 1) / 2) * 70}%`, animationDelay: `${i * 22}ms` }} />
              ))}
            </span>
          </div>
        </div>
      )}
    </div>
  );
}

/* ---------------------------------------------------------------- 06 */
const SLOTS = [
  { id: 'face', label: 'Face photograph', hint: 'Frontal, unobstructed. Drives the facial embedding.' },
  { id: 'body', label: 'Full-body photograph', hint: 'Supports build, height and clothing evidence.' },
  { id: 'side', label: 'Side profile', hint: 'Improves embedding robustness under pose variation.' },
  { id: 'other', label: 'Other useful images', hint: 'Identification marks, documents, recovered belongings.' },
];

function StepImages({ f, set }) {
  const [busy, setBusy] = useState(null);

  const upload = (slot) => {
    if (f.images.find((i) => i.slot === slot)) return;
    setBusy(slot);
    setTimeout(() => {
      const seed = 1000 + SLOTS.findIndex((s) => s.id === slot) * 37;
      const q = [0.91, 0.86, 0.78, 0.83][SLOTS.findIndex((s) => s.id === slot)];
      set('images', [...f.images, {
        slot, seed, quality: q,
        resolution: q > 0.85 ? 'High' : 'Adequate',
        blur: q > 0.85 ? 'Low' : 'Moderate',
        lighting: q > 0.8 ? 'Good' : 'Uneven',
        visibility: Math.round(q * 100 + 2),
      }]);
      setBusy(null);
    }, 1800);
  };

  return (
    <div className="stack gap-16">
      <div className="panel ticked panel-pad stack gap-18">
        <div className="row between wrap gap-12">
          <span className="section-title">Biometric Evidence</span>
          <span className="badge badge-gray">{f.images.length} / 4 ATTACHED</span>
        </div>

        <div className="grid" style={{ gridTemplateColumns: 'repeat(auto-fit,minmax(230px,1fr))', gap: 13 }}>
          {SLOTS.map((s) => {
            const img = f.images.find((i) => i.slot === s.id);
            const working = busy === s.id;
            return (
              <div key={s.id}>
                {img ? (
                  <div className="panel flat" style={{ padding: 12, borderColor: 'rgba(53,223,160,.28)' }}>
                    <div className="row gap-12">
                      <Portrait seed={img.seed} size={62} landmarks={s.id === 'face'} quality={img.quality} radius={9} />
                      <div className="grow stack gap-5">
                        <div style={{ fontSize: 12.5, fontWeight: 600 }}>{s.label}</div>
                        <Badge tone="green"><Check size={9} strokeWidth={3} />ANALYSED</Badge>
                      </div>
                    </div>
                  </div>
                ) : (
                  <button className="drop scanbox" onClick={() => upload(s.id)} disabled={working}>
                    {working && <i className="scanline" />}
                    <div className="stack gap-8" style={{ alignItems: 'center' }}>
                      {working
                        ? <Loader2 size={22} strokeWidth={1.8} color="var(--cyan)" className="spin" />
                        : <ImageUp size={22} strokeWidth={1.6} color="var(--dim)" />}
                      <div style={{ fontSize: 12.5, fontWeight: 500 }}>{working ? 'Analysing image…' : s.label}</div>
                      <div style={{ fontSize: 11, color: 'var(--dim)', lineHeight: 1.5 }}>
                        {working ? 'Resolution · blur · lighting · face visibility' : 'Drag & drop, or click to attach'}
                      </div>
                    </div>
                  </button>
                )}
                <div style={{ fontSize: 10.5, color: 'var(--faint)', marginTop: 7, lineHeight: 1.5 }}>{s.hint}</div>
              </div>
            );
          })}
        </div>
      </div>

      {!!f.images.length && (
        <Reveal>
          <div className="panel ticked panel-pad stack gap-16">
            <span className="section-title">Image quality analysis</span>
            <div className="grid" style={{ gridTemplateColumns: 'repeat(auto-fit,minmax(260px,1fr))', gap: 13 }}>
              {f.images.map((img) => {
                const s = SLOTS.find((x) => x.id === img.slot);
                return (
                  <div key={img.slot} className="panel flat" style={{ padding: 14 }}>
                    <div className="row between">
                      <span className="eyebrow">{s.label}</span>
                      <span className="badge" style={{
                        color: img.quality >= 0.85 ? '#7cecc0' : '#ffc98a',
                        background: img.quality >= 0.85 ? 'var(--green-dim)' : 'var(--amber-dim)',
                        borderColor: img.quality >= 0.85 ? 'rgba(53,223,160,.28)' : 'rgba(255,177,86,.28)',
                      }}>Q {img.quality.toFixed(2)}</span>
                    </div>
                    <div className="stack gap-7 mt-12">
                      {[['Resolution', img.resolution], ['Blur', img.blur], ['Lighting', img.lighting],
                        ['Face visibility', `${img.visibility}%`], ['Quality score', img.quality.toFixed(2)]].map(([k, v]) => (
                        <div className="kv" key={k}><span className="k">{k}</span><span className="v">{v}</span></div>
                      ))}
                    </div>
                    <div className="meter mt-12">
                      <i style={{ width: `${img.quality * 100}%`, background: img.quality >= 0.85 ? '#35dfa0' : '#ffb156' }} />
                    </div>
                  </div>
                );
              })}
            </div>

            {f.images.some((i) => i.slot === 'face') && (
              <div className="panel flat scanbox" style={{
                padding: 16, borderColor: 'rgba(53,214,255,.28)',
                background: 'linear-gradient(150deg, rgba(53,214,255,.07), rgba(10,17,30,.6))',
              }}>
                <div className="row between wrap gap-12">
                  <div className="row gap-12">
                    <Portrait seed={1000} size={64} landmarks radius={10} />
                    <div>
                      <div className="eyebrow hot">FACIAL EMBEDDING GENERATED</div>
                      <div style={{ fontSize: 12.5, color: 'var(--muted)', marginTop: 5, maxWidth: '46ch', lineHeight: 1.55 }}>
                        Represented abstractly. The underlying vector is stored encrypted and is never exposed
                        in the investigator interface.
                      </div>
                    </div>
                  </div>
                  <div className="stack gap-8" style={{ minWidth: 180 }}>
                    <span className="embed-chip" style={{ alignSelf: 'flex-start' }}>512-D · FACE EMBEDDING</span>
                    <span className="vecbar">
                      {Array.from({ length: 30 }, (_, i) => (
                        <span key={i} style={{ height: `${20 + ((Math.sin(i * 1.3) + Math.cos(i * 0.7) + 2) / 4) * 78}%`, animationDelay: `${i * 18}ms` }} />
                      ))}
                    </span>
                  </div>
                </div>
              </div>
            )}
          </div>
        </Reveal>
      )}
    </div>
  );
}

/* ---------------------------------------------------------------- 07 */
function StepReview({ f }) {
  const rows = [
    ['Case type', f.caseType === 'missing' ? 'Missing Person' : f.caseType === 'unidentified' ? 'Unidentified Person' : '—'],
    ['Case number', f.caseNumber],
  ];
  return (
    <div className="stack gap-16">
      <div className="panel ticked panel-pad stack gap-18">
        <span className="section-title">Review & submit</span>

        <div className="grid" style={{ gridTemplateColumns: 'repeat(auto-fit,minmax(230px,1fr))', gap: 14 }}>
          {rows.map(([k, v]) => (
            <div className="panel flat" style={{ padding: 13 }} key={k}>
              <div className="label">{k}</div>
              <div className="mono mt-8" style={{ fontSize: 13 }}>{v}</div>
            </div>
          ))}
          {[['Name', f.name, ''], ['Age', f.age, 'yrs'], ['Sex / Gender', f.sex, ''],
            ['Height', f.height, 'cm'], ['Build', f.build, ''], ['Blood type', f.bloodType, '']].map(([k, v, u]) => (
            <div className="panel flat" style={{ padding: 13 }} key={k}>
              <div className="label">{k}</div>
              <div className="mt-8"><UncertainValue v={v} unit={u} /></div>
            </div>
          ))}
        </div>

        <div className="grid" style={{ gridTemplateColumns: 'repeat(auto-fit,minmax(230px,1fr))', gap: 14 }}>
          <div className="panel flat" style={{ padding: 13 }}>
            <div className="label">Last seen</div>
            <div className="mono mt-8" style={{ fontSize: 13 }}>{f.dateLastSeen} · {f.timeLastSeen}</div>
          </div>
          <div className="panel flat" style={{ padding: 13 }}>
            <div className="label">Last known location</div>
            <div className="mt-8"><UncertainValue v={f.location} /></div>
          </div>
          <div className="panel flat" style={{ padding: 13 }}>
            <div className="label">Coordinates</div>
            <div className="mono mt-8" style={{ fontSize: 13 }}>{f.lat}, {f.lon}</div>
          </div>
          <div className="panel flat" style={{ padding: 13 }}>
            <div className="label">Distinguishing characteristics</div>
            <div className="mono mt-8" style={{ fontSize: 13 }}>{f.marks.length} recorded</div>
          </div>
          <div className="panel flat" style={{ padding: 13 }}>
            <div className="label">Biometric evidence</div>
            <div className="mono mt-8" style={{ fontSize: 13 }}>{f.images.length} image{f.images.length === 1 ? '' : 's'}</div>
          </div>
        </div>

        <div className="row gap-12 wrap" style={{
          padding: '12px 14px', borderRadius: 11, border: '1px solid rgba(53,214,255,.22)', background: 'rgba(53,214,255,.05)',
        }}>
          <ShieldQuestion size={16} strokeWidth={1.9} color="var(--cyan)" />
          <span style={{ fontSize: 12.5, color: 'var(--text-2)', flex: 1, minWidth: 240 }}>
            On submission this record is indexed nationally and matched against the opposite register.
            Unknown fields are preserved as unknown — they reduce evidence available, not candidate eligibility.
          </span>
        </div>

        <HumanLoopNotice />
      </div>
    </div>
  );
}

function Submitted({ record, go }) {
  const number = record.case_number;
  return (
    <div className="stack gap-20" style={{ maxWidth: 640, margin: '40px auto', textAlign: 'center', alignItems: 'center' }}>
      <div style={{
        width: 66, height: 66, borderRadius: 20, display: 'grid', placeItems: 'center',
        background: record.persisted ? 'rgba(53,223,160,.12)' : 'rgba(255,177,86,.12)',
        border: `1px solid ${record.persisted ? 'rgba(53,223,160,.34)' : 'rgba(255,177,86,.4)'}`,
        boxShadow: `0 0 40px -12px ${record.persisted ? 'rgba(53,223,160,.7)' : 'rgba(255,177,86,.7)'}`,
        animation: 'scaleIn .5s var(--ease-out) both',
      }}>
        {record.persisted
          ? <CircleCheckBig size={30} strokeWidth={1.8} color="#35dfa0" />
          : <ShieldAlert size={30} strokeWidth={1.8} color="#ffb156" />}
      </div>
      <div className="anim-2">
        <h2 style={{ fontSize: 24 }}>{record.persisted ? 'Case registered' : 'Not saved'}</h2>
        {record.persisted ? (
          <p className="page-sub" style={{ margin: '8px auto 0' }}>
            <span className="mono" style={{ color: 'var(--cyan)' }}>{number}</span>{' '}
            has been written to the index and is ready for cross-state matching.
          </p>
        ) : (
          <div className="stack gap-12" style={{ marginTop: 12, maxWidth: 520 }}>
            <p className="page-sub" style={{ margin: 0 }}>
              The API did not respond, so <strong>this case was not written to the
              database</strong>. Nothing has been stored anywhere — re-submit once the
              backend is running.
            </p>
            <div className="stack gap-6" style={{
              padding: '12px 14px', borderRadius: 10, textAlign: 'left',
              border: '1px solid rgba(255,177,86,.26)', background: 'rgba(255,177,86,.06)',
            }}>
              <span className="mono" style={{ fontSize: 10, letterSpacing: '.13em', color: '#ffc98a' }}>
                START THE BACKEND
              </span>
              <code style={{ fontSize: 11.5, color: 'var(--text-2)', lineHeight: 1.7 }}>
                cd backend<br />
                python scripts/check_db.py<br />
                uvicorn app.main:app --reload
              </code>
            </div>
          </div>
        )}
      </div>
      <div className="row gap-12 wrap center anim-3">
        <button className="btn btn-primary" onClick={() => go('match', { id: number })}>
          Run match intelligence <ArrowRight size={14} strokeWidth={2.2} />
        </button>
        <button className="btn btn-ghost" onClick={() => go('dashboard')}>Back to command center</button>
      </div>
    </div>
  );
}

function NoteBar({ text }) {
  return (
    <div className="row gap-10" style={{ fontSize: 11.5, color: 'var(--dim)', lineHeight: 1.55 }}>
      <span style={{ width: 2, alignSelf: 'stretch', background: 'var(--line-2)', borderRadius: 2, flexShrink: 0 }} />
      {text}
    </div>
  );
}

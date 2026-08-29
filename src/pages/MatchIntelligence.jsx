import { useState, useEffect, useRef, useCallback } from 'react';
import {
  RotateCcw, Check, Loader2, ChevronRight, Sigma, TriangleAlert,
  Layers, Filter, ScanFace, Gauge, ListOrdered, Database,
} from 'lucide-react';
import { PIPELINE, FUNNEL, CANDIDATES, CASES } from '../data/sample';
import { useBackend } from '../api/BackendContext';
import { runMatch, adaptCandidate } from '../api/client';
import Portrait from '../components/Portrait';
import Method from './Method';
import {
  ConfidenceRing, EvidenceBar, Badge, HumanLoopNotice, confColor, confLabel, Tip,
} from '../components/ui';

const STAGE_ICON = {
  ingest: Database, hard: Filter, attr: Layers, semantic: Sigma,
  face: ScanFace, quality: Gauge, rank: ListOrdered,
};

// A real run finishes in tens of milliseconds — far too fast to read. The
// animation replays the stages at a legible pace while the timing column shows
// the measured duration, so nothing on screen is invented.
const MIN_STAGE_MS = 320;

const formatDuration = (ms) =>
  ms < 1 ? `${ms.toFixed(2)} ms` : ms < 1000 ? `${ms.toFixed(1)} ms` : `${(ms / 1000).toFixed(2)} s`;

export default function MatchIntelligence({ go, params }) {
  const { online } = useBackend();
  const subjectId = params?.id || CASES[0].id;
  const sampleSubject = CASES.find((c) => c.id === subjectId) || CASES[0];

  const [tab, setTab] = useState('ranking');
  const [stage, setStage] = useState(-1);
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState(null);   // live API result, or null
  const [error, setError] = useState(null);
  const timers = useRef([]);

  const clearTimers = () => { timers.current.forEach(clearTimeout); timers.current = []; };

  const replay = useCallback((stages) => {
    clearTimers();
    setStage(0);
    let acc = 0;
    stages.forEach((s, i) => {
      acc += Math.max(s.duration_ms ?? s.ms ?? 0, MIN_STAGE_MS);
      timers.current.push(setTimeout(() => {
        setStage(i + 1);
        if (i === stages.length - 1) setRunning(false);
      }, acc));
    });
  }, []);

  const run = useCallback(async () => {
    setError(null);
    setRunning(true);
    setStage(-1);
    clearTimers();

    if (!online) {
      setResult(null);
      replay(PIPELINE);
      return;
    }

    try {
      const body = await runMatch(subjectId);
      setResult(body);
      replay(body.stages);
    } catch (err) {
      setError(err.message || 'The matching service did not respond.');
      setResult(null);
      replay(PIPELINE);
    }
  }, [online, subjectId, replay]);

  useEffect(() => {
    const t = setTimeout(run, 320);
    return () => { clearTimeout(t); clearTimers(); };
  }, [run]);

  const stages = result?.stages ?? PIPELINE.map((p) => ({ ...p, duration_ms: p.ms }));
  const done = stage >= stages.length;

  const funnelRows = result
    ? (result.stages.find((s) => s.id === 'hard')?.substeps ?? []).map((s) => ({
        n: s.remaining, label: s.label, stage: s.stage === 'corpus' ? 'Corpus' : 'Hard search',
        predicate: s.predicate,
      }))
    : FUNNEL;

  const candidates = result ? result.candidates.map(adaptCandidate) : CANDIDATES;
  const funnelDepth = stage <= 0 ? 0
    : Math.min(funnelRows.length, Math.round((stage / stages.length) * funnelRows.length) + 1);

  const backends = result?.backends;

  return (
    <div className="stack gap-24">
      <div className="row between wrap gap-16">
        <div>
          <span className="eyebrow hot">MATCH INTELLIGENCE</span>
          <h1 className="page-title mt-8">AI Candidate Ranking</h1>
          <p className="page-sub">Potential matches ranked using multiple evidence sources.</p>
        </div>
        <div className="row gap-10 wrap">
          <div className="panel flat row gap-10" style={{ padding: '8px 13px' }}>
            <span className="label" style={{ fontSize: 9 }}>SUBJECT</span>
            <span className="mono" style={{ fontSize: 12, color: 'var(--cyan)' }}>{subjectId}</span>
          </div>
          <button className="btn" onClick={run} disabled={running}>
            {running ? <><Loader2 size={14} className="spin" /> Running</> : <><RotateCcw size={14} strokeWidth={2.1} /> Re-run</>}
          </button>
        </div>
      </div>

      {!online && (
        <div className="row gap-10" style={{
          padding: '11px 14px', borderRadius: 10,
          border: '1px solid rgba(255,177,86,.26)', background: 'rgba(255,177,86,.06)',
        }}>
          <TriangleAlert size={15} strokeWidth={2} color="#ffb156" style={{ flexShrink: 0 }} />
          <span style={{ fontSize: 12.5, color: 'var(--text-2)' }}>
            <strong>Sample data.</strong> The matching service is not reachable, so the
            scores, timings and funnel below are illustrative rather than computed. Start
            the API to run this case against the real index.
          </span>
        </div>
      )}

      {error && (
        <div className="row gap-10" style={{
          padding: '11px 14px', borderRadius: 10,
          border: '1px solid rgba(255,95,112,.3)', background: 'var(--red-dim)',
        }}>
          <TriangleAlert size={15} strokeWidth={2} color="#ff8e9b" style={{ flexShrink: 0 }} />
          <span style={{ fontSize: 12.5 }}>{error}</span>
        </div>
      )}

      {backends && !backends.arcface_real && backends.face_notice && (
        <div className="row gap-10" style={{
          padding: '11px 14px', borderRadius: 10,
          border: '1px solid rgba(255,177,86,.26)', background: 'rgba(255,177,86,.06)',
        }}>
          <ScanFace size={15} strokeWidth={2} color="#ffb156" style={{ flexShrink: 0 }} />
          <span style={{ fontSize: 12.5, color: 'var(--text-2)' }}>{backends.face_notice}</span>
        </div>
      )}

      <div className="tabs">
        <button data-on={tab === 'ranking'} onClick={() => setTab('ranking')}>Candidate ranking</button>
        <button data-on={tab === 'method'} onClick={() => setTab('method')}>How the ranking is produced</button>
      </div>

      {tab === 'method' ? <Method /> : (
        <div className="stack gap-24 page-enter">
          <div className="grid mi-split" style={{ gap: 18 }}>
            <div className="panel ticked panel-pad stack gap-14">
              <div className="row between wrap gap-10">
                <span className="section-title">Processing pipeline</span>
                {done
                  ? <Badge tone="green"><Check size={9} strokeWidth={3} />
                      COMPLETE · {formatDuration(result?.duration_ms ?? 4900)}
                    </Badge>
                  : <Badge tone="cyan" dot>PROCESSING</Badge>}
              </div>

              <div className="pipe">
                {stages.map((s, i) => {
                  const meta = PIPELINE.find((p) => p.id === s.id) ?? {};
                  const Icon = STAGE_ICON[s.id] ?? Database;
                  const st = stage > i ? 'done' : stage === i ? 'active' : 'idle';
                  const ms = s.duration_ms ?? s.ms ?? 0;
                  return (
                    <div key={s.id}>
                      {i > 0 && <div className="pipe-connector" data-lit={stage > i - 1} />}
                      <div className="pipe-stage" data-state={st}>
                        <span className="pipe-node">
                          {st === 'done' ? <Check size={14} strokeWidth={3} />
                            : st === 'active' ? <Loader2 size={14} strokeWidth={2.4} className="spin" />
                            : <Icon size={14} strokeWidth={1.9} />}
                        </span>
                        <div className="grow" style={{ minWidth: 0 }}>
                          <div className="row gap-9 wrap">
                            <span style={{ fontSize: 13, fontWeight: 500 }}>{s.label ?? meta.label}</span>
                            <span className="mono" style={{ fontSize: 9.5, color: 'var(--faint)', letterSpacing: '.1em' }}>
                              {String(i + 1).padStart(2, '0')}
                            </span>
                            {s.remaining != null && st !== 'idle' && (
                              <span className="mono" style={{ fontSize: 9.5, color: 'var(--dim)' }}>
                                {s.remaining} remaining
                              </span>
                            )}
                          </div>
                          <div className="pipe-detail">{s.detail || meta.detail}</div>
                        </div>
                        <span className="mono" style={{ fontSize: 10, color: st === 'done' ? '#7cecc0' : 'var(--faint)' }}>
                          {st === 'done' ? (ms < 1 ? `${ms.toFixed(2)}ms` : ms < 1000 ? `${ms.toFixed(1)}ms` : `${(ms / 1000).toFixed(2)}s`)
                            : st === 'active' ? '· · ·' : '—'}
                        </span>
                      </div>
                    </div>
                  );
                })}
              </div>

              {result && (
                <div style={{ fontSize: 10.5, color: 'var(--faint)', lineHeight: 1.55 }}>
                  Durations are measured server-side. The animation is replayed at a
                  readable pace — the real run completed in {result.duration_ms.toFixed(1)} ms.
                </div>
              )}
            </div>

            <div className="panel ticked panel-pad stack gap-16">
              <div className="row between wrap gap-10">
                <span className="section-title">Hard search — space reduction</span>
                <Tip content="Expensive comparison — semantic embedding and facial matching — runs only on records that survive cheap deterministic filters. This is what makes national-scale search tractable.">
                  <span className="badge badge-gray" style={{ cursor: 'help' }}>WHY THIS ORDER?</span>
                </Tip>
              </div>

              <div className="funnel">
                {funnelRows.map((r, i) => {
                  const lit = i < funnelDepth;
                  const pct = funnelRows[0].n ? (r.n / funnelRows[0].n) * 100 : 0;
                  return (
                    <Tip key={`${r.label}-${i}`} content={r.predicate || r.label} width={280}>
                      <div className="funnel-row" data-final={i === funnelRows.length - 1} style={{ width: '100%' }}>
                        <div className="tar">
                          <div className="num" style={{ fontSize: 15, fontWeight: 600, color: lit ? 'var(--text)' : 'var(--faint)' }}>
                            {lit ? r.n.toLocaleString('en-IN') : '—'}
                          </div>
                          <div className="mono" style={{ fontSize: 8.5, letterSpacing: '.1em', color: 'var(--faint)' }}>
                            {String(r.stage).toUpperCase()}
                          </div>
                        </div>
                        <div className="funnel-bar">
                          <div className="funnel-fill" style={{ width: lit ? `${Math.max(pct, 4)}%` : '0%', transitionDelay: `${i * 90}ms` }} />
                          <div className="funnel-lab">
                            <span style={{ opacity: lit ? 1 : .35 }}>{r.label}</span>
                            <span className="mono" style={{ fontSize: 10, color: 'var(--dim)', opacity: lit ? 1 : 0 }}>
                              {i === 0 ? '100%' : `−${(100 - (r.n / (funnelRows[i - 1].n || 1)) * 100).toFixed(0)}%`}
                            </span>
                          </div>
                        </div>
                      </div>
                    </Tip>
                  );
                })}
              </div>

              <div className="row gap-10" style={{ fontSize: 11.5, color: 'var(--dim)', lineHeight: 1.55 }}>
                <span style={{ width: 2, alignSelf: 'stretch', background: 'var(--line-2)', borderRadius: 2, flexShrink: 0 }} />
                {result
                  ? `Facial comparison ran on ${funnelRows[funnelRows.length - 1]?.n ?? 0} records instead of ${(funnelRows[0]?.n ?? 0).toLocaleString('en-IN')}, with no candidate eliminated on a missing field.`
                  : 'Facial comparison ran on 37 records instead of 12,482 — a 99.7% reduction in the most expensive stage, with no candidate eliminated on a missing field.'}
              </div>

              <div className="stack gap-12" style={{ paddingTop: 15, borderTop: '1px solid var(--line)' }}>
                <div className="row between wrap gap-10">
                  <span className="section-title" style={{ fontSize: 12 }}>Evidence weights applied</span>
                  <Tip content="Weights are not fixed. They shift with elapsed time, image quality, how much of the record is populated, and the measured reliability of the loaded face backend.">
                    <span className="badge badge-gray" style={{ cursor: 'help' }}>ADAPTIVE</span>
                  </Tip>
                </div>
                {weightRows(candidates[0]).map(([l, w, c], i) => (
                  <div key={l}>
                    <div className="kv"><span className="k">{l}</span><span className="v" style={{ color: c }}>{w}%</span></div>
                    <div className="meter" style={{ marginTop: 5 }}>
                      <i style={{ width: `${Math.min(100, w * 2.6)}%`, background: `linear-gradient(90deg,${c}55,${c})`,
                                  animation: `growW .9s ${200 + i * 90}ms var(--ease-out) both` }} />
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>

          <div className="stack gap-16">
            <div className="row between wrap gap-12">
              <span className="section-title">Top Potential Matches</span>
              <div className="row gap-10 wrap">
                <Badge tone="gray">{candidates.length} CANDIDATES</Badge>
                <Badge tone="amber">NOT A CONFIRMED IDENTIFICATION</Badge>
              </div>
            </div>

            <HumanLoopNotice />

            {done ? (
              candidates.length ? (
                <div className="stack gap-12">
                  {candidates.map((c, i) => (
                    <CandidateRow key={c.id} c={c} go={go} delay={i * 80}
                                  runId={result?.id} question={result?.adaptive_question} />
                  ))}
                </div>
              ) : (
                <div className="panel panel-pad" style={{ textAlign: 'center', padding: 40, color: 'var(--muted)' }}>
                  No candidate cleared the reporting threshold for this record.
                </div>
              )
            ) : (
              <div className="panel panel-pad scanbox" style={{ padding: 40, textAlign: 'center' }}>
                <i className="scanline" />
                <Loader2 size={22} className="spin" color="var(--cyan)" />
                <div className="mono mt-12 shimmer-text" style={{ fontSize: 11.5, letterSpacing: '.16em' }}>
                  RANKING CANDIDATES…
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

/** Weight breakdown from the live run when available, else the documented defaults. */
function weightRows(top) {
  const palette = {
    face: ['Facial evidence', '#35d6ff'],
    marks: ['Identification marks', '#8b7dff'],
    demographic: ['Demographic intervals', '#35dfa0'],
    time: ['Temporal plausibility', '#ffb156'],
    location: ['Geospatial plausibility', '#5b8dff'],
  };
  if (top?.sources && Object.keys(top.sources).length) {
    const total = Object.values(top.sources).reduce((sum, s) => sum + (s.weight || 0), 0) || 1;
    return Object.entries(palette)
      .filter(([k]) => top.sources[k])
      .map(([k, [label, colour]]) => [label, Math.round((top.sources[k].weight / total) * 100), colour]);
  }
  return [['Facial evidence', 34, '#35d6ff'], ['Identification marks', 26, '#8b7dff'],
          ['Demographic intervals', 18, '#35dfa0'], ['Temporal plausibility', 13, '#ffb156'],
          ['Geospatial plausibility', 9, '#5b8dff']];
}

function CandidateRow({ c, go, delay, runId, question }) {
  const col = confColor(c.confidence);
  return (
    <button className="cand" onClick={() => go('compare', { id: c.id, runId, question })}
            style={{ animation: `fadeUp .55s ${delay}ms var(--ease-out) both` }}>
      <div className="row gap-14" style={{ alignItems: 'center' }}>
        <div className="stack gap-8" style={{ alignItems: 'center' }}>
          <span className="rankchip" data-top={c.rank === 1}>#{String(c.rank).padStart(2, '0')}</span>
        </div>
        <Portrait seed={c.seed} size={78} radius={11} landmarks tone="candidate" />
      </div>

      <div className="stack gap-12" style={{ minWidth: 0 }}>
        <div className="row between wrap gap-10">
          <div>
            <div className="row gap-9 wrap">
              <span className="mono" style={{ fontSize: 12, color: 'var(--cyan)' }}>{c.id}</span>
              <Badge tone="violet">{c.label.toUpperCase()}</Badge>
              <Badge tone={c.confidence >= 85 ? 'green' : c.confidence >= 70 ? 'cyan' : 'amber'}>
                {confLabel(c.confidence)} CONFIDENCE
              </Badge>
              {c.coverage != null && c.coverage < 0.7 && (
                <Tip content="Several evidence sources had nothing to compare on this record. Its confidence is shrunk toward neutral to reflect how little evidence is behind it.">
                  <Badge tone="gray">{Math.round(c.coverage * 100)}% EVIDENCE COVERAGE</Badge>
                </Tip>
              )}
            </div>
            <div className="row gap-14 wrap mt-8" style={{ fontSize: 11.5, color: 'var(--muted)' }}>
              <span>Age {c.ageText}</span>
              <span>{c.location}</span>
              <span className="mono" style={{ fontSize: 10.5 }}>{c.date}</span>
            </div>
          </div>
          <span className="row gap-6" style={{ fontSize: 11.5, color: 'var(--cyan)' }}>
            Compare evidence <ChevronRight size={13} strokeWidth={2.4} />
          </span>
        </div>

        <div className="cand-scores">
          <EvidenceBar label="Face similarity" value={c.scores.face} delay={delay} />
          <EvidenceBar label="Identification marks" value={c.scores.marks} delay={delay + 60} />
          <EvidenceBar label="Demographic" value={c.scores.demographic} delay={delay + 120} />
          <EvidenceBar label="Time compatibility" value={c.scores.time} delay={delay + 180} />
          <EvidenceBar label="Image quality" value={c.scores.quality} delay={delay + 240} />
        </div>
      </div>

      <div className="cand-ring stack gap-8" style={{ alignItems: 'center' }}>
        <ConfidenceRing value={c.confidence} size={92} stroke={6} delay={delay + 200} />
        <span className="mono" style={{ fontSize: 9, letterSpacing: '.14em', color: col }}>{confLabel(c.confidence)}</span>
      </div>
    </button>
  );
}

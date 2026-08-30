import { useState, useMemo } from 'react';
import { MapPin, Filter, Layers } from 'lucide-react';
import IndiaMap, { project } from '../components/IndiaMap';
import { MAP_POINTS as RAW_POINTS, MAP_LINKS, CASES } from '../data/sample';
import { analyticsMap } from '../api/client';
import { useApiData } from '../api/useApiData';
import { SourceBanner } from '../components/DataState';

import { Badge, Reveal, confColor } from '../components/ui';

const SAMPLE_POINTS = RAW_POINTS.map((p) => ({ ...p, ...project(p.lon, p.lat) }));

/** API map rows -> the shape the markers expect, projected for drawing. */
function adaptPoints(rows) {
  return rows
    .filter((r) => r.lat != null && r.lon != null)
    .map((r) => ({
      id: r.case_number,
      city: r.city || (r.state ?? '—'),
      state: r.state ?? 'Unknown',
      kind: r.kind,
      lon: r.lon,
      lat: r.lat,
      conf: 0,
      ...project(r.lon, r.lat),
    }));
}
const KINDS = [
  { id: 'all', label: 'All' },
  { id: 'missing', label: 'Missing' },
  { id: 'unidentified', label: 'Unidentified' },
];

export default function Geospatial({ go }) {
  const [kind, setKind] = useState('all');
  const [minConf, setMinConf] = useState(0);
  const [state, setState] = useState('All states');

  const { data: points, loading, error, live } = useApiData(
    (signal) => analyticsMap(signal).then(adaptPoints),
    SAMPLE_POINTS,
    [],
  );

  const STATES = useMemo(
    () => ['All states', ...[...new Set(points.map((p) => p.state))].filter(Boolean).sort()],
    [points],
  );

  const pts = useMemo(
    () => points.filter((p) =>
      (kind === 'all' || p.kind === kind) &&
      (state === 'All states' || p.state === state) &&
      (p.conf ?? 0) >= minConf),
    [points, kind, minConf, state]
  );
  const visible = new Set(pts.map((p) => p.id));
  const byId = Object.fromEntries(points.map((p) => [p.id, p]));

  // Derived from whatever is currently on the map, so the panel always agrees
  // with the markers rather than asserting fixed corridors.
  const topStates = useMemo(() => {
    const tally = new Map();
    for (const p of pts) {
      const row = tally.get(p.state) ?? { total: 0, missing: 0, unidentified: 0 };
      row.total += 1;
      row[p.kind === 'missing' ? 'missing' : 'unidentified'] += 1;
      tally.set(p.state, row);
    }
    return [...tally.entries()].sort((a, b) => b[1].total - a[1].total).slice(0, 5);
  }, [pts]);

  return (
    <div className="stack gap-24">
      <div className="row between wrap gap-16">
        <div>
          <span className="eyebrow hot">GEOSPATIAL INTELLIGENCE</span>
          <h1 className="page-title mt-8">Investigations map</h1>
          <p className="page-sub">
            Case clusters, last-known locations and cross-state candidate links. Connection lines mark
            record pairs the matching engine has associated.
          </p>
        </div>
        <div className="stack gap-10" style={{ alignItems: 'flex-end' }}>
          <div className="row gap-10 wrap">
            <Badge tone="cyan"><i className="dot" />{pts.filter((p) => p.kind === 'missing').length} MISSING</Badge>
            <Badge tone="violet"><i className="dot" />{pts.filter((p) => p.kind === 'unidentified').length} UNIDENTIFIED</Badge>
          </div>
          <SourceBanner live={live} loading={loading} error={error}
                        count={live ? points.length : null} noun="geocoded cases" />
        </div>
      </div>

      <div className="grid geo-split" style={{ gap: 18 }}>
        <div className="panel ticked" style={{ padding: 16 }}>
          <div className="mapwrap">
            <svg viewBox="0 0 100 100" preserveAspectRatio="none"
                 style={{ position: 'absolute', inset: 0, width: '100%', height: '100%' }}>
              <defs>
                <pattern id="mg" width="5" height="5" patternUnits="userSpaceOnUse">
                  <path d="M5 0H0V5" fill="none" stroke="rgba(126,165,224,.08)" strokeWidth=".2" />
                </pattern>
                <linearGradient id="lnk" x1="0" y1="0" x2="1" y2="1">
                  <stop offset="0%" stopColor="rgba(53,214,255,.1)" />
                  <stop offset="50%" stopColor="rgba(53,214,255,.75)" />
                  <stop offset="100%" stopColor="rgba(139,125,255,.2)" />
                </linearGradient>
              </defs>
              <rect width="100" height="100" fill="url(#mg)" />
              <IndiaMap states fill="rgba(24,62,102,.3)" stroke="rgba(130,190,245,.5)" strokeWidth={0.32}
                        stateStroke="rgba(120,180,240,.2)" stateWidth={0.14} />
              {(live ? [] : MAP_LINKS).filter(([a, b]) => visible.has(a) && visible.has(b)).map(([a, b], i) => {
                const A = byId[a], B = byId[b];
                const mx = (A.x + B.x) / 2 - (B.y - A.y) * 0.22;
                const my = (A.y + B.y) / 2 + (B.x - A.x) * 0.22;
                const d = `M${A.x},${A.y} Q${mx},${my} ${B.x},${B.y}`;
                return (
                  <g key={i}>
                    <path d={d} fill="none" stroke="url(#lnk)" strokeWidth=".4" strokeDasharray="1.5 1.5" />
                    <circle r=".8" fill="#35d6ff">
                      <animateMotion dur={`${3.2 + i * 0.5}s`} repeatCount="indefinite" path={d} />
                    </circle>
                  </g>
                );
              })}
            </svg>

            {pts.map((p, i) => {
              const col = p.kind === 'missing' ? '#35d6ff' : '#8b7dff';
              return (
                <div key={p.id} className="marker"
                     style={{ left: `${p.x}%`, top: `${p.y}%`, '--mc': col, '--md': `${i * 0.28}s` }}
                     onClick={() => go('case', { id: p.id })}>
                  <i />
                  <div className="mtip">
                    <div className="mono" style={{ fontSize: 10, color: 'var(--cyan)' }}>{p.id}</div>
                    <div style={{ fontSize: 11.5, marginTop: 2 }}>{p.city}, {p.state}</div>
                    <div className="row gap-8 mt-8">
                      <span className="badge" style={{
                        color: col, background: `${col}18`, borderColor: `${col}45`,
                      }}>{p.kind.toUpperCase()}</span>
                      {p.conf > 0 && (
                        <span className="mono" style={{ fontSize: 10, color: confColor(p.conf) }}>{p.conf}%</span>
                      )}
                    </div>
                  </div>
                </div>
              );
            })}

            <div className="row gap-14 wrap" style={{
              position: 'absolute', left: 14, bottom: 14, padding: '8px 12px', borderRadius: 9,
              background: 'rgba(6,11,20,.8)', border: '1px solid var(--line)', backdropFilter: 'blur(8px)',
            }}>
              {[['Missing person', '#35d6ff'], ['Unidentified person', '#8b7dff'], ['Matched pair', 'rgba(53,214,255,.6)']].map(([l, c]) => (
                <span key={l} className="row gap-6" style={{ fontSize: 10.5, color: 'var(--muted)' }}>
                  <i style={{ width: 7, height: 7, borderRadius: 99, background: c, boxShadow: `0 0 8px ${c}`, display: 'block' }} />
                  {l}
                </span>
              ))}
            </div>

            <div className="mono" style={{
              position: 'absolute', right: 14, top: 14, fontSize: 9, letterSpacing: '.14em',
              color: 'var(--dim)', padding: '5px 9px', borderRadius: 7,
              background: 'rgba(6,11,20,.72)', border: '1px solid var(--line)',
            }}>
              EQUIRECTANGULAR · SCHEMATIC
            </div>
          </div>
        </div>

        <div className="stack gap-16">
          <div className="panel ticked panel-pad stack gap-16">
            <span className="section-title"><Filter size={12} strokeWidth={2} style={{ marginLeft: -2 }} /> Filters</span>

            <div className="field">
              <span className="label">Case type</span>
              <div className="seg">
                {KINDS.map((k) => <button key={k.id} data-on={kind === k.id} onClick={() => setKind(k.id)}>{k.label}</button>)}
              </div>
            </div>

            <div className="field">
              <span className="label">State</span>
              <select className="select" value={state} onChange={(e) => setState(e.target.value)}>
                {STATES.map((s) => <option key={s}>{s}</option>)}
              </select>
            </div>

            <div className="field">
              <span className="label">District</span>
              <select className="select"><option>All districts</option><option>Bengaluru Urban</option><option>Chennai</option><option>Pune City</option></select>
            </div>

            <div className="field">
              <span className="label">Date range</span>
              <div className="row gap-10">
                <input className="input" type="date" defaultValue="2026-01-01" />
                <input className="input" type="date" defaultValue="2026-08-29" />
              </div>
            </div>

            <div className="field">
              <div className="row between">
                <span className="label">Minimum confidence</span>
                <span className="mono" style={{ fontSize: 11, color: 'var(--cyan)' }}>{minConf}%</span>
              </div>
              <input type="range" min="0" max="95" value={minConf} onChange={(e) => setMinConf(+e.target.value)}
                     style={{ width: '100%', accentColor: '#35d6ff' }} />
            </div>
          </div>

          <Reveal>
            <div className="panel ticked panel-pad stack gap-12">
              <span className="section-title"><Layers size={12} strokeWidth={2} style={{ marginLeft: -2 }} /> Caseload by state</span>
              {topStates.length === 0 && (
                <p className="note" style={{ fontSize: 12, color: 'var(--muted)' }}>
                  No geocoded cases match the current filters.
                </p>
              )}
              {topStates.map(([name, counts]) => (
                <div key={name} className="row gap-11" style={{
                  padding: '11px 12px', borderRadius: 10, border: '1px solid var(--line)', background: 'rgba(4,8,16,.4)',
                }}>
                  <MapPin size={14} strokeWidth={2} color="#35d6ff" style={{ flexShrink: 0, marginTop: 1 }} />
                  <div className="grow">
                    <div className="row between gap-10">
                      <span style={{ fontSize: 12.5, fontWeight: 500 }}>{name}</span>
                      <span className="mono" style={{ fontSize: 11.5 }}>{counts.total}</span>
                    </div>
                    <div style={{ fontSize: 11, color: 'var(--muted)', marginTop: 2 }}>
                      {counts.missing} missing · {counts.unidentified} unidentified
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </Reveal>
        </div>
      </div>
    </div>
  );
}

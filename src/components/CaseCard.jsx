import { MapPin, CalendarDays, Users, ArrowUpRight, Ruler, Fingerprint } from 'lucide-react';
import Portrait from './Portrait';
import { Badge, confColor } from './ui';

// An unrecorded value must read as "Unknown", never as "undefined" — the
// uncertainty model is the point of this system, so it has to survive rendering.
function ageText(c) {
  if (c.ageMode === 'range' && c.ageMin != null && c.ageMax != null) return `${c.ageMin}–${c.ageMax}`;
  if (c.ageMode === 'exact' && c.ageExact != null) return `${c.ageExact}`;
  return 'Age unknown';
}
function heightText(c) {
  if (c.heightMode === 'range' && c.heightMin != null && c.heightMax != null) {
    return `${c.heightMin}–${c.heightMax} cm`;
  }
  if (c.heightMode === 'exact' && c.heightExact != null) return `${c.heightExact} cm`;
  return 'Height unknown';
}

export default function CaseCard({ c, go, delay = 0 }) {
  const conf = c.confidence;
  const hasMatch = conf > 0;
  const col = confColor(conf);
  const seed = parseInt(String(c.id).replace(/\D/g, '').slice(-4) || '1', 10);

  return (
    <div
      className="case-card"
      role="button" tabIndex={0}
      onClick={() => go('case', { id: c.id })}
      onKeyDown={(e) => { if (e.key === 'Enter') go('case', { id: c.id }); }}
      style={{ animation: `fadeUp .6s ${delay}ms var(--ease-out) both` }}
    >
      <div className="case-strip" style={{
        background: c.priority === 'HIGH PRIORITY'
          ? 'linear-gradient(90deg, #ff5f70, rgba(255,95,112,0))'
          : 'linear-gradient(90deg, #35d6ff, rgba(53,214,255,0))',
      }} />

      <div className="case-body">
        <div className="row between gap-10">
          <span className="mono" style={{ fontSize: 11.5, color: 'var(--cyan)', letterSpacing: '.04em', whiteSpace: 'nowrap' }}>{c.id}</span>
          <div className="row gap-6 wrap">
            {c.priority === 'HIGH PRIORITY' && <Badge dot>HIGH PRIORITY</Badge>}
            <Badge>{c.status}</Badge>
          </div>
        </div>

        <div className="row gap-14 mt-12" style={{ alignItems: 'flex-start' }}>
          <Portrait seed={seed} size={62} radius={10} tone={c.type === 'unidentified' ? 'candidate' : undefined} />
          <div className="grow stack gap-4">
            <div style={{ fontSize: 15.5, fontWeight: 600, letterSpacing: '-0.015em' }}>
              {c.nameKnown ? c.name : <span style={{ color: 'var(--muted)', fontStyle: 'italic', fontWeight: 500 }}>Identity unknown</span>}
            </div>
            <div className="mono" style={{ fontSize: 10, letterSpacing: '.13em', color: 'var(--dim)', textTransform: 'uppercase' }}>
              {c.type === 'missing' ? 'Missing Person' : 'Unidentified Person'}
            </div>
            <div className="row gap-12 wrap mt-8" style={{ fontSize: 11.5, color: 'var(--muted)' }}>
              <span className="row gap-4"><Users size={11} strokeWidth={2} /> {ageText(c)} · {c.sex}</span>
              <span className="row gap-4"><Ruler size={11} strokeWidth={2} /> {heightText(c)}</span>
            </div>
          </div>
        </div>

        <div className="row between mt-12 gap-12" style={{ alignItems: 'flex-end' }}>
          <div className="stack gap-4" style={{ fontSize: 11.5, color: 'var(--muted)' }}>
            <span className="row gap-6"><MapPin size={11} strokeWidth={2} color="var(--dim)" /> {c.location}</span>
            <span className="row gap-6"><CalendarDays size={11} strokeWidth={2} color="var(--dim)" /> Last seen {c.lastSeen}</span>
          </div>
          {/* No matching run yet means no top score — showing 0% would read as
              "we looked and found nothing", which is not what happened. */}
          <div className="tar" style={{ flexShrink: 0 }}>
            {hasMatch ? (
              <>
                <div className="num" style={{ fontSize: 20, fontWeight: 600, color: col, lineHeight: 1 }}>
                  {conf}<span style={{ fontSize: 11, opacity: .7 }}>%</span>
                </div>
                <div className="mono" style={{ fontSize: 8.5, letterSpacing: '.13em', color: 'var(--dim)', marginTop: 2 }}>TOP MATCH</div>
              </>
            ) : (
              <div className="mono" style={{ fontSize: 8.5, letterSpacing: '.12em', color: 'var(--faint)' }}>
                NOT YET MATCHED
              </div>
            )}
          </div>
        </div>

        {hasMatch && (
          <div className="meter mt-12">
            <i style={{ width: `${conf}%`, background: `linear-gradient(90deg, ${col}55, ${col})`, boxShadow: `0 0 10px -2px ${col}` }} />
          </div>
        )}

        {/* revealed on hover */}
        <div className="case-reveal">
          <div style={{ borderTop: '1px solid var(--line)', paddingTop: 11 }}>
            <div className="row gap-16 wrap" style={{ fontSize: 11.5, color: 'var(--muted)' }}>
              <span className="row gap-5"><Users size={11} strokeWidth={2} color="var(--cyan)" /> {c.matches} potential matches</span>
              <span className="row gap-5"><Fingerprint size={11} strokeWidth={2} color="var(--cyan)" /> {c.marks.length} identification marks</span>
            </div>
            <p style={{ fontSize: 11.5, color: 'var(--dim)', marginTop: 8, lineHeight: 1.55,
                        display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical', overflow: 'hidden' }}>
              {c.circumstances}
            </p>
            <div className="row gap-8 mt-12">
              <span className="btn btn-sm btn-primary" style={{ flex: 1 }}>
                Open Investigation <ArrowUpRight size={13} strokeWidth={2.2} />
              </span>
              <span className="btn btn-sm" onClick={(e) => { e.stopPropagation(); go('match', { id: c.id }); }}>
                Matches
              </span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

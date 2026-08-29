import { HelpCircle } from 'lucide-react';
import { Tip } from './ui';

const MODES = [
  { id: 'exact', label: 'Exact' },
  { id: 'range', label: 'Range' },
  { id: 'unknown', label: 'Unknown' },
];

/**
 * UncertainField — the schema primitive behind the whole platform.
 * Every attribute can be recorded as an exact value, a bounded interval,
 * or explicitly unknown. Unknown is a recorded state, not an empty field:
 * downstream scoring treats it as neutral rather than disqualifying.
 */
export default function UncertainField({
  label, value, onChange, unit = '', placeholder = '', hint,
  min = '', max = '', options,
}) {
  const mode = value?.mode || 'exact';
  const set = (patch) => onChange({ ...value, ...patch });

  return (
    <div className="field">
      <div className="row between gap-10" style={{ alignItems: 'center' }}>
        <span className="label row gap-5">
          {label}
          {hint && (
            <Tip content={hint}>
              <HelpCircle size={11} strokeWidth={2} color="var(--faint)" style={{ cursor: 'help' }} />
            </Tip>
          )}
        </span>
        <div className="seg">
          {MODES.map((m) => (
            <button key={m.id} type="button" data-on={mode === m.id} data-tone={m.id}
                    onClick={() => set({ mode: m.id })}>{m.label}</button>
          ))}
        </div>
      </div>

      {mode === 'exact' && (
        options ? (
          <select className="select" value={value?.exact || ''} onChange={(e) => set({ exact: e.target.value })}>
            <option value="">Select…</option>
            {options.map((o) => <option key={o}>{o}</option>)}
          </select>
        ) : (
          <div style={{ position: 'relative' }}>
            <input className="input" value={value?.exact ?? ''} placeholder={placeholder}
                   onChange={(e) => set({ exact: e.target.value })} />
            {unit && <Unit>{unit}</Unit>}
          </div>
        )
      )}

      {mode === 'range' && (
        <div className="row gap-10" style={{ alignItems: 'center' }}>
          <div style={{ position: 'relative', flex: 1 }}>
            <input className="input" value={value?.min ?? ''} placeholder={`Min ${min}`}
                   onChange={(e) => set({ min: e.target.value })} />
            {unit && <Unit>{unit}</Unit>}
          </div>
          <span className="mono" style={{ color: 'var(--dim)', fontSize: 12 }}>→</span>
          <div style={{ position: 'relative', flex: 1 }}>
            <input className="input" value={value?.max ?? ''} placeholder={`Max ${max}`}
                   onChange={(e) => set({ max: e.target.value })} />
            {unit && <Unit>{unit}</Unit>}
          </div>
        </div>
      )}

      {mode === 'unknown' && (
        <div className="row gap-9" style={{
          padding: '10px 12px', borderRadius: 9, border: '1px dashed rgba(126,165,224,.26)',
          background: 'rgba(126,165,224,.045)', fontSize: 12, color: 'var(--muted)',
        }}>
          <span className="badge badge-gray">UNKNOWN</span>
          <span>Recorded as unknown — scored as neutral, never disqualifying.</span>
        </div>
      )}
    </div>
  );
}

function Unit({ children }) {
  return (
    <span className="mono" style={{
      position: 'absolute', right: 11, top: '50%', transform: 'translateY(-50%)',
      fontSize: 10.5, color: 'var(--faint)', pointerEvents: 'none',
    }}>{children}</span>
  );
}

/** Compact read-only rendering of an uncertainty-aware value. */
export function UncertainValue({ v, unit = '' }) {
  if (!v || v.mode === 'unknown' || (v.mode === 'exact' && !v.exact) || (v.mode === 'range' && !v.min && !v.max)) {
    return <span className="badge badge-gray">UNKNOWN</span>;
  }
  if (v.mode === 'range') {
    return (
      <span className="row gap-6">
        <span className="mono" style={{ fontSize: 12.5 }}>{v.min}–{v.max}{unit ? ` ${unit}` : ''}</span>
        <span className="badge badge-cyan">RANGE</span>
      </span>
    );
  }
  return (
    <span className="row gap-6">
      <span className="mono" style={{ fontSize: 12.5 }}>{v.exact}{unit ? ` ${unit}` : ''}</span>
      <span className="badge badge-green">EXACT</span>
    </span>
  );
}

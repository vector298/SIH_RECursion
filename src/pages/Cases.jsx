import { useState, useMemo } from 'react';
import { Search, Plus, SlidersHorizontal } from 'lucide-react';
import { CASES } from '../data/sample';
import CaseCard from '../components/CaseCard';

const TYPES = [
  { id: 'all', label: 'All cases' },
  { id: 'missing', label: 'Missing' },
  { id: 'unidentified', label: 'Unidentified' },
];
const PRIOS = ['All priorities', 'HIGH PRIORITY', 'ACTIVE'];
const SORTS = [
  { id: 'conf', label: 'Top match confidence' },
  { id: 'recent', label: 'Most recent' },
  { id: 'matches', label: 'Candidate count' },
];

export default function Cases({ go }) {
  const [q, setQ] = useState('');
  const [type, setType] = useState('all');
  const [prio, setPrio] = useState('All priorities');
  const [sort, setSort] = useState('conf');

  const list = useMemo(() => {
    let l = CASES.filter((c) => {
      if (type !== 'all' && c.type !== type) return false;
      if (prio !== 'All priorities' && c.priority !== prio) return false;
      if (q) {
        const hay = `${c.id} ${c.name || ''} ${c.location} ${c.state} ${c.status}`.toLowerCase();
        if (!hay.includes(q.toLowerCase())) return false;
      }
      return true;
    });
    l = [...l].sort((a, b) =>
      sort === 'conf' ? b.confidence - a.confidence
      : sort === 'matches' ? b.matches - a.matches
      : new Date(b.opened) - new Date(a.opened));
    return l;
  }, [q, type, prio, sort]);

  return (
    <div className="stack gap-24">
      <div className="row between wrap gap-16">
        <div>
          <span className="eyebrow hot">CASE REGISTER</span>
          <h1 className="page-title mt-8">Cases</h1>
          <p className="page-sub">Every missing and unidentified person record visible to your jurisdiction.</p>
        </div>
        <button className="btn btn-primary" onClick={() => go('newcase')}>
          <Plus size={15} strokeWidth={2.4} /> New case
        </button>
      </div>

      <div className="panel panel-pad row wrap gap-12" style={{ alignItems: 'flex-end' }}>
        <div className="field grow" style={{ minWidth: 220 }}>
          <span className="label">Search</span>
          <div style={{ position: 'relative' }}>
            <Search size={14} strokeWidth={2} color="var(--dim)"
                    style={{ position: 'absolute', left: 11, top: '50%', transform: 'translateY(-50%)' }} />
            <input className="input" style={{ paddingLeft: 33 }} value={q} onChange={(e) => setQ(e.target.value)}
                   placeholder="Case number, name, city or state…" />
          </div>
        </div>

        <div className="field">
          <span className="label">Case type</span>
          <div className="seg">
            {TYPES.map((t) => (
              <button key={t.id} data-on={type === t.id} onClick={() => setType(t.id)}>{t.label}</button>
            ))}
          </div>
        </div>

        <div className="field" style={{ minWidth: 150 }}>
          <span className="label">Priority</span>
          <select className="select" value={prio} onChange={(e) => setPrio(e.target.value)}>
            {PRIOS.map((p) => <option key={p}>{p}</option>)}
          </select>
        </div>

        <div className="field" style={{ minWidth: 180 }}>
          <span className="label"><SlidersHorizontal size={9} style={{ display: 'inline', marginRight: 4 }} />Sort by</span>
          <select className="select" value={sort} onChange={(e) => setSort(e.target.value)}>
            {SORTS.map((s) => <option key={s.id} value={s.id}>{s.label}</option>)}
          </select>
        </div>
      </div>

      <div className="row between">
        <span className="mono" style={{ fontSize: 11, color: 'var(--dim)', letterSpacing: '.1em' }}>
          {list.length} {list.length === 1 ? 'RECORD' : 'RECORDS'}
        </span>
      </div>

      {list.length ? (
        <div className="case-grid">
          {list.map((c, i) => <CaseCard key={c.id} c={c} go={go} delay={i * 60} />)}
        </div>
      ) : (
        <div className="panel panel-pad" style={{ textAlign: 'center', padding: 44, color: 'var(--muted)' }}>
          No records match those filters.
        </div>
      )}
    </div>
  );
}

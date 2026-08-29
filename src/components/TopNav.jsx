import { useState, useEffect, useRef } from 'react';
import {
  LayoutDashboard, FolderSearch, FilePlus2, GitCompareArrows, Map, ChartNoAxesCombined,
  Bell, ShieldCheck, ChevronDown, Activity, LogOut, X,
} from 'lucide-react';
import { OFFICER, NOTIFICATIONS } from '../data/sample';
import { useBackend } from '../api/BackendContext';
import { Tip } from './ui';

const NAV = [
  { id: 'dashboard', label: 'Dashboard',         Icon: LayoutDashboard },
  { id: 'cases',     label: 'Cases',             Icon: FolderSearch },
  { id: 'newcase',   label: 'New Case',          Icon: FilePlus2 },
  { id: 'match',     label: 'Match Intelligence',Icon: GitCompareArrows },
  { id: 'geo',       label: 'Investigations',    Icon: Map },
  { id: 'analytics', label: 'Analytics',         Icon: ChartNoAxesCombined },
];

const TONE_COL = { amber: '#ffb156', cyan: '#35d6ff', green: '#35dfa0', gray: '#7d90ae' };

export default function TopNav({ route, go }) {
  const [openMenu, setOpenMenu] = useState(null); // 'notif' | 'profile' | 'mobile'
  const wrapRef = useRef(null);
  const { online } = useBackend();

  useEffect(() => {
    const h = (e) => { if (wrapRef.current && !wrapRef.current.contains(e.target)) setOpenMenu(null); };
    document.addEventListener('mousedown', h);
    return () => document.removeEventListener('mousedown', h);
  }, []);

  useEffect(() => { setOpenMenu(null); }, [route]);

  return (
    <header ref={wrapRef} style={{
      position: 'fixed', top: 0, left: 0, right: 0, height: 'var(--nav-h)', zIndex: 80,
      background: 'linear-gradient(180deg, rgba(7,12,22,.94), rgba(7,12,22,.78))',
      backdropFilter: 'blur(18px) saturate(1.2)', WebkitBackdropFilter: 'blur(18px) saturate(1.2)',
      borderBottom: '1px solid var(--line)',
    }}>
      <div style={{
        maxWidth: 1560, margin: '0 auto', height: '100%', padding: '0 22px',
        display: 'flex', alignItems: 'center', gap: 20,
      }}>
        {/* logo */}
        <button className="row gap-10" onClick={() => go('dashboard')}
          style={{ background: 'none', border: 0, cursor: 'pointer', padding: 0, flexShrink: 0 }}>
          <Logo />
          <span className="mono" style={{ fontSize: 14, fontWeight: 600, letterSpacing: '.02em' }}>
            CASE<span style={{ color: 'var(--cyan)' }}>//</span>INTEL
          </span>
        </button>

        {/* nav */}
        <nav className="nav-desktop row gap-2" style={{ marginLeft: 6 }}>
          {NAV.map(({ id, label, Icon }) => {
            const on = route === id || (id === 'cases' && route === 'case') || (id === 'match' && route === 'compare');
            return (
              <button key={id} onClick={() => go(id)} className="navbtn" data-on={on}>
                <Icon size={14} strokeWidth={1.9} />
                <span>{label}</span>
                <i className="navline" />
              </button>
            );
          })}
        </nav>

        <div className="grow" />

        {/* system status — reports the real backend state, never a fixed label */}
        <SystemStatus />

        {/* offline notice on mobile, where the status pill is hidden */}
        {!online && (
          <span className="badge badge-amber sysstat-mobile" title="Backend unreachable — showing sample data">
            DEMO
          </span>
        )}

        {/* notifications */}
        <div style={{ position: 'relative' }}>
          <button className="iconbtn" onClick={() => setOpenMenu(openMenu === 'notif' ? null : 'notif')}
                  aria-label="Notifications">
            <Bell size={16} strokeWidth={1.9} />
            <i className="dotmark" />
          </button>
          {openMenu === 'notif' && (
            <div className="menu" style={{ width: 322 }}>
              <div className="row between" style={{ padding: '11px 13px', borderBottom: '1px solid var(--line)' }}>
                <span className="eyebrow">Activity</span>
                <span className="badge badge-cyan">4 NEW</span>
              </div>
              {NOTIFICATIONS.map((n) => (
                <div key={n.id} className="menurow">
                  <i style={{ background: TONE_COL[n.tone], boxShadow: `0 0 8px ${TONE_COL[n.tone]}` }} />
                  <div className="grow">
                    <div style={{ fontSize: 12.5, fontWeight: 500 }}>{n.title}</div>
                    <div style={{ fontSize: 11, color: 'var(--muted)', marginTop: 2 }}>{n.body}</div>
                    <div className="mono" style={{ fontSize: 9.5, color: 'var(--faint)', marginTop: 4 }}>{n.t}</div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* profile */}
        <div style={{ position: 'relative' }}>
          <button className="profilebtn" onClick={() => setOpenMenu(openMenu === 'profile' ? null : 'profile')}>
            <span className="avatar">AR</span>
            <span className="profilemeta">
              <span style={{ fontSize: 12, fontWeight: 500, display: 'block', lineHeight: 1.25 }}>{OFFICER.name}</span>
              <span className="mono" style={{ fontSize: 9, color: 'var(--dim)', letterSpacing: '.1em' }}>{OFFICER.badge}</span>
            </span>
            <ChevronDown size={13} strokeWidth={2} color="var(--dim)" />
          </button>
          {openMenu === 'profile' && (
            <div className="menu" style={{ width: 260 }}>
              <div style={{ padding: '13px 14px', borderBottom: '1px solid var(--line)' }}>
                <div style={{ fontSize: 13, fontWeight: 600 }}>{OFFICER.name}</div>
                <div style={{ fontSize: 11, color: 'var(--muted)', marginTop: 3 }}>{OFFICER.unit}</div>
                <div className="row gap-8 mt-8">
                  <span className="badge badge-green"><ShieldCheck size={9} />{OFFICER.clearance}</span>
                  <span className="badge badge-gray">{OFFICER.badge}</span>
                </div>
              </div>
              <button className="menurow as-btn" onClick={() => go('landing')}>
                <LogOut size={14} strokeWidth={1.9} color="var(--muted)" />
                <span style={{ fontSize: 12.5 }}>Exit investigation portal</span>
              </button>
            </div>
          )}
        </div>

        {/* mobile nav toggle */}
        <button className="iconbtn nav-mobile-toggle"
                onClick={() => setOpenMenu(openMenu === 'mobile' ? null : 'mobile')} aria-label="Menu">
          {openMenu === 'mobile' ? <X size={17} /> : <MenuIcon />}
        </button>
      </div>

      {openMenu === 'mobile' && (
        <div className="mobilenav">
          {NAV.map(({ id, label, Icon }) => (
            <button key={id} onClick={() => go(id)} data-on={route === id}>
              <Icon size={15} strokeWidth={1.9} /> {label}
            </button>
          ))}
        </div>
      )}
    </header>
  );
}

/** Live backend state. Shows which models are actually loaded, so nobody
 *  demonstrates a fallback descriptor believing it is ArcFace. */
function SystemStatus() {
  const { status, health } = useBackend();

  const tone = status === 'online' ? '#35dfa0' : status === 'checking' ? '#7d90ae' : '#ffb156';
  const label = status === 'online' ? 'API CONNECTED'
    : status === 'checking' ? 'CONNECTING…' : 'SAMPLE DATA';

  const b = health?.backends;
  const detail = status === 'online' ? (
    <span className="stack gap-6" style={{ textAlign: 'left' }}>
      <strong style={{ color: 'var(--text)' }}>Live backends</strong>
      <span>Face: <code>{b?.face_embedding}</code>
        {b?.face_is_real_arcface ? '' : ' — fallback descriptor, not face recognition'}</span>
      <span>Semantic: <code>{b?.semantic}</code></span>
      <span>Language: <code>{b?.language}</code></span>
      <span style={{ color: 'var(--dim)' }}>
        {health?.counts?.cases?.toLocaleString('en-IN')} records indexed
      </span>
    </span>
  ) : status === 'checking' ? 'Checking for the API…' : (
    <span className="stack gap-6" style={{ textAlign: 'left' }}>
      <strong style={{ color: 'var(--text)' }}>Backend unreachable</strong>
      <span>Showing the fictional sample corpus. Rankings and pipeline timings on
        screen are illustrative, not computed.</span>
      <span style={{ color: 'var(--dim)' }}>Start it with <code>uvicorn app.main:app</code>.</span>
    </span>
  );

  return (
    <Tip content={detail} width={300}>
      <div className="sysstat row gap-8" style={{ cursor: 'help' }}>
        <Activity size={13} strokeWidth={2} color={tone} />
        <span className="mono" style={{ fontSize: 9.5, letterSpacing: '.14em', color: 'var(--muted)' }}>
          {label}
        </span>
        {status === 'online' && !b?.face_is_real_arcface && (
          <span style={{ width: 5, height: 5, borderRadius: 99, background: '#ffb156' }} />
        )}
      </div>
    </Tip>
  );
}

function MenuIcon() {
  return (
    <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
      <path d="M3 6h18M3 12h18M3 18h18" />
    </svg>
  );
}

export function Logo({ size = 26 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" fill="none" style={{ flexShrink: 0 }}>
      <defs>
        <linearGradient id="lg1" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%" stopColor="#35d6ff" /><stop offset="100%" stopColor="#4d7dff" />
        </linearGradient>
      </defs>
      <path d="M16 2.4 27.6 8v10.2c0 6.3-4.7 10.4-11.6 13.4C9.1 28.6 4.4 24.5 4.4 18.2V8L16 2.4Z"
            fill="rgba(53,214,255,.09)" stroke="url(#lg1)" strokeWidth="1.5" />
      <circle cx="14.6" cy="14.6" r="4.4" fill="none" stroke="url(#lg1)" strokeWidth="1.6" />
      <path d="M18 18l4.2 4.2" stroke="url(#lg1)" strokeWidth="1.8" strokeLinecap="round" />
      <circle cx="14.6" cy="14.6" r="1.5" fill="#35d6ff" />
    </svg>
  );
}

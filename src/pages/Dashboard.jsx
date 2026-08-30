import { Plus, ArrowRight, Radar, CircleHelp, Clock3, Database } from 'lucide-react';
import { METRICS, CASES, TIMELINE } from '../data/sample';
import { analyticsSummary, listCases, adaptCase } from '../api/client';
import { useApiData } from '../api/useApiData';
import { useBackend } from '../api/BackendContext';
import { SourceBanner, LoadingRows } from '../components/DataState';
import MetricCard from '../components/MetricCard';
import CaseCard from '../components/CaseCard';
import { Reveal, Badge, HumanLoopNotice, ConfidenceRing } from '../components/ui';

/** Map the API's counts onto the metric tiles, keeping each tile's styling.
 *
 *  Trends and sparklines are dropped: the service records no history yet, and a
 *  fabricated "+4.2%" beside a real count is the kind of detail that makes an
 *  entire demo untrustworthy once someone checks it.
 */
function metricsFrom(summary) {
  const by = Object.fromEntries(METRICS.map((m) => [m.id, m]));
  const live = (tile, value, note) => ({ ...tile, value, note, trend: null, spark: null });

  return [
    live(by.active,   summary.active_missing),
    live(by.unid,     summary.unidentified),
    live(by.matches,  summary.potential_matches, 'STORED'),
    live(by.high,     summary.high_priority),
    live(by.resolved, summary.resolved),
    // Requires resolved cases with verification timestamps to compute.
    live(by.avgtime,  null, 'NO DATA YET'),
  ];
}

/** Label, icon and colour for the language-model row.
 *
 *  Three states, not two. "Key set" and "key working" look identical from the
 *  outside — an invalid key still reports as configured while every call
 *  silently falls back — so the middle state gets its own amber label rather
 *  than being rounded up to green.
 */
function languageBackend(health) {
  const g = health?.backends?.gemini;
  if (!health?.backends?.gemini_configured) return ['local rules', Clock3, '#ffb156'];
  if (!g) return ['Gemini (key set)', Clock3, '#ffb156'];
  const model = (g.chat_model || '').replace(/^gemini-/, '');
  if (g.chat_verified) return [`Gemini ${model}`, Clock3, '#35dfa0'];
  return [`Gemini ${model} — unverified`, Clock3, '#ffb156'];
}

export default function Dashboard({ go }) {
  const { health } = useBackend();

  const summary = useApiData((signal) => analyticsSummary(signal), null, []);
  const cases = useApiData(
    (signal) => listCases({ limit: 4 }, signal).then((rows) => rows.map(adaptCase)),
    CASES.slice(0, 4),
    [],
  );

  const metrics = summary.live && summary.data ? metricsFrom(summary.data) : METRICS;
  const active = cases.data.slice(0, 4);
  const topCase = active[0];

  return (
    <div className="stack gap-32">
      {/* header */}
      <div className="row between wrap gap-16">
        <div>
          <span className="eyebrow hot">COMMAND CENTER</span>
          <h1 className="page-title mt-8">Investigation Command Center</h1>
          <p className="page-sub">Cross-state case intelligence and AI-assisted matching.</p>
        </div>
        <div className="row gap-10 wrap">
          <button className="btn" onClick={() => go('match')}>
            <Radar size={15} strokeWidth={2} /> Run matching
          </button>
          <button className="btn btn-primary" onClick={() => go('newcase')}>
            <Plus size={15} strokeWidth={2.4} /> New case
          </button>
        </div>
      </div>

      {/* metrics */}
      <div className="stack gap-12">
        <SourceBanner live={summary.live} loading={summary.loading} error={summary.error}
                      count={summary.live ? summary.data?.total_records : null} noun="records indexed" />
        <div className="metric-grid">
          {metrics.map((m, i) => <MetricCard key={m.id} metric={m} delay={i * 70} />)}
        </div>
      </div>

      {/* main split */}
      <div className="dash-split">
        <div className="stack gap-16">
          <div className="row between wrap gap-12">
            <span className="section-title">Active Investigations</span>
            <button className="btn btn-sm btn-ghost" onClick={() => go('cases')}>
              View all cases <ArrowRight size={13} strokeWidth={2.2} />
            </button>
          </div>
          {cases.loading
            ? <LoadingRows rows={2} height={220} />
            : (
              <div className="case-grid">
                {active.map((c, i) => <CaseCard key={c.id} c={c} go={go} delay={i * 80} />)}
              </div>
            )}
        </div>

        <aside className="stack gap-16 dash-rail">
          <Reveal>
            <div className="panel ticked panel-pad stack gap-14">
              <div className="row between">
                <span className="section-title" style={{ fontSize: 12 }}>Needs your decision</span>
                <Badge tone="amber" dot>2 OPEN</Badge>
              </div>

              <div className="stack gap-10" style={{
                padding: 13, borderRadius: 11, border: '1px solid rgba(255,177,86,.24)',
                background: 'linear-gradient(160deg, rgba(255,177,86,.09), rgba(255,177,86,.02))',
              }}>
                <div className="row gap-8">
                  <CircleHelp size={14} strokeWidth={2} color="#ffb156" />
                  <span className="mono" style={{ fontSize: 9.5, letterSpacing: '.14em', color: '#ffc98a' }}>
                    ADAPTIVE INVESTIGATION
                  </span>
                </div>
                <div style={{ fontSize: 12.5, lineHeight: 1.55 }}>
                  Run matching on{' '}
                  <span className="mono" style={{ color: 'var(--cyan)' }}>{topCase?.id ?? '—'}</span>{' '}
                  to see whether its leading candidates are close enough to need a targeted question.
                </div>
                <button className="btn btn-sm" style={{ alignSelf: 'flex-start' }}
                        disabled={!topCase}
                        onClick={() => topCase && go('match', { id: topCase.id })}>
                  Run matching <ArrowRight size={12} strokeWidth={2.4} />
                </button>
              </div>

              {topCase && (
                <div className="row gap-14" style={{ padding: '4px 2px' }}>
                  {topCase.confidence > 0 && (
                    <ConfidenceRing value={topCase.confidence} size={74} stroke={5} label="TOP" />
                  )}
                  <div className="stack gap-6 grow">
                    <div className="mono" style={{ fontSize: 10.5, color: 'var(--cyan)' }}>{topCase.id}</div>
                    <div style={{ fontSize: 12, color: 'var(--muted)', lineHeight: 1.5 }}>
                      {topCase.matches
                        ? `${topCase.matches} candidate${topCase.matches === 1 ? '' : 's'} ranked. Highest-confidence lead awaiting physical verification.`
                        : 'No matching run recorded yet for this case.'}
                    </div>
                    <button className="btn btn-sm btn-ghost" style={{ alignSelf: 'flex-start' }}
                            onClick={() => go('match', { id: topCase.id })}>
                      Review ranking
                    </button>
                  </div>
                </div>
              )}

              <HumanLoopNotice compact />
            </div>
          </Reveal>

          <Reveal delay={90}>
            <div className="panel panel-pad stack gap-12">
              <span className="section-title" style={{ fontSize: 12 }}>Index status</span>
              {[
                ['National record index',
                  (summary.live ? summary.data.total_records : 12482).toLocaleString('en-IN'),
                  Database, '#35d6ff'],
                ['Unidentified persons',
                  (summary.live ? summary.data.unidentified : 3096).toLocaleString('en-IN'),
                  Database, '#8b7dff'],
                ['Database',
                  health?.database === 'postgresql' ? 'PostgreSQL' : health?.database ?? 'sample',
                  Database, '#35dfa0'],
                // A key being set is not the same as a key that works, and the
                // difference is invisible until a call is made — so an
                // unconfirmed key reads amber, not green.
                ['Language model', ...languageBackend(health)],
              ].map(([l, v, Icon, c]) => (
                <div className="kv" key={l}>
                  <span className="k row gap-7"><Icon size={11} strokeWidth={2} color={c} /> {l}</span>
                  <span className="v" style={{ color: c }}>{v}</span>
                </div>
              ))}
            </div>
          </Reveal>

          <Reveal delay={160}>
            <div className="panel panel-pad stack gap-12">
              <span className="section-title" style={{ fontSize: 12 }}>Recent activity</span>
              <div className="tl" style={{ paddingLeft: 22 }}>
                {TIMELINE.slice(-4).reverse().map((t) => (
                  <div key={t.title} className="tl-item" data-pending={!!t.pending}
                       style={{ '--tl-c': { cyan: '#35d6ff', violet: '#8b7dff', amber: '#ffb156', green: '#35dfa0', gray: '#7d90ae' }[t.tone], paddingBottom: 14 }}>
                    <div style={{ fontSize: 12.5, fontWeight: 500 }}>{t.title}</div>
                    <div className="mono" style={{ fontSize: 9.5, color: 'var(--faint)', marginTop: 2 }}>{t.t}</div>
                  </div>
                ))}
              </div>
            </div>
          </Reveal>
        </aside>
      </div>
    </div>
  );
}

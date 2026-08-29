import {
  ResponsiveContainer, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend,
  AreaChart, Area, PieChart, Pie, Cell, LineChart, Line,
} from 'recharts';
import { BY_STATE, CONFIDENCE_DIST, RESOLVED_OVER_TIME, AGE_DIST, METRICS } from '../data/sample';
import { Reveal, Counter } from '../components/ui';

const AXIS = { stroke: 'rgba(126,165,224,.18)', tick: { fill: '#5b6c8a', fontSize: 10 } };
const TOOLTIP = {
  contentStyle: {
    background: 'rgba(8,14,26,.97)', border: '1px solid rgba(126,165,224,.24)',
    borderRadius: 10, fontSize: 12, boxShadow: '0 20px 50px -20px rgba(0,0,0,.9)',
  },
  labelStyle: { color: '#a9bbd4', fontSize: 11, marginBottom: 4 },
  cursor: { fill: 'rgba(53,214,255,.06)' },
};

const PIE = [
  { name: 'Missing persons', value: 12482, c: '#35d6ff' },
  { name: 'Unidentified persons', value: 3096, c: '#8b7dff' },
  { name: 'Resolved & closed', value: 1364, c: '#35dfa0' },
];

export default function Analytics() {
  return (
    <div className="stack gap-24">
      <div>
        <span className="eyebrow hot">INTELLIGENCE ANALYTICS</span>
        <h1 className="page-title mt-8">Analytics</h1>
        <p className="page-sub">
          Caseload distribution, resolution velocity and confidence characteristics across the national index.
        </p>
      </div>

      <div className="grid" style={{ gridTemplateColumns: 'repeat(auto-fit,minmax(190px,1fr))', gap: 13 }}>
        {[['Records indexed', 15578, ''], ['Cases resolved (12 mo)', 1364, ''], ['Median time to identification', 34, ' d'], ['Candidate precision @ top-1', 78, '%']]
          .map(([l, v, s], i) => (
          <div key={l} className="panel panel-pad" style={{ animation: `fadeUp .5s ${i * 70}ms var(--ease-out) both` }}>
            <div className="label">{l}</div>
            <div className="mt-8" style={{ fontSize: 26, fontWeight: 600, letterSpacing: '-0.03em' }}>
              <Counter to={v} suffix={s} />
            </div>
          </div>
        ))}
      </div>

      <div className="chart-grid">
        <Panel title="Cases by state" sub="Missing vs unidentified records held by each state bureau.">
          <ResponsiveContainer width="100%" height={280}>
            <BarChart data={BY_STATE} margin={{ top: 6, right: 6, left: -18, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(126,165,224,.08)" vertical={false} />
              <XAxis dataKey="state" {...AXIS} interval={0} angle={-28} textAnchor="end" height={62} />
              <YAxis {...AXIS} />
              <Tooltip {...TOOLTIP} />
              <Legend wrapperStyle={{ fontSize: 11, color: '#7d90ae' }} />
              <Bar dataKey="missing" name="Missing" fill="#35d6ff" radius={[3, 3, 0, 0]} maxBarSize={22} />
              <Bar dataKey="unidentified" name="Unidentified" fill="#8b7dff" radius={[3, 3, 0, 0]} maxBarSize={22} />
            </BarChart>
          </ResponsiveContainer>
        </Panel>

        <Panel title="Cases opened vs resolved" sub="Twelve-month rolling view. Resolution rate is closing the gap.">
          <ResponsiveContainer width="100%" height={280}>
            <AreaChart data={RESOLVED_OVER_TIME} margin={{ top: 6, right: 6, left: -18, bottom: 0 }}>
              <defs>
                <linearGradient id="ga" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#35dfa0" stopOpacity=".42" />
                  <stop offset="100%" stopColor="#35dfa0" stopOpacity="0" />
                </linearGradient>
                <linearGradient id="gb" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#35d6ff" stopOpacity=".3" />
                  <stop offset="100%" stopColor="#35d6ff" stopOpacity="0" />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(126,165,224,.08)" vertical={false} />
              <XAxis dataKey="m" {...AXIS} />
              <YAxis {...AXIS} />
              <Tooltip {...TOOLTIP} />
              <Legend wrapperStyle={{ fontSize: 11 }} />
              <Area type="monotone" dataKey="opened" name="Opened" stroke="#35d6ff" strokeWidth={2} fill="url(#gb)" />
              <Area type="monotone" dataKey="resolved" name="Resolved" stroke="#35dfa0" strokeWidth={2} fill="url(#ga)" />
            </AreaChart>
          </ResponsiveContainer>
        </Panel>

        <Panel title="Match confidence distribution" sub="Most candidates fall in the moderate band — exactly where officer judgement matters most.">
          <ResponsiveContainer width="100%" height={260}>
            <BarChart data={CONFIDENCE_DIST} margin={{ top: 6, right: 6, left: -18, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(126,165,224,.08)" vertical={false} />
              <XAxis dataKey="bucket" {...AXIS} />
              <YAxis {...AXIS} />
              <Tooltip {...TOOLTIP} />
              <Bar dataKey="n" name="Candidates" radius={[3, 3, 0, 0]} maxBarSize={44}>
                {CONFIDENCE_DIST.map((d, i) => (
                  <Cell key={i} fill={i >= 5 ? '#35dfa0' : i >= 3 ? '#35d6ff' : i >= 2 ? '#ffb156' : '#ff5f70'} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </Panel>

        <Panel title="Register composition" sub="Split of the national index by record class.">
          <ResponsiveContainer width="100%" height={260}>
            <PieChart>
              <Tooltip {...TOOLTIP} />
              <Pie data={PIE} dataKey="value" nameKey="name" innerRadius={62} outerRadius={96} paddingAngle={3} stroke="none">
                {PIE.map((d) => <Cell key={d.name} fill={d.c} />)}
              </Pie>
              <Legend wrapperStyle={{ fontSize: 11 }} />
            </PieChart>
          </ResponsiveContainer>
        </Panel>

        <Panel title="Age distribution of open cases" sub="Minors and young adults dominate the open caseload.">
          <ResponsiveContainer width="100%" height={250}>
            <BarChart data={AGE_DIST} layout="vertical" margin={{ top: 6, right: 16, left: 6, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(126,165,224,.08)" horizontal={false} />
              <XAxis type="number" {...AXIS} />
              <YAxis type="category" dataKey="band" {...AXIS} width={54} />
              <Tooltip {...TOOLTIP} />
              <Bar dataKey="n" name="Open cases" fill="#5b8dff" radius={[0, 3, 3, 0]} maxBarSize={20} />
            </BarChart>
          </ResponsiveContainer>
        </Panel>

        <Panel title="Average time to identification" sub="Days from case creation to officer-verified identification.">
          <ResponsiveContainer width="100%" height={250}>
            <LineChart data={METRICS[5].spark.map((v, i) => ({ m: RESOLVED_OVER_TIME[i].m, d: v }))}
                       margin={{ top: 6, right: 6, left: -18, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(126,165,224,.08)" vertical={false} />
              <XAxis dataKey="m" {...AXIS} />
              <YAxis {...AXIS} />
              <Tooltip {...TOOLTIP} />
              <Line type="monotone" dataKey="d" name="Days" stroke="#ffb156" strokeWidth={2}
                    dot={{ r: 2.5, fill: '#ffb156' }} activeDot={{ r: 4 }} />
            </LineChart>
          </ResponsiveContainer>
        </Panel>
      </div>
    </div>
  );
}

function Panel({ title, sub, children }) {
  return (
    <Reveal>
      <div className="panel ticked panel-pad stack gap-16" style={{ height: '100%' }}>
        <div>
          <span className="section-title">{title}</span>
          <p style={{ fontSize: 11.5, color: 'var(--muted)', marginTop: 7, lineHeight: 1.55 }}>{sub}</p>
        </div>
        {children}
      </div>
    </Reveal>
  );
}

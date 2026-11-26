import React, { useState } from 'react';
import { Link } from 'react-router-dom';
import { Area, AreaChart, Bar, BarChart, CartesianGrid, Cell, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { Wallet, Target, Hourglass, CheckCircle2, FolderKanban, TrendingUp, Footprints, Trophy, Coins, Layers, ArrowUpRight } from 'lucide-react';
import { api, qs } from '../lib/api.js';
import { useAuth } from '../lib/auth.jsx';
import { inr, inrShort, num, pct, greeting, roleName } from '../lib/format.js';
import { Card, Kpi, Seg, Skeleton, Empty, useLoad } from '../components/ui.jsx';
import { CountUp, LiquidOrb, Ring, Tilt } from '../components/fx.jsx';

const MONTHS = [['current', 'This month'], ['last', 'Last month'], ['next', 'Next month'], ['', 'All time']];
// SVG presentation attributes don't reliably resolve CSS variables, so read the live token values.
const cssVar = (n) => (getComputedStyle(document.documentElement).getPropertyValue(n) || '').trim() || '#6366f1';
const C = (i) => cssVar(`--chart-${(i % 6) + 1}`);

function ChartTip({ active, payload, label, money }) {
  if (!active || !payload || !payload.length) return null;
  return (
    <div className="card chart-tip">
      <div className="faint" style={{ marginBottom: 4 }}>{label}</div>
      {payload.map(p => <div key={p.dataKey} className="row" style={{ gap: 8 }}>
        <span style={{ width: 8, height: 8, borderRadius: 4, background: p.color }} /> {p.name}: <b>{money && p.dataKey !== 'visits' ? inr(p.value) : num(p.value)}</b>
      </div>)}
    </div>
  );
}

export default function Dashboard({ edition }) {
  const { user } = useAuth();
  const [mb, setMb] = useState('current');
  const { data: d, error, loading } = useLoad(() => api('/api/analytics/dashboard' + qs({ month_bucket: mb })), [mb]);
  const k = (d && d.kpis) || {};
  const first = ((user && user.name) || '').split(' ')[0];
  const trend = ((d && d.trend) || []).map(t => ({ ...t, label: String(t.date).slice(5).split('-').reverse().join('/') }));
  const banks = ((d && d.by_bank) || []).slice().sort((a, b) => (b.received + b.pending) - (a.received + a.pending)).slice(0, 8);
  const pipe = (d && d.pipeline) || [];
  const status = [['Paid', k.paid, cssVar('--good')], ['Partial', k.partial, cssVar('--warn')], ['Unpaid', k.unpaid, cssVar('--bad')]];
  const statusTotal = status.reduce((s, x) => s + (x[1] || 0), 0) || 1;
  const leaders = ((d && d.fo_leaderboard) || []).slice(0, 8);
  const topAmt = Math.max(1, ...leaders.map(r => r.collected ?? r.received ?? 0));
  const spark = trend.map(t => t.collected || 0);
  const pipeTone = ['accent', 'info', 'violet', 'warn', 'good'];

  return (
    <>
      <div className="page-head rise">
        <div className="grow">
          <h1 className="page-title">{greeting()}, <span className="grad-text">{first}</span></h1>
          <div className="page-sub">{roleName(user && user.role)} · here’s how recovery is tracking</div>
        </div>
        <Seg value={mb} onChange={setMb} options={MONTHS} />
      </div>

      {error && <Card><div style={{ color: 'var(--bad)' }}>{error}</div></Card>}

      <div className="bento">
        {/* Hero */}
        <div className="s-7 rise" style={{ '--i': 1 }}>
          <Tilt className="hero-t" max={4}>
            <section className="card hero-card">
              <div className="card-pad" style={{ padding: '24px 26px' }}>
                <div className="row" style={{ alignItems: 'stretch', gap: 22 }}>
                  <div className="grow" style={{ minWidth: 0 }}>
                    <div className="row" style={{ gap: 8 }}><span className="hero-chip-mini"><Coins size={14} /> Recovered this period</span></div>
                    <div className="hero-amt" style={{ marginTop: 14 }}>{d ? <CountUp value={k.received || 0} format={inr} /> : <Skeleton h={48} w={260} />}</div>
                    <div className="muted" style={{ fontSize: 13.5, marginTop: 6 }}>of <b style={{ color: 'var(--hero-ink)' }}>{inr(k.target)}</b> target</div>
                    <div className="hero-bar" style={{ marginTop: 16, maxWidth: 460 }}><span style={{ width: Math.min(100, k.recovery_rate || 0) + '%' }} /></div>
                    <div className="row wrap" style={{ gap: 10, marginTop: 20 }}>
                      <div className="hero-chip"><span className="l">Cash collected</span><span className="v">{inrShort(k.cash_collected)}</span></div>
                      <div className="hero-chip"><span className="l">Resolution</span><span className="v">{pct(k.resolution_rate)}</span></div>
                      <div className="hero-chip"><span className="l">Accounts</span><span className="v"><CountUp value={k.total_cases || 0} /></span></div>
                    </div>
                  </div>
                  <div className="hero-ring hide-sm">
                    <Ring value={k.recovery_rate || 0} size={168} stroke={12}>
                      {() => <LiquidOrb size={118} colors={[cssVar('--chart-1'), cssVar('--chart-2')]} />}
                    </Ring>
                    <div className="ring-label"><b><CountUp value={k.recovery_rate || 0} format={(x) => x.toFixed(1) + '%'} /></b><span>recovery</span></div>
                  </div>
                </div>
              </div>
            </section>
          </Tilt>
        </div>

        {/* KPI 2×2 */}
        <div className="s-5 kpi-2x2">
          {loading && !d ? [0, 1, 2, 3].map(i => <div key={i} className="card kpi clay"><Skeleton h={14} w="50%" /><Skeleton h={28} w="70%" style={{ marginTop: 18 }} /></div>) : <>
            <Kpi i={2} icon={Wallet} label="Recovered" value={k.received || 0} format={inrShort} sub={`${pct(k.recovery_rate)} of target`} tone="good" spark={spark} />
            <Kpi i={3} icon={Target} label="Target (ENR)" value={k.target || 0} format={inrShort} sub={`${num(k.total_cases)} accounts`} tone="accent" />
            <Kpi i={4} icon={Hourglass} label="Pending" value={k.pending || 0} format={inrShort} sub="still to recover" tone="warn" />
            <Kpi i={5} icon={CheckCircle2} label="Resolved" value={pct(k.resolution_rate)} sub={`${num(k.paid)} paid · ${num(k.partial)} partial`} tone="violet" />
          </>}
        </div>

        {/* Trend */}
        <div className="s-8 rise" style={{ '--i': 6 }}>
          <Card title="Collections trend" sub="Last 30 days · amount collected" actions={<span className="pill accent"><TrendingUp size={13} /> live</span>}>
            {trend.length ? (
              <div style={{ height: 280 }}>
                <ResponsiveContainer>
                  <AreaChart data={trend} margin={{ left: 0, right: 8, top: 6 }}>
                    <defs>
                      <linearGradient id="gc" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor={C(0)} stopOpacity={.45} /><stop offset="100%" stopColor={C(0)} stopOpacity={0} /></linearGradient>
                      <linearGradient id="gl" x1="0" y1="0" x2="1" y2="0"><stop offset="0%" stopColor={C(0)} /><stop offset="100%" stopColor={C(1)} /></linearGradient>
                    </defs>
                    <CartesianGrid stroke="var(--line)" vertical={false} />
                    <XAxis dataKey="label" tick={{ fill: 'var(--text-3)', fontSize: 11 }} axisLine={false} tickLine={false} interval="preserveStartEnd" />
                    <YAxis tick={{ fill: 'var(--text-3)', fontSize: 11 }} axisLine={false} tickLine={false} tickFormatter={inrShort} width={64} />
                    <Tooltip content={<ChartTip money />} cursor={{ stroke: C(0), strokeOpacity: .3 }} />
                    <Area isAnimationActive={false} type="monotone" dataKey="collected" name="Collected" stroke="url(#gl)" strokeWidth={3} fill="url(#gc)" activeDot={{ r: 5, strokeWidth: 0 }} />
                  </AreaChart>
                </ResponsiveContainer>
              </div>
            ) : loading ? <Skeleton h={280} /> : <Empty title="No collections yet in this period" />}
          </Card>
        </div>

        {/* Status + pipeline */}
        <div className="s-4 rise" style={{ '--i': 7 }}>
          <Card title="Account status" sub="By payment state">
            <div className="row" style={{ gap: 16 }}>
              <div style={{ width: 140, height: 140, position: 'relative' }}>
                <ResponsiveContainer>
                  <PieChart>
                    <Pie isAnimationActive={false} data={status.map(s => ({ name: s[0], value: s[1] || 0 }))} dataKey="value" innerRadius={46} outerRadius={66} paddingAngle={3} cornerRadius={6} stroke="none">
                      {status.map((s) => <Cell key={s[0]} fill={s[2]} />)}
                    </Pie>
                  </PieChart>
                </ResponsiveContainer>
                <div className="donut-c"><b><CountUp value={k.total_cases || 0} /></b><span>accounts</span></div>
              </div>
              <div className="col grow" style={{ gap: 12 }}>
                {status.map(s => (
                  <div key={s[0]}>
                    <div className="row" style={{ fontSize: 13 }}><span style={{ width: 9, height: 9, borderRadius: 3, background: s[2] }} /><span className="grow">{s[0]}</span><b className="num">{num(s[1])}</b></div>
                    <div className="bar" style={{ height: 6, marginTop: 5 }}><span style={{ width: ((s[1] || 0) / statusTotal * 100) + '%', background: s[2] }} /></div>
                  </div>
                ))}
              </div>
            </div>
            <div className="pipe">
              {pipe.map((p, i) => (
                <div key={p.key} className={'clay tone-' + pipeTone[i % 5]}>
                  <div className="num" style={{ fontWeight: 700, fontSize: 17 }}><CountUp value={p.count || 0} /></div>
                  <div className="faint" style={{ fontSize: 10.5, textTransform: 'capitalize' }}>{String(p.key).replace('_', ' ')}</div>
                </div>
              ))}
            </div>
          </Card>
        </div>

        {/* By bank */}
        <div className="s-7 rise" style={{ '--i': 8 }}>
          <Card title="Portfolio by bank" sub="Recovered vs pending" actions={<Link className="btn ghost sm" to="/cases"><Layers />Accounts<ArrowUpRight /></Link>}>
            {banks.length ? (
              <div style={{ height: 290 }}>
                <ResponsiveContainer>
                  <BarChart data={banks} layout="vertical" margin={{ left: 8, right: 12 }} barCategoryGap={10}>
                    <defs>
                      <linearGradient id="bg1" x1="0" y1="0" x2="1" y2="0"><stop offset="0%" stopColor={C(0)} stopOpacity={.75} /><stop offset="100%" stopColor={C(0)} /></linearGradient>
                      <linearGradient id="bg2" x1="0" y1="0" x2="1" y2="0"><stop offset="0%" stopColor={C(1)} stopOpacity={.55} /><stop offset="100%" stopColor={C(1)} stopOpacity={.85} /></linearGradient>
                    </defs>
                    <CartesianGrid stroke="var(--line)" horizontal={false} />
                    <XAxis type="number" tick={{ fill: 'var(--text-3)', fontSize: 11 }} tickFormatter={inrShort} axisLine={false} tickLine={false} />
                    <YAxis type="category" dataKey="bank" tick={{ fill: 'var(--text-2)', fontSize: 12 }} axisLine={false} tickLine={false} width={90} />
                    <Tooltip content={<ChartTip money />} cursor={{ fill: 'var(--bg-hover)' }} />
                    <Bar isAnimationActive={false} dataKey="received" name="Recovered" stackId="a" fill="url(#bg1)" radius={[8, 0, 0, 8]} />
                    <Bar isAnimationActive={false} dataKey="pending" name="Pending" stackId="a" fill="url(#bg2)" radius={[0, 8, 8, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            ) : loading ? <Skeleton h={290} /> : <Empty title="No portfolios in this period" />}
          </Card>
        </div>

        {/* Leaderboard */}
        <div className="s-5 rise" style={{ '--i': 9 }}>
          <Card title="Field leaderboard" sub="Top field agents by collection" actions={<Trophy size={18} className="faint" />}>
            <div className="col" style={{ gap: 12 }}>
              {leaders.map((r, i) => {
                const amt = r.collected ?? r.received ?? 0;
                return (
                  <div key={r.id || i} className="row" style={{ gap: 12 }}>
                    <span className={'medal ' + (i < 3 ? 'm' + (i + 1) : 'mx')}>{i + 1}</span>
                    <div className="grow" style={{ minWidth: 0 }}>
                      <div className="row" style={{ gap: 8 }}>
                        <b className="grow" style={{ whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{r.name}</b>
                        <span className="faint row" style={{ gap: 4, fontSize: 12 }}><Footprints size={12} />{num(r.visits)}</span>
                        <b className="num" style={{ fontSize: 13 }}>{inrShort(amt)}</b>
                      </div>
                      <div className="lb-bar"><span style={{ width: (amt / topAmt * 100) + '%' }} /></div>
                    </div>
                  </div>
                );
              })}
              {d && !leaders.length && <Empty title="No field activity yet" />}
              {!d && loading && [0, 1, 2, 3].map(i => <Skeleton key={i} h={30} />)}
            </div>
          </Card>
        </div>
      </div>
    </>
  );
}

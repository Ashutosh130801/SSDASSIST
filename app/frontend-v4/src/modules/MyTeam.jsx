import React, { useState } from 'react';
import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { CheckCircle2, Download, FolderOpen, LineChart, Pencil, Phone, Percent, UserMinus, UserPlus, Users, Wallet, IdCard } from 'lucide-react';
import { api, download } from '../lib/api.js';
import { useAuth } from '../lib/auth.jsx';
import { inr, inrShort, num, roleName } from '../lib/format.js';
import { Card, Kpi, Pill, Empty, Skeleton, useLoad, useToast } from '../components/ui.jsx';
import { ModuleHead, Chips, Avatar, Bar, Presence, usePresence, usePanel, useLive, ChartTip, chartColor } from './kit.jsx';

const MB = [['current', 'This month'], ['next', 'Next month'], ['last', 'Last month'], ['all', 'All months']];

/** Team Lead — my team: KPIs, 30-day trend, member cards (profile, performance, edit, remove) and leaderboard. */
export default function MyTeam() {
  const { user } = useAuth();
  const toast = useToast();
  const panel = usePanel();
  const [mb, setMb] = useState('current');
  const [rep, setRep] = useState('current');
  const [busy, setBusy] = useState('');
  const { data: ov, loading, error, reload } = useLoad(() => api('/api/team/overview?month_bucket=' + mb), [mb]);
  useLive(reload);
  const members = (ov && ov.members) || [];
  const pres = usePresence(members.map(m => m.id));
  const k = (ov && ov.kpis) || {};
  const trend = ((ov && ov.trend) || []).map(t => ({ label: t.date.slice(5), collected: t.collected }));
  const remove = (m) => {
    if (!window.confirm(`Remove ${m.name} from your team? They'll be marked inactive.`)) return;
    api('/api/users/' + m.id, { method: 'DELETE' }).then(() => { toast(m.name + ' removed'); reload(); }).catch(e => toast(e.message, 'err'));
  };
  const report = async (kind) => {
    setBusy(kind);
    try { await download(`/api/team/staff-report?kind=${kind}&month_bucket=${rep}&layout=compact`, `${kind === 'fos' ? 'FOS' : 'Callers'}_coverage_${rep}.xlsx`); }
    catch (e) { toast(e.message || 'Download failed', 'err'); } finally { setBusy(''); }
  };

  return (
    <>
      <ModuleHead icon={Users} title={'My Team' + (user && user.branch ? ' · ' + user.branch : '')} sub="Your agents, their books and today’s work" full="tldash">
        <button className="btn primary" onClick={() => panel('staff', {}).then(ok => ok && reload())}><UserPlus />Add member</button>
      </ModuleHead>
      <div className="card toolbar-card rise"><div className="row wrap" style={{ gap: 10 }}>
        <Chips value={mb} onChange={setMb} options={MB} />
        <div className="grow" />
        <select className="select" value={rep} onChange={e => setRep(e.target.value)} title="Month for the coverage report">
          <option value="current">This month</option><option value="last">Last month</option><option value="all">All months</option></select>
        <button className="btn" disabled={!!busy} onClick={() => report('fos')}><Download />{busy === 'fos' ? '…' : 'FOS report'}</button>
        <button className="btn" disabled={!!busy} onClick={() => report('caller')}><Download />{busy === 'caller' ? '…' : 'Caller report'}</button>
      </div></div>

      {error && <div className="card" style={{ padding: 16, color: 'var(--bad)' }}>{error}</div>}
      {loading && !ov && <div className="grid g-kpi"><Skeleton h={120} /><Skeleton h={120} /><Skeleton h={120} /><Skeleton h={120} /></div>}
      {ov && <>
        <div className="grid g-kpi" style={{ marginBottom: 16 }}>
          <Kpi icon={Users} label="Team members" i={1} value={num(k.members)} sub={`${num(k.fos)} FOS · ${num(k.callers)} callers`} />
          <Kpi icon={FolderOpen} label="Cases" i={2} value={num(k.cases)} sub={`${num(k.resolved)} resolved`} tone="info" />
          <Kpi icon={CheckCircle2} label="Recovered" i={3} value={k.recovered || 0} format={inrShort} tone="good" />
          <Kpi icon={Wallet} label="Pending" i={4} value={k.pending || 0} format={inrShort} tone="warn" />
          <Kpi icon={Percent} label="Recovery" i={5} value={Number(k.recovery_pct || 0).toFixed(1) + '%'} tone="accent" />
        </div>

        <Card title="Team collections" sub="Last 30 days" className="rise" style={{ marginBottom: 16 }}>
          {trend.length ? <div style={{ height: 220 }}><ResponsiveContainer>
            <AreaChart data={trend} margin={{ left: 0, right: 8, top: 6 }}>
              <defs><linearGradient id="tmc" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor={chartColor(0)} stopOpacity={.42} /><stop offset="100%" stopColor={chartColor(0)} stopOpacity={0} /></linearGradient></defs>
              <CartesianGrid stroke="var(--line)" vertical={false} />
              <XAxis dataKey="label" tick={{ fill: 'var(--text-3)', fontSize: 11 }} axisLine={false} tickLine={false} interval="preserveStartEnd" />
              <YAxis tick={{ fill: 'var(--text-3)', fontSize: 11 }} axisLine={false} tickLine={false} tickFormatter={inrShort} width={60} />
              <Tooltip content={<ChartTip fmt={inr} />} />
              <Area isAnimationActive={false} type="monotone" dataKey="collected" name="Collected" stroke={chartColor(0)} strokeWidth={2.5} fill="url(#tmc)" />
            </AreaChart></ResponsiveContainer></div> : <Empty title="No collections in the last 30 days" />}
        </Card>

        <div className="sec-t">Members · {members.length}</div>
        {!members.length ? <Empty icon={Users} title="No team members yet">Add FOS or callers to your team.</Empty> :
          <div className="member-grid">
            {members.map((m, i) => (
              <div key={m.id} className="card member rise" style={{ '--i': Math.min(i, 14) }}>
                <div className="row" style={{ alignItems: 'flex-start' }}>
                  <Avatar name={m.name} size={42} />
                  <div className="grow">
                    <button className="link-btn" onClick={() => panel('employee', { u: m })}>{m.name}</button>
                    <div className="cell-sub">{roleName(m.role)}{m.emp_code ? ' · ' + m.emp_code : ''}</div>
                    <Presence p={pres[String(m.id)]} />
                  </div>
                  <div className="member-pct num">{Number(m.recovery_pct || 0).toFixed(0)}%</div>
                </div>
                <Bar pct={m.recovery_pct} tone={m.recovery_pct >= 60 ? 'good' : 'accent'} h={6} />
                <div className="member-stats">
                  <div><span>Cases</span><b>{num(m.assigned)}</b></div>
                  <div><span>Resolved</span><b style={{ color: 'var(--good)' }}>{num(m.resolved)}</b></div>
                  <div><span>Recovered</span><b>{inrShort(m.recovered)}</b></div>
                </div>
                <div className="faint" style={{ fontSize: 12 }}>Today: {m.today ? (m.today.label === 'visits' ? `${m.today.count} visits` : `${m.today.count} calls · ${m.today.ptp || 0} PTP`) : '—'}</div>
                <div className="member-act">
                  {m.phone && <a className="btn sm" href={'tel:' + m.phone}><Phone />Call</a>}
                  <button className="btn sm" onClick={() => panel('employee', { u: m })}><IdCard />Profile</button>
                  <button className="btn sm" onClick={() => panel('perf', { u: m })}><LineChart />Performance</button>
                  <button className="btn sm ghost" title="Edit" onClick={() => panel('staff', { editing: m }).then(ok => ok && reload())}><Pencil /></button>
                  <button className="btn sm ghost danger" title="Remove" onClick={() => remove(m)}><UserMinus /></button>
                </div>
              </div>
            ))}
          </div>}

        {ov.leaderboard && ov.leaderboard.length > 0 && <Card title="Leaderboard" pad={false} className="rise" style={{ marginTop: 16 }}>
          <div className="table-wrap"><table className="t">
            <thead><tr><th>#</th><th>Member</th><th>Role</th><th className="r">Cases</th><th className="r">Recovered</th><th style={{ width: 200 }}>Recovery</th></tr></thead>
            <tbody>{ov.leaderboard.map((m, i) => <tr key={m.id}>
              <td>{i < 3 ? <span className={'medal m' + (i + 1)}>{i + 1}</span> : i + 1}</td>
              <td><div className="row" style={{ gap: 8 }}><Avatar name={m.name} size={26} /><b>{m.name}</b></div></td>
              <td><Pill tone="neutral">{roleName(m.role)}</Pill></td><td className="r">{num(m.assigned)}</td>
              <td className="r" style={{ color: 'var(--good)' }}>{inr(m.recovered)}</td>
              <td><div className="row" style={{ gap: 8 }}><Bar pct={m.recovery_pct} h={6} /><b className="num" style={{ minWidth: 44 }}>{Number(m.recovery_pct || 0).toFixed(1)}%</b></div></td>
            </tr>)}</tbody></table></div>
        </Card>}
      </>}
    </>
  );
}

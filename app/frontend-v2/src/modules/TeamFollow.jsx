import React, { useMemo, useState } from 'react';
import { CheckCircle2, Clock, Download, Eye, FolderOpen, History, IdCard, LineChart, MapPin, Percent, Phone, PhoneCall, Footprints, Trash2, UserPlus, Users, Wallet } from 'lucide-react';
import { api } from '../lib/api.js';
import { inr, inrShort, num } from '../lib/format.js';
import { Card, Kpi, Pill, Empty, Skeleton, useLoad, useToast } from '../components/ui.jsx';
import { ModuleHead, Chips, Avatar, Bar, Presence, usePresence, usePanel, useLive, Modal, SearchBox } from './kit.jsx';

const MB = [['current', 'This month'], ['next', 'Next month'], ['last', 'Last month'], ['all', 'All months']];
const tm = s => { if (!s) return '—'; try { return new Date(s).toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit' }); } catch (e) { return '—'; } };
const hit = (q, ...xs) => !q || xs.some(x => String(x || '').toLowerCase().includes(q.toLowerCase()));

/** Board of the people a team follower tracks. `followerId` = HR / HO preview of another follower. */
export function FollowBoard({ followerId, embedded }) {
  const panel = usePanel();
  const [mb, setMb] = useState('current');
  const [q, setQ] = useState(''); const [roleF, setRoleF] = useState('all'); const [sort, setSort] = useState('name');
  const { data: d, loading, error, reload } = useLoad(
    () => api('/api/team-follow/me/members?month_bucket=' + mb + (followerId ? '&follower_id=' + followerId : '')), [mb, followerId]);
  useLive(reload);
  const all = (d && d.members) || [];
  const pres = usePresence(all.map(m => m.id));
  const t = (d && d.totals) || {};
  const rows = useMemo(() => {
    const by = { name: (a, b) => a.name.localeCompare(b.name), recovered: (a, b) => b.money.recovered - a.money.recovered,
      pct: (a, b) => b.money.recovery_pct - a.money.recovery_pct, today: (a, b) => b.money.collected_today - a.money.collected_today,
      activity: (a, b) => (b.activity.visits_today + b.activity.calls_today) - (a.activity.visits_today + a.activity.calls_today) };
    return all.filter(m => roleF === 'all' || (roleF === 'fos' ? m.fos_hat : m.caller_hat))
      .filter(m => hit(q, m.name, m.all_ids, m.branch, m.location, m.phone)).sort(by[sort] || by.name);
  }, [all, roleF, q, sort]);
  const csv = () => {
    const H = ['Name', 'IDs', 'Role', 'Branch', 'Checked in', 'Assigned', 'Paid', 'PTP open', 'ENR', 'Recovered', 'Recovery %', 'Pending', 'Collected (calls+visits)', 'Collected today', 'Visits today', 'Visits (month)', 'Calls today', 'Calls (month)'];
    const R = rows.map(m => [m.name, m.all_ids, m.role_label, m.branch || '', tm(m.attendance.check_in_at), m.cases.assigned, m.cases.paid, m.cases.ptp_open, m.money.enr, m.money.recovered, m.money.recovery_pct, m.money.pending, m.money.collected_logs, m.money.collected_today, m.activity.visits_today, m.activity.visits_month, m.activity.calls_today, m.activity.calls_month]);
    const body = [H, ...R].map(r => r.map(x => '"' + String(x == null ? '' : x).replace(/"/g, '""') + '"').join(',')).join('\n');
    const a = document.createElement('a'); a.href = URL.createObjectURL(new Blob([body], { type: 'text/csv' })); a.download = 'team_follow_up.csv'; a.click();
  };

  return (
    <>
      <div className="card toolbar-card rise"><div className="row wrap" style={{ gap: 10 }}>
        <Chips value={mb} onChange={setMb} options={MB} />
        <SearchBox value={q} onChange={setQ} placeholder="Search name / ID / branch" width={240} />
        <Chips value={roleF} onChange={setRoleF} options={[['all', 'All'], ['fos', 'Field agents'], ['caller', 'Callers']]} />
        <div className="grow" />
        <select className="select" value={sort} onChange={e => setSort(e.target.value)}>
          <option value="name">Sort: Name</option><option value="recovered">Sort: Recovered ₹</option><option value="pct">Sort: Recovery %</option>
          <option value="today">Sort: Collected today</option><option value="activity">Sort: Activity today</option></select>
        <button className="btn" onClick={csv} disabled={!rows.length}><Download />CSV</button>
      </div></div>

      {error && <div className="card" style={{ padding: 16, color: 'var(--bad)' }}>{error}</div>}
      {loading && !d && <div className="grid g-kpi"><Skeleton h={120} /><Skeleton h={120} /><Skeleton h={120} /><Skeleton h={120} /></div>}
      {d && <>
        <div className="grid g-kpi" style={{ marginBottom: 16 }}>
          <Kpi icon={Users} label="Team members" i={1} value={num(t.members)} sub={`${num(t.present)} checked in today`} />
          <Kpi icon={FolderOpen} label="Cases" i={2} value={num(t.assigned)} sub={`${num(t.paid)} paid · ${num(t.ptp_open)} PTP open`} tone="info" />
          <Kpi icon={CheckCircle2} label="Recovered" i={3} value={t.recovered || 0} format={inrShort} tone="good" />
          <Kpi icon={Wallet} label="Pending" i={4} value={t.pending || 0} format={inrShort} tone="warn" />
          <Kpi icon={Percent} label="Recovery" i={5} value={Number(t.recovery_pct || 0).toFixed(1) + '%'} tone="accent" />
          <Kpi icon={Clock} label="Today" i={6} value={t.collected_today || 0} format={inrShort} tone="good" sub={`${num(t.visits_today)} visits · ${num(t.calls_today)} calls`} />
        </div>
        <div className="sec-t">Team members · {rows.length}</div>
        {!all.length ? <Empty icon={Eye} title="No one added yet">HR / Head Office can add FOS or callers from Manpower → Field TL groups.</Empty> :
          <div className="member-grid">
            {rows.map((m, i) => (
              <div key={m.id} className="card member rise" style={{ '--i': Math.min(i, 14) }}>
                <div className="row" style={{ alignItems: 'flex-start' }}>
                  <Avatar name={m.name} size={42} />
                  <div className="grow">
                    <button className="link-btn" onClick={() => panel('employee', { u: m })}>{m.name}</button>
                    <div className="cell-sub">{m.role_label}{m.also_field_agent && m.role !== 'fos' ? ' + FOS' : ''}{m.also_caller && m.role !== 'telecaller' ? ' + Caller' : ''}{m.all_ids ? ' · ' + m.all_ids : ''}{m.branch ? ' · ' + m.branch : ''}</div>
                    <Presence p={pres[String(m.id)]} />
                  </div>
                  <div className="member-pct num">{Number(m.money.recovery_pct || 0).toFixed(0)}%</div>
                </div>
                <Bar pct={m.money.recovery_pct} tone={m.money.recovery_pct >= 60 ? 'good' : 'accent'} h={6} />
                <div className="faint" style={{ fontSize: 12 }}>
                  {m.attendance.check_in_at ? <>In {tm(m.attendance.check_in_at)}{m.attendance.late ? ' · late' : ''}{m.attendance.check_out_at ? ' · Out ' + tm(m.attendance.check_out_at) : ''}</> : <span style={{ color: 'var(--warn)' }}>Not checked in today</span>}
                  {m.fos_hat && m.activity.last_ping ? ' · last GPS ' + tm(m.activity.last_ping) : ''}
                </div>
                <div className="member-stats">
                  <div><span>Cases</span><b>{num(m.cases.assigned)}</b></div>
                  <div><span>Paid</span><b style={{ color: 'var(--good)' }}>{num(m.cases.paid)}</b></div>
                  <div><span>PTP open</span><b style={{ color: 'var(--warn)' }}>{num(m.cases.ptp_open)}</b></div>
                </div>
                <div className="member-stats">
                  <div><span>Recovered</span><b>{inrShort(m.money.recovered)}</b></div>
                  <div><span>Pending</span><b>{inrShort(m.money.pending)}</b></div>
                  <div><span>Today</span><b style={{ color: 'var(--good)' }}>{inrShort(m.money.collected_today)}</b></div>
                </div>
                <div className="row wrap" style={{ gap: 6, fontSize: 12 }}>
                  {m.fos_hat && <Pill tone="info"><Footprints size={12} /> {m.activity.visits_today} visits today · {m.activity.visits_month} mo</Pill>}
                  {m.caller_hat && <Pill tone="info"><PhoneCall size={12} /> {m.activity.calls_today} calls today · {m.activity.calls_month} mo</Pill>}
                </div>
                {m.cases.banks.length > 0 && <div className="faint" style={{ fontSize: 11.5 }}>Portfolios: {m.cases.banks.join(', ')}</div>}
                <div className="member-act">
                  {m.phone && <a className="btn sm" href={'tel:' + m.phone}><Phone />Call</a>}
                  <button className="btn sm" onClick={() => panel('employee', { u: m })}><IdCard />Profile</button>
                  <button className="btn sm" onClick={() => panel('perf', { u: m })}><LineChart />Performance</button>
                  {m.fos_hat && <button className="btn sm" onClick={() => panel('liveRoute', { officer: m })}><MapPin />Live</button>}
                  {m.fos_hat && <button className="btn sm" onClick={() => panel('routeHistory', { officer: m })}><History />History</button>}
                </div>
              </div>))}
          </div>}
        {rows.length > 0 && !embedded && <Card title="Leaderboard" sub="Recovery across every portfolio" pad={false} className="rise" style={{ marginTop: 16 }}>
          <div className="table-wrap"><table className="t">
            <thead><tr><th>#</th><th>Person</th><th className="r">Cases</th><th className="r">Recovered</th><th className="r">Collected (calls+visits)</th><th style={{ width: 200 }}>Recovery</th></tr></thead>
            <tbody>{[...rows].sort((a, b) => b.money.recovered - a.money.recovered).map((m, i) => <tr key={m.id}>
              <td>{i < 3 ? <span className={'medal m' + (i + 1)}>{i + 1}</span> : i + 1}</td>
              <td><div className="row" style={{ gap: 8 }}><Avatar name={m.name} size={26} /><b>{m.name}</b></div></td>
              <td className="r">{num(m.cases.assigned)}</td>
              <td className="r" style={{ color: 'var(--good)' }}>{inr(m.money.recovered)}</td>
              <td className="r">{inr(m.money.collected_logs)}</td>
              <td><div className="row" style={{ gap: 8 }}><Bar pct={m.money.recovery_pct} h={6} /><b className="num" style={{ minWidth: 44 }}>{Number(m.money.recovery_pct || 0).toFixed(1)}%</b></div></td>
            </tr>)}</tbody></table></div>
        </Card>}
      </>}
    </>
  );
}

/** Team Follower view — the complete performance of the people they follow. */
export default function TeamFollow() {
  return (
    <>
      <ModuleHead icon={Eye} title="Field TL" sub="Complete performance of your FOS / callers — every bank and portfolio" />
      <FollowBoard />
    </>
  );
}

/** HR / admin / HO: pick a follower and add / remove the FOS & callers they track. */
export function FollowManageModal({ open, onClose, initialId }) {
  const toast = useToast();
  const [sel, setSel] = useState(initialId || null);
  const [fq, setFq] = useState(''); const [q, setQ] = useState(''); const [pick, setPick] = useState({});
  const [busy, setBusy] = useState(false); const [preview, setPreview] = useState(false);
  const { data: list, reload } = useLoad(() => open ? api('/api/team-follow/followers') : Promise.resolve(null), [open]);
  const { data: cand } = useLoad(() => open ? api('/api/team-follow/candidates') : Promise.resolve(null), [open]);
  const followers = list || [];
  const curId = sel || (followers[0] && followers[0].id);
  const cur = followers.find(f => f.id === curId);
  const mine = new Set((cur ? cur.members : []).map(m => m.id));
  const candRows = (cand || []).filter(u => u.id !== curId && !mine.has(u.id)).filter(u => hit(q, u.name, u.all_ids, u.branch, u.location));
  const picked = Object.keys(pick).filter(k => pick[k]).map(Number);
  const add = async () => {
    if (!picked.length) { toast('Pick at least one FOS or caller', 'err'); return; }
    setBusy(true);
    try { await api(`/api/team-follow/${curId}/members`, { method: 'POST', body: { member_ids: picked } }); setPick({}); toast(`Added ${picked.length}`); reload(); }
    catch (e) { toast(e.message, 'err'); } finally { setBusy(false); }
  };
  const remove = async (m) => {
    if (!window.confirm(`Remove ${m.name} from ${cur.name}'s Field TL group?`)) return;
    try { await api(`/api/team-follow/${curId}/members/${m.id}`, { method: 'DELETE' }); toast(m.name + ' removed'); reload(); } catch (e) { toast(e.message, 'err'); }
  };
  return (
    <Modal open={open} onClose={onClose} width={1100} title="Field TL groups"
      sub="Choose a Field TL, then add the FOS / callers whose complete performance they track. Create a Field TL by adding staff with the Field TL role, or tick “Also a Field TL” on a team lead / FOS / caller.">
      {!list ? <Skeleton h={200} /> : !followers.length ? <Empty icon={Eye} title="No Field TLs yet">Use Add staff with role “Field TL”, or edit a team lead / FOS / caller and tick “Also a Field TL”.</Empty> :
        <div className="tf-manage">
          <div className="card tf-list">
            <SearchBox value={fq} onChange={setFq} placeholder="Search Field TLs" width="100%" />
            {followers.filter(f => hit(fq, f.name, f.tf_emp_code, f.all_ids)).map(f => (
              <button key={f.id} className={'tf-item' + (f.id === curId ? ' on' : '')} onClick={() => { setSel(f.id); setPreview(false); setPick({}); }}>
                <Avatar name={f.name} size={30} />
                <span className="grow"><b>{f.name}</b><span className="cell-sub">{f.tf_emp_code || '—'} · {f.primary_follower ? 'Field TL' : f.role_label + ' + Field TL'} · {f.member_count} members</span></span>
              </button>))}
          </div>
          {cur && <div className="grow" style={{ minWidth: 0 }}>
            <div className="row wrap" style={{ gap: 8, marginBottom: 10 }}>
              <b>{cur.name}</b><Pill tone="accent">{cur.tf_emp_code || '—'}</Pill><span className="faint">{cur.member_count} members</span>
              <div className="grow" />
              <button className={'btn sm' + (preview ? ' primary' : '')} onClick={() => setPreview(p => !p)}><Eye />{preview ? 'Back to members' : 'Preview their board'}</button>
            </div>
            {preview ? <FollowBoard followerId={cur.id} embedded /> : <>
              <Card title="Members" pad={false}>
                {!cur.members.length ? <div className="faint" style={{ padding: 14 }}>No one yet — add FOS / callers below.</div> :
                  <div className="table-wrap" style={{ maxHeight: 220 }}><table className="t">
                    <thead><tr><th>Name</th><th>ID</th><th>Role</th><th>Branch</th><th /></tr></thead>
                    <tbody>{cur.members.map(m => <tr key={m.id}><td><b>{m.name}</b></td><td className="mono">{m.all_ids}</td><td>{m.role_label}</td><td>{m.branch || '—'}</td>
                      <td className="r"><button className="btn sm ghost danger" onClick={() => remove(m)}><Trash2 />Remove</button></td></tr>)}</tbody></table></div>}
              </Card>
              <Card title="Add FOS / callers" pad={false} style={{ marginTop: 12 }}>
                <div className="row wrap" style={{ gap: 8, padding: '10px 14px' }}>
                  <SearchBox value={q} onChange={setQ} placeholder="Search name / ID / branch" width={260} />
                  <div className="grow" />
                  <button className="btn sm" onClick={() => { const n = {}; candRows.forEach(u => { n[u.id] = true; }); setPick(n); }}>Select shown</button>
                  <button className="btn sm primary" disabled={busy || !picked.length} onClick={add}><UserPlus />{busy ? 'Adding…' : `Add selected (${picked.length})`}</button>
                </div>
                {!cand ? <Skeleton h={120} /> : <div className="table-wrap" style={{ maxHeight: 280 }}><table className="t">
                  <thead><tr><th /><th>Name</th><th>ID</th><th>Role</th><th>Branch</th></tr></thead>
                  <tbody>{candRows.slice(0, 300).map(u => <tr key={u.id} style={{ cursor: 'pointer' }} onClick={() => setPick(p => ({ ...p, [u.id]: !p[u.id] }))}>
                    <td><input type="checkbox" readOnly checked={!!pick[u.id]} /></td><td>{u.name}</td><td className="mono">{u.all_ids}</td>
                    <td>{u.role_label}{u.also_field_agent && u.role !== 'fos' ? ' + FOS' : ''}{u.also_caller && u.role !== 'telecaller' ? ' + Caller' : ''}</td><td>{u.branch || '—'}</td></tr>)}</tbody></table></div>}
              </Card></>}
          </div>}
        </div>}
    </Modal>
  );
}

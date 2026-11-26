import React, { useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { UserCheck, UserX, Palmtree, Clock3, Wifi, Search, Download, FileSpreadsheet, SlidersHorizontal } from 'lucide-react';
import { api, qs, download } from '../lib/api.js';
import { fmtTime, istToday, roleName, initials, num } from '../lib/format.js';
import { Card, Kpi, Seg, Pill, Empty, Skeleton, useLoad, useToast } from '../components/ui.jsx';

const ST = { present: ['good', 'Present'], absent: ['bad', 'Absent'], leave: ['info', 'Leave'], half_leave: ['warn', 'Half-day leave'], half_day: ['warn', 'Half day'], weekoff: ['neutral', 'Week off'] };
const dur = (s) => { s = Math.max(0, Math.floor(s || 0)); const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60); return h ? `${h}h ${m}m` : `${m}m`; };

export default function Attendance() {
  const [date, setDate] = useState(istToday());
  const [st, setSt] = useState('');
  const [q, setQ] = useState('');
  const toast = useToast();
  const { data, loading, error } = useLoad(() => api('/api/attendance/day' + qs({ date })), [date]);
  const rows = (data && data.rows) || [];
  const s = (data && data.summary) || {};
  const shown = useMemo(() => rows.filter(r => (!st || (st === 'late' ? r.late : st === 'online' ? ['active', 'idle'].includes(r.presence && r.presence.state) : r.status === st))
    && (!q || `${r.name} ${r.emp_code || ''} ${r.branch || ''}`.toLowerCase().includes(q.toLowerCase()))), [rows, st, q]);

  const fosReport = async (kind) => {
    try {
      if (kind === 'daily') await download('/api/attendance/fos-report/daily.xlsx' + qs({ start: date, end: date }), `FOS_Daily_Visit_Report_${date}.xlsx`);
      else await download('/api/attendance/fos-report/monthly.xlsx', 'FOS_Visit_Attendance_Sheet.xlsx');
    } catch (e) { toast(e.message, 'err'); }
  };

  return (
    <>
      <div className="page-head rise">
        <div className="grow"><h1 className="page-title">Attendance</h1><div className="page-sub">Check-ins, presence and working hours</div></div>
        <input type="date" className="input" value={date} max={istToday()} onChange={e => setDate(e.target.value)} />
        <button className="btn" onClick={() => fosReport('daily')}><FileSpreadsheet />FOS daily report</button>
        <button className="btn" onClick={() => fosReport('monthly')}><Download />FOS monthly sheet</button>
        <Link className="btn" to="/m/attendance" title="Month view, per-person detail, previews and every download"><SlidersHorizontal />Full module</Link>
      </div>

      <div className="grid g-kpi" style={{ marginBottom: 16 }}>
        <Kpi icon={UserCheck} label="Present" i={1} value={num(s.present)} sub={`of ${num(s.total)} staff`} tone="good" />
        <Kpi icon={Clock3} label="Late" i={2} value={num(s.late)} sub="after shift start" tone="warn" />
        <Kpi icon={UserX} label="Absent" i={3} value={num(s.absent)} sub="no check-in" tone="bad" />
        <Kpi icon={Palmtree} label="On leave" i={4} value={num((s.leave || 0) + (s.half_leave || 0))} sub="approved" tone="info" />
        <Kpi icon={Wifi} label="Online now" i={5} tone="violet" value={num(s.online)} sub="active or idle" />
      </div>

      <Card pad={false}>
        <div className="row wrap" style={{ padding: 14, gap: 10, borderBottom: '1px solid var(--line)' }}>
          <Seg value={st} onChange={setSt} options={[['', 'All'], ['present', 'Present'], ['late', 'Late'], ['absent', 'Absent'], ['leave', 'Leave'], ['online', 'Online']]} />
          <div className="input-icon grow" style={{ maxWidth: 340 }}><Search /><input className="input" placeholder="Search name, ID, branch…" value={q} onChange={e => setQ(e.target.value)} /></div>
        </div>
        {error && <div style={{ padding: 16, color: 'var(--bad)' }}>{error}</div>}
        <div className="table-wrap" style={{ maxHeight: 'calc(100vh - 380px)' }}>
          <table className="t">
            <thead><tr><th>Employee</th><th>Status</th><th>Presence</th><th>Check-in</th><th>Check-out</th><th className="r">Worked</th><th className="r">Idle</th></tr></thead>
            <tbody>
              {loading && !rows.length && [...Array(8)].map((_, i) => <tr key={i}><td colSpan={7}><Skeleton h={18} /></td></tr>)}
              {shown.map(r => {
                const [tone, lbl] = ST[r.status] || ['neutral', r.status || '—'];
                const pr = (r.presence && r.presence.state) || 'offline';
                return (
                  <tr key={r.user_id}>
                    <td><div className="row" style={{ gap: 10 }}><span className="avatar" style={{ width: 30, height: 30, fontSize: 11 }}>{initials(r.name)}</span>
                      <div><div className="cell-main">{r.name}</div><div className="cell-sub">{[r.emp_code, roleName(r.role), r.branch].filter(Boolean).join(' · ')}</div></div></div></td>
                    <td><Pill tone={tone} dot>{lbl}</Pill>{r.late && <Pill tone="warn">Late</Pill>}</td>
                    <td><Pill tone={pr === 'active' ? 'good' : pr === 'idle' ? 'warn' : 'neutral'} dot>{pr[0].toUpperCase() + pr.slice(1)}</Pill></td>
                    <td className="num">{fmtTime(r.check_in_at) || <span className="faint">—</span>}</td>
                    <td className="num">{fmtTime(r.check_out_at) || <span className="faint">—</span>}</td>
                    <td className="r">{r.worked_seconds ? dur(r.worked_seconds) : '—'}</td>
                    <td className="r faint">{r.idle_seconds ? dur(r.idle_seconds) : '—'}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          {!loading && !shown.length && <Empty icon={UserCheck} title="No one matches these filters" />}
        </div>
      </Card>
    </>
  );
}

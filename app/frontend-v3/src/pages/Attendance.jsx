import React, { useEffect, useMemo, useState } from 'react';
import { CalendarDays, CalendarRange, Clock3, Download, FileSpreadsheet, MapPin, Printer, Satellite, UserCheck, UserX, Palmtree, Wifi, Timer, Wallet, CalendarClock } from 'lucide-react';
import { api, download } from '../lib/api.js';
import { useAuth } from '../lib/auth.jsx';
import { cx, fmtTime, istToday, num, roleName, inr } from '../lib/format.js';
import { Card, Kpi, Pill, Empty, Skeleton, useLoad } from '../components/ui.jsx';
import { ModuleHead, Chips, SearchBox, Avatar, Presence, useLive, useClassicUI, printTables } from '../modules/kit.jsx';

const dur = (s) => { s = Math.max(0, Math.floor(s || 0)); const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60); return h ? `${h}h ${m}m` : `${m}m`; };
const ATT = { 'H•': 'violet', H: 'orange', P: 'good', L: 'warn', A: 'bad', W: 'neutral', LV: 'info' };
const label = (r) => (r.half_day_leave || r.status === 'half_leave'
  ? 'Half-day leave (approved)' + (r.check_in_at ? (r.late ? ' · checked in late' : ' · checked in') : ' · no check-in')
  : r.status === 'half_day' ? 'Half day · checked in after 11:30'
  : r.status === 'leave' ? 'Leave' : r.late ? 'Late' : ({ present: 'Present', weekoff: 'Week-off', absent: 'Absent' }[r.status] || r.status || ''));
const tone = (r) => (r.half_day_leave || r.status === 'half_leave' ? 'violet' : r.status === 'half_day' ? 'warn' : r.status === 'leave' ? 'info' : r.late ? 'warn' : r.status === 'present' ? 'good' : r.status === 'absent' ? 'bad' : 'neutral');
const VICI = { READY: ['Ready', 'good'], CLOSER: ['Ready (inbound)', 'good'], QUEUE: ['Call ringing', 'info'], INCALL: ['In call', 'info'], PAUSED: ['Paused', 'warn'], DISPO: ['Wrap-up', 'accent'], LOGGED_OUT: ['Not logged in', 'neutral'], NOT_FOUND: ['ID not in ViciDial', 'bad'] };
const ymd = (d) => d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0');

/** Attendance — day board, month grid and salary-cycle range, with every filter, live ViciDial
 *  state, per-person detail, FOS visit reports, print / CSV / Excel. */
export default function Attendance() {
  const { user } = useAuth();
  const ui = useClassicUI();
  const today = istToday();
  const [tab, setTab] = useState('today');
  const [date, setDate] = useState(today);
  const [month, setMonth] = useState(today.slice(0, 7));
  const [role, setRole] = useState(''); const [loc, setLoc] = useState(''); const [q, setQ] = useState(''); const [statF, setStatF] = useState('');
  const cycle = (back) => { const t = new Date(today + 'T00:00:00'); const endM = t.getMonth() + (t.getDate() >= 21 ? 1 : 0) - back; const end = new Date(t.getFullYear(), endM, 20); const start = new Date(end.getFullYear(), end.getMonth() - 1, 21); return [ymd(start), ymd(end)]; };
  const [rStart, setRStart] = useState(() => cycle(0)[0]); const [rEnd, setREnd] = useState(() => cycle(0)[1]);
  const rangeQ = () => { const p = new URLSearchParams(); if (tab === 'range') { p.set('start', rStart); p.set('end', rEnd); } else p.set('month', month); if (role) p.set('role', role); return p; };
  const dayL = useLoad(() => (tab === 'today' ? api('/api/attendance/day?date=' + date + (role ? '&role=' + role : '')).catch(() => null) : Promise.resolve(null)), [tab, date, role]);
  const monL = useLoad(() => (tab !== 'today' ? api('/api/attendance/month?' + rangeQ()).catch(() => null) : Promise.resolve(null)), [tab, month, role, rStart, rEnd]);
  useLive(() => (tab === 'today' ? dayL.reload() : monL.reload()));
  useEffect(() => { if (tab !== 'today') return undefined; const t = setInterval(dayL.reload, 30000); return () => clearInterval(t); }, [tab, date, role]); // eslint-disable-line
  const canVici = ['admin', 'headoffice', 'hr', 'manager', 'teamlead'].includes(user.role);
  const [vici, setVici] = useState(null);
  useEffect(() => {
    if (!canVici || tab !== 'today' || date !== today) { setVici(null); return undefined; }
    let stop = false; const pull = () => api('/api/integration/vicidial/agents-live').then(r => !stop && setVici(r)).catch(() => !stop && setVici(null));
    pull(); const t = setInterval(pull, 20000); return () => { stop = true; clearInterval(t); };
  }, [tab, date, canVici]); // eslint-disable-line
  const showVici = !!(vici && (Object.keys(vici.agents || {}).length || vici.error));

  const day = dayL.data; const mon = monL.data;
  const roles = day ? [...new Set(day.rows.map(r => r.role))].sort() : [];
  const src = tab === 'today' ? (day ? day.rows : []) : (mon ? mon.people : []);
  const locations = useMemo(() => { const m = new Map(); src.forEach(r => { const v = (r.branch || '').trim(); if (v && !m.has(v.toLowerCase())) m.set(v.toLowerCase(), v); }); return [...m.values()].sort((a, b) => a.localeCompare(b)); }, [src]);
  const online = r => r.presence && (r.presence.state === 'active' || r.presence.state === 'idle');
  const passLoc = r => !loc || (r.branch || '').trim().toLowerCase() === loc.toLowerCase();
  const passQ = r => !q || (r.name || '').toLowerCase().includes(q.toLowerCase()) || (r.emp_code || '').toLowerCase().includes(q.toLowerCase());
  const base = (day ? day.rows : []).filter(r => passLoc(r) && passQ(r));
  const halfL = r => r.half_day_leave || r.status === 'half_leave' || r.status === 'half_day';
  const sum = { present: base.filter(r => r.status === 'present').length, late: base.filter(r => r.late).length, absent: base.filter(r => r.status === 'absent').length,
    leave: base.filter(r => r.status === 'leave').length, half_leave: base.filter(halfL).length, online: base.filter(online).length };
  const pass = r => !statF || (statF === 'present' && r.status === 'present') || (statF === 'late' && r.late) || (statF === 'absent' && r.status === 'absent')
    || (statF === 'leave' && r.status === 'leave') || (statF === 'half_leave' && halfL(r)) || (statF === 'online' && online(r));
  const rows = base.filter(pass);
  const people = (mon ? mon.people : []).filter(p => passLoc(p) && passQ(p));
  const filterLabel = () => { const p = []; if (loc) p.push(loc); if (role) p.push(roleName(role)); if (statF) p.push(statF); if (q) p.push('“' + q + '”'); return p.length ? p.join(' · ') : 'All staff'; };
  const COLS = ['Name', 'Emp ID', 'Role', 'Location', 'Status', 'Presence', 'Check-in', 'Check-out', 'Worked', 'Idle', 'Calls', 'Visits', 'Collected'];
  const cells = (r) => [r.name || '', r.emp_code || '', roleName(r.role), r.branch || '', label(r), r.presence ? (r.presence.state === 'active' ? 'Active' : r.presence.state === 'idle' ? 'Idle' : 'Offline') : 'Offline',
    fmtTime(r.check_in_at) || '', fmtTime(r.check_out_at) || '', dur(r.worked_seconds), dur(r.idle_seconds), r.show_activity ? (r.calls || 0) : '—', r.show_activity ? (r.visits || 0) : '—', r.show_activity ? inr(r.collected) : '—'];
  const printDay = () => printTables(`Attendance — ${date}`, [[`Filter: ${filterLabel()} · ${rows.length} people`, COLS, rows.map(cells)]]);
  const csv = () => {
    const e = v => { const s = String(v ?? ''); return /[",\n]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s; };
    const blob = new Blob(['﻿' + [COLS.map(e).join(','), ...rows.map(r => cells(r).map(e).join(','))].join('\r\n')], { type: 'text/csv;charset=utf-8;' });
    const a = document.createElement('a'); a.href = URL.createObjectURL(blob); a.download = `Attendance_${date}.csv`; a.click();
  };
  const dl = () => download('/api/attendance/download?' + rangeQ(), tab === 'range' ? `Attendance_${rStart}_to_${rEnd}.xlsx` : `Attendance_${month}.xlsx`);
  const detail = (id, d) => ui.modal('AttendanceDetail', { id, date: d });
  const KPIS = [['present', 'Present', sum.present, UserCheck, 'good'], ['late', 'Late', sum.late, Clock3, 'warn'], ['absent', 'Absent', sum.absent, UserX, 'bad'],
    ['leave', 'On leave', sum.leave, Palmtree, 'info'], ['half_leave', 'Half day', sum.half_leave, CalendarClock, 'violet'], ['online', 'Online now', sum.online, Wifi, 'accent']];

  return (
    <>
      <ModuleHead icon={Clock3} title="Attendance" sub="Who’s in, who’s out — day, month or salary cycle">
        <button className="btn" onClick={() => ui.modal('FosVisitReportsModal', { defDate: tab === 'today' ? date : today, cycle, locations })}><FileSpreadsheet />FOS visit reports</button>
        {tab === 'today' && day && <button className="btn" onClick={printDay}><Printer />Print</button>}
        {tab === 'today' && day && <button className="btn" onClick={csv}><Download />CSV</button>}
        {tab !== 'today' && mon && <button className="btn primary" onClick={dl}><Download />Download sheet</button>}
      </ModuleHead>

      <div className="card toolbar-card rise">
        <div className="row wrap" style={{ gap: 10 }}>
          <div className="seg-tabs" style={{ margin: 0, padding: 0 }}>
            {[['today', 'Day', CalendarDays], ['month', 'Month', CalendarRange], ['range', 'Salary cycle / range', Wallet]].map(([v, l, I]) =>
              <button key={v} className={tab === v ? 'on' : ''} onClick={() => setTab(v)}><I /><span>{l}</span></button>)}
          </div>
          <div className="grow" />
          {tab === 'today' ? <input type="date" className="input" value={date} max={today} onChange={e => setDate(e.target.value)} />
            : tab === 'month' ? <input type="month" className="input" value={month} max={today.slice(0, 7)} onChange={e => setMonth(e.target.value)} />
            : <div className="row wrap" style={{ gap: 6 }}>
                <button className="btn sm ghost" onClick={() => { const [a, b] = cycle(0); setRStart(a); setREnd(b); }}>This salary cycle</button>
                <button className="btn sm ghost" onClick={() => { const [a, b] = cycle(1); setRStart(a); setREnd(b); }}>Previous cycle</button>
                <input type="date" className="input" value={rStart} onChange={e => setRStart(e.target.value)} /><span className="faint">→</span>
                <input type="date" className="input" value={rEnd} min={rStart} onChange={e => setREnd(e.target.value)} /></div>}
        </div>
        <div className="row wrap" style={{ gap: 8 }}>
          <SearchBox value={q} onChange={setQ} placeholder="Name or employee ID" width={240} />
          <Chips value={role} onChange={setRole} label="Role" options={[['', 'All'], ...(tab === 'today' ? roles : ['fos', 'telecaller', 'teamlead', 'manager', 'headoffice', 'hr', 'backend']).map(r => [r, roleName(r)])]} />
        </div>
        {locations.length > 1 && <Chips value={loc} onChange={v => setLoc(loc === v ? '' : v)} label="Location" options={[['', 'All'], ...locations.map(l => [l, l])]} />}
      </div>

      {tab === 'today' && (!day ? <Skeleton h={300} /> : <>
        <div className="att-kpis">
          {KPIS.map(([k, l, v, I, t], i) => <button key={k} className={cx('kpi-btn', statF === k && 'on')} onClick={() => setStatF(statF === k ? '' : k)}>
            <Kpi icon={I} label={l} i={i} value={num(v)} tone={t} tilt={false} sub={statF === k ? 'filtered' : ''} /></button>)}
        </div>
        {vici && vici.error && <div className="faint" style={{ color: 'var(--warn)', fontSize: 12, margin: '0 2px 8px' }}>ViciDial live status unavailable — {vici.error}</div>}
        <Card pad={false} className="rise" title={`${rows.length} ${rows.length === 1 ? 'person' : 'people'}`} sub={filterLabel()}>
          {!rows.length ? <Empty title="No one to show" /> :
            <div className="table-wrap" style={{ maxHeight: 'calc(100vh - 380px)' }}><table className="t">
              <thead><tr><th>Employee</th><th>Status</th><th>Presence</th>{showVici && <th>ViciDial</th>}<th>Check-in</th><th>Check-out</th><th>Worked</th><th>Idle</th><th className="r">Calls</th><th className="r">Visits</th><th className="r">Collected</th></tr></thead>
              <tbody>{rows.map(r => { const v = showVici ? (vici.agents || {})[String(r.user_id)] : null; const [vl, vt] = v && v.status ? (VICI[v.status] || [v.status, 'neutral']) : [null]; return (
                <tr key={r.user_id} className="click" onClick={() => detail(r.user_id, date)}>
                  <td><div className="row" style={{ gap: 10 }}><Avatar name={r.name} size={32} /><div><div className="cell-main">{r.name}</div><div className="cell-sub">{[r.emp_code, roleName(r.role), r.branch].filter(Boolean).join(' · ')}</div></div></div></td>
                  <td><Pill tone={tone(r)} dot>{label(r)}</Pill></td>
                  <td><Presence p={r.presence} /></td>
                  {showVici && <td>{vl ? <Pill tone={vt} title={v.agent || ''}>{vl}{v.campaign && v.status !== 'LOGGED_OUT' ? ' · ' + v.campaign : ''}{v.calls_today ? ' · ' + v.calls_today + ' calls' : ''}</Pill> : <span className="faint">—</span>}</td>}
                  <td onClick={e => e.stopPropagation()}>{fmtTime(r.check_in_at) || '—'}
                    {r.check_in_lat != null && <div><a className="cell-sub" target="_blank" rel="noreferrer" href={`https://maps.google.com/?q=${r.check_in_lat},${r.check_in_lng}`}><MapPin size={11} /> {r.check_in_lat.toFixed(4)}, {r.check_in_lng.toFixed(4)}</a></div>}
                    {r.role === 'fos' && r.live_lat != null && <div><a target="_blank" rel="noreferrer" href={`https://maps.google.com/?q=${r.live_lat},${r.live_lng}`} style={{ color: 'var(--good)', fontWeight: 650, fontSize: 11.5 }}><Satellite size={11} /> Live · {fmtTime(r.live_at)}</a></div>}</td>
                  <td>{fmtTime(r.check_out_at) || '—'}{r.auto_checkout && <span className="faint" style={{ fontSize: 11 }}> (auto)</span>}</td>
                  <td>{dur(r.worked_seconds)}</td><td className="faint">{dur(r.idle_seconds)}</td>
                  <td className="r">{r.show_activity ? num(r.calls) : '—'}{r.team_total && r.show_activity ? <span className="faint" style={{ fontSize: 10 }}> team</span> : ''}</td>
                  <td className="r">{r.show_activity ? num(r.visits) : '—'}</td>
                  <td className="r">{r.show_activity ? inr(r.collected) : '—'}</td>
                </tr>); })}</tbody></table></div>}
        </Card>
      </>)}

      {tab !== 'today' && (!mon ? <Skeleton h={300} /> : <Card pad={false} className="rise" title={tab === 'range' ? `${rStart} → ${rEnd}` : month} sub={`${people.length} people · ${filterLabel()}`}>
        {!people.length ? <Empty title="No data" /> : <div className="table-wrap" style={{ maxHeight: 'calc(100vh - 360px)' }}><table className="t att-grid">
          <thead><tr><th className="sticky-c">Employee</th>{mon.days.map(d => <th key={d} className="c">{tab === 'range' ? <>{d.slice(8)}<div className="faint" style={{ fontSize: 9 }}>{d.slice(5, 7)}</div></> : d.slice(8)}</th>)}
            <th className="c">P</th><th className="c">Late</th><th className="c" title="Checked in after 11:30">H</th><th className="c">Lv</th><th className="c">Abs</th><th className="c" title="Approved half-day leaves">H•</th><th className="c">Hrs</th></tr></thead>
          <tbody>{people.map(p => <tr key={p.user_id}>
            <td className="sticky-c click" onClick={() => detail(p.user_id, (tab === 'range' ? rStart : month + '-01'))}><div className="cell-main">{p.name}</div><div className="cell-sub">{[p.emp_code, p.branch].filter(Boolean).join(' · ')}</div></td>
            {mon.days.map(d => { const v = p.days[d] || ''; const t = (p.times || {})[d]; return <td key={d} className="c"><span className={'att-c a-' + (ATT[v] || 'none')}>{v}</span>
              {t && ['P', 'L', 'H', 'H•'].includes(v) && <div className="faint" style={{ fontSize: 9 }}>{t}</div>}</td>; })}
            <td className="c"><b>{p.present}</b></td><td className="c" style={{ color: 'var(--warn)' }}>{p.late}</td><td className="c" style={{ color: 'var(--warn)' }}>{p.late_half_days || 0}</td>
            <td className="c" style={{ color: 'var(--info)' }}>{p.leave}</td><td className="c" style={{ color: 'var(--bad)' }}>{p.absent}</td><td className="c">{p.half_days || 0}</td><td className="c">{p.worked_hours}</td>
          </tr>)}</tbody></table></div>}
        <div className="faint" style={{ fontSize: 11.5, padding: '10px 16px' }}>P Present · L Late (after 10:00) · H Half day (checked in after 11:30 → 0.5 present + 0.5 absent) · H• Approved half-day leave · LV Leave · A Absent · W Week-off. Time under P / L / H = check-in time.</div>
      </Card>)}
    </>
  );
}

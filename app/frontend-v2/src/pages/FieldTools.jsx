// Field Tracking tools that used to live only in the classic map: FOS roster, multi-officer /
// multi-date route + visit export, flagged visits and geocoding.
import React, { useEffect, useState } from 'react';
import { Download, Flag, MapPin, Users } from 'lucide-react';
import { api, download } from '../lib/api.js';
import { istToday, fmtTime, num } from '../lib/format.js';
import { Pill, Skeleton } from '../components/ui.jsx';
import { Modal, SearchBox, useClassicUI } from '../modules/kit.jsx';

export function RosterModal({ onClose }) {
  const [date, setDate] = useState('');
  const [q, setQ] = useState('');
  const [r, setR] = useState(null);
  useEffect(() => { setR(null); api('/api/tracking/roster' + (date ? '?date=' + date : '')).then(setR).catch(() => setR({ active: [], inactive: [], active_count: 0, inactive_count: 0, total: 0, error: true })); }, [date]);
  const m = (o) => { const s = q.trim().toLowerCase(); return !s || [o.name, o.emp_code, o.branch, o.location, o.phone].some(v => String(v || '').toLowerCase().includes(s)); };
  return (
    <Modal open onClose={onClose} width={780} title={`Field officers — ${r ? (r.is_today ? 'Today' : r.date) : '…'}`}
      sub={r && !r.error ? `${r.active_count} active · ${r.inactive_count} inactive · ${r.total} total` : ''}>
      <div className="row wrap" style={{ gap: 8, marginBottom: 12 }}>
        <input className="input" type="date" max={istToday()} value={date} onChange={e => setDate(e.target.value)} />
        {date && <button className="btn sm" onClick={() => setDate('')}>Today</button>}
        <SearchBox value={q} onChange={setQ} placeholder="Name, ID, branch, phone" width={260} />
      </div>
      {!r ? <Skeleton h={240} /> : <div className="grid g-2e" style={{ gap: 12 }}>
        <div className="card" style={{ padding: 12, maxHeight: 380, overflow: 'auto' }}>
          <b style={{ color: 'var(--good)' }}>● Active ({r.active_count})</b><div className="faint" style={{ fontSize: 11.5, marginBottom: 8 }}>Shared live location this day</div>
          {r.active.filter(m).map(o => <div key={o.id} className="roster-i"><b>{o.name}</b> <span className="faint">{o.emp_code || ''}</span>
            <div className="cell-sub">{o.branch || o.location || '—'} · {num(o.pings)} pts · {o.distance_km || 0} km</div>
            <div className="cell-sub">{fmtTime(o.first_seen)}–{fmtTime(o.last_seen)}</div></div>)}
          {!r.active.filter(m).length && <div className="faint" style={{ fontSize: 12 }}>{q ? 'No match.' : 'None.'}</div>}
        </div>
        <div className="card" style={{ padding: 12, maxHeight: 380, overflow: 'auto' }}>
          <b className="faint">● Inactive ({r.inactive_count})</b><div className="faint" style={{ fontSize: 11.5, marginBottom: 8 }}>No tracking this day</div>
          {r.inactive.filter(m).map(o => <div key={o.id} className="roster-i"><b>{o.name}</b> <span className="faint">{o.emp_code || ''}</span>
            <div className="cell-sub">{o.branch || o.location || '—'}{o.phone ? ' · ' + o.phone : ''}</div></div>)}
          {!r.inactive.filter(m).length && <div className="faint" style={{ fontSize: 12 }}>{q ? 'No match.' : 'None — everyone tracked'}</div>}
        </div>
      </div>}
    </Modal>
  );
}

export function ExportModal({ onClose, branch }) {
  const [list, setList] = useState(null); const [fos, setFos] = useState(new Set());
  const [dates, setDates] = useState(null); const [pick, setPick] = useState(new Set());
  const [q, setQ] = useState(''); const [busy, setBusy] = useState(false);
  useEffect(() => { api('/api/tracking/roster').then(r => setList([...(r.active || []), ...(r.inactive || [])].sort((a, b) => String(a.name || '').localeCompare(b.name || '')))).catch(() => setList([])); }, []);
  useEffect(() => { setDates(null); setPick(new Set()); api('/api/tracking/available-dates' + (fos.size ? '?officer_ids=' + [...fos].join(',') : '')).then(setDates).catch(() => setDates([])); }, [fos]);
  const tog = (set, setter, v) => { const n = new Set(set); n.has(v) ? n.delete(v) : n.add(v); setter(n); };
  const m = (o) => { const s = q.trim().toLowerCase(); return !s || [o.name, o.emp_code, o.branch].some(v => String(v || '').toLowerCase().includes(s)); };
  const run = () => {
    setBusy(true);
    const p = new URLSearchParams(); p.set('officer_ids', fos.size ? [...fos].join(',') : 'all'); p.set('dates', pick.size ? [...pick].join(',') : 'all'); if (branch) p.set('branch', branch);
    download('/api/tracking/export?' + p, `route_export_${istToday()}.xlsx`).finally(() => { setBusy(false); onClose(); });
  };
  return (
    <Modal open onClose={() => !busy && onClose()} width={820} title="Export routes & visits — Excel"
      sub="Pick officers and dates (leave a side empty for all). One workbook: a sheet per date, each officer with route summary and visit log."
      footer={<><span className="faint">{fos.size || 'All'} officer(s) × {pick.size || 'all'} date(s)</span><div className="grow" />
        <button className="btn primary" disabled={busy || (dates && !dates.length)} onClick={run}><Download />{busy ? 'Preparing…' : 'Download Excel'}</button></>}>
      <div className="grid g-2e" style={{ gap: 12 }}>
        <div className="card" style={{ padding: 12 }}>
          <div className="row" style={{ marginBottom: 8 }}><b className="grow">Officers {fos.size ? `(${fos.size})` : '(all)'}</b>
            <button className="btn sm ghost" onClick={() => setFos(new Set((list || []).map(o => o.id)))}>All</button><button className="btn sm ghost" onClick={() => setFos(new Set())}>None</button></div>
          <SearchBox value={q} onChange={setQ} placeholder="Name, ID, branch" width="100%" />
          <div style={{ maxHeight: 300, overflow: 'auto', marginTop: 8 }}>{list === null ? <Skeleton h={200} /> : list.filter(m).map(o =>
            <label key={o.id} className="ms-opt"><input type="checkbox" checked={fos.has(o.id)} onChange={() => tog(fos, setFos, o.id)} /><span><b>{o.name}</b> <span className="faint">{o.emp_code || ''} · {o.branch || '—'}</span></span></label>)}</div>
        </div>
        <div className="card" style={{ padding: 12 }}>
          <div className="row" style={{ marginBottom: 8 }}><b className="grow">Dates {pick.size ? `(${pick.size})` : '(all)'}</b>
            <button className="btn sm ghost" onClick={() => setPick(new Set(dates || []))}>All</button><button className="btn sm ghost" onClick={() => setPick(new Set())}>None</button></div>
          <div className="faint" style={{ fontSize: 11.5, marginBottom: 6 }}>Days with recorded routes {fos.size ? 'for the selected officers' : '(any officer)'}, last 3 months.</div>
          <div style={{ maxHeight: 330, overflow: 'auto' }}>{dates === null ? <Skeleton h={200} /> : !dates.length ? <div className="faint">No route dates.</div> : dates.map(d =>
            <label key={d} className="ms-opt"><input type="checkbox" checked={pick.has(d)} onChange={() => tog(pick, setPick, d)} /><span>{d}</span></label>)}</div>
        </div>
      </div>
    </Modal>
  );
}

/** Buttons row used by Field Tracking. */
export function FieldToolButtons({ branch }) {
  const ui = useClassicUI();
  const [roster, setRoster] = useState(false); const [exp, setExp] = useState(false);
  return <>
    <button className="btn sm" onClick={() => setRoster(true)}><Users />FOS roster</button>
    <button className="btn sm primary" onClick={() => setExp(true)}><Download />Export routes</button>
    <button className="btn sm" onClick={() => ui.modal('FlaggedVisitsModal', {})}><Flag />Flagged visits</button>
    <button className="btn sm" onClick={() => ui.tools(['GeocodeButton'], 'Geocode case addresses')}><MapPin />Geocode</button>
    {roster && <RosterModal onClose={() => setRoster(false)} />}
    {exp && <ExportModal branch={branch} onClose={() => setExp(false)} />}
  </>;
}

/** Day visit log → Excel (uses the same spreadsheet library the classic app loads). */
export function dayVisitsExcel(xlsx, name, day, visits) {
  if (!xlsx || !visits) return false;
  const cols = ['#', 'Time', 'Customer / case', 'Disposition', 'Paid', 'Amount', 'Distance from address (m)', 'Note'];
  const aoa = [cols].concat(visits.map((v, i) => [i + 1, fmtTime(v.at), v.case_label || '', v.disposition || '', v.paid ? 'Yes' : '', v.amount || 0, v.distance_m ?? '', v.note || '']));
  const wb = xlsx.utils.book_new(); xlsx.utils.book_append_sheet(wb, xlsx.utils.aoa_to_sheet(aoa), 'Visits');
  xlsx.writeFile(wb, `Visits_${name}_${day}.xlsx`.replace(/[^\w.-]/g, '_'));
  return true;
}
export { Pill };

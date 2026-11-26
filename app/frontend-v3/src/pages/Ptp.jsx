import React, { useMemo, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { AlarmClock, CalendarCheck2, CalendarClock, Handshake, Search, SlidersHorizontal } from 'lucide-react';
import { api, qs } from '../lib/api.js';
import { inr, fmtDate, num } from '../lib/format.js';
import { Card, Kpi, Seg, Pill, Empty, Skeleton, useLoad } from '../components/ui.jsx';
import CaseDrawer from './CaseDrawer.jsx';

const BUCKET = { overdue: ['bad', 'Overdue'], today: ['warn', 'Due today'], upcoming: ['info', 'Upcoming'] };

export default function Ptp() {
  const [sp, setSp] = useSearchParams();
  const [b, setB] = useState('');
  const [q, setQ] = useState('');
  const [from, setFrom] = useState('');
  const [to, setTo] = useState('');
  const { data, loading, error } = useLoad(() => api('/api/calls/ptp-tracker' + qs({ date_from: from, date_to: to })), [from, to]);
  const rows = (data && data.rows) || [];
  const counts = (data && data.counts) || {};
  const shown = useMemo(() => rows.filter(r => (!b || r.bucket === b) && (!q || `${r.case.customer_name} ${r.case.account_no} ${r.case.assigned_caller_name || ''} ${r.case.assigned_fos_name || ''}`.toLowerCase().includes(q.toLowerCase()))), [rows, b, q]);
  const promised = shown.reduce((s, r) => s + (r.ptp_amount || 0), 0);

  return (
    <>
      <div className="page-head rise">
        <div className="grow"><h1 className="page-title">PTP Tracker</h1><div className="page-sub">Promises to pay — chase broken promises first</div></div>
        <div className="row" style={{ gap: 6 }}>
          <input type="date" className="input" value={from} onChange={e => setFrom(e.target.value)} title="Promised from" />
          <span className="faint">→</span>
          <input type="date" className="input" value={to} onChange={e => setTo(e.target.value)} title="Promised to" />
        </div>
        <Link className="btn" to="/m/ptp" title="The complete PTP module"><SlidersHorizontal />Full module</Link>
      </div>

      <div className="grid g-kpi" style={{ marginBottom: 16 }}>
        <Kpi icon={AlarmClock} label="Overdue" i={1} value={num(counts.overdue)} sub="promise date passed" tone="bad" />
        <Kpi icon={CalendarCheck2} label="Due today" i={2} value={num(counts.today)} sub="call / visit today" tone="warn" />
        <Kpi icon={CalendarClock} label="Upcoming" i={3} value={num(counts.upcoming)} sub="scheduled" tone="info" />
        <Kpi icon={Handshake} label="Promised (shown)" i={4} value={promised} format={inr} sub={`${num(shown.length)} promises`} tone="good" />
      </div>

      <Card pad={false}>
        <div className="row wrap" style={{ padding: 14, gap: 10, borderBottom: '1px solid var(--line)' }}>
          <Seg value={b} onChange={setB} options={[['', 'All'], ['overdue', 'Overdue'], ['today', 'Today'], ['upcoming', 'Upcoming']]} />
          <div className="input-icon grow" style={{ maxWidth: 360 }}><Search /><input className="input" placeholder="Search customer, account, caller, agent…" value={q} onChange={e => setQ(e.target.value)} /></div>
        </div>
        {error && <div style={{ padding: 16, color: 'var(--bad)' }}>{error}</div>}
        <div className="table-wrap" style={{ maxHeight: 'calc(100vh - 380px)' }}>
          <table className="t">
            <thead><tr><th>Customer</th><th>When</th><th className="r">Promised</th><th>Caller / Agent</th><th>Latest notes</th></tr></thead>
            <tbody>
              {loading && !rows.length && [...Array(6)].map((_, i) => <tr key={i}><td colSpan={5}><Skeleton h={18} /></td></tr>)}
              {shown.map(r => {
                const [tone, lbl] = BUCKET[r.bucket] || ['neutral', r.bucket];
                const note = (r.notes || [])[0];
                return (
                  <tr key={r.case.id} className="click" onClick={() => setSp({ open: r.case.id })}>
                    <td><div className="cell-main">{r.case.customer_name}</div><div className="cell-sub mono">{r.case.account_no} · {r.case.bank} {r.case.product}</div></td>
                    <td><Pill tone={tone} dot>{lbl}</Pill><div className="cell-sub" style={{ marginTop: 3 }}>{r.promised_date ? fmtDate(r.promised_date) : 'no date'}</div></td>
                    <td className="r"><b>{r.ptp_amount ? inr(r.ptp_amount) : '—'}</b></td>
                    <td><div style={{ fontSize: 12.5 }}>{r.case.assigned_caller_name || '—'}</div><div className="cell-sub">{r.case.assigned_fos_name || ''}</div></td>
                    <td style={{ maxWidth: 320 }}><div className="muted" style={{ fontSize: 12.5, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{note ? (note.text || note.note || note.detail || '') : '—'}</div></td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          {!loading && !shown.length && <Empty icon={Handshake} title="No promises here" />}
        </div>
      </Card>
      <CaseDrawer id={Number(sp.get('open')) || null} onClose={() => setSp({})} />
    </>
  );
}

import React, { useMemo, useState } from 'react';
import { AlarmClock, CalendarCheck2, CalendarClock, Handshake, RefreshCw, X, PhoneCall, Footprints } from 'lucide-react';
import { api, qs } from '../lib/api.js';
import { inr, num, cx } from '../lib/format.js';
import { Card, Kpi, Pill, Empty, Skeleton, useLoad } from '../components/ui.jsx';
import { ModuleHead, SearchBox, useLive, useClassicUI } from '../modules/kit.jsx';

const BUCKETS = [['overdue', 'Overdue', 'bad'], ['today', 'Due today', 'warn'], ['upcoming', 'Upcoming', 'info']];

/** PTP Tracker — every promise to pay, grouped overdue / today / upcoming, with every filter. */
export default function Ptp() {
  const ui = useClassicUI();
  const [seg, setSeg] = useState('');
  const [q, setQ] = useState('');
  const [bank, setBank] = useState(''); const [product, setProduct] = useState('');
  const [from, setFrom] = useState(''); const [to, setTo] = useState('');
  const [caller, setCaller] = useState(''); const [fos, setFos] = useState('');
  const { data, loading, error, reload } = useLoad(() => api('/api/calls/ptp-tracker' + qs({ bank, product, date_from: from, date_to: to, caller_id: caller, fos_id: fos })), [bank, product, from, to, caller, fos]);
  const { data: meta } = useLoad(() => api('/api/calls/ptp-tracker').catch(() => ({ rows: [] })), []);
  useLive(reload);
  const all = useMemo(() => ((meta && meta.rows) || []).map(r => r.case), [meta]);
  const banks = [...new Set(all.map(c => c.bank).filter(Boolean))].sort();
  const products = [...new Set(all.filter(c => !bank || c.bank === bank).map(c => c.product).filter(Boolean))].sort();
  const counts = (data && data.counts) || {};
  const match = (c) => { const s = q.trim().toLowerCase(); if (!s) return true; const d = s.replace(/\D/g, '');
    const f = [c.customer_name, c.account_no, c.card_no, c.phone, c.alt_phone, c.pincode];
    return f.some(v => v && String(v).toLowerCase().includes(s)) || (d && f.some(v => v && String(v).replace(/\D/g, '').includes(d))); };
  const visible = ((data && data.rows) || []).filter(r => match(r.case));
  const promised = visible.reduce((s, r) => s + (Number(r.ptp_amount) || 0), 0);
  const anyF = bank || product || from || to || caller || fos || q;

  return (
    <>
      <ModuleHead icon={Handshake} title="PTP Tracker" sub="Promises to pay — chase broken promises first">
        <button className="btn" onClick={reload}><RefreshCw />Refresh</button>
      </ModuleHead>
      <div className="grid g-kpi" style={{ marginBottom: 16 }}>
        {BUCKETS.map(([k, l, tone], i) => <button key={k} className={cx('kpi-btn', seg === k && 'on')} onClick={() => setSeg(seg === k ? '' : k)}>
          <Kpi icon={k === 'overdue' ? AlarmClock : k === 'today' ? CalendarCheck2 : CalendarClock} label={l} i={i + 1} value={num(counts[k])} sub={seg === k ? 'filtered — click to show all' : 'click to filter'} tone={tone} tilt={false} />
        </button>)}
        <Kpi icon={Handshake} label="Promised (shown)" i={4} value={promised} format={inr} sub={`${num(visible.length)} promises`} tone="good" />
      </div>
      <div className="card toolbar-card rise">
        <div className="row wrap" style={{ gap: 8 }}>
          <SearchBox value={q} onChange={setQ} placeholder="Name, account, card, phone, pincode" width={280} />
          <span className="chips-l">Promise date</span>
          <input type="date" className="input" value={from} onChange={e => setFrom(e.target.value)} title="From" />
          <span className="faint">→</span>
          <input type="date" className="input" value={to} onChange={e => setTo(e.target.value)} title="To" />
        </div>
        <div className="row wrap" style={{ gap: 8 }}>
          <select className="select" value={bank} onChange={e => { setBank(e.target.value); setProduct(''); }}><option value="">All banks</option>{banks.map(b => <option key={b}>{b}</option>)}</select>
          <select className="select" value={product} onChange={e => setProduct(e.target.value)}><option value="">All products</option>{products.map(p => <option key={p}>{p}</option>)}</select>
          <select className="select" value={caller} onChange={e => setCaller(e.target.value)}><option value="">All callers</option>{((data && data.callers) || []).map(u => <option key={u.id} value={u.id}>{u.name}{u.emp_code ? ` (${u.emp_code})` : ''}</option>)}</select>
          <select className="select" value={fos} onChange={e => setFos(e.target.value)}><option value="">All FOS</option>{((data && data.fos) || []).map(u => <option key={u.id} value={u.id}>{u.name}{u.emp_code ? ` (${u.emp_code})` : ''}</option>)}</select>
          {anyF && <button className="btn sm ghost" onClick={() => { setBank(''); setProduct(''); setFrom(''); setTo(''); setCaller(''); setFos(''); setQ(''); }}><X />Clear</button>}
        </div>
      </div>
      {error && <div className="card" style={{ padding: 16, color: 'var(--bad)' }}>Couldn’t load the PTP tracker: {error}</div>}
      {loading && !data && <Skeleton h={300} />}
      {data && !visible.length && <Empty icon={Handshake} title={q ? `No promises match “${q}”` : 'No active promises to pay right now'} />}
      {data && visible.length > 0 && BUCKETS.filter(([k]) => !seg || k === seg).map(([key, label, tone], gi) => {
        const rows = visible.filter(r => r.bucket === key);
        return (
          <Card key={key} pad={false} className="rise" style={{ '--i': gi, marginBottom: 14 }} title={<span className="row" style={{ gap: 8 }}><Pill tone={tone} dot>{label}</Pill><span className="faint">{rows.length}</span></span>}>
            {!rows.length ? <div className="faint" style={{ padding: 16 }}>No {label.toLowerCase()} promises.</div> :
              <div className="table-wrap"><table className="t">
                <thead><tr><th>Customer</th><th>Portfolio</th><th>Bucket</th><th>Cycle</th><th>Card / A/C</th><th className="r">Outstanding</th><th className="r">Collected</th><th className="r">Promised</th><th>Promise date</th><th className="r">Pending</th><th>Caller</th><th>FOS</th><th>Recent notes</th></tr></thead>
                <tbody>{rows.map(r => { const c = r.case; return (
                  <tr key={c.id} className="click" onClick={() => ui.openCase(c.id)}>
                    <td><div className="cell-main">{c.customer_name}</div><div className="cell-sub">{c.phone || '—'}</div></td>
                    <td className="muted">{c.bank}<div className="cell-sub">{c.product || ''}</div></td>
                    <td>{c.bucket || '—'}</td><td className="mono">{c.cycle || '—'}</td><td className="mono">{c.card_no || c.account_no || '—'}</td>
                    <td className="r">{inr(c.enr || c.total_outstanding || c.funding_amount || 0)}</td>
                    <td className="r" style={{ color: 'var(--good)' }}>{inr(c.received_amount)}</td>
                    <td className="r"><b>{r.ptp_amount != null ? inr(r.ptp_amount) : '—'}</b></td>
                    <td style={{ whiteSpace: 'nowrap', color: key === 'overdue' ? 'var(--bad)' : undefined, fontWeight: key === 'overdue' ? 650 : undefined }}>{r.promised_date || '—'}</td>
                    <td className="r" style={{ color: 'var(--warn)' }}>{inr(c.pending_amount)}</td>
                    <td style={{ fontSize: 12.5 }}>{c.assigned_caller_name ? `${c.assigned_caller_name}${c.assigned_caller_code ? ` (${c.assigned_caller_code})` : ''}` : (c.caller_name || '—')}</td>
                    <td style={{ fontSize: 12.5 }}>{c.assigned_fos_name ? `${c.assigned_fos_name}${c.assigned_fos_code ? ` (${c.assigned_fos_code})` : ''}` : (c.fos_name || '—')}</td>
                    <td style={{ minWidth: 240, maxWidth: 340 }}>{(r.notes && r.notes.length) ? <div className="col" style={{ gap: 3 }}>{r.notes.slice(0, 5).map((n, i) =>
                      <div key={i} className="note-line">{n.source === 'visit' ? <Footprints size={12} /> : <PhoneCall size={12} />}<span>{n.disposition ? <b>{n.disposition}</b> : null}{n.disposition && n.text ? ': ' : ''}{n.text}<span className="faint"> — {n.by}{n.when ? `, ${n.when}` : ''}</span></span></div>)}</div> : <span className="faint">—</span>}</td>
                  </tr>); })}</tbody></table></div>}
          </Card>);
      })}
    </>
  );
}

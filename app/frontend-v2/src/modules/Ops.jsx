// Operations modules: Bank Feedback, Litigation, Communication, Monthly Archive, Team-lead
// Portfolios, Security and Help & Support.
import React, { useEffect, useMemo, useState } from 'react';
import {
  Archive as ArchiveIcon, ArrowLeft, Briefcase, Check, Columns3, Download, Fingerprint, Gavel, KeyRound, Landmark, LifeBuoy, MessageSquare, Package,
  Pencil, Plus, RefreshCw, Scale, Send, ShieldCheck, Trash2, Upload, Users, Users2, X, Headset, Phone, CalendarClock, AlarmClock, FileText,
} from 'lucide-react';
import { api, download } from '../lib/api.js';
import { useAuth } from '../lib/auth.jsx';
import { cx, fmtDate, fmtTime, inr, inrShort, istToday, num, roleName } from '../lib/format.js';
import { Card, Kpi, Pill, Empty, Skeleton, useLoad, useToast } from '../components/ui.jsx';
import { ModuleHead, Chips, Modal, Field, SearchBox, Avatar, useLive, useClassicUI } from './kit.jsx';
import { useClassic } from '../lib/classic.jsx';

const dt = (t) => (t ? `${fmtDate(t)} ${fmtTime(t)}` : '—');
const MB4 = [['current', 'This month'], ['next', 'Next month'], ['last', 'Last month'], ['', 'All']];

/* ─────────── Bank Feedback ─────────── */
export function Feedback() {
  const toast = useToast();
  const [sel, setSel] = useState(null); const [day, setDay] = useState(istToday()); const [mb, setMb] = useState('current');
  const [filters, setFilters] = useState({}); const [search, setSearch] = useState(''); const [picked, setPicked] = useState({});
  const [colMenu, setColMenu] = useState(false); const [dlCols, setDlCols] = useState(null); const [busy, setBusy] = useState(false);
  const cfgL = useLoad(() => api('/api/feedback/config'), []);
  const { data: prodRows } = useLoad(() => api('/api/cases/product-summary').catch(() => []), []);
  const prods = useMemo(() => { const seen = {}, l = []; (prodRows || []).forEach(r => { const k = r.bank + '||' + r.product; if (!seen[k] && r.product !== '—') { seen[k] = 1; l.push({ bank: r.bank, product: r.product }); } }); return l; }, [prodRows]);
  useEffect(() => { if (!sel && prods.length) setSel(prods[0]); }, [prods]); // eslint-disable-line
  useEffect(() => { if (cfgL.data && !dlCols) setDlCols(new Set(cfgL.data.columns.map(c => c.key))); }, [cfgL.data]); // eslint-disable-line
  const qbase = sel ? `bank=${encodeURIComponent(sel.bank)}&product=${encodeURIComponent(sel.product)}&day=${day}` + (mb ? `&month_bucket=${mb}` : '') : '';
  const { data, loading, error, reload } = useLoad(() => (sel ? api('/api/feedback?' + qbase) : Promise.resolve(null)), [qbase]);
  useLive(reload);
  const [rows, setRows] = useState([]);
  useEffect(() => { setRows((data && data.rows) || []); setPicked({}); }, [data]);
  const cfg = cfgL.data; const cols = cfg ? cfg.columns : [];
  const setCell = (row, col, val) => { setRows(rs => rs.map(r => (r.id === row.id ? { ...r, [col.key]: val } : r)));
    api('/api/feedback/' + row.id, { method: 'PATCH', body: { field: col.key, value: val } }).catch(() => { toast('Save failed — reloading', 'err'); reload(); }); };
  const refresh = () => { setBusy(true); api('/api/feedback/refresh?' + qbase, { method: 'POST' }).then(() => { reload(); toast('Pulled latest from call & visit logs'); }).catch(() => {}).finally(() => setBusy(false)); };
  const gq = search.trim().toLowerCase(); const gd = gq.replace(/\D/g, '');
  const shown = rows.filter(r => { const vals = [r.customer, r.phone, ...cols.map(c => r[c.key])];
    const ms = !gq || vals.some(v => v != null && String(v).toLowerCase().includes(gq)) || (gd && vals.some(v => v != null && String(v).replace(/\D/g, '').includes(gd)));
    return ms && Object.keys(filters).every(k => { const f = (filters[k] || '').toLowerCase(); return !f || String(r[k] ?? '').toLowerCase().includes(f); }); });
  const pickedIds = Object.keys(picked).filter(id => picked[id]);
  const allPicked = shown.length > 0 && shown.every(r => picked[r.id]);
  const doDl = () => { const keys = cols.filter(c => dlCols.has(c.key)).map(c => c.key).join(','); let url = '/api/feedback/download?' + qbase + '&columns=' + encodeURIComponent(keys); if (pickedIds.length) url += '&ids=' + pickedIds.join(','); download(url, `feedback_${sel.bank}_${sel.product}_${day}.xlsx`); };
  const cell = (row, col) => {
    if (col.readonly) return <span>{row[col.key] || '—'}</span>;
    const v = row[col.key] ?? '';
    if (col.type === 'code') return <select className="cell-in" value={v} onChange={e => setCell(row, col, e.target.value)}><option value="" />{(cfg.codes[col.code] || []).map(o => <option key={o}>{o}</option>)}</select>;
    if (col.type === 'date') return <input type="date" className="cell-in" value={/^\d{4}-\d{2}-\d{2}$/.test(v) ? v : ''} onChange={e => setCell(row, col, e.target.value)} />;
    return <input className="cell-in" style={{ minWidth: col.key.includes('remark') ? 220 : 120 }} defaultValue={v} onBlur={e => { if (e.target.value !== String(v)) setCell(row, col, e.target.value); }} onKeyDown={e => { if (e.key === 'Enter') e.target.blur(); }} />;
  };
  if (cfgL.error) return <><ModuleHead icon={Landmark} title="Bank Feedback" /><div className="card" style={{ padding: 16, color: 'var(--warn)' }}>Couldn’t load the feedback format: {cfgL.error} <button className="btn sm" onClick={cfgL.reload}>Retry</button></div></>;
  return (
    <>
      <ModuleHead icon={Landmark} title="Bank Feedback" sub={sel ? `Daily feedback for ${sel.bank} · ${sel.product} — auto-filled from caller & FOS logs, stays editable` : ''}>
        <button className="btn" disabled={busy || !sel} onClick={refresh}><RefreshCw />{busy ? '…' : 'Pull from logs'}</button>
        <button className="btn primary" disabled={!sel || !dlCols} onClick={doDl}><Download />Download {pickedIds.length ? 'selected' : 'full'}</button>
      </ModuleHead>
      <div className="card toolbar-card rise"><div className="row wrap" style={{ gap: 8 }}>
        <select className="select" value={sel ? sel.bank + '||' + sel.product : ''} onChange={e => { const [b, p] = e.target.value.split('||'); setSel({ bank: b, product: p }); }}>
          {prods.map((p, i) => <option key={i} value={p.bank + '||' + p.product}>{p.bank} · {p.product}</option>)}</select>
        <input type="date" className="input" value={day} onChange={e => setDay(e.target.value)} />
        <Chips value={mb} onChange={setMb} options={MB4} label="Month" />
        <SearchBox value={search} onChange={setSearch} placeholder="Name, phone or any column" width={260} />
        <div className="grow" /><span className="faint" style={{ fontSize: 12 }}>{shown.length} of {rows.length} rows{pickedIds.length ? ` · ${pickedIds.length} selected` : ''}</span>
        <span className="pop-wrap"><button className={cx('btn sm', colMenu && 'primary')} onClick={() => setColMenu(v => !v)}><Columns3 />Columns</button>
          {colMenu && dlCols && <><div className="pop-scrim" onClick={() => setColMenu(false)} /><div className="pop-menu col-menu" style={{ right: 0, left: 'auto' }}>
            <div className="chips-l">Columns to download</div><div className="col-list">{cols.map(c => <label key={c.key} className="ms-opt"><input type="checkbox" checked={dlCols.has(c.key)} onChange={() => setDlCols(s => { const n = new Set(s); n.has(c.key) ? n.delete(c.key) : n.add(c.key); return n; })} />{c.label}</label>)}</div></div></>}</span>
      </div></div>
      {error && <div className="card" style={{ padding: 16, color: 'var(--bad)' }}>{error}</div>}
      <div className="card ls-scroll rise">
        {(!cfg || (loading && !rows.length)) ? <div style={{ padding: 16 }}><Skeleton h={240} /></div> : !shown.length ? <Empty title={gq || Object.values(filters).some(Boolean) ? 'No rows match your search / filters' : 'No cases for this product / day'} /> :
          <table className="ls-t"><thead>
            <tr><th className="ls-act"><input type="checkbox" checked={allPicked} onChange={() => { if (allPicked) setPicked({}); else { const m = {}; shown.forEach(r => { m[r.id] = true; }); setPicked(m); } }} /></th><th>Customer</th>{cols.map(c => <th key={c.key}>{c.label}</th>)}</tr>
            <tr className="ls-fil"><th className="ls-act" /><th />{cols.map(c => <th key={c.key}><input value={filters[c.key] || ''} placeholder="filter" onChange={e => setFilters(f => ({ ...f, [c.key]: e.target.value }))} /></th>)}</tr>
          </thead><tbody>{shown.map(r => <tr key={r.id}>
            <td className="ls-act"><input type="checkbox" checked={!!picked[r.id]} onChange={() => setPicked(p => ({ ...p, [r.id]: !p[r.id] }))} /></td>
            <td><div className="cell-main">{r.customer || '—'}</div>{r.phone && <div className="cell-sub">{r.phone}</div>}</td>
            {cols.map(c => <td key={c.key}>{cell(r, c)}</td>)}</tr>)}</tbody></table>}
      </div>
    </>
  );
}

/* ─────────── Litigation ─────────── */
const MATTER_TYPES = ['Sec 138', 'SARFAESI', 'Arbitration', 'IBC', 'Civil', 'Criminal', 'Consumer'];
const STATUS_TONE = { won: 'good', settled: 'good', lost: 'bad', open: 'info', closed: 'neutral' };
export function Legal() {
  const ui = useClassicUI();
  const [mt, setMt] = useState(''); const [st, setSt] = useState(''); const [q, setQ] = useState('');
  const { data, loading, reload } = useLoad(() => { const p = new URLSearchParams(); if (mt) p.set('matter_type', mt); if (st) p.set('status', st); return api('/api/legal' + (p.toString() ? '?' + p : '')).catch(() => []); }, [mt, st]);
  const { data: ins, reload: ri } = useLoad(() => api('/api/legal/insights').catch(() => null), []);
  const today = istToday();
  const items = (Array.isArray(data) ? data : []).filter(l => !q || [l.borrower_name, l.bank, l.court, l.case_number].some(v => String(v || '').toLowerCase().includes(q.toLowerCase())));
  const edit = (l) => ui.modal('LegalModal', { editing: l ? { ...l, filed_date: l.filed_date || '', next_hearing_date: l.next_hearing_date || '', amount: l.amount || '' } : null }).then(ok => { if (ok) { reload(); ri(); } });
  return (
    <>
      <ModuleHead icon={Scale} title="Litigation" sub="Legal matters, stages and hearing dates"><button className="btn primary" onClick={() => edit(null)}><Plus />New matter</button></ModuleHead>
      {ins && <div className="grid g-kpi" style={{ marginBottom: 16 }}>
        <Kpi icon={Gavel} label="Open matters" i={1} value={num(ins.open)} />
        <Kpi icon={AlarmClock} label="Hearing overdue" i={2} value={num(ins.hearing_overdue)} tone="bad" />
        <Kpi icon={CalendarClock} label="Hearing today" i={3} value={num(ins.hearing_today)} tone="warn" />
        <Kpi icon={CalendarClock} label="This week" i={4} value={num(ins.hearing_week)} tone="info" />
      </div>}
      <div className="card toolbar-card rise"><div className="row wrap" style={{ gap: 8 }}>
        <SearchBox value={q} onChange={setQ} placeholder="Borrower, bank, court, case no." width={280} />
        <select className="select" value={mt} onChange={e => setMt(e.target.value)}><option value="">All matters</option>{MATTER_TYPES.map(m => <option key={m}>{m}</option>)}</select>
        <Chips value={st} onChange={setSt} label="Status" options={[['', 'All'], ['open', 'Open'], ['settled', 'Settled'], ['won', 'Won'], ['lost', 'Lost'], ['closed', 'Closed']]} />
      </div></div>
      <Card pad={false} className="rise">
        {loading && !items.length ? <div style={{ padding: 16 }}><Skeleton h={200} /></div> : !items.length ? <Empty icon={Scale} title="No matters yet">Add one to track hearings and stages.</Empty> :
          <div className="table-wrap"><table className="t">
            <thead><tr><th>Borrower</th><th>Matter</th><th>Court</th><th>Case no.</th><th>Stage</th><th>Next hearing</th><th>Status</th><th></th></tr></thead>
            <tbody>{items.map(l => { const d = l.next_hearing_date; return <tr key={l.id} className="click" onClick={() => edit(l)}>
              <td><div className="cell-main">{l.borrower_name || '—'}</div><div className="cell-sub">{l.bank}{l.amount > 0 ? ' · ' + inr(l.amount) : ''}</div></td>
              <td><Pill tone="accent">{l.matter_type}</Pill></td><td className="muted">{l.court || '—'}</td><td className="mono">{l.case_number || '—'}</td><td>{l.stage || '—'}</td>
              <td style={{ color: d && d < today ? 'var(--bad)' : d === today ? 'var(--warn)' : undefined, fontWeight: d && d <= today ? 650 : undefined }}>{d || '—'}</td>
              <td><Pill tone={STATUS_TONE[l.status] || 'neutral'} dot>{l.status}</Pill></td>
              <td><button className="btn sm ghost"><Pencil /></button></td></tr>; })}</tbody></table></div>}
      </Card>
    </>
  );
}

/* ─────────── Communication (templates) ─────────── */
export function Templates() {
  const ui = useClassicUI(); const toast = useToast();
  const { data, loading, reload } = useLoad(() => api('/api/templates').catch(() => []), []);
  const items = Array.isArray(data) ? data : [];
  const edit = (t) => ui.modal('TemplateModal', { editing: t || null }).then(ok => ok && reload());
  const del = async (t) => { if (!window.confirm(`Delete template “${t.name}”?`)) return; try { await api('/api/templates/' + t.id, { method: 'DELETE' }); toast('Deleted'); reload(); } catch (e) { toast(e.message, 'err'); } };
  return (
    <>
      <ModuleHead icon={MessageSquare} title="Communication" sub="Reusable WhatsApp / SMS / email messages with merge fields — used from any case and in bulk campaigns">
        <button className="btn primary" onClick={() => edit(null)}><Plus />New template</button>
      </ModuleHead>
      <div className="card note-card rise" style={{ marginBottom: 16 }}><FileText /><div>Merge fields: <span className="mono">{'{name} {bank} {pending} {account} {ptp_date} {bucket} {address} {pincode} {address1} {address2} {address3}'}</span></div></div>
      {loading && !items.length ? <Skeleton h={200} /> : !items.length ? <Empty icon={MessageSquare} title="No templates yet">Create one to send quick reminders.</Empty> :
        <div className="tpl-grid">{items.map((t, i) => <div key={t.id} className="card tpl rise" style={{ '--i': Math.min(i, 10) }}>
          <div className="row"><b className="grow">{t.name}</b><Pill tone={t.channel === 'whatsapp' ? 'good' : t.channel === 'sms' ? 'info' : 'accent'}>{t.channel}</Pill></div>
          <div className="tpl-body">{t.body}</div>
          <div className="row" style={{ gap: 6 }}><button className="btn sm" onClick={() => edit(t)}><Pencil />Edit</button><button className="btn sm ghost danger" onClick={() => del(t)}><Trash2 />Delete</button></div>
        </div>)}</div>}
    </>
  );
}

/* ─────────── Monthly Archive ─────────── */
const MN = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
const pretty = (p) => { if (!p) return ''; const [y, m] = p.split('-'); return MN[Number(m) - 1] + ' ' + y; };
export function Archive() {
  const toast = useToast();
  const { data: periods } = useLoad(() => api('/api/archive/periods').catch(() => []), []);
  const [period, setPeriod] = useState(''); const [f, setF] = useState({ closing_type: '', product: '', cyc: '' }); const [zip, setZip] = useState(false);
  useEffect(() => { if (!period && periods && periods.length) setPeriod(periods[0].period); }, [periods]); // eslint-disable-line
  const { data: cyc } = useLoad(() => (period ? api('/api/archive/cycle-report?period=' + period).catch(() => null) : Promise.resolve(null)), [period]);
  const { data, loading } = useLoad(() => { if (!period) return Promise.resolve(null); const q = new URLSearchParams({ period }); Object.entries(f).forEach(([k, v]) => v && q.set(k, v)); return api('/api/archive/summary?' + q).catch(() => null); }, [period, f.closing_type, f.product, f.cyc]);
  const t = data && data.totals; const set = (k, v) => setF(s => ({ ...s, [k]: v }));
  const dlZip = async () => { setZip(true); toast('Preparing the ' + pretty(period) + ' archive — large months can take a minute…'); try { await download('/api/archive/export.zip?period=' + period, 'RecoverIQ_Archive_' + period + '.zip'); } finally { setZip(false); } };
  return (
    <>
      <ModuleHead icon={ArchiveIcon} title="Monthly Archive" sub="Everything that ran in a month — product-wise numbers, how it closed and per-staff performance">
        <button className="btn primary" disabled={!period || zip} onClick={dlZip}><Package />{zip ? 'Preparing ZIP…' : 'Download month (ZIP)'}</button>
      </ModuleHead>
      {!periods ? <Skeleton h={240} /> : !periods.length ? <Empty icon={ArchiveIcon} title="No months uploaded yet" /> : <>
        <div className="card toolbar-card rise"><div className="row wrap" style={{ gap: 8 }}>
          <select className="select" value={period} onChange={e => setPeriod(e.target.value)}>{periods.map(p => <option key={p.period} value={p.period}>{pretty(p.period)} — {p.total} cases ({p.closed} closed)</option>)}</select>
          <select className="select" value={f.closing_type} onChange={e => set('closing_type', e.target.value)}><option value="">All closing types</option><option value="cyc">Cycle-wise</option><option value="month_end">Month-end</option><option value="due_date">Due-date</option></select>
          {data && <select className="select" value={f.product} onChange={e => set('product', e.target.value)}><option value="">All products</option>{[...new Set(data.products.map(p => p.product))].map(p => <option key={p}>{p}</option>)}</select>}
          <input className="input" type="number" min="1" max="31" placeholder="Cycle day" value={f.cyc} onChange={e => set('cyc', e.target.value)} style={{ width: 110 }} />
          {(f.closing_type || f.product || f.cyc) && <button className="btn sm ghost" onClick={() => setF({ closing_type: '', product: '', cyc: '' })}><X />Clear</button>}
        </div></div>
        {loading && !data ? <Skeleton h={300} /> : data && <>
          <div className="grid g-kpi" style={{ marginBottom: 16 }}>
            <Kpi icon={Briefcase} label="Cases" i={1} value={num(t.cases)} sub={`${num(t.closed)} closed · ${num(t.open)} open`} />
            <Kpi icon={Check} label="Paid" i={2} value={num(t.paid)} tone="good" />
            <Kpi icon={Landmark} label="Recovered" i={3} value={t.received || 0} format={inrShort} tone="good" />
            <Kpi icon={AlarmClock} label="Pending" i={4} value={t.pending || 0} format={inrShort} tone="warn" />
          </div>
          <Card title="Product-wise" pad={false} className="rise" style={{ marginBottom: 16 }}><div className="table-wrap"><table className="t">
            <thead><tr><th>Bank</th><th>Product</th><th>Closing</th><th>Closes on</th><th className="r">Cases</th><th className="r">Paid</th><th className="r">Recovered</th><th className="r">Pending</th></tr></thead>
            <tbody>{data.products.map((p, i) => <tr key={i}><td>{p.bank}</td><td className="cell-main">{p.product}</td><td><Pill tone="accent">{p.closing_type || '—'}</Pill></td><td className="faint">{(p.close_days || []).join(', ') || '—'}</td>
              <td className="r">{num(p.cases)}</td><td className="r">{num(p.paid)}</td><td className="r" style={{ color: 'var(--good)' }}>{inr(p.received)}</td><td className="r" style={{ color: 'var(--warn)' }}>{inr(p.pending)}</td></tr>)}</tbody></table></div></Card>
          <div className="grid g-2e" style={{ gap: 16, marginBottom: 16 }}>
            <Card title="Closing breakdown" pad={false} className="rise"><div className="table-wrap"><table className="t"><thead><tr><th>Closes on</th><th className="r">Cases</th><th className="r">Recovered</th></tr></thead>
              <tbody>{data.by_close.map((b, i) => <tr key={i}><td className="faint">{b.closes}</td><td className="r">{num(b.cases)}</td><td className="r" style={{ color: 'var(--good)' }}>{inr(b.received)}</td></tr>)}</tbody></table></div></Card>
            <Card title="Performance" pad={false} className="rise"><div className="table-wrap" style={{ maxHeight: 420 }}><table className="t"><thead><tr><th>Staff</th><th>Role</th><th className="r">Cases</th><th className="r">Paid</th><th className="r">Recovered</th></tr></thead>
              <tbody>{[...data.performance.callers.map(s => ({ ...s, r: 'Caller' })), ...data.performance.fos.map(s => ({ ...s, r: 'FOS' }))].map(s => <tr key={s.r + s.id}><td className="cell-main">{s.name}</td><td><Pill tone={s.r === 'FOS' ? 'info' : 'accent'}>{s.r}</Pill></td>
                <td className="r">{num(s.cases)}</td><td className="r">{num(s.paid)}</td><td className="r" style={{ color: 'var(--good)' }}>{inr(s.received)}</td></tr>)}</tbody></table></div></Card>
          </div>
          {cyc && (cyc.cycle_days.length > 0 || cyc.by_type.length > 0) && <div className="grid g-2e" style={{ gap: 16 }}>
            <Card title="Cases closing on each cycle date" pad={false} className="rise"><div className="table-wrap"><table className="t"><thead><tr><th>Cycle</th><th>Closes on</th><th className="r">Cases</th><th className="r">Closed</th><th className="r">Open</th><th className="r">Recovered</th><th>Products</th></tr></thead>
              <tbody>{cyc.cycle_days.map(d => <tr key={d.day}><td><b>CYC {d.day}</b></td><td className="faint">{d.close_date}</td><td className="r">{d.cases}</td><td className="r">{d.closed}</td><td className="r">{d.open}</td><td className="r" style={{ color: 'var(--good)' }}>{inr(d.received)}</td><td className="faint" style={{ fontSize: 11.5 }}>{(d.products || []).join(', ')}</td></tr>)}</tbody></table></div></Card>
            <Card title="By closing type" pad={false} className="rise"><div className="table-wrap"><table className="t"><thead><tr><th>Closing</th><th className="r">Cases</th><th className="r">Closed</th><th className="r">Recovered</th></tr></thead>
              <tbody>{cyc.by_type.map(b => <tr key={b.closing_type}><td><Pill tone="accent">{b.closing_type}</Pill></td><td className="r">{b.cases}</td><td className="r">{b.closed}</td><td className="r" style={{ color: 'var(--good)' }}>{inr(b.received)}</td></tr>)}</tbody></table></div></Card>
          </div>}
        </>}
      </>}
    </>
  );
}

/* ─────────── Team-lead Portfolios ─────────── */
const monthName = (per) => { if (!per) return 'No month'; const [y, m] = per.split('-').map(Number); return new Date(y, m - 1, 1).toLocaleString('en-IN', { month: 'long', year: 'numeric' }); };
export function TLPortfolios() {
  const ui = useClassicUI();
  const [pfMonth, setPfMonth] = useState(''); const [sel, setSel] = useState(null); const [lead, setLead] = useState(null);
  const [mb, setMb] = useState('current'); const [tab, setTab] = useState('team');
  const pfs = useLoad(() => api('/api/team/portfolios' + (pfMonth ? '?month_bucket=' + pfMonth : '')), [pfMonth]);
  const qOf = (p) => 'bank=' + encodeURIComponent(p.bank) + '&product=' + encodeURIComponent(p.product) + '&branch=' + encodeURIComponent(p.branch || '');
  const leads = useLoad(() => (sel ? api('/api/team/portfolio/leads?' + qOf(sel) + (sel.period ? '&month_bucket=' + sel.period : '')) : Promise.resolve(null)), [sel]);
  const ov = useLoad(() => (sel && lead ? api('/api/team/portfolio/lead/' + lead.id + '/overview?' + qOf(sel) + '&month_bucket=' + mb) : Promise.resolve(null)), [sel, lead, mb]);
  const cs = useLoad(() => (sel && lead ? api('/api/team/portfolio/lead/' + lead.id + '/cases?' + qOf(sel) + '&month_bucket=' + mb).then(r => r.cases || []).catch(() => []) : Promise.resolve(null)), [sel, lead, mb]);
  const label = (p) => p.bank + ' · ' + p.product + (p.branch ? ' · ' + p.branch : '');
  const openLead = (l) => { setMb((sel && sel.period) || 'current'); setLead(l); setTab('team'); };

  if (sel && lead) { const t = ov.data; return (
    <>
      <ModuleHead icon={Users2} title={lead.name + (lead.is_me ? ' (you)' : '')} sub={label(sel) + (lead.is_me ? '' : ' · read-only')}>
        <button className="btn ghost" onClick={() => setLead(null)}><ArrowLeft />Team leads</button>
      </ModuleHead>
      <div className="card toolbar-card rise"><Chips value={mb} onChange={setMb} options={[...(/^\d{4}-\d{2}$/.test(mb) ? [[mb, monthName(mb)]] : []), ['current', 'This month'], ['next', 'Next month'], ['last', 'Last month'], ['all', 'All']]} /></div>
      {!t ? <Skeleton h={300} /> : <>
        <div className="grid g-kpi" style={{ marginBottom: 16 }}>
          <Kpi icon={Users} label="Members" i={1} value={num(t.kpis.members)} sub={`${num(t.kpis.fos)} FOS · ${num(t.kpis.callers)} callers`} />
          <Kpi icon={Briefcase} label="Cases" i={2} value={num(t.kpis.cases)} sub={`${num(t.kpis.resolved)} resolved`} tone="info" />
          <Kpi icon={Landmark} label="Recovered" i={3} value={t.kpis.recovered || 0} format={inrShort} sub={t.kpis.recovery_pct + '%'} tone="good" />
          <Kpi icon={AlarmClock} label="Pending" i={4} value={t.kpis.pending || 0} format={inrShort} tone="warn" />
        </div>
        <div className="seg-tabs rise"><button className={tab === 'team' ? 'on' : ''} onClick={() => setTab('team')}><Users /><span>Members</span></button><button className={tab === 'cases' ? 'on' : ''} onClick={() => setTab('cases')}><Briefcase /><span>Cases & status</span></button></div>
        <Card pad={false} className="rise">{tab === 'team' ? <div className="table-wrap"><table className="t">
          <thead><tr><th>Member</th><th>Role</th><th className="r">Assigned</th><th className="r">Resolved</th><th className="r">Recovered</th><th className="r">Pending</th><th className="r">Recovery</th></tr></thead>
          <tbody>{(t.members || []).map(m => <tr key={m.id} className="click" onClick={() => ui.perf(m.id, m.role === 'fos' ? 'fos' : 'caller', m.name, lead.is_me ? undefined : lead.id)}>
            <td><div className="row" style={{ gap: 8 }}><Avatar name={m.name} size={28} /><div><div className="cell-main">{m.name}</div><div className="cell-sub mono">{m.emp_code}</div></div></div></td>
            <td><Pill tone={m.role === 'fos' ? 'info' : 'accent'}>{m.role === 'fos' ? 'FOS' : 'Caller'}</Pill></td><td className="r">{num(m.assigned)}</td><td className="r">{num(m.resolved)}</td>
            <td className="r" style={{ color: 'var(--good)' }}>{inr(m.recovered)}</td><td className="r">{inr(m.pending)}</td><td className="r"><b>{m.recovery_pct}%</b></td></tr>)}
            {!(t.members || []).length && <tr><td colSpan={7}><Empty title="No team members on this portfolio for the selected month" /></td></tr>}</tbody></table></div>
          : <div className="table-wrap" style={{ maxHeight: 520 }}><table className="t">
            <thead><tr><th>Account</th><th>Customer</th><th>FOS</th><th>Caller</th><th>Status</th><th className="r">Recovered</th><th className="r">Pending</th></tr></thead>
            <tbody>{(cs.data || []).map(c => <tr key={c.id} className="click" onClick={() => (lead.is_me ? ui.openCase(c.id) : ui.modal('CaseDrawer', { c: { id: c.id, customer_name: c.customer, account_no: c.account_no, read_only: true, read_only_lead: lead.name }, readOnly: true }))}>
              <td className="mono">{c.account_no || '—'}</td><td className="cell-main">{c.customer || '—'}</td><td>{c.fos || '—'}</td><td>{c.caller || '—'}</td>
              <td><Pill tone={(c.paid_status || '').toUpperCase() === 'PAID' ? 'good' : 'neutral'}>{c.paid_status || 'UNPAID'}</Pill>{c.disposition && <span className="faint" style={{ fontSize: 11 }}> · {c.disposition}</span>}</td>
              <td className="r" style={{ color: 'var(--good)' }}>{inr(c.received)}</td><td className="r">{inr(c.pending)}</td></tr>)}
              {cs.data && !cs.data.length && <tr><td colSpan={7}><Empty title="No cases for the selected month" /></td></tr>}</tbody></table></div>}</Card>
      </>}
    </>); }

  if (sel) return (
    <>
      <ModuleHead icon={Users2} title={label(sel)} sub={(sel.period ? monthName(sel.period) + ' · ' : '') + 'team leads working this portfolio'}><button className="btn ghost" onClick={() => setSel(null)}><ArrowLeft />Portfolios</button></ModuleHead>
      {leads.error && <div className="card" style={{ padding: 16, color: 'var(--bad)' }}>{leads.error}</div>}
      {!leads.data ? <Skeleton h={200} /> : !leads.data.length ? <Empty title="No team leads found on this portfolio" /> :
        <div className="member-grid">{leads.data.map((l, i) => <button key={l.id} className={cx('card member rise', l.is_me && 'me')} style={{ '--i': i, textAlign: 'left', font: 'inherit', color: 'var(--text)', cursor: 'pointer' }} onClick={() => openLead(l)}>
          <div className="row"><Avatar name={l.name} size={40} /><div className="grow"><div className="cell-main">{l.name}{l.is_me ? ' (you)' : ''}</div><div className="cell-sub mono">{l.emp_code}</div></div></div>
          <div className="member-stats"><div><span>Members</span><b>{num(l.members)}</b></div><div><span>Cases</span><b>{num(l.count)}</b></div><div><span>Paid</span><b style={{ color: 'var(--good)' }}>{num(l.paid)}</b></div></div>
          <div className="cell-sub">Recovered <b style={{ color: 'var(--good)' }}>{inr(l.received)}</b> · Pending <b style={{ color: 'var(--warn)' }}>{inr(l.pending)}</b></div>
          <span className="faint" style={{ fontSize: 11.5 }}>Open team →</span></button>)}</div>}
    </>);

  const list = Array.isArray(pfs.data) ? pfs.data : null;
  return (
    <>
      <ModuleHead icon={Briefcase} title="My Portfolios" sub="Open one to see every team lead working it (read-only), or upload a portfolio file — only rows with your team-lead ID import" />
      <div className="card toolbar-card rise"><Chips value={pfMonth} onChange={setPfMonth} options={[['', 'All months'], ['current', 'This month'], ['next', 'Next month'], ['last', 'Last month']]} /></div>
      {pfs.error && <div className="card" style={{ padding: 16, color: 'var(--bad)' }}>{pfs.error}</div>}
      {!list ? <Skeleton h={240} /> : !list.length ? <Empty icon={Briefcase} title={pfMonth ? 'No portfolios for this month' : 'No portfolios yet'}>Once cases tagged with your team-lead ID are uploaded, they’ll appear here.</Empty> :
        [...new Set(list.map(p => p.period || ''))].map(per => <div key={per || 'none'} style={{ marginBottom: 18 }}>
          <div className="sec-t">{monthName(per)} <span className="faint" style={{ fontWeight: 500, fontSize: 12 }}>· {list.filter(p => (p.period || '') === per).length} portfolio(s)</span></div>
          <div className="branch-grid">{list.filter(p => (p.period || '') === per).map((p, i) => <div key={i} className="card branch-card rise" style={{ '--i': Math.min(i, 10), cursor: 'default' }}>
            <div className="row"><span className="mod-ic sm"><Briefcase /></span><b className="grow branch-n">{p.bank} · {p.product}</b></div>
            {p.branch && <div className="cell-sub">{p.branch}</div>}
            <div className="cell-sub">{num(p.count)} case(s) · {num(p.paid)} paid · {num(p.unpaid)} unpaid</div>
            <div className="branch-money"><div><span>Recovered</span><b style={{ color: 'var(--good)' }}>{inr(p.received)}</b></div><div style={{ textAlign: 'right' }}><span>Pending</span><b style={{ color: 'var(--warn)' }}>{inr(p.pending)}</b></div></div>
            <div className="row" style={{ gap: 6 }}><button className="btn sm primary" onClick={() => setSel(p)}><Users2 />Team leads</button>
              <button className="btn sm" onClick={() => ui.modal('UploadModal', { initial: p }).then(() => pfs.reload())}><Upload />Upload cases</button></div>
          </div>)}</div></div>)}
    </>
  );
}

/* ─────────── Security ─────────── */
export function Security() {
  const toast = useToast(); const ui = useClassicUI();
  const { api: capi } = useClassic();
  const st = useLoad(() => api('/api/auth/2fa/status').catch(() => ({ enabled: false })), []);
  const keys = useLoad(() => api('/api/auth/webauthn/list').catch(() => []), []);
  const [setup, setSetup] = useState(null); const [code, setCode] = useState(''); const [busy, setBusy] = useState(false);
  const begin = async () => { setBusy(true); try { setSetup(await api('/api/auth/2fa/setup', { method: 'POST' })); } catch (e) { toast(e.message, 'err'); } finally { setBusy(false); } };
  const enable = async () => { setBusy(true); try { await api('/api/auth/2fa/enable', { body: { otp: code } }); toast('Two-factor enabled'); setSetup(null); setCode(''); st.reload(); } catch (e) { toast(e.message, 'err'); } finally { setBusy(false); } };
  const disable = async () => { const c = window.prompt('Enter a current 6-digit code to turn off 2FA:'); if (!c) return; setBusy(true); try { await api('/api/auth/2fa/disable', { body: { otp: c } }); toast('Two-factor disabled'); st.reload(); } catch (e) { toast(e.message, 'err'); } finally { setBusy(false); } };
  const addKey = async () => { setBusy(true); try { const r = capi && capi.registerPasskey ? capi.registerPasskey('Passkey · ' + new Date().toLocaleDateString()) : null; if (!r) throw new Error('Passkeys are still loading — try again in a moment'); await r; toast('Passkey added'); keys.reload(); } catch (e) { toast(e.message || 'Passkey setup cancelled', 'err'); } finally { setBusy(false); } };
  const delKey = async (id) => { if (!window.confirm('Remove this passkey?')) return; try { await api('/api/auth/webauthn/' + id, { method: 'DELETE' }); keys.reload(); } catch (e) { toast(e.message, 'err'); } };
  const supported = typeof window !== 'undefined' && !!window.PublicKeyCredential && !!(navigator.credentials && navigator.credentials.create);
  const on = st.data && st.data.enabled;
  return (
    <>
      <ModuleHead icon={ShieldCheck} title="Security" sub="Two-factor sign-in, passkeys and your ViciDial agent ID" />
      <div className="grid g-2e" style={{ gap: 16 }}>
        <Card title={<span className="row" style={{ gap: 8 }}><KeyRound size={16} />Two-factor authentication</span>} sub="A 6-digit code from an authenticator app (Google Authenticator, Authy) on top of your password"
          actions={st.data && <Pill tone={on ? 'good' : 'bad'} dot>{on ? 'ON' : 'OFF'}</Pill>} className="rise">
          {!st.data ? <Skeleton h={60} /> : on ? <button className="btn" disabled={busy} onClick={disable}>Turn off 2FA</button>
            : setup ? <div className="col" style={{ gap: 10 }}>
              <div style={{ fontSize: 13 }}>Scan the QR in your authenticator app, then enter the code to confirm.</div>
              <button className="btn sm" style={{ alignSelf: 'flex-start' }} onClick={() => ui.inline('QR', { text: setup.otpauth_url, size: 200 }, 'Scan with your authenticator app', 320)}>Show QR code</button>
              <div className="faint mono" style={{ fontSize: 11.5, wordBreak: 'break-all' }}>Manual key: {setup.secret}</div>
              <input className="input" inputMode="numeric" placeholder="123456" value={code} onChange={e => setCode(e.target.value.replace(/\D/g, '').slice(0, 6))} style={{ maxWidth: 180 }} />
              <button className="btn primary" style={{ alignSelf: 'flex-start' }} disabled={busy || code.length < 6} onClick={enable}><Check />Confirm & enable</button>
            </div> : <button className="btn primary" disabled={busy} onClick={begin}>Set up 2FA</button>}
        </Card>
        <Card title={<span className="row" style={{ gap: 8 }}><Fingerprint size={16} />Passkeys / biometric</span>} sub="Sign in with Face ID, fingerprint, Windows Hello or a security key — no password. Requires HTTPS." className="rise" style={{ '--i': 1 }}>
          {supported ? <button className="btn primary" disabled={busy} onClick={addKey}><Plus />Add a passkey on this device</button> : <div className="faint">This browser/device doesn’t support passkeys.</div>}
          <div className="col" style={{ gap: 8, marginTop: 14 }}>
            {!(keys.data || []).length ? <div className="faint" style={{ fontSize: 13 }}>No passkeys yet.</div> : keys.data.map(k => <div key={k.id} className="hl-row">
              <span className="grow"><b>{k.label || 'Passkey'}</b><div className="cell-sub">{k.last_used ? 'Last used ' + fmtDate(k.last_used) : 'Never used'}</div></span>
              <button className="btn sm ghost danger" onClick={() => delKey(k.id)}><Trash2 />Remove</button></div>)}
          </div>
        </Card>
      </div>
      <Card title={<span className="row" style={{ gap: 8 }}><Phone size={16} />My ViciDial agent ID</span>} sub="View, enter or change the agent ID your calls are matched to" className="rise" style={{ marginTop: 16 }}
        actions={<button className="btn sm" onClick={() => ui.inline('MyViciAgent', {}, 'My ViciDial agent ID', 560)}>Open</button>}>
        <div className="faint" style={{ fontSize: 13 }}>Opens the agent-ID panel (saves into the ViciDial connection’s agent map).</div>
      </Card>
    </>
  );
}

/* ─────────── Help & Support / Support Inbox ─────────── */
const T_STATUS = { open: ['Open', 'warn'], in_progress: ['In progress', 'info'], resolved: ['Resolved', 'good'] };
export function Support() {
  const toast = useToast();
  const [statusF, setStatusF] = useState('');
  const { data: d, error, reload } = useLoad(() => api('/api/support/tickets' + (statusF ? '?status=' + statusF : '')), [statusF]);
  const { data: meta } = useLoad(() => api('/api/support/meta').catch(() => null), []);
  useLive(reload);
  const cats = (meta && meta.categories) || ['login', 'data', 'bug', 'feature', 'performance', 'other'];
  const [form, setForm] = useState({ subject: '', category: 'other', message: '' });
  const [sel, setSel] = useState(null); const [reply, setReply] = useState(''); const [remark, setRemark] = useState(''); const [busy, setBusy] = useState(false);
  const isSupport = d && d.is_support;
  const open = (t) => api('/api/support/tickets/' + t.id).then(setSel).catch(() => setSel(t));
  const submit = async () => { if (!form.subject.trim() || !form.message.trim()) { toast('Add a subject and describe the issue.', 'err'); return; }
    setBusy(true); try { await api('/api/support/tickets', { method: 'POST', body: form }); setForm({ subject: '', category: 'other', message: '' }); toast('Query raised — tech support will respond. Track it below.'); reload(); } catch (e) { toast(e.message, 'err'); } finally { setBusy(false); } };
  const send = async () => { if (!reply.trim()) return; setBusy(true); try { setSel(await api('/api/support/tickets/' + sel.id + '/reply', { method: 'POST', body: { text: reply } })); setReply(''); reload(); } catch (e) { toast(e.message, 'err'); } finally { setBusy(false); } };
  const setStatus = async (s) => { setBusy(true); try { setSel(await api('/api/support/tickets/' + sel.id + '/status', { method: 'POST', body: { status: s, remark } })); setRemark(''); toast('Ticket ' + s.replace('_', ' ')); reload(); } catch (e) { toast(e.message, 'err'); } finally { setBusy(false); } };
  return (
    <>
      <ModuleHead icon={isSupport ? Headset : LifeBuoy} title={isSupport ? 'Support Inbox' : 'Help & Support'}
        sub={d ? (isSupport ? `${d.counts.open || 0} open · ${d.counts.in_progress || 0} in progress · ${d.counts.resolved || 0} resolved` : 'Raise a query and track its status here') : ''} />
      {d && !isSupport && <Card title="Raise a new query / issue" className="rise" style={{ marginBottom: 16 }}>
        <div className="form-g" style={{ gridTemplateColumns: '2fr 1fr' }}>
          <Field label="Subject"><input className="input" maxLength={200} value={form.subject} onChange={e => setForm({ ...form, subject: e.target.value })} placeholder="Short summary of the problem" /></Field>
          <Field label="Category"><select className="select" value={form.category} onChange={e => setForm({ ...form, category: e.target.value })}>{cats.map(c => <option key={c} value={c}>{c[0].toUpperCase() + c.slice(1)}</option>)}</select></Field>
        </div>
        <Field label="Describe the issue"><textarea className="input" rows={4} value={form.message} onChange={e => setForm({ ...form, message: e.target.value })} placeholder="What happened, what you expected, which screen…" /></Field>
        <button className="btn primary" disabled={busy} onClick={submit}><Send />{busy ? 'Sending…' : 'Raise ticket'}</button>
      </Card>}
      {isSupport && <div className="card toolbar-card rise"><Chips value={statusF} onChange={setStatusF} options={[['', 'All'], ['open', 'Open'], ['in_progress', 'In progress'], ['resolved', 'Resolved']]} /></div>}
      {error ? <div className="card" style={{ padding: 16, color: 'var(--bad)' }}>{error}</div> : !d ? <Skeleton h={200} /> : !d.tickets.length ? <Empty icon={LifeBuoy} title={isSupport ? 'No tickets' : 'No queries yet'} /> :
        <div className="col" style={{ gap: 10 }}>{d.tickets.map((t, i) => { const [l, tn] = T_STATUS[t.status] || [t.status, 'neutral']; const last = (t.messages || [])[(t.messages || []).length - 1]; return (
          <button key={t.id} className="card creq rise" style={{ '--i': Math.min(i, 10), textAlign: 'left', font: 'inherit', color: 'var(--text)', cursor: 'pointer' }} onClick={() => open(t)}>
            <div className="row"><b className="grow">#{t.id} · {t.subject}</b><Pill tone={tn} dot>{l}</Pill></div>
            <div className="cell-sub">{t.category} · {isSupport ? `${t.user_name} (${roleName(t.user_role)})${t.branch ? ' · ' + t.branch : ''} · ` : ''}{dt(t.updated_at)}</div>
            {last && <div className="muted" style={{ fontSize: 12.5, marginTop: 4 }}>{(last.text || '').slice(0, 140)}</div>}
          </button>); })}</div>}
      {sel && <Modal open onClose={() => setSel(null)} width={680} title={`#${sel.id} · ${sel.subject}`} sub={`${sel.category} · ${sel.user_name} (${roleName(sel.user_role)})${sel.branch ? ' · ' + sel.branch : ''} · ${(T_STATUS[sel.status] || [sel.status])[0]}`}
        footer={(sel.status !== 'resolved' || isSupport) && <>
          <button className="btn" disabled={busy || !reply.trim()} onClick={send}><Send />Send reply</button>
          {isSupport && <><div className="grow" /><input className="input" style={{ maxWidth: 220 }} value={remark} onChange={e => setRemark(e.target.value)} placeholder="Resolution remark (optional)" />
            {sel.status !== 'in_progress' && <button className="btn" disabled={busy} onClick={() => setStatus('in_progress')}>In progress</button>}
            <button className="btn primary" disabled={busy} onClick={() => setStatus('resolved')}><Check />Resolve</button>
            {sel.status === 'resolved' && <button className="btn" disabled={busy} onClick={() => setStatus('open')}>Reopen</button>}</>}</>}>
        <div className="chat-thread">{(sel.messages || []).map((m, i) => { const sup = m.role === 'techsupport' || m.role === 'admin'; return (
          <div key={i} className={cx('bubble', sup ? 'them' : 'me')}><div className="cell-sub">{(m.name || (sup ? 'Support' : 'You'))} · {dt(m.at)}{m.kind && m.kind.startsWith('status:') ? ` · marked ${m.kind.split(':')[1].replace('_', ' ')}` : ''}</div>
            <div style={{ whiteSpace: 'pre-wrap', marginTop: 2 }}>{m.text}</div></div>); })}</div>
        {(sel.status !== 'resolved' || isSupport) ? <textarea className="input" rows={2} style={{ width: '100%', marginTop: 10 }} value={reply} onChange={e => setReply(e.target.value)} placeholder={isSupport ? 'Reply to the user…' : 'Add more details / reply…'} />
          : <div className="faint" style={{ marginTop: 10 }}>This ticket is resolved. Raise a new query if you still need help.</div>}
      </Modal>}
    </>
  );
}

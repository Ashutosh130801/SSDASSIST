// Admin & HR modules: Change Requests, Devices, Audit Log, Activity, RTSB, Live Monitor.
import React, { useEffect, useMemo, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import {
  Activity as ActivityIcon, ArrowRight, Camera, Check, CheckCircle2, Coins, FileEdit, Footprints, Mail, MapPin, MonitorDot,
  PhoneCall, Printer, RefreshCw, ScrollText, ShieldAlert, Smartphone, Target, Trash2, Users, Wallet, X, Ban, Radio,
} from 'lucide-react';
import { api, qs } from '../lib/api.js';
import { useAuth } from '../lib/auth.jsx';
import { cx, fmtDate, fmtTime, inr, inrShort, num, roleName } from '../lib/format.js';
import { Card, Kpi, Pill, Empty, Skeleton, useLoad, useToast } from '../components/ui.jsx';
import CaseDrawer from '../pages/CaseDrawer.jsx';
import { ModuleHead, Chips, Avatar, Bar, SearchBox, usePanel, useLive, MONTHS } from './kit.jsx';

const dt = (t) => (t ? `${fmtDate(t)} ${fmtTime(t)}` : '—');
const TONE = { approved: 'good', rejected: 'bad', pending: 'warn' };

/* ─────────── Profile change requests (HR) ─────────── */
export function ChangeRequests() {
  const toast = useToast();
  const [status, setStatus] = useState('pending');
  const [q, setQ] = useState(''); const [qd, setQd] = useState('');
  const [note, setNote] = useState({}); const [busy, setBusy] = useState(0);
  const { data, loading, reload } = useLoad(() => api('/api/manpower/change-requests' + qs({ status, q: qd })).catch(() => []), [status, qd]);
  useLive(reload);
  useEffect(() => { const t = setTimeout(() => setQd(q.trim()), 350); return () => clearTimeout(t); }, [q]);
  const rows = Array.isArray(data) ? data : [];
  const decide = async (r, d) => {
    setBusy(r.id);
    try {
      await api(`/api/manpower/change-requests/${r.id}/${d}`, { method: 'POST', body: { review_note: note[r.id] || '' } });
      toast(d === 'approve' ? 'Approved & applied to profile.' : 'Request rejected.');
      setNote(n => { const c = { ...n }; delete c[r.id]; return c; }); reload();
    } catch (e) { toast(e.message, 'err'); } finally { setBusy(0); }
  };
  return (
    <>
      <ModuleHead icon={FileEdit} title="Change Requests" sub="Employees’ requested profile edits — approve to apply, or reject" full="preqs" />
      <div className="card toolbar-card rise"><div className="row wrap" style={{ gap: 10 }}>
        <Chips value={status} onChange={setStatus} options={[['pending', 'Pending'], ['approved', 'Approved'], ['rejected', 'Rejected'], ['all', 'All']]} />
        <div className="grow" /><SearchBox value={q} onChange={setQ} placeholder="Name, field, value…" width={280} />
      </div></div>
      {loading && !rows.length && <Skeleton h={160} />}
      {!loading && !rows.length && <Empty icon={FileEdit} title={`No requests${status !== 'all' ? ' (' + status + ')' : ''}`} />}
      <div className="col" style={{ gap: 12 }}>
        {rows.map((r, i) => (
          <div key={r.id} className="card creq rise" style={{ '--i': Math.min(i, 12) }}>
            <div className="row wrap" style={{ gap: 10 }}>
              <Avatar name={r.user_name} size={36} />
              <div className="grow"><div className="cell-main">{r.user_name}</div><div className="cell-sub">{[r.user_code, r.user_branch].filter(Boolean).join(' · ')}</div></div>
              <Pill tone={TONE[r.status] || 'neutral'} dot>{r.status}</Pill>
              <span className="faint" style={{ fontSize: 12 }}>{dt(r.created_at)}</span>
            </div>
            <div className="creq-diff">
              <span className="creq-f">{r.field_label}</span>
              <span className="creq-old">{r.old_value || '—'}</span><ArrowRight size={15} className="faint" /><span className="creq-new">{r.new_value}</span>
            </div>
            {r.note && <div className="muted" style={{ fontSize: 12.5 }}>Reason: {r.note}</div>}
            {r.status === 'pending' ? <div className="row wrap" style={{ gap: 8, marginTop: 10 }}>
              <input className="input grow" placeholder="Remark (optional)" value={note[r.id] || ''} onChange={e => setNote(n => ({ ...n, [r.id]: e.target.value }))} />
              <button className="btn sm primary" disabled={busy === r.id} onClick={() => decide(r, 'approve')}><Check />Approve & apply</button>
              <button className="btn sm" disabled={busy === r.id} onClick={() => decide(r, 'reject')}><X />Reject</button>
            </div> : <div className="faint" style={{ fontSize: 12, marginTop: 8 }}>{r.status === 'approved' ? 'Applied' : 'Rejected'}{r.reviewer_name ? ' by ' + r.reviewer_name : ''}{r.review_note ? ' · ' + r.review_note : ''}</div>}
          </div>
        ))}
      </div>
    </>
  );
}

/* ─────────── Devices (approve sign-in devices) ─────────── */
export function Devices() {
  const toast = useToast();
  const [q, setQ] = useState('');
  const { data, loading, reload } = useLoad(() => api('/api/devices').catch(() => []), []);
  const items = Array.isArray(data) ? data : [];
  const act = async (id, kind) => {
    try {
      if (kind === 'delete') await api('/api/devices/' + id, { method: 'DELETE' }); else await api('/api/devices/' + id + '/' + kind, { method: 'POST' });
      toast(kind === 'approve' ? 'Device approved' : kind === 'revoke' ? 'Device revoked' : 'Device removed'); reload();
    } catch (e) { toast(e.message, 'err'); }
  };
  const words = q.trim().toLowerCase().split(/\s+/).filter(Boolean);
  const hay = d => [d.user_name, d.user_code, d.user_role, roleName(d.user_role), d.user_branch, d.device_id, d.label].filter(Boolean).join(' ').toLowerCase();
  const shown = words.length ? items.filter(d => words.every(w => hay(d).includes(w))) : items;
  const pending = shown.filter(d => !d.approved); const approved = shown.filter(d => d.approved);
  const CAP = 2, EXEMPT = ['admin', 'techsupport'];
  const tbl = (list, isP) => (
    <div className="table-wrap"><table className="t">
      <thead><tr><th>User</th><th>Branch</th><th>Active devices</th><th>Device</th><th>Last seen</th><th></th></tr></thead>
      <tbody>{list.map(d => { const n = d.approved_count || 0; const ex = EXEMPT.includes(d.user_role); return (
        <tr key={d.id}>
          <td><div className="row" style={{ gap: 8 }}><Avatar name={d.user_name} size={28} /><div><div className="cell-main">{d.user_name || '#' + d.user_id}</div>
            <div className="cell-sub">{[d.user_code, roleName(d.user_role), d.label].filter(Boolean).join(' · ')}</div></div></div></td>
          <td className="muted">{d.user_branch || '—'}</td>
          <td><Pill tone={n >= CAP && !ex ? 'warn' : 'accent'}>{n} approved</Pill>
            <div className="cell-sub">{ex ? 'no limit' : isP && n >= CAP ? `approving drops the oldest (max ${CAP})` : `max ${CAP}`}</div></td>
          <td className="mono">{d.device_id}</td>
          <td className="faint" style={{ whiteSpace: 'nowrap' }}>{dt(d.last_seen)}</td>
          <td style={{ whiteSpace: 'nowrap' }}>{isP
            ? <><button className="btn sm primary" onClick={() => act(d.id, 'approve')}><Check />Approve</button> <button className="btn sm" onClick={() => act(d.id, 'delete')}><X />Reject</button></>
            : <><button className="btn sm" onClick={() => act(d.id, 'revoke')}><Ban />Revoke</button> <button className="btn sm ghost danger" onClick={() => act(d.id, 'delete')}><Trash2 /></button></>}</td>
        </tr>); })}</tbody></table></div>
  );
  return (
    <>
      <ModuleHead icon={Smartphone} title="Devices" sub="A new device is blocked until you approve it" full="devices">
        <button className="btn" onClick={reload}><RefreshCw />Refresh</button>
      </ModuleHead>
      <div className="grid g-kpi" style={{ marginBottom: 16 }}>
        <Kpi icon={ShieldAlert} label="Pending approval" i={1} value={num(items.filter(d => !d.approved).length)} tone="warn" />
        <Kpi icon={CheckCircle2} label="Approved" i={2} value={num(items.filter(d => d.approved).length)} tone="good" />
        <Kpi icon={Users} label="People" i={3} value={num(new Set(items.map(d => d.user_id)).size)} tone="info" />
      </div>
      <div className="card toolbar-card rise"><div className="row wrap" style={{ gap: 10 }}>
        <SearchBox value={q} onChange={setQ} placeholder="Name, employee ID, role, branch or device ID" width={420} />
        {q && <span className="faint">{shown.length} of {items.length} devices</span>}
      </div></div>
      {loading && !items.length && <Skeleton h={200} />}
      <Card title={`Pending approval · ${pending.length}`} pad={false} className="rise" style={{ marginBottom: 16 }}>
        {pending.length ? tbl(pending, true) : <Empty icon={ShieldAlert} title={q ? 'No pending devices match' : 'No devices awaiting approval'} />}
      </Card>
      <Card title={`Approved devices · ${approved.length}`} pad={false} className="rise">
        {approved.length ? tbl(approved, false) : <Empty icon={Smartphone} title={q ? 'No approved devices match' : 'No approved devices yet'} />}
      </Card>
    </>
  );
}

/* ─────────── Audit log ─────────── */
const BLANK = { role: '', emp: '', action: '', branch: '', bank: '', product: '', days: '', q: '' };
export function AuditLog() {
  const { user } = useAuth();
  const panel = usePanel();
  const [f, setF] = useState(BLANK); const [qd, setQd] = useState('');
  const [page, setPage] = useState(0); const PAGE = 300;
  const { data: opts } = useLoad(() => api('/api/audit/filters').catch(() => ({})), []);
  useEffect(() => { const t = setTimeout(() => { setQd(f.q); setPage(0); }, 300); return () => clearTimeout(t); }, [f.q]);
  const { data, loading, reload } = useLoad(() => api('/api/audit' + qs({ ...f, q: qd, limit: PAGE, offset: page * PAGE })).catch(() => ({ items: [], total: 0 })),
    [f.role, f.emp, f.action, f.branch, f.bank, f.product, f.days, qd, page]);
  useLive(reload);
  const set = (k, v) => { setPage(0); setF(p => ({ ...p, [k]: v })); };
  const active = Object.values(f).filter(Boolean).length;
  const items = (data && data.items) || [];
  const o = opts || {};
  const sel = (k, label, list, map = (x) => [x, x]) => <select className="select" value={f[k]} onChange={e => set(k, e.target.value)}>
    <option value="">{label}</option>{(list || []).map(x => { const [v, l] = map(x); return <option key={v} value={v}>{l}</option>; })}</select>;
  return (
    <>
      <ModuleHead icon={ScrollText} title="Audit Log" sub={`Every change, re-allocation, payment, visit, call and edit — with who did it${user && user.role === 'manager' ? ' · your branch' : ''}`} full="audit">
        <span className="pill accent">{data ? num(data.total) + ' tracked actions' : '…'}</span>
      </ModuleHead>
      <div className="card toolbar-card rise"><div className="row wrap" style={{ gap: 8 }}>
        <SearchBox value={f.q} onChange={v => setF(p => ({ ...p, q: v }))} placeholder="Text, person or value" width={240} />
        {sel('role', 'All roles', o.roles)}
        {sel('emp', 'All employees', o.employees, e => [e.id, `${e.name} (${e.role})`])}
        {sel('action', 'All actions', o.actions)}
        {user && user.role !== 'manager' && sel('branch', 'All branches', o.branches)}
        {sel('bank', 'All banks', o.banks)}
        {sel('product', 'All products', o.products)}
        <select className="select" value={f.days} onChange={e => set('days', e.target.value)}><option value="">Any time</option><option value="1">Today</option><option value="7">Last 7 days</option><option value="30">Last 30 days</option></select>
        {active > 0 && <button className="btn sm ghost" onClick={() => { setPage(0); setF(BLANK); }}><X />Clear ({active})</button>}
      </div></div>
      <Card pad={false} className="rise">
        {loading && !items.length ? <div style={{ padding: 16 }}><Skeleton h={240} /></div> : !items.length ? <Empty icon={ScrollText} title="No matching activity" /> :
          <div className="table-wrap" style={{ maxHeight: 'calc(100vh - 300px)' }}><table className="t">
            <thead><tr><th>When</th><th>Who</th><th>Action</th><th>Case</th><th>Field</th><th>Change</th><th>Detail</th><th>Branch</th></tr></thead>
            <tbody>{items.map(r => <tr key={r.id} className="click" onClick={() => panel('audit', { row: r })} title="Open full log & case details">
              <td className="faint" style={{ whiteSpace: 'nowrap', fontSize: 12 }}>{dt(r.at)}</td>
              <td><div className="cell-main">{r.actor || '—'}</div><div className="cell-sub">{r.role}</div></td>
              <td><Pill tone="accent">{r.action}</Pill></td>
              <td>{r.meta && r.meta.dpr ? <Pill tone="info">{r.meta.changes_count ?? '—'} cases · view</Pill>
                : r.meta && r.meta.bulk ? <Pill tone="info">{r.meta.cases ?? r.meta.items_count ?? '—'} cases · view</Pill>
                : r.customer ? <><div>{r.customer}</div><div className="cell-sub">#{r.case_id}</div></> : r.case_id ? '#' + r.case_id : '—'}</td>
              <td className="muted" style={{ fontSize: 12 }}>{r.field || '—'}</td>
              <td style={{ fontSize: 12 }}>{(r.old || r.new) ? <span><span className="faint">{r.old ?? '∅'}</span> → <b>{r.new ?? '∅'}</b></span> : '—'}</td>
              <td style={{ fontSize: 12, maxWidth: 280 }}>{r.detail || '—'}</td>
              <td className="muted" style={{ fontSize: 12 }}>{r.branch || '—'}</td>
            </tr>)}</tbody></table></div>}
        {data && data.total > items.length && <div className="row" style={{ justifyContent: 'center', gap: 10, padding: 12 }}>
          <span className="faint">Page {page + 1} — {items.length} of {num(data.total)}</span>
          {page > 0 && <button className="btn sm" onClick={() => setPage(p => p - 1)}>‹ Prev</button>}
          {(page + 1) * PAGE < data.total && <button className="btn sm" onClick={() => setPage(p => p + 1)}>Next ›</button>}
        </div>}
      </Card>
    </>
  );
}

/* ─────────── Activity (visits / calls / payments) ─────────── */
const KIND_ICON = { payment: Wallet, call: PhoneCall, visit: Footprints };
export function Activity() {
  const { user } = useAuth();
  const [sp, setSp] = useSearchParams();
  const [kind, setKind] = useState('all'); const [flag, setFlag] = useState(false);
  const [f, setF] = useState({ bank: '', branch: '', product: '', area: '', emp: '' });
  const { data: opts } = useLoad(() => api('/api/analytics/activity/filters').catch(() => ({})), []);
  const { data: sum, reload: rs } = useLoad(() => api('/api/analytics/summary').catch(() => null), []);
  const { data, loading, reload } = useLoad(() => api('/api/analytics/activity' + qs({ kind, limit: 250, ...f })).catch(() => []), [kind, f.bank, f.branch, f.product, f.area, f.emp]);
  useLive(() => { rs(); reload(); });
  const items = Array.isArray(data) ? data : [];
  const shown = items.filter(r => !flag || r.off_location);
  const flagged = items.filter(r => r.off_location).length;
  const o = opts || {};
  const set = (k, v) => setF(p => ({ ...p, [k]: v }));
  const nf = Object.values(f).filter(Boolean).length;
  return (
    <>
      <ModuleHead icon={ActivityIcon} title="Activity" sub="Field visits, calls and payments as they happen — with photos and GPS" full="records">
        <button className="btn" onClick={() => { rs(); reload(); }}><RefreshCw />Refresh</button>
      </ModuleHead>
      {sum && <div className="grid g-kpi" style={{ marginBottom: 16 }}>
        <Kpi icon={Users} label="Cases" i={1} value={num(sum.cases)} sub={`${num(sum.users_total)} staff accounts`} />
        <Kpi icon={Footprints} label="Field visits" i={2} value={num(sum.visits)} tone="info" />
        <Kpi icon={PhoneCall} label="Calls logged" i={3} value={num(sum.calls)} sub={`${num(sum.payments)} payments`} tone="accent" />
        <Kpi icon={MapPin} label="Location pings" i={4} value={num(sum.location_pings)} sub={`${num(sum.import_batches)} uploads`} tone="good" />
      </div>}
      <div className="card toolbar-card rise">
        <div className="row wrap" style={{ gap: 8 }}>
          <select className="select" value={f.bank} onChange={e => set('bank', e.target.value)}><option value="">All banks</option>{(o.banks || []).map(b => <option key={b}>{b}</option>)}</select>
          {user && user.role !== 'manager' && <select className="select" value={f.branch} onChange={e => set('branch', e.target.value)}><option value="">All branches</option>{(o.branches || []).map(b => <option key={b}>{b}</option>)}</select>}
          <select className="select" value={f.product} onChange={e => set('product', e.target.value)}><option value="">All products</option>{(o.products || []).map(b => <option key={b}>{b}</option>)}</select>
          <select className="select" value={f.area} onChange={e => set('area', e.target.value)}><option value="">All areas</option>{(o.areas || []).map(b => <option key={b}>{b}</option>)}</select>
          <select className="select" value={f.emp} onChange={e => set('emp', e.target.value)}><option value="">All FOS & callers</option>{(o.employees || []).map(e => <option key={e.id} value={e.id}>{e.name} · {e.role === 'fos' ? 'FOS' : 'Caller'}</option>)}</select>
          {nf > 0 && <button className="btn sm ghost" onClick={() => setF({ bank: '', branch: '', product: '', area: '', emp: '' })}><X />Clear ({nf})</button>}
        </div>
        <div className="row wrap" style={{ gap: 8 }}>
          <Chips value={kind} onChange={(v) => { setKind(v); setFlag(false); }} options={[['all', 'All activity'], ['visits', 'Field visits'], ['calls', 'Calls'], ['payments', 'Payments']]} />
          <button className={cx('chip', 'warn-chip', flag && 'on')} onClick={() => setFlag(v => !v)}><ShieldAlert size={13} />Off-location{flagged ? ` (${flagged})` : ''}</button>
          <div className="grow" /><span className="faint">{shown.length} records</span>
        </div>
      </div>
      <Card pad={false} className="rise">
        {loading && !items.length ? <div style={{ padding: 16 }}><Skeleton h={240} /></div> : !shown.length ? <Empty icon={ActivityIcon} title={flag ? 'No off-location visits — all clear' : 'No activity matches these filters'} /> :
          <div className="table-wrap" style={{ maxHeight: 'calc(100vh - 380px)' }}><table className="t">
            <thead><tr><th></th><th>When</th><th>Customer</th><th>Portfolio</th><th>Area / branch</th><th>By</th><th>Detail</th><th className="r">Amount</th></tr></thead>
            <tbody>{shown.map((r, i) => { const I = KIND_ICON[r.type] || ActivityIcon; return (
              <tr key={i} className={cx('click', r.off_location && 'flag-row')} onClick={() => r.case_id && setSp({ open: r.case_id })}>
                <td><span className={'mod-ic xs ' + (r.type === 'payment' ? 'good' : r.type === 'call' ? 'info' : 'accent')}><I /></span></td>
                <td className="faint" style={{ whiteSpace: 'nowrap', fontSize: 12 }}>{dt(r.at)}</td>
                <td className="cell-main">{r.customer || '—'}</td>
                <td className="muted">{r.bank || '—'}<div className="cell-sub">{r.product || ''}</div></td>
                <td className="muted">{r.area || '—'}<div className="cell-sub">{r.branch || ''}</div></td>
                <td>{r.by || '—'}</td>
                <td className="muted" style={{ maxWidth: 300 }} onClick={e => e.stopPropagation()}>{r.detail || '—'}
                  {r.photo && <a href={r.photo} target="_blank" rel="noreferrer" className="ico-link" title="Photo"><Camera size={14} /></a>}
                  {r.lat && <a href={`https://maps.google.com/?q=${r.lat},${r.lng}`} target="_blank" rel="noreferrer" className="ico-link" title="GPS"><MapPin size={14} /></a>}
                  {r.off_location && <Pill tone="bad">off-location</Pill>}
                  {r.note && <div className="cell-sub">{r.note}</div>}</td>
                <td className="r">{r.amount > 0 ? <b style={{ color: 'var(--good)' }}>{inr(r.amount)}</b> : '—'}</td>
              </tr>); })}</tbody></table></div>}
      </Card>
      <CaseDrawer id={Number(sp.get('open')) || null} onClose={() => setSp({})} />
    </>
  );
}

/* ─────────── RTSB — target vs achievement ─────────── */
export function Rtsb() {
  const [mb, setMb] = useState('current'); const [role, setRole] = useState(''); const [tab, setTab] = useState('pending');
  const { data: d, loading, reload } = useLoad(() => api('/api/mis/rtsb' + qs({ month_bucket: mb, role })).catch(() => ({ people: [], totals: {}, achieved_list: [], pending_list: [] })), [mb, role]);
  useLive(reload);
  const t = (d && d.totals) || {};
  const list = !d ? [] : tab === 'achieved' ? d.achieved_list || [] : tab === 'all' ? d.people || [] : d.pending_list || [];
  const email = () => {
    const lines = ((d && d.people) || []).map(p => `${p.name} (${p.role === 'fos' ? 'Field' : 'Caller'}): ${p.pct_done}% — target ${inr(p.target_enr)}, achieved ${inr(p.achieved_enr)}, gap ${inr(p.gap_enr)}`).join('%0D%0A');
    window.location.href = `mailto:?subject=${encodeURIComponent(`RTSB scorecard (${mb})`)}&body=RTSB — ${t.achieved || 0}/${t.people || 0} on target.%0D%0A%0D%0A${lines}`;
  };
  const hit = t.people ? Math.round((t.achieved || 0) * 100 / t.people) : 0;
  return (
    <>
      <ModuleHead icon={Target} title="RTSB" sub="Target vs achievement for every caller and field agent" full="rtsb">
        <button className="btn" onClick={() => window.print()}><Printer />Print</button>
        <button className="btn" onClick={email}><Mail />Email</button>
      </ModuleHead>
      <div className="card toolbar-card rise"><div className="row wrap" style={{ gap: 10 }}>
        <Chips value={mb} onChange={setMb} options={[...MONTHS, ['all', 'All']]} />
        <Chips value={role} onChange={setRole} options={[['', 'Everyone'], ['caller', 'Callers'], ['fos', 'Field agents']]} />
      </div></div>
      {loading && !d && <Skeleton h={300} />}
      {d && <>
        <div className="grid g-kpi" style={{ marginBottom: 16 }}>
          <Kpi icon={Users} label="People" i={1} value={num(t.people)} />
          <Kpi icon={CheckCircle2} label="Achieved" i={2} value={num(t.achieved)} sub={hit + '% of people'} tone="good" />
          <Kpi icon={ShieldAlert} label="Not yet" i={3} value={num(t.pending)} tone="warn" />
          <Kpi icon={Target} label="Target ENR" i={4} value={t.target_enr || 0} format={inrShort} tone="info" />
          <Kpi icon={Coins} label="Achieved ENR" i={5} value={t.achieved_enr || 0} format={inrShort} tone="good" />
        </div>
        <div className="seg-tabs rise">
          {[['pending', 'Not achieved', (d.pending_list || []).length], ['achieved', 'Achieved', (d.achieved_list || []).length], ['all', 'All', (d.people || []).length]].map(([v, l, n]) =>
            <button key={v} className={tab === v ? 'on' : ''} onClick={() => setTab(v)}><span>{l}</span><b>{n}</b></button>)}
        </div>
        <Card pad={false} className="rise">
          {!list.length ? <Empty icon={Target} title="No one here" /> :
            <div className="table-wrap"><table className="t">
              <thead><tr><th>Name</th><th>Role</th><th className="r">Cases</th><th className="r">Paid</th><th className="r">Target</th><th className="r">Achieved</th><th className="r">Gap</th><th style={{ width: 200 }}>% done</th></tr></thead>
              <tbody>{list.map(p => <tr key={p.role + p.id}>
                <td><div className="row" style={{ gap: 8 }}><Avatar name={p.name} size={26} /><div><div className="cell-main">{p.name}</div>{p.emp_code && <div className="cell-sub mono">{p.emp_code}</div>}</div></div></td>
                <td><Pill tone={p.role === 'fos' ? 'info' : 'accent'}>{p.role === 'fos' ? 'Field' : 'Caller'}</Pill></td>
                <td className="r">{num(p.cases)}</td><td className="r">{num(p.paid)}</td>
                <td className="r">{inr(p.target_enr)}</td><td className="r" style={{ color: 'var(--good)' }}>{inr(p.achieved_enr)}</td>
                <td className="r" style={{ color: 'var(--warn)' }}>{inr(p.gap_enr)}</td>
                <td><div className="row" style={{ gap: 8 }}><Bar pct={p.pct_done} h={6} tone={p.achieved ? 'good' : p.pct_done >= 60 ? 'accent' : 'warn'} /><b className="num" style={{ minWidth: 40 }}>{p.pct_done}%</b></div></td>
              </tr>)}</tbody></table></div>}
        </Card>
      </>}
    </>
  );
}

/* ─────────── Live Monitor (war-room) ─────────── */
export function Monitor() {
  const { data: d, loading, reload } = useLoad(() => api('/api/monitor/live').catch(() => null), []);
  useLive(reload);
  useEffect(() => { const t = setInterval(reload, 15000); return () => clearInterval(t); }, []); // eslint-disable-line
  const c = (d && d.counters) || {};
  const feed = (d && d.feed) || [];
  return (
    <>
      <ModuleHead icon={MonitorDot} title="Live Monitor" sub="War-room view — updates every 15 seconds" full="monitor">
        <span className="pill good"><Radio size={13} className="pulse" /> live</span>
      </ModuleHead>
      {loading && !d && <Skeleton h={300} />}
      {d && <>
        <div className="grid g-kpi" style={{ marginBottom: 16 }}>
          <Kpi icon={Users} label="Online now" i={1} value={num(c.online_now)} tone="good" />
          <Kpi icon={PhoneCall} label="Calls today" i={2} value={num(c.calls)} tone="accent" />
          <Kpi icon={Footprints} label="Visits today" i={3} value={num(c.visits)} tone="info" />
          <Kpi icon={CheckCircle2} label="Payments" i={4} value={num(c.paid_count)} tone="good" />
          <Kpi icon={Wallet} label="Collected today" i={5} value={c.collected || 0} format={inrShort} tone="warn" />
        </div>
        <Card title="Live activity feed" sub={`${feed.length} events today`} className="rise">
          {!feed.length ? <Empty icon={ActivityIcon} title="No activity yet today" /> :
            <div className="feed">{feed.map((f, i) => { const I = f.type === 'call' ? PhoneCall : Footprints; return (
              <div key={i} className="feed-i rise" style={{ '--i': Math.min(i, 10) }}>
                <span className="feed-t num">{fmtTime(f.at)}</span>
                <span className={'mod-ic xs ' + (f.type === 'call' ? 'accent' : 'info')}><I /></span>
                <b className="feed-w">{f.who}</b><span className="feed-d grow">{f.detail}</span>
                {f.amount > 0 && <b style={{ color: 'var(--good)' }}>{inr(f.amount)}</b>}
              </div>); })}</div>}
        </Card>
      </>}
    </>
  );
}

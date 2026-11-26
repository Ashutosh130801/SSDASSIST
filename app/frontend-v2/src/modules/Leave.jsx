import React, { useEffect, useMemo, useState } from 'react';
import { CalendarCheck2, CalendarClock, CalendarDays, Check, Hourglass, Palmtree, Send, UserCheck, X } from 'lucide-react';
import { api, qs } from '../lib/api.js';
import { useAuth } from '../lib/auth.jsx';
import { cx, num } from '../lib/format.js';
import { Card, Kpi, Pill, Empty, Skeleton, useLoad, useToast } from '../components/ui.jsx';
import { ModuleHead, Chips, Modal, Field, Bar, Avatar, SearchBox, useLive } from './kit.jsx';

const TYPES = ['Casual', 'Sick', 'Earned', 'Unpaid'];
const ROLES = [['all', 'All roles'], ['fos', 'FOS'], ['telecaller', 'Caller'], ['teamlead', 'Team Lead'], ['manager', 'Manager'],
  ['headoffice', 'Head Office'], ['hr', 'HR'], ['backend', 'Back office'], ['admin', 'Admin']];
const roleL = (r) => (ROLES.find(x => x[0] === r) || [, r])[1] || '—';
const days = (l) => l.days_effective ?? (l.half_day ? 0.5 : Number(l.days || 0));
const dur = (l) => (l.half_day ? '0.5 · half day' : days(l));
const TONE = { approved: 'good', rejected: 'bad', pending: 'warn' };

function StatusCell({ l }) {
  return <div>
    <Pill tone={TONE[l.status] || 'neutral'} dot>{l.partial && l.status === 'approved' ? 'partly approved' : l.status}</Pill>
    {l.partial && l.requested_start && <div className="cell-sub">{l.parent_id ? `part of request #${l.parent_id}` : `asked ${l.requested_days} day(s): ${l.requested_start} → ${l.requested_end}`}</div>}
    {l.decision_note && <div className="cell-sub" style={{ color: l.status === 'rejected' ? 'var(--bad)' : undefined }}>{l.status === 'rejected' ? 'Reason: ' : 'Note: '}{l.decision_note}</div>}
  </div>;
}

/** Approve all, approve only chosen dates, or reject with a reason (Sundays never count). */
function Decide({ leave, mode, onClose, onDone }) {
  const toast = useToast();
  const all = useMemo(() => {
    const out = []; const s = new Date(leave.start_date + 'T00:00:00'); const e = new Date(leave.end_date + 'T00:00:00');
    for (let d = new Date(s); d <= e; d.setDate(d.getDate() + 1)) if (d.getDay() !== 0) out.push(`${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`);
    return out;
  }, [leave]);
  const [picked, setPicked] = useState(() => new Set(all));
  const [note, setNote] = useState(''); const [busy, setBusy] = useState(false); const [err, setErr] = useState('');
  const reject = mode === 'reject';
  const partial = !reject && !leave.half_day && picked.size < all.length;
  const fmt = d => new Date(d + 'T00:00:00').toLocaleDateString('en-IN', { weekday: 'short', day: '2-digit', month: 'short' });
  const toggle = d => setPicked(p => { const n = new Set(p); n.has(d) ? n.delete(d) : n.add(d); return n; });
  const submit = async () => {
    setErr('');
    if (reject && !note.trim()) { setErr('Please write the reason for rejection — the employee will see it.'); return; }
    if (!reject && !leave.half_day && picked.size === 0) { setErr('Select at least one date to approve, or reject the request.'); return; }
    setBusy(true);
    try {
      const body = { note: note.trim() || undefined };
      if (partial) body.dates = all.filter(d => picked.has(d));
      await api(`/api/leaves/${leave.id}/${reject ? 'reject' : 'approve'}`, { method: 'POST', body });
      toast(reject ? 'Rejected' : partial ? `Approved ${picked.size} of ${all.length} day(s)` : 'Approved'); onDone();
    } catch (e) { setErr(e.message); } finally { setBusy(false); }
  };
  return (
    <Modal open onClose={onClose} title={reject ? 'Reject leave' : 'Approve leave'}
      sub={`${leave.user_name} · ${leave.leave_type} · ${leave.start_date} → ${leave.end_date} · asked ${leave.half_day ? '0.5' : all.length} day(s)`}
      footer={<><button className="btn" onClick={onClose}>Cancel</button><div className="grow" />
        <button className={cx('btn', reject ? 'danger-solid' : 'primary')} disabled={busy} onClick={submit}>{busy ? 'Saving…' : reject ? 'Reject' : partial ? `Approve ${picked.size} day(s)` : 'Approve'}</button></>}>
      {leave.reason && <div className="quote">“{leave.reason}”</div>}
      {!reject && !leave.half_day && all.length > 1 && <>
        <div className="row wrap" style={{ gap: 8, margin: '8px 0' }}>
          <span className="faint">Days to grant</span><b>{picked.size}</b><span className="faint">of {all.length}</span><div className="grow" />
          <button className="btn sm ghost" onClick={() => setPicked(new Set(all))}>All</button><button className="btn sm ghost" onClick={() => setPicked(new Set())}>None</button>
        </div>
        <div className="day-grid">{all.map(d => <button key={d} type="button" className={cx('day', picked.has(d) && 'on')} onClick={() => toggle(d)}>{picked.has(d) ? <Check /> : <span />}{fmt(d)}</button>)}</div>
        {partial && <div style={{ color: 'var(--warn)', fontSize: 12.5, marginTop: 8 }}>Partial approval — the other {all.length - picked.size} day(s) won’t count as leave.</div>}
      </>}
      <Field label={reject ? 'Reason for rejection (required)' : 'Note to employee (optional)'}>
        <textarea className="input" rows={3} value={note} onChange={e => setNote(e.target.value)} placeholder={reject ? 'e.g. Month-end closing — team already short that week' : 'Optional'} />
      </Field>
      {err && <div style={{ color: 'var(--bad)', fontSize: 13 }}>{err}</div>}
    </Modal>
  );
}

/** Leave — apply, balances, my requests; approvals, history and per-employee balances for HR / managers. */
export default function Leave() {
  const { user } = useAuth();
  const toast = useToast();
  const isMgr = ['admin', 'manager', 'hr', 'headoffice'].includes(user && user.role);
  const [type, setType] = useState('Casual'); const [s1, setS1] = useState(''); const [s2, setS2] = useState('');
  const [half, setHalf] = useState(false); const [reason, setReason] = useState(''); const [busy, setBusy] = useState(false);
  const [decide, setDecide] = useState(null);
  const [hf, setHf] = useState({ status: 'all', type: 'all', role: 'all', from: '', to: '', q: '' });
  const [hq, setHq] = useState('');
  const [balRole, setBalRole] = useState('all'); const [balQ, setBalQ] = useState(''); const [balQd, setBalQd] = useState('');

  const bal = useLoad(() => api('/api/leaves/balance').catch(() => []), []);
  const mine = useLoad(() => api('/api/leaves?scope=mine').catch(() => []), []);
  const team = useLoad(() => (isMgr ? api('/api/leaves?scope=team&status=pending').catch(() => []) : Promise.resolve([])), [isMgr]);
  const ins = useLoad(() => (isMgr ? api('/api/leaves/insights').catch(() => null) : Promise.resolve(null)), [isMgr]);
  const hist = useLoad(() => (isMgr ? api('/api/leaves' + qs({ scope: 'team', status: hf.status !== 'all' ? hf.status : '', leave_type: hf.type !== 'all' ? hf.type : '',
    role: hf.role !== 'all' ? hf.role : '', from_date: hf.from, to_date: hf.to, q: hq })).catch(() => []) : Promise.resolve([])), [isMgr, hf.status, hf.type, hf.role, hf.from, hf.to, hq]);
  const bals = useLoad(() => (isMgr ? api('/api/leaves/balances' + qs({ role: balRole !== 'all' ? balRole : '', q: balQd })).catch(() => ({ rows: [] })) : Promise.resolve(null)), [isMgr, balRole, balQd]);
  const reloadAll = () => { bal.reload(); mine.reload(); team.reload(); ins.reload(); hist.reload(); bals.reload(); };
  useLive(reloadAll);
  useEffect(() => { const t = setTimeout(() => setHq(hf.q.trim()), 350); return () => clearTimeout(t); }, [hf.q]);

  const balances = Array.isArray(bal.data) ? bal.data : [];
  const cur = balances.find(b => b.type === type);
  const apply = async () => {
    if (busy || !s1 || (!half && !s2)) return;
    if (!half && s2 < s1) { toast('End date must be on or after start date.', 'err'); return; }
    setBusy(true);
    try { await api('/api/leaves', { method: 'POST', body: { leave_type: type, start_date: s1, end_date: half ? s1 : s2, half_day: half, reason } });
      toast(half ? 'Half-day leave requested (0.5 day).' : 'Leave applied.'); setReason(''); setS1(''); setS2(''); setHalf(false); reloadAll();
    } catch (e) { toast(e.message, 'err'); } finally { setBusy(false); }
  };
  const pend = Array.isArray(team.data) ? team.data : [];
  const histRows = Array.isArray(hist.data) ? hist.data : [];
  const grouped = useMemo(() => {
    const g = {}; histRows.forEach(l => { const k = String(l.start_date || '').slice(0, 7) || '—'; (g[k] = g[k] || []).push(l); });
    return Object.keys(g).sort().reverse().map(k => [k, g[k]]);
  }, [histRows]);
  const monthL = (ym) => { try { const [y, m] = ym.split('-'); return new Date(y, m - 1, 1).toLocaleString('en-IN', { month: 'long', year: 'numeric' }); } catch { return ym; } };
  const I = ins.data;

  return (
    <>
      <ModuleHead icon={Palmtree} title="Leave" sub={isMgr ? 'Requests, approvals, history and balances' : 'Apply for leave and track your requests'} full="leave" />

      {isMgr && I && <div className="grid g-kpi" style={{ marginBottom: 16 }}>
        <Kpi icon={Hourglass} label="Pending approvals" i={1} value={num(I.pending)} tone="warn" sub="waiting on you" />
        <Kpi icon={UserCheck} label="On leave today" i={2} value={num((I.on_leave_today || []).length)} tone="info"
          sub={(I.on_leave_today || []).map(x => x.name + (x.half_day ? ' (½)' : '')).join(', ') || '—'} />
        <Kpi icon={CalendarClock} label="Upcoming 7 days" i={3} value={num(I.upcoming_week)} tone="accent" />
      </div>}

      {isMgr && <Card title={`Pending approvals · ${pend.length}`} pad={false} className="rise" style={{ marginBottom: 16 }}>
        {!pend.length ? <Empty icon={CalendarCheck2} title="Nothing to approve" /> :
          <div className="table-wrap"><table className="t">
            <thead><tr><th>Who</th><th>Type</th><th>Dates</th><th>Days</th><th>Reason</th><th></th></tr></thead>
            <tbody>{pend.map(l => <tr key={l.id}>
              <td><div className="row" style={{ gap: 8 }}><Avatar name={l.user_name} size={28} /><div><div className="cell-main">{l.user_name}</div><div className="cell-sub">{l.user_branch}</div></div></div></td>
              <td><Pill tone="accent">{l.leave_type}</Pill></td><td className="muted">{l.start_date} → {l.end_date}</td><td className="num">{dur(l)}</td>
              <td className="muted" style={{ maxWidth: 260 }}>{l.reason || '—'}</td>
              <td style={{ whiteSpace: 'nowrap' }}>{l.user_id === user.id ? <span className="faint">Your request — sent to Admin</span> : <>
                <button className="btn sm primary" onClick={() => setDecide({ l, mode: 'approve' })}><Check />Approve</button>{' '}
                <button className="btn sm" onClick={() => setDecide({ l, mode: 'reject' })}><X />Reject</button></>}</td>
            </tr>)}</tbody></table></div>}
      </Card>}

      <div className="grid g-2e" style={{ marginBottom: 16 }}>
        <Card title="Apply for leave" className="rise">
          <Chips value={half ? 'half' : 'full'} onChange={v => { const h = v === 'half'; setHalf(h); if (h) setS2(s1); }} options={[['full', 'Full day / multiple days'], ['half', 'Half day (0.5)']]} />
          <div className="form-g">
            <Field label="Type"><select className="select" value={type} onChange={e => setType(e.target.value)}>{TYPES.map(t => <option key={t}>{t}</option>)}</select></Field>
            <Field label="Balance"><div className="input ro">{cur ? (cur.remaining != null ? `${cur.remaining} of ${cur.allowance} left` : 'no limit') : '—'}</div></Field>
            <Field label={half ? 'Date' : 'From'}><input className="input" type="date" value={s1} disabled={busy} onChange={e => { setS1(e.target.value); if (half) setS2(e.target.value); }} /></Field>
            {!half && <Field label="To"><input className="input" type="date" min={s1 || undefined} value={s2} disabled={busy} onChange={e => setS2(e.target.value)} /></Field>}
          </div>
          {half && <div className="faint" style={{ fontSize: 12, margin: '4px 0 8px' }}>Single date. Once approved it counts as 0.5 day; the other half follows attendance.</div>}
          <Field label="Reason"><textarea className="input" rows={3} value={reason} onChange={e => setReason(e.target.value)} /></Field>
          <button className="btn primary block" onClick={apply} disabled={busy || !s1 || (!half && (!s2 || s2 < s1))}><Send />{busy ? 'Submitting…' : half ? 'Request half-day leave' : 'Apply for leave'}</button>
        </Card>
        <Card title="My balances" sub="this year" className="rise" style={{ '--i': 1 }}>
          {bal.loading && !balances.length ? <Skeleton h={160} /> : <div className="col" style={{ gap: 14 }}>
            {balances.map(b => { const used = Number(b.used || 0), al = Number(b.allowance || 0); return (
              <div key={b.type}>
                <div className="row" style={{ marginBottom: 6 }}><b className="grow">{b.type}</b>
                  <span className="num">{b.remaining != null ? <><b>{b.remaining}</b> <span className="faint">left</span></> : <span className="faint">no limit</span>}</span></div>
                {al > 0 && <Bar pct={(used / al) * 100} tone={b.remaining === 0 ? 'bad' : 'accent'} h={7} />}
                <div className="faint" style={{ fontSize: 11.5, marginTop: 4 }}>{used} used{b.pending ? ` · ${b.pending} pending` : ''}{al ? ` · ${al} a year` : ''}</div>
              </div>); })}
          </div>}
        </Card>
      </div>

      <Card title="My requests" pad={false} className="rise" style={{ marginBottom: 16 }}>
        {!(mine.data || []).length ? <Empty icon={CalendarDays} title="No leave requests yet" /> :
          <div className="table-wrap"><table className="t">
            <thead><tr><th>Type</th><th>Dates</th><th>Days</th><th>Status</th><th>Reason</th></tr></thead>
            <tbody>{mine.data.map(l => <tr key={l.id}><td><Pill tone="accent">{l.leave_type}</Pill></td><td className="muted">{l.start_date} → {l.end_date}</td>
              <td className="num">{dur(l)}</td><td><StatusCell l={l} /></td><td className="muted">{l.reason || '—'}</td></tr>)}</tbody></table></div>}
      </Card>

      {isMgr && <Card title={`Leave history — all employees · ${histRows.length}`} pad={false} className="rise" style={{ marginBottom: 16 }}>
        <div className="card-tools">
          <Chips value={hf.status} onChange={v => setHf(s => ({ ...s, status: v }))} options={[['all', 'All'], ['pending', 'Pending'], ['approved', 'Approved'], ['rejected', 'Rejected']]} />
          <Chips value={hf.type} onChange={v => setHf(s => ({ ...s, type: v }))} options={[['all', 'All types'], ...TYPES.map(t => [t, t])]} />
          <Chips value={hf.role} onChange={v => setHf(s => ({ ...s, role: v }))} label="Role" options={ROLES} />
          <div className="row wrap" style={{ gap: 8 }}>
            <input className="input" type="date" value={hf.from} onChange={e => setHf(s => ({ ...s, from: e.target.value }))} title="From" />
            <span className="faint">→</span>
            <input className="input" type="date" value={hf.to} onChange={e => setHf(s => ({ ...s, to: e.target.value }))} title="To" />
            <SearchBox value={hf.q} onChange={v => setHf(s => ({ ...s, q: v }))} placeholder="Name, branch, type, reason…" width={260} />
            {(hf.status !== 'all' || hf.type !== 'all' || hf.role !== 'all' || hf.from || hf.to || hf.q) &&
              <button className="btn sm ghost" onClick={() => setHf({ status: 'all', type: 'all', role: 'all', from: '', to: '', q: '' })}><X />Clear</button>}
          </div>
        </div>
        {!histRows.length ? <Empty title="No leave records match" /> :
          <div className="table-wrap" style={{ maxHeight: 520 }}><table className="t">
            <thead><tr><th>Who</th><th>Role</th><th>Type</th><th>Dates</th><th>Days</th><th>Status</th><th>Approver</th><th>Reason</th></tr></thead>
            <tbody>{grouped.map(([ym, rows]) => <React.Fragment key={ym}>
              <tr className="grp-row"><td colSpan={8}>{monthL(ym)} · {rows.length} request{rows.length === 1 ? '' : 's'} · {rows.reduce((a, l) => a + days(l), 0)} days</td></tr>
              {rows.map(l => <tr key={l.id}>
                <td><div className="cell-main">{l.user_name}</div><div className="cell-sub">{l.user_branch || '—'}</div></td>
                <td className="muted">{roleL(l.user_role)}</td><td>{l.leave_type}</td>
                <td className="muted" style={{ whiteSpace: 'nowrap' }}>{l.start_date} → {l.end_date}</td><td className="num">{dur(l)}</td>
                <td><StatusCell l={l} /></td><td className="muted">{l.approver_name || '—'}</td><td className="muted">{l.reason || '—'}</td>
              </tr>)}
            </React.Fragment>)}</tbody></table></div>}
      </Card>}

      {isMgr && <Card title={`Per-employee balance${bals.data && bals.data.year ? ' · ' + bals.data.year : ''}`} pad={false} className="rise">
        <div className="card-tools">
          <Chips value={balRole} onChange={setBalRole} label="Role" options={ROLES} />
          <div className="row" style={{ gap: 8 }}><SearchBox value={balQ} onChange={setBalQ} onEnter={() => setBalQd(balQ.trim())} placeholder="Name / employee code — Enter" width={300} /></div>
        </div>
        {!((bals.data && bals.data.rows) || []).length ? <Empty title="No employees match" /> :
          <div className="table-wrap" style={{ maxHeight: 520 }}><table className="t">
            <thead><tr><th>Employee</th><th>Role</th><th>Branch</th>{TYPES.filter(t => t !== 'Unpaid').map(t => <th key={t} className="r">{t}</th>)}<th className="r">Taken</th><th className="r">Remaining</th></tr></thead>
            <tbody>{bals.data.rows.map(r => <tr key={r.user_id}>
              <td><div className="cell-main">{r.name}</div>{r.emp_code && <div className="cell-sub mono">{r.emp_code}</div>}</td>
              <td className="muted">{roleL(r.role)}</td><td className="muted">{r.branch || '—'}</td>
              {TYPES.filter(t => t !== 'Unpaid').map(t => { const b = r.types.find(x => x.type === t) || {}; return <td key={t} className="r num">{b.remaining != null ? b.remaining : '—'}<span className="faint">/{b.allowance}</span></td>; })}
              <td className="r"><b>{r.total_taken}</b>{r.total_pending ? <span className="faint"> (+{r.total_pending}p)</span> : ''}</td>
              <td className="r" style={{ color: 'var(--good)' }}><b>{r.total_remaining}</b></td>
            </tr>)}</tbody></table></div>}
      </Card>}

      {decide && <Decide leave={decide.l} mode={decide.mode} onClose={() => setDecide(null)} onDone={() => { setDecide(null); reloadAll(); }} />}
    </>
  );
}

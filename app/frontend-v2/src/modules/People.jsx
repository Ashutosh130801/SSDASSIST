// People & HR: Manpower directory and My E-ID.
import React, { useEffect, useState } from 'react';
import { Ban, Camera, Check, Download, FileText, FolderOpen, IdCard, Pencil, Send, ShieldCheck, UserCog, UserPlus, Users, X, Lock, Crown } from 'lucide-react';
import { api, download } from '../lib/api.js';
import { useAuth } from '../lib/auth.jsx';
import { cx, fmtDate, fmtTime, initials, num, roleName } from '../lib/format.js';
import { Card, Kpi, Pill, Empty, Skeleton, useLoad, useToast } from '../components/ui.jsx';
import { ModuleHead, Chips, Modal, Field, SearchBox, Presence, usePresence, ContactBtns, useLive, useClassicUI } from './kit.jsx';
import { Trends } from './MyPerformance.jsx';

export function EIDCard({ e, presence }) {
  return (
    <div className="eid">
      <div className="eid-h"><b>SSD Enterprises</b><span>EMPLOYEE ID</span></div>
      <div className="eid-b">
        <div className="eid-ph">{e.photo_url ? <img src={e.photo_url} alt="" /> : <span>{initials(e.name)}</span>}</div>
        <div className="grow" style={{ minWidth: 0 }}>
          <div className="eid-n">{e.name}</div>
          <div className="muted" style={{ fontSize: 13 }}>{e.designation || roleName(e.role)}</div>
          {presence && <Presence p={presence} />}
          <div style={{ marginTop: 6, fontSize: 13 }}><b className="mono">{e.all_ids || e.emp_code || '—'}</b> · {e.all_roles || roleName(e.role)}</div>
          <div className="cell-sub">{[e.location, e.branch].filter(Boolean).join(' · ')}</div>
          <div className="cell-sub">{e.phone}{e.blood_group ? ' · Blood ' + e.blood_group : ''}</div>
        </div>
      </div>
    </div>
  );
}

const KV = ({ rows }) => <dl className="kv">{rows.map(([k, v]) => <React.Fragment key={k}><dt>{k}</dt><dd>{v || '—'}</dd></React.Fragment>)}</dl>;
const dt = (t) => (t ? `${fmtDate(t)} ${fmtTime(t)}` : '');

/* ─────────── Manpower ─────────── */
export function Manpower() {
  const { user } = useAuth();
  const toast = useToast();
  const ui = useClassicUI();
  const canAdd = ['admin', 'headoffice', 'hr'].includes(user.role);
  const [f, setF] = useState({ role: '', location: '', q: '' }); const [qd, setQd] = useState('');
  const [statusF, setStatusF] = useState('all');
  const [sel, setSel] = useState(null);
  useEffect(() => { const t = setTimeout(() => setQd(f.q), 250); return () => clearTimeout(t); }, [f.q]);
  const { data: opts } = useLoad(() => api('/api/manpower/filters').catch(() => ({ roles: [], locations: [] })), []);
  const { data, loading, reload } = useLoad(() => { const p = new URLSearchParams(); if (f.role) p.set('role', f.role); if (f.location) p.set('location', f.location); if (qd) p.set('q', qd); return api('/api/manpower?' + p).catch(() => []); }, [f.role, f.location, qd]);
  useLive(reload);
  const rows = Array.isArray(data) ? data : [];
  const shown = rows.filter(e => (statusF === 'all' ? true : statusF === 'blocked' ? e.is_active === false : e.is_active !== false));
  const blocked = rows.filter(e => e.is_active === false).length;
  const pres = usePresence(shown.slice(0, 200).map(e => e.id));
  const o = opts || { roles: [], locations: [] };
  const dl = () => { const p = new URLSearchParams(); if (f.role) p.set('role', f.role); if (f.location) p.set('location', f.location); download('/api/manpower/download?' + p, 'SSDE_manpower.xlsx'); };
  const block = (e) => {
    const reason = window.prompt(`Block / remove ${e.name}?\n\nThey will be signed out everywhere, unable to log in, and hidden from all active pickers. Their previous cases, allocations and performance history stay intact — this is reversible.\n\nReason (e.g. left organisation, on hold):`, e.blocked_reason || 'Left organisation');
    if (reason === null) return;
    api('/api/manpower/' + e.id, { method: 'PATCH', body: { is_active: false, block_reason: reason } }).then(() => { toast(e.name + ' blocked — their data is kept safe.'); setSel(null); reload(); }).catch(err => toast(err.message, 'err'));
  };
  const unblock = (e) => api('/api/manpower/' + e.id, { method: 'PATCH', body: { is_active: true } }).then(() => { toast(e.name + ' restored — they can log in again.'); setSel(null); reload(); }).catch(err => toast(err.message, 'err'));
  const hoMgr = (e) => { const make = !e.ho_manager;
    api('/api/manpower/' + e.id + '/ho-manager', { method: 'POST', body: { value: make } }).then(() => { toast(make ? e.name + ' is now Head Office Manager.' : 'Head Office Manager title removed.'); setSel(s => (s ? { ...s, ho_manager: make } : s)); reload(); }).catch(err => toast(err.message, 'err')); };
  const extra = (e) => [e.also_team_lead && e.role !== 'teamlead' && '+TL', e.also_field_agent && e.role !== 'fos' && '+FOS', e.also_caller && e.role !== 'telecaller' && '+Caller'].filter(Boolean);
  const set = (k, v) => setF(s => ({ ...s, [k]: v }));

  return (
    <>
      <ModuleHead icon={UserCog} title="Manpower" sub={`${num(shown.length)} employee${shown.length === 1 ? '' : 's'}${statusF !== 'all' ? ' · ' + statusF : ''}`}>
        {canAdd && <button className="btn" onClick={() => ui.modal('StaffFormModal', { roles: o.roles, isAdmin: user.role === 'admin' }).then(ok => ok && reload())}><UserPlus />Add staff</button>}
        <button className="btn primary" onClick={dl}><Download />Download Excel</button>
      </ModuleHead>
      <div className="grid g-kpi" style={{ marginBottom: 16 }}>
        <Kpi icon={Users} label="Employees" i={1} value={num(rows.length)} />
        <Kpi icon={ShieldCheck} label="Active" i={2} value={num(rows.length - blocked)} tone="good" />
        <Kpi icon={Ban} label="Blocked" i={3} value={num(blocked)} tone="bad" />
        <Kpi icon={UserCog} label="Online now" i={4} value={num(Object.values(pres).filter(p => p && p.state === 'active').length)} tone="info" />
      </div>
      <div className="card toolbar-card rise"><div className="row wrap" style={{ gap: 8 }}>
        <SearchBox value={f.q} onChange={v => set('q', v)} placeholder="Name, code, phone, designation…" width={280} />
        <select className="select" value={f.role} onChange={e => set('role', e.target.value)}><option value="">All roles</option>{o.roles.map(r => <option key={r} value={r}>{roleName(r)}</option>)}</select>
        <select className="select" value={f.location} onChange={e => set('location', e.target.value)}><option value="">All locations</option>{o.locations.map(l => <option key={l}>{l}</option>)}</select>
        <Chips value={statusF} onChange={setStatusF} options={[['all', 'All'], ['active', 'Active'], ['blocked', 'Blocked', blocked || null]]} />
      </div></div>
      <Card pad={false} className="rise">
        {loading && !rows.length ? <div style={{ padding: 16 }}><Skeleton h={240} /></div> : !shown.length ? <Empty icon={Users} title={statusF === 'blocked' ? 'No blocked employees' : 'No employees match'} /> :
          <div className="table-wrap" style={{ maxHeight: 'calc(100vh - 380px)' }}><table className="t">
            <thead><tr><th>Employee</th><th>Role</th><th>Designation</th><th>Location</th><th>Branch</th><th>Phone</th><th>Joined</th><th></th></tr></thead>
            <tbody>{shown.map(e => <tr key={e.id} className={cx('click', e.is_active === false && 'flag-row')} onClick={() => setSel(e)}>
              <td><div className="row" style={{ gap: 10 }}><span className="av" style={{ width: 34, height: 34, fontSize: 12 }}>{e.photo_url ? <img src={e.photo_url} alt="" className="av-img" /> : initials(e.name)}</span><div>
                <div className="cell-main">{e.name}{e.is_active === false && <Pill tone="bad">Blocked</Pill>}</div>
                <div className="cell-sub mono">{e.emp_code || '—'}{e.also_team_lead && e.tl_emp_code ? ' / ' + e.tl_emp_code : ''}{e.also_field_agent && e.fos_emp_code ? ' / ' + e.fos_emp_code : ''}{e.also_caller && e.tc_emp_code ? ' / ' + e.tc_emp_code : ''}</div>
                <Presence p={pres[String(e.id)]} /></div></div></td>
              <td><Pill tone="accent">{roleName(e.role)}</Pill>{extra(e).map(x => <Pill key={x} tone="info">{x}</Pill>)}</td>
              <td className="muted">{e.designation || '—'}</td><td>{e.location || '—'}</td><td className="muted">{e.branch || '—'}</td>
              <td className="mono">{e.phone || '—'}</td><td className="faint">{e.joining_date || '—'}</td>
              <td onClick={ev => ev.stopPropagation()}><ContactBtns phone={e.phone} compact /></td>
            </tr>)}</tbody></table></div>}
      </Card>

      {sel && <Modal open onClose={() => setSel(null)} width={640} title={sel.name} sub={[roleName(sel.role), sel.designation].filter(Boolean).join(' · ')}
        footer={canAdd && <>
          <button className="btn" onClick={() => ui.modal('LetterModal', { emp: sel, kind: 'offer' })}><FileText />Offer letter</button>
          <button className="btn" onClick={() => ui.modal('LetterModal', { emp: sel, kind: 'agreement' })}><FileText />Agreement letter</button>
          <div className="grow" />
          {sel.id !== user.id && (sel.is_active === false ? <button className="btn" style={{ color: 'var(--good)' }} onClick={() => unblock(sel)}><Check />Unblock / Restore</button>
            : <button className="btn ghost danger" onClick={() => block(sel)}><Ban />Block / Remove</button>)}</>}>
        <div className="row wrap" style={{ gap: 8, marginBottom: 12 }}>
          {canAdd && <button className="btn sm" onClick={() => ui.modal('StaffFormModal', { existing: sel, roles: o.roles, isAdmin: user.role === 'admin' }).then(ok => { if (ok) { setSel(null); reload(); } })}><Pencil />Edit</button>}
          {canAdd && <button className="btn sm" onClick={() => ui.inline('EmployeeDocs', { emp: sel }, 'Documents — ' + sel.name, 820)}><FolderOpen />Documents</button>}
          <ContactBtns phone={sel.phone} />
        </div>
        <EIDCard e={sel} presence={pres[String(sel.id)]} />
        {sel.is_active === false && <div className="card note-card" style={{ marginTop: 12, borderLeftColor: 'var(--bad)' }}><Ban style={{ color: 'var(--bad)' }} /><div><b style={{ color: 'var(--bad)' }}>Blocked — cannot log in.</b> {sel.blocked_reason ? 'Reason: ' + sel.blocked_reason : 'No reason recorded'}{sel.blocked_at ? ' · ' + dt(sel.blocked_at) : ''}. Past cases & performance are preserved.</div></div>}
        <div style={{ marginTop: 12 }}><KV rows={[['Emp code(s)', sel.all_ids || sel.emp_code], ['HR ref', sel.hr_ref], ['Role(s)', sel.all_roles || roleName(sel.role)], ['Designation', sel.designation],
          ['Location', sel.location], ['Branch', sel.branch], ['Email', sel.email], ['Phone', sel.phone], ['Gender', sel.gender], ['DOB', sel.dob], ['Blood group', sel.blood_group], ['Marital', sel.marital_status],
          ['Emergency', (sel.emergency_name || '') + (sel.emergency_contact ? ' · ' + sel.emergency_contact : '')], ['Aadhaar', sel.aadhar_number], ['PAN', sel.pan_number], ['Bank', sel.bank_name],
          ['Account', sel.bank_account], ['IFSC', sel.ifsc_code], ['Current address', sel.current_address]]} /></div>
        {user.role === 'admin' && sel.role === 'headoffice' && <div className="card note-card" style={{ marginTop: 12 }}><Crown /><div className="grow"><b>Head Office Manager</b><div className="faint" style={{ fontSize: 12 }}>Same access as Head Office, titled “Head Office Manager”, no attendance login-window limit. Admin only.</div></div>
          <button className={cx('btn sm', !sel.ho_manager && 'primary')} onClick={() => hoMgr(sel)}>{sel.ho_manager ? 'Remove title' : 'Make HO Manager'}</button></div>}
      </Modal>}
    </>
  );
}

/* ─────────── My E-ID ─────────── */
const PROFILE_FIELDS = [['phone', 'Phone', 'text'], ['gender', 'Gender', 'text'], ['dob', 'Date of birth', 'date'], ['blood_group', 'Blood group', 'text'], ['marital_status', 'Marital status', 'text'],
  ['emergency_contact', 'Emergency contact no.', 'text'], ['emergency_name', 'Emergency contact name', 'text'], ['emergency_relation', 'Relation', 'text'], ['current_address', 'Current address', 'text'],
  ['aadhar_number', 'Aadhaar number', 'text'], ['pan_number', 'PAN', 'text'], ['bank_holder', 'Bank a/c holder', 'text'], ['bank_account', 'Bank account no.', 'text'], ['ifsc_code', 'IFSC', 'text'], ['bank_name', 'Bank name', 'text']];
const TONE = { approved: 'good', rejected: 'bad', pending: 'warn' };

export function Profile() {
  const { user } = useAuth();
  const toast = useToast();
  const isHR = ['admin', 'headoffice', 'hr'].includes(user.role);
  const showTrends = ['fos', 'telecaller', 'teamlead'].includes(user.role);
  const { data: me, reload } = useLoad(() => api('/api/manpower/me').catch(() => ({})), []);
  const { data: tr } = useLoad(() => (showTrends ? api('/api/mis/employee-trends?user_id=' + user.id).catch(() => null) : Promise.resolve(null)), []);
  const [f, setF] = useState({}); const [editing, setEditing] = useState(false); const [busy, setBusy] = useState(false); const [photoBusy, setPhotoBusy] = useState(false);
  const [cr, setCr] = useState({ field: '', value: '', note: '' }); const [crOpen, setCrOpen] = useState(false);
  useEffect(() => { if (me) setF(me); }, [me]);
  const locked = me && me.profile_completed && !isHR;
  const canEdit = me && (!me.profile_completed || isHR);
  const { data: crFields } = useLoad(() => (locked ? api('/api/manpower/me/change-fields').catch(() => []) : Promise.resolve([])), [locked]);
  const reqs = useLoad(() => (locked ? api('/api/manpower/me/change-requests').catch(() => []) : Promise.resolve([])), [locked]);
  const crField = (crFields || []).find(x => x.field === cr.field);
  const photo = async (file) => {
    if (!file) return; if (!/^image\//.test(file.type || '')) { toast('Please choose an image file', 'err'); return; }
    setPhotoBusy(true); try { const fd = new FormData(); fd.append('file', file); await api('/api/manpower/me/photo', { method: 'POST', form: fd }); toast('Profile photo updated.'); reload(); } catch (e) { toast(e.message, 'err'); } finally { setPhotoBusy(false); }
  };
  const save = async () => { setBusy(true); try { const body = {}; PROFILE_FIELDS.forEach(([k]) => { if (f[k] !== undefined && f[k] !== null) body[k] = f[k]; });
    await api('/api/manpower/me', { method: 'PATCH', body }); toast(isHR ? 'Profile saved.' : 'Profile completed — thank you! Contact HR for further changes.'); setEditing(false); reload();
  } catch (e) { toast(e.message, 'err'); } finally { setBusy(false); } };
  const submit = async () => {
    if (!cr.field || !String(cr.value).trim()) { toast('Pick a field and enter the new value.', 'err'); return; }
    setBusy(true); try { await api('/api/manpower/me/change-request', { method: 'POST', body: cr }); toast('Request sent to HR/Admin for approval.'); setCr({ field: '', value: '', note: '' }); setCrOpen(false); reqs.reload(); } catch (e) { toast(e.message, 'err'); } finally { setBusy(false); }
  };
  if (!me) return <><ModuleHead icon={IdCard} title="My E-ID" /><Skeleton h={300} /></>;
  const noHr = !(me.phone || me.designation || me.location || me.dob || me.blood_group || me.aadhar_number);
  return (
    <>
      <ModuleHead icon={IdCard} title="My E-ID" sub="Your employee card and profile" />
      {showTrends && tr && tr.trends && <Card title="My achievement — cash collected" className="rise" style={{ marginBottom: 16 }}><Trends trends={tr.trends} /></Card>}
      {noHr && isHR && <div className="card note-card rise" style={{ marginBottom: 16 }}><IdCard /><div><b>This is a system/admin login — it has no personal HR record.</b> Every employee’s details are on the Manpower page.</div></div>}
      <div className="eid-layout">
        <div className="col" style={{ gap: 10 }}>
          <EIDCard e={{ ...me, ...f }} />
          <label className="btn sm" style={{ alignSelf: 'flex-start', cursor: photoBusy ? 'default' : 'pointer' }}><Camera />{photoBusy ? 'Uploading…' : 'Change photo'}
            <input type="file" accept="image/*" hidden disabled={photoBusy} onChange={e => { photo(e.target.files[0]); e.target.value = ''; }} /></label>
        </div>
        <Card className="rise" title={editing ? 'Edit profile' : 'Profile'} actions={!editing && canEdit && <button className="btn sm primary" onClick={() => setEditing(true)}><Pencil />{me.profile_completed ? 'Edit profile' : 'Complete my profile (one-time)'}</button>}>
          {!editing ? <>
            <KV rows={[['Employee code', me.emp_code], ['Role', roleName(me.role)], ['Designation', me.designation], ['Location', me.location], ['Branch', me.branch], ['Email', me.email], ['Phone', me.phone], ['DOB', me.dob], ['Blood group', me.blood_group], ['Joined', me.joining_date]]} />
            {!me.profile_completed && !isHR && <div className="faint" style={{ fontSize: 12, marginTop: 10 }}>You can complete your profile once. After saving, request any further change for HR/Admin approval.</div>}
          </> : <>
            <div className="form-g">{PROFILE_FIELDS.map(([k, l, t]) => <Field key={k} label={l}><input className="input" type={t} value={t === 'date' ? String(f[k] || '').slice(0, 10) : (f[k] || '')} onChange={e => setF(s => ({ ...s, [k]: e.target.value }))} /></Field>)}</div>
            <div className="row"><button className="btn" onClick={() => { setEditing(false); setF(me); }}>Cancel</button><div className="grow" /><button className="btn primary" disabled={busy} onClick={save}>{busy ? 'Saving…' : me.profile_completed ? 'Save' : 'Save & complete'}</button></div>
          </>}
        </Card>
      </div>
      {locked && <Card className="rise" style={{ marginTop: 16 }} title={<span className="row" style={{ gap: 8 }}><Lock size={16} />Your profile is locked</span>} sub="Need a correction? Request a change — HR/Admin will review and apply it."
        actions={<button className="btn sm primary" onClick={() => setCrOpen(o => !o)}>{crOpen ? 'Close' : 'Request a change'}</button>}>
        {crOpen && <div style={{ marginBottom: 14 }}>
          <div className="form-g">
            <Field label="Field to change"><select className="select" value={cr.field} onChange={e => setCr(s => ({ ...s, field: e.target.value, value: '' }))}><option value="">Choose a field…</option>{(crFields || []).map(x => <option key={x.field} value={x.field}>{x.label}</option>)}</select></Field>
            <Field label="New value" hint={crField ? 'Current: ' + (crField.current || '—') : ''}><input className="input" type={['dob', 'joining_date'].includes(cr.field) ? 'date' : 'text'} value={cr.value} onChange={e => setCr(s => ({ ...s, value: e.target.value }))} /></Field>
          </div>
          <Field label="Reason (optional)"><input className="input" maxLength={300} value={cr.note} onChange={e => setCr(s => ({ ...s, note: e.target.value }))} /></Field>
          <button className="btn primary" disabled={busy} onClick={submit}><Send />{busy ? 'Sending…' : 'Submit request'}</button>
        </div>}
        {(reqs.data || []).length > 0 && <div className="table-wrap"><table className="t">
          <thead><tr><th>Field</th><th>Requested value</th><th>Status</th><th>Reviewed by</th></tr></thead>
          <tbody>{reqs.data.map(r => <tr key={r.id}><td>{r.field_label}</td><td className="muted">{r.old_value ? <>{r.old_value} → <b>{r.new_value}</b></> : <b>{r.new_value}</b>}</td>
            <td><Pill tone={TONE[r.status] || 'neutral'} dot>{r.status}</Pill>{r.review_note && <div className="cell-sub">{r.review_note}</div>}</td><td className="muted">{r.reviewer_name || '—'}</td></tr>)}</tbody></table></div>}
      </Card>}
    </>
  );
}
export { X };

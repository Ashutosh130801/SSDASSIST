// Add-ons, phase 3 — Settlement / OTS, Smart allocation & route, Legal notices (native, same APIs as classic).
import React, { useEffect, useState } from 'react';
import { ArrowLeft, CheckCircle2, Download, FileText, Map as MapIcon, Plus, Search, Send, Sparkles, Trash2, Upload, X, Eye, Wand2, Gauge } from 'lucide-react';
import { api, download } from '../lib/api.js';
import { cx, fmtDate } from '../lib/format.js';
import { Card, Pill, useToast } from '../components/ui.jsx';
import { Modal, Field, useClassicUI } from './kit.jsx';
import { AdState, AdTabs, AdTable, AdStats, AdNote, useAd, usePrompt, useConfirm, useErr, INR } from './AddonKit.jsx';

const searchCases = (q) => api('/api/cases?search=' + encodeURIComponent(q) + '&limit=20').then(r => (Array.isArray(r) ? r : (r.items || r.cases || [])));

/* ═════════════════════════════ 🤝 Settlement / OTS ═════════════════════════════ */
const OTS_TONE = { pending: 'warn', approved: 'info', accepted: 'info', completed: 'good', rejected: 'bad', cancelled: 'neutral' };
export function AddonSettlement() {
  const toast = useToast(); const err = useErr(); const [ask, askEl] = usePrompt(); const [confirm, confirmEl] = useConfirm();
  const [st, setSt] = useState('');
  const q = useAd(() => api('/api/settlements' + (st ? '?status=' + st : '')), [st]);
  const lim = useAd(() => api('/api/settlements/limits'));
  const [nw, setNw] = useState(null);
  const decide = async (o, approve) => { const note = await ask(approve ? 'Approve this offer' : 'Reject this offer', { label: approve ? 'Approval note (optional)' : 'Reason for rejecting', multiline: true, ok: approve ? 'Approve' : 'Reject', danger: !approve });
    if (note === null) return; api(`/api/settlements/${o.id}/decide`, { method: 'POST', body: { approve, note } }).then(q.reload).catch(err); };
  const setS = (o, body) => api(`/api/settlements/${o.id}/status`, { method: 'POST', body }).then(q.reload).catch(err);
  const cancel = async (o) => { if (await confirm('Cancel this offer?', `${o.customer} · ${INR(o.offer_amount)}`, { danger: true, ok: 'Cancel offer' })) setS(o, { status: 'cancelled' }); };
  const submit = () => api('/api/settlements', { method: 'POST', body: { case_id: nw.pick.id, offer_amount: nw.offer, due: nw.due || null, reason: nw.reason, installments: nw.inst } })
    .then(r => { toast(r.status === 'approved' ? 'Approved' : `Sent for ${r.needs_role} approval`); setNw(null); q.reload(); }).catch(err);
  const L = lim.data;
  const waiver = nw && nw.pick && nw.offer > 0 ? (100 * (1 - nw.offer / (nw.pick.pending_amount || 1))) : null;
  return <>
    {L && <AdNote>Approval limits — caller/FOS up to <b>{L.caller}%</b> waiver · team lead up to <b>{L.teamlead}%</b> · manager/HO up to <b>{L.manager}%</b> · above that Admin.</AdNote>}
    <div className="row wrap ad-bar">
      <div className="chips">{['', 'pending', 'approved', 'accepted', 'completed', 'rejected'].map(s => <button key={s} className={cx('chip', st === s && 'on')} onClick={() => setSt(s)}>{s ? s[0].toUpperCase() + s.slice(1) : 'All'}</button>)}</div>
      <span className="grow" /><button className="btn primary sm" onClick={() => setNw({ q: '', res: null, pick: null, offer: '', due: '', reason: '', inst: [] })}><Plus size={14} />New offer</button></div>
    <AdState q={q}>{d => <Card pad={false} className="rise"><AdTable cols={[['created_at', 'Date', fmtDate], ['customer', 'Customer', (v, r) => <><b>{v}</b><div className="faint" style={{ fontSize: 11.5 }}>{r.bank} · {r.account_no}</div></>],
      ['outstanding', 'Outstanding', INR, { num: 1 }], ['offer_amount', 'Offer', INR, { num: 1 }], ['waiver_pct', 'Waiver', v => <b>{v}%</b>, { num: 1 }],
      ['status', 'Status', (v, r) => <><Pill tone={OTS_TONE[v]} dot>{v}</Pill>{v === 'pending' && <div className="faint" style={{ fontSize: 11 }}>needs {r.needs_role}</div>}</>],
      ['installments', 'Instalments', (v, r) => (v || []).length ? (v || []).map((x, i) => <label key={i} className="ad-inst">
        <input type="checkbox" checked={!!x.paid} disabled={!['approved', 'accepted'].includes(r.status)} onChange={e => setS(r, { paid_index: i, paid: e.target.checked })} />{fmtDate(x.due)} · {INR(x.amount)}</label>) : <span className="faint">—</span>],
      ['created_by', 'By'], ['id', '', (v, r) => <div className="row wrap" style={{ gap: 4 }}>
        {r.can_decide && <><button className="btn sm primary" onClick={() => decide(r, true)}>Approve</button><button className="btn ghost sm" onClick={() => decide(r, false)}>Reject</button></>}
        {r.status === 'approved' && <button className="btn sm" onClick={() => setS(r, { status: 'accepted' })}>Customer agreed</button>}
        {['approved', 'accepted', 'completed'].includes(r.status) && <button className="icon-btn" title="Settlement letter (PDF)" onClick={() => download(`/api/settlements/${v}/letter.pdf`, `OTS_${v}.pdf`)}><FileText /></button>}
        {['pending', 'approved', 'accepted'].includes(r.status) && <button className="icon-btn" title="Cancel offer" onClick={() => cancel(r)}><X /></button>}</div>]]} rows={d} empty="No settlement offers here." /></Card>}</AdState>
    <Modal open={!!nw} onClose={() => setNw(null)} title="New settlement offer" sub={nw && nw.pick ? `${nw.pick.customer_name} · outstanding ${INR(nw.pick.pending_amount)}` : 'Find the account first'} width={620}
      footer={nw && nw.pick ? <><button className="btn ghost" onClick={() => setNw({ ...nw, pick: null })}><ArrowLeft size={15} />Change account</button><span className="grow" />
        <button className="btn ghost" onClick={() => setNw(null)}>Cancel</button><button className="btn primary" onClick={submit}><Send size={15} />Submit</button></> : null}>
      {nw && (!nw.pick ? <>
        <div className="row" style={{ gap: 8 }}>
          <div className="ad-search grow"><Search size={15} /><input autoFocus placeholder="Customer, account no. or phone" value={nw.q} onChange={e => setNw({ ...nw, q: e.target.value })}
            onKeyDown={e => e.key === 'Enter' && searchCases(nw.q).then(r => setNw(n => ({ ...n, res: r }))).catch(err)} /></div>
          <button className="btn primary" onClick={() => searchCases(nw.q).then(r => setNw(n => ({ ...n, res: r }))).catch(err)}>Search</button></div>
        {nw.res && !nw.res.length && <div className="faint" style={{ marginTop: 10 }}>No accounts match.</div>}
        {nw.res && nw.res.length > 0 && <div className="ad-pick">{nw.res.map(c => <button key={c.id} className="ad-pick-row" onClick={() => setNw({ ...nw, pick: c })}>
          <b>{c.customer_name}</b><span>{c.bank} · {c.account_no}</span><span className="num">Pending {INR(c.pending_amount)}</span></button>)}</div>}
      </> : <div className="col" style={{ gap: 10 }}>
        <div className="form-grid" style={{ marginBottom: 0 }}>
          <Field label="Offer amount" hint={waiver != null ? `Waiver ${waiver.toFixed(1)}%` : 'What the customer will pay in full settlement'}><input className="input" type="number" autoFocus value={nw.offer} onChange={e => setNw({ ...nw, offer: e.target.value })} /></Field>
          {!nw.inst.length && <Field label="Pay by"><input className="input" type="date" value={nw.due} onChange={e => setNw({ ...nw, due: e.target.value })} /></Field>}
        </div>
        {nw.inst.length > 0 && <div className="faint" style={{ fontSize: 12, fontWeight: 600 }}>Instalments</div>}
        {nw.inst.map((x, i) => <div key={i} className="row" style={{ gap: 6 }}>
          <span className="ad-step-n">{i + 1}</span>
          <input className="input" type="date" value={x.due} onChange={e => setNw({ ...nw, inst: nw.inst.map((y, j) => j === i ? { ...y, due: e.target.value } : y) })} />
          <input className="input" type="number" placeholder="Amount ₹" value={x.amount} onChange={e => setNw({ ...nw, inst: nw.inst.map((y, j) => j === i ? { ...y, amount: e.target.value } : y) })} />
          <button className="icon-btn" title="Remove" onClick={() => setNw({ ...nw, inst: nw.inst.filter((_, j) => j !== i) })}><Trash2 /></button></div>)}
        <button className="btn ghost sm" style={{ alignSelf: 'flex-start' }} onClick={() => setNw({ ...nw, inst: [...nw.inst, { due: '', amount: '' }] })}><Plus size={14} />Instalment</button>
        <Field label="Reason (customer's situation)"><textarea className="input" rows={3} value={nw.reason} onChange={e => setNw({ ...nw, reason: e.target.value })} /></Field>
      </div>)}
    </Modal>{askEl}{confirmEl}
  </>;
}

/* ═════════════════════════════ 🧠 Smart allocation & route ═════════════════════════════ */
export function AddonSmart({ user }) {
  const lead = ['admin', 'headoffice', 'manager', 'teamlead'].includes(user.role);
  const tabs = [['scores', 'Likelihood to pay'], ...(lead ? [['alloc', 'Smart allocation']] : []), ...(lead || user.role === 'fos' ? [['route', 'Route plan']] : [])];
  const [tab, setTab] = useState(user.role === 'fos' ? 'route' : 'scores');
  return <><AdTabs tabs={tabs} cur={tab} set={setTab} />{tab === 'scores' && <SmartScores />}{tab === 'alloc' && <SmartAlloc />}{tab === 'route' && <SmartRoute user={user} />}</>;
}
const scoreTone = (v) => (v >= 70 ? 'good' : v >= 45 ? 'warn' : 'bad');
function SmartScores() {
  const ui = useClassicUI();
  const q = useAd(() => api('/api/smart/scores'));
  const [band, setBand] = useState('');
  return <AdState q={q}>{d => { const rows = d.rows.filter(r => !band || (band === 'high' ? r.score >= 70 : band === 'medium' ? r.score >= 45 && r.score < 70 : r.score < 45));
    return <>
      <AdStats items={[['High (70+)', d.bands.high || 0, 'good'], ['Medium', d.bands.medium || 0, 'warn'], ['Low', d.bands.low || 0, 'bad']]} />
      <div className="chips">{[['', 'All'], ['high', 'High'], ['medium', 'Medium'], ['low', 'Low']].map(([k, l]) => <button key={k} className={cx('chip', band === k && 'on')} onClick={() => setBand(k)}>{l}</button>)}</div>
      <Card pad={false} className="rise"><AdTable cols={[['score', 'Score', v => <span className={cx('ad-score', 's-' + scoreTone(v))}>{v}</span>],
        ['customer', 'Customer', (v, r) => <button className="link-btn" onClick={() => ui.openCase(r.case_id)}>{v}</button>],
        ['bank', 'Bank'], ['bucket', 'Bucket'], ['pending', 'Pending', INR, { num: 1 }], ['why', 'Why', v => <span className="faint" style={{ fontSize: 12 }}>{(v || []).join(' · ')}</span>], ['best_time', 'Best time to call']]}
        rows={rows} empty="No scored cases." /></Card>
    </>; }}</AdState>;
}
function SmartAlloc() {
  const toast = useToast(); const err = useErr(); const [confirm, confirmEl] = useConfirm();
  const [kind, setKind] = useState('fos'); const [only, setOnly] = useState(true); const [pv, setPv] = useState(null); const [sel, setSel] = useState({}); const [busy, setBusy] = useState(false);
  const run = () => { setBusy(true); api('/api/smart/allocate/preview', { method: 'POST', body: { kind, only_unallocated: only } }).then(r => { setPv(r); setSel(Object.fromEntries(r.suggestions.map(s => [s.case_id, true]))); }).catch(err).finally(() => setBusy(false)); };
  const apply = async () => { const items = pv.suggestions.filter(s => sel[s.case_id]); if (!items.length) return;
    if (!await confirm(`Allocate ${items.length} case(s)?`, 'Each case goes to the suggested person. You can re-allocate later.', { ok: 'Allocate' })) return;
    api('/api/smart/allocate/apply', { method: 'POST', body: { kind, items } }).then(r => { toast(`Allocated ${r.applied}`); setPv(null); }).catch(err); };
  const nSel = pv ? pv.suggestions.filter(s => sel[s.case_id]).length : 0;
  return <>
    <Card className="rise">
      <div className="row wrap" style={{ gap: 12, alignItems: 'center' }}>
        <Seg2 value={kind} onChange={setKind} options={[['fos', 'Field (FOS)'], ['caller', 'Callers']]} />
        <label className="row" style={{ gap: 6, fontSize: 13 }}><input type="checkbox" checked={only} onChange={e => setOnly(e.target.checked)} />Only unallocated cases</label>
        <span className="grow" />
        <button className="btn primary" onClick={run} disabled={busy}><Wand2 size={15} />{busy ? 'Working…' : 'Suggest'}</button></div>
    </Card>
    {pv && <>
      <AdNote>{pv.suggestions.length} suggestions{pv.capacity ? ` (capacity ${pv.capacity} open cases each)` : ''}{pv.skipped_full ? ` · ${pv.skipped_full} left — everyone at capacity` : ''}
        {Object.keys(pv.per_user || {}).length > 0 && <> · {Object.entries(pv.per_user).map(([k, n]) => `${k}: ${n}`).join(' · ')}</>}</AdNote>
      <Card pad={false} className="rise"><AdTable cols={[['case_id', <input type="checkbox" checked={nSel === pv.suggestions.length && nSel > 0} onChange={e => setSel(Object.fromEntries(pv.suggestions.map(s => [s.case_id, e.target.checked])))} />,
        v => <input type="checkbox" checked={!!sel[v]} onChange={e => setSel({ ...sel, [v]: e.target.checked })} />], ['customer', 'Customer'], ['pending', 'Pending', INR, { num: 1 }], ['user', 'Suggested', v => <b>{v}</b>], ['why', 'Why', v => <span className="faint" style={{ fontSize: 12 }}>{v}</span>]]}
        rows={pv.suggestions} empty="Nothing to allocate." /></Card>
      {pv.suggestions.length > 0 && <button className="btn primary" style={{ alignSelf: 'flex-start' }} disabled={!nSel} onClick={apply}><CheckCircle2 size={15} />Allocate {nSel} selected</button>}
    </>}{confirmEl}
  </>;
}
function Seg2({ value, onChange, options }) {
  return <div className="seg">{options.map(([v, l]) => <button key={v} className={cx(value === v && 'on')} onClick={() => onChange(v)}>{l}</button>)}</div>;
}
function SmartRoute({ user }) {
  const err = useErr(); const ui = useClassicUI();
  const [fos, setFos] = useState(''); const [list, setList] = useState([]); const [d, setD] = useState(null); const [busy, setBusy] = useState(false);
  const load = (id) => { setBusy(true); api('/api/smart/route' + (id ? '?fos_id=' + id : '')).then(setD).catch(err).finally(() => setBusy(false)); };
  useEffect(() => { if (user.role !== 'fos') api('/api/users?role=fos').then(r => setList(Array.isArray(r) ? r : [])).catch(() => {}); else load(); }, []);
  return <>
    {user.role !== 'fos' && <Card className="rise"><div className="row wrap" style={{ gap: 10, alignItems: 'center' }}>
      <MapIcon size={18} /><b>Plan today's route for</b>
      <select className="input" style={{ maxWidth: 320 }} value={fos} onChange={e => { setFos(e.target.value); e.target.value && load(e.target.value); }}>
        <option value="">Pick a FOS…</option>{list.map(u => <option key={u.id} value={u.id}>{u.name} {u.emp_code ? `(${u.emp_code})` : ''}</option>)}</select>
      {busy && <span className="faint">Planning…</span>}</div></Card>}
    {d && <>
      <AdStats items={[['Field agent', d.fos], ['Stops', d.stops.length], ['Distance', `≈${d.km} km`], ['Start', d.start]]} />
      {d.maps_url && <a className="btn primary" style={{ alignSelf: 'flex-start' }} target="_blank" rel="noreferrer" href={d.maps_url}><MapIcon size={15} />Open in Google Maps</a>}
      <Card pad={false} className="rise"><AdTable cols={[['case_id', '#', (v, r) => <span className="ad-step-n">{d.stops.indexOf(r) + 1}</span>],
        ['customer', 'Customer', (v, r) => <><button className="link-btn" onClick={() => ui.openCase(r.case_id)}>{v}</button>{r.ptp_due && <> <Pill tone="warn">PTP due</Pill></>}</>],
        ['address', 'Address', v => <span style={{ fontSize: 12.5 }}>{v}</span>], ['km_from_prev', 'km', null, { num: 1 }], ['score', 'Score', v => <span className={cx('ad-score', 's-' + scoreTone(v))}>{v}</span>], ['pending', 'Pending', INR, { num: 1 }]]}
        rows={d.stops} empty="No geotagged unpaid cases for this FOS." /></Card>
    </>}
  </>;
}

/* ═════════════════════════════ 📨 Legal notices ═════════════════════════════ */
export function AddonNotices() {
  const [tab, setTab] = useState('batches'); const [open, setOpen] = useState(null);
  return <><AdTabs tabs={[['batches', 'Batches'], ['new', 'New batch']]} cur={tab} set={t => { setTab(t); setOpen(null); }} />
    {tab === 'new' && <NoticeNew onDone={id => { setTab('batches'); setOpen(id); }} />}
    {tab === 'batches' && (open ? <NoticeBatch id={open} onBack={() => setOpen(null)} /> : <NoticeBatches onOpen={setOpen} />)}</>;
}
function NoticeBatches({ onOpen }) {
  const q = useAd(() => api('/api/notices/batches'));
  return <AdState q={q}>{d => <Card pad={false} className="rise"><AdTable cols={[['created_at', 'Date', fmtDate], ['name', 'Batch', (v, r) => <button className="link-btn" onClick={() => onOpen(r.id)}>{v}</button>], ['kind', 'Type', v => <Pill tone="info">{v}</Pill>], ['count', 'Notices', null, { num: 1 }],
    ['status', 'Status', v => Object.entries(v || {}).map(([k, n]) => `${k} ${n}`).join(' · ')], ['id', '', v => <button className="btn ghost sm" onClick={() => download(`/api/notices/batches/${v}/pdf`, `notices_${v}.pdf`)}><FileText size={14} />PDF</button>]]} rows={d} empty="No notice batches yet." /></Card>}</AdState>;
}
function NoticeNew({ onDone }) {
  const toast = useToast(); const err = useErr();
  const tq = useAd(() => api('/api/notices/templates'));
  const [f, setF] = useState({ kind: 'demand', subject: '', body: '', filters: { bank: '', product: '', bucket: '', branch: '', disposition: '' }, name: '' });
  const [pv, setPv] = useState(null);
  const tpls = tq.data;
  useEffect(() => { if (tpls && !f.body) { const t = tpls.find(x => x.kind === f.kind) || tpls[0]; t && setF(x => ({ ...x, kind: t.kind, subject: t.subject, body: t.body })); } }, [tpls]);
  const pickT = k => { const t = tpls.find(x => x.kind === k); setF({ ...f, kind: k, subject: t.subject, body: t.body }); setPv(null); };
  const body = () => ({ ...f, filters: Object.fromEntries(Object.entries(f.filters).filter(([, v]) => v)) });
  return <AdState q={tq}>{() => <Card className="rise" title="New notice batch" sub="Pick a template, narrow the cases, check, then generate">
    <div className="col" style={{ gap: 10 }}>
      <div className="form-grid" style={{ marginBottom: 0 }}>
        <Field label="Notice type"><select className="input" value={f.kind} onChange={e => pickT(e.target.value)}>{tpls.map(t => <option key={t.kind} value={t.kind}>{t.name}</option>)}</select></Field>
        <Field label="Batch name"><input className="input" value={f.name} onChange={e => setF({ ...f, name: e.target.value })} placeholder="e.g. AXIS X-BKT demand Nov" /></Field>
      </div>
      <div className="form-grid four">{Object.keys(f.filters).map(k => <Field key={k} label={k[0].toUpperCase() + k.slice(1)}>
        <input className="input" value={f.filters[k]} placeholder="Any" onChange={e => { setF({ ...f, filters: { ...f.filters, [k]: e.target.value } }); setPv(null); }} /></Field>)}</div>
      <Field label="Subject"><input className="input" value={f.subject} onChange={e => setF({ ...f, subject: e.target.value })} /></Field>
      <Field label="Notice text"><textarea className="input ad-mono" rows={10} value={f.body} onChange={e => setF({ ...f, body: e.target.value })} /></Field>
      <div className="faint" style={{ fontSize: 12 }}>Placeholders: {'{name} {address} {pincode} {bank} {account_no} {product} {outstanding} {date} {reply_days} {reply_by} {ref_no} {company} {signatory}'} · Have the wording checked by your advocate before sending.</div>
      {pv && <AdNote><b>{pv.count}</b> unpaid cases match{pv.without_address ? ` · ${pv.without_address} have no address and will be skipped` : ''}.</AdNote>}
      <div className="row" style={{ gap: 8 }}>
        <button className="btn" onClick={() => api('/api/notices/preview', { method: 'POST', body: body() }).then(setPv).catch(err)}><Eye size={15} />Check</button><span className="grow" />
        <button className="btn primary" disabled={!pv || !pv.count} onClick={() => api('/api/notices/batches', { method: 'POST', body: body() }).then(r => { toast(`${r.count} notices created`); onDone(r.id); }).catch(err)}><Sparkles size={15} />Generate notices</button></div>
    </div></Card>}</AdState>;
}
const NOTICE_TONE = { generated: 'info', dispatched: 'warn', delivered: 'good', returned: 'bad' };
function NoticeBatch({ id, onBack }) {
  const toast = useToast(); const err = useErr(); const [ask, askEl] = usePrompt();
  const q = useAd(() => api('/api/notices/batches/' + id), [id]);
  const [file, setFile] = useState(null); const [probs, setProbs] = useState(null);
  const set = async (n, status) => {
    let tracking_no = null;
    if (status === 'dispatched') { tracking_no = await ask('Mark as sent', { label: 'Tracking / article no (optional)', ok: 'Mark sent' }); if (tracking_no === null) return; }
    api(`/api/notices/${n.id}/status`, { method: 'POST', body: { status, mode: status === 'dispatched' ? 'speed_post' : undefined, tracking_no } }).then(q.reload).catch(err); };
  const up = () => { const fd = new FormData(); fd.append('file', file); api(`/api/notices/batches/${id}/tracking`, { method: 'POST', form: fd })
    .then(r => { toast(`Updated ${r.updated}` + (r.errors.length ? ` · ${r.errors.length} problems` : '')); if (r.errors.length) setProbs(r.errors); setFile(null); q.reload(); }).catch(err); };
  return <AdState q={q}>{d => <>
    <div className="row wrap ad-bar">
      <button className="btn ghost sm" onClick={onBack}><ArrowLeft size={14} />Batches</button><b style={{ fontSize: 15 }}>{d.name}</b><span className="grow" />
      <button className="btn sm" onClick={() => download(`/api/notices/batches/${id}/pdf`, `notices_${id}.pdf`)}><FileText size={14} />Print PDF</button>
      <button className="btn ghost sm" onClick={() => download(`/api/notices/tracking-template.xlsx?bid=${id}`, `notice_tracking_${id}.xlsx`)}><Download size={14} />Tracking sheet</button>
      <label className="btn ghost sm"><Upload size={14} />{file ? file.name : 'Choose tracking file'}<input type="file" hidden accept=".xlsx" onChange={e => setFile(e.target.files[0])} /></label>
      {file && <button className="btn primary sm" onClick={up}>Upload tracking</button>}</div>
    <Card pad={false} className="rise"><AdTable cols={[['ref_no', 'Ref'], ['customer', 'Customer'], ['status', 'Status', v => <Pill tone={NOTICE_TONE[v]} dot>{v}</Pill>], ['mode', 'Mode'], ['tracking_no', 'Tracking'],
      ['dispatched_at', 'Sent', fmtDate], ['delivered_at', 'Delivered / returned', fmtDate],
      ['id', '', (v, r) => <div className="row" style={{ gap: 4 }}>{r.status === 'generated' && <button className="btn sm" onClick={() => set(r, 'dispatched')}><Send size={13} />Sent</button>}
        {r.status === 'dispatched' && <><button className="btn sm" onClick={() => set(r, 'delivered')}>Delivered</button><button className="btn ghost sm" onClick={() => set(r, 'returned')}>Returned</button></>}</div>]]} rows={d.notices} empty="No notices in this batch." /></Card>
    <Modal open={!!probs} onClose={() => setProbs(null)} title="Tracking upload — problems" width={520}>{probs && <ul className="ad-probs">{probs.map((p, i) => <li key={i}>{p}</li>)}</ul>}</Modal>
    {askEl}</>}</AdState>;
}

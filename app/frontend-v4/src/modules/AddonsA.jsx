// Add-ons, phase 2 — Compliance guardrails, Payment links, Outreach journeys (native, same APIs as classic).
import React, { useEffect, useState } from 'react';
import { Award, CheckCircle2, Copy, Download, FileSpreadsheet, Link2, MessageCircle, Pause, Pencil, Play, Plus, Search, Send, ShieldCheck, Trash2, Upload, X, Mail, QrCode, Eye } from 'lucide-react';
import { api, download } from '../lib/api.js';
import { cx, fmtDate } from '../lib/format.js';
import { Card, Pill, useToast } from '../components/ui.jsx';
import { Modal, Field, waHref } from './kit.jsx';
import { useClassic } from '../lib/classic.jsx';
import { AdState, AdTabs, AdTable, AdStats, AdNote, useAd, usePrompt, useConfirm, useErr, fmtDT, INR, INR2 } from './AddonKit.jsx';

/* ═════════════════════════════ 🛡️ Compliance ═════════════════════════════ */
export function AddonCompliance({ user }) {
  const tabs = [['overview', 'Overview']];
  if (['admin', 'headoffice', 'manager', 'hr'].includes(user.role)) tabs.push(['certs', 'Certifications']);
  if (['admin', 'headoffice', 'manager'].includes(user.role)) tabs.push(['requests', 'Data requests (DPDP)']);
  if (user.role === 'admin') tabs.push(['retention', 'Retention']);
  const [tab, setTab] = useState('overview');
  return <>
    <AdTabs tabs={tabs} cur={tab} set={setTab} />
    {tab === 'overview' && <CompOverview />}{tab === 'certs' && <CompCerts />}{tab === 'requests' && <CompRequests />}{tab === 'retention' && <CompRetention />}
  </>;
}

function CompOverview() {
  const q = useAd(() => api('/api/compliance/summary'));
  return <AdState q={q}>{d => { const s = d.settings || {};
    return <>
      <AdNote>Rules: contact {s.enforce_hours ? `${s.hours_from}–${s.hours_to}` : 'any time'} · max {s.max_calls_per_day || '∞'} calls/day · max {s.max_visits_per_week || '∞'} visits/week{s.block_uncertified ? ' · certification required' : ''}.
        Dialling is blocked when a rule is broken; calls and visits logged outside the rules are flagged here.</AdNote>
      <AdStats items={[['Flags (30 days)', d.events.length, 'bad'], ['Agents certified', `${d.certs.certified}/${d.certs.agents}`, 'good'],
        ['Expiring in 30 days', d.certs.expiring_30d, 'warn'], ['Open data requests', d.open_requests], ['Overdue requests', d.overdue_requests, 'bad']]} />
      <div className="ad-2col">
        <Card title="By agent" pad={false} className="rise"><AdTable maxH={420} cols={[['agent', 'Agent'], ['violations', 'Flagged', null, { num: 1 }], ['blocked', 'Blocked dials', null, { num: 1 }]]} rows={d.by_agent} empty="No flags — all clear." /></Card>
        <Card title="Recent" pad={false} className="rise"><AdTable maxH={420} cols={[['at', 'When', fmtDT], ['agent', 'Agent'],
          ['action', 'Type', v => v === 'compliance.blocked' ? <Pill tone="bad">blocked</Pill> : <Pill tone="warn">flagged</Pill>], ['case_id', 'Case'], ['detail', 'Detail']]} rows={d.events} empty="Nothing flagged in the last 30 days." /></Card>
      </div>
    </>; }}</AdState>;
}

const CERT_TONE = { valid: 'good', expiring: 'warn', expired: 'bad', missing: 'neutral' };
function CompCerts() {
  const toast = useToast(); const err = useErr(); const [confirm, confirmEl] = useConfirm();
  const q = useAd(() => api('/api/compliance/certifications'));
  const [f, setF] = useState(null); const [term, setTerm] = useState(''); const [st, setSt] = useState('');
  const save = () => api('/api/compliance/certifications', { method: 'POST', body: f }).then(() => { toast('Saved'); setF(null); q.reload(); }).catch(err);
  const del = async (c) => { if (await confirm('Remove this certificate?', `${c.name} ${c.number || ''}`, { danger: true, ok: 'Remove' })) api('/api/compliance/certifications/' + c.id, { method: 'DELETE' }).then(q.reload).catch(err); };
  return <AdState q={q}>{d => { const t = term.trim().toLowerCase();
    const rows = d.filter(r => (!st || r.status === st) && (!t || `${r.name} ${r.emp_code} ${r.branch}`.toLowerCase().includes(t)));
    const n = k => d.filter(r => r.status === k).length;
    return <>
      <div className="row wrap ad-bar">
        <div className="chips">{[['', 'All', d.length], ['valid', 'Valid', n('valid')], ['expiring', 'Expiring', n('expiring')], ['expired', 'Expired', n('expired')], ['missing', 'Missing', n('missing')]].map(([k, l, c]) =>
          <button key={k} className={cx('chip', st === k && 'on')} onClick={() => setSt(k)}>{l}<span className="chip-n">{c}</span></button>)}</div>
        <span className="grow" />
        <div className="ad-search"><Search size={15} /><input placeholder="Search agent, ID, branch" value={term} onChange={e => setTerm(e.target.value)} /></div>
      </div>
      <Card pad={false} className="rise"><AdTable cols={[['name', 'Agent', (v, r) => <><b>{v}</b><div className="faint" style={{ fontSize: 11.5 }}>{r.emp_code} · {r.role}{r.branch ? ' · ' + r.branch : ''}</div></>],
        ['status', 'Status', v => <Pill tone={CERT_TONE[v]} dot>{v}</Pill>],
        ['certs', 'Certificates', v => (v || []).length ? (v || []).map(c => <div key={c.id} className="ad-cert"><Award size={13} />{c.name} {c.number} · till {fmtDate(c.valid_until)}
          <button className="icon-btn xs" title="Remove" onClick={() => del(c)}><X size={13} /></button></div>) : <span className="faint">—</span>],
        ['user_id', '', (v, r) => <button className="btn sm" onClick={() => setF({ user_id: v, name: 'IIBF Debt Recovery Agent', number: '', valid_until: '', who: r.name })}><Plus size={14} />Add</button>]]} rows={rows} empty="No agents match." /></Card>
      <Modal open={!!f} onClose={() => setF(null)} title="Add certificate" sub={f && f.who} width={440}
        footer={<><span className="grow" /><button className="btn ghost" onClick={() => setF(null)}>Cancel</button><button className="btn primary" onClick={save}>Save</button></>}>
        {f && <div className="form-grid one">
          <Field label="Certificate"><input className="input" value={f.name} onChange={e => setF({ ...f, name: e.target.value })} /></Field>
          <Field label="Number"><input className="input" value={f.number} onChange={e => setF({ ...f, number: e.target.value })} /></Field>
          <Field label="Valid until"><input className="input" type="date" value={f.valid_until} onChange={e => setF({ ...f, valid_until: e.target.value })} /></Field>
        </div>}
      </Modal>{confirmEl}
    </>; }}</AdState>;
}

const REQ_KIND = { access: 'Access (copy of my data)', correction: 'Correction', erasure: 'Erasure', grievance: 'Grievance' };
function CompRequests() {
  const toast = useToast(); const err = useErr(); const [ask, askEl] = usePrompt(); const [confirm, confirmEl] = useConfirm();
  const [st, setSt] = useState('open');
  const q = useAd(() => api('/api/compliance/requests?status=' + st), [st]);
  const [f, setF] = useState(null);
  const add = () => api('/api/compliance/requests', { method: 'POST', body: f }).then(() => { toast('Logged'); setF(null); q.reload(); }).catch(err);
  const close = async (r, status) => {
    const resolution = await ask(status === 'done' ? 'What was done?' : 'Why is it rejected?', { label: 'Resolution', multiline: true, ok: status === 'done' ? 'Mark done' : 'Reject' });
    if (resolution === null) return;
    let body = { status, resolution };
    if (status === 'done' && r.kind === 'erasure' && r.case_id && await confirm('Erase personal details now?', 'Also erase this customer\'s name, phones and addresses from the case. Only possible once the account is closed or paid.', { danger: true, ok: 'Continue' })) {
      const c = await ask('Confirm erasure', { must: 'ERASE', danger: true, ok: 'Erase' }); if (c === null) return; body = { ...body, erase: true, confirm: c };
    }
    api(`/api/compliance/requests/${r.id}/close`, { method: 'POST', body }).then(() => { toast('Closed'); q.reload(); }).catch(err);
  };
  const today = new Date().toISOString().slice(0, 10);
  return <>
    <div className="row wrap ad-bar">
      <div className="chips">{['open', 'done', 'rejected', 'all'].map(s => <button key={s} className={cx('chip', st === s && 'on')} onClick={() => setSt(s)}>{s[0].toUpperCase() + s.slice(1)}</button>)}</div>
      <span className="grow" /><button className="btn primary sm" onClick={() => setF({ kind: 'access', requester: '', contact: '', case_id: '', details: '', due_days: 30 })}><Plus size={14} />Log request</button>
    </div>
    <AdState q={q}>{d => <Card pad={false} className="rise"><AdTable cols={[['id', '#'], ['kind', 'Type', v => <Pill tone={v === 'erasure' ? 'bad' : v === 'grievance' ? 'warn' : 'info'}>{v}</Pill>], ['requester', 'From', (v, r) => <>{v}<div className="faint" style={{ fontSize: 11.5 }}>{r.contact}</div></>],
      ['customer', 'Case', (v, r) => r.case_id ? `#${r.case_id} ${v || ''}` : '—'], ['details', 'Details'],
      ['due_date', 'Due', (v, r) => <span style={{ color: r.status === 'open' && v && v < today ? 'var(--bad)' : undefined, fontWeight: r.status === 'open' && v && v < today ? 700 : undefined }}>{fmtDate(v)}</span>],
      ['status', 'Status', v => <Pill tone={v === 'open' ? 'warn' : v === 'done' ? 'good' : 'neutral'}>{v}</Pill>], ['resolution', 'Resolution'],
      ['id', '', (v, r) => r.status === 'open' && <div className="row" style={{ gap: 4 }}><button className="btn sm" onClick={() => close(r, 'done')}><CheckCircle2 size={14} />Done</button><button className="btn ghost sm" onClick={() => close(r, 'rejected')}>Reject</button></div>]]}
      rows={d} empty="No requests here." /></Card>}</AdState>
    <Modal open={!!f} onClose={() => setF(null)} title="Customer data request" sub="Log a DPDP request so it's answered on time" width={500}
      footer={<><span className="grow" /><button className="btn ghost" onClick={() => setF(null)}>Cancel</button><button className="btn primary" onClick={add}>Save</button></>}>
      {f && <div className="form-grid">
        <Field label="Type"><select className="input" value={f.kind} onChange={e => setF({ ...f, kind: e.target.value })}>{Object.entries(REQ_KIND).map(([k, l]) => <option key={k} value={k}>{l}</option>)}</select></Field>
        <Field label="Respond within (days)"><input className="input" type="number" value={f.due_days} onChange={e => setF({ ...f, due_days: e.target.value })} /></Field>
        <Field label="Requester name"><input className="input" value={f.requester} onChange={e => setF({ ...f, requester: e.target.value })} /></Field>
        <Field label="Contact"><input className="input" value={f.contact} onChange={e => setF({ ...f, contact: e.target.value })} /></Field>
        <Field label="Case id (optional)"><input className="input" value={f.case_id} onChange={e => setF({ ...f, case_id: e.target.value.replace(/\D/g, '') })} /></Field>
        <div className="span2"><Field label="Details"><textarea className="input" rows={3} value={f.details} onChange={e => setF({ ...f, details: e.target.value })} /></Field></div>
      </div>}
    </Modal>{askEl}{confirmEl}
  </>;
}

function CompRetention() {
  const toast = useToast(); const err = useErr(); const [ask, askEl] = usePrompt();
  const q = useAd(() => api('/api/compliance/retention'));
  const purge = async (d) => { const c = await ask('Erase personal data', { sub: `Names, phones and addresses of ${d.count} cases from before ${d.before} will be erased. Amounts and history stay for MIS.`, must: 'ERASE', danger: true, ok: 'Erase now' });
    if (c === null) return; api('/api/compliance/retention/purge', { method: 'POST', body: { confirm: c } }).then(r => { toast(`Erased ${r.erased} cases`); q.reload(); }).catch(err); };
  return <AdState q={q}>{d => !d.months
    ? <Card className="rise"><div className="row" style={{ gap: 10 }}><ShieldCheck size={20} />Retention is off. Set “Keep closed-case personal data for (months)” in Services → Compliance guardrails.</div></Card>
    : <Card className="rise" title="Data retention" sub={`Keep personal data for ${d.months} months`}>
      <AdStats items={[['Due for erasure', d.count, d.count ? 'warn' : 'good'], ['Closed before', fmtDate(d.before)]]} />
      <button className="btn danger fill" style={{ marginTop: 12 }} disabled={!d.count} onClick={() => purge(d)}><Trash2 size={15} />Erase personal data now</button>
      {askEl}</Card>}</AdState>;
}

/* ═════════════════════════════ 💳 Payment links ═════════════════════════════ */
export function AddonPayments({ user }) {
  const office = ['admin', 'headoffice', 'manager', 'backend'].includes(user.role);
  const [tab, setTab] = useState('links');
  return <>
    <AdTabs tabs={[['links', 'Payment links'], ['new', 'New link'], ...(office ? [['recon', 'Reconcile statement']] : [])]} cur={tab} set={setTab} />
    {tab === 'links' && <PayLinks />}{tab === 'new' && <PayLinkNew onDone={() => setTab('links')} />}{tab === 'recon' && <PayRecon />}
  </>;
}
const LINK_TONE = { created: 'info', paid: 'good', partial: 'warn', expired: 'neutral', cancelled: 'neutral' };
const copyText = (t, toast) => { try { navigator.clipboard.writeText(t); toast('Copied'); } catch (e) { toast('Copy failed — select the link and copy it', 'err'); } };

function QrImg({ text, size = 140 }) {
  const { api: capi } = useClassic();
  const [src, setSrc] = useState('');
  useEffect(() => { setSrc(capi && capi.qrDataUrl ? capi.qrDataUrl(text, size) : ''); }, [text, capi]);
  return src ? <img className="ad-qr" src={src} width={size} height={size} alt="QR code" /> : <div className="ad-qr empty" style={{ width: size, height: size }}><QrCode /></div>;
}

function PayLinks() {
  const toast = useToast(); const err = useErr(); const [confirm, confirmEl] = useConfirm();
  const [st, setSt] = useState(''); const [qr, setQr] = useState(null);
  const q = useAd(() => api('/api/paylinks' + (st ? '?status=' + st : '')), [st]);
  const cancel = async (r) => { if (await confirm('Cancel this payment link?', `${r.customer} · ${INR(r.amount)}`, { danger: true, ok: 'Cancel link' })) api(`/api/paylinks/${r.id}/cancel`, { method: 'POST' }).then(q.reload).catch(err); };
  const msg = (r) => `Dear customer, please pay ${INR(r.amount - r.paid_amount)} for your ${r.bank} account ending ${String(r.account_no || '').slice(-4)} securely here: ${r.page_url}`;
  return <AdState q={q}>{d => <>
    <AdStats items={[['Links', d.summary.links], ['Paid / part paid', d.summary.paid, 'good'], ['Collected online', INR(d.summary.collected), 'good']]} />
    <div className="row wrap ad-bar"><div className="chips">{['', 'created', 'paid', 'partial', 'expired'].map(s => <button key={s} className={cx('chip', st === s && 'on')} onClick={() => setSt(s)}>{s ? s[0].toUpperCase() + s.slice(1) : 'All'}</button>)}</div></div>
    <Card pad={false} className="rise"><AdTable cols={[['created_at', 'Created', fmtDT], ['customer', 'Customer', (v, r) => <><b>{v}</b><div className="faint" style={{ fontSize: 11.5 }}>{r.bank} · {r.account_no}</div></>],
      ['amount', 'Amount', INR, { num: 1 }], ['paid_amount', 'Paid', INR, { num: 1 }], ['status', 'Status', v => <Pill tone={LINK_TONE[v]} dot>{v}</Pill>], ['utr', 'UTR'],
      ['page_url', 'Share', (v, r) => <div className="row" style={{ gap: 2 }}>
        <button className="icon-btn" title="Copy link" onClick={() => copyText(v, toast)}><Copy /></button>
        <button className="icon-btn" title="QR code" onClick={() => setQr(r)}><QrCode /></button>
        <a className="icon-btn" title="Send on WhatsApp" target="_blank" rel="noreferrer" href={waHref('', msg(r))}><MessageCircle /></a>
        {r.status === 'created' && <button className="icon-btn" title="Cancel link" onClick={() => cancel(r)}><X /></button>}</div>]]} rows={d.links} empty="No payment links yet." /></Card>
    <Modal open={!!qr} onClose={() => setQr(null)} title="Scan to pay" sub={qr && `${qr.customer} · ${INR(qr.amount - qr.paid_amount)}`} width={360}>
      {qr && <div className="col" style={{ alignItems: 'center', gap: 10 }}><QrImg text={qr.page_url} size={200} /><div className="faint" style={{ fontSize: 12, wordBreak: 'break-all', textAlign: 'center' }}>{qr.page_url}</div></div>}
    </Modal>{confirmEl}
  </>}</AdState>;
}

function PayLinkNew({ onDone }) {
  const toast = useToast(); const err = useErr();
  const [q, setQ] = useState(''); const [res, setRes] = useState(null); const [pick, setPick] = useState(null); const [amt, setAmt] = useState(''); const [out, setOut] = useState(null); const [busy, setBusy] = useState(false);
  const search = () => { if (!q.trim()) return; setBusy(true); api('/api/cases?search=' + encodeURIComponent(q) + '&limit=20').then(r => setRes(Array.isArray(r) ? r : (r.items || r.cases || []))).catch(err).finally(() => setBusy(false)); };
  const make = () => api('/api/paylinks', { method: 'POST', body: { case_id: pick.id, amount: amt || null } }).then(r => { setOut(r); toast('Link ready'); }).catch(err);
  if (out) return <Card className="rise ad-narrow" title={`Link for ${out.customer}`} sub={INR(out.amount)}>
    <div className="row wrap" style={{ gap: 16, alignItems: 'center' }}>
      <QrImg text={out.page_url} size={150} />
      <div className="col grow" style={{ gap: 8 }}>
        <div className="ad-url">{out.page_url}</div>
        <div className="row wrap" style={{ gap: 6 }}>
          <a className="btn primary sm" target="_blank" rel="noreferrer" href={waHref('', `Please pay ${INR(out.amount)} for your ${out.bank} account securely here: ${out.page_url}`)}><MessageCircle size={14} />Send on WhatsApp</a>
          <button className="btn sm" onClick={() => copyText(out.page_url, toast)}><Copy size={14} />Copy</button>
          <button className="btn ghost sm" onClick={onDone}>Done</button></div>
      </div></div></Card>;
  return <Card className="rise ad-narrow" title="Create a payment link" sub="Find the account, choose an amount, share the link or QR">
    <div className="row" style={{ gap: 8 }}>
      <div className="ad-search grow"><Search size={15} /><input autoFocus placeholder="Customer, account no. or phone" value={q} onChange={e => setQ(e.target.value)} onKeyDown={e => e.key === 'Enter' && search()} /></div>
      <button className="btn primary" disabled={busy} onClick={search}>{busy ? 'Searching…' : 'Search'}</button></div>
    {res && !res.length && <div className="faint" style={{ marginTop: 10 }}>No accounts match.</div>}
    {res && res.length > 0 && <div className="ad-pick">{res.map(c => <button key={c.id} className={cx('ad-pick-row', pick && pick.id === c.id && 'on')} onClick={() => { setPick(c); setAmt(''); }}>
      <b>{c.customer_name}</b><span>{c.bank} {c.product} · {c.account_no}</span><span className="num">Pending {INR(c.pending_amount)}</span></button>)}</div>}
    {pick && <div className="row wrap" style={{ gap: 10, marginTop: 12, alignItems: 'flex-end' }}>
      <div className="grow"><Field label="Amount" hint={`Leave blank for the full pending ${INR(pick.pending_amount)}`}><input className="input" type="number" value={amt} onChange={e => setAmt(e.target.value)} /></Field></div>
      <button className="btn primary" onClick={make}><Link2 size={15} />Create link</button></div>}
  </Card>;
}

function PayRecon() {
  const toast = useToast(); const err = useErr();
  const [file, setFile] = useState(null); const [pv, setPv] = useState(null); const [busy, setBusy] = useState(false);
  const check = () => { const fd = new FormData(); fd.append('file', file); setBusy(true); api('/api/paylinks/reconcile/preview', { method: 'POST', form: fd }).then(setPv).catch(err).finally(() => setBusy(false)); };
  const apply = () => api('/api/paylinks/reconcile/apply', { method: 'POST', body: { lines: pv.lines.filter(l => l.link_id && !l.duplicate) } }).then(r => { toast(`${r.applied} payment(s) posted to cases`); setPv(null); }).catch(err);
  return <Card className="rise" title="Reconcile a bank statement" sub="Excel or CSV with Narration and Credit columns">
    <AdNote>Credits are matched to open links by the link note, the UTR the customer reported, or account number + amount. Each credit is posted only once.</AdNote>
    <div className="row wrap" style={{ gap: 8 }}>
      <label className="btn"><Upload size={15} />{file ? file.name : 'Choose file'}<input type="file" hidden accept=".xlsx,.csv" onChange={e => { setFile(e.target.files[0]); setPv(null); }} /></label>
      <button className="btn primary" disabled={!file || busy} onClick={check}><FileSpreadsheet size={15} />{busy ? 'Checking…' : 'Check'}</button></div>
    {pv && <div style={{ marginTop: 14 }}>
      <AdStats items={[['Credits', pv.total], ['Matched', pv.matched, 'good'], ['Unmatched', pv.total - pv.matched, pv.total - pv.matched ? 'warn' : null]]} />
      <AdTable maxH={420} cols={[['date', 'Date'], ['amount', 'Amount', INR2, { num: 1 }], ['narration', 'Narration'], ['ref', 'Ref'],
        ['customer', 'Matched to', (v, r) => r.duplicate ? <Pill>already posted</Pill> : v ? <>{v} <span className="faint">({r.match})</span></> : <span className="faint">no match</span>]]} rows={pv.lines} />
      <button className="btn primary" style={{ marginTop: 10 }} disabled={!pv.matched} onClick={apply}><CheckCircle2 size={15} />Post {pv.matched} payment(s)</button>
    </div>}
  </Card>;
}

/* ═════════════════════════════ 📣 Outreach ═════════════════════════════ */
export function AddonOutreach() {
  const [tab, setTab] = useState('journeys');
  return <><AdTabs tabs={[['journeys', 'Journeys'], ['messages', 'Messages']]} cur={tab} set={setTab} />{tab === 'journeys' ? <OutJourneys /> : <OutMessages />}</>;
}
const OUT_TRIG = { close: 'Days before close date', ptp: 'Days from PTP date (−1 = day before)', monthly: 'Day of month' };
const BLANK_J = { name: '', trigger: 'close', filters: {}, steps: [{ offset: 3, channel: 'whatsapp', text: 'Dear {name}, ₹{amount} is due on your {bank} account ending {account_last4}. Please pay before {close_date}: {pay_link}' }], active: true };

function OutJourneys() {
  const toast = useToast(); const err = useErr();
  const q = useAd(() => api('/api/outreach/journeys'));
  const [ed, setEd] = useState(null); const [pv, setPv] = useState(null); const [running, setRunning] = useState(false);
  const save = () => api('/api/outreach/journeys' + (ed.id ? '/' + ed.id : ''), { method: ed.id ? 'PUT' : 'POST', body: ed }).then(() => { toast('Saved'); setEd(null); q.reload(); }).catch(err);
  const run = () => { setRunning(true); api('/api/outreach/run', { method: 'POST', body: {} }).then(r => { toast(r.waiting ? `Created ${r.created} — waiting for contact hours` : `Created ${r.created} · sent ${r.sent} · to send by hand ${r.manual} · failed ${r.failed}`); q.reload(); }).catch(err).finally(() => setRunning(false)); };
  const step = (i, k, v) => setEd({ ...ed, steps: ed.steps.map((s, j) => j === i ? { ...s, [k]: v } : s) });
  return <>
    <div className="row wrap ad-bar"><button className="btn primary sm" onClick={() => { setEd(JSON.parse(JSON.stringify(BLANK_J))); setPv(null); }}><Plus size={14} />New journey</button>
      <button className="btn sm" disabled={running} onClick={run}><Play size={14} />{running ? 'Running…' : 'Run today\'s steps now'}</button></div>
    <AdState q={q}>{d => <Card pad={false} className="rise"><AdTable cols={[['name', 'Journey', v => <b>{v}</b>], ['trigger', 'Trigger', v => OUT_TRIG[v]],
      ['filters', 'For', v => Object.entries(v || {}).filter(([, x]) => x).map(([k, x]) => `${k}: ${x}`).join(', ') || 'All unpaid'],
      ['steps', 'Steps', v => (v || []).map((s, i) => <div key={i} className="ad-step">{s.channel === 'sms' ? <Mail size={12} /> : <MessageCircle size={12} />}<b>{s.offset}</b>{String(s.text || '').slice(0, 60)}…</div>)],
      ['stats', 'Messages', v => Object.entries(v || {}).map(([k, n]) => `${k} ${n}`).join(' · ') || '—'], ['active', 'Active', v => v ? <Pill tone="good" dot>Active</Pill> : <Pill>Paused</Pill>],
      ['id', '', (v, r) => <div className="row" style={{ gap: 2 }}><button className="icon-btn" title="Edit" onClick={() => { setEd(JSON.parse(JSON.stringify(r))); setPv(null); }}><Pencil /></button>
        {r.active && <button className="icon-btn" title="Pause" onClick={() => api('/api/outreach/journeys/' + v, { method: 'DELETE' }).then(q.reload).catch(err)}><Pause /></button>}</div>]]} rows={d} empty="No journeys yet — create one." /></Card>}</AdState>
    <Modal open={!!ed} onClose={() => setEd(null)} title={ed && ed.id ? 'Edit journey' : 'New journey'} sub="Automatic reminders to unpaid customers" width={720}
      footer={<><button className="btn ghost" onClick={() => api('/api/outreach/preview', { method: 'POST', body: ed }).then(setPv).catch(err)}><Eye size={15} />Preview</button><span className="grow" />
        <button className="btn ghost" onClick={() => setEd(null)}>Cancel</button><button className="btn primary" onClick={save}>Save</button></>}>
      {ed && <div className="col" style={{ gap: 10 }}>
        <div className="form-grid">
          <Field label="Name"><input className="input" value={ed.name} onChange={e => setEd({ ...ed, name: e.target.value })} /></Field>
          <Field label="Trigger"><select className="input" value={ed.trigger} onChange={e => setEd({ ...ed, trigger: e.target.value })}>{Object.entries(OUT_TRIG).map(([k, l]) => <option key={k} value={k}>{l}</option>)}</select></Field>
        </div>
        <div className="form-grid four">{['bank', 'product', 'bucket', 'branch'].map(k => <Field key={k} label={k[0].toUpperCase() + k.slice(1)}>
          <input className="input" value={(ed.filters || {})[k] || ''} placeholder="Any" onChange={e => setEd({ ...ed, filters: { ...ed.filters, [k]: e.target.value } })} /></Field>)}</div>
        <div className="faint" style={{ fontSize: 12 }}>Placeholders: {'{name} {amount} {bank} {account_last4} {ptp_date} {ptp_amount} {close_date} {pay_link} {company}'}</div>
        {ed.steps.map((s, i) => <div key={i} className="ad-stepcard">
          <div className="row" style={{ gap: 6 }}>
            <span className="ad-step-n">{i + 1}</span>
            <input className="input" type="number" style={{ width: 90 }} value={s.offset} onChange={e => step(i, 'offset', e.target.value)} title={OUT_TRIG[ed.trigger]} />
            <select className="input" style={{ width: 140 }} value={s.channel} onChange={e => step(i, 'channel', e.target.value)}><option value="whatsapp">WhatsApp</option><option value="sms">SMS</option></select>
            <span className="grow faint" style={{ fontSize: 11.5 }}>{OUT_TRIG[ed.trigger]}</span>
            <button className="icon-btn" title="Remove step" onClick={() => setEd({ ...ed, steps: ed.steps.filter((_, j) => j !== i) })}><Trash2 /></button></div>
          <textarea className="input" rows={2} value={s.text} onChange={e => step(i, 'text', e.target.value)} /></div>)}
        <button className="btn ghost sm" style={{ alignSelf: 'flex-start' }} onClick={() => setEd({ ...ed, steps: [...ed.steps, { offset: 1, channel: 'whatsapp', text: '' }] })}><Plus size={14} />Add step</button>
        {pv && <AdNote>Reaches <b>{pv.cases}</b> unpaid cases now. Sample: <i>{pv.sample}</i></AdNote>}
      </div>}
    </Modal>
  </>;
}

function OutMessages() {
  const err = useErr();
  const [st, setSt] = useState('manual');
  const q = useAd(() => api('/api/outreach/messages' + (st ? '?status=' + st : '')), [st]);
  const tone = { manual: 'warn', queued: 'info', sent: 'good', failed: 'bad', skipped: 'neutral' };
  return <>
    <div className="row wrap ad-bar">
      <div className="chips">{[['manual', 'To send by hand'], ['queued', 'Queued'], ['sent', 'Sent'], ['failed', 'Failed'], ['skipped', 'Skipped'], ['', 'All']].map(([k, l]) =>
        <button key={k} className={cx('chip', st === k && 'on')} onClick={() => setSt(k)}>{l}</button>)}</div><span className="grow" />
      {st === 'manual' && <button className="btn sm" onClick={() => download('/api/outreach/messages.csv?status=manual', 'outreach_manual.csv')}><Download size={14} />CSV for bulk tool</button>}</div>
    <AdState q={q}>{d => <Card pad={false} className="rise"><AdTable cols={[['run_date', 'Date', fmtDate], ['journey', 'Journey'], ['customer', 'Customer'],
      ['channel', 'Via', v => v === 'sms' ? <Pill><Mail size={11} /> SMS</Pill> : <Pill tone="good"><MessageCircle size={11} /> WhatsApp</Pill>],
      ['text', 'Message', v => <span className="ad-msg">{v}</span>], ['status', 'Status', (v, r) => <><Pill tone={tone[v]}>{v}</Pill>{r.error && <div className="faint" style={{ fontSize: 11 }}>{r.error}</div>}</>],
      ['id', '', (v, r) => (r.status === 'manual' || r.status === 'failed') && <div className="row" style={{ gap: 2 }}>
        {r.channel === 'whatsapp' && <a className="icon-btn" title="Open WhatsApp" target="_blank" rel="noreferrer" href={waHref(r.to, r.text)}><MessageCircle /></a>}
        {r.channel === 'sms' && <a className="icon-btn" title="Open SMS" href={`sms:+91${r.to}?body=${encodeURIComponent(r.text)}`}><Send /></a>}
        <button className="btn sm" onClick={() => api(`/api/outreach/messages/${v}/done`, { method: 'POST' }).then(q.reload).catch(err)}><CheckCircle2 size={14} />Sent</button></div>]]} rows={d} empty="No messages here." /></Card>}</AdState>
  </>;
}

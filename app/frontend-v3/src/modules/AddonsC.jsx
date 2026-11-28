// Add-ons, phase 4 — Advanced analytics, Agency billing, Skip tracing, Open API & webhooks (native, same APIs as classic).
import React, { useState } from 'react';
import { Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { Copy, FileText, KeyRound, Pause, Pencil, Phone, Play, Plus, Search, Send, Trash2, Webhook, X, AlertTriangle, Calculator, CheckCircle2 } from 'lucide-react';
import { api, download } from '../lib/api.js';
import { cx, fmtDate } from '../lib/format.js';
import { Card, Pill, useToast } from '../components/ui.jsx';
import { Modal, Field, ChartTip, chartColor } from './kit.jsx';
import { AdState, AdTabs, AdTable, AdStats, AdNote, useAd, useConfirm, useErr, fmtDT, INR, INR2 } from './AddonKit.jsx';

const pct = (v) => (v == null ? '—' : v + '%');

/* ═════════════════════════════ 📊 Advanced analytics ═════════════════════════════ */
export function AddonAnalytics() {
  const q = useAd(() => api('/api/insights'));
  return <AdState q={q} h={320}>{d => { const f = d.forecast, qu = d.quality, r = d.rolls;
    return <>
      <Card title={`Month-end forecast · ${d.period}`} sub={`Method: ${f.method}`} className="rise">
        <AdStats items={[['Collected so far', INR(f.collected_so_far), 'good'], ['Forecast month-end', INR(f.forecast_month_end)], ['Open PTP value', INR(f.open_ptp_value), 'warn'],
          ['Expected from PTPs', INR(f.expected_from_ptps)], ['Days left', f.days_left]]} />
      </Card>
      <div className="ad-2col even">
        <Card title="Contact & promise quality" className="rise">
          <AdStats items={[['Attempts', qu.attempts], ['Connect rate', pct(qu.connect_rate)], ['PTPs', qu.ptps], ['PTP kept', `${qu.ptp_kept}/${qu.ptp_due}`, 'good', `${qu.kept_ratio}% kept`]]} />
        </Card>
        <Card title="Best hours to call" sub="Connect rate by hour" className="rise">
          {!(d.hours || []).some(h => h.attempts) ? <div className="faint" style={{ padding: '40px 0', textAlign: 'center' }}>No call attempts logged yet this month.</div> : <div style={{ height: 170 }}><ResponsiveContainer><BarChart data={d.hours.map(h => ({ ...h, h: String(h.hour).slice(0, 2) }))} margin={{ top: 6, right: 6, left: -18, bottom: 0 }}>
            <CartesianGrid vertical={false} stroke="var(--line)" /><XAxis dataKey="h" tick={{ fontSize: 11, fill: 'var(--text-3)' }} axisLine={false} tickLine={false} />
            <YAxis tick={{ fontSize: 11, fill: 'var(--text-3)' }} axisLine={false} tickLine={false} unit="%" />
            <Tooltip content={<ChartTip fmt={(v) => v + '%'} />} cursor={{ fill: 'var(--bg-hover)' }} />
            <Bar dataKey="connect_rate" name="Connect rate" radius={[6, 6, 0, 0]}>{d.hours.map((h, i) => <Cell key={i} fill={chartColor(0)} fillOpacity={0.45 + Math.min(.55, (h.connect_rate || 0) / 100)} />)}</Bar>
          </BarChart></ResponsiveContainer></div>}
        </Card>
      </div>
      <Card title="Roll-back / roll-forward" sub="Same account, last month → this month" className="rise">
        <AdStats items={[['Rolled back (improved)', r.counts.rolled_back || 0, 'good'], ['Stabilised', r.counts.stabilised || 0], ['Rolled forward', r.counts.rolled_forward || 0, 'bad']]} />
        <div style={{ marginTop: 12 }}><AdTable maxH={300} cols={[['from', 'Last month'], ['to', 'This month'], ['cases', 'Cases', null, { num: 1 }]]} rows={r.matrix} empty="Needs last month's data for the same accounts." /></div>
      </Card>
      <Card title="Resolution by bank / product / bucket" pad={false} className="rise"><AdTable maxH={420} cols={[['bank', 'Bank'], ['product', 'Product'], ['bucket', 'Bucket'], ['cases', 'Cases', null, { num: 1 }], ['paid', 'Paid', null, { num: 1 }], ['partial', 'Part', null, { num: 1 }],
        ['resolution_pct', 'Resolution', v => <ResBar v={v} />], ['received', 'Collected', INR, { num: 1 }], ['collection_pct', 'Collection %', pct, { num: 1 }]]} rows={d.resolution} /></Card>
      <Card title="Agent productivity · this month" pad={false} className="rise"><AdTable maxH={460} cols={[['name', 'Agent', v => <b>{v}</b>], ['role', 'Role'], ['days', 'Days', null, { num: 1 }], ['per_day', 'Actions/day', null, { num: 1 }], ['connect_rate', 'Connect', pct, { num: 1 }],
        ['ptps', 'PTPs', null, { num: 1 }], ['visits', 'Visits', null, { num: 1 }], ['collected', 'Collected', INR, { num: 1 }], ['collected_per_day', '₹/day', INR, { num: 1 }]]} rows={d.productivity} /></Card>
    </>; }}</AdState>;
}
const ResBar = ({ v }) => <div className="ad-resbar"><span style={{ width: Math.min(100, Number(v) || 0) + '%' }} /><b>{pct(v)}</b></div>;

/* ═════════════════════════════ 🧾 Agency billing ═════════════════════════════ */
export function AddonBilling() {
  const [tab, setTab] = useState('invoices');
  return <><AdTabs tabs={[['invoices', 'Invoices'], ['rates', 'Commission rates']]} cur={tab} set={setTab} />{tab === 'rates' ? <BillRates /> : <BillInvoices />}</>;
}
const BASIS = { percent: '% of collection', per_case: '₹ per paid case', fixed: '₹ fixed / month' };
const BLANK_RATE = { bank: '', product: '', bucket: '', basis: 'percent', rate: '', note: '' };
function BillRates() {
  const toast = useToast(); const err = useErr(); const [confirm, confirmEl] = useConfirm();
  const q = useAd(() => api('/api/billing/rates'));
  const [f, setF] = useState(BLANK_RATE);
  const save = () => api('/api/billing/rates', { method: 'POST', body: f }).then(() => { toast('Saved'); setF({ ...BLANK_RATE, bank: f.bank }); q.reload(); }).catch(err);
  const del = async (r) => { if (await confirm('Delete this rate?', `${r.bank} ${r.product || 'all'} · ${r.rate}`, { danger: true, ok: 'Delete' })) api('/api/billing/rates/' + r.id, { method: 'DELETE' }).then(q.reload).catch(err); };
  return <>
    <Card title={f.id ? 'Edit rate' : 'Add a commission rate'} className="rise">
      <div className="form-grid six">
        <Field label="Bank"><input className="input" value={f.bank} onChange={e => setF({ ...f, bank: e.target.value })} /></Field>
        <Field label="Product" hint="Blank = all"><input className="input" value={f.product} onChange={e => setF({ ...f, product: e.target.value })} /></Field>
        <Field label="Bucket" hint="Blank = any"><input className="input" value={f.bucket} onChange={e => setF({ ...f, bucket: e.target.value })} /></Field>
        <Field label="Basis"><select className="input" value={f.basis} onChange={e => setF({ ...f, basis: e.target.value })}>{Object.entries(BASIS).map(([k, l]) => <option key={k} value={k}>{l}</option>)}</select></Field>
        <Field label="Rate"><input className="input" type="number" value={f.rate} onChange={e => setF({ ...f, rate: e.target.value })} /></Field>
        <Field label="Note"><input className="input" value={f.note} onChange={e => setF({ ...f, note: e.target.value })} /></Field>
      </div>
      <div className="row" style={{ gap: 8 }}><span className="grow" />{f.id && <button className="btn ghost" onClick={() => setF(BLANK_RATE)}>Cancel edit</button>}
        <button className="btn primary" onClick={save}>{f.id ? 'Update' : <><Plus size={15} />Add</>}</button></div>
    </Card>
    <AdState q={q}>{d => <Card pad={false} className="rise"><AdTable cols={[['bank', 'Bank', v => <b>{v}</b>], ['product', 'Product', v => v || 'All'], ['bucket', 'Bucket', v => v || 'Any'], ['basis', 'Basis', v => BASIS[v] || v], ['rate', 'Rate', null, { num: 1 }], ['note', 'Note'],
      ['id', '', (v, r) => <div className="row" style={{ gap: 2 }}><button className="icon-btn" title="Edit" onClick={() => setF({ ...r, product: r.product || '', bucket: r.bucket || '' })}><Pencil /></button>
        <button className="icon-btn" title="Delete" onClick={() => del(r)}><Trash2 /></button></div>]]} rows={d} empty="No rates yet — add one above." /></Card>}</AdState>
    {confirmEl}
  </>;
}
const INV_TONE = { draft: 'neutral', issued: 'info', paid: 'good', cancelled: 'bad' };
function BillInvoices() {
  const toast = useToast(); const err = useErr(); const [confirm, confirmEl] = useConfirm();
  const q = useAd(() => api('/api/billing/invoices'));
  const [nw, setNw] = useState(null);
  const st = async (i, status) => { if (await confirm(`Mark ${i.number} as ${status}?`, null, { danger: status === 'cancelled', ok: 'Yes' })) api(`/api/billing/invoices/${i.id}/status`, { method: 'POST', body: { status } }).then(q.reload).catch(err); };
  const calc = () => api('/api/billing/invoices/preview', { method: 'POST', body: nw }).then(pv => setNw(n => ({ ...n, pv }))).catch(err);
  const create = () => api('/api/billing/invoices', { method: 'POST', body: { bank: nw.bank, period: nw.period, bill_to: nw.bill_to } }).then(() => { toast('Draft created'); setNw(null); q.reload(); }).catch(err);
  return <>
    <div className="row ad-bar"><button className="btn primary sm" onClick={() => setNw({ bank: '', period: new Date().toISOString().slice(0, 7), bill_to: '', pv: null })}><Plus size={14} />New invoice</button></div>
    <AdState q={q}>{d => <Card pad={false} className="rise"><AdTable cols={[['number', 'Invoice', v => <b>{v}</b>], ['bank', 'Bank'], ['period', 'Month'], ['subtotal', 'Taxable', INR2, { num: 1 }], ['gst', 'GST', INR2, { num: 1 }], ['total', 'Total', v => <b>{INR2(v)}</b>, { num: 1 }],
      ['status', 'Status', v => <Pill tone={INV_TONE[v]} dot>{v}</Pill>],
      ['id', '', (v, r) => <div className="row" style={{ gap: 4 }}><button className="icon-btn" title="Invoice PDF" onClick={() => download(`/api/billing/invoices/${v}.pdf`, `${r.number.replace(/\//g, '-')}.pdf`)}><FileText /></button>
        {r.status === 'draft' && <button className="btn sm" onClick={() => st(r, 'issued')}>Issue</button>}{r.status === 'issued' && <button className="btn sm" onClick={() => st(r, 'paid')}>Mark paid</button>}
        {['draft', 'issued'].includes(r.status) && <button className="icon-btn" title="Cancel" onClick={() => st(r, 'cancelled')}><X /></button>}</div>]]} rows={d} empty="No invoices yet." /></Card>}</AdState>
    <Modal open={!!nw} onClose={() => setNw(null)} title="New invoice" sub="Calculated from collections and your commission rates" width={700}
      footer={nw && nw.pv ? <><span className="grow" /><button className="btn ghost" onClick={() => setNw(null)}>Cancel</button><button className="btn primary" onClick={create}>Create draft</button></> : null}>
      {nw && <div className="col" style={{ gap: 10 }}>
        <div className="row wrap" style={{ gap: 8, alignItems: 'flex-end' }}>
          <div className="grow"><Field label="Bank"><input className="input" placeholder="e.g. AXIS" value={nw.bank} onChange={e => setNw({ ...nw, bank: e.target.value.toUpperCase(), pv: null })} /></Field></div>
          <Field label="Month"><input className="input" type="month" value={nw.period} onChange={e => setNw({ ...nw, period: e.target.value, pv: null })} /></Field>
          <button className="btn" onClick={calc}><Calculator size={15} />Calculate</button></div>
        {nw.pv && <>
          <AdTable maxH={260} cols={[['description', 'Line'], ['cases', 'Cases', null, { num: 1 }], ['collected', 'Collected', INR, { num: 1 }], ['amount', 'Amount', INR2, { num: 1 }]]} rows={nw.pv.lines} empty="No billable collections for this bank and month." />
          <div className="ad-totals"><span>Taxable <b>{INR2(nw.pv.subtotal)}</b></span><span>GST <b>{INR2(nw.pv.gst)}</b></span><span className="t">Total <b>{INR2(nw.pv.total)}</b></span></div>
          <Field label="Bill to (bank's name, address, GSTIN)"><textarea className="input" rows={3} value={nw.bill_to} onChange={e => setNw({ ...nw, bill_to: e.target.value })} /></Field>
        </>}
      </div>}
    </Modal>{confirmEl}
  </>;
}

/* ═════════════════════════════ 🔎 Skip tracing ═════════════════════════════ */
export function AddonSkipTrace() {
  const q = useAd(() => api('/api/skiptrace/unreachable'));
  const [open, setOpen] = useState(null); const [term, setTerm] = useState('');
  return <>
    <AdNote>Unpaid customers you can't reach (RNR / switched off / wrong number). Leads come only from your own data — the same customer's other loans, numbers your team updated and addresses found on visits.</AdNote>
    <AdState q={q}>{d => { const t = term.trim().toLowerCase(); const rows = d.filter(r => !t || `${r.customer} ${r.bank} ${r.product}`.toLowerCase().includes(t));
      return <>
        <div className="row ad-bar"><AdStats items={[['Unreachable', d.length, d.length ? 'warn' : 'good'], ['With phone leads', d.filter(r => r.phone_leads > 0).length, 'good'], ['With address leads', d.filter(r => r.address_leads > 0).length, 'good']]} />
          <span className="grow" /><div className="ad-search"><Search size={15} /><input placeholder="Search customer or bank" value={term} onChange={e => setTerm(e.target.value)} /></div></div>
        <Card pad={false} className="rise"><AdTable cols={[['customer', 'Customer', v => <b>{v}</b>], ['bank', 'Bank'], ['product', 'Product'], ['disposition', 'Last outcome', v => <Pill tone="bad">{v}</Pill>],
          ['phone_leads', 'Phone leads', v => <span className={cx('ad-lead', v > 0 && 'on')}>{v}</span>, { num: 1 }], ['address_leads', 'Address leads', v => <span className={cx('ad-lead', v > 0 && 'on')}>{v}</span>, { num: 1 }],
          ['case_id', '', v => <button className="btn sm primary" onClick={() => setOpen(v)}><Search size={14} />Trace</button>]]} rows={rows} empty="No unreachable cases right now." /></Card>
      </>; }}</AdState>
    {open && <SkipTraceModal caseId={open} onClose={() => { setOpen(null); q.reload(); }} />}
  </>;
}
function SkipTraceModal({ caseId, onClose }) {
  const toast = useToast(); const err = useErr();
  const q = useAd(() => api('/api/skiptrace/case/' + caseId), [caseId]);
  const use = body => api(`/api/skiptrace/case/${caseId}/apply`, { method: 'POST', body }).then(() => { toast('Saved on the case'); q.reload(); }).catch(err);
  return <Modal open onClose={onClose} title="Skip-trace leads" sub={`Case #${caseId}`} width={660}>
    <AdState q={q}>{d => <div className="col" style={{ gap: 14 }}>
      <div><div className="ad-h">Phone numbers</div>{d.phones.length ? d.phones.map(p => <div key={p.value} className="ad-lead-row">
        <Phone size={15} /><div className="grow"><b>{p.value}</b><div className="faint" style={{ fontSize: 11.5 }}>{p.sources.join(' · ')}</div></div>
        <a className="icon-btn" title="Call" href={`tel:${p.value}`}><Phone /></a><button className="btn sm" onClick={() => use({ phone: p.value })}>Use as new number</button></div>)
        : <div className="faint">No other numbers found.</div>}</div>
      <div><div className="ad-h">Addresses</div>{d.addresses.length ? d.addresses.map(a => <div key={a.value} className="ad-lead-row">
        <div className="grow">{a.value}<div className="faint" style={{ fontSize: 11.5 }}>{a.sources.join(' · ')}</div></div>
        <button className="btn sm" onClick={() => use({ address: a.value })}>Use as new address</button></div>)
        : <div className="faint">No other addresses found.</div>}</div>
      {d.related_cases.length > 0 && <div><div className="ad-h">Related accounts</div>
        <AdTable maxH={220} cols={[['id', '#'], ['bank', 'Bank'], ['product', 'Product'], ['period', 'Month'], ['status', 'Status']]} rows={d.related_cases} /></div>}
    </div>}</AdState>
  </Modal>;
}

/* ═════════════════════════════ 🔌 Open API & webhooks ═════════════════════════════ */
export function AddonOpenApi() {
  const toast = useToast(); const err = useErr(); const [confirm, confirmEl] = useConfirm();
  const q = useAd(() => api('/api/apikeys'));
  const [k, setK] = useState({ name: '', scopes: ['cases:read'], banks: '' }); const [w, setW] = useState({ url: '', events: [], banks: '' }); const [shown, setShown] = useState(null);
  const tog = (arr, v) => (arr.includes(v) ? arr.filter(x => x !== v) : [...arr, v]);
  const banks = s => s.split(',').map(x => x.trim()).filter(Boolean);
  const copy = (t) => { try { navigator.clipboard.writeText(t); toast('Copied'); } catch (e) { toast('Copy failed — select it and copy', 'err'); } };
  const createKey = () => api('/api/apikeys', { method: 'POST', body: { ...k, banks: banks(k.banks) } }).then(r => { setShown({ kind: 'API key', value: r.key }); setK({ name: '', scopes: ['cases:read'], banks: '' }); q.reload(); }).catch(err);
  const addHook = () => api('/api/apikeys/webhooks', { method: 'POST', body: { ...w, banks: banks(w.banks) } }).then(r => { setShown({ kind: 'Webhook signing secret', value: r.secret }); setW({ url: '', events: [], banks: '' }); q.reload(); }).catch(err);
  const revoke = async (r) => { if (await confirm('Revoke this key?', 'Systems using it will stop working immediately.', { danger: true, ok: 'Revoke' })) api(`/api/apikeys/${r.id}/revoke`, { method: 'POST' }).then(q.reload).catch(err); };
  const delHook = async (h) => { if (await confirm('Delete this webhook?', h.url, { danger: true, ok: 'Delete' })) api(`/api/apikeys/webhooks/${h.id}`, { method: 'POST', body: { delete: true } }).then(q.reload).catch(err); };
  return <AdState q={q}>{d => <>
    <Card title="API keys" sub="Let a bank's or partner's system read cases and post payments" className="rise">
      <div className="col" style={{ gap: 10 }}>
        <div className="row wrap" style={{ gap: 8, alignItems: 'flex-end' }}>
          <div style={{ minWidth: 220 }}><Field label="Name"><input className="input" placeholder="e.g. Axis MIS feed" value={k.name} onChange={e => setK({ ...k, name: e.target.value })} /></Field></div>
          <div style={{ minWidth: 220 }}><Field label="Limit to banks"><input className="input" placeholder="Comma separated · blank = all" value={k.banks} onChange={e => setK({ ...k, banks: e.target.value })} /></Field></div>
          <button className="btn primary" disabled={!k.name.trim()} onClick={createKey}><KeyRound size={15} />Create key</button></div>
        <div className="chips">{d.scopes.map(s => <button key={s} className={cx('chip', k.scopes.includes(s) && 'on')} onClick={() => setK({ ...k, scopes: tog(k.scopes, s) })}>{s}{s === 'pii' ? ' (full phone numbers)' : ''}</button>)}</div>
      </div>
      <div style={{ marginTop: 12 }}><AdTable maxH={300} cols={[['name', 'Name', v => <b>{v}</b>], ['prefix', 'Key', v => <code className="ad-code">{v}…</code>], ['scopes', 'Scopes', v => (v || []).join(', ')], ['banks', 'Banks', v => (v || []).join(', ') || 'All'],
        ['last_used_at', 'Last used', fmtDT], ['revoked', 'Status', v => v ? <Pill tone="bad">revoked</Pill> : <Pill tone="good" dot>active</Pill>],
        ['id', '', (v, r) => !r.revoked && <button className="btn ghost sm" onClick={() => revoke(r)}>Revoke</button>]]} rows={d.keys} empty="No keys yet." /></div>
      <AdNote>Use: <code className="ad-code">Authorization: Bearer riq_…</code> · GET /api/open/v1/cases · GET /api/open/v1/cases/&lt;account&gt; · POST /api/open/v1/payments {'{account_no, amount, mode, reference}'} · GET /api/open/v1/events?since_id=</AdNote>
    </Card>
    <Card title="Webhooks" sub="Push events to another system as they happen" className="rise">
      <div className="col" style={{ gap: 10 }}>
        <div className="row wrap" style={{ gap: 8, alignItems: 'flex-end' }}>
          <div className="grow" style={{ minWidth: 280 }}><Field label="URL"><input className="input" placeholder="https://your-system/hook" value={w.url} onChange={e => setW({ ...w, url: e.target.value })} /></Field></div>
          <div style={{ minWidth: 200 }}><Field label="Banks"><input className="input" placeholder="Comma separated · blank = all" value={w.banks} onChange={e => setW({ ...w, banks: e.target.value })} /></Field></div>
          <button className="btn primary" disabled={!w.url.trim()} onClick={addHook}><Webhook size={15} />Add webhook</button></div>
        <div className="chips"><span className="chips-l">Events</span>{d.events.map(ev => <button key={ev} className={cx('chip', w.events.includes(ev) && 'on')} onClick={() => setW({ ...w, events: tog(w.events, ev) })}>{ev}</button>)}</div>
        <div className="faint" style={{ fontSize: 12 }}>Each delivery is signed: header X-RecoverIQ-Signature = sha256=HMAC(secret, body). Failed deliveries retry up to 6 times.</div>
      </div>
    </Card>
    {d.webhooks.map(h => <Card key={h.id} className="rise" title={<span className="ad-url-t">{h.url}</span>} sub={(h.events || []).join(', ') || 'All events'}
      actions={<div className="row" style={{ gap: 4 }}>
        {!h.active && <Pill>paused</Pill>}
        <button className="btn ghost sm" onClick={() => api(`/api/apikeys/webhooks/${h.id}/test`, { method: 'POST' }).then(r => { toast(`Test: ${r.status} ${r.code || ''} ${r.error || ''}`); q.reload(); }).catch(err)}><Send size={14} />Send test</button>
        <button className="icon-btn" title={h.active ? 'Pause' : 'Resume'} onClick={() => api(`/api/apikeys/webhooks/${h.id}`, { method: 'POST', body: { active: !h.active } }).then(q.reload).catch(err)}>{h.active ? <Pause /> : <Play />}</button>
        <button className="icon-btn" title="Delete" onClick={() => delHook(h)}><Trash2 /></button></div>}>
      <AdTable maxH={260} cols={[['at', 'When', fmtDT], ['event', 'Event'], ['status', 'Status', v => <Pill tone={v === 'delivered' || v === 'ok' ? 'good' : v === 'failed' ? 'bad' : 'neutral'}>{v}</Pill>], ['attempts', 'Tries', null, { num: 1 }], ['code', 'HTTP'], ['error', 'Error']]} rows={h.recent} empty="No deliveries yet." />
    </Card>)}
    <Modal open={!!shown} onClose={() => setShown(null)} title={shown ? `Your new ${shown.kind}` : ''} width={520}
      footer={<><span className="grow" /><button className="btn" onClick={() => copy(shown.value)}><Copy size={15} />Copy</button><button className="btn primary" onClick={() => setShown(null)}><CheckCircle2 size={15} />I've saved it</button></>}>
      {shown && <div className="col" style={{ gap: 10 }}>
        <div className="row" style={{ gap: 8, color: 'var(--warn-ink)' }}><AlertTriangle size={16} /><b>Copy it now — it's shown only once.</b></div>
        <code className="ad-code block">{shown.value}</code></div>}
    </Modal>
    {confirmEl}
  </>}</AdState>;
}

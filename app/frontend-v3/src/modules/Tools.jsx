// Workspace tools rebuilt natively: AI Assist, Add-ons hub, Services (admin), Connections, Salary (locked).
import React, { useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Area, AreaChart, Bar, BarChart, CartesianGrid, Cell, Legend, Line, LineChart, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import {
  Bot, Check, ChevronDown, ChevronRight, Download, ExternalLink, FileText, FlaskConical, KeyRound, Lock, Maximize2, MessageCircle,
  Plug, Plus, Power, Puzzle, RefreshCw, Save, Search, Send, Settings2, Sparkles, Trash2, X, Phone, FolderOpen, Link2,
} from 'lucide-react';
import { api, download } from '../lib/api.js';
import { useAuth } from '../lib/auth.jsx';
import { cx } from '../lib/format.js';
import { Card, Pill, Empty, Skeleton, useLoad, useToast } from '../components/ui.jsx';
import { ModuleHead, Modal, Field, SearchBox, ChartTip, chartColor, waHref, useClassicUI } from './kit.jsx';
import { useClassic } from '../lib/classic.jsx';

/* ═════════════════════════════ AI Assist ═════════════════════════════ */
const fmtN = (k, v, short) => {
  if (v == null || v === '') return '—';
  if (typeof v !== 'number') return String(v);
  const money = /(amount|collected|pending|enr|pos|recovered|cash|₹|value|tos)/i.test(String(k || ''));
  const pct = /(pct|%|rate|percent)/i.test(String(k || ''));
  if (pct) return v.toFixed(1) + '%';
  if (money) {
    if (short && Math.abs(v) >= 1e7) return '₹' + (v / 1e7).toFixed(2) + ' Cr';
    if (short && Math.abs(v) >= 1e5) return '₹' + (v / 1e5).toFixed(2) + ' L';
    return '₹' + Math.round(v).toLocaleString('en-IN');
  }
  return v.toLocaleString('en-IN');
};

function MiniMd({ text }) {
  const lines = String(text || '').split('\n'); const out = []; let i = 0;
  const inline = s => s.split(/(\*\*[^*]+\*\*)/g).map((p, k) => p.startsWith('**') && p.endsWith('**') ? <b key={k}>{p.slice(2, -2)}</b> : p);
  while (i < lines.length) {
    const l = lines[i];
    if (/^\s*\|.*\|\s*$/.test(l)) {
      const rows = []; while (i < lines.length && /^\s*\|.*\|\s*$/.test(lines[i])) { rows.push(lines[i]); i++; }
      const cells = rows.filter(r => !/^\s*\|[\s:|-]+\|\s*$/.test(r)).map(r => r.trim().slice(1, -1).split('|').map(c => c.trim()));
      out.push(<div key={'t' + i} className="table-wrap ai-tbl"><table className="t"><thead><tr>{(cells[0] || []).map((c, k) => <th key={k}>{inline(c)}</th>)}</tr></thead>
        <tbody>{cells.slice(1).map((r, a) => <tr key={a}>{r.map((c, k) => <td key={k}>{inline(c)}</td>)}</tr>)}</tbody></table></div>);
      continue;
    }
    if (/^#{1,3} /.test(l)) out.push(<div key={i} className="ai-h">{inline(l.replace(/^#+ /, ''))}</div>);
    else if (/^\s*[-*] /.test(l)) out.push(<div key={i} className="ai-li">• {inline(l.replace(/^\s*[-*] /, ''))}</div>);
    else if (/^\s*\d+\. /.test(l)) out.push(<div key={i} className="ai-li">{inline(l.trim())}</div>);
    else if (l.trim() === '') out.push(<div key={i} style={{ height: 6 }} />);
    else out.push(<div key={i}>{inline(l)}</div>);
    i++;
  }
  return <div className="ai-md">{out}</div>;
}

function visualRows(v) {
  if (v.kind === 'table') return [v.columns, ...v.rows.map(r => v.columns.map(c => r[c]))];
  if (v.kind === 'kpis') return [['Metric', 'Value'], ...v.items.map(it => [it.label, it.value])];
  if (v.kind === 'chart') return [['Label', ...v.series.map(s => s.name)], ...v.labels.map((l, i) => [l, ...v.series.map(s => s.data[i])])];
  return [];
}
function AiVisual({ v, xlsx }) {
  const [full, setFull] = useState(false);
  const title = v.title || (v.kind === 'kpis' ? 'Key numbers' : v.kind === 'flow' ? 'Steps' : 'Chart');
  const body = (h) => {
    if (v.kind === 'kpis') return <div className="ai-kpis">{v.items.map((it, i) => <div key={i} className="ai-kpi" style={{ '--c': chartColor(i) }}>
      <div className="faint">{it.label}</div><b title={fmtN(it.key || it.label, it.value)}>{fmtN(it.key || it.label, it.value, true)}</b></div>)}</div>;
    if (v.kind === 'flow') return <div className="ai-flow">{v.steps.map((s, i) => <React.Fragment key={i}><div className="ai-step"><span>{i + 1}</span>{s}</div>{i < v.steps.length - 1 && <ChevronRight className="faint" size={16} />}</React.Fragment>)}</div>;
    if (v.kind === 'table') return <div className="table-wrap" style={{ maxHeight: h ? 'none' : 320 }}><table className="t">
      <thead><tr>{v.columns.map(c => <th key={c}>{c.replace(/_/g, ' ')}</th>)}</tr></thead>
      <tbody>{v.rows.map((r, i) => <tr key={i}>{v.columns.map(c => <td key={c} className={typeof r[c] === 'number' ? 'num' : ''}>{fmtN(c, r[c])}</td>)}</tr>)}</tbody></table></div>;
    const ct = v.chart_type; const data = v.labels.map((l, i) => { const o = { label: l }; v.series.forEach(s => { o[s.name] = s.data[i]; }); return o; });
    const H = h || 260;
    const axes = <><CartesianGrid stroke="var(--line)" vertical={false} /><XAxis dataKey="label" tick={{ fill: 'var(--text-3)', fontSize: 11 }} axisLine={false} tickLine={false} />
      <YAxis tick={{ fill: 'var(--text-3)', fontSize: 11 }} axisLine={false} tickLine={false} width={56} tickFormatter={x => fmtN(v.series[0] && v.series[0].name, x, true)} />
      <Tooltip content={<ChartTip fmt={x => fmtN(v.series[0] && v.series[0].name, x)} />} />{v.series.length > 1 && <Legend />}</>;
    if (ct === 'pie' || ct === 'doughnut') {
      const s = v.series[0] || { data: [] };
      return <div style={{ height: H }}><ResponsiveContainer><PieChart><Pie isAnimationActive={false} data={v.labels.map((l, i) => ({ name: l, value: s.data[i] }))} dataKey="value" nameKey="name"
        innerRadius={ct === 'doughnut' ? '55%' : 0} outerRadius="85%" paddingAngle={1}>{v.labels.map((_, i) => <Cell key={i} fill={chartColor(i)} />)}</Pie>
        <Tooltip content={<ChartTip fmt={x => fmtN(s.name, x)} />} /><Legend layout="vertical" align="right" verticalAlign="middle" /></PieChart></ResponsiveContainer></div>;
    }
    if (ct === 'line') return <div style={{ height: H }}><ResponsiveContainer><LineChart data={data}>{axes}{v.series.map((s, i) => <Line key={s.name} isAnimationActive={false} dataKey={s.name} stroke={chartColor(i)} strokeWidth={2.5} dot={false} />)}</LineChart></ResponsiveContainer></div>;
    if (ct === 'area') return <div style={{ height: H }}><ResponsiveContainer><AreaChart data={data}>{axes}{v.series.map((s, i) => <Area key={s.name} isAnimationActive={false} dataKey={s.name} stroke={chartColor(i)} fill={chartColor(i)} fillOpacity={.2} />)}</AreaChart></ResponsiveContainer></div>;
    return <div style={{ height: H }}><ResponsiveContainer><BarChart data={data} layout={ct === 'hbar' ? 'vertical' : 'horizontal'}>
      {ct === 'hbar' ? <><CartesianGrid stroke="var(--line)" horizontal={false} /><XAxis type="number" tick={{ fill: 'var(--text-3)', fontSize: 11 }} /><YAxis type="category" dataKey="label" width={110} tick={{ fill: 'var(--text-2)', fontSize: 11 }} /><Tooltip content={<ChartTip />} /></> : axes}
      {v.series.map((s, i) => <Bar key={s.name} isAnimationActive={false} dataKey={s.name} fill={chartColor(i)} radius={[6, 6, 0, 0]} />)}</BarChart></ResponsiveContainer></div>;
  };
  const head = <div className="ai-vis-h"><b>{title}</b><div className="grow" />
    {v.kind !== 'flow' && <button className="btn sm ghost" title="Download Excel" onClick={() => xlsx(title, visualRows(v))}><Download /></button>}
    <button className="btn sm ghost" title="Full screen" onClick={() => setFull(true)}><Maximize2 /></button></div>;
  return <>
    <div className={cx('ai-vis', 'k-' + v.kind)}>{head}{body()}</div>
    <Modal open={full} onClose={() => setFull(false)} title={title} width={1180}>{body(Math.round(window.innerHeight * .62))}</Modal>
  </>;
}

export function AiMsg({ m, onSend, onOpenCase, onConfirm, xlsx }) {
  const [steps, setSteps] = useState(false);
  if (m.role === 'user') return <div className="ai-bubble me">{m.content}</div>;
  return <div className={cx('ai-bubble bot', (m.visuals || []).length && 'wide')}>
    <MiniMd text={m.content} />
    {(m.visuals || []).length > 0 && <div className="ai-visuals">{m.visuals.map((v, i) => <AiVisual key={i} v={v} xlsx={xlsx} />)}</div>}
    {(m.files || []).length > 0 && <div className="row wrap" style={{ gap: 6, marginTop: 8 }}>{m.files.map(f =>
      <button key={f.token} className="btn sm primary" onClick={() => download('/api/ai/files/' + f.token, f.name)}><FileText />{f.name}{f.rows != null ? ` · ${f.rows} rows` : ''}</button>)}</div>}
    {(m.actions || []).length > 0 && <div className="row wrap" style={{ gap: 6, marginTop: 8 }}>{m.actions.map((a, k) => <React.Fragment key={k}>
      {a.type === 'follow_up' && (a.done ? <Pill tone="good"><Check size={12} /> {a.label}</Pill> : <button className="btn sm" onClick={() => onConfirm(a)}><Check />Confirm: {a.label}</button>)}
      {a.type === 'open_case' && <button className="btn sm ghost" onClick={() => onOpenCase(a.case_id)}><FolderOpen />{a.label}</button>}
      {a.type === 'whatsapp' && <a className="btn sm ghost" href={waHref(a.phone, a.text)} target="_blank" rel="noreferrer"><MessageCircle />{a.label}</a>}
    </React.Fragment>)}</div>}
    {(m.suggestions || []).length > 0 && onSend && <div className="chips" style={{ marginTop: 8 }}>{m.suggestions.map((s, k) => <button key={k} className="chip" onClick={() => onSend(s)}>↳ {s}</button>)}</div>}
    <div className="row" style={{ gap: 10, marginTop: 6 }}>
      {m.timing && <span className="faint" style={{ fontSize: 11 }}>⏱ {m.timing.how === 'instant' ? 'instant' : m.timing.how === 'cache' ? 'instant (repeat)' : ((m.timing.total_ms || 0) / 1000).toFixed(1) + 's'}</span>}
      {(m.steps || m.tools || []).length > 0 && <button className="link-btn faint" style={{ fontSize: 11 }} onClick={() => setSteps(s => !s)}>
        {steps ? <ChevronDown size={12} /> : <ChevronRight size={12} />} {m.steps ? `${m.steps.length} step${m.steps.length === 1 ? '' : 's'}` : 'sources'}: {[...new Set((m.steps || []).map(s => s.tool).concat(m.tools || []))].join(', ')}</button>}
    </div>
    {steps && m.steps && <div className="ai-steps">{m.steps.map((s, k) => <div key={k}>{s.ok ? '✓' : '✗'} <b>{s.tool}</b> <span className="mono">{JSON.stringify(s.args)}</span>
      {s.rows != null ? ` → ${s.rows} row(s)` : ''}{s.error ? <span style={{ color: 'var(--bad)' }}> — {s.error}</span> : ''}</div>)}</div>}
  </div>;
}

const QUICK = ['Dashboard of my portfolio this month', 'Chart: paid % by bank and bucket', 'Daily collection trend this month', 'Which cases should I prioritise today?',
  'Overdue PTPs — make an Excel', 'Who changed what in the Audit Log today?', 'My team performance this month — chart', 'How do I upload a DPR file?',
  'Write a polite WhatsApp payment reminder', 'Write an SOP for field visits as a Word file'];

export function AiAssist() {
  const { user } = useAuth();
  const toast = useToast();
  const ui = useClassicUI();
  const { api: capi } = useClassic();
  const [convs, setConvs] = useState([]); const [cid, setCid] = useState(null);
  const [msgs, setMsgs] = useState([]); const [input, setInput] = useState(''); const [busy, setBusy] = useState(false);
  const [st, setSt] = useState(null); const [q, setQ] = useState('');
  const end = useRef(null);
  const loadConvs = () => api('/api/ai/conversations').then(setConvs).catch(() => {});
  const loadSt = () => api('/api/ai/status').then(setSt).catch(e => setSt({ error: e.message }));
  useEffect(() => { loadConvs(); loadSt(); }, []);
  useEffect(() => { end.current && end.current.scrollIntoView({ behavior: 'smooth', block: 'end' }); }, [msgs, busy]);
  const openConv = async (id) => { setCid(id); try { const c = await api('/api/ai/conversations/' + id); setMsgs(c.messages || []); } catch (e) { toast(e.message, 'err'); } };
  const send = async (text) => {
    const t = (text ?? input).trim(); if (!t || busy) return;
    setMsgs(m => [...m, { role: 'user', content: t }]); setInput(''); setBusy(true);
    try {
      const r = await api('/api/ai/chat', { method: 'POST', body: { message: t, conversation_id: cid } });
      setCid(r.conversation_id);
      setMsgs(m => [...m, { role: 'assistant', content: r.reply, files: r.files, actions: r.actions, tools: r.tools, visuals: r.visuals, steps: r.steps, suggestions: r.suggestions, timing: r.timing }]);
      loadConvs(); loadSt();
    } catch (e) { setMsgs(m => [...m, { role: 'assistant', content: '⚠️ ' + e.message }]); } finally { setBusy(false); }
  };
  const confirm = async (a) => { try { await api(`/api/ai/actions/${a.token}/confirm`, { method: 'POST' }); toast('Done ✓'); a.done = true; setMsgs(m => [...m]); } catch (e) { toast(e.message, 'err'); } };
  const del = (c) => { if (!window.confirm('Delete this chat?')) return;
    api('/api/ai/conversations/' + c.id, { method: 'DELETE' }).then(() => { if (c.id === cid) { setCid(null); setMsgs([]); } loadConvs(); }); };
  const xlsx = async (title, rows) => {
    try { const X = capi && capi.getXLSX ? await capi.getXLSX() : window.XLSX; if (!X) throw new Error('Excel library not loaded');
      const wb = X.utils.book_new(); X.utils.book_append_sheet(wb, X.utils.aoa_to_sheet(rows), 'Data'); X.writeFile(wb, (title || 'ai-data').replace(/[\\/:*?"<>|]/g, '') + '.xlsx');
    } catch (e) { toast(e.message, 'err'); }
  };
  const shown = convs.filter(c => !q || (c.title || '').toLowerCase().includes(q.toLowerCase()));
  return (
    <>
      <ModuleHead icon={Sparkles} title="AI Assist" sub={st && !st.error ? `${st.local ? 'On your server · ' : ''}${st.provider_label || st.provider || ''} · ${st.model || ''}` : 'Ask anything about RecoverIQ'} />
      <div className="ai-grid">
        <div className="card ai-side rise">
          <button className="btn primary" style={{ width: '100%' }} onClick={() => { setCid(null); setMsgs([]); }}><Plus />New chat</button>
          <SearchBox value={q} onChange={setQ} placeholder="Search chats" width="100%" />
          <div className="ai-convs">
            {!shown.length && <div className="faint" style={{ fontSize: 12.5, padding: 8 }}>No chats yet.</div>}
            {shown.map(c => <div key={c.id} className={cx('ai-conv', c.id === cid && 'on')} onClick={() => openConv(c.id)}>
              <MessageCircle size={14} /><span className="grow">{c.title}</span>
              <button className="icon-btn sm" title="Delete" onClick={e => { e.stopPropagation(); del(c); }}><Trash2 size={13} /></button></div>)}
          </div>
        </div>
        <div className="card ai-main rise">
          <div className="ai-status faint">{st && !st.error ? <>
            <Bot size={13} /> {st.local ? (st.provider_label || 'Local model') + ' — data stays on your server' : (st.provider_label || st.provider)} · {st.model}
            {st.mask_pii ? ' · phone/account numbers masked' : ''} · {st.used_today}/{st.daily_limit} today
            {st.speed && st.speed.avg_s ? ` · avg ${st.speed.avg_s}s` : ''}
            {!st.configured && <b style={{ color: 'var(--bad)' }}> · not set up: {st.hint}</b>}</> : (st && st.error)}</div>
          <div className="ai-thread">
            {!msgs.length && <div className="ai-empty">
              <div className="mod-ic"><Sparkles /></div>
              <b>Hi {(user.name || '').split(' ')[0]} — what do you need?</b>
              <div className="faint">Cases, PTPs, MIS, team, visits, calls, Audit Log, DPR, legal, settlements, attendance, leave or payslips. Ask for a <b>dashboard</b> or <b>chart</b> and it's drawn here. I only see what you can see.</div>
              <div className="chips" style={{ justifyContent: 'center' }}>{QUICK.map(x => <button key={x} className="chip" onClick={() => send(x)}>{x}</button>)}</div>
            </div>}
            {msgs.map((m, i) => <AiMsg key={i} m={m} xlsx={xlsx} onSend={i === msgs.length - 1 ? send : null} onOpenCase={id => ui.openCase(id)} onConfirm={confirm} />)}
            {busy && <div className="ai-bubble bot typing"><span /><span /><span /></div>}
            <div ref={end} />
          </div>
          <div className="ai-input">
            <input className="input" value={input} onChange={e => setInput(e.target.value)} onKeyDown={e => e.key === 'Enter' && send()}
              placeholder="Ask anything — e.g. ‘Excel of unpaid Axis X-bucket cases with PTP this week’" />
            <button className="btn primary" onClick={() => send()} disabled={busy || !input.trim()}><Send />Send</button>
          </div>
        </div>
      </div>
    </>
  );
}

/* ═════════════════════════════ Services (admin) ═════════════════════════════ */
function Toggle({ on, disabled, onChange }) {
  return <button type="button" className={cx('tgl', on && 'on')} disabled={disabled} onClick={() => onChange(!on)} aria-pressed={on}><i /></button>;
}

function ModelField({ f, v, setV }) {
  const prov = f.key === 'model' ? v.provider : v.fallback_provider;
  const [list, setList] = useState([]); const [busy, setBusy] = useState(false); const [err, setErr] = useState('');
  if (f.key === 'fallback_model' && (!prov || prov === 'none')) return null;
  const load = () => { setBusy(true); setErr('');
    api('/api/ai/providers/models?provider=' + encodeURIComponent(prov)).then(r => { setList(r.models || []); if (!(r.models || []).length) setErr('No models found.'); })
      .catch(e => setErr(e.message + ' — save the key / URL first')).finally(() => setBusy(false)); };
  return <Field label={f.label} hint={list.length ? `${list.length} models — click the box to pick.` : null}>
    <div className="row" style={{ gap: 6 }}>
      <input className="input grow" list={'dl-' + f.key} value={v[f.key] ?? ''} onChange={e => setV({ ...v, [f.key]: e.target.value })} placeholder={prov === 'ollama' ? 'qwen3:4b' : 'provider default'} />
      <button className="btn sm" type="button" disabled={busy} onClick={load}><RefreshCw />{busy ? '…' : 'Load models'}</button>
    </div>
    <datalist id={'dl-' + f.key}>{list.map(m => <option key={m} value={m} />)}</datalist>
    {err && <div style={{ fontSize: 11.5, color: 'var(--bad)' }}>{err}</div>}
  </Field>;
}

function AiTest({ v, saved }) {
  const [res, setRes] = useState(null); const [busy, setBusy] = useState('');
  const dirty = ['provider', 'model', 'local_url', 'custom_url', 'fallback_provider', 'fallback_model'].some(k => (v[k] ?? '') !== (saved[k] ?? ''));
  const run = fb => { setBusy(fb ? 'fb' : 'main'); setRes(null);
    api('/api/ai/providers/test', { method: 'POST', body: { fallback: fb } }).then(r => setRes({ ...r, fb })).catch(e => setRes({ ok: false, detail: e.message, fb })).finally(() => setBusy('')); };
  return <div className="svc-test">
    <div className="row wrap" style={{ gap: 6 }}>
      <b className="row" style={{ gap: 6, fontSize: 12.5 }}><FlaskConical size={14} />Test</b>
      <button className="btn sm" type="button" disabled={!!busy || dirty} onClick={() => run(false)}>{busy === 'main' ? 'Testing…' : 'Test main provider'}</button>
      {saved.fallback_provider && saved.fallback_provider !== 'none' && <button className="btn sm ghost" type="button" disabled={!!busy || dirty} onClick={() => run(true)}>{busy === 'fb' ? 'Testing…' : 'Test backup'}</button>}
      {dirty && <span className="faint" style={{ fontSize: 11.5 }}>Save settings first, then test.</span>}
    </div>
    {res && <div style={{ fontSize: 12.5, marginTop: 6, color: res.ok ? 'var(--good)' : 'var(--bad)' }}>
      {res.ok ? <>✅ {res.provider_label} · {res.model} works — answered in {res.seconds}s{res.local ? ' · data stays on your server' : ' · cloud (masked data)'}. <span className="faint">“{res.answer}”</span></>
        : <>❌ {res.provider_label ? res.provider_label + ' · ' + (res.model || '') + ': ' : ''}{res.detail}</>}</div>}
  </div>;
}

function SvcSettingsForm({ s, onSave }) {
  const [v, setV] = useState({ ...(s.settings || {}) });
  const [keys, setKeys] = useState({}); const [clear, setClear] = useState([]); const [busy, setBusy] = useState(false);
  const sec = s.secrets || {};
  const shown = f => !f.for || f.for.includes(v.provider) || f.for.includes(v.fallback_provider);
  const isAi = s.key === 'ai_assist';
  const save = async () => {
    setBusy(true);
    const ok = await onSave({ settings: v, secrets: Object.fromEntries(Object.entries(keys).filter(([, x]) => (x || '').trim())), clear_secrets: clear });
    setBusy(false); if (ok) { setKeys({}); setClear([]); }
  };
  return <div className="svc-form">
    <div className="svc-fields">
      {s.schema.filter(shown).map(f => {
        if (isAi && (f.key === 'model' || f.key === 'fallback_model')) return <ModelField key={f.key} f={f} v={v} setV={setV} />;
        if (f.type === 'bool') return <label key={f.key} className="svc-bool"><Toggle on={!!v[f.key]} onChange={x => setV({ ...v, [f.key]: x })} /><span>{f.label}</span></label>;
        if (f.type === 'secret') return <Field key={f.key} label={<span className="row" style={{ gap: 4 }}><KeyRound size={12} />{f.label}</span>}>
          <input className="input" type="password" autoComplete="new-password" value={keys[f.key] || ''} onChange={e => setKeys({ ...keys, [f.key]: e.target.value })}
            placeholder={sec[f.key] && sec[f.key].set ? `Saved ${sec[f.key].hint} (${sec[f.key].source === 'env' ? 'from server .env' : 'in app'}) — type to replace` : 'Not set — paste the key'} />
          {sec[f.key] && sec[f.key].source === 'app' && <label className="faint row" style={{ gap: 6, fontSize: 11.5 }}>
            <input type="checkbox" checked={clear.includes(f.key)} onChange={e => setClear(e.target.checked ? [...clear, f.key] : clear.filter(x => x !== f.key))} />Remove the saved key</label>}
        </Field>;
        if (f.type === 'secret_hint') return <div key={f.key} className="faint" style={{ fontSize: 12 }}><KeyRound size={12} /> {f.default}</div>;
        return <Field key={f.key} label={f.label}>
          {f.type === 'select'
            ? <select className="select" value={v[f.key] ?? ''} onChange={e => setV({ ...v, [f.key]: e.target.value })}>{Object.entries(f.options).map(([k, l]) => <option key={k} value={k}>{l}</option>)}</select>
            : <input className="input" type={f.type === 'number' ? 'number' : f.type === 'time' ? 'time' : 'text'} value={v[f.key] ?? ''} onChange={e => setV({ ...v, [f.key]: e.target.value })} />}
        </Field>;
      })}
    </div>
    {isAi && <AiTest v={v} saved={s.settings || {}} />}
    {Object.keys(sec).length > 0 && <div className="faint" style={{ fontSize: 11.5 }}>Keys are stored encrypted, never shown again after saving (only the last 4 characters), and every change is written to the Audit Log.</div>}
    <div><button className="btn primary sm" disabled={busy} onClick={save}><Save />{busy ? 'Saving…' : 'Save settings'}</button></div>
  </div>;
}

export function Services() {
  const { user } = useAuth();
  const toast = useToast();
  const [q, setQ] = useState(''); const [open, setOpen] = useState(null);
  const { data, loading, reload } = useLoad(() => api('/api/services'), []);
  if (user.role !== 'admin') return <><ModuleHead icon={Settings2} title="Services" /><Empty icon={Lock} title="Only Admin can manage services" /></>;
  const list = Array.isArray(data) ? data : (data && data.services) || [];
  const save = async (key, body) => {
    try { await api('/api/services/' + key, { method: 'PUT', body }); toast('Saved'); await reload(); try { window.dispatchEvent(new CustomEvent('riq-services-changed')); } catch (e) { /* ignore */ } return true; }
    catch (e) { toast(e.message, 'err'); return false; }
  };
  const match = s => !q || (s.name + ' ' + s.desc).toLowerCase().includes(q.toLowerCase());
  const groups = [['Core services', list.filter(s => s.group === 'core' && match(s))],
    ['Add-ons', list.filter(s => s.group === 'addon' && !s.reminder && match(s))],
    ['Coming soon', list.filter(s => s.reminder && match(s))]];
  return (
    <>
      <ModuleHead icon={Settings2} title="Services" sub="Turn features on or off for everyone · settings and keys">
        <SearchBox value={q} onChange={setQ} placeholder="Search services" width={240} />
      </ModuleHead>
      <div className="card note-card rise" style={{ marginBottom: 14 }}><Power /><div>Turn a service off and it disappears from everyone's menu and its features stop working until you turn it back on. Data is kept. Core services marked <b>always on</b> are needed for the app to work.</div></div>
      {loading && !data && <div className="svc-grid"><Skeleton h={120} /><Skeleton h={120} /><Skeleton h={120} /></div>}
      {groups.map(([title, items]) => items.length > 0 && <div key={title} style={{ marginBottom: 18 }}>
        <div className="sec-t">{title} · {items.length}</div>
        <div className="svc-grid">{items.map((s, i) => <div key={s.key} className={cx('card svc rise', s.reminder && 'soon', open === s.key && 'open')} style={{ '--i': Math.min(i, 14) }}>
          <div className="row" style={{ alignItems: 'flex-start', gap: 12 }}>
            <span className="svc-ic">{s.icon}</span>
            <div className="grow"><b>{s.name}</b>{s.required && <span className="faint" style={{ fontSize: 11 }}> · always on</span>}
              <div className="cell-sub" style={{ whiteSpace: 'normal' }}>{s.desc}</div></div>
            {s.reminder ? <Pill tone="warn">Coming soon</Pill> : <Toggle on={s.enabled} disabled={s.required} onChange={x => save(s.key, { enabled: x })} />}
          </div>
          {(s.schema || []).length > 0 && !s.reminder && <div style={{ marginTop: 10 }}>
            <button className="btn sm ghost" onClick={() => setOpen(open === s.key ? null : s.key)}><Settings2 />{open === s.key ? 'Hide settings' : 'Settings'}</button>
            {open === s.key && <SvcSettingsForm key={JSON.stringify(s.secrets || {})} s={s} onSave={body => save(s.key, body)} />}
          </div>}
        </div>)}</div>
      </div>)}
    </>
  );
}

/* ═════════════════════════════ Add-ons hub ═════════════════════════════ */
const ADDON_ROLES = {
  ai_assist: null, payments: null, settlement: null, skip_tracing: ['admin', 'headoffice', 'manager', 'teamlead', 'fos', 'telecaller'],
  compliance: ['admin', 'headoffice', 'manager', 'hr'], outreach: ['admin', 'headoffice', 'manager'],
  smart_allocation: ['admin', 'headoffice', 'manager', 'teamlead', 'fos'], legal_notices: ['admin', 'headoffice', 'manager'],
  analytics: ['admin', 'headoffice', 'manager', 'teamlead'], billing: ['admin', 'headoffice'], open_api: ['admin'],
};
export function Addons() {
  const { user } = useAuth();
  const nav = useNavigate();
  const { data, loading } = useLoad(() => api('/api/services'), []);
  const list = (Array.isArray(data) ? data : (data && data.services) || []).filter(s => s.group === 'addon');
  const allowed = s => { const r = ADDON_ROLES[s.key]; return !r || r.includes(user.role); };
  const openAddon = (s) => {
    if (s.key === 'ai_assist') { nav('/ai'); return; }
    nav('/addons/' + s.key);     // native workspace where rebuilt; AddonHost falls back to the classic one
  };
  return (
    <>
      <ModuleHead icon={Puzzle} title="Add-ons" sub="Extra modules switched on by your administrator" />
      {loading && !data && <div className="svc-grid"><Skeleton h={150} /><Skeleton h={150} /><Skeleton h={150} /></div>}
      {data && !list.filter(allowed).length && <Empty icon={Puzzle} title="No add-ons for your role yet" />}
      <div className="addon-grid">{list.filter(allowed).map((s, i) => {
        const usable = s.enabled && !s.reminder;
        return <button key={s.key} type="button" className={cx('card addon rise', !usable && 'off')} style={{ '--i': Math.min(i, 14) }} disabled={!usable} onClick={() => usable && openAddon(s)}>
          <span className="addon-ic">{s.icon}</span>
          <b>{s.name}</b>
          <span className="cell-sub" style={{ whiteSpace: 'normal', minHeight: 34 }}>{s.desc}</span>
          {s.reminder ? <Pill tone="warn">Coming soon — on the roadmap</Pill> : s.enabled ? <span className="addon-go">Open <ChevronRight size={14} /></span>
            : <Pill tone="neutral">Turned off{user.role === 'admin' ? ' — enable in Services' : ' by admin'}</Pill>}
        </button>;
      })}</div>
    </>
  );
}

/* ═════════════════════════════ Connections ═════════════════════════════ */
const parseMap = (txt) => { const m = {}; (txt || '').split(/[\n,]/).forEach(line => { const p = line.split('='); if (p.length === 2 && p[0].trim() && p[1].trim()) m[p[0].trim().toUpperCase()] = p[1].trim(); }); return m; };
const EMPTY_VF = { name: 'ViciDial', base_url: '', vici_user: '', vici_pass: '', campaign_id: '', list_id: '', source: 'recoveriq', phone_code: '91', recording_base: '', branch: '', agent_map: '', dispo_map: '',
  sftp_host: '', sftp_port: '22', sftp_user: '', sftp_pass: '', sftp_base: '', ami_host: '', ami_port: '5038', ami_user: '', ami_secret: '' };

export function Connections() {
  const { user } = useAuth();
  const toast = useToast();
  const ui = useClassicUI();
  const [rows, setRows] = useState(null);
  const [form, setForm] = useState({ name: '', base_url: '', api_key: '', branch: '' });
  const [busy, setBusy] = useState(false);
  const [vf, setVf] = useState(EMPTY_VF); const [vbusy, setVbusy] = useState(false);
  const [camps, setCamps] = useState(null);
  const [dispoUrl, setDispoUrl] = useState(''); const [startCallUrl, setStartCallUrl] = useState('');
  const load = () => api('/api/integration/connections').then(d => setRows(d.connections || [])).catch(() => setRows([]));
  useEffect(() => { load(); }, []);
  useEffect(() => {
    if (camps !== null || !rows) return;
    const v = rows.find(r => r.kind === 'vicidial'); const caps = (v && v.capabilities) || {};
    const lst = (caps.campaigns || []).map(c => ({ ...c }));
    if (!lst.length && caps.campaign_id && caps.list_id) lst.push({ name: caps.campaign_id, bank: '', campaign_id: caps.campaign_id, list_id: caps.list_id });
    setCamps(lst.length ? lst : [{ name: '', bank: '', campaign_id: '', list_id: '' }]);
    const dm = caps.dispo_map || {};
    if (Object.keys(dm).length) setVf(f => f.dispo_map ? f : { ...f, dispo_map: Object.entries(dm).map(([k, x]) => k + '=' + x).join('\n') });
  }, [rows]);
  const setCamp = (i, k, val) => setCamps(cs => cs.map((c, j) => j === i ? { ...c, [k]: val } : c));
  const F = (k) => ({ value: vf[k], onChange: e => setVf({ ...vf, [k]: e.target.value }) });
  const viciConnect = async () => {
    if (!vf.base_url || !vf.vici_user) { toast('ViciDial URL and API user are required', 'err'); return; }
    setVbusy(true);
    try {
      const campaigns = (camps || []).filter(c => (c.campaign_id || '').trim() && (c.list_id || '').trim()); const first = campaigns[0] || {};
      const body = { ...vf, agent_map: parseMap(vf.agent_map), dispo_map: parseMap(vf.dispo_map), recoveriq_base: window.location.origin, campaigns,
        campaign_id: first.campaign_id || vf.campaign_id, list_id: first.list_id || vf.list_id };
      const r = await api('/api/integration/vicidial/connect', { method: 'POST', body });
      setDispoUrl(r.dispo_url || ''); setStartCallUrl(r.start_call_url || ''); await load();
      toast('ViciDial saved — testing the connection…');
      try { const t = await api('/api/integration/vicidial/test', { method: 'POST', body: { cid: r.id } });
        toast(t.ok ? '✓ ViciDial reachable — now paste the URLs into ViciDial (shown below).' : 'Saved, but ViciDial is NOT reachable: ' + (t.detail || 'no response'), t.ok ? 'ok' : 'err');
      } catch (e) { toast('Saved, but the test failed: ' + e.message, 'err'); }
      await load();
    } catch (e) { toast(e.message, 'err'); } finally { setVbusy(false); }
  };
  const add = async () => {
    if (!form.name || !form.base_url || !form.api_key) { toast('Name, URL and key are required', 'err'); return; }
    setBusy(true);
    try { const c = await api('/api/integration/connections', { method: 'POST', body: form });
      setForm({ name: '', base_url: '', api_key: '', branch: '' }); await load();
      api('/api/integration/connections/' + c.id + '/test', { method: 'POST' }).then(load).catch(() => {}); toast('Connection added — testing…');
    } catch (e) { toast(e.message, 'err'); } finally { setBusy(false); }
  };
  const test = (c) => {
    const p = c.kind === 'vicidial' ? api('/api/integration/vicidial/test', { method: 'POST', body: { cid: c.id } }) : api('/api/integration/connections/' + c.id + '/test', { method: 'POST' });
    p.then(r => { toast(r.ok ? 'Reachable ✓' : ('Not reachable' + (r.detail ? ' — ' + r.detail : '')), r.ok ? 'ok' : 'err'); load(); }).catch(e => toast(e.message, 'err'));
  };
  const toggle = (id) => api('/api/integration/connections/' + id + '/toggle', { method: 'POST' }).then(load);
  const del = (id) => { if (window.confirm('Remove this connection?')) api('/api/integration/connections/' + id, { method: 'DELETE' }).then(load); };
  const tone = s => s === 'ok' ? 'good' : s === 'down' ? 'bad' : 'neutral';
  const ro = user.role === 'it_support_view';
  return (
    <>
      <ModuleHead icon={Plug} title="Connections" sub="Autodialer, AI-Voice and your office ViciDial" />

      <Card title="Connected systems" sub={rows ? `${rows.length} connection${rows.length === 1 ? '' : 's'}` : ''} pad={false} className="rise" style={{ marginBottom: 16 }}>
        {rows === null ? <div style={{ padding: 16 }}><Skeleton h={80} /></div> : !rows.length ? <Empty icon={Plug} title="No connections yet">Add your Autodialer or ViciDial below.</Empty> :
          <div className="table-wrap"><table className="t">
            <thead><tr><th>Status</th><th>Name</th><th>URL</th><th>Key</th><th>Branch</th><th>Enabled</th><th /></tr></thead>
            <tbody>{rows.map(c => <tr key={c.id}>
              <td><Pill tone={tone(c.status)} dot>{c.status || 'unknown'}</Pill></td>
              <td><b>{c.name}</b> <span className="faint" style={{ fontSize: 11 }}>{c.kind}</span></td>
              <td className="mono" style={{ fontSize: 12 }}>{c.base_url}</td><td className="mono" style={{ fontSize: 12 }}>{c.api_key_masked}</td>
              <td>{c.branch || '—'}</td><td>{c.enabled ? <Pill tone="good">Yes</Pill> : <Pill tone="neutral">No</Pill>}</td>
              <td><div className="row wrap" style={{ gap: 6, justifyContent: 'flex-end' }}>
                <button className="btn sm" onClick={() => test(c)}><RefreshCw />Test</button>
                {c.kind === 'vicidial' && !ro && <button className="btn sm" disabled={!c.enabled} onClick={() => ui.modal('ViciDialTestCall', { connection: c }).then(load)}><Phone />Test call</button>}
                {c.kind === 'vicidial' && <button className="btn sm ghost" onClick={() => api('/api/integration/vicidial/' + c.id + '/start-call-url').then(r => setStartCallUrl(r.start_call_url)).catch(e => toast(e.message, 'err'))}><Link2 />Start Call URL</button>}
                <button className="btn sm ghost" onClick={() => toggle(c.id)}><Power />{c.enabled ? 'Disable' : 'Enable'}</button>
                <button className="btn sm ghost danger" onClick={() => del(c.id)}><Trash2 /></button>
              </div></td>
            </tr>)}</tbody></table></div>}
      </Card>

      <Card title="Autodialer / AI-Voice" sub="Separate products — RecoverIQ pushes call queues to them and shows their calls / PTPs here. When a dialer is healthy, a Call via dialer button appears on cases." className="rise" style={{ marginBottom: 16 }}>
        <div className="form-grid">
          <Field label="Name"><input className="input" value={form.name} onChange={e => setForm({ ...form, name: e.target.value })} placeholder="Hyderabad dialer" /></Field>
          <Field label="Base URL"><input className="input" value={form.base_url} onChange={e => setForm({ ...form, base_url: e.target.value })} placeholder="https://100.x.y.z:8090" /></Field>
          <Field label="API key (shared secret)"><input className="input" value={form.api_key} onChange={e => setForm({ ...form, api_key: e.target.value })} placeholder="paste the dialer's integration key" /></Field>
          <Field label="Branch (optional)"><input className="input" value={form.branch} onChange={e => setForm({ ...form, branch: e.target.value })} placeholder="leave blank for all branches" /></Field>
        </div>
        <button className="btn primary" onClick={add} disabled={busy || ro}><Plus />{busy ? 'Adding…' : 'Add connection'}</button>
      </Card>

      <Card title="ViciDial (existing office dialer)" sub="Callers keep using Zoiper. Dispositions and recordings come back onto the case automatically. Agents must be logged into the ViciDial agent screen for click-to-call." className="rise">
        <div className="card note-card" style={{ marginBottom: 12 }}><Phone /><div><b>Predictive screen-pop uses push delivery:</b> paste the generated URL into ViciDial's <b>Start Call URL</b> (not Web Form). Enable <code>agent_status</code> (level 7+) for a one-time recovery check on reconnect. Map each employee uniquely and allocate their cases. Start Call URL does not cover manual dialling.</div></div>
        <div className="form-grid">
          <Field label="Name"><input className="input" {...F('name')} /></Field>
          <Field label="ViciDial URL"><input className="input" {...F('base_url')} placeholder="http://192.168.1.50" /></Field>
          <Field label="API user"><input className="input" {...F('vici_user')} placeholder="apiuser (level 8-9, API + Agent API = 1)" /></Field>
          <Field label="API password"><input className="input" type="password" {...F('vici_pass')} placeholder="leave blank to keep existing" /></Field>
          <Field label="Source tag"><input className="input" {...F('source')} /></Field>
          <Field label="Phone code"><input className="input" {...F('phone_code')} /></Field>
          <Field label="Recording URL base (optional)"><input className="input" {...F('recording_base')} placeholder="http://192.168.1.50/RECORDINGS/MP3" /></Field>
          <Field label="Branch (optional)"><input className="input" {...F('branch')} placeholder="leave blank for all branches" /></Field>
        </div>
        <div className="sec-t" style={{ marginTop: 6 }}>Campaigns <span className="faint" style={{ fontWeight: 400, fontSize: 12 }}>· one row per ViciDial campaign (e.g. one per bank), each with its own List ID</span></div>
        <div className="table-wrap"><table className="t">
          <thead><tr><th>Display name</th><th>Bank</th><th>Campaign ID</th><th>List ID</th><th /></tr></thead>
          <tbody>{(camps || []).map((c, i) => <tr key={i}>
            <td><input className="input" value={c.name} onChange={e => setCamp(i, 'name', e.target.value)} placeholder="Axis predictive" /></td>
            <td><input className="input" value={c.bank} onChange={e => setCamp(i, 'bank', e.target.value)} placeholder="AXIS" /></td>
            <td><input className="input" value={c.campaign_id} onChange={e => setCamp(i, 'campaign_id', e.target.value)} placeholder="RIQAXIS" /></td>
            <td><input className="input" value={c.list_id} onChange={e => setCamp(i, 'list_id', e.target.value.replace(/\D/g, ''))} placeholder="5001" /></td>
            <td><button className="icon-btn" type="button" onClick={() => setCamps(cs => cs.filter((_, j) => j !== i))}><X size={14} /></button></td>
          </tr>)}</tbody></table></div>
        <button className="btn sm" type="button" style={{ margin: '8px 0 14px' }} onClick={() => setCamps(cs => [...(cs || []), { name: '', bank: '', campaign_id: '', list_id: '' }])}><Plus />Add campaign</button>
        <div className="sec-t">Recording access over SFTP <span className="faint" style={{ fontWeight: 400, fontSize: 12 }}>· when recordings aren't served over HTTP</span></div>
        <div className="form-grid">
          <Field label="SFTP host"><input className="input" {...F('sftp_host')} placeholder="192.168.75.250" /></Field>
          <Field label="SFTP port"><input className="input" {...F('sftp_port')} /></Field>
          <Field label="SFTP user"><input className="input" {...F('sftp_user')} /></Field>
          <Field label="SFTP password"><input className="input" type="password" {...F('sftp_pass')} placeholder="leave blank to keep existing" /></Field>
          <Field label="Recordings folder"><input className="input" {...F('sftp_base')} placeholder="/home — comma-separate multiple roots" /></Field>
        </div>
        <div className="sec-t">Asterisk manager (AMI) for Hang up <span className="faint" style={{ fontWeight: 400, fontSize: 12 }}>· optional; lets Hang up end a still-ringing call</span></div>
        <div className="form-grid">
          <Field label="AMI host"><input className="input" {...F('ami_host')} /></Field>
          <Field label="AMI port"><input className="input" {...F('ami_port')} /></Field>
          <Field label="AMI user"><input className="input" {...F('ami_user')} /></Field>
          <Field label="AMI secret"><input className="input" type="password" {...F('ami_secret')} placeholder="leave blank to keep existing" /></Field>
        </div>
        <div className="form-grid">
          <Field label="Agent map — RecoverIQ emp code = ViciDial agent (one per line)"><textarea className="input" rows={4} {...F('agent_map')} placeholder={'TC001=8001\nTC002=8002'} /></Field>
          <Field label="Disposition map — RecoverIQ disposition = ViciDial status" hint="Every status here must exist in your campaign (max 6 characters).">
            <textarea className="input" rows={4} {...F('dispo_map')} placeholder={'PAID=SALE\nPTP=CALLBK\nRTP=NI\nRNR=N\nBUSY=B'} /></Field>
        </div>
        <button className="btn primary" onClick={viciConnect} disabled={vbusy || ro}><Save />{vbusy ? 'Saving…' : 'Save ViciDial connection'}</button>
        {startCallUrl && <div className="card note-card" style={{ marginTop: 12, display: 'block' }}><b>Paste into ViciDial → Campaign → Start Call URL</b>
          <div className="faint" style={{ fontSize: 12, margin: '4px 0 6px' }}>Keep the VAR prefix. This URL contains a secret — don't share it or put it in screenshots.</div>
          <textarea className="input mono" rows={3} readOnly value={startCallUrl} onFocus={e => e.target.select()} /></div>}
        {dispoUrl && <div className="card note-card" style={{ marginTop: 12, display: 'block' }}><b>Paste into ViciDial → Campaign → Dispo Call URL</b>
          <div className="faint" style={{ fontSize: 12, margin: '4px 0 6px' }}>Sends the disposition and recording filename back to RecoverIQ after every call.</div>
          <textarea className="input mono" rows={3} readOnly value={dispoUrl} onFocus={e => e.target.select()} /></div>}
      </Card>
    </>
  );
}

/* ═════════════════════════════ Salary & Payslips (locked) ═════════════════════════════ */
export function SalaryLocked() {
  return (
    <>
      <ModuleHead icon={Lock} title="Salary & Payslips" sub="Section locked" />
      <div className="card locked-card rise">
        <div className="mod-ic lg"><Lock /></div>
        <b>Salary &amp; Payslips — section locked</b>
        <div className="faint">This section is not enabled yet. It will be unlocked by the administrator.</div>
      </div>
    </>
  );
}

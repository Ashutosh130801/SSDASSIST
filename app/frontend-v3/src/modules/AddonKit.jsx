// Shared building blocks for the native add-on workspaces (tables, stats, tabs, prompts) — all theme-token based.
import React, { useState } from 'react';
import { AlertTriangle } from 'lucide-react';
import { Card, Skeleton, Empty, useLoad, useToast } from '../components/ui.jsx';
import { Modal, Field, Metric } from './kit.jsx';
import { cx, fmtDate, fmtTime } from '../lib/format.js';

export const fmtDT = (v) => (v ? `${fmtDate(v)} ${fmtTime(v)}` : '—');
export const INR = (v) => '₹' + Math.round(Number(v) || 0).toLocaleString('en-IN');
export const INR2 = (v) => '₹' + (Number(v) || 0).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 });

/** Loader wrapper: { data, error, loading, reload } with shared skeleton + error card. */
export function useAd(fn, deps = []) { return useLoad(fn, deps); }

export function AdState({ q, children, h = 160 }) {
  if (q.error) return <Card className="rise"><div className="row" style={{ gap: 8, color: 'var(--bad)' }}><AlertTriangle size={16} />{q.error}</div></Card>;
  if (!q.data) return <Skeleton h={h} style={{ borderRadius: 16 }} />;
  return children(q.data);
}

export function AdTabs({ tabs, cur, set }) {
  return <div className="seg ad-tabs" role="tablist">{tabs.map(([k, l]) =>
    <button key={k} role="tab" aria-selected={cur === k} className={cx(cur === k && 'on')} onClick={() => set(k)}>{l}</button>)}</div>;
}

export function AdTable({ cols, rows, empty = 'Nothing here yet.', max = 400, maxH = 'calc(100vh - 330px)', rowClass }) {
  if (!rows || !rows.length) return <Empty title={empty} />;
  return <div className="table-wrap ad-table" style={{ maxHeight: maxH }}><table className="t">
    <thead><tr>{cols.map(([, l, , o], j) => <th key={j} className={o && o.num ? 'num' : ''}>{l}</th>)}</tr></thead>
    <tbody>{rows.slice(0, max).map((r, i) => <tr key={r.id ?? i} className={rowClass ? rowClass(r) : ''}>{cols.map(([k, , f, o], j) =>
      <td key={j} className={o && o.num ? 'num' : ''}>{f ? f(r[k], r) : (r[k] ?? '')}</td>)}</tr>)}</tbody></table>
    {rows.length > max && <div className="faint" style={{ padding: 8, fontSize: 12 }}>Showing first {max} of {rows.length}.</div>}
  </div>;
}

export const AdStats = ({ items }) => <div className="metric-g ad-stats">{items.filter(Boolean).map(([label, value, tone, sub], i) =>
  <Metric key={i} label={label} value={value} tone={tone} sub={sub} />)}</div>;

export const AdNote = ({ children }) => <div className="ad-note">{children}</div>;

/** Promise-based text prompt in a themed modal (replaces window.prompt). */
export function usePrompt() {
  const [p, setP] = useState(null);
  const ask = (title, opts = {}) => new Promise(res => setP({ title, ...opts, value: opts.value || '', res }));
  const close = (v) => { const r = p && p.res; setP(null); r && r(v); };
  const el = p ? <Modal open onClose={() => close(null)} title={p.title} sub={p.sub} width={440}
    footer={<><span className="grow" /><button className="btn ghost" onClick={() => close(null)}>Cancel</button>
      <button className={cx('btn', p.danger ? 'danger' : 'primary')} disabled={p.must && p.value.trim() !== p.must} onClick={() => close(p.value)}>{p.ok || 'OK'}</button></>}>
    <Field label={p.label || ''} hint={p.must ? `Type ${p.must} to confirm` : p.hint}>
      {p.multiline ? <textarea className="input" rows={3} autoFocus value={p.value} onChange={e => setP({ ...p, value: e.target.value })} />
        : <input className="input" autoFocus value={p.value} onChange={e => setP({ ...p, value: e.target.value })} onKeyDown={e => { if (e.key === 'Enter' && (!p.must || p.value.trim() === p.must)) close(p.value); }} />}
    </Field>
  </Modal> : null;
  return [ask, el];
}

/** Themed confirm (replaces window.confirm). */
export function useConfirm() {
  const [c, setC] = useState(null);
  const ask = (title, sub, opts = {}) => new Promise(res => setC({ title, sub, ...opts, res }));
  const close = (v) => { const r = c && c.res; setC(null); r && r(v); };
  const el = c ? <Modal open onClose={() => close(false)} title={c.title} width={420}
    footer={<><span className="grow" /><button className="btn ghost" onClick={() => close(false)}>Cancel</button>
      <button className={cx('btn', c.danger ? 'danger' : 'primary')} onClick={() => close(true)}>{c.ok || 'Confirm'}</button></>}>
    {c.sub && <div style={{ fontSize: 13.5, color: 'var(--text-2)' }}>{c.sub}</div>}
  </Modal> : null;
  return [ask, el];
}

export function useErr() { const toast = useToast(); return (e) => toast((e && e.message) || String(e), 'err'); }

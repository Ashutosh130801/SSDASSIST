// Shared building blocks for the natively redesigned modules. The same files ship in
// frontend-v2 / v3 / v4 — each template's stylesheet (glass / clay / spatial) gives them their look.
import React, { useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { Link } from 'react-router-dom';
import { Maximize2, Phone, MessageCircle, Navigation, Search, X } from 'lucide-react';
import { useClassic } from '../lib/classic.jsx';
import { api } from '../lib/api.js';
import { cx, initials } from '../lib/format.js';

/** Dropdown layer: drawn on top of everything (portaled to <body>, fixed to its button) so cards, tables and
 *  animated panels can never hide or clip it. Flips upward when there's no room below. */
export function PopLayer({ onClose, className = '', style, align = 'left', children, onClick }) {
  const mark = useRef(null); const menu = useRef(null);
  const [pos, setPos] = useState(null);
  useEffect(() => {
    const place = () => {
      const a = mark.current && (mark.current.closest('.pop-wrap') || mark.current.parentElement); if (!a) return;
      const r = a.getBoundingClientRect(); const vw = window.innerWidth, vh = window.innerHeight;
      const m = menu.current; const mw = m ? m.offsetWidth : 240; const mh = m ? m.scrollHeight : 300;
      const below = vh - r.bottom - 12, above = r.top - 12;
      const up = mh > below && above > below;
      const maxH = Math.max(160, Math.min(up ? above : below, vh - 24));
      let left = align === 'right' ? r.right - mw : r.left;
      left = Math.max(8, Math.min(left, vw - mw - 8));
      setPos(up ? { left, bottom: vh - r.top + 6, maxHeight: maxH } : { left, top: r.bottom + 6, maxHeight: maxH });
    };
    place(); const t = requestAnimationFrame(place);
    window.addEventListener('resize', place); window.addEventListener('scroll', place, true);
    return () => { cancelAnimationFrame(t); window.removeEventListener('resize', place); window.removeEventListener('scroll', place, true); };
  }, [align]);
  const { right, left: _l, ...rest } = style || {};
  return <>
    <span ref={mark} style={{ display: 'none' }} />
    {createPortal(<>
      <div className="pop-scrim portal" onClick={(e) => { e.stopPropagation(); onClose && onClose(); }} />
      <div ref={menu} data-v2-overlay className={cx('pop-menu portal', className)} onClick={onClick}
        style={{ ...rest, ...(pos || { left: -9999, top: 0 }), overflowY: 'auto' }}>{children}</div>
    </>, document.body)}
  </>;
}

/** Re-run `fn` whenever data changes anywhere (same WebSocket + local events the classic app uses). */
export function useLive(fn) {
  const classic = useClassic();
  const ref = useRef(fn); ref.current = fn;
  useEffect(() => {
    const a = classic.api;
    if (!a || !a.subscribe) return undefined;
    return a.subscribe(() => ref.current && ref.current());
  }, [classic.api]);
}

/** Page header: icon tile, title, subtitle, actions, and a link to the complete classic module. */
export function ModuleHead({ icon: Icon, title, sub, children, full }) {
  return (
    <div className="page-head rise mod-head">
      {Icon && <span className="mod-ic"><Icon /></span>}
      <div className="grow"><h1 className="page-title">{title}</h1>{sub && <div className="page-sub">{sub}</div>}</div>
      <div className="row wrap" style={{ gap: 8 }}>
        {children}
      </div>
    </div>
  );
}

/** Small chip-style filter group (wraps; "on" chip is highlighted by each theme). */
export function Chips({ value, onChange, options, label }) {
  return (
    <div className="chips">
      {label && <span className="chips-l">{label}</span>}
      {options.map(([v, l, n]) => (
        <button key={String(v)} type="button" className={cx('chip', value === v && 'on')} onClick={() => onChange(v)}>
          {l}{n != null && <span className="chip-n">{n}</span>}
        </button>
      ))}
    </div>
  );
}

export const MONTHS = [['current', 'This month'], ['next', 'Next month'], ['last', 'Last month']];

/** Centered modal, portaled above the classic layer. */
export function Modal({ open, onClose, title, sub, children, footer, width = 520 }) {
  useEffect(() => {
    if (!open) return undefined;
    const k = (e) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', k);
    return () => window.removeEventListener('keydown', k);
  }, [open, onClose]);
  if (!open) return null;
  return createPortal(<>
    <div className="scrim" onClick={onClose} />
    <div className="modal-v" data-v2-overlay role="dialog" aria-modal="true" style={{ maxWidth: width }}>
      <div className="modal-h row">
        <div className="grow"><div className="card-t">{title}</div>{sub && <div className="card-s">{sub}</div>}</div>
        <button className="icon-btn" aria-label="Close" onClick={onClose}><X /></button>
      </div>
      <div className="modal-b">{children}</div>
      {footer && <div className="modal-f row">{footer}</div>}
    </div>
  </>, document.body);
}

export const Field = ({ label, children, hint }) => (
  <label className="fld"><span className="fld-l">{label}</span>{children}{hint && <span className="fld-h">{hint}</span>}</label>
);

/** Progress bar 0–100 with tone. */
export function Bar({ pct, tone = 'accent', h = 8 }) {
  const v = Math.max(0, Math.min(100, Number(pct) || 0));
  return <div className={cx('pbar', 'tone-' + tone)} style={{ height: h }}><i style={{ width: v + '%' }} /></div>;
}

export const Avatar = ({ name, size = 34, tone }) => (
  <span className={cx('av', tone && 'av-' + tone)} style={{ width: size, height: size, fontSize: size * .38 }}>{initials(name)}</span>
);

/** Mini metric tile (used inside cards). */
export const Metric = ({ label, value, sub, tone }) => (
  <div className={cx('metric', tone && 'm-' + tone)}>
    <div className="metric-l">{label}</div>
    <div className="metric-v num">{value}</div>
    {sub && <div className="metric-s">{sub}</div>}
  </div>
);

const tel = (p) => String(p || '').replace(/[^0-9+]/g, '');
export const waHref = (p, text) => { let d = String(p || '').replace(/\D/g, ''); if (d.length === 10) d = '91' + d; return 'https://wa.me/' + d + (text ? '?text=' + encodeURIComponent(text) : ''); };
export const navHref = (c) => {
  if (!c) return null;
  if (c.latitude != null && c.longitude != null) return `https://www.google.com/maps/dir/?api=1&destination=${c.latitude},${c.longitude}`;
  const a = [c.address, c.pincode].filter(Boolean).join(', ');
  return a ? 'https://www.google.com/maps/dir/?api=1&destination=' + encodeURIComponent(a) : null;
};

/** Call (ViciDial when connected, else phone dialer) + WhatsApp. */
export function ContactBtns({ phone, caseId, compact }) {
  const { api: capi } = useClassic();
  const [vici, setVici] = useState(false);
  const [open, setOpen] = useState(false);
  useEffect(() => {
    let on = true;
    if (caseId && capi && capi.dialerStatus) Promise.resolve(capi.dialerStatus()).then(s => on && setVici(!!(s && (s.connected || s.vicidial || s === true)))).catch(() => {});
    return () => { on = false; };
  }, [capi, caseId]);
  if (!phone) return null;
  return <>
    <span className="pop-wrap">
      <button type="button" className="btn sm" title={'Call ' + phone} onClick={(e) => { e.stopPropagation(); if (vici) setOpen(o => !o); else window.location.href = 'tel:' + tel(phone); }}>
        <Phone />{!compact && 'Call'}
      </button>
      {open && <>
        <PopLayer onClose={() => setOpen(false)} onClick={e => e.stopPropagation()}>
          <button className="btn sm primary block" onClick={() => { setOpen(false); capi.dialCase(caseId); }}>Call via ViciDial</button>
          <a className="btn sm ghost block" href={'tel:' + tel(phone)} onClick={() => setOpen(false)}>Phone dialer</a>
        </PopLayer>
      </>}
    </span>
    <a className="btn sm wa" href={waHref(phone)} target="_blank" rel="noreferrer" onClick={e => e.stopPropagation()} title="WhatsApp"><MessageCircle />{!compact && 'WhatsApp'}</a>
  </>;
}

export function NavBtn({ c }) {
  const h = navHref(c);
  if (!h) return null;
  return <a className="btn sm" href={h} target="_blank" rel="noreferrer" onClick={e => e.stopPropagation()}><Navigation />Navigate</a>;
}

/** Open a classic form/panel (visit camera, staff editor, profile…). Resolves true when saved. */
export function usePanel() {
  const { api: capi } = useClassic();
  return (kind, props) => (capi && capi.openPanel ? capi.openPanel(kind, props) : Promise.resolve(false));
}

// SVG chart attributes don't resolve CSS variables reliably, so read the live token values.
export const cssVar = (n) => (getComputedStyle(document.documentElement).getPropertyValue(n) || '').trim() || '#2563eb';
export const chartColor = (i) => cssVar(`--chart-${(i % 6) + 1}`);
export function ChartTip({ active, payload, label, fmt }) {
  if (!active || !payload || !payload.length) return null;
  return (
    <div className="card chart-tip">
      <div className="faint" style={{ marginBottom: 4 }}>{label}</div>
      {payload.map(p => <div key={p.dataKey} className="row" style={{ gap: 8 }}>
        <span style={{ width: 8, height: 8, borderRadius: 4, background: p.color }} /> {p.name}: <b>{fmt ? fmt(p.value) : p.value}</b></div>)}
    </div>
  );
}

/** Live presence for a set of user ids → { [id]: {state, platform, last_seen, idle_seconds} } (refreshes every 45s). */
export function usePresence(ids) {
  const key = (ids || []).filter(Boolean).join(',');
  const [map, setMap] = useState({});
  useEffect(() => {
    if (!key) return undefined;
    let stop = false;
    const load = () => fetchPresence(key).then(m => { if (!stop) setMap(m || {}); }).catch(() => {});
    load(); const t = setInterval(load, 45000);
    return () => { stop = true; clearInterval(t); };
  }, [key]);
  return map;
}
const fetchPresence = (key) => api('/api/attendance/presence?ids=' + key);

export function Presence({ p }) {
  if (!p) return null;
  const plat = p.platform === 'android' ? 'mobile' : p.platform === 'ios' ? 'iPhone' : 'web';
  const label = p.state === 'active' ? 'Active on ' + plat : p.state === 'idle' ? 'Idle' : 'Offline';
  return <span className={cx('presence', 'p-' + (p.state || 'offline'))}><i />{label}</span>;
}

/** Search box with icon. */
export function SearchBox({ value, onChange, placeholder = 'Search…', onEnter, width = 320 }) {
  return (
    <div className="input-icon" style={{ width, maxWidth: '100%' }}>
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="11" cy="11" r="7" /><path d="m20 20-3.5-3.5" /></svg>
      <input className="input" value={value} placeholder={placeholder} onChange={e => onChange(e.target.value)}
        onKeyDown={e => { if (e.key === 'Enter' && onEnter) onEnter(); }} />
    </div>
  );
}

/** Multi-select dropdown chip (checkbox list). options: [{value,label}] */
export function MultiSelect({ label, icon: Icon, options, selected, onChange, width = 220 }) {
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState('');
  const sel = selected || [];
  const toggle = (v) => onChange(sel.includes(v) ? sel.filter(x => x !== v) : [...sel, v]);
  const ql = q.trim().toLowerCase();
  const searchable = (options || []).length > 6;          // type-to-search on long lists (FOS / callers …)
  const shown = ql ? (options || []).filter(o => String(o.label || '').toLowerCase().includes(ql) || String(o.value || '').toLowerCase().includes(ql)) : (options || []);
  const close = () => { setOpen(false); setQ(''); };
  return (
    <span className="pop-wrap">
      <button type="button" className={cx('chip', sel.length > 0 && 'on')} onClick={() => setOpen(o => !o)}>
        {Icon && <Icon size={13} />}{label}{sel.length ? ` · ${sel.length}` : ''}<span style={{ opacity: .6 }}>▾</span>
      </button>
      {open && <>
        <PopLayer onClose={close} className="ms-menu" style={{ minWidth: width }}>
          <div className="ms-head">
            <div className="row" style={{ marginBottom: 4 }}><b className="grow" style={{ fontSize: 12 }}>{label}</b>
              {ql && shown.length > 0 && <button className="btn sm ghost" onClick={() => onChange([...new Set([...sel, ...shown.map(o => o.value)])])}>Select shown</button>}
              {sel.length > 0 && <button className="btn sm ghost" onClick={() => onChange([])}>Clear</button>}</div>
            {searchable && <div className="ms-search"><Search size={14} /><input autoFocus value={q} onChange={e => setQ(e.target.value)}
              onKeyDown={e => { if (e.key === 'Escape') close(); }} placeholder={'Search ' + String(label || '').toLowerCase() + ' name / ID…'} /></div>}
          </div>
          {(!options || !options.length) && <div className="faint" style={{ fontSize: 12 }}>None available</div>}
          {options && options.length > 0 && !shown.length && <div className="faint" style={{ fontSize: 12, padding: '4px 2px' }}>No match for “{q}”</div>}
          {shown.map(o => (
            <label key={String(o.value)} className="ms-opt"><input type="checkbox" checked={sel.includes(o.value)} onChange={() => toggle(o.value)} /><span>{o.label}</span></label>
          ))}
        </PopLayer>
      </>}
    </span>
  );
}

/** Open a printable window with one or more tables. tables: [[title, headers[], rows2d[][]]] */
export function printTables(docTitle, tables) {
  const w = window.open('', '_blank'); if (!w) return;
  const esc = (s) => String(s == null ? '' : s).replace(/[&<>]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;' }[c]));
  let html = '<html><head><title>' + esc(docTitle) + '</title><style>body{font-family:system-ui;padding:20px}h1{font-size:18px}h2{color:#2563EB;margin:16px 0 6px;font-size:14px}table{border-collapse:collapse;width:100%;font-size:11px;margin-bottom:12px}th,td{border:1px solid #cbd5e1;padding:4px 7px;text-align:left}th{background:#EEF3FB}</style></head><body><h1>' + esc(docTitle) + '</h1>';
  tables.forEach(([t, h, rows]) => { html += '<h2>' + esc(t) + '</h2><table><thead><tr>' + h.map(x => '<th>' + esc(x) + '</th>').join('') + '</tr></thead><tbody>' + rows.map(r => '<tr>' + r.map(c => '<td>' + esc(c) + '</td>').join('') + '</tr>').join('') + '</tbody></table>'; });
  w.document.write(html + '</body></html>'); w.document.close(); w.focus(); setTimeout(() => { try { w.print(); } catch (e) { /* ignore */ } }, 400);
}

/** Helpers that open the classic app's own forms/panels INSIDE the new UI (themed overlays). */
export function useClassicUI() {
  const { api: capi } = useClassic();
  const open = (kind, props) => (capi && capi.openPanel ? capi.openPanel(kind, props) : Promise.resolve(false));
  return {
    ready: !!capi,
    /** A classic modal component by name (UploadModal, DprModal, …). Resolves with its onDone value / true / false. */
    modal: (name, props) => open('component', { name, props }),
    /** A classic inline component shown inside a themed modal shell. */
    inline: (name, props, title, width) => open('inline', { name, props, title, width }),
    /** A row of classic tool buttons (each brings its own dialog). */
    tools: (names, title) => open('tools', { names, title }),
    openCase: (id) => capi && capi.openCase && capi.openCase(id),
    perf: (id, role, name, peer) => capi && capi.openPerf && capi.openPerf(id, role, name, peer),
  };
}

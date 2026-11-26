// Shared building blocks for the natively redesigned modules. The same files ship in
// frontend-v2 / v3 / v4 — each template's stylesheet (glass / clay / spatial) gives them their look.
import React, { useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { Link } from 'react-router-dom';
import { Maximize2, Phone, MessageCircle, Navigation, X } from 'lucide-react';
import { useClassic } from '../lib/classic.jsx';
import { api } from '../lib/api.js';
import { cx, initials } from '../lib/format.js';

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
        {full && <Link className="btn" to={'/m/' + full} title="Open the complete classic module"><Maximize2 />Full module</Link>}
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
        <div className="pop-scrim" onClick={(e) => { e.stopPropagation(); setOpen(false); }} />
        <div className="pop-menu" onClick={e => e.stopPropagation()}>
          <button className="btn sm primary block" onClick={() => { setOpen(false); capi.dialCase(caseId); }}>Call via ViciDial</button>
          <a className="btn sm ghost block" href={'tel:' + tel(phone)} onClick={() => setOpen(false)}>Phone dialer</a>
        </div>
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

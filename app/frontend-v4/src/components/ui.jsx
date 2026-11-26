import React, { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { Inbox, X } from 'lucide-react';
import { cx } from '../lib/format.js';
import { CountUp, Spark, Tilt } from './fx.jsx';

export function Card({ title, sub, actions, children, className, pad = true, hero = false, style }) {
  return (
    <section className={cx('card', hero && 'hero-card', className)} style={style}>
      {(title || actions) && (
        <header className="card-h">
          <div className="grow"><div className="card-t">{title}</div>{sub && <div className="card-s">{sub}</div>}</div>
          {actions}
        </header>
      )}
      <div className={pad ? 'card-pad' : ''}>{children}</div>
    </section>
  );
}

export function Kpi({ label, value, sub, icon: Icon, delta, tone = 'accent', spark, format, i = 0, tilt = true }) {
  const body = (
    <div className={cx('card kpi clay', 'tone-' + tone)}>
      <div className="kpi-l">{Icon && <span className="ic"><Icon /></span>}{label}</div>
      {spark && <Spark data={spark} />}
      <div className="kpi-v">{format && typeof value === 'number' ? <CountUp value={value} format={format} /> : value}</div>
      <div className="row" style={{ gap: 8, marginTop: 4 }}>
        {delta != null && <span className={cx('delta', delta >= 0 ? 'up' : 'down')}>{delta >= 0 ? '▲' : '▼'} {Math.abs(delta).toFixed(1)}%</span>}
        {sub && <span className="kpi-s">{sub}</span>}
      </div>
    </div>
  );
  return <div className="rise" style={{ '--i': i }}>{tilt ? <Tilt>{body}</Tilt> : body}</div>;
}

export const Pill = ({ tone = 'neutral', dot = false, children, title }) => (
  <span className={cx('pill', tone)} title={title}>{dot && <span className="dot" />}{children}</span>
);

/** Payment / case status → pill tone. */
export function StatusPill({ value }) {
  const v = String(value || '').toUpperCase();
  const tone = v === 'PAID' ? 'good' : v === 'PARTIAL' ? 'warn' : v.includes('PTP') ? 'info'
    : (v === 'RTP' || v === 'UNPAID' || v === 'ABSENT') ? 'bad' : v ? 'neutral' : 'neutral';
  return <Pill tone={tone} dot>{v || '—'}</Pill>;
}

export function Seg({ value, onChange, options }) {
  return (
    <div className="seg" role="tablist">
      {options.map(([v, l]) => <button key={v} role="tab" aria-selected={value === v} className={cx(value === v && 'on')} onClick={() => onChange(v)}>{l}</button>)}
    </div>
  );
}

export const Skeleton = ({ h = 16, w = '100%', style }) => <div className="skel" style={{ height: h, width: w, ...style }} />;

export function Empty({ icon: Icon = Inbox, title = 'Nothing here yet', children }) {
  return <div className="empty"><Icon /><div style={{ fontWeight: 600, color: 'var(--text-2)' }}>{title}</div>{children && <div style={{ marginTop: 4 }}>{children}</div>}</div>;
}

export function Drawer({ open, onClose, header, children, width }) {
  useEffect(() => {
    if (!open) return undefined;
    const k = (e) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', k);
    return () => window.removeEventListener('keydown', k);
  }, [open, onClose]);
  if (!open) return null;
  // Portal: always above the embedded classic layer and any animated (transformed) page wrapper.
  return createPortal(<>
    <div className="scrim" onClick={onClose} />
    <aside className="drawer" data-v2-overlay style={width ? { width } : undefined} role="dialog" aria-modal="true">
      <div className="drawer-h row">
        <div className="grow">{header}</div>
        <button className="icon-btn" aria-label="Close" onClick={onClose}><X /></button>
      </div>
      <div className="drawer-b">{children}</div>
    </aside>
  </>, document.body);
}

/* ── Toasts ── */
const ToastCtx = createContext(() => {});
export const useToast = () => useContext(ToastCtx);
export function ToastProvider({ children }) {
  const [t, setT] = useState(null);
  const timer = useRef(null);
  const show = useCallback((msg, kind) => {
    setT({ msg, kind }); clearTimeout(timer.current);
    timer.current = setTimeout(() => setT(null), 3200);
  }, []);
  return <ToastCtx.Provider value={show}>{children}{t && <div className={cx('toast', t.kind === 'err' && 'err')}>{t.msg}</div>}</ToastCtx.Provider>;
}

/** Load data with loading/error state; re-runs when deps change. */
export function useLoad(fn, deps) {
  const [state, setState] = useState({ data: null, error: null, loading: true });
  const [tick, setTick] = useState(0);
  useEffect(() => {
    let alive = true;
    setState(s => ({ ...s, loading: true, error: null }));
    Promise.resolve().then(fn).then(
      d => alive && setState({ data: d, error: null, loading: false }),
      e => alive && setState({ data: null, error: e.message || 'Could not load', loading: false }));
    return () => { alive = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, tick]);
  return { ...state, reload: () => setTick(t => t + 1) };
}

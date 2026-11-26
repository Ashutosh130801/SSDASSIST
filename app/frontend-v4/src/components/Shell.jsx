import React, { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { NavLink, useLocation, useNavigate } from 'react-router-dom';
import {
  Search, Sun, Moon, PanelLeftClose, PanelLeftOpen, Bell, LogOut, Repeat, Menu as MenuIcon, ChevronRight,
  Command, Sparkles, Monitor, Layers3, Box, Palette, Printer, Download, Apple, MonitorDown, Compass, Check, Circle, Settings2, Puzzle,
} from 'lucide-react';
import { useAuth } from '../lib/auth.jsx';
import { useClassic } from '../lib/classic.jsx';
import { ICONS, LABELS, routeFor, nativeFor, topExtras, titleOf } from '../lib/nav.js';
import { PALETTES } from '../lib/palettes.js';
import { cx, initials, roleName, fmtDate, fmtTime } from '../lib/format.js';
import { EDITIONS, setEdition } from '../lib/edition.js';
import { api } from '../lib/api.js';
import BrandMark from './BrandMark.jsx';
import { RecoverIQMark } from './RecoverIQLogo.jsx';

/** App frame shared by both editions — the look differs through tokens + palette + edition CSS. */
export default function Shell({ edition, mode, onMode, palette, onPalette, sections, children }) {
  const { user, logout, switchView, config } = useAuth();
  const classic = useClassic();
  const [collapsed, setCollapsed] = useState(() => { try { return localStorage.getItem('riq_v4_collapsed') === '1'; } catch { return false; } });
  const [mobile, setMobile] = useState(false);
  const [palette_, setPaletteOpen] = useState(false);
  const loc = useLocation();
  const navigate = useNavigate();
  const premium = edition === 'premium';
  const native = nativeFor(user);

  useEffect(() => { try { localStorage.setItem('riq_v4_collapsed', collapsed ? '1' : '0'); } catch { /* ignore */ } }, [collapsed]);
  useEffect(() => { setMobile(false); }, [loc.pathname]);
  useEffect(() => {
    const k = (e) => { if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') { e.preventDefault(); setPaletteOpen(p => !p); } };
    window.addEventListener('keydown', k);
    return () => window.removeEventListener('keydown', k);
  }, []);

  const currentId = (() => { const p = loc.pathname.split('/').filter(Boolean); return p[0] === 'm' ? p[1] : (p[0] || 'dashboard'); })();
  const current = titleOf(currentId, sections);
  const brand = (config && config.brand_name) || 'RecoverIQ';
  const go = (id) => navigate(routeFor(id, native));
  const extras = topExtras(user);

  return (
    <div className={cx('app', collapsed && 'collapsed', mobile && 'mobile-open')}>
      <aside className="side">
        <div className="side-brand">
          <RecoverIQMark size={38} />
          <div className="txt">
            <div className="n riq-name">Recover<b>IQ</b></div>
            <div className="s">{user && user.ho_manager ? 'Head Office Manager' : roleName(user && user.role)}</div>
          </div>
        </div>
        {(user && (user.available_views || []).length > 1) && (
          <ViewSwitch user={user} onSwitch={switchView} />
        )}
        <div className="side-scroll">
          {sections.map(sec => (
            <div className="side-sec" key={sec.title}>
              <div className="side-sec-t">{sec.title}</div>
              {sec.items.map(it => <NavItem key={it.id} it={it} />)}
            </div>
          ))}
        </div>
        <div className="side-foot">
          <div className="by-ssd" title="SSD Enterprises"><BrandMark size={22} /><span className="txt">by SSD Enterprises</span></div>
          <a className="nav-i" href="/" title="Back to the classic RecoverIQ">
            <Monitor /><span className="lbl txt">Classic interface</span>
          </a>
          <a className="nav-i" href="/v2/" title="Switch template"><Sparkles /><span className="lbl txt">Aurora Glass (v2)</span></a>
          <a className="nav-i" href="/v3/" title="Switch template"><Layers3 /><span className="lbl txt">Soft Clay (v3)</span></a>
          <button className="nav-i" onClick={() => setCollapsed(c => !c)} aria-label="Collapse sidebar">
            {collapsed ? <PanelLeftOpen /> : <PanelLeftClose />}<span className="lbl txt">Collapse</span>
          </button>
        </div>
      </aside>

      <div className="main">
        <header className="top">
          <button className="icon-btn show-sm" aria-label="Menu" onClick={() => setMobile(m => !m)}><MenuIcon /></button>
          <div className="crumbs hide-sm"><span>{brand}</span><ChevronRight size={14} /><b>{current}</b></div>
          <div className="grow" />
          <button className="search-trigger" onClick={() => setPaletteOpen(true)}>
            <Search size={16} /><span className="grow hide-sm" style={{ textAlign: 'left' }}>Search accounts, pages…</span>
            <span className="kbd hide-sm"><Command size={10} style={{ verticalAlign: -1 }} />K</span>
          </button>
          <div className="row top-tools" style={{ gap: 2 }}>
            {extras.map(id => {
              const I = ICONS[id] || Circle;
              return <button key={id} className={cx('icon-btn', currentId === id && 'on')} title={LABELS[id]} aria-label={LABELS[id]} onClick={() => go(id)}><I /></button>;
            })}
            {user && user.role === 'fos' && classic.api && <button className="icon-btn" title="Print my beat-sheet (liner)" onClick={() => classic.api.printLiner()}><Printer /></button>}
            <button className={cx('icon-btn', currentId === 'addons' && 'on')} title="Add-ons — extra modules" onClick={() => go('addons')}><Puzzle /></button>
            {user && user.role === 'admin' && <button className={cx('icon-btn', currentId === 'services' && 'on')} title="Services — turn features on/off and set them up" onClick={() => go('services')}><Settings2 /></button>}
          </div>
          <span className="top-sep" />
          <PalettePicker value={palette} onChange={onPalette} />
          <Notifications />
          <UserMenu user={user} onLogout={logout} />
        </header>
        {user && user.role === 'it_support_view' && (
          <div className="card banner" style={{ margin: '0 0 8px', padding: '9px 14px', fontSize: 13 }}>
            👁️ <b>IT Support View</b> — read-only. You can view and download everything; changes are blocked.
          </div>
        )}
        <div className="content"><div className="page page-enter" key={loc.pathname}>{children}</div></div>
      </div>
      {mobile && <div className="scrim" onClick={() => setMobile(false)} />}
      {palette_ && <CommandPalette sections={sections} onClose={() => setPaletteOpen(false)} />}
    </div>
  );
}

function NavItem({ it }) {
  const Icon = it.icon;
  return (
    <NavLink to={it.to} data-nav={it.id} className={({ isActive }) => cx('nav-i', isActive && 'on')} title={it.label}>
      {Icon ? <Icon /> : <span className="emo">{it.emoji || '•'}</span>}<span className="lbl">{it.label}</span>
    </NavLink>
  );
}

function ViewSwitch({ user, onSwitch }) {
  const [open, setOpen] = useState(false);
  const ref = useRef(null);
  return (
    <div style={{ padding: '0 10px 6px' }}>
      <button ref={ref} className="nav-i switch" onClick={() => setOpen(o => !o)} title="You have more than one role — switch your active view">
        <Repeat /><span className="lbl">Switch view · {roleName(user.role)}</span>
      </button>
      <Popover anchor={ref} open={open} onClose={() => setOpen(false)} align="left">
        {(user.available_views || []).map(v => (
          <button key={v} onClick={() => { setOpen(false); if (v !== user.role) onSwitch(v); }}>
            {v === user.role ? <Check /> : <Circle />}{roleName(v)}
          </button>
        ))}
      </Popover>
    </div>
  );
}

/* ── Popover rendered in a portal so it always sits above the classic runtime layer ── */
export function Popover({ anchor, open, onClose, children, width, align = 'right' }) {
  const [pos, setPos] = useState(null);
  const box = useRef(null);
  useLayoutEffect(() => {
    if (!open || !anchor.current) return;
    const r = anchor.current.getBoundingClientRect();
    setPos(align === 'left' ? { top: r.bottom + 8, left: r.left } : { top: r.bottom + 8, right: Math.max(8, window.innerWidth - r.right) });
  }, [open, anchor, align]);
  useEffect(() => {
    if (!open) return undefined;
    const h = (e) => { if (box.current && !box.current.contains(e.target) && anchor.current && !anchor.current.contains(e.target)) onClose(); };
    const k = (e) => { if (e.key === 'Escape') onClose(); };
    document.addEventListener('mousedown', h); window.addEventListener('keydown', k);
    return () => { document.removeEventListener('mousedown', h); window.removeEventListener('keydown', k); };
  }, [open, onClose, anchor]);
  if (!open || !pos) return null;
  return createPortal(<div ref={box} className="menu pop" data-v2-overlay style={{ position: 'fixed', zIndex: 70, width, ...pos }}>{children}</div>, document.body);
}

function PalettePicker({ value, onChange }) {
  const [open, setOpen] = useState(false);
  const ref = useRef(null);
  return (<>
    <button ref={ref} className="icon-btn" title="Colour palette" aria-label="Colour palette" onClick={() => setOpen(o => !o)}><Palette /></button>
    <Popover anchor={ref} open={open} onClose={() => setOpen(false)} width={300}>
      <div className="menu-h">Colour palette</div>
      <div className="swatches">
        {Object.entries(PALETTES).map(([k, p]) => (
          <button key={k} className={cx('swatch', value === k && 'on')} onClick={() => { onChange(k); }}>
            <span className="sw" style={{ background: `conic-gradient(from 210deg, rgb(${p.accent}), rgb(${p.accent2}), ${p.charts[2]}, rgb(${p.accent}))` }} />
            <span className="grow" style={{ textAlign: 'left' }}><b>{p.name}</b><small>{p.blurb}</small></span>
            {value === k && <Check size={16} />}
          </button>
        ))}
      </div>
    </Popover>
  </>);
}

function Notifications() {
  const classic = useClassic();
  const [open, setOpen] = useState(false);
  const [data, setData] = useState({ items: [], unread: 0 });
  const ref = useRef(null);
  const load = useCallback(() => api('/api/notifications?limit=30').then(d => setData({ items: (d && d.items) || (Array.isArray(d) ? d : []), unread: (d && d.unread) || 0 })).catch(() => {}), []);
  useEffect(() => { load(); const t = setInterval(load, 60000); return () => clearInterval(t); }, [load]);
  const openOne = (n) => {
    if (!n.read) api(`/api/notifications/${n.id}/read`, { method: 'POST' }).then(load).catch(() => {});
    setOpen(false);
    if (n.case_id && classic.api) classic.api.openCase(n.case_id);
  };
  const markAll = () => api('/api/notifications/read-all', { method: 'POST' }).then(load).catch(() => {});
  return (<>
    <button ref={ref} className="icon-btn" aria-label="Notifications" onClick={() => { setOpen(o => !o); if (!open) load(); }} style={{ position: 'relative' }}>
      <Bell />{data.unread > 0 && <span className="badge-dot pulse">{data.unread > 9 ? '9+' : data.unread}</span>}
    </button>
    <Popover anchor={ref} open={open} onClose={() => setOpen(false)} width={360}>
      <div className="row menu-h"><span className="grow">Notifications</span>{data.unread > 0 && <button className="btn ghost sm" onClick={markAll}>Mark all read</button>}</div>
      <div style={{ maxHeight: 420, overflow: 'auto' }}>
        {data.items.slice(0, 30).map((n, i) => (
          <button key={n.id || i} className={cx('notif', !n.read && 'unread')} onClick={() => openOne(n)}>
            <div className="grow" style={{ textAlign: 'left' }}>
              <div style={{ fontWeight: 600 }}>{n.title || n.kind || 'Update'}</div>
              <div className="muted" style={{ fontSize: 12.5 }}>{n.body || n.message || n.detail || ''}</div>
              {n.created_at && <div className="faint" style={{ fontSize: 11 }}>{fmtDate(n.created_at)} {fmtTime(n.created_at)}</div>}
            </div>
          </button>
        ))}
        {!data.items.length && <div className="faint" style={{ padding: '8px 12px 14px', fontSize: 13 }}>You're all caught up.</div>}
      </div>
    </Popover>
  </>);
}

function UserMenu({ user, onLogout }) {
  const classic = useClassic();
  const [open, setOpen] = useState(false);
  const [dl, setDl] = useState({});
  const ref = useRef(null);
  useEffect(() => {
    const get = (f) => fetch('/downloads/' + f, { cache: 'no-store' }).then(r => (r.ok ? r.json() : null)).catch(() => null);
    Promise.all([get('version.json'), get('ios.json'), get('desktop.json')]).then(([a, i, d]) => setDl({ a, i, d }));
  }, []);
  const origin = window.location.origin;
  return (<>
    <button ref={ref} className="row user-btn" onClick={() => setOpen(o => !o)}>
      <span className="avatar">{initials(user && user.name)}</span>
      <span className="hide-sm" style={{ textAlign: 'left', lineHeight: 1.2 }}>
        <div style={{ fontWeight: 600, fontSize: 13 }}>{user && user.name}</div>
        <div className="faint" style={{ fontSize: 11.5 }}>{(user && (user.branch || user.email)) || ''}</div>
      </span>
    </button>
    <Popover anchor={ref} open={open} onClose={() => setOpen(false)} width={270}>
      <div style={{ padding: '6px 10px 8px' }}>
        <div style={{ fontWeight: 600 }}>{user && user.name}</div>
        <div className="faint" style={{ fontSize: 12 }}>{user && user.email}{user && user.emp_code ? ' · ' + user.emp_code : ''}</div>
      </div>
      <hr />
      {classic.api && <button onClick={() => { setOpen(false); classic.api.openTour(); }}><Compass />App tour</button>}
      {dl.a && <a className="mi" href="/downloads/RecoverIQ-native.apk" download><Download />Android app{dl.a.version_name ? ' · v' + dl.a.version_name : ''}</a>}
      {dl.i && <a className="mi" href={'sidestore://source?url=' + encodeURIComponent(origin + '/downloads/ios-source.json')}><Apple />iPhone app (SideStore){dl.i.version_name ? ' · v' + dl.i.version_name : ''}</a>}
      {dl.d && <a className="mi" href={'/downloads/' + (dl.d.file || 'RecoverIQ-desktop.exe')} download><MonitorDown />Windows app{dl.d.version_name ? ' · v' + dl.d.version_name : ''}</a>}
      <hr />
      <button onClick={() => { window.location.href = '/'; }}><Monitor />Open classic interface</button>
      <button onClick={onLogout}><LogOut />Sign out</button>
    </Popover>
  </>);
}

function CommandPalette({ sections, onClose }) {
  const [q, setQ] = useState('');
  const [cases, setCases] = useState([]);
  const [sel, setSel] = useState(0);
  const navigate = useNavigate();
  const pages = sections.flatMap(s => s.items).filter(i => !q || i.label.toLowerCase().includes(q.toLowerCase()));
  useEffect(() => {
    if (q.trim().length < 3) { setCases([]); return undefined; }
    const t = setTimeout(() => {
      api('/api/cases?limit=8&search=' + encodeURIComponent(q.trim())).then(r => setCases(Array.isArray(r) ? r : [])).catch(() => setCases([]));
    }, 220);
    return () => clearTimeout(t);
  }, [q]);
  const results = [
    ...pages.map(p => ({ kind: 'Pages', label: p.label, icon: p.icon, emoji: p.emoji, go: () => navigate(p.to) })),
    ...cases.map(c => ({ kind: 'Accounts', label: c.customer_name || c.account_no, sub: `${c.account_no || ''} · ${c.bank || ''} ${c.product || ''}`, go: () => navigate('/cases?open=' + c.id) })),
  ];
  const run = (r) => { onClose(); if (r) r.go(); };
  return (<>
    <div className="scrim" onClick={onClose} />
    <div className="palette" role="dialog" aria-label="Command palette" data-v2-overlay>
      <input autoFocus placeholder="Search accounts by name / number, or jump to any screen…" value={q}
        onChange={e => { setQ(e.target.value); setSel(0); }}
        onKeyDown={e => {
          if (e.key === 'Escape') onClose();
          if (e.key === 'ArrowDown') { e.preventDefault(); setSel(s => Math.min(s + 1, results.length - 1)); }
          if (e.key === 'ArrowUp') { e.preventDefault(); setSel(s => Math.max(s - 1, 0)); }
          if (e.key === 'Enter') run(results[sel]);
        }} />
      <div className="list">
        {['Pages', 'Accounts'].map(g => {
          const items = results.map((r, i) => ({ ...r, i })).filter(r => r.kind === g);
          if (!items.length) return null;
          return <div key={g}><div className="grp">{g}</div>
            {items.map(r => {
              const Icon = r.icon;
              return <div key={r.i} className={cx('it', sel === r.i && 'on')} onMouseEnter={() => setSel(r.i)} onClick={() => run(r)}>
                {Icon ? <Icon size={16} /> : r.emoji ? <span>{r.emoji}</span> : <Search size={16} />}
                <div className="grow"><div style={{ fontWeight: 550 }}>{r.label}</div>{r.sub && <div className="faint" style={{ fontSize: 12 }}>{r.sub}</div>}</div>
              </div>;
            })}
          </div>;
        })}
        {!results.length && <div className="faint" style={{ padding: 18, textAlign: 'center' }}>No matches. Type at least 3 characters to search accounts.</div>}
      </div>
    </div>
  </>);
}

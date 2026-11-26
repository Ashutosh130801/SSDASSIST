import React, { useCallback, useEffect, useRef } from 'react';
import skinCss from '../styles/classic-skin.css?inline';
import { applyPalette } from '../lib/palettes.js';

/* ───────────────────────── Classic runtime host ─────────────────────────
   One transparent, full-viewport iframe runs the classic RecoverIQ app (?host=v2) for the whole
   session. It hides its own chrome and keeps everything that lives in the classic shell alive:
   chat, AI bot, voice calls, broadcasts, check-in / attendance gate, GPS pings, idle logout,
   screen-pop, guided tour, the full case drawer and every module not yet rebuilt natively.

   • Module routes (/m/:id) → the classic screen is laid out exactly over v2's content area.
   • Native routes → classic shows nothing but its floating widgets / popups.
   • Clicks pass straight through to v2 except where classic has something on screen
     (we track those rectangles and flip the iframe's pointer-events on hover / tap). */

const FIXED_SEL = [
  '[style*="position: fixed"]', '[style*="position:fixed"]',
  '.toast', '.modal-bg', '.drawer-bg', '.aibot', '.aibot-panel', '.aibot-hello', '[role="status"]',
].join(',');
const V2_OVERLAY = '.palette, .menu, .drawer, .scrim, .toast, [data-v2-overlay]';

export default function ClassicHost({ user, mode, palette, moduleId, onView, onReady, onLogout }) {
  const frame = useRef(null);
  const api = useRef(null);          // window.__riqClassic inside the iframe
  const rects = useRef([]);
  const stamp = useRef(0);
  const lastPt = useRef(null);        // last pointer position seen by either document
  const moduleRef = useRef(moduleId); moduleRef.current = moduleId;
  const cb = useRef({ onView, onReady, onLogout }); cb.current = { onView, onReady, onLogout };
  const src = useRef('/v2/classic/index.html?host=v2#' + (moduleId || 'none')).current;   // stable: navigation never reloads the runtime

  const doc = () => { try { return frame.current && frame.current.contentDocument; } catch { return null; } };
  const setPE = (v) => { const f = frame.current; if (f && f.style.pointerEvents !== v) f.style.pointerEvents = v; };

  /* Content-area geometry → CSS vars in the iframe (classic lays its module out there). */
  const layout = useCallback(() => {
    const d = doc(); if (!d || !d.documentElement) return;
    const el = document.querySelector('.content');
    const r = el ? el.getBoundingClientRect() : { top: 80, left: 270, width: window.innerWidth - 290, height: window.innerHeight - 100 };
    const s = d.documentElement.style;
    s.setProperty('--ht', r.top + 'px'); s.setProperty('--hl', r.left + 'px');
    s.setProperty('--hw', r.width + 'px'); s.setProperty('--hh', r.height + 'px');
  }, []);

  /* Theme: palette vars + mode + edition, and the skin stylesheet. */
  const theme = useCallback(() => {
    const d = doc(); if (!d || !d.documentElement) return;
    const root = d.documentElement;
    root.dataset.mode = mode; root.classList.add('riq-host');
    applyPalette(palette, 'light', root);       // classic modules render on a light "sheet" for legibility
    root.style.setProperty('--v2-accent-dark', getComputedStyle(document.documentElement).getPropertyValue('--accent'));
    if (!d.getElementById('riq-v2-skin')) {
      const st = d.createElement('style'); st.id = 'riq-v2-skin'; st.textContent = skinCss; d.head.appendChild(st);
      const ln = d.createElement('link'); ln.rel = 'stylesheet';
      ln.href = 'https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Sora:wght@500;600;700&display=swap';
      d.head.appendChild(ln);
    }
  }, [mode, palette]);

  /* Which screen classic shows. */
  const sync = useCallback(() => {
    const d = doc(); const a = api.current; if (!d || !d.documentElement || !a) return;
    const id = moduleRef.current;
    d.documentElement.classList.toggle('riq-module', !!id);
    if ((a.view || '') !== (id || 'none')) a.setView(id || 'none');
    layout();
  }, [layout]);

  /* Rectangles where classic is drawing something interactive. */
  const measure = useCallback(() => {
    const d = doc(); const out = [];
    if (d && d.body) {
      if (moduleRef.current && api.current) {
        const el = document.querySelector('.content');
        if (el) { const r = el.getBoundingClientRect(); out.push([r.left, r.top, r.right, r.bottom]); }
      }
      d.querySelectorAll(FIXED_SEL).forEach(el => {
        const r = el.getBoundingClientRect();
        if (r.width < 2 || r.height < 2) return;
        const cs = d.defaultView.getComputedStyle(el);
        if (cs.visibility === 'hidden' || cs.display === 'none' || cs.opacity === '0' || cs.pointerEvents === 'none') return;
        out.push([r.left, r.top, r.right, r.bottom]);
      });
    }
    rects.current = out; stamp.current = performance.now();
  }, []);

  const hit = useCallback((x, y) => {
    if (performance.now() - stamp.current > 120) measure();
    if (!rects.current.some(([l, t, r, b]) => x >= l && x <= r && y >= t && y <= b)) return false;
    // A v2 overlay (menu, palette, drawer…) on top wins.
    const f = frame.current; const prev = f && f.style.pointerEvents;
    if (f) f.style.pointerEvents = 'none';
    const under = document.elementFromPoint(x, y);
    if (f) f.style.pointerEvents = prev;
    return !(under && under.closest && under.closest(V2_OVERLAY));
  }, [measure]);

  /* Bridge object the classic app calls into. */
  useEffect(() => {
    window.__riqHost = {
      onView: (v) => { if (api.current) api.current.view = v; cb.current.onView && cb.current.onView(v); },
      onReady: (a) => {
        const first = !api.current; api.current = a;
        if (first) { theme(); sync(); }
        cb.current.onReady && cb.current.onReady(a);
      },
      onLogout: () => cb.current.onLogout && cb.current.onLogout(),
    };
    return () => { delete window.__riqHost; };
  }, [theme, sync]);

  useEffect(() => { theme(); }, [theme]);
  useEffect(() => { sync(); }, [moduleId, sync]);

  /* Geometry + pointer hand-off. */
  useEffect(() => {
    const ro = new ResizeObserver(() => layout());
    const content = document.querySelector('.content'); if (content) ro.observe(content);
    window.addEventListener('resize', layout);
    // Watchdog: if the pointer is no longer over anything classic draws, hand it back to v2.
    const tick = setInterval(() => {
      measure(); layout();
      const f = frame.current; const lp = lastPt.current;
      if (f && f.style.pointerEvents === 'auto' && (!lp || !hit(lp[0], lp[1]))) setPE('none');
    }, 300);

    const move = (e) => { lastPt.current = [e.clientX, e.clientY]; if (hit(e.clientX, e.clientY)) setPE('auto'); };
    let touchFwd = false;
    const down = (e) => { if (e.pointerType !== 'mouse' && hit(e.clientX, e.clientY)) { setPE('auto'); touchFwd = true; } };
    const click = (e) => {
      if (!touchFwd) return; touchFwd = false;
      const d = doc(); if (!d) return;
      const el = d.elementFromPoint(e.clientX, e.clientY);
      if (el) { e.preventDefault(); e.stopPropagation(); if (el.focus) el.focus(); el.click(); }
    };
    window.addEventListener('pointermove', move, { capture: true, passive: true });
    window.addEventListener('pointerdown', down, { capture: true, passive: true });
    window.addEventListener('click', click, true);
    // Activity in v2 counts as activity for classic's idle-logout / presence (it only sees its own window).
    let lastFwd = 0;
    const activity = (e) => {
      const now = Date.now(); if (now - lastFwd < 4000) return; lastFwd = now;
      const d = doc(); if (d && d.defaultView) { try { d.defaultView.dispatchEvent(new Event(e.type === 'keydown' ? 'keydown' : 'mousemove')); } catch { /* ignore */ } }
    };
    const acts = ['mousemove', 'mousedown', 'keydown', 'touchstart', 'scroll', 'wheel'];
    acts.forEach(t => window.addEventListener(t, activity, { capture: true, passive: true }));
    return () => {
      acts.forEach(t => window.removeEventListener(t, activity, true));
      ro.disconnect(); clearInterval(tick); window.removeEventListener('resize', layout);
      window.removeEventListener('pointermove', move, true); window.removeEventListener('pointerdown', down, true);
      window.removeEventListener('click', click, true);
    };
  }, [hit, layout, measure]);

  const onLoad = () => {
    const d = doc(); if (!d || !d.documentElement) return;
    theme(); layout();
    // Inside the iframe: release the pointer as soon as it leaves classic's interactive areas.
    d.addEventListener('pointermove', (e) => { lastPt.current = [e.clientX, e.clientY]; if (!hit(e.clientX, e.clientY)) setPE('none'); }, { passive: true });
    d.documentElement.addEventListener('mouseleave', () => { lastPt.current = null; setPE('none'); });
    d.addEventListener('keydown', (e) => {   // keep ⌘K / Ctrl+K working while focus is in classic
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') { e.preventDefault(); window.dispatchEvent(new KeyboardEvent('keydown', { key: 'k', ctrlKey: true })); }
    });
  };

  return (
    <iframe
      ref={frame}
      key={user && `${user.id}:${user.role}:${user.active_view || ''}`}
      title="RecoverIQ modules"
      className="classic-host"
      src={src}
      onLoad={onLoad}
      allow="camera; microphone; geolocation; clipboard-read; clipboard-write; fullscreen; autoplay; display-capture"
      style={{ position: 'fixed', inset: 0, width: '100%', height: '100%', border: 0, zIndex: 35, background: 'transparent', pointerEvents: 'none', colorScheme: 'normal' }}
    />
  );
}

import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  Search, Satellite, Map as MapIcon, Crosshair, RefreshCw, X, Phone, MessageCircle, Play, Pause, Route as RouteIcon,
  Footprints, Clock, Navigation, SlidersHorizontal, Users, Radio, MoonStar, CalendarDays, Camera, IndianRupee, Layers,
} from 'lucide-react';
import { api, qs } from '../lib/api.js';
import { istToday, num, inr, fmtTime } from '../lib/format.js';
import { L, baseLayer, INDIA, statusOf, STATUS, ago, agentIcon, dotIcon, pinIcon, gradientRoute, hhmm } from '../lib/map.js';
import { useClassic } from '../lib/classic.jsx';
import { CountUp } from '../components/fx.jsx';
import { FieldToolButtons, dayVisitsExcel } from './FieldTools.jsx';

const cssVar = (n) => (getComputedStyle(document.documentElement).getPropertyValue(n) || '').trim();
const FILTERS = [['all', 'All'], ['live', 'Live'], ['idle', 'Idle'], ['offline', 'Offline']];

/** Field Tracking — live map of the field force (admin / manager / head office). Read-only over existing APIs. */
export default function FieldMap() {
  const box = useRef(null);
  const map = useRef(null);
  const layers = useRef({});
  const [tile, setTile] = useState('map');
  const [date, setDate] = useState(istToday());
  const [roster, setRoster] = useState(null);
  const [live, setLive] = useState([]);
  const [q, setQ] = useState('');
  const [flt, setFlt] = useState('all');
  const [branch, setBranch] = useState('');
  const [sel, setSel] = useState(null);
  const [busy, setBusy] = useState(false);
  const isToday = date === istToday();
  const mode = document.documentElement.dataset.mode;

  /* ── map setup ── */
  useEffect(() => {
    const m = L.map(box.current, { zoomControl: false, attributionControl: true, preferCanvas: false }).setView(INDIA, 12);
    L.control.zoom({ position: 'bottomright' }).addTo(m);
    layers.current = { agents: L.layerGroup().addTo(m), route: L.layerGroup().addTo(m), visits: L.layerGroup().addTo(m), play: L.layerGroup().addTo(m) };
    map.current = m;
    const ro = new ResizeObserver(() => m.invalidateSize()); ro.observe(box.current);
    return () => { ro.disconnect(); m.remove(); };
  }, []);
  useEffect(() => {
    const m = map.current; if (!m) return undefined;
    const lyr = baseLayer(tile === 'satellite' ? 'satellite' : 'street').addTo(m);
    return () => { m.removeLayer(lyr); };
  }, [tile, mode]);

  /* ── data ── */
  const load = useCallback(async () => {
    setBusy(true);
    try {
      const [r, l] = await Promise.all([
        api('/api/tracking/roster' + qs({ date })).catch(() => null),
        isToday ? api('/api/tracking/live?minutes=720').catch(() => []) : Promise.resolve([]),
      ]);
      setRoster(r); setLive(Array.isArray(l) ? l : []);
    } finally { setBusy(false); }
  }, [date, isToday]);
  useEffect(() => { load(); if (!isToday) return undefined; const t = setInterval(load, 15000); return () => clearInterval(t); }, [load, isToday]);

  const agents = useMemo(() => {
    const pos = new Map(live.map(x => [x.officer_id, x]));
    const all = [...((roster && roster.active) || []), ...((roster && roster.inactive) || [])];
    return all.map(a => {
      const p = pos.get(a.id);
      const st = isToday ? (p ? statusOf(p.last_seen) : 'offline') : (a.active ? 'idle' : 'offline');
      return { ...a, pos: p ? [p.latitude, p.longitude] : null, seen: (p && p.last_seen) || a.last_seen, status: st, checked_in: p ? p.checked_in : undefined };
    });
  }, [roster, live, isToday]);
  const branches = useMemo(() => [...new Set(agents.map(a => a.branch).filter(Boolean))].sort(), [agents]);
  const shown = agents.filter(a => (flt === 'all' || a.status === flt) && (!branch || a.branch === branch)
    && (!q || `${a.name} ${a.emp_code || ''} ${a.branch || ''}`.toLowerCase().includes(q.toLowerCase())))
    .sort((a, b) => ['live', 'idle', 'offline'].indexOf(a.status) - ['live', 'idle', 'offline'].indexOf(b.status) || (b.distance_km || 0) - (a.distance_km || 0));
  const counts = agents.reduce((c, a) => ({ ...c, [a.status]: (c[a.status] || 0) + 1 }), {});
  const totalKm = agents.reduce((s, a) => s + (a.distance_km || 0), 0);

  /* ── markers ── */
  const fitted = useRef(false);
  useEffect(() => {
    const g = layers.current.agents; if (!g) return;
    g.clearLayers();
    const pts = [];
    shown.forEach(a => {
      if (!a.pos) return;
      pts.push(a.pos);
      L.marker(a.pos, { icon: agentIcon(a.name, a.status, sel === a.id), riseOnHover: true, zIndexOffset: sel === a.id ? 1000 : (a.status === 'live' ? 500 : 0) })
        .on('click', () => setSel(a.id))
        .bindTooltip(`<b>${a.name}</b><br>${STATUS[a.status].label} · ${ago(a.seen)}`, { direction: 'top', offset: [0, -44], className: 'fm-tt' })
        .addTo(g);
    });
    if (!fitted.current && pts.length) { map.current.fitBounds(pts, { paddingTopLeft: [380, 80], paddingBottomRight: [60, 60], maxZoom: 15 }); fitted.current = true; }
  }, [shown, sel]);

  const fitAll = () => { const pts = shown.filter(a => a.pos).map(a => a.pos); if (pts.length) map.current.flyToBounds(pts, { paddingTopLeft: [380, 80], paddingBottomRight: [60, 60], maxZoom: 15, duration: .8 }); };
  const selected = agents.find(a => a.id === sel) || null;

  return (
    <div className="fm-wrap rise">
      <div ref={box} className="fm-map" />

      {/* Roster panel */}
      <aside className="fm-panel">
        <div className="fm-head">
          <div className="row" style={{ gap: 8 }}><Radio size={16} className="fm-live-ic" /><b>Field force</b>
            <span className="grow" />
            <button className="icon-btn" title="Refresh" onClick={load}><RefreshCw className={busy ? 'spin' : ''} /></button></div>
          <div className="fm-kpis">
            <div className="fm-k live"><b><CountUp value={counts.live || 0} /></b><span>Live</span></div>
            <div className="fm-k idle"><b><CountUp value={counts.idle || 0} /></b><span>Idle</span></div>
            <div className="fm-k off"><b><CountUp value={counts.offline || 0} /></b><span>Offline</span></div>
            <div className="fm-k km"><b><CountUp value={totalKm} format={(x) => x.toFixed(1)} /></b><span>km today</span></div>
          </div>
          <div className="input-icon"><Search /><input className="input" placeholder="Search agent, ID, branch…" value={q} onChange={e => setQ(e.target.value)} /></div>
          <div className="row" style={{ gap: 6, marginTop: 8 }}>
            <div className="seg fm-seg">{FILTERS.map(([v, l]) => <button key={v} className={flt === v ? 'on' : ''} onClick={() => setFlt(v)}>{l}</button>)}</div>
          </div>
          <div className="row" style={{ gap: 6, marginTop: 8 }}>
            <select className="select grow" value={branch} onChange={e => setBranch(e.target.value)}><option value="">All branches</option>{branches.map(b => <option key={b}>{b}</option>)}</select>
            <label className="fm-date"><CalendarDays size={14} /><input type="date" value={date} max={istToday()} onChange={e => { setDate(e.target.value); fitted.current = false; }} /></label>
          </div>
        </div>
        <div className="fm-list">
          {!roster && [0, 1, 2, 3, 4].map(i => <div key={i} className="skel" style={{ height: 52, margin: '8px 0' }} />)}
          {roster && !shown.length && <div className="faint" style={{ padding: 16, fontSize: 13 }}>No field agents match. Agents appear here once their app shares a location.</div>}
          {shown.map((a, i) => (
            <button key={a.id} className={'fm-row' + (sel === a.id ? ' on' : '')} style={{ '--i': i }}
              onClick={() => { setSel(a.id); if (a.pos) map.current.flyTo(a.pos, Math.max(map.current.getZoom(), 15), { duration: .7 }); }}>
              <span className={'fm-av-sm ' + a.status}>{String(a.name || '?').split(' ').map(w => w[0]).slice(0, 2).join('')}</span>
              <span className="grow" style={{ minWidth: 0 }}>
                <span className="fm-n">{a.name}</span>
                <span className="fm-s">{[a.emp_code, a.branch].filter(Boolean).join(' · ') || '—'}</span>
              </span>
              <span className="fm-r">
                <span className={'fm-st ' + a.status}>{STATUS[a.status].label}</span>
                <span className="fm-s">{a.distance_km ? a.distance_km.toFixed(1) + ' km' : ago(a.seen)}</span>
              </span>
            </button>
          ))}
        </div>
      </aside>

      {/* Map tools */}
      <div className="fm-tools">
        <div className="seg fm-seg">
          <button className={tile === 'map' ? 'on' : ''} onClick={() => setTile('map')}><MapIcon size={14} /> Map</button>
          <button className={tile === 'satellite' ? 'on' : ''} onClick={() => setTile('satellite')}><Satellite size={14} /> Satellite</button>
        </div>
        <button className="btn sm" onClick={fitAll}><Crosshair />Fit all</button>
        <FieldToolButtons branch={branch} />
      </div>
      <div className="fm-legend">
        {Object.entries(STATUS).map(([k, s]) => <span key={k}><i style={{ background: s.color }} />{s.label}</span>)}
        <span className="faint">{isToday ? 'auto-refresh 15 s' : 'history · ' + date}</span>
      </div>

      {selected && <AgentDetail key={selected.id + date} a={selected} date={date} map={map} layers={layers} onClose={() => setSel(null)} />}
    </div>
  );
}

function AgentDetail({ a, date, map, layers, onClose }) {
  const classic = useClassic();
  const [tab, setTab] = useState('route');
  const [route, setRoute] = useState(null);
  const [visits, setVisits] = useState(null);
  const [days, setDays] = useState([]);
  const [day, setDay] = useState(date);
  const [idx, setIdx] = useState(0);
  const [playing, setPlaying] = useState(false);

  useEffect(() => { api(`/api/tracking/officer/${a.id}/history-dates?days=30`).then(d => setDays(Array.isArray(d) ? d.slice(0, 10) : [])).catch(() => {}); }, [a.id]);
  useEffect(() => {
    setRoute(null); setVisits(null); setIdx(0); setPlaying(false);
    api(`/api/tracking/officer/${a.id}/route` + qs({ date: day })).then(r => setRoute(Array.isArray(r) ? r : [])).catch(() => setRoute([]));
    api(`/api/attendance/user/${a.id}/visits` + qs({ date: day })).then(v => setVisits((v && v.visits) || [])).catch(() => setVisits([]));
  }, [a.id, day]);

  const pts = useMemo(() => (route || []).map(p => [p.latitude, p.longitude]), [route]);
  const km = useMemo(() => { let s = 0; for (let i = 1; i < pts.length; i++) { const [x1, y1] = pts[i - 1], [x2, y2] = pts[i]; const R = 6371, d = Math.PI / 180; const h = Math.sin((x2 - x1) * d / 2) ** 2 + Math.cos(x1 * d) * Math.cos(x2 * d) * Math.sin((y2 - y1) * d / 2) ** 2; s += 2 * R * Math.asin(Math.sqrt(h)); } return s; }, [pts]);

  /* draw route + visits */
  useEffect(() => {
    const { route: rl, visits: vl } = layers.current; rl.clearLayers(); vl.clearLayers();
    if (pts.length > 1) {
      gradientRoute(rl, pts, cssVar('--chart-2') || '#0EA5E9', cssVar('--chart-1') || '#2563EB');
      L.marker(pts[0], { icon: dotIcon('#10B981', 'S', 'start') }).bindTooltip('Start · ' + hhmm(route[0].created_at), { className: 'fm-tt' }).addTo(rl);
      L.marker(pts[pts.length - 1], { icon: dotIcon('#EF4444', 'E', 'end') }).bindTooltip('Last · ' + hhmm(route[route.length - 1].created_at), { className: 'fm-tt' }).addTo(rl);
      map.current.flyToBounds(pts, { paddingTopLeft: [380, 90], paddingBottomRight: [400, 60], maxZoom: 16, duration: .8 });
    } else if (a.pos) map.current.flyTo(a.pos, 15, { duration: .6 });
    (visits || []).forEach(v => {
      if (v.lat == null) return;
      L.marker([v.lat, v.lng], { icon: pinIcon(v.paid ? '#10B981' : '#2563EB', v.paid ? '₹' : '•') })
        .bindPopup(`<div class="fm-pop">${v.photo ? `<img src="${v.photo}" />` : ''}<b>${v.case_label || 'Visit'}</b><div>${v.disposition || ''} · ${hhmm(v.at)}</div>${v.paid ? `<div class="paid">Collected ${inr(v.amount)}</div>` : ''}${v.note ? `<div class="note">${String(v.note).slice(0, 140)}</div>` : ''}</div>`, { maxWidth: 260 })
        .addTo(vl);
    });
    return () => { rl.clearLayers(); vl.clearLayers(); layers.current.play.clearLayers(); };
  }, [pts, visits]); // eslint-disable-line react-hooks/exhaustive-deps

  /* playback */
  useEffect(() => {
    const pl = layers.current.play; pl.clearLayers();
    if (pts.length > 1 && idx > 0) L.marker(pts[Math.min(idx, pts.length - 1)], { icon: dotIcon(cssVar('--accent') || '#2563EB', '', 'play') }).addTo(pl);
  }, [idx, pts]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (!playing) return undefined;
    const t = setInterval(() => setIdx(i => { if (i >= pts.length - 1) { setPlaying(false); return i; } return i + Math.max(1, Math.round(pts.length / 240)); }), 40);
    return () => clearInterval(t);
  }, [playing, pts.length]);

  const tel = a.phone ? String(a.phone).replace(/[^0-9+]/g, '') : '';
  return (
    <aside className="fm-detail">
      <div className="row" style={{ gap: 12, alignItems: 'flex-start' }}>
        <span className={'fm-av-lg ' + a.status}>{String(a.name || '?').split(' ').map(w => w[0]).slice(0, 2).join('')}</span>
        <div className="grow" style={{ minWidth: 0 }}>
          <div className="fm-title">{a.name}</div>
          <div className="faint" style={{ fontSize: 12.5 }}>{[a.emp_code, a.branch, a.location].filter(Boolean).join(' · ')}</div>
          <div className="row" style={{ gap: 6, marginTop: 6 }}>
            <span className={'fm-st ' + a.status}>{STATUS[a.status].label}</span>
            <span className="faint" style={{ fontSize: 12 }}><Clock size={12} style={{ verticalAlign: -2 }} /> {ago(a.seen)}</span>
            {a.checked_in === false && <span className="pill warn">Not checked in</span>}
          </div>
        </div>
        <button className="icon-btn" onClick={onClose} aria-label="Close"><X /></button>
      </div>

      <div className="fm-stats">
        <div><b>{km ? km.toFixed(1) : (a.distance_km || 0).toFixed(1)}</b><span>km</span></div>
        <div><b>{num(visits ? visits.length : 0)}</b><span>visits</span></div>
        <div><b>{num(visits ? visits.filter(v => v.paid).length : 0)}</b><span>paid</span></div>
        <div><b>{route && route.length ? hhmm(route[0].created_at) : '—'}</b><span>first ping</span></div>
      </div>

      <div className="row" style={{ gap: 6 }}>
        {tel && <a className="btn sm" href={'tel:' + tel}><Phone />Call</a>}
        {tel && <a className="btn sm" target="_blank" rel="noreferrer" href={'https://wa.me/' + (tel.length === 10 ? '91' + tel : tel.replace('+', ''))}><MessageCircle />WhatsApp</a>}
        {a.pos && <a className="btn sm" target="_blank" rel="noreferrer" href={`https://www.google.com/maps?q=${a.pos[0]},${a.pos[1]}`}><Navigation />Google Maps</a>}
      </div>

      {days.length > 0 && <div className="fm-days">{days.map(d => <button key={d.date} className={day === d.date ? 'on' : ''} onClick={() => setDay(d.date)}>
        <b>{d.date.slice(8)}/{d.date.slice(5, 7)}</b><span>{d.distance_km} km</span></button>)}</div>}

      <div className="seg fm-seg" style={{ alignSelf: 'flex-start' }}>
        <button className={tab === 'route' ? 'on' : ''} onClick={() => setTab('route')}><RouteIcon size={14} /> Route</button>
        <button className={tab === 'visits' ? 'on' : ''} onClick={() => setTab('visits')}><Footprints size={14} /> Visits {visits ? `(${visits.length})` : ''}</button>
      </div>

      {tab === 'route' && <div className="fm-sec">
        {route === null ? <div className="skel" style={{ height: 70 }} /> : pts.length < 2 ? <div className="faint" style={{ fontSize: 13 }}>No route recorded for this day.</div> : <>
          <div className="row" style={{ gap: 10 }}>
            <button className="btn primary sm" onClick={() => { if (idx >= pts.length - 1) setIdx(0); setPlaying(p => !p); }}>{playing ? <Pause /> : <Play />}{playing ? 'Pause' : 'Replay day'}</button>
            <span className="faint" style={{ fontSize: 12 }}>{route[Math.min(idx, route.length - 1)] ? hhmm(route[Math.min(idx, route.length - 1)].created_at) : ''} · {num(pts.length)} points</span>
          </div>
          <input className="fm-range" type="range" min={0} max={pts.length - 1} value={idx} onChange={e => { setPlaying(false); setIdx(Number(e.target.value)); }} />
        </>}
      </div>}

      {tab === 'visits' && <div className="fm-sec fm-visits">
        {visits && visits.length > 0 && <button className="btn sm" style={{ alignSelf: 'flex-start' }} onClick={() => { const X = classic.api && classic.api.getXLSX && classic.api.getXLSX(); if (!dayVisitsExcel(X, a.name || 'officer', day, visits)) alert('Excel export is still loading — try again in a moment.'); }}>Day visits → Excel</button>}
        {visits === null && <div className="skel" style={{ height: 70 }} />}
        {visits && !visits.length && <div className="faint" style={{ fontSize: 13 }}>No visits logged this day.</div>}
        {(visits || []).map(v => (
          <button key={v.id} className="fm-visit" onClick={() => { if (v.lat != null) map.current.flyTo([v.lat, v.lng], 17, { duration: .6 }); }}>
            {v.photo ? <img src={v.photo} alt="" /> : <span className="fm-noimg"><Camera size={16} /></span>}
            <span className="grow" style={{ minWidth: 0, textAlign: 'left' }}>
              <span className="fm-n">{v.case_label || 'Visit'}</span>
              <span className="fm-s">{hhmm(v.at)} · {v.disposition || '—'}{v.distance_m != null ? ` · ${v.distance_m} m from address` : ''}</span>
            </span>
            {v.paid && <span className="pill good"><IndianRupee size={11} />{num(v.amount)}</span>}
            {v.case_id && classic.api && <span className="fm-open" onClick={(e) => { e.stopPropagation(); classic.api.openCase(v.case_id); }}>Open</span>}
          </button>
        ))}
      </div>}
    </aside>
  );
}

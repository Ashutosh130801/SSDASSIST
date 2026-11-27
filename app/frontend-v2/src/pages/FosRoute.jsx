import React, { useEffect, useMemo, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { Search, Satellite, Map as MapIcon, LocateFixed, Navigation, SlidersHorizontal, Route as RouteIcon, MapPin, Footprints, IndianRupee, ExternalLink } from 'lucide-react';
import { api, qs } from '../lib/api.js';
import { useAuth } from '../lib/auth.jsx';
import { useClassic } from '../lib/classic.jsx';
import { inr, num, istToday } from '../lib/format.js';
import { L, baseLayer, INDIA, pinIcon, dotIcon, gradientRoute, kmBetween } from '../lib/map.js';
import { CountUp } from '../components/fx.jsx';

const cssVar = (n) => (getComputedStyle(document.documentElement).getPropertyValue(n) || '').trim();
const tone = (c) => {
  const s = String(c.paid_status || '').toUpperCase();
  if (s === 'PAID') return ['#10B981', '✓'];
  if (s === 'PARTIAL') return ['#F59E0B', '½'];
  if (/PTP/.test(c.disposition || '')) return ['#6366F1', 'P'];
  return ['#2563EB', '•'];
};

/** "My route" for field agents: today's trail, my accounts on the map, nearest-first worklist. */
export default function FosRoute() {
  const { user } = useAuth();
  const classic = useClassic();
  const box = useRef(null); const map = useRef(null); const lay = useRef({});
  const [tile, setTile] = useState('map');
  const [today, setToday] = useState(null);
  const [cases, setCases] = useState(null);
  const [visits, setVisits] = useState([]);
  const [me, setMe] = useState(null);
  const [flt, setFlt] = useState('open');
  const [q, setQ] = useState('');
  const mode = document.documentElement.dataset.mode;

  useEffect(() => {
    const m = L.map(box.current, { zoomControl: false }).setView(INDIA, 13);
    L.control.zoom({ position: 'bottomright' }).addTo(m);
    lay.current = { route: L.layerGroup().addTo(m), cases: L.layerGroup().addTo(m), me: L.layerGroup().addTo(m) };
    map.current = m;
    const ro = new ResizeObserver(() => m.invalidateSize()); ro.observe(box.current);
    return () => { ro.disconnect(); m.remove(); };
  }, []);
  useEffect(() => { const m = map.current; const l = baseLayer(tile === 'satellite' ? 'satellite' : 'street').addTo(m); return () => m.removeLayer(l); }, [tile, mode]);

  useEffect(() => {
    const load = () => {
      api('/api/tracking/me/today').then(setToday).catch(() => setToday({ points: [], distance_km: 0, count: 0 }));
      if (user) api(`/api/attendance/user/${user.id}/visits` + qs({ date: istToday() })).then(v => setVisits((v && v.visits) || [])).catch(() => {});
    };
    load(); const t = setInterval(load, 30000);
    api('/api/cases?limit=3000').then(r => setCases(Array.isArray(r) ? r : [])).catch(() => setCases([]));
    let wid = null;
    if (navigator.geolocation) wid = navigator.geolocation.watchPosition(p => setMe([p.coords.latitude, p.coords.longitude]), () => {}, { enableHighAccuracy: true, maximumAge: 20000 });
    return () => { clearInterval(t); if (wid != null) navigator.geolocation.clearWatch(wid); };
  }, [user]);

  const pts = useMemo(() => ((today && today.points) || []).map(p => [p.lat, p.lng]), [today]);
  const here = me || pts[pts.length - 1] || null;
  const located = useMemo(() => (cases || []).map(c => {
    const ll = c.latitude != null ? [c.latitude, c.longitude] : (c.latitude2 != null ? [c.latitude2, c.longitude2] : null);
    return { ...c, ll, km: ll && here ? kmBetween(here, ll) : null };
  }), [cases, here]);
  const list = located.filter(c => (flt === 'all' || (flt === 'open' ? String(c.paid_status).toUpperCase() !== 'PAID' : /PTP/.test(c.disposition || '')))
    && (!q || `${c.customer_name} ${c.account_no || ''} ${c.address || ''}`.toLowerCase().includes(q.toLowerCase())))
    .sort((a, b) => (a.km == null) - (b.km == null) || (a.km || 0) - (b.km || 0));

  useEffect(() => {
    const { route } = lay.current; route.clearLayers();
    if (pts.length > 1) {
      gradientRoute(route, pts, cssVar('--chart-2') || '#0EA5E9', cssVar('--chart-1') || '#2563EB');
      L.marker(pts[0], { icon: dotIcon('#10B981', 'S', 'start') }).addTo(route);
    }
  }, [pts]);
  const fitted = useRef(false);
  useEffect(() => {
    const g = lay.current.cases; g.clearLayers();
    const b = [];
    list.slice(0, 400).forEach(c => {
      if (!c.ll) return; b.push(c.ll);
      const [col, gl] = tone(c);
      L.marker(c.ll, { icon: pinIcon(col, gl) }).bindPopup(`<div class="fm-pop"><b>${c.customer_name || ''}</b><div>${c.bank || ''} ${c.product || ''} · ${c.account_no || ''}</div><div class="paid">Pending ${inr(c.pending_amount)}</div>${c.km != null ? `<div>${c.km.toFixed(1)} km away</div>` : ''}</div>`).addTo(g);
    });
    if (!fitted.current && (b.length || here)) { map.current.fitBounds([...b, ...(here ? [here] : [])].slice(0, 300), { paddingTopLeft: [380, 70], paddingBottomRight: [60, 60], maxZoom: 15 }); fitted.current = true; }
  }, [list.length, flt, q, cases]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    const g = lay.current.me; g.clearLayers();
    if (here) L.marker(here, { icon: L.divIcon({ className: 'fm-me-wrap', iconSize: [22, 22], iconAnchor: [11, 11], html: '<div class="fm-me"><span></span></div>' }), zIndexOffset: 2000 }).addTo(g);
  }, [here]);

  const paid = visits.filter(v => v.paid);
  return (
    <div className="fm-wrap rise">
      <div ref={box} className="fm-map" />
      <aside className="fm-panel">
        <div className="fm-head">
          <div className="row" style={{ gap: 8 }}><RouteIcon size={16} /><b>My route today</b></div>
          <div className="fm-kpis">
            <div className="fm-k km"><b><CountUp value={(today && today.distance_km) || 0} format={(x) => x.toFixed(1)} /></b><span>km</span></div>
            <div className="fm-k live"><b><CountUp value={visits.length} /></b><span>visits</span></div>
            <div className="fm-k idle"><b><CountUp value={paid.length} /></b><span>paid</span></div>
            <div className="fm-k off"><b>{inr(paid.reduce((s, v) => s + (v.amount || 0), 0)).replace('₹', '₹')}</b><span>collected</span></div>
          </div>
          <div className="input-icon"><Search /><input className="input" placeholder="Search my accounts…" value={q} onChange={e => setQ(e.target.value)} /></div>
          <div className="seg fm-seg" style={{ marginTop: 8 }}>
            {[['open', 'To recover'], ['ptp', 'PTP'], ['all', 'All']].map(([v, l]) => <button key={v} className={flt === v ? 'on' : ''} onClick={() => setFlt(v)}>{l}</button>)}
          </div>
          <div className="faint" style={{ fontSize: 11.5, marginTop: 8 }}>{here ? 'Sorted nearest first' : 'Allow location to sort nearest first'} · {num(list.length)} accounts</div>
        </div>
        <div className="fm-list">
          {cases === null && [0, 1, 2, 3].map(i => <div key={i} className="skel" style={{ height: 58, margin: '8px 0' }} />)}
          {list.slice(0, 150).map(c => {
            const [col] = tone(c);
            return (
              <div key={c.id} className="fm-row case" onClick={() => c.ll && map.current.flyTo(c.ll, 17, { duration: .6 })}>
                <span className="fm-pin-sm" style={{ background: col }}><MapPin size={13} /></span>
                <span className="grow" style={{ minWidth: 0 }}>
                  <span className="fm-n">{c.customer_name}</span>
                  <span className="fm-s">{[c.bank, c.product, c.km != null ? c.km.toFixed(1) + ' km' : 'no location'].filter(Boolean).join(' · ')}</span>
                </span>
                <span className="fm-r">
                  <b className="num" style={{ fontSize: 12.5 }}>{inr(c.pending_amount)}</b>
                  <span className="row" style={{ gap: 4 }}>
                    {c.ll && <a className="fm-mini" title="Navigate" target="_blank" rel="noreferrer" onClick={e => e.stopPropagation()} href={`https://www.google.com/maps/dir/?api=1&destination=${c.ll[0]},${c.ll[1]}`}><Navigation size={13} /></a>}
                    {classic.api && <button className="fm-mini" title="Open case · log visit / payment" onClick={e => { e.stopPropagation(); classic.api.openCase(c.id); }}><ExternalLink size={13} /></button>}
                  </span>
                </span>
              </div>
            );
          })}
        </div>
      </aside>
      <div className="fm-tools">
        <div className="seg fm-seg">
          <button className={tile === 'map' ? 'on' : ''} onClick={() => setTile('map')}><MapIcon size={14} /> Map</button>
          <button className={tile === 'satellite' ? 'on' : ''} onClick={() => setTile('satellite')}><Satellite size={14} /> Satellite</button>
        </div>
        {here && <button className="btn sm" onClick={() => map.current.flyTo(here, 16, { duration: .6 })}><LocateFixed />Me</button>}
      </div>
      <div className="fm-legend">
        <span><i style={{ background: '#2563EB' }} />To recover</span><span><i style={{ background: '#6366F1' }} />PTP</span>
        <span><i style={{ background: '#F59E0B' }} />Partial</span><span><i style={{ background: '#10B981' }} />Paid</span>
      </div>
    </div>
  );
}

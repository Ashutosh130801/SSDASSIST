const { useState, useEffect, useRef, useCallback } = React;

/* ============================== helpers ============================== */
const store = {
  get t() { try { return localStorage.getItem('ssd_token'); } catch { return null; } },
  set t(v) { try { v ? localStorage.setItem('ssd_token', v) : localStorage.removeItem('ssd_token'); } catch {} },
  get u() { try { return JSON.parse(localStorage.getItem('ssd_user') || 'null'); } catch { return null; } },
  set u(v) { try { v ? localStorage.setItem('ssd_user', JSON.stringify(v)) : localStorage.removeItem('ssd_user'); } catch {} },
};

// Stable per-browser device id (for device-access approval / anti-fraud).
const deviceId = (() => {
  try {
    let d = localStorage.getItem('ssd_device');
    if (!d) { d = 'dev-' + Math.random().toString(36).slice(2, 10) + Date.now().toString(36); localStorage.setItem('ssd_device', d); }
    return d;
  } catch { return 'dev-unknown'; }
})();
const deviceLabel = (() => { try { return (navigator.userAgent || 'device').slice(0, 140); } catch { return 'device'; } })();

async function api(path, { method, body, form, auth = true } = {}) {
  const headers = {};
  if (auth && store.t) headers['Authorization'] = 'Bearer ' + store.t;
  // A request carrying a body must be POST — a GET+body throws in Firefox.
  const httpMethod = method || (body || form ? 'POST' : 'GET');
  const opts = { method: httpMethod, headers };
  if (form) { opts.body = form; }
  else if (body) { headers['Content-Type'] = 'application/json'; opts.body = JSON.stringify(body); }
  const res = await fetch(path, opts);
  if (res.status === 401) { store.t = null; store.u = null; location.reload(); throw new Error('unauthorized'); }
  const ct = res.headers.get('content-type') || '';
  if (!res.ok) {
    let msg = res.statusText;
    if (ct.includes('json')) { try { msg = (await res.json()).detail || msg; } catch {} }
    throw new Error(typeof msg === 'string' ? msg : JSON.stringify(msg));
  }
  if (ct.includes('json')) return res.json();
  return res;
}

async function download(path, filename) {
  try {
    const res = await fetch(path, { headers: store.t ? { Authorization: 'Bearer ' + store.t } : {} });
    if (!res.ok) {
      let msg = 'Download failed'; try { msg = (await res.json()).detail || msg; } catch {}
      toast(msg, 'err'); return;
    }
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a'); a.href = url; a.download = filename;
    document.body.appendChild(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 4000);
  } catch (e) { toast('Download failed: ' + e.message, 'err'); }
}

const INR = (n) => '₹' + Number(n || 0).toLocaleString('en-IN', { maximumFractionDigits: 0 });
const INR2 = (n) => '₹' + Number(n || 0).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const cx = (...a) => a.filter(Boolean).join(' ');
const initials = (name) => (name || '?').split(' ').map(w => w[0]).slice(0, 2).join('').toUpperCase();
const cleanTel = (p) => String(p || '').replace(/[^0-9+]/g, '');
const waNum = (p) => { let d = String(p || '').replace(/\D/g, ''); if (d.length === 10) d = '91' + d; else if (d.length === 11 && d[0] === '0') d = '91' + d.slice(1); return d; };
const waHref = (p, text) => `https://wa.me/${waNum(p)}` + (text ? `?text=${encodeURIComponent(text)}` : '');
// Server timestamps are UTC; SQLite returns them without a timezone marker, so the browser
// would wrongly read them as local time. Append 'Z' when no zone is present so they parse as UTC.
const toMs = (iso) => {
  if (!iso) return NaN;
  let s = String(iso);
  if (!/[zZ]|[+-]\d\d:?\d\d$/.test(s)) s += 'Z';
  return new Date(s).getTime();
};
const toDate = (iso) => new Date(toMs(iso));
// Always display timestamps in India Standard Time, regardless of the viewer's device zone.
const IST_TZ = 'Asia/Kolkata';
const fmtDT = (iso) => { const d = toDate(iso); return isNaN(d.getTime()) ? '' : d.toLocaleString('en-IN', { timeZone: IST_TZ, day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' }); };
const fmtHM = (iso) => { const d = toDate(iso); return isNaN(d.getTime()) ? '—' : d.toLocaleTimeString('en-IN', { timeZone: IST_TZ, hour: '2-digit', minute: '2-digit' }); };
const fmtDay = (iso) => { const d = toDate(iso); return isNaN(d.getTime()) ? '' : d.toLocaleDateString('en-IN', { timeZone: IST_TZ, day: '2-digit', month: 'short', year: 'numeric' }); };

// Field-officer presence: "live" if their app pinged within the last 3 minutes.
// "live" if a ping arrived within the last 12s (~3-4 of the 3s refresh cycles). Using a single
// short window made the dot flicker on every tiny network delay; requiring several missed updates
// before showing "offline" keeps the status steady.
const ONLINE_MS = 12 * 1000;
const isOnline = (iso) => !!iso && (Date.now() - toMs(iso)) < ONLINE_MS;
const agoLabel = (iso) => {
  if (!iso) return 'never';
  const s = Math.max(0, Math.round((Date.now() - toMs(iso)) / 1000));
  if (s < 60) return 'just now';
  const m = Math.round(s / 60); if (m < 60) return m + 'm ago';
  const h = Math.round(m / 60); if (h < 24) return h + 'h ago';
  return Math.round(h / 24) + 'd ago';
};
const kmBetween = (a, b) => { const R = 6371, dLa = (b.lat - a.lat) * Math.PI / 180, dLo = (b.lng - a.lng) * Math.PI / 180,
  la1 = a.lat * Math.PI / 180, la2 = b.lat * Math.PI / 180;
  const h = Math.sin(dLa / 2) ** 2 + Math.cos(la1) * Math.cos(la2) * Math.sin(dLo / 2) ** 2; return 2 * R * Math.asin(Math.sqrt(h)); };
// Reusable Call + WhatsApp buttons for a phone number
function ContactBtns({ phone, text, size = 'sm' }) {
  if (!phone) return null;
  return <>
    <a className={cx('btn', size)} href={'tel:' + cleanTel(phone)} title={'Call ' + phone}>📞 Call</a>
    <a className={cx('btn', size)} style={{ background: '#25D366', color: '#04310f', border: 'none' }}
       href={waHref(phone, text)} target="_blank" rel="noreferrer" title="WhatsApp">💬 WhatsApp</a>
  </>;
}

function upiLink(cfg, c, amount) {
  const vpa = cfg && cfg.upi_vpa; if (!vpa) return null;
  const pn = (cfg.upi_payee_name || 'SSD Enterprises');
  const am = Number(amount || c.pending_amount || 0).toFixed(2);
  const tn = `Case ${c.id} ${c.customer_name || ''}`.slice(0, 40);
  return `upi://pay?pa=${encodeURIComponent(vpa)}&pn=${encodeURIComponent(pn)}&am=${am}&cu=INR&tn=${encodeURIComponent(tn)}`;
}
function QR({ text, size = 148 }) {
  const ref = useRef(null);
  useEffect(() => {
    if (!ref.current || !window.QRCode || !text) return;
    ref.current.innerHTML = '';
    try { new window.QRCode(ref.current, { text, width: size, height: size, correctLevel: window.QRCode.CorrectLevel.M }); } catch (e) {}
  }, [text]);
  return <div ref={ref} style={{ display: 'inline-block', background: '#fff', padding: 8, borderRadius: 10 }} />;
}
const propMeta = (s) => s == null ? null : s >= 70 ? { cls: 'paid', label: 'High' } : s >= 40 ? { cls: 'partial', label: 'Medium' } : { cls: 'unpaid', label: 'Low' };
function PropBadge({ score }) {
  const m = propMeta(score); if (!m) return null;
  return <span className={cx('badge', m.cls)} title="Recovery propensity">🎯 {score} {m.label}</span>;
}

/* ---- WebAuthn (passkey / biometric) helpers ---- */
const b64u = {
  toBuf(s) {
    s = String(s).replace(/-/g, '+').replace(/_/g, '/');
    const pad = '='.repeat((4 - (s.length % 4)) % 4);
    const bin = atob(s + pad); const b = new Uint8Array(bin.length);
    for (let i = 0; i < bin.length; i++) b[i] = bin.charCodeAt(i);
    return b.buffer;
  },
  fromBuf(buf) {
    const b = new Uint8Array(buf); let s = '';
    for (let i = 0; i < b.length; i++) s += String.fromCharCode(b[i]);
    return btoa(s).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
  },
};
const passkeySupported = () => typeof window !== 'undefined' && !!window.PublicKeyCredential && !!(navigator.credentials && navigator.credentials.create);

async function registerPasskey(label) {
  const o = await api('/api/auth/webauthn/register/options', { method: 'POST' });
  o.challenge = b64u.toBuf(o.challenge);
  o.user.id = b64u.toBuf(o.user.id);
  if (o.excludeCredentials) o.excludeCredentials = o.excludeCredentials.map(c => ({ ...c, id: b64u.toBuf(c.id) }));
  const cred = await navigator.credentials.create({ publicKey: o });
  const payload = {
    id: cred.id, rawId: b64u.fromBuf(cred.rawId), type: cred.type,
    response: {
      attestationObject: b64u.fromBuf(cred.response.attestationObject),
      clientDataJSON: b64u.fromBuf(cred.response.clientDataJSON),
    },
    clientExtensionResults: cred.getClientExtensionResults ? cred.getClientExtensionResults() : {},
  };
  return api('/api/auth/webauthn/register/verify', { method: 'POST', body: { credential: payload, label: label || 'Passkey' } });
}

async function passkeyAssertion(email) {
  const o = await api('/api/auth/webauthn/login/options', { auth: false, body: { email } });
  o.challenge = b64u.toBuf(o.challenge);
  if (o.allowCredentials) o.allowCredentials = o.allowCredentials.map(c => ({ ...c, id: b64u.toBuf(c.id) }));
  const cred = await navigator.credentials.get({ publicKey: o });
  const payload = {
    id: cred.id, rawId: b64u.fromBuf(cred.rawId), type: cred.type,
    response: {
      authenticatorData: b64u.fromBuf(cred.response.authenticatorData),
      clientDataJSON: b64u.fromBuf(cred.response.clientDataJSON),
      signature: b64u.fromBuf(cred.response.signature),
      userHandle: cred.response.userHandle ? b64u.fromBuf(cred.response.userHandle) : null,
    },
    clientExtensionResults: cred.getClientExtensionResults ? cred.getClientExtensionResults() : {},
  };
  return api('/api/auth/webauthn/login/verify', { auth: false, body: { email, credential: payload } });
}

let _toast;
function Toaster() {
  const [msg, setMsg] = useState(null);
  _toast = (text, kind = 'ok') => { setMsg({ text, kind }); setTimeout(() => setMsg(null), 2600); };
  if (!msg) return null;
  return <div className={cx('toast', msg.kind)}>{msg.text}</div>;
}
const toast = (t, k) => _toast && _toast(t, k);

/* Map loader — OpenStreetMap via Leaflet (no API key, no billing).
   Exposes a tiny window.google.maps-compatible shim so every existing map view works unchanged. */
let _mapsPromise = null;
const _toLL = (x) => !x ? x : Array.isArray(x) ? x : (x.lat !== undefined ? [x.lat, x.lng] : x);
function _buildMapsShim() {
  const L = window.L;
  const _raw = (m) => (m && m._map) ? m._map : m;
  const SymbolPath = { CIRCLE: 'circle', FORWARD_CLOSED_ARROW: 'arrow', BACKWARD_CLOSED_ARROW: 'arrow' };
  const _pin = (icon, label) => {
    const d = Math.max(12, ((icon && icon.scale) || 7) * 2);
    const fill = (icon && icon.fillColor) || '#2563EB';
    const stroke = (icon && icon.strokeColor) || '#1D4ED8';
    const sw = (icon && icon.strokeWeight) || 2;
    const txt = (label && label.text) || '';
    const tc = (label && label.color) || '#ffffff';
    const html = '<div style="width:' + d + 'px;height:' + d + 'px;border-radius:50%;background:' + fill
      + ';border:' + sw + 'px solid ' + stroke + ';display:flex;align-items:center;justify-content:center;color:' + tc
      + ';font-weight:700;font-size:' + Math.round(d * 0.42) + 'px;font-family:sans-serif;box-shadow:0 1px 4px rgba(0,0,0,.4)">' + txt + '</div>';
    return L.divIcon({ html, className: '', iconSize: [d, d], iconAnchor: [d / 2, d / 2] });
  };
  class GMap {
    constructor(el, opts) {
      opts = opts || {};
      this._map = L.map(el, { zoomControl: true }).setView(_toLL(opts.center) || [17.72, 83.30], opts.zoom || 11);
      L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', { maxZoom: 19, attribution: '&copy; OpenStreetMap' }).addTo(this._map);
      const m = this._map;
      const fix = () => { try { m.invalidateSize(); } catch (e) {} };
      [120, 350, 700, 1200].forEach(t => setTimeout(fix, t));   // re-measure once the container has real height
      window.addEventListener('resize', fix);
    }
    fitBounds(b, pad) { try { this._map.fitBounds(b._b, { padding: [pad || 40, pad || 40] }); } catch (e) {} }
    panTo(ll) { this._map.panTo(_toLL(ll)); }
    setCenter(ll) { this._map.setView(_toLL(ll), this._map.getZoom()); }
    setZoom(z) { this._map.setZoom(z); }
  }
  class GMarker {
    constructor(o) { o = o || {}; this._pos = o.position;
      this._m = L.marker(_toLL(o.position), { icon: _pin(o.icon, o.label), title: o.title || '', zIndexOffset: o.zIndex || 0 });
      if (o.map) this._m.addTo(_raw(o.map)); }
    setPosition(ll) { this._pos = ll; this._m.setLatLng(_toLL(ll)); }
    getPosition() { return this._pos; }
    setMap(m) { if (!m) { if (this._m._map) this._m.remove(); } else this._m.addTo(_raw(m)); }
    addListener(ev, fn) { this._m.on(ev, fn); }
  }
  class GPoly {
    constructor(o) { o = o || {}; this._l = L.polyline((o.path || []).map(_toLL),
      { color: o.strokeColor || '#2563EB', weight: o.strokeWeight || 4, opacity: o.strokeOpacity != null ? o.strokeOpacity : 1 });
      if (o.map) this._l.addTo(_raw(o.map)); }
    setMap(m) { if (!m) { if (this._l._map) this._l.remove(); } else this._l.addTo(_raw(m)); }
    setPath(p) { this._l.setLatLngs((p || []).map(_toLL)); }
  }
  class GCircle {
    constructor(o) { o = o || {}; this._c = L.circle(_toLL(o.center),
      { radius: o.radius || 10, color: o.strokeColor || '#2563EB', weight: o.strokeWeight || 1,
        opacity: o.strokeOpacity != null ? o.strokeOpacity : .5, fillColor: o.fillColor || '#2563EB',
        fillOpacity: o.fillOpacity != null ? o.fillOpacity : .15 });
      if (o.map) this._c.addTo(_raw(o.map)); }
    setCenter(ll) { this._c.setLatLng(_toLL(ll)); }
    setRadius(r) { this._c.setRadius(r); }
    setMap(m) { if (!m) { if (this._c._map) this._c.remove(); } else this._c.addTo(_raw(m)); }
  }
  class GInfo {
    constructor(o) { this._content = (o && o.content) || ''; }
    open(map, marker) { try { L.popup().setLatLng(_toLL(marker._pos)).setContent(this._content).openOn(_raw(map)); } catch (e) {} }
  }
  class GBounds { constructor() { this._b = L.latLngBounds([]); } extend(ll) { this._b.extend(_toLL(ll)); } }
  return { maps: { Map: GMap, Marker: GMarker, Polyline: GPoly, Circle: GCircle, InfoWindow: GInfo, LatLngBounds: GBounds, SymbolPath } };
}
function loadMaps() {
  if (window.google && window.google.maps) return Promise.resolve(window.google);
  if (_mapsPromise) return _mapsPromise;
  _mapsPromise = new Promise((resolve, reject) => {
    const ready = () => { try { window.google = _buildMapsShim(); resolve(window.google); } catch (e) { reject(e); } };
    if (window.L) { ready(); return; }
    if (!document.getElementById('leaflet-css')) {
      const link = document.createElement('link'); link.id = 'leaflet-css'; link.rel = 'stylesheet';
      link.href = 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.css'; document.head.appendChild(link);
    }
    const s = document.createElement('script');
    s.src = 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.js';
    s.async = true; s.onload = ready; s.onerror = () => reject(new Error('leaflet-load-failed'));
    document.head.appendChild(s);
  });
  return _mapsPromise;
}
/* Draw a travelled route as a continuous line on the (Leaflet-backed) map:
   - blue line along the actual path
   - grey dashed segments where the officer was offline (a gap between pings)
   - clickable dots + line: tapping shows the time & coordinates of that point
   Returns { layers, path, points } so the caller can clear/replay it. */
/* Compass bearing (deg, 0=N) from point a to b — used for direction arrows / the moving icon. */
function bearingDeg(a, b) {
  const toR = x => x * Math.PI / 180, toD = x => x * 180 / Math.PI;
  const dLon = toR(b.lng - a.lng);
  const y = Math.sin(dLon) * Math.cos(toR(b.lat));
  const x = Math.cos(toR(a.lat)) * Math.sin(toR(b.lat)) - Math.sin(toR(a.lat)) * Math.cos(toR(b.lat)) * Math.cos(dLon);
  return (toD(Math.atan2(y, x)) + 360) % 360;
}
/* A Leaflet DivIcon that looks like a live rider pin (Swiggy/Zomato style). */
function fosDivIcon(label, heading) {
  const L = window.L; if (!L) return null;
  if (!document.getElementById('fospulse-css')) {
    const st = document.createElement('style'); st.id = 'fospulse-css';
    st.textContent = '@keyframes fospulse{0%{transform:scale(.5);opacity:.7}100%{transform:scale(1.7);opacity:0}}';
    document.head.appendChild(st);
  }
  const h = heading || 0;
  return L.divIcon({
    className: '', iconSize: [34, 34], iconAnchor: [17, 17],
    html: '<div style="position:relative;width:34px;height:34px">'
      + '<div style="position:absolute;inset:0;border-radius:50%;background:rgba(37,99,235,.25);animation:fospulse 1.6s ease-out infinite"></div>'
      + '<div style="position:absolute;top:6px;left:6px;width:22px;height:22px;border-radius:50%;background:#2563EB;border:2px solid #fff;'
      + 'box-shadow:0 2px 6px rgba(0,0,0,.45);display:flex;align-items:center;justify-content:center;font-size:13px">🏍️</div>'
      + (label ? '<div style="position:absolute;top:-14px;left:50%;transform:translateX(-50%);white-space:nowrap;background:#111;color:#fff;font-size:10px;padding:1px 5px;border-radius:6px">' + label + '</div>' : '')
      + '</div>',
  });
}
/* Smoothly slide a Leaflet marker from its current position to [lat,lng] (~900ms). */
function animateMarker(marker, lat, lng, ms) {
  const L = window.L; if (!marker || !L) return;
  const from = marker.getLatLng(); const to = L.latLng(lat, lng);
  if (from.lat === to.lat && from.lng === to.lng) return;
  const dur = ms || 900; const t0 = performance.now();
  if (marker._anim) cancelAnimationFrame(marker._anim);
  const tick = (now) => {
    const k = Math.min(1, (now - t0) / dur);
    const e = 1 - Math.pow(1 - k, 3);   // ease-out
    marker.setLatLng([from.lat + (to.lat - from.lat) * e, from.lng + (to.lng - from.lng) * e]);
    if (k < 1) marker._anim = requestAnimationFrame(tick);
  };
  marker._anim = requestAnimationFrame(tick);
}
function clearRouteLayers(r) { if (r && r.layers) r.layers.forEach(function (l) { try { l.remove(); } catch (e) {} }); }
function drawRouteLeaflet(gmap, pts, opts) {
  opts = opts || {};
  const L = window.L;
  const out = { layers: [], path: [], points: [] };
  if (!L || !gmap || !gmap._map) return out;
  const lm = gmap._map;
  const P = (pts || []).map(p => ({ lat: p.latitude, lng: p.longitude, t: toMs(p.created_at || p.last_seen || p.at) }))
    .filter(p => p.lat != null && p.lng != null && !isNaN(p.lat) && !isNaN(p.lng));
  if (!P.length) return out;
  out.points = P; out.path = P.map(p => [p.lat, p.lng]);
  const GAP = 150 * 1000;   // pings more than 2.5 min apart = the officer was offline
  const popupHtml = (p) => {
    const d = toDate(p.t);
    const ok = !isNaN(d.getTime());
    const when = ok
      ? '<b>' + d.toLocaleTimeString('en-IN', { timeZone: IST_TZ, hour: '2-digit', minute: '2-digit', second: '2-digit' }) + '</b><br>'
        + d.toLocaleDateString('en-IN', { timeZone: IST_TZ }) + '<br>'
      : '<span style="color:#64748b">Time not recorded</span><br>';
    return '<div style="font-family:sans-serif;font-size:12.5px;color:#111;line-height:1.5">'
      + when + p.lat.toFixed(6) + ', ' + p.lng.toFixed(6) + '</div>';
  };
  let run = [P[0]];
  const flush = () => {
    if (run.length >= 2) {
      const ln = L.polyline(run.map(p => [p.lat, p.lng]), { color: '#2563EB', weight: 5, opacity: .9 }).addTo(lm);
      const rc = run.slice();
      ln.on('click', (e) => {
        let b = rc[0], bd = Infinity;
        rc.forEach(p => { const dd = (p.lat - e.latlng.lat) ** 2 + (p.lng - e.latlng.lng) ** 2; if (dd < bd) { bd = dd; b = p; } });
        L.popup().setLatLng([b.lat, b.lng]).setContent(popupHtml(b)).openOn(lm);
      });
      out.layers.push(ln);
    }
  };
  for (let i = 1; i < P.length; i++) {
    if (P[i].t - P[i - 1].t > GAP) {
      flush();
      out.layers.push(L.polyline([[P[i - 1].lat, P[i - 1].lng], [P[i].lat, P[i].lng]],
        { color: '#8494A8', weight: 4, opacity: .7, dashArray: '6,9' }).addTo(lm));
      run = [P[i]];
    } else run.push(P[i]);
  }
  flush();
  const step = Math.max(1, Math.floor(P.length / 180));   // cap clickable dots ~180
  for (let i = 0; i < P.length; i += step) {
    const p = P[i];
    const dot = L.circleMarker([p.lat, p.lng], { radius: 3.5, color: '#1D4ED8', fillColor: '#3B82F6', fillOpacity: .9, weight: 1 }).addTo(lm);
    dot.on('click', () => L.popup().setLatLng([p.lat, p.lng]).setContent(popupHtml(p)).openOn(lm));
    out.layers.push(dot);
  }
  // Direction arrows along the path — show which way the officer was moving.
  if (opts.arrows !== false && P.length >= 2) {
    const astep = Math.max(1, Math.floor(P.length / 14));
    for (let i = astep; i < P.length; i += astep) {
      const a = P[i - 1], b = P[i];
      if (a.lat === b.lat && a.lng === b.lng) continue;
      const brg = bearingDeg(a, b);
      const arrow = L.marker([b.lat, b.lng], { interactive: false, zIndexOffset: 300, icon: L.divIcon({
        className: '', iconSize: [16, 16], iconAnchor: [8, 8],
        html: '<div style="transform:rotate(' + (brg - 90) + 'deg);color:#1D4ED8;font-size:15px;line-height:16px;text-align:center">➤</div>',
      }) }).addTo(lm);
      out.layers.push(arrow);
    }
  }
  const badge = (p, txt, color) => L.marker([p.lat, p.lng], { zIndexOffset: 500, icon: L.divIcon({
    className: '', iconSize: [22, 22], iconAnchor: [11, 11],
    html: '<div style="width:22px;height:22px;border-radius:50%;background:' + color + ';border:2px solid #fff;color:#fff;display:flex;align-items:center;justify-content:center;font-weight:700;font-size:11px;box-shadow:0 1px 4px rgba(0,0,0,.4)">' + txt + '</div>',
  }) }).addTo(lm);
  out.layers.push(badge(P[0], 'S', '#16A34A'));
  if (!opts.noEnd) out.layers.push(badge(P[P.length - 1], 'E', '#DC2626'));
  if (opts.fit !== false) { try { lm.fitBounds(L.latLngBounds(out.path), { padding: [50, 50] }); } catch (e) {} }
  return out;
}

function getGPS(opts = {}) {
  return new Promise((resolve, reject) => {
    if (!navigator.geolocation) return reject(new Error('Geolocation unavailable'));
    navigator.geolocation.getCurrentPosition(
      (p) => resolve(p.coords), reject,
      { enableHighAccuracy: true, timeout: 12000, maximumAge: 0, ...opts });
  });
}

/* Burn GPS coordinates + date/time + address onto a captured photo (GPS-camera style).
   Uses the browser's real geolocation, so the stamp is trustworthy regardless of the
   phone's camera app. Returns a new JPEG File; falls back to the original on any error. */
async function stampPhoto(file, coords, address) {
  try {
    let src, W, H;
    if (window.createImageBitmap) {
      try { src = await createImageBitmap(file, { imageOrientation: 'from-image' }); }
      catch (e) { src = await createImageBitmap(file); }
      W = src.width; H = src.height;
    } else {
      src = await new Promise((res, rej) => { const i = new Image(); i.onload = () => res(i); i.onerror = rej; i.src = URL.createObjectURL(file); });
      W = src.naturalWidth; H = src.naturalHeight;
    }
    const scale = Math.min(1, 1600 / Math.max(W, H || 1));
    const cw = Math.max(1, Math.round(W * scale)), ch = Math.max(1, Math.round(H * scale));
    const canvas = document.createElement('canvas'); canvas.width = cw; canvas.height = ch;
    const ctx = canvas.getContext('2d');
    ctx.drawImage(src, 0, 0, cw, ch);
    const now = new Date();
    const lines = [
      now.toLocaleString('en-IN', { timeZone: IST_TZ, day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' }),
      coords ? `Lat ${coords.latitude.toFixed(6)}, Lng ${coords.longitude.toFixed(6)}${coords.accuracy ? ` (±${Math.round(coords.accuracy)}m)` : ''}` : 'GPS: not available',
    ];
    if (address) lines.push(String(address).replace(/\s+/g, ' ').slice(0, 64));
    const pad = Math.round(cw * 0.022);
    const fs = Math.max(13, Math.round(cw * 0.03));
    const lh = Math.round(fs * 1.4);
    const barH = lh * lines.length + pad * 1.6;
    ctx.fillStyle = 'rgba(0,0,0,.58)';
    ctx.fillRect(0, ch - barH, cw, barH);
    ctx.fillStyle = '#fff'; ctx.textBaseline = 'top';
    lines.forEach((t, i) => {
      ctx.font = `${i === 0 ? 700 : 500} ${fs}px sans-serif`;
      ctx.fillText(t, pad, ch - barH + pad * 0.8 + i * lh, cw - pad * 2);
    });
    const blob = await new Promise((res) => canvas.toBlob(res, 'image/jpeg', 0.85));
    if (src && src.close) src.close();
    return blob ? new File([blob], 'visit_geotagged.jpg', { type: 'image/jpeg' }) : file;
  } catch (e) { return file; }
}

/* Chart.js wrapper */
function ChartBox({ type, data, options, height = 240 }) {
  const ref = useRef(null); const chart = useRef(null);
  useEffect(() => {
    if (!ref.current || !window.Chart) return;
    try {
      chart.current = new window.Chart(ref.current, {
        type, data,
        options: {
          responsive: true, maintainAspectRatio: false,
          plugins: { legend: { labels: { color: '#475569', font: { family: 'Hanken Grotesk' } } } },
          scales: type === 'doughnut' || type === 'pie' ? {} : {
            x: { ticks: { color: '#64748B' }, grid: { color: 'rgba(15,27,45,.07)' } },
            y: { ticks: { color: '#64748B' }, grid: { color: 'rgba(15,27,45,.07)' } },
          }, ...options,
        },
      });
    } catch (e) { console.error('Chart render failed:', e); }
    return () => { try { chart.current && chart.current.destroy(); } catch (e) {} };
  }, [JSON.stringify(data), type]);
  return <div style={{ height }}><canvas ref={ref} /></div>;
}
const GOLD = '#2563EB', GOLD2 = '#1D4ED8';
const PALETTE = ['#2563EB', '#0EA5E9', '#16A34A', '#F97316', '#8B5CF6', '#14B8A6', '#EAB308'];

/* Role display labels (internal keys stay admin/manager/fos/telecaller for RBAC) */
const ROLE_LABEL = { admin: 'Administrator', manager: 'Collections Manager', teamlead: 'Team Lead', fos: 'Field Agent', telecaller: 'Tele-calling Agent', backend: 'Back-office Official', headoffice: 'Head Office', hr: 'HR', it: 'IT', staff: 'Staff' };
const roleName = (r) => ROLE_LABEL[r] || r;

/* ============================== Login ============================== */
/* Shows a "Download Android app" button, but only once a build has been published to the
   server (/downloads/version.json exists). Serves the APK straight from this domain. */
function AndroidDownloadButton({ block, style, compact }) {
  const [ver, setVer] = useState(null);
  useEffect(() => {
    fetch('/downloads/version.json', { cache: 'no-store' })
      .then(r => (r.ok ? r.json() : null)).then(setVer).catch(() => setVer(null));
  }, []);
  if (!ver) return null;
  const label = compact ? '🤖 Android app' : '🤖 Download Android app';
  return (
    <a className={cx('btn', block && 'block')} href="/downloads/RecoverIQ-native.apk" download
      style={{ marginTop: compact ? 0 : 10, ...style }}
      title={'Install on an Android phone' + (ver.version_name ? ' (v' + ver.version_name + ')' : '')}>
      {label}{ver.version_name && !compact ? ' · v' + ver.version_name : ''}
    </a>
  );
}
function Login({ onLogin, config }) {
  const [email, setEmail] = useState(''); const [pw, setPw] = useState('');
  const [busy, setBusy] = useState(false); const [err, setErr] = useState('');
  const [otp, setOtp] = useState(''); const [need2fa, setNeed2fa] = useState(false);
  const brand = (config && config.brand_name) || 'RecoverIQ';
  const tagline = (config && config.brand_tagline) || 'Collections & Recovery Intelligence';
  const submit = async (e) => {
    e && e.preventDefault(); setErr(''); setBusy(true);
    try {
      const body = { email, password: pw, device_id: deviceId, device_label: deviceLabel };
      if (need2fa) body.otp = otp;
      const r = await api('/api/auth/login-json', { auth: false, body });
      store.t = r.access_token; store.u = r.user; onLogin(r.user);
    } catch (ex) {
      if ((ex.message || '') === '2FA_REQUIRED') { setNeed2fa(true); setErr('Enter the 6-digit code from your authenticator app.'); }
      else setErr(ex.message || 'Login failed');
    } finally { setBusy(false); }
  };
  const signInPasskey = async () => {
    if (!email) { setErr('Enter your email first, then use your passkey.'); return; }
    setErr(''); setBusy(true);
    try {
      const r = await passkeyAssertion(email);
      store.t = r.access_token; store.u = r.user; onLogin(r.user);
    } catch (ex) { setErr(ex.message === 'unauthorized' ? 'Passkey sign-in failed' : (ex.message || 'Passkey sign-in failed')); }
    finally { setBusy(false); }
  };
  return (
    <div className="login">
      <div className="login-art glass" style={{ borderRadius: 0, border: 'none' }}>
        <div className="orb a"></div><div className="orb b"></div>
        <div className="brand" style={{ padding: 0 }}>
          <img src="assets/logo.png" alt="" />
          <div><div className="n brandfont">{brand}</div><div className="s">{tagline}</div></div>
        </div>
        <div>
          <div className="eyebrow">Collections Platform</div>
          <div className="big">Every case tracked.<br/>Every rupee recovered.</div>
          <p style={{ color: 'var(--ink-soft)', maxWidth: 440, marginTop: 18, lineHeight: 1.6 }}>
            One intelligent platform for digital outreach, field recovery with live GPS,
            payments, litigation tracking and real-time analytics — across every borrower and branch.
          </p>
        </div>
        <div className="muted" style={{ fontSize: 12 }}>© {brand}</div>
      </div>
      <div className="login-form">
        <form className="login-card glass" onSubmit={submit}>
          <div className="brand" style={{ padding: '0 0 14px' }}>
            <img src="assets/logo.png" alt="" style={{ width: 38, height: 38 }} />
            <div><div className="n brandfont" style={{ fontSize: 16 }}>{brand}</div>
              <div className="s">Sign in</div></div>
          </div>
          <div className="field"><label>Email</label>
            <input className="input" type="email" value={email} autoComplete="username"
              onChange={e => setEmail(e.target.value)} placeholder="you@company.com" required /></div>
          <div className="field"><label>Password</label>
            <input className="input" type="password" value={pw} autoComplete="current-password"
              onChange={e => setPw(e.target.value)} placeholder="••••••••" required /></div>
          {need2fa && <div className="field"><label>Authenticator code (2FA)</label>
            <input className="input" inputMode="numeric" autoComplete="one-time-code" value={otp}
              onChange={e => setOtp(e.target.value.replace(/\D/g, '').slice(0, 6))}
              placeholder="123456" autoFocus /></div>}
          {err && <div style={{ color: need2fa ? 'var(--ink-soft)' : 'var(--bad)', fontSize: 13, marginBottom: 10 }}>{err}</div>}
          <button className="btn gold block" disabled={busy}>{busy ? 'Signing in…' : (need2fa ? 'Verify & sign in' : 'Sign in')}</button>
          {passkeySupported() &&
            <button type="button" className="btn block" style={{ marginTop: 10 }} disabled={busy} onClick={signInPasskey}>
              🔐 Sign in with passkey / biometric</button>}
          {config && config.google_client_id ?
            <div id="gbtn" style={{ marginTop: 14, display: 'flex', justifyContent: 'center' }}></div> : null}
          <AndroidDownloadButton block />
          <div className="divider"></div>
          <div className="muted" style={{ fontSize: 11.5, lineHeight: 1.6 }}>
            Use the credentials issued by your administrator. Trouble signing in from a new device?
            Ask your admin to approve it.
          </div>
        </form>
      </div>
    </div>
  );
}

/* ============================== shared bits ============================== */
function StatusBadge({ s }) {
  const map = { paid: 'paid', unpaid: 'unpaid', new: 'new', allocated: 'allocated', ptp: 'ptp', in_progress: 'partial' };
  return <span className={cx('badge', map[s] || 'new')}>{(s || '—').replace('_', ' ')}</span>;
}
function PaidBadge({ s }) {
  const k = (s || 'UNPAID').toLowerCase();
  return <span className={cx('badge', k.includes('unpaid') ? 'unpaid' : k.includes('partial') ? 'partial' : 'paid')}>{s || 'UNPAID'}</span>;
}
function Loader({ size }) { return <div className={cx('ssd-loader', size)}><img src="assets/logo.png" alt="Loading…" /></div>; }

/* ============================== Dashboard ============================== */
function StatCard({ icon, label, value, sub, accent, valueColor }) {
  return (
    <div className={cx('glass stat', accent)}>
      <div className="top"><div className="l">{label}</div><div className="ic">{icon}</div></div>
      <div className="v" style={valueColor ? { color: valueColor } : null}>{value}</div>
      <div className="sub">{sub}</div>
    </div>
  );
}

/* Cash-collected comparison across time windows: FTD (today) / MTD / LMTD / Overall. */
const TREND_META = [['ftd', 'FTD', 'For the day (today)'], ['mtd', 'MTD', 'Month till day'],
  ['lmtd', 'LMTD', 'Last month till the same day'], ['overall', 'Overall', 'Lifetime collected']];
function TrendStrip({ trends, title, compact }) {
  if (!trends) return null;
  const money = v => '₹' + Math.round(Number(v) || 0).toLocaleString('en-IN');
  return (
    <div className={compact ? '' : 'glass card'} style={{ padding: compact ? 0 : 10, marginTop: compact ? 8 : 12 }}>
      {title && <div className="muted" style={{ fontSize: 12, marginBottom: 6 }}>{title}</div>}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(108px,1fr))', gap: 8 }}>
        {TREND_META.map(([k, lbl, hint]) => (
          <div key={k} title={hint} style={{ background: 'var(--glass-2)', border: '1px solid var(--stroke-soft)', borderRadius: 10, padding: '7px 10px' }}>
            <div className="muted" style={{ fontSize: 11 }}>{lbl}<span style={{ fontSize: 10, opacity: .7 }}> · {hint.split(' (')[0].replace('Last month till the same day', 'Last MTD').replace('Month till day', 'This MTD')}</span></div>
            <b style={{ fontSize: 15, color: k === 'ftd' ? 'var(--good)' : 'var(--ink)' }}>{money(trends[k])}</b>
          </div>
        ))}
      </div>
    </div>
  );
}

const STAGE_META = {
  new: { label: 'New', color: '#0EA5E9' },
  allocated: { label: 'Allocated', color: '#2563EB' },
  in_progress: { label: 'In Progress', color: '#D97706' },
  ptp: { label: 'PTP', color: '#8B5CF6' },
  paid: { label: 'Resolved', color: '#16A34A' },
  unpaid: { label: 'Unpaid', color: '#DC2626' },
};

function Dashboard({ user, branch }) {
  const [d, setD] = useState(null); const [err, setErr] = useState(''); const [hl, setHl] = useState(null);
  const isMgr = (user.role === 'admin' || user.role === 'manager' || user.role === 'headoffice') && !branch;
  const money = v => '₹' + Math.round(Number(v) || 0).toLocaleString('en-IN');
  const loadDash = () => {
    api('/api/analytics/dashboard' + (branch ? '?branch=' + encodeURIComponent(branch) : '')).then(setD).catch(e => setErr(e.message));
    if (isMgr) api('/api/mis/highlights').then(setHl).catch(() => {});
  };
  useEffect(() => { loadDash(); }, [branch]);
  useDataChanged(loadDash);   // live: refresh dashboard on any log/payment/edit
  if (err) return <div className="glass card" style={{ color: 'var(--bad)' }}>{err}</div>;
  if (!d) return <Loader />;
  const k = d.kpis;
  const statusMap = {}; (d.by_status || []).forEach(s => { statusMap[s.status] = s.count; });
  const stages = ['new', 'allocated', 'in_progress', 'ptp', 'paid']
    .map(s => ({ key: s, ...STAGE_META[s], count: statusMap[s] || 0 }));
  const maxStage = Math.max(1, ...stages.map(s => s.count));
  const rate = Math.max(0, Math.min(100, k.recovery_rate || 0));
  const lb = d.fo_leaderboard || [];
  const maxLb = Math.max(1, ...lb.map(f => f.collected));
  const collectedToday = d.trend && d.trend.length ? d.trend[d.trend.length - 1].collected : 0;

  return (
    <div>
      <div className="kpis">
        <StatCard icon="📁" label="Total Cases" accent="blue" value={k.total_cases.toLocaleString('en-IN')}
          sub={<span>{k.paid} resolved · {k.unpaid} open · {k.partial} partial</span>} />
        <StatCard icon="🏁" label="Resolution %" accent="" value={(k.resolution_rate != null ? k.resolution_rate : 0) + '%'}
          valueColor="var(--info)" sub={<span>{k.paid} of {k.total_cases} cases settled</span>} />
        <StatCard icon="✅" label="Recovered" accent="green" value={INR(k.received)} valueColor="var(--good)"
          sub={<span><b style={{ color: 'var(--good)' }}>{k.recovery_rate}%</b> recovery rate (₹)</span>} />
        <StatCard icon="⏳" label="Pending" accent="amber" value={INR(k.pending)} valueColor="var(--warn)"
          sub={<span>{INR(collectedToday)} collected today</span>} />
        <StatCard icon="🎯" label="Portfolio Target" accent="" value={INR(k.target)}
          sub="Total outstanding" />
      </div>

      {hl && <div className="glass card" style={{ padding: 14, marginTop: 4 }}>
        <div className="section-h" style={{ marginBottom: 8 }}><h3 style={{ margin: 0 }}>📈 MIS highlights</h3>
          <span className="muted" style={{ fontSize: 12 }}>live · open MIS for full detail</span></div>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill,minmax(150px,1fr))', gap: 10 }}>
          <div className="glass card" style={{ padding: 12 }}><div className="muted" style={{ fontSize: 12 }}>Target gap (ENR)</div><b style={{ fontSize: 19, color: 'var(--bad)' }}>{money(hl.target_gap)}</b><div className="muted" style={{ fontSize: 11 }}>{hl.employees_behind}/{hl.employees_total} behind target</div></div>
          <div className="glass card" style={{ padding: 12 }}><div className="muted" style={{ fontSize: 12 }}>Untouched cases</div><b style={{ fontSize: 19, color: 'var(--warn)' }}>{hl.untouched}</b><div className="muted" style={{ fontSize: 11 }}>{money(hl.untouched_pending)} pending</div></div>
          <div className="glass card" style={{ padding: 12 }}><div className="muted" style={{ fontSize: 12 }}>PTP broken</div><b style={{ fontSize: 19, color: 'var(--bad)' }}>{hl.ptp_broken}</b></div>
          <div className="glass card" style={{ padding: 12 }}><div className="muted" style={{ fontSize: 12 }}>Realization</div><b style={{ fontSize: 19 }}>{hl.realization_pct}%</b><div className="muted" style={{ fontSize: 11 }}>collected ÷ NORM</div></div>
          <div className="glass card" style={{ padding: 12 }}><div className="muted" style={{ fontSize: 12 }}>Achieved (ENR)</div><b style={{ fontSize: 19, color: 'var(--good)' }}>{hl.achieved_pct}%</b><div className="muted" style={{ fontSize: 11 }}>{money(hl.paid_enr)} of {money(hl.total_enr)}</div></div>
        </div>
        <div className="grid2" style={{ gridTemplateColumns: '1fr 1fr', gap: 12, marginTop: 12 }}>
          <div><div className="muted" style={{ fontSize: 12, marginBottom: 4 }}>Most behind target</div>
            {(hl.behind_targets || []).slice(0, 5).map((r, i) => <div key={i} className="stat-row"><span className="k">{r.emp} <span className="muted" style={{ fontSize: 11 }}>· {r.product}</span></span><b style={{ color: 'var(--bad)' }}>{money(r.gap_enr)}</b></div>)}
            {(!hl.behind_targets || !hl.behind_targets.length) && <div className="muted" style={{ fontSize: 12 }}>No targets set yet.</div>}</div>
          <div><div className="muted" style={{ fontSize: 12, marginBottom: 4 }}>Top untouched high-value</div>
            {(hl.top_untouched || []).slice(0, 5).map((r, i) => <div key={i} className="stat-row"><span className="k">{r.customer || '—'} <span className="muted" style={{ fontSize: 11 }}>· {r.product}</span></span><b style={{ color: 'var(--warn)' }}>{money(r.pending)}</b></div>)}
            {(!hl.top_untouched || !hl.top_untouched.length) && <div className="muted" style={{ fontSize: 12 }}>All cases have been contacted.</div>}</div>
        </div>
      </div>}

      <div className="grid2" style={{ marginBottom: 16 }}>
        <div className="glass card">
          <div className="section-h"><h3>Recovery Progress</h3>
            <span className="badge paid" style={{ fontSize: 12 }}>{rate}% of target</span></div>
          <div className="progress" style={{ height: 14, marginTop: 4 }}><i style={{ width: rate + '%' }} /></div>
          <div className="prog-legend">
            <div><span className="dot" style={{ background: 'var(--good)' }} />Recovered <b>{INR(k.received)}</b></div>
            <div><span className="dot" style={{ background: 'var(--warn)' }} />Pending <b>{INR(k.pending)}</b></div>
            <div><span className="dot" style={{ background: 'var(--gold-2)' }} />Target <b>{INR(k.target)}</b></div>
          </div>
        </div>
        <div className="glass card">
          <div className="section-h"><h3>Resolution Status</h3></div>
          <ChartBox type="doughnut" height={190} options={{ cutout: '70%' }} data={{
            labels: ['Resolved', 'Open', 'Partial'],
            datasets: [{ data: [k.paid, k.unpaid, k.partial], backgroundColor: ['#16A34A', '#DC2626', '#D97706'], borderWidth: 0 }],
          }} />
        </div>
      </div>

      <div className="glass card" style={{ marginBottom: 16 }}>
        <div className="section-h"><h3>Collections Pipeline</h3></div>
        <div className="pipe">
          {stages.map(s => <div className="st" key={s.key}>
            <div className="n" style={{ color: s.color }}>{s.count}</div>
            <div className="t">{s.label}</div>
            <div className="bar" style={{ background: s.color, width: Math.max(6, s.count / maxStage * 100) + '%' }} />
          </div>)}
        </div>
      </div>

      <div className="grid2" style={{ marginBottom: 16 }}>
        <div className="glass card">
          <div className="section-h"><h3>Collections — last 14 days</h3></div>
          {d.trend.length ? <ChartBox type="line" height={260} data={{
            labels: d.trend.map(t => t.date.slice(5)),
            datasets: [{ label: 'Collected', data: d.trend.map(t => t.collected), borderColor: GOLD,
              backgroundColor: 'rgba(37,99,235,.12)', fill: true, tension: .4, pointRadius: 0,
              borderWidth: 2.5, pointHoverRadius: 5 }],
          }} /> : <p className="muted">No visit collections logged yet.</p>}
        </div>
        <div className="glass card">
          <div className="section-h"><h3>Recovery by Bank</h3></div>
          {d.by_bank.length ? <ChartBox type="bar" height={260} options={{ scales: { x: { stacked: true, ticks: { color: '#8C846F' }, grid: { display: false } }, y: { stacked: true, ticks: { color: '#8C846F' }, grid: { color: 'rgba(255,255,255,.05)' } } } }} data={{
            labels: d.by_bank.map(b => b.bank),
            datasets: [
              { label: 'Received', data: d.by_bank.map(b => b.received), backgroundColor: GOLD, borderRadius: 5 },
              { label: 'Pending', data: d.by_bank.map(b => b.pending), backgroundColor: 'rgba(220,38,38,.55)', borderRadius: 5 },
            ],
          }} /> : <p className="muted">No data.</p>}
        </div>
      </div>

      <div className="grid2" style={{ marginBottom: 16 }}>
        <div className="glass card">
          <div className="section-h"><h3>Top Dispositions</h3></div>
          {d.by_disposition.length ? <ChartBox type="bar" height={250} options={{ indexAxis: 'y', plugins: { legend: { display: false } } }} data={{
            labels: d.by_disposition.map(x => x.disposition),
            datasets: [{ label: 'Cases', data: d.by_disposition.map(x => x.count), backgroundColor: PALETTE, borderRadius: 5 }],
          }} /> : <p className="muted">No dispositions yet.</p>}
        </div>
        {user.role === 'admin' && lb.length > 0 ? (
          <div className="glass card">
            <div className="section-h"><h3>Field Agent Leaderboard</h3></div>
            <div className="lb">{lb.map((f, i) => <div className="row" key={i}>
              <div className="rank">{i + 1}</div>
              <div className="nm">{f.name}<div className="muted" style={{ fontSize: 12, fontWeight: 400 }}>{f.visits} visits</div>
                <div className="progress" style={{ height: 5, marginTop: 6 }}><i style={{ width: (f.collected / maxLb * 100) + '%' }} /></div></div>
              <div className="amt">{INR(f.collected)}</div>
            </div>)}</div>
          </div>
        ) : (
          <div className="glass card">
            <div className="section-h"><h3>Resolution Mix</h3></div>
            <ChartBox type="bar" height={250} options={{ plugins: { legend: { display: false } } }} data={{
              labels: stages.map(s => s.label),
              datasets: [{ data: stages.map(s => s.count), backgroundColor: stages.map(s => s.color), borderRadius: 5 }],
            }} />
          </div>
        )}
      </div>
    </div>
  );
}

/* ============================== Cases (admin) ============================== */
const MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'];

/* Admin: onboard a NEW bank and/or product with its closing rule. */
function AddProductModal({ presetBank, onClose, onAdded }) {
  const [bank, setBank] = useState(presetBank || '');
  const [product, setProduct] = useState('');
  const [segment, setSegment] = useState('Credit Card');
  const [closing, setClosing] = useState('month_end');
  const [busy, setBusy] = useState(false); const [err, setErr] = useState('');
  const save = async () => {
    if (!bank.trim()) { setErr('Bank name is required'); return; }
    setBusy(true); setErr('');
    try {
      const r = await api('/api/catalog/product', { method: 'POST',
        body: { bank: bank.trim(), product: product.trim(), segment, closing_type: closing } });
      toast(`Added ${r.bank}${r.product ? ' · ' + r.product : ' (bank)'}.`);
      onAdded(r.bank, r.product || '');
    } catch (e) { setErr(e.message); } finally { setBusy(false); }
  };
  return (
    <div className="modal-bg" onClick={onClose}>
      <div className="modal glass" onClick={e => e.stopPropagation()} style={{ maxWidth: 420 }}>
        <div className="section-h"><h3>Add bank / product</h3><button className="btn ghost sm" onClick={onClose}>✕</button></div>
        <p className="muted" style={{ fontSize: 13 }}>Type a new bank and/or product. Leave product blank to just add a bank. The closing rule decides when its cases leave the live views.</p>
        <div className="field"><label>Bank</label>
          <input className="input" value={bank} onChange={e => setBank(e.target.value)} placeholder="e.g. KOTAK" /></div>
        <div className="field"><label>Product <span className="muted" style={{ fontWeight: 400 }}>(optional)</span></label>
          <input className="input" value={product} onChange={e => setProduct(e.target.value)} placeholder="e.g. 2 BKT" /></div>
        <div className="grid2" style={{ gridTemplateColumns: '1fr 1fr', gap: 10 }}>
          <div className="field"><label>Segment</label>
            <select className="input" value={segment} onChange={e => setSegment(e.target.value)}>
              <option>Credit Card</option><option>PL/BL</option></select></div>
          <div className="field"><label>Closing rule</label>
            <select className="input" value={closing} onChange={e => setClosing(e.target.value)}>
              <option value="month_end">Month-end</option>
              <option value="cyc">Cycle-wise (CYC date)</option>
              <option value="due_date">Due-date</option></select></div>
        </div>
        {err && <div style={{ color: 'var(--bad)', fontSize: 13 }}>{err}</div>}
        <div className="toolbar"><button className="btn" onClick={onClose}>Cancel</button><div style={{ flex: 1 }} />
          <button className="btn gold" disabled={busy} onClick={save}>{busy ? 'Adding…' : 'Add'}</button></div>
      </div>
    </div>
  );
}

/* DPR bulk update — upload a bank's Daily Payment Report for one portfolio, auto-detect
   columns, preview the paid/unpaid changes, then confirm to apply them. */
function DprModal({ onClose, onDone }) {
  const [cat, setCat] = useState(null);
  const [bank, setBank] = useState(''); const [product, setProduct] = useState('');
  const [file, setFile] = useState(null);
  const [prev, setPrev] = useState(null); const [res, setRes] = useState(null);
  const [busy, setBusy] = useState(false); const [err, setErr] = useState('');
  useEffect(() => { api('/api/config').then(c => setCat(c.bank_products)).catch(() => {}); }, []);
  const products = (cat && bank && cat.products[bank]) || [];
  const form = () => { const f = new FormData(); f.append('file', file); f.append('default_bank', bank); f.append('product', product); return f; };
  const changes = prev ? (prev.counts.mark_paid + prev.counts.mark_unpaid + (prev.counts.field_updates || 0)) : 0;
  const doPreview = async () => {
    if (!file || !bank || !product) return; setErr(''); setBusy(true); setRes(null);
    try { setPrev(await api('/api/dpr/preview', { method: 'POST', form: form() })); }
    catch (e) { setErr(e.message); } finally { setBusy(false); }
  };
  const doCommit = async () => {
    setErr(''); setBusy(true);
    try { const r = await api('/api/dpr/commit', { method: 'POST', form: form() }); setRes(r);
      toast(`DPR applied — ${r.paid} paid, ${r.unpaid} reversed.`); onDone && onDone();
    } catch (e) { setErr(e.message); } finally { setBusy(false); }
  };
  const badge = (a) => ({ mark_paid: ['✓ Mark paid', 'var(--good)'], mark_unpaid: ['↩ Reverse (unpaid)', 'var(--warn)'], already_paid: ['• Already paid', 'var(--ink-dim)'], unmatched: ['⚠ Unmatched', 'var(--bad)'] }[a] || [a, '']);
  return (
    <div className="modal-bg" onClick={onClose}>
      <div className="modal glass" onClick={e => e.stopPropagation()} style={{ maxWidth: 720 }}>
        <div className="section-h"><h3>🏦 DPR bulk update</h3><button className="btn ghost sm" onClick={onClose}>✕</button></div>
        <p className="muted" style={{ fontSize: 13, marginTop: 0 }}>Upload a bank's DPR for one portfolio. We match each row by account/loan number, then update <b>every recognised column present in the file</b> — payment status &amp; amount plus contact, address, balances, bucket, PTP date, remarks and more. Blank cells never overwrite existing data. You'll see a preview before anything changes.</p>
        <div className="grid2" style={{ gridTemplateColumns: '1fr 1fr', gap: 10 }}>
          <div className="field"><label>Bank</label>
            <select className="input" value={bank} onChange={e => { setBank(e.target.value); setProduct(''); setPrev(null); }}>
              <option value="">— select —</option>{(cat ? cat.banks : []).map(b => <option key={b} value={b}>{b}</option>)}</select></div>
          <div className="field"><label>Product</label>
            <select className="input" value={product} onChange={e => { setProduct(e.target.value); setPrev(null); }} disabled={!bank}>
              <option value="">— select —</option>{products.map(pp => <option key={pp} value={pp}>{pp}</option>)}</select></div>
        </div>
        <div className="field"><label>DPR file (.xlsx)</label>
          <input className="input" type="file" accept=".xlsx,.xls" onChange={e => { setFile(e.target.files[0]); setPrev(null); setRes(null); }} /></div>
        {err && <div style={{ color: 'var(--bad)', fontSize: 13, marginBottom: 8 }}>{err}</div>}
        {!res && <div className="toolbar">
          <button className="btn" onClick={doPreview} disabled={!file || !bank || !product || busy}>{busy && !prev ? 'Reading…' : (prev ? 'Re-preview' : 'Preview')}</button>
          {prev && <button className="btn gold" onClick={doCommit} disabled={busy || changes === 0}>{busy ? 'Applying…' : `Confirm & apply (${changes} change${changes === 1 ? '' : 's'})`}</button>}
        </div>}
        {prev && !res && <div className="glass card" style={{ marginTop: 8 }}>
          <div style={{ display: 'flex', gap: 14, flexWrap: 'wrap', fontSize: 13, marginBottom: 6 }}>
            <span><b style={{ color: 'var(--good)' }}>{prev.counts.mark_paid}</b> to mark paid</span>
            <span><b style={{ color: 'var(--warn)' }}>{prev.counts.mark_unpaid}</b> to reverse</span>
            <span><b style={{ color: 'var(--ink-dim)' }}>{prev.counts.already_paid}</b> already paid</span>
            <span><b style={{ color: 'var(--bad)' }}>{prev.counts.unmatched}</b> unmatched</span>
            <span><b style={{ color: 'var(--info)' }}>{prev.counts.field_updates || 0}</b> field updates{prev.counts.rows_with_updates ? ` (${prev.counts.rows_with_updates} rows)` : ''}</span>
          </div>
          <div className="muted" style={{ fontSize: 11.5, marginBottom: 4 }}>Match/pay → key: {prev.detected.keys.join(', ') || '—'} · amount: {prev.detected.amount || '—'} · status: {prev.detected.status || '—'} · norm/stab: {prev.detected.ns || '—'}</div>
          {prev.detected.fields && Object.keys(prev.detected.fields).length > 0 &&
            <div className="muted" style={{ fontSize: 11.5, marginBottom: 6 }}>Other columns synced → {Object.entries(prev.detected.fields).map(([f, h]) => `${f} (${h})`).join(' · ')}</div>}
          <div className="tablewrap" style={{ maxHeight: 260, overflow: 'auto' }}><table>
            <thead><tr><th>Action</th><th>Key</th><th>Customer</th><th>Amount</th><th>NORM/STAB</th><th>Other updates</th></tr></thead>
            <tbody>{prev.rows.map((r, i) => { const [lbl, col] = badge(r.action); const ups = r.updates || {}; const uk = Object.keys(ups); return <tr key={i}>
              <td style={{ color: col, whiteSpace: 'nowrap' }}>{lbl}</td>
              <td className="mono">{r.key || '—'}</td><td>{r.customer || r.name || '—'}</td>
              <td className="mono">{r.amount ? INR2(r.amount) : '—'}</td><td>{r.norm_stab || '—'}</td>
              <td style={{ fontSize: 11.5 }} title={uk.map(k => `${k}: ${ups[k]}`).join('\n')}>{uk.length ? `${uk.length}: ${uk.join(', ')}` : '—'}</td></tr>; })}</tbody></table></div>
          {prev.capped && <div className="muted" style={{ fontSize: 11 }}>Showing the first 500 rows.</div>}
        </div>}
        {res && <div className="glass card" style={{ marginTop: 8, borderLeft: '3px solid var(--good)' }}>
          <b>Done.</b> <span className="muted" style={{ fontSize: 13 }}>{res.paid} marked paid · {res.unpaid} reversed · {res.already_paid} already paid · {res.field_updates || 0} field updates · {res.unmatched} unmatched (of {res.total} rows).</span>
          <div className="toolbar" style={{ marginTop: 8 }}><button className="btn" onClick={onClose}>Close</button></div></div>}
      </div>
    </div>
  );
}
/* Recent uploads — admin/head office can undo a wrong portfolio upload. Removing an upload
   soft-deletes its cases (they land in the Removed-cases bin and can be restored). */
function UploadsModal({ onClose, onDone }) {
  const [rows, setRows] = useState(null);
  const [busy, setBusy] = useState(0);
  const [confirmId, setConfirmId] = useState(null);
  const load = () => api('/api/import/batches').then(setRows).catch(() => setRows([]));
  useEffect(() => { load(); }, []);
  const del = async (b) => {
    setBusy(b.id);
    try {
      const r = await api('/api/import/batches/' + b.id + '/delete', { method: 'POST' });
      toast(`Upload undone — ${r.removed} case${r.removed === 1 ? '' : 's'} moved to Removed bin.`);
      setConfirmId(null); await load(); onDone && onDone();
    } catch (e) { toast(e.message || 'Could not undo upload'); }
    finally { setBusy(0); }
  };
  return (
    <div className="modal-bg" onClick={onClose}>
      <div className="modal glass" onClick={e => e.stopPropagation()} style={{ maxWidth: 760 }}>
        <div className="section-h"><h3>↩ Recent uploads</h3><button className="btn ghost sm" onClick={onClose}>✕</button></div>
        <p className="muted" style={{ fontSize: 13, marginTop: 0 }}>
          Uploaded a wrong file? Undo it here — every case from that upload moves to the Removed-cases bin
          (reversible: restore them from there if needed).
        </p>
        {!rows ? <Loader /> : rows.length === 0 ? <p className="muted" style={{ padding: 12 }}>No uploads yet.</p> : (
          <div className="tablewrap" style={{ maxHeight: 420, overflow: 'auto' }}><table>
            <thead><tr><th>When</th><th>Bank · Product</th><th>File</th><th>By</th><th>Live</th><th></th></tr></thead>
            <tbody>{rows.map(b => <tr key={b.id}>
              <td className="muted" style={{ whiteSpace: 'nowrap', fontSize: 12 }}>{b.created_at ? fmtDT(b.created_at) : '—'}</td>
              <td><b>{b.bank || '—'}</b> · {b.product || '—'}</td>
              <td className="muted" style={{ fontSize: 12, maxWidth: 180, overflow: 'hidden', textOverflow: 'ellipsis' }} title={b.filename}>{b.filename || '—'}</td>
              <td className="muted" style={{ fontSize: 12 }}>{b.uploaded_by}</td>
              <td className="mono">{b.live}{b.removed ? <span className="muted" style={{ fontSize: 11 }}> (+{b.removed} removed)</span> : ''}</td>
              <td style={{ textAlign: 'right' }}>
                {confirmId === b.id
                  ? <span style={{ whiteSpace: 'nowrap' }}>
                      <button className="btn sm" style={{ background: 'var(--bad)', color: '#fff', border: 'none' }}
                        disabled={busy === b.id} onClick={() => del(b)}>{busy === b.id ? 'Removing…' : `Remove ${b.live}`}</button>
                      <button className="btn ghost sm" onClick={() => setConfirmId(null)} style={{ marginLeft: 6 }}>Cancel</button>
                    </span>
                  : <button className="btn sm" disabled={!b.live} onClick={() => setConfirmId(b.id)}>🗑 Undo</button>}
              </td></tr>)}</tbody></table></div>
        )}
        <div className="toolbar" style={{ marginTop: 8 }}><div style={{ flex: 1 }} /><button className="btn" onClick={onClose}>Close</button></div>
      </div>
    </div>
  );
}
function UploadModal({ onClose, onDone }) {
  const [cat, setCat] = useState(null);
  const now = new Date();
  const [file, setFile] = useState(null); const [bank, setBank] = useState(''); const [product, setProduct] = useState('');
  const [segment, setSegment] = useState(''); const [branch, setBranch] = useState(''); const [prev, setPrev] = useState(null);
  const [res, setRes] = useState(null);
  const [year, setYear] = useState(now.getFullYear()); const [month, setMonth] = useState(now.getMonth() + 1);
  const [addOpen, setAddOpen] = useState(false);
  const [busy, setBusy] = useState(false); const [err, setErr] = useState('');
  const loadCat = () => api('/api/config').then(c => setCat(c.bank_products)).catch(() => {});
  useEffect(() => { loadCat(); }, []);
  const onCatalogAdded = async (nb, np) => {
    setAddOpen(false);
    await loadCat();
    if (nb) { setBank(nb); if (np) setProduct(np); }
  };
  const products = (cat && bank && cat.products[bank]) || [];
  const ready = file && bank && product && segment && year && month;
  const buildForm = () => {
    const f = new FormData(); f.append('file', file);
    f.append('default_bank', bank); f.append('product', product); f.append('segment', segment);
    f.append('year', String(year)); f.append('month', String(month));
    if (branch) f.append('branch', branch); return f;
  };
  const doPreview = async () => {
    if (!file) return; setErr(''); setBusy(true);
    try { setPrev(await api('/api/import/preview', { method: 'POST', form: buildForm() })); }
    catch (e) { setErr(e.message); } finally { setBusy(false); }
  };
  const doCommit = async () => {
    if (!ready) return; setErr(''); setBusy(true);
    try { const f = buildForm(); f.append('auto_allocate', 'true');
      const r = await api('/api/import/commit', { method: 'POST', form: f });
      setRes(r);
      const rep = r.assignment_report || { rows: [] };
      const bad = (rep.unresolved_caller || 0) + (rep.unresolved_fos || 0);
      toast(`Imported ${r.imported} ${bank} ${product} cases, updated ${r.updated}. ${r.assigned_fos_total}/${r.total_cases} assigned to field agents.`
        + (bad ? ` ⚠ ${bad} row(s) couldn't be matched — see below.` : ''), bad ? 'err' : 'ok');
      // Refresh the underlying data now; keep the modal open only when there's a report to read.
      onDone(!(rep.rows && rep.rows.length));
    } catch (e) { setErr(e.message); } finally { setBusy(false); }
  };
  const downloadUnresolved = () => {
    const rows = (res && res.assignment_report && res.assignment_report.rows) || [];
    const head = ['Account', 'Customer', 'Field', 'Value in sheet', 'Reason', 'Detail'];
    const esc = (v) => '"' + String(v == null ? '' : v).replace(/"/g, '""') + '"';
    const csv = [head.join(',')].concat(rows.map(r =>
      [r.account_no, r.customer, r.field, r.value_in_sheet, r.reason, r.detail].map(esc).join(','))).join('\n');
    const a = document.createElement('a');
    a.href = URL.createObjectURL(new Blob([csv], { type: 'text/csv' }));
    a.download = `unassigned_${bank}_${product}.csv`; a.click();
  };
  return (
    <div className="modal-bg" onClick={onClose}>
      <div className="modal glass" onClick={e => e.stopPropagation()}>
        <div className="section-h"><h3>Upload accounts — one product per file</h3>
          <div style={{ display: 'flex', gap: 8 }}>
            <button className="btn sm" onClick={() => setAddOpen(true)} title="Onboard a new bank or product">➕ New bank/product</button>
            <button className="btn ghost sm" onClick={onClose}>✕</button></div></div>
        <p className="muted" style={{ fontSize: 13 }}>Choose the bank, product, segment and the <b>month/year</b> this file belongs to; every row is tagged to that period, then auto-allocated by pincode &amp; nearest FO. Cases close automatically per the product's rule (cycle date / month-end / due date) and then move to the admin Monthly Archive.</p>
        <div className="grid2" style={{ gridTemplateColumns: '1fr 1fr' }}>
          <div className="field"><label>Data month</label>
            <select className="input" value={month} onChange={e => setMonth(Number(e.target.value))}>
              {MONTHS.map((mn, i) => <option key={mn} value={i + 1}>{mn}</option>)}</select></div>
          <div className="field"><label>Year</label>
            <select className="input" value={year} onChange={e => setYear(Number(e.target.value))}>
              {[now.getFullYear() + 1, now.getFullYear(), now.getFullYear() - 1, now.getFullYear() - 2].map(y => <option key={y} value={y}>{y}</option>)}</select></div>
          <div className="field"><label>Bank</label>
            <select className="input" value={bank} onChange={e => { setBank(e.target.value); setProduct(''); }}>
              <option value="">— select bank —</option>
              {(cat ? cat.banks : []).map(b => <option key={b} value={b}>{b}</option>)}</select></div>
          <div className="field"><label>Product</label>
            <select className="input" value={product} onChange={e => setProduct(e.target.value)} disabled={!bank}>
              <option value="">— select product —</option>
              {products.map(p => <option key={p} value={p}>{p}</option>)}</select></div>
          <div className="field"><label>Segment</label>
            <select className="input" value={segment} onChange={e => setSegment(e.target.value)}>
              <option value="">— select —</option>
              {(cat ? cat.segments : ['Credit Card', 'PL/BL']).map(s => <option key={s} value={s}>{s}</option>)}</select></div>
          <div className="field"><label>Branch <span className="muted" style={{ fontWeight: 400 }}>(makes a branch-specific portfolio)</span></label>
            <input className="input" list="ssd-branch-list" value={branch} onChange={e => setBranch(e.target.value)}
              placeholder="Select or type a branch (e.g. Visakhapatnam)" />
            <datalist id="ssd-branch-list">
              {((window.__ssdCfg || {}).branches || ['Visakhapatnam', 'Vijayawada', 'Tirupati', 'Kadapa', 'Hyderabad', 'Telangana']).map(b => <option key={b} value={b} />)}
            </datalist></div>
        </div>
        <div className="field"><label>Excel file (.xlsx)</label>
          <input className="input" type="file" accept=".xlsx,.xls"
            onChange={e => { setFile(e.target.files[0]); setPrev(null); }} /></div>
        {err && <div style={{ color: 'var(--bad)', fontSize: 13, marginBottom: 8 }}>{err}</div>}
        <div className="toolbar">
          <button className="btn" onClick={doPreview} disabled={!file || busy}>Preview</button>
          <button className="btn gold" onClick={doCommit} disabled={!ready || busy}>{busy ? 'Working…' : 'Import & Allocate'}</button>
        </div>
        {prev && <div className="glass card" style={{ marginTop: 6 }}>
          <b>{prev.total_rows}</b> rows found in sheet <b>{prev.sheet}</b>. Preview:
          <div className="tablewrap" style={{ marginTop: 8 }}><table><thead><tr>
            <th>Name</th><th>Bank</th><th>Account</th><th>Target</th><th>Pincode</th></tr></thead>
            <tbody>{prev.sample.map((s, i) => <tr key={i}>
              <td>{s.customer_name}</td><td>{s.bank}</td><td className="mono">{s.account_no}</td>
              <td className="mono">{s.funding_amount}</td><td>{s.pincode || '—'}</td></tr>)}</tbody></table></div>
        </div>}
        {res && res.assignment_report && (res.assignment_report.rows || []).length > 0 && (() => {
          const rep = res.assignment_report;
          return <div className="glass card" style={{ marginTop: 8, borderLeft: '3px solid var(--bad)' }}>
            <div className="section-h" style={{ marginBottom: 4 }}>
              <b>⚠ {rep.unresolved_caller + rep.unresolved_fos} row(s) not assigned</b>
              <button className="btn ghost sm" onClick={downloadUnresolved}>⬇ CSV</button>
            </div>
            <p className="muted" style={{ fontSize: 12, marginTop: 0 }}>
              These rows imported fine and MIS counts them — only the caller/FO link is missing.
              Fix the name/ID in the sheet (or create the person) and re-upload, or assign them by hand.
              {rep.blank_caller || rep.blank_fos ? ` (${rep.blank_caller} row(s) had no caller, ${rep.blank_fos} had no FO — left blank.)` : ''}
            </p>
            <div className="tablewrap" style={{ maxHeight: 220, overflow: 'auto' }}>
              <table><thead><tr>
                <th>Account</th><th>Customer</th><th>Field</th><th>In sheet</th><th>Why</th></tr></thead>
                <tbody>{rep.rows.map((r, i) => <tr key={i}>
                  <td className="mono">{r.account_no || '—'}</td><td>{r.customer || '—'}</td>
                  <td>{r.field === 'fos' ? 'Field officer' : 'Caller'}</td>
                  <td>{r.value_in_sheet || '—'}</td><td className="muted" style={{ fontSize: 12 }}>{r.detail}</td>
                </tr>)}</tbody></table></div>
            {rep.capped && <p className="muted" style={{ fontSize: 11 }}>Showing the first 300 — download the CSV for the full list.</p>}
            <div className="toolbar" style={{ marginTop: 8 }}>
              <button className="btn" onClick={onClose}>Done</button></div>
          </div>;
        })()}
        {addOpen && <AddProductModal presetBank={bank} onClose={() => setAddOpen(false)} onAdded={onCatalogAdded} />}
      </div>
    </div>
  );
}

/* Bulk de-allocate / re-allocate selected cases to a different FOS, caller or team lead. */
function ReassignModal({ ids, onClose, onDone }) {
  const [users, setUsers] = useState(null);
  const [fos, setFos] = useState('keep');       // 'keep' | 'null' | id
  const [caller, setCaller] = useState('keep');
  const [tl, setTl] = useState('keep');         // 'keep' | '' (clear) | name
  const [busy, setBusy] = useState(false);
  useEffect(() => { api('/api/users').then(setUsers).catch(() => setUsers([])); }, []);
  const foses = (users || []).filter(u => u.role === 'fos' && u.is_active !== false);
  const callers = (users || []).filter(u => u.role === 'telecaller' && u.is_active !== false);
  const leads = [...new Set((users || []).filter(u => u.role === 'teamlead').map(u => u.name))];
  const val = (s) => s === 'keep' ? 'keep' : (s === 'null' ? null : Number(s));
  const save = async () => {
    setBusy(true);
    try {
      const body = { case_ids: ids, assigned_fos_id: val(fos), assigned_caller_id: val(caller),
                     team_lead: tl };
      const r = await api('/api/cases/bulk-reassign', { method: 'POST', body });
      toast(`Updated ${r.updated} of ${r.requested} case${r.requested === 1 ? '' : 's'}.`);
      onDone();
    } catch (e) { toast(e.message, 'err'); } finally { setBusy(false); }
  };
  return (
    <div className="modal-bg" onClick={onClose}>
      <div className="modal glass" onClick={e => e.stopPropagation()} style={{ maxWidth: 460 }}>
        <div className="section-h"><h3>Re-allocate {ids.length} case{ids.length === 1 ? '' : 's'}</h3>
          <button className="btn ghost sm" onClick={onClose}>✕</button></div>
        <p className="muted" style={{ fontSize: 13 }}>Leave a field on “Keep as-is” to not touch it. Pick “De-allocate” to unassign.</p>
        <div className="field"><label>Field officer (FOS)</label>
          <select className="input" value={fos} onChange={e => setFos(e.target.value)}>
            <option value="keep">Keep as-is</option><option value="null">— De-allocate —</option>
            {foses.map(u => <option key={u.id} value={u.id}>{u.name}{u.branch ? ` · ${u.branch}` : ''}</option>)}
          </select></div>
        <div className="field"><label>Telecaller</label>
          <select className="input" value={caller} onChange={e => setCaller(e.target.value)}>
            <option value="keep">Keep as-is</option><option value="null">— De-allocate —</option>
            {callers.map(u => <option key={u.id} value={u.id}>{u.name}{u.branch ? ` · ${u.branch}` : ''}</option>)}
          </select></div>
        <div className="field"><label>Team lead</label>
          <select className="input" value={tl} onChange={e => setTl(e.target.value)}>
            <option value="keep">Keep as-is</option><option value="">— Clear —</option>
            {leads.map(n => <option key={n} value={n}>{n}</option>)}
          </select></div>
        <div className="toolbar"><button className="btn" onClick={onClose}>Cancel</button><div style={{ flex: 1 }} />
          <button className="btn gold" disabled={busy || !ids.length} onClick={save}>{busy ? 'Saving…' : 'Apply'}</button></div>
      </div>
    </div>
  );
}

function CasesView({ user }) {
  const canUpload = user.role === 'admin' || user.role === 'backend' || user.role === 'headoffice';
  const canDpr = ['admin', 'headoffice', 'backend', 'manager', 'teamlead'].includes(user.role);
  const [dprOpen, setDprOpen] = useState(false);
  const canReassign = ['admin', 'manager', 'teamlead', 'headoffice'].includes(user.role);
  const [reassignOpen, setReassignOpen] = useState(false);
  const isAdmin = user.role === 'admin';
  const isHO = ['headoffice', 'admin'].includes(user.role);   // head office / admin may remove/restore cases
  const canUploads = ['headoffice', 'admin'].includes(user.role);  // …and undo a whole upload batch
  const [uploadsOpen, setUploadsOpen] = useState(false);
  const [picked, setPicked] = useState({});          // selected case ids (head office delete)
  const [delOpen, setDelOpen] = useState(false); const [delReason, setDelReason] = useState('');
  const [removedRows, setRemovedRows] = useState(null); const [pickedRm, setPickedRm] = useState({});
  const [mode, setMode] = useState('products');
  const [summary, setSummary] = useState(null); const [staff, setStaff] = useState({});
  const [cases, setCases] = useState(null); const [bank, setBank] = useState('');
  const [product, setProduct] = useState(''); const [segment, setSegment] = useState('');
  const [paid, setPaid] = useState(''); const [q, setQ] = useState('');
  const [openState, setOpenState] = useState(''); const [cyc, setCyc] = useState('');   // ''|'open'|'closed', cycle day
  const [monthB, setMonthB] = useState('current');   // default to THIS month so months are never mixed. '' | 'current' | 'next'
  const [area, setArea] = useState(''); const [areas, setAreas] = useState([]);   // AREA-wise filter
  const [branchF, setBranchF] = useState('');   // portfolio is per-branch
  const [flaggedOnly, setFlaggedOnly] = useState(false);   // ⚠ caution-flagged cases only
  const nextPeriod = (window.__ssdCfg || {}).next_period;
  const [upload, setUpload] = useState(false); const [busy, setBusy] = useState(false); const [drawer, setDrawer] = useState(null); const [campaign, setCampaign] = useState(false);
  const [resetOpen, setResetOpen] = useState(false); const [resetTxt, setResetTxt] = useState('');
  const loadSummary = () => api('/api/cases/product-summary').then(setSummary).catch(() => setSummary([]));
  const load = useCallback(() => {
    const p = new URLSearchParams();
    if (bank) p.set('bank', bank); if (product) p.set('product', product); if (segment) p.set('segment', segment);
    if (branchF) p.set('branch', branchF);
    if (paid) p.set('paid_status', paid); if (q) p.set('search', q);
    if (openState) p.set('closed', openState === 'closed' ? 'true' : 'false');
    if (cyc) p.set('cyc', cyc);
    if (monthB) p.set('month_bucket', monthB);
    if (area) p.set('area', area);
    api('/api/cases?' + p).then(setCases);
  }, [bank, product, segment, branchF, paid, q, openState, cyc, monthB, area]);
  useEffect(() => { loadSummary(); api('/api/users').then(us => { const m = {}; (us || []).forEach(u => { m[u.id] = u.name; }); setStaff(m); }).catch(() => {}); }, []);
  // Populate the AREA list for whichever portfolio is open.
  useEffect(() => { if (mode === 'list' && (bank || product)) { const p = new URLSearchParams(); if (bank) p.set('bank', bank); if (product) p.set('product', product); if (branchF) p.set('branch', branchF); api('/api/cases/areas?' + p).then(a => setAreas(a || [])).catch(() => setAreas([])); } }, [mode, bank, product, branchF]);
  useEffect(() => { if (mode !== 'list') return; const t = setTimeout(load, 250); return () => clearTimeout(t); }, [load, mode]);
  useDataChanged(() => { loadSummary(); if (mode === 'list') load(); });   // live product cards / list
  const openProduct = (c, mb = 'current') => { setBank(c.bank === '—' ? '' : c.bank); setProduct(c.product === '—' ? '' : c.product); setSegment(c.segment || ''); setBranchF(c.branch || ''); setMonthB(mb); setArea(''); setMode('list'); };
  const backToProducts = () => { setProduct(''); setSegment(''); setBank(''); setBranchF(''); setArea(''); setAreas([]); setMode('products'); loadSummary(); };
  const INRc = v => '₹' + Math.round(Number(v) || 0).toLocaleString('en-IN');
  const allocate = async () => { setBusy(true); try {
    const r = await api('/api/cases/allocate', { method: 'POST', body: { only_unallocated: true } });
    toast(`Allocated ${r.fos_allocated} to FOs, ${r.caller_allocated} to callers.`); load();
  } catch (e) { toast(e.message, 'err'); } finally { setBusy(false); } };
  const exportXlsx = () => download('/api/import/export', 'Recovery_Tracker.xlsx');
  const geocode = async () => { setBusy(true); try {
    let total = 0, rounds = 0;
    while (rounds < 60) { rounds++;
      const r = await api('/api/cases/geocode?limit=20', { method: 'POST' });
      total += r.geocoded;
      toast(`Geocoded ${total} so far… ${r.remaining} left`);
      if (r.remaining === 0 || r.geocoded === 0) break;
    }
    toast(`Geocoding done — ${total} cases now mapped.`); load();
  } catch (e) { toast(e.message, 'err'); } finally { setBusy(false); } };
  const doReset = async () => {
    setBusy(true);
    try {
      const r = await api('/api/cases/all?confirm=DELETE-ALL', { method: 'DELETE' });
      setResetOpen(false); setResetTxt('');
      toast(`Removed ${r.deleted_cases} cases. Now upload your fresh file.`);
      load(); setUpload(true);
    } catch (e) { toast(e.message, 'err'); } finally { setBusy(false); }
  };
  const pickedIds = Object.keys(picked).filter(k => picked[k]).map(Number);
  const togglePick = (id) => setPicked(p => ({ ...p, [id]: !p[id] }));
  const clearPicks = () => setPicked({});
  const doRemove = async () => {
    setBusy(true);
    try {
      const r = await api('/api/cases/remove', { method: 'POST', body: { ids: pickedIds, reason: delReason || null } });
      toast(`Removed ${r.removed} case${r.removed === 1 ? '' : 's'} → Removed cases.`);
      setDelOpen(false); setDelReason(''); clearPicks(); load(); loadSummary();
    } catch (e) { toast(e.message, 'err'); } finally { setBusy(false); }
  };
  const loadRemoved = () => api('/api/cases/removed').then(setRemovedRows).catch(() => setRemovedRows([]));
  const pickedRmIds = Object.keys(pickedRm).filter(k => pickedRm[k]).map(Number);
  const doRestore = async (ids) => {
    try { const r = await api('/api/cases/restore', { method: 'POST', body: { ids } });
      toast(`Restored ${r.restored} case${r.restored === 1 ? '' : 's'}.`); setPickedRm({}); loadRemoved(); loadSummary();
    } catch (e) { toast(e.message, 'err'); }
  };
  const doPurge = async (ids) => {
    if (!window.confirm(`Permanently delete ${ids.length} case(s)? This cannot be undone.`)) return;
    try { const r = await api('/api/cases/removed/purge', { method: 'POST', body: { ids } });
      toast(`Purged ${r.purged} case(s).`); setPickedRm({}); loadRemoved();
    } catch (e) { toast(e.message, 'err'); }
  };
  useEffect(() => { if (mode === 'removed') loadRemoved(); }, [mode]);

  return (
    <div>
      <div className="toolbar">
        <div className={cx('chip', mode === 'products' && 'on')} onClick={() => setMode('products')}>🧩 Products</div>
        <div className={cx('chip', mode === 'list' && 'on')} onClick={() => setMode('list')}>📋 All cases (Excel)</div>
        {isHO && <div className={cx('chip', mode === 'removed' && 'on')} onClick={() => setMode('removed')}>🗑 Removed cases</div>}
        <div style={{ flex: 1 }} />
        {canDpr && <button className="btn" onClick={() => setDprOpen(true)} title="Bulk mark paid/unpaid from a bank DPR file">🏦 DPR update</button>}
        {canUploads && <button className="btn" onClick={() => setUploadsOpen(true)} title="Undo a wrong portfolio upload">↩ Undo upload</button>}
        {canUpload && <button className="btn gold" onClick={() => setUpload(true)}>⬆ Upload</button>}
        {isAdmin && <>
          <button className="btn" onClick={allocate} disabled={busy}>⚡ Auto-allocate</button>
          <button className="btn" onClick={geocode} disabled={busy} title="Fill map coordinates from addresses">📍 Geocode</button>
          <button className="btn" onClick={() => setCampaign(true)} disabled={!cases || !cases.length}>💬 Campaign</button>
          <button className="btn gold" onClick={exportXlsx}>⬇ Export Excel</button>
          <button className="btn" style={{ borderColor: 'var(--bad)', color: 'var(--bad)' }} onClick={() => { setResetTxt(''); setResetOpen(true); }} disabled={busy}
            title="Delete all cases so you can upload a fresh loading file">🗑 Reset all</button>
        </>}
      </div>

      {mode === 'removed' ? (
        !removedRows ? <Loader /> : (
          <div>
            <div className="toolbar">
              <span className="muted" style={{ fontSize: 13 }}>{removedRows.length} removed case{removedRows.length === 1 ? '' : 's'}. Restore to return them to active work, or purge to delete permanently.</span>
              <div style={{ flex: 1 }} />
              {pickedRmIds.length > 0 && <>
                <button className="btn" onClick={() => doRestore(pickedRmIds)}>↩ Restore {pickedRmIds.length}</button>
                <button className="btn" style={{ borderColor: 'var(--bad)', color: 'var(--bad)' }} onClick={() => doPurge(pickedRmIds)}>🗑 Purge {pickedRmIds.length}</button>
              </>}
            </div>
            {removedRows.length === 0 ? <div className="glass card muted" style={{ padding: 24, textAlign: 'center' }}>No removed cases.</div> :
              <div className="glass card" style={{ padding: 6 }}>
                <div className="tablewrap"><table>
                  <thead><tr>
                    <th style={{ width: 30 }}><input type="checkbox"
                      checked={removedRows.length > 0 && pickedRmIds.length === removedRows.length}
                      onChange={e => setPickedRm(e.target.checked ? Object.fromEntries(removedRows.map(c => [c.id, true])) : {})} /></th>
                    <th>Customer</th><th>Bank</th><th>Product</th><th>Account / Card</th><th>Pending</th><th>Removed on</th><th></th></tr></thead>
                  <tbody>{removedRows.map(c => <tr key={c.id}>
                    <td><input type="checkbox" checked={!!pickedRm[c.id]} onChange={() => setPickedRm(p => ({ ...p, [c.id]: !p[c.id] }))} /></td>
                    <td><b>{c.customer_name || '—'}</b></td><td>{c.bank}</td><td>{c.product || '—'}</td>
                    <td className="mono">{c.account_no || c.card_no || '—'}</td>
                    <td className="mono" style={{ color: 'var(--warn)' }}>{INR(c.pending_amount)}</td>
                    <td className="muted" style={{ fontSize: 12 }}>{c.removed_at ? fmtDT(c.removed_at) : '—'}</td>
                    <td style={{ whiteSpace: 'nowrap' }}>
                      <button className="btn sm" onClick={() => doRestore([c.id])}>Restore</button>{' '}
                      <button className="btn sm" style={{ color: 'var(--bad)' }} onClick={() => doPurge([c.id])}>Purge</button></td></tr>)}
                  </tbody></table></div>
              </div>}
          </div>
        )
      ) : mode === 'products' ? (
        !summary ? <Loader /> : summary.length === 0 ? <div className="glass card muted" style={{ padding: 24, textAlign: 'center' }}>No cases uploaded yet.{canUpload && ' Use ⬆ Upload to add a product file.'}</div> :
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill,minmax(230px,1fr))', gap: 14 }}>
            {summary.map((c, i) => (
              <div key={i} className="glass card" style={{ padding: 16, cursor: 'pointer' }} onClick={() => openProduct(c, 'current')}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <b style={{ fontSize: 15 }}>{c.bank} · {c.product}{c.branch ? ' · ' + c.branch : ''}</b><span className="badge allocated">{c.count}</span></div>
                {(c.segment || c.branch) && <div className="muted" style={{ fontSize: 12, marginTop: 2 }}>{[c.segment, c.branch && ('📍 ' + c.branch)].filter(Boolean).join(' · ')}</div>}
                {/* Month-wise split so this-month and next-month data are never mixed. */}
                <div style={{ display: 'flex', gap: 8, marginTop: 10 }}>
                  <div onClick={e => { e.stopPropagation(); openProduct(c, 'current'); }}
                    style={{ flex: 1, textAlign: 'center', padding: '7px 4px', borderRadius: 10, background: 'rgba(59,130,246,.10)' }}>
                    <div className="muted" style={{ fontSize: 10.5 }}>📅 This month</div>
                    <b style={{ fontSize: 17, color: 'var(--info)' }}>{c.count_current ?? 0}</b></div>
                  <div onClick={e => { e.stopPropagation(); openProduct(c, 'next'); }}
                    style={{ flex: 1, textAlign: 'center', padding: '7px 4px', borderRadius: 10, background: 'rgba(120,120,120,.08)' }}>
                    <div className="muted" style={{ fontSize: 10.5 }}>🔜 Next month</div>
                    <b style={{ fontSize: 17 }}>{c.count_next ?? 0}</b></div>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 12 }}>
                  <div><div className="muted" style={{ fontSize: 11 }}>Recovered</div><b style={{ color: 'var(--good)' }}>{INRc(c.received)}</b></div>
                  <div style={{ textAlign: 'right' }}><div className="muted" style={{ fontSize: 11 }}>Pending</div><b style={{ color: 'var(--warn)' }}>{INRc(c.pending)}</b></div></div>
              </div>))}
          </div>
      ) : (<>
        <div className="toolbar">
          {product && <button className="btn ghost" onClick={backToProducts}>← Products</button>}
          {product && <span className="badge allocated">{bank} · {product}{segment ? ' · ' + segment : ''}{branchF ? ' · 📍 ' + branchF : ''}</span>}
          <input className="input" style={{ maxWidth: 240 }} placeholder="Search name / account / phone / pincode"
            value={q} onChange={e => setQ(e.target.value)} />
          {['', 'PAID', 'UNPAID', 'PARTIAL'].map(s =>
            <div key={s} className={cx('chip', paid === s && 'on')} onClick={() => setPaid(s)}>{s || 'All'}</div>)}
          <span style={{ width: 1, height: 20, background: 'var(--line)' }} />
          {[['', 'All months'], ['current', '📅 This month'], ['next', '🔜 Next month']].map(([v, lbl]) =>
            <div key={v} className={cx('chip', monthB === v && 'on')} onClick={() => setMonthB(v)}>{lbl}</div>)}
          {areas.length > 0 && <select className="input" style={{ maxWidth: 150 }} value={area} onChange={e => setArea(e.target.value)} title="Filter by area">
            <option value="">📍 All areas</option>{areas.map(a => <option key={a} value={a}>{a}</option>)}</select>}
          {(cases || []).some(c => c.flagged) && <div className={cx('chip', flaggedOnly && 'on')} onClick={() => setFlaggedOnly(v => !v)}
            style={flaggedOnly ? { background: 'rgba(220,38,38,.12)', color: 'var(--bad)' } : { color: 'var(--bad)' }}
            title="Cases flagged for review (e.g. old RTP)">⚠️ Flagged ({(cases || []).filter(c => c.flagged).length})</div>}
          <span style={{ width: 1, height: 20, background: 'var(--line)' }} />
          {[['', 'All'], ['open', '🟢 Open'], ['closed', '🔒 Closed']].map(([v, lbl]) =>
            <div key={v} className={cx('chip', openState === v && 'on')} onClick={() => setOpenState(v)}>{lbl}</div>)}
          {openState === 'closed' && <input className="input" style={{ maxWidth: 96 }} type="number" min="1" max="31"
            placeholder="Cycle day" value={cyc} onChange={e => setCyc(e.target.value)} />}
          {(isHO || canReassign) && <><div style={{ flex: 1 }} />
            {pickedIds.length > 0 && canReassign && <button className="btn gold"
              onClick={() => setReassignOpen(true)}>🔀 Re-allocate {pickedIds.length}</button>}
            {pickedIds.length > 0 && isHO && <button className="btn" style={{ background: 'var(--bad)', color: '#fff', border: 'none' }}
              onClick={() => setDelOpen(true)}>🗑 Delete {pickedIds.length} selected</button>}</>}
        </div>
        {!cases ? <Loader /> : (
          <div className="glass card" style={{ padding: 6 }}>
            <div className="tablewrap"><table>
              <thead><tr>{(isHO || canReassign) && <th style={{ width: 28 }}><input type="checkbox"
                  checked={cases.length > 0 && pickedIds.length === cases.length}
                  onChange={e => setPicked(e.target.checked ? Object.fromEntries(cases.map(c => [c.id, true])) : {})} /></th>}
                <th>Customer</th><th>Bank</th><th>Product</th><th>Caller</th><th>FOS</th><th>Account</th><th>Target</th><th>Received</th>
                <th>Pending</th><th>Status</th><th>Paid</th><th>Pincode</th><th>Dispo</th></tr></thead>
              <tbody>{(flaggedOnly ? cases.filter(c => c.flagged) : cases).map(c => <tr key={c.id} style={{ cursor: 'pointer', ...(c.flagged ? { boxShadow: 'inset 3px 0 0 var(--bad)' } : {}) }} onClick={() => setDrawer(c)}>
                {(isHO || canReassign) && <td onClick={e => e.stopPropagation()}><input type="checkbox" checked={!!picked[c.id]} onChange={() => togglePick(c.id)} /></td>}
                <td><b>{c.customer_name || '—'}</b>{c.flagged && <span title={c.flag_reason || 'Needs review'} style={{ marginLeft: 6, color: 'var(--bad)', cursor: 'help' }}>⚠️</span>}{c.closed && <span className="badge" title={`Closed ${c.close_date || ''} · locked`} style={{ background: '#e5e7eb', color: '#374151', marginLeft: 6, fontSize: 10 }}>🔒 closed</span>}{nextPeriod && c.period === nextPeriod && <span className="badge" title="Next month's data" style={{ background: '#dbeafe', color: '#1e40af', marginLeft: 6, fontSize: 10 }}>🔜 next</span>}<div className="muted" style={{ fontSize: 12 }}>{c.phone}</div></td>
                <td>{c.bank}</td><td>{c.product || '—'}</td>
                <td className="muted">{staff[c.assigned_caller_id] || '—'}</td>
                <td className="muted">{staff[c.assigned_fos_id] || '—'}</td>
                <td className="mono">{c.account_no}</td>
                <td className="mono">{INR(c.funding_amount)}</td>
                <td className="mono" style={{ color: 'var(--good)' }}>{INR(c.received_amount)}</td>
                <td className="mono" style={{ color: 'var(--warn)' }}>{INR(c.pending_amount)}</td>
                <td><StatusBadge s={c.status} /></td><td><PaidBadge s={c.paid_status} /></td>
                <td>{c.pincode || '—'}</td><td className="muted">{c.disposition || '—'}</td></tr>)}
              </tbody></table></div>
            {cases.length === 0 && <p className="muted" style={{ padding: 16 }}>No cases here.</p>}
          </div>
        )}
      </>)}
      {upload && <UploadModal onClose={() => setUpload(false)} onDone={(shouldClose = true) => { load(); if (shouldClose) setUpload(false); }} />}
      {dprOpen && <DprModal onClose={() => setDprOpen(false)} onDone={() => { load(); loadSummary(); }} />}
      {uploadsOpen && <UploadsModal onClose={() => setUploadsOpen(false)} onDone={() => { load(); loadSummary(); }} />}
      {campaign && <CampaignModal cases={cases || []} onClose={() => setCampaign(false)} />}
      {delOpen && <div className="modal-bg" onClick={() => setDelOpen(false)}>
        <div className="modal glass" onClick={e => e.stopPropagation()} style={{ maxWidth: 440 }}>
          <div className="section-h"><h3>Remove {pickedIds.length} case{pickedIds.length === 1 ? '' : 's'}?</h3><button className="btn ghost sm" onClick={() => setDelOpen(false)}>✕</button></div>
          <p style={{ fontSize: 14, lineHeight: 1.6 }}>The selected case{pickedIds.length === 1 ? '' : 's'} will move to <b>Removed cases</b> and drop out of every list, MIS, dashboard and performance calc. You can restore {pickedIds.length === 1 ? 'it' : 'them'} anytime.</p>
          <div className="field"><label>Reason (optional)</label><input className="input" value={delReason} onChange={e => setDelReason(e.target.value)} placeholder="e.g. duplicate / wrong upload" /></div>
          <div className="toolbar"><button className="btn" onClick={() => setDelOpen(false)}>Cancel</button><div style={{ flex: 1 }} />
            <button className="btn" style={{ background: 'var(--bad)', color: '#fff', border: 'none' }} disabled={busy} onClick={doRemove}>{busy ? 'Removing…' : '🗑 Remove selected'}</button></div>
        </div></div>}
      {resetOpen && <div className="modal-bg" onClick={() => setResetOpen(false)}>
        <div className="modal glass" onClick={e => e.stopPropagation()}>
          <div className="section-h"><h3>Reset all cases</h3><button className="btn ghost sm" onClick={() => setResetOpen(false)}>✕</button></div>
          <p style={{ fontSize: 14, lineHeight: 1.6 }}>This permanently deletes <b>all cases, visits and call logs</b> so you can upload a fresh loading file. Staff, leave, devices and settings are kept. <b style={{ color: 'var(--bad)' }}>This cannot be undone.</b></p>
          <div className="field"><label>Type DELETE to confirm</label>
            <input className="input" value={resetTxt} onChange={e => setResetTxt(e.target.value)} placeholder="DELETE" autoFocus /></div>
          <div className="toolbar">
            <button className="btn" onClick={() => setResetOpen(false)}>Cancel</button>
            <div style={{ flex: 1 }} />
            <button className="btn" style={{ background: 'var(--bad)', color: '#fff', border: 'none' }}
              disabled={busy || resetTxt.trim().toUpperCase() !== 'DELETE'} onClick={doReset}>{busy ? 'Deleting…' : 'Delete all cases'}</button>
          </div>
        </div>
      </div>}
      {reassignOpen && <ReassignModal ids={pickedIds} onClose={() => setReassignOpen(false)}
        onDone={() => { setReassignOpen(false); clearPicks(); load(); loadSummary(); }} />}
      {drawer && <CaseDrawer c={drawer} onClose={() => setDrawer(null)} onChanged={load} />}
    </div>
  );
}

/* ============================== Live Map (admin) ============================== */
function LiveMap({ config }) {
  const mapEl = useRef(null); const map = useRef(null); const markers = useRef({});
  const liveTrails = useRef({}); const lastPos = useRef({}); const didFit = useRef(false);
  const routeLine = useRef(null); const routeMarks = useRef([]); const routeActive = useRef(false); const routeObj = useRef(null);
  const [status, setStatus] = useState('loading'); const [officers, setOfficers] = useState([]);
  const [histOfficer, setHistOfficer] = useState(null); const [dates, setDates] = useState(null);
  const [selDate, setSelDate] = useState(''); const [routeInfo, setRouteInfo] = useState(null);
  const [, setTick] = useState(0);   // local 1s clock so live/offline + "seen ago" update on their own
  const [branch, setBranch] = useState(''); const branchRef = useRef('');
  const visitMarks = useRef([]);
  const [dayVisits, setDayVisits] = useState(null); const [selVisit, setSelVisit] = useState(null);
  const [showReport, setShowReport] = useState(false); const [drawerCase, setDrawerCase] = useState(null);
  const [rosterOpen, setRosterOpen] = useState(false); const [roster, setRoster] = useState(null); const [rosterDate, setRosterDate] = useState('');
  const [rosterQ, setRosterQ] = useState('');
  const _rmatch = o => { const q = rosterQ.trim().toLowerCase(); if (!q) return true;
    return [o.name, o.emp_code, o.branch, o.location, o.phone].some(v => (v || '').toString().toLowerCase().includes(q)); };
  const loadRoster = useCallback((d) => {
    setRoster(null);
    api('/api/tracking/roster' + (d ? '?date=' + d : '')).then(setRoster).catch(() => setRoster({ active: [], inactive: [], active_count: 0, inactive_count: 0, total: 0, error: true }));
  }, []);
  const openRoster = () => { setRosterDate(''); setRosterOpen(true); loadRoster(''); };
  const fmtT = (iso) => fmtHM(iso);

  const refresh = useCallback(async () => {
    try {
      const list = await api('/api/tracking/live?minutes=1440');
      list.sort((a, b) => (isOnline(b.last_seen) - isOnline(a.last_seen)) || String(a.name || '').localeCompare(b.name || ''));
      setOfficers(list);
      if (map.current && window.google && window.L) {
        const g = window.google; const L = window.L; const rawMap = map.current._map;
        const bounds = new g.maps.LatLngBounds();
        const shown = list.filter(o => !branchRef.current || o.branch === branchRef.current);
        const seen = {};
        shown.forEach(o => {
          seen[o.officer_id] = true;
          const pos = { lat: o.latitude, lng: o.longitude };
          const on = isOnline(o.last_seen);
          const prev = lastPos.current[o.officer_id];
          const heading = (prev && (prev.lat !== pos.lat || prev.lng !== pos.lng)) ? bearingDeg(prev, pos) : (prev ? prev.hd : 0);
          const title = o.name + (on ? ' · live' : ' · offline ' + agoLabel(o.last_seen));
          let gm = markers.current[o.officer_id];
          if (!gm) {
            // first sighting — drop the pin where they are
            gm = markers.current[o.officer_id] = new g.maps.Marker({ position: pos, map: map.current, title });
            gm._m.setIcon(fosDivIcon(initials(o.name), heading));
            gm._m.setLatLng([pos.lat, pos.lng]);
          } else {
            gm._m.options.title = title; try { gm._m.setIcon(fosDivIcon(initials(o.name), heading)); } catch (e) {}
            if (on) animateMarker(gm._m, pos.lat, pos.lng, 900);   // glide to the new fix, Swiggy-style
            else gm._m.setLatLng([pos.lat, pos.lng]);
          }
          gm._m.setZIndexOffset(on ? 500 : 100);
          // extend a live trail only while online and actually moving
          if (on && prev && (prev.lat !== pos.lat || prev.lng !== pos.lng)) {
            let tr = liveTrails.current[o.officer_id];
            if (!tr) { tr = liveTrails.current[o.officer_id] = L.polyline([[prev.lat, prev.lng]], { color: '#2563EB', weight: 3, opacity: .55, dashArray: '1 6', lineCap: 'round' }).addTo(rawMap); }
            tr.addLatLng([pos.lat, pos.lng]);
          }
          lastPos.current[o.officer_id] = { lat: pos.lat, lng: pos.lng, hd: heading };
          bounds.extend(pos);
        });
        // drop markers/trails for officers no longer in the feed
        Object.keys(markers.current).forEach(id => {
          if (!seen[id]) {
            try { markers.current[id].setMap(null); } catch (e) {}
            delete markers.current[id];
            if (liveTrails.current[id]) { try { liveTrails.current[id].remove(); } catch (e) {} delete liveTrails.current[id]; }
          }
        });
        if (shown.length && !routeActive.current && !didFit.current) { map.current.fitBounds(bounds, 80); didFit.current = true; }
      }
    } catch (e) { /* ignore transient */ }
  }, []);

  useEffect(() => {
    let timer;
    loadMaps(config && config.google_maps_api_key).then((g) => {
      map.current = new g.maps.Map(mapEl.current, {
        center: { lat: 17.72, lng: 83.30 }, zoom: 11, disableDefaultUI: false, styles: DARK_MAP_STYLE,
      });
      setStatus('ready'); refresh();
      timer = setInterval(refresh, 3000);   // real-time (officers stream positions continuously)
    }).catch(() => setStatus('nokey'));
    return () => timer && clearInterval(timer);
  }, []);

  // re-render every second so the ● Live/Offline dots, the "X live · Y offline" count and the
  // "seen … ago" text stay accurate on their own, without waiting for the next fetch or a manual refresh
  useEffect(() => { const t = setInterval(() => setTick(x => (x + 1) % 100000), 1000); return () => clearInterval(t); }, []);
  useEffect(() => { branchRef.current = branch; didFit.current = false; refresh(); }, [branch]);

  const navigateTo = (o) => window.open(`https://www.google.com/maps/dir/?api=1&destination=${o.latitude},${o.longitude}`, '_blank');

  const clearRoute = () => {
    routeActive.current = false;
    clearRouteLayers(routeObj.current); routeObj.current = null;
    if (routeLine.current) { routeLine.current.setMap(null); routeLine.current = null; }
    routeMarks.current.forEach(m => m.setMap(null)); routeMarks.current = [];
    visitMarks.current.forEach(m => { try { m.setMap(null); } catch (e) {} }); visitMarks.current = []; setDayVisits(null);
  };

  const openHistory = async (o) => {
    setHistOfficer(o); setDates(null); setSelDate(''); setRouteInfo(null); clearRoute();
    try { const ds = await api(`/api/tracking/officer/${o.officer_id}/history-dates`); setDates(ds);
      if (ds.length) setSelDate(ds[0].date); } catch (e) { toast(e.message, 'err'); }
  };

  const showRoute = async () => {
    if (!histOfficer || !selDate || !window.google) return;
    clearRoute();
    try {
      const pts = await api(`/api/tracking/officer/${histOfficer.officer_id}/route?date=${selDate}`);
      if (!pts.length) { toast('No route recorded that day', 'err'); return; }
      routeObj.current = drawRouteLeaflet(map.current, pts);
      routeActive.current = true;
      setRouteInfo((dates || []).find(d => d.date === selDate) || { points: pts.length });
      // Overlay the day's field visits as numbered tags on the route.
      try {
        const dv = await api(`/api/visits/officer/${histOfficer.officer_id}/day?date=${selDate}`);
        setDayVisits(dv);
        const g = window.google;
        (dv.visits || []).forEach((v, idx) => {
          if (v.lat == null || v.lng == null) return;
          const mk = new g.maps.Marker({
            position: { lat: v.lat, lng: v.lng }, map: map.current,
            title: `#${idx + 1} · ${v.time} · ${v.customer || ''}${v.paid ? ' · ₹' + v.amount : ''}`,
            label: { text: String(idx + 1), color: '#fff', fontWeight: '700' },
            icon: { path: g.maps.SymbolPath.CIRCLE, scale: 12, fillColor: v.paid ? '#16A34A' : (v.off_location ? '#DC2626' : '#D97706'), fillOpacity: 1, strokeColor: '#fff', strokeWeight: 2 },
          });
          try { mk.addListener('click', () => setSelVisit(v)); } catch (e) {}
          visitMarks.current.push(mk);
        });
      } catch (e) {}
    } catch (e) { toast(e.message, 'err'); }
  };
  const dlDayExcel = () => {
    if (!dayVisits || !window.XLSX) return;
    const cols = ['#', 'Time', 'Customer', 'Account', 'Bank', 'Product', 'Disposition', 'Paid', 'Amount', 'N/S', 'Off-loc', 'Note'];
    const aoa = [cols].concat((dayVisits.visits || []).map((v, i) => [i + 1, v.time, v.customer, v.account, v.bank, v.product, v.disposition, v.paid ? 'Yes' : '', v.amount, v.norm_stab, v.off_location ? 'Yes' : '', v.note]));
    const ws = XLSX.utils.aoa_to_sheet(aoa); const wb = XLSX.utils.book_new();
    XLSX.utils.book_append_sheet(wb, ws, 'Visits');
    XLSX.writeFile(wb, `Visits_${histOfficer.name}_${selDate}.xlsx`.replace(/[^\w.-]/g, '_'));
  };

  const shown = officers.filter(o => !branch || o.branch === branch);

  return (
    <div>
      <div className="toolbar">
        <span className="muted">Live field-officer positions · auto-refresh every 3s</span>
        <select className="input" style={{ maxWidth: 190 }} value={branch} onChange={e => setBranch(e.target.value)}>
          <option value="">All branches</option>
          {[...new Set(officers.map(o => o.branch).filter(Boolean))].map(b => <option key={b} value={b}>{b}</option>)}
        </select>
        <div style={{ flex: 1 }} />
        {routeActive.current && <button className="btn sm" onClick={() => { clearRoute(); setRouteInfo(null); refresh(); }}>✕ Clear route</button>}
        <button className="btn sm" onClick={openRoster}>🧑‍🤝‍🧑 FOS roster</button>
        <button className="btn sm" onClick={refresh}>↻ Refresh</button>
      </div>
      {status === 'nokey' && <div className="glass card" style={{ marginBottom: 12, color: 'var(--warn)' }}>
        Map couldn't load — check the device's internet connection and reload.
      </div>}
      <div className="grid2" style={{ gridTemplateColumns: '1fr 320px' }}>
        <div className="glass" style={{ padding: 6 }}><div className="map tall" ref={mapEl}></div></div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
          <div className="glass card">
            <div className="section-h"><h3>Officers{branch ? ' · ' + branch : ''}</h3>
              <span style={{ fontSize: 12 }}>
                <span style={{ color: 'var(--good)', fontWeight: 600 }}>● {shown.filter(o => isOnline(o.last_seen)).length} live</span>
                <span className="muted"> · {shown.filter(o => !isOnline(o.last_seen)).length} offline</span>
              </span></div>
            {shown.length === 0 && <p className="muted">No field officers{branch ? ' in ' + branch : ''} active today. They appear here once their app has sent a location.</p>}
            {shown.map(o => { const on = isOnline(o.last_seen); return <div key={o.officer_id} style={{ padding: '9px 0', borderBottom: '1px solid var(--stroke-soft)', opacity: on ? 1 : .62 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 8 }}>
                <div><b><span style={{ color: on ? 'var(--good)' : 'var(--ink-dim)' }}>●</span> {o.name}</b>
                  <div className="muted" style={{ fontSize: 11.5 }}>{on ? 'Live now' : 'Offline · seen ' + agoLabel(o.last_seen)}</div>
                  <div className="muted" style={{ fontSize: 11 }}>🏢 {o.branch || '—'}{o.banks && o.banks.length ? ' · 🏦 ' + o.banks.join('/') : ''}</div></div>
                <div style={{ display: 'flex', gap: 6 }}>
                  <button className="btn sm gold" onClick={() => navigateTo(o)} title="Directions to live location">🧭</button>
                  <button className="btn sm" onClick={() => openHistory(o)} title="Route & visits">🕘</button>
                </div>
              </div>
            </div>; })}
          </div>

          {histOfficer && <div className="glass card">
            <div className="section-h"><h3>Route history — {histOfficer.name}</h3>
              <button className="btn ghost sm" onClick={() => { setHistOfficer(null); clearRoute(); setRouteInfo(null); }}>✕</button></div>
            {dates === null ? <Loader /> : dates.length === 0 ? <p className="muted">No route recorded in the last 3 months.</p> : <>
              <div className="field"><label>Date (last 3 months)</label>
                <select className="input" value={selDate} onChange={e => setSelDate(e.target.value)}>
                  {dates.map(d => <option key={d.date} value={d.date}>{d.date} · {d.points} pts · {d.distance_km} km</option>)}
                </select></div>
              <button className="btn gold block" onClick={showRoute}>Show route on map</button>
              {routeInfo && <div style={{ marginTop: 12 }}>
                <div className="stat-row"><span className="k">Points logged</span><b>{routeInfo.points}</b></div>
                {routeInfo.distance_km != null && <div className="stat-row"><span className="k">Distance</span><b>{routeInfo.distance_km} km</b></div>}
                {routeInfo.first_seen && <div className="stat-row"><span className="k">Active</span><b>{routeInfo.first_seen}–{routeInfo.last_seen}</b></div>}
                <div className="muted" style={{ fontSize: 11.5, marginTop: 6 }}>🟢 S = start · 🔴 E = end of day</div>
              </div>}
              {dayVisits && <div style={{ marginTop: 12, borderTop: '1px solid var(--stroke-soft)', paddingTop: 10 }}>
                <div className="stat-row"><span className="k">Field visits</span><b>{dayVisits.count}</b></div>
                <div className="stat-row"><span className="k">Collected on visits</span><b style={{ color: 'var(--good)' }}>{INR2(dayVisits.collected)}</b></div>
                <div className="muted" style={{ fontSize: 11, marginTop: 4 }}>🟢 paid · 🟠 visit · 🔴 off-location — tap a numbered tag on the map for details</div>
                <button className="btn block" style={{ marginTop: 8 }} onClick={() => setShowReport(true)}>📋 View day report / Excel</button>
              </div>}
            </>}
          </div>}
        </div>
      </div>

      {rosterOpen && <div className="modal-bg" onClick={() => setRosterOpen(false)}>
        <div className="modal glass" onClick={e => e.stopPropagation()} style={{ maxWidth: 640 }}>
          <div className="section-h"><h3>Field officers — {roster ? (roster.is_today ? 'Today' : roster.date) : '…'}</h3>
            <button className="btn ghost sm" onClick={() => setRosterOpen(false)}>✕</button></div>
          <div className="toolbar" style={{ gap: 10, marginBottom: 10, alignItems: 'flex-end' }}>
            <div className="field" style={{ margin: 0 }}><label style={{ fontSize: 11 }}>Date</label>
              <input className="input" type="date" max={new Date().toISOString().slice(0, 10)} value={rosterDate}
                onChange={e => { setRosterDate(e.target.value); loadRoster(e.target.value); }} /></div>
            {rosterDate && <button className="btn sm" onClick={() => { setRosterDate(''); loadRoster(''); }}>Today</button>}
            <div className="field" style={{ margin: 0, minWidth: 200 }}><label style={{ fontSize: 11 }}>Search</label>
              <input className="input" value={rosterQ} onChange={e => setRosterQ(e.target.value)}
                placeholder="🔍 Name / ID / branch / phone" /></div>
            <div style={{ flex: 1 }} />
            {roster && !roster.error && <span className="muted" style={{ fontSize: 12.5 }}>
              <b style={{ color: 'var(--good)' }}>{roster.active_count} active</b> · {roster.inactive_count} inactive · {roster.total} total</span>}
          </div>
          {!roster ? <Loader /> : <div className="grid2" style={{ gridTemplateColumns: '1fr 1fr', gap: 12 }}>
            <div className="glass card" style={{ padding: 8, maxHeight: 360, overflow: 'auto' }}>
              <b style={{ color: 'var(--good)' }}>● Active ({roster.active_count})</b>
              <p className="muted" style={{ fontSize: 11, margin: '2px 0 6px' }}>Shared live location this day</p>
              {roster.active.filter(_rmatch).length === 0 ? <div className="muted" style={{ fontSize: 12 }}>{rosterQ ? 'No match.' : 'None.'}</div> :
                roster.active.filter(_rmatch).map(o => <div key={o.id} style={{ padding: '6px 0', borderBottom: '1px solid var(--stroke-soft)' }}>
                  <b>{o.name}</b> <span className="muted" style={{ fontSize: 11 }}>{o.emp_code || ''}</span>
                  <div className="muted" style={{ fontSize: 11 }}>🏢 {o.branch || o.location || '—'} · {o.pings} pts · {o.distance_km || 0} km</div>
                  <div className="muted" style={{ fontSize: 11 }}>🕘 {fmtT(o.first_seen)}–{fmtT(o.last_seen)}</div>
                </div>)}
            </div>
            <div className="glass card" style={{ padding: 8, maxHeight: 360, overflow: 'auto' }}>
              <b style={{ color: 'var(--ink-dim)' }}>● Inactive ({roster.inactive_count})</b>
              <p className="muted" style={{ fontSize: 11, margin: '2px 0 6px' }}>No tracking this day</p>
              {roster.inactive.filter(_rmatch).length === 0 ? <div className="muted" style={{ fontSize: 12 }}>{rosterQ ? 'No match.' : 'None — everyone tracked 🎉'}</div> :
                roster.inactive.filter(_rmatch).map(o => <div key={o.id} style={{ padding: '6px 0', borderBottom: '1px solid var(--stroke-soft)' }}>
                  <b>{o.name}</b> <span className="muted" style={{ fontSize: 11 }}>{o.emp_code || ''}</span>
                  <div className="muted" style={{ fontSize: 11 }}>🏢 {o.branch || o.location || '—'}{o.phone ? ' · 📞 ' + o.phone : ''}</div>
                </div>)}
            </div>
          </div>}
        </div>
      </div>}

      {selVisit && <div className="modal-bg" onClick={() => setSelVisit(null)}><div className="modal glass" onClick={e => e.stopPropagation()} style={{ maxWidth: 460 }}>
        <div className="section-h"><h3>Visit — {selVisit.customer || '—'}</h3><button className="btn ghost sm" onClick={() => setSelVisit(null)}>✕</button></div>
        <div className="stat-row"><span className="k">Time</span><b>{selVisit.time}</b></div>
        <div className="stat-row"><span className="k">Account</span><b className="mono">{selVisit.account || '—'}</b></div>
        <div className="stat-row"><span className="k">Bank / Product</span><b>{[selVisit.bank, selVisit.product].filter(Boolean).join(' · ') || '—'}</b></div>
        <div className="stat-row"><span className="k">Disposition</span><b>{selVisit.disposition || '—'}</b></div>
        {selVisit.paid && <div className="stat-row"><span className="k">Payment</span><b style={{ color: 'var(--good)' }}>{INR2(selVisit.amount)}{selVisit.norm_stab ? ' · ' + selVisit.norm_stab : ''}</b></div>}
        {selVisit.person_moved && <div className="stat-row"><span className="k">Flag</span><b style={{ color: 'var(--warn)' }}>Person moved</b></div>}
        {selVisit.off_location && <div className="stat-row"><span className="k">⚠ Location</span><b style={{ color: 'var(--bad)' }}>{Math.round(selVisit.distance_m)}m off case</b></div>}
        {selVisit.note && <div style={{ marginTop: 8 }}><div className="muted" style={{ fontSize: 12 }}>Log submitted</div><div style={{ fontSize: 13, lineHeight: 1.5 }}>{selVisit.note}</div></div>}
        {selVisit.photo && <img src={selVisit.photo} alt="visit" style={{ width: '100%', borderRadius: 10, marginTop: 10 }} />}
        <button className="btn gold block" style={{ marginTop: 10 }} onClick={async () => { try { const c = await api('/api/cases/' + selVisit.case_id); setDrawerCase(c); setSelVisit(null); } catch (e) { toast(e.message, 'err'); } }}>Open full case</button>
      </div></div>}

      {showReport && dayVisits && <div className="modal-bg" onClick={() => setShowReport(false)}><div className="modal glass" onClick={e => e.stopPropagation()} style={{ maxWidth: 860, width: '96%' }}>
        <div className="section-h"><h3>{histOfficer.name} — {selDate} field report</h3>
          <div style={{ display: 'flex', gap: 6 }}><button className="btn sm gold" onClick={dlDayExcel}>⬇ Excel</button><button className="btn ghost sm" onClick={() => setShowReport(false)}>✕</button></div></div>
        <div className="toolbar"><span>Visits <b>{dayVisits.count}</b></span><span>Collected <b style={{ color: 'var(--good)' }}>{INR2(dayVisits.collected)}</b></span></div>
        <div className="tablewrap" style={{ maxHeight: 440, overflow: 'auto' }}><table><thead><tr><th>#</th><th>Time</th><th>Customer</th><th>Bank</th><th>Dispo</th><th>Paid</th><th>N/S</th><th>Log</th></tr></thead>
          <tbody>{dayVisits.visits.map((v, i) => <tr key={i} style={{ cursor: 'pointer' }} onClick={() => setSelVisit(v)}>
            <td>{i + 1}</td><td>{v.time}</td><td><b>{v.customer || '—'}</b></td><td>{v.bank}</td><td>{v.disposition || '—'}</td>
            <td className="mono" style={{ color: 'var(--good)' }}>{v.paid ? INR2(v.amount) : '—'}</td><td>{v.norm_stab || '—'}</td>
            <td className="muted" style={{ maxWidth: 220, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{v.note || '—'}</td></tr>)}</tbody></table></div>
        {dayVisits.count === 0 && <div className="muted" style={{ padding: 16 }}>No visits logged this day.</div>}
      </div></div>}

      {drawerCase && <CaseDrawer c={drawerCase} onClose={() => setDrawerCase(null)} onChanged={() => {}} />}
    </div>
  );
}
const DARK_MAP_STYLE = [
  { elementType: 'geometry', stylers: [{ color: '#1a1710' }] },
  { elementType: 'labels.text.stroke', stylers: [{ color: '#0e0c08' }] },
  { elementType: 'labels.text.fill', stylers: [{ color: '#a99f86' }] },
  { featureType: 'road', elementType: 'geometry', stylers: [{ color: '#2a2417' }] },
  { featureType: 'water', elementType: 'geometry', stylers: [{ color: '#0f1a24' }] },
  { featureType: 'poi', stylers: [{ visibility: 'off' }] },
];

/* ============================== Staff (admin) ============================== */
function StaffModal({ editing, onClose, onDone, presetBranch, me }) {
  const isMgr = me && me.role === 'manager';
  const isTL = me && me.role === 'teamlead';
  const [f, setF] = useState(editing || { name: '', email: '', role: 'fos',
    branch: isMgr || isTL ? (me.branch || '') : (presetBranch || ''), password: '',
    banks: [], assigned_products: [], assigned_pincodes: [], home_lat: '', home_lng: '' });
  const [busy, setBusy] = useState(false); const [err, setErr] = useState('');
  const [cat, setCat] = useState(null); const [leads, setLeads] = useState([]);
  useEffect(() => { api('/api/config').then(c => setCat(c.bank_products)).catch(() => {}); }, []);
  // team leads available to assign a FOS/caller under (admin/manager only)
  useEffect(() => { if (!isTL) api('/api/users?role=teamlead').then(setLeads).catch(() => setLeads([])); }, []);
  const branchLeads = leads.filter(l => !f.branch || (l.branch || '') === f.branch);
  const upd = (k, v) => setF(s => ({ ...s, [k]: v }));
  const toggleIn = (k, v) => setF(s => { const arr = s[k] || []; return { ...s, [k]: arr.includes(v) ? arr.filter(x => x !== v) : [...arr, v] }; });
  const toggleBank = (b) => toggleIn('banks', b);
  const allBanks = cat && cat.banks ? cat.banks : ['ICICI', 'RBL', 'AXIS'];
  const prodOptions = () => {                       // products across the FOS's selected banks
    if (!cat || !cat.products) return [];
    const seen = new Set(); const out = [];
    (f.banks.length ? f.banks : allBanks).forEach(b => (cat.products[b] || []).forEach(p => { if (!seen.has(p)) { seen.add(p); out.push(p); } }));
    return out;
  };
  const save = async () => { setErr(''); setBusy(true);
    const body = { ...f,
      assigned_pincodes: typeof f.assigned_pincodes === 'string'
        ? f.assigned_pincodes.split(',').map(x => x.trim()).filter(Boolean) : f.assigned_pincodes,
      home_lat: f.home_lat === '' ? null : Number(f.home_lat),
      home_lng: f.home_lng === '' ? null : Number(f.home_lng),
      joining_date: f.joining_date || null };
    try {
      if (editing) await api('/api/users/' + editing.id, { method: 'PATCH', body });
      else await api('/api/users', { method: 'POST', body });
      toast('Saved.'); onDone();
    } catch (e) { setErr(e.message); } finally { setBusy(false); }
  };
  return (
    <div className="modal-bg" onClick={onClose}>
      <div className="modal glass" onClick={e => e.stopPropagation()}>
        <div className="section-h"><h3>{editing ? 'Edit' : 'Add'} staff
          {editing && editing.emp_code && <span className="badge allocated" style={{ marginLeft: 8, fontFamily: 'var(--mono, monospace)' }}>ID {editing.emp_code}</span>}</h3>
          <button className="btn ghost sm" onClick={onClose}>✕</button></div>
        {!editing && <p className="muted" style={{ fontSize: 12, margin: '0 0 8px' }}>A staff/caller ID (e.g. TC001) is generated automatically on save — use it in the CALLER column of upload sheets.</p>}
        <div className="grid2" style={{ gridTemplateColumns: '1fr 1fr' }}>
          <div className="field"><label>Name</label><input className="input" value={f.name} onChange={e => upd('name', e.target.value)} /></div>
          <div className="field"><label>Email</label><input className="input" value={f.email} disabled={!!editing} onChange={e => upd('email', e.target.value)} /></div>
          <div className="field"><label>Role</label><select className="input" value={f.role} onChange={e => upd('role', e.target.value)}>
            <option value="fos">Field Agent</option><option value="telecaller">Tele-calling Agent</option>
            {!isTL && <option value="teamlead">Team Lead</option>}
            {!isTL && <option value="backend">Back-office Official</option>}
            {!isTL && <option value="manager">Collections Manager</option>}
            {!isMgr && !isTL && <option value="headoffice">Head Office (all portfolios)</option>}
            {!isMgr && !isTL && <option value="admin">Administrator</option>}</select></div>
          <div className="field"><label>Branch</label><input className="input" value={f.branch || ''} disabled={isMgr || isTL} title={isMgr || isTL ? 'Locked to your branch' : ''} onChange={e => upd('branch', e.target.value)} /></div>
          {!isTL && (f.role === 'fos' || f.role === 'telecaller') && <div className="field"><label>Team lead <span className="muted" style={{ fontWeight: 400 }}>(who they report to)</span></label>
            <select className="input" value={f.team_lead_id || ''} onChange={e => upd('team_lead_id', e.target.value ? Number(e.target.value) : null)}>
              <option value="">— none —</option>
              {branchLeads.map(l => <option key={l.id} value={l.id}>{l.name}{l.emp_code ? ' · ' + l.emp_code : ''}</option>)}
            </select>
            {branchLeads.length === 0 && <div className="muted" style={{ fontSize: 11.5 }}>No team leads in this branch yet — create one first (Role → Team Lead).</div>}</div>}
          <div className="field"><label>Phone</label><input className="input" value={f.phone || ''} onChange={e => upd('phone', e.target.value)} /></div>
          <div className="field"><label>{editing ? 'New password (blank = keep)' : 'Password'}</label>
            <input className="input" type="password" value={f.password || ''} onChange={e => upd('password', e.target.value)} /></div>
        </div>
        <div className="field"><label>Banks</label><div className="toolbar" style={{ margin: 0, flexWrap: 'wrap' }}>
          {allBanks.map(b => <div key={b} className={cx('chip', f.banks.includes(b) && 'on')} onClick={() => toggleBank(b)}>{b}</div>)}
        </div></div>
        {f.role === 'fos' && <div className="field"><label>Assigned products <span className="muted" style={{ fontWeight: 400 }}>(cases of these products route here first)</span></label>
          <div className="toolbar" style={{ margin: 0, flexWrap: 'wrap' }}>
            {prodOptions().length === 0 ? <span className="muted" style={{ fontSize: 12 }}>Pick a bank to see its products.</span> :
              prodOptions().map(p => <div key={p} className={cx('chip', (f.assigned_products || []).includes(p) && 'on')} onClick={() => toggleIn('assigned_products', p)}>{p}</div>)}
          </div></div>}
        {f.role === 'fos' && <div className="grid2" style={{ gridTemplateColumns: '1fr 1fr' }}>
          <div className="field"><label>Assigned pincodes (comma-separated)</label>
            <input className="input" value={Array.isArray(f.assigned_pincodes) ? f.assigned_pincodes.join(', ') : f.assigned_pincodes}
              onChange={e => upd('assigned_pincodes', e.target.value)} placeholder="530001, 530016" /></div>
          <div className="field" style={{ display: 'flex', flexDirection: 'row', gap: 8 }}>
            <div><label>Base lat</label><input className="input" value={f.home_lat || ''} onChange={e => upd('home_lat', e.target.value)} /></div>
            <div><label>Base lng</label><input className="input" value={f.home_lng || ''} onChange={e => upd('home_lng', e.target.value)} /></div>
          </div>
        </div>}
        <div className="grid2" style={{ gridTemplateColumns: '1fr 1fr' }}>
          <div className="field"><label>Employment type</label>
            <select className="input" value={f.employment_type || ''} onChange={e => upd('employment_type', e.target.value)}>
              <option value="">—</option><option>Full-time</option><option>Part-time</option><option>Contract</option><option>Intern</option></select></div>
          <div className="field"><label>Joining date</label><input className="input" type="date" value={f.joining_date || ''} onChange={e => upd('joining_date', e.target.value)} /></div>
          <div className="field"><label>Emergency contact</label><input className="input" value={f.emergency_contact || ''} onChange={e => upd('emergency_contact', e.target.value)} placeholder="name / phone" /></div>
          <div className="field"><label>Photo URL (optional)</label><input className="input" value={f.photo_url || ''} onChange={e => upd('photo_url', e.target.value)} /></div>
        </div>
        <div className="field"><label>Address</label><textarea className="input" value={f.address || ''} onChange={e => upd('address', e.target.value)} /></div>
        {editing && <div className="field"><label>Employment status</label>
          <div className="toolbar" style={{ margin: 0 }}>
            <div className={cx('chip', f.is_active !== false && 'on')} onClick={() => upd('is_active', true)}>✓ Active</div>
            <div className={cx('chip', f.is_active === false && 'on')} onClick={() => upd('is_active', false)}>Inactive / left</div>
          </div></div>}
        {err && <div style={{ color: 'var(--bad)', fontSize: 13 }}>{err}</div>}
        <button className="btn gold block" onClick={save} disabled={busy} style={{ marginTop: 8 }}>{busy ? 'Saving…' : 'Save'}</button>
      </div>
    </div>
  );
}
function RouteHistoryModal({ officer, config, onClose }) {
  const mapEl = useRef(null); const map = useRef(null); const routeObj = useRef(null);
  const mover = useRef(null); const timer = useRef(null); const pathRef = useRef([]); const idx = useRef(0);
  const [dates, setDates] = useState(null); const [selDate, setSelDate] = useState(''); const [info, setInfo] = useState(null);
  const [nokey, setNokey] = useState(false); const [playing, setPlaying] = useState(false); const [speed, setSpeed] = useState(2); const [ready, setReady] = useState(false);
  useEffect(() => {
    api(`/api/tracking/officer/${officer.id}/history-dates`).then(ds => { setDates(ds); if (ds.length) setSelDate(ds[0].date); }).catch(() => setDates([]));
    loadMaps(config && config.google_maps_api_key).then(g => {
      map.current = new g.maps.Map(mapEl.current, { center: { lat: 17.72, lng: 83.30 }, zoom: 11, styles: DARK_MAP_STYLE });
    }).catch(() => setNokey(true));
    return () => { if (timer.current) clearInterval(timer.current); };
  }, []);
  const stopPlay = () => { if (timer.current) { clearInterval(timer.current); timer.current = null; } setPlaying(false); };
  const clear = () => {
    stopPlay();
    clearRouteLayers(routeObj.current); routeObj.current = null;
    if (mover.current) { mover.current.setMap(null); mover.current = null; }
    setReady(false);
  };
  const show = async () => {
    if (!selDate) return; clear();
    try {
      const pts = await api(`/api/tracking/officer/${officer.id}/route?date=${selDate}`);
      if (!pts.length) { toast('No route recorded that day', 'err'); return; }
      if (map.current && window.google) {
        const g = window.google;
        const r = drawRouteLeaflet(map.current, pts);
        routeObj.current = r; pathRef.current = r.path; idx.current = 0;
        if (r.path.length) {
          mover.current = new g.maps.Marker({ position: r.path[0], map: map.current, zIndex: 999,
            icon: { path: g.maps.SymbolPath.CIRCLE, scale: 6, fillColor: '#F59E0B', fillOpacity: 1, strokeColor: '#ffffff', strokeWeight: 2 } });
        }
        setReady(true);
      }
      setInfo((dates || []).find(d => d.date === selDate) || { points: pts.length });
    } catch (e) { toast(e.message, 'err'); }
  };
  const startTimer = () => {
    timer.current = setInterval(() => {
      const path = pathRef.current;
      idx.current++;
      if (idx.current >= path.length) { idx.current = path.length - 1; stopPlay(); return; }
      if (mover.current) mover.current.setPosition(path[idx.current]);
      if (map.current) map.current.panTo(path[idx.current]);
    }, Math.max(60, 360 / speed));
  };
  const play = () => { const path = pathRef.current; if (path.length < 2 || !mover.current) return;
    if (idx.current >= path.length - 1) idx.current = 0; setPlaying(true); startTimer(); };
  const pause = () => stopPlay();
  useEffect(() => { if (playing) { if (timer.current) clearInterval(timer.current); startTimer(); } }, [speed]);
  const downloadCsv = () => selDate && download(`/api/tracking/officer/${officer.id}/route.csv?date=${selDate}`, `route_${officer.name.replace(/\s/g, '')}_${selDate}.csv`);
  return (
    <div className="modal-bg" onClick={onClose}>
      <div className="modal glass" onClick={e => e.stopPropagation()} style={{ maxWidth: 720 }}>
        <div className="section-h"><h3>Route history — {officer.name}</h3><button className="btn ghost sm" onClick={onClose}>✕</button></div>
        {nokey && <div className="glass card" style={{ color: 'var(--warn)', marginBottom: 10, fontSize: 13 }}>Add GOOGLE_MAPS_API_KEY to draw the map — the day list &amp; CSV export below still work.</div>}
        <div className="map" style={{ height: 300, marginBottom: 12 }} ref={mapEl}></div>
        {dates === null ? <Loader /> : dates.length === 0 ? <p className="muted">No route recorded in the last 3 months.</p> : <>
          <div className="toolbar">
            <select className="input" style={{ maxWidth: 260 }} value={selDate} onChange={e => { setSelDate(e.target.value); clear(); }}>
              {dates.map(d => <option key={d.date} value={d.date}>{d.date} · {d.points} pts · {d.distance_km} km</option>)}
            </select>
            <button className="btn gold" onClick={show}>Show route</button>
            <button className="btn" onClick={downloadCsv}>⬇ CSV</button>
          </div>
          {ready && <div className="toolbar" style={{ marginTop: -2 }}>
            <span className="muted" style={{ fontSize: 12.5 }}>Replay:</span>
            {!playing ? <button className="btn sm gold" onClick={play}>▶ Play</button> : <button className="btn sm" onClick={pause}>⏸ Pause</button>}
            {[1, 2, 4, 8].map(s => <div key={s} className={cx('chip', speed === s && 'on')} onClick={() => setSpeed(s)}>{s}×</div>)}
          </div>}
          {info && <div className="stat-row"><span className="k">Selected day</span>
            <b>{info.points} pts{info.distance_km != null ? ` · ${info.distance_km} km` : ''}{info.first_seen ? ` · ${info.first_seen}–${info.last_seen}` : ''}</b></div>}
        </>}
      </div>
    </div>
  );
}

function LiveRouteModal({ officer, config, onClose }) {
  const mapEl = useRef(null), map = useRef(null), curMk = useRef(null), routeObj = useRef(null);
  const [info, setInfo] = useState(null);
  const todayIST = new Date(Date.now() + 5.5 * 3600 * 1000).toISOString().slice(0, 10);
  const draw = async (fit) => {
    try {
      const pts = await api(`/api/tracking/officer/${officer.id}/route?date=${todayIST}`);
      if (!map.current || !window.google) return;
      const g = window.google;
      if (!pts.length) { setInfo({ points: 0 }); return; }
      clearRouteLayers(routeObj.current);
      routeObj.current = drawRouteLeaflet(map.current, pts, { noEnd: true, fit: !!fit });
      const P = routeObj.current.points, path = routeObj.current.path;
      const cur = path[path.length - 1], last = pts[pts.length - 1].created_at, on = isOnline(last);
      if (curMk.current) curMk.current.setPosition(cur);
      else curMk.current = new g.maps.Marker({ position: cur, map: map.current, zIndex: 999,
        label: { text: initials(officer.name), color: '#fff' }, icon: { path: g.maps.SymbolPath.CIRCLE, scale: 13, fillColor: on ? '#16A34A' : '#8494A8', fillOpacity: 1, strokeColor: '#fff', strokeWeight: 2 } });
      let d = 0; for (let i = 1; i < P.length; i++) d += kmBetween(P[i - 1], P[i]);
      setInfo({ points: pts.length, distance_km: d, last, online: on });
    } catch (e) {}
  };
  useEffect(() => {
    let timer;
    loadMaps(config && config.google_maps_api_key).then(() => {
      const g = window.google;
      map.current = new g.maps.Map(mapEl.current, { center: { lat: 17.72, lng: 83.30 }, zoom: 13, styles: DARK_MAP_STYLE });
      draw(true); timer = setInterval(() => draw(false), 3000);
    }).catch(() => {});
    return () => timer && clearInterval(timer);
  }, []);
  return (
    <div className="modal-bg" onClick={onClose}>
      <div className="modal glass" style={{ maxWidth: 780 }} onClick={e => e.stopPropagation()}>
        <div className="section-h"><h3>{officer.name} — today's live route</h3><button className="btn ghost sm" onClick={onClose}>✕</button></div>
        <div className="kpi3">
          <div className="b"><div className="l">Status</div><div className="v" style={{ color: info && info.online ? 'var(--good)' : 'var(--ink-dim)' }}>{info ? (info.online ? '● Live' : '● Offline') : '…'}</div></div>
          <div className="b"><div className="l">Distance today</div><div className="v">{info && info.distance_km != null ? info.distance_km.toFixed(1) + ' km' : '—'}</div></div>
          <div className="b"><div className="l">Last update</div><div className="v" style={{ fontSize: 14 }}>{info && info.last ? agoLabel(info.last) : '—'}</div></div>
        </div>
        <div className="glass" style={{ padding: 6, marginTop: 10 }}><div className="map tall" ref={mapEl}></div></div>
        {info && info.points === 0 && <p className="muted" style={{ marginTop: 8 }}>No movement recorded today yet. The route appears here once the officer's app sends a location.</p>}
        <p className="muted" style={{ fontSize: 11.5, marginTop: 8 }}>Live — refreshes every 3s. Green “S” is where they started today; the labelled marker is their current position.</p>
      </div>
    </div>
  );
}

function ReportModal({ officers, onClose }) {
  const today = new Date().toISOString().slice(0, 10);
  const weekAgo = new Date(Date.now() - 6 * 864e5).toISOString().slice(0, 10);
  const [start, setStart] = useState(weekAgo); const [end, setEnd] = useState(today); const [oid, setOid] = useState('');
  const dl = () => { const p = new URLSearchParams({ start, end }); if (oid) p.set('officer_id', oid);
    download('/api/tracking/distance-report?' + p.toString(), `SSD_Attendance_${start}_to_${end}.xlsx`); };
  return (
    <div className="modal-bg" onClick={onClose}>
      <div className="modal glass" onClick={e => e.stopPropagation()}>
        <div className="section-h"><h3>Attendance / distance report</h3><button className="btn ghost sm" onClick={onClose}>✕</button></div>
        <p className="muted" style={{ fontSize: 13 }}>Per-officer daily distance travelled and active hours across a date range — for payroll/attendance. Exports a two-sheet Excel (daily detail + per-officer summary).</p>
        <div className="grid2" style={{ gridTemplateColumns: '1fr 1fr' }}>
          <div className="field"><label>From</label><input className="input" type="date" value={start} onChange={e => setStart(e.target.value)} /></div>
          <div className="field"><label>To</label><input className="input" type="date" value={end} onChange={e => setEnd(e.target.value)} /></div>
        </div>
        <div className="field"><label>Officer</label>
          <select className="input" value={oid} onChange={e => setOid(e.target.value)}>
            <option value="">All field agents</option>
            {officers.filter(o => o.role === 'fos').map(o => <option key={o.id} value={o.id}>{o.name}</option>)}
          </select></div>
        <button className="btn gold block" onClick={dl}>⬇ Download Excel report</button>
      </div>
    </div>
  );
}

function TeamLeadView({ config, user }) {
  const [ov, setOv] = useState(null); const [err, setErr] = useState('');
  const [modal, setModal] = useState(false); const [editing, setEditing] = useState(null);
  const [perfUser, setPerfUser] = useState(null); const [dashUser, setDashUser] = useState(null);
  const money = v => '₹' + Math.round(Number(v) || 0).toLocaleString('en-IN');
  const load = () => api('/api/team/overview').then(setOv).catch(e => setErr(e.message || 'Could not load'));
  useEffect(() => { load(); }, []);
  const removeMember = (m) => {
    if (!window.confirm(`Remove ${m.name} from your team? They'll be marked inactive.`)) return;
    api('/api/users/' + m.id, { method: 'DELETE' }).then(() => { toast(m.name + ' removed'); load(); }).catch(e => toast(e.message, 'err'));
  };
  if (err) return <div className="glass card" style={{ color: 'var(--bad)', padding: 18 }}>{err}</div>;
  if (!ov) return <Loader />;
  const k = ov.kpis;
  const trend = { labels: (ov.trend || []).map(t => t.date.slice(5)), datasets: [{ label: 'Collected ₹', data: (ov.trend || []).map(t => t.collected), borderColor: '#2563EB', backgroundColor: 'rgba(37,99,235,.15)', fill: true, tension: .35 }] };
  const memberCard = (m) => (
    <div key={m.id} className="glass card" style={{ padding: 14 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 8 }}>
        <div>
          <b style={{ color: 'var(--gold)', cursor: 'pointer' }} title="Open full dashboard" onClick={() => setDashUser(m)}>{m.name}</b>
          {m.emp_code && <span className="badge allocated" style={{ marginLeft: 6, fontSize: 10.5 }}>{m.emp_code}</span>}
          <div className="muted" style={{ fontSize: 12 }}>{roleName(m.role)}{m.phone ? ' · ' + m.phone : ''}</div>
        </div>
        <span className="badge allocated">{Number(m.recovery_pct || 0).toFixed(0)}%</span>
      </div>
      <div style={{ display: 'flex', gap: 10, marginTop: 10, fontSize: 12 }} className="muted">
        <span>Cases <b style={{ color: 'var(--ink)' }}>{m.assigned}</b></span>
        <span>Resolved <b style={{ color: 'var(--good)' }}>{m.resolved}</b></span>
        <span>Recovered <b style={{ color: 'var(--good)' }}>{money(m.recovered)}</b></span>
      </div>
      <div className="muted" style={{ fontSize: 11.5, marginTop: 4 }}>
        Today: {m.today ? (m.today.label === 'visits' ? `${m.today.count} visits` : `${m.today.count} calls · ${m.today.ptp || 0} PTP`) : '—'}
      </div>
      <div className="toolbar" style={{ margin: '10px 0 0', flexWrap: 'wrap' }}>
        {m.phone && <a className="btn sm gold" href={'tel:' + m.phone}>📞 Call</a>}
        <button className="btn sm" onClick={() => setDashUser(m)}>Profile</button>
        <button className="btn sm" onClick={() => setPerfUser(m)}>📈 Performance</button>
        <button className="btn sm" onClick={() => { setEditing(m); setModal(true); }}>Edit</button>
        <button className="btn sm" style={{ color: 'var(--bad)' }} onClick={() => removeMember(m)}>Remove</button>
      </div>
    </div>
  );
  return (
    <div>
      <div className="toolbar"><h3 style={{ margin: 0 }}>My team{user.branch ? ' · ' + user.branch : ''}</h3><div style={{ flex: 1 }} />
        <button className="btn gold" onClick={() => { setEditing(null); setModal(true); }}>+ Add member</button></div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill,minmax(150px,1fr))', gap: 12, marginBottom: 14 }}>
        <div className="glass card" style={{ padding: 14 }}><div className="muted" style={{ fontSize: 12 }}>Team members</div><b>{k.members}</b><div className="muted" style={{ fontSize: 11 }}>{k.fos} FOS · {k.callers} callers</div></div>
        <div className="glass card" style={{ padding: 14 }}><div className="muted" style={{ fontSize: 12 }}>Cases</div><b>{k.cases}</b><div className="muted" style={{ fontSize: 11 }}>{k.resolved} resolved</div></div>
        <div className="glass card" style={{ padding: 14 }}><div className="muted" style={{ fontSize: 12 }}>Recovered</div><b style={{ color: 'var(--good)' }}>{money(k.recovered)}</b></div>
        <div className="glass card" style={{ padding: 14 }}><div className="muted" style={{ fontSize: 12 }}>Pending</div><b style={{ color: 'var(--gold)' }}>{money(k.pending)}</b></div>
        <div className="glass card" style={{ padding: 14 }}><div className="muted" style={{ fontSize: 12 }}>Recovery %</div><b>{Number(k.recovery_pct || 0).toFixed(1)}%</b></div>
      </div>

      {window.Chart && <div className="glass card" style={{ padding: 14, marginBottom: 14 }}>
        <div className="section-h"><h3 style={{ fontSize: 14 }}>Team collections — last 30 days</h3></div>
        <ChartBox type="line" data={trend} height={200} />
      </div>}

      <div className="section-h"><h3 style={{ fontSize: 15 }}>Members</h3></div>
      {ov.members.length === 0 ? <div className="glass card muted" style={{ padding: 20, textAlign: 'center' }}>No team members yet. Add FOS or callers to your team.</div> :
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill,minmax(260px,1fr))', gap: 12 }}>{ov.members.map(memberCard)}</div>}

      {ov.leaderboard && ov.leaderboard.length > 0 && <div className="glass card" style={{ padding: 6, marginTop: 16 }}>
        <div className="section-h" style={{ padding: '8px 10px 0' }}><h3 style={{ fontSize: 14 }}>Leaderboard</h3></div>
        <div className="tablewrap"><table>
          <thead><tr><th>#</th><th>Member</th><th>Role</th><th>Cases</th><th>Recovered</th><th>Recovery %</th></tr></thead>
          <tbody>{ov.leaderboard.map((m, i) => <tr key={m.id}>
            <td>{i + 1}</td><td><b>{m.name}</b></td><td>{roleName(m.role)}</td><td>{m.assigned}</td>
            <td style={{ color: 'var(--good)' }}>{money(m.recovered)}</td><td>{Number(m.recovery_pct || 0).toFixed(1)}%</td></tr>)}
          </tbody></table></div>
      </div>}

      {modal && <StaffModal me={user} editing={editing} onClose={() => setModal(false)} onDone={() => { setModal(false); load(); }} />}
      {perfUser && <PerformanceModal u={perfUser} onClose={() => setPerfUser(null)} />}
      {dashUser && <EmployeeDashboard u={dashUser} config={config} onClose={() => setDashUser(null)} />}
    </div>
  );
}

/* Move (or swap) a staff member's entire caseload to another same-role staff member. */
function TransferModal({ staff, onClose, onDone }) {
  const [role, setRole] = useState('fos');
  const [from, setFrom] = useState(''); const [to, setTo] = useState('');
  const [swap, setSwap] = useState(false); const [busy, setBusy] = useState(false);
  const roleLabel = { fos: 'Field officers', telecaller: 'Telecallers', teamlead: 'Team leads' };
  const pool = (staff || []).filter(u => u.role === role && u.is_active !== false);
  const save = async () => {
    if (!from || !to || from === to) { toast('Pick two different people', 'err'); return; }
    setBusy(true);
    try {
      const r = await api('/api/team/transfer-cases', { method: 'POST',
        body: { from_user_id: Number(from), to_user_id: Number(to), swap } });
      toast(`Moved ${r.moved} case${r.moved === 1 ? '' : 's'} ${swap ? 'between' : 'to'} ${r.to}.`);
      onDone();
    } catch (e) { toast(e.message, 'err'); } finally { setBusy(false); }
  };
  return (
    <div className="modal-bg" onClick={onClose}>
      <div className="modal glass" onClick={e => e.stopPropagation()} style={{ maxWidth: 460 }}>
        <div className="section-h"><h3>Transfer caseload</h3><button className="btn ghost sm" onClick={onClose}>✕</button></div>
        <p className="muted" style={{ fontSize: 13 }}>Move every case assigned to one person over to another of the same role. Enable swap to exchange both caseloads.</p>
        <div className="field"><label>Role</label>
          <select className="input" value={role} onChange={e => { setRole(e.target.value); setFrom(''); setTo(''); }}>
            {Object.entries(roleLabel).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></div>
        <div className="grid2" style={{ gridTemplateColumns: '1fr 1fr', gap: 10 }}>
          <div className="field"><label>From</label>
            <select className="input" value={from} onChange={e => setFrom(e.target.value)}>
              <option value="">—</option>{pool.map(u => <option key={u.id} value={u.id}>{u.name}{u.branch ? ` · ${u.branch}` : ''}</option>)}</select></div>
          <div className="field"><label>To</label>
            <select className="input" value={to} onChange={e => setTo(e.target.value)}>
              <option value="">—</option>{pool.filter(u => String(u.id) !== from).map(u => <option key={u.id} value={u.id}>{u.name}{u.branch ? ` · ${u.branch}` : ''}</option>)}</select></div>
        </div>
        <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 14, margin: '4px 0 10px' }}>
          <input type="checkbox" checked={swap} onChange={e => setSwap(e.target.checked)} /> Swap — exchange both caseloads</label>
        <div className="toolbar"><button className="btn" onClick={onClose}>Cancel</button><div style={{ flex: 1 }} />
          <button className="btn gold" disabled={busy} onClick={save}>{busy ? 'Moving…' : (swap ? '🔁 Swap caseloads' : '🔁 Transfer')}</button></div>
      </div>
    </div>
  );
}

function StaffView({ config, user }) {
  const isAdmin = user.role === 'admin';
  const canTransfer = user.role === 'admin' || user.role === 'manager';
  const [transferOpen, setTransferOpen] = useState(false);
  const seesAll = user.role === 'admin' || user.role === 'headoffice';   // cross-branch grid
  const [users, setUsers] = useState(null);
  const [branches, setBranches] = useState(null);
  const [openBranch, setOpenBranch] = useState(seesAll ? null : (user.branch || 'Unassigned'));
  const [modal, setModal] = useState(false); const [editing, setEditing] = useState(null); const [presetBranch, setPresetBranch] = useState('');
  const [addBranch, setAddBranch] = useState(false);
  const [routeOfficer, setRouteOfficer] = useState(null); const [showReport, setShowReport] = useState(false);
  const [liveOfficer, setLiveOfficer] = useState(null); const [perfUser, setPerfUser] = useState(null); const [showChart, setShowChart] = useState(false); const [dashUser, setDashUser] = useState(null);
  const load = () => { api('/api/users').then(setUsers); api('/api/team/branches').then(setBranches).catch(() => setBranches([])); };
  useEffect(() => { load(); }, []);
  const [associates, setAssociates] = useState([]);   // FOS from other locations working this branch's cases
  useEffect(() => {
    if (!openBranch) { setAssociates([]); return; }
    api('/api/team/branch-associates?branch=' + encodeURIComponent(openBranch)).then(setAssociates).catch(() => setAssociates([]));
  }, [openBranch]);
  // Admin/HO: all field officers, filterable by location (they aren't bound to a branch).
  const [fosMode, setFosMode] = useState(false);
  const [fosLoc, setFosLoc] = useState('');
  const [fosList, setFosList] = useState(null);
  const [fosLocs, setFosLocs] = useState([]);
  useEffect(() => { if (seesAll) api('/api/manpower/filters').then(d => setFosLocs(d.locations || [])).catch(() => {}); }, [seesAll]);
  useEffect(() => {
    if (!fosMode) return;
    const p = new URLSearchParams({ role: 'fos' }); if (fosLoc) p.set('location', fosLoc);
    api('/api/manpower?' + p).then(setFosList).catch(() => setFosList([]));
  }, [fosMode, fosLoc]);

  const money = v => '₹' + Math.round(Number(v) || 0).toLocaleString('en-IN');

  // ---- Employee search (across everyone in scope) ----
  const [q, setQ] = useState('');
  const q0 = q.trim().toLowerCase();
  const searchHits = q0 ? (users || []).filter(u =>
    [u.name, u.emp_code, u.phone, u.email, u.role, u.branch, u.location, u.designation]
      .some(v => String(v || '').toLowerCase().includes(q0))) : [];
  const searchBox = <input className="input" style={{ maxWidth: 240 }} placeholder="🔍 Search employees…"
    value={q} onChange={e => setQ(e.target.value)} />;
  if (q0) {
    return (
      <div>
        <div className="toolbar">
          <input className="input" style={{ maxWidth: 240 }} autoFocus placeholder="🔍 Search employees…"
            value={q} onChange={e => setQ(e.target.value)} />
          <button className="btn ghost" onClick={() => setQ('')}>✕ Clear</button>
          <div style={{ flex: 1 }} />
          <span className="muted" style={{ fontSize: 12 }}>{searchHits.length} match{searchHits.length === 1 ? '' : 'es'}</span>
        </div>
        {!users ? <Loader /> : <div className="glass card" style={{ padding: 6 }}>
          <div className="tablewrap"><table>
            <thead><tr><th>Code</th><th>Name</th><th>Role</th><th>Branch</th><th>Location</th><th>Phone</th><th></th></tr></thead>
            <tbody>{searchHits.map(u => <tr key={u.id}>
              <td className="mono">{u.emp_code || '—'}</td>
              <td><b style={{ color: 'var(--gold)', cursor: 'pointer' }} onClick={() => setDashUser({ id: u.id, name: u.name, role: u.role, branch: u.branch, phone: u.phone, emp_code: u.emp_code })}>{u.name}</b>
                {u.is_active === false && <span className="badge" style={{ marginLeft: 6 }}>inactive</span>}</td>
              <td>{roleName(u.role)}</td><td className="muted">{u.branch || '—'}</td><td>{u.location || '—'}</td><td>{u.phone || '—'}</td>
              <td style={{ whiteSpace: 'nowrap' }}><button className="btn sm" onClick={() => setDashUser({ id: u.id, name: u.name, role: u.role, branch: u.branch, phone: u.phone, emp_code: u.emp_code })}>Performance</button> <ContactBtns phone={u.phone} /></td></tr>)}
              {searchHits.length === 0 && <tr><td colSpan="7" className="muted" style={{ padding: 12 }}>No employees match “{q}”.</td></tr>}
            </tbody></table></div>
        </div>}
        {dashUser && <EmployeeDashboard u={dashUser} config={config} onClose={() => setDashUser(null)} />}
      </div>
    );
  }

  // ---- Admin / Head Office: branch grid ----
  if (seesAll && !openBranch) {
    return (
      <div>
        <div className="toolbar">
          <div className={cx('chip', !fosMode && 'on')} onClick={() => setFosMode(false)}>🏢 Branches</div>
          <div className={cx('chip', fosMode && 'on')} onClick={() => setFosMode(true)}>🧭 Field Officers</div>
          {searchBox}
          <div style={{ flex: 1 }} />
          {fosMode && <select className="input" style={{ maxWidth: 180, height: 34 }} value={fosLoc} onChange={e => setFosLoc(e.target.value)}>
            <option value="">All locations</option>{fosLocs.map(l => <option key={l} value={l}>{l}</option>)}</select>}
          <button className="btn" onClick={() => setShowReport(true)}>📅 Attendance</button>
          <button className="btn gold" onClick={() => setAddBranch(true)}>+ Add branch</button></div>
        {fosMode ? (
          !fosList ? <Loader /> : <div className="glass card" style={{ padding: 6 }}>
            <div className="muted" style={{ fontSize: 12, padding: '4px 8px' }}>{fosList.length} field officers{fosLoc ? ' in ' + fosLoc : ' (all locations)'} — they're location-based, not tied to a branch.</div>
            <div className="tablewrap"><table>
              <thead><tr><th>Code</th><th>Name</th><th>Location</th><th>Branch</th><th>Phone</th><th></th></tr></thead>
              <tbody>{fosList.map(u => <tr key={u.id}>
                <td className="mono">{u.emp_code}</td>
                <td><b style={{ color: 'var(--gold)', cursor: 'pointer' }} onClick={() => setDashUser({ id: u.id, name: u.name, role: 'fos', branch: u.branch, phone: u.phone, emp_code: u.emp_code })}>{u.name}</b></td>
                <td>{u.location || '—'}</td><td className="muted">{u.branch || '—'}</td><td>{u.phone || '—'}</td>
                <td style={{ whiteSpace: 'nowrap' }}><button className="btn sm" onClick={() => setDashUser({ id: u.id, name: u.name, role: 'fos', branch: u.branch, phone: u.phone, emp_code: u.emp_code })}>Performance</button> <ContactBtns phone={u.phone} /></td></tr>)}
                {fosList.length === 0 && <tr><td colSpan="6" className="muted" style={{ padding: 12 }}>No field officers here.</td></tr>}
              </tbody></table></div>
          </div>
        ) : !branches ? <Loader /> : branches.length === 0 ? <div className="glass card muted" style={{ padding: 24, textAlign: 'center' }}>No branches yet. Add one to assign a manager.</div> :
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill,minmax(260px,1fr))', gap: 14 }}>
            {branches.map(b => (
              <div key={b.branch} className="glass card" style={{ padding: 16, cursor: 'pointer' }} onClick={() => setOpenBranch(b.branch)}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <b style={{ fontSize: 16 }}>{b.branch}</b><span className="badge allocated">{b.staff} staff</span></div>
                <div className="muted" style={{ fontSize: 13, marginTop: 4 }}>{b.manager ? '👤 ' + b.manager.name : '⚠ No manager'}</div>
                <div style={{ display: 'flex', gap: 12, marginTop: 10, fontSize: 12 }} className="muted">
                  <span>FOS {b.fos}</span><span>Callers {b.telecaller}</span><span>Back-office {b.backend}</span></div>
                <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 10 }}>
                  <div><div className="muted" style={{ fontSize: 11 }}>Recovered</div><b style={{ color: 'var(--good)' }}>{money(b.received)}</b></div>
                  <div style={{ textAlign: 'right' }}><div className="muted" style={{ fontSize: 11 }}>Pending</div><b style={{ color: 'var(--gold)' }}>{money(b.pending)}</b></div></div>
              </div>))}
          </div>}
        {addBranch && <AddBranchModal onClose={() => setAddBranch(false)} onDone={() => { setAddBranch(false); load(); }} />}
        {showReport && users && <ReportModal officers={users} onClose={() => setShowReport(false)} />}
        {dashUser && <EmployeeDashboard u={dashUser} config={config} onClose={() => setDashUser(null)} />}
      </div>);
  }

  // ---- Branch detail: staff + stats ----
  const branchName = openBranch;
  const card = (branches || []).find(b => b.branch === branchName) || { branch: branchName, staff: 0, fos: 0, telecaller: 0, backend: 0, received: 0, pending: 0, cases: 0, manager: null };
  const staff = (users || []).filter(u => (u.branch || 'Unassigned') === branchName);
  const renameBranch = () => {
    const nn = (window.prompt('Rename branch', branchName) || '').trim();
    if (!nn || nn === branchName) return;
    api('/api/team/branches/' + encodeURIComponent(branchName), { method: 'PATCH', body: { new_name: nn } })
      .then(() => { toast('Branch renamed'); setOpenBranch(nn); load(); }).catch(e => toast(e.message, 'err'));
  };
  const deleteBranch = () => {
    if (!window.confirm(`Delete branch "${branchName}"? Its staff & cases become unassigned (staff accounts are kept).`)) return;
    api('/api/team/branches/' + encodeURIComponent(branchName), { method: 'DELETE' })
      .then(() => { toast('Branch deleted'); setOpenBranch(isAdmin ? null : branchName); load(); }).catch(e => toast(e.message, 'err'));
  };
  const removeStaff = (u) => {
    if (u.is_active === false) {
      api('/api/users/' + u.id, { method: 'PATCH', body: { is_active: true } })
        .then(() => { toast(u.name + ' reactivated'); load(); }).catch(e => toast(e.message, 'err'));
      return;
    }
    if (!window.confirm(`Remove ${u.name}? They'll be marked inactive (kept in records, not counted going forward).`)) return;
    api('/api/users/' + u.id, { method: 'DELETE' })
      .then(() => { toast(u.name + ' removed'); load(); }).catch(e => toast(e.message, 'err'));
  };
  return (
    <div>
      <div className="toolbar">
        {seesAll && <button className="btn ghost" onClick={() => setOpenBranch(null)}>← Branches</button>}
        <h3 style={{ margin: 0 }}>{branchName}</h3><div style={{ flex: 1 }} />
        {searchBox}
        <button className="btn" onClick={() => setShowChart(v => !v)}>📊 {showChart ? 'Hide analytics' : 'Analytics'}</button>
        <button className="btn" onClick={() => setShowReport(true)}>📅 Attendance</button>
        {isAdmin && branchName !== 'Unassigned' && <button className="btn" onClick={renameBranch} title="Rename this branch">✏ Rename</button>}
        {isAdmin && branchName !== 'Unassigned' && <button className="btn" onClick={deleteBranch} title="Delete this branch">🗑 Delete</button>}
        {canTransfer && <button className="btn" onClick={() => setTransferOpen(true)} title="Move all of a staff member's cases to another">🔁 Transfer cases</button>}
        <button className="btn gold" onClick={() => { setEditing(null); setPresetBranch(branchName); setModal(true); }}>+ Add staff</button></div>

      {showChart && <div style={{ marginBottom: 16 }}><Dashboard user={user} branch={branchName} /></div>}

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill,minmax(150px,1fr))', gap: 12, marginBottom: 14 }}>
        <div className="glass card" style={{ padding: 14 }}><div className="muted" style={{ fontSize: 12 }}>Manager</div><b>{card.manager ? card.manager.name : '—'}</b></div>
        <div className="glass card" style={{ padding: 14 }}><div className="muted" style={{ fontSize: 12 }}>Staff</div><b>{card.staff}</b></div>
        <div className="glass card" style={{ padding: 14 }}><div className="muted" style={{ fontSize: 12 }}>Cases</div><b>{card.cases}</b></div>
        <div className="glass card" style={{ padding: 14 }}><div className="muted" style={{ fontSize: 12 }}>Recovered</div><b style={{ color: 'var(--good)' }}>{money(card.received)}</b></div>
        <div className="glass card" style={{ padding: 14 }}><div className="muted" style={{ fontSize: 12 }}>Pending</div><b style={{ color: 'var(--gold)' }}>{money(card.pending)}</b></div>
      </div>

      {!users ? <Loader /> : <div className="glass card" style={{ padding: 6 }}>
        <div className="tablewrap"><table>
          <thead><tr><th>Name</th><th>Role</th><th>Banks</th><th>Status</th><th></th></tr></thead>
          <tbody>{staff.map(u => <tr key={u.id}>
            <td><b style={{ color: 'var(--gold)', cursor: 'pointer' }} title="Open full dashboard" onClick={() => setDashUser(u)}>{u.name}</b>
              {u.emp_code && <span className="badge allocated" style={{ marginLeft: 6, fontSize: 10.5 }}>{u.emp_code}</span>}
              <div className="muted" style={{ fontSize: 12 }}>{u.email}</div></td>
            <td><span className="badge allocated">{roleName(u.role)}</span></td>
            <td>{(u.banks || []).join(', ') || '—'}</td>
            <td>{u.is_active ? <span className="badge paid">active</span> : <span className="badge unpaid">inactive</span>}
              {u.employment_type && <div className="muted" style={{ fontSize: 11 }}>{u.employment_type}</div>}</td>
            <td style={{ whiteSpace: 'nowrap' }}>
              {(u.role === 'fos' || u.role === 'telecaller') && <button className="btn sm gold" onClick={() => setPerfUser(u)} title="Daily / weekly / monthly performance">📈 Performance</button>}
              {' '}{u.role === 'fos' && <button className="btn sm" onClick={() => setLiveOfficer(u)} title="Today's live route">📍 Live</button>}
              {' '}{u.role === 'fos' && <button className="btn sm" onClick={() => setRouteOfficer(u)} title="Route history">🕘 History</button>}
              {' '}<button className="btn sm" onClick={() => { setEditing(u); setPresetBranch(branchName); setModal(true); }}>Edit</button>
              {' '}{u.id !== user.id && <button className="btn sm" style={u.is_active === false ? { color: 'var(--good)' } : { color: 'var(--bad)' }} onClick={() => removeStaff(u)}>{u.is_active === false ? 'Restore' : 'Remove'}</button>}</td></tr>)}
          </tbody></table></div>
        {staff.length === 0 && <div className="muted" style={{ padding: 18, textAlign: 'center' }}>No staff in this branch yet.</div>}</div>}

      {associates.length > 0 && <div style={{ marginTop: 16 }}>
        <div className="section-h"><h3 style={{ fontSize: 14, margin: 0 }}>Field officers working this branch <span className="muted" style={{ fontWeight: 400, fontSize: 12 }}>(based elsewhere · assigned to this branch's cases)</span></h3></div>
        <div className="glass card" style={{ padding: 6 }}>
          <div className="tablewrap"><table>
            <thead><tr><th>Name</th><th>Role</th><th>Home branch</th><th>Cases here</th><th>Paid</th><th>Recovered</th><th>Pending</th><th></th></tr></thead>
            <tbody>{associates.map(a => <tr key={a.id}>
              <td><b style={{ color: 'var(--gold)', cursor: 'pointer' }} onClick={() => setDashUser({ id: a.id, name: a.name, role: a.role, branch: a.home_branch, phone: a.phone, emp_code: a.emp_code })}>{a.name}</b>
                {a.emp_code && <span className="badge allocated" style={{ marginLeft: 6, fontSize: 10.5 }}>{a.emp_code}</span>}</td>
              <td><span className="badge allocated">{roleName(a.role)}</span></td>
              <td className="muted">{a.home_branch}</td>
              <td>{a.cases}</td><td>{a.paid}</td>
              <td className="mono" style={{ color: 'var(--good)' }}>{money(a.received)}</td>
              <td className="mono" style={{ color: 'var(--warn)' }}>{money(a.pending)}</td>
              <td style={{ whiteSpace: 'nowrap' }}>
                <button className="btn sm" onClick={() => setDashUser({ id: a.id, name: a.name, role: a.role, branch: a.home_branch, phone: a.phone, emp_code: a.emp_code })}>Performance</button>
                {' '}<ContactBtns phone={a.phone} /></td></tr>)}
            </tbody></table></div>
        </div>
      </div>}

      {modal && <StaffModal me={user} editing={editing} presetBranch={presetBranch} onClose={() => setModal(false)} onDone={() => { setModal(false); load(); }} />}
      {transferOpen && <TransferModal staff={user.role === 'manager' ? staff : users} onClose={() => setTransferOpen(false)} onDone={() => { setTransferOpen(false); load(); }} />}
      {perfUser && <PerformanceModal u={perfUser} onClose={() => setPerfUser(null)} />}
      {dashUser && <EmployeeDashboard u={dashUser} config={config} onClose={() => setDashUser(null)} />}
      {routeOfficer && <RouteHistoryModal officer={routeOfficer} config={config} onClose={() => setRouteOfficer(null)} />}
      {liveOfficer && <LiveRouteModal officer={liveOfficer} config={config} onClose={() => setLiveOfficer(null)} />}
      {showReport && users && <ReportModal officers={users} onClose={() => setShowReport(false)} />}
    </div>
  );
}

function AddBranchModal({ onClose, onDone }) {
  const [branch, setBranch] = useState(''); const [name, setName] = useState(''); const [email, setEmail] = useState('');
  const [phone, setPhone] = useState(''); const [password, setPassword] = useState(''); const [busy, setBusy] = useState(false); const [err, setErr] = useState('');
  const save = async () => {
    setBusy(true); setErr('');
    try { await api('/api/team/branches', { method: 'POST', body: { branch, manager: { name, email, phone, password } } }); onDone(); }
    catch (e) { setErr(e.message || 'Could not create branch'); } finally { setBusy(false); }
  };
  return (
    <div className="modal-bg" onClick={onClose}><div className="modal glass" onClick={e => e.stopPropagation()} style={{ maxWidth: 460 }}>
      <div className="section-h"><h3>New branch + manager</h3><button className="btn ghost sm" onClick={onClose}>✕</button></div>
      <p className="muted" style={{ marginTop: 0, fontSize: 13 }}>Creating a branch assigns its Collections Manager, who can then add staff under it.</p>
      <div className="field"><label>Branch name</label><input className="input" value={branch} onChange={e => setBranch(e.target.value)} placeholder="e.g. Vizag" /></div>
      <div className="field"><label>Manager name</label><input className="input" value={name} onChange={e => setName(e.target.value)} /></div>
      <div className="field"><label>Manager email</label><input className="input" value={email} onChange={e => setEmail(e.target.value)} /></div>
      <div className="field"><label>Manager phone</label><input className="input" value={phone} onChange={e => setPhone(e.target.value)} /></div>
      <div className="field"><label>Temp password</label><input className="input" value={password} onChange={e => setPassword(e.target.value)} /></div>
      {err && <div style={{ color: 'var(--bad)', fontSize: 13 }}>{err}</div>}
      <button className="btn gold block" disabled={busy || !branch || !name || !email || !password} onClick={save}>{busy ? 'Creating…' : 'Create branch'}</button>
    </div></div>);
}

function PerformanceModal({ u, onClose }) {
  const [data, setData] = useState(null); const [err, setErr] = useState('');
  useEffect(() => { api('/api/team/user/' + u.id + '/performance').then(setData).catch(e => setErr(e.message || 'Could not load')); }, [u.id]);
  const money = v => '₹' + Math.round(Number(v) || 0).toLocaleString('en-IN');
  const Row = ({ label, w }) => (
    <div className="glass card" style={{ padding: 14 }}>
      <div className="muted" style={{ fontSize: 12 }}>{label}</div>
      <div style={{ display: 'flex', gap: 18, marginTop: 6 }}>
        <div><b style={{ fontSize: 20 }}>{w.count}</b><div className="muted" style={{ fontSize: 11 }}>{w.label}</div></div>
        {w.ptp != null && <div><b style={{ fontSize: 20 }}>{w.ptp}</b><div className="muted" style={{ fontSize: 11 }}>PTP</div></div>}
        <div><b style={{ fontSize: 20, color: 'var(--good)' }}>{money(w.collected)}</b><div className="muted" style={{ fontSize: 11 }}>collected</div></div>
      </div></div>);
  return (
    <div className="modal-bg" onClick={onClose}><div className="modal glass" onClick={e => e.stopPropagation()} style={{ maxWidth: 480 }}>
      <div className="section-h"><h3>{u.name} — performance</h3><button className="btn ghost sm" onClick={onClose}>✕</button></div>
      {err ? <div style={{ color: 'var(--bad)' }}>{err}</div> : !data ? <Loader /> :
        <div style={{ display: 'grid', gap: 10 }}>
          <Row label="Today" w={data.daily} /><Row label="This week" w={data.weekly} />
          <Row label="This month" w={data.monthly} /><Row label="Overall" w={data.overall} />
        </div>}
    </div></div>);
}

function EKpi({ label, val, color }) {
  return <div className="glass card" style={{ padding: 12 }}><div className="muted" style={{ fontSize: 12 }}>{label}</div><b style={{ fontSize: 18, color: color || 'inherit' }}>{val}</b></div>;
}

const EMP_CLUSTERS = [
  ['all', 'All', c => true],
  ['unpaid', 'Unpaid', c => (c.paid_status || '') === 'UNPAID'],
  ['partial', 'Partial', c => (c.paid_status || '') === 'PARTIAL'],
  ['paid', 'Paid', c => (c.paid_status || '') === 'PAID'],
  ['pending', 'Pending ₹', c => (c.paid_status || '') !== 'PAID' && Number(c.pending_amount || 0) > 0],
  ['recovered', 'Recovered', c => Number(c.received_amount || 0) > 0],
  ['resolved', 'Resolved', c => c.status === 'paid' || c.status === 'closed'],
  ['ptp', 'PTP', c => (c.disposition || '').toUpperCase() === 'PTP'],
  ['visited', 'Visited', c => c.visited || c.visited_today],
  ['notvisited', 'Not visited', c => !(c.visited || c.visited_today)],
  ['contacted', 'Contacted', c => !!c.last_contacted_at || c.contacted_today],
  ['notcontacted', 'Not contacted', c => !c.last_contacted_at && !c.contacted_today],
];
function EmployeeDashboard({ u, config, onClose }) {
  const [d, setD] = useState(null); const [err, setErr] = useState('');
  const [route, setRoute] = useState(null); const [live, setLive] = useState(null);
  const [cases, setCases] = useState(null); const [cluster, setCluster] = useState('all'); const [drawer, setDrawer] = useState(null);
  const [trends, setTrends] = useState(null);
  const money = v => '₹' + Math.round(Number(v) || 0).toLocaleString('en-IN');
  const loadEmp = () => api('/api/team/user/' + u.id + '/dashboard').then(setD).catch(e => setErr(e.message || 'Could not load'));
  const loadCases = () => api('/api/team/user/' + u.id + '/cases').then(setCases).catch(() => setCases([]));
  const loadTrends = () => api('/api/mis/employee-trends?user_id=' + u.id).then(r => setTrends(r.trends)).catch(() => setTrends(null));
  useEffect(() => { loadEmp(); loadCases(); loadTrends(); }, [u.id]);
  useDataChanged(() => { loadEmp(); loadCases(); loadTrends(); });   // live: refreshes on any log
  const isFos = u.role === 'fos';
  const clFn = (EMP_CLUSTERS.find(x => x[0] === cluster) || EMP_CLUSTERS[0])[2];
  const clCases = (cases || []).filter(clFn);
  return (
    <div className="modal-bg" onClick={onClose}>
      <div className="modal glass" onClick={e => e.stopPropagation()} style={{ maxWidth: 920, width: '96%' }}>
        <div className="section-h"><h3 style={{ margin: 0 }}>{u.name} <span className="muted" style={{ fontSize: 12, fontWeight: 400 }}>· {roleName(u.role)}{u.branch ? ' · ' + u.branch : ''}</span></h3>
          <button className="btn ghost sm" onClick={onClose}>✕</button></div>
        {err && <div style={{ color: 'var(--bad)' }}>{err}</div>}
        {!d ? <Loader /> : <>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill,minmax(120px,1fr))', gap: 10 }}>
            <EKpi label="Assigned" val={d.kpis.assigned} />
            <EKpi label="Resolved" val={d.kpis.resolved} color="var(--good)" />
            <EKpi label="Pending" val={d.kpis.pending_count} color="var(--warn)" />
            <EKpi label="Recovered" val={money(d.kpis.recovered)} color="var(--good)" />
            <EKpi label="Recovery %" val={d.kpis.recovery_pct + '%'} />
            <EKpi label="Cash coll" val={money(d.kpis.cash_collected)} />
          </div>
          {trends && <TrendStrip trends={trends} title="Cash collected — FTD / MTD / LMTD / Overall" />}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill,minmax(150px,1fr))', gap: 10, marginTop: 12 }}>
            {['daily', 'weekly', 'monthly', 'overall'].map(w => { const p = d.performance[w]; return (
              <div key={w} className="glass card" style={{ padding: 12 }}>
                <div className="muted" style={{ fontSize: 12, textTransform: 'capitalize' }}>{w}</div>
                <div style={{ display: 'flex', gap: 12, marginTop: 4 }}>
                  <div><b style={{ fontSize: 18 }}>{p.count}</b><div className="muted" style={{ fontSize: 10 }}>{p.label}</div></div>
                  {p.ptp != null && <div><b style={{ fontSize: 18 }}>{p.ptp}</b><div className="muted" style={{ fontSize: 10 }}>PTP</div></div>}
                  <div><b style={{ fontSize: 18, color: 'var(--good)' }}>{money(p.collected)}</b><div className="muted" style={{ fontSize: 10 }}>coll</div></div>
                </div></div>); })}
          </div>
          <div className="grid2" style={{ gridTemplateColumns: '1fr 1fr', gap: 12, marginTop: 12 }}>
            <div className="glass card" style={{ padding: 12 }}><b>Collection trend (30d)</b>
              <ChartBox type="line" height={200} data={{ labels: d.trend.map(t => t.date.slice(5)), datasets: [{ data: d.trend.map(t => t.collected), borderColor: '#2563EB', backgroundColor: 'rgba(37,99,235,.12)', fill: true, tension: .3 }] }} options={{ plugins: { legend: { display: false } } }} /></div>
            <div className="glass card" style={{ padding: 12 }}><b>Dispositions</b>
              {d.dispositions.length ? <ChartBox type="doughnut" height={200} options={{ cutout: '60%' }} data={{ labels: d.dispositions.map(x => x.label), datasets: [{ data: d.dispositions.map(x => x.count), backgroundColor: ['#2563EB', '#16A34A', '#D97706', '#DC2626', '#3B82F6', '#8494A8', '#1D4ED8', '#F59E0B'] }] }} /> : <div className="muted" style={{ padding: 20 }}>No dispositions yet.</div>}</div>
          </div>
          <div className="glass card" style={{ padding: 12, marginTop: 12 }}>
            {isFos ? <div className="toolbar" style={{ flexWrap: 'wrap' }}>
              <span>Visits <b>{d.field.visits}</b></span><span>Today <b>{d.field.visits_today}</b></span>
              <span>Distance <b>{d.field.distance_km} km</b></span><span>Off-location <b style={{ color: 'var(--bad)' }}>{d.field.off_location}</b></span>
              <div style={{ flex: 1 }} />
              <button className="btn sm gold" onClick={() => setLive(u)}>📍 Live route</button>
              <button className="btn sm" onClick={() => setRoute(u)}>🕘 History</button>
            </div> : <div className="toolbar" style={{ flexWrap: 'wrap' }}>
              <span>Calls <b>{d.field.calls}</b></span><span>Today <b>{d.field.calls_today}</b></span>
              <span>PTP <b>{d.field.ptp_total}</b></span><span>Kept <b style={{ color: 'var(--good)' }}>{d.field.ptp_kept}</b></span><span>Broken <b style={{ color: 'var(--bad)' }}>{d.field.ptp_broken}</b></span>
            </div>}
          </div>
          <div className="glass card" style={{ padding: 6, marginTop: 12 }}>
            <div className="section-h" style={{ padding: '6px 8px' }}><h3 style={{ margin: 0, fontSize: 15 }}>Cases {cases ? `· ${clCases.length}` : ''}</h3>
              <span className="muted" style={{ fontSize: 11.5 }}>Click a count to filter · click a row for details &amp; log</span></div>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, padding: '2px 8px 8px' }}>
              {EMP_CLUSTERS.map(([id, label, fn]) => {
                const n = (cases || []).filter(fn).length;
                return <div key={id} className={cx('chip', cluster === id && 'on')} onClick={() => setCluster(id)}>{label} ({n})</div>;
              })}
            </div>
            {!cases ? <Loader /> : clCases.length === 0 ? <div className="muted" style={{ padding: 16, textAlign: 'center' }}>No cases in this group.</div> :
              <div className="tablewrap" style={{ maxHeight: 320, overflow: 'auto' }}><table><thead><tr><th>Customer</th><th>Bank</th><th>Product</th><th>Pending</th><th>Status</th><th>Paid</th><th>Dispo</th><th>Touch</th></tr></thead>
                <tbody>{clCases.map(c => <tr key={c.id} style={{ cursor: 'pointer' }} onClick={() => setDrawer(c)}>
                  <td><b style={{ color: 'var(--gold)' }}>{c.customer_name || '—'}</b><div className="muted" style={{ fontSize: 11 }}>{c.account_no}</div></td>
                  <td>{c.bank}</td><td>{c.product || '—'}</td>
                  <td className="mono" style={{ color: 'var(--warn)' }}>{money(c.pending_amount)}</td>
                  <td><StatusBadge s={c.status} /></td><td><PaidBadge s={c.paid_status} /></td>
                  <td className="muted">{c.disposition || '—'}</td>
                  <td style={{ fontSize: 11 }}>{c.visited_today ? '📍 visited' : c.contacted_today ? '📞 called' : c.visited ? 'visited' : '—'}</td></tr>)}</tbody></table></div>}
          </div>
        </>}
        {route && <RouteHistoryModal officer={route} config={config} onClose={() => setRoute(null)} />}
        {live && <LiveRouteModal officer={live} config={config} onClose={() => setLive(null)} />}
        {drawer && <CaseDrawer c={drawer} onClose={() => setDrawer(null)} onChanged={() => { loadEmp(); loadCases(); }} />}
      </div></div>);
}

/* ============================== Field Officer ============================== */
const DISPOS_FIELD = ['PAID', 'PTP', 'NOT AVAILABLE', 'MOVED', 'WRONG ADDRESS', 'DISPUTE', 'REFUSED', 'RNR'];

function VisitModal({ c, onClose, onDone }) {
  const [coords, setCoords] = useState(null); const [photo, setPhoto] = useState(null); const [photoUrl, setPhotoUrl] = useState(null);
  const fileRef = useRef(null); const [stamping, setStamping] = useState(false);
  const [locOk, setLocOk] = useState(true); const [moved, setMoved] = useState(false);
  const [paid, setPaid] = useState(false); const [amount, setAmount] = useState('');
  const [dispo, setDispo] = useState('PTP'); const [note, setNote] = useState(''); const [ptpDate, setPtpDate] = useState('');
  const [busy, setBusy] = useState(false); const [err, setErr] = useState(''); const [gps, setGps] = useState('idle');
  const grab = async () => { setGps('getting'); try { const c = await getGPS(); setCoords(c); setGps('ok'); }
    catch (e) { setGps('fail'); setErr('GPS: ' + e.message); } };
  useEffect(() => { grab(); }, []);
  const onPhoto = async (e) => {
    const file = e.target.files[0]; if (!file) return;
    setStamping(true);
    let cc = coords;
    if (!cc) { try { cc = await getGPS({ timeout: 9000 }); setCoords(cc); setGps('ok'); } catch (x) {} }
    const stamped = await stampPhoto(file, cc, c.address);
    setPhoto(stamped); setPhotoUrl(URL.createObjectURL(stamped)); setStamping(false);
  };
  const submit = async () => {
    setErr(''); setBusy(true);
    try {
      const f = new FormData(); f.append('case_id', c.id);
      if (coords) { f.append('latitude', coords.latitude); f.append('longitude', coords.longitude);
        if (coords.accuracy) f.append('gps_accuracy', coords.accuracy); }
      f.append('location_correct', locOk); f.append('person_moved', moved);
      f.append('paid', paid); f.append('amount_collected', paid ? (amount || '0') : '0');
      f.append('disposition', moved ? 'MOVED' : dispo); f.append('note', note);
      if (ptpDate && dispo === 'PTP' && !paid) f.append('ptp_date', ptpDate);
      if (photo) f.append('photo', photo);
      await api('/api/visits', { method: 'POST', form: f });
      toast('Visit saved.'); onDone();
    } catch (e) { setErr(e.message); } finally { setBusy(false); }
  };
  return (
    <div className="modal-bg" onClick={onClose}>
      <div className="modal glass" onClick={e => e.stopPropagation()}>
        <div className="section-h"><h3>Log visit — {c.customer_name}</h3>
          <button className="btn ghost sm" onClick={onClose}>✕</button></div>
        <div className="glass card" style={{ marginBottom: 12, background: 'rgba(0,0,0,.2)' }}>
          <div className="stat-row"><span className="k">Pending</span><b className="mono" style={{ color: 'var(--warn)' }}>{INR2(c.pending_amount)}</b></div>
          <div className="stat-row"><span className="k">GPS</span><span>{gps === 'ok' && coords ?
            <span style={{ color: 'var(--good)' }}>±{Math.round(coords.accuracy)}m ✓</span> :
            gps === 'getting' ? 'locating…' : <button className="btn sm" onClick={grab}>Get GPS</button>}</span></div>
        </div>
        <div className="field"><label>GPS camera photo</label>
          <input ref={fileRef} type="file" accept="image/*" capture="environment" onChange={onPhoto} style={{ display: 'none' }} />
          <button type="button" className="btn block" onClick={() => fileRef.current && fileRef.current.click()} disabled={stamping}>
            📷 {stamping ? 'Stamping GPS…' : (photo ? 'Retake geotagged photo' : 'Open camera & capture')}
          </button>
          <div className="muted" style={{ fontSize: 11.5, marginTop: 5 }}>Opens your camera. GPS coordinates, date &amp; time are stamped onto the photo automatically.</div>
          {photoUrl && <img src={photoUrl} style={{ marginTop: 8, borderRadius: 12, maxHeight: 200, width: '100%', objectFit: 'cover' }} />}</div>
        <div className="toolbar">
          <div className={cx('chip', locOk && 'on')} onClick={() => setLocOk(!locOk)}>{locOk ? '✓ ' : ''}Location correct</div>
          <div className={cx('chip', moved && 'on')} onClick={() => setMoved(!moved)}>{moved ? '✓ ' : ''}Person moved</div>
          <div className={cx('chip', paid && 'on')} onClick={() => setPaid(!paid)}>{paid ? '✓ ' : ''}Payment collected</div>
        </div>
        {paid && <div className="field"><label>Amount collected (₹)</label>
          <input className="input" type="number" inputMode="decimal" value={amount} onChange={e => setAmount(e.target.value)} placeholder="0.00" /></div>}
        {!moved && <div className="field"><label>Disposition</label>
          <select className="input" value={dispo} onChange={e => setDispo(e.target.value)}>
            {DISPOS_FIELD.map(d => <option key={d}>{d}</option>)}</select></div>}
        {!moved && !paid && dispo === 'PTP' && <div className="field"><label>PTP date <span className="muted" style={{ fontWeight: 400 }}>(promised date — case re-surfaces then)</span></label>
          <input className="input" type="date" value={ptpDate} onChange={e => setPtpDate(e.target.value)} /></div>}
        <div className="field"><label>Note</label>
          <textarea className="input" value={note} onChange={e => setNote(e.target.value)} placeholder="What happened at the location…" /></div>
        {err && <div style={{ color: 'var(--bad)', fontSize: 13, marginBottom: 8 }}>{err}</div>}
        <button className="btn gold block" onClick={submit} disabled={busy}>{busy ? 'Saving…' : 'Save visit'}</button>
      </div>
    </div>
  );
}

// Priority + grouping helpers for the field-officer queue
const bucketRank = (b) => {
  const s = (b || '').toUpperCase();
  if (s.includes('X')) return 0;                       // cross-bucket = most overdue
  const m = s.match(/(\d+)/);
  if (m) return 10 - Math.min(9, parseInt(m[1], 10));  // higher bucket number = higher priority
  return 50;
};
function casePriority(c) {
  const pend = Number(c.pending_amount || 0);
  const b = (c.bucket || '').toUpperCase();
  if (b.includes('X') || pend >= 50000) return { label: 'High', cls: 'unpaid' };
  if (/[23456789]/.test(b) || pend >= 10000) return { label: 'Medium', cls: 'partial' };
  return { label: 'Low', cls: 'paid' };
}
/* Case working-state for the FOS/caller views: fresh (untouched, top) → touched today
   (yellow) → paid (green, bottom). Priority/high-value stays on top within a state. */
function caseState(c) {
  if ((c.paid_status || '') === 'PAID' || c.status === 'paid') return 'paid';
  if (c.visited_today || c.contacted_today || c.status === 'in_progress' || c.status === 'ptp' || c.status === 'callback') return 'touched';
  return 'fresh';
}
const STATE_RANK = { fresh: 0, touched: 1, paid: 2 };
function caseCompare(a, b) {
  const ra = STATE_RANK[caseState(a)], rb = STATE_RANK[caseState(b)];
  if (ra !== rb) return ra - rb;
  return (Number(b.propensity || 0) - Number(a.propensity || 0)) || (Number(b.pending_amount || 0) - Number(a.pending_amount || 0));
}
const STATE_STYLE = {
  paid: { borderColor: 'rgba(22,163,74,.55)', background: 'rgba(22,163,74,.09)' },
  touched: { borderColor: 'rgba(217,119,6,.5)', background: 'rgba(245,200,66,.14)' },
  fresh: null,
};

function RemindersBanner() {
  const [d, setD] = useState(null); const [open, setOpen] = useState(true); const [drawer, setDrawer] = useState(null);
  const load = () => api('/api/reminders').then(setD).catch(() => {});
  useEffect(() => { load(); }, []);
  useDataChanged(load);
  if (!d || !d.count) return null;
  return (
    <div className="glass card" style={{ padding: 10, marginBottom: 12, borderColor: 'rgba(217,119,6,.5)', background: 'rgba(245,200,66,.10)' }}>
      <div className="section-h" style={{ margin: 0, cursor: 'pointer' }} onClick={() => setOpen(o => !o)}>
        <h3 style={{ margin: 0, fontSize: 15 }}>🔔 PTP reminders · {d.count}
          <span className="muted" style={{ fontWeight: 400, fontSize: 12.5 }}> — {d.overdue} overdue · {d.due_today} due today</span></h3>
        <span className="muted">{open ? '▾' : '▸'}</span>
      </div>
      {open && <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginTop: 8 }}>
        {d.rows.slice(0, 30).map(r => <div key={r.case_id} onClick={() => setDrawer({ id: r.case_id })}
          className="glass" style={{ padding: '7px 10px', borderRadius: 10, cursor: 'pointer', minWidth: 190,
            border: '1px solid ' + (r.overdue ? 'rgba(220,38,38,.4)' : 'rgba(217,119,6,.35)') }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8 }}>
            <b style={{ fontSize: 13 }}>{r.customer || r.account || 'Case'}</b>
            <span className="badge" style={{ background: r.overdue ? 'rgba(220,38,38,.15)' : 'rgba(217,119,6,.15)', color: r.overdue ? 'var(--bad)' : 'var(--gold-2)' }}>{r.overdue ? 'Overdue' : 'Today'}</span></div>
          <div className="muted" style={{ fontSize: 11.5 }}>{r.bank} · 📅 {r.ptp_date} · {INR(r.pending)} pending</div>
        </div>)}
      </div>}
      {drawer && <CaseDrawer c={drawer} onClose={() => setDrawer(null)} onChanged={load} />}
    </div>
  );
}

function groupCases(cases) {
  const banks = {};
  cases.forEach(c => {
    const bank = c.bank || '—'; const bucket = c.bucket || 'No bucket';
    (banks[bank] = banks[bank] || {});
    (banks[bank][bucket] = banks[bank][bucket] || []).push(c);
  });
  return Object.keys(banks).sort().map(bank => {
    const buckets = Object.keys(banks[bank]).sort((a, b) => bucketRank(a) - bucketRank(b)).map(bucket => {
      const list = banks[bank][bucket].slice().sort(caseCompare);
      return { bucket, cases: list, pending: list.reduce((s, c) => s + Number(c.pending_amount || 0), 0) };
    });
    return { bank, buckets,
      count: buckets.reduce((s, bk) => s + bk.cases.length, 0),
      pending: buckets.reduce((s, bk) => s + bk.pending, 0) };
  });
}
function CaseCard({ c, onVisit, onNav, onDetails }) {
  const p = casePriority(c);
  const st = caseState(c);
  const tag = st === 'paid' ? { t: 'PAID', c: 'paid' } : st === 'touched' ? { t: c.visited_today ? 'VISITED TODAY' : 'DONE TODAY', c: 'partial' } : null;
  return (
    <div className="glass card" style={STATE_STYLE[st]}>
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8, alignItems: 'flex-start' }}>
        <b style={onDetails ? { cursor: 'pointer', color: 'var(--gold)' } : null} title={onDetails ? 'View case details' : ''} onClick={onDetails}>{c.customer_name}</b>
        <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap', justifyContent: 'flex-end' }}>
          {c.closed && <span className="badge" style={{ background: '#e5e7eb', color: '#374151' }}>🔒 CLOSED</span>}
          {(window.__ssdCfg || {}).next_period && c.period === (window.__ssdCfg || {}).next_period && <span className="badge" style={{ background: '#dbeafe', color: '#1e40af' }}>🔜 NEXT MONTH</span>}
          {tag && <span className={cx('badge', tag.c)}>{tag.t}</span>}
          <span className={cx('badge', p.cls)}>{p.label}</span><PropBadge score={c.propensity} /></div></div>
      <div className="muted" style={{ fontSize: 13, margin: '4px 0 8px' }}>{c.bank} · {c.bucket || '—'} · cyc {c.cycle || '—'}</div>
      <div style={{ fontSize: 13, color: 'var(--ink-soft)', minHeight: 34 }}>{c.address || 'No address'} {c.pincode ? `(${c.pincode})` : ''}</div>
      <div className="stat-row"><span className="k">Pending</span><b className="mono" style={{ color: 'var(--warn)' }}>{INR(c.pending_amount)}</b></div>
      <div className="toolbar" style={{ margin: '10px 0 0' }}>
        <button className="btn sm gold" style={{ flex: 1 }} onClick={onVisit} disabled={c.closed} title={c.closed ? 'Closed for the month — locked' : ''}>Log visit</button>
        {onDetails && <button className="btn sm" onClick={onDetails}>Details</button>}
        <button className="btn sm" onClick={onNav}>🧭 Navigate</button>
        <ContactBtns phone={c.phone} />
      </div>
    </div>
  );
}

function FOLiveMap({ config }) {
  const mapEl = useRef(null); const map = useRef(null); const me = useRef(null); const acc = useRef(null);
  const route = useRef(null); const caseMarks = useRef([]); const watch = useRef(null);
  const myTrail = useRef(null); const lastMe = useRef(null);
  const [nokey, setNokey] = useState(false); const [stats, setStats] = useState(null); const [count, setCount] = useState(0);
  const loadRoute = () => api('/api/tracking/me/today').then(d => {
    setStats(d);
    if (map.current && window.google && d.points && d.points.length) {
      const path = d.points.map(p => ({ lat: p.lat, lng: p.lng }));
      if (route.current) route.current.setPath(path);
      else route.current = new window.google.maps.Polyline({ path, strokeColor: '#E9C877', strokeWeight: 4, strokeOpacity: .9, map: map.current });
    }
  }).catch(() => {});
  useEffect(() => {
    let routeTimer;
    loadMaps(config && config.google_maps_api_key).then(g => {
      map.current = new g.maps.Map(mapEl.current, { center: { lat: 17.72, lng: 83.30 }, zoom: 13, styles: DARK_MAP_STYLE });
      api('/api/cases').then(cs => {
        setCount(cs.length); const b = new g.maps.LatLngBounds(); let any = false;
        cs.forEach(c => {
          if (c.latitude && c.longitude) {
            any = true;
            const m = new g.maps.Marker({ position: { lat: c.latitude, lng: c.longitude }, map: map.current, title: c.customer_name,
              icon: { path: g.maps.SymbolPath.CIRCLE, scale: 8, fillColor: '#E9C877', fillOpacity: .95, strokeColor: '#B8893A', strokeWeight: 1.5 } });
            const info = new g.maps.InfoWindow({ content:
              `<div style="color:#111;font-family:sans-serif;font-size:13px"><b>${(c.customer_name || '').replace(/</g, '')}</b><br>${c.bank || ''} · pending ₹${Math.round(c.pending_amount || 0)}<br>`
              + `<a href="https://www.google.com/maps/dir/?api=1&destination=${c.latitude},${c.longitude}" target="_blank">Navigate ›</a></div>` });
            m.addListener('click', () => info.open(map.current, m));
            caseMarks.current.push(m); b.extend({ lat: c.latitude, lng: c.longitude });
          }
        });
        if (any) map.current.fitBounds(b, 60);
      }).catch(() => {});
      loadRoute(); routeTimer = setInterval(loadRoute, 60000);
      if (navigator.geolocation) {
        watch.current = navigator.geolocation.watchPosition(pos => {
          const p = { lat: pos.coords.latitude, lng: pos.coords.longitude }; const r = pos.coords.accuracy || 30;
          const prev = lastMe.current; const moved = prev && (prev.lat !== p.lat || prev.lng !== p.lng);
          const heading = moved ? bearingDeg(prev, p) : (prev ? prev.hd : 0);
          if (me.current) {
            try { me.current._m.setIcon(fosDivIcon('You', heading)); } catch (e) {}
            if (moved) animateMarker(me.current._m, p.lat, p.lng, 900); else me.current._m.setLatLng([p.lat, p.lng]);
          } else {
            me.current = new g.maps.Marker({ position: p, map: map.current, zIndex: 999, title: 'You' });
            try { me.current._m.setIcon(fosDivIcon('You', heading)); me.current._m.setZIndexOffset(900); } catch (e) {}
            map.current.setCenter(p); map.current.setZoom(15);
          }
          // grow a live breadcrumb trail as I move
          if (window.L && map.current._map) {
            if (!myTrail.current) myTrail.current = window.L.polyline([[p.lat, p.lng]], { color: '#6BB6F0', weight: 4, opacity: .85, lineCap: 'round' }).addTo(map.current._map);
            else if (moved) myTrail.current.addLatLng([p.lat, p.lng]);
          }
          lastMe.current = { lat: p.lat, lng: p.lng, hd: heading };
          if (acc.current) { acc.current.setCenter(p); acc.current.setRadius(r); }
          else acc.current = new g.maps.Circle({ center: p, radius: r, map: map.current, fillColor: '#6BB6F0', fillOpacity: .12, strokeColor: '#6BB6F0', strokeOpacity: .4, strokeWeight: 1 });
        }, () => {}, { enableHighAccuracy: true, maximumAge: 5000, timeout: 15000 });
      }
    }).catch(() => setNokey(true));
    return () => { if (routeTimer) clearInterval(routeTimer); if (watch.current != null && navigator.geolocation) navigator.geolocation.clearWatch(watch.current); };
  }, []);
  const recenter = () => { if (me.current && map.current) { const ll = me.current._m.getLatLng(); map.current.panTo({ lat: ll.lat, lng: ll.lng }); map.current.setZoom(15); } };
  return (
    <div>
      <div className="toolbar">
        <span className="muted">Your live position · today's route · your {count} allocated cases</span>
        <div style={{ flex: 1 }} />
        {stats && <span className="badge allocated">{stats.distance_km} km today · {stats.count} pings</span>}
        <button className="btn sm gold" onClick={recenter}>◎ Recenter on me</button>
        <button className="btn sm" onClick={loadRoute}>↻</button>
      </div>
      {nokey && <div className="glass card" style={{ color: 'var(--warn)', marginBottom: 10 }}>Add GOOGLE_MAPS_API_KEY to the backend .env to see the map.</div>}
      <div className="glass" style={{ padding: 6 }}><div className="map tall" ref={mapEl}></div></div>
      <div className="muted" style={{ fontSize: 12, marginTop: 8 }}>🔵 you · 🟡 allocated cases (tap a pin to navigate) · gold line = today's route. Keep this screen open with location on for live tracking.</div>
    </div>
  );
}

function FOCases({ config }) {
  const [cases, setCases] = useState(null); const [view, setView] = useState('list'); const [active, setActive] = useState(null); const [detail, setDetail] = useState(null);
  const [collapsed, setCollapsed] = useState({}); const [bucketFilter, setBucketFilter] = useState('');
  const [search, setSearch] = useState('');
  const mapEl = useRef(null); const map = useRef(null);
  const load = () => api('/api/cases').then(setCases);
  useEffect(() => { load(); }, []);
  useDataChanged(load);
  // Search across name / account / card / phone (digit-aware, so "98765" matches a phone).
  const matchQ = (c) => { const q = search.trim().toLowerCase(); if (!q) return true;
    const digits = q.replace(/\D/g, ''); const fields = [c.customer_name, c.account_no, c.card_no, c.phone, c.alt_phone];
    return fields.some(v => v && String(v).toLowerCase().includes(q)) ||
      (digits && fields.some(v => v && String(v).replace(/\D/g, '').includes(digits))); };
  useEffect(() => {
    if (view !== 'map' || !cases) return;
    const pts = cases.filter(c => (!bucketFilter || (c.bucket || 'No bucket') === bucketFilter) && matchQ(c));
    loadMaps(config && config.google_maps_api_key).then((g) => {
      map.current = new g.maps.Map(mapEl.current, { center: { lat: 17.72, lng: 83.30 }, zoom: 11, styles: DARK_MAP_STYLE });
      const bounds = new g.maps.LatLngBounds(); let any = false;
      pts.forEach(c => { if (c.latitude && c.longitude) { any = true;
        const m = new g.maps.Marker({ position: { lat: c.latitude, lng: c.longitude }, map: map.current, title: c.customer_name });
        m.addListener('click', () => setActive(c)); bounds.extend({ lat: c.latitude, lng: c.longitude }); } });
      if (any) map.current.fitBounds(bounds, 60);
    }).catch(() => { });
  }, [view, cases, bucketFilter, search]);
  const openNav = (c) => {
    const q = c.latitude && c.longitude ? `${c.latitude},${c.longitude}` : encodeURIComponent(c.address || c.pincode || '');
    window.open(`https://www.google.com/maps/dir/?api=1&destination=${q}`, '_blank');
  };
  if (!cases) return <Loader />;
  const allBuckets = Array.from(new Set(cases.map(c => c.bucket || 'No bucket'))).sort((a, b) => bucketRank(a) - bucketRank(b));
  const shown = cases.filter(c => (!bucketFilter || (c.bucket || 'No bucket') === bucketFilter) && matchQ(c));
  const groups = groupCases(shown);
  const toggle = (bank) => setCollapsed(s => ({ ...s, [bank]: !s[bank] }));
  return (
    <div>
      <RemindersBanner />
      <div className="toolbar">
        <div className={cx('chip', view === 'list' && 'on')} onClick={() => setView('list')}>☰ Grouped</div>
        <div className={cx('chip', view === 'map' && 'on')} onClick={() => setView('map')}>◎ Map</div>
        <input value={search} onChange={e => setSearch(e.target.value)} placeholder="🔍 Search name / account / card / phone"
          style={{ minWidth: 230, border: '1px solid var(--stroke-soft)', borderRadius: 10, padding: '7px 10px', fontSize: 13 }} />
        {search && <button className="btn ghost sm" onClick={() => setSearch('')}>✕</button>}
        <div style={{ flex: 1 }} />
        <span className="muted" style={{ fontSize: 11.5, display: 'flex', gap: 8, alignItems: 'center' }}>
          <span><span style={{ display: 'inline-block', width: 9, height: 9, borderRadius: 2, background: '#E3E9F1', marginRight: 3 }} />To do</span>
          <span><span style={{ display: 'inline-block', width: 9, height: 9, borderRadius: 2, background: 'rgba(245,200,66,.9)', marginRight: 3 }} />Visited</span>
          <span><span style={{ display: 'inline-block', width: 9, height: 9, borderRadius: 2, background: 'rgba(22,163,74,.8)', marginRight: 3 }} />Paid</span>
        </span>
        <span className="muted">{shown.length}{bucketFilter ? ` of ${cases.length}` : ''} assigned</span>
      </div>
      <div className="toolbar" style={{ marginTop: -2 }}>
        <span className="muted" style={{ fontSize: 12.5 }}>Bucket:</span>
        <div className={cx('chip', !bucketFilter && 'on')} onClick={() => setBucketFilter('')}>All ({cases.length})</div>
        {allBuckets.map(b => {
          const n = cases.filter(c => (c.bucket || 'No bucket') === b).length;
          return <div key={b} className={cx('chip', bucketFilter === b && 'on')} onClick={() => setBucketFilter(b)}>{b} ({n})</div>;
        })}
      </div>
      {view === 'map' ? <div className="glass" style={{ padding: 6 }}><div className="map tall" ref={mapEl}></div></div> :
        shown.length === 0 ? <p className="muted">{search ? `No cases match "${search}".` : 'No cases in this bucket.'}</p> :
          <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
            {groups.map(bank => <div key={bank.bank} className="glass card">
              <div className="section-h" style={{ cursor: 'pointer', margin: 0 }} onClick={() => toggle(bank.bank)}>
                <h3>{collapsed[bank.bank] ? '▸' : '▾'} {bank.bank}
                  <span className="muted" style={{ fontWeight: 400, fontSize: 13 }}> · {bank.count} cases · {INR(bank.pending)} pending</span></h3>
              </div>
              {!collapsed[bank.bank] && bank.buckets.map(bk => <div key={bk.bucket} style={{ marginTop: 12 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, margin: '4px 2px 8px' }}>
                  <span className="badge allocated">{bk.bucket}</span>
                  <span className="muted" style={{ fontSize: 12.5 }}>{bk.cases.length} cases · {INR(bk.pending)} pending</span>
                </div>
                <div className="grid3">
                  {bk.cases.map(c => <CaseCard key={c.id} c={c} onVisit={() => setActive(c)} onNav={() => openNav(c)} onDetails={() => setDetail(c)} />)}
                </div>
              </div>)}
            </div>)}
          </div>}
      {active && <VisitModal c={active} onClose={() => setActive(null)} onDone={() => { setActive(null); load(); }} />}
      {detail && <CaseDrawer c={detail} onClose={() => setDetail(null)} onChanged={load} />}
    </div>
  );
}

/* Background location ping loop for field officers */
function useLocationPing(user, config) {
  useEffect(() => {
    if (!user || user.role !== 'fos') return;
    // ---- Native Android (Capacitor): true background tracking via a foreground service ----
    const Cap = window.Capacitor;
    if (Cap && (Cap.isNativePlatform ? Cap.isNativePlatform() : Cap.isNative) && Cap.registerPlugin) {
      // Our own native foreground-location service (LocationService) reads GPS and POSTs to
      // /api/tracking/ping from native code — so it keeps reporting when the app is locked,
      // backgrounded, or switched away. It requests the location permission itself on start.
      try {
        const Tracker = Cap.registerPlugin('Tracker');
        Tracker.start({ url: (window.location.origin || '') + '/api/tracking/ping', token: store.t || '' });
      } catch (e) {}
      return () => { try { Cap.registerPlugin('Tracker').stop(); } catch (e) {} };
    }
    // ---- Web fallback (foreground only) ----
    if (!navigator.geolocation) return;
    let alive = true, lastSent = 0, lastPos = null, watchId = null, wakeLock = null;
    const minGap = 2 * 1000;                                    // allow a location send about every 3s
    const heartbeatMs = 3 * 1000;                              // force a ping every 3s even when stationary
    const distM = (a, b) => { if (!a || !b) return 1e9; const R = 6371000, dLa = (b.latitude - a.latitude) * Math.PI / 180,
      dLo = (b.longitude - a.longitude) * Math.PI / 180, la1 = a.latitude * Math.PI / 180, la2 = b.latitude * Math.PI / 180;
      const h = Math.sin(dLa / 2) ** 2 + Math.cos(la1) * Math.cos(la2) * Math.sin(dLo / 2) ** 2; return 2 * R * Math.asin(Math.sqrt(h)); };
    const push = async (coords, force) => {
      const now = Date.now();
      if (!force && now - lastSent < minGap && distM(lastPos, coords) < 20) return;   // skip tiny jitter
      lastSent = now; lastPos = coords;
      try { await api('/api/tracking/ping', { method: 'POST', body: { latitude: coords.latitude, longitude: coords.longitude, accuracy: coords.accuracy, speed: coords.speed } }); } catch (e) {}
    };
    // real-time movement stream (fires as the officer moves)
    const startWatch = () => {
      if (watchId != null) return;
      watchId = navigator.geolocation.watchPosition(
        p => { if (alive) push(p.coords, false); }, () => {},
        { enableHighAccuracy: true, maximumAge: 4000, timeout: 25000 });
    };
    // heartbeat keeps the "live" status fresh even while standing still
    const heartbeat = setInterval(() => {
      if (!alive) return;
      navigator.geolocation.getCurrentPosition(p => alive && push(p.coords, true), () => {}, { enableHighAccuracy: true, maximumAge: 8000, timeout: 25000 });
    }, heartbeatMs);
    // keep the screen awake so tracking keeps running in the field
    const lock = async () => { try { if ('wakeLock' in navigator && document.visibilityState === 'visible') wakeLock = await navigator.wakeLock.request('screen'); } catch (e) {} };
    // re-acquire the watch + wake lock whenever the app comes back to the foreground
    const onVis = () => { if (document.visibilityState === 'visible' && alive) { startWatch(); lock(); } };
    document.addEventListener('visibilitychange', onVis);
    startWatch(); lock();
    return () => { alive = false; clearInterval(heartbeat); if (watchId != null) navigator.geolocation.clearWatch(watchId);
      document.removeEventListener('visibilitychange', onVis); if (wakeLock) { try { wakeLock.release(); } catch (e) {} } };
  }, [user && user.id]);
}

/* ============================== Telecaller ============================== */
const DISPOS_CALL = ['RTP', 'PTP', 'RNR', 'SWITCHED OFF', 'WRONG NUMBER', 'BUSY', 'NOT REACHABLE', 'DISPUTE', 'PAID'];
function CallModal({ c, onClose, onDone }) {
  const [dispo, setDispo] = useState('PTP'); const [amt, setAmt] = useState('');
  const [ptpDate, setPtpDate] = useState(''); const [followDate, setFollowDate] = useState('');
  const [paidAmt, setPaidAmt] = useState(''); const [note, setNote] = useState(''); const [normStab, setNormStab] = useState('STAB');
  const [busy, setBusy] = useState(false); const [err, setErr] = useState('');
  const isPTP = dispo === 'PTP';   // RTP = Refuse to Pay is not a promise
  const isPaid = dispo === 'PAID'; const isCC = c.segment === 'Credit Card';
  const save = async () => {
    setErr(''); setBusy(true);
    const body = { case_id: c.id, disposition: dispo, note };
    if (isPTP) { body.ptp_amount = amt || '0'; body.ptp_date = ptpDate || null; }
    else if (isPaid) { body.paid_amount = paidAmt || '0'; if (isCC) body.norm_stab = normStab; }
    else { body.follow_up_date = followDate || null; }
    try { await api('/api/calls', { method: 'POST', body });
      toast(isPaid ? 'Marked paid — removed from queue.' : 'Call logged.'); onDone();
    } catch (e) { setErr(e.message); } finally { setBusy(false); }
  };
  const outcome = isPaid ? 'This case will leave the queue.'
    : isPTP ? (ptpDate ? `Re-queues on ${ptpDate} (PTP).` : 'Set a PTP date to schedule the callback.')
    : (followDate ? `Scheduled to call back on ${followDate}.` : 'Stays due — will reappear tomorrow if not scheduled.');
  return (
    <div className="modal-bg" onClick={onClose}>
      <div className="modal glass" onClick={e => e.stopPropagation()}>
        <div className="section-h"><h3>Log call — {c.customer_name}</h3>
          <button className="btn ghost sm" onClick={onClose}>✕</button></div>
        <div className="glass card" style={{ marginBottom: 12, background: 'rgba(0,0,0,.2)' }}>
          <div className="stat-row"><span className="k">Phone</span><b>{c.phone || '—'}</b></div>
          <div className="stat-row"><span className="k">Pending</span><b className="mono" style={{ color: 'var(--warn)' }}>{INR2(c.pending_amount)}</b></div>
          {c.phone && <div className="toolbar" style={{ marginTop: 8 }}><ContactBtns phone={c.phone} /></div>}
        </div>
        <div className="field"><label>Disposition</label>
          <select className="input" value={dispo} onChange={e => setDispo(e.target.value)}>{DISPOS_CALL.map(d => <option key={d}>{d}</option>)}</select></div>
        {isPTP && <div className="grid2" style={{ gridTemplateColumns: '1fr 1fr' }}>
          <div className="field"><label>PTP amount (₹)</label><input className="input" type="number" value={amt} onChange={e => setAmt(e.target.value)} /></div>
          <div className="field"><label>PTP date</label><input className="input" type="date" value={ptpDate} onChange={e => setPtpDate(e.target.value)} /></div>
        </div>}
        {isPaid && <div className="grid2" style={{ gridTemplateColumns: isCC ? '1fr 1fr' : '1fr' }}>
          <div className="field"><label>Amount collected (₹)</label>
            <input className="input" type="number" value={paidAmt} onChange={e => setPaidAmt(e.target.value)} placeholder="0.00" /></div>
          {isCC && <div className="field"><label>Paid at (credit card)</label>
            <select className="input" value={normStab} onChange={e => setNormStab(e.target.value)}><option>STAB</option><option>NORM</option><option>ROLLBACK</option></select></div>}
        </div>}
        {!isPTP && !isPaid && <div className="field"><label>Schedule next call (optional)</label>
          <input className="input" type="date" value={followDate} onChange={e => setFollowDate(e.target.value)} /></div>}
        <div className="field"><label>Note</label><textarea className="input" value={note} onChange={e => setNote(e.target.value)} /></div>
        <div className="muted" style={{ fontSize: 12.5, marginBottom: 10 }}>➡ {outcome}</div>
        {err && <div style={{ color: 'var(--bad)', fontSize: 13, marginBottom: 8 }}>{err}</div>}
        <button className="btn gold block" onClick={save} disabled={busy}>{busy ? 'Saving…' : 'Save call'}</button>
      </div>
    </div>
  );
}

function histIcon(d) {
  const s = (d || '').toUpperCase();
  if (s.includes('PAYMENT')) return '💰';
  if (s.includes('PTP')) return '🤝';   // RTP (Refuse to Pay) is not a promise
  if (s.includes('PAID')) return '✅';
  if (s.includes('RNR') || s.includes('NO ANSWER') || s.includes('SWITCH')) return '📵';
  return '📞';
}
const TL_ICON = { created: '🆕', allocated: '📌', visit: '📍', call: '📞', payment: '💰' };

function CaseDrawer({ c, onClose, onChanged }) {
  const [cur, setCur] = useState(c); const [hist, setHist] = useState(null); const [tab, setTab] = useState('call');
  const [tpls, setTpls] = useState([]); const [tplId, setTplId] = useState(''); const [msg, setMsg] = useState('');
  const [dispo, setDispo] = useState('PTP'); const [amt, setAmt] = useState(''); const [ptpDate, setPtpDate] = useState('');
  const [followDate, setFollowDate] = useState(''); const [callNote, setCallNote] = useState('');
  const [payAmt, setPayAmt] = useState(''); const [payMode, setPayMode] = useState('UPI'); const [payNote, setPayNote] = useState(''); const [normStab, setNormStab] = useState('STAB');
  const [ncAddr, setNcAddr] = useState(''); const [ncPhone, setNcPhone] = useState(''); const [ncEdit, setNcEdit] = useState(false);
  const [busy, setBusy] = useState(false);
  const saveContact = async () => {
    if (!ncAddr.trim() && !ncPhone.trim()) { toast('Enter a new address and/or phone', 'err'); return; }
    setBusy(true);
    try {
      const updated = await api(`/api/cases/${c.id}/contact-update`, { method: 'POST', body: { new_address: ncAddr, new_phone: ncPhone } });
      setCur(updated); setNcEdit(false); toast('Saved — assigned field officer notified.'); await refresh(); onChanged && onChanged();
    } catch (e) { toast(e.message, 'err'); } finally { setBusy(false); }
  };
  const isPTP = dispo === 'PTP';   // RTP = Refuse to Pay is not a promise
  const isPaid = dispo === 'PAID'; const isCC = cur.segment === 'Credit Card';
  const refresh = () => Promise.all([
    api(`/api/cases/${c.id}`).then(setCur).catch(() => {}),
    api(`/api/cases/${c.id}/timeline`).then(setHist).catch(() => setHist([])),
  ]);
  useEffect(() => { refresh(); api('/api/templates').then(setTpls).catch(() => {}); }, []);
  const pickTpl = (id) => { setTplId(id); const t = tpls.find(x => String(x.id) === String(id)); setMsg(t ? renderTemplate(t.body, cur) : ''); };
  const waSend = () => {
    if (!cur.phone || !msg) return;
    window.open(`https://wa.me/${String(cur.phone).replace(/[^0-9]/g, '')}?text=${encodeURIComponent(msg)}`, '_blank');
    api('/api/templates/log', { method: 'POST', body: { case_id: c.id, channel: 'whatsapp', text: msg } }).then(() => { toast('Message logged'); refresh(); }).catch(() => {});
  };
  const logCall = async () => {
    setBusy(true);
    const body = { case_id: c.id, disposition: dispo, note: callNote };
    if (isPTP) { body.ptp_amount = amt || '0'; body.ptp_date = ptpDate || null; }
    else if (isPaid) { body.paid_amount = amt || '0'; if (isCC) body.norm_stab = normStab; }
    else { body.follow_up_date = followDate || null; }
    try { await api('/api/calls', { method: 'POST', body }); toast('Call logged.');
      setCallNote(''); await refresh(); onChanged && onChanged();
    } catch (e) { toast(e.message, 'err'); } finally { setBusy(false); }
  };
  const recordPay = async () => {
    if (!payAmt) return; setBusy(true);
    try { const updated = await api(`/api/cases/${c.id}/payment`, { method: 'POST', body: { amount: payAmt, mode: payMode, note: payNote, norm_stab: isCC ? normStab : null } });
      setCur(updated); setPayAmt(''); setPayNote(''); toast('Payment recorded.'); await refresh(); onChanged && onChanged();
    } catch (e) { toast(e.message, 'err'); } finally { setBusy(false); }
  };
  const meRole = (store.u || {}).role; const meId = (store.u || {}).id;
  const canEscalate = ['admin', 'manager', 'backend', 'teamlead'].includes(meRole);
  const showCallFos = cur.assigned_fos_phone && cur.assigned_fos_id !== meId;
  const showCallCaller = cur.assigned_caller_phone && cur.assigned_caller_id !== meId;
  const canEditContact = ['admin', 'headoffice', 'manager', 'backend', 'telecaller', 'teamlead'].includes(meRole);
  const escalate = async () => {
    setBusy(true);
    try {
      const path = cur.escalated ? 'deescalate' : 'escalate';
      await api(`/api/cases/${c.id}/${path}`, { method: 'POST', body: {} });
      toast(cur.escalated ? 'Released back to the pool.' : 'Escalated to you — off the FOS/caller’s performance.');
      await refresh(); onChanged && onChanged();
    } catch (e) { toast(e.message, 'err'); } finally { setBusy(false); }
  };
  const canUndo = ['admin', 'headoffice', 'manager', 'backend', 'telecaller', 'teamlead'].includes(meRole);
  const undoLast = async () => {
    if (!window.confirm('Undo the last change on this case? This reverses the most recent payment, or restores the last edited field.')) return;
    setBusy(true);
    try {
      const updated = await api(`/api/cases/${c.id}/undo`, { method: 'POST' });
      setCur(updated); toast('Last change undone.'); await refresh(); onChanged && onChanged();
    } catch (e) { toast(e.message || 'Nothing to undo', 'err'); } finally { setBusy(false); }
  };
  const row = (k, v) => <React.Fragment key={k}><div className="dt">{k}</div><div className="dd">{v || '—'}</div></React.Fragment>;
  return (
    <div className="drawer-bg" onClick={onClose}>
      <div className="drawer glass" onClick={e => e.stopPropagation()}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 10 }}>
          <div><div className="brandfont" style={{ fontSize: 19, fontWeight: 600 }}>{cur.customer_name || '—'}</div>
            <div className="muted" style={{ fontSize: 13 }}>{cur.account_no || 'no account'} · {cur.bank || ''}</div></div>
          <button className="btn ghost sm" onClick={onClose}>✕</button>
        </div>
        <div className="toolbar" style={{ margin: '12px 0' }}>
          {cur.phone && <a className="btn sm gold" href={'tel:' + cur.phone}>📞 Call customer</a>}
          {cur.phone && <a className="btn sm" href={'https://wa.me/' + String(cur.phone).replace(/[^0-9]/g, '')} target="_blank" rel="noreferrer">WhatsApp</a>}
          {showCallFos && <a className="btn sm" href={'tel:' + cur.assigned_fos_phone} title={'Call the assigned field agent: ' + (cur.assigned_fos_name || '')}>🧑‍🔧 Call FOS</a>}
          {showCallCaller && <a className="btn sm" href={'tel:' + cur.assigned_caller_phone} title={'Call the assigned caller: ' + (cur.assigned_caller_name || '')}>☎️ Call caller</a>}
          {canEscalate && <button className="btn sm" disabled={busy} onClick={escalate} title={cur.escalated ? 'Return to the FOS/caller pool' : 'Pull off the FOS/caller and own it (stays in MIS & feedback)'}>{cur.escalated ? '↩ Release' : '🚩 Escalate to me'}</button>}
          {canUndo && <button className="btn sm" disabled={busy} onClick={undoLast} title="Reverse the last payment, or restore the last edited field on this case">↶ Undo last</button>}
          <StatusBadge s={cur.status} /><PaidBadge s={cur.paid_status} /><PropBadge score={cur.propensity} />
          {cur.escalated && <span className="badge" style={{ background: 'rgba(220,38,38,.15)', color: 'var(--bad)' }}>Escalated</span>}
        </div>
        {(() => {
          // Funding-load sheets carry a FUNDING AMOUNT; CC & PL/BL sheets don't, so use Total
          // Outstanding (TOS) — then ENR — as the base, and derive Pending from it (never negative).
          const base = Number(cur.funding_amount) > 0 ? Number(cur.funding_amount)
            : (Number(cur.total_outstanding) > 0 ? Number(cur.total_outstanding) : (Number(cur.enr) || 0));
          const recv = Number(cur.received_amount) || 0;
          const pend = Math.max(0, base - recv);
          const label = Number(cur.funding_amount) > 0 ? 'Funded' : 'Outstanding';
          return <div className="kpi3">
            <div className="b"><div className="l">{label}</div><div className="v">{INR(base)}</div></div>
            <div className="b"><div className="l">Received</div><div className="v" style={{ color: 'var(--good)' }}>{INR(recv)}</div></div>
            <div className="b"><div className="l">Pending</div><div className="v" style={{ color: 'var(--warn)' }}>{INR(pend)}</div></div>
          </div>;
        })()}
        <div className="divider"></div>
        <div className="section-h"><h3 style={{ fontSize: 14 }}>Account details</h3></div>
        <div className="dl">
          {row('Phone', cur.phone)}{row('Alt phone', cur.alt_phone)}
          {row('Address 1', cur.address)}{cur.address2 ? row('Address 2', cur.address2) : null}{row('Pincode', cur.pincode)}
          {row('Bank / Product', (cur.bank || '') + (cur.product ? ' · ' + cur.product : '') + (cur.segment ? ' · ' + cur.segment : ''))}
          {row('Card no', cur.card_no)}
          {row('Bucket / Cycle', (cur.bucket || '—') + ' · cyc ' + (cur.cycle || '—'))}
          {row('Month', cur.month)}
          {row('Branch / Area', (cur.branch || '—') + (cur.team ? ' · ' + cur.team : ''))}
          {row('Team lead', cur.team_lead)}{row('Category', cur.cat)}
          {row('Caller', cur.caller_name)}{row('Field agent (FOS)', cur.fos_name)}
          {/* recovery figures */}
          {row('ENR', Number(cur.enr) ? INR(cur.enr) : null)}
          {row('Outstanding (TOS)', Number(cur.total_outstanding) ? INR(cur.total_outstanding) : null)}
          {row('Principal (POS)', Number(cur.principal_outstanding) ? INR(cur.principal_outstanding) : null)}
          {(Number(cur.norm_amount) || Number(cur.stab_amount) || cur.norm_stab) && row('NORM / STAB',
            `${Number(cur.norm_amount) ? 'NORM ' + INR(cur.norm_amount) : ''}${Number(cur.stab_amount) ? '  ·  STAB ' + INR(cur.stab_amount) : ''}${cur.norm_stab ? '  ·  paid: ' + cur.norm_stab : ''}`.trim() || '—')}
          {row('Cash collected', Number(cur.received_amount) ? INR(cur.received_amount) : null)}
          {row('Last disposition', cur.disposition)}
          {row('Last contacted', cur.last_contacted_at ? fmtDT(cur.last_contacted_at) : null)}
          {row('Next follow-up', cur.follow_up_date)}
          {row('Remarks', cur.remarks)}
        </div>
        {(cur.new_phone || cur.new_address) && <div className="glass card" style={{ borderLeft: '3px solid var(--gold)', margin: '10px 0' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 8 }}>
            <b>🆕 Latest customer contact</b>
            <span className="muted" style={{ fontSize: 11 }}>{cur.new_contact_by ? 'by ' + cur.new_contact_by : ''}{cur.new_contact_at ? ' · ' + fmtDT(cur.new_contact_at) : ''}</span>
          </div>
          {cur.new_phone && <div style={{ marginTop: 8, display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
            <span>📞 <b>{cur.new_phone}</b></span>
            <a className="btn sm gold" href={'tel:' + cur.new_phone}>Call</a>
            <a className="btn sm" href={'https://wa.me/' + String(cur.new_phone).replace(/[^0-9]/g, '')} target="_blank" rel="noreferrer">WhatsApp</a></div>}
          {cur.new_address && <div style={{ marginTop: 8, display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
            <span>📍 {cur.new_address}</span>
            <a className="btn sm" href={'https://www.google.com/maps/search/?api=1&query=' + encodeURIComponent(cur.new_address)} target="_blank" rel="noreferrer">Navigate</a></div>}
        </div>}
        {canEditContact && (ncEdit ? <div className="glass card" style={{ margin: '10px 0' }}>
          <div className="section-h"><h3 style={{ fontSize: 14 }}>Update customer contact</h3></div>
          <p className="muted" style={{ fontSize: 12, marginTop: 0 }}>Saving alerts the assigned field officer instantly.</p>
          <div className="field"><label>New phone</label><input className="input" value={ncPhone} onChange={e => setNcPhone(e.target.value)} placeholder="10-digit mobile" /></div>
          <div className="field"><label>New address</label><textarea className="input" value={ncAddr} onChange={e => setNcAddr(e.target.value)} placeholder="latest address found" /></div>
          <div className="toolbar"><button className="btn" onClick={() => setNcEdit(false)}>Cancel</button><div style={{ flex: 1 }} /><button className="btn gold" disabled={busy} onClick={saveContact}>Save &amp; notify FOS</button></div>
        </div> : <button className="btn sm" style={{ margin: '4px 0 10px' }} onClick={() => { setNcPhone(cur.new_phone || ''); setNcAddr(cur.new_address || ''); setNcEdit(true); }}>✏ {(cur.new_phone || cur.new_address) ? 'Update' : 'Add'} new address / phone</button>)}
        <div className="divider"></div>
        {cur.closed && <div className="glass card" style={{ background: '#f3f4f6', color: '#374151', fontSize: 13, padding: '8px 12px', marginBottom: 8 }}>
          🔒 This case has <b>closed for the month</b>{cur.close_date ? ` (on ${cur.close_date})` : ''} and is locked. It stays visible for reference; an admin can still make changes.</div>}
        <div className="toolbar">
          <div className={cx('chip', tab === 'call' && 'on')} onClick={() => setTab('call')}>📞 Log call</div>
          <div className={cx('chip', tab === 'pay' && 'on')} onClick={() => setTab('pay')}>💰 Record payment</div>
          <div className={cx('chip', tab === 'msg' && 'on')} onClick={() => setTab('msg')}>💬 Message</div>
          <div className={cx('chip', tab === 'hist' && 'on')} onClick={() => setTab('hist')}>🕘 History</div>
        </div>
        {tab === 'call' && <div className="glass card" style={{ background: 'rgba(0,0,0,.18)' }}>
          <div className="field"><label>Disposition</label>
            <select className="input" value={dispo} onChange={e => setDispo(e.target.value)}>{DISPOS_CALL.map(d => <option key={d}>{d}</option>)}</select></div>
          {isPTP && <div className="grid2" style={{ gridTemplateColumns: '1fr 1fr' }}>
            <div className="field"><label>PTP amount (₹)</label><input className="input" type="number" value={amt} onChange={e => setAmt(e.target.value)} /></div>
            <div className="field"><label>PTP date</label><input className="input" type="date" value={ptpDate} onChange={e => setPtpDate(e.target.value)} /></div></div>}
          {isPaid && <div className="grid2" style={{ gridTemplateColumns: isCC ? '1fr 1fr' : '1fr' }}>
            <div className="field"><label>Amount collected (₹)</label><input className="input" type="number" value={amt} onChange={e => setAmt(e.target.value)} /></div>
            {isCC && <div className="field"><label>Paid at (credit card)</label><select className="input" value={normStab} onChange={e => setNormStab(e.target.value)}><option>STAB</option><option>NORM</option><option>ROLLBACK</option></select></div>}</div>}
          {!isPTP && !isPaid && <div className="field"><label>Schedule next call (optional)</label><input className="input" type="date" value={followDate} onChange={e => setFollowDate(e.target.value)} /></div>}
          <div className="field"><label>Note</label><textarea className="input" value={callNote} onChange={e => setCallNote(e.target.value)} /></div>
          <button className="btn gold block" onClick={logCall} disabled={busy || cur.closed}>Save call</button>
        </div>}
        {tab === 'pay' && <div className="glass card" style={{ background: 'rgba(0,0,0,.18)' }}>
          <div className="grid2" style={{ gridTemplateColumns: '1fr 1fr' }}>
            <div className="field"><label>Amount (₹)</label><input className="input" type="number" value={payAmt} onChange={e => setPayAmt(e.target.value)} placeholder="0.00" /></div>
            <div className="field"><label>Mode</label><select className="input" value={payMode} onChange={e => setPayMode(e.target.value)}>
              <option>UPI</option><option>Cash</option><option>Bank Transfer</option><option>Cheque</option><option>BBPS</option></select></div></div>
          {isCC && <div className="field"><label>Paid at (credit card)</label>
            <select className="input" value={normStab} onChange={e => setNormStab(e.target.value)}><option>STAB</option><option>NORM</option><option>ROLLBACK</option></select></div>}
          <div className="field"><label>Note (optional)</label><input className="input" value={payNote} onChange={e => setPayNote(e.target.value)} /></div>
          <button className="btn gold block" onClick={recordPay} disabled={busy || !payAmt || cur.closed}>Save payment</button>
          {(() => {
            const cfg = window.__ssdCfg || {};
            const link = upiLink(cfg, cur, payAmt);
            if (!cfg.upi_vpa) return <div className="muted" style={{ fontSize: 11.5, marginTop: 10 }}>Set UPI_VPA in the backend .env to generate a UPI collect link + QR here.</div>;
            const waMsg = `Hello ${cur.customer_name || ''}, please pay ₹${Number(payAmt || cur.pending_amount || 0).toFixed(0)} towards your ${cur.bank || ''} account. Pay via UPI: ${link}`;
            const wa = cur.phone ? `https://wa.me/${String(cur.phone).replace(/[^0-9]/g, '')}?text=${encodeURIComponent(waMsg)}` : null;
            return <div style={{ marginTop: 14, borderTop: '1px solid rgba(255,255,255,.08)', paddingTop: 12 }}>
              <div style={{ fontWeight: 600, fontSize: 13.5, marginBottom: 8 }}>💳 UPI collect link</div>
              <div style={{ display: 'flex', gap: 12, alignItems: 'center', flexWrap: 'wrap' }}>
                <QR text={link} />
                <div style={{ flex: 1, minWidth: 160 }}>
                  <div className="muted" style={{ fontSize: 11.5, wordBreak: 'break-all', marginBottom: 8 }}>{link}</div>
                  <div className="toolbar" style={{ margin: 0 }}>
                    <button className="btn sm" onClick={() => { try { navigator.clipboard.writeText(link); toast('Link copied'); } catch { toast('Copy failed', 'err'); } }}>Copy link</button>
                    {wa && <a className="btn sm gold" href={wa} target="_blank" rel="noreferrer">Send on WhatsApp</a>}
                  </div>
                  <div className="muted" style={{ fontSize: 11, marginTop: 6 }}>Amount = {Number(payAmt || cur.pending_amount || 0).toFixed(0)}. Customer scans / taps to pay; then record the payment above.</div>
                </div>
              </div>
            </div>;
          })()}
        </div>}
        {tab === 'msg' && <div className="glass card" style={{ background: 'rgba(0,0,0,.18)' }}>
          <div className="field"><label>Template</label>
            <select className="input" value={tplId} onChange={e => pickTpl(e.target.value)}>
              <option value="">— pick a template —</option>
              {tpls.map(t => <option key={t.id} value={t.id}>{t.name} ({t.channel})</option>)}
            </select></div>
          {tpls.length === 0 && <div className="muted" style={{ fontSize: 12, marginBottom: 8 }}>No templates yet — an admin/manager can create them under Templates.</div>}
          <div className="field"><label>Message</label><textarea className="input" style={{ minHeight: 90 }} value={msg} onChange={e => setMsg(e.target.value)} placeholder="Type or pick a template…" /></div>
          <div className="toolbar" style={{ margin: 0 }}>
            {cur.phone && <button className="btn gold" onClick={waSend} disabled={!msg}>Send on WhatsApp</button>}
            <button className="btn" onClick={() => { try { navigator.clipboard.writeText(msg); toast('Copied'); } catch {} }} disabled={!msg}>Copy</button>
          </div>
        </div>}
        {tab === 'hist' && <div>
          {hist === null ? <Loader /> : hist.length === 0 ? <p className="muted">No activity yet.</p> :
            hist.map((h, i) => <div key={i} className="tl">
              <div className="ic">{TL_ICON[h.type] || '•'}</div>
              <div style={{ flex: 1 }}>
                <div style={{ fontWeight: 600, fontSize: 13.5 }}>{h.title}{Number(h.amount) > 0 ? ` · ${INR(h.amount)}` : ''}</div>
                {h.detail && <div className="muted" style={{ fontSize: 12.5 }}>{h.detail}</div>}
                <div className="muted" style={{ fontSize: 11.5 }}>{h.by ? `by ${h.by} · ` : ''}{h.at ? fmtDT(h.at) : ''}
                  {h.photo && <a href={h.photo} target="_blank" rel="noreferrer" style={{ marginLeft: 6 }}>📷 photo</a>}
                  {h.lat && <a href={`https://maps.google.com/?q=${h.lat},${h.lng}`} target="_blank" rel="noreferrer" style={{ marginLeft: 6 }}>📍 map</a>}
                  {h.ptp_date && <span style={{ marginLeft: 6, color: 'var(--gold-2)' }}>PTP {String(h.ptp_date).slice(0, 10)}</span>}</div>
                {h.note && h.note !== h.detail && <div style={{ fontSize: 12, marginTop: 2 }}>{h.note}</div>}
              </div>
            </div>)}
        </div>}
      </div>
    </div>
  );
}

const QUEUE_SEG = [['due', '⏰ Due now', 'due'], ['today', '✓ Contacted today', 'contacted_today'], ['upcoming', '📅 Upcoming', 'upcoming'], ['paid', '💰 Paid today', 'paid_today'], ['closed', '🔒 Closed', 'closed'], ['next', '🔜 Next month', 'next']];
function CallQueue() {
  const [data, setData] = useState(null); const [active, setActive] = useState(null); const [err, setErr] = useState('');
  const [seg, setSeg] = useState('due'); const [bank, setBank] = useState(''); const [bucket, setBucket] = useState(''); const [q, setQ] = useState(''); const [paidF, setPaidF] = useState('');
  const EMPTY = { due: [], contacted_today: [], upcoming: [], paid_today: [], closed: [], next: [], counts: { due: 0, contacted_today: 0, upcoming: 0, paid_today: 0, closed: 0, next: 0 } };
  const load = () => {
    const p = new URLSearchParams(); if (bank) p.set('bank', bank);
    api('/api/calls/queue' + (p.toString() ? '?' + p : ''))
      .then(d => { setData(d); setErr(''); })
      .catch(e => { setErr(e.message || 'Could not load queue'); setData(EMPTY); });
  };
  useEffect(() => { load(); }, [bank]);
  useDataChanged(load);
  if (!data) return <Loader />;
  if (err) return <div className="glass card" style={{ color: 'var(--warn)' }}>
    Couldn’t load the call queue: {err}. If you just updated the app, restart the server and reload. <button className="btn sm" style={{ marginLeft: 10 }} onClick={load}>Retry</button></div>;
  const key = (QUEUE_SEG.find(s => s[0] === seg) || QUEUE_SEG[0])[2];
  const all = [...data.due, ...data.contacted_today, ...data.upcoming];
  const buckets = Array.from(new Set(all.map(c => c.bucket || 'No bucket'))).sort((a, b) => bucketRank(a) - bucketRank(b));
  let list = data[key] || [];
  if (bucket) list = list.filter(c => (c.bucket || 'No bucket') === bucket);
  if (paidF) list = list.filter(c => (c.paid_status || 'UNPAID').toUpperCase() === paidF);
  if (q) { const s = q.toLowerCase(); list = list.filter(c => (c.customer_name || '').toLowerCase().includes(s) || (c.phone || '').includes(q) || (c.account_no || '').includes(q)); }
  const cardStyle = seg === 'paid' ? STATE_STYLE.paid : seg === 'today' ? STATE_STYLE.touched : null;
  return (
    <div>
      <RemindersBanner />
      <div className="toolbar">
        {QUEUE_SEG.map(([id, label, k]) => <div key={id} className={cx('chip', seg === id && 'on')} onClick={() => setSeg(id)}>{label} ({data.counts[k]})</div>)}
        <div style={{ flex: 1 }} />
        <input className="input" style={{ maxWidth: 210 }} placeholder="Search…" value={q} onChange={e => setQ(e.target.value)} />
        <button className="btn sm" onClick={load}>↻</button>
      </div>
      <div className="toolbar" style={{ marginTop: -2 }}>
        <select className="input" style={{ maxWidth: 130 }} value={bank} onChange={e => setBank(e.target.value)}>
          <option value="">All banks</option><option>ICICI</option><option>RBL</option><option>AXIS</option><option>BRBL</option></select>
        <span className="muted" style={{ fontSize: 12.5 }}>Status:</span>
        {[['', 'All'], ['PAID', 'Paid'], ['UNPAID', 'Unpaid'], ['PARTIAL', 'Partial']].map(([v, lbl]) =>
          <div key={v || 'all'} className={cx('chip', paidF === v && 'on')} onClick={() => setPaidF(v)}>{lbl}</div>)}
        <span className="muted" style={{ fontSize: 12.5 }}>Bucket:</span>
        <div className={cx('chip', !bucket && 'on')} onClick={() => setBucket('')}>All</div>
        {buckets.map(b => <div key={b} className={cx('chip', bucket === b && 'on')} onClick={() => setBucket(b)}>{b}</div>)}
      </div>
      {list.length === 0 ? <p className="muted">{seg === 'due' ? 'Nothing due — nicely done. Check Upcoming for scheduled callbacks.' : 'Nothing here.'}</p> :
        <div className="grid3">
          {list.map(c => <div key={c.id} className="glass card" style={cardStyle}>
            <div style={{ display: 'flex', justifyContent: 'space-between' }}><b>{c.customer_name}</b><PaidBadge s={c.paid_status} /></div>
            <div className="muted" style={{ fontSize: 13, margin: '4px 0' }}>{c.bank} · {c.bucket || ''} · cyc {c.cycle || '—'}</div>
            <div className="stat-row"><span className="k">Pending</span><b className="mono" style={{ color: 'var(--warn)' }}>{INR(c.pending_amount)}</b></div>
            {c.disposition && <div className="muted" style={{ fontSize: 12, marginTop: 4 }}>Last: {c.disposition}</div>}
            {c.follow_up_date && <div style={{ fontSize: 12, marginTop: 2, color: 'var(--gold-2)' }}>📅 {seg === 'upcoming' ? 'Scheduled' : 'Next'}: {c.follow_up_date}</div>}
            <div className="toolbar" style={{ margin: '10px 0 0' }}>
              <button className="btn sm gold" style={{ flex: 1 }} onClick={() => setActive(c)}>Open case ›</button>
              <ContactBtns phone={c.phone} />
            </div>
          </div>)}
        </div>}
      {active && <CaseDrawer c={active} onClose={() => setActive(null)} onChanged={load} />}
    </div>
  );
}

/* ============================== AI Assist ============================== */
function AIAssist({ user }) {
  const [msgs, setMsgs] = useState([{ who: 'bot', text: `Hi ${user.name.split(' ')[0]} — I'm your recovery assistant. Ask me to prioritise cases, draft a payment reminder, write a call script, or explain your numbers.` }]);
  const [input, setInput] = useState(''); const [busy, setBusy] = useState(false); const end = useRef(null);
  useEffect(() => { end.current && end.current.scrollIntoView({ behavior: 'smooth' }); }, [msgs]);
  const send = async () => {
    if (!input.trim() || busy) return; const prompt = input.trim();
    setMsgs(m => [...m, { who: 'me', text: prompt }]); setInput(''); setBusy(true);
    try { const r = await api('/api/ai', { method: 'POST', body: { prompt } });
      setMsgs(m => [...m, { who: 'bot', text: r.reply }]);
    } catch (e) { setMsgs(m => [...m, { who: 'bot', text: 'Error: ' + e.message }]); } finally { setBusy(false); }
  };
  const quick = ['Which cases should I prioritise today?', 'Draft a polite WhatsApp payment reminder', 'Write a firm but compliant call script', 'Summarise my current recovery numbers'];
  return (
    <div className="glass card" style={{ display: 'flex', flexDirection: 'column', height: 'calc(100vh - 150px)', minHeight: 420 }}>
      <div style={{ flex: 1, overflowY: 'auto', display: 'flex', flexDirection: 'column' }}>
        {msgs.map((m, i) => <div key={i} className={cx('ai-msg', m.who === 'me' ? 'me' : 'bot')}>{m.text}</div>)}
        {busy && <div className="ai-msg bot">…thinking</div>}
        <div ref={end} />
      </div>
      <div className="toolbar" style={{ margin: '10px 0 0' }}>{quick.map(q =>
        <div key={q} className="chip" onClick={() => setInput(q)}>{q}</div>)}</div>
      <div className="toolbar" style={{ margin: '8px 0 0' }}>
        <input className="input" value={input} onChange={e => setInput(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && send()} placeholder="Ask the assistant…" />
        <button className="btn gold" onClick={send} disabled={busy}>Send</button>
      </div>
    </div>
  );
}

/* ============================== PTP Tracker ============================== */
function PTPTracker() {
  const [data, setData] = useState(null); const [bank, setBank] = useState(''); const [drawer, setDrawer] = useState(null);
  const [err, setErr] = useState(''); const [search, setSearch] = useState('');
  const load = () => { const p = new URLSearchParams(); if (bank) p.set('bank', bank);
    setErr('');
    api('/api/calls/ptp-tracker' + (p.toString() ? '?' + p : '')).then(d => setData(d))
      .catch(e => { setErr(e.message || 'Could not load promises'); setData({ rows: [], counts: { overdue: 0, today: 0, upcoming: 0 } }); }); };
  useEffect(() => { load(); }, [bank]);
  if (!data) return <Loader />;
  if (err) return <div className="glass card" style={{ color: 'var(--bad)' }}>Couldn’t load the PTP tracker: {err}
    <button className="btn sm" style={{ marginLeft: 10 }} onClick={load}>Retry</button></div>;
  const groups = [['overdue', 'Overdue', 'unpaid'], ['today', 'Due today', 'partial'], ['upcoming', 'Upcoming', 'ptp']];
  const matchQ = (c) => { const q = search.trim().toLowerCase(); if (!q) return true;
    const digits = q.replace(/\D/g, ''); const fields = [c.customer_name, c.account_no, c.card_no, c.phone, c.alt_phone, c.pincode];
    return fields.some(v => v && String(v).toLowerCase().includes(q)) ||
      (digits && fields.some(v => v && String(v).replace(/\D/g, '').includes(digits))); };
  const visible = data.rows.filter(r => matchQ(r.case));
  return (
    <div>
      <div className="toolbar">
        <span className="badge unpaid">{data.counts.overdue} overdue</span>
        <span className="badge partial">{data.counts.today} due today</span>
        <span className="badge ptp">{data.counts.upcoming} upcoming</span>
        <input value={search} onChange={e => setSearch(e.target.value)} placeholder="🔍 Search name / account / card / phone"
          style={{ minWidth: 230, border: '1px solid var(--stroke-soft)', borderRadius: 10, padding: '7px 10px', fontSize: 13 }} />
        {search && <button className="btn ghost sm" onClick={() => setSearch('')}>✕</button>}
        <div style={{ flex: 1 }} />
        <select className="input" style={{ maxWidth: 130 }} value={bank} onChange={e => setBank(e.target.value)}>
          <option value="">All banks</option><option>ICICI</option><option>RBL</option><option>AXIS</option><option>BRBL</option></select>
        <button className="btn sm" onClick={load}>↻</button>
      </div>
      {visible.length === 0 ? <p className="muted">{search ? `No promises match "${search}".` : 'No active promises to pay right now.'}</p> :
        groups.map(([key, label, cls]) => {
          const rows = visible.filter(r => r.bucket === key);
          if (!rows.length) return null;
          return <div key={key} className="glass card" style={{ marginBottom: 14 }}>
            <div className="section-h"><h3 style={{ fontSize: 15 }}><span className={cx('badge', cls)}>{label}</span>
              <span className="muted" style={{ fontWeight: 400, fontSize: 13 }}> · {rows.length}</span></h3></div>
            <div className="tablewrap"><table>
              <thead><tr>
                <th>Customer</th><th>Bank · Product</th><th>Bucket</th><th>Cycle</th><th>Card / A/C</th>
                <th>Outstanding</th><th>Collected</th><th>Promised (PTP)</th><th>Promise date</th><th>Pending</th><th>Caller / FOS</th><th></th>
              </tr></thead>
              <tbody>{rows.map(r => { const c = r.case; return <tr key={c.id} style={{ cursor: 'pointer' }} onClick={() => setDrawer(c)}>
                <td><b>{c.customer_name}</b><div className="muted" style={{ fontSize: 12 }}>{c.phone || '—'}</div></td>
                <td>{c.bank}{c.product ? <div className="muted" style={{ fontSize: 12 }}>{c.product}</div> : null}</td>
                <td>{c.bucket || '—'}</td>
                <td className="mono">{c.cycle || '—'}</td>
                <td className="mono" style={{ fontSize: 12 }}>{c.card_no || c.account_no || '—'}</td>
                <td className="mono">{INR(c.enr || c.total_outstanding || c.funding_amount || 0)}</td>
                <td className="mono" style={{ color: 'var(--good)' }}>{INR(c.received_amount)}</td>
                <td className="mono">{r.ptp_amount != null ? INR(r.ptp_amount) : '—'}</td>
                <td style={{ color: key === 'overdue' ? 'var(--bad)' : 'var(--ink)', whiteSpace: 'nowrap' }}>{r.promised_date || '—'}</td>
                <td className="mono" style={{ color: 'var(--warn)' }}>{INR(c.pending_amount)}</td>
                <td style={{ fontSize: 12 }}>{c.caller_name || c.fos_name || '—'}</td>
                <td><button className="btn sm gold" onClick={e => { e.stopPropagation(); setDrawer(c); }}>Open ›</button></td>
              </tr>; })}</tbody></table></div>
          </div>;
        })}
      {drawer && <CaseDrawer c={drawer} onClose={() => setDrawer(null)} onChanged={load} />}
    </div>
  );
}

/* ============================== Records / Activity (admin) ============================== */
function RecordsView({ user }) {
  const [sum, setSum] = useState(null); const [items, setItems] = useState(null);
  const [kind, setKind] = useState('all'); const [drawer, setDrawer] = useState(null); const [flagOnly, setFlagOnly] = useState(false);
  const [opts, setOpts] = useState({ banks: [], branches: [], products: [], areas: [], employees: [] });
  const [f, setF] = useState({ bank: '', branch: '', product: '', area: '', emp: '' });
  const isManager = user && user.role === 'manager';
  useEffect(() => { api('/api/analytics/activity/filters').then(setOpts).catch(() => {}); }, []);
  const load = () => {
    api('/api/analytics/summary').then(setSum).catch(() => {});
    const qs = new URLSearchParams({ kind, limit: '250' });
    ['bank', 'branch', 'product', 'area', 'emp'].forEach(k => { if (f[k]) qs.set(k, f[k]); });
    api('/api/analytics/activity?' + qs.toString()).then(setItems).catch(() => setItems([]));
  };
  useEffect(() => { load(); }, [kind, f]);
  useDataChanged(load);
  const set = (k, v) => setF(p => ({ ...p, [k]: v }));
  const reset = () => setF({ bank: '', branch: '', product: '', area: '', emp: '' });
  const activeCount = Object.values(f).filter(Boolean).length;
  const icon = t => t === 'payment' ? '💰' : t === 'call' ? '📞' : '📍';
  const shown = (items || []).filter(r => !flagOnly || r.off_location);
  const flagged = (items || []).filter(r => r.off_location).length;
  const sel = { minWidth: 130, maxWidth: 180, height: 34, padding: '0 8px', fontSize: 13 };
  return (
    <div>
      {sum && <div className="kpis">
        <div className="glass kpi"><div className="l">Cases</div><div className="v">{sum.cases}</div>
          <div className="sub">{sum.users_total} staff accounts</div></div>
        <div className="glass kpi"><div className="l">Field visits</div><div className="v">{sum.visits}</div></div>
        <div className="glass kpi"><div className="l">Calls logged</div><div className="v">{sum.calls}</div>
          <div className="sub">{sum.payments} payments</div></div>
        <div className="glass kpi"><div className="l">Location pings</div><div className="v">{sum.location_pings}</div>
          <div className="sub">{sum.import_batches} uploads</div></div>
      </div>}
      <div className="glass card" style={{ padding: 10, marginBottom: 12 }}>
        <div className="toolbar" style={{ flexWrap: 'wrap', gap: 8 }}>
          <select className="input" style={sel} value={f.bank} onChange={e => set('bank', e.target.value)}>
            <option value="">All banks</option>{opts.banks.map(b => <option key={b} value={b}>{b}</option>)}</select>
          {!isManager && <select className="input" style={sel} value={f.branch} onChange={e => set('branch', e.target.value)}>
            <option value="">All branches</option>{opts.branches.map(b => <option key={b} value={b}>{b}</option>)}</select>}
          <select className="input" style={sel} value={f.product} onChange={e => set('product', e.target.value)}>
            <option value="">All products</option>{opts.products.map(p => <option key={p} value={p}>{p}</option>)}</select>
          <select className="input" style={sel} value={f.area} onChange={e => set('area', e.target.value)}>
            <option value="">All areas (code)</option>{opts.areas.map(a => <option key={a} value={a}>{a}</option>)}</select>
          <select className="input" style={sel} value={f.emp} onChange={e => set('emp', e.target.value)}>
            <option value="">All FOS &amp; callers</option>
            {opts.employees.map(e => <option key={e.id} value={e.id}>{e.name} · {e.role === 'fos' ? 'FOS' : 'Caller'}</option>)}</select>
          {activeCount > 0 && <button className="btn sm" onClick={reset}>✕ Clear ({activeCount})</button>}
        </div>
      </div>
      <div className="toolbar">
        {[['all', 'All activity'], ['visits', 'Field visits'], ['calls', 'Calls'], ['payments', 'Payments']].map(([k, l]) =>
          <div key={k} className={cx('chip', kind === k && 'on')} onClick={() => { setKind(k); setFlagOnly(false); }}>{l}</div>)}
        <div className={cx('chip', flagOnly && 'on')} onClick={() => setFlagOnly(v => !v)}>⚠ Off-location{flagged ? ` (${flagged})` : ''}</div>
        <div style={{ flex: 1 }} />
        <span className="muted" style={{ fontSize: 12, marginRight: 8 }}>{shown.length} record{shown.length === 1 ? '' : 's'}</span>
        <button className="btn sm" onClick={load}>↻ Refresh</button>
      </div>
      {!items ? <Loader /> : shown.length === 0 ? <p className="muted">{flagOnly ? 'No off-location visits — all clear.' : 'No activity matches these filters.'}</p> :
        <div className="glass card" style={{ padding: 6 }}>
          <div className="tablewrap"><table>
            <thead><tr><th></th><th>When</th><th>Customer</th><th>Bank</th><th>Product</th><th>Area</th><th>Branch</th><th>By</th><th>Detail</th><th>Amount</th><th></th></tr></thead>
            <tbody>{shown.map((r, i) => <tr key={i} style={r.off_location ? { background: 'rgba(240,119,107,.08)' } : null}>
              <td>{icon(r.type)}</td>
              <td className="muted" style={{ fontSize: 12, whiteSpace: 'nowrap' }}>{fmtDT(r.at)}</td>
              <td><b>{r.customer || '—'}</b></td><td>{r.bank || '—'}</td>
              <td className="muted">{r.product || '—'}</td><td className="muted">{r.area || '—'}</td><td className="muted">{r.branch || '—'}</td>
              <td>{r.by || '—'}</td>
              <td className="muted">{r.detail || '—'}
                {r.photo && <a href={r.photo} target="_blank" rel="noreferrer" style={{ marginLeft: 6 }}>📷</a>}
                {r.lat && <a href={`https://maps.google.com/?q=${r.lat},${r.lng}`} target="_blank" rel="noreferrer" style={{ marginLeft: 6 }}>📍</a>}
                {r.note && <div style={{ fontSize: 11.5 }}>{r.note}</div>}</td>
              <td className="mono">{r.amount > 0 ? INR(r.amount) : '—'}</td>
              <td><button className="btn sm" onClick={() => setDrawer({ id: r.case_id })}>Account ›</button></td>
            </tr>)}</tbody></table></div>
        </div>}
      {drawer && <CaseDrawer c={drawer} onClose={() => setDrawer(null)} onChanged={load} />}
    </div>
  );
}

/* ============================== Audit Log (admin / manager / head office) ============================== */
const AUDIT_ICON = {
  reassign: '🔀', deallocate: '➖', transfer: '🔁', edit: '✏️', cell_edit: '⌨️',
  paid: '✅', unpaid: '↩️', payment: '💰', visit: '📍', call: '📞',
  delete: '🗑️', restore: '♻️', escalate: '🚩', deescalate: '🏳️', import: '📥', login: '🔑',
};
function AuditLogView({ user }) {
  const [opts, setOpts] = useState({ branches: [], banks: [], products: [], actions: [], roles: [], employees: [] });
  const [data, setData] = useState(null);
  const [f, setF] = useState({ role: '', emp: '', action: '', branch: '', bank: '', product: '', days: '', q: '' });
  const [busy, setBusy] = useState(false); const [logSel, setLogSel] = useState(null);
  useEffect(() => { api('/api/audit/filters').then(setOpts).catch(() => {}); }, []);
  const load = useCallback(() => {
    setBusy(true);
    const qs = new URLSearchParams({ limit: '300' });
    Object.entries(f).forEach(([k, v]) => { if (v) qs.set(k, v); });
    api('/api/audit?' + qs.toString()).then(setData).catch(() => setData({ items: [], total: 0 })).finally(() => setBusy(false));
  }, [f]);
  useEffect(() => { const t = setTimeout(load, 200); return () => clearTimeout(t); }, [load]);
  useDataChanged(load);
  const set = (k, v) => setF(p => ({ ...p, [k]: v }));
  const reset = () => setF({ role: '', emp: '', action: '', branch: '', bank: '', product: '', days: '', q: '' });
  const active = Object.values(f).filter(Boolean).length;
  const sel = { minWidth: 120, maxWidth: 190, height: 34, padding: '0 8px', fontSize: 13 };
  const when = (t) => fmtDT(t);
  const items = (data && data.items) || [];
  return (
    <div>
      <div className="section-h"><h2 style={{ margin: 0 }}>Audit Log</h2>
        <span className="muted" style={{ fontSize: 13 }}>{data ? `${data.total} tracked action${data.total === 1 ? '' : 's'}` : '…'}</span></div>
      <p className="muted" style={{ fontSize: 13, marginTop: -4 }}>Every change, re-allocation, payment, visit, call and edit — with who did it. {user.role === 'manager' ? 'Scoped to your branch.' : ''}</p>
      <div className="glass card" style={{ padding: 10, marginBottom: 12 }}>
        <div className="toolbar" style={{ flexWrap: 'wrap', gap: 8 }}>
          <input className="input" style={{ maxWidth: 220 }} placeholder="Search text / person / value" value={f.q} onChange={e => set('q', e.target.value)} />
          <select className="input" style={sel} value={f.role} onChange={e => set('role', e.target.value)}>
            <option value="">All roles</option>{opts.roles.map(r => <option key={r} value={r}>{r}</option>)}</select>
          <select className="input" style={sel} value={f.emp} onChange={e => set('emp', e.target.value)}>
            <option value="">All employees</option>{opts.employees.map(e => <option key={e.id} value={e.id}>{e.name} ({e.role})</option>)}</select>
          <select className="input" style={sel} value={f.action} onChange={e => set('action', e.target.value)}>
            <option value="">All actions</option>{opts.actions.map(a => <option key={a} value={a}>{a}</option>)}</select>
          {user.role !== 'manager' && <select className="input" style={sel} value={f.branch} onChange={e => set('branch', e.target.value)}>
            <option value="">All branches</option>{opts.branches.map(b => <option key={b} value={b}>{b}</option>)}</select>}
          <select className="input" style={sel} value={f.bank} onChange={e => set('bank', e.target.value)}>
            <option value="">All banks</option>{opts.banks.map(b => <option key={b} value={b}>{b}</option>)}</select>
          <select className="input" style={sel} value={f.product} onChange={e => set('product', e.target.value)}>
            <option value="">All products</option>{opts.products.map(p => <option key={p} value={p}>{p}</option>)}</select>
          <select className="input" style={sel} value={f.days} onChange={e => set('days', e.target.value)}>
            <option value="">Any time</option><option value="1">Today</option><option value="7">Last 7 days</option><option value="30">Last 30 days</option></select>
          {active > 0 && <button className="btn ghost" onClick={reset}>Clear ({active})</button>}
        </div>
      </div>
      {!data ? <Loader /> : items.length === 0 ? <div className="glass card muted" style={{ padding: 24, textAlign: 'center' }}>No matching activity.</div> : (
        <div className="glass card" style={{ padding: 6 }}>
          <div className="tablewrap"><table>
            <thead><tr><th>When</th><th>Who</th><th>Action</th><th>Case</th><th>Field</th><th>Change</th><th>Detail</th><th>Branch</th></tr></thead>
            <tbody>{items.map(r => <tr key={r.id} style={{ cursor: 'pointer' }} onClick={() => setLogSel(r)} title="Open full log & case details">
              <td className="muted" style={{ fontSize: 12, whiteSpace: 'nowrap' }}>{when(r.at)}</td>
              <td><b>{r.actor || '—'}</b><div className="muted" style={{ fontSize: 11 }}>{r.role}</div></td>
              <td style={{ whiteSpace: 'nowrap' }}>{AUDIT_ICON[r.action] || '•'} {r.action}</td>
              <td>{r.customer ? <span>{r.customer}<div className="muted" style={{ fontSize: 11 }}>#{r.case_id}</div></span> : (r.case_id ? '#' + r.case_id : '—')}</td>
              <td className="muted" style={{ fontSize: 12 }}>{r.field || '—'}</td>
              <td style={{ fontSize: 12 }}>{(r.old || r.new) ? <span><span className="muted">{r.old ?? '∅'}</span> → <b>{r.new ?? '∅'}</b></span> : '—'}</td>
              <td style={{ fontSize: 12 }}>{r.detail || '—'}</td>
              <td className="muted" style={{ fontSize: 12 }}>{r.branch || '—'}</td></tr>)}
            </tbody></table></div>
          {data.total > items.length && <p className="muted" style={{ padding: '8px 12px', fontSize: 12 }}>Showing latest {items.length} of {data.total}. Narrow with filters to see older entries.</p>}
        </div>
      )}
      {logSel && <AuditDetailModal row={logSel} onClose={() => setLogSel(null)} />}
    </div>
  );
}

/* Popup for one audit entry — who did what & when, plus the linked case's details. */
function AuditDetailModal({ row, onClose }) {
  const [c, setC] = useState(null); const [err, setErr] = useState('');
  useEffect(() => {
    if (row.case_id) api('/api/cases/' + row.case_id).then(setC)
      .catch(() => setErr('Case details unavailable (it may be closed or removed).'));
  }, [row.case_id]);
  const money = v => v == null || v === '' ? '—' : '₹' + Math.round(Number(v) || 0).toLocaleString('en-IN');
  const line = (k, v) => <div className="stat-row"><span className="k">{k}</span><b>{v == null || v === '' ? '—' : v}</b></div>;
  return (
    <div className="modal-bg" onClick={onClose}>
      <div className="modal glass" onClick={e => e.stopPropagation()} style={{ maxWidth: 560 }}>
        <div className="section-h"><h3>{AUDIT_ICON[row.action] || '•'} {row.action} — log detail</h3>
          <button className="btn ghost sm" onClick={onClose}>✕</button></div>
        <div className="glass card" style={{ padding: 12, marginBottom: 10 }}>
          <div style={{ fontWeight: 600, marginBottom: 6 }}>Who &amp; when</div>
          {line('Done by', (row.actor || '—') + (row.role ? ' · ' + roleName(row.role) : ''))}
          {line('When (IST)', fmtDT(row.at))}
          {line('Action', row.action)}
          {row.field && line('Field', row.field)}
          {(row.old || row.new) && <div className="stat-row"><span className="k">Change</span>
            <b><span className="muted">{row.old ?? '∅'}</span> → {row.new ?? '∅'}</b></div>}
          {row.detail && line('Detail', row.detail)}
          {row.branch && line('Branch', row.branch)}
          {(row.bank || row.product) && line('Portfolio', [row.bank, row.product].filter(Boolean).join(' · '))}
        </div>
        {row.case_id && <div className="glass card" style={{ padding: 12 }}>
          <div style={{ fontWeight: 600, marginBottom: 6 }}>Case #{row.case_id}</div>
          {err ? <div className="muted" style={{ fontSize: 12.5 }}>{err}</div> : !c ? <Loader /> : <>
            {line('Customer', c.customer_name)}
            {line('Account / Card', c.account_no || c.card_no)}
            {line('Bank / Product', [c.bank, c.product, c.segment].filter(Boolean).join(' · '))}
            {line('Bucket / Cycle', (c.bucket || '—') + ' · cyc ' + (c.cycle || '—'))}
            {line('Status', (c.status || '—') + ' · ' + (c.paid_status || '—'))}
            {line('Funded / Received / Pending', money(c.funding_amount) + ' / ' + money(c.received_amount) + ' / ' + money(c.pending_amount))}
            {line('Caller', c.assigned_caller_name || c.caller_name)}
            {line('Field officer', c.assigned_fos_name || c.fos_name)}
            {line('Phone', c.phone)}
          </>}
        </div>}
      </div>
    </div>
  );
}

/* ============================== Monthly Archive (admin only) ============================== */
function ArchiveView({ user }) {
  const [periods, setPeriods] = useState(null);
  const [period, setPeriod] = useState('');
  const [data, setData] = useState(null);
  const [cycle, setCycle] = useState(null);
  const [f, setF] = useState({ closing_type: '', product: '', cyc: '' });
  const money = v => '₹' + Math.round(Number(v) || 0).toLocaleString('en-IN');
  useEffect(() => { api('/api/archive/periods').then(ps => { setPeriods(ps); if (ps.length && !period) setPeriod(ps[0].period); }).catch(() => setPeriods([])); }, []);
  useEffect(() => { if (!period) return; setCycle(null); api('/api/archive/cycle-report?period=' + period).then(setCycle).catch(() => setCycle(null)); }, [period]);
  useEffect(() => {
    if (!period) return;
    const qs = new URLSearchParams({ period });
    if (f.closing_type) qs.set('closing_type', f.closing_type);
    if (f.product) qs.set('product', f.product);
    if (f.cyc) qs.set('cyc', f.cyc);
    setData(null);
    api('/api/archive/summary?' + qs.toString()).then(setData).catch(() => setData(null));
  }, [period, f]);
  const pretty = p => { if (!p) return ''; const [y, m] = p.split('-'); return MONTHS[Number(m) - 1] + ' ' + y; };
  const set = (k, v) => setF(s => ({ ...s, [k]: v }));
  const t = data && data.totals;
  const sel = { minWidth: 130, height: 34, padding: '0 8px', fontSize: 13 };
  return (
    <div>
      <div className="section-h"><h2 style={{ margin: 0 }}>Monthly Archive</h2>
        <span className="muted" style={{ fontSize: 13 }}>Admin-only history. Closed cases live here by month.</span></div>
      <p className="muted" style={{ fontSize: 13, marginTop: -4 }}>Pick a month to see everything that ran — product-wise numbers, how it closed (cycle / month-end / due date), and per-staff performance. Closed cases have already left the field/caller views.</p>

      {!periods ? <Loader /> : periods.length === 0 ? <div className="glass card muted" style={{ padding: 24, textAlign: 'center' }}>No months uploaded yet.</div> : (<>
        <div className="glass card" style={{ padding: 10, marginBottom: 12 }}>
          <div className="toolbar" style={{ flexWrap: 'wrap', gap: 8 }}>
            <select className="input" style={sel} value={period} onChange={e => setPeriod(e.target.value)}>
              {periods.map(p => <option key={p.period} value={p.period}>{pretty(p.period)} — {p.total} cases ({p.closed} closed)</option>)}</select>
            <select className="input" style={sel} value={f.closing_type} onChange={e => set('closing_type', e.target.value)}>
              <option value="">All closing types</option><option value="cyc">Cycle-wise</option><option value="month_end">Month-end</option><option value="due_date">Due-date</option></select>
            {data && <select className="input" style={sel} value={f.product} onChange={e => set('product', e.target.value)}>
              <option value="">All products</option>{[...new Set(data.products.map(p => p.product))].map(p => <option key={p} value={p}>{p}</option>)}</select>}
            <input className="input" style={{ ...sel, minWidth: 90 }} type="number" min="1" max="31" placeholder="Cycle day" value={f.cyc} onChange={e => set('cyc', e.target.value)} />
            {(f.closing_type || f.product || f.cyc) && <button className="btn ghost" onClick={() => setF({ closing_type: '', product: '', cyc: '' })}>Clear</button>}
          </div>
        </div>

        {!data ? <Loader /> : (<>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill,minmax(150px,1fr))', gap: 12, marginBottom: 14 }}>
            <StatCard label="Cases" value={t.cases} />
            <StatCard label="Closed / Open" value={`${t.closed} / ${t.open}`} />
            <StatCard label="Paid" value={t.paid} valueColor="var(--good)" />
            <StatCard label="Recovered" value={money(t.received)} valueColor="var(--good)" />
            <StatCard label="Pending" value={money(t.pending)} valueColor="var(--warn)" />
          </div>

          <div className="section-h"><h3 style={{ fontSize: 14, margin: '4px 0' }}>Product-wise</h3></div>
          <div className="glass card" style={{ padding: 6, marginBottom: 14 }}>
            <div className="tablewrap"><table>
              <thead><tr><th>Bank</th><th>Product</th><th>Closing</th><th>Closes on</th><th>Cases</th><th>Paid</th><th>Recovered</th><th>Pending</th></tr></thead>
              <tbody>{data.products.map((p, i) => <tr key={i}>
                <td>{p.bank}</td><td><b>{p.product}</b></td>
                <td><span className="badge allocated">{p.closing_type || '—'}</span></td>
                <td className="muted" style={{ fontSize: 12 }}>{(p.close_days || []).join(', ') || '—'}</td>
                <td>{p.cases}</td><td>{p.paid}</td>
                <td className="mono" style={{ color: 'var(--good)' }}>{money(p.received)}</td>
                <td className="mono" style={{ color: 'var(--warn)' }}>{money(p.pending)}</td></tr>)}
              </tbody></table></div>
          </div>

          <div className="grid2" style={{ gridTemplateColumns: '1fr 1fr', gap: 14, alignItems: 'start' }}>
            <div>
              <div className="section-h"><h3 style={{ fontSize: 14, margin: '4px 0' }}>Closing breakdown</h3></div>
              <div className="glass card" style={{ padding: 6 }}>
                <div className="tablewrap"><table><thead><tr><th>Closes on</th><th>Cases</th><th>Recovered</th></tr></thead>
                  <tbody>{data.by_close.map((b, i) => <tr key={i}><td className="muted" style={{ fontSize: 12 }}>{b.closes}</td><td>{b.cases}</td>
                    <td className="mono" style={{ color: 'var(--good)' }}>{money(b.received)}</td></tr>)}</tbody></table></div>
              </div>
            </div>
            <div>
              <div className="section-h"><h3 style={{ fontSize: 14, margin: '4px 0' }}>Performance</h3></div>
              <div className="glass card" style={{ padding: 6 }}>
                <div className="tablewrap"><table><thead><tr><th>Staff</th><th>Role</th><th>Cases</th><th>Paid</th><th>Recovered</th></tr></thead>
                  <tbody>
                    {data.performance.callers.map(s => <tr key={'c' + s.id}><td><b>{s.name}</b></td><td className="muted">Caller</td><td>{s.cases}</td><td>{s.paid}</td><td className="mono" style={{ color: 'var(--good)' }}>{money(s.received)}</td></tr>)}
                    {data.performance.fos.map(s => <tr key={'f' + s.id}><td><b>{s.name}</b></td><td className="muted">FOS</td><td>{s.cases}</td><td>{s.paid}</td><td className="mono" style={{ color: 'var(--good)' }}>{money(s.received)}</td></tr>)}
                  </tbody></table></div>
              </div>
            </div>
          </div>

          {cycle && (cycle.cycle_days.length > 0 || cycle.by_type.length > 0) && <div style={{ marginTop: 16 }}>
            <div className="section-h"><h3 style={{ fontSize: 14, margin: '4px 0' }}>Cycle-wise closing analysis</h3></div>
            <div className="grid2" style={{ gridTemplateColumns: '1.4fr 1fr', gap: 14, alignItems: 'start' }}>
              <div className="glass card" style={{ padding: 6 }}>
                <div className="muted" style={{ fontSize: 12, padding: '4px 8px' }}>Cases closing on each cycle date</div>
                <div className="tablewrap"><table><thead><tr><th>Cycle day</th><th>Closes on</th><th>Cases</th><th>Closed</th><th>Open</th><th>Recovered</th><th>Products</th></tr></thead>
                  <tbody>{cycle.cycle_days.map(d => <tr key={d.day}>
                    <td><b>CYC {d.day}</b></td><td className="muted" style={{ fontSize: 12 }}>{d.close_date}</td>
                    <td>{d.cases}</td><td>{d.closed}</td><td>{d.open}</td>
                    <td className="mono" style={{ color: 'var(--good)' }}>{money(d.received)}</td>
                    <td className="muted" style={{ fontSize: 11 }}>{(d.products || []).join(', ')}</td></tr>)}
                    {cycle.cycle_days.length === 0 && <tr><td colSpan="7" className="muted" style={{ padding: 12 }}>No cycle-wise products this month.</td></tr>}
                  </tbody></table></div>
              </div>
              <div className="glass card" style={{ padding: 6 }}>
                <div className="muted" style={{ fontSize: 12, padding: '4px 8px' }}>By closing type</div>
                <div className="tablewrap"><table><thead><tr><th>Closing</th><th>Cases</th><th>Closed</th><th>Recovered</th></tr></thead>
                  <tbody>{cycle.by_type.map(b => <tr key={b.closing_type}>
                    <td><span className="badge allocated">{b.closing_type}</span></td><td>{b.cases}</td><td>{b.closed}</td>
                    <td className="mono" style={{ color: 'var(--good)' }}>{money(b.received)}</td></tr>)}</tbody></table></div>
              </div>
            </div>
          </div>}
        </>)}
      </>)}
    </div>
  );
}

/* ============================== Leave management ============================== */
const LEAVE_TYPES = ['Casual', 'Sick', 'Earned', 'Unpaid'];
function LeaveView({ user }) {
  const [bal, setBal] = useState(null); const [mine, setMine] = useState(null);
  const [team, setTeam] = useState(null); const [ins, setIns] = useState(null);
  // HR + head office approve leave org-wide, alongside admin/manager.
  const isMgr = ['admin', 'manager', 'hr', 'headoffice'].includes(user.role);
  const [ltype, setLtype] = useState('Casual'); const [s1, setS1] = useState(''); const [s2, setS2] = useState('');
  const [reason, setReason] = useState(''); const [busy, setBusy] = useState(false);
  const load = () => {
    api('/api/leaves/balance').then(setBal).catch(() => {});
    api('/api/leaves?scope=mine').then(setMine).catch(() => setMine([]));
    if (isMgr) { api('/api/leaves?scope=team&status=pending').then(setTeam).catch(() => setTeam([])); api('/api/leaves/insights').then(setIns).catch(() => {}); }
  };
  useEffect(() => { load(); }, []);
  const apply = async () => {
    if (!s1 || !s2) return; setBusy(true);
    try { await api('/api/leaves', { method: 'POST', body: { leave_type: ltype, start_date: s1, end_date: s2, reason } });
      toast('Leave applied.'); setReason(''); setS1(''); setS2(''); load();
    } catch (e) { toast(e.message, 'err'); } finally { setBusy(false); }
  };
  const decide = async (id, d) => { try { await api(`/api/leaves/${id}/${d}`, { method: 'POST' }); toast(d === 'approve' ? 'Approved' : 'Rejected'); load(); } catch (e) { toast(e.message, 'err'); } };
  const stBadge = s => s === 'approved' ? 'paid' : s === 'rejected' ? 'unpaid' : 'partial';
  const curBal = bal && bal.find(x => x.type === ltype);
  return (
    <div>
      {isMgr && ins && <div className="kpis">
        <div className="glass kpi"><div className="l">Pending approvals</div><div className="v">{ins.pending}</div></div>
        <div className="glass kpi"><div className="l">On leave today</div><div className="v">{ins.on_leave_today.length}</div>
          <div className="sub">{ins.on_leave_today.map(x => x.name).join(', ') || '—'}</div></div>
        <div className="glass kpi"><div className="l">Upcoming (7 days)</div><div className="v">{ins.upcoming_week}</div></div>
      </div>}
      {isMgr && team && <div className="glass card" style={{ marginBottom: 16 }}>
        <div className="section-h"><h3 style={{ fontSize: 15 }}>Pending approvals ({team.length})</h3></div>
        {team.length === 0 ? <p className="muted">Nothing to approve.</p> :
          <div className="tablewrap"><table>
            <thead><tr><th>Who</th><th>Type</th><th>Dates</th><th>Days</th><th>Reason</th><th></th></tr></thead>
            <tbody>{team.map(l => <tr key={l.id}>
              <td><b>{l.user_name}</b><div className="muted" style={{ fontSize: 11.5 }}>{l.user_branch}</div></td>
              <td>{l.leave_type}</td><td className="muted">{l.start_date} → {l.end_date}</td><td className="mono">{l.days}</td>
              <td className="muted">{l.reason || '—'}</td>
              <td style={{ whiteSpace: 'nowrap' }}><button className="btn sm gold" onClick={() => decide(l.id, 'approve')}>Approve</button>{' '}<button className="btn sm" onClick={() => decide(l.id, 'reject')}>Reject</button></td>
            </tr>)}</tbody></table></div>}
      </div>}
      <div className="grid2" style={{ gridTemplateColumns: '1.2fr 1fr' }}>
        <div className="glass card">
          <div className="section-h"><h3 style={{ fontSize: 15 }}>Apply for leave</h3></div>
          <div className="grid2" style={{ gridTemplateColumns: '1fr 1fr' }}>
            <div className="field"><label>Type</label><select className="input" value={ltype} onChange={e => setLtype(e.target.value)}>{LEAVE_TYPES.map(t => <option key={t}>{t}</option>)}</select></div>
            <div className="field"><label>Balance</label><div className="input" style={{ display: 'flex', alignItems: 'center' }}>{curBal ? (curBal.remaining != null ? `${curBal.remaining} of ${curBal.allowance} left` : 'no limit') : '—'}</div></div>
            <div className="field"><label>From</label><input className="input" type="date" value={s1} onChange={e => setS1(e.target.value)} /></div>
            <div className="field"><label>To</label><input className="input" type="date" value={s2} onChange={e => setS2(e.target.value)} /></div>
          </div>
          <div className="field"><label>Reason</label><textarea className="input" value={reason} onChange={e => setReason(e.target.value)} /></div>
          <button className="btn gold block" onClick={apply} disabled={busy || !s1 || !s2}>Apply for leave</button>
        </div>
        <div className="glass card">
          <div className="section-h"><h3 style={{ fontSize: 15 }}>My balances (this year)</h3></div>
          {!bal ? <Loader /> : bal.map(b => <div key={b.type} className="stat-row">
            <span className="k">{b.type}</span>
            <b>{b.remaining != null ? `${b.remaining} left` : 'no limit'} <span className="muted" style={{ fontWeight: 400, fontSize: 12 }}>({b.used} used{b.pending ? `, ${b.pending} pending` : ''})</span></b>
          </div>)}
        </div>
      </div>
      <div className="glass card" style={{ marginTop: 16 }}>
        <div className="section-h"><h3 style={{ fontSize: 15 }}>My requests</h3></div>
        {!mine ? <Loader /> : mine.length === 0 ? <p className="muted">No leave requests yet.</p> :
          <div className="tablewrap"><table>
            <thead><tr><th>Type</th><th>Dates</th><th>Days</th><th>Status</th><th>Reason</th></tr></thead>
            <tbody>{mine.map(l => <tr key={l.id}>
              <td>{l.leave_type}</td><td className="muted">{l.start_date} → {l.end_date}</td><td className="mono">{l.days}</td>
              <td><span className={cx('badge', stBadge(l.status))}>{l.status}</span></td><td className="muted">{l.reason || '—'}</td>
            </tr>)}</tbody></table></div>}
      </div>
    </div>
  );
}

/* ============================== Devices (admin/manager) ============================== */
function DevicesView() {
  const [items, setItems] = useState(null);
  const load = () => api('/api/devices').then(setItems).catch(() => setItems([]));
  useEffect(() => { load(); }, []);
  const act = async (id, kind) => {
    try {
      if (kind === 'delete') await api('/api/devices/' + id, { method: 'DELETE' });
      else await api('/api/devices/' + id + '/' + kind, { method: 'POST' });
      toast(kind === 'approve' ? 'Device approved' : kind === 'revoke' ? 'Device revoked' : 'Device removed'); load();
    } catch (e) { toast(e.message, 'err'); }
  };
  if (!items) return <Loader />;
  const pending = items.filter(d => !d.approved); const approved = items.filter(d => d.approved);
  const tbl = (list, isPending) => <div className="glass card" style={{ padding: 6, marginBottom: 14 }}>
    <div className="tablewrap"><table>
      <thead><tr><th>User</th><th>Branch</th><th>Device</th><th>Last seen</th><th></th></tr></thead>
      <tbody>{list.map(d => <tr key={d.id}>
        <td><b>{d.user_name || ('#' + d.user_id)}</b><div className="muted" style={{ fontSize: 11.5 }}>{d.label}</div></td>
        <td>{d.user_branch || '—'}</td>
        <td className="mono" style={{ fontSize: 12 }}>{d.device_id}</td>
        <td className="muted" style={{ fontSize: 12, whiteSpace: 'nowrap' }}>{fmtDT(d.last_seen)}</td>
        <td style={{ whiteSpace: 'nowrap' }}>
          {isPending
            ? <><button className="btn sm gold" onClick={() => act(d.id, 'approve')}>Approve</button>{' '}<button className="btn sm" onClick={() => act(d.id, 'delete')}>Reject</button></>
            : <><button className="btn sm" onClick={() => act(d.id, 'revoke')}>Revoke</button>{' '}<button className="btn sm" onClick={() => act(d.id, 'delete')}>Remove</button></>}
        </td>
      </tr>)}</tbody></table></div></div>;
  return (
    <div>
      <div className="toolbar"><span className="muted">Approve the devices your staff sign in from. A new device is blocked until you approve it.</span>
        <div style={{ flex: 1 }} /><button className="btn sm" onClick={load}>↻ Refresh</button></div>
      <div className="section-h"><h3 style={{ fontSize: 15 }}><span className="badge unpaid">{pending.length}</span> Pending approval</h3></div>
      {pending.length ? tbl(pending, true) : <p className="muted">No devices awaiting approval.</p>}
      <div className="section-h" style={{ marginTop: 10 }}><h3 style={{ fontSize: 15 }}><span className="badge paid">{approved.length}</span> Approved devices</h3></div>
      {approved.length ? tbl(approved, false) : <p className="muted">No approved devices yet.</p>}
    </div>
  );
}

/* ============================== Message templates ============================== */
function renderTemplate(body, c) {
  const map = {
    name: c.customer_name || '', customer: c.customer_name || '', bank: c.bank || '',
    account: c.account_no || '', pending: '₹' + Math.round(c.pending_amount || 0),
    amount: '₹' + Math.round(c.pending_amount || 0), ptp_date: c.follow_up_date || '',
    bucket: c.bucket || '', phone: c.phone || '',
  };
  return (body || '').replace(/\{(\w+)\}/g, (m, k) => (k in map ? map[k] : m));
}
function TemplateModal({ editing, onClose, onDone }) {
  const [f, setF] = useState(editing || { name: '', channel: 'whatsapp', body: '' });
  const [busy, setBusy] = useState(false); const [err, setErr] = useState('');
  const save = async () => { setErr(''); setBusy(true);
    try { if (editing) await api('/api/templates/' + editing.id, { method: 'PATCH', body: f });
      else await api('/api/templates', { method: 'POST', body: f });
      toast('Saved.'); onDone();
    } catch (e) { setErr(e.message); } finally { setBusy(false); } };
  return (
    <div className="modal-bg" onClick={onClose}>
      <div className="modal glass" onClick={e => e.stopPropagation()}>
        <div className="section-h"><h3>{editing ? 'Edit' : 'New'} template</h3><button className="btn ghost sm" onClick={onClose}>✕</button></div>
        <div className="grid2" style={{ gridTemplateColumns: '2fr 1fr' }}>
          <div className="field"><label>Name</label><input className="input" value={f.name} onChange={e => setF({ ...f, name: e.target.value })} /></div>
          <div className="field"><label>Channel</label><select className="input" value={f.channel} onChange={e => setF({ ...f, channel: e.target.value })}><option>whatsapp</option><option>sms</option><option>email</option></select></div>
        </div>
        <div className="field"><label>Message</label><textarea className="input" style={{ minHeight: 120 }} value={f.body} onChange={e => setF({ ...f, body: e.target.value })} placeholder="Hi {name}, your {bank} account has {pending} pending. Please pay." /></div>
        <div className="muted" style={{ fontSize: 11.5 }}>Merge fields: {'{name} {bank} {pending} {account} {ptp_date} {bucket}'}</div>
        {err && <div style={{ color: 'var(--bad)', fontSize: 13, marginTop: 6 }}>{err}</div>}
        <button className="btn gold block" onClick={save} disabled={busy || !f.name || !f.body} style={{ marginTop: 10 }}>Save template</button>
      </div>
    </div>
  );
}
function TemplatesView() {
  const [items, setItems] = useState(null); const [modal, setModal] = useState(false); const [editing, setEditing] = useState(null);
  const load = () => api('/api/templates').then(setItems).catch(() => setItems([]));
  useEffect(() => { load(); }, []);
  const del = async (id) => { try { await api('/api/templates/' + id, { method: 'DELETE' }); toast('Deleted'); load(); } catch (e) { toast(e.message, 'err'); } };
  return (
    <div>
      <div className="toolbar"><span className="muted">Reusable WhatsApp/SMS messages with merge fields — used from any case and in bulk campaigns.</span>
        <div style={{ flex: 1 }} /><button className="btn gold" onClick={() => { setEditing(null); setModal(true); }}>+ New template</button></div>
      {!items ? <Loader /> : items.length === 0 ? <p className="muted">No templates yet. Create one to send quick reminders.</p> :
        <div className="grid2">{items.map(t => <div key={t.id} className="glass card">
          <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8 }}><b>{t.name}</b><span className="badge allocated">{t.channel}</span></div>
          <div className="muted" style={{ fontSize: 13, margin: '8px 0', whiteSpace: 'pre-wrap' }}>{t.body}</div>
          <div className="toolbar" style={{ margin: 0 }}><button className="btn sm" onClick={() => { setEditing(t); setModal(true); }}>Edit</button>
            <button className="btn sm" onClick={() => del(t.id)}>Delete</button></div>
        </div>)}</div>}
      {modal && <TemplateModal editing={editing} onClose={() => setModal(false)} onDone={() => { setModal(false); load(); }} />}
    </div>
  );
}

function CampaignModal({ cases, onClose }) {
  const [tpls, setTpls] = useState([]); const [tid, setTid] = useState('');
  useEffect(() => { api('/api/templates').then(setTpls).catch(() => setTpls([])); }, []);
  const tpl = tpls.find(t => String(t.id) === String(tid));
  const withPhone = cases.filter(c => c.phone);
  const dl = () => {
    if (!tpl) return;
    const esc = v => `"${String(v == null ? '' : v).replace(/"/g, '""')}"`;
    const lines = [['customer', 'phone', 'bank', 'pending', 'message'].join(',')].concat(
      withPhone.map(c => [esc(c.customer_name), esc(c.phone), esc(c.bank), esc(Math.round(c.pending_amount || 0)), esc(renderTemplate(tpl.body, c))].join(',')));
    const blob = new Blob([lines.join('\n')], { type: 'text/csv' }); const url = URL.createObjectURL(blob);
    const a = document.createElement('a'); a.href = url; a.download = `campaign_${tpl.name.replace(/\s/g, '')}.csv`; document.body.appendChild(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 3000);
    toast(`CSV for ${withPhone.length} contacts downloaded`);
  };
  return (
    <div className="modal-bg" onClick={onClose}>
      <div className="modal glass" onClick={e => e.stopPropagation()}>
        <div className="section-h"><h3>Bulk message campaign</h3><button className="btn ghost sm" onClick={onClose}>✕</button></div>
        <p className="muted" style={{ fontSize: 13 }}>Applies to the {cases.length} cases in your current filter · {withPhone.length} have a phone number. Downloads a CSV (name, phone, merged message) ready for a WhatsApp/SMS provider.</p>
        <div className="field"><label>Template</label>
          <select className="input" value={tid} onChange={e => setTid(e.target.value)}>
            <option value="">— pick a template —</option>{tpls.map(t => <option key={t.id} value={t.id}>{t.name} ({t.channel})</option>)}</select></div>
        {tpls.length === 0 && <div className="muted" style={{ fontSize: 12 }}>No templates yet — create one under Templates first.</div>}
        {tpl && withPhone[0] && <div className="glass card" style={{ background: 'rgba(0,0,0,.2)', fontSize: 13, marginBottom: 10 }}>
          <div className="muted" style={{ fontSize: 11.5, marginBottom: 4 }}>Preview → {withPhone[0].customer_name}</div>{renderTemplate(tpl.body, withPhone[0])}</div>}
        <button className="btn gold block" onClick={dl} disabled={!tpl || withPhone.length === 0}>⬇ Download campaign CSV ({withPhone.length})</button>
      </div>
    </div>
  );
}

/* ============================== Litigation / Legal ============================== */
const MATTER_TYPES = ['Sec 138', 'SARFAESI', 'Arbitration', 'IBC', 'Civil', 'Criminal', 'Consumer'];
const LEGAL_STAGES = ['Notice', 'Filed', 'Admitted', 'Evidence', 'Arguments', 'Order', 'Execution', 'Disposed'];
function LegalModal({ editing, onClose, onDone }) {
  const [f, setF] = useState(editing || { matter_type: 'Sec 138', status: 'open', borrower_name: '', bank: '', court: '', case_number: '', stage: 'Notice', filed_date: '', next_hearing_date: '', amount: '', notes: '', branch: '' });
  const [busy, setBusy] = useState(false); const [err, setErr] = useState('');
  const save = async () => { setErr(''); setBusy(true);
    const body = { ...f, filed_date: f.filed_date || null, next_hearing_date: f.next_hearing_date || null, amount: f.amount || '0' };
    try { if (editing) await api('/api/legal/' + editing.id, { method: 'PATCH', body }); else await api('/api/legal', { method: 'POST', body });
      toast('Saved.'); onDone();
    } catch (e) { setErr(e.message); } finally { setBusy(false); } };
  const u = (k, v) => setF({ ...f, [k]: v });
  return (
    <div className="modal-bg" onClick={onClose}>
      <div className="modal glass" onClick={e => e.stopPropagation()}>
        <div className="section-h"><h3>{editing ? 'Edit' : 'New'} matter</h3><button className="btn ghost sm" onClick={onClose}>✕</button></div>
        <div className="grid2" style={{ gridTemplateColumns: '1fr 1fr' }}>
          <div className="field"><label>Borrower</label><input className="input" value={f.borrower_name || ''} onChange={e => u('borrower_name', e.target.value)} /></div>
          <div className="field"><label>Bank</label><input className="input" value={f.bank || ''} onChange={e => u('bank', e.target.value)} /></div>
          <div className="field"><label>Matter type</label><select className="input" value={f.matter_type} onChange={e => u('matter_type', e.target.value)}>{MATTER_TYPES.map(m => <option key={m}>{m}</option>)}</select></div>
          <div className="field"><label>Stage</label><select className="input" value={f.stage || ''} onChange={e => u('stage', e.target.value)}><option value="">—</option>{LEGAL_STAGES.map(s => <option key={s}>{s}</option>)}</select></div>
          <div className="field"><label>Court</label><input className="input" value={f.court || ''} onChange={e => u('court', e.target.value)} /></div>
          <div className="field"><label>Case number</label><input className="input" value={f.case_number || ''} onChange={e => u('case_number', e.target.value)} /></div>
          <div className="field"><label>Filed date</label><input className="input" type="date" value={f.filed_date || ''} onChange={e => u('filed_date', e.target.value)} /></div>
          <div className="field"><label>Next hearing</label><input className="input" type="date" value={f.next_hearing_date || ''} onChange={e => u('next_hearing_date', e.target.value)} /></div>
          <div className="field"><label>Amount (₹)</label><input className="input" type="number" value={f.amount || ''} onChange={e => u('amount', e.target.value)} /></div>
          <div className="field"><label>Status</label><select className="input" value={f.status} onChange={e => u('status', e.target.value)}><option>open</option><option>settled</option><option>won</option><option>lost</option><option>closed</option></select></div>
        </div>
        <div className="field"><label>Notes</label><textarea className="input" value={f.notes || ''} onChange={e => u('notes', e.target.value)} /></div>
        {err && <div style={{ color: 'var(--bad)', fontSize: 13 }}>{err}</div>}
        <button className="btn gold block" onClick={save} disabled={busy} style={{ marginTop: 8 }}>Save</button>
      </div>
    </div>
  );
}
function LegalView() {
  const [items, setItems] = useState(null); const [ins, setIns] = useState(null);
  const [modal, setModal] = useState(false); const [editing, setEditing] = useState(null);
  const [mt, setMt] = useState(''); const [st, setSt] = useState('');
  const load = () => {
    const p = new URLSearchParams(); if (mt) p.set('matter_type', mt); if (st) p.set('status', st);
    api('/api/legal' + (p.toString() ? '?' + p : '')).then(setItems).catch(() => setItems([]));
    api('/api/legal/insights').then(setIns).catch(() => {});
  };
  useEffect(() => { load(); }, [mt, st]);
  const today = new Date().toISOString().slice(0, 10);
  const hearingStyle = (d) => !d ? {} : d < today ? { color: 'var(--bad)', fontWeight: 600 } : d === today ? { color: 'var(--gold-2)', fontWeight: 600 } : {};
  return (
    <div>
      {ins && <div className="kpis">
        <div className="glass kpi"><div className="l">Open matters</div><div className="v">{ins.open}</div></div>
        <div className="glass kpi"><div className="l">Hearing overdue</div><div className="v" style={{ color: 'var(--bad)' }}>{ins.hearing_overdue}</div></div>
        <div className="glass kpi"><div className="l">Hearing today</div><div className="v" style={{ color: 'var(--gold-2)' }}>{ins.hearing_today}</div></div>
        <div className="glass kpi"><div className="l">This week</div><div className="v">{ins.hearing_week}</div></div>
      </div>}
      <div className="toolbar">
        <select className="input" style={{ maxWidth: 150 }} value={mt} onChange={e => setMt(e.target.value)}><option value="">All matters</option>{MATTER_TYPES.map(m => <option key={m}>{m}</option>)}</select>
        <select className="input" style={{ maxWidth: 130 }} value={st} onChange={e => setSt(e.target.value)}><option value="">All status</option><option>open</option><option>settled</option><option>won</option><option>lost</option><option>closed</option></select>
        <div style={{ flex: 1 }} /><button className="btn gold" onClick={() => { setEditing(null); setModal(true); }}>+ New matter</button>
      </div>
      {!items ? <Loader /> : items.length === 0 ? <p className="muted">No matters yet. Add one to track hearings and stages.</p> :
        <div className="glass card" style={{ padding: 6 }}><div className="tablewrap"><table>
          <thead><tr><th>Borrower</th><th>Matter</th><th>Court</th><th>Case no.</th><th>Stage</th><th>Next hearing</th><th>Status</th><th></th></tr></thead>
          <tbody>{items.map(l => <tr key={l.id}>
            <td><b>{l.borrower_name || '—'}</b><div className="muted" style={{ fontSize: 11.5 }}>{l.bank} {l.amount > 0 ? '· ₹' + Math.round(l.amount) : ''}</div></td>
            <td><span className="badge allocated">{l.matter_type}</span></td>
            <td className="muted">{l.court || '—'}</td><td className="mono" style={{ fontSize: 12 }}>{l.case_number || '—'}</td>
            <td>{l.stage || '—'}</td>
            <td style={hearingStyle(l.next_hearing_date)}>{l.next_hearing_date || '—'}</td>
            <td><span className={cx('badge', l.status === 'won' || l.status === 'settled' ? 'paid' : l.status === 'lost' ? 'unpaid' : 'ptp')}>{l.status}</span></td>
            <td><button className="btn sm" onClick={() => { setEditing({ ...l, filed_date: l.filed_date || '', next_hearing_date: l.next_hearing_date || '', amount: l.amount || '' }); setModal(true); }}>Edit</button></td>
          </tr>)}</tbody></table></div></div>}
      {modal && <LegalModal editing={editing} onClose={() => setModal(false)} onDone={() => { setModal(false); load(); }} />}
    </div>
  );
}

/* ============================== Security (2FA + passkeys) ============================== */
function SecurityView({ user }) {
  const [st, setSt] = useState(null);         // { enabled }
  const [setup, setSetup] = useState(null);   // { secret, otpauth_url }
  const [code, setCode] = useState('');
  const [keys, setKeys] = useState([]);
  const [busy, setBusy] = useState(false);
  const load = () => {
    api('/api/auth/2fa/status').then(setSt).catch(() => setSt({ enabled: false }));
    api('/api/auth/webauthn/list').then(setKeys).catch(() => setKeys([]));
  };
  useEffect(load, []);
  const begin = async () => { setBusy(true); try { setSetup(await api('/api/auth/2fa/setup', { method: 'POST' })); } catch (e) { toast(e.message, 'err'); } finally { setBusy(false); } };
  const enable = async () => { setBusy(true); try { await api('/api/auth/2fa/enable', { body: { otp: code } }); toast('Two-factor enabled'); setSetup(null); setCode(''); load(); } catch (e) { toast(e.message, 'err'); } finally { setBusy(false); } };
  const disable = async () => { const c = prompt('Enter a current 6-digit code to turn off 2FA:'); if (!c) return; setBusy(true); try { await api('/api/auth/2fa/disable', { body: { otp: c } }); toast('Two-factor disabled'); load(); } catch (e) { toast(e.message, 'err'); } finally { setBusy(false); } };
  const addKey = async () => { setBusy(true); try { await registerPasskey('Passkey · ' + new Date().toLocaleDateString()); toast('Passkey added'); load(); } catch (e) { toast(e.message || 'Passkey setup cancelled', 'err'); } finally { setBusy(false); } };
  const delKey = async (id) => { if (!confirm('Remove this passkey?')) return; try { await api('/api/auth/webauthn/' + id, { method: 'DELETE' }); load(); } catch (e) { toast(e.message, 'err'); } };
  return (
    <div className="grid2" style={{ alignItems: 'start' }}>
      <div className="glass card">
        <div className="section-h"><h3>Two-factor authentication</h3>
          {st && <span className={cx('badge', st.enabled ? 'paid' : 'unpaid')}>{st.enabled ? 'ON' : 'OFF'}</span>}</div>
        <p className="muted" style={{ fontSize: 13 }}>Adds a 6-digit code from an authenticator app (Google Authenticator, Authy) on top of your password.</p>
        {!st ? <Loader /> : st.enabled ? (
          <button className="btn" onClick={disable} disabled={busy}>Turn off 2FA</button>
        ) : setup ? (
          <div>
            <p style={{ fontSize: 13 }}>Scan this in your authenticator app, then enter the code to confirm:</p>
            <div style={{ display: 'flex', justifyContent: 'center', margin: '10px 0' }}><QR text={setup.otpauth_url} size={160} /></div>
            <p className="muted" style={{ fontSize: 11.5, wordBreak: 'break-all' }}>Manual key: {setup.secret}</p>
            <div className="field"><input className="input" inputMode="numeric" placeholder="123456" value={code}
              onChange={e => setCode(e.target.value.replace(/\D/g, '').slice(0, 6))} /></div>
            <button className="btn gold" onClick={enable} disabled={busy || code.length < 6}>Confirm & enable</button>
          </div>
        ) : (
          <button className="btn gold" onClick={begin} disabled={busy}>Set up 2FA</button>
        )}
      </div>

      <div className="glass card">
        <div className="section-h"><h3>Passkeys / biometric</h3></div>
        <p className="muted" style={{ fontSize: 13 }}>Sign in with Face ID, fingerprint, Windows Hello or a security key — no password needed. Requires HTTPS.</p>
        {passkeySupported()
          ? <button className="btn gold" onClick={addKey} disabled={busy}>➕ Add a passkey on this device</button>
          : <div className="muted" style={{ fontSize: 13 }}>This browser/device doesn't support passkeys.</div>}
        <div style={{ marginTop: 12 }}>
          {keys.length === 0 ? <p className="muted" style={{ fontSize: 13 }}>No passkeys yet.</p> :
            keys.map(k => <div key={k.id} className="stat-row">
              <div><b>{k.label || 'Passkey'}</b><div className="muted" style={{ fontSize: 11.5 }}>{k.last_used ? 'Last used ' + fmtDay(k.last_used) : 'Never used'}</div></div>
              <button className="btn ghost sm" onClick={() => delKey(k.id)}>Remove</button>
            </div>)}
        </div>
      </div>
    </div>
  );
}

/* ============================== Shell + App ============================== */
/* Live refresh — runs cb (debounced) whenever the server broadcasts a data change
   (any FOS/caller log, payment, or sheet edit). Used by MIS, dashboards, cases. */
function useDataChanged(cb) {
  const ref = React.useRef(cb); ref.current = cb;
  React.useEffect(() => {
    let stop = false, ws, timer;
    const connect = () => {
      try {
        ws = new WebSocket(location.origin.replace(/^http/, 'ws') + '/ws?token=' + encodeURIComponent(store.t || ''));
        ws.onmessage = e => { try { const m = JSON.parse(e.data);
          if (m.type === 'notification') { try { window.dispatchEvent(new CustomEvent('ssd-notif', { detail: m.notification })); } catch (_) {} return; }
          if (m.type === 'data_changed' || m.type === 'case_update') { clearTimeout(timer); timer = setTimeout(() => ref.current(m), 700); } } catch (_) {} };
        ws.onclose = () => { if (!stop) setTimeout(connect, 3000); };
      } catch (_) { if (!stop) setTimeout(connect, 3000); }
    };
    connect();
    return () => { stop = true; clearTimeout(timer); try { ws && ws.close(); } catch (_) {} };
  }, []);
}

/* ==================== Cycle-wise MIS (per portfolio, per billing cycle) ==================== */
/* Shared by the MIS section (managers/HO/etc.) and the caller/FOS scorecard — the backend
   scopes rows by role, so each viewer only sees what they're allowed to. */
function CycleMIS({ compact }) {
  const [monthB, setMonthB] = useState('current');
  const [d, setD] = useState(null); const [err, setErr] = useState('');
  const money = v => '₹' + Math.round(Number(v) || 0).toLocaleString('en-IN');
  const load = () => { setErr(''); api('/api/mis/by-cycle?month_bucket=' + monthB).then(setD)
    .catch(e => { setErr(e.message || 'Could not load'); setD({ portfolios: [] }); }); };
  useEffect(() => { load(); }, [monthB]);
  useDataChanged(load);
  const COLS = [['cycle', 'Cycle'], ['count', 'Cases'], ['paid', 'Paid'], ['unpaid', 'Unpaid'],
    ['enr', 'ENR'], ['paid_enr', 'Paid ENR'], ['pct', 'Achieved %'], ['norm_pct', 'NORM %'],
    ['stab_pct', 'STAB %'], ['collected', 'Cash'], ['pending', 'Pending'],
    ['target_pct', 'Target %'], ['to_target_pct', 'To target %']];
  const cell = (k, v) => {
    if (v === null || v === undefined || v === '') return '—';
    if (/_pct$|^pct$/.test(k)) return v + '%';
    if (/(enr|collected|pending|cash)/.test(k) && typeof v === 'number') return money(v);
    return v;
  };
  return (
    <div>
      <style>{`
        table.mis-grid thead th{background:linear-gradient(180deg,#2563EB,#1D4ED8);color:#fff;font-weight:600}
        table.mis-grid tbody tr:nth-child(even) td{background:#F5F8FE}
        table.mis-grid td,table.mis-grid th{border-color:#dbe3ef}
      `}</style>
      <div className="toolbar" style={{ marginBottom: 12 }}>
        <b style={{ fontSize: compact ? 14 : 16 }}>🔄 Cycle-wise MIS</b>
        <span className="muted" style={{ fontSize: 12 }}>Every portfolio, split by billing cycle.</span>
        <div style={{ flex: 1 }} />
        {[['current', '📅 This month'], ['next', '🔜 Next month'], ['', 'All months']].map(([v, lbl]) =>
          <div key={v} className={cx('chip', monthB === v && 'on')} onClick={() => setMonthB(v)}>{lbl}</div>)}
      </div>
      {err && <div className="glass card" style={{ color: 'var(--bad)' }}>{err}</div>}
      {!d ? <Loader /> : (!d.portfolios || !d.portfolios.length) ?
        <div className="glass card muted" style={{ padding: 20 }}>No cycle data for this month yet.</div> :
        d.portfolios.map((p, i) => (
          <div key={i} className="glass card" style={{ padding: 10, marginTop: 12 }}>
            <div className="section-h"><h3 style={{ margin: 0, fontSize: 15 }}>{p.label}</h3>
              <span className="muted" style={{ fontSize: 12 }}>{p.totals.count} cases · {money(p.totals.enr)} ENR · <b style={{ color: 'var(--good)' }}>{p.totals.pct}%</b> achieved · {money(p.totals.collected)} collected</span></div>
            <div className="tablewrap"><table className="mis-grid">
              <thead><tr>{COLS.map(c => <th key={c[0]}>{c[1]}</th>)}</tr></thead>
              <tbody>{p.cycles.map((r, j) => <tr key={j}>{COLS.map(c => {
                const v = r[c[0]]; const pct = /_pct$|^pct$/.test(c[0]) && typeof v === 'number';
                return <td key={c[0]} className={typeof v === 'number' ? 'mono' : ''}
                  style={pct ? { background: v >= 60 ? 'rgba(22,163,74,.16)' : v >= 30 ? 'rgba(217,119,6,.16)' : 'rgba(220,38,38,.13)', fontWeight: 600 } : null}>{cell(c[0], v)}</td>;
              })}</tr>)}</tbody></table></div>
          </div>
        ))}
    </div>
  );
}

/* ==================== MIS (analysis core) ==================== */
function MISView({ user }) {
  const canTarget = ['admin', 'manager', 'backend', 'headoffice'].includes(user.role);
  const [prods, setProds] = useState(null); const [sel, setSel] = useState(null); const [ov, setOv] = useState(null);
  const [d, setD] = useState(null); const [err, setErr] = useState(''); const [emp, setEmp] = useState('');
  const [full, setFull] = useState(false);
  const [monthB, setMonthB] = useState('current');   // month-wise MIS: 'current' | 'next' | '' (all)
  const [cycleView, setCycleView] = useState(false); // 'Cycle-wise MIS' — every portfolio by cycle
  const [area, setArea] = useState(''); const [areas, setAreas] = useState([]);   // area-wise MIS
  const money = v => '₹' + Math.round(Number(v) || 0).toLocaleString('en-IN');
  useEffect(() => {
    api('/api/cases/product-summary').then(rows => {
      const seen = {}, list = [];
      (rows || []).forEach(r => { const k = r.bank + '||' + r.product + '||' + (r.branch || ''); if (!seen[k] && r.product !== '—') { seen[k] = 1; list.push({ bank: r.bank, product: r.product, branch: r.branch || '' }); } });
      setProds(list); if (list[0]) setSel(list[0]);
    }).catch(() => setProds([]));
    api('/api/mis/overview').then(setOv).catch(() => {});
  }, []);
  const mbq = (monthB ? `&month_bucket=${monthB}` : '') + (area ? `&area=${encodeURIComponent(area)}` : '') + ((sel && sel.branch) ? `&branch=${encodeURIComponent(sel.branch)}` : '');
  const load = () => { if (!sel) { setD(null); return; } api(`/api/mis?bank=${encodeURIComponent(sel.bank)}&product=${encodeURIComponent(sel.product)}${mbq}`).then(setD).catch(e => setErr(e.message || 'Could not load MIS')); };
  useEffect(() => { setErr(''); setD(null); load(); }, [sel, monthB, area]);
  // Area list for the selected portfolio (reset area when switching portfolio).
  useEffect(() => { setArea(''); if (!sel) { setAreas([]); return; } api(`/api/cases/areas?bank=${encodeURIComponent(sel.bank)}&product=${encodeURIComponent(sel.product)}${(sel.branch ? '&branch=' + encodeURIComponent(sel.branch) : '')}`).then(a => setAreas(a || [])).catch(() => setAreas([])); }, [sel]);
  // Real-time: recompute the MIS instantly whenever any log/payment/edit lands.
  useDataChanged(m => { if (!sel) return; if (m && m.product && m.product !== sel.product) return; load(); api('/api/mis/overview').then(setOv).catch(() => {}); });
  const saveTarget = (e) => {          // ONE product-wide target for every FOS & caller
    const v = parseFloat(e.target.value) || 0;
    api('/api/mis/target', { method: 'PUT', body: { bank: sel.bank, product: sel.product, target_pct: v } }).then(load).catch(() => {});
  };
  const dl = (tables) => download(`/api/mis/download?bank=${encodeURIComponent(sel.bank)}&product=${encodeURIComponent(sel.product)}&tables=${tables}${mbq}`, `MIS_${sel.bank}_${sel.product}${sel.branch ? '_' + sel.branch : ''}_${monthB || 'all'}.xlsx`);

  if (!prods) return <Loader />;
  if (!prods.length) return <div className="glass card muted" style={{ padding: 24, textAlign: 'center' }}>No products with cases yet. Upload a product file first.</div>;

  const fmtCell = (k, v) => {
    if (v === null || v === undefined || v === '') return '—';
    if (/(_pct$|^pct$)/.test(k)) return v + '%';
    if (typeof v === 'boolean') return v ? 'Yes' : '—';
    if (/(enr|amount|pending|collected|cash|coll|leakage|target_enr|achieved_enr|gap)/.test(k) && typeof v === 'number') return money(v);
    return v;
  };
  const printTable = (title, headers, rows2d) => {
    const w = window.open('', '_blank'); if (!w) return;
    const th = headers.map(h => '<th>' + h + '</th>').join('');
    const body = rows2d.map(r => '<tr>' + r.map(c => '<td>' + (c == null ? '' : String(c)) + '</td>').join('') + '</tr>').join('');
    w.document.write('<html><head><title>' + title + '</title><style>body{font-family:system-ui;padding:22px}h2{color:#2563EB}table{border-collapse:collapse;width:100%;font-size:12px}th,td{border:1px solid #cbd5e1;padding:5px 8px;text-align:left}th{background:#EEF3FB}</style></head><body><h2>' + title + ' — ' + sel.bank + ' ' + sel.product + '</h2><table><thead><tr>' + th + '</tr></thead><tbody>' + body + '</tbody></table></body></html>');
    w.document.close(); w.focus(); setTimeout(() => { try { w.print(); } catch (e) {} }, 350);
  };
  const goto = tk => { const el = document.getElementById('mis-' + tk); if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' }); };

  const GROUP = [['label', 'Name'], ['count', 'Count'], ['paid', 'Paid'], ['unpaid', 'Unpaid'], ['enr', 'ENR'], ['paid_enr', 'Paid ENR'], ['pct', 'Paid %'], ['norm_pct', 'NORM %'], ['stab_pct', 'STAB %'], ['rollback_pct', 'RB %'], ['rollback_collected', 'RB ₹'], ['amount', 'Cash'], ['visited', 'Vis'], ['not_visited', 'Not vis']];
  // Area-wise gets its own columns highlighting outstanding + recovery rate per area.
  const AREA = [['label', 'Area'], ['count', 'Count'], ['paid', 'Paid'], ['unpaid', 'Unpaid'], ['enr', 'ENR'], ['pending', 'Pending'], ['amount', 'Collected'], ['recovery_pct', 'Recovery %'], ['pct', 'Paid %'], ['norm_pct', 'NORM %'], ['stab_pct', 'STAB %']];
  const CASES = [['customer', 'Customer'], ['account', 'Account'], ['pending', 'Pending'], ['enr', 'ENR'], ['propensity', 'Score'], ['fos', 'FOS'], ['caller', 'Caller']];
  const TABLES = [
    ['by_fos', GROUP], ['by_caller', GROUP], ['by_area', AREA], ['by_team_lead', GROUP], ['by_cat', GROUP], ['by_dpd', GROUP],
    ['aging', [['label', 'Recency'], ['count', 'Count'], ['pending', 'Pending']]],
    ['untouched_table', CASES], ['top_pending', CASES], ['priority', CASES],
    ['obstacles', [['caller', 'Caller'], ['total', 'Total'], ['obstacles', 'Obstacles'], ['rate_pct', 'Rate %']]],
    ['productivity', [['emp', 'Employee'], ['calls_today', 'Calls'], ['visits_today', 'Visits'], ['idle', 'Idle']]],
    ['field_efficiency', [['fos', 'FOS'], ['visits', 'Visits'], ['distance_km', 'Dist km'], ['off_location', 'Off-loc'], ['collected', 'Collected']]],
    ['trend', [['date', 'Date'], ['collected', 'Collected']]],
  ];
  const MisTable = ({ tk, cols }) => {
    const rows = (d && d[tk]) || [];
    const title = (d && d.table_names && d.table_names[tk]) || tk;
    const doPrint = () => printTable(title, cols.map(c => c[1]), rows.map(r => cols.map(c => fmtCell(c[0], r[c[0]]))));
    return <div id={'mis-' + tk} className="glass card" style={{ padding: 10, marginTop: 14 }}>
      <div className="section-h"><h3 style={{ margin: 0 }}>{title}</h3>
        <div style={{ display: 'flex', gap: 6 }}><button className="btn sm" onClick={() => dl(tk)}>⬇</button><button className="btn sm" onClick={doPrint}>🖨</button></div></div>
      <div className="tablewrap"><table className="mis-grid"><thead><tr>{cols.map(c => <th key={c[0]}>{c[1]}</th>)}</tr></thead>
        <tbody>{rows.map((r, i) => <tr key={i}>{cols.map(c => {
          const v = r[c[0]]; const pct = /(_pct$|^pct$)/.test(c[0]) && typeof v === 'number';
          return <td key={c[0]} className={typeof v === 'number' ? 'mono' : ''}
            style={pct ? { background: v >= 60 ? 'rgba(22,163,74,.16)' : v >= 30 ? 'rgba(217,119,6,.16)' : 'rgba(220,38,38,.13)', fontWeight: 600 } : null}>{fmtCell(c[0], v)}</td>;
        })}</tr>)}</tbody></table></div>
      {rows.length === 0 && <div className="muted" style={{ padding: 12 }}>No data.</div>}
    </div>;
  };
  const STATUS_COLOR = { green: 'var(--good)', amber: 'var(--warn)', red: 'var(--bad)', none: '#c9ced8' };
  const lb = d ? (emp ? d.leaderboard.filter(x => x.emp === emp) : d.leaderboard) : [];
  const proj = d && d.projection; const fn = d && d.funnel; const st = d && d.settlement;
  const LB_COLS = [['emp', 'Employee'], ['count', 'Count'], ['unpaid', 'Unpaid'], ['paid', 'Paid'], ['enr', 'ENR'], ['target_pct', 'Target %'], ['target_enr', 'Target ENR'], ['achieved_pct', 'Achieved %'], ['achieved_enr', 'Achieved ENR'], ['gap_enr', 'Gap ENR'], ['to_target_pct', 'To target %'], ['pending_visit', 'Pend visit'], ['cash_coll', 'Cash coll']];
  const sheetTables = () => [['Employee performance & leaderboard', LB_COLS, lb]].concat(
    TABLES.map(([tk, cols]) => [(d.table_names && d.table_names[tk]) || tk, cols, (d[tk] || [])]));
  const printAll = () => {
    const w = window.open('', '_blank'); if (!w) return;
    let html = '<html><head><title>MIS ' + sel.bank + ' ' + sel.product + '</title><style>body{font-family:system-ui;padding:20px}h1{font-size:18px;color:#1e293b}h2{color:#2563EB;margin:18px 0 6px;font-size:14px}table{border-collapse:collapse;width:100%;font-size:11px;margin-bottom:14px}th,td{border:1px solid #cbd5e1;padding:4px 7px;text-align:left}th{background:#EEF3FB}</style></head><body><h1>MIS — ' + sel.bank + ' · ' + sel.product + '</h1>';
    sheetTables().forEach(([title, cols, rows]) => {
      html += '<h2>' + title + '</h2><table><thead><tr>' + cols.map(c => '<th>' + c[1] + '</th>').join('') + '</tr></thead><tbody>'
        + rows.map(r => '<tr>' + cols.map(c => '<td>' + String(fmtCell(c[0], r[c[0]]) ?? '') + '</td>').join('') + '</tr>').join('') + '</tbody></table>';
    });
    html += '</body></html>'; w.document.write(html); w.document.close(); w.focus(); setTimeout(() => { try { w.print(); } catch (e) {} }, 400);
  };

  return (
    <div>
      <style>{`
        table.mis-grid thead th{background:linear-gradient(180deg,#2563EB,#1D4ED8);color:#fff;font-weight:600;position:sticky;top:0;z-index:1}
        table.mis-grid tbody tr:nth-child(even) td{background:#F5F8FE}
        table.mis-grid tbody tr:hover td{background:#EAF1FF}
        table.mis-grid td,table.mis-grid th{border-color:#dbe3ef}
      `}</style>
      <div className="toolbar">
        <select className="input" style={{ maxWidth: 300 }} value={sel ? sel.bank + '||' + sel.product + '||' + (sel.branch || '') : ''}
          onChange={e => { const [b, p, br] = e.target.value.split('||'); setSel({ bank: b, product: p, branch: br || '' }); setEmp(''); }}>
          {prods.map((p, i) => <option key={i} value={p.bank + '||' + p.product + '||' + (p.branch || '')}>{p.bank} · {p.product}{p.branch ? ' · 📍 ' + p.branch : ''}</option>)}
        </select>
        {/* Month-wise MIS — keep this-month and next-month figures cleanly separate. */}
        {[['current', '📅 This month'], ['next', '🔜 Next month'], ['', 'All months']].map(([v, lbl]) =>
          <div key={v} className={cx('chip', monthB === v && 'on')} onClick={() => setMonthB(v)}>{lbl}</div>)}
        {/* Cycle-wise MIS — every portfolio broken down by billing cycle. */}
        <div className={cx('chip', cycleView && 'on')} onClick={() => setCycleView(v => !v)} title="MIS analytics for each portfolio, per billing cycle">🔄 Cycle-wise MIS</div>
        {/* Area-wise — full MIS for one AREA only. */}
        {areas.length > 0 && <select className="input" style={{ maxWidth: 160 }} value={area} onChange={e => setArea(e.target.value)} title="Full MIS for one area">
          <option value="">📍 All areas</option>{areas.map(a => <option key={a} value={a}>{a}</option>)}</select>}
        {d && <select className="input" style={{ maxWidth: 220 }} value={emp} onChange={e => setEmp(e.target.value)}>
          <option value="">All employees</option>
          {d.by_fos.map((r, i) => <option key={i} value={r.label}>{r.label}</option>)}
        </select>}
        <div style={{ flex: 1 }} />
        {d && <button className="btn" onClick={() => setFull(true)}>📄 Full sheet</button>}
        {d && <button className="btn gold" onClick={() => dl(Object.keys(d.table_names || {}).join(','))}>⬇ Download all MIS</button>}
      </div>
      {err && <div className="glass card" style={{ color: 'var(--bad)' }}>{err}</div>}
      {cycleView && <CycleMIS />}
      {d && d.base_label === 'TOS' && !cycleView && <div className="muted" style={{ fontSize: 12, margin: '2px 2px 8px' }}>PL/BL recovery base: <b>TOS</b> (total outstanding) · % = paid TOS ÷ total TOS · pivoted by caller &amp; FOS{d.segment ? ` · ${d.segment}` : ''}</div>}
      {cycleView ? null : !d ? <Loader /> : <>
        {/* Table index */}
        <div className="glass card" style={{ padding: 10, marginBottom: 12 }}>
          <div className="muted" style={{ fontSize: 12, marginBottom: 6 }}>MIS tables — jump to</div>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
            <div className="chip" onClick={() => goto('leaderboard')}>Leaderboard</div>
            {TABLES.map(([tk]) => <div key={tk} className="chip" onClick={() => goto(tk)}>{(d.table_names && d.table_names[tk]) || tk}</div>)}
          </div>
        </div>

        {/* KPIs + projection */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill,minmax(150px,1fr))', gap: 12 }}>
          <div className="glass card" style={{ padding: 14 }}><div className="muted" style={{ fontSize: 12 }}>Total cases</div><b style={{ fontSize: 20 }}>{d.overall.count}</b></div>
          <div className="glass card" style={{ padding: 14 }}><div className="muted" style={{ fontSize: 12 }}>Total {d.base_label || 'ENR'}</div><b style={{ fontSize: 20 }}>{money(d.overall.enr)}</b></div>
          <div className="glass card" style={{ padding: 14 }}><div className="muted" style={{ fontSize: 12 }}>Paid {d.base_label || 'ENR'}</div><b style={{ fontSize: 20, color: 'var(--good)' }}>{money(d.overall.paid_enr)}</b></div>
          <div className="glass card" style={{ padding: 14 }}><div className="muted" style={{ fontSize: 12 }}>Achieved %</div><b style={{ fontSize: 20, color: 'var(--gold)' }}>{d.overall.pct}%</b></div>
          <div className="glass card" style={{ padding: 14 }}><div className="muted" style={{ fontSize: 12 }}>Collected (MTD)</div><b style={{ fontSize: 20, color: 'var(--good)' }}>{money(proj.collected_mtd)}</b></div>
          <div className="glass card" style={{ padding: 14 }}><div className="muted" style={{ fontSize: 12 }}>Projected month-end</div><b style={{ fontSize: 20 }}>{money(proj.projected_month_end)}</b><div className="muted" style={{ fontSize: 11 }}>{proj.projected_pct}% of target</div></div>
          <div className="glass card" style={{ padding: 14 }}><div className="muted" style={{ fontSize: 12 }}>PTP kept</div><b style={{ fontSize: 20 }}>{fn.ptp_kept}/{fn.ptp_total}</b><div className="muted" style={{ fontSize: 11 }}>{fn.ptp_kept_pct}% · {fn.ptp_broken} broken</div></div>
          <div className="glass card" style={{ padding: 14 }}><div className="muted" style={{ fontSize: 12 }}>Untouched</div><b style={{ fontSize: 20, color: 'var(--bad)' }}>{fn.untouched}</b><div className="muted" style={{ fontSize: 11 }}>{money(fn.untouched_pending)} pending</div></div>
          <div className="glass card" style={{ padding: 14 }}><div className="muted" style={{ fontSize: 12 }}>Realization</div><b style={{ fontSize: 20 }}>{st.realization_pct}%</b><div className="muted" style={{ fontSize: 11 }}>leak {money(st.leakage)}</div></div>
          <div className="glass card" style={{ padding: 14 }}><div className="muted" style={{ fontSize: 12 }}>Conversion</div><b style={{ fontSize: 20 }}>{fn.conversion_pct}%</b><div className="muted" style={{ fontSize: 11 }}>{fn.paid_of_contacted}/{fn.contacted} contacted</div></div>
          {st.rollback_target > 0 && <div className="glass card" style={{ padding: 14 }}><div className="muted" style={{ fontSize: 12 }}>Rollback collected</div><b style={{ fontSize: 20, color: 'var(--good)' }}>{money(st.rollback_collected)}</b><div className="muted" style={{ fontSize: 11 }}>{st.rollback_pct}% of ENR · {st.rollback_realization_pct}% of {money(st.rollback_target)} · {st.rollback_count} cases</div></div>}
        </div>

        {/* FTD / MTD / LMTD / Overall cash-collected comparison for this portfolio */}
        {d.trends && <TrendStrip trends={d.trends} title={`Achievement (cash collected) — ${sel.bank} · ${sel.product}${sel.branch ? ' · ' + sel.branch : ''}`} />}

        {/* Charts */}
        <div className="grid2" style={{ gridTemplateColumns: '1fr 1fr', gap: 14, marginTop: 14 }}>
          <div className="glass card" style={{ padding: 12 }}><b>Collection trend (30 days)</b>
            <ChartBox type="line" height={220} data={{ labels: d.trend.map(t => t.date.slice(5)), datasets: [{ label: 'Collected', data: d.trend.map(t => t.collected), borderColor: '#2563EB', backgroundColor: 'rgba(37,99,235,.12)', fill: true, tension: .3 }] }} options={{ plugins: { legend: { display: false } } }} /></div>
          <div className="glass card" style={{ padding: 12 }}><b>Top FOS — achieved ENR</b>
            <ChartBox type="bar" height={220} data={{ labels: d.leaderboard.slice(0, 10).map(r => (r.emp || '').split('/')[0]), datasets: [{ data: d.leaderboard.slice(0, 10).map(r => r.achieved_enr), backgroundColor: '#2563EB' }] }} options={{ plugins: { legend: { display: false } } }} /></div>
          <div className="glass card" style={{ padding: 12 }}><b>Settlement — STAB vs NORM ENR</b>
            <ChartBox type="doughnut" height={220} options={{ cutout: '65%' }} data={{ labels: ['STAB', 'NORM'], datasets: [{ data: [st.stab_enr, st.norm_enr], backgroundColor: ['#D97706', '#16A34A'] }] }} /></div>
          <div className="glass card" style={{ padding: 12 }}><b>PTP kept vs broken</b>
            <ChartBox type="doughnut" height={220} options={{ cutout: '65%' }} data={{ labels: ['Kept', 'Broken', 'Pending'], datasets: [{ data: [fn.ptp_kept, fn.ptp_broken, Math.max(fn.ptp_total - fn.ptp_kept - fn.ptp_broken, 0)], backgroundColor: ['#16A34A', '#DC2626', '#E3E9F1'] }] }} /></div>
          <div className="glass card" style={{ padding: 12 }}><b>Area-wise achieved %</b>
            <ChartBox type="bar" height={220} data={{ labels: d.by_area.map(r => r.label), datasets: [{ data: d.by_area.map(r => r.pct), backgroundColor: '#3B82F6' }] }} options={{ plugins: { legend: { display: false } } }} /></div>
          <div className="glass card" style={{ padding: 12 }}><b>Recovery % by bucket (DPD)</b>
            <ChartBox type="bar" height={220} data={{ labels: d.by_dpd.map(r => r.label), datasets: [{ data: d.by_dpd.map(r => r.pct), backgroundColor: '#1D4ED8' }] }} options={{ plugins: { legend: { display: false } } }} /></div>
          <div className="glass card" style={{ padding: 12 }}><b>Contact aging (pending ₹)</b>
            <ChartBox type="bar" height={220} data={{ labels: d.aging.map(r => r.label), datasets: [{ data: d.aging.map(r => r.pending), backgroundColor: '#D97706' }] }} options={{ plugins: { legend: { display: false } } }} /></div>
          {ov && <div className="glass card" style={{ padding: 12 }}><b>Recovery % across products</b>
            <ChartBox type="bar" height={220} data={{ labels: ov.by_product.map(r => r.label), datasets: [{ data: ov.by_product.map(r => r.pct), backgroundColor: '#16A34A' }] }} options={{ indexAxis: 'y', plugins: { legend: { display: false } } }} /></div>}
        </div>

        {/* Leaderboard (editable target) */}
        <div className="glass card" style={{ padding: 12, marginTop: 14, display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
          <b>Target %</b>
          <span className="muted" style={{ fontSize: 12.5 }}>One goal for every FOS &amp; caller on {sel.bank} · {sel.product} — set it once (e.g. 85) and it applies to all.</span>
          <div style={{ flex: 1 }} />
          {canTarget
            ? <input className="input" style={{ width: 90, textAlign: 'center', fontWeight: 700 }} type="number" min="0" max="100"
                key={d.product_target} defaultValue={d.product_target || ''} placeholder="e.g. 85"
                onBlur={saveTarget} onKeyDown={e => { if (e.key === 'Enter') e.target.blur(); }} />
            : <span className="badge allocated" style={{ fontSize: 14 }}>{d.product_target || 0}%</span>}
        </div>

        <div id="mis-leaderboard" className="glass card" style={{ padding: 10, marginTop: 14 }}>
          <div className="section-h"><h3 style={{ margin: 0 }}>FOS performance &amp; leaderboard</h3>
            <div style={{ display: 'flex', gap: 6 }}><button className="btn sm" onClick={() => dl('leaderboard')}>⬇</button>
              <button className="btn sm" onClick={() => printTable('Leaderboard', ['#', 'Employee', 'Count', 'Unpaid', 'Paid', 'ENR', 'Target %', 'Target ENR', 'Achieved %', 'Achieved ENR', 'Gap ENR', 'To target %', 'Pending visit', 'Cash coll'], lb.map((r, i) => [i + 1, r.emp, r.count, r.unpaid, r.paid, money(r.enr), r.target_pct + '%', money(r.target_enr), r.achieved_pct + '%', money(r.achieved_enr), money(r.gap_enr), r.to_target_pct + '%', r.pending_visit, money(r.cash_coll)]))}>🖨</button></div></div>
          <div className="tablewrap"><table><thead><tr>
            <th>#</th><th></th><th>Employee</th><th>Count</th><th>Unpaid</th><th>Paid</th><th>ENR</th><th>Target %</th><th>Target ENR</th>
            <th>Achieved %</th><th>Achieved ENR</th><th>Gap ENR</th><th>To target</th><th>Pend. visit</th><th>Cash coll</th></tr></thead>
            <tbody>{lb.map((r, i) => <tr key={i}>
              <td>{i + 1}</td><td><span style={{ display: 'inline-block', width: 9, height: 9, borderRadius: '50%', background: STATUS_COLOR[r.status] || '#c9ced8' }} /></td>
              <td><b>{r.emp}</b></td><td>{r.count}</td><td>{r.unpaid}</td><td style={{ color: 'var(--good)' }}>{r.paid}</td>
              <td className="mono">{money(r.enr)}</td>
              <td>{r.target_pct}%</td>
              <td className="mono">{money(r.target_enr)}</td>
              <td><b>{r.achieved_pct}%</b></td><td className="mono" style={{ color: 'var(--good)' }}>{money(r.achieved_enr)}</td>
              <td className="mono" style={{ color: 'var(--bad)' }}>{money(r.gap_enr)}</td><td>{r.to_target_pct}%</td>
              <td style={{ color: 'var(--warn)' }}>{r.pending_visit}</td><td className="mono">{money(r.cash_coll)}</td></tr>)}
            </tbody></table></div>
        </div>

        {d.caller_leaderboard && <div className="glass card" style={{ padding: 10, marginTop: 14 }}>
          <div className="section-h"><h3 style={{ margin: 0 }}>Caller performance &amp; leaderboard</h3></div>
          <div className="tablewrap"><table><thead><tr>
            <th>#</th><th></th><th>Caller</th><th>Count</th><th>Unpaid</th><th>Paid</th><th>ENR</th><th>Target %</th><th>Target ENR</th>
            <th>Achieved %</th><th>Achieved ENR</th><th>Gap ENR</th><th>To target</th><th>Cash coll</th></tr></thead>
            <tbody>{d.caller_leaderboard.map((r, i) => <tr key={i}>
              <td>{i + 1}</td><td><span style={{ display: 'inline-block', width: 9, height: 9, borderRadius: '50%', background: STATUS_COLOR[r.status] || '#c9ced8' }} /></td>
              <td><b>{r.emp}</b></td><td>{r.count}</td><td>{r.unpaid}</td><td style={{ color: 'var(--good)' }}>{r.paid}</td>
              <td className="mono">{money(r.enr)}</td><td>{r.target_pct}%</td><td className="mono">{money(r.target_enr)}</td>
              <td><b>{r.achieved_pct}%</b></td><td className="mono" style={{ color: 'var(--good)' }}>{money(r.achieved_enr)}</td>
              <td className="mono" style={{ color: 'var(--bad)' }}>{money(r.gap_enr)}</td><td>{r.to_target_pct}%</td>
              <td className="mono">{money(r.cash_coll)}</td></tr>)}
            </tbody></table></div>
        </div>}

        {TABLES.map(([tk, cols]) => <MisTable key={tk} tk={tk} cols={cols} />)}
      </>}

      {full && d && (
        <div className="modal-bg" onClick={() => setFull(false)}>
          <div className="modal glass" onClick={e => e.stopPropagation()} style={{ maxWidth: '96vw', width: '96vw', maxHeight: '92vh', overflow: 'auto' }}>
            <div className="section-h" style={{ position: 'sticky', top: 0, background: 'var(--bg)', zIndex: 3, paddingBottom: 8 }}>
              <h3 style={{ margin: 0 }}>Full MIS sheet — {sel.bank} · {sel.product}</h3>
              <div style={{ display: 'flex', gap: 6 }}>
                <button className="btn sm" onClick={() => dl(Object.keys(d.table_names || {}).join(','))}>⬇ Excel</button>
                <button className="btn sm" onClick={printAll}>🖨 Print</button>
                <button className="btn ghost sm" onClick={() => setFull(false)}>✕</button>
              </div>
            </div>
            <div style={{ fontSize: 12.5 }}>
              {sheetTables().map(([title, cols, rows], ti) => (
                <div key={ti} style={{ marginTop: 12 }}>
                  <div style={{ fontWeight: 700, color: 'var(--gold)', margin: '10px 0 4px' }}>{title}</div>
                  <div className="tablewrap"><table className="mis-grid">
                    <thead><tr>{cols.map(c => <th key={c[0]}>{c[1]}</th>)}</tr></thead>
                    <tbody>{rows.map((r, i) => <tr key={i}>{cols.map(c => {
                      const v = r[c[0]]; const pct = /(_pct$|^pct$)/.test(c[0]) && typeof v === 'number';
                      return <td key={c[0]} className={typeof v === 'number' ? 'mono' : ''}
                        style={pct ? { background: v >= 60 ? 'rgba(22,163,74,.14)' : v >= 30 ? 'rgba(217,119,6,.14)' : 'rgba(220,38,38,.12)', fontWeight: 600 } : null}>{fmtCell(c[0], v)}</td>;
                    })}</tr>)}</tbody></table></div>
                  {rows.length === 0 && <div className="muted" style={{ padding: 8 }}>No data.</div>}
                </div>))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

/* ==================== Bank feedback sheet (per product, per day) ==================== */
function FeedbackView({ user }) {
  const [cfg, setCfg] = useState(null);
  const [prods, setProds] = useState(null);
  const [sel, setSel] = useState(null);
  const [day, setDay] = useState(new Date().toISOString().slice(0, 10));
  const [data, setData] = useState(null);
  const [err, setErr] = useState('');
  const [filters, setFilters] = useState({});
  const [search, setSearch] = useState('');           // global search across every column
  const [picked, setPicked] = useState({});           // selected row ids
  const [colMenu, setColMenu] = useState(false);
  const [dlCols, setDlCols] = useState(null);          // set of column keys to include in download
  const [busy, setBusy] = useState(false);
  const [setupErr, setSetupErr] = useState('');

  const loadSetup = () => {
    setSetupErr('');
    api('/api/feedback/config').then(c => { setCfg(c); setDlCols(new Set(c.columns.map(x => x.key))); })
      .catch(e => setSetupErr((e && e.message) || 'Could not load the feedback format. Restart the server if you just updated.'));
    api('/api/cases/product-summary').then(rows => {
      const seen = {}, list = [];
      (rows || []).forEach(r => { const k = r.bank + '||' + r.product + '||' + (r.branch || ''); if (!seen[k] && r.product !== '—') { seen[k] = 1; list.push({ bank: r.bank, product: r.product, branch: r.branch || '' }); } });
      setProds(list); if (list[0]) setSel(list[0]);
    }).catch(() => setProds([]));
  };
  useEffect(() => { loadSetup(); }, []);

  const qbase = () => sel ? `bank=${encodeURIComponent(sel.bank)}&product=${encodeURIComponent(sel.product)}&day=${day}` : '';
  const load = () => { if (!sel) { setData(null); return; } api('/api/feedback?' + qbase()).then(setData).catch(e => setErr(e.message || 'Could not load')); };
  useEffect(() => { setErr(''); setData(null); setPicked({}); load(); }, [sel, day]);
  useDataChanged(() => load());

  const setCell = (row, col, val) => {
    setData(d => ({ ...d, rows: d.rows.map(r => r.id === row.id ? { ...r, [col.key]: val } : r) }));
    api('/api/feedback/' + row.id, { method: 'PATCH', body: { field: col.key, value: val } }).catch(() => { setErr('Save failed — reloading'); load(); });
  };
  const refresh = () => { if (!sel) return; setBusy(true); api('/api/feedback/refresh?' + qbase(), { method: 'POST' }).then(() => { load(); toast('Pulled latest from call & visit logs'); }).catch(() => {}).finally(() => setBusy(false)); };

  const cols = cfg ? cfg.columns : [];
  const rows = data ? data.rows : [];
  const gq = search.trim().toLowerCase();
  const gdigits = gq.replace(/\D/g, '');
  const matchSearch = (r) => { if (!gq) return true;
    const vals = [r.customer, r.phone, ...cols.map(c => r[c.key])];
    return vals.some(v => v != null && String(v).toLowerCase().includes(gq)) ||
      (gdigits && vals.some(v => v != null && String(v).replace(/\D/g, '').includes(gdigits))); };
  const shown = rows.filter(r => matchSearch(r) &&
    Object.keys(filters).every(k => { const f = (filters[k] || '').toLowerCase(); return !f || String(r[k] == null ? '' : r[k]).toLowerCase().includes(f); }));
  const allPicked = shown.length > 0 && shown.every(r => picked[r.id]);
  const toggleAll = () => { if (allPicked) setPicked({}); else { const m = {}; shown.forEach(r => m[r.id] = true); setPicked(m); } };
  const pickedIds = Object.keys(picked).filter(id => picked[id]);

  const doDownload = () => {
    if (!sel) return;
    const keys = cols.filter(c => dlCols.has(c.key)).map(c => c.key).join(',');
    let url = '/api/feedback/download?' + qbase() + '&columns=' + encodeURIComponent(keys);
    if (pickedIds.length) url += '&ids=' + pickedIds.join(',');
    download(url, `feedback_${sel.bank}_${sel.product}_${day}.xlsx`);
  };

  if (setupErr) return <div className="glass card" style={{ padding: 20, color: 'var(--warn)' }}>
    Couldn’t load Bank Feedback: {setupErr}<br /><span className="muted" style={{ fontSize: 12.5 }}>If you just updated the app, restart the server (run_local.bat) and reload.</span>
    <div style={{ marginTop: 10 }}><button className="btn sm" onClick={loadSetup}>↻ Retry</button></div></div>;
  if (!cfg || !prods) return <Loader />;
  if (!prods.length) return <div className="glass card muted" style={{ padding: 24, textAlign: 'center' }}>No products with cases yet. Upload a product file first.</div>;

  const cellInput = (row, col) => {
    if (col.readonly) return <span>{row[col.key] || '—'}</span>;
    const v = row[col.key] == null ? '' : row[col.key];
    if (col.type === 'code') return (
      <select className="input" style={{ minWidth: 120, padding: '3px 6px', fontSize: 12.5 }} value={v} onChange={e => setCell(row, col, e.target.value)}>
        <option value=""></option>{(cfg.codes[col.code] || []).map(o => <option key={o} value={o}>{o}</option>)}
      </select>);
    if (col.type === 'date') return <input type="date" className="input" style={{ minWidth: 130, padding: '3px 6px', fontSize: 12.5 }}
      value={/^\d{4}-\d{2}-\d{2}$/.test(v) ? v : ''} onChange={e => setCell(row, col, e.target.value)} title={v && !/^\d{4}-/.test(v) ? v : ''} />;
    return <input className="input" style={{ minWidth: col.key.includes('remark') ? 200 : 120, padding: '3px 6px', fontSize: 12.5 }}
      defaultValue={v} onBlur={e => { if (e.target.value !== String(v)) setCell(row, col, e.target.value); }} onKeyDown={e => { if (e.key === 'Enter') e.target.blur(); }} />;
  };

  return (
    <div>
      <div className="toolbar" style={{ flexWrap: 'wrap', gap: 8, position: 'relative' }}>
        <select className="input" style={{ maxWidth: 260 }} value={sel ? sel.bank + '||' + sel.product : ''}
          onChange={e => { const [b, p] = e.target.value.split('||'); setSel({ bank: b, product: p }); }}>
          {prods.map((p, i) => <option key={i} value={p.bank + '||' + p.product}>{p.bank} · {p.product}</option>)}
        </select>
        <input type="date" className="input" style={{ maxWidth: 170 }} value={day} onChange={e => setDay(e.target.value)} />
        <input className="input" style={{ minWidth: 220 }} value={search} onChange={e => setSearch(e.target.value)}
          placeholder="🔍 Search name / phone / any column" />
        {search && <button className="btn ghost sm" onClick={() => setSearch('')}>✕</button>}
        <button className="btn sm" disabled={busy} onClick={refresh}>{busy ? '…' : '↻ Pull from logs'}</button>
        <div style={{ flex: 1 }} />
        <span className="muted" style={{ fontSize: 12 }}>{shown.length} of {rows.length} rows{pickedIds.length ? ` · ${pickedIds.length} selected` : ''}</span>
        <button className="btn sm" onClick={() => setColMenu(v => !v)}>⚙ Columns</button>
        <button className="btn gold" onClick={doDownload}>⬇ Download {pickedIds.length ? 'selected' : 'full'}</button>
        {colMenu && (
          <div className="glass card" style={{ position: 'absolute', right: 0, top: 42, zIndex: 30, padding: 10, minWidth: 220, maxHeight: 320, overflow: 'auto', boxShadow: 'var(--shadow)' }}>
            <div style={{ fontWeight: 600, marginBottom: 6, fontSize: 13 }}>Columns to download</div>
            {cols.map(c => <label key={c.key} style={{ display: 'flex', gap: 8, alignItems: 'center', fontSize: 13, padding: '3px 2px', cursor: 'pointer' }}>
              <input type="checkbox" checked={dlCols.has(c.key)} onChange={() => setDlCols(s => { const n = new Set(s); n.has(c.key) ? n.delete(c.key) : n.add(c.key); return n; })} />{c.label}</label>)}
          </div>
        )}
      </div>
      <p className="muted" style={{ fontSize: 12.5, margin: '2px 2px 10px' }}>Daily bank feedback for {sel.bank} · {sel.product}. Rows auto-fill from caller & FOS logs and stay editable — your edits are kept. Saved per day; use the date picker for 3-day / weekly hand-offs.</p>
      {err && <div className="glass card" style={{ color: 'var(--bad)', marginBottom: 10 }}>{err}</div>}
      {!data ? <Loader /> : shown.length === 0 ? <div className="glass card muted" style={{ padding: 20, textAlign: 'center' }}>{(search || Object.values(filters).some(Boolean)) ? 'No rows match your search / filters.' : 'No cases for this product / day.'}</div> :
        <div className="glass card" style={{ padding: 6 }}>
          <div className="tablewrap" style={{ maxHeight: '70vh', overflow: 'auto' }}><table>
            <thead>
              <tr>
                <th style={{ width: 30 }}><input type="checkbox" checked={allPicked} onChange={toggleAll} /></th>
                <th>Customer</th>
                {cols.map(c => <th key={c.key}>{c.label}</th>)}
              </tr>
              <tr>
                <th></th><th></th>
                {cols.map(c => <th key={c.key}><input className="input" style={{ width: '100%', minWidth: 90, padding: '2px 5px', fontSize: 11 }} placeholder="filter" value={filters[c.key] || ''} onChange={e => setFilters(f => ({ ...f, [c.key]: e.target.value }))} /></th>)}
              </tr>
            </thead>
            <tbody>{shown.map(r => <tr key={r.id}>
              <td><input type="checkbox" checked={!!picked[r.id]} onChange={() => setPicked(p => ({ ...p, [r.id]: !p[r.id] }))} /></td>
              <td style={{ whiteSpace: 'nowrap' }}><b style={{ fontSize: 12.5 }}>{r.customer || '—'}</b>{r.phone && <div className="muted" style={{ fontSize: 11 }}>{r.phone}</div>}</td>
              {cols.map(c => <td key={c.key}>{cellInput(r, c)}</td>)}
            </tr>)}</tbody>
          </table></div>
        </div>}
    </div>
  );
}

/* ==================== Escalations (pull hard cases off FOS/caller) ==================== */
function EscalationsView({ user }) {
  const [q, setQ] = useState(''); const [results, setResults] = useState(null);
  const [mine, setMine] = useState([]); const [drawer, setDrawer] = useState(null); const [busy, setBusy] = useState(0);
  const money = v => '₹' + Math.round(Number(v) || 0).toLocaleString('en-IN');
  const loadMine = () => api('/api/cases/escalated?mine=false').then(setMine).catch(() => setMine([]));
  const search = () => {
    const p = new URLSearchParams({ limit: '60' }); if (q) p.set('search', q);
    api('/api/cases?' + p).then(rows => setResults((rows || []).filter(c => !c.escalated)
      .sort((a, b) => Number(b.pending_amount || 0) - Number(a.pending_amount || 0)))).catch(() => setResults([]));
  };
  useEffect(() => { loadMine(); }, []);
  useDataChanged(() => { loadMine(); if (results) search(); });
  const escalate = (c) => { setBusy(c.id); api('/api/cases/' + c.id + '/escalate', { method: 'POST', body: {} })
    .then(() => { toast('Escalated to you — removed from ' + (c.customer_name || 'the') + '’s handler'); loadMine(); search(); })
    .catch(e => toast(e.message, 'err')).finally(() => setBusy(0)); };
  const release = (c) => { setBusy(c.id); api('/api/cases/' + c.id + '/deescalate', { method: 'POST', body: {} })
    .then(() => { toast('Released back to the pool'); loadMine(); }).catch(e => toast(e.message, 'err')).finally(() => setBusy(0)); };

  return (
    <div>
      <p className="muted" style={{ fontSize: 13, margin: '0 2px 10px' }}>Pull a hard or high-value case off its field agent / caller and own it yourself. It leaves their queue and individual performance, but stays counted in MIS &amp; the bank feedback sheet.</p>
      <div className="glass card" style={{ padding: 12, marginBottom: 14 }}>
        <div className="toolbar">
          <input className="input" placeholder="Search by name, account, phone, pincode…" value={q}
            onChange={e => setQ(e.target.value)} onKeyDown={e => e.key === 'Enter' && search()} />
          <button className="btn gold" onClick={search}>Search</button>
        </div>
        {results && (results.length === 0 ? <p className="muted" style={{ margin: '8px 2px 0' }}>No matching un-escalated cases.</p> :
          <div className="tablewrap" style={{ marginTop: 10, maxHeight: 340, overflow: 'auto' }}><table>
            <thead><tr><th>Customer</th><th>Bank·Product</th><th>Pending</th><th>ENR</th><th>Handler</th><th>Score</th><th></th></tr></thead>
            <tbody>{results.map(c => <tr key={c.id}>
              <td style={{ cursor: 'pointer' }} onClick={() => setDrawer(c)}><b style={{ color: 'var(--gold)' }}>{c.customer_name || '—'}</b><div className="muted" style={{ fontSize: 11 }}>{c.account_no}</div></td>
              <td className="muted">{c.bank} · {c.product || '—'}</td>
              <td className="mono" style={{ color: 'var(--warn)' }}>{money(c.pending_amount)}</td>
              <td className="mono">{money(c.enr)}</td>
              <td className="muted" style={{ fontSize: 12 }}>{c.fos_name || c.caller_name || '—'}</td>
              <td><PropBadge score={c.propensity} /></td>
              <td><button className="btn sm gold" disabled={busy === c.id} onClick={() => escalate(c)}>Escalate to me</button></td></tr>)}</tbody></table></div>)}
      </div>

      <div className="glass card" style={{ padding: 6 }}>
        <div className="section-h" style={{ padding: '6px 8px' }}><h3 style={{ margin: 0, fontSize: 15 }}>Escalated cases ({mine.length})</h3></div>
        {mine.length === 0 ? <div className="muted" style={{ padding: 16, textAlign: 'center' }}>Nothing escalated yet.</div> :
          <div className="tablewrap" style={{ maxHeight: 420, overflow: 'auto' }}><table>
            <thead><tr><th>Customer</th><th>Bank·Product</th><th>Pending</th><th>Status</th><th>Paid</th><th>Dispo</th><th></th></tr></thead>
            <tbody>{mine.map(c => <tr key={c.id}>
              <td style={{ cursor: 'pointer' }} onClick={() => setDrawer(c)}><b style={{ color: 'var(--gold)' }}>{c.customer_name || '—'}</b><div className="muted" style={{ fontSize: 11 }}>{c.account_no}</div></td>
              <td className="muted">{c.bank} · {c.product || '—'}</td>
              <td className="mono" style={{ color: 'var(--warn)' }}>{money(c.pending_amount)}</td>
              <td><StatusBadge s={c.status} /></td><td><PaidBadge s={c.paid_status} /></td>
              <td className="muted">{c.disposition || '—'}</td>
              <td><button className="btn sm" disabled={busy === c.id} onClick={() => release(c)}>Release</button></td></tr>)}</tbody></table></div>}
      </div>
      {drawer && <CaseDrawer c={drawer} onClose={() => setDrawer(null)} onChanged={() => { loadMine(); if (results) search(); }} />}
    </div>
  );
}

/* ==================== My Performance (caller / FOS own scorecard) ==================== */
function MyPerformance({ user }) {
  const [monthB, setMonthB] = useState('current');
  const [tab, setTab] = useState('scorecard');   // 'scorecard' | 'cycle'
  const [d, setD] = useState(null); const [err, setErr] = useState('');
  const money = v => '₹' + Math.round(Number(v) || 0).toLocaleString('en-IN');
  const load = () => api('/api/mis/my-performance?month_bucket=' + monthB).then(setD).catch(e => setErr(e.message || 'Could not load'));
  useEffect(() => { load(); }, [monthB]);
  useDataChanged(load);   // live: refresh my scorecard whenever a payment/log lands
  const tabs = (
    <div className="toolbar" style={{ marginBottom: 12 }}>
      <div className={cx('chip', tab === 'scorecard' && 'on')} onClick={() => setTab('scorecard')}>🏆 My scorecard</div>
      <div className={cx('chip', tab === 'cycle' && 'on')} onClick={() => setTab('cycle')}>🔄 Cycle-wise</div>
    </div>
  );
  if (tab === 'cycle') return <div>{tabs}<CycleMIS compact /></div>;
  if (err) return <div>{tabs}<div className="glass card" style={{ color: 'var(--bad)' }}>{err}</div></div>;
  if (!d) return <div>{tabs}<Loader /></div>;
  const t = d.totals || {};
  const roleWord = d.as_fos ? 'field agents' : 'callers';
  return (
    <div>
      {tabs}
      <div className="toolbar" style={{ marginBottom: 12, alignItems: 'center', gap: 10 }}>
        <select className="sv-btn" value={monthB} onChange={e => setMonthB(e.target.value)} title="Each month is a separate book">
          <option value="current">This month</option>
          <option value="next">Next month</option>
          <option value="">All months</option>
        </select>
        <span className="muted" style={{ fontSize: 12 }}>Each portfolio is kept separate for the month you pick — nothing is merged.</span>
      </div>

      <div className="kpis">
        <StatCard icon="📁" label="My cases" accent="blue" value={(t.count || 0).toLocaleString('en-IN')}
          sub={<span>{t.paid || 0} paid · {t.unpaid || 0} open</span>} />
        <StatCard icon="💼" label="My book (ENR)" value={money(t.enr)} sub="Total receivables assigned to me" />
        <StatCard icon="✅" label="Achieved (ENR)" accent="green" value={money(t.paid_enr)} valueColor="var(--good)"
          sub={<span><b style={{ color: 'var(--good)' }}>{t.achieved_pct || 0}%</b> of my book</span>} />
        <StatCard icon="💰" label="Cash collected" accent="amber" value={money(t.collected)}
          sub={<span>{money(t.pending)} still pending</span>} />
      </div>

      {d.trends && <TrendStrip trends={d.trends} title="My cash collected — FTD / MTD / LMTD / Overall (all my portfolios)" />}

      {(!d.portfolios || !d.portfolios.length) && <div className="glass card muted" style={{ marginTop: 12 }}>
        No portfolios assigned to you for this month yet.</div>}

      {(d.portfolios || []).map((p, i) => (
        <div key={i} className="glass card" style={{ marginTop: 14, padding: 12 }}>
          <div className="section-h">
            <h3 style={{ margin: 0 }}>{p.label}</h3>
            {p.rank && <span className="badge paid" style={{ fontSize: 12 }}>🏆 Rank #{p.rank} of {p.field_size}</span>}
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill,minmax(128px,1fr))', gap: 10, margin: '10px 0 12px' }}>
            <div className="glass card" style={{ padding: 10 }}><div className="muted" style={{ fontSize: 12 }}>Cases</div><b style={{ fontSize: 18 }}>{p.count}</b><div className="muted" style={{ fontSize: 11 }}>{p.paid} paid · {p.unpaid} open</div></div>
            <div className="glass card" style={{ padding: 10 }}><div className="muted" style={{ fontSize: 12 }}>My ENR</div><b style={{ fontSize: 18 }}>{money(p.enr)}</b></div>
            <div className="glass card" style={{ padding: 10 }}><div className="muted" style={{ fontSize: 12 }}>Achieved</div><b style={{ fontSize: 18, color: 'var(--good)' }}>{p.achieved_pct}%</b><div className="muted" style={{ fontSize: 11 }}>{money(p.paid_enr)}</div></div>
            <div className="glass card" style={{ padding: 10 }}><div className="muted" style={{ fontSize: 12 }}>Target</div><b style={{ fontSize: 18 }}>{p.target_pct}%</b><div className="muted" style={{ fontSize: 11 }}>{p.target_pct ? money(p.target_enr) : 'not set'}</div></div>
            <div className="glass card" style={{ padding: 10 }}><div className="muted" style={{ fontSize: 12 }}>To target</div><b style={{ fontSize: 18, color: p.to_target_pct >= 100 ? 'var(--good)' : 'var(--warn)' }}>{p.to_target_pct}%</b>{p.gap_enr > 0 && <div className="muted" style={{ fontSize: 11 }}>gap {money(p.gap_enr)}</div>}</div>
            <div className="glass card" style={{ padding: 10 }}><div className="muted" style={{ fontSize: 12 }}>Cash</div><b style={{ fontSize: 18 }}>{money(p.collected)}</b><div className="muted" style={{ fontSize: 11 }}>{money(p.pending)} pending</div></div>
          </div>
          {p.trends && <TrendStrip trends={p.trends} compact title="Cash collected — FTD / MTD / LMTD / Overall" />}
          {p.leaderboard && p.leaderboard.length > 0 && <div style={{ marginTop: 12 }}>
            <div className="muted" style={{ fontSize: 12, marginBottom: 6 }}>Leaderboard — {roleWord} on this portfolio (you are highlighted)</div>
            <div className="tablewrap"><table><thead><tr>
              <th>#</th><th>Agent</th><th>Cases</th><th>ENR</th><th>Achieved %</th><th>Paid ENR</th><th>Cash coll</th></tr></thead>
              <tbody>{p.leaderboard.map((r, j) => <tr key={j} style={r.you ? { background: 'rgba(37,99,235,.12)', fontWeight: 700 } : null}>
                <td>{r.rank}</td><td>{r.name}{r.you ? ' (you)' : ''}</td><td>{r.count}</td>
                <td className="mono">{money(r.enr)}</td><td><b>{r.achieved_pct}%</b></td>
                <td className="mono" style={{ color: 'var(--good)' }}>{money(r.paid_enr)}</td>
                <td className="mono">{money(r.collected)}</td></tr>)}
              </tbody></table></div>
          </div>}
        </div>
      ))}
    </div>
  );
}

/* ==================== Live Sheet (telecaller spreadsheet) ==================== */
const SHEET_COLS = [
  { k: 'customer_name', t: 'Customer', type: 'text' },
  { k: 'phone', t: 'Phone', type: 'text', edit: true },
  { k: 'alt_phone', t: 'Alt phone', type: 'text', edit: true },
  { k: 'new_phone', t: 'New phone', type: 'text', edit: true },
  { k: 'new_address', t: 'New address', type: 'text', edit: true },
  { k: 'card_no', t: 'Card no', type: 'text' },
  { k: 'account_no', t: 'A/C no', type: 'text' },
  { k: 'bank', t: 'Bank', type: 'text' },
  { k: 'branch', t: 'Branch', type: 'text' },
  { k: 'product', t: 'Product', type: 'text' },
  { k: 'bucket', t: 'Bucket', type: 'text' },
  { k: 'cycle', t: 'Cycle', type: 'text' },
  { k: 'month', t: 'Month', type: 'text' },
  { k: 'total_outstanding', t: 'TOS', type: 'num', edit: true },
  { k: 'principal_outstanding', t: 'POS / PRI', type: 'num', edit: true },
  { k: 'enr', t: 'ENR', type: 'num' },
  { k: 'norm_amount', t: 'OD NORM', type: 'num', edit: true },
  { k: 'stab_amount', t: 'OD STAB', type: 'num', edit: true },
  { k: 'rollback_amount', t: 'ROLLBACK', type: 'num', edit: true },
  { k: 'min_amount_due', t: 'Min due', type: 'num', edit: true },
  { k: 'received_amount', t: 'Amount', type: 'num', edit: true },
  { k: 'pending_amount', t: 'Pending', type: 'num', edit: true },
  { k: 'norm_stab', t: 'N/S paid', type: 'sel', edit: true, opts: ['', 'NORM', 'STAB', 'ROLLBACK'] },
  { k: 'status', t: 'Status', type: 'sel', edit: true, opts: ['', 'new', 'ptp', 'callback', 'paid', 'closed'] },
  { k: 'paid_status', t: 'Paid', type: 'sel', edit: true, opts: ['', 'PAID', 'PARTIAL', 'UNPAID'] },
  { k: 'disposition', t: 'Disposition', type: 'sel', edit: true, opts: ['', 'PTP', 'RTP', 'PAID', 'CALLBACK', 'NO_CONTACT', 'WRONG_NUMBER', 'REFUSED'] },
  { k: 'follow_up_date', t: 'Follow-up', type: 'date', edit: true },
  { k: 'remarks', t: 'Remarks', type: 'text', edit: true },
  { k: 'caller_name', t: 'Caller', type: 'text', edit: true },
  { k: 'fos_name', t: 'FOS', type: 'text', edit: true },
  { k: 'team', t: 'Area', type: 'text', edit: true },
  { k: 'team_lead', t: 'Team lead', type: 'text', edit: true },
  { k: 'cat', t: 'Cat', type: 'text', edit: true },
  { k: 'segment', t: 'Segment', type: 'text' },
  { k: 'final_status', t: 'Status', type: 'text' },              // BL: NORM / STAB / FLOW
  // ---- PL/BL loan / caller working columns (stored in extra) ----
  { k: 'x_emi', t: 'EMI', type: 'num', data: true, edit: true },
  { k: 'x_pos_ovd', t: 'POS OVD', type: 'num', data: true, edit: true },
  { k: 'x_interest_ovd', t: 'Int OVD', type: 'num', data: true, edit: true },
  { k: 'x_charges_ovd', t: 'Charges OVD', type: 'num', data: true, edit: true },
  { k: 'x_tot_od', t: 'Total OD', type: 'num', data: true, edit: true },
  { k: 'x_disbursement', t: 'Disbursement', type: 'num', data: true },
  { k: 'x_risk', t: 'Risk cat', type: 'text', data: true },
  { k: 'x_city', t: 'City', type: 'text', data: true },
  { k: 'x_od', t: 'OD', type: 'num', data: true, edit: true },
  { k: 'x_ptp_date', t: 'PTP date', type: 'text', data: true, edit: true },
  { k: 'x_paid_date', t: 'Paid date', type: 'text', data: true, edit: true },
  { k: 'x_mode_of_payment', t: 'Mode', type: 'text', data: true, edit: true },
  { k: 'x_tenure', t: 'Tenure', type: 'num', data: true },
  { k: 'x_balance_tenure', t: 'Bal tenure', type: 'num', data: true },
  { k: 'x_billed_emi', t: 'Billed EMI', type: 'num', data: true },
  { k: 'x_traced_contact', t: 'Traced no', type: 'text', data: true, edit: true },
  { k: 'x_last_payment_date', t: 'Last pay dt', type: 'text', data: true },
  { k: 'x_last_payment_amount', t: 'Last pay amt', type: 'num', data: true },
  { k: 'x_organisation', t: 'Organisation', type: 'text', data: true },
  { k: 'x_designation', t: 'Designation', type: 'text', data: true },
  { k: 'address', t: 'Address 1', type: 'text' },
  { k: 'address2', t: 'Address 2', type: 'text' },
  { k: 'pincode', t: 'Pincode', type: 'text' },
  { k: 'propensity', t: 'Score', type: 'num' },
  { k: 'updated_by_name', t: 'Last changed by', type: 'text' },
];
const SHEET_DEFAULT_VISIBLE = ['customer_name', 'phone', 'new_phone', 'new_address', 'bank', 'product', 'enr', 'norm_amount', 'stab_amount', 'received_amount', 'norm_stab', 'paid_status', 'status', 'disposition', 'caller_name', 'fos_name', 'remarks'];
// Column preset matching the AXIS PL/BL callers' working sheet (TOS/PRI/EMI, OD components,
// OD STAB & OD NORM, STATUS = NORM/STAB/FLOW).
const SHEET_VISIBLE_PLBL = ['bucket', 'account_no', 'customer_name', 'cycle', 'phone', 'x_disbursement',
  'total_outstanding', 'principal_outstanding', 'x_emi', 'x_pos_ovd', 'x_interest_ovd', 'x_charges_ovd',
  'x_tot_od', 'x_mode_of_payment', 'stab_amount', 'norm_amount', 'received_amount',
  'paid_status', 'final_status', 'norm_stab', 'caller_name', 'address', 'team', 'pincode', 'fos_name',
  'x_last_payment_amount', 'x_risk', 'x_tenure', 'x_balance_tenure', 'remarks'];
const SHEET_FUNCS = { ROUND: Math.round, ABS: Math.abs, MIN: Math.min, MAX: Math.max, SQRT: Math.sqrt, IF: (c, a, b) => (c ? a : b) };
function sheetSafeCalc(expr) {
  if (!/^[-+*/%(). ,0-9<>=?:A-Za-z_]*$/.test(expr)) throw new Error('bad expression');
  const names = Object.keys(SHEET_FUNCS);
  const fn = new Function(...names, 'return (' + expr + ');');
  return fn(...names.map(n => SHEET_FUNCS[n]));
}
function sheetFmt(v) {
  if (v === null || v === undefined || v === '') return '';
  if (typeof v === 'number' && isFinite(v)) return (Math.round(v * 100) / 100).toLocaleString('en-IN');
  return v;
}
function sheetWaNumber(p) {
  let n = String(p || '').replace(/[^\d+]/g, '');
  if (n.startsWith('+')) return n.slice(1);
  n = n.replace(/^0+/, '');
  return n.length === 10 ? '91' + n : n;
}

function SheetView({ user, config }) {
  const [rows, setRows] = React.useState([]);
  const [prefs, setPrefs] = React.useState(null);
  const [err, setErr] = React.useState('');
  const [drawer, setDrawer] = React.useState(null);
  const [sort, setSort] = React.useState(null);
  const [filters, setFilters] = React.useState({});
  const [colMenu, setColMenu] = React.useState(false);
  const [calc, setCalc] = React.useState('=SUM([pending_amount])');
  const [calcRes, setCalcRes] = React.useState('');
  const [live, setLive] = React.useState(false);
  const [search, setSearch] = React.useState('');
  const [bankF, setBankF] = React.useState(''); const [prodF, setProdF] = React.useState('');
  const [monthB, setMonthB] = React.useState('current');   // default THIS month so months aren't merged
  const [payModal, setPayModal] = React.useState(null);   // {row, mode:'paid'|'unpaid'}
  const [presence, setPresence] = React.useState({});      // case_id -> [{id,name,role,field}]
  const wsRef = React.useRef(null);
  const saveTimer = React.useRef(null);
  // Horizontal slide-navigation for the wide sheet — a controllable scrollbar shown ON SCREEN
  // (above the table) instead of the hard-to-reach browser scrollbar at the very bottom.
  const scrollRef = React.useRef(null);
  const [scrollPct, setScrollPct] = React.useState(0);
  const [scrollable, setScrollable] = React.useState(false);
  const syncSlider = React.useCallback(() => {
    const el = scrollRef.current; if (!el) return;
    const max = el.scrollWidth - el.clientWidth;
    setScrollable(max > 4);
    setScrollPct(max > 0 ? Math.round((el.scrollLeft / max) * 100) : 0);
  }, []);
  const slideTo = (pct) => { const el = scrollRef.current; if (!el) return;
    const max = el.scrollWidth - el.clientWidth; el.scrollLeft = (pct / 100) * max; setScrollPct(pct); };
  // ◀/▶ move by ~two columns (measured from a real header cell), so it steps like Excel
  // instead of jumping the whole width in one click.
  const nudge = (dir) => { const el = scrollRef.current; if (!el) return;
    const cell = el.querySelector('table.sv thead th');
    const colW = cell ? cell.getBoundingClientRect().width : 130;
    el.scrollBy({ left: dir * Math.max(90, colW * 2), behavior: 'smooth' }); };
  React.useEffect(() => { window.addEventListener('resize', syncSlider); return () => window.removeEventListener('resize', syncSlider); }, [syncSlider]);
  // Re-measure when the columns/rows change (a wider/narrower sheet changes the scroll range).
  React.useEffect(() => { const t = setTimeout(syncSlider, 60); return () => clearTimeout(t); }, [rows, prefs, syncSlider]);
  // head office / admin / manager / back-office / callers may flip paid/unpaid with the
  // accounting popups (callers only on their own cases — enforced by the backend scope).
  const canPayEdit = ['admin', 'headoffice', 'manager', 'backend', 'telecaller', 'teamlead'].includes(user.role);

  const monthBRef = React.useRef(monthB);
  React.useEffect(() => { monthBRef.current = monthB; }, [monthB]);
  const load = () => {
    const mb = monthBRef.current;
    return api('/api/cases?limit=2000' + (mb ? '&month_bucket=' + encodeURIComponent(mb) : ''))
      .then(d => setRows(Array.isArray(d) ? d : [])).catch(e => setErr(e.message || 'Could not load'));
  };

  // Reload the sheet whenever the month filter changes so each month's book is separate.
  React.useEffect(() => { load(); }, [monthB]);

  React.useEffect(() => {
    api('/api/sheet/prefs').then(p => setPrefs({
      visible: (p && p.visible) || SHEET_DEFAULT_VISIBLE,
      order: (p && p.order) || SHEET_COLS.map(c => c.k),
      custom: (p && p.custom) || [],
      aggs: (p && p.aggs) || {},
    })).catch(() => setPrefs({ visible: SHEET_DEFAULT_VISIBLE, order: SHEET_COLS.map(c => c.k), custom: [], aggs: {} }));
  }, []);

  // Live updates over WebSocket
  React.useEffect(() => {
    let stop = false, ws;
    const connect = () => {
      try {
        ws = new WebSocket(location.origin.replace(/^http/, 'ws') + '/ws?token=' + encodeURIComponent(store.t || ''));
        wsRef.current = ws;
        ws.onopen = () => { if (!stop) setLive(true); };
        ws.onclose = () => { setLive(false); wsRef.current = null; if (!stop) setTimeout(connect, 3000); };
        ws.onmessage = (e) => {
          try {
            const m = JSON.parse(e.data);
            if (m.type === 'case_update' && m.case) {
              setRows(rs => { const i = rs.findIndex(r => r.id === m.case.id); if (i < 0) return rs; const cp = rs.slice(); cp[i] = { ...cp[i], ...m.case }; return cp; });
            } else if (m.type === 'data_changed' || m.type === 'payment' || m.type === 'case_changed') {
              // A payment/log/edit landed anywhere (e.g. a telecaller logged a payment) —
              // pull the sheet fresh so paid/pending/status reflect it automatically.
              load();
            } else if (m.type === 'presence') {
              setPresence(p => { const cp = { ...p }; if (m.editors && m.editors.length) cp[m.case_id] = m.editors; else delete cp[m.case_id]; return cp; });
            }
          } catch (_) {}
        };
      } catch (_) { if (!stop) setTimeout(connect, 3000); }
    };
    connect();
    return () => { stop = true; try { ws && ws.close(); } catch (_) {} };
  }, []);

  // Tell everyone which row/cell I'm editing (live presence badges).
  const sendPresence = (caseId, field, editing) => {
    const ws = wsRef.current;
    if (ws && ws.readyState === 1) {
      try { ws.send(JSON.stringify({ type: editing ? 'editing' : 'editing_stop', case_id: caseId, field })); } catch (_) {}
    }
  };
  // Other people (not me) currently editing a given row.
  const othersEditing = (caseId) => (presence[caseId] || []).filter(e => e.id !== user.id);

  const allDefs = () => SHEET_COLS.concat((prefs ? prefs.custom : []).map(c => ({ ...c, custom: true })));
  const defByKey = k => allDefs().find(c => c.k === k);
  const savePrefs = (next) => { setPrefs(next); clearTimeout(saveTimer.current); saveTimer.current = setTimeout(() => api('/api/sheet/prefs', { method: 'PUT', body: next }).catch(() => {}), 600); };
  const toggleCol = (k) => { if (!prefs) return; const vis = prefs.visible.includes(k) ? prefs.visible.filter(x => x !== k) : prefs.visible.concat(k); savePrefs({ ...prefs, visible: vis }); };
  const applyPreset = (kind) => {
    if (!prefs) return;
    const want = kind === 'plbl' ? SHEET_VISIBLE_PLBL : SHEET_DEFAULT_VISIBLE;
    const known = allDefs().map(c => c.k);
    const vis = want.filter(k => known.includes(k));
    const order = vis.concat(prefs.order.filter(k => !vis.includes(k)));
    savePrefs({ ...prefs, visible: vis, order });
  };
  const addFormulaCol = () => {
    const label = window.prompt('Column name'); if (!label) return;
    const formula = window.prompt('Formula — reference columns like [pending_amount]\ne.g. =[pending_amount]*0.1 or =ROUND([received_amount]/[total_outstanding]*100)'); if (!formula) return;
    const k = 'f_' + Date.now();
    savePrefs({ ...prefs, custom: prefs.custom.concat({ k, t: label, type: 'num', formula }), order: prefs.order.concat(k), visible: prefs.visible.concat(k) });
  };
  const addDataCol = () => {
    const label = window.prompt('New column name (free text you fill per row)'); if (!label) return;
    const k = 'x_' + label.replace(/[^a-z0-9]/gi, '_').toLowerCase() + '_' + String(Date.now()).slice(-4);
    savePrefs({ ...prefs, custom: prefs.custom.concat({ k, t: label, type: 'text', data: true }), order: prefs.order.concat(k), visible: prefs.visible.concat(k) });
  };
  const visibleCols = () => (prefs ? prefs.order : SHEET_COLS.map(c => c.k)).filter(k => prefs && prefs.visible.includes(k)).map(defByKey).filter(Boolean);

  const rowFormula = (formula, row) => {
    try { return sheetSafeCalc(String(formula).replace(/^=/, '').replace(/\[([a-z_0-9]+)\]/gi, (_, k) => Number(row[k] || 0))); } catch (_) { return '—'; }
  };
  const cellVal = (row, col) => col.data ? ((row.extra || {})[col.k] ?? '') : (col.custom ? rowFormula(col.formula, row) : row[col.k]);
  const cellText = (row, col) => sheetFmt(cellVal(row, col));

  const viewRows = () => {
    let out = rows.slice();
    if (bankF) out = out.filter(r => (r.bank || '') === bankF);
    if (prodF) out = out.filter(r => (r.product || '') === prodF);
    if (search) { const q = search.toLowerCase(); out = out.filter(r =>
      String(r.customer_name || '').toLowerCase().includes(q) ||
      String(r.card_no || '').toLowerCase().includes(q) ||
      String(r.account_no || '').toLowerCase().includes(q) ||
      String(r.phone || '').toLowerCase().includes(q)); }
    Object.keys(filters).forEach(k => { const f = (filters[k] || '').toLowerCase(); if (f) out = out.filter(r => String(r[k] == null ? '' : r[k]).toLowerCase().includes(f)); });
    if (sort) { const d = defByKey(sort.k); out.sort((a, b) => { let x = d && d.custom ? rowFormula(d.formula, a) : a[sort.k], y = d && d.custom ? rowFormula(d.formula, b) : b[sort.k]; if (d && (d.type === 'num')) { x = Number(x) || 0; y = Number(y) || 0; } else { x = String(x == null ? '' : x); y = String(y == null ? '' : y); } return (x < y ? -1 : x > y ? 1 : 0) * (sort.dir === 'desc' ? -1 : 1); }); }
    return out;
  };

  const editCell = (row, col, value) => {
    // "Paid" and "Status" are linked: flipping either toward/away from paid runs the same
    // accounting popup (record a payment or revert one) so paid_status + status move together
    // and FOS/caller performance, MIS and feedback all stay in sync.
    if (canPayEdit && col.k === 'paid_status' && (value === 'PAID' || value === 'UNPAID') && (row.paid_status || '') !== value) {
      setPayModal({ row, mode: value === 'PAID' ? 'paid' : 'unpaid' });
      return;
    }
    if (canPayEdit && col.k === 'status') {
      const cur = row.status || '';
      if (value === 'paid' && cur !== 'paid') { setPayModal({ row, mode: 'paid' }); return; }
      if (cur === 'paid' && value !== 'paid') { setPayModal({ row, mode: 'unpaid' }); return; }
    }
    // Typing a collection into the Amount cell = logging a payment. If the figure goes UP on a
    // not-yet-paid case, open the payment popup (amount pre-filled, NORM/STAB) so it marks Paid,
    // credits the caller/FOS and lands in resolved cases — instead of silently editing a number.
    if (canPayEdit && col.k === 'received_amount' && (row.paid_status || '').toUpperCase() !== 'PAID') {
      const newAmt = Number(value) || 0, curRecv = Number(row.received_amount) || 0;
      if (newAmt > curRecv) { setPayModal({ row, mode: 'paid', amount: String(Math.round(newAmt - curRecv)) }); return; }
    }
    setRows(rs => rs.map(r => r.id === row.id
      ? (col.data ? { ...r, extra: { ...(r.extra || {}), [col.k]: value } } : { ...r, [col.k]: value })
      : r));
    api('/api/sheet/cell/' + row.id, { method: 'PATCH', body: { field: col.k, value } }).catch(() => { setErr('Save failed — reloading'); load(); });
  };
  const applyPayResult = (updated) => {
    setRows(rs => rs.map(r => r.id === updated.id ? { ...r, ...updated } : r));
    setPayModal(null);
  };
  const openCase = (row) => { setDrawer(row); api('/api/sheet/open/' + row.id, { method: 'POST' }).catch(() => {}); };

  const agg = (fn, k) => { const xs = viewRows().map(r => Number(r[k] || 0)); if (!xs.length) return 0; fn = fn.toUpperCase(); if (fn === 'SUM') return xs.reduce((a, b) => a + b, 0); if (fn === 'COUNT') return xs.length; if (fn === 'MIN') return Math.min(...xs); if (fn === 'MAX') return Math.max(...xs); return xs.reduce((a, b) => a + b, 0) / xs.length; };
  const runCalc = () => { try { let e = String(calc).replace(/^=/, '').replace(/(SUM|AVG|AVERAGE|MIN|MAX|COUNT)\(\s*\[([a-z_0-9]+)\]\s*\)/gi, (_, fn, k) => agg(fn === 'AVERAGE' ? 'AVG' : fn, k)); setCalcRes(sheetFmt(sheetSafeCalc(e))); } catch (_) { setCalcRes('error'); } };
  const footAgg = (col) => { if (col.type !== 'num') return ''; const mode = (prefs && prefs.aggs[col.k]) || (col.custom ? '' : 'sum'); if (!mode) return ''; const xs = viewRows().map(r => Number(cellVal(r, col)) || 0); if (!xs.length) return ''; let v = 0; if (mode === 'sum') v = xs.reduce((a, b) => a + b, 0); else if (mode === 'avg') v = xs.reduce((a, b) => a + b, 0) / xs.length; else if (mode === 'min') v = Math.min(...xs); else if (mode === 'max') v = Math.max(...xs); else if (mode === 'count') v = xs.length; return mode.toUpperCase() + ' ' + sheetFmt(v); };
  const cycleAgg = (k) => { const modes = ['sum', 'avg', 'min', 'max', 'count', '']; const cur = (prefs && prefs.aggs[k]) || 'sum'; const next = modes[(modes.indexOf(cur) + 1) % modes.length]; savePrefs({ ...prefs, aggs: { ...prefs.aggs, [k]: next } }); };

  const exportCSV = () => {
    const cols = visibleCols(); const esc = s => '"' + String(s == null ? '' : s).replace(/"/g, '""') + '"';
    const lines = [cols.map(c => esc(c.t)).join(',')].concat(viewRows().map(r => cols.map(c => esc(cellText(r, c))).join(',')));
    const blob = new Blob([lines.join('\n')], { type: 'text/csv' }); const a = document.createElement('a'); a.href = URL.createObjectURL(blob); a.download = 'recoveriq-sheet.csv'; a.click();
  };
  const exportXLSX = () => {
    if (!window.XLSX) return exportCSV();
    const cols = visibleCols(); const aoa = [cols.map(c => c.t)].concat(viewRows().map(r => cols.map(c => col_isNum(c) ? Number(cellVal(r, c)) || 0 : (cellVal(r, c) == null ? '' : cellVal(r, c)))));
    const ws = XLSX.utils.aoa_to_sheet(aoa); const wb = XLSX.utils.book_new(); XLSX.utils.book_append_sheet(wb, ws, 'Cases'); XLSX.writeFile(wb, 'recoveriq-sheet.xlsx');
  };
  const col_isNum = c => c.type === 'num';

  if (!prefs) return <div className="glass" style={{ padding: 24, borderRadius: 16 }}>Loading sheet…</div>;

  // KPI strip (computed live from the visible data)
  const today = new Date().toISOString().slice(0, 10);
  // KPIs follow the current view: a selected bank/product shows THAT portfolio's totals; with
  // "all" selected they show the overall figures. (viewRows applies the bank/product filters.)
  const kpiRows = viewRows();
  const contacted = kpiRows.filter(r => (r.last_contacted_at || '').slice(0, 10) === today).length;
  const ptp = kpiRows.filter(r => r.disposition === 'PTP' || r.status === 'ptp').length;
  const collected = kpiRows.reduce((s, r) => s + Number(r.received_amount || 0), 0);
  const pending = kpiRows.reduce((s, r) => {
    const base = Number(r.funding_amount) > 0 ? Number(r.funding_amount)
      : (Number(r.total_outstanding) > 0 ? Number(r.total_outstanding) : (Number(r.enr) || 0));
    return s + Math.max(0, base - (Number(r.received_amount) || 0));
  }, 0);
  const cols = visibleCols();

  return (
    <div className="sv-wrap">
      <style>{`
        .sv-wrap{display:flex;flex-direction:column;gap:12px;height:100%}
        .sv-kpis{display:grid;grid-template-columns:repeat(4,1fr);gap:12px}
        .sv-kpi{background:var(--glass-2);border:1px solid var(--stroke-soft);border-radius:14px;padding:12px 14px}
        .sv-kpi b{display:block;font-size:20px;color:var(--gold)}
        .sv-kpi span{font-size:12px;color:var(--ink-dim)}
        .sv-bar{display:flex;gap:8px;align-items:center;flex-wrap:wrap}
        .sv-btn{border:1px solid var(--stroke-soft);background:var(--glass-2);border-radius:10px;padding:7px 12px;cursor:pointer;font-size:13px;color:var(--ink)}
        .sv-btn:hover{border-color:var(--gold)}
        .sv-btn.primary{background:var(--gold);color:#fff;border-color:var(--gold)}
        .sv-dot{width:9px;height:9px;border-radius:50%;display:inline-block;margin-right:6px}
        .sv-scroll{overflow:auto;border:1px solid var(--stroke-soft);border-radius:14px;background:var(--glass-2);flex:1}
        table.sv{border-collapse:separate;border-spacing:0;width:100%;font-size:13px}
        table.sv th,table.sv td{padding:7px 10px;border-bottom:1px solid var(--stroke-soft);white-space:nowrap;text-align:left}
        table.sv thead th{position:sticky;top:0;background:#EEF3FB;cursor:pointer;z-index:2;font-weight:600;color:var(--ink)}
        table.sv tr:hover td{background:#F7FAFF}
        table.sv td input,table.sv td select{width:100%;min-width:80px;border:1px solid transparent;background:transparent;border-radius:6px;padding:4px 6px;font-size:13px}
        table.sv td input:focus,table.sv td select:focus{border-color:var(--gold);background:#fff;outline:none}
        .sv-fil input{width:100%;border:1px solid var(--stroke-soft);border-radius:6px;padding:3px 6px;font-size:12px}
        table.sv tfoot td{position:sticky;bottom:0;background:#EEF3FB;font-weight:600;cursor:pointer;color:var(--gold)}
        .sv-name{color:var(--gold);cursor:pointer;font-weight:600}
        .sv-ico{border:none;background:transparent;cursor:pointer;font-size:15px;padding:0 3px}
        .sv-menu{position:absolute;right:0;top:38px;background:#fff;border:1px solid var(--stroke-soft);border-radius:12px;padding:10px;max-height:340px;overflow:auto;z-index:20;box-shadow:var(--shadow);min-width:230px}
        .sv-menu label{display:flex;gap:8px;align-items:center;padding:4px 2px;font-size:13px;cursor:pointer}
        /* On-screen horizontal slide navigation for the wide sheet */
        .sv-slide{display:flex;align-items:center;gap:10px;background:var(--glass-2);border:1px solid var(--stroke-soft);border-radius:12px;padding:6px 12px;position:sticky;top:0;z-index:5}
        .sv-slide-btn{border:1px solid var(--stroke-soft);background:#fff;border-radius:8px;min-width:34px;height:30px;cursor:pointer;font-size:12px;color:var(--ink);line-height:1;flex:0 0 auto}
        .sv-slide-btn:hover{border-color:var(--gold);color:var(--gold)}
        .sv-slide-range{flex:1;min-width:120px;accent-color:var(--gold);cursor:pointer;height:6px}
        .sv-slide-pct{font-size:12px;color:var(--ink-dim);min-width:38px;text-align:right;flex:0 0 auto}
        @media(max-width:720px){.sv-kpis{grid-template-columns:repeat(2,1fr)} .sv-slide-pct{display:none}}
      `}</style>

      <div className="sv-kpis" style={{ position: 'relative' }}>
        <div className="sv-kpi"><b>{contacted}</b><span>Contacted today</span></div>
        <div className="sv-kpi"><b>{ptp}</b><span>Active PTP</span></div>
        <div className="sv-kpi"><b>₹{sheetFmt(collected)}</b><span>Collected</span></div>
        <div className="sv-kpi"><b>₹{sheetFmt(pending)}</b><span>Pending</span></div>
        <div style={{ alignSelf: 'center', marginLeft: 'auto', fontSize: 11.5, color: 'var(--ink-dim)' }}>
          {(bankF || prodF) ? `Totals for ${[bankF, prodF].filter(Boolean).join(' · ')}` : 'Totals across all portfolios'}</div>
      </div>

      <div className="sv-bar" style={{ position: 'relative' }}>
        <span><i className="sv-dot" style={{ background: live ? 'var(--good)' : '#c9ced8' }} />{live ? 'Live' : 'Reconnecting…'}</span>
        <span style={{ color: 'var(--ink-dim)', fontSize: 12 }}>{viewRows().length} rows</span>
        <input value={search} onChange={e => setSearch(e.target.value)} placeholder="🔍 Search card no / name / account…"
          style={{ width: 250, border: '1px solid var(--stroke-soft)', borderRadius: 10, padding: '7px 10px', fontSize: 13 }} />
        <select className="sv-btn" value={bankF} onChange={e => { setBankF(e.target.value); setProdF(''); }}>
          <option value="">All banks</option>
          {[...new Set(rows.map(r => r.bank).filter(Boolean))].sort().map(b => <option key={b} value={b}>{b}</option>)}
        </select>
        <select className="sv-btn" value={prodF} onChange={e => setProdF(e.target.value)}>
          <option value="">All products</option>
          {[...new Set(rows.filter(r => !bankF || r.bank === bankF).map(r => r.product).filter(Boolean))].sort().map(p => <option key={p} value={p}>{p}</option>)}
        </select>
        <select className="sv-btn" value={monthB} onChange={e => setMonthB(e.target.value)} title="Each month is a separate book">
          <option value="current">This month</option>
          <option value="next">Next month</option>
          <option value="">All months</option>
        </select>
        <div style={{ flex: 1 }} />
        <input value={calc} onChange={e => setCalc(e.target.value)} placeholder="=SUM([pending_amount])"
          style={{ width: 220, border: '1px solid var(--stroke-soft)', borderRadius: 10, padding: '7px 10px', fontSize: 13 }} />
        <button className="sv-btn" onClick={runCalc}>ƒx</button>
        {calcRes !== '' && <span style={{ fontWeight: 600, color: 'var(--gold)' }}>= {calcRes}</span>}
        <button className="sv-btn" onClick={exportCSV}>⬇ CSV</button>
        <button className="sv-btn" onClick={exportXLSX}>⬇ Excel</button>
        <button className="sv-btn" onClick={() => setColMenu(v => !v)}>⚙ Columns</button>
        {colMenu && (
          <div className="sv-menu">
            <div style={{ fontWeight: 600, marginBottom: 6 }}>Column presets</div>
            <div className="toolbar" style={{ margin: '0 0 8px', gap: 6 }}>
              <button className="sv-btn" onClick={() => applyPreset('cc')}>Credit Card</button>
              <button className="sv-btn" onClick={() => applyPreset('plbl')}>PL / BL</button>
            </div>
            <div style={{ fontWeight: 600, marginBottom: 6 }}>Show columns</div>
            {allDefs().map(c => (
              <label key={c.k}><input type="checkbox" checked={prefs.visible.includes(c.k)} onChange={() => toggleCol(c.k)} />{c.t}{c.custom ? ' (ƒ)' : ''}</label>
            ))}
            <button className="sv-btn" style={{ width: '100%', marginTop: 8 }} onClick={addDataCol}>＋ Data column</button>
            <button className="sv-btn" style={{ width: '100%', marginTop: 6 }} onClick={addFormulaCol}>＋ Formula column (ƒ)</button>
          </div>
        )}
      </div>

      {err && <div style={{ color: 'var(--bad)', fontSize: 13 }}>{err}</div>}

      {scrollable && (
        <div className="sv-slide">
          <button className="sv-slide-btn" onClick={() => nudge(-1)} title="Scroll left" aria-label="Scroll left">◀</button>
          <input className="sv-slide-range" type="range" min="0" max="100" step="1" value={scrollPct}
            onChange={e => slideTo(Number(e.target.value))} aria-label="Scroll the sheet left/right" />
          <button className="sv-slide-btn" onClick={() => nudge(1)} title="Scroll right" aria-label="Scroll right">▶</button>
          <span className="sv-slide-pct">{scrollPct}%</span>
        </div>
      )}

      <div className="sv-scroll" ref={scrollRef} onScroll={syncSlider}>
        <table className="sv">
          <thead>
            <tr>
              <th style={{ minWidth: 70 }}>Act</th>
              {cols.map(c => (
                <th key={c.k} onClick={() => setSort(s => s && s.k === c.k ? { k: c.k, dir: s.dir === 'asc' ? 'desc' : 'asc' } : { k: c.k, dir: 'asc' })}>
                  {c.t}{c.edit ? ' ✎' : ''}{sort && sort.k === c.k ? (sort.dir === 'asc' ? ' ▲' : ' ▼') : ''}
                </th>
              ))}
            </tr>
            <tr className="sv-fil">
              <th></th>
              {cols.map(c => <th key={c.k}>{!c.custom && <input value={filters[c.k] || ''} placeholder="filter" onChange={e => setFilters(f => ({ ...f, [c.k]: e.target.value }))} />}</th>)}
            </tr>
          </thead>
          <tbody>
            {viewRows().map(row => (
              <tr key={row.id}>
                <td>
                  {row.phone && <a className="sv-ico" href={'tel:' + row.phone} title="Call">📞</a>}
                  {row.phone && <button className="sv-ico" title="WhatsApp" onClick={() => window.open('https://wa.me/' + sheetWaNumber(row.phone), '_blank')}>💬</button>}
                  <button className="sv-ico" title="Open on my phone" onClick={() => openCase(row)}>📲</button>
                  {row.closed && <span className="badge" title={`Closed ${row.close_date || ''} — locked`} style={{ background: '#e5e7eb', color: '#374151', marginLeft: 4, fontSize: 10 }}>🔒</span>}
                  {othersEditing(row.id).length > 0 && <span className="badge" style={{ background: '#fde68a', color: '#92400e', marginLeft: 4, fontSize: 10.5 }}
                    title={othersEditing(row.id).map(e => e.name + (e.field ? ` (${e.field})` : '')).join(', ') + ' editing now'}>
                    ✏ {othersEditing(row.id)[0].name.split(' ')[0]}{othersEditing(row.id).length > 1 ? ` +${othersEditing(row.id).length - 1}` : ''}</span>}
                </td>
                {cols.map(c => (
                  <td key={c.k}>
                    {row.closed && (c.edit || c.data) ? (
                        <span className="muted" title="Closed for the month — locked">{c.data ? ((row.extra || {})[c.k] || '—') : cellText(row, c)}</span>
                      ) : c.data ? <input key={row.id + '-' + c.k} defaultValue={(row.extra || {})[c.k] || ''}
                        onFocus={() => sendPresence(row.id, c.t, true)}
                        onBlur={e => { sendPresence(row.id, c.t, false); if (String(e.target.value) !== String((row.extra || {})[c.k] || '')) editCell(row, c, e.target.value); }}
                        onKeyDown={e => { if (e.key === 'Enter') e.target.blur(); }} />
                      : c.custom ? sheetFmt(rowFormula(c.formula, row))
                      : c.k === 'customer_name' ? <span className="sv-name" onClick={() => openCase(row)}>{row.customer_name || '—'}</span>
                      : !c.edit ? cellText(row, c)
                      : c.type === 'sel' ? (
                        <select value={row[c.k] || ''} onChange={e => editCell(row, c, e.target.value)}>
                          {c.opts.map(o => <option key={o} value={o}>{o || '—'}</option>)}
                        </select>
                      ) : c.type === 'date' ? (
                        <input type="date" value={(row[c.k] || '').slice(0, 10)} onChange={e => editCell(row, c, e.target.value)} />
                      ) : (
                        <input key={row.id + '-' + c.k} type={c.type === 'num' ? 'number' : 'text'} defaultValue={row[c.k] == null ? '' : row[c.k]}
                          onFocus={() => sendPresence(row.id, c.t, true)}
                          onBlur={e => { sendPresence(row.id, c.t, false); if (String(e.target.value) !== String(row[c.k] == null ? '' : row[c.k])) editCell(row, c, e.target.value); }}
                          onKeyDown={e => { if (e.key === 'Enter') e.target.blur(); }} />
                      )}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
          <tfoot>
            <tr>
              <td></td>
              {cols.map(c => <td key={c.k} onClick={() => c.type === 'num' && cycleAgg(c.k)} title={c.type === 'num' ? 'Click to change aggregation' : ''}>{footAgg(c)}</td>)}
            </tr>
          </tfoot>
        </table>
      </div>

      {drawer && <CaseDrawer c={drawer} onClose={() => setDrawer(null)} onChanged={load} />}
      {payModal && <PaymentEditModal row={payModal.row} mode={payModal.mode} initAmount={payModal.amount} onClose={() => { setPayModal(null); load(); }} onDone={applyPayResult} />}
    </div>
  );
}

function PaymentEditModal({ row, mode, initAmount, onClose, onDone }) {
  const [state, setState] = React.useState(null); const [err, setErr] = React.useState('');
  const [amount, setAmount] = React.useState(''); const [ns, setNs] = React.useState('STAB');
  const [busy, setBusy] = React.useState(false); const [okOver, setOkOver] = React.useState(false);
  const money = v => '₹' + Math.round(Number(v) || 0).toLocaleString('en-IN');
  const isCC = (row.segment || '') === 'Credit Card';
  // Overpayment guard: if the total received would exceed the funded/outstanding amount,
  // pending goes below zero — usually a duplicate payment being logged twice.
  const base = state ? (Number(state.funding_amount) || Number(state.enr) || 0) : 0;
  const already = state ? (Number(state.received_amount) || 0) : 0;
  const willBe = already + (Number(amount) || 0);
  const over = base > 0 ? (willBe - base) : 0;
  const isOver = mode === 'paid' && over > 1;
  React.useEffect(() => {
    api('/api/cases/' + row.id + '/pay-state').then(s => {
      setState(s);
      // If the user typed an amount into the Amount cell, use that; otherwise pre-fill the outstanding due.
      if (initAmount != null && initAmount !== '') {
        setAmount(String(Math.round(Number(initAmount))));
      } else {
        const due = Number(s.pending_amount) > 0 ? Number(s.pending_amount)
          : Math.max(0, (Number(s.funding_amount) || Number(s.enr) || 0) - Number(s.received_amount || 0));
        setAmount(due ? String(Math.round(due)) : '');
      }
      if (s.norm_stab) setNs(s.norm_stab);
    }).catch(e => setErr(e.message || 'Could not load'));
  }, []);
  const confirmPaid = async () => {
    setBusy(true); setErr('');
    try {
      const updated = await api('/api/cases/' + row.id + '/mark-paid', { method: 'POST',
        body: { amount: amount || null, norm_stab: isCC ? ns : null, mode: 'Manual' } });
      toast('Marked paid — reflected in performance & MIS.'); onDone(updated);
    } catch (e) { setErr(e.message); setBusy(false); }
  };
  const confirmUnpaid = async () => {
    setBusy(true); setErr('');
    try {
      const updated = await api('/api/cases/' + row.id + '/mark-unpaid', { method: 'POST', body: {} });
      toast('Reverted to unpaid — payment undone everywhere.'); onDone(updated);
    } catch (e) { setErr(e.message); setBusy(false); }
  };
  return (
    <div className="modal-bg" onClick={onClose} style={{ zIndex: 1000 }}>
      <div className="modal glass" onClick={e => e.stopPropagation()} style={{ maxWidth: 440 }}>
        <div className="section-h"><h3>{mode === 'paid' ? '💰 Mark as PAID' : '↩ Revert to UNPAID'}</h3>
          <button className="btn ghost sm" onClick={onClose}>✕</button></div>
        <div className="muted" style={{ fontSize: 13, marginTop: -4 }}>{row.customer_name || '—'} · {row.card_no || row.account_no || ''}</div>
        {!state ? <Loader /> : mode === 'paid' ? (
          <>
            <p style={{ fontSize: 13.5, lineHeight: 1.6 }}>Record a payment the customer made directly (e.g. from the bank DPR). This credits the assigned caller/FOS and updates MIS.</p>
            <div className="stat-row"><span className="k">Already received</span><b>{money(state.received_amount)}</b></div>
            <div className="stat-row"><span className="k">Outstanding</span><b style={{ color: 'var(--warn)' }}>{money(state.pending_amount)}</b></div>
            <div className="field"><label>Amount paid (₹)</label><input className="input" type="number" value={amount} onChange={e => setAmount(e.target.value)} /></div>
            {isCC && <div className="field"><label>Paid at (credit card)</label>
              <select className="input" value={ns} onChange={e => setNs(e.target.value)}><option>STAB</option><option>NORM</option><option>ROLLBACK</option></select></div>}
            {isOver && <div className="glass card" style={{ background: 'rgba(220,38,38,.08)', border: '1px solid rgba(220,38,38,.35)', padding: 10, marginTop: 4 }}>
              <div style={{ color: 'var(--bad)', fontWeight: 700, fontSize: 13 }}>⚠ Overpayment — likely a duplicate</div>
              <div className="muted" style={{ fontSize: 12.5, marginTop: 3, lineHeight: 1.5 }}>
                Total received would become <b>{money(willBe)}</b> — that's <b>{money(over)}</b> more than the outstanding <b>{money(base)}</b>, so pending goes below zero. This usually means the payment was already logged. Don't record it twice.</div>
              <label style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 8, fontSize: 12.5, color: 'var(--ink)' }}>
                <input type="checkbox" checked={okOver} onChange={e => setOkOver(e.target.checked)} /> This is a genuine additional payment, not a duplicate</label>
            </div>}
            {err && <div style={{ color: 'var(--bad)', fontSize: 13 }}>{err}</div>}
            <button className="btn gold block" disabled={busy || (isOver && !okOver)} onClick={confirmPaid} style={{ marginTop: 6 }}>{busy ? 'Saving…' : (isOver ? 'Log anyway' : 'OK — mark paid')}</button>
          </>
        ) : (
          <>
            <p style={{ fontSize: 13.5, lineHeight: 1.6, color: 'var(--bad)' }}>This will revert the recorded payment and return the case to the working pool (status → allocated, paid → UNPAID). The reversal flows through the caller/FOS performance and MIS.</p>
            <div className="glass card" style={{ background: 'rgba(0,0,0,.05)', padding: 12 }}>
              <div style={{ fontWeight: 600, fontSize: 13, marginBottom: 4 }}>Will be reverted:</div>
              <div className="stat-row"><span className="k">Received so far</span><b>{money(state.received_amount)}</b></div>
              {state.last_payment && <div className="stat-row"><span className="k">Last payment</span><b>{money(state.last_payment.amount)}</b></div>}
              {state.last_payment && state.last_payment.note && <div className="muted" style={{ fontSize: 12 }}>{state.last_payment.note}</div>}
              {state.norm_stab && <div className="stat-row"><span className="k">NORM/STAB</span><b>{state.norm_stab}</b></div>}
            </div>
            {err && <div style={{ color: 'var(--bad)', fontSize: 13, marginTop: 8 }}>{err}</div>}
            <button className="btn block" disabled={busy} onClick={confirmUnpaid} style={{ marginTop: 8, background: 'var(--bad)', color: '#fff' }}>{busy ? 'Reverting…' : 'OK — revert payment'}</button>
          </>
        )}
      </div>
    </div>
  );
}

/* ============================== Manpower directory (HR / admin) ============================== */
/* HR: add a NEW employee, or edit an EXISTING one (pass `existing`), with the full detail set. */
function StaffFormModal({ existing, roles, onClose, onDone, isAdmin }) {
  const editing = !!existing;
  const init = editing
    ? { ...existing, dob: (existing.dob || '').slice(0, 10), joining_date: (existing.joining_date || '').slice(0, 10), password: '' }
    : { role: 'telecaller', password: 'Ssd@2026' };
  const [f, setF] = useState(init);
  const [busy, setBusy] = useState(false); const [err, setErr] = useState('');
  const set = (k, v) => setF(s => ({ ...s, [k]: v }));
  let ROLE_OPTS = (roles && roles.length ? roles : ['manager', 'teamlead', 'telecaller', 'fos', 'headoffice', 'backend', 'hr', 'it', 'staff', 'admin']);
  // Only an admin may assign the Administrator role — hide it for everyone else,
  // unless the person being edited is already an admin (keep it shown so it's not dropped).
  if (!isAdmin && !(existing && existing.role === 'admin')) ROLE_OPTS = ROLE_OPTS.filter(r => r !== 'admin');
  const field = (k, label, type = 'text') => (
    <div className="field" key={k}><label>{label}</label>
      <input className="input" type={type} value={f[k] || ''} onChange={e => set(k, e.target.value)} /></div>
  );
  const save = async () => {
    if (!f.name || !f.email || !f.role) { setErr('Name, login email and role are required'); return; }
    setBusy(true); setErr('');
    try {
      if (editing) { await api('/api/manpower/' + existing.id, { method: 'PATCH', body: f }); toast('Employee updated.'); }
      else { await api('/api/manpower', { method: 'POST', body: f }); toast('Staff added.'); }
      onDone();
    } catch (e) { setErr(e.message); } finally { setBusy(false); }
  };
  return (
    <div className="modal-bg" onClick={onClose} style={{ zIndex: 1000 }}>
      <div className="modal glass" onClick={e => e.stopPropagation()} style={{ maxWidth: 700 }}>
        <div className="section-h"><h3>{editing ? 'Edit employee' : 'Add staff'}</h3><button className="btn ghost sm" onClick={onClose}>✕</button></div>
        <p className="muted" style={{ fontSize: 12, marginTop: 0 }}>
          {editing
            ? <>Editing <b>{existing.emp_code || existing.name}</b>. Leave the password blank to keep it unchanged.</>
            : <>A login is created with starter password <b>{f.password || 'Ssd@2026'}</b>; they set their own on first sign-in. A role-wise employee code is generated automatically.</>}
        </p>
        <div className="grid2" style={{ gridTemplateColumns: '1fr 1fr', gap: 10 }}>
          {field('name', 'Full name *')}
          {field('email', 'Login email *', 'email')}
          <div className="field"><label>Role *</label>
            <select className="input" value={f.role} onChange={e => set('role', e.target.value)}>
              {ROLE_OPTS.map(r => <option key={r} value={r}>{roleName(r)}</option>)}</select></div>
          {field('designation', 'Designation')}
          {field('phone', 'Phone')}
          {field('location', 'Location')}
          {field('branch', 'Branch')}
          {field('hr_ref', 'HR ref (SSD ID)')}
          {field('gender', 'Gender')}
          {field('dob', 'Date of birth', 'date')}
          {field('joining_date', 'Date of joining', 'date')}
          {field('blood_group', 'Blood group')}
          {field('marital_status', 'Marital status')}
          {field('emergency_name', 'Emergency contact name')}
          {field('emergency_contact', 'Emergency contact no.')}
          {field('emergency_relation', 'Relation')}
          {field('aadhar_number', 'Aadhaar number')}
          {field('pan_number', 'PAN')}
          {field('bank_holder', 'Bank a/c holder')}
          {field('bank_account', 'Bank account no.')}
          {field('ifsc_code', 'IFSC')}
          {field('bank_name', 'Bank name')}
          {field('employment_type', 'Employment type')}
          {field('password', editing ? 'Reset password (optional)' : 'Starter password')}
        </div>
        <div className="field"><label>Current address</label>
          <textarea className="input" value={f.current_address || ''} onChange={e => set('current_address', e.target.value)} /></div>
        {editing && f.role !== existing.role && (
          <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 13, margin: '6px 0' }}>
            <input type="checkbox" checked={!!f.regen_code} onChange={e => set('regen_code', e.target.checked)} />
            Regenerate employee code to match the new role (current: <b>{existing.emp_code || '—'}</b>)
          </label>)}
        {editing && ['telecaller', 'fos'].includes(f.role) && (
          <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 13, margin: '6px 0' }}>
            <input type="checkbox" checked={!!f.also_team_lead} onChange={e => set('also_team_lead', e.target.checked)} />
            Also a team lead — adds a Team Leader view they can switch to
            {existing.tl_emp_code ? <> (team-lead ID: <b>{existing.tl_emp_code}</b>)</> : <> (a team-lead ID is generated on save)</>}
          </label>)}
        {err && <div style={{ color: 'var(--bad)', fontSize: 13, margin: '6px 0' }}>{err}</div>}
        <div className="toolbar" style={{ marginTop: 8 }}>
          <button className="btn" onClick={onClose}>Cancel</button><div style={{ flex: 1 }} />
          <button className="btn gold" disabled={busy} onClick={save}>{busy ? 'Saving…' : (editing ? 'Save changes' : 'Add staff')}</button>
        </div>
      </div>
    </div>
  );
}
function ManpowerView({ user }) {
  const [opts, setOpts] = useState({ roles: [], locations: [] });
  const [rows, setRows] = useState(null);
  const [f, setF] = useState({ role: '', location: '', q: '' });
  const [sel, setSel] = useState(null);
  const [addOpen, setAddOpen] = useState(false);
  const [edit, setEdit] = useState(null);
  const [offerFor, setOfferFor] = useState(null);
  const canAdd = ['admin', 'headoffice', 'hr'].includes(user.role);
  useEffect(() => { api('/api/manpower/filters').then(setOpts).catch(() => {}); }, []);
  const load = useCallback(() => {
    const p = new URLSearchParams(); if (f.role) p.set('role', f.role); if (f.location) p.set('location', f.location); if (f.q) p.set('q', f.q);
    api('/api/manpower?' + p).then(setRows).catch(() => setRows([]));
  }, [f]);
  useEffect(() => { const t = setTimeout(load, 200); return () => clearTimeout(t); }, [load]);
  const set = (k, v) => setF(s => ({ ...s, [k]: v }));
  const dl = () => { const p = new URLSearchParams(); if (f.role) p.set('role', f.role); if (f.location) p.set('location', f.location); download('/api/manpower/download?' + p, 'SSDE_manpower.xlsx'); };
  const selStyle = { minWidth: 150, height: 34, padding: '0 8px', fontSize: 13 };
  return (
    <div>
      <div className="section-h"><h2 style={{ margin: 0 }}>Manpower</h2>
        <span className="muted" style={{ fontSize: 13 }}>{rows ? `${rows.length} employees` : '…'}</span></div>
      <div className="glass card" style={{ padding: 10, marginBottom: 12 }}>
        <div className="toolbar" style={{ flexWrap: 'wrap', gap: 8 }}>
          <input className="input" style={{ maxWidth: 240 }} placeholder="🔍 Search name, code, phone, designation…" value={f.q} onChange={e => set('q', e.target.value)} />
          <select className="input" style={selStyle} value={f.role} onChange={e => set('role', e.target.value)}>
            <option value="">All roles</option>{opts.roles.map(r => <option key={r} value={r}>{roleName(r)}</option>)}</select>
          <select className="input" style={selStyle} value={f.location} onChange={e => set('location', e.target.value)}>
            <option value="">All locations</option>{opts.locations.map(l => <option key={l} value={l}>{l}</option>)}</select>
          <div style={{ flex: 1 }} />
          {canAdd && <button className="btn" onClick={() => setAddOpen(true)}>➕ Add staff</button>}
          <button className="btn gold" onClick={dl}>⬇ Download Excel</button>
        </div>
      </div>
      {addOpen && <StaffFormModal roles={opts.roles} isAdmin={user.role === 'admin'} onClose={() => setAddOpen(false)} onDone={() => { setAddOpen(false); load(); }} />}
      {edit && <StaffFormModal existing={edit} roles={opts.roles} isAdmin={user.role === 'admin'} onClose={() => setEdit(null)} onDone={() => { setEdit(null); setSel(null); load(); }} />}
      {!rows ? <Loader /> : rows.length === 0 ? <div className="glass card muted" style={{ padding: 24, textAlign: 'center' }}>No employees match.</div> : (
        <div className="glass card" style={{ padding: 6 }}>
          <div className="tablewrap"><table>
            <thead><tr><th>Code</th><th>Name</th><th>Role</th><th>Designation</th><th>Location</th><th>Branch</th><th>Phone</th><th>DOJ</th><th></th></tr></thead>
            <tbody>{rows.map(e => <tr key={e.id} style={{ cursor: 'pointer' }} onClick={() => setSel(e)}>
              <td className="mono">{e.emp_code || '—'}{e.also_team_lead && e.tl_emp_code ? <span className="muted"> / {e.tl_emp_code}</span> : ''}</td><td><b>{e.name}</b></td>
              <td><span className="badge allocated">{roleName(e.role)}</span>{e.also_team_lead && e.role !== 'teamlead' && <span className="badge" style={{ marginLeft: 4, background: 'rgba(59,130,246,.12)', color: 'var(--info)' }}>+ Team Lead</span>}</td>
              <td className="muted" style={{ fontSize: 12 }}>{e.designation || '—'}</td>
              <td>{e.location || '—'}</td><td className="muted">{e.branch || '—'}</td>
              <td>{e.phone || '—'}</td><td className="muted" style={{ fontSize: 12 }}>{e.joining_date || '—'}</td>
              <td><ContactBtns phone={e.phone} /></td></tr>)}
            </tbody></table></div>
        </div>
      )}
      {sel && <div className="modal-bg" onClick={() => setSel(null)}>
        <div className="modal glass" onClick={e => e.stopPropagation()} style={{ maxWidth: 560 }}>
          <div className="section-h"><h3>{sel.name}</h3>
            <div style={{ display: 'flex', gap: 8 }}>
              {canAdd && <button className="btn sm" onClick={() => setEdit(sel)}>✏ Edit</button>}
              <button className="btn ghost sm" onClick={() => setSel(null)}>✕</button></div></div>
          <EIDCard e={sel} />
          <div className="dl" style={{ marginTop: 10 }}>
            {[['Emp code(s)', sel.all_ids || sel.emp_code], ['HR ref', sel.hr_ref], ['Role(s)', sel.all_roles || roleName(sel.role)], ['Designation', sel.designation],
              ['Location', sel.location], ['Branch', sel.branch], ['Email', sel.email], ['Phone', sel.phone],
              ['Gender', sel.gender], ['DOB', sel.dob], ['Blood group', sel.blood_group], ['Marital', sel.marital_status],
              ['Emergency', (sel.emergency_name || '') + (sel.emergency_contact ? ' · ' + sel.emergency_contact : '')],
              ['Aadhaar', sel.aadhar_number], ['PAN', sel.pan_number], ['Bank', sel.bank_name],
              ['Account', sel.bank_account], ['IFSC', sel.ifsc_code], ['Current address', sel.current_address]].map(([k, v]) =>
              <React.Fragment key={k}><div className="dt">{k}</div><div className="dd">{v || '—'}</div></React.Fragment>)}
          </div>
          {canAdd && <EmployeeDocs emp={sel} />}
          {canAdd && <div className="toolbar" style={{ marginTop: 10 }}>
            <button className="btn gold" onClick={() => setOfferFor({ emp: sel, kind: 'offer' })}>📝 Offer letter</button>
            <button className="btn gold" onClick={() => setOfferFor({ emp: sel, kind: 'agreement' })}>📄 Agreement letter</button>
          </div>}
        </div></div>}
      {offerFor && <LetterModal emp={offerFor.emp} kind={offerFor.kind} onClose={() => setOfferFor(null)} />}
    </div>
  );
}

/* HR document vault for one employee — upload / download each of the required documents. */
const DOC_LIST = [
  ['pan', 'PAN card'], ['aadhaar', 'Aadhaar card'], ['photo', 'Photo'],
  ['signature', 'Signature (white paper)'], ['pvc', 'PVC'], ['dra', 'DRA certificate'],
  ['cibil', 'CIBIL report (Paisabazaar)'], ['bank_details', 'Bank account details'],
  ['reference', 'Reference contact details'], ['whatsapp', 'WhatsApp no. (not PhonePe)'],
  ['email', 'Email ID proof'],
];
const DOC_LABEL = Object.fromEntries(DOC_LIST);
DOC_LABEL.other = 'Other / misc';
// Map a filename to a document type. Order matters (most specific first). Anything that
// doesn't match a known keyword falls into 'other'.
const DOC_MATCH = [
  ['aadhaar', /(aadha?r|aadhaar|uidai)/i],
  ['pan', /pan(\s|_|-|card|\.|$)/i],
  ['cibil', /(cibil|paisa|credit.?report)/i],
  ['pvc', /pvc/i],
  ['dra', /\bdra\b|dra.?cert/i],
  ['bank_details', /(bank|passbook|cheque|ifsc|account|acct)/i],
  ['signature', /(signature|sign(\s|_|-|\.|$)|sig)/i],
  ['whatsapp', /(whats.?app|wa.?no)/i],
  ['email', /(e.?mail|gmail)/i],
  ['reference', /(reference|ref.?contact|ref(\s|_|-|\.|$))/i],
  ['photo', /(photo|passport|\bpic\b|\bdp\b|profile)/i],
];
function detectDocType(name) {
  const n = (name || '').toLowerCase();
  for (const [k, re] of DOC_MATCH) if (re.test(n)) return k;
  return 'other';
}
function EmployeeDocs({ emp }) {
  const [docs, setDocs] = useState(null);
  const [busy, setBusy] = useState('');
  const [preview, setPreview] = useState(null);   // {url, mime, filename, label}
  const [folderPrev, setFolderPrev] = useState(null);   // [{file,name,mime,url,type}] before bulk upload
  const [folderBusy, setFolderBusy] = useState(false);
  const [gallery, setGallery] = useState(false);        // view-all modal
  const load = () => api(`/api/manpower/${emp.id}/documents`).then(setDocs).catch(() => setDocs([]));
  useEffect(() => { load(); }, [emp.id]);
  // ---- folder (bulk) upload: read files, auto-map by filename, confirm, then upload ----
  const onFolder = (fileList) => {
    const items = Array.from(fileList || []).filter(f => f.size > 0).map(f => {
      const mime = f.type || '';
      return { file: f, name: f.webkitRelativePath || f.name, base: f.name, mime,
        url: mime.startsWith('image/') ? URL.createObjectURL(f) : null, type: detectDocType(f.name) };
    });
    if (!items.length) { toast('No files found in that folder'); return; }
    setFolderPrev(items);
  };
  const closeFolder = () => { (folderPrev || []).forEach(i => { if (i.url) { try { URL.revokeObjectURL(i.url); } catch (e) {} } }); setFolderPrev(null); };
  const setItemType = (idx, t) => setFolderPrev(list => list.map((i, j) => j === idx ? { ...i, type: t } : i));
  const uploadFolder = async () => {
    const items = (folderPrev || []).filter(i => i.type !== 'skip');
    if (!items.length) { toast('Nothing selected to upload'); return; }
    setFolderBusy(true);
    try {
      const fd = new FormData();
      items.forEach(i => { fd.append('files', i.file); fd.append('doc_types', i.type); });
      const r = await api(`/api/manpower/${emp.id}/documents/bulk`, { method: 'POST', form: fd });
      toast(`Uploaded ${r.uploaded} file(s).`); closeFolder(); await load();
    } catch (e) { toast(e.message || 'Bulk upload failed'); } finally { setFolderBusy(false); }
  };
  // preview a document inline (image or PDF) — fetch with auth, show via an object URL
  const view = async (d, label) => { setBusy(d.doc_type);
    try {
      const res = await fetch(`/api/manpower/${emp.id}/documents/${d.id}/download`,
        { headers: store.t ? { Authorization: 'Bearer ' + store.t } : {} });
      if (!res.ok) { toast('Could not open document'); return; }
      const blob = await res.blob();
      const mime = blob.type || res.headers.get('content-type') || '';
      setPreview({ url: URL.createObjectURL(blob), mime, filename: d.filename || d.doc_type, label });
    } catch (e) { toast('Could not open: ' + e.message); } finally { setBusy(''); }
  };
  const closePreview = () => { if (preview) { try { URL.revokeObjectURL(preview.url); } catch (e) {} } setPreview(null); };
  const byType = {}; (docs || []).forEach(d => { byType[d.doc_type] = d; });
  const up = async (type, file) => {
    if (!file) return; setBusy(type);
    try { const fd = new FormData(); fd.append('doc_type', type); fd.append('file', file);
      await api(`/api/manpower/${emp.id}/documents`, { method: 'POST', form: fd });
      toast('Uploaded.'); await load();
    } catch (e) { toast(e.message || 'Upload failed'); } finally { setBusy(''); }
  };
  const del = async (d) => { setBusy(d.doc_type);
    try { await api(`/api/manpower/${emp.id}/documents/${d.id}`, { method: 'DELETE' }); await load(); }
    catch (e) { toast(e.message); } finally { setBusy(''); } };
  const zipName = (emp.name || 'employee').replace(/[^a-zA-Z0-9 _-]/g, '').trim().replace(/\s+/g, '_') + '.zip';
  return (
    <div className="glass card" style={{ marginTop: 12, padding: 12 }}>
      <div className="section-h" style={{ marginTop: 0, flexWrap: 'wrap', gap: 6 }}><h3 style={{ margin: 0, fontSize: 15 }}>📄 Documents</h3>
        <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
          <label className="btn sm" style={{ cursor: 'pointer', margin: 0 }}>📁 Upload folder
            <input type="file" multiple style={{ display: 'none' }}
              ref={el => { if (el) { el.webkitdirectory = true; el.directory = true; } }}
              onChange={e => { onFolder(e.target.files); e.target.value = ''; }} /></label>
          <button className="btn sm" onClick={() => setGallery(true)} disabled={!(docs && docs.length)}>🖼 View all ({(docs || []).length})</button>
          <button className="btn sm" onClick={() => download(`/api/manpower/${emp.id}/documents.zip`, zipName)}>⬇ Download all (.zip)</button>
        </div></div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
        {DOC_LIST.map(([k, label]) => { const d = byType[k]; return (
          <div key={k} style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 13, padding: '4px 0', borderBottom: '1px solid var(--line)' }}>
            <span style={{ flex: 1 }}>{d ? '✅' : '⬜'} {label}</span>
            {d && <button className="btn ghost sm" disabled={busy === k} onClick={() => view(d, label)} title="View / preview">👁</button>}
            {d && <a className="btn ghost sm" onClick={() => download(`/api/manpower/${emp.id}/documents/${d.id}/download`, d.filename || k)} title="Download">⬇</a>}
            {d && <button className="btn ghost sm" disabled={busy === k} onClick={() => del(d)} title="Delete">🗑</button>}
            <label className="btn sm" style={{ cursor: 'pointer', margin: 0 }}>{busy === k ? '…' : (d ? 'Replace' : 'Upload')}
              <input type="file" style={{ display: 'none' }} onChange={e => up(k, e.target.files[0])} /></label>
          </div>); })}
      </div>

      {preview && <div className="modal-bg" onClick={closePreview} style={{ zIndex: 1000 }}>
        <div className="modal glass" onClick={e => e.stopPropagation()} style={{ maxWidth: 820, width: '90%' }}>
          <div className="section-h"><h3 style={{ margin: 0, fontSize: 15 }}>{preview.label} — {emp.name}</h3>
            <button className="btn ghost sm" onClick={closePreview}>✕</button></div>
          <div style={{ background: '#fff', borderRadius: 10, padding: 8, textAlign: 'center', maxHeight: '70vh', overflow: 'auto' }}>
            {preview.mime.startsWith('image/') ?
              <img src={preview.url} alt={preview.label} style={{ maxWidth: '100%', height: 'auto' }} /> :
              preview.mime.includes('pdf') ?
                <iframe src={preview.url} title={preview.label} style={{ width: '100%', height: '68vh', border: 'none' }} /> :
                <div className="muted" style={{ padding: 24 }}>Can’t preview this file type ({preview.mime || 'unknown'}). Use download instead.</div>}
          </div>
          <div className="toolbar" style={{ marginTop: 10 }}>
            <a className="btn sm" href={preview.url} download={preview.filename}>⬇ Download</a>
          </div>
        </div>
      </div>}

      {/* Folder bulk-upload: preview every file + its auto-detected type, adjust, then upload. */}
      {folderPrev && <div className="modal-bg" onClick={closeFolder} style={{ zIndex: 1000 }}>
        <div className="modal glass" onClick={e => e.stopPropagation()} style={{ maxWidth: 760, width: '94%' }}>
          <div className="section-h"><h3 style={{ margin: 0, fontSize: 15 }}>📁 Upload folder — {emp.name}</h3>
            <button className="btn ghost sm" onClick={closeFolder}>✕</button></div>
          <p className="muted" style={{ fontSize: 12, marginTop: 0 }}>{folderPrev.length} file(s) found. We matched each to a document type from its filename — check and adjust, then upload. Set a row to <b>Skip</b> to leave it out.</p>
          <div className="tablewrap" style={{ maxHeight: '52vh', overflow: 'auto' }}><table>
            <thead><tr><th></th><th>File</th><th>Maps to</th></tr></thead>
            <tbody>{folderPrev.map((it, i) => <tr key={i}>
              <td style={{ width: 46 }}>{it.url ? <img src={it.url} alt="" style={{ width: 40, height: 40, objectFit: 'cover', borderRadius: 6 }} /> : <span style={{ fontSize: 22 }}>📄</span>}</td>
              <td style={{ fontSize: 12.5 }}><b>{it.base}</b><div className="muted" style={{ fontSize: 11 }}>{Math.max(1, Math.round(it.file.size / 1024))} KB</div></td>
              <td><select className="input" style={{ minWidth: 190, padding: '4px 8px', fontSize: 12.5, background: it.type === 'skip' ? '#FDECEC' : it.type === 'other' ? '#FFF7E6' : '#fff' }}
                value={it.type} onChange={e => setItemType(i, e.target.value)}>
                {DOC_LIST.map(([k, l]) => <option key={k} value={k}>{l}</option>)}
                <option value="other">Other / misc</option>
                <option value="skip">— Skip —</option>
              </select></td>
            </tr>)}</tbody></table></div>
          <div className="toolbar" style={{ marginTop: 10 }}>
            <span className="muted" style={{ fontSize: 12 }}>{folderPrev.filter(i => i.type !== 'skip').length} will be uploaded</span>
            <div style={{ flex: 1 }} />
            <button className="btn" onClick={closeFolder}>Cancel</button>
            <button className="btn gold" disabled={folderBusy} onClick={uploadFolder}>{folderBusy ? 'Uploading…' : '⬆ Upload files'}</button>
          </div>
        </div>
      </div>}

      {/* View all: every uploaded doc (fixed types + extras), with preview / download / delete. */}
      {gallery && <div className="modal-bg" onClick={() => setGallery(false)} style={{ zIndex: 1000 }}>
        <div className="modal glass" onClick={e => e.stopPropagation()} style={{ maxWidth: 720, width: '94%' }}>
          <div className="section-h"><h3 style={{ margin: 0, fontSize: 15 }}>🖼 All documents — {emp.name}</h3>
            <button className="btn ghost sm" onClick={() => setGallery(false)}>✕</button></div>
          {(!docs || !docs.length) ? <div className="muted" style={{ padding: 16 }}>No documents uploaded yet.</div> :
            <div className="tablewrap" style={{ maxHeight: '60vh', overflow: 'auto' }}><table>
              <thead><tr><th>Type</th><th>File</th><th style={{ textAlign: 'right' }}>Actions</th></tr></thead>
              <tbody>{docs.map(d => <tr key={d.id}>
                <td style={{ fontSize: 12.5 }}>{DOC_LABEL[d.doc_type] || d.doc_type}</td>
                <td style={{ fontSize: 12.5 }} className="muted">{d.filename || '—'}</td>
                <td style={{ textAlign: 'right', whiteSpace: 'nowrap' }}>
                  <button className="btn ghost sm" onClick={() => view(d, DOC_LABEL[d.doc_type] || d.doc_type)} title="View">👁</button>{' '}
                  <a className="btn ghost sm" onClick={() => download(`/api/manpower/${emp.id}/documents/${d.id}/download`, d.filename || d.doc_type)} title="Download">⬇</a>{' '}
                  <button className="btn ghost sm" onClick={() => del(d)} title="Delete">🗑</button>
                </td>
              </tr>)}</tbody></table></div>}
          <div className="toolbar" style={{ marginTop: 10 }}>
            <div style={{ flex: 1 }} />
            <button className="btn sm" onClick={() => download(`/api/manpower/${emp.id}/documents.zip`, zipName)}>⬇ Download all (.zip)</button>
          </div>
        </div>
      </div>}
    </div>
  );
}

/* Generate → edit → download / email an OFFER or AGREEMENT letter for a (new) employee,
   using the SSD letter formats. HR fills details, tweaks the salary break-up, then previews. */
const SALARY_DEFAULT = [
  { component: 'Basic Salary', annual: '' }, { component: 'House Rent Allowance (HRA)', annual: '' },
  { component: 'Special Allowance', annual: '' }, { component: 'Bonus', annual: '' },
  { component: 'Leave Travel Allowance', annual: '' }, { component: 'Commission', annual: '' },
];
function LetterModal({ emp, kind: initialKind, onClose }) {
  const ref = React.useRef(null);
  const [kind, setKind] = useState(initialKind || 'offer');
  const [html, setHtml] = useState('');
  const [to, setTo] = useState(emp.email || '');
  const [busy, setBusy] = useState('');
  const [meta, setMeta] = useState({
    designation: emp.designation || '', reporting_to: '', location: emp.location || emp.branch || '',
    joining_date: '', ctc: '', employment_type: 'Full Time', work_schedule: '9:30 AM to 7:30 PM',
    address: emp.current_address || '', probation_months: '3', notice_days: '30',
  });
  const [salary, setSalary] = useState(SALARY_DEFAULT.map(s => ({ ...s })));
  const isAgr = kind === 'agreement';
  const ep = isAgr ? 'agreement-letter' : 'offer-letter';
  const title = isAgr ? 'Employment Agreement' : 'Offer of Employment';
  const gen = async () => { setBusy('gen');
    try { const r = await api(`/api/manpower/${ep}`, { method: 'POST', body: { emp_id: emp.id, ...meta, salary } });
      setHtml(r.html); if (!to && r.email) setTo(r.email);
    } catch (e) { toast(e.message); } finally { setBusy(''); } };
  useEffect(() => { gen(); }, [kind]);   // regenerate when switching letter type
  const current = () => (ref.current ? ref.current.innerHTML : html);
  const print = () => { const w = window.open('', '_blank'); if (!w) return;
    w.document.write(`<html><head><title>${title} — ${emp.name}</title></head><body style="padding:24px">${current()}</body></html>`);
    w.document.close(); w.focus(); setTimeout(() => { try { w.print(); } catch (e) {} }, 300); };
  const sendEmail = async () => { if (!to) { toast('Add a recipient email'); return; } setBusy('mail');
    try { const r = await api(`/api/manpower/${ep}/email`, { method: 'POST', body: { emp_id: emp.id, to, html: current(), subject: `${title} — ${emp.name}`, ...meta, salary } });
      toast('Letter emailed to ' + r.to); onClose();
    } catch (e) { toast(e.message || 'Could not send (check SMTP settings)'); } finally { setBusy(''); } };
  const setSal = (i, v) => setSalary(list => list.map((s, j) => j === i ? { ...s, annual: v } : s));
  const F = ([k, lbl]) => <div className="field" key={k}><label>{lbl}</label><input className="input" value={meta[k]} onChange={e => setMeta(m => ({ ...m, [k]: e.target.value }))} /></div>;
  const fields = isAgr
    ? [['designation', 'Position / Department'], ['reporting_to', 'Reporting to'], ['location', 'Location'], ['joining_date', 'Commencement date'], ['ctc', 'Annual CTC (₹)'], ['probation_months', 'Probation (months)'], ['notice_days', 'Notice (days)'], ['address', 'Employee address']]
    : [['designation', 'Job title'], ['reporting_to', 'Reporting to'], ['location', 'Job location'], ['joining_date', 'Start date'], ['ctc', 'Annual CTC (₹)'], ['employment_type', 'Employment type'], ['work_schedule', 'Work schedule']];
  return (
    <div className="modal-bg" onClick={onClose} style={{ zIndex: 1000 }}>
      <div className="modal glass" onClick={e => e.stopPropagation()} style={{ maxWidth: 860, width: '96%' }}>
        <div className="section-h"><h3>📝 Letter — {emp.name}</h3><button className="btn ghost sm" onClick={onClose}>✕</button></div>
        <div className="toolbar" style={{ marginBottom: 8 }}>
          <div className={cx('chip', !isAgr && 'on')} onClick={() => setKind('offer')}>📝 Offer letter</div>
          <div className={cx('chip', isAgr && 'on')} onClick={() => setKind('agreement')}>📄 Agreement letter</div>
        </div>
        <p className="muted" style={{ fontSize: 12, marginTop: 0 }}>Fill the details, generate, then fine-tune directly in the preview before downloading or emailing.</p>
        <div className="grid2" style={{ gridTemplateColumns: '1fr 1fr 1fr', gap: 8 }}>{fields.map(F)}</div>
        {isAgr && <div style={{ marginTop: 8 }}>
          <div className="muted" style={{ fontSize: 12, marginBottom: 4 }}>Salary break-up (Annexure A) — annual ₹ per component</div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill,minmax(210px,1fr))', gap: 6 }}>
            {salary.map((s, i) => <div key={i} style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
              <span style={{ flex: 1, fontSize: 12 }}>{s.component}</span>
              <input className="input" style={{ width: 100, padding: '4px 6px', fontSize: 12 }} placeholder="₹/yr" value={s.annual} onChange={e => setSal(i, e.target.value)} />
            </div>)}
          </div>
        </div>}
        <div className="toolbar" style={{ margin: '8px 0' }}>
          <button className="btn" disabled={busy === 'gen'} onClick={gen}>{busy === 'gen' ? 'Generating…' : '↻ Regenerate'}</button>
          <div style={{ flex: 1 }} />
          <input className="input" style={{ maxWidth: 240 }} placeholder="Recipient email" value={to} onChange={e => setTo(e.target.value)} />
        </div>
        <div ref={ref} contentEditable suppressContentEditableWarning dangerouslySetInnerHTML={{ __html: html }}
          style={{ background: '#fff', border: '1px solid var(--line)', borderRadius: 10, padding: 18, maxHeight: 400, overflow: 'auto' }} />
        <div className="toolbar" style={{ marginTop: 10 }}>
          <button className="btn" onClick={print}>🖨 Download / Print</button>
          <div style={{ flex: 1 }} />
          <button className="btn gold" disabled={busy === 'mail'} onClick={sendEmail}>{busy === 'mail' ? 'Sending…' : '✉ Send to employee'}</button>
        </div>
      </div>
    </div>
  );
}

/* A shareable employee ID card (E-ID). */
function EIDCard({ e }) {
  const brand = (window.__ssdCfg || {}).brand_name || 'SSD Enterprises';
  return (
    <div style={{ borderRadius: 14, overflow: 'hidden', border: '1px solid var(--line)', maxWidth: 380 }}>
      <div style={{ background: 'linear-gradient(120deg,#1e3a8a,#2563eb)', color: '#fff', padding: '12px 16px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <b style={{ fontSize: 15 }}>{brand}</b><span style={{ fontSize: 11, opacity: .85 }}>EMPLOYEE ID</span></div>
      <div style={{ display: 'flex', gap: 14, padding: 16, alignItems: 'center' }}>
        <div style={{ width: 84, height: 84, borderRadius: 10, background: '#e5e7eb', overflow: 'hidden', flexShrink: 0, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
          {e.photo_url ? <img src={e.photo_url} alt="" style={{ width: '100%', height: '100%', objectFit: 'cover' }} /> : <span style={{ fontSize: 26, color: '#94a3b8' }}>{initials(e.name)}</span>}
        </div>
        <div style={{ flex: 1 }}>
          <div style={{ fontSize: 17, fontWeight: 700 }}>{e.name}</div>
          <div className="muted" style={{ fontSize: 13 }}>{e.designation || roleName(e.role)}</div>
          <div style={{ marginTop: 6, fontSize: 13 }}><b className="mono">{e.all_ids || e.emp_code}</b> · {e.all_roles || roleName(e.role)}</div>
          <div className="muted" style={{ fontSize: 12 }}>{[e.location, e.branch].filter(Boolean).join(' · ')}</div>
          <div className="muted" style={{ fontSize: 12 }}>{e.phone}{e.blood_group ? ' · 🩸 ' + e.blood_group : ''}</div>
        </div>
        <div style={{ flexShrink: 0 }}><QR text={e.emp_code || e.email || e.name} size={72} /></div>
      </div>
    </div>
  );
}

/* ============================== My profile / E-ID (all staff) ============================== */
const PROFILE_FIELDS = [
  ['phone', 'Phone', 'text'], ['gender', 'Gender', 'text'], ['dob', 'Date of birth', 'date'],
  ['blood_group', 'Blood group', 'text'], ['marital_status', 'Marital status', 'text'],
  ['emergency_contact', 'Emergency contact no.', 'text'], ['emergency_name', 'Emergency contact name', 'text'],
  ['emergency_relation', 'Relation', 'text'], ['current_address', 'Current address', 'text'],
  ['aadhar_number', 'Aadhaar number', 'text'], ['pan_number', 'PAN', 'text'],
  ['bank_holder', 'Bank a/c holder', 'text'], ['bank_account', 'Bank account no.', 'text'],
  ['ifsc_code', 'IFSC', 'text'], ['bank_name', 'Bank name', 'text'],
];
function ProfileView({ user }) {
  const [me, setMe] = useState(null);
  const [f, setF] = useState({});
  const [editing, setEditing] = useState(false);
  const [busy, setBusy] = useState(false);
  const [photoBusy, setPhotoBusy] = useState(false);
  const [trends, setTrends] = useState(null);   // FTD/MTD/LMTD/Overall for field/calling staff
  const showTrends = ['fos', 'telecaller', 'teamlead'].includes(user.role);
  const load = () => api('/api/manpower/me').then(m => { setMe(m); setF(m); }).catch(() => setMe({}));
  const uploadPhoto = async (fileObj) => {
    if (!fileObj) return;
    if (!/^image\//.test(fileObj.type || '')) { toast('Please choose an image file', 'err'); return; }
    setPhotoBusy(true);
    try {
      const fd = new FormData(); fd.append('file', fileObj);
      await api('/api/manpower/me/photo', { method: 'POST', form: fd });
      toast('Profile photo updated.'); load();
    } catch (e) { toast(e.message, 'err'); } finally { setPhotoBusy(false); }
  };
  useEffect(() => { load(); if (showTrends) api('/api/mis/employee-trends?user_id=' + user.id).then(r => setTrends(r.trends)).catch(() => {}); }, []);
  const isHR = ['admin', 'headoffice', 'hr'].includes(user.role);
  const canEdit = me && (!me.profile_completed || isHR);
  const upd = (k, v) => setF(s => ({ ...s, [k]: v }));
  const save = async () => {
    setBusy(true);
    try {
      const body = {}; PROFILE_FIELDS.forEach(([k]) => { if (f[k] !== undefined && f[k] !== null) body[k] = f[k]; });
      await api('/api/manpower/me', { method: 'PATCH', body });
      toast(isHR ? 'Profile saved.' : 'Profile completed — thank you! Contact HR for further changes.');
      setEditing(false); load();
    } catch (e) { toast(e.message, 'err'); } finally { setBusy(false); }
  };
  if (!me) return <Loader />;
  // Admin / system logins aren't part of the HR manpower sheet, so their own card has no
  // personal fields. Show a clear note (not a wall of dashes) pointing to where staff
  // details actually live, rather than looking broken.
  const noHr = !(me.phone || me.designation || me.location || me.dob || me.blood_group || me.aadhar_number);
  return (
    <div>
      <div className="section-h"><h2 style={{ margin: 0 }}>My E-ID</h2></div>
      {showTrends && trends && <TrendStrip trends={trends} title="My achievement (cash collected) — FTD / MTD / LMTD / Overall" />}
      {noHr && isHR && <div className="glass card" style={{ margin: '4px 0 14px', borderLeft: '3px solid var(--gold)' }}>
        <b>This is a system/admin login — it has no personal HR record.</b>
        <p className="muted" style={{ fontSize: 13, margin: '4px 0 0' }}>
          Every employee's phone number and full details are on the <b>🧑‍💼 Manpower</b> page
          (in the left menu). Open it to search staff, view each person's E-ID, call them, or
          download the directory. Only real employees imported from the HR sheet carry these fields.
        </p></div>}
      <div style={{ display: 'grid', gridTemplateColumns: 'auto 1fr', gap: 18, alignItems: 'start', flexWrap: 'wrap' }}>
        <div>
          <EIDCard e={{ ...me, ...f }} />
          <label className="btn sm" style={{ marginTop: 8, display: 'inline-flex', alignItems: 'center', gap: 6, cursor: photoBusy ? 'default' : 'pointer', opacity: photoBusy ? 0.6 : 1 }}>
            {photoBusy ? 'Uploading…' : '📷 Change photo'}
            <input type="file" accept="image/*" style={{ display: 'none' }} disabled={photoBusy}
              onChange={e => { uploadPhoto(e.target.files[0]); e.target.value = ''; }} />
          </label>
        </div>
        <div style={{ minWidth: 280, flex: 1 }}>
          {!editing ? (<>
            <div className="dl">
              {[['Employee code', me.emp_code], ['Role', roleName(me.role)], ['Designation', me.designation],
                ['Location', me.location], ['Branch', me.branch], ['Email', me.email], ['Phone', me.phone],
                ['DOB', me.dob], ['Blood group', me.blood_group], ['Joined', me.joining_date]].map(([k, v]) =>
                <React.Fragment key={k}><div className="dt">{k}</div><div className="dd">{v || '—'}</div></React.Fragment>)}
            </div>
            {canEdit && <button className="btn gold" style={{ marginTop: 12 }} onClick={() => setEditing(true)}>
              {me.profile_completed ? '✏ Edit profile' : '✏ Complete my profile (one-time)'}</button>}
            {!me.profile_completed && !isHR && <p className="muted" style={{ fontSize: 12, marginTop: 8 }}>You can complete your profile once. After saving, ask HR for any further change.</p>}
            {me.profile_completed && !isHR && <p className="muted" style={{ fontSize: 12, marginTop: 8 }}>🔒 Your profile is completed and locked. Contact HR/admin for changes.</p>}
          </>) : (<>
            <div className="grid2" style={{ gridTemplateColumns: '1fr 1fr', gap: 10 }}>
              {PROFILE_FIELDS.map(([k, label, type]) => <div className="field" key={k}>
                <label>{label}</label>
                <input className="input" type={type} value={(f[k] || (type === 'date' ? '' : '')) && type === 'date' ? String(f[k]).slice(0, 10) : (f[k] || '')} onChange={e => upd(k, e.target.value)} /></div>)}
            </div>
            <div className="toolbar" style={{ marginTop: 8 }}><button className="btn" onClick={() => { setEditing(false); setF(me); }}>Cancel</button><div style={{ flex: 1 }} />
              <button className="btn gold" disabled={busy} onClick={save}>{busy ? 'Saving…' : (me.profile_completed ? 'Save' : 'Save & complete')}</button></div>
          </>)}
        </div>
      </div>
    </div>
  );
}

const NAV = {
  admin: [['dashboard', '📊', 'Dashboard'], ['cases', '🗂️', 'Accounts'], ['sheet', '📊', 'Live Sheet'], ['ptp', '🤝', 'PTP Tracker'], ['escalations', '🚩', 'Escalations'], ['legal', '⚖️', 'Litigation'], ['map', '📍', 'Field Tracking'], ['records', '🗃️', 'Activity'], ['audit', '📜', 'Audit Log'], ['archive', '🗄️', 'Monthly Archive'], ['staff', '👥', 'Team'], ['manpower', '🧑‍💼', 'Manpower'], ['mis', '📈', 'MIS'], ['feedback', '🏦', 'Bank Feedback'], ['leave', '🌴', 'Leave'], ['templates', '💬', 'Communication'], ['devices', '📱', 'Devices'], ['ai', '✨', 'AI Assist'], ['security', '🔒', 'Security']],
  manager: [['dashboard', '📊', 'Dashboard'], ['cases', '🗂️', 'Accounts'], ['ptp', '🤝', 'PTP Tracker'], ['escalations', '🚩', 'Escalations'], ['legal', '⚖️', 'Litigation'], ['map', '📍', 'Field Tracking'], ['records', '🗃️', 'Activity'], ['audit', '📜', 'Audit Log'], ['staff', '👥', 'Team'], ['manpower', '🧑‍💼', 'Manpower'], ['mis', '📈', 'MIS'], ['feedback', '🏦', 'Bank Feedback'], ['leave', '🌴', 'Leave'], ['templates', '💬', 'Communication'], ['devices', '📱', 'Devices'], ['ai', '✨', 'AI Assist'], ['security', '🔒', 'Security']],
  fos: [['dashboard', '📊', 'My Stats'], ['myperf', '🏆', 'My Performance'], ['fcases', '🗂️', 'My Accounts'], ['fmap', '📍', 'Field Tracking'], ['leave', '🌴', 'Leave'], ['ai', '✨', 'AI Assist'], ['security', '🔒', 'Security']],
  telecaller: [['dashboard', '📊', 'My Stats'], ['myperf', '🏆', 'My Performance'], ['queue', '📞', 'Calling'], ['sheet', '📊', 'Live Sheet'], ['feedback', '🏦', 'Bank Feedback'], ['ptp', '🤝', 'PTP Tracker'], ['leave', '🌴', 'Leave'], ['ai', '✨', 'AI Assist'], ['security', '🔒', 'Security']],
  teamlead: [['tldash', '👥', 'My Team'], ['cases', '🗂️', 'Team Accounts'], ['mis', '📈', 'MIS'], ['ptp', '🤝', 'PTP Tracker'], ['escalations', '🚩', 'Escalations'], ['feedback', '🏦', 'Bank Feedback'], ['leave', '🌴', 'Leave'], ['ai', '✨', 'AI Assist'], ['security', '🔒', 'Security']],
  backend: [['dashboard', '📊', 'Dashboard'], ['cases', '🗂️', 'Accounts'], ['escalations', '🚩', 'Escalations'], ['mis', '📈', 'MIS'], ['feedback', '🏦', 'Bank Feedback'], ['leave', '🌴', 'Leave'], ['ai', '✨', 'AI Assist'], ['security', '🔒', 'Security']],
  headoffice: [['dashboard', '📊', 'Dashboard'], ['cases', '🗂️', 'Portfolios'], ['sheet', '📊', 'Live Sheet'], ['ptp', '🤝', 'PTP Tracker'], ['escalations', '🚩', 'Escalations'], ['map', '📍', 'Field Tracking'], ['records', '🗃️', 'Activity'], ['audit', '📜', 'Audit Log'], ['staff', '👥', 'Team'], ['manpower', '🧑‍💼', 'Manpower'], ['mis', '📈', 'MIS'], ['feedback', '🏦', 'Bank Feedback'], ['leave', '🌴', 'Leave'], ['ai', '✨', 'AI Assist'], ['security', '🔒', 'Security']],
  hr: [['manpower', '🧑‍💼', 'Manpower'], ['leave', '🌴', 'Leave'], ['profile', '🪪', 'My E-ID'], ['security', '🔒', 'Security']],
  it: [['profile', '🪪', 'My E-ID'], ['leave', '🌴', 'Leave'], ['security', '🔒', 'Security']],
  staff: [['profile', '🪪', 'My E-ID'], ['leave', '🌴', 'Leave'], ['security', '🔒', 'Security']],
};
function NativeTrackingOnboard({ onDone }) {
  const openSettings = () => { try { const BG = window.Capacitor.registerPlugin('BackgroundGeolocation'); if (BG.openSettings) BG.openSettings(); } catch (e) {} };
  return (
    <div className="modal-bg">
      <div className="modal glass" onClick={e => e.stopPropagation()}>
        <div className="section-h"><h3>Turn on always-on tracking</h3></div>
        <p style={{ fontSize: 14, lineHeight: 1.6 }}>So your live location keeps sharing even when the phone is locked or you're using another app, please allow:</p>
        <ol style={{ fontSize: 14, lineHeight: 1.8, paddingLeft: 18, marginTop: 0 }}>
          <li>Location → tap <b>Allow</b>, then choose <b>"Allow all the time"</b></li>
          <li>Notifications → <b>Allow</b> (keeps the "on duty" status)</li>
          <li>Battery → <b>Unrestricted</b>; on Xiaomi/Oppo/Vivo also turn on <b>Autostart</b></li>
        </ol>
        <div className="toolbar" style={{ marginTop: 6 }}>
          <button className="btn gold" onClick={openSettings}>Open settings</button>
          <div style={{ flex: 1 }} />
          <button className="btn" onClick={onDone}>Done</button>
        </div>
      </div>
    </div>
  );
}

function NotificationBell({ onOpenCase, style }) {
  const [items, setItems] = useState([]); const [unread, setUnread] = useState(0); const [open, setOpen] = useState(false);
  const seen = React.useRef(new Set());
  const load = () => api('/api/notifications?limit=30').then(d => { setItems(d.items || []); setUnread(d.unread || 0); }).catch(() => {});
  useEffect(() => {
    load();
    const t = setInterval(load, 60000);
    const onNotif = (e) => {
      const n = e.detail || {};
      if (n.id && seen.current.has(n.id)) return;
      if (n.id) seen.current.add(n.id);
      toast('🔔 ' + (n.title || 'New notification'));
      load();
    };
    window.addEventListener('ssd-notif', onNotif);
    return () => { clearInterval(t); window.removeEventListener('ssd-notif', onNotif); };
  }, []);
  const click = (n) => {
    if (!n.read) api(`/api/notifications/${n.id}/read`, { method: 'POST' }).then(load).catch(() => {});
    setOpen(false);
    if (n.case_id && onOpenCase) onOpenCase(n.case_id);
  };
  const markAll = () => api('/api/notifications/read-all', { method: 'POST' }).then(load).catch(() => {});
  return (
    <div style={{ position: 'relative', ...style }}>
      <button className="btn ghost sm" onClick={() => { setOpen(o => !o); if (!open) load(); }} title="Notifications" style={{ fontSize: 18, lineHeight: 1, position: 'relative' }}>
        🔔{unread > 0 && <span style={{ position: 'absolute', top: -5, right: -5, background: 'var(--bad)', color: '#fff', borderRadius: 10, fontSize: 10, minWidth: 16, height: 16, display: 'inline-flex', alignItems: 'center', justifyContent: 'center', padding: '0 4px' }}>{unread > 99 ? '99+' : unread}</span>}
      </button>
      {open && <div className="glass card" style={{ position: 'absolute', right: 0, top: '115%', width: 320, maxHeight: 420, overflow: 'auto', zIndex: 60, padding: 8 }}>
        <div className="section-h" style={{ marginBottom: 6 }}><b>Notifications</b>{unread > 0 && <button className="btn ghost sm" onClick={markAll}>Mark all read</button>}</div>
        {items.length === 0 ? <p className="muted" style={{ fontSize: 13, padding: '8px 4px' }}>No notifications yet.</p> :
          items.map(n => <div key={n.id} onClick={() => click(n)} style={{ padding: '8px 6px', borderRadius: 8, cursor: 'pointer', background: n.read ? 'transparent' : 'rgba(37,99,235,.08)', borderBottom: '1px solid var(--line)' }}>
            <div style={{ fontWeight: n.read ? 500 : 700, fontSize: 13 }}>{n.title}</div>
            <div className="muted" style={{ fontSize: 12, whiteSpace: 'pre-wrap' }}>{n.body}</div>
            <div className="muted" style={{ fontSize: 10, marginTop: 2 }}>{n.created_at ? fmtDT(n.created_at) : ''}</div>
          </div>)}
      </div>}
    </div>
  );
}
/* ==================== Guided tour (per-role onboarding) ==================== */
// Bump this whenever the app changes enough that everyone should see the tour again.
const TOUR_VERSION = 1;
const TOUR_DESC = {
  dashboard: 'Your home base — headline numbers at a glance: total cases, recovery %, cash collected, pending, and your resolution %.',
  tldash: 'My Team — your team’s overview, members and their performance, all scoped to you.',
  myperf: 'My Performance — how much you’ve achieved (FTD / MTD / LMTD / Overall), broken down per portfolio, with a live leaderboard.',
  cases: 'Portfolios & Accounts — browse every portfolio; open any case for full details, payments and history.',
  fcases: 'My Accounts — your assigned field cases grouped by bank & bucket. Search, filter, or view them on a map.',
  sheet: 'Live Sheet — an editable spreadsheet of your cases. Log payments and edits here and they sync instantly for everyone.',
  queue: 'Calling — your call queue: who’s due now, contacted today, upcoming and paid. Search, filter by status/bank/bucket to work faster.',
  ptp: 'PTP Tracker — promise-to-pay cases split into overdue / due today / upcoming so you chase the right ones first.',
  mis: 'MIS — full recovery analytics: leaderboards, month-wise and cycle-wise pivots, targets and downloads.',
  feedback: 'Bank Feedback — the daily bank sheet, auto-filled from call & visit logs. Edit and download it per day.',
  map: 'Field Tracking — live agent locations, routes and visit history on the map.',
  fmap: 'Field Tracking — your live location and today’s route; log GPS-stamped visits from here.',
  leave: 'Leave — apply for leave and track your approvals.',
  manpower: 'Manpower — employee records, the document vault (upload a whole folder), and offer / agreement letters.',
  staff: 'Team — branch staff, their profiles and performance.',
  escalations: 'Escalations — hard or high-value cases pulled up for special attention.',
  records: 'Activity — a live log of every call, visit and payment.',
  audit: 'Audit Log — a full trail of every change made in the system.',
  archive: 'Monthly Archive — closed months, kept for reference.',
  templates: 'Communication — WhatsApp / SMS message templates.',
  devices: 'Devices — approve or block the devices your staff log in from.',
  legal: 'Litigation — the legal / court case tracker.',
  ai: 'AI Assist — ask plain-English questions about your data.',
  security: 'Security — change your password and set up 2-factor authentication.',
  profile: 'My E-ID — your profile, ID card and personal details.',
};

function TourOverlay({ steps, go, onClose }) {
  const [idx, setIdx] = useState(0);
  const [rect, setRect] = useState(null);
  const step = steps[idx] || {};
  useEffect(() => {
    if (step.navId && go) go(step.navId);
    const measure = () => {
      if (!step.navId) { setRect(null); return; }
      const els = Array.from(document.querySelectorAll(`[data-nav="${step.navId}"]`));
      const el = els.find(e => e.offsetParent !== null) || els[0];
      setRect(el ? el.getBoundingClientRect() : null);
    };
    const t = setTimeout(measure, 90);
    const on = () => measure();
    window.addEventListener('resize', on); window.addEventListener('scroll', on, true);
    return () => { clearTimeout(t); window.removeEventListener('resize', on); window.removeEventListener('scroll', on, true); };
  }, [idx]); // eslint-disable-line
  const last = idx === steps.length - 1;
  const next = () => { if (last) onClose(); else setIdx(i => i + 1); };
  const vw = window.innerWidth, vh = window.innerHeight;
  let cardStyle;
  if (rect && rect.width) {
    if (vw - rect.right > 350) cardStyle = { left: rect.right + 14, top: Math.min(Math.max(12, rect.top - 8), vh - 240) };
    else if (rect.top > 260) cardStyle = { left: Math.min(Math.max(12, rect.left), vw - 342), top: rect.top - 224 };
    else cardStyle = { left: Math.min(Math.max(12, rect.left), vw - 342), top: rect.bottom + 14 };
  } else cardStyle = { left: '50%', top: '50%', transform: 'translate(-50%,-50%)' };
  return (
    <div style={{ position: 'fixed', inset: 0, zIndex: 3000 }}>
      {rect && rect.width
        ? <div style={{ position: 'fixed', left: rect.left - 6, top: rect.top - 6, width: rect.width + 12, height: rect.height + 12, borderRadius: 12, boxShadow: '0 0 0 9999px rgba(8,15,35,.62)', border: '2px solid var(--gold, #C7A24A)', pointerEvents: 'none', transition: 'all .2s' }} />
        : <div style={{ position: 'fixed', inset: 0, background: 'rgba(8,15,35,.62)' }} />}
      <div style={{ position: 'fixed', width: 320, maxWidth: '92vw', ...cardStyle, background: '#fff', color: '#111', borderRadius: 14, boxShadow: '0 18px 50px rgba(0,0,0,.35)', padding: 16 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 8 }}>
          <b style={{ fontSize: 15 }}>{step.title}</b>
          <button className="btn ghost sm" onClick={onClose} title="Skip tour">Skip ✕</button>
        </div>
        <p style={{ fontSize: 13.5, lineHeight: 1.55, margin: '8px 0 12px', color: '#374151' }}>{step.body}</p>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <div style={{ display: 'flex', gap: 4, flex: 1, flexWrap: 'wrap' }}>
            {steps.map((_, i) => <span key={i} onClick={() => setIdx(i)} style={{ width: 7, height: 7, borderRadius: '50%', cursor: 'pointer', background: i === idx ? 'var(--gold,#C7A24A)' : '#d1d5db' }} />)}
          </div>
          {idx > 0 && <button className="btn sm" onClick={() => setIdx(i => Math.max(0, i - 1))}>Back</button>}
          <button className="btn gold sm" onClick={next}>{last ? 'Done' : 'Next ›'}</button>
        </div>
        <div style={{ fontSize: 11, color: '#9aa4b2', marginTop: 6 }}>Step {idx + 1} of {steps.length}</div>
      </div>
    </div>
  );
}

function Shell({ user, config, onLogout, installEvt, onInstall, canSwitchView, onSwitchView }) {
  const baseNav = NAV[user.role] || NAV.telecaller;
  // Everyone gets a personal E-ID / profile entry.
  const nav = baseNav.some(n => n[0] === 'profile') ? baseNav : [...baseNav, ['profile', '🪪', 'My E-ID']];
  const [view, setView] = useState(nav[0][0]);
  const [trackOnboard, setTrackOnboard] = useState(false);
  const [notifCase, setNotifCase] = useState(null);
  const [tour, setTour] = useState(false);
  // Per-role guided tour: welcome → one step per feature → finish. Shown once, reopenable.
  const tourKey = `ssd_tour_v${TOUR_VERSION}_${user.id}_${user.role}`;
  const firstName = (user.name || '').split(' ')[0] || 'there';
  const tourSteps = [{ title: `👋 Welcome, ${firstName}!`, body: `Here’s a quick tour of your ${roleName(user.role)} workspace — we’ll walk through each feature. You can skip anytime and reopen this from the “?” button in the bottom-right corner.` }]
    .concat(nav.map(([id, ic, label]) => ({ navId: id, title: `${ic} ${label}`, body: TOUR_DESC[id] || `Open ${label}.` })))
    .concat([{ title: '🎉 You’re all set!', body: 'That’s the tour. Whenever you need it again, tap the “?” button in the bottom-right corner. Happy working!' }]);
  const closeTour = () => { try { localStorage.setItem(tourKey, '1'); } catch (e) {} setTour(false); };
  useEffect(() => { try { if (!localStorage.getItem(tourKey)) { const t = setTimeout(() => setTour(true), 800); return () => clearTimeout(t); } } catch (e) {} }, [tourKey]);
  useLocationPing(user, config);
  useEffect(() => {
    try {
      const cap = window.Capacitor;
      const native = cap && (cap.isNativePlatform ? cap.isNativePlatform() : cap.isNative);
      if (native && user.role === 'fos' && !localStorage.getItem('ssd_trackonboard')) setTrackOnboard(true);
    } catch (e) {}
  }, []);
  const title = (nav.find(n => n[0] === view) || [, , ''])[2];
  const render = () => {
    switch (view) {
      case 'dashboard': return <Dashboard user={user} />;
      case 'cases': return <CasesView user={user} />;
      case 'map': return <LiveMap config={config} />;
      case 'staff': return <StaffView config={config} user={user} />;
      case 'tldash': return <TeamLeadView config={config} user={user} />;
      case 'records': return <RecordsView user={user} />;
      case 'audit': return <AuditLogView user={user} />;
      case 'archive': return <ArchiveView user={user} />;
      case 'manpower': return <ManpowerView user={user} />;
      case 'profile': return <ProfileView user={user} config={config} />;
      case 'feedback': return <FeedbackView user={user} />;
      case 'escalations': return <EscalationsView user={user} />;
      case 'devices': return <DevicesView />;
      case 'leave': return <LeaveView user={user} />;
      case 'templates': return <TemplatesView />;
      case 'legal': return <LegalView />;
      case 'fcases': return <FOCases config={config} />;
      case 'fmap': return <FOLiveMap config={config} />;
      case 'queue': return <CallQueue />;
      case 'myperf': return <MyPerformance user={user} />;
      case 'mis': return <MISView user={user} />;
      case 'sheet': return <SheetView user={user} config={config} />;
      case 'ptp': return <PTPTracker />;
      case 'ai': return <AIAssist user={user} />;
      case 'security': return <SecurityView user={user} />;
      default: return null;
    }
  };
  return (
    <div className="app">
      <aside className="sidebar glass" style={{ borderRadius: 0 }}>
        <div className="brand"><img src="assets/logo.png" alt="" />
          <div><div className="n brandfont" style={{ fontSize: 16 }}>{(config && config.brand_name) || 'RecoverIQ'}</div>
            <div className="s" style={{ fontSize: 10 }}>{roleName(user.role)}</div></div></div>
        {canSwitchView && <div className="navitem" onClick={onSwitchView}
          title="You have more than one role — switch your active view"
          style={{ background: 'rgba(59,130,246,.10)', color: 'var(--info)', fontWeight: 600 }}>
          <span className="ic">🔀</span>Switch view</div>}
        <div className="navscroll">
          {nav.map(([id, ic, label]) => <div key={id} data-nav={id} className={cx('navitem', view === id && 'active')} onClick={() => setView(id)}>
            <span className="ic">{ic}</span>{label}</div>)}
        </div>
        <AndroidDownloadButton compact block style={{ margin: '4px 0' }} />
        <div className="navitem signout" onClick={onLogout}><span className="ic">⎋</span>Sign out</div>
      </aside>
      <main className="main">
        <div className="topbar">
          <h1>{title}</h1>
          {installEvt && <button className="btn sm gold" style={{ marginLeft: 'auto', marginRight: 10 }} onClick={onInstall}>⬇ Install app</button>}
          <NotificationBell onOpenCase={setNotifCase} style={{ marginLeft: installEvt ? 0 : 'auto', marginRight: 10 }} />
          <div className="usertag"><div className="avatar">{initials(user.name)}</div>
            <div><div style={{ fontWeight: 600, fontSize: 14 }}>{user.name}</div>
              <div className="muted" style={{ fontSize: 12 }}>{user.branch || user.email}</div></div></div>
        </div>
        {render()}
        {notifCase && <CaseDrawer c={{ id: notifCase }} onClose={() => setNotifCase(null)} onChanged={() => {}} />}
        {trackOnboard && <NativeTrackingOnboard onDone={() => { try { localStorage.setItem('ssd_trackonboard', '1'); } catch (e) {} setTrackOnboard(false); }} />}
      </main>
      <nav className="mobnav">
        {nav.map(([id, ic, label]) => <div key={id} data-nav={id} className={cx('navitem', view === id && 'active')} onClick={() => setView(id)}>
          <span className="ic">{ic}</span>{label}</div>)}
        <div className="navitem" onClick={onLogout}><span className="ic">⎋</span>Sign out</div>
      </nav>

      {/* Floating help / tour button (bottom-right) — reopens the guided tour anytime. */}
      <button onClick={() => setTour(true)} title="App tour / help"
        style={{ position: 'fixed', right: 18, bottom: 'calc(18px + env(safe-area-inset-bottom, 0px))', zIndex: 2500, width: 50, height: 50, borderRadius: '50%', border: '2px solid var(--gold,#C7A24A)', background: 'var(--navy,#0B234F)', color: 'var(--gold,#C7A24A)', fontSize: 22, fontWeight: 800, cursor: 'pointer', boxShadow: '0 8px 22px rgba(11,35,79,.35)' }}>?</button>

      {tour && <TourOverlay steps={tourSteps} go={setView} onClose={closeTour} />}
    </div>
  );
}

/* First-login gate: force a new password before the app opens. */
function ForcePasswordChange({ user, onDone, onLogout }) {
  const [cur, setCur] = useState('');
  const [pw, setPw] = useState('');
  const [pw2, setPw2] = useState('');
  const [busy, setBusy] = useState(false); const [err, setErr] = useState('');
  const submit = async () => {
    if (pw.length < 6) { setErr('New password must be at least 6 characters.'); return; }
    if (pw !== pw2) { setErr('The two new passwords do not match.'); return; }
    setBusy(true); setErr('');
    try {
      const r = await api('/api/auth/change-password', { method: 'POST', body: { current_password: cur, new_password: pw } });
      store.t = r.access_token; store.u = r.user;
      toast('Password updated — welcome!');
      onDone(r.user);
    } catch (e) { setErr(e.message); setBusy(false); }
  };
  return (
    <div style={{ display: 'flex', minHeight: '100vh', alignItems: 'center', justifyContent: 'center', padding: 20 }}>
      <div className="glass card" style={{ maxWidth: 420, width: '100%', padding: 24 }}>
        <div className="brandfont" style={{ fontSize: 20, fontWeight: 700, color: 'var(--brand)' }}>Set a new password</div>
        <p className="muted" style={{ fontSize: 13, marginTop: 4 }}>Hi {user.name?.split(' ')[0] || 'there'} — for your security, please replace the temporary password before continuing.</p>
        <div className="field"><label>Current (temporary) password</label>
          <input className="input" type="password" value={cur} onChange={e => setCur(e.target.value)} placeholder="Ssd@2026" autoFocus /></div>
        <div className="field"><label>New password</label>
          <input className="input" type="password" value={pw} onChange={e => setPw(e.target.value)} /></div>
        <div className="field"><label>Confirm new password</label>
          <input className="input" type="password" value={pw2} onChange={e => setPw2(e.target.value)} onKeyDown={e => { if (e.key === 'Enter') submit(); }} /></div>
        {err && <div style={{ color: 'var(--bad)', fontSize: 13, marginBottom: 8 }}>{err}</div>}
        <button className="btn gold block" disabled={busy} onClick={submit}>{busy ? 'Saving…' : 'Save & continue'}</button>
        <button className="btn ghost block" style={{ marginTop: 8 }} onClick={onLogout}>Sign out</button>
      </div>
    </div>
  );
}

/* Dual-role "which hat?" picker — shown right after login for a caller/FOS who is also a
   team lead, and again whenever they tap "Switch view". One hat at a time. */
const VIEW_META = {
  teamlead: ['👥', 'Team Leader', 'Your team’s cases, MIS & DPR'],
  fos: ['🗺️', 'Field Agent', 'Your field visits & route'],
  telecaller: ['📞', 'Tele-calling', 'Your calling queue'],
  manager: ['🏢', 'Manager', 'Branch overview'],
  headoffice: ['🏛️', 'Head Office', 'All portfolios'],
  admin: ['🛡️', 'Administrator', 'Full access'],
};
function ViewPicker({ user, onPicked, onLogout }) {
  const [busy, setBusy] = useState('');
  const views = user.available_views || [user.role];
  const pick = async (v) => {
    setBusy(v);
    try {
      const r = await api('/api/auth/switch-view', { method: 'POST', body: { view: v } });
      store.t = r.access_token; store.u = r.user; onPicked(r.user);
    } catch (e) { toast(e.message || 'Could not switch view'); setBusy(''); }
  };
  return (
    <div style={{ display: 'flex', minHeight: '100vh', alignItems: 'center', justifyContent: 'center', padding: 20 }}>
      <div className="glass card" style={{ maxWidth: 460, width: '100%', padding: 26 }}>
        <div className="brandfont" style={{ fontSize: 20, fontWeight: 700, color: 'var(--info)' }}>Choose your view</div>
        <p className="muted" style={{ fontSize: 13, marginTop: 4 }}>
          Hi {user.name?.split(' ')[0] || 'there'} — you have more than one role. Pick how you want to work now; you can switch anytime.
        </p>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10, marginTop: 14 }}>
          {views.map(v => { const [ic, title, sub] = VIEW_META[v] || ['•', v, '']; return (
            <button key={v} className="glass card" disabled={!!busy}
              onClick={() => pick(v)}
              style={{ display: 'flex', alignItems: 'center', gap: 14, padding: '14px 16px', cursor: 'pointer', textAlign: 'left', border: '1px solid var(--stroke)' }}>
              <span style={{ fontSize: 26 }}>{ic}</span>
              <span style={{ flex: 1 }}>
                <div style={{ fontWeight: 700 }}>{title}{v === user.active_view ? '  ·  current' : ''}</div>
                <div className="muted" style={{ fontSize: 12 }}>{sub}</div>
              </span>
              <span className="muted">{busy === v ? '…' : '→'}</span>
            </button>
          ); })}
        </div>
        <button className="btn ghost block" style={{ marginTop: 14 }} onClick={onLogout}>Sign out</button>
      </div>
    </div>
  );
}

function App() {
  const [user, setUser] = useState(store.u); const [config, setConfig] = useState(null); const [ready, setReady] = useState(false);
  const [installEvt, setInstallEvt] = useState(null);
  const [pendingPick, setPendingPick] = useState(false);
  // After a fresh login (or password change), a dual-role user must choose a view.
  const handleLogin = (u) => { setUser(u); setPendingPick(!!(u && (u.available_views || []).length > 1)); };
  useEffect(() => {
    api('/api/config', { auth: false }).then(cfg => { setConfig(cfg); window.__ssdCfg = cfg; }).catch(() => setConfig({}));
    if (store.t) api('/api/auth/me').then(u => { setUser(u); store.u = u; }).catch(() => { store.t = null; setUser(null); }).finally(() => setReady(true));
    else setReady(true);
    const h = (e) => { e.preventDefault(); setInstallEvt(e); };
    window.addEventListener('beforeinstallprompt', h);
    return () => window.removeEventListener('beforeinstallprompt', h);
  }, []);
  const logout = () => { store.t = null; store.u = null; setUser(null); };
  const install = async () => { if (!installEvt) return; installEvt.prompt(); try { await installEvt.userChoice; } catch {} setInstallEvt(null); };
  if (!ready || !config) return <div style={{ display: 'flex', height: '100vh', alignItems: 'center', justifyContent: 'center' }}><Loader /></div>;
  const multiView = user && (user.available_views || []).length > 1;
  return (<>
    <Toaster />
    {user ? (user.must_change_password
        ? <ForcePasswordChange user={user} onDone={handleLogin} onLogout={logout} />
        : (pendingPick && multiView)
          ? <ViewPicker user={user} onPicked={(u) => { setUser(u); setPendingPick(false); }} onLogout={logout} />
          : <Shell user={user} config={config} onLogout={logout} installEvt={installEvt} onInstall={install}
                   canSwitchView={multiView} onSwitchView={() => setPendingPick(true)} />)
      : <Login onLogin={handleLogin} config={config} />}
  </>);
}

/* Catches render crashes and shows the real error (instead of a cross-origin "Script error"). */
class ErrorBoundary extends React.Component {
  constructor(props) { super(props); this.state = { err: null, info: null }; }
  static getDerivedStateFromError(err) { return { err }; }
  componentDidCatch(err, info) { this.setState({ info }); try { console.error('App crash:', err, info); } catch (e) {} }
  render() {
    if (!this.state.err) return this.props.children;
    const msg = String((this.state.err && (this.state.err.stack || this.state.err.message)) || this.state.err);
    const cs = this.state.info && this.state.info.componentStack;
    return (
      <div style={{ maxWidth: 680, margin: '48px auto', padding: 22, borderRadius: 16, background: '#FDECEC', border: '1px solid rgba(220,38,38,.4)', color: '#7f1d1d', fontFamily: 'system-ui', lineHeight: 1.5 }}>
        <div style={{ fontWeight: 700, marginBottom: 8, fontSize: 16 }}>Something went wrong</div>
        <pre style={{ whiteSpace: 'pre-wrap', fontSize: 12.5, margin: 0 }}>{msg}</pre>
        {cs && <pre style={{ whiteSpace: 'pre-wrap', fontSize: 11.5, marginTop: 10, color: '#9a3b3b' }}>{cs.split('\n').slice(0, 8).join('\n')}</pre>}
        <button onClick={() => { store.t = null; store.u = null; location.reload(); }} style={{ marginTop: 14, padding: '9px 16px', borderRadius: 10, border: 'none', background: '#DC2626', color: '#fff', fontWeight: 600, cursor: 'pointer' }}>Sign out &amp; reload</button>
      </div>
    );
  }
}

ReactDOM.createRoot(document.getElementById('root')).render(<ErrorBoundary><App /></ErrorBoundary>);
// build: v11


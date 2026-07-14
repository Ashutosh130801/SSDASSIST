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

// Field-officer presence: "live" if their app pinged within the last 3 minutes.
const ONLINE_MS = 3 * 60 * 1000;
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
      now.toLocaleString('en-IN', { day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' }),
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
const ROLE_LABEL = { admin: 'Administrator', manager: 'Collections Manager', fos: 'Field Agent', telecaller: 'Tele-calling Agent' };
const roleName = (r) => ROLE_LABEL[r] || r;

/* ============================== Login ============================== */
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
function Loader() { return <div className="spin"></div>; }

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

const STAGE_META = {
  new: { label: 'New', color: '#0EA5E9' },
  allocated: { label: 'Allocated', color: '#2563EB' },
  in_progress: { label: 'In Progress', color: '#D97706' },
  ptp: { label: 'PTP', color: '#8B5CF6' },
  paid: { label: 'Resolved', color: '#16A34A' },
  unpaid: { label: 'Unpaid', color: '#DC2626' },
};

function Dashboard({ user }) {
  const [d, setD] = useState(null); const [err, setErr] = useState('');
  useEffect(() => { api('/api/analytics/dashboard').then(setD).catch(e => setErr(e.message)); }, []);
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
        <StatCard icon="🎯" label="Portfolio Target" accent="" value={INR(k.target)}
          sub="Total outstanding funded" />
        <StatCard icon="✅" label="Recovered" accent="green" value={INR(k.received)} valueColor="var(--good)"
          sub={<span><b style={{ color: 'var(--good)' }}>{k.recovery_rate}%</b> recovery rate</span>} />
        <StatCard icon="⏳" label="Pending" accent="amber" value={INR(k.pending)} valueColor="var(--warn)"
          sub={<span>{INR(collectedToday)} collected today</span>} />
      </div>

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
function UploadModal({ onClose, onDone }) {
  const [file, setFile] = useState(null); const [bank, setBank] = useState('');
  const [branch, setBranch] = useState(''); const [prev, setPrev] = useState(null);
  const [busy, setBusy] = useState(false); const [err, setErr] = useState('');
  const doPreview = async () => {
    if (!file) return; setErr(''); setBusy(true);
    try { const f = new FormData(); f.append('file', file); if (bank) f.append('default_bank', bank);
      setPrev(await api('/api/import/preview', { method: 'POST', form: f }));
    } catch (e) { setErr(e.message); } finally { setBusy(false); }
  };
  const doCommit = async () => {
    if (!file) return; setErr(''); setBusy(true);
    try { const f = new FormData(); f.append('file', file); if (bank) f.append('default_bank', bank);
      if (branch) f.append('branch', branch); f.append('auto_allocate', 'true');
      const r = await api('/api/import/commit', { method: 'POST', form: f });
      toast(`Imported ${r.imported}, updated ${r.updated}. ${r.assigned_fos_total}/${r.total_cases} cases assigned to field agents.`);
      onDone();
    } catch (e) { setErr(e.message); } finally { setBusy(false); }
  };
  return (
    <div className="modal-bg" onClick={onClose}>
      <div className="modal glass" onClick={e => e.stopPropagation()}>
        <div className="section-h"><h3>Upload accounts from Excel</h3>
          <button className="btn ghost sm" onClick={onClose}>✕</button></div>
        <p className="muted" style={{ fontSize: 13 }}>Reads your loading-file / live-sheet formats and creates or updates cases, then auto-allocates by pincode &amp; nearest FO.</p>
        <div className="field"><label>Excel file (.xlsx)</label>
          <input className="input" type="file" accept=".xlsx,.xls"
            onChange={e => { setFile(e.target.files[0]); setPrev(null); }} /></div>
        <div className="grid2" style={{ gridTemplateColumns: '1fr 1fr' }}>
          <div className="field"><label>Default bank (if not in sheet)</label>
            <select className="input" value={bank} onChange={e => setBank(e.target.value)}>
              <option value="">— auto —</option><option>ICICI</option><option>RBL</option><option>AXIS</option></select></div>
          <div className="field"><label>Branch (optional)</label>
            <input className="input" value={branch} onChange={e => setBranch(e.target.value)} placeholder="Visakhapatnam" /></div>
        </div>
        {err && <div style={{ color: 'var(--bad)', fontSize: 13, marginBottom: 8 }}>{err}</div>}
        <div className="toolbar">
          <button className="btn" onClick={doPreview} disabled={!file || busy}>Preview</button>
          <button className="btn gold" onClick={doCommit} disabled={!file || busy}>{busy ? 'Working…' : 'Import & Allocate'}</button>
        </div>
        {prev && <div className="glass card" style={{ marginTop: 6 }}>
          <b>{prev.total_rows}</b> rows found in sheet <b>{prev.sheet}</b>. Preview:
          <div className="tablewrap" style={{ marginTop: 8 }}><table><thead><tr>
            <th>Name</th><th>Bank</th><th>Account</th><th>Target</th><th>Pincode</th></tr></thead>
            <tbody>{prev.sample.map((s, i) => <tr key={i}>
              <td>{s.customer_name}</td><td>{s.bank}</td><td className="mono">{s.account_no}</td>
              <td className="mono">{s.funding_amount}</td><td>{s.pincode || '—'}</td></tr>)}</tbody></table></div>
        </div>}
      </div>
    </div>
  );
}

function CasesView({ user }) {
  const [cases, setCases] = useState(null); const [bank, setBank] = useState('');
  const [paid, setPaid] = useState(''); const [q, setQ] = useState('');
  const [upload, setUpload] = useState(false); const [busy, setBusy] = useState(false); const [drawer, setDrawer] = useState(null); const [campaign, setCampaign] = useState(false);
  const [resetOpen, setResetOpen] = useState(false); const [resetTxt, setResetTxt] = useState('');
  const load = useCallback(() => {
    const p = new URLSearchParams(); if (bank) p.set('bank', bank); if (paid) p.set('paid_status', paid); if (q) p.set('search', q);
    api('/api/cases?' + p).then(setCases);
  }, [bank, paid, q]);
  useEffect(() => { const t = setTimeout(load, 250); return () => clearTimeout(t); }, [load]);
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

  return (
    <div>
      <div className="toolbar">
        <input className="input" style={{ maxWidth: 260 }} placeholder="Search name / account / phone / pincode"
          value={q} onChange={e => setQ(e.target.value)} />
        <select className="input" style={{ maxWidth: 130 }} value={bank} onChange={e => setBank(e.target.value)}>
          <option value="">All banks</option><option>ICICI</option><option>RBL</option><option>AXIS</option><option>BRBL</option></select>
        {['', 'PAID', 'UNPAID', 'PARTIAL'].map(s =>
          <div key={s} className={cx('chip', paid === s && 'on')} onClick={() => setPaid(s)}>{s || 'All'}</div>)}
        <div style={{ flex: 1 }} />
        {user.role === 'admin' && <>
          <button className="btn" onClick={() => setUpload(true)}>⬆ Upload</button>
          <button className="btn" onClick={allocate} disabled={busy}>⚡ Auto-allocate</button>
          <button className="btn" onClick={geocode} disabled={busy} title="Fill map coordinates from addresses">📍 Geocode</button>
          <button className="btn" onClick={() => setCampaign(true)} disabled={!cases || !cases.length}>💬 Campaign</button>
          <button className="btn gold" onClick={exportXlsx}>⬇ Export Excel</button>
          <button className="btn" style={{ borderColor: 'var(--bad)', color: 'var(--bad)' }} onClick={() => { setResetTxt(''); setResetOpen(true); }} disabled={busy}
            title="Delete all cases so you can upload a fresh loading file">🗑 Reset all</button>
        </>}
      </div>
      {!cases ? <Loader /> : (
        <div className="glass card" style={{ padding: 6 }}>
          <div className="tablewrap"><table>
            <thead><tr><th>Customer</th><th>Bank</th><th>Account</th><th>Target</th><th>Received</th>
              <th>Pending</th><th>Status</th><th>Paid</th><th>Score</th><th>Pincode</th><th>Dispo</th></tr></thead>
            <tbody>{cases.map(c => <tr key={c.id} style={{ cursor: 'pointer' }} onClick={() => setDrawer(c)}>
              <td><b>{c.customer_name || '—'}</b><div className="muted" style={{ fontSize: 12 }}>{c.phone}</div></td>
              <td>{c.bank}</td><td className="mono">{c.account_no}</td>
              <td className="mono">{INR(c.funding_amount)}</td>
              <td className="mono" style={{ color: 'var(--good)' }}>{INR(c.received_amount)}</td>
              <td className="mono" style={{ color: 'var(--warn)' }}>{INR(c.pending_amount)}</td>
              <td><StatusBadge s={c.status} /></td><td><PaidBadge s={c.paid_status} /></td>
              <td><PropBadge score={c.propensity} /></td>
              <td>{c.pincode || '—'}</td><td className="muted">{c.disposition || '—'}</td></tr>)}
            </tbody></table></div>
          {cases.length === 0 && <p className="muted" style={{ padding: 16 }}>No cases. Upload an Excel to get started.</p>}
        </div>
      )}
      {upload && <UploadModal onClose={() => setUpload(false)} onDone={() => { setUpload(false); load(); }} />}
      {campaign && <CampaignModal cases={cases || []} onClose={() => setCampaign(false)} />}
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
      {drawer && <CaseDrawer c={drawer} onClose={() => setDrawer(null)} onChanged={load} />}
    </div>
  );
}

/* ============================== Live Map (admin) ============================== */
function LiveMap({ config }) {
  const mapEl = useRef(null); const map = useRef(null); const markers = useRef({});
  const routeLine = useRef(null); const routeMarks = useRef([]); const routeActive = useRef(false);
  const [status, setStatus] = useState('loading'); const [officers, setOfficers] = useState([]);
  const [histOfficer, setHistOfficer] = useState(null); const [dates, setDates] = useState(null);
  const [selDate, setSelDate] = useState(''); const [routeInfo, setRouteInfo] = useState(null);

  const refresh = useCallback(async () => {
    try {
      const list = await api('/api/tracking/live?minutes=1440');
      list.sort((a, b) => (isOnline(b.last_seen) - isOnline(a.last_seen)) || String(a.name || '').localeCompare(b.name || ''));
      setOfficers(list);
      if (map.current && window.google) {
        const g = window.google; const bounds = new g.maps.LatLngBounds();
        Object.values(markers.current).forEach(m => m.setMap(null)); markers.current = {};
        list.forEach(o => {
          const pos = { lat: o.latitude, lng: o.longitude };
          const on = isOnline(o.last_seen);
          markers.current[o.officer_id] = new g.maps.Marker({
            position: pos, map: map.current, title: o.name + (on ? ' · live' : ' · offline ' + agoLabel(o.last_seen)),
            label: { text: initials(o.name), color: '#fff', fontWeight: '700' },
            icon: { path: g.maps.SymbolPath.CIRCLE, scale: 15, fillColor: on ? '#16A34A' : '#8494A8', fillOpacity: 1, strokeColor: on ? '#0f6e2f' : '#5b6b7f', strokeWeight: 2 },
          });
          bounds.extend(pos);
        });
        if (list.length && !routeActive.current) map.current.fitBounds(bounds, 80);
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
      timer = setInterval(refresh, 15000);   // near real-time (officers stream positions continuously)
    }).catch(() => setStatus('nokey'));
    return () => timer && clearInterval(timer);
  }, []);

  const navigateTo = (o) => window.open(`https://www.google.com/maps/dir/?api=1&destination=${o.latitude},${o.longitude}`, '_blank');

  const clearRoute = () => {
    routeActive.current = false;
    if (routeLine.current) { routeLine.current.setMap(null); routeLine.current = null; }
    routeMarks.current.forEach(m => m.setMap(null)); routeMarks.current = [];
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
      const g = window.google; const path = pts.map(p => ({ lat: p.latitude, lng: p.longitude }));
      routeLine.current = new g.maps.Polyline({ path, strokeColor: '#E9C877', strokeWeight: 4, strokeOpacity: .95, map: map.current });
      const mk = (pos, txt, fill, stroke) => new g.maps.Marker({ position: pos, map: map.current,
        label: { text: txt, color: '#0b0a06', fontWeight: '700', fontSize: '11px' },
        icon: { path: g.maps.SymbolPath.CIRCLE, scale: 11, fillColor: fill, fillOpacity: 1, strokeColor: stroke, strokeWeight: 2 } });
      routeMarks.current = [mk(path[0], 'S', '#5FD08A', '#0b3d1f'), mk(path[path.length - 1], 'E', '#F0776B', '#5a1710')];
      const b = new g.maps.LatLngBounds(); path.forEach(p => b.extend(p)); map.current.fitBounds(b, 60);
      routeActive.current = true;
      setRouteInfo((dates || []).find(d => d.date === selDate) || { points: pts.length });
    } catch (e) { toast(e.message, 'err'); }
  };

  return (
    <div>
      <div className="toolbar">
        <span className="muted">Live field-officer positions · auto-refresh every {config.location_ping_seconds || 60}s</span>
        <div style={{ flex: 1 }} />
        {routeActive.current && <button className="btn sm" onClick={() => { clearRoute(); setRouteInfo(null); refresh(); }}>✕ Clear route</button>}
        <button className="btn sm" onClick={refresh}>↻ Refresh</button>
      </div>
      {status === 'nokey' && <div className="glass card" style={{ marginBottom: 12, color: 'var(--warn)' }}>
        Map couldn't load — check the device's internet connection and reload.
      </div>}
      <div className="grid2" style={{ gridTemplateColumns: '1fr 320px' }}>
        <div className="glass" style={{ padding: 6 }}><div className="map tall" ref={mapEl}></div></div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
          <div className="glass card">
            <div className="section-h"><h3>Officers</h3>
              <span style={{ fontSize: 12 }}>
                <span style={{ color: 'var(--good)', fontWeight: 600 }}>● {officers.filter(o => isOnline(o.last_seen)).length} live</span>
                <span className="muted"> · {officers.filter(o => !isOnline(o.last_seen)).length} offline</span>
              </span></div>
            {officers.length === 0 && <p className="muted">No field officers active today. They appear here once their app has sent a location.</p>}
            {officers.map(o => { const on = isOnline(o.last_seen); return <div key={o.officer_id} style={{ padding: '9px 0', borderBottom: '1px solid var(--stroke-soft)', opacity: on ? 1 : .62 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 8 }}>
                <div><b><span style={{ color: on ? 'var(--good)' : 'var(--ink-dim)' }}>●</span> {o.name}</b>
                  <div className="muted" style={{ fontSize: 11.5 }}>{on ? 'Live now' : 'Offline · seen ' + agoLabel(o.last_seen)}</div></div>
                <div style={{ display: 'flex', gap: 6 }}>
                  <button className="btn sm gold" onClick={() => navigateTo(o)} title="Directions to live location">🧭</button>
                  <button className="btn sm" onClick={() => openHistory(o)} title="Route history">🕘</button>
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
            </>}
          </div>}
        </div>
      </div>
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
function StaffModal({ editing, onClose, onDone }) {
  const [f, setF] = useState(editing || { name: '', email: '', role: 'fos', branch: '', password: '',
    banks: [], assigned_pincodes: [], home_lat: '', home_lng: '' });
  const [busy, setBusy] = useState(false); const [err, setErr] = useState('');
  const upd = (k, v) => setF(s => ({ ...s, [k]: v }));
  const toggleBank = (b) => setF(s => ({ ...s, banks: s.banks.includes(b) ? s.banks.filter(x => x !== b) : [...s.banks, b] }));
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
        <div className="section-h"><h3>{editing ? 'Edit' : 'Add'} staff</h3>
          <button className="btn ghost sm" onClick={onClose}>✕</button></div>
        <div className="grid2" style={{ gridTemplateColumns: '1fr 1fr' }}>
          <div className="field"><label>Name</label><input className="input" value={f.name} onChange={e => upd('name', e.target.value)} /></div>
          <div className="field"><label>Email</label><input className="input" value={f.email} disabled={!!editing} onChange={e => upd('email', e.target.value)} /></div>
          <div className="field"><label>Role</label><select className="input" value={f.role} onChange={e => upd('role', e.target.value)}>
            <option value="fos">Field Agent</option><option value="telecaller">Tele-calling Agent</option><option value="manager">Collections Manager</option><option value="admin">Administrator</option></select></div>
          <div className="field"><label>Branch</label><input className="input" value={f.branch || ''} onChange={e => upd('branch', e.target.value)} /></div>
          <div className="field"><label>Phone</label><input className="input" value={f.phone || ''} onChange={e => upd('phone', e.target.value)} /></div>
          <div className="field"><label>{editing ? 'New password (blank = keep)' : 'Password'}</label>
            <input className="input" type="password" value={f.password || ''} onChange={e => upd('password', e.target.value)} /></div>
        </div>
        <div className="field"><label>Banks</label><div className="toolbar" style={{ margin: 0 }}>
          {['ICICI', 'RBL', 'AXIS'].map(b => <div key={b} className={cx('chip', f.banks.includes(b) && 'on')} onClick={() => toggleBank(b)}>{b}</div>)}
        </div></div>
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
        {err && <div style={{ color: 'var(--bad)', fontSize: 13 }}>{err}</div>}
        <button className="btn gold block" onClick={save} disabled={busy} style={{ marginTop: 8 }}>{busy ? 'Saving…' : 'Save'}</button>
      </div>
    </div>
  );
}
function RouteHistoryModal({ officer, config, onClose }) {
  const mapEl = useRef(null); const map = useRef(null); const line = useRef(null); const marks = useRef([]);
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
    if (line.current) { line.current.setMap(null); line.current = null; }
    marks.current.forEach(m => m.setMap(null)); marks.current = [];
    if (mover.current) { mover.current.setMap(null); mover.current = null; }
    setReady(false);
  };
  const show = async () => {
    if (!selDate) return; clear();
    try {
      const pts = await api(`/api/tracking/officer/${officer.id}/route?date=${selDate}`);
      if (!pts.length) { toast('No route recorded that day', 'err'); return; }
      const path = pts.map(p => ({ lat: p.latitude, lng: p.longitude }));
      pathRef.current = path; idx.current = 0;
      if (map.current && window.google) {
        const g = window.google;
        line.current = new g.maps.Polyline({ path, strokeColor: '#E9C877', strokeWeight: 4, strokeOpacity: .95, map: map.current });
        const mk = (pos, t, f, s) => new g.maps.Marker({ position: pos, map: map.current,
          label: { text: t, color: '#0b0a06', fontWeight: '700', fontSize: '11px' },
          icon: { path: g.maps.SymbolPath.CIRCLE, scale: 11, fillColor: f, fillOpacity: 1, strokeColor: s, strokeWeight: 2 } });
        marks.current = [mk(path[0], 'S', '#5FD08A', '#0b3d1f'), mk(path[path.length - 1], 'E', '#F0776B', '#5a1710')];
        mover.current = new g.maps.Marker({ position: path[0], map: map.current, zIndex: 999,
          icon: { path: g.maps.SymbolPath.FORWARD_CLOSED_ARROW, scale: 5, fillColor: '#6BB6F0', fillOpacity: 1, strokeColor: '#0f2f4a', strokeWeight: 2 } });
        const b = new g.maps.LatLngBounds(); path.forEach(p => b.extend(p)); map.current.fitBounds(b, 50);
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
  const mapEl = useRef(null), map = useRef(null), line = useRef(null), startMk = useRef(null), curMk = useRef(null);
  const [info, setInfo] = useState(null);
  const todayIST = new Date(Date.now() + 5.5 * 3600 * 1000).toISOString().slice(0, 10);
  const draw = async (fit) => {
    try {
      const pts = await api(`/api/tracking/officer/${officer.id}/route?date=${todayIST}`);
      if (!map.current || !window.google) return;
      const g = window.google;
      if (!pts.length) { setInfo({ points: 0 }); return; }
      const path = pts.map(p => ({ lat: p.latitude, lng: p.longitude }));
      if (line.current) line.current.setPath(path);
      else line.current = new g.maps.Polyline({ path, strokeColor: '#2563EB', strokeWeight: 4, strokeOpacity: .95, map: map.current });
      if (!startMk.current) startMk.current = new g.maps.Marker({ position: path[0], map: map.current,
        label: { text: 'S', color: '#fff' }, icon: { path: g.maps.SymbolPath.CIRCLE, scale: 10, fillColor: '#16A34A', fillOpacity: 1, strokeColor: '#0f6e2f', strokeWeight: 2 } });
      const cur = path[path.length - 1], last = pts[pts.length - 1].created_at, on = isOnline(last);
      if (curMk.current) curMk.current.setPosition(cur);
      else curMk.current = new g.maps.Marker({ position: cur, map: map.current, zIndex: 999,
        label: { text: initials(officer.name), color: '#fff' }, icon: { path: g.maps.SymbolPath.CIRCLE, scale: 13, fillColor: on ? '#16A34A' : '#8494A8', fillOpacity: 1, strokeColor: '#fff', strokeWeight: 2 } });
      let d = 0; for (let i = 1; i < path.length; i++) d += kmBetween(path[i - 1], path[i]);
      setInfo({ points: pts.length, distance_km: d, last, online: on });
      if (fit) { const b = new g.maps.LatLngBounds(); path.forEach(p => b.extend(p)); map.current.fitBounds(b, 60); }
    } catch (e) {}
  };
  useEffect(() => {
    let timer;
    loadMaps(config && config.google_maps_api_key).then(() => {
      const g = window.google;
      map.current = new g.maps.Map(mapEl.current, { center: { lat: 17.72, lng: 83.30 }, zoom: 13, styles: DARK_MAP_STYLE });
      draw(true); timer = setInterval(() => draw(false), 15000);
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
        <p className="muted" style={{ fontSize: 11.5, marginTop: 8 }}>Live — refreshes every 15s. Green “S” is where they started today; the labelled marker is their current position.</p>
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

function StaffView({ config }) {
  const [users, setUsers] = useState(null); const [modal, setModal] = useState(false); const [editing, setEditing] = useState(null);
  const [routeOfficer, setRouteOfficer] = useState(null); const [showReport, setShowReport] = useState(false);
  const [liveOfficer, setLiveOfficer] = useState(null);
  const load = () => api('/api/users').then(setUsers);
  useEffect(() => { load(); }, []);
  return (
    <div>
      <div className="toolbar"><div style={{ flex: 1 }} />
        <button className="btn" onClick={() => setShowReport(true)}>📅 Attendance report</button>
        <button className="btn gold" onClick={() => { setEditing(null); setModal(true); }}>+ Add staff</button></div>
      {!users ? <Loader /> : <div className="glass card" style={{ padding: 6 }}>
        <div className="tablewrap"><table>
          <thead><tr><th>Name</th><th>Role</th><th>Branch</th><th>Banks</th><th>Pincodes</th><th>Status</th><th></th></tr></thead>
          <tbody>{users.map(u => <tr key={u.id}>
            <td><b>{u.name}</b><div className="muted" style={{ fontSize: 12 }}>{u.email}</div></td>
            <td><span className="badge allocated">{roleName(u.role)}</span></td><td>{u.branch || '—'}</td>
            <td>{(u.banks || []).join(', ') || '—'}</td><td>{(u.assigned_pincodes || []).join(', ') || '—'}</td>
            <td>{u.is_active ? <span className="badge paid">active</span> : <span className="badge unpaid">off</span>}</td>
            <td style={{ whiteSpace: 'nowrap' }}>
              {u.role === 'fos' && <button className="btn sm gold" onClick={() => setLiveOfficer(u)} title="Today's live route & movement">📍 Live route</button>}
              {' '}{u.role === 'fos' && <button className="btn sm" onClick={() => setRouteOfficer(u)} title="3-month route history">🕘 History</button>}
              {' '}<button className="btn sm" onClick={() => { setEditing(u); setModal(true); }}>Edit</button></td></tr>)}
          </tbody></table></div></div>}
      {modal && <StaffModal editing={editing} onClose={() => setModal(false)} onDone={() => { setModal(false); load(); }} />}
      {routeOfficer && <RouteHistoryModal officer={routeOfficer} config={config} onClose={() => setRouteOfficer(null)} />}
      {liveOfficer && <LiveRouteModal officer={liveOfficer} config={config} onClose={() => setLiveOfficer(null)} />}
      {showReport && users && <ReportModal officers={users} onClose={() => setShowReport(false)} />}
    </div>
  );
}

/* ============================== Field Officer ============================== */
const DISPOS_FIELD = ['PAID', 'PTP', 'NOT AVAILABLE', 'MOVED', 'WRONG ADDRESS', 'DISPUTE', 'REFUSED', 'RNR'];

function VisitModal({ c, onClose, onDone }) {
  const [coords, setCoords] = useState(null); const [photo, setPhoto] = useState(null); const [photoUrl, setPhotoUrl] = useState(null);
  const fileRef = useRef(null); const [stamping, setStamping] = useState(false);
  const [locOk, setLocOk] = useState(true); const [moved, setMoved] = useState(false);
  const [paid, setPaid] = useState(false); const [amount, setAmount] = useState('');
  const [dispo, setDispo] = useState('PTP'); const [note, setNote] = useState('');
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
function groupCases(cases) {
  const banks = {};
  cases.forEach(c => {
    const bank = c.bank || '—'; const bucket = c.bucket || 'No bucket';
    (banks[bank] = banks[bank] || {});
    (banks[bank][bucket] = banks[bank][bucket] || []).push(c);
  });
  return Object.keys(banks).sort().map(bank => {
    const buckets = Object.keys(banks[bank]).sort((a, b) => bucketRank(a) - bucketRank(b)).map(bucket => {
      const list = banks[bank][bucket].slice().sort((a, b) => Number(b.pending_amount || 0) - Number(a.pending_amount || 0));
      return { bucket, cases: list, pending: list.reduce((s, c) => s + Number(c.pending_amount || 0), 0) };
    });
    return { bank, buckets,
      count: buckets.reduce((s, bk) => s + bk.cases.length, 0),
      pending: buckets.reduce((s, bk) => s + bk.pending, 0) };
  });
}
function CaseCard({ c, onVisit, onNav }) {
  const p = casePriority(c);
  return (
    <div className="glass card">
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8, alignItems: 'flex-start' }}>
        <b>{c.customer_name}</b>
        <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap', justifyContent: 'flex-end' }}>
          <span className={cx('badge', p.cls)}>{p.label}</span><PropBadge score={c.propensity} /></div></div>
      <div className="muted" style={{ fontSize: 13, margin: '4px 0 8px' }}>{c.bank} · {c.bucket || '—'} · cyc {c.cycle || '—'}</div>
      <div style={{ fontSize: 13, color: 'var(--ink-soft)', minHeight: 34 }}>{c.address || 'No address'} {c.pincode ? `(${c.pincode})` : ''}</div>
      <div className="stat-row"><span className="k">Pending</span><b className="mono" style={{ color: 'var(--warn)' }}>{INR(c.pending_amount)}</b></div>
      <div className="toolbar" style={{ margin: '10px 0 0' }}>
        <button className="btn sm gold" style={{ flex: 1 }} onClick={onVisit}>Log visit</button>
        <button className="btn sm" onClick={onNav}>🧭 Navigate</button>
        <ContactBtns phone={c.phone} />
      </div>
    </div>
  );
}

function FOLiveMap({ config }) {
  const mapEl = useRef(null); const map = useRef(null); const me = useRef(null); const acc = useRef(null);
  const route = useRef(null); const caseMarks = useRef([]); const watch = useRef(null);
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
          if (me.current) me.current.setPosition(p);
          else { me.current = new g.maps.Marker({ position: p, map: map.current, zIndex: 999, title: 'You',
            icon: { path: g.maps.SymbolPath.CIRCLE, scale: 8, fillColor: '#6BB6F0', fillOpacity: 1, strokeColor: '#ffffff', strokeWeight: 2 } });
            map.current.setCenter(p); map.current.setZoom(15); }
          if (acc.current) { acc.current.setCenter(p); acc.current.setRadius(r); }
          else acc.current = new g.maps.Circle({ center: p, radius: r, map: map.current, fillColor: '#6BB6F0', fillOpacity: .12, strokeColor: '#6BB6F0', strokeOpacity: .4, strokeWeight: 1 });
        }, () => {}, { enableHighAccuracy: true, maximumAge: 5000, timeout: 15000 });
      }
    }).catch(() => setNokey(true));
    return () => { if (routeTimer) clearInterval(routeTimer); if (watch.current != null && navigator.geolocation) navigator.geolocation.clearWatch(watch.current); };
  }, []);
  const recenter = () => { if (me.current && map.current) { map.current.panTo(me.current.getPosition()); map.current.setZoom(15); } };
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
  const [cases, setCases] = useState(null); const [view, setView] = useState('list'); const [active, setActive] = useState(null);
  const [collapsed, setCollapsed] = useState({}); const [bucketFilter, setBucketFilter] = useState('');
  const mapEl = useRef(null); const map = useRef(null);
  const load = () => api('/api/cases').then(setCases);
  useEffect(() => { load(); }, []);
  useEffect(() => {
    if (view !== 'map' || !cases) return;
    const pts = bucketFilter ? cases.filter(c => (c.bucket || 'No bucket') === bucketFilter) : cases;
    loadMaps(config && config.google_maps_api_key).then((g) => {
      map.current = new g.maps.Map(mapEl.current, { center: { lat: 17.72, lng: 83.30 }, zoom: 11, styles: DARK_MAP_STYLE });
      const bounds = new g.maps.LatLngBounds(); let any = false;
      pts.forEach(c => { if (c.latitude && c.longitude) { any = true;
        const m = new g.maps.Marker({ position: { lat: c.latitude, lng: c.longitude }, map: map.current, title: c.customer_name });
        m.addListener('click', () => setActive(c)); bounds.extend({ lat: c.latitude, lng: c.longitude }); } });
      if (any) map.current.fitBounds(bounds, 60);
    }).catch(() => { });
  }, [view, cases, bucketFilter]);
  const openNav = (c) => {
    const q = c.latitude && c.longitude ? `${c.latitude},${c.longitude}` : encodeURIComponent(c.address || c.pincode || '');
    window.open(`https://www.google.com/maps/dir/?api=1&destination=${q}`, '_blank');
  };
  if (!cases) return <Loader />;
  const allBuckets = Array.from(new Set(cases.map(c => c.bucket || 'No bucket'))).sort((a, b) => bucketRank(a) - bucketRank(b));
  const shown = bucketFilter ? cases.filter(c => (c.bucket || 'No bucket') === bucketFilter) : cases;
  const groups = groupCases(shown);
  const toggle = (bank) => setCollapsed(s => ({ ...s, [bank]: !s[bank] }));
  return (
    <div>
      <div className="toolbar">
        <div className={cx('chip', view === 'list' && 'on')} onClick={() => setView('list')}>☰ Grouped</div>
        <div className={cx('chip', view === 'map' && 'on')} onClick={() => setView('map')}>◎ Map</div>
        <div style={{ flex: 1 }} /><span className="muted">{shown.length}{bucketFilter ? ` of ${cases.length}` : ''} assigned</span>
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
        shown.length === 0 ? <p className="muted">No cases in this bucket.</p> :
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
                  {bk.cases.map(c => <CaseCard key={c.id} c={c} onVisit={() => setActive(c)} onNav={() => openNav(c)} />)}
                </div>
              </div>)}
            </div>)}
          </div>}
      {active && <VisitModal c={active} onClose={() => setActive(null)} onDone={() => { setActive(null); load(); }} />}
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
      let watcherId = null, cleared = false;
      try {
        const BG = Cap.registerPlugin('BackgroundGeolocation');
        BG.addWatcher({
          requestPermissions: true, stale: false, distanceFilter: 20,
          backgroundTitle: 'RecoverIQ — on duty',
          backgroundMessage: 'Sharing your live location with your branch.',
        }, (location, error) => {
          if (error || !location) return;
          api('/api/tracking/ping', { method: 'POST', body: { latitude: location.latitude, longitude: location.longitude, accuracy: location.accuracy, speed: location.speed } }).catch(() => {});
        }).then(id => { watcherId = id; if (cleared) BG.removeWatcher({ id }); });
      } catch (e) {}
      return () => { cleared = true; try { if (watcherId) Cap.registerPlugin('BackgroundGeolocation').removeWatcher({ id: watcherId }); } catch (e) {} };
    }
    // ---- Web fallback (foreground only) ----
    if (!navigator.geolocation) return;
    let alive = true, lastSent = 0, lastPos = null, watchId = null, wakeLock = null;
    const minGap = 12 * 1000;                                   // don't hit the server more than ~every 12s
    const heartbeatMs = Math.max(30, (config && config.location_ping_seconds) || 60) * 1000;
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
  const [paidAmt, setPaidAmt] = useState(''); const [note, setNote] = useState('');
  const [busy, setBusy] = useState(false); const [err, setErr] = useState('');
  const isPTP = dispo === 'PTP' || dispo === 'RTP'; const isPaid = dispo === 'PAID';
  const save = async () => {
    setErr(''); setBusy(true);
    const body = { case_id: c.id, disposition: dispo, note };
    if (isPTP) { body.ptp_amount = amt || '0'; body.ptp_date = ptpDate || null; }
    else if (isPaid) { body.paid_amount = paidAmt || '0'; }
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
        {isPaid && <div className="field"><label>Amount collected (₹)</label>
          <input className="input" type="number" value={paidAmt} onChange={e => setPaidAmt(e.target.value)} placeholder="0.00" /></div>}
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
  if (s.includes('PTP') || s.includes('RTP')) return '🤝';
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
  const [payAmt, setPayAmt] = useState(''); const [payMode, setPayMode] = useState('UPI'); const [payNote, setPayNote] = useState('');
  const [busy, setBusy] = useState(false);
  const isPTP = dispo === 'PTP' || dispo === 'RTP'; const isPaid = dispo === 'PAID';
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
    else if (isPaid) { body.paid_amount = amt || '0'; }
    else { body.follow_up_date = followDate || null; }
    try { await api('/api/calls', { method: 'POST', body }); toast('Call logged.');
      setCallNote(''); await refresh(); onChanged && onChanged();
    } catch (e) { toast(e.message, 'err'); } finally { setBusy(false); }
  };
  const recordPay = async () => {
    if (!payAmt) return; setBusy(true);
    try { const updated = await api(`/api/cases/${c.id}/payment`, { method: 'POST', body: { amount: payAmt, mode: payMode, note: payNote } });
      setCur(updated); setPayAmt(''); setPayNote(''); toast('Payment recorded.'); await refresh(); onChanged && onChanged();
    } catch (e) { toast(e.message, 'err'); } finally { setBusy(false); }
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
          {cur.phone && <a className="btn sm gold" href={'tel:' + cur.phone}>📞 Call</a>}
          {cur.phone && <a className="btn sm" href={'https://wa.me/' + String(cur.phone).replace(/[^0-9]/g, '')} target="_blank" rel="noreferrer">WhatsApp</a>}
          <StatusBadge s={cur.status} /><PaidBadge s={cur.paid_status} /><PropBadge score={cur.propensity} />
        </div>
        <div className="kpi3">
          <div className="b"><div className="l">Funded</div><div className="v">{INR(cur.funding_amount)}</div></div>
          <div className="b"><div className="l">Received</div><div className="v" style={{ color: 'var(--good)' }}>{INR(cur.received_amount)}</div></div>
          <div className="b"><div className="l">Pending</div><div className="v" style={{ color: 'var(--warn)' }}>{INR(cur.pending_amount)}</div></div>
        </div>
        <div className="divider"></div>
        <div className="section-h"><h3 style={{ fontSize: 14 }}>Account details</h3></div>
        <div className="dl">
          {row('Phone', cur.phone)}{row('Alt phone', cur.alt_phone)}
          {row('Address', cur.address)}{row('Pincode', cur.pincode)}
          {row('Bank / Product', (cur.bank || '') + (cur.product ? ' · ' + cur.product : ''))}
          {row('Card no', cur.card_no)}
          {row('Bucket / Cycle', (cur.bucket || '—') + ' · cyc ' + (cur.cycle || '—'))}
          {row('Month', cur.month)}
          {row('Last disposition', cur.disposition)}
          {row('Last contacted', cur.last_contacted_at ? new Date(cur.last_contacted_at).toLocaleString() : null)}
          {row('Next follow-up', cur.follow_up_date)}
          {row('Remarks', cur.remarks)}
        </div>
        <div className="divider"></div>
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
          {isPaid && <div className="field"><label>Amount collected (₹)</label><input className="input" type="number" value={amt} onChange={e => setAmt(e.target.value)} /></div>}
          {!isPTP && !isPaid && <div className="field"><label>Schedule next call (optional)</label><input className="input" type="date" value={followDate} onChange={e => setFollowDate(e.target.value)} /></div>}
          <div className="field"><label>Note</label><textarea className="input" value={callNote} onChange={e => setCallNote(e.target.value)} /></div>
          <button className="btn gold block" onClick={logCall} disabled={busy}>Save call</button>
        </div>}
        {tab === 'pay' && <div className="glass card" style={{ background: 'rgba(0,0,0,.18)' }}>
          <div className="grid2" style={{ gridTemplateColumns: '1fr 1fr' }}>
            <div className="field"><label>Amount (₹)</label><input className="input" type="number" value={payAmt} onChange={e => setPayAmt(e.target.value)} placeholder="0.00" /></div>
            <div className="field"><label>Mode</label><select className="input" value={payMode} onChange={e => setPayMode(e.target.value)}>
              <option>UPI</option><option>Cash</option><option>Bank Transfer</option><option>Cheque</option><option>BBPS</option></select></div></div>
          <div className="field"><label>Note (optional)</label><input className="input" value={payNote} onChange={e => setPayNote(e.target.value)} /></div>
          <button className="btn gold block" onClick={recordPay} disabled={busy || !payAmt}>Save payment</button>
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
                <div className="muted" style={{ fontSize: 11.5 }}>{h.by ? `by ${h.by} · ` : ''}{h.at ? toDate(h.at).toLocaleString() : ''}
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

const QUEUE_SEG = [['due', '⏰ Due now', 'due'], ['today', '✓ Contacted today', 'contacted_today'], ['upcoming', '📅 Upcoming', 'upcoming']];
function CallQueue() {
  const [data, setData] = useState(null); const [active, setActive] = useState(null); const [err, setErr] = useState('');
  const [seg, setSeg] = useState('due'); const [bank, setBank] = useState(''); const [bucket, setBucket] = useState(''); const [q, setQ] = useState('');
  const EMPTY = { due: [], contacted_today: [], upcoming: [], counts: { due: 0, contacted_today: 0, upcoming: 0 } };
  const load = () => {
    const p = new URLSearchParams(); if (bank) p.set('bank', bank);
    api('/api/calls/queue' + (p.toString() ? '?' + p : ''))
      .then(d => { setData(d); setErr(''); })
      .catch(e => { setErr(e.message || 'Could not load queue'); setData(EMPTY); });
  };
  useEffect(() => { load(); }, [bank]);
  if (!data) return <Loader />;
  if (err) return <div className="glass card" style={{ color: 'var(--warn)' }}>
    Couldn’t load the call queue: {err}. If you just updated the app, restart the server and reload. <button className="btn sm" style={{ marginLeft: 10 }} onClick={load}>Retry</button></div>;
  const key = (QUEUE_SEG.find(s => s[0] === seg) || QUEUE_SEG[0])[2];
  const all = [...data.due, ...data.contacted_today, ...data.upcoming];
  const buckets = Array.from(new Set(all.map(c => c.bucket || 'No bucket'))).sort((a, b) => bucketRank(a) - bucketRank(b));
  let list = data[key] || [];
  if (bucket) list = list.filter(c => (c.bucket || 'No bucket') === bucket);
  if (q) { const s = q.toLowerCase(); list = list.filter(c => (c.customer_name || '').toLowerCase().includes(s) || (c.phone || '').includes(q) || (c.account_no || '').includes(q)); }
  return (
    <div>
      <div className="toolbar">
        {QUEUE_SEG.map(([id, label, k]) => <div key={id} className={cx('chip', seg === id && 'on')} onClick={() => setSeg(id)}>{label} ({data.counts[k]})</div>)}
        <div style={{ flex: 1 }} />
        <input className="input" style={{ maxWidth: 210 }} placeholder="Search…" value={q} onChange={e => setQ(e.target.value)} />
        <button className="btn sm" onClick={load}>↻</button>
      </div>
      <div className="toolbar" style={{ marginTop: -2 }}>
        <select className="input" style={{ maxWidth: 130 }} value={bank} onChange={e => setBank(e.target.value)}>
          <option value="">All banks</option><option>ICICI</option><option>RBL</option><option>AXIS</option><option>BRBL</option></select>
        <span className="muted" style={{ fontSize: 12.5 }}>Bucket:</span>
        <div className={cx('chip', !bucket && 'on')} onClick={() => setBucket('')}>All</div>
        {buckets.map(b => <div key={b} className={cx('chip', bucket === b && 'on')} onClick={() => setBucket(b)}>{b}</div>)}
      </div>
      {list.length === 0 ? <p className="muted">{seg === 'due' ? 'Nothing due — nicely done. Check Upcoming for scheduled callbacks.' : 'Nothing here.'}</p> :
        <div className="grid3">
          {list.map(c => <div key={c.id} className="glass card">
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
  const load = () => { const p = new URLSearchParams(); if (bank) p.set('bank', bank);
    api('/api/calls/ptp-tracker' + (p.toString() ? '?' + p : '')).then(setData)
      .catch(() => setData({ rows: [], counts: { overdue: 0, today: 0, upcoming: 0 } })); };
  useEffect(() => { load(); }, [bank]);
  if (!data) return <Loader />;
  const groups = [['overdue', 'Overdue', 'unpaid'], ['today', 'Due today', 'partial'], ['upcoming', 'Upcoming', 'ptp']];
  return (
    <div>
      <div className="toolbar">
        <span className="badge unpaid">{data.counts.overdue} overdue</span>
        <span className="badge partial">{data.counts.today} due today</span>
        <span className="badge ptp">{data.counts.upcoming} upcoming</span>
        <div style={{ flex: 1 }} />
        <select className="input" style={{ maxWidth: 130 }} value={bank} onChange={e => setBank(e.target.value)}>
          <option value="">All banks</option><option>ICICI</option><option>RBL</option><option>AXIS</option><option>BRBL</option></select>
        <button className="btn sm" onClick={load}>↻</button>
      </div>
      {data.rows.length === 0 ? <p className="muted">No active promises to pay right now.</p> :
        groups.map(([key, label, cls]) => {
          const rows = data.rows.filter(r => r.bucket === key);
          if (!rows.length) return null;
          return <div key={key} className="glass card" style={{ marginBottom: 14 }}>
            <div className="section-h"><h3 style={{ fontSize: 15 }}><span className={cx('badge', cls)}>{label}</span>
              <span className="muted" style={{ fontWeight: 400, fontSize: 13 }}> · {rows.length}</span></h3></div>
            <div className="tablewrap"><table>
              <thead><tr><th>Customer</th><th>Bank</th><th>Promised</th><th>Promise date</th><th>Pending</th><th></th></tr></thead>
              <tbody>{rows.map(r => <tr key={r.case.id} style={{ cursor: 'pointer' }} onClick={() => setDrawer(r.case)}>
                <td><b>{r.case.customer_name}</b><div className="muted" style={{ fontSize: 12 }}>{r.case.phone}</div></td>
                <td>{r.case.bank}</td>
                <td className="mono">{r.ptp_amount != null ? INR(r.ptp_amount) : '—'}</td>
                <td style={{ color: key === 'overdue' ? 'var(--bad)' : 'var(--ink)' }}>{r.promised_date || '—'}</td>
                <td className="mono" style={{ color: 'var(--warn)' }}>{INR(r.case.pending_amount)}</td>
                <td><button className="btn sm gold" onClick={e => { e.stopPropagation(); setDrawer(r.case); }}>Open ›</button></td>
              </tr>)}</tbody></table></div>
          </div>;
        })}
      {drawer && <CaseDrawer c={drawer} onClose={() => setDrawer(null)} onChanged={load} />}
    </div>
  );
}

/* ============================== Records / Activity (admin) ============================== */
function RecordsView() {
  const [sum, setSum] = useState(null); const [items, setItems] = useState(null);
  const [kind, setKind] = useState('all'); const [drawer, setDrawer] = useState(null); const [flagOnly, setFlagOnly] = useState(false);
  const load = () => {
    api('/api/analytics/summary').then(setSum).catch(() => {});
    api('/api/analytics/activity?kind=' + kind + '&limit=200').then(setItems).catch(() => setItems([]));
  };
  useEffect(() => { load(); }, [kind]);
  const icon = t => t === 'payment' ? '💰' : t === 'call' ? '📞' : '📍';
  const shown = (items || []).filter(r => !flagOnly || r.off_location);
  const flagged = (items || []).filter(r => r.off_location).length;
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
      <div className="toolbar">
        {[['all', 'All activity'], ['visits', 'Field visits'], ['calls', 'Calls'], ['payments', 'Payments']].map(([k, l]) =>
          <div key={k} className={cx('chip', kind === k && 'on')} onClick={() => { setKind(k); setFlagOnly(false); }}>{l}</div>)}
        <div className={cx('chip', flagOnly && 'on')} onClick={() => setFlagOnly(v => !v)}>⚠ Off-location{flagged ? ` (${flagged})` : ''}</div>
        <div style={{ flex: 1 }} /><button className="btn sm" onClick={load}>↻ Refresh</button>
      </div>
      {!items ? <Loader /> : shown.length === 0 ? <p className="muted">{flagOnly ? 'No off-location visits — all clear.' : 'No records yet.'}</p> :
        <div className="glass card" style={{ padding: 6 }}>
          <div className="tablewrap"><table>
            <thead><tr><th></th><th>When</th><th>Customer</th><th>Bank</th><th>By</th><th>Detail</th><th>Amount</th><th></th></tr></thead>
            <tbody>{shown.map((r, i) => <tr key={i} style={r.off_location ? { background: 'rgba(240,119,107,.08)' } : null}>
              <td>{icon(r.type)}</td>
              <td className="muted" style={{ fontSize: 12, whiteSpace: 'nowrap' }}>{toDate(r.at).toLocaleString()}</td>
              <td><b>{r.customer || '—'}</b></td><td>{r.bank || '—'}</td><td>{r.by || '—'}</td>
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

/* ============================== Leave management ============================== */
const LEAVE_TYPES = ['Casual', 'Sick', 'Earned', 'Unpaid'];
function LeaveView({ user }) {
  const [bal, setBal] = useState(null); const [mine, setMine] = useState(null);
  const [team, setTeam] = useState(null); const [ins, setIns] = useState(null);
  const isMgr = user.role === 'admin' || user.role === 'manager';
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
        <td className="muted" style={{ fontSize: 12, whiteSpace: 'nowrap' }}>{toDate(d.last_seen).toLocaleString()}</td>
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
              <div><b>{k.label || 'Passkey'}</b><div className="muted" style={{ fontSize: 11.5 }}>{k.last_used ? 'Last used ' + toDate(k.last_used).toLocaleDateString() : 'Never used'}</div></div>
              <button className="btn ghost sm" onClick={() => delKey(k.id)}>Remove</button>
            </div>)}
        </div>
      </div>
    </div>
  );
}

/* ============================== Shell + App ============================== */
const NAV = {
  admin: [['dashboard', '📊', 'Dashboard'], ['cases', '🗂️', 'Accounts'], ['ptp', '🤝', 'PTP Tracker'], ['legal', '⚖️', 'Litigation'], ['map', '📍', 'Field Tracking'], ['records', '🗃️', 'Activity'], ['staff', '👥', 'Team'], ['leave', '🌴', 'Leave'], ['templates', '💬', 'Communication'], ['devices', '📱', 'Devices'], ['ai', '✨', 'AI Assist'], ['security', '🔒', 'Security']],
  manager: [['dashboard', '📊', 'Dashboard'], ['cases', '🗂️', 'Accounts'], ['ptp', '🤝', 'PTP Tracker'], ['legal', '⚖️', 'Litigation'], ['map', '📍', 'Field Tracking'], ['staff', '👥', 'Team'], ['leave', '🌴', 'Leave'], ['templates', '💬', 'Communication'], ['devices', '📱', 'Devices'], ['ai', '✨', 'AI Assist'], ['security', '🔒', 'Security']],
  fos: [['dashboard', '📊', 'My Stats'], ['fcases', '🗂️', 'My Accounts'], ['fmap', '📍', 'Field Tracking'], ['leave', '🌴', 'Leave'], ['ai', '✨', 'AI Assist'], ['security', '🔒', 'Security']],
  telecaller: [['dashboard', '📊', 'My Stats'], ['queue', '📞', 'Calling'], ['ptp', '🤝', 'PTP Tracker'], ['leave', '🌴', 'Leave'], ['ai', '✨', 'AI Assist'], ['security', '🔒', 'Security']],
};
function Shell({ user, config, onLogout, installEvt, onInstall }) {
  const nav = NAV[user.role] || NAV.telecaller;
  const [view, setView] = useState(nav[0][0]);
  useLocationPing(user, config);
  const title = (nav.find(n => n[0] === view) || [, , ''])[2];
  const render = () => {
    switch (view) {
      case 'dashboard': return <Dashboard user={user} />;
      case 'cases': return <CasesView user={user} />;
      case 'map': return <LiveMap config={config} />;
      case 'staff': return <StaffView config={config} />;
      case 'records': return <RecordsView />;
      case 'devices': return <DevicesView />;
      case 'leave': return <LeaveView user={user} />;
      case 'templates': return <TemplatesView />;
      case 'legal': return <LegalView />;
      case 'fcases': return <FOCases config={config} />;
      case 'fmap': return <FOLiveMap config={config} />;
      case 'queue': return <CallQueue />;
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
        {nav.map(([id, ic, label]) => <div key={id} className={cx('navitem', view === id && 'active')} onClick={() => setView(id)}>
          <span className="ic">{ic}</span>{label}</div>)}
        <div style={{ flex: 1 }} />
        <div className="navitem" onClick={onLogout}><span className="ic">⎋</span>Sign out</div>
      </aside>
      <main className="main">
        <div className="topbar">
          <h1>{title}</h1>
          {installEvt && <button className="btn sm gold" style={{ marginLeft: 'auto', marginRight: 10 }} onClick={onInstall}>⬇ Install app</button>}
          <div className="usertag"><div className="avatar">{initials(user.name)}</div>
            <div><div style={{ fontWeight: 600, fontSize: 14 }}>{user.name}</div>
              <div className="muted" style={{ fontSize: 12 }}>{user.branch || user.email}</div></div></div>
        </div>
        {render()}
      </main>
      <nav className="mobnav">
        {nav.map(([id, ic, label]) => <div key={id} className={cx('navitem', view === id && 'active')} onClick={() => setView(id)}>
          <span className="ic">{ic}</span>{label}</div>)}
        <div className="navitem" onClick={onLogout}><span className="ic">⎋</span>Sign out</div>
      </nav>
    </div>
  );
}

function App() {
  const [user, setUser] = useState(store.u); const [config, setConfig] = useState(null); const [ready, setReady] = useState(false);
  const [installEvt, setInstallEvt] = useState(null);
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
  return (<>
    <Toaster />
    {user ? <Shell user={user} config={config} onLogout={logout} installEvt={installEvt} onInstall={install} /> : <Login onLogin={setUser} config={config} />}
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


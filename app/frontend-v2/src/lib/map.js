import L from 'leaflet';
import 'leaflet/dist/leaflet.css';

export { L };

/** Base layers: clean vector-style street maps (light/dark) + satellite imagery. */
export const TILES = {
  street: ['https://tile.openstreetmap.org/{z}/{x}/{y}.png', '&copy; OpenStreetMap contributors'],
  satellite: ['https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}', 'Imagery &copy; Esri'],
};

/** Street map is restyled with CSS (soft in light mode, a proper night map in dark mode) — see .fm-tiles-*. */
export function baseLayer(kind) {
  const sat = kind === 'satellite';
  const [url, attribution] = sat ? TILES.satellite : TILES.street;
  return L.tileLayer(url, { attribution, maxZoom: 19, crossOrigin: true, className: sat ? 'fm-tiles-sat' : 'fm-tiles-street' });
}

/** Server timestamps may arrive without a timezone (stored UTC) — treat those as UTC. */
export function parseTs(t) {
  if (!t) return null;
  if (t instanceof Date) return t;
  const s = String(t);
  return new Date(/[zZ]|[+-]\d\d:?\d\d$/.test(s) ? s : s.replace(' ', 'T') + 'Z');
}
export const hhmm = (t) => { const d = parseTs(t); return d ? d.toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit' }) : '—'; };

export const INDIA = [17.69, 83.22];   // Visakhapatnam — default centre when nobody is on the map yet

/** Live status from last-seen time. */
export function statusOf(lastSeen) {
  if (!lastSeen) return 'offline';
  const mins = (Date.now() - parseTs(lastSeen).getTime()) / 60000;
  if (mins <= 5) return 'live';
  if (mins <= 30) return 'idle';
  return 'offline';
}

export const STATUS = {
  live: { label: 'Live', color: '#10B981' },
  idle: { label: 'Idle', color: '#F59E0B' },
  offline: { label: 'Offline', color: '#94A3B8' },
};

export function ago(t) {
  if (!t) return '—';
  const s = Math.max(0, (Date.now() - parseTs(t).getTime()) / 1000);
  if (s < 60) return 'just now';
  if (s < 3600) return Math.round(s / 60) + ' min ago';
  if (s < 86400) return Math.round(s / 3600) + ' h ago';
  return Math.round(s / 86400) + ' d ago';
}

const ini = (n) => String(n || '?').split(/\s+/).filter(Boolean).slice(0, 2).map(w => w[0]).join('').toUpperCase();

/** Avatar marker with a status ring and a pulse when live. */
export function agentIcon(name, status, selected) {
  const c = (STATUS[status] || STATUS.offline).color;
  return L.divIcon({
    className: 'fm-agent-wrap',
    iconSize: [44, 52], iconAnchor: [22, 48], popupAnchor: [0, -46],
    html: `<div class="fm-agent ${status} ${selected ? 'sel' : ''}" style="--c:${c}">
      ${status === 'live' ? '<span class="fm-pulse"></span>' : ''}
      <span class="fm-av">${ini(name)}</span><span class="fm-tip"></span></div>`,
  });
}

export function dotIcon(color, label, cls = '') {
  return L.divIcon({
    className: 'fm-dot-wrap', iconSize: [26, 26], iconAnchor: [13, 13],
    html: `<div class="fm-dot ${cls}" style="--c:${color}">${label || ''}</div>`,
  });
}

export function pinIcon(color, glyph = '') {
  return L.divIcon({
    className: 'fm-pin-wrap', iconSize: [30, 40], iconAnchor: [15, 38], popupAnchor: [0, -34],
    html: `<div class="fm-pin" style="--c:${color}"><span>${glyph}</span></div>`,
  });
}

/** Draw a route as a gradient polyline (older = faint → newer = strong). */
export function gradientRoute(layer, pts, from, to) {
  if (!pts || pts.length < 2) return;
  const n = pts.length;
  const lerp = (a, b, t) => Math.round(a + (b - a) * t);
  const hx = (h) => [1, 3, 5].map(i => parseInt(h.slice(i, i + 2), 16));
  const A = hx(from), B = hx(to);
  const step = Math.max(1, Math.floor(n / 60));
  for (let i = 0; i < n - 1; i += step) {
    const j = Math.min(n - 1, i + step);
    const t = i / (n - 1);
    const col = `rgb(${lerp(A[0], B[0], t)},${lerp(A[1], B[1], t)},${lerp(A[2], B[2], t)})`;
    L.polyline([pts[i], pts[j]], { color: col, weight: 5, opacity: .35 + .6 * t, lineCap: 'round' }).addTo(layer);
  }
  L.polyline(pts, { color: '#fff', weight: 9, opacity: .35, lineCap: 'round' }).addTo(layer).bringToBack();
}

export function kmBetween(a, b) {
  const R = 6371, toR = (x) => x * Math.PI / 180;
  const dLat = toR(b[0] - a[0]), dLng = toR(b[1] - a[1]);
  const s = Math.sin(dLat / 2) ** 2 + Math.cos(toR(a[0])) * Math.cos(toR(b[0])) * Math.sin(dLng / 2) ** 2;
  return 2 * R * Math.asin(Math.sqrt(s));
}

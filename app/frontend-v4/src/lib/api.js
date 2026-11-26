// API client — talks to the same RecoverIQ backend as the classic UI and shares its session
// (same localStorage keys), so signing in on one UI signs you in on the other.
const K = { token: 'ssd_token', user: 'ssd_user', device: 'ssd_device' };

export const session = {
  get token() { try { return localStorage.getItem(K.token) || ''; } catch { return ''; } },
  set token(v) { try { v ? localStorage.setItem(K.token, v) : localStorage.removeItem(K.token); } catch { /* ignore */ } },
  get user() { try { return JSON.parse(localStorage.getItem(K.user) || 'null'); } catch { return null; } },
  set user(v) { try { v ? localStorage.setItem(K.user, JSON.stringify(v)) : localStorage.removeItem(K.user); } catch { /* ignore */ } },
  get deviceId() {
    try {
      let d = localStorage.getItem(K.device);
      if (!d) { d = 'dev-' + Math.random().toString(36).slice(2, 10) + Date.now().toString(36); localStorage.setItem(K.device, d); }
      return d;
    } catch { return 'dev-unknown'; }
  },
};

export class ApiError extends Error {
  constructor(message, status) { super(message); this.status = status; }
}

const GATEWAY = [502, 503, 504, 520, 521, 522, 523, 524];

export async function api(path, { method, body, form, auth = true, signal, raw = false } = {}) {
  const headers = {};
  if (auth && session.token) headers.Authorization = 'Bearer ' + session.token;
  const m = method || (body || form ? 'POST' : 'GET');
  const opts = { method: m, headers, signal };
  if (form) opts.body = form;
  else if (body !== undefined) { headers['Content-Type'] = 'application/json'; opts.body = JSON.stringify(body); }
  let res = await fetch(path, opts);
  if (GATEWAY.includes(res.status) && m === 'GET') { await new Promise(r => setTimeout(r, 1200)); res = await fetch(path, opts); }
  if (GATEWAY.includes(res.status)) throw new ApiError(`Server didn't answer (HTTP ${res.status}). It may be restarting — try again in a few seconds.`, res.status);
  if (res.status === 401 && auth) {
    session.token = ''; session.user = null;
    window.dispatchEvent(new Event('riq:logout'));
    throw new ApiError('Your session has ended. Please sign in again.', 401);
  }
  if (!res.ok) {
    let msg = res.statusText || 'Request failed';
    try { const j = await res.json(); msg = typeof j.detail === 'string' ? j.detail : (j.detail ? JSON.stringify(j.detail) : msg); } catch { /* ignore */ }
    throw new ApiError(msg, res.status);
  }
  if (raw) return res;
  const ct = res.headers.get('content-type') || '';
  return ct.includes('json') ? res.json() : res;
}

/** Fetch a file with auth and hand it to the browser as a download. */
export async function download(path, filename) {
  const res = await api(path, { raw: true });
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url; a.download = filename; document.body.appendChild(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 4000);
}

export const qs = (o) => {
  const p = new URLSearchParams();
  Object.entries(o || {}).forEach(([k, v]) => { if (v !== undefined && v !== null && v !== '') p.set(k, v); });
  const s = p.toString();
  return s ? '?' + s : '';
};

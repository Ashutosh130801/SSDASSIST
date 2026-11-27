// Indian-format money / numbers / dates (IST), shared by both editions.
const nf0 = new Intl.NumberFormat('en-IN', { maximumFractionDigits: 0 });
const nf1 = new Intl.NumberFormat('en-IN', { maximumFractionDigits: 1 });

export const num = (n) => nf0.format(Number(n) || 0);
export const inr = (n) => '₹' + nf0.format(Number(n) || 0);
/** ₹ in lakhs / crores for KPI tiles: 1,23,45,678 → ₹1.23 Cr */
export const inrShort = (n) => {
  const v = Number(n) || 0, a = Math.abs(v);
  if (a >= 1e7) return '₹' + nf1.format(v / 1e7) + ' Cr';
  if (a >= 1e5) return '₹' + nf1.format(v / 1e5) + ' L';
  if (a >= 1e3) return '₹' + nf1.format(v / 1e3) + 'K';
  return '₹' + nf0.format(v);
};
export const pct = (n) => (Number(n) || 0).toFixed(1) + '%';

const toMs = (iso) => { if (!iso) return NaN; let s = String(iso); if (!/[zZ]|[+-]\d\d:?\d\d$/.test(s) && s.includes('T')) s += 'Z'; return new Date(s).getTime(); };
export const fmtDate = (iso) => { const t = toMs(iso); return isNaN(t) ? (iso || '—') : new Date(t).toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric', timeZone: 'Asia/Kolkata' }); };
export const fmtTime = (iso) => { const t = toMs(iso); return isNaN(t) ? '' : new Date(t).toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit', timeZone: 'Asia/Kolkata' }); };
export const istToday = () => new Date(Date.now() + 5.5 * 3600e3).toISOString().slice(0, 10);

export const initials = (name) => (name || '?').split(/\s+/).filter(Boolean).map(w => w[0]).slice(0, 2).join('').toUpperCase();
export const cx = (...a) => a.filter(Boolean).join(' ');

export const ROLE_LABEL = {
  admin: 'Administrator', manager: 'Collections Manager', teamlead: 'Team Lead', fos: 'Field Agent',
  telecaller: 'Tele-calling Agent', backend: 'Back-office', headoffice: 'Head Office', hr: 'HR', it: 'IT',
  staff: 'Staff', techsupport: 'Tech Support', it_support_view: 'IT Support View', teamfollower: 'Field TL',
};
export const roleName = (r) => ROLE_LABEL[r] || r;

/** Greeting by IST hour. */
export const greeting = () => {
  const h = new Date(Date.now() + 5.5 * 3600e3).getUTCHours();
  return h < 12 ? 'Good morning' : h < 17 ? 'Good afternoon' : 'Good evening';
};

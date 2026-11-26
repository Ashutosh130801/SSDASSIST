// Soft Clay template (frontend-v3, served at /v3/). One look; light/dark is a per-user toggle.
export const EDITIONS = {
  enterprise: { key: 'enterprise', name: 'Soft Clay', path: '/v3/', defaultMode: 'light' },
  premium: { key: 'premium', name: 'Soft Clay', path: '/v3/', defaultMode: 'light' },
};
export const TEMPLATE = 'v3';
export function detectEdition() { return 'enterprise'; }
export function setEdition() { /* single look in this template */ }
const MODE_KEY = 'riq_v3_mode';
export const getMode = () => { try { return localStorage.getItem(MODE_KEY) || 'light'; } catch { return 'light'; } };
export const setMode = (ed, m) => { try { localStorage.setItem(MODE_KEY, m); } catch { /* ignore */ } };

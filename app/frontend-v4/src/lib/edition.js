// Spatial 3D template (frontend-v4, served at /v4/). One look; light/dark is a per-user toggle.
export const EDITIONS = {
  enterprise: { key: 'enterprise', name: 'Spatial 3D', path: '/v4/', defaultMode: 'dark' },
  premium: { key: 'premium', name: 'Spatial 3D', path: '/v4/', defaultMode: 'dark' },
};
export const TEMPLATE = 'v4';
export function detectEdition() { return 'premium'; }
export function setEdition() { /* single look in this template */ }
const MODE_KEY = 'riq_v4_mode';
export const getMode = () => { return 'dark'; };
export const setMode = (ed, m) => { try { localStorage.setItem(MODE_KEY, m); } catch { /* ignore */ } };

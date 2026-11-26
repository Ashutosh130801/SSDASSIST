// One codebase, two editions. The edition comes from the URL the build is served under:
//   /v2/…  → Enterprise  (clean, light, data-dense — "Atlas")
//   /v3/…  → Premium     (dark-first, luxe gradients, gold accents — "Aurum")
// ?edition=premium|enterprise overrides it (handy in dev).
export const EDITIONS = {
  enterprise: { key: 'enterprise', name: 'Enterprise', path: '/v2/', defaultMode: 'light' },
  premium: { key: 'premium', name: 'Premium', path: '/v3/', defaultMode: 'dark' },
};

export function detectEdition() {
  const q = new URLSearchParams(window.location.search).get('edition');
  if (q && EDITIONS[q]) return q;
  if (window.__RIQ_EDITION__ && EDITIONS[window.__RIQ_EDITION__]) return window.__RIQ_EDITION__;
  try { const s = localStorage.getItem('riq_v2_edition'); if (EDITIONS[s]) return s; } catch { /* ignore */ }
  return 'enterprise';
}
/** v2 now lives only at /v2 — the Premium look is a per-user toggle (v3/v4 are separate templates). */
export function setEdition(ed) { try { localStorage.setItem('riq_v2_edition', ed); } catch { /* ignore */ } window.location.reload(); }

const MODE_KEY = (ed) => 'riq_v2_mode_' + ed;
export const getMode = (ed) => { try { return localStorage.getItem(MODE_KEY(ed)) || EDITIONS[ed].defaultMode; } catch { return EDITIONS[ed].defaultMode; } };
export const setMode = (ed, m) => { try { localStorage.setItem(MODE_KEY(ed), m); } catch { /* ignore */ } };

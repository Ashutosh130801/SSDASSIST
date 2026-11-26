// Named colour palettes. Each one drives every accent, KPI tone, chart series, hero gradient,
// backdrop blob and the WebGL aurora — and is pushed into the embedded classic modules too.
// Users pick one from the top bar; each edition has its own default.
//
// rgb triplets ("r, g, b") so CSS can do rgba(var(--t-x), a).

export const PALETTES = {
  azure: {
    name: 'Azure', blurb: 'Royal blue · sky · crisp white',
    accent: '37, 99, 235', accent2: '14, 165, 233', ink: '#1E40AF',
    good: '16, 185, 129', warn: '245, 158, 11', bad: '239, 68, 68', info: '6, 182, 212', violet: '79, 70, 229',
    charts: ['#2563EB', '#0EA5E9', '#10B981', '#F59E0B', '#6366F1', '#F43F5E'],
    light: { page: '#EEF4FF', blobs: ['#BFDBFE', '#A5F3FC', '#E0ECFF', '#C7D7FE'],
      hero: ['#1D4ED8', '#2563EB', '#0EA5E9'], ring: ['#FFFFFF', '#BAE6FD'] },
    dark: { page: '#050B1A', blobs: ['#1E3A8A', '#0C4A6E', '#1E40AF', '#164E63'],
      hero: ['#0B1E4F', '#1D4ED8', '#0369A1'], ring: ['#93C5FD', '#67E8F9'] },
  },
  sapphire: {
    name: 'Sapphire', blurb: 'Deep navy · electric blue · ice',
    accent: '59, 130, 246', accent2: '56, 189, 248', ink: '#1E3A8A',
    good: '52, 211, 153', warn: '251, 191, 36', bad: '248, 113, 113', info: '34, 211, 238', violet: '129, 140, 248',
    charts: ['#3B82F6', '#38BDF8', '#34D399', '#FBBF24', '#818CF8', '#FB7185'],
    light: { page: '#F3F7FF', blobs: ['#C7DBFF', '#BAE6FD', '#E0E7FF', '#DBEAFE'],
      hero: ['#1E3A8A', '#2563EB', '#38BDF8'], ring: ['#FFFFFF', '#BAE6FD'] },
    dark: { page: '#040814', blobs: ['#1E3A8A', '#075985', '#1E2F6B', '#0F3460'],
      hero: ['#0A1636', '#13307A', '#0E5A8A'], ring: ['#93C5FD', '#7DD3FC'] },
  },
  lagoon: {
    name: 'Lagoon', blurb: 'Teal · coral · sunflower',
    accent: '13, 148, 136', accent2: '255, 107, 107', ink: '#0B5E57',
    good: '16, 185, 129', warn: '245, 158, 11', bad: '244, 63, 94', info: '14, 165, 233', violet: '124, 92, 255',
    charts: ['#0D9488', '#FF6B6B', '#F59E0B', '#7C5CFF', '#0EA5E9', '#EC4899'],
    light: { page: '#E8F3F1', blobs: ['#7EE6D4', '#FFB3A7', '#FFE08A', '#C9BCFF'],
      hero: ['#0B7A72', '#0EA5A4', '#36C2D9'], ring: ['#FFFFFF', '#FFD3A8'] },
    dark: { page: '#06110F', blobs: ['#0F766E', '#B9384A', '#A16207', '#4C3BB3'],
      hero: ['#0A4D48', '#0B7A72', '#155E75'], ring: ['#5EEAD4', '#FDA4AF'] },
  },
  orchid: {
    name: 'Noir Orchid', blurb: 'Magenta · violet · cyan glow',
    accent: '236, 72, 153', accent2: '139, 92, 246', ink: '#9D174D',
    good: '45, 212, 191', warn: '251, 191, 36', bad: '251, 113, 133', info: '56, 189, 248', violet: '139, 92, 246',
    charts: ['#EC4899', '#8B5CF6', '#22D3EE', '#FBBF24', '#34D399', '#F97316'],
    light: { page: '#FBF1F6', blobs: ['#F9A8D4', '#C4B5FD', '#A5F3FC', '#FDE68A'],
      hero: ['#BE185D', '#DB2777', '#7C3AED'], ring: ['#FFFFFF', '#A5F3FC'] },
    dark: { page: '#0B0612', blobs: ['#9D174D', '#6D28D9', '#0E7490', '#7C2D12'],
      hero: ['#3B0A2A', '#4C1D95', '#831843'], ring: ['#F9A8D4', '#A78BFA'] },
  },
  sunset: {
    name: 'Sunset Citrus', blurb: 'Tangerine · rose · plum',
    accent: '249, 115, 22', accent2: '236, 72, 153', ink: '#9A3412',
    good: '22, 163, 74', warn: '234, 179, 8', bad: '225, 29, 72', info: '59, 130, 246', violet: '147, 51, 234',
    charts: ['#F97316', '#EC4899', '#9333EA', '#EAB308', '#06B6D4', '#22C55E'],
    light: { page: '#FFF3EA', blobs: ['#FDBA74', '#F9A8D4', '#D8B4FE', '#FDE047'],
      hero: ['#EA580C', '#F43F5E', '#9333EA'], ring: ['#FFFFFF', '#FEF08A'] },
    dark: { page: '#120805', blobs: ['#C2410C', '#BE123C', '#7E22CE', '#A16207'],
      hero: ['#7C2D12', '#9F1239', '#581C87'], ring: ['#FDBA74', '#F0ABFC'] },
  },
  emerald: {
    name: 'Emerald Gold', blurb: 'Forest · emerald · antique gold',
    accent: '5, 150, 105', accent2: '202, 138, 4', ink: '#065F46',
    good: '16, 185, 129', warn: '217, 119, 6', bad: '220, 38, 38', info: '2, 132, 199', violet: '101, 163, 13',
    charts: ['#059669', '#CA8A04', '#0EA5E9', '#65A30D', '#DC2626', '#7C3AED'],
    light: { page: '#EEF4EC', blobs: ['#86EFAC', '#FDE68A', '#A7F3D0', '#BAE6FD'],
      hero: ['#064E3B', '#047857', '#B48A1E'], ring: ['#FFFFFF', '#FDE68A'] },
    dark: { page: '#04100B', blobs: ['#065F46', '#854D0E', '#155E75', '#3F6212'],
      hero: ['#022C22', '#065F46', '#713F12'], ring: ['#6EE7B7', '#FCD34D'] },
  },
  ocean: {
    name: 'Electric Ocean', blurb: 'Cobalt · cyan · lime',
    accent: '37, 99, 235', accent2: '6, 182, 212', ink: '#1E3A8A',
    good: '132, 204, 22', warn: '245, 158, 11', bad: '239, 68, 68', info: '6, 182, 212', violet: '99, 102, 241',
    charts: ['#2563EB', '#06B6D4', '#84CC16', '#F59E0B', '#A855F7', '#EF4444'],
    light: { page: '#EAF1FD', blobs: ['#93C5FD', '#67E8F9', '#D9F99D', '#C7D2FE'],
      hero: ['#1D4ED8', '#2563EB', '#06B6D4'], ring: ['#FFFFFF', '#D9F99D'] },
    dark: { page: '#050A18', blobs: ['#1E40AF', '#0E7490', '#3F6212', '#4338CA'],
      hero: ['#0B1E4F', '#1E3A8A', '#0E7490'], ring: ['#93C5FD', '#BEF264'] },
  },
  aurum: {
    name: 'Aurum', blurb: 'Champagne gold · ink · violet',
    accent: '201, 153, 69', accent2: '139, 124, 246', ink: '#7A5C17',
    good: '52, 211, 153', warn: '251, 191, 36', bad: '248, 113, 113', info: '96, 165, 250', violet: '139, 124, 246',
    charts: ['#E8C27A', '#8B7CF6', '#34D399', '#60A5FA', '#F472B6', '#F59E0B'],
    light: { page: '#F4EFE5', blobs: ['#F3D9A4', '#C4B5FD', '#BAE6FD', '#FBCFE8'],
      hero: ['#B8893A', '#D4AE62', '#8B7CF6'], ring: ['#1E1708', '#6D5DD3'], heroInk: '#1E1708' },
    dark: { page: '#06070C', blobs: ['#3B3486', '#8A6A2A', '#0B3B3A', '#3A2448'],
      hero: ['#1A1630', '#2A2140', '#3B2E1A'], ring: ['#F3D9A4', '#A78BFA'] },
  },
};

export const DEFAULT_PALETTE = { enterprise: 'azure', premium: 'sapphire' };
const KEY = (ed) => 'riq_v2_pal_' + ed;   // (renamed so everyone starts on the blue defaults)
export const getPalette = (ed) => { try { const p = localStorage.getItem(KEY(ed)); return PALETTES[p] ? p : DEFAULT_PALETTE[ed]; } catch { return DEFAULT_PALETTE[ed]; } };
export const savePalette = (ed, p) => { try { localStorage.setItem(KEY(ed), p); } catch { /* ignore */ } };

const hexA = (hex, a) => { const n = parseInt(hex.slice(1), 16); return `rgba(${n >> 16 & 255}, ${n >> 8 & 255}, ${n & 255}, ${a})`; };
const rgb = (t) => `rgb(${t})`;
const rgba = (t, a) => `rgba(${t}, ${a})`;

/** All CSS custom properties for a palette in a mode. */
export function paletteVars(key, mode) {
  const p = PALETTES[key] || PALETTES.azure;
  const m = p[mode] || p.light;
  const dark = mode === 'dark';
  const [h0, h1, h2] = m.hero;
  const v = {
    '--t-accent': p.accent, '--t-accent2': p.accent2, '--t-good': p.good, '--t-warn': p.warn, '--t-bad': p.bad,
    '--t-info': p.info, '--t-violet': p.violet,
    '--accent': rgb(p.accent), '--accent-2': rgb(p.accent2),
    '--accent-soft': rgba(p.accent, dark ? .16 : .12), '--accent-ink': dark ? `color-mix(in srgb, ${rgb(p.accent)} 70%, white)` : p.ink,
    '--on-accent': '#FFFFFF',
    '--good': rgb(p.good), '--warn': rgb(p.warn), '--bad': rgb(p.bad), '--info': rgb(p.info),
    '--good-soft': rgba(p.good, dark ? .14 : .12), '--warn-soft': rgba(p.warn, dark ? .14 : .14),
    '--bad-soft': rgba(p.bad, dark ? .14 : .11), '--info-soft': rgba(p.info, dark ? .14 : .11),
    '--bg-active': rgba(p.accent, dark ? .16 : .10),
    '--ring': `0 0 0 3px ${rgba(p.accent, .22)}`,
    '--page': m.page,
    '--blob-1': hexA(m.blobs[0], dark ? .55 : .55), '--blob-2': hexA(m.blobs[1], dark ? .45 : .45),
    '--blob-3': hexA(m.blobs[2], dark ? .35 : .45), '--blob-4': hexA(m.blobs[3], dark ? .30 : .45),
    '--hero-bg': dark
      ? `radial-gradient(560px 300px at 100% -20%, ${rgba(p.accent, .45)}, transparent 60%), radial-gradient(520px 320px at -10% 120%, ${rgba(p.accent2, .40)}, transparent 60%), linear-gradient(135deg, ${h0}, ${h1} 55%, ${h2})`
      : `radial-gradient(520px 260px at 88% -30%, rgba(255,255,255,.42), transparent 60%), radial-gradient(420px 260px at 0% 120%, ${rgba(p.accent2, .45)}, transparent 60%), linear-gradient(135deg, ${h0} 0%, ${h1} 50%, ${h2} 100%)`,
    '--hero-shadow': dark
      ? `0 40px 80px -36px rgba(0,0,0,.9), 0 30px 60px -40px ${rgba(p.accent, .6)}, inset 0 1px 0 rgba(255,255,255,.16)`
      : `0 34px 60px -28px ${hexA(h1, .7)}, inset 0 2px 4px rgba(255,255,255,.35), inset 0 -14px 26px rgba(0,0,0,.18)`,
    '--hero-ink': m.heroInk || '#FFFFFF',
    '--hero-ink-2': m.heroInk ? 'rgba(30,23,8,.7)' : 'rgba(255,255,255,.80)',
    '--ring-a': m.ring[0], '--ring-b': m.ring[1],
    '--ring-track': m.heroInk ? 'rgba(30,23,8,.14)' : 'rgba(255,255,255,.22)',
    '--glass-edge': dark
      ? `linear-gradient(140deg, rgba(255,255,255,.22), rgba(255,255,255,.03) 40%, ${rgba(p.accent, .45)})`
      : `linear-gradient(140deg, rgba(255,255,255,.98), rgba(255,255,255,.35) 45%, ${rgba(p.accent, .35)})`,
  };
  p.charts.forEach((c, i) => { v[`--chart-${i + 1}`] = c; });
  return v;
}

/** Shader colours for the WebGL aurora. */
export function shaderPalette(key, mode) {
  const p = PALETTES[key] || PALETTES.azure;
  const m = p[mode] || p.light;
  return { base: m.page, c: m.blobs, amt: mode === 'dark' ? 0.5 : 0.6 };
}

export function applyPalette(key, mode, root = document.documentElement) {
  const vars = paletteVars(key, mode);
  Object.entries(vars).forEach(([k, val]) => root.style.setProperty(k, val));
  return vars;
}

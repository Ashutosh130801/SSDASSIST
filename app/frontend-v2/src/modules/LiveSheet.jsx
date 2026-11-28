import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import {
  ChevronLeft, ChevronRight, Columns3, Download, Flag, MessageCircle, Phone, Plus, Sigma, Smartphone, Table2, X, Lock, Bookmark, FunctionSquare,
} from 'lucide-react';
import { api, session } from '../lib/api.js';
import { useAuth } from '../lib/auth.jsx';
import { cx, istToday, num } from '../lib/format.js';
import { Kpi, useToast } from '../components/ui.jsx';
import { useClassic } from '../lib/classic.jsx';
import CaseDrawer from '../pages/CaseDrawer.jsx';
import { ModuleHead, Chips, MultiSelect, usePanel, PopLayer } from './kit.jsx';
import { Wallet, PhoneCall, Handshake, Hourglass } from 'lucide-react';

/* Column catalogue — identical to the classic Live Sheet (same keys, same saved prefs). */
const COLS = [
  { k: 'customer_name', t: 'Customer', type: 'text' }, { k: 'phone', t: 'Phone', type: 'text', edit: true },
  { k: 'alt_phone', t: 'Alt phone', type: 'text', edit: true }, { k: 'new_phone', t: 'New phone', type: 'text', edit: true },
  { k: 'new_address', t: 'New address', type: 'text', edit: true }, { k: 'card_no', t: 'Card no', type: 'text' },
  { k: 'account_no', t: 'A/C no', type: 'text' }, { k: 'bank', t: 'Bank', type: 'text' }, { k: 'branch', t: 'Branch', type: 'text' },
  { k: 'product', t: 'Product', type: 'text' }, { k: 'bucket', t: 'Bucket', type: 'text' }, { k: 'cycle', t: 'Cycle', type: 'text' },
  { k: 'month', t: 'Month', type: 'text' }, { k: 'total_outstanding', t: 'TOS', type: 'num', edit: true },
  { k: 'principal_outstanding', t: 'POS / PRI', type: 'num', edit: true }, { k: 'enr', t: 'ENR', type: 'num' },
  { k: 'norm_amount', t: 'OD NORM', type: 'num', edit: true }, { k: 'stab_amount', t: 'OD STAB', type: 'num', edit: true },
  { k: 'rollback_amount', t: 'ROLLBACK', type: 'num', edit: true }, { k: 'min_amount_due', t: 'Min due', type: 'num', edit: true },
  { k: 'received_amount', t: 'Amount', type: 'num', edit: true }, { k: 'pending_amount', t: 'Pending', type: 'num', edit: true },
  { k: 'norm_stab', t: 'N/S paid', type: 'sel', edit: true, opts: ['', 'NORM', 'STAB', 'ROLLBACK'] },
  { k: 'status', t: 'Status', type: 'sel', edit: true, opts: ['', 'new', 'ptp', 'callback', 'paid', 'closed'] },
  { k: 'paid_status', t: 'Paid', type: 'sel', edit: true, opts: ['', 'PAID', 'PARTIAL', 'UNPAID'] },
  { k: 'disposition', t: 'Disposition', type: 'sel', edit: true, opts: ['', 'PTP', 'RTP', 'PAID', 'CALLBACK', 'NO_CONTACT', 'WRONG_NUMBER', 'REFUSED'] },
  { k: 'follow_up_date', t: 'Follow-up', type: 'date', edit: true }, { k: 'remarks', t: 'Remarks', type: 'text', edit: true },
  { k: 'notes_text', t: 'Remarks history', type: 'text' }, { k: 'caller_name', t: 'Caller', type: 'text', edit: true },
  { k: 'fos_name', t: 'FOS', type: 'text', edit: true }, { k: 'team', t: 'Area', type: 'text', edit: true },
  { k: 'team_lead', t: 'Team lead', type: 'text', edit: true }, { k: 'cat', t: 'Cat', type: 'text', edit: true },
  { k: 'segment', t: 'Segment', type: 'text' }, { k: 'final_status', t: 'Status', type: 'text' },
  { k: 'x_emi', t: 'EMI', type: 'num', data: true, edit: true }, { k: 'x_pos_ovd', t: 'POS OVD', type: 'num', data: true, edit: true },
  { k: 'x_interest_ovd', t: 'Int OVD', type: 'num', data: true, edit: true }, { k: 'x_charges_ovd', t: 'Charges OVD', type: 'num', data: true, edit: true },
  { k: 'x_tot_od', t: 'Total OD', type: 'num', data: true, edit: true }, { k: 'x_disbursement', t: 'Disbursement', type: 'num', data: true },
  { k: 'x_risk', t: 'Risk cat', type: 'text', data: true }, { k: 'x_city', t: 'City', type: 'text', data: true },
  { k: 'x_od', t: 'OD', type: 'num', data: true, edit: true }, { k: 'x_ptp_date', t: 'PTP date', type: 'text', data: true, edit: true },
  { k: 'x_paid_date', t: 'Paid date', type: 'text', data: true, edit: true }, { k: 'x_mode_of_payment', t: 'Mode', type: 'text', data: true, edit: true },
  { k: 'x_tenure', t: 'Tenure', type: 'num', data: true }, { k: 'x_balance_tenure', t: 'Bal tenure', type: 'num', data: true },
  { k: 'x_billed_emi', t: 'Billed EMI', type: 'num', data: true }, { k: 'x_traced_contact', t: 'Traced no', type: 'text', data: true, edit: true },
  { k: 'x_last_payment_date', t: 'Last pay dt', type: 'text', data: true }, { k: 'x_last_payment_amount', t: 'Last pay amt', type: 'num', data: true },
  { k: 'x_organisation', t: 'Organisation', type: 'text', data: true }, { k: 'x_designation', t: 'Designation', type: 'text', data: true },
  { k: 'address', t: 'Address 1', type: 'text' }, { k: 'address2', t: 'Address 2', type: 'text' }, { k: 'pincode', t: 'Pincode', type: 'text' },
  { k: 'propensity', t: 'Score', type: 'num' }, { k: 'updated_by_name', t: 'Last changed by', type: 'text' },
];
const DEFAULT_VISIBLE = ['customer_name', 'phone', 'new_phone', 'new_address', 'bank', 'product', 'enr', 'norm_amount', 'stab_amount', 'received_amount', 'norm_stab', 'paid_status', 'status', 'disposition', 'caller_name', 'fos_name', 'remarks'];
const VISIBLE_PLBL = ['bucket', 'account_no', 'customer_name', 'cycle', 'phone', 'x_disbursement', 'total_outstanding', 'principal_outstanding', 'x_emi', 'x_pos_ovd', 'x_interest_ovd', 'x_charges_ovd',
  'x_tot_od', 'x_mode_of_payment', 'stab_amount', 'norm_amount', 'received_amount', 'paid_status', 'final_status', 'norm_stab', 'caller_name', 'address', 'team', 'pincode', 'fos_name',
  'x_last_payment_amount', 'x_risk', 'x_tenure', 'x_balance_tenure', 'remarks'];
const REVIEW = [['red', '#EF4444'], ['amber', '#F59E0B'], ['green', '#22C55E'], ['blue', '#3B82F6'], ['purple', '#8B5CF6'], ['pink', '#EC4899'], ['grey', '#94A3B8']];
const REVIEW_HEX = Object.fromEntries(REVIEW);
const FUNCS = { ROUND: Math.round, ABS: Math.abs, MIN: Math.min, MAX: Math.max, SQRT: Math.sqrt, IF: (c, a, b) => (c ? a : b) };
function safeCalc(expr) {
  if (!/^[-+*/%(). ,0-9<>=?:A-Za-z_]*$/.test(expr)) throw new Error('bad expression');
  const names = Object.keys(FUNCS);
  // eslint-disable-next-line no-new-func
  return new Function(...names, 'return (' + expr + ');')(...names.map(n => FUNCS[n]));
}
const fmt = (v) => (v === null || v === undefined || v === '' ? '' : typeof v === 'number' && isFinite(v) ? (Math.round(v * 100) / 100).toLocaleString('en-IN') : v);
const waNum = (p) => { let n = String(p || '').replace(/[^\d+]/g, ''); if (n.startsWith('+')) return n.slice(1); n = n.replace(/^0+/, ''); return n.length === 10 ? '91' + n : n; };
const LIMIT = 5000;

/** Live Sheet — the spreadsheet callers work in: live multi-user edits, presence, formulas, presets, exports. */
export default function LiveSheet() {
  const { user } = useAuth();
  const toast = useToast();
  const panel = usePanel();
  const classic = useClassic();
  const [sp, setSp] = useSearchParams();
  const canPayEdit = ['admin', 'headoffice', 'manager', 'backend', 'telecaller', 'teamlead'].includes(user.role);
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState('');
  const [prefs, setPrefs] = useState(null);
  const [opts, setOpts] = useState({ combos: [], total: 0 });
  const [mb, setMb] = useState('current');
  const [bankF, setBankF] = useState(''); const [prodF, setProdF] = useState(''); const [branchF, setBranchF] = useState('');
  const [cycles, setCycles] = useState([]); const [paidF, setPaidF] = useState(''); const [escOnly, setEscOnly] = useState(false); const [reviewF, setReviewF] = useState('');
  const [search, setSearch] = useState(''); const [filters, setFilters] = useState({}); const [sort, setSort] = useState(null);
  const [colMenu, setColMenu] = useState(false);
  const [calc, setCalc] = useState('=SUM([pending_amount])'); const [calcRes, setCalcRes] = useState('');
  const [live, setLive] = useState(false); const [presence, setPresence] = useState({});
  const [vici, setVici] = useState(false);
  const [fx, setFx] = useState(null); const [fxVal, setFxVal] = useState('');
  const wsRef = useRef(null); const saveT = useRef(null); const autoMonth = useRef(false);
  const qRef = useRef({}); qRef.current = { mb, bankF, prodF, branchF };
  const scrollRef = useRef(null); const [scrollPct, setScrollPct] = useState(0); const [scrollable, setScrollable] = useState(false);

  useEffect(() => { if (classic.api && classic.api.dialerStatus) Promise.resolve(classic.api.dialerStatus()).then(v => setVici(v === true)).catch(() => {}); }, [classic.api]);

  const load = useCallback(() => {
    const { mb: m, bankF: b, prodF: p, branchF: br } = qRef.current;
    const q = new URLSearchParams({ limit: String(LIMIT), with_notes: 'true' });
    if (m) q.set('month_bucket', m); if (b) q.set('bank', b); if (p) q.set('product', p); if (br) q.set('branch', br);
    setLoading(true);
    return api('/api/cases?' + q).then(d => { setRows(Array.isArray(d) ? d : []); setErr(''); }).catch(e => setErr(e.message || 'Could not load')).finally(() => setLoading(false));
  }, []);
  const loadOpts = useCallback(() => api('/api/cases/sheet-options' + (qRef.current.mb ? '?month_bucket=' + encodeURIComponent(qRef.current.mb) : '')).then(o => {
    const oo = o && o.combos ? o : { combos: [], total: 0 };
    if (!autoMonth.current) {
      const m = qRef.current.mb; const nxt = !oo.total ? (m === 'current' ? 'next' : m === 'next' ? 'last' : null) : null;
      if (nxt) { setMb(nxt); return; }
      autoMonth.current = true;
    }
    setOpts(oo);
  }).catch(() => {}), []);
  useEffect(() => { load(); }, [mb, bankF, prodF, branchF, load]);
  useEffect(() => { loadOpts(); }, [mb, loadOpts]);
  useEffect(() => {
    api('/api/sheet/prefs').then(p => setPrefs({ visible: (p && p.visible) || DEFAULT_VISIBLE, order: (p && p.order) || COLS.map(c => c.k), custom: (p && p.custom) || [], aggs: (p && p.aggs) || {} }))
      .catch(() => setPrefs({ visible: DEFAULT_VISIBLE, order: COLS.map(c => c.k), custom: [], aggs: {} }));
  }, []);

  // Live: row patches, reloads and who-is-editing presence over the same WebSocket as classic.
  useEffect(() => {
    let ws = null, stop = false, tries = 0, retry = null;
    const open = () => {
      if (stop) return;
      try {
        ws = new WebSocket(location.origin.replace(/^http/, 'ws') + '/ws?token=' + encodeURIComponent(session.token || ''));
        ws.onopen = () => { tries = 0; wsRef.current = ws; setLive(true); };
        ws.onclose = () => { setLive(false); wsRef.current = null; if (!stop) { tries = Math.min(tries + 1, 10); retry = setTimeout(open, Math.min(30000, 2000 * tries)); } };
        ws.onerror = () => { try { ws.close(); } catch (e) { /* ignore */ } };
        ws.onmessage = (e) => {
          let m; try { m = JSON.parse(e.data); } catch (x) { return; }
          if (m.type === 'case_update' && m.case) setRows(rs => { const i = rs.findIndex(r => r.id === m.case.id); if (i < 0) return rs; const cp = rs.slice(); cp[i] = { ...cp[i], ...m.case }; return cp; });
          else if (m.type === 'data_changed' || m.type === 'payment' || m.type === 'case_changed') { load(); loadOpts(); }
          else if (m.type === 'presence') setPresence(p => { const cp = { ...p }; if (m.editors && m.editors.length) cp[m.case_id] = m.editors; else delete cp[m.case_id]; return cp; });
        };
      } catch (x) { retry = setTimeout(open, 3000); }
    };
    open();
    return () => { stop = true; clearTimeout(retry); if (ws) try { ws.close(); } catch (e) { /* ignore */ } };
  }, [load, loadOpts]);
  const sendPresence = (caseId, field, editing) => { const ws = wsRef.current; if (ws && ws.readyState === 1) try { ws.send(JSON.stringify({ type: editing ? 'editing' : 'editing_stop', case_id: caseId, field })); } catch (e) { /* ignore */ } };
  const others = (id) => (presence[id] || []).filter(e => e.id !== user.id);

  const allDefs = useCallback(() => COLS.concat((prefs ? prefs.custom : []).map(c => ({ ...c, custom: true }))), [prefs]);
  const defByKey = (k) => allDefs().find(c => c.k === k);
  const savePrefs = (next) => { setPrefs(next); clearTimeout(saveT.current); saveT.current = setTimeout(() => api('/api/sheet/prefs', { method: 'PUT', body: next }).catch(() => {}), 600); };
  const toggleCol = (k) => savePrefs({ ...prefs, visible: prefs.visible.includes(k) ? prefs.visible.filter(x => x !== k) : prefs.visible.concat(k) });
  const preset = (kind) => { const want = kind === 'plbl' ? VISIBLE_PLBL : DEFAULT_VISIBLE; const known = allDefs().map(c => c.k); const vis = want.filter(k => known.includes(k)); savePrefs({ ...prefs, visible: vis, order: vis.concat(prefs.order.filter(k => !vis.includes(k))) }); };
  const addFormula = () => { const label = window.prompt('Column name'); if (!label) return; const f = window.prompt('Formula — reference columns like [pending_amount]\ne.g. =[pending_amount]*0.1'); if (!f) return; const k = 'f_' + Date.now(); savePrefs({ ...prefs, custom: prefs.custom.concat({ k, t: label, type: 'num', formula: f }), order: prefs.order.concat(k), visible: prefs.visible.concat(k) }); };
  const addData = () => { const label = window.prompt('New column name (free text you fill per row)'); if (!label) return; const k = 'x_' + label.replace(/[^a-z0-9]/gi, '_').toLowerCase() + '_' + String(Date.now()).slice(-4); savePrefs({ ...prefs, custom: prefs.custom.concat({ k, t: label, type: 'text', data: true }), order: prefs.order.concat(k), visible: prefs.visible.concat(k) }); };
  const reorder = (from, to) => { if (!prefs || !from || from === to) return; const o = prefs.order.slice(); const fi = o.indexOf(from); if (fi < 0) return; o.splice(fi, 1); let ti = o.indexOf(to); if (ti < 0) ti = o.length; o.splice(ti, 0, from); savePrefs({ ...prefs, order: o }); };
  const cols = prefs ? prefs.order.filter(k => prefs.visible.includes(k)).map(defByKey).filter(Boolean) : [];
  const rowFormula = (f, row) => { try { return safeCalc(String(f).replace(/^=/, '').replace(/\[([a-z_0-9]+)\]/gi, (_, k) => Number(row[k] || 0))); } catch (e) { return '—'; } };
  const cellVal = (row, c) => (c.data ? ((row.extra || {})[c.k] ?? '') : c.custom ? rowFormula(c.formula, row) : row[c.k]);

  const view = useMemo(() => {
    let out = rows.slice();
    if (escOnly) out = out.filter(r => r.escalated);
    if (reviewF) out = out.filter(r => (reviewF === 'any' ? r.review_color : r.review_color === reviewF));
    if (paidF) out = out.filter(r => (r.paid_status || '').toUpperCase() === paidF);
    if (cycles.length) out = out.filter(r => cycles.includes(r.cycle));
    if (search) { const q = search.toLowerCase(); out = out.filter(r => ['customer_name', 'card_no', 'account_no', 'phone'].some(k => String(r[k] || '').toLowerCase().includes(q))); }
    Object.keys(filters).forEach(k => { const f = (filters[k] || '').toLowerCase(); if (f) out = out.filter(r => String(r[k] == null ? '' : r[k]).toLowerCase().includes(f)); });
    if (sort) {
      const d = defByKey(sort.k);
      out.sort((a, b) => { let x = d && d.custom ? rowFormula(d.formula, a) : a[sort.k], y = d && d.custom ? rowFormula(d.formula, b) : b[sort.k];
        if (d && d.type === 'num') { x = Number(x) || 0; y = Number(y) || 0; } else { x = String(x ?? ''); y = String(y ?? ''); }
        return (x < y ? -1 : x > y ? 1 : 0) * (sort.dir === 'desc' ? -1 : 1); });
    }
    return out;
  }, [rows, escOnly, reviewF, paidF, cycles, search, filters, sort, prefs]); // eslint-disable-line

  const editCell = (row, c, value) => {
    if (canPayEdit && c.k === 'paid_status' && (value === 'PAID' || value === 'UNPAID') && (row.paid_status || '') !== value) return pay(row, value === 'PAID' ? 'paid' : 'unpaid');
    if (canPayEdit && c.k === 'status') { const cur = row.status || ''; if (value === 'paid' && cur !== 'paid') return pay(row, 'paid'); if (cur === 'paid' && value !== 'paid') return pay(row, 'unpaid'); }
    if (canPayEdit && c.k === 'received_amount' && (row.paid_status || '').toUpperCase() !== 'PAID') {
      const n = Number(value) || 0, cur = Number(row.received_amount) || 0;
      if (n > cur) return pay(row, 'paid', String(Math.round(n - cur)));
    }
    setRows(rs => rs.map(r => (r.id === row.id ? (c.data ? { ...r, extra: { ...(r.extra || {}), [c.k]: value } } : { ...r, [c.k]: value }) : r)));
    api('/api/sheet/cell/' + row.id, { method: 'PATCH', body: { field: c.k, value } }).catch(() => { setErr('Save failed — reloading'); load(); });
    return undefined;
  };
  const pay = (row, mode, amount) => panel('payEdit', { row, mode, amount }).then(u => { if (u && typeof u === 'object') setRows(rs => rs.map(r => (r.id === u.id ? { ...r, ...u } : r))); else load(); });
  const openCase = (row) => { setSp({ open: row.id }); api('/api/sheet/open/' + row.id, { method: 'POST' }).catch(() => {}); };
  const pushToPhone = (row) => api('/api/sheet/open/' + row.id, { method: 'POST' }).then(() => toast('Sent to your phone')).catch(e => toast(e.message, 'err'));
  const dial = (row) => { if (vici && classic.api) classic.api.dialCase(row.id); else window.location.href = 'tel:' + String(row.phone).replace(/[^0-9+]/g, ''); };

  const agg = (fn, k) => { const xs = view.map(r => Number(r[k] || 0)); if (!xs.length) return 0; fn = fn.toUpperCase(); if (fn === 'SUM') return xs.reduce((a, b) => a + b, 0); if (fn === 'COUNT') return xs.length; if (fn === 'MIN') return Math.min(...xs); if (fn === 'MAX') return Math.max(...xs); return xs.reduce((a, b) => a + b, 0) / xs.length; };
  const runCalc = () => { try { setCalcRes(fmt(safeCalc(String(calc).replace(/^=/, '').replace(/(SUM|AVG|AVERAGE|MIN|MAX|COUNT)\(\s*\[([a-z_0-9]+)\]\s*\)/gi, (_, f, k) => agg(f === 'AVERAGE' ? 'AVG' : f, k))))); } catch (e) { setCalcRes('error'); } };
  const footAgg = (c) => { if (c.type !== 'num') return ''; const mode = (prefs && prefs.aggs[c.k]) || (c.custom ? '' : 'sum'); if (!mode) return ''; const xs = view.map(r => Number(cellVal(r, c)) || 0); if (!xs.length) return '';
    const v = mode === 'sum' ? xs.reduce((a, b) => a + b, 0) : mode === 'avg' ? xs.reduce((a, b) => a + b, 0) / xs.length : mode === 'min' ? Math.min(...xs) : mode === 'max' ? Math.max(...xs) : xs.length; return mode.toUpperCase() + ' ' + fmt(v); };
  const cycleAgg = (k) => { const modes = ['sum', 'avg', 'min', 'max', 'count', '']; const cur = (prefs && prefs.aggs[k]) || 'sum'; savePrefs({ ...prefs, aggs: { ...prefs.aggs, [k]: modes[(modes.indexOf(cur) + 1) % modes.length] } }); };
  const exportCSV = () => { const e = s => '"' + String(s ?? '').replace(/"/g, '""') + '"'; const lines = [cols.map(c => e(c.t)).join(',')].concat(view.map(r => cols.map(c => e(fmt(cellVal(r, c)))).join(',')));
    const a = document.createElement('a'); a.href = URL.createObjectURL(new Blob([lines.join('\n')], { type: 'text/csv' })); a.download = 'recoveriq-sheet.csv'; a.click(); };
  const exportXLSX = () => { const X = classic.api && classic.api.getXLSX && classic.api.getXLSX(); if (!X) return exportCSV();
    const aoa = [cols.map(c => c.t)].concat(view.map(r => cols.map(c => (c.type === 'num' ? Number(cellVal(r, c)) || 0 : (cellVal(r, c) ?? '')))));
    const wb = X.utils.book_new(); X.utils.book_append_sheet(wb, X.utils.aoa_to_sheet(aoa), 'Cases'); X.writeFile(wb, 'recoveriq-sheet.xlsx'); return undefined; };

  const syncSlider = useCallback(() => { const el = scrollRef.current; if (!el) return; const max = el.scrollWidth - el.clientWidth; setScrollable(max > 4); setScrollPct(max > 0 ? Math.round(el.scrollLeft / max * 100) : 0); }, []);
  useEffect(() => { const t = setTimeout(syncSlider, 80); return () => clearTimeout(t); }, [rows, prefs, syncSlider]);
  useEffect(() => { window.addEventListener('resize', syncSlider); return () => window.removeEventListener('resize', syncSlider); }, [syncSlider]);
  const slideTo = (p) => { const el = scrollRef.current; if (!el) return; el.scrollLeft = (p / 100) * (el.scrollWidth - el.clientWidth); setScrollPct(p); };
  const nudge = (dir) => { const el = scrollRef.current; if (!el) return; const th = el.querySelector('thead th'); el.scrollBy({ left: dir * Math.max(90, (th ? th.getBoundingClientRect().width : 130) * 2), behavior: 'smooth' }); };
  const focusFx = (row, c, id, v) => { setFx({ row, c, id, label: c.t }); setFxVal(v == null ? '' : String(v)); };
  const commitFx = () => { if (!fx) return; const el = document.getElementById(fx.id); if (el) el.value = fxVal; const cur = fx.c.data ? ((fx.row.extra || {})[fx.c.k] || '') : (fx.row[fx.c.k] ?? ''); if (String(cur) !== fxVal) editCell(fx.row, fx.c, fxVal); };

  // KPIs follow the current view
  const today = istToday();
  const k = useMemo(() => view.reduce((t, r) => {
    if ((r.last_contacted_at || '').slice(0, 10) === today) t.contacted++;
    if (r.disposition === 'PTP' || r.status === 'ptp') t.ptp++;
    t.collected += Number(r.received_amount || 0);
    const base = Number(r.funding_amount) > 0 ? Number(r.funding_amount) : Number(r.total_outstanding) > 0 ? Number(r.total_outstanding) : Number(r.enr) || 0;
    t.pending += Math.max(0, base - (Number(r.received_amount) || 0)); return t;
  }, { contacted: 0, ptp: 0, collected: 0, pending: 0 }), [view, today]);
  const scopeTotal = (opts.combos || []).filter(c => (!bankF || c.bank === bankF) && (!prodF || c.product === prodF) && (!branchF || (c.branch || '').toLowerCase() === branchF.toLowerCase())).reduce((a, c) => a + c.count, 0);
  const banks = [...new Set((opts.combos || []).map(c => c.bank).filter(Boolean))].sort();
  const prods = [...new Set((opts.combos || []).filter(c => !bankF || c.bank === bankF).map(c => c.product).filter(Boolean))].sort();
  const locs = (() => { const m = new Map(); (opts.combos || []).filter(c => (!bankF || c.bank === bankF) && (!prodF || c.product === prodF) && c.branch)
    .forEach(c => { const key = c.branch.toLowerCase(); const e = m.get(key); m.set(key, { label: e ? e.label : c.branch, n: (e ? e.n : 0) + c.count }); }); return [...m.values()].sort((a, b) => a.label.localeCompare(b.label)); })();
  const escCount = rows.filter(r => r.escalated).length;
  const clearAll = () => { setPaidF(''); setBankF(''); setProdF(''); setBranchF(''); setSearch(''); setEscOnly(false); setReviewF(''); setCycles([]); setFilters({}); };

  return (
    <div className="ls">
      <ModuleHead icon={Table2} title="Live Sheet" sub={(bankF || prodF || branchF) ? `Totals for ${[bankF, prodF, branchF].filter(Boolean).join(' · ')}` : 'Everyone’s edits appear instantly — totals across all portfolios'} full="sheet">
        <span className={cx('pill', live ? 'good' : 'neutral')}><span className={cx('dot', live && 'pulse')} />{live ? 'Live' : 'Reconnecting…'}</span>
        <button className="btn" onClick={exportCSV}><Download />CSV</button>
        <button className="btn primary" onClick={exportXLSX}><Download />Excel</button>
      </ModuleHead>

      <div className="grid g-kpi" style={{ marginBottom: 14 }}>
        <Kpi icon={PhoneCall} label="Contacted today" i={1} value={num(k.contacted)} tone="info" tilt={false} />
        <Kpi icon={Handshake} label="Active PTP" i={2} value={num(k.ptp)} tone="accent" tilt={false} />
        <Kpi icon={Wallet} label="Collected" i={3} value={'₹' + fmt(k.collected)} tone="good" tilt={false} />
        <Kpi icon={Hourglass} label="Pending" i={4} value={'₹' + fmt(k.pending)} tone="warn" tilt={false} />
      </div>

      <div className="card toolbar-card rise">
        <div className="row wrap" style={{ gap: 8 }}>
          <div className="input-icon" style={{ width: 260 }}><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="11" cy="11" r="7" /><path d="m20 20-3.5-3.5" /></svg>
            <input className="input" value={search} onChange={e => setSearch(e.target.value)} placeholder="Card no, name, account, phone…" /></div>
          <select className="select" value={bankF} onChange={e => { setBankF(e.target.value); setProdF(''); }}><option value="">All banks</option>{banks.map(b => <option key={b}>{b}</option>)}</select>
          <select className="select" value={prodF} onChange={e => { setProdF(e.target.value); setBranchF(''); }}><option value="">All products</option>{prods.map(p => <option key={p}>{p}</option>)}</select>
          <select className="select" value={branchF} onChange={e => setBranchF(e.target.value)}><option value="">All locations</option>{locs.map(x => <option key={x.label} value={x.label}>{x.label} ({x.n})</option>)}</select>
          <select className="select" value={mb} onChange={e => setMb(e.target.value)} title="Each month is a separate book">
            <option value="current">This month</option><option value="next">Next month</option><option value="last">Last month</option><option value="">All months</option></select>
          <MultiSelect label="Cycle" width={150} selected={cycles} onChange={setCycles} options={[...new Set(rows.map(r => r.cycle).filter(Boolean))].sort().map(c => ({ value: c, label: 'Cycle ' + c }))} />
          <div className="grow" />
          <span className="faint" style={{ fontSize: 12 }}>{loading ? 'loading…' : num(view.length) + ' rows'}</span>
        </div>
        <div className="row wrap" style={{ gap: 8 }}>
          <Chips value={paidF} onChange={v => setPaidF(paidF === v ? '' : v)} label="Paid" options={[['', 'All'], ['PAID', 'Paid'], ['PARTIAL', 'Partial'], ['UNPAID', 'Unpaid']]} />
          {escCount > 0 && <button className={cx('chip', 'warn-chip', escOnly && 'on')} onClick={() => setEscOnly(v => !v)}><Flag size={13} />Escalated · {escCount}</button>}
          <span className="chips-l" style={{ marginLeft: 6 }}><Bookmark size={12} /></span>
          <button className={cx('chip', reviewF === 'any' && 'on')} onClick={() => setReviewF(reviewF === 'any' ? '' : 'any')}>Flagged</button>
          {REVIEW.filter(([c]) => rows.some(r => r.review_color === c)).map(([c, hex]) => <button key={c} title={c} className={cx('swatch-dot', reviewF === c && 'on')} style={{ background: hex }} onClick={() => setReviewF(reviewF === c ? '' : c)} />)}
          <button className="btn sm ghost" onClick={clearAll}><X />Clear</button>
          <div className="grow" />
          <div className="calc"><FunctionSquare size={15} /><input value={calc} onChange={e => setCalc(e.target.value)} onKeyDown={e => e.key === 'Enter' && runCalc()} placeholder="=SUM([pending_amount])" />
            <button className="btn sm" onClick={runCalc}><Sigma /></button>{calcRes !== '' && <b className="calc-r">= {calcRes}</b>}</div>
          <span className="pop-wrap">
            <button className={cx('btn sm', colMenu && 'primary')} onClick={() => setColMenu(v => !v)}><Columns3 />Columns</button>
            {colMenu && prefs && <><PopLayer onClose={() => setColMenu(false)} className="col-menu" align="right">
                <div className="chips-l">Presets</div>
                <div className="row" style={{ gap: 6 }}><button className="btn sm" onClick={() => preset('cc')}>Credit Card</button><button className="btn sm" onClick={() => preset('plbl')}>PL / BL</button></div>
                <div className="chips-l" style={{ marginTop: 8 }}>Show columns</div>
                <div className="col-list">{allDefs().map(c => <label key={c.k} className="ms-opt"><input type="checkbox" checked={prefs.visible.includes(c.k)} onChange={() => toggleCol(c.k)} />{c.t}{c.custom ? ' (ƒ)' : ''}</label>)}</div>
                <button className="btn sm block" onClick={addData}><Plus />Data column</button>
                <button className="btn sm block" onClick={addFormula}><Plus />Formula column (ƒ)</button>
              </PopLayer></>}
          </span>
        </div>
        {!loading && scopeTotal > rows.length && rows.length >= LIMIT && <div style={{ color: 'var(--warn)', fontSize: 12.5, fontWeight: 600 }}>Showing the latest {num(rows.length)} of {num(scopeTotal)} — pick a bank / product / location to see a whole portfolio.</div>}
      </div>
      {err && <div style={{ color: 'var(--bad)', fontSize: 13, margin: '0 0 8px' }}>{err}</div>}

      <div className="card ls-fx">
        <span className="ls-fx-l">{fx ? fx.label : 'ƒx'}</span>
        <input value={fxVal} disabled={!fx} placeholder={fx ? `Full text of “${fx.label}” — edit here, Enter to save` : 'Click a cell to read or edit its full text here'}
          onChange={e => { setFxVal(e.target.value); const el = fx && document.getElementById(fx.id); if (el) el.value = e.target.value; }}
          onKeyDown={e => { if (e.key === 'Enter') { e.preventDefault(); commitFx(); e.target.blur(); } }} onBlur={commitFx} />
      </div>

      {scrollable && <div className="card ls-slide">
        <button className="btn sm ghost" onClick={() => nudge(-1)} aria-label="Scroll left"><ChevronLeft /></button>
        <input type="range" min="0" max="100" value={scrollPct} onChange={e => slideTo(Number(e.target.value))} aria-label="Scroll the sheet sideways" />
        <button className="btn sm ghost" onClick={() => nudge(1)} aria-label="Scroll right"><ChevronRight /></button>
        <span className="faint" style={{ minWidth: 36, textAlign: 'right', fontSize: 12 }}>{scrollPct}%</span>
      </div>}

      <div className="card ls-scroll" ref={scrollRef} onScroll={syncSlider}>
        {!prefs ? <div style={{ padding: 20 }} className="faint">Loading sheet…</div> :
        <table className="ls-t">
          <thead>
            <tr><th className="ls-act">Actions</th>
              {cols.map(c => <th key={c.k} draggable onDragStart={e => { e.dataTransfer.setData('text/col', c.k); e.dataTransfer.effectAllowed = 'move'; }}
                onDragOver={e => { e.preventDefault(); e.dataTransfer.dropEffect = 'move'; }} onDrop={e => { e.preventDefault(); reorder(e.dataTransfer.getData('text/col'), c.k); }}
                onClick={() => setSort(s => (s && s.k === c.k ? { k: c.k, dir: s.dir === 'asc' ? 'desc' : 'asc' } : { k: c.k, dir: 'asc' }))} title="Drag to reorder · click to sort">
                <span className="grip">⠿</span>{c.t}{c.edit ? <span className="faint"> ✎</span> : ''}{sort && sort.k === c.k ? (sort.dir === 'asc' ? ' ▲' : ' ▼') : ''}</th>)}
            </tr>
            <tr className="ls-fil"><th />{cols.map(c => <th key={c.k}>{!c.custom && <input value={filters[c.k] || ''} placeholder="filter" onChange={e => setFilters(f => ({ ...f, [c.k]: e.target.value }))} />}</th>)}</tr>
          </thead>
          <tbody>{view.map(row => { const ed = others(row.id); return (
            <tr key={row.id} className={cx(row.escalated && 'esc')} style={row.review_color ? { boxShadow: `inset 4px 0 0 ${REVIEW_HEX[row.review_color] || '#888'}` } : undefined}>
              <td className="ls-act"><div className="row" style={{ gap: 2 }}>
                {row.phone && <button className="ls-ico" title={vici ? 'Call via ViciDial' : 'Call'} onClick={() => dial(row)}><Phone /></button>}
                {row.phone && <a className="ls-ico wa" title="WhatsApp" href={'https://wa.me/' + waNum(row.phone)} target="_blank" rel="noreferrer"><MessageCircle /></a>}
                <button className="ls-ico" title="Open on my phone" onClick={() => pushToPhone(row)}><Smartphone /></button>
                {row.escalated && <span className="pill bad" title="Escalated — locked">ESC</span>}
                {row.closed && <span className="pill neutral" title={`Closed ${row.close_date || ''}`}><Lock size={10} /></span>}
                {ed.length > 0 && <span className="pill warn" title={ed.map(e => e.name + (e.field ? ` (${e.field})` : '')).join(', ') + ' editing now'}>✏ {ed[0].name.split(' ')[0]}{ed.length > 1 ? ` +${ed.length - 1}` : ''}</span>}
              </div></td>
              {cols.map(c => { const id = 'ls-' + row.id + '-' + c.k; const locked = (row.closed || row.escalated) && (c.edit || c.data); return (
                <td key={c.k} className={c.type === 'num' ? 'r' : ''}>
                  {locked ? <span className="faint" title={row.escalated ? 'Escalated — locked' : 'Closed for the month — locked'}>{fmt(cellVal(row, c)) || '—'}</span>
                    : c.data ? <input key={id} id={id} defaultValue={(row.extra || {})[c.k] || ''} onFocus={e => { sendPresence(row.id, c.t, true); focusFx(row, c, id, e.target.value); }}
                      onInput={e => setFxVal(e.target.value)} onBlur={e => { sendPresence(row.id, c.t, false); if (String(e.target.value) !== String((row.extra || {})[c.k] || '')) editCell(row, c, e.target.value); }}
                      onKeyDown={e => { if (e.key === 'Enter') e.target.blur(); }} />
                    : c.custom ? fmt(rowFormula(c.formula, row))
                    : c.k === 'customer_name' ? <button className="link-btn" onClick={() => openCase(row)}>{row.customer_name || '—'}</button>
                    : !c.edit ? fmt(row[c.k])
                    : c.type === 'sel' ? <select value={row[c.k] || ''} onChange={e => editCell(row, c, e.target.value)}>{c.opts.map(o => <option key={o} value={o}>{o || '—'}</option>)}</select>
                    : c.type === 'date' ? <input type="date" value={(row[c.k] || '').slice(0, 10)} onChange={e => editCell(row, c, e.target.value)} />
                    : <input key={id} id={id} type={c.type === 'num' ? 'number' : 'text'} defaultValue={row[c.k] ?? ''} onFocus={e => { sendPresence(row.id, c.t, true); focusFx(row, c, id, e.target.value); }}
                      onInput={e => setFxVal(e.target.value)} onBlur={e => { sendPresence(row.id, c.t, false); if (String(e.target.value) !== String(row[c.k] ?? '')) editCell(row, c, e.target.value); }}
                      onKeyDown={e => { if (e.key === 'Enter') e.target.blur(); }} />}
                </td>); })}
            </tr>); })}</tbody>
          <tfoot><tr><td />{cols.map(c => <td key={c.k} className="r" onClick={() => c.type === 'num' && cycleAgg(c.k)} title={c.type === 'num' ? 'Click to change aggregation' : ''}>{footAgg(c)}</td>)}</tr></tfoot>
        </table>}
        {prefs && !loading && !view.length && <div className="faint" style={{ padding: 24, textAlign: 'center' }}>No rows match.</div>}
      </div>
      <CaseDrawer id={Number(sp.get('open')) || null} onClose={() => setSp({})} />
    </div>
  );
}

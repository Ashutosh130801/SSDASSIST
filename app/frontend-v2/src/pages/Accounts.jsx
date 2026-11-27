import React, { useEffect, useMemo, useState } from 'react';
import {
  AlertTriangle, ArrowLeft, Building2, Download, FileSpreadsheet, FolderKanban, Landmark, Lock, MapPin, Megaphone, PhoneForwarded,
  Pencil, Plus, RotateCcw, Shuffle, Trash2, Undo2, Upload, Users2, Wand2, Wrench, X, Zap, Archive, LayoutGrid, List, Car, Tag, Repeat, Compass, Phone,
} from 'lucide-react';
import { api, download } from '../lib/api.js';
import { useAuth } from '../lib/auth.jsx';
import { inr, inrShort, num, cx, fmtDate, fmtTime } from '../lib/format.js';
import { Card, Kpi, Pill, StatusPill, Empty, Skeleton, useLoad, useToast } from '../components/ui.jsx';
import { ModuleHead, Chips, MultiSelect, Modal, Field, SearchBox, useLive, useClassicUI } from '../modules/kit.jsx';

const MB = [['current', 'This month'], ['next', 'Next month'], ['last', 'Last month'], ['', 'All months']];
const monthLbl = (p) => { if (!p || !/^\d{4}-\d{2}$/.test(p)) return p || ''; const M = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']; return M[parseInt(p.slice(5, 7), 10) - 1] + " '" + p.slice(2, 4); };

function BankLogo({ bank, domain, size = 56 }) {
  const [step, setStep] = useState(0);
  const ini = (bank || '—').trim().replace(/[^A-Za-z]/g, '').slice(0, 2).toUpperCase() || '#';
  if (!domain || step >= 2) return <span className="bank-logo ini" style={{ width: size, height: size, fontSize: size * .34 }}>{ini}</span>;
  const src = step === 0 ? `https://www.google.com/s2/favicons?sz=128&domain=${domain}` : `https://icons.duckduckgo.com/ip3/${domain}.ico`;
  return <span className="bank-logo" style={{ width: size, height: size }}><img key={step} src={src} alt={bank} loading="lazy" referrerPolicy="no-referrer" onError={() => setStep(s => s + 1)} /></span>;
}

function Money({ received, pending, paid, unpaid }) {
  const tot = (received || 0) + (pending || 0); const p = tot ? (received || 0) * 100 / tot : 0;
  return <>
    <div className="branch-money"><div><span>Recovered</span><b style={{ color: 'var(--good)' }}>{inr(received)}</b></div>
      <div style={{ textAlign: 'right' }}><span>Pending</span><b style={{ color: 'var(--warn)' }}>{inr(pending)}</b></div></div>
    <div className="pbar tone-good" style={{ height: 6, flex: 'none', width: '100%' }}><i style={{ width: p + '%' }} /></div>
    {paid != null && <div className="cell-sub"><span style={{ color: 'var(--good)' }}>{num(paid)} paid</span> · <span style={{ color: 'var(--warn)' }}>{num(unpaid)} unpaid</span></div>}
  </>;
}

/** Accounts — the complete case book: banks → products → locations → cases, every filter, bulk
 *  re-allocation / joint / transfer / delete, uploads, DPR, corrections, campaigns and exports. */
export default function Accounts() {
  const { user } = useAuth();
  const toast = useToast();
  const ui = useClassicUI();
  const role = user.role;
  const canUpload = ['admin', 'backend', 'headoffice'].includes(role);
  const canDpr = ['admin', 'headoffice', 'backend', 'manager', 'teamlead'].includes(role);
  const canReassign = ['admin', 'manager', 'teamlead', 'headoffice'].includes(role);
  const isAdmin = role === 'admin';
  const isHO = ['headoffice', 'admin'].includes(role);
  const canTools = ['admin', 'headoffice', 'teamlead'].includes(role);

  const [mode, setMode] = useState('products');
  const [mb, setMb] = useState('current');
  const [bankSel, setBankSel] = useState('');
  const [branchProduct, setBranchProduct] = useState(null);
  const [bank, setBank] = useState(''); const [product, setProduct] = useState(''); const [segment, setSegment] = useState('');
  const [branchF, setBranchF] = useState(''); const [cardPeriod, setCardPeriod] = useState('');
  const [paid, setPaid] = useState(''); const [q, setQ] = useState(''); const [qd, setQd] = useState('');
  const [openState, setOpenState] = useState(''); const [cyc, setCyc] = useState('');
  const [area, setArea] = useState(''); const [flaggedOnly, setFlaggedOnly] = useState(false);
  const [cycles, setCycles] = useState([]); const [fosSel, setFosSel] = useState([]); const [callerSel, setCallerSel] = useState([]);
  const [vehType, setVehType] = useState(''); const [brandF, setBrandF] = useState(''); const [oldNew, setOldNew] = useState('');
  const [picked, setPicked] = useState({}); const [pickedRm, setPickedRm] = useState({});
  const [busy, setBusy] = useState(false);
  const [delOpen, setDelOpen] = useState(false); const [delReason, setDelReason] = useState('');
  const [resetOpen, setResetOpen] = useState(false); const [resetTxt, setResetTxt] = useState('');
  const [segEdit, setSegEdit] = useState(false); const [segNew, setSegNew] = useState('');
  const [limit, setLimit] = useState(300);
  useEffect(() => { const t = setTimeout(() => setQd(q.trim()), 280); return () => clearTimeout(t); }, [q]);

  const mq = mb ? '?month_bucket=' + mb : '';
  const summaryL = useLoad(() => api('/api/cases/product-summary' + mq).catch(() => []), [mb]);
  const banksL = useLoad(() => api('/api/cases/portfolio-banks' + mq).catch(() => []), [mb]);
  const { data: users } = useLoad(() => api('/api/users').catch(() => []), []);
  const staff = useMemo(() => Object.fromEntries((users || []).map(u => [u.id, u.name])), [users]);
  const pq = new URLSearchParams(); if (bank) pq.set('bank', bank); if (product) pq.set('product', product); if (branchF) pq.set('branch', branchF);
  const pqs = pq.toString();
  const { data: fo } = useLoad(() => (mode === 'list' && (bank || product) ? api('/api/cases/filter-options?' + pqs).catch(() => ({})) : Promise.resolve({})), [mode, pqs]);
  const { data: areas } = useLoad(() => (mode === 'list' && (bank || product) ? api('/api/cases/areas?' + pqs).catch(() => []) : Promise.resolve([])), [mode, pqs]);
  const listQ = (() => {
    const p = new URLSearchParams(pq);
    if (segment) p.set('segment', segment); if (paid) p.set('paid_status', paid); if (qd) p.set('search', qd);
    if (openState) p.set('closed', openState === 'closed' ? 'true' : 'false'); if (cyc) p.set('cyc', cyc);
    if (cardPeriod) p.set('period', cardPeriod); else if (mb) p.set('month_bucket', mb);
    if (area) p.set('area', area); if (cycles.length) p.set('cycles', cycles.join(','));
    if (fosSel.length) p.set('fos_ids', fosSel.join(',')); if (callerSel.length) p.set('caller_ids', callerSel.join(','));
    if (vehType) p.set('vehicle_type', vehType); if (brandF) p.set('brand', brandF); if (oldNew) p.set('old_new', oldNew);
    return p.toString();
  })();
  const casesL = useLoad(() => (mode === 'list' ? api('/api/cases?' + listQ) : Promise.resolve(null)), [mode, listQ]);
  const removedL = useLoad(() => (mode === 'removed' ? api('/api/cases/removed').catch(() => []) : Promise.resolve(null)), [mode]);
  const reloadAll = () => { summaryL.reload(); banksL.reload(); casesL.reload(); removedL.reload(); };
  useLive(reloadAll);
  useEffect(() => { setPicked({}); setLimit(300); }, [listQ]);

  const summary = summaryL.data || []; const banks = banksL.data || [];
  const cases = Array.isArray(casesL.data) ? casesL.data : null;
  const shownCases = cases ? (flaggedOnly ? cases.filter(c => c.flagged) : cases) : [];
  const pickedIds = Object.keys(picked).filter(k => picked[k]).map(Number);
  const pickedRmIds = Object.keys(pickedRm).filter(k => pickedRm[k]).map(Number);
  const bankProducts = summary.filter(c => (c.bank || '—') === bankSel);
  const o = fo || {};

  const clearFilters = () => { setCycles([]); setFosSel([]); setCallerSel([]); setPaid(''); setArea(''); setFlaggedOnly(false); setVehType(''); setBrandF(''); setOldNew(''); };
  const openProduct = (c, br = '') => { setBank(c.bank === '—' ? '' : c.bank); setProduct(c.product === '—' ? '' : c.product); setSegment(c.segment || ''); setBranchF(br || ''); setCardPeriod(c.period || ''); clearFilters(); setMode('list'); };
  const openProductCard = (c) => { if (c.branch_split && (c.branches || []).length) setBranchProduct({ ...c }); else openProduct(c); };
  const allCases = () => { setBank(''); setProduct(''); setSegment(''); setBranchF(''); setCardPeriod(''); setArea(''); setBranchProduct(null); clearFilters(); setOpenState(''); setCyc(''); setMode('list'); };
  const backToProducts = () => { setProduct(''); setSegment(''); setBranchF(''); setCardPeriod(''); setArea(''); clearFilters(); setBranchProduct(null); setMode('products'); };
  const dlPortfolio = (e, b, p, br, period) => {
    if (e) e.stopPropagation();
    const qs = new URLSearchParams({ bank: b || '', product: p || '' }); if (br) qs.set('branch', br);
    if (period) qs.set('period', period); else if (mb) qs.set('month_bucket', mb);
    toast('Preparing Excel…');
    download('/api/cases/portfolio-export?' + qs, `${b}_${p}_${br || 'All_locations'}${period ? '_' + period : ''}.xlsx`.replace(/[^\w.-]+/g, '_'));
  };
  const allocate = async () => { setBusy(true); try { const r = await api('/api/cases/allocate', { method: 'POST', body: { only_unallocated: true } }); toast(`Allocated ${r.fos_allocated} to FOS, ${r.caller_allocated} to callers.`); reloadAll(); } catch (e) { toast(e.message, 'err'); } finally { setBusy(false); } };
  const geocode = async () => {
    setBusy(true);
    try { let total = 0, rounds = 0;
      while (rounds < 60) { rounds++; const r = await api('/api/cases/geocode?limit=20', { method: 'POST' }); total += r.geocoded; toast(`Geocoded ${total} so far… ${r.remaining} left`); if (r.remaining === 0 || r.geocoded === 0) break; }
      toast(`Geocoding done — ${total} cases now mapped.`); reloadAll();
    } catch (e) { toast(e.message, 'err'); } finally { setBusy(false); }
  };
  const doReset = async () => { setBusy(true); try { const r = await api('/api/cases/all?confirm=DELETE-ALL', { method: 'DELETE' }); setResetOpen(false); setResetTxt(''); toast(`Removed ${r.deleted_cases} cases. Now upload your fresh file.`); reloadAll(); ui.modal('UploadModal', {}).then(reloadAll); } catch (e) { toast(e.message, 'err'); } finally { setBusy(false); } };
  const doRemove = async () => { setBusy(true); try { const r = await api('/api/cases/remove', { method: 'POST', body: { ids: pickedIds, reason: delReason || null } }); toast(`Removed ${r.removed} case${r.removed === 1 ? '' : 's'} → Removed cases.`); setDelOpen(false); setDelReason(''); setPicked({}); reloadAll(); } catch (e) { toast(e.message, 'err'); } finally { setBusy(false); } };
  const doRestore = async (ids) => { try { const r = await api('/api/cases/restore', { method: 'POST', body: { ids } }); toast(`Restored ${r.restored} case${r.restored === 1 ? '' : 's'}.`); setPickedRm({}); reloadAll(); } catch (e) { toast(e.message, 'err'); } };
  const doPurge = async (ids) => { if (!window.confirm(`Permanently delete ${ids.length} case(s)? This cannot be undone.`)) return; try { const r = await api('/api/cases/removed/purge', { method: 'POST', body: { ids } }); toast(`Purged ${r.purged} case(s).`); setPickedRm({}); reloadAll(); } catch (e) { toast(e.message, 'err'); } };
  const saveSegment = async () => {
    setBusy(true);
    try { const r = await api('/api/cases/portfolio/set-segment', { method: 'POST', body: { bank, product, segment, branch: branchF || '', period: cardPeriod || '', new_segment: segNew } });
      toast('Segment changed to ' + r.new_segment + ' for ' + r.updated + ' case(s)'); setSegEdit(false); backToProducts(); reloadAll();
    } catch (e) { toast(e.message || 'Could not change segment', 'err'); } finally { setBusy(false); }
  };
  const nFilters = cycles.length + fosSel.length + callerSel.length + (paid ? 1 : 0) + (vehType ? 1 : 0) + (brandF ? 1 : 0) + (oldNew ? 1 : 0) + (area ? 1 : 0);
  const tot = useMemo(() => banks.reduce((t, b) => ({ count: t.count + (b.count || 0), received: t.received + (b.received || 0), pending: t.pending + (b.pending || 0) }), { count: 0, received: 0, pending: 0 }), [banks]);

  return (
    <>
      <ModuleHead icon={FolderKanban} title="Accounts" sub="Every portfolio, month by month — banks, products, locations and cases">
        {canDpr && <button className="btn" onClick={() => ui.modal('DprModal', {}).then(reloadAll)}><Landmark />DPR update</button>}
        {canUpload && <button className="btn primary" onClick={() => ui.modal('UploadModal', {}).then(reloadAll)}><Upload />Upload</button>}
      </ModuleHead>

      <div className="card toolbar-card rise">
        <div className="row wrap" style={{ gap: 10 }}>
          <div className="seg-tabs" style={{ margin: 0, padding: 0 }}>
            <button className={mode === 'products' ? 'on' : ''} onClick={() => setMode('products')}><LayoutGrid /><span>Portfolios</span></button>
            <button className={mode === 'list' && !product && !bank ? 'on' : ''} onClick={allCases}><List /><span>All cases</span></button>
            {isHO && <button className={mode === 'removed' ? 'on' : ''} onClick={() => setMode('removed')}><Archive /><span>Removed</span></button>}
          </div>
          {mode !== 'removed' && <Chips value={mb} onChange={setMb} options={MB} />}
          <div className="grow" />
          {isHO && cases && cases.length > 0 && <button className="btn sm" onClick={() => ui.modal('ViciPushModal', { cases })}><PhoneForwarded />Send to ViciDial</button>}
          {isHO && <button className="btn sm" onClick={() => ui.modal('UploadsModal', {}).then(reloadAll)}><Undo2 />Undo upload</button>}
          {canTools && <button className="btn sm" onClick={() => ui.tools(['CorrectColumnsButton', 'BackfillAddressButton', 'RelinkAllocationButton'], 'Data corrections').then(reloadAll)}><Wrench />Corrections</button>}
        </div>
        {isAdmin && <div className="row wrap" style={{ gap: 8 }}>
          <span className="chips-l">Admin</span>
          <button className="btn sm" disabled={busy} onClick={allocate}><Zap />Auto-allocate</button>
          <button className="btn sm" disabled={busy} onClick={geocode}><MapPin />Geocode</button>
          <button className="btn sm" disabled={!cases || !cases.length} onClick={() => ui.modal('CampaignModal', { cases: cases || [] })}><Megaphone />Campaign</button>
          <button className="btn sm" onClick={() => download('/api/import/export', 'Recovery_Tracker.xlsx')}><Download />Export Excel</button>
          <button className="btn sm ghost danger" disabled={busy} onClick={() => { setResetTxt(''); setResetOpen(true); }}><Trash2 />Reset all</button>
        </div>}
      </div>

      {/* ── Removed cases ── */}
      {mode === 'removed' && (!removedL.data ? <Skeleton h={240} /> : (
        <Card title={`Removed cases · ${removedL.data.length}`} sub="Restore to return them to active work, or purge to delete permanently" pad={false} className="rise"
          actions={pickedRmIds.length > 0 && <div className="row" style={{ gap: 6 }}><button className="btn sm" onClick={() => doRestore(pickedRmIds)}><RotateCcw />Restore {pickedRmIds.length}</button>
            <button className="btn sm ghost danger" onClick={() => doPurge(pickedRmIds)}><Trash2 />Purge {pickedRmIds.length}</button></div>}>
          {!removedL.data.length ? <Empty icon={Archive} title="No removed cases" /> :
            <div className="table-wrap"><table className="t">
              <thead><tr><th style={{ width: 34 }}><input type="checkbox" checked={pickedRmIds.length === removedL.data.length} onChange={e => setPickedRm(e.target.checked ? Object.fromEntries(removedL.data.map(c => [c.id, true])) : {})} /></th>
                <th>Customer</th><th>Portfolio</th><th>Account / Card</th><th className="r">Pending</th><th>Removed on</th><th></th></tr></thead>
              <tbody>{removedL.data.map(c => <tr key={c.id}>
                <td><input type="checkbox" checked={!!pickedRm[c.id]} onChange={() => setPickedRm(p => ({ ...p, [c.id]: !p[c.id] }))} /></td>
                <td className="cell-main">{c.customer_name || '—'}</td><td className="muted">{c.bank} · {c.product || '—'}</td>
                <td className="mono">{c.account_no || c.card_no || '—'}</td><td className="r" style={{ color: 'var(--warn)' }}>{inr(c.pending_amount)}</td>
                <td className="faint" style={{ fontSize: 12 }}>{c.removed_at ? `${fmtDate(c.removed_at)} ${fmtTime(c.removed_at)}` : '—'}</td>
                <td style={{ whiteSpace: 'nowrap' }}><button className="btn sm" onClick={() => doRestore([c.id])}><RotateCcw />Restore</button> <button className="btn sm ghost danger" onClick={() => doPurge([c.id])}><Trash2 /></button></td>
              </tr>)}</tbody></table></div>}
        </Card>))}

      {/* ── Portfolios: banks → products → locations ── */}
      {mode === 'products' && (summaryL.loading && !summary.length ? <div className="branch-grid">{[...Array(6)].map((_, i) => <Skeleton key={i} h={190} />)}</div>
        : branchProduct ? <>
          <div className="row wrap" style={{ gap: 10, marginBottom: 14 }}>
            <button className="btn ghost" onClick={() => setBranchProduct(null)}><ArrowLeft />{branchProduct.bank} products</button>
            <Pill tone="accent">{branchProduct.bank} · {branchProduct.product}{branchProduct.segment ? ' · ' + branchProduct.segment : ''}{branchProduct.period ? ' · ' + monthLbl(branchProduct.period) : ''}</Pill>
            <div className="grow" /><button className="btn sm" onClick={e => dlPortfolio(e, branchProduct.bank, branchProduct.product, '', branchProduct.period)}><FileSpreadsheet />Excel (all locations)</button>
          </div>
          <div className="branch-grid">{(branchProduct.branches || []).map((br, i) => (
            <div key={i} className="card branch-card rise" style={{ '--i': Math.min(i, 12) }} onClick={() => openProduct(branchProduct, br.branch)} role="button" tabIndex={0}>
              <div className="row"><span className="mod-ic sm"><MapPin /></span><b className="grow branch-n">{br.branch}</b><Pill tone="accent">{num(br.count)}</Pill></div>
              <div className="cell-sub">{[branchProduct.product, branchProduct.segment, branchProduct.period && monthLbl(branchProduct.period)].filter(Boolean).join(' · ')}</div>
              <Money received={br.received} pending={br.pending} paid={br.paid || 0} unpaid={br.unpaid || 0} />
              <button className="btn sm ghost" onClick={e => dlPortfolio(e, branchProduct.bank, branchProduct.product, br.branch, branchProduct.period)}><FileSpreadsheet />Excel</button>
            </div>))}</div>
        </> : bankSel ? <>
          <div className="row wrap" style={{ gap: 10, marginBottom: 14 }}>
            <button className="btn ghost" onClick={() => setBankSel('')}><ArrowLeft />Banks</button><Pill tone="accent">{bankSel}</Pill>
          </div>
          {!bankProducts.length ? <Empty title="No products for this bank" /> :
            <div className="branch-grid">{bankProducts.map((c, i) => (
              <div key={i} className="card branch-card rise" style={{ '--i': Math.min(i, 12) }} onClick={() => openProductCard(c)} role="button" tabIndex={0}>
                <div className="row"><span className="mod-ic sm"><FolderKanban /></span><b className="grow branch-n">{c.product}{c.segment ? ' · ' + c.segment : ''}</b><Pill tone="accent">{num(c.count)}</Pill></div>
                <div className="row wrap" style={{ gap: 6 }}>{c.period && <Pill tone="info">{monthLbl(c.period)}</Pill>}{c.branch_split && <Pill tone="neutral"><MapPin size={11} />{(c.branches || []).length} locations</Pill>}</div>
                <Money received={c.received} pending={c.pending} paid={c.paid || 0} unpaid={c.unpaid || 0} />
                <div className="row"><span className="faint grow" style={{ fontSize: 11.5 }}>{c.branch_split ? 'Tap to choose a location →' : 'Tap to open cases →'}</span>
                  <button className="btn sm ghost" title={`Download all ${c.count} cases as Excel`} onClick={e => dlPortfolio(e, c.bank, c.product, '', c.period)}><FileSpreadsheet />Excel</button></div>
              </div>))}</div>}
        </> : <>
          <div className="grid g-kpi" style={{ marginBottom: 16 }}>
            <Kpi icon={Building2} label="Banks" i={1} value={num(banks.length)} />
            <Kpi icon={FolderKanban} label="Cases" i={2} value={num(tot.count)} tone="info" />
            <Kpi icon={Landmark} label="Recovered" i={3} value={tot.received} format={inrShort} tone="good" />
            <Kpi icon={AlertTriangle} label="Pending" i={4} value={tot.pending} format={inrShort} tone="warn" />
          </div>
          {!banks.length ? <Empty icon={Building2} title="No cases uploaded yet">{canUpload && 'Use Upload to add a product file.'}</Empty> :
            <div className="bank-grid">{banks.map((b, i) => (
              <div key={i} className="card bank-card rise" style={{ '--i': Math.min(i, 12) }} onClick={() => setBankSel(b.bank)} role="button" tabIndex={0}>
                <BankLogo bank={b.bank} domain={b.logo_domain} size={72} />
                <b className="bank-n">{b.bank}</b>
                <div className="faint" style={{ fontSize: 12.5 }}>{b.product_count} product{b.product_count === 1 ? '' : 's'} · {num(b.count)} cases</div>
                <Money received={b.received} pending={b.pending} />
              </div>))}</div>}
        </>)}

      {/* ── Case list ── */}
      {mode === 'list' && <>
        <div className="card toolbar-card rise">
          <div className="row wrap" style={{ gap: 8 }}>
            {product && <button className="btn sm ghost" onClick={backToProducts}><ArrowLeft />Portfolios</button>}
            {product && <Pill tone="accent">{bank} · {product}{segment ? ' · ' + segment : ''}{branchF ? ' · ' + branchF : ''}{cardPeriod ? ' · ' + monthLbl(cardPeriod) : ''}</Pill>}
            {product && isHO && <button className="btn sm ghost" onClick={() => { setSegNew(segment || 'Credit Card'); setSegEdit(true); }}><Pencil />Segment</button>}
            {product && <button className="btn sm" onClick={e => dlPortfolio(e, bank, product, branchF, cardPeriod)}><FileSpreadsheet />Portfolio Excel</button>}
            <SearchBox value={q} onChange={setQ} placeholder="Name, account, card, phone, pincode, case #" width={300} />
            <div className="grow" />
            <span className="faint" style={{ fontSize: 12 }}>{cases ? num(shownCases.length) + ' cases' : '…'}</span>
          </div>
          <div className="chips">
            <Chips value={paid} onChange={v => setPaid(paid === v ? '' : v)} options={[['', 'All'], ['PAID', 'Paid'], ['UNPAID', 'Unpaid'], ['PARTIAL', 'Partial']]} />
            <MultiSelect label="Cycle" icon={Repeat} width={160} selected={cycles} onChange={setCycles} options={(o.cycles || []).map(c => ({ value: c, label: 'Cycle ' + c }))} />
            <MultiSelect label="FOS" icon={Compass} selected={fosSel} onChange={setFosSel} options={(o.fos || []).map(f => ({ value: f.id, label: f.name + (f.code ? ` (${f.code})` : '') }))} />
            <MultiSelect label="Caller" icon={Phone} selected={callerSel} onChange={setCallerSel} options={(o.callers || []).map(f => ({ value: f.id, label: f.name + (f.code ? ` (${f.code})` : '') }))} />
            {(areas || []).length > 0 && <select className="select" value={area} onChange={e => setArea(e.target.value)}><option value="">All areas</option>{areas.map(a => <option key={a}>{a}</option>)}</select>}
            {(o.vehicle_types || []).length > 0 && <select className="select" value={vehType} onChange={e => setVehType(e.target.value)}><option value="">All vehicle types</option>{o.vehicle_types.map(v => <option key={v}>{v}</option>)}</select>}
            {(o.brands || []).length > 0 && <select className="select" value={brandF} onChange={e => setBrandF(e.target.value)}><option value="">All brands</option>{o.brands.map(v => <option key={v}>{v}</option>)}</select>}
            {(o.old_new || []).length > 0 && <select className="select" value={oldNew} onChange={e => setOldNew(e.target.value)}><option value="">Old / New</option>{o.old_new.map(v => <option key={v}>{v}</option>)}</select>}
            {(cases || []).some(c => c.flagged) && <button className={cx('chip', 'warn-chip', flaggedOnly && 'on')} onClick={() => setFlaggedOnly(v => !v)}><AlertTriangle size={13} />Flagged · {(cases || []).filter(c => c.flagged).length}</button>}
            {nFilters > 0 && <button className="btn sm ghost" onClick={clearFilters}><X />Clear</button>}
          </div>
          <div className="chips">
            <Chips value={openState} onChange={v => setOpenState(openState === v ? '' : v)} label="State" options={[['', 'All'], ['open', 'Open'], ['closed', 'Closed']]} />
            {openState === 'closed' && <input className="input" type="number" min="1" max="31" placeholder="Cycle day" value={cyc} onChange={e => setCyc(e.target.value)} style={{ width: 110 }} />}
            <div className="grow" />
            {canReassign && <button className="btn sm" onClick={() => ui.modal('AllocTransferModal', {}).then(reloadAll)}><Shuffle />Transfer by person</button>}
            {canReassign && pickedIds.length > 0 && <button className="btn sm primary" onClick={() => ui.modal('ReassignModal', { ids: pickedIds }).then(ok => { if (ok) { setPicked({}); reloadAll(); } })}><Shuffle />Re-allocate {pickedIds.length}</button>}
            {canReassign && pickedIds.length > 0 && <button className="btn sm" onClick={() => ui.modal('JointAllocateModal', { caseIds: pickedIds }).then(ok => { if (ok) { setPicked({}); reloadAll(); } })}><Users2 />Joint allocate {pickedIds.length}</button>}
            {isHO && pickedIds.length > 0 && <button className="btn sm danger-solid" onClick={() => setDelOpen(true)}><Trash2 />Delete {pickedIds.length}</button>}
          </div>
        </div>

        <Card pad={false} className="rise">
          {!cases ? <div style={{ padding: 16 }}><Skeleton h={260} /></div> : !shownCases.length ? <Empty icon={FolderKanban} title="No cases here" /> : <>
            <div className="table-wrap" style={{ maxHeight: 'calc(100vh - 330px)' }}><table className="t">
              <thead><tr>
                {(isHO || canReassign) && <th style={{ width: 34 }}><input type="checkbox" checked={pickedIds.length > 0 && pickedIds.length === shownCases.length}
                  onChange={e => setPicked(e.target.checked ? Object.fromEntries(shownCases.map(c => [c.id, true])) : {})} /></th>}
                <th>Customer</th><th>Portfolio</th><th>Cycle</th><th>Caller</th><th>FOS</th><th>Account</th><th className="r">Received</th><th className="r">Pending</th><th>Status</th><th>Paid</th><th>Pincode</th><th>Disposition</th>
              </tr></thead>
              <tbody>{shownCases.slice(0, limit).map(c => <tr key={c.id} className={cx('click', c.flagged && 'flag-row')} onClick={() => ui.openCase(c.id)}>
                {(isHO || canReassign) && <td onClick={e => e.stopPropagation()}><input type="checkbox" checked={!!picked[c.id]} onChange={() => setPicked(p => ({ ...p, [c.id]: !p[c.id] }))} /></td>}
                <td><div className="cell-main">{c.customer_name || '—'}{c.flagged && <AlertTriangle size={13} style={{ color: 'var(--bad)', marginLeft: 6 }} title={c.flag_reason || 'Needs review'} />}</div>
                  <div className="row" style={{ gap: 4 }}>{c.phone && <span className="cell-sub">{c.phone}</span>}{c.closed && <Pill tone="neutral"><Lock size={10} />closed</Pill>}{c.escalated && <Pill tone="bad">escalated</Pill>}</div></td>
                <td className="muted">{c.bank}<div className="cell-sub">{c.product || '—'}</div></td>
                <td className="muted">{c.cycle || '—'}</td>
                <td onClick={e => e.stopPropagation()}>{c.assigned_caller_id ? <button className="link-btn" onClick={() => ui.perf(c.assigned_caller_id, 'caller', staff[c.assigned_caller_id] || c.caller_name)}>{staff[c.assigned_caller_id] || c.caller_name}</button> : <span className="faint">{c.caller_name || '—'}</span>}</td>
                <td onClick={e => e.stopPropagation()}>{c.assigned_fos_id ? <button className="link-btn" onClick={() => ui.perf(c.assigned_fos_id, 'fos', staff[c.assigned_fos_id] || c.fos_name)}>{staff[c.assigned_fos_id] || c.fos_name}</button> : <span className="faint">{c.fos_name || '—'}</span>}</td>
                <td className="mono">{c.account_no || c.card_no || '—'}</td>
                <td className="r" style={{ color: 'var(--good)' }}>{inr(c.received_amount)}</td>
                <td className="r" style={{ color: 'var(--warn)' }}><b>{inr(c.pending_amount)}</b></td>
                <td><Pill tone="neutral">{c.status || '—'}</Pill></td><td><StatusPill value={c.paid_status} /></td>
                <td className="muted">{c.pincode || '—'}</td><td className="muted">{c.disposition || '—'}</td>
              </tr>)}</tbody></table></div>
            {shownCases.length > limit && <div className="row" style={{ justifyContent: 'center', padding: 12 }}>
              <span className="faint">Showing {num(limit)} of {num(shownCases.length)}</span><button className="btn sm" onClick={() => setLimit(l => l + 500)}>Show 500 more</button>
              <button className="btn sm ghost" onClick={() => setLimit(shownCases.length)}>Show all</button></div>}
          </>}
        </Card>
      </>}

      {segEdit && <Modal open onClose={() => !busy && setSegEdit(false)} title="Change segment" sub={`${bank} · ${product}${segment ? ' · ' + segment : ''}${branchF ? ' · ' + branchF : ''}${cardPeriod ? ' · ' + monthLbl(cardPeriod) : ''}`}
        footer={<><button className="btn" disabled={busy} onClick={() => setSegEdit(false)}>Cancel</button><div className="grow" /><button className="btn primary" disabled={busy || !segNew || segNew === segment} onClick={saveSegment}>{busy ? 'Applying…' : 'Apply'}</button></>}>
        <Field label="New segment"><select className="select" value={segNew} onChange={e => setSegNew(e.target.value)}>
          {(segment && !['Credit Card', 'PL/BL', 'AUTO LOANS'].includes(segment) ? [segment, 'Credit Card', 'PL/BL', 'AUTO LOANS'] : ['Credit Card', 'PL/BL', 'AUTO LOANS']).map(s => <option key={s}>{s}</option>)}</select></Field>
        <div className="faint" style={{ fontSize: 12 }}>Only the segment changes for this portfolio — payments, allocation, visits, calls and history stay as they are.</div>
      </Modal>}
      {delOpen && <Modal open onClose={() => setDelOpen(false)} title={`Remove ${pickedIds.length} case${pickedIds.length === 1 ? '' : 's'}?`}
        footer={<><button className="btn" onClick={() => setDelOpen(false)}>Cancel</button><div className="grow" /><button className="btn danger-solid" disabled={busy} onClick={doRemove}><Trash2 />{busy ? 'Removing…' : 'Remove selected'}</button></>}>
        <p style={{ marginTop: 0 }}>They move to <b>Removed cases</b> and drop out of every list, MIS, dashboard and performance calc. You can restore them anytime.</p>
        <Field label="Reason (optional)"><input className="input" value={delReason} onChange={e => setDelReason(e.target.value)} placeholder="e.g. duplicate / wrong upload" /></Field>
      </Modal>}
      {resetOpen && <Modal open onClose={() => setResetOpen(false)} title="Reset all cases"
        footer={<><button className="btn" onClick={() => setResetOpen(false)}>Cancel</button><div className="grow" /><button className="btn danger-solid" disabled={busy || resetTxt.trim().toUpperCase() !== 'DELETE'} onClick={doReset}>{busy ? 'Deleting…' : 'Delete all cases'}</button></>}>
        <p style={{ marginTop: 0 }}>This permanently deletes <b>all cases, visits and call logs</b> so you can upload a fresh loading file. Staff, leave, devices and settings are kept. <b style={{ color: 'var(--bad)' }}>This cannot be undone.</b></p>
        <Field label="Type DELETE to confirm"><input className="input" value={resetTxt} onChange={e => setResetTxt(e.target.value)} placeholder="DELETE" autoFocus /></Field>
      </Modal>}
    </>
  );
}

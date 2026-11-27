import React, { useEffect, useMemo, useRef, useState } from 'react';
import { Area, AreaChart, Bar, BarChart, CartesianGrid, Cell, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import {
  BarChart3, CheckCircle2, Coins, Download, Eye, FileSpreadsheet, FolderOpen, Gauge, Handshake, Landmark, LineChart, MapPin,
  Percent, Phone, Printer, Repeat, Target, TrendingUp, UserX, Users, Users2, Wallet, X, Compass, Layers, Table2,
} from 'lucide-react';
import { api, download } from '../lib/api.js';
import { useAuth } from '../lib/auth.jsx';
import { inr, inrShort, num, cx } from '../lib/format.js';
import { Card, Kpi, Empty, Skeleton, useLoad } from '../components/ui.jsx';
import { ModuleHead, Chips, Modal, MultiSelect, Bar as PBar, usePanel, useLive, ChartTip, chartColor, cssVar, printTables } from './kit.jsx';
import { Trends } from './MyPerformance.jsx';
import { useClassic } from '../lib/classic.jsx';

const MB = [['current', 'This month'], ['next', 'Next month'], ['last', 'Last month'], ['', 'All months']];
const isPct = (k) => /(_pct$|^pct$)/.test(k);
const isMoney = (k) => /(enr|amount|pending|collected|cash|coll|leakage|target_enr|achieved_enr|gap|^norm$|^stab$|pending_norm|pending_stab)/.test(k);
const fmtCell = (k, v) => {
  if (v === null || v === undefined || v === '') return '—';
  if (isPct(k)) return v + '%';
  if (typeof v === 'boolean') return v ? 'Yes' : '—';
  if (isMoney(k) && typeof v === 'number') return inr(v);
  return v;
};
const GROUP = [['label', 'Name'], ['count', 'Count'], ['paid', 'Paid'], ['unpaid', 'Unpaid'], ['enr', 'ENR'], ['paid_enr', 'Paid ENR'], ['pct', 'Paid %'], ['norm_pct', 'NORM %'], ['stab_pct', 'STAB %'], ['rollback_pct', 'RB %'], ['rollback_collected', 'RB ₹'], ['amount', 'Cash'], ['partial_payments', 'Partial'], ['actual_collection', 'Actual coll'], ['visited', 'Vis'], ['not_visited', 'Not vis']];
const AREA = [['label', 'Area'], ['count', 'Count'], ['paid', 'Paid'], ['unpaid', 'Unpaid'], ['enr', 'ENR'], ['pending', 'Pending'], ['amount', 'Collected'], ['recovery_pct', 'Recovery %'], ['pct', 'Paid %'], ['norm_pct', 'NORM %'], ['stab_pct', 'STAB %']];
const CASES = [['customer', 'Customer'], ['account', 'Account'], ['pending', 'Pending'], ['enr', 'ENR'], ['propensity', 'Score'], ['fos', 'FOS'], ['caller', 'Caller']];
const NS_CASES = [['customer', 'Customer'], ['account', 'Account'], ['norm', 'NORM'], ['pending_norm', 'Pending NORM'], ['stab', 'STAB'], ['pending_stab', 'Pending STAB'], ['pending', 'Pending'], ['fos', 'FOS'], ['caller', 'Caller']];
const TABLES = [
  ['by_fos', GROUP], ['by_caller', GROUP], ['by_area', AREA], ['by_team_lead', GROUP], ['by_cat', GROUP], ['by_dpd', GROUP],
  ['aging', [['label', 'Recency'], ['count', 'Count'], ['pending', 'Pending']]],
  ['untouched_table', CASES], ['top_by_norm', NS_CASES], ['top_by_stab', NS_CASES], ['top_pending', CASES], ['priority', CASES],
  ['obstacles', [['caller', 'Caller'], ['total', 'Total'], ['obstacles', 'Obstacles'], ['rate_pct', 'Rate %']]],
  ['productivity', [['emp', 'Employee'], ['calls_today', 'Calls'], ['visits_today', 'Visits'], ['idle', 'Idle']]],
  ['field_efficiency', [['fos', 'FOS'], ['visits', 'Visits'], ['distance_km', 'Dist km'], ['off_location', 'Off-loc'], ['collected', 'Collected']]],
  ['trend', [['date', 'Date'], ['collected', 'Collected']]],
];
const LB_COLS = [['emp', 'Employee'], ['count', 'Count'], ['unpaid', 'Unpaid'], ['paid', 'Paid'], ['enr', 'ENR'], ['target_pct', 'Target %'], ['target_enr', 'Target ENR'], ['achieved_pct', 'Achieved %'], ['achieved_enr', 'Achieved ENR'], ['gap_enr', 'Gap ENR'], ['to_target_pct', 'To target %'], ['pending_visit', 'Pend visit'], ['cash_coll', 'Cash coll']];
const CALLER_COLS = LB_COLS.filter(c => c[0] !== 'pending_visit');
const STATUS_TONE = { green: 'good', amber: 'warn', red: 'bad' };
const pctTone = (v) => (v >= 60 ? 'good' : v >= 30 ? 'warn' : 'bad');

function ChartCard({ title, children, i }) {
  return <Card title={title} className="rise" style={{ '--i': i }}><div style={{ height: 220 }}><ResponsiveContainer>{children}</ResponsiveContainer></div></Card>;
}
const axis = { tick: { fill: 'var(--text-3)', fontSize: 11 }, axisLine: false, tickLine: false };

function Donut({ data, fmt }) {
  const raw = data.reduce((s, d) => s + (Number(d.value) || 0), 0);
  const tot = raw || 1;
  if (!raw) return <div className="donut-wrap"><Empty title="Nothing to show yet" /></div>;
  return (
    <div className="donut-wrap">
      <div style={{ width: 170, height: 170 }}><ResponsiveContainer><PieChart>
        <Pie data={data} dataKey="value" nameKey="name" innerRadius={52} outerRadius={78} paddingAngle={2} stroke="none" isAnimationActive={false}>
          {data.map((d, i) => <Cell key={i} fill={d.color} />)}
        </Pie><Tooltip content={<ChartTip fmt={fmt} />} /></PieChart></ResponsiveContainer></div>
      <div className="donut-legend">{data.map(d => <div key={d.name}><i style={{ background: d.color }} /><span className="grow">{d.name}</span><b>{fmt ? fmt(d.value) : num(d.value)}</b><span className="faint">{Math.round((Number(d.value) || 0) * 100 / tot)}%</span></div>)}</div>
    </div>
  );
}

/** One MIS table with download + print, heat-coloured % cells and clickable people. */
function MisTable({ tk, cols, rows, title, onDl, onPerson, i }) {
  return (
    <Card title={title} sub={`${rows.length} rows`} pad={false} className="rise mis-card" style={{ '--i': i }}
      actions={<div className="row" style={{ gap: 6 }}>
        <button className="btn sm ghost" title="Download Excel" onClick={() => onDl(tk)}><Download /></button>
        <button className="btn sm ghost" title="Print" onClick={() => printTables(title, [[title, cols.map(c => c[1]), rows.map(r => cols.map(c => fmtCell(c[0], r[c[0]])))]])}><Printer /></button></div>}>
      <span id={'mis-' + tk} />
      {!rows.length ? <div className="faint" style={{ padding: 16 }}>No data.</div> :
        <div className="table-wrap" style={{ maxHeight: 420 }}><table className="t mis-t">
          <thead><tr>{cols.map(c => <th key={c[0]} className={typeof (rows[0] || {})[c[0]] === 'number' ? 'r' : ''}>{c[1]}</th>)}</tr></thead>
          <tbody>{rows.map((r, ri) => <tr key={ri}>{cols.map(c => {
            const v = r[c[0]]; const person = c[0] === 'label' && r.emp_id && (tk === 'by_fos' || tk === 'by_caller');
            return <td key={c[0]} className={typeof v === 'number' ? 'r num' : ''}>
              {isPct(c[0]) && typeof v === 'number' ? <span className={'heat h-' + pctTone(v)}>{v}%</span>
                : person ? <button className="link-btn" onClick={() => onPerson(r.emp_id, tk === 'by_fos' ? 'fos' : 'caller', v)}>{v}</button> : fmtCell(c[0], v)}</td>;
          })}</tr>)}</tbody></table></div>}
    </Card>
  );
}

function Leaderboard({ title, rows, cols, fos, onDl, onPerson, i }) {
  return (
    <Card title={title} sub={`${rows.length} people`} pad={false} className="rise" style={{ '--i': i }}
      actions={<div className="row" style={{ gap: 6 }}>
        {onDl && <button className="btn sm ghost" title="Download Excel" onClick={() => onDl('leaderboard')}><Download /></button>}
        <button className="btn sm ghost" title="Print" onClick={() => printTables(title, [[title, ['#', ...cols.map(c => c[1])], rows.map((r, j) => [j + 1, ...cols.map(c => fmtCell(c[0], r[c[0]]))])]])}><Printer /></button></div>}>
      <span id="mis-leaderboard" />
      {!rows.length ? <div className="faint" style={{ padding: 16 }}>No data.</div> :
        <div className="table-wrap" style={{ maxHeight: 480 }}><table className="t">
          <thead><tr><th>#</th><th>{fos ? 'Employee' : 'Caller'}</th><th className="r">Cases</th><th className="r">Paid</th><th className="r">ENR</th><th className="r">Target</th><th style={{ minWidth: 170 }}>Achieved</th><th className="r">Gap</th><th className="r">To target</th>{fos && <th className="r">Pend. visit</th>}<th className="r">Cash</th></tr></thead>
          <tbody>{rows.map((r, j) => <tr key={j}>
            <td>{j < 3 ? <span className={'medal m' + (j + 1)}>{j + 1}</span> : j + 1}</td>
            <td><div className="row" style={{ gap: 8 }}><span className={'sdot s-' + (STATUS_TONE[r.status] || 'none')} />
              {r.emp_id ? <button className="link-btn" onClick={() => onPerson(r.emp_id, fos ? 'fos' : 'caller', r.emp)}>{r.emp}</button> : <b>{r.emp}</b>}</div></td>
            <td className="r">{num(r.count)}<div className="cell-sub">{num(r.unpaid)} open</div></td>
            <td className="r" style={{ color: 'var(--good)' }}>{num(r.paid)}</td>
            <td className="r">{inr(r.enr)}</td>
            <td className="r">{r.target_pct}%<div className="cell-sub">{inr(r.target_enr)}</div></td>
            <td><div className="row" style={{ gap: 8 }}><PBar pct={r.target_pct ? (r.achieved_pct / r.target_pct) * 100 : r.achieved_pct} h={6} tone={r.to_target_pct >= 100 ? 'good' : 'accent'} />
              <b className="num" style={{ minWidth: 42 }}>{r.achieved_pct}%</b></div><div className="cell-sub">{inr(r.achieved_enr)}</div></td>
            <td className="r" style={{ color: 'var(--bad)' }}>{inr(r.gap_enr)}</td>
            <td className="r"><b>{r.to_target_pct}%</b></td>
            {fos && <td className="r" style={{ color: 'var(--warn)' }}>{num(r.pending_visit)}</td>}
            <td className="r">{inr(r.cash_coll)}</td>
          </tr>)}</tbody></table></div>}
    </Card>
  );
}

/** MIS — per-portfolio analytics: KPIs, projection, charts, leaderboards and 16 drill tables. */
export default function Mis() {
  const { user } = useAuth();
  const panel = usePanel();
  const classic = useClassic();
  const canTarget = ['admin', 'manager', 'backend', 'headoffice'].includes(user.role);
  const isTL = user.role === 'teamlead';
  const [mb, setMb] = useState('current');
  const autoMonth = useRef(false);
  const [sel, setSel] = useState(null);
  const [area, setArea] = useState('');
  const [cycles, setCycles] = useState([]); const [fosSel, setFosSel] = useState([]); const [callerSel, setCallerSel] = useState([]); const [tlSel, setTlSel] = useState([]);
  const [branchSel, setBranchSel] = useState([]);
  const [peer, setPeer] = useState(null);
  const [emp, setEmp] = useState('');
  const [full, setFull] = useState(false);
  const [tab, setTab] = useState('overview');
  const viewingPeer = isTL && peer && peer !== user.id;

  const prodsL = useLoad(() => api('/api/cases/product-summary' + (mb ? '?month_bucket=' + mb : '')).catch(() => []), [mb]);
  const prods = useMemo(() => {
    const seen = {}, list = [];
    (prodsL.data || []).forEach(r => { const k = r.bank + '||' + r.product; if (!seen[k] && r.product !== '—') { seen[k] = 1; list.push({ bank: r.bank, product: r.product, branch_split: !!r.branch_split, branches: (r.branches || []).map(b => b.branch) }); } });
    return list;
  }, [prodsL.data]);
  useEffect(() => {
    if (prodsL.loading || !prodsL.data) return;
    if (!prods.length && !autoMonth.current) { const nxt = mb === 'current' ? 'next' : mb === 'next' ? 'last' : null; if (nxt) { setMb(nxt); return; } }
    autoMonth.current = true;
    setSel(cur => (cur && prods.find(p => p.bank === cur.bank && p.product === cur.product)) || prods[0] || null);
  }, [prods, prodsL.loading]); // eslint-disable-line

  const bq = sel ? `bank=${encodeURIComponent(sel.bank)}&product=${encodeURIComponent(sel.product)}` : '';
  const { data: areas } = useLoad(() => (sel ? api('/api/cases/areas?' + bq).catch(() => []) : Promise.resolve([])), [bq]);
  const { data: tlOpts } = useLoad(() => (sel && isTL ? api('/api/mis/tl-options?' + bq).catch(() => []) : Promise.resolve([])), [bq]);
  const { data: fo } = useLoad(() => (sel ? api('/api/cases/filter-options?' + bq + (viewingPeer ? '&peer_lead=' + peer : '')).catch(() => ({})) : Promise.resolve({})), [bq, peer]);
  const { data: ov } = useLoad(() => api('/api/mis/overview').catch(() => null), []);
  useEffect(() => { setArea(''); setCycles([]); setFosSel([]); setCallerSel([]); setTlSel([]); setBranchSel([]); setEmp(''); setPeer(isTL ? user.id : null); }, [bq]); // eslint-disable-line
  useEffect(() => { setCycles([]); setFosSel([]); setCallerSel([]); }, [peer]);

  const fq = (cycles.length ? `&cycles=${cycles.join(',')}` : '') + (fosSel.length ? `&fos_ids=${fosSel.join(',')}` : '') + (callerSel.length ? `&caller_ids=${callerSel.join(',')}` : '')
    + (!isTL && tlSel.length ? `&team_leads=${tlSel.map(encodeURIComponent).join(',')}` : '') + (viewingPeer ? `&peer_lead=${peer}` : '');
  const mbq = (mb ? `&month_bucket=${mb}` : '') + (area ? `&area=${encodeURIComponent(area)}` : '') + (branchSel.length ? `&branch=${branchSel.map(encodeURIComponent).join(',')}` : '') + fq;
  const { data: d, loading, error, reload } = useLoad(() => (sel ? api(`/api/mis?${bq}${mbq}`) : Promise.resolve(null)), [bq, mbq]);
  useLive(reload);

  const dl = (tables) => download(`/api/mis/download?${bq}&tables=${tables}${mbq}`, `MIS_${sel.bank}_${sel.product}${branchSel.length ? '_' + branchSel.join('-') : ''}_${mb || 'all'}.xlsx`);
  const dlAll = () => d && dl(Object.keys(d.table_names || {}).join(','));
  const person = (id, role, name) => classic.api && classic.api.openPerf && classic.api.openPerf(id, role, name);
  const saveTarget = (e) => { const v = parseFloat(e.target.value) || 0; api('/api/mis/target', { method: 'PUT', body: { bank: sel.bank, product: sel.product, target_pct: v } }).then(reload).catch(() => {}); };
  const nFilters = cycles.length + fosSel.length + callerSel.length + (isTL ? 0 : tlSel.length);

  if (prodsL.loading && !prods.length) return <><ModuleHead icon={LineChart} title="MIS" full="mis" /><Skeleton h={300} /></>;
  if (!prods.length) return (
    <>
      <ModuleHead icon={LineChart} title="MIS" sub="Per-portfolio recovery analytics" full="mis" />
      <div className="card toolbar-card"><Chips value={mb} onChange={(v) => { autoMonth.current = true; setMb(v); }} options={MB} /></div>
      <Empty icon={LineChart} title="No portfolios with cases for this month">Try another month above.</Empty>
    </>
  );

  const o = d && d.overall; const proj = d && d.projection; const fn = d && d.funnel; const st = d && d.settlement;
  const lb = d ? (emp ? d.leaderboard.filter(x => x.emp === emp) : d.leaderboard) : [];
  const base = (d && d.base_label) || 'ENR';
  const trend = d ? (d.trend || []).map(t => ({ label: String(t.date).slice(5), collected: t.collected })) : [];
  const C = (i) => chartColor(i);
  const tables = d ? TABLES.map(([tk, cols]) => [tk, cols, (d.table_names && d.table_names[tk]) || tk, d[tk] || []]) : [];
  const SECTIONS = [['overview', 'Overview', Gauge], ['people', 'Leaderboards', Users], ['tables', 'All tables', Table2]];

  // KPI tiles + achievement — reused for a Field TL's portfolio-wide summary and their group MIS.
  const kpiSection = (dd, trendTitle, trendSub) => (<>
          <div className="grid g-kpi" style={{ marginBottom: 14 }}>
            <Kpi icon={FolderOpen} label="Total cases" i={1} value={num(dd.overall.count)} sub={`${num(dd.overall.paid)} paid · ${num(dd.overall.unpaid)} unpaid`} />
            <Kpi icon={Landmark} label={'Total ' + (dd.base_label || 'ENR')} i={2} value={dd.overall.enr || 0} format={inrShort} sub={'POS ' + inrShort(dd.overall.pos)} tone="info" />
            <Kpi icon={CheckCircle2} label={'Paid ' + (dd.base_label || 'ENR')} i={3} value={dd.overall.paid_enr || 0} format={inrShort} sub={`${dd.overall.pct}% achieved`} tone="good" />
            <Kpi icon={Wallet} label="Actual collection" i={4} value={dd.overall.actual_collection != null ? dd.overall.actual_collection : (Number(dd.overall.amount || 0) + Number(dd.overall.partial_payments || 0))} format={inrShort}
              sub={`${inrShort(dd.overall.amount)} cash + ${inrShort(dd.overall.partial_payments)} partial`} tone="warn" />
          </div>
          <div className="mini-kpis rise">
            {[['Collected MTD', inr(dd.projection.collected_mtd), null, TrendingUp], ['Projected month-end', inr(dd.projection.projected_month_end), `${dd.projection.projected_pct}% of target`, Target],
              ['PTP kept', `${dd.funnel.ptp_kept}/${dd.funnel.ptp_total}`, `${dd.funnel.ptp_kept_pct}% · ${dd.funnel.ptp_broken} broken`, Handshake],
              ['Untouched', num(dd.funnel.untouched), inr(dd.funnel.untouched_pending) + ' pending', UserX], ['Realization', dd.settlement.realization_pct + '%', 'leak ' + inr(dd.settlement.leakage), Percent],
              ['Conversion', dd.funnel.conversion_pct + '%', `${dd.funnel.paid_of_contacted}/${dd.funnel.contacted} contacted`, Coins],
              ...(dd.settlement.rollback_target > 0 ? [['Rollback collected', inr(dd.settlement.rollback_collected), `${dd.settlement.rollback_pct}% · ${dd.settlement.rollback_count} cases`, Layers]] : []),
            ].map(([l, v, s, I]) => <div key={l} className="mini-kpi"><I /><div><div className="faint">{l}</div><b className="num">{v}</b>{s && <div className="cell-sub">{s}</div>}</div></div>)}
          </div>

          {dd.trends && <Card title={trendTitle} sub={trendSub} className="rise" style={{ margin: '14px 0' }}><Trends trends={dd.trends} /></Card>}
  </>);
  return (
    <>
      <ModuleHead icon={LineChart} title="MIS" sub={sel ? `${sel.bank} · ${sel.product}${branchSel.length ? ' · ' + branchSel.join(', ') : ''}${area ? ' · ' + area : ''}` : ''} full="mis">
        {sel && !viewingPeer && <button className="btn" onClick={() => panel('cycle', { bank: sel.bank, product: sel.product, monthB: mb })}><Repeat />Cycle-wise</button>}
        {sel && !viewingPeer && <button className="btn" onClick={() => panel('pivot', { bank: sel.bank, product: sel.product, monthB: mb, branch: branchSel.join(',') })}><FileSpreadsheet />MIS Pivot</button>}
        {d && <button className="btn" onClick={() => setFull(true)}><Eye />Full sheet</button>}
        {d && <button className="btn primary" onClick={dlAll}><Download />Download all</button>}
        {user.role === 'teamfollower' && <button className="btn" onClick={() => download('/api/team-follow/me/report.xlsx?month_bucket=' + (mb || 'all'), 'FieldTL_group_report_' + (mb || 'all') + '.xlsx')} title="Daily · monthly · per person · per portfolio"><FileSpreadsheet />Group report</button>}
      </ModuleHead>

      <div className="card toolbar-card rise">
        <div className="row wrap" style={{ gap: 10 }}>
          <select className="select" value={sel ? sel.bank : ''} onChange={e => { const f = prods.find(p => p.bank === e.target.value); setSel(f || null); }}>
            {[...new Set(prods.map(p => p.bank))].map(b => <option key={b}>{b}</option>)}</select>
          <select className="select" value={sel ? sel.product : ''} onChange={e => setSel(prods.find(p => p.bank === sel.bank && p.product === e.target.value) || sel)}>
            {prods.filter(p => sel && p.bank === sel.bank).map(p => <option key={p.product} value={p.product}>{p.product}{p.branch_split ? ' · by location' : ''}</option>)}</select>
          <Chips value={mb} onChange={setMb} options={MB} />
          <div className="grow" />
          {(areas || []).length > 0 && <select className="select" value={area} onChange={e => setArea(e.target.value)}><option value="">All areas</option>{areas.map(a => <option key={a}>{a}</option>)}</select>}
          {isTL && (tlOpts || []).length > 0 && <select className="select" value={peer || user.id} onChange={e => setPeer(Number(e.target.value))} title="Another lead’s MIS opens read-only">
            {tlOpts.map(t => <option key={t.id} value={t.id}>{t.name}{t.emp_code ? ` (${t.emp_code})` : ''}{t.is_me ? ' — you' : ''}</option>)}</select>}
        </div>
        <div className="chips">
          <span className="chips-l">Filter</span>
          {sel && sel.branch_split && sel.branches.length > 0 && <MultiSelect label="Location" icon={MapPin} selected={branchSel} onChange={setBranchSel} options={sel.branches.map(b => ({ value: b, label: b }))} />}
          <MultiSelect label="Cycle" icon={Repeat} width={160} selected={cycles} onChange={setCycles} options={((fo && fo.cycles) || []).map(c => ({ value: c, label: 'Cycle ' + c }))} />
          <MultiSelect label="FOS" icon={Compass} selected={fosSel} onChange={setFosSel} options={((fo && fo.fos) || []).map(f => ({ value: f.id, label: f.name + (f.code ? ` (${f.code})` : '') }))} />
          <MultiSelect label="Caller" icon={Phone} selected={callerSel} onChange={setCallerSel} options={((fo && fo.callers) || []).map(f => ({ value: f.id, label: f.name + (f.code ? ` (${f.code})` : '') }))} />
          {!isTL && ((fo && fo.team_leads) || []).length > 0 && <MultiSelect label="Team Lead" icon={Users2} selected={tlSel} onChange={setTlSel} options={fo.team_leads.map(t => ({ value: t, label: t }))} />}
          {nFilters > 0 && <button className="btn sm ghost" onClick={() => { setCycles([]); setFosSel([]); setCallerSel([]); setTlSel([]); }}><X />Clear</button>}
        </div>
      </div>

      {viewingPeer && d && d.viewing_lead && <div className="card note-card rise"><Eye /><div>Read-only — <b>{d.viewing_lead.name}</b>’s MIS on {sel.bank} · {sel.product}. Switch back to yourself in the team-lead dropdown.</div></div>}
      {d && d.base_label === 'TOS' && <div className="faint" style={{ fontSize: 12, margin: '0 2px 12px' }}>PL/BL recovery base: <b>TOS</b> · % = paid TOS ÷ total TOS{d.segment ? ` · ${d.segment}` : ''}</div>}
      {error && <div className="card" style={{ padding: 16, color: 'var(--bad)' }}>{error}</div>}
      {loading && !d && <div className="grid g-kpi"><Skeleton h={120} /><Skeleton h={120} /><Skeleton h={120} /><Skeleton h={120} /></div>}

      {d && <>
        <div className="seg-tabs rise">{SECTIONS.map(([v, l, I]) => <button key={v} className={tab === v ? 'on' : ''} onClick={() => setTab(v)}><I /><span>{l}</span></button>)}</div>

        {tab === 'overview' && <>
          {d.portfolio_overall && <>
            <div className="sec-t">Portfolio overall — {sel.bank} · {sel.product} <span className="faint" style={{ fontWeight: 400, fontSize: 12 }}>· all teams · summary only</span></div>
            {kpiSection(d.portfolio_overall, 'Portfolio achievement — cash collected', `${sel.bank} · ${sel.product} · all teams`)}
            <div className="sec-t" style={{ marginTop: 18 }}>Your group — {d.group_size} {d.group_size === 1 ? 'person' : 'people'} <span className="faint" style={{ fontWeight: 400, fontSize: 12 }}>· everything below is only the FOS / callers under you</span></div>
          </>}
          {kpiSection(d, 'Achievement — cash collected', `${sel.bank} · ${sel.product}${d.portfolio_overall ? ' · your group' : ''}`)}

          <Card className="rise target-card" style={{ marginBottom: 14 }}>
            <div className="row wrap" style={{ gap: 12 }}>
              <span className="mod-ic sm"><Target /></span>
              <div className="grow"><b>Target %</b><div className="faint" style={{ fontSize: 12.5 }}>One goal for every FOS & caller on {sel.bank} · {sel.product}.</div></div>
              {canTarget ? <input className="input" style={{ width: 96, textAlign: 'center', fontWeight: 700 }} type="number" min="0" max="100" key={d.product_target}
                defaultValue={d.product_target || ''} placeholder="e.g. 85" onBlur={saveTarget} onKeyDown={e => { if (e.key === 'Enter') e.target.blur(); }} />
                : <span className="pill accent" style={{ fontSize: 14 }}>{d.product_target || 0}%</span>}
            </div>
          </Card>

          <div className="chart-grid">
            <ChartCard title="Collection trend · 30 days" i={1}>
              <AreaChart data={trend} margin={{ left: 0, right: 8, top: 6 }}>
                <defs><linearGradient id="misg" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor={C(0)} stopOpacity={.42} /><stop offset="100%" stopColor={C(0)} stopOpacity={0} /></linearGradient></defs>
                <CartesianGrid stroke="var(--line)" vertical={false} /><XAxis dataKey="label" {...axis} interval="preserveStartEnd" /><YAxis {...axis} tickFormatter={inrShort} width={58} />
                <Tooltip content={<ChartTip fmt={inr} />} /><Area isAnimationActive={false} type="monotone" dataKey="collected" name="Collected" stroke={C(0)} strokeWidth={2.5} fill="url(#misg)" />
              </AreaChart>
            </ChartCard>
            <ChartCard title="Top FOS — achieved ENR" i={2}>
              <BarChart data={d.leaderboard.slice(0, 10).map(r => ({ name: (r.emp || '').split('/')[0], v: r.achieved_enr }))} margin={{ left: 0, right: 8 }}>
                <CartesianGrid stroke="var(--line)" vertical={false} /><XAxis dataKey="name" {...axis} interval={0} angle={-25} textAnchor="end" height={50} /><YAxis {...axis} tickFormatter={inrShort} width={58} />
                <Tooltip content={<ChartTip fmt={inr} />} cursor={{ fill: 'var(--bg-hover)' }} /><Bar isAnimationActive={false} dataKey="v" name="Achieved" radius={[6, 6, 0, 0]} fill={C(0)} />
              </BarChart>
            </ChartCard>
            <Card title="Settlement — STAB vs NORM ENR" className="rise" style={{ '--i': 3 }}>
              <Donut fmt={inr} data={[{ name: 'STAB', value: st.stab_enr, color: cssVar('--warn') }, { name: 'NORM', value: st.norm_enr, color: cssVar('--good') }]} /></Card>
            <Card title="PTP kept vs broken" className="rise" style={{ '--i': 4 }}>
              <Donut data={[{ name: 'Kept', value: fn.ptp_kept, color: cssVar('--good') }, { name: 'Broken', value: fn.ptp_broken, color: cssVar('--bad') },
                { name: 'Pending', value: Math.max(fn.ptp_total - fn.ptp_kept - fn.ptp_broken, 0), color: cssVar('--text-3') }]} /></Card>
            <ChartCard title="Area-wise achieved %" i={5}>
              <BarChart data={(d.by_area || []).map(r => ({ name: r.label, v: r.pct }))} margin={{ left: 0, right: 8 }}>
                <CartesianGrid stroke="var(--line)" vertical={false} /><XAxis dataKey="name" {...axis} /><YAxis {...axis} unit="%" width={44} />
                <Tooltip content={<ChartTip fmt={v => v + '%'} />} cursor={{ fill: 'var(--bg-hover)' }} /><Bar isAnimationActive={false} dataKey="v" name="Achieved" radius={[6, 6, 0, 0]} fill={C(1)} />
              </BarChart>
            </ChartCard>
            <ChartCard title="Recovery % by bucket (DPD)" i={6}>
              <BarChart data={(d.by_dpd || []).map(r => ({ name: r.label, v: r.pct }))} margin={{ left: 0, right: 8 }}>
                <CartesianGrid stroke="var(--line)" vertical={false} /><XAxis dataKey="name" {...axis} /><YAxis {...axis} unit="%" width={44} />
                <Tooltip content={<ChartTip fmt={v => v + '%'} />} cursor={{ fill: 'var(--bg-hover)' }} /><Bar isAnimationActive={false} dataKey="v" name="Recovery" radius={[6, 6, 0, 0]} fill={C(2)} />
              </BarChart>
            </ChartCard>
            <ChartCard title="Contact aging — pending ₹" i={7}>
              <BarChart data={(d.aging || []).map(r => ({ name: r.label, v: r.pending }))} margin={{ left: 0, right: 8 }}>
                <CartesianGrid stroke="var(--line)" vertical={false} /><XAxis dataKey="name" {...axis} /><YAxis {...axis} tickFormatter={inrShort} width={58} />
                <Tooltip content={<ChartTip fmt={inr} />} cursor={{ fill: 'var(--bg-hover)' }} /><Bar isAnimationActive={false} dataKey="v" name="Pending" radius={[6, 6, 0, 0]} fill={cssVar('--warn')} />
              </BarChart>
            </ChartCard>
            {ov && <ChartCard title="Recovery % across products" i={8}>
              <BarChart layout="vertical" data={(ov.by_product || []).map(r => ({ name: r.label, v: r.pct }))} margin={{ left: 10, right: 12 }}>
                <CartesianGrid stroke="var(--line)" horizontal={false} /><XAxis type="number" {...axis} unit="%" /><YAxis type="category" dataKey="name" {...axis} width={110} />
                <Tooltip content={<ChartTip fmt={v => v + '%'} />} cursor={{ fill: 'var(--bg-hover)' }} /><Bar isAnimationActive={false} dataKey="v" name="Recovery" radius={[0, 6, 6, 0]} fill={cssVar('--good')} />
              </BarChart>
            </ChartCard>}
          </div>
        </>}

        {tab === 'people' && <>
          <div className="card toolbar-card rise"><div className="row wrap" style={{ gap: 10 }}>
            <select className="select" value={emp} onChange={e => setEmp(e.target.value)}><option value="">All employees</option>{(d.by_fos || []).map((r, i) => <option key={i} value={r.label}>{r.label}</option>)}</select>
            <div className="grow" /><span className="faint" style={{ fontSize: 12 }}>Target {d.product_target || 0}% · click a name for their full performance</span>
          </div></div>
          <Leaderboard title="FOS performance & leaderboard" rows={lb} cols={LB_COLS} fos onDl={dl} onPerson={person} i={1} />
          {d.caller_leaderboard && <div style={{ marginTop: 14 }}><Leaderboard title="Caller performance & leaderboard" rows={d.caller_leaderboard} cols={CALLER_COLS} onPerson={person} i={2} /></div>}
        </>}

        {tab === 'tables' && <>
          <div className="card toolbar-card rise"><div className="chips"><span className="chips-l">Jump to</span>
            {tables.map(([tk, , title]) => <button key={tk} className="chip" onClick={() => { const el = document.getElementById('mis-' + tk); if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' }); }}>{title}</button>)}</div></div>
          <div className="col" style={{ gap: 14 }}>{tables.map(([tk, cols, title, rows], i) => <MisTable key={tk} tk={tk} cols={cols} rows={rows} title={title} onDl={dl} onPerson={person} i={Math.min(i, 8)} />)}</div>
        </>}
      </>}

      {full && d && <Modal open onClose={() => setFull(false)} width={1400} title={`Full MIS sheet — ${sel.bank} · ${sel.product}`}
        footer={<><button className="btn" onClick={() => setFull(false)}>Close</button><div className="grow" />
          <button className="btn" onClick={() => printTables(`MIS — ${sel.bank} · ${sel.product}`, [['Employee performance & leaderboard', LB_COLS, lb], ...tables.map(([, cols, title, rows]) => [title, cols, rows])]
            .map(([t, cols, rows]) => [t, cols.map(c => c[1]), rows.map(r => cols.map(c => fmtCell(c[0], r[c[0]])))]))}><Printer />Print</button>
          <button className="btn primary" onClick={dlAll}><Download />Excel</button></>}>
        {[['Employee performance & leaderboard', LB_COLS, lb], ...tables.map(([, cols, title, rows]) => [title, cols, rows])].map(([t, cols, rows], ti) => (
          <div key={ti} style={{ marginBottom: 16 }}>
            <div className="sec-t" style={{ margin: '4px 0 8px' }}>{t}</div>
            {!rows.length ? <div className="faint">No data.</div> : <div className="table-wrap"><table className="t mis-t">
              <thead><tr>{cols.map(c => <th key={c[0]}>{c[1]}</th>)}</tr></thead>
              <tbody>{rows.map((r, i) => <tr key={i}>{cols.map(c => { const v = r[c[0]]; return <td key={c[0]} className={typeof v === 'number' ? 'r num' : ''}>
                {isPct(c[0]) && typeof v === 'number' ? <span className={'heat h-' + pctTone(v)}>{v}%</span> : fmtCell(c[0], v)}</td>; })}</tr>)}</tbody></table></div>}
          </div>))}
      </Modal>}
    </>
  );
}

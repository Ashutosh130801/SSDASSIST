import React, { useMemo, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { ChevronDown, FolderKanban, Map as MapIcon, Printer, Wallet, Footprints, CheckCircle2, ListChecks } from 'lucide-react';
import { api, qs } from '../lib/api.js';
import { inr, inrShort, num, cx } from '../lib/format.js';
import { Kpi, Empty, Skeleton, useLoad } from '../components/ui.jsx';
import { useClassic } from '../lib/classic.jsx';
import CaseDrawer from '../pages/CaseDrawer.jsx';
import { ModuleHead, Chips, MONTHS, SearchBox, useLive, usePanel } from './kit.jsx';
import { CaseCard, Reminders, bucketRank, caseState, groupCases } from './caseKit.jsx';

const SORTS = [['', 'Grouped'], ['pending', 'Pending ↓'], ['norm', 'Pending NORM ↓'], ['stab', 'Pending STAB ↓']];

/** FOS — My Accounts: month books, bank → bucket groups, priority cards, visit / call / navigate. */
export default function MyAccounts({ mapRoute = '/m/fmap' }) {
  const [sp, setSp] = useSearchParams();
  const nav = useNavigate();
  const classic = useClassic();
  const panel = usePanel();
  const [mb, setMb] = useState('current');
  const [bucket, setBucket] = useState('');
  const [q, setQ] = useState('');
  const [sort, setSort] = useState('');
  const [collapsed, setCollapsed] = useState({});
  const { data, loading, reload } = useLoad(() => api('/api/cases' + qs({ month_bucket: mb })), [mb]);
  useLive(reload);
  const cases = Array.isArray(data) ? data : [];

  const match = (c) => {
    const s = q.trim().toLowerCase(); if (!s) return true;
    const d = s.replace(/\D/g, ''); const f = [c.customer_name, c.account_no, c.card_no, c.phone, c.alt_phone];
    return f.some(v => v && String(v).toLowerCase().includes(s)) || (d && f.some(v => v && String(v).replace(/\D/g, '').includes(d)));
  };
  const buckets = useMemo(() => [...new Set(cases.map(c => c.bucket || 'No bucket'))].sort((a, b) => bucketRank(a) - bucketRank(b)), [cases]);
  const shown = useMemo(() => cases.filter(c => (!bucket || (c.bucket || 'No bucket') === bucket) && match(c)), [cases, bucket, q]); // eslint-disable-line
  const groups = useMemo(() => groupCases(shown), [shown]);
  const flat = useMemo(() => {
    if (!sort) return [];
    const v = (c) => Number(sort === 'norm' ? c.remaining_to_norm : sort === 'stab' ? c.remaining_to_stab : c.pending_amount) || 0;
    return shown.slice().sort((a, b) => v(b) - v(a));
  }, [shown, sort]);

  const k = useMemo(() => cases.reduce((t, c) => {
    const st = caseState(c); t.pending += Number(c.pending_amount || 0); t[st] += 1; return t;
  }, { pending: 0, fresh: 0, touched: 0, paid: 0 }), [cases]);

  const open = (id) => setSp({ open: id });
  const visit = (c) => panel('visit', { c }).then(ok => ok && reload());
  const locked = mb === 'last';

  return (
    <>
      <ModuleHead icon={FolderKanban} title="My Accounts" sub="Your field book — worked top to bottom: untouched → visited today → paid" full="fcases">
        <button className="btn" onClick={() => nav(mapRoute)}><MapIcon />Map view</button>
        <button className="btn" disabled={!classic.api} onClick={() => classic.api && classic.api.printLiner()}><Printer />Print liner</button>
      </ModuleHead>

      <Reminders onOpen={open} />

      <div className="grid g-kpi" style={{ marginBottom: 16 }}>
        <Kpi icon={ListChecks} label="Assigned" i={1} value={num(cases.length)} sub={locked ? 'last month — view only' : 'accounts this book'} />
        <Kpi icon={Wallet} label="Pending" i={2} value={k.pending} format={inrShort} sub="across the book" tone="warn" />
        <Kpi icon={Footprints} label="Worked today" i={3} value={num(k.touched)} sub={`${num(k.fresh)} still untouched`} tone="info" />
        <Kpi icon={CheckCircle2} label="Paid" i={4} value={num(k.paid)} sub={cases.length ? Math.round(k.paid * 100 / cases.length) + '% of accounts' : '—'} tone="good" />
      </div>

      <div className="card toolbar-card rise" style={{ '--i': 5 }}>
        <div className="row wrap" style={{ gap: 10 }}>
          <Chips value={mb} onChange={setMb} options={MONTHS} />
          <SearchBox value={q} onChange={setQ} placeholder="Name, account, card or phone…" />
          <div className="grow" />
          <Chips value={sort} onChange={setSort} options={SORTS} label="Sort" />
        </div>
        <Chips value={bucket} onChange={setBucket} label="Bucket"
          options={[['', 'All', cases.length], ...buckets.map(b => [b, b, cases.filter(c => (c.bucket || 'No bucket') === b).length])]} />
      </div>

      {loading && !cases.length && <div className="ccard-grid">{[...Array(6)].map((_, i) => <Skeleton key={i} h={190} />)}</div>}
      {!loading && !shown.length && <Empty icon={FolderKanban} title={q ? `No accounts match “${q}”` : 'No accounts in this view'} />}

      {sort ? (
        <div className="ccard-grid">{flat.map((c, i) => <CaseCard key={c.id} i={i} c={c} onOpen={() => open(c.id)} onVisit={locked ? null : visit} />)}</div>
      ) : groups.map((g, gi) => (
        <section key={g.bank} className="grp-sec rise" style={{ '--i': gi + 6 }}>
          <button className="grp-h" onClick={() => setCollapsed(s => ({ ...s, [g.bank]: !s[g.bank] }))}>
            <ChevronDown className={cx('chev', collapsed[g.bank] && 'rot')} />
            <span className="grp-t">{g.bank}</span>
            <span className="muted">{num(g.count)} accounts · {inr(g.pending)} pending</span>
          </button>
          {!collapsed[g.bank] && g.buckets.map(b => (
            <div key={b.bucket} className="grp-b">
              <div className="grp-sub"><span className="pill accent">{b.bucket}</span><span className="faint">{b.cases.length} accounts · {inr(b.pending)}</span></div>
              <div className="ccard-grid">{b.cases.map((c, i) => <CaseCard key={c.id} i={i} c={c} onOpen={() => open(c.id)} onVisit={locked ? null : visit} />)}</div>
            </div>
          ))}
        </section>
      ))}

      <CaseDrawer id={Number(sp.get('open')) || null} onClose={() => setSp({})} />
    </>
  );
}

import React, { useMemo, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { AlarmClock, CalendarClock, CheckCheck, Lock, PhoneCall, RefreshCw, Wallet, CalendarPlus } from 'lucide-react';
import { api, qs } from '../lib/api.js';
import { num, fmtDate } from '../lib/format.js';
import { Kpi, Empty, Skeleton, useLoad } from '../components/ui.jsx';
import CaseDrawer from '../pages/CaseDrawer.jsx';
import { ModuleHead, Chips, SearchBox, useLive } from './kit.jsx';
import { CaseCard, Reminders, bucketRank } from './caseKit.jsx';

const SEGS = [
  ['due', 'Due now', 'due', AlarmClock], ['today', 'Contacted today', 'contacted_today', CheckCheck],
  ['upcoming', 'Upcoming', 'upcoming', CalendarClock], ['paid', 'Paid today', 'paid_today', Wallet],
  ['closed', 'Closed', 'closed', Lock], ['next', 'Next month', 'next', CalendarPlus],
];
const EMPTY = { counts: {} };

/** Tele-calling queue — segments by what needs a call now, with bank/product/status/bucket filters. */
export default function CallQueue() {
  const [sp, setSp] = useSearchParams();
  const [seg, setSeg] = useState('due');
  const [bank, setBank] = useState('');
  const [product, setProduct] = useState('');
  const [bucket, setBucket] = useState('');
  const [paid, setPaid] = useState('');
  const [q, setQ] = useState('');
  const { data, loading, error, reload } = useLoad(() => api('/api/calls/queue' + qs({ bank, product })), [bank, product]);
  const { data: meta } = useLoad(() => api('/api/calls/queue').catch(() => EMPTY), []);
  useLive(reload);
  const d = data || EMPTY;
  const counts = d.counts || {};
  const allMeta = useMemo(() => SEGS.flatMap(s => (meta && meta[s[2]]) || []), [meta]);
  const banks = useMemo(() => [...new Set(allMeta.map(c => c.bank).filter(Boolean))].sort(), [allMeta]);
  const products = useMemo(() => [...new Set(allMeta.filter(c => !bank || c.bank === bank).map(c => c.product).filter(Boolean))].sort(), [allMeta, bank]);
  const key = (SEGS.find(s => s[0] === seg) || SEGS[0])[2];
  const working = [...(d.due || []), ...(d.contacted_today || []), ...(d.upcoming || [])];
  const buckets = [...new Set(working.map(c => c.bucket || 'No bucket'))].sort((a, b) => bucketRank(a) - bucketRank(b));
  let list = d[key] || [];
  if (bucket) list = list.filter(c => (c.bucket || 'No bucket') === bucket);
  if (paid) list = list.filter(c => (c.paid_status || 'UNPAID').toUpperCase() === paid);
  if (q) { const s = q.toLowerCase(); list = list.filter(c => (c.customer_name || '').toLowerCase().includes(s) || (c.phone || '').includes(q) || (c.account_no || '').includes(q)); }

  return (
    <>
      <ModuleHead icon={PhoneCall} title="Calling" sub="Your queue — who to call now, callbacks, and promises" full="queue">
        <button className="btn" onClick={reload}><RefreshCw />Refresh</button>
      </ModuleHead>
      <Reminders onOpen={(id) => setSp({ open: id })} />

      <div className="grid g-kpi" style={{ marginBottom: 16 }}>
        <Kpi icon={AlarmClock} label="Due now" i={1} value={num(counts.due)} sub="call these first" tone="bad" />
        <Kpi icon={CheckCheck} label="Contacted today" i={2} value={num(counts.contacted_today)} sub="logged today" tone="info" />
        <Kpi icon={CalendarClock} label="Upcoming" i={3} value={num(counts.upcoming)} sub="scheduled callbacks" tone="warn" />
        <Kpi icon={Wallet} label="Paid today" i={4} value={num(counts.paid_today)} sub="collected" tone="good" />
      </div>

      <div className="seg-tabs rise" style={{ '--i': 5 }}>
        {SEGS.map(([id, l, k, I]) => (
          <button key={id} className={seg === id ? 'on' : ''} onClick={() => setSeg(id)}><I /><span>{l}</span><b>{num(counts[k])}</b></button>
        ))}
      </div>

      <div className="card toolbar-card rise" style={{ '--i': 6 }}>
        <div className="row wrap" style={{ gap: 10 }}>
          <SearchBox value={q} onChange={setQ} placeholder="Name, phone or account…" width={280} />
          <select className="select" value={bank} onChange={e => { setBank(e.target.value); setProduct(''); }}><option value="">All banks</option>{banks.map(b => <option key={b}>{b}</option>)}</select>
          <select className="select" value={product} onChange={e => setProduct(e.target.value)}><option value="">All products</option>{products.map(p => <option key={p}>{p}</option>)}</select>
          <Chips value={paid} onChange={v => setPaid(paid === v ? '' : v)} label="Status" options={[['', 'All'], ['PAID', 'Paid'], ['UNPAID', 'Unpaid'], ['PARTIAL', 'Partial']]} />
        </div>
        {buckets.length > 0 && <Chips value={bucket} onChange={setBucket} label="Bucket" options={[['', 'All'], ...buckets.map(b => [b, b])]} />}
      </div>

      {error && <div className="card" style={{ padding: 16, color: 'var(--bad)' }}>Couldn’t load the call queue: {error} <button className="btn sm" onClick={reload}>Retry</button></div>}
      {loading && !list.length && <div className="ccard-grid">{[...Array(6)].map((_, i) => <Skeleton key={i} h={170} />)}</div>}
      {!loading && !list.length && <Empty icon={PhoneCall} title={seg === 'due' ? 'Nothing due — nicely done' : 'Nothing here'}>{seg === 'due' ? 'Check Upcoming for scheduled callbacks.' : null}</Empty>}
      <div className="ccard-grid">
        {list.map((c, i) => <CaseCard key={c.id} i={i} c={c} showAddr={false} onOpen={() => setSp({ open: c.id })}
          extra={(c.disposition || c.follow_up_date) && <div className="ccard-note">
            {c.disposition && <div><span className="faint">Last:</span> {c.disposition}</div>}
            {c.follow_up_date && <div style={{ color: 'var(--accent)' }}>{seg === 'upcoming' ? 'Scheduled' : 'Next'}: {fmtDate(c.follow_up_date)}</div>}
          </div>} />)}
      </div>
      <CaseDrawer id={Number(sp.get('open')) || null} onClose={() => setSp({})} />
    </>
  );
}

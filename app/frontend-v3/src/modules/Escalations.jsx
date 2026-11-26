import React, { useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { ArrowUpRight, Flag, Undo2, Search, Wallet } from 'lucide-react';
import { api, qs } from '../lib/api.js';
import { inr, inrShort, num } from '../lib/format.js';
import { Card, Kpi, Pill, StatusPill, Empty, useLoad, useToast } from '../components/ui.jsx';
import CaseDrawer from '../pages/CaseDrawer.jsx';
import { ModuleHead, SearchBox, useLive } from './kit.jsx';

/** Pull a hard / high-value case off its handler and own it; release it back when done. */
export default function Escalations() {
  const toast = useToast();
  const [sp, setSp] = useSearchParams();
  const [q, setQ] = useState('');
  const [results, setResults] = useState(null);
  const [busy, setBusy] = useState(0);
  const { data, reload } = useLoad(() => api('/api/cases/escalated?mine=false').catch(() => []), []);
  const mine = Array.isArray(data) ? data : [];
  const search = () => api('/api/cases' + qs({ limit: 60, search: q })).then(rows => setResults((rows || []).filter(c => !c.escalated)
    .sort((a, b) => Number(b.pending_amount || 0) - Number(a.pending_amount || 0)))).catch(() => setResults([]));
  useLive(() => { reload(); if (results) search(); });
  const act = (c, kind) => {
    setBusy(c.id);
    api('/api/cases/' + c.id + (kind === 'up' ? '/escalate' : '/deescalate'), { method: 'POST', body: {} })
      .then(() => { toast(kind === 'up' ? `Escalated to you — removed from ${c.customer_name || 'the'}’s handler` : 'Released back to the pool'); reload(); if (results) search(); })
      .catch(e => toast(e.message, 'err')).finally(() => setBusy(0));
  };
  const pending = mine.reduce((s, c) => s + Number(c.pending_amount || 0), 0);

  return (
    <>
      <ModuleHead icon={Flag} title="Escalations" sub="Own a hard case yourself — it leaves the agent’s queue and score, but stays in MIS and the bank sheet" full="escalations" />
      <div className="grid g-kpi" style={{ marginBottom: 16 }}>
        <Kpi icon={Flag} label="Escalated" i={1} value={num(mine.length)} sub="owned by managers" tone="bad" />
        <Kpi icon={Wallet} label="Pending on them" i={2} value={pending} format={inrShort} sub="to recover" tone="warn" />
        <Kpi icon={ArrowUpRight} label="Paid" i={3} value={num(mine.filter(c => c.paid_status === 'PAID').length)} sub="closed out" tone="good" />
      </div>

      <Card title="Find a case to escalate" sub="Search by name, account, phone or pincode — highest pending first" className="rise" style={{ marginBottom: 16 }}>
        <div className="row wrap" style={{ gap: 10 }}>
          <SearchBox value={q} onChange={setQ} onEnter={search} placeholder="Name, account, phone, pincode…" width={420} />
          <button className="btn primary" onClick={search}><Search />Search</button>
        </div>
        {results && (results.length === 0 ? <div className="faint" style={{ marginTop: 12 }}>No matching un-escalated cases.</div> :
          <div className="table-wrap" style={{ marginTop: 12, maxHeight: 360 }}><table className="t">
            <thead><tr><th>Customer</th><th>Portfolio</th><th className="r">Pending</th><th className="r">ENR</th><th>Handler</th><th>Score</th><th></th></tr></thead>
            <tbody>{results.map(c => <tr key={c.id} className="click" onClick={() => setSp({ open: c.id })}>
              <td><div className="cell-main">{c.customer_name || '—'}</div><div className="cell-sub mono">{c.account_no}</div></td>
              <td className="muted">{c.bank} · {c.product || '—'}</td>
              <td className="r" style={{ color: 'var(--warn)' }}><b>{inr(c.pending_amount)}</b></td><td className="r">{inr(c.enr)}</td>
              <td className="muted">{c.fos_name || c.caller_name || '—'}</td>
              <td>{c.propensity != null ? <Pill tone={c.propensity >= 70 ? 'good' : c.propensity >= 40 ? 'warn' : 'bad'}>{c.propensity}</Pill> : '—'}</td>
              <td onClick={e => e.stopPropagation()}><button className="btn sm primary" disabled={busy === c.id} onClick={() => act(c, 'up')}><ArrowUpRight />Escalate to me</button></td>
            </tr>)}</tbody></table></div>)}
      </Card>

      <Card title={`Escalated cases · ${mine.length}`} pad={false} className="rise">
        {!mine.length ? <Empty icon={Flag} title="Nothing escalated yet" /> :
          <div className="table-wrap" style={{ maxHeight: 460 }}><table className="t">
            <thead><tr><th>Customer</th><th>Portfolio</th><th className="r">Pending</th><th>Status</th><th>Paid</th><th>Disposition</th><th></th></tr></thead>
            <tbody>{mine.map(c => <tr key={c.id} className="click" onClick={() => setSp({ open: c.id })}>
              <td><div className="cell-main">{c.customer_name || '—'}</div><div className="cell-sub mono">{c.account_no}</div></td>
              <td className="muted">{c.bank} · {c.product || '—'}</td>
              <td className="r" style={{ color: 'var(--warn)' }}><b>{inr(c.pending_amount)}</b></td>
              <td><Pill tone="neutral">{c.status || '—'}</Pill></td><td><StatusPill value={c.paid_status} /></td>
              <td className="muted">{c.disposition || '—'}</td>
              <td onClick={e => e.stopPropagation()}><button className="btn sm" disabled={busy === c.id} onClick={() => act(c, 'down')}><Undo2 />Release</button></td>
            </tr>)}</tbody></table></div>}
      </Card>
      <CaseDrawer id={Number(sp.get('open')) || null} onClose={() => setSp({})} />
    </>
  );
}

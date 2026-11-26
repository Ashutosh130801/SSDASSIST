import React, { useEffect, useMemo, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { Search, SlidersHorizontal, Download, FolderKanban, ChevronLeft, ChevronRight, Flag } from 'lucide-react';
import { api, qs } from '../lib/api.js';
import { inr, num } from '../lib/format.js';
import { Card, Seg, StatusPill, Pill, Empty, Skeleton, useLoad } from '../components/ui.jsx';
import CaseDrawer from './CaseDrawer.jsx';

const PAGE = 50;
const MONTHS = [['current', 'This month'], ['next', 'Next month'], ['last', 'Last month']];
const PAY = [['', 'All'], ['UNPAID', 'Unpaid'], ['PARTIAL', 'Partial'], ['PAID', 'Paid']];

export default function Accounts() {
  const [sp, setSp] = useSearchParams();
  const [mb, setMb] = useState('current');
  const [pay, setPay] = useState('');
  const [bank, setBank] = useState('');
  const [q, setQ] = useState('');
  const [debounced, setDebounced] = useState('');
  const [page, setPage] = useState(0);
  const [sort, setSort] = useState({ k: 'pending', dir: -1 });
  const openId = Number(sp.get('open')) || null;

  useEffect(() => { const t = setTimeout(() => setDebounced(q.trim()), 250); return () => clearTimeout(t); }, [q]);
  useEffect(() => { setPage(0); }, [mb, pay, bank, debounced]);

  const { data, loading, error } = useLoad(
    () => api('/api/cases' + qs({ month_bucket: mb, paid_status: pay, bank, search: debounced, limit: 5000 })),
    [mb, pay, bank, debounced]);
  const rows = Array.isArray(data) ? data : [];
  const banks = useMemo(() => [...new Set(rows.map(r => r.bank).filter(Boolean))].sort(), [rows]);
  const pendingOf = (c) => Number(c.pending_amount ?? Math.max(0, (Number(c.enr || c.total_outstanding || 0) - Number(c.received_amount || 0))));
  const sorted = useMemo(() => {
    const val = (c) => sort.k === 'pending' ? pendingOf(c) : sort.k === 'received' ? Number(c.received_amount || 0)
      : sort.k === 'name' ? (c.customer_name || '') : (c[sort.k] || '');
    return rows.slice().sort((a, b) => { const x = val(a), y = val(b); return (x > y ? 1 : x < y ? -1 : 0) * sort.dir; });
  }, [rows, sort]);
  const shown = sorted.slice(page * PAGE, page * PAGE + PAGE);
  const pages = Math.max(1, Math.ceil(sorted.length / PAGE));
  const totals = useMemo(() => rows.reduce((t, c) => ({ pending: t.pending + pendingOf(c), received: t.received + Number(c.received_amount || 0) }), { pending: 0, received: 0 }), [rows]);
  const th = (k, label, right) => (
    <th className={right ? 'r' : ''} style={{ cursor: 'pointer' }} onClick={() => setSort(s => ({ k, dir: s.k === k ? -s.dir : -1 }))}>
      {label}{sort.k === k ? (sort.dir < 0 ? ' ↓' : ' ↑') : ''}
    </th>
  );

  return (
    <>
      <div className="page-head rise">
        <div className="grow">
          <h1 className="page-title">Accounts</h1>
          <div className="page-sub">{loading ? 'Loading…' : `${num(rows.length)} accounts · ${inr(totals.received)} recovered · ${inr(totals.pending)} pending`}</div>
        </div>
        <Seg value={mb} onChange={setMb} options={MONTHS} />
      </div>

      <Card pad={false}>
        <div className="row wrap" style={{ padding: 14, gap: 10, borderBottom: '1px solid var(--line)' }}>
          <div className="input-icon grow" style={{ minWidth: 240, maxWidth: 420 }}>
            <Search /><input className="input" placeholder="Search name, account no, phone…" value={q} onChange={e => setQ(e.target.value)} />
          </div>
          <Seg value={pay} onChange={setPay} options={PAY} />
          <select className="select" value={bank} onChange={e => setBank(e.target.value)} style={{ minWidth: 150 }}>
            <option value="">All banks</option>{banks.map(b => <option key={b} value={b}>{b}</option>)}
          </select>
          <div className="grow" />
          <Link className="btn sm" to="/m/cases" title="Uploads, allocation, bulk actions, portfolios, exports — the complete Accounts module"><SlidersHorizontal />Full module</Link>
        </div>

        {error && <div style={{ padding: 16, color: 'var(--bad)' }}>{error}</div>}
        <div className="table-wrap" style={{ maxHeight: 'calc(100vh - 290px)' }}>
          <table className="t">
            <thead><tr>
              {th('name', 'Customer')}<th>Portfolio</th><th>Assigned</th><th>Disposition</th><th>Status</th>
              {th('received', 'Recovered', true)}{th('pending', 'Pending', true)}
            </tr></thead>
            <tbody>
              {loading && !rows.length && [...Array(8)].map((_, i) => <tr key={i}><td colSpan={7}><Skeleton h={18} /></td></tr>)}
              {shown.map(c => (
                <tr key={c.id} className="click" onClick={() => setSp({ open: c.id })}>
                  <td>
                    <div className="cell-main row" style={{ gap: 6 }}>{c.customer_name || '—'}{c.escalated && <Flag size={13} color="var(--bad)" />}</div>
                    <div className="cell-sub mono">{c.account_no || c.card_no || ''}</div>
                  </td>
                  <td><div>{c.bank} · {c.product}</div><div className="cell-sub">{[c.branch, c.cycle && 'cyc ' + c.cycle].filter(Boolean).join(' · ')}</div></td>
                  <td><div style={{ fontSize: 12.5 }}>{c.assigned_fos_name || c.fos_name || '—'}</div><div className="cell-sub">{c.assigned_caller_name || c.caller_name || ''}</div></td>
                  <td>{c.disposition ? <Pill tone={/PTP/.test(c.disposition) ? 'info' : c.disposition === 'RTP' ? 'bad' : 'neutral'}>{c.disposition}</Pill> : <span className="faint">—</span>}</td>
                  <td><StatusPill value={c.paid_status} /></td>
                  <td className="r">{inr(c.received_amount)}</td>
                  <td className="r"><b>{inr(pendingOf(c))}</b></td>
                </tr>
              ))}
            </tbody>
          </table>
          {!loading && !rows.length && <Empty icon={FolderKanban} title="No accounts match">Try another month, status or search.</Empty>}
        </div>
        {rows.length > PAGE && (
          <div className="row" style={{ padding: '10px 14px', borderTop: '1px solid var(--line)' }}>
            <span className="faint grow" style={{ fontSize: 12.5 }}>{page * PAGE + 1}–{Math.min(rows.length, page * PAGE + PAGE)} of {num(rows.length)}</span>
            <button className="btn sm" disabled={page === 0} onClick={() => setPage(p => p - 1)}><ChevronLeft />Prev</button>
            <span className="faint" style={{ fontSize: 12.5 }}>Page {page + 1} / {pages}</span>
            <button className="btn sm" disabled={page >= pages - 1} onClick={() => setPage(p => p + 1)}>Next<ChevronRight /></button>
          </div>
        )}
      </Card>

      <CaseDrawer id={openId} onClose={() => setSp({})} />
    </>
  );
}

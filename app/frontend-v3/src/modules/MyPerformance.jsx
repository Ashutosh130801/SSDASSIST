import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { Briefcase, CheckCircle2, FolderOpen, Medal, Repeat, Trophy, Wallet, X } from 'lucide-react';
import { api, qs } from '../lib/api.js';
import { inr, inrShort, num, cx } from '../lib/format.js';
import { Card, Kpi, Empty, Skeleton, useLoad } from '../components/ui.jsx';
import { ModuleHead, Chips, Bar, Metric, useLive, useClassicUI } from './kit.jsx';

export const TREND_META = [['ftd', 'FTD', 'Today'], ['mtd', 'MTD', 'Month till day'], ['lmtd', 'LMTD', 'Last month, same day'], ['overall', 'Overall', 'Lifetime']];

/** FTD / MTD / LMTD / Overall cash strip. */
export function Trends({ trends, title }) {
  if (!trends) return null;
  const mtd = Number(trends.mtd) || 0, lmtd = Number(trends.lmtd) || 0;
  const delta = lmtd ? ((mtd - lmtd) / lmtd) * 100 : null;
  return (
    <div className="trends">
      {title && <div className="trends-t">{title}</div>}
      <div className="trends-g">
        {TREND_META.map(([k, l, hint]) => (
          <div key={k} className={cx('trend', k === 'ftd' && 'hot')} title={hint}>
            <div className="trend-l">{l}<span>{hint}</span></div>
            <div className="trend-v num">{inr(trends[k])}</div>
            {k === 'mtd' && delta != null && <div className={cx('delta', delta >= 0 ? 'up' : 'down')}>{delta >= 0 ? '▲' : '▼'} {Math.abs(delta).toFixed(1)}% vs LMTD</div>}
          </div>
        ))}
      </div>
    </div>
  );
}

const MB = [['current', 'This month'], ['next', 'Next month'], ['last', 'Last month'], ['', 'All months']];

/** Caller / FOS scorecard — per-portfolio books, targets, trends and leaderboard. */
export default function MyPerformance() {
  const ui = useClassicUI();
  const [mb, setMb] = useState('current');
  const [bank, setBank] = useState('');
  const [product, setProduct] = useState('');
  const [cycles, setCycles] = useState([]);
  const [base, setBase] = useState([]);
  const { data: opts } = useLoad(() => api('/api/cases/filter-options').catch(() => ({})), []);
  const { data: d, loading, error, reload } = useLoad(() => api('/api/mis/my-performance' + qs({ month_bucket: mb, bank, product, cycles: cycles.join(',') })), [mb, bank, product, cycles.join(',')]);
  useLive(reload);
  useEffect(() => { if (d && d.portfolios && !bank && !product && !cycles.length) setBase(d.portfolios); }, [d]); // eslint-disable-line
  const t = (d && d.totals) || {};
  const roleWord = d && d.as_fos ? 'field agents' : 'callers';
  const allCycles = (opts && opts.cycles) || [];
  const toggleCycle = (c) => setCycles(s => s.includes(c) ? s.filter(x => x !== c) : [...s, c]);
  const filtered = bank || product || cycles.length;

  return (
    <>
      <ModuleHead icon={Trophy} title="My Performance" sub="Each portfolio is its own book for the month you pick — nothing is merged" full="myperf">
        <button className="btn" onClick={() => ui.inline('CycleMIS', { compact: true }, 'Cycle-wise MIS — my portfolios', 1300)}><Repeat />Cycle-wise</button>
      </ModuleHead>

      <div className="card toolbar-card rise">
        <div className="row wrap" style={{ gap: 10 }}>
          <Chips value={mb} onChange={setMb} options={MB} />
          {base.length > 0 && <select className="select" value={bank} onChange={e => { setBank(e.target.value); setProduct(''); }}>
            <option value="">All banks</option>{[...new Set(base.map(p => p.bank))].map(b => <option key={b}>{b}</option>)}</select>}
          {base.length > 0 && <select className="select" value={product} onChange={e => setProduct(e.target.value)}>
            <option value="">All products</option>{[...new Set(base.filter(p => !bank || p.bank === bank).map(p => p.product))].map(p => <option key={p}>{p}</option>)}</select>}
          {filtered ? <button className="btn sm ghost" onClick={() => { setBank(''); setProduct(''); setCycles([]); }}><X />Clear</button> : null}
        </div>
        {allCycles.length > 0 && <div className="chips"><span className="chips-l">Cycle</span>
          {allCycles.map(c => <button key={c} className={cx('chip', cycles.includes(c) && 'on')} onClick={() => toggleCycle(c)}>Cycle {c}</button>)}</div>}
      </div>

      {error && <div className="card" style={{ padding: 16, color: 'var(--bad)' }}>{error}</div>}
      {loading && !d && <div className="grid g-kpi"><Skeleton h={120} /><Skeleton h={120} /><Skeleton h={120} /><Skeleton h={120} /></div>}
      {d && <>
        <div className="grid g-kpi" style={{ marginBottom: 16 }}>
          <Kpi icon={FolderOpen} label="My cases" i={1} value={num(t.count)} sub={`${num(t.paid)} paid · ${num(t.unpaid)} open`} />
          <Kpi icon={Briefcase} label="My book (ENR)" i={2} value={t.enr || 0} format={inrShort} sub="total receivables assigned" tone="info" />
          <Kpi icon={CheckCircle2} label="Achieved (ENR)" i={3} value={t.paid_enr || 0} format={inrShort} sub={`${t.achieved_pct || 0}% of my book`} tone="good" />
          <Kpi icon={Wallet} label="Cash collected" i={4} value={t.collected || 0} format={inrShort} sub={`${inr(t.pending)} still pending`} tone="warn" />
        </div>
        {d.trends && <Card title="My cash collected" sub="all my portfolios" style={{ marginBottom: 16 }}><Trends trends={d.trends} /></Card>}
        {(!d.portfolios || !d.portfolios.length) && <Empty icon={Briefcase} title="No portfolios assigned to you for this month yet" />}

        {(d.portfolios || []).map((p, i) => (
          <Card key={i} className="rise port-card" style={{ '--i': i + 5, marginBottom: 16 }}
            title={p.label} sub={`${num(p.count)} accounts · ${num(p.paid)} paid · ${num(p.unpaid)} open`}
            actions={p.rank ? <span className="rank-badge"><Medal />Rank #{p.rank} <span>of {p.field_size}</span></span> : null}>
            <div className="metric-g">
              <Metric label="My ENR" value={inr(p.enr)} />
              <Metric label="Achieved" value={(p.achieved_pct || 0) + '%'} sub={inr(p.paid_enr)} tone="good" />
              <Metric label="Target" value={(p.target_pct || 0) + '%'} sub={p.target_pct ? inr(p.target_enr) : 'not set'} />
              <Metric label="To target" value={(p.to_target_pct || 0) + '%'} sub={p.gap_enr > 0 ? 'gap ' + inr(p.gap_enr) : 'on target'} tone={p.to_target_pct >= 100 ? 'good' : 'warn'} />
              <Metric label="Cash" value={inr(p.collected)} sub={inr(p.pending) + ' pending'} />
            </div>
            <div style={{ margin: '12px 0 4px' }}><div className="row faint" style={{ fontSize: 12, marginBottom: 6 }}><span className="grow">Progress to target</span><b>{p.to_target_pct || 0}%</b></div>
              <Bar pct={p.to_target_pct} tone={p.to_target_pct >= 100 ? 'good' : 'accent'} /></div>
            {p.trends && <Trends trends={p.trends} />}
            {p.leaderboard && p.leaderboard.length > 0 && <div style={{ marginTop: 14 }}>
              <div className="faint" style={{ fontSize: 12, marginBottom: 6 }}>Leaderboard — {roleWord} on this portfolio</div>
              <div className="table-wrap"><table className="t">
                <thead><tr><th>#</th><th>Agent</th><th className="r">Cases</th><th className="r">ENR</th><th className="r">Paid %</th><th className="r">Paid ENR</th><th className="r">Cash</th></tr></thead>
                <tbody>{p.leaderboard.map((r, j) => <tr key={j} className={r.you ? 'you' : ''}>
                  <td>{r.rank <= 3 ? <span className={'medal m' + r.rank}>{r.rank}</span> : r.rank}</td>
                  <td><b>{r.name}</b>{r.you && <span className="pill accent" style={{ marginLeft: 6 }}>you</span>}</td>
                  <td className="r">{num(r.count)}</td><td className="r">{inr(r.enr)}</td><td className="r"><b>{r.achieved_pct}%</b></td>
                  <td className="r" style={{ color: 'var(--good)' }}>{inr(r.paid_enr)}</td><td className="r">{inr(r.collected)}</td></tr>)}</tbody>
              </table></div>
            </div>}
          </Card>
        ))}
      </>}
    </>
  );
}

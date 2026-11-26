// Case helpers shared by the FOS / caller / joint / reminders screens (same rules as the classic app).
import React from 'react';
import { BellRing, ChevronDown, Footprints, Lock, MapPin, Navigation } from 'lucide-react';
import { api } from '../lib/api.js';
import { inr, cx } from '../lib/format.js';
import { Pill, StatusPill, useLoad } from '../components/ui.jsx';
import { ContactBtns, useLive } from './kit.jsx';

export const bucketRank = (b) => {
  const s = (b || '').toUpperCase();
  if (s.includes('X')) return 0;
  const m = s.match(/(\d+)/);
  if (m) return 10 - Math.min(9, parseInt(m[1], 10));
  return 50;
};
export function casePriority(c) {
  const pend = Number(c.pending_amount || 0); const b = (c.bucket || '').toUpperCase();
  if (b.includes('X') || pend >= 50000) return ['High', 'bad'];
  if (/[23456789]/.test(b) || pend >= 10000) return ['Medium', 'warn'];
  return ['Low', 'good'];
}
export function caseState(c) {
  if ((c.paid_status || '') === 'PAID' || c.status === 'paid') return 'paid';
  if (c.visited_today || c.contacted_today || c.status === 'in_progress' || c.status === 'ptp' || c.status === 'callback') return 'touched';
  return 'fresh';
}
const RANK = { fresh: 0, touched: 1, paid: 2 };
export const caseCompare = (a, b) => (RANK[caseState(a)] - RANK[caseState(b)])
  || (Number(b.propensity || 0) - Number(a.propensity || 0)) || (Number(b.pending_amount || 0) - Number(a.pending_amount || 0));

export function groupCases(cases) {
  const banks = {};
  cases.forEach(c => { const bank = c.bank || '—'; const bk = c.bucket || 'No bucket'; ((banks[bank] = banks[bank] || {})[bk] = banks[bank][bk] || []).push(c); });
  return Object.keys(banks).sort().map(bank => {
    const buckets = Object.keys(banks[bank]).sort((a, b) => bucketRank(a) - bucketRank(b)).map(bucket => {
      const list = banks[bank][bucket].slice().sort(caseCompare);
      return { bucket, cases: list, pending: list.reduce((s, c) => s + Number(c.pending_amount || 0), 0) };
    });
    return { bank, buckets, count: buckets.reduce((s, b) => s + b.cases.length, 0), pending: buckets.reduce((s, b) => s + b.pending, 0) };
  });
}

export const caseAddresses = (c) => [
  { addr: c.address, pin: c.pincode, lat: c.latitude, lng: c.longitude },
  { addr: c.address2, pin: c.pincode2, lat: c.latitude2, lng: c.longitude2 },
  { addr: c.address3, pin: c.pincode3, lat: c.latitude3, lng: c.longitude3 },
].filter(r => r.addr || r.pin);
const addrNav = (r) => 'https://www.google.com/maps/dir/?api=1&destination=' + (r.lat != null && r.lng != null ? `${r.lat},${r.lng}` : encodeURIComponent([r.addr, r.pin].filter(Boolean).join(', ')));

const STATE_TAG = { paid: ['Paid', 'good'], touched: ['Worked today', 'warn'] };

/** Account card for field / calling work. */
export function CaseCard({ c, onOpen, onVisit, i = 0, extra, showAddr = true }) {
  const [pl, pt] = casePriority(c);
  const st = caseState(c);
  const tag = STATE_TAG[st];
  const addrs = caseAddresses(c);
  return (
    <div className={cx('card ccard rise', 'st-' + st)} style={{ '--i': Math.min(i, 12) }} onClick={onOpen}>
      <div className="ccard-top">
        <div className="grow">
          <div className="ccard-name">{c.customer_name || '—'}</div>
          <div className="cell-sub">{[c.bank, c.product, c.bucket && 'Bkt ' + c.bucket, c.cycle && 'Cyc ' + c.cycle].filter(Boolean).join(' · ')}</div>
        </div>
        <div className="ccard-tags">
          {c.closed && <Pill tone="neutral"><Lock size={11} />Closed</Pill>}
          {tag && <Pill tone={tag[1]} dot>{st === 'touched' && c.visited_today ? 'Visited today' : tag[0]}</Pill>}
          <Pill tone={pt}>{pl}</Pill>
          {c.propensity != null && <Pill tone={c.propensity >= 70 ? 'good' : c.propensity >= 40 ? 'warn' : 'bad'} title="Recovery propensity">{c.propensity}</Pill>}
        </div>
      </div>
      <div className="ccard-amt">
        <div><div className="faint">Pending</div><b className="num">{inr(c.pending_amount)}</b></div>
        {c.is_settlement_case && (c.paid_status || '') !== 'PAID' && <div><div className="faint">NORM / STAB</div><span className="num">{c.remaining_to_norm != null ? inr(c.remaining_to_norm) : '—'} / {c.remaining_to_stab != null ? inr(c.remaining_to_stab) : '—'}</span></div>}
        <div style={{ marginLeft: 'auto' }}><StatusPill value={c.paid_status} /></div>
      </div>
      {extra}
      {showAddr && addrs.length > 0 && <div className="ccard-addr">
        {addrs.slice(0, 3).map((r, k) => <a key={k} href={addrNav(r)} target="_blank" rel="noreferrer" onClick={e => e.stopPropagation()} title="Navigate to this address">
          <MapPin size={13} /><span>{r.addr || ''}{r.pin ? ' · ' + r.pin : ''}</span><Navigation size={12} className="go" /></a>)}
      </div>}
      <div className="ccard-act" onClick={e => e.stopPropagation()}>
        {onVisit && <button className="btn sm primary" disabled={!!c.closed} onClick={() => onVisit(c)} title={c.closed ? 'Case closed — locked' : 'Log a field visit (GPS camera)'}>
          {c.closed ? <><Lock />Closed</> : <><Footprints />Log visit</>}</button>}
        <ContactBtns phone={c.phone} caseId={c.id} />
      </div>
    </div>
  );
}

/** PTP reminders strip (overdue / due today) — shown on FOS and caller work screens. */
export function Reminders({ onOpen }) {
  const { data, reload } = useLoad(() => api('/api/reminders').catch(() => null), []);
  useLive(reload);
  const [open, setOpen] = React.useState(true);
  if (!data || !data.count) return null;
  return (
    <div className="card remind rise">
      <button className="remind-h row" onClick={() => setOpen(o => !o)}>
        <span className="mod-ic sm warn"><BellRing /></span>
        <b>PTP reminders · {data.count}</b>
        <span className="muted">{data.overdue} overdue · {data.due_today} due today</span>
        <ChevronDown className={cx('chev', !open && 'rot')} />
      </button>
      {open && <div className="remind-list">
        {data.rows.slice(0, 30).map(r => (
          <button key={r.case_id} className={cx('remind-i', r.overdue && 'od')} onClick={() => onOpen(r.case_id)}>
            <div className="row" style={{ gap: 6 }}><b className="grow">{r.customer || r.account || 'Case'}</b><Pill tone={r.overdue ? 'bad' : 'warn'}>{r.overdue ? 'Overdue' : 'Today'}</Pill></div>
            <div className="cell-sub">{r.bank} · {r.ptp_date} · {inr(r.pending)} pending</div>
          </button>
        ))}
      </div>}
    </div>
  );
}

import React from 'react';
import { Phone, MessageCircle, Navigation, ExternalLink, MapPin, Wallet, Footprints, PhoneCall, FileClock } from 'lucide-react';
import { api } from '../lib/api.js';
import { inr, fmtDate, fmtTime } from '../lib/format.js';
import { Drawer, StatusPill, Pill, Skeleton, useLoad, Card } from '../components/ui.jsx';
import { useClassic } from '../lib/classic.jsx';
import { useAuth } from '../lib/auth.jsx';

const tel = (p) => String(p || '').replace(/[^0-9+]/g, '');
const wa = (p) => { let d = String(p || '').replace(/\D/g, ''); if (d.length === 10) d = '91' + d; return 'https://wa.me/' + d; };
const ICON = { visit: Footprints, call: PhoneCall, payment: Wallet };

/** Case detail side-panel. Read view + quick contact actions; logging calls/visits/payments
 *  still happens in the classic case screen (linked) until those forms are redesigned. */
export default function CaseDrawer({ id, onClose }) {
  const classic = useClassic();
  // The complete case screen (log call / visit / payment, PTP, edits, live ViciDial bar, history)
  // opens directly as soon as the runtime is up; this read-only panel only covers the first seconds.
  React.useEffect(() => {
    if (id && classic.api && classic.api.openCase) { classic.api.openCase(id); onClose(); }
  }, [id, classic.api]); // eslint-disable-line
  const { user } = useAuth();
  const isFos = user && (user.role === 'fos' || user.active_view === 'fos');
  const logVisit = () => { if (classic.api && classic.api.openPanel && c) { onClose(); classic.api.openPanel('visit', { c }); } };
  const openFull = () => { if (classic.api) { onClose(); classic.api.openCase(id); } };
  const { data: c, loading } = useLoad(() => (id ? api('/api/cases/' + id) : Promise.resolve(null)), [id]);
  const { data: tl } = useLoad(() => (id ? api('/api/cases/' + id + '/timeline') : Promise.resolve([])), [id]);
  const events = Array.isArray(tl) ? tl : (tl && (tl.events || tl.items)) || [];
  const pending = c ? Number(c.pending_amount ?? Math.max(0, Number(c.enr || c.total_outstanding || 0) - Number(c.received_amount || 0))) : 0;
  const addr = c ? [c.address, c.address2, c.address3].filter(Boolean) : [];

  return (
    <Drawer open={!!id} onClose={onClose} header={c ? (
      <div>
        <div className="row" style={{ gap: 8 }}><b style={{ fontSize: 17, fontFamily: 'var(--font-display)' }}>{c.customer_name}</b><StatusPill value={c.paid_status} />{c.escalated && <Pill tone="bad">Escalated</Pill>}</div>
        <div className="faint mono" style={{ marginTop: 2 }}>{c.account_no || c.card_no} · {c.bank} {c.product}</div>
      </div>) : <Skeleton h={22} w={220} />}>
      {loading && !c && <div className="col"><Skeleton h={90} /><Skeleton h={160} /><Skeleton h={200} /></div>}
      {c && <>
        <div className="grid" style={{ gridTemplateColumns: 'repeat(3, 1fr)', gap: 10, marginBottom: 14 }}>
          <Stat label="Pending" value={inr(pending)} strong />
          <Stat label="Recovered" value={inr(c.received_amount)} />
          <Stat label="ENR / TOS" value={inr(c.enr || c.total_outstanding)} />
        </div>

        <div className="row wrap" style={{ gap: 8, marginBottom: 16 }}>
          {c.phone && <a className="btn sm" href={'tel:' + tel(c.phone)}><Phone />Call</a>}
          {c.phone && <a className="btn sm" href={wa(c.phone)} target="_blank" rel="noreferrer"><MessageCircle />WhatsApp</a>}
          {addr[0] && <a className="btn sm" target="_blank" rel="noreferrer" href={c.latitude ? `https://www.google.com/maps/dir/?api=1&destination=${c.latitude},${c.longitude}` : 'https://www.google.com/maps/search/?api=1&query=' + encodeURIComponent(addr[0])}><Navigation />Navigate</a>}
          <div className="grow" />
          {isFos && <button className="btn sm" disabled={!classic.api || (c && c.closed)} onClick={logVisit} title="Log a field visit (GPS camera)"><Footprints />Log visit</button>}
          <button className="btn primary sm" disabled={!classic.api} onClick={openFull} title="Open the full case: log call / visit / payment, PTP, edits, history"><ExternalLink />Open full case · log activity</button>
        </div>

        <Card title="Account details" style={{ marginBottom: 14 }}>
          <dl className="kv">
            <dt>Phone</dt><dd>{c.phone || '—'}{c.new_phone ? <span className="faint"> · new {c.new_phone}</span> : null}</dd>
            <dt>Portfolio</dt><dd>{c.bank} · {c.product}{c.branch ? ' · ' + c.branch : ''}</dd>
            <dt>Cycle / bucket</dt><dd>{[c.cycle && 'Cycle ' + c.cycle, c.bucket && 'Bkt ' + c.bucket, c.period].filter(Boolean).join(' · ') || '—'}</dd>
            <dt>Disposition</dt><dd>{c.disposition || '—'}{c.follow_up_date ? <span className="faint"> · follow-up {fmtDate(c.follow_up_date)}</span> : null}</dd>
            <dt>Field agent</dt><dd>{c.assigned_fos_name || c.fos_name || '—'}</dd>
            <dt>Caller</dt><dd>{c.assigned_caller_name || c.caller_name || '—'}</dd>
            <dt>Team lead</dt><dd>{c.team_lead || '—'}</dd>
            {c.remaining_to_norm != null && <><dt>Pending NORM / STAB</dt><dd>{inr(c.remaining_to_norm)} / {inr(c.remaining_to_stab)}</dd></>}
          </dl>
        </Card>

        {addr.length > 0 && <Card title="Addresses" style={{ marginBottom: 14 }}>
          <div className="col" style={{ gap: 10 }}>
            {addr.map((a, i) => <div key={i} className="row" style={{ alignItems: 'flex-start', gap: 10 }}>
              <MapPin size={16} className="faint" style={{ marginTop: 2, flex: 'none' }} /><div className="grow" style={{ fontSize: 13 }}>{a}</div>
              <a className="btn ghost sm" target="_blank" rel="noreferrer" href={'https://www.google.com/maps/search/?api=1&query=' + encodeURIComponent(a)}><Navigation /></a>
            </div>)}
          </div>
        </Card>}

        <Card title="Activity" sub={`${events.length} events`}>
          {!events.length && <div className="faint" style={{ fontSize: 13 }}>No activity yet.</div>}
          <div className="timeline">
            {events.slice().reverse().slice(0, 40).map((e, i) => {
              const I = ICON[e.type] || FileClock;
              return <div className="tl-i" key={i}>
                <div className="row" style={{ gap: 6, fontWeight: 600, fontSize: 13 }}><I size={14} className="faint" />{e.title}
                  {e.amount ? <Pill tone="good">{inr(e.amount)}</Pill> : null}</div>
                {e.detail && <div className="muted" style={{ fontSize: 12.5 }}>{e.detail}</div>}
                <div className="faint" style={{ fontSize: 11.5 }}>{fmtDate(e.at)} {fmtTime(e.at)}{e.by ? ' · ' + e.by : ''}</div>
              </div>;
            })}
          </div>
        </Card>
      </>}
    </Drawer>
  );
}

const Stat = ({ label, value, strong }) => (
  <div className="card" style={{ padding: '12px 14px' }}>
    <div className="faint" style={{ fontSize: 12 }}>{label}</div>
    <div className="num" style={{ fontFamily: 'var(--font-display)', fontWeight: 650, fontSize: strong ? 20 : 17, color: strong ? 'var(--accent)' : undefined }}>{value}</div>
  </div>
);

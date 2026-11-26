import React from 'react';
import { useSearchParams } from 'react-router-dom';
import { CircleAlert, Handshake, ListTodo, MapPinned, PhoneCall, PhoneIncoming, Wallet } from 'lucide-react';
import { api } from '../lib/api.js';
import { inr, num, fmtTime } from '../lib/format.js';
import { useAuth } from '../lib/auth.jsx';
import { Card, Skeleton, useLoad } from '../components/ui.jsx';
import CaseDrawer from '../pages/CaseDrawer.jsx';
import { ModuleHead, useLive } from './kit.jsx';

/** My work queue — everything that needs action today, in four lanes. */
export default function Todo() {
  const { user } = useAuth();
  const [sp, setSp] = useSearchParams();
  const { data: d, loading, reload } = useLoad(() => api('/api/todo/me'), []);
  useLive(reload);
  const fos = user && user.role === 'fos';
  const LANES = [
    ['ptp_broken', 'Broken PTPs', 'overdue promises', CircleAlert, 'bad'],
    ['ptp_today', "Today's PTPs", 'promised for today', Handshake, 'warn'],
    [fos ? 'visits_pending' : 'calls_pending', fos ? 'Visits pending' : 'Calls pending', 'not worked yet', fos ? MapPinned : PhoneCall, 'info'],
    ['paid_not_updated', 'Paid — status not updated', 'mark them paid', Wallet, 'good'],
  ];
  const open = (id) => id && setSp({ open: id });
  const cb = (d && d.callbacks) || [];

  return (
    <>
      <ModuleHead icon={ListTodo} title="My Work Queue" sub="Everything that needs action today — nothing slips through" full="todo" />
      {cb.length > 0 && <Card title={<span className="row" style={{ gap: 8 }}><PhoneIncoming size={16} />Callback requests · {cb.length}</span>} style={{ marginBottom: 16 }} className="rise">
        <div className="col" style={{ gap: 6 }}>
          {cb.map(c => <button key={c.id} className="lane-i" onClick={() => open(c.case_id)} disabled={!c.case_id}>
            <b>{c.from}</b><span className="muted grow" style={{ textAlign: 'left' }}>{c.body}</span><span className="faint">{fmtTime(c.at)}</span></button>)}
        </div>
      </Card>}
      {loading && !d && <div className="lanes">{[...Array(4)].map((_, i) => <Skeleton key={i} h={300} />)}</div>}
      {d && <div className="lanes">
        {LANES.map(([key, label, sub, I, tone], li) => { const rows = d[key] || []; return (
          <section key={key} className={'card lane rise tone-' + tone} style={{ '--i': li + 1 }}>
            <header className="lane-h"><span className={'mod-ic sm ' + tone}><I /></span><div className="grow"><b>{label}</b><div className="faint" style={{ fontSize: 11.5 }}>{sub}</div></div><span className="lane-n num">{num(rows.length)}</span></header>
            <div className="lane-b">
              {!rows.length && <div className="faint lane-empty">Nothing pending 🎉</div>}
              {rows.slice(0, 50).map(c => <button key={c.id} className="lane-i" onClick={() => open(c.id)}>
                <div className="grow" style={{ textAlign: 'left', minWidth: 0 }}><div className="cell-main ellip">{c.customer || c.account}</div>
                  <div className="cell-sub">{c.bank} {c.product}{c.follow_up ? ' · due ' + c.follow_up : ''}</div></div>
                <b className="num" style={{ fontSize: 12.5 }}>{inr(c.pending)}</b></button>)}
            </div>
          </section>); })}
      </div>}
      <CaseDrawer id={Number(sp.get('open')) || null} onClose={() => setSp({})} />
    </>
  );
}

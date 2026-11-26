import React from 'react';
import { useSearchParams } from 'react-router-dom';
import { Users2, Wallet, Info } from 'lucide-react';
import { api } from '../lib/api.js';
import { inrShort, num } from '../lib/format.js';
import { Kpi, Empty, Skeleton, useLoad } from '../components/ui.jsx';
import CaseDrawer from '../pages/CaseDrawer.jsx';
import { ModuleHead, useLive, usePanel, NavBtn } from './kit.jsx';
import { CaseCard } from './caseKit.jsx';

/** FOS — cases another agent owns, sent to you to visit a new address and collect. */
export default function JointCases() {
  const [sp, setSp] = useSearchParams();
  const panel = usePanel();
  const { data, loading, reload } = useLoad(() => api('/api/cases/joint-mine').catch(() => []), []);
  useLive(reload);
  const rows = Array.isArray(data) ? data : [];
  const pending = rows.reduce((s, c) => s + Number(c.pending_amount || 0), 0);
  const visit = (c) => panel('visit', { c }).then(ok => ok && reload());

  return (
    <>
      <ModuleHead icon={Users2} title="Joint Cases" sub="Accounts shared with you to visit a new address and collect" full="jointcases" />
      <div className="card note-card rise"><Info /><div>These count for you only after you log a <b>paid visit</b> — then they drop off this list. The primary agent keeps the account until then.</div></div>
      <div className="grid g-kpi" style={{ margin: '16px 0' }}>
        <Kpi icon={Users2} label="Joint accounts" i={1} value={num(rows.length)} sub="waiting for your visit" tone="info" />
        <Kpi icon={Wallet} label="Pending" i={2} value={pending} format={inrShort} sub="to collect" tone="warn" />
      </div>
      {loading && !rows.length && <div className="ccard-grid">{[...Array(3)].map((_, i) => <Skeleton key={i} h={200} />)}</div>}
      {!loading && !rows.length && <Empty icon={Users2} title="No joint cases right now" />}
      <div className="ccard-grid">
        {rows.map((c, i) => <CaseCard key={c.id} i={i} c={c} onOpen={() => setSp({ open: c.id })} onVisit={visit}
          extra={<div className="ccard-note"><div className="row" style={{ gap: 6 }}><span className="faint">Primary agent</span><b>{c.fos_name || '—'}</b><div className="grow" /><NavBtn c={c} /></div>
            {c.joint_note && <div className="muted" style={{ fontSize: 12.5, marginTop: 4 }}>“{c.joint_note}”</div>}</div>} />)}
      </div>
      <CaseDrawer id={Number(sp.get('open')) || null} onClose={() => setSp({})} />
    </>
  );
}

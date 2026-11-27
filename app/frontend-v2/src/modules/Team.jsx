import React, { useEffect, useMemo, useState } from 'react';
import {
  ArrowLeft, BarChart3, Building2, CalendarDays, Compass, Download, History, LineChart, MapPin, Pencil, Phone, Plus,
  RotateCcw, Repeat, Trash2, UserMinus, UserPlus, Users, Users2, Wallet, CheckCircle2, FolderOpen, UserCog,
} from 'lucide-react';
import { api, download } from '../lib/api.js';
import { useAuth } from '../lib/auth.jsx';
import { inr, inrShort, num, roleName, cx } from '../lib/format.js';
import { Card, Kpi, Pill, Empty, Skeleton, useLoad, useToast } from '../components/ui.jsx';
import Dashboard from '../pages/Dashboard.jsx';
import { ModuleHead, Chips, Avatar, Presence, usePresence, usePanel, useLive, SearchBox, ContactBtns } from './kit.jsx';

/** FOS / caller coverage reports (xlsx), same endpoint as classic. */
function ReportButtons() {
  const toast = useToast();
  const [m, setM] = useState('current'); const [busy, setBusy] = useState('');
  const go = async (kind) => {
    setBusy(kind);
    try { await download(`/api/team/staff-report?kind=${kind}&month_bucket=${m}&layout=compact`, `${kind === 'fos' ? 'FOS' : 'Callers'}_coverage_${m}.xlsx`); }
    catch (e) { toast(e.message || 'Download failed', 'err'); } finally { setBusy(''); }
  };
  return <span className="row" style={{ gap: 6 }}>
    <select className="select" value={m} onChange={e => setM(e.target.value)} title="Month for the report">
      <option value="current">This month</option><option value="last">Last month</option><option value="all">All months</option></select>
    <button className="btn" disabled={!!busy} onClick={() => go('fos')}><Download />{busy === 'fos' ? '…' : 'FOS report'}</button>
    <button className="btn" disabled={!!busy} onClick={() => go('caller')}><Download />{busy === 'caller' ? '…' : 'Caller report'}</button>
  </span>;
}

const ROLE_TABS = [['', 'Branches', Building2], ['fos', 'Field Officers', Compass], ['telecaller', 'Callers', Phone], ['teamlead', 'Team Leads', Users2]];

/** Team — branch cards (admin / head office), role directories, branch detail with staff actions. */
export default function Team() {
  const { user } = useAuth();
  const toast = useToast();
  const panel = usePanel();
  const isAdmin = user.role === 'admin';
  const seesAll = isAdmin || user.role === 'headoffice';
  const canTransfer = isAdmin || user.role === 'manager';
  const [openBranch, setOpenBranch] = useState(seesAll ? null : (user.branch || 'Unassigned'));
  const [listRole, setListRole] = useState('');
  const [fosLoc, setFosLoc] = useState('');
  const [q, setQ] = useState('');
  const [showChart, setShowChart] = useState(false);

  const usersL = useLoad(() => api('/api/users'), []);
  const branchesL = useLoad(() => api('/api/team/branches').catch(() => []), []);
  const reload = () => { usersL.reload(); branchesL.reload(); };
  useLive(reload);
  const users = Array.isArray(usersL.data) ? usersL.data : null;
  const branches = Array.isArray(branchesL.data) ? branchesL.data : null;
  const { data: locs } = useLoad(() => (seesAll ? api('/api/manpower/filters').then(d => d.locations || []).catch(() => []) : Promise.resolve([])), [seesAll]);
  const roleList = useLoad(() => (listRole ? api('/api/manpower?role=' + listRole + (listRole === 'fos' && fosLoc ? '&location=' + encodeURIComponent(fosLoc) : '')).catch(() => []) : Promise.resolve(null)), [listRole, fosLoc]);
  const assoc = useLoad(() => (openBranch ? api('/api/team/branch-associates?branch=' + encodeURIComponent(openBranch)).catch(() => []) : Promise.resolve([])), [openBranch]);

  const q0 = q.trim().toLowerCase();
  const hits = useMemo(() => (q0 && users ? users.filter(u => [u.name, u.emp_code, u.phone, u.email, u.role, u.branch, u.location, u.designation]
    .some(v => String(v || '').toLowerCase().includes(q0))) : []), [q0, users]);
  const staffAll = useMemo(() => (users || []).filter(u => (u.branch || 'Unassigned') === openBranch), [users, openBranch]);
  // Branch detail role filter — each chip shows only that role's people (dual-role staff count under every role they hold).
  const [brRole, setBrRole] = useState('all');
  const [brStatus, setBrStatus] = useState('all');   // all | active | inactive
  useEffect(() => { setBrRole('all'); setBrStatus('all'); }, [openBranch]);
  const hasRole = (u, r) => u.role === r || (r === 'teamlead' && u.also_team_lead) || (r === 'fos' && u.also_field_agent)
    || (r === 'telecaller' && u.also_caller) || (r === 'teamfollower' && u.also_team_follower);
  const ROLE_ORDER = ['manager', 'teamlead', 'teamfollower', 'fos', 'telecaller', 'backend', 'hr', 'headoffice', 'admin', 'it', 'staff'];
  const brRoles = useMemo(() => [...new Set(staffAll.flatMap(u => ROLE_ORDER.filter(r => hasRole(u, r)).concat(ROLE_ORDER.includes(u.role) ? [] : [u.role])))]
    .sort((a, b) => (ROLE_ORDER.indexOf(a) + 1 || 99) - (ROLE_ORDER.indexOf(b) + 1 || 99)), [staffAll]);
  const isAct = u => u.is_active !== false;
  const staffSt = useMemo(() => (brStatus === 'all' ? staffAll : staffAll.filter(u => (brStatus === 'active') === isAct(u))), [staffAll, brStatus]);
  const staff = useMemo(() => (brRole === 'all' ? staffSt : staffSt.filter(u => hasRole(u, brRole))), [staffSt, brRole]);
  const pres = usePresence((q0 ? hits : openBranch ? staff : []).slice(0, 200).map(u => u.id));

  const profile = (u) => panel('employee', { u });
  const attendance = () => users && panel('report', { officers: users });
  const totals = useMemo(() => (branches || []).reduce((t, b) => ({ staff: t.staff + (b.staff || 0), fos: t.fos + (b.fos || 0), callers: t.callers + (b.telecaller || 0),
    received: t.received + (b.received || 0), pending: t.pending + (b.pending || 0) }), { staff: 0, fos: 0, callers: 0, received: 0, pending: 0 }), [branches]);

  /* ── search results ── */
  if (q0) return (
    <>
      <ModuleHead icon={Users} title="Team" sub={`${hits.length} match${hits.length === 1 ? '' : 'es'} for “${q}”`} full="staff">
        <SearchBox value={q} onChange={setQ} placeholder="Search employees…" width={280} />
        <button className="btn ghost" onClick={() => setQ('')}>Clear</button>
      </ModuleHead>
      <Card pad={false} className="rise">
        {!users ? <div style={{ padding: 16 }}><Skeleton h={200} /></div> : !hits.length ? <Empty icon={Users} title={`No employees match “${q}”`} /> :
          <div className="table-wrap"><table className="t">
            <thead><tr><th>Employee</th><th>Role</th><th>Branch</th><th>Location</th><th>Phone</th><th></th></tr></thead>
            <tbody>{hits.map(u => <tr key={u.id} className="click" onClick={() => profile({ ...u })}>
              <td><div className="row" style={{ gap: 10 }}><Avatar name={u.name} size={32} /><div>
                <div className="cell-main">{u.name}{u.is_active === false && <Pill tone="neutral">inactive</Pill>}</div>
                <div className="cell-sub mono">{u.emp_code || '—'}</div><Presence p={pres[String(u.id)]} /></div></div></td>
              <td><Pill tone="accent">{roleName(u.role)}</Pill></td><td className="muted">{u.branch || '—'}</td><td className="muted">{u.location || '—'}</td>
              <td className="mono">{u.phone || '—'}</td>
              <td onClick={e => e.stopPropagation()} style={{ whiteSpace: 'nowrap' }}><button className="btn sm" onClick={() => profile({ ...u })}><LineChart />Performance</button> <ContactBtns phone={u.phone} compact /></td>
            </tr>)}</tbody></table></div>}
      </Card>
    </>
  );

  /* ── admin / head office: branch grid or role directory ── */
  if (seesAll && !openBranch) {
    const rl = Array.isArray(roleList.data) ? roleList.data : null;
    return (
      <>
        <ModuleHead icon={Users} title="Team" sub="Branches, people and how each one is performing" full="staff">
          <button className="btn" onClick={attendance}><CalendarDays />Attendance</button>
          <button className="btn primary" onClick={() => panel('addBranch').then(ok => ok && reload())}><Plus />Add branch</button>
        </ModuleHead>
        <div className="grid g-kpi" style={{ marginBottom: 16 }}>
          <Kpi icon={Building2} label="Branches" i={1} value={num((branches || []).length)} />
          <Kpi icon={Users} label="People" i={2} value={num(totals.staff)} sub={`${num(totals.fos)} FOS · ${num(totals.callers)} callers`} tone="info" />
          <Kpi icon={CheckCircle2} label="Recovered" i={3} value={totals.received} format={inrShort} tone="good" />
          <Kpi icon={Wallet} label="Pending" i={4} value={totals.pending} format={inrShort} tone="warn" />
        </div>
        <div className="card toolbar-card rise"><div className="row wrap" style={{ gap: 10 }}>
          <div className="seg-tabs" style={{ margin: 0, padding: 0 }}>
            {ROLE_TABS.map(([v, l, I]) => <button key={v} className={listRole === v ? 'on' : ''} onClick={() => setListRole(v)}><I /><span>{l}</span></button>)}
          </div>
          <SearchBox value={q} onChange={setQ} placeholder="Search employees…" width={240} />
          <div className="grow" />
          {listRole === 'fos' && <select className="select" value={fosLoc} onChange={e => setFosLoc(e.target.value)}><option value="">All locations</option>{(locs || []).map(l => <option key={l}>{l}</option>)}</select>}
          <ReportButtons />
        </div></div>

        {listRole ? (
          <Card pad={false} className="rise" title={rl ? `${rl.length} ${listRole === 'fos' ? 'field officers' : listRole === 'telecaller' ? 'callers' : 'team leads'}${listRole === 'fos' ? (fosLoc ? ' in ' + fosLoc : ' · all locations') : ''}` : 'Loading…'}
            sub={listRole === 'teamlead' ? 'Open a team lead to see their team and each member’s performance' : null}>
            {!rl ? <div style={{ padding: 16 }}><Skeleton h={200} /></div> : !rl.length ? <Empty title="None here" /> :
              <div className="table-wrap"><table className="t">
                <thead><tr><th>Employee</th><th>{listRole === 'fos' ? 'Location' : 'Branch'}</th><th>Phone</th><th></th></tr></thead>
                <tbody>{rl.map(u => { const open = () => (listRole === 'teamlead' ? panel('tlOverview', { lead: u }) : profile({ ...u, role: listRole })); return (
                  <tr key={u.id} className="click" onClick={open}>
                    <td><div className="row" style={{ gap: 10 }}><Avatar name={u.name} size={30} /><div>
                      <div className="cell-main">{u.name}{u.also_team_lead && listRole !== 'teamlead' && <Pill tone="accent">+TL</Pill>}</div>
                      <div className="cell-sub mono">{listRole === 'teamlead' ? (u.tl_emp_code || u.emp_code || '—') : (u.emp_code || u.tl_emp_code || '—')}</div></div></div></td>
                    <td className="muted">{(listRole === 'fos' ? u.location : u.branch) || '—'}</td><td className="mono">{u.phone || '—'}</td>
                    <td onClick={e => e.stopPropagation()} style={{ whiteSpace: 'nowrap' }}>
                      {listRole === 'teamlead' ? <button className="btn sm primary" onClick={open}><Users2 />Team & performance</button>
                        : <button className="btn sm" onClick={open}><LineChart />Performance</button>} <ContactBtns phone={u.phone} compact /></td>
                  </tr>); })}</tbody></table></div>}
          </Card>
        ) : !branches ? <div className="branch-grid">{[...Array(6)].map((_, i) => <Skeleton key={i} h={170} />)}</div>
          : !branches.length ? <Empty icon={Building2} title="No branches yet">Add one to assign a manager.</Empty> :
          <div className="branch-grid">
            {branches.map((b, i) => { const tot = (b.received || 0) + (b.pending || 0); const pct = tot ? (b.received || 0) * 100 / tot : 0; return (
              <button key={b.branch} className="card branch-card rise" style={{ '--i': Math.min(i, 12) }} onClick={() => setOpenBranch(b.branch)}>
                <div className="row"><span className="mod-ic sm"><Building2 /></span><b className="grow branch-n">{b.branch}</b><Pill tone="accent" title="Everyone in this branch, all roles">{b.staff} staff</Pill></div>
                <div className="cell-sub" style={{ marginTop: 6 }}>{b.manager ? <><UserCog size={12} /> {b.manager.name}</> : <span style={{ color: 'var(--warn)' }}>No manager</span>}</div>
                <div className="branch-roles">
                  <span><b>{b.fos}</b>FOS</span><span><b>{b.telecaller}</b>Callers</span><span><b>{b.teamlead || 0}</b>Team leads</span>
                  {b.backend > 0 && <span><b>{b.backend}</b>Back-office</span>}
                  {b.other > 0 && <span title="Managers, HR, IT and other roles"><b>{b.other}</b>Others</span>}
                </div>
                <div className="branch-money">
                  <div><span>Recovered</span><b style={{ color: 'var(--good)' }}>{inr(b.received)}</b></div>
                  <div style={{ textAlign: 'right' }}><span>Pending</span><b style={{ color: 'var(--warn)' }}>{inr(b.pending)}</b></div>
                </div>
                <div className="pbar tone-good" style={{ height: 6 }}><i style={{ width: pct + '%' }} /></div>
              </button>); })}
          </div>}
      </>
    );
  }

  /* ── branch detail ── */
  const card = (branches || []).find(b => b.branch === openBranch) || { branch: openBranch, staff: 0, cases: 0, received: 0, pending: 0, manager: null };
  const associates = Array.isArray(assoc.data) ? assoc.data : [];
  const rename = () => {
    const nn = (window.prompt('Rename branch', openBranch) || '').trim();
    if (!nn || nn === openBranch) return;
    api('/api/team/branches/' + encodeURIComponent(openBranch), { method: 'PATCH', body: { new_name: nn } })
      .then(() => { toast('Branch renamed'); setOpenBranch(nn); reload(); }).catch(e => toast(e.message, 'err'));
  };
  const del = () => {
    if (!window.confirm(`Delete branch "${openBranch}"? Its staff & cases become unassigned (staff accounts are kept).`)) return;
    api('/api/team/branches/' + encodeURIComponent(openBranch), { method: 'DELETE' })
      .then(() => { toast('Branch deleted'); setOpenBranch(isAdmin ? null : openBranch); reload(); }).catch(e => toast(e.message, 'err'));
  };
  const toggleStaff = (u) => {
    if (u.is_active === false) {
      api('/api/users/' + u.id, { method: 'PATCH', body: { is_active: true } }).then(() => { toast(u.name + ' reactivated'); reload(); }).catch(e => toast(e.message, 'err'));
      return;
    }
    if (!window.confirm(`Remove ${u.name}? They'll be marked inactive (kept in records, not counted going forward).`)) return;
    api('/api/users/' + u.id, { method: 'DELETE' }).then(() => { toast(u.name + ' removed'); reload(); }).catch(e => toast(e.message, 'err'));
  };

  return (
    <>
      <ModuleHead icon={Building2} title={openBranch} sub={card.manager ? 'Managed by ' + card.manager.name : 'No manager assigned'} full="staff">
        {seesAll && <button className="btn ghost" onClick={() => setOpenBranch(null)}><ArrowLeft />Branches</button>}
        <button className={cx('btn', showChart && 'primary')} onClick={() => setShowChart(v => !v)}><BarChart3 />{showChart ? 'Hide analytics' : 'Analytics'}</button>
        <button className="btn" onClick={attendance}><CalendarDays />Attendance</button>
        {canTransfer && <button className="btn" onClick={() => panel('transfer', { staff: user.role === 'manager' ? staff : users || [] }).then(ok => ok && reload())}><Repeat />Transfer cases</button>}
        <button className="btn primary" onClick={() => panel('staff', { presetBranch: openBranch }).then(ok => ok && reload())}><UserPlus />Add staff</button>
      </ModuleHead>

      <div className="card toolbar-card rise"><div className="row wrap" style={{ gap: 10 }}>
        <SearchBox value={q} onChange={setQ} placeholder="Search employees…" width={260} />
        <div className="grow" />
        {isAdmin && openBranch !== 'Unassigned' && <><button className="btn sm" onClick={rename}><Pencil />Rename</button><button className="btn sm ghost danger" onClick={del}><Trash2 />Delete branch</button></>}
      </div></div>

      {showChart && <div className="embed-dash rise" style={{ marginBottom: 16 }}><Dashboard branch={openBranch} embedded /></div>}

      <div className="grid g-kpi" style={{ marginBottom: 16 }}>
        <Kpi icon={Users} label="Staff" i={1} value={num(card.staff)} sub="all roles" />
        <Kpi icon={FolderOpen} label="Cases" i={2} value={num(card.cases)} tone="info" />
        <Kpi icon={CheckCircle2} label="Recovered" i={3} value={card.received || 0} format={inrShort} tone="good" />
        <Kpi icon={Wallet} label="Pending" i={4} value={card.pending || 0} format={inrShort} tone="warn" />
      </div>

      {users && staffAll.length > 0 && <div className="card toolbar-card rise"><div className="row wrap" style={{ gap: 10 }}>
        <span className="faint" style={{ fontSize: 12.5 }}>Role</span>
        <Chips value={brRole} onChange={setBrRole} options={[['all', `All (${staffSt.length})`],
          ...brRoles.map(r => [r, `${roleName(r)} (${staffSt.filter(u => hasRole(u, r)).length}${r === 'fos' && associates.length ? ' + ' + associates.length : ''})`])]} />
        <div className="grow" />
        <span className="faint" style={{ fontSize: 12.5 }}>Status</span>
        <Chips value={brStatus} onChange={setBrStatus} options={[['all', `All (${staffAll.length})`],
          ['active', `Active (${staffAll.filter(isAct).length})`], ['inactive', `Inactive (${staffAll.filter(u => !isAct(u)).length})`]]} />
      </div></div>}
      <Card title={`${brRole === 'all' ? 'People' : roleName(brRole)} · ${staff.length}`} pad={false} className="rise">
        {!users ? <div style={{ padding: 16 }}><Skeleton h={220} /></div> : !staff.length ? <Empty icon={Users} title={brRole === 'all' && brStatus === 'all' ? 'No staff in this branch yet' : `No ${brStatus !== 'all' ? brStatus + ' ' : ''}${brRole === 'all' ? 'staff' : roleName(brRole)} in this branch`} /> :
          <div className="table-wrap"><table className="t">
            <thead><tr><th>Employee</th><th>Role</th><th>Banks</th><th>Status</th><th></th></tr></thead>
            <tbody>{staff.map(u => <tr key={u.id}>
              <td><div className="row" style={{ gap: 10 }}><Avatar name={u.name} size={34} /><div>
                <button className="link-btn" onClick={() => profile(u)}>{u.name}</button>{u.emp_code && <span className="mono faint" style={{ marginLeft: 6 }}>{u.emp_code}</span>}
                <div className="cell-sub">{u.email}</div><Presence p={pres[String(u.id)]} /></div></div></td>
              <td><Pill tone="accent">{roleName(u.role)}</Pill>{u.also_team_lead && u.role !== 'teamlead' && <Pill tone="info">+TL</Pill>}
                {u.also_field_agent && u.role !== 'fos' && <Pill tone="info">+FOS</Pill>}{u.also_caller && u.role !== 'telecaller' && <Pill tone="info">+Caller</Pill>}
                {u.also_team_follower && u.role !== 'teamfollower' && <Pill tone="info">+Field TL</Pill>}</td>
              <td className="muted" style={{ maxWidth: 200 }}>{(u.banks || []).join(', ') || '—'}</td>
              <td><Pill tone={u.is_active ? 'good' : 'bad'} dot>{u.is_active ? 'active' : 'inactive'}</Pill>{u.employment_type && <div className="cell-sub">{u.employment_type}</div>}</td>
              <td><div className="row wrap" style={{ gap: 6, justifyContent: 'flex-end' }}>
                {(u.role === 'teamlead' || u.also_team_lead) && <button className="btn sm primary" onClick={() => panel('tlOverview', { lead: u })}><Users2 />Team</button>}
                {(u.role === 'fos' || u.role === 'telecaller') && <button className="btn sm" onClick={() => panel('perf', { u })}><LineChart />Performance</button>}
                {u.role === 'fos' && <button className="btn sm" onClick={() => panel('liveRoute', { officer: u })} title="Today's live route"><MapPin />Live</button>}
                {u.role === 'fos' && <button className="btn sm" onClick={() => panel('routeHistory', { officer: u })} title="Route history"><History />History</button>}
                <button className="btn sm ghost" title="Edit" onClick={() => panel('staff', { editing: u, presetBranch: openBranch }).then(ok => ok && reload())}><Pencil /></button>
                {u.id !== user.id && (u.is_active === false
                  ? <button className="btn sm ghost" title="Restore" style={{ color: 'var(--good)' }} onClick={() => toggleStaff(u)}><RotateCcw /></button>
                  : <button className="btn sm ghost danger" title="Remove" onClick={() => toggleStaff(u)}><UserMinus /></button>)}
              </div></td>
            </tr>)}</tbody></table></div>}
      </Card>

      {associates.length > 0 && (brRole === 'all' || brRole === 'fos') && <Card title="Field officers working this branch" sub="Based elsewhere · assigned to this branch’s cases" pad={false} className="rise" style={{ marginTop: 16 }}>
        <div className="table-wrap"><table className="t">
          <thead><tr><th>Employee</th><th>Home branch</th><th className="r">Cases here</th><th className="r">Paid</th><th className="r">Recovered</th><th className="r">Pending</th><th></th></tr></thead>
          <tbody>{associates.map(a => <tr key={a.id}>
            <td><div className="row" style={{ gap: 10 }}><Avatar name={a.name} size={30} /><div><button className="link-btn" onClick={() => profile({ ...a, branch: a.home_branch })}>{a.name}</button>
              <div className="cell-sub">{roleName(a.role)}{a.emp_code ? ' · ' + a.emp_code : ''}</div></div></div></td>
            <td className="muted">{a.home_branch}</td><td className="r">{num(a.cases)}</td><td className="r">{num(a.paid)}</td>
            <td className="r" style={{ color: 'var(--good)' }}>{inr(a.received)}</td><td className="r" style={{ color: 'var(--warn)' }}>{inr(a.pending)}</td>
            <td style={{ whiteSpace: 'nowrap' }}><button className="btn sm" onClick={() => profile({ ...a, branch: a.home_branch })}><LineChart />Performance</button> <ContactBtns phone={a.phone} compact /></td>
          </tr>)}</tbody></table></div>
      </Card>}
    </>
  );
}

// Navigation. The source of truth is the classic app's own menu (role- and Services-filtered),
// read live from the embedded classic runtime — so every role sees exactly the same screens as
// the classic UI and nothing is ever left out. A static copy is used only for the first second
// while the runtime boots.
//
// Screens rebuilt natively open at "/<id>"; every other screen opens at "/m/<id>", which shows the
// full classic module inside the new frame (same features, new skin).
import {
  LayoutDashboard, FolderKanban, Table2, Handshake, Flag, Scale, MapPinned, History, ScrollText, Archive,
  Users, UserCog, FileEdit, LineChart, Landmark, Palmtree, MessageSquare, Smartphone, Sparkles, Lock,
  Trophy, Phone, Clock, IdCard, Wallet, LifeBuoy, Plug, Receipt, Briefcase, ListTodo, Target, MonitorDot,
  Puzzle, Settings2, Headset, Users2, Circle,
} from 'lucide-react';

export const ICONS = {
  dashboard: LayoutDashboard, cases: FolderKanban, fcases: FolderKanban, sheet: Table2, ptp: Handshake,
  escalations: Flag, legal: Scale, map: MapPinned, fmap: MapPinned, records: History, audit: ScrollText,
  archive: Archive, staff: Users, manpower: UserCog, preqs: FileEdit, mis: LineChart, feedback: Landmark,
  leave: Palmtree, templates: MessageSquare, devices: Smartphone, ai: Sparkles, security: Lock,
  myperf: Trophy, jointcases: Users2, queue: Phone, tldash: Users, portfolios: Briefcase, profile: IdCard,
  payroll: Wallet, payouts: Wallet, payslips: Receipt, connections: Plug, help: LifeBuoy, support: Headset,
  attendance: Clock, todo: ListTodo, rtsb: Target, monitor: MonitorDot, addons: Puzzle, services: Settings2,
};

export const LABELS = {
  attendance: 'Attendance', todo: 'My Work Queue', rtsb: 'RTSB', monitor: 'Live Monitor', addons: 'Add-ons',
  services: 'Services', help: 'Help & Support', support: 'Support Inbox', profile: 'My E-ID',
};

// Static fallback (mirrors classic NAV) — replaced by the live menu as soon as the runtime is up.
const FALLBACK = {
  admin: 'dashboard cases sheet ptp escalations legal map records audit archive staff manpower preqs mis feedback leave templates devices ai connections payroll security',
  manager: 'dashboard cases ptp escalations legal map records audit staff manpower mis feedback leave templates devices ai security',
  fos: 'dashboard myperf fcases jointcases fmap leave ai security',
  telecaller: 'dashboard myperf queue sheet feedback ptp leave ai security',
  teamlead: 'tldash portfolios cases mis ptp escalations audit feedback leave ai security',
  backend: 'dashboard cases escalations mis feedback leave ai security',
  headoffice: 'dashboard cases sheet ptp escalations map records audit staff manpower mis feedback leave ai connections security',
  hr: 'manpower preqs leave payroll profile security',
  it: 'attendance profile leave security',
  staff: 'attendance profile leave security',
};
const FALLBACK_LABEL = {
  dashboard: 'Dashboard', cases: 'Accounts', fcases: 'My Accounts', sheet: 'Live Sheet', ptp: 'PTP Tracker',
  escalations: 'Escalations', legal: 'Litigation', map: 'Field Tracking', fmap: 'Field Tracking', records: 'Activity',
  audit: 'Audit Log', archive: 'Monthly Archive', staff: 'Team', manpower: 'Manpower', preqs: 'Change Requests',
  mis: 'MIS', feedback: 'Bank Feedback', leave: 'Leave', templates: 'Communication', devices: 'Devices',
  ai: 'AI Assist', security: 'Security', myperf: 'My Performance', jointcases: 'Joint Cases', queue: 'Calling',
  tldash: 'My Team', portfolios: 'My Portfolios', payroll: 'Salary & Payslips', connections: 'Connections',
  ...LABELS,
};

export const NATIVE_MODULES = ['fcases', 'jointcases', 'queue', 'myperf', 'todo', 'escalations', 'tldash', 'leave', 'preqs', 'devices', 'audit', 'records', 'rtsb', 'monitor'];

const MGMT = ['admin', 'manager', 'headoffice', 'backend', 'it_support_view', 'techsupport'];
/** Which screens have a native (rebuilt) page for this role. Everything else uses the classic module. */
export function nativeFor(user) {
  const r = (user && user.role) || '';
  const s = new Set();
  if (MGMT.includes(r)) { s.add('dashboard'); s.add('cases'); }
  s.add('ptp');
  if (['admin', 'manager', 'headoffice', 'hr', 'it_support_view', 'techsupport'].includes(r)) s.add('attendance');
  // Redesigned modules (round 1). The live classic menu still decides who sees each one.
  NATIVE_MODULES.forEach(id => s.add(id));
  return s;
}

const SECTIONS = [
  ['Overview', ['dashboard', 'tldash', 'myperf', 'support']],
  ['Collections', ['cases', 'fcases', 'portfolios', 'queue', 'sheet', 'ptp', 'jointcases', 'escalations', 'legal', 'feedback']],
  ['Field & people', ['map', 'fmap', 'attendance', 'staff', 'manpower', 'leave', 'preqs', 'payroll', 'payouts', 'payslips', 'profile']],
  ['Insights', ['mis', 'records', 'audit', 'archive']],
  ['Workspace', ['templates', 'ai', 'devices', 'connections', 'security', 'help']],
];

export const routeFor = (id, native) => (native.has(id) ? '/' + id : '/m/' + id);

/** Build sidebar sections from the live classic menu ([[id, emoji, label], …]) or the fallback. */
export function buildNav(user, liveNav) {
  const native = nativeFor(user);
  const role = (user && user.role) || 'telecaller';
  const list = (liveNav && liveNav.length)
    ? liveNav.map(([id, emoji, label]) => ({ id, emoji, label }))
    : [...(FALLBACK[role] || FALLBACK.telecaller).split(' '), 'help'].map(id => ({ id, label: FALLBACK_LABEL[id] || id }));
  const byId = new Map(list.map(x => [x.id, x]));
  const used = new Set();
  const mk = (x) => ({ ...x, icon: ICONS[x.id] || null, to: routeFor(x.id, native) });
  const sections = SECTIONS.map(([title, ids]) => ({
    title, items: ids.filter(id => byId.has(id) && !used.has(id) && used.add(id)).map(id => mk(byId.get(id))),
  }));
  const rest = list.filter(x => !used.has(x.id));
  if (rest.length) sections.push({ title: 'More', items: rest.map(mk) });
  return sections.filter(s => s.items.length);
}

/** Top-bar shortcuts the classic shell offers outside the menu (same role rules). */
export function topExtras(user) {
  const r = (user && user.role) || '';
  const out = [];
  if (['fos', 'telecaller', 'teamlead', 'manager', 'admin', 'headoffice', 'backend'].includes(r)) out.push('todo');
  if (['admin', 'manager', 'headoffice', 'teamlead', 'backend'].includes(r)) out.push('rtsb', 'monitor');
  out.push('attendance');
  return out;
}

export const titleOf = (id, sections) => {
  for (const s of sections || []) for (const i of s.items) if (i.id === id) return i.label;
  return LABELS[id] || FALLBACK_LABEL[id] || id;
};

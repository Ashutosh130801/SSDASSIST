import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { HashRouter, Navigate, Route, Routes, useLocation, useNavigate, useParams } from 'react-router-dom';
import './styles/app.css';
import './styles/surfaces.css';
import './styles/modules.css';
import './styles/clay.css';
import { AuthProvider, useAuth } from './lib/auth.jsx';
import { detectEdition, getMode, setMode } from './lib/edition.js';
import { applyPalette, getPalette, savePalette, shaderPalette, DEFAULT_PALETTE, PALETTES } from './lib/palettes.js';
import { buildNav, nativeFor, routeFor } from './lib/nav.js';
import { ClassicCtx } from './lib/classic.jsx';
import { ToastProvider } from './components/ui.jsx';
import { Backdrop } from './components/fx.jsx';
import ClassicHost from './components/ClassicHost.jsx';
import Shell from './components/Shell.jsx';
import Login from './pages/Login.jsx';
import Dashboard from './pages/Dashboard.jsx';
import Accounts from './pages/Accounts.jsx';
import Ptp from './pages/Ptp.jsx';
import Attendance from './pages/Attendance.jsx';
import ClassicPage from './pages/ClassicPage.jsx';
import MyAccounts from './modules/MyAccounts.jsx';
import JointCases from './modules/JointCases.jsx';
import CallQueue from './modules/CallQueue.jsx';
import MyPerformance from './modules/MyPerformance.jsx';
import Todo from './modules/Todo.jsx';
import Escalations from './modules/Escalations.jsx';
import MyTeam from './modules/MyTeam.jsx';
import Leave from './modules/Leave.jsx';
import { ChangeRequests, Devices, AuditLog, Activity, Rtsb, Monitor } from './modules/Admin.jsx';
import Team from './modules/Team.jsx';
import Mis from './modules/Mis.jsx';
import LiveSheet from './modules/LiveSheet.jsx';
import { Manpower, Profile } from './modules/People.jsx';
import { Feedback, Legal, Templates, Archive, TLPortfolios, Security, Support } from './modules/Ops.jsx';

const edition = detectEdition();

function App() {
  const { user, logout } = useAuth();
  const [mode, setM] = useState(() => getMode(edition));
  const [palette, setPal] = useState(() => getPalette(edition));
  // Theme is applied synchronously so charts (which read live tokens) render in the right colours.
  const root = document.documentElement;
  root.dataset.edition = edition; root.dataset.mode = mode;
  // Sign-in screen always uses the edition's signature blue palette; the user's pick applies once inside.
  const active = user ? palette : DEFAULT_PALETTE[edition];
  useMemo(() => applyPalette(active, mode), [active, mode]);
  useEffect(() => {
    document.title = 'RecoverIQ · Soft Clay';
    setMode(edition, mode); savePalette(edition, palette);
  }, [mode, palette]);

  // Soft Clay: a calm moulded surface with slow floating clay forms (no WebGL — tactile, not flashy).
  const bg = <div className="clay-bg" aria-hidden="true"><i className="c1" /><i className="c2" /><i className="c3" /><i className="c4" /></div>;
  if (!user) return <>{bg}<Login edition={edition} mode={mode} palette={active} onMode={setM} /></>;
  if (user.must_change_password) return <>{bg}<MustChange /></>;
  return <>{bg}<Workspace mode={mode} setM={setM} palette={palette} setPal={setPal} onLogout={logout} /></>;
}

function Workspace({ mode, setM, palette, setPal, onLogout }) {
  const { user } = useAuth();
  const loc = useLocation();
  const navigate = useNavigate();
  const [classicApi, setClassicApi] = useState(null);
  const [liveNav, setLiveNav] = useState(null);
  const navSig = useRef('');
  const native = useMemo(() => nativeFor(user), [user]);
  const sections = useMemo(() => buildNav(user, liveNav), [user, liveNav]);
  const parts = loc.pathname.split('/').filter(Boolean);
  const moduleId = parts[0] === 'm' ? parts[1] : null;
  const locRef = useRef(loc.pathname); locRef.current = loc.pathname;

  const onReady = useCallback((a) => {
    setClassicApi(prev => prev || a);
    const sig = JSON.stringify((a.nav || []).map(n => n[0] + n[2]));
    if (sig !== navSig.current) { navSig.current = sig; setLiveNav(a.nav); }
  }, []);
  // Classic navigated by itself (tour step, in-module link) → follow it.
  const onView = useCallback((v) => {
    if (!v || v === 'none') return;
    const to = routeFor(v, native);
    if (locRef.current !== to) navigate(to);
  }, [native, navigate]);

  // Popups opened from a page belong to that page: close them when the user moves to another screen,
  // and let Escape close them from anywhere in the new UI.
  useEffect(() => { if (classicApi && classicApi.closePanel) { classicApi.closePanel(); if (classicApi.closeCase) classicApi.closeCase(); } }, [loc.pathname]); // eslint-disable-line
  useEffect(() => {
    const k = (e) => { if (e.key === 'Escape' && classicApi && classicApi.closePanel) classicApi.closePanel(); };
    window.addEventListener('keydown', k); return () => window.removeEventListener('keydown', k);
  }, [classicApi]);
  const home = sections[0] && sections[0].items[0] ? sections[0].items[0].to : '/m/dashboard';
  const nativeOr = (id, el) => (native.has(id) ? el : <Navigate to={'/m/' + id} replace />);

  return (
    <ClassicCtx.Provider value={{ api: classicApi, ready: !!classicApi }}>
      <Shell edition={edition} mode={mode} onMode={setM} palette={palette} onPalette={setPal} sections={sections}>
        <Routes>
          <Route path="/dashboard" element={nativeOr('dashboard', <Dashboard key={mode + palette} edition={edition} />)} />
          <Route path="/cases" element={nativeOr('cases', <Accounts />)} />
          <Route path="/ptp" element={nativeOr('ptp', <Ptp />)} />
          <Route path="/attendance" element={nativeOr('attendance', <Attendance />)} />
          <Route path="/fcases" element={nativeOr('fcases', <MyAccounts mapRoute={routeFor('fmap', native)} />)} />
          <Route path="/jointcases" element={nativeOr('jointcases', <JointCases />)} />
          <Route path="/queue" element={nativeOr('queue', <CallQueue />)} />
          <Route path="/myperf" element={nativeOr('myperf', <MyPerformance />)} />
          <Route path="/todo" element={nativeOr('todo', <Todo />)} />
          <Route path="/escalations" element={nativeOr('escalations', <Escalations />)} />
          <Route path="/tldash" element={nativeOr('tldash', <MyTeam />)} />
          <Route path="/leave" element={nativeOr('leave', <Leave />)} />
          <Route path="/preqs" element={nativeOr('preqs', <ChangeRequests />)} />
          <Route path="/devices" element={nativeOr('devices', <Devices />)} />
          <Route path="/audit" element={nativeOr('audit', <AuditLog />)} />
          <Route path="/records" element={nativeOr('records', <Activity />)} />
          <Route path="/rtsb" element={nativeOr('rtsb', <Rtsb />)} />
          <Route path="/monitor" element={nativeOr('monitor', <Monitor />)} />
          <Route path="/staff" element={nativeOr('staff', <Team />)} />
          <Route path="/mis" element={nativeOr('mis', <Mis />)} />
          <Route path="/sheet" element={nativeOr('sheet', <LiveSheet />)} />
          <Route path="/manpower" element={nativeOr('manpower', <Manpower />)} />
          <Route path="/profile" element={nativeOr('profile', <Profile />)} />
          <Route path="/feedback" element={nativeOr('feedback', <Feedback />)} />
          <Route path="/legal" element={nativeOr('legal', <Legal />)} />
          <Route path="/templates" element={nativeOr('templates', <Templates />)} />
          <Route path="/archive" element={nativeOr('archive', <Archive />)} />
          <Route path="/portfolios" element={nativeOr('portfolios', <TLPortfolios />)} />
          <Route path="/security" element={nativeOr('security', <Security />)} />
          <Route path="/help" element={nativeOr('help', <Support />)} />
          <Route path="/support" element={nativeOr('support', <Support />)} />
          <Route path="/m/:id" element={<ClassicRoute />} />
          <Route path="*" element={<Navigate to={home} replace />} />
        </Routes>
      </Shell>
      <ClassicHost user={user} mode={mode} palette={palette} moduleId={moduleId}
        onReady={onReady} onView={onView} onLogout={onLogout} />
    </ClassicCtx.Provider>
  );
}

function ClassicRoute() {
  const { id } = useParams();
  return <ClassicPage id={id} />;
}

function MustChange() {
  return (
    <div className="center-screen">
      <div className="card" style={{ maxWidth: 440, padding: 28 }}>
        <h2 style={{ marginTop: 0 }}>Set a new password first</h2>
        <p className="muted">Your account is using a temporary password. Change it once in the classic screen, then come back here.</p>
        <a className="btn primary" href="/">Change password</a>
      </div>
    </div>
  );
}

createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <HashRouter>
      <AuthProvider>
        <ToastProvider><App /></ToastProvider>
      </AuthProvider>
    </HashRouter>
  </React.StrictMode>
);

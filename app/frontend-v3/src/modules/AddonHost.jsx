// One add-on's workspace at /addons/:key — native where rebuilt, otherwise the classic add-on inside this theme.
import React, { useEffect } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { ArrowLeft, Puzzle } from 'lucide-react';
import { api } from '../lib/api.js';
import { useAuth } from '../lib/auth.jsx';
import { Empty, Skeleton, useLoad } from '../components/ui.jsx';
import { ModuleHead } from './kit.jsx';
import { AddonCompliance, AddonPayments, AddonOutreach } from './AddonsA.jsx';
import { AddonSettlement, AddonSmart, AddonNotices } from './AddonsB.jsx';
import { AddonAnalytics, AddonBilling, AddonSkipTrace, AddonOpenApi } from './AddonsC.jsx';

export const ADDON_ROLES = {
  ai_assist: null, payments: null, settlement: null, skip_tracing: ['admin', 'headoffice', 'manager', 'teamlead', 'fos', 'telecaller'],
  compliance: ['admin', 'headoffice', 'manager', 'hr'], outreach: ['admin', 'headoffice', 'manager'],
  smart_allocation: ['admin', 'headoffice', 'manager', 'teamlead', 'fos'], legal_notices: ['admin', 'headoffice', 'manager'],
  analytics: ['admin', 'headoffice', 'manager', 'teamlead'], billing: ['admin', 'headoffice'], open_api: ['admin'],
};
export const NATIVE_ADDONS = {
  compliance: AddonCompliance, payments: AddonPayments, outreach: AddonOutreach,
  settlement: AddonSettlement, smart_allocation: AddonSmart, legal_notices: AddonNotices,
  analytics: AddonAnalytics, billing: AddonBilling, skip_tracing: AddonSkipTrace, open_api: AddonOpenApi,
};

export default function AddonHost() {
  const { key } = useParams();
  const { user } = useAuth();
  const nav = useNavigate();
  const { data } = useLoad(() => api('/api/services'), []);
  const Native = NATIVE_ADDONS[key];
  useEffect(() => {
    if (key === 'ai_assist') { nav('/ai', { replace: true }); return; }
    if (!Native) { try { sessionStorage.setItem('riq_addon', key); } catch (e) { /* ignore */ } nav('/m/addons', { replace: true }); }
  }, [key]);
  if (!Native) return null;
  const list = Array.isArray(data) ? data : (data && data.services) || [];
  const s = list.find(x => x.key === key);
  const roles = ADDON_ROLES[key];
  const allowed = !roles || roles.includes(user.role);
  return <>
    <ModuleHead icon={Puzzle} title={s ? s.name : 'Add-on'} sub={s ? s.desc : ''}>
      <button className="btn ghost sm" onClick={() => nav('/addons')}><ArrowLeft size={15} />All add-ons</button>
    </ModuleHead>
    {!data ? <Skeleton h={200} style={{ borderRadius: 16 }} />
      : !s || !s.enabled || s.reminder ? <Empty icon={Puzzle} title="This add-on is turned off">{user.role === 'admin' ? 'Switch it on in Services.' : 'Ask your administrator to switch it on.'}</Empty>
      : !allowed ? <Empty icon={Puzzle} title="Not available for your role" />
      : <div className="addon-ws"><Native user={user} /></div>}
  </>;
}

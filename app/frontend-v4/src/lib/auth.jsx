import React, { createContext, useContext, useEffect, useState, useCallback } from 'react';
import { api, session } from './api.js';

const Ctx = createContext(null);
export const useAuth = () => useContext(Ctx);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(() => (session.token ? session.user : null));
  const [config, setConfig] = useState(null);

  useEffect(() => { api('/api/config', { auth: false }).then(setConfig).catch(() => setConfig({})); }, []);
  // Refresh the profile once (role/view may have changed in the classic UI).
  useEffect(() => {
    if (!session.token) return;
    api('/api/auth/me').then(u => { session.user = u; setUser(u); }).catch(() => {});
  }, []);
  useEffect(() => {
    const h = () => setUser(null);
    window.addEventListener('riq:logout', h);
    return () => window.removeEventListener('riq:logout', h);
  }, []);

  const login = useCallback(async ({ email, password, otp }) => {
    const body = { email, password, device_id: session.deviceId, device_label: (navigator.userAgent || 'browser').slice(0, 140) };
    if (otp) body.otp = otp;
    const r = await api('/api/auth/login-json', { auth: false, body });
    session.token = r.access_token; session.user = r.user; setUser(r.user);
    return r.user;
  }, []);

  const logout = useCallback(() => { session.token = ''; session.user = null; setUser(null); }, []);

  const switchView = useCallback(async (view) => {
    const r = await api('/api/auth/switch-view', { method: 'POST', body: { view } });
    session.token = r.access_token; if (r.user) { session.user = r.user; setUser(r.user); }
    else { const u = await api('/api/auth/me'); session.user = u; setUser(u); }
  }, []);

  return <Ctx.Provider value={{ user, config, login, logout, switchView }}>{children}</Ctx.Provider>;
}

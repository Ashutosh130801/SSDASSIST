import React, { useEffect, useState } from 'react';
import { Lock, Mail, ShieldCheck, ArrowRight, MapPinned, LineChart, Handshake, Download, Apple, MonitorDown, Eye, EyeOff, Sun, Moon } from 'lucide-react';
import { useAuth } from '../lib/auth.jsx';
import { LiquidOrb } from '../components/fx.jsx';
import BrandMark from '../components/BrandMark.jsx';
import { RecoverIQMark } from '../components/RecoverIQLogo.jsx';
import { PALETTES } from '../lib/palettes.js';

export default function Login({ edition, palette, mode, onMode }) {
  const { login, config } = useAuth();
  const [email, setEmail] = useState('');
  const [pw, setPw] = useState('');
  const [show, setShow] = useState(false);
  const [otp, setOtp] = useState('');
  const [need2fa, setNeed2fa] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');
  const [dl, setDl] = useState({});
  const brand = (config && config.brand_name) || 'RecoverIQ';
  const premium = edition === 'premium';
  const p = PALETTES[palette] || PALETTES.lagoon;

  useEffect(() => {
    const get = (f) => fetch('/downloads/' + f, { cache: 'no-store' }).then(r => (r.ok ? r.json() : null)).catch(() => null);
    Promise.all([get('version.json'), get('ios.json'), get('desktop.json')]).then(([a, i, d]) => setDl({ a, i, d }));
  }, []);

  const submit = async (e) => {
    e.preventDefault(); setErr(''); setBusy(true);
    try { await login({ email, password: pw, otp: need2fa ? otp : undefined }); }
    catch (ex) {
      if ((ex.message || '') === '2FA_REQUIRED') { setNeed2fa(true); setErr('Enter the 6-digit code from your authenticator app.'); }
      else setErr(ex.message || 'Sign-in failed');
    } finally { setBusy(false); }
  };

  return (
    <div className="login">
      <div className="login-art">
        <div className="shapes" aria-hidden="true">
          <span className="shape sphere tone-accent" style={{ width: 120, height: 120, left: '8%', top: '18%', animationDelay: '-2s' }} />
          <span className="shape cube tone-violet" style={{ width: 84, height: 84, right: '14%', top: '10%', '--r': '18deg', animationDelay: '-5s' }} />
          <span className="shape pill-s tone-warn" style={{ width: 150, height: 56, left: '20%', bottom: '14%', '--r': '-14deg', animationDelay: '-1s' }} />
          <span className="shape sphere glassy" style={{ width: 70, height: 70, right: '22%', bottom: '24%', animationDelay: '-3.5s' }} />
          <span className="shape cube tone-good" style={{ width: 48, height: 48, left: '46%', top: '8%', '--r': '30deg', animationDelay: '-6s' }} />
        </div>

        <div className="row rise" style={{ gap: 12, position: 'relative' }}>
          <RecoverIQMark size={48} className="login-logo" />
          <div>
            <div className="riq-name" style={{ fontSize: 20 }}>Recover<b>IQ</b></div>
            <div className="faint" style={{ fontSize: 11.5, letterSpacing: '.1em', textTransform: 'uppercase' }}>{premium ? 'Premium edition' : 'Enterprise edition'}</div>
          </div>
        </div>

        <div className="login-hero">
          <LiquidOrb size={230} className="login-orb" colors={[p.charts[0], p.charts[1]]} />
          <div style={{ position: 'relative', maxWidth: 520 }}>
            <div className="login-title rise" style={{ '--i': 1 }}>
              {premium ? <>Recovery,<br /><span className="grad-text">elevated.</span></> : <>Every case tracked.<br /><span className="grad-text">Every rupee recovered.</span></>}
            </div>
            <p className="muted rise" style={{ '--i': 2, fontSize: 15.5, lineHeight: 1.6, marginTop: 18 }}>
              Field recovery with live GPS, tele-calling, PTP tracking, MIS, payroll and payments — one workspace for every branch and portfolio.
            </p>
            <div className="row wrap rise" style={{ '--i': 3, gap: 10, marginTop: 24 }}>
              {[[MapPinned, 'Live field tracking'], [Handshake, 'PTP & payments'], [LineChart, 'Real-time MIS']].map(([I, t]) => (
                <span key={t} className="feature"><I size={15} />{t}</span>
              ))}
            </div>
          </div>
        </div>
        <div className="faint row" style={{ fontSize: 12, position: 'relative', gap: 8 }}><BrandMark size={22} />© {new Date().getFullYear()} SSD Enterprises · Secured with device approval & 2FA</div>
      </div>

      <div className="login-form">
        {onMode && <button type="button" className="icon-btn login-mode" title={mode === 'dark' ? 'Light mode' : 'Dark mode'} aria-label="Toggle theme"
          onClick={() => onMode(mode === 'dark' ? 'light' : 'dark')}>{mode === 'dark' ? <Sun /> : <Moon />}</button>}
        <form className="login-box card rise" style={{ '--i': 2 }} onSubmit={submit}>
          <h1>{premium ? 'Welcome back' : 'Sign in'}</h1>
          <p className="muted" style={{ marginTop: 0, marginBottom: 24 }}>Use the credentials issued by your administrator.</p>
          <label className="label" htmlFor="em">Email</label>
          <div className="input-icon" style={{ marginBottom: 14 }}><Mail /><input id="em" className="input" type="email" autoComplete="username" required value={email} onChange={e => setEmail(e.target.value)} placeholder="name@company.com" /></div>
          <label className="label" htmlFor="pw">Password</label>
          <div className="input-icon" style={{ marginBottom: 14 }}>
            <Lock /><input id="pw" className="input" type={show ? 'text' : 'password'} autoComplete="current-password" required value={pw} onChange={e => setPw(e.target.value)} placeholder="••••••••" style={{ paddingRight: 40 }} />
            <button type="button" className="eye" onClick={() => setShow(s => !s)} aria-label={show ? 'Hide password' : 'Show password'}>{show ? <EyeOff size={16} /> : <Eye size={16} />}</button>
          </div>
          {need2fa && <>
            <label className="label" htmlFor="otp">Authenticator code</label>
            <div className="input-icon" style={{ marginBottom: 14 }}><ShieldCheck /><input id="otp" className="input" inputMode="numeric" maxLength={6} autoFocus value={otp} onChange={e => setOtp(e.target.value.replace(/\D/g, ''))} placeholder="123456" /></div>
          </>}
          {err && <div className="login-err">{err}</div>}
          <button className="btn primary block" disabled={busy} style={{ height: 46, fontSize: 14.5 }}>
            {busy ? 'Signing in…' : <>{need2fa ? 'Verify & sign in' : 'Sign in'}<ArrowRight size={16} /></>}
          </button>
          {(dl.a || dl.i || dl.d) && (
            <div className="row wrap" style={{ gap: 8, marginTop: 16 }}>
              {dl.a && <a className="btn sm" href="/downloads/RecoverIQ-native.apk" download><Download />Android app</a>}
              {dl.i && <a className="btn sm" href="/" title="Install guide on the classic sign-in page"><Apple />iPhone app</a>}
              {dl.d && <a className="btn sm" href={'/downloads/' + (dl.d.file || 'RecoverIQ-desktop.exe')} download><MonitorDown />Windows app</a>}
            </div>
          )}
          <div className="faint" style={{ fontSize: 12.5, marginTop: 16, lineHeight: 1.6 }}>
            New device? Your administrator approves it once. Prefer the current look? <a href="/">Open the classic interface</a>.
          </div>
        </form>
      </div>
    </div>
  );
}

// Floating Messages + AI companion, rebuilt natively for the new UIs (same APIs and behaviour as the classic widgets).
import React, { useEffect, useRef, useState } from 'react';
import { ArrowLeft, Megaphone, MessageCircle, Phone, Plus, Search, Send, Smile, X, PenSquare, Lock, Hourglass, Eye, EyeOff, Drama, CheckCheck } from 'lucide-react';
import { api } from '../lib/api.js';
import { cx, roleName, fmtTime, initials } from '../lib/format.js';
import { useToast } from '../components/ui.jsx';
import { useClassic } from '../lib/classic.jsx';
import { AiMsg } from './Tools.jsx';
import { PETS, Pet, CompanionCard, PetPicker, BotThree } from './Pets.jsx';

/* ═════════════════════════════ Messages ═════════════════════════════ */
const STICKERS = ['chick_hello', 'chick_happy', 'chick_wink', 'chick_love', 'chick_celebrate', 'chick_thinking', 'chick_talking', 'chick_surprised', 'chick_sorry', 'chick_sleepy'];
const stickerOf = (t) => { const m = /^\[sticker:(chick_[a-z]+)\]$/.exec(String(t || '').trim()); return m && STICKERS.includes(m[1]) ? m[1] : null; };
const stickerSrc = (k) => `/assets/stickers/${k}.webp`;
const chatWhen = (iso) => {
  if (!iso) return ''; const d = new Date(/Z|[+-]\d\d:?\d\d$/.test(iso) ? iso : iso + 'Z'); if (isNaN(d)) return '';
  const now = new Date(); const same = d.toDateString() === now.toDateString();
  const y = new Date(now); y.setDate(now.getDate() - 1);
  if (same) return fmtTime(iso); if (d.toDateString() === y.toDateString()) return 'Yesterday';
  return d.toLocaleDateString('en-IN', { day: '2-digit', month: 'short' });
};

function Av({ name, office, size = 40 }) {
  return <div className={cx('fc-av', office && 'office')} style={{ width: size, height: size, flex: `0 0 ${size}px`, fontSize: size * 0.38 }}>
    {office ? <Megaphone size={size * 0.45} /> : initials(name || '?')}</div>;
}

function ConvRow({ onClick, name, office, last, at, unread, sub }) {
  return <button className="fc-row" onClick={onClick}>
    <Av name={name} office={office} />
    <div className="fc-row-b">
      <div className="fc-row-t"><b>{name}</b>{at && <span className={cx('fc-when', unread > 0 && 'hot')}>{chatWhen(at)}</span>}</div>
      <div className="fc-row-t"><span className="fc-last">{(stickerOf(last) ? '🐥 Sticker' : last) || sub}</span>{unread > 0 && <span className="fc-badge">{unread}</span>}</div>
    </div>
  </button>;
}

export function FloatChat({ user }) {
  const toast = useToast();
  const { api: capi } = useClassic();
  const [open, setOpen] = useState(false); const [unread, setUnread] = useState(0);
  const [contacts, setContacts] = useState(null);
  const [active, setActive] = useState(null);            // {id} | 'office'
  const [screen, setScreen] = useState('list');         // list | picker | broadcast
  const [msgs, setMsgs] = useState([]); const [text, setText] = useState('');
  const [q, setQ] = useState(''); const [pq, setPq] = useState(''); const [roleF, setRoleF] = useState('');
  const [bsel, setBsel] = useState([]); const [btext, setBtext] = useState(''); const [bq, setBq] = useState('');
  const [stickers, setStickers] = useState(false);
  const endRef = useRef(null);

  const pollUnread = () => api('/api/chat/unread').then(r => setUnread(r.unread || 0)).catch(() => {});
  const loadContacts = () => api('/api/chat/contacts').then(setContacts).catch(() => setContacts({ contacts: [], roles: [] }));
  useEffect(() => { pollUnread(); const t = setInterval(pollUnread, 15000); return () => clearInterval(t); }, []);
  useEffect(() => { if (!open) return undefined; loadContacts(); const t = setInterval(() => { if (!active) loadContacts(); }, 12000); return () => clearInterval(t); }, [open, active]);
  const loadThread = () => { if (!active) return;
    const p = active === 'office' ? 'office=true' : 'with_id=' + active.id;
    api('/api/chat/thread?' + p).then(r => { setMsgs(r.messages || []); pollUnread(); setTimeout(() => endRef.current && endRef.current.scrollIntoView({ block: 'end' }), 30); }).catch(() => setMsgs([])); };
  useEffect(() => { if (!active) return undefined; loadThread(); const t = setInterval(loadThread, 8000); return () => clearInterval(t); }, [active]);
  useEffect(() => { const k = (e) => { if (e.key === 'Escape' && open) setOpen(false); }; window.addEventListener('keydown', k); return () => window.removeEventListener('keydown', k); }, [open]);

  const openThread = (a) => { setActive(a); setScreen('list'); setMsgs([]); setStickers(false); };
  const post = (b) => { const body = active === 'office' ? { office: true, body: b } : { to_id: active.id, body: b };
    return api('/api/chat/send', { method: 'POST', body }).then(() => { loadThread(); loadContacts(); }).catch(e => toast(e.message || 'Could not send', 'err')); };
  const send = () => { const b = text.trim(); if (!b) return; setText(''); post(b); };
  const sendSticker = (k) => { setStickers(false); post(`[sticker:${k}]`); };
  const requestChat = (c) => api('/api/chat/request', { method: 'POST', body: { to_id: c.id } })
    .then(r => { toast(r.already ? 'You can chat now.' : r.pending ? 'Request already pending.' : 'Request sent to Head Office.'); loadContacts(); })
    .catch(e => toast(e.message || 'Could not send request', 'err'));
  const onPick = (c) => { if (c.locked) { if (!c.pending) requestChat(c); else toast('Request pending Head Office approval.'); return; } openThread({ id: c.id }); };
  const sendBroadcast = () => { const t = btext.trim(); if (!t) { toast('Type a message', 'err'); return; } if (!bsel.length) { toast('Pick at least one person', 'err'); return; }
    api('/api/chat/broadcast', { method: 'POST', body: { to_ids: bsel, body: t } })
      .then(r => { toast(`Broadcast sent to ${r.sent}.`); setScreen('list'); setBsel([]); setBtext(''); setBq(''); loadContacts(); })
      .catch(e => toast(e.message || 'Could not broadcast', 'err')); };
  const call = () => { if (!active || active === 'office') return;
    if (capi && capi.startCall) { setOpen(false); capi.startCall(active.id, activeName); } else toast('Voice calling is starting up — try again in a moment.', 'err'); };

  const roles = (contacts && contacts.roles) || [];
  const all = (contacts && contacts.contacts) || [];
  const office = (contacts && contacts.office) || {};
  const term = q.trim().toLowerCase();
  const convos = all.filter(c => c.last_at && (!term || (c.name || '').toLowerCase().includes(term)));
  const hasOffice = office && office.last_at && (!term || 'office desk'.includes(term));
  const pterm = pq.trim().toLowerCase();
  const pickList = all.filter(c => (!roleF || c.role === roleF) && (!pterm || (c.name || '').toLowerCase().includes(pterm) || (c.emp_code || '').toLowerCase().includes(pterm)));
  const btm = bq.trim().toLowerCase();
  const bList = all.filter(c => !c.locked && (!btm || (c.name || '').toLowerCase().includes(btm) || (c.emp_code || '').toLowerCase().includes(btm)));
  const who = active && active !== 'office' ? all.find(c => c.id === active.id) || {} : {};
  const activeName = active === 'office' ? 'Office desk' : who.name || 'Chat';
  const activeRole = active === 'office' ? 'Broadcast to the whole office' : roleName(who.role || '');

  return <>
    <button className={cx('fc-fab', open && 'on')} data-v2-overlay onClick={() => setOpen(o => !o)} title="Messages" aria-label="Messages">
      {open ? <X /> : <MessageCircle />}{unread > 0 && !open && <span className="fc-fab-n">{unread > 99 ? '99+' : unread}</span>}
    </button>
    {open && <div className="fc-panel" data-v2-overlay role="dialog" aria-label="Messages">
      {active ? <>
        <div className="fc-head">
          <button className="icon-btn" onClick={() => setActive(null)} aria-label="Back"><ArrowLeft /></button>
          <Av name={activeName} office={active === 'office'} size={34} />
          <div className="fc-head-t"><b>{activeName}</b><span>{activeRole}</span></div>
          {active !== 'office' && <button className="icon-btn" title={'Voice call ' + activeName} onClick={call}><Phone /></button>}
          <button className="icon-btn" onClick={() => setOpen(false)} aria-label="Close"><X /></button>
        </div>
        <div className="fc-thread">
          {msgs.length === 0 ? <div className="fc-hint">No messages yet. Say hello 👋</div> :
            msgs.map(m => <div key={m.id} className={cx('fc-msg', m.mine ? 'me' : 'them', stickerOf(m.body) && 'stk')}>
              {!m.mine && active === 'office' && <div className="fc-from">{m.from}</div>}
              {m.kind === 'callback' ? <b>{m.body}</b> : stickerOf(m.body) ? <img src={stickerSrc(stickerOf(m.body))} alt="sticker" /> : m.body}
              <span className="fc-meta">{fmtTime(m.at)}{m.mine && <CheckCheck size={13} className={cx('fc-tick', m.read && 'read')} />}</span>
            </div>)}
          <div ref={endRef} />
        </div>
        {stickers && <div className="fc-stickers">{STICKERS.map(k => <img key={k} src={stickerSrc(k)} alt={k.replace('chick_', '')} title={k.replace('chick_', '')} onClick={() => sendSticker(k)} />)}</div>}
        <div className="fc-compose">
          <button className={cx('icon-btn', stickers && 'on')} title="Stickers" onClick={() => setStickers(v => !v)}><Smile /></button>
          <input className="input" value={text} placeholder="Type a message" autoFocus onChange={e => setText(e.target.value)} onKeyDown={e => { if (e.key === 'Enter') send(); }} />
          <button className="btn primary fc-send" onClick={send} aria-label="Send"><Send /></button>
        </div>
      </> : screen === 'broadcast' ? <>
        <div className="fc-head">
          <button className="icon-btn" onClick={() => { setScreen('list'); setBq(''); }} aria-label="Back"><ArrowLeft /></button>
          <div className="fc-head-t"><b>Broadcast{bsel.length ? ` · ${bsel.length} selected` : ''}</b><span>Send one message to many people</span></div>
          <button className="icon-btn" onClick={() => setOpen(false)} aria-label="Close"><X /></button>
        </div>
        <div className="fc-search"><Search size={15} /><input value={bq} placeholder="Search people…" onChange={e => setBq(e.target.value)} /></div>
        <div className="fc-sel-row">
          <button className="link-btn" onClick={() => setBsel([...new Set([...bsel, ...bList.map(c => c.id)])])}>Select shown ({bList.length})</button>
          {bsel.length > 0 && <button className="link-btn" onClick={() => setBsel([])}>Clear</button>}
        </div>
        <div className="fc-list">
          {bList.map(c => { const on = bsel.includes(c.id);
            return <button key={c.id} className={cx('fc-row', on && 'sel')} onClick={() => setBsel(on ? bsel.filter(x => x !== c.id) : [...bsel, c.id])}>
              <input type="checkbox" checked={on} readOnly tabIndex={-1} />
              <Av name={c.name} size={34} />
              <div className="fc-row-b"><b>{c.name}</b><span className="fc-last">{roleName(c.role)}{c.emp_code ? ` · ${c.emp_code}` : ''}</span></div>
            </button>; })}
        </div>
        <div className="fc-bfoot">
          <textarea className="input" value={btext} onChange={e => setBtext(e.target.value)} placeholder="Broadcast message…" rows={2} />
          <button className="btn primary" onClick={sendBroadcast}><Send />Send to {bsel.length || 0} {bsel.length === 1 ? 'person' : 'people'}</button>
        </div>
      </> : screen === 'picker' ? <>
        <div className="fc-head">
          <button className="icon-btn" onClick={() => { setScreen('list'); setPq(''); setRoleF(''); }} aria-label="Back"><ArrowLeft /></button>
          <div className="fc-head-t"><b>New chat</b><span>{all.length} contacts</span></div>
          <button className="icon-btn" onClick={() => setOpen(false)} aria-label="Close"><X /></button>
        </div>
        <div className="fc-search"><Search size={15} /><input value={pq} autoFocus placeholder="Search name or ID…" onChange={e => setPq(e.target.value)} /></div>
        <div className="fc-chips">{['', ...roles].map(r => <button key={r || 'all'} className={cx('chip', roleF === r && 'on')} onClick={() => setRoleF(r)}>{r ? roleName(r) : 'All'}</button>)}</div>
        <div className="fc-list">
          <ConvRow onClick={() => openThread('office')} name="Office desk" office last={office.last} at={office.last_at} sub="Broadcast to the whole office" />
          {!contacts ? <div className="fc-hint">Loading…</div> : pickList.length === 0 ? <div className="fc-hint">{pterm || roleF ? 'No one matches that search.' : 'No contacts in your scope yet.'}</div> :
            pickList.map(c => <button key={c.id} className="fc-row" onClick={() => onPick(c)}>
              <Av name={c.name} />
              <div className="fc-row-b"><b>{c.name}</b><span className="fc-last">{roleName(c.role)}{c.emp_code ? ` · ${c.emp_code}` : ''}</span></div>
              {c.locked && <span className={cx('fc-lock', c.pending && 'pending')}>{c.pending ? <><Hourglass size={12} />Requested</> : <><Lock size={12} />Request</>}</span>}
            </button>)}
        </div>
      </> : <>
        <div className="fc-head">
          <div className="fc-head-t"><b className="fc-title">Messages</b><span>{user && user.name}</span></div>
          {contacts && contacts.can_broadcast && <button className="icon-btn" title="Broadcast to selected people" onClick={() => setScreen('broadcast')}><Megaphone /></button>}
          <button className="icon-btn" title="New chat" onClick={() => { setScreen('picker'); loadContacts(); }}><PenSquare /></button>
          <button className="icon-btn" onClick={() => setOpen(false)} aria-label="Close"><X /></button>
        </div>
        <div className="fc-search"><Search size={15} /><input value={q} placeholder="Search chats" onChange={e => setQ(e.target.value)} /></div>
        <div className="fc-list">
          {hasOffice && <ConvRow onClick={() => openThread('office')} name="Office desk" office last={office.last} at={office.last_at} sub="Office broadcast" />}
          {!contacts ? <div className="fc-hint">Loading…</div> :
            (convos.length === 0 && !hasOffice) ? <div className="fc-empty"><MessageCircle size={30} /><b>No conversations yet</b><span>Start one with the button below.</span></div> :
            convos.map(c => <ConvRow key={c.id} onClick={() => openThread({ id: c.id })} name={c.name} last={c.last} at={c.last_at} unread={c.unread} sub={roleName(c.role)} />)}
        </div>
        <button className="fc-new" onClick={() => { setScreen('picker'); loadContacts(); }} title="New chat"><Plus /></button>
      </>}
    </div>}
  </>;
}

/* ═════════════════════════════ AI companion ═════════════════════════════ */
function readPageContext() {
  const clean = s => String(s || '').replace(/[ \t ]+/g, ' ').replace(/\n\s*\n+/g, '\n').trim();
  const vis = el => el && !el.closest('[data-ai-skip]') && el.getClientRects().length > 0;
  const overlays = Array.from(document.querySelectorAll('.modal-v, .drawer')).filter(vis);
  const main = document.querySelector('.content .page') || document.querySelector('.content') || document.getElementById('root');
  const parts = [];
  if (overlays.length) parts.push('[Open window]\n' + overlays.map(o => clean(o.innerText)).join('\n---\n'));
  if (main) parts.push((overlays.length ? '[Page behind]\n' : '') + clean(main.innerText));
  const crumb = document.querySelector('.crumbs b');
  const label = crumb ? clean(crumb.innerText) : document.title;
  const top = overlays[overlays.length - 1] || main;
  const h = top && top.querySelector('h1, h2, h3, .modal-h');
  const path = String(location.pathname || '').replace(/^\/v\d/, '') || '/';
  return { label, ctx: { section: path, title: label + (h ? ' › ' + clean(h.innerText).slice(0, 80) : ''), text: parts.join('\n\n').slice(0, 6000) } };
}

export function FloatBot({ user }) {
  const toast = useToast();
  const { api: capi } = useClassic();
  const [st, setSt] = useState(null);
  const BOT = 76;
  const [pos, setPos] = useState(() => { try { const p = JSON.parse(localStorage.getItem('riq_bot_pos') || 'null'); if (p && p.r >= 0) return p; } catch (e) { /* ignore */ } return { r: 16, b: 136 }; });
  const [open, setOpen] = useState(false); const [busy, setBusy] = useState(false);
  const [mood, setMood] = useState(null);
  const [sleepy, setSleepy] = useState(false); const [dragging, setDragging] = useState(false);
  const [look, setLook] = useState({ x: 0, y: 0 }); const [threeFailed, setThreeFailed] = useState(false);
  const [msgs, setMsgs] = useState([]); const [input, setInput] = useState('');
  const [cid, setCid] = useState(() => { try { return Number(sessionStorage.getItem('riq_bot_cid')) || null; } catch (e) { return null; } });
  const [readOn, setReadOn] = useState(true); const [bubble, setBubble] = useState('');
  const [picking, setPicking] = useState(false); const [task, setTask] = useState(null); const taskT = useRef(0);
  const [pageLabel, setPageLabel] = useState('');
  const petKey = 'riq_pet_' + (user && user.id);
  const [myPet, setMyPet] = useState(() => { try { return localStorage.getItem(petKey) || ''; } catch (e) { return ''; } });
  const drag = useRef(null); const end = useRef(null); const lastAct = useRef(Date.now()); const moodT = useRef(0); const lookHold = useRef(0); const bubbleT = useRef(0);

  const react = (m, ms = 1800, after) => { clearTimeout(moodT.current); setMood(m);
    moodT.current = setTimeout(() => { setMood(after || null); if (after) moodT.current = setTimeout(() => setMood(null), 2200); }, ms); };
  const say = (t, ms = 3500) => { setBubble(t); clearTimeout(bubbleT.current); bubbleT.current = setTimeout(() => setBubble(''), ms); };

  useEffect(() => { api('/api/ai/status').then(setSt).catch(() => setSt({ off: true })); }, []);
  useEffect(() => { if (!st || st.off || !st.bot_enabled) return;
    try { if (!sessionStorage.getItem('riq_bot_hi')) { sessionStorage.setItem('riq_bot_hi', '1');
      const h = new Date().getHours(); const part = h < 12 ? 'Good morning' : h < 17 ? 'Good afternoon' : 'Good evening';
      setTimeout(() => { react('wave', 2200); say(`${part}, ${String(user.name || '').split(' ')[0]}! 👋 Click me for help with this page.`, 6000); }, 900); } } catch (e) { /* ignore */ } }, [st]);
  useEffect(() => { if (open && cid && !msgs.length) api('/api/ai/conversations/' + cid).then(c => setMsgs(c.messages || [])).catch(() => setCid(null)); }, [open]);
  useEffect(() => { try { cid ? sessionStorage.setItem('riq_bot_cid', String(cid)) : sessionStorage.removeItem('riq_bot_cid'); } catch (e) { /* ignore */ } }, [cid]);
  useEffect(() => { end.current && end.current.scrollIntoView && end.current.scrollIntoView({ block: 'end' }); }, [msgs, busy, open]);
  useEffect(() => { if (!open) return undefined; const upd = () => setPageLabel(readPageContext().label); upd(); const t = setInterval(upd, 2000); return () => clearInterval(t); }, [open]);
  useEffect(() => {
    let raf = 0;
    const mv = (e) => { lastAct.current = Date.now();
      setSleepy(s => { if (s) react('happy', 900); return false; });
      if (raf || Date.now() < lookHold.current || e.clientX == null) return; raf = requestAnimationFrame(() => { raf = 0;
        const cx0 = window.innerWidth - pos.r - BOT / 2, cy0 = window.innerHeight - pos.b - BOT / 2;
        const dx = (e.clientX - cx0) / (window.innerWidth / 2), dy = (e.clientY - cy0) / (window.innerHeight / 2);
        setLook({ x: Math.max(-1, Math.min(1, dx)), y: Math.max(-1, Math.min(1, dy)) }); }); };
    window.addEventListener('pointermove', mv); window.addEventListener('keydown', mv);
    return () => { window.removeEventListener('pointermove', mv); window.removeEventListener('keydown', mv); cancelAnimationFrame(raf); };
  }, [pos.r, pos.b]);
  useEffect(() => {
    const t = setInterval(() => {
      if (busy || drag.current) return;
      if (Date.now() - lastAct.current > 60000 && !open) { setSleepy(true); return; }
      if (Math.random() < .35) { const act = Math.random();
        if (act < .5) { lookHold.current = Date.now() + 1400; setLook({ x: Math.random() * 2 - 1, y: Math.random() - .6 }); }
        else if (act < .8) react('hop', 700); else react('happy', 900); }
    }, 7000);
    return () => clearInterval(t);
  }, [busy, open]);
  useEffect(() => { const fit = () => setPos(p => ({ r: Math.min(Math.max(4, p.r), window.innerWidth - BOT - 4), b: Math.min(Math.max(4, p.b), window.innerHeight - BOT - 4) }));
    fit(); window.addEventListener('resize', fit); return () => window.removeEventListener('resize', fit); }, []);

  if (!st || st.off || !st.bot_enabled) return null;
  const canRead = st.bot_read_page !== false;
  const allowPick = st.bot_user_pick !== false;
  const kind = (allowPick && myPet) || st.bot_avatar || 'rivet';
  const flat = kind === 'rivet3d' ? 'rivet' : (PETS[kind] ? kind : 'rivet');
  const state = dragging ? 'drag' : busy ? (task || 'thinking') : mood === 'hop' ? 'idle' : mood || (open && input.trim() ? 'thinking' : (sleepy ? 'sleep' : 'idle'));
  const useThree = kind === 'rivet3d' && !threeFailed;
  const petName = (PETS[kind] || PETS.rivet).name;
  const pickPet = (k) => { setMyPet(k); try { localStorage.setItem(petKey, k); } catch (e) { /* ignore */ } react('happy', 1500); say(`Hi, I'm ${(PETS[k] || PETS.rivet).name}! ✨`, 2500); };

  const onDown = (e) => { e.preventDefault(); drag.current = { x: e.clientX, y: e.clientY, r: pos.r, b: pos.b, moved: false };
    try { e.currentTarget.setPointerCapture(e.pointerId); } catch (err) { /* ignore */ } };
  const onMove = (e) => { const d = drag.current; if (!d) return;
    const dx = e.clientX - d.x, dy = e.clientY - d.y; if (!d.moved && Math.abs(dx) + Math.abs(dy) > 5) { d.moved = true; setDragging(true); }
    if (d.moved) setPos({ r: Math.min(Math.max(4, d.r - dx), window.innerWidth - BOT - 4), b: Math.min(Math.max(4, d.b - dy), window.innerHeight - BOT - 4) }); };
  const onUp = () => { const d = drag.current; drag.current = null; setDragging(false); if (!d) return; lastAct.current = Date.now(); setSleepy(false);
    if (!d.moved) { setOpen(o => { react(o ? 'happy' : 'wink', o ? 1100 : 1500); return !o; }); setBubble(''); }
    else { try { localStorage.setItem('riq_bot_pos', JSON.stringify(pos)); } catch (e) { /* ignore */ } react('happy', 700); } };

  const send = async (text) => {
    const t = (text ?? input).trim(); if (!t || busy) return;
    setMsgs(m => [...m, { role: 'user', content: t }]); setInput(''); setBusy(true); setPicking(false); lastAct.current = Date.now();
    const reading = canRead && readOn; setTask(reading ? 'reading' : 'thinking'); clearTimeout(taskT.current);
    if (reading) taskT.current = setTimeout(() => setTask('thinking'), 1800);
    try {
      const body = { message: t, conversation_id: cid, origin: 'bot' };
      if (reading) body.page_context = readPageContext().ctx;
      const r = await api('/api/ai/chat', { method: 'POST', body });
      setCid(r.conversation_id);
      const full = String(r.reply || '');
      const msg = { role: 'assistant', content: '', typing: true, files: r.files, actions: r.actions, tools: r.tools, visuals: r.visuals, steps: r.steps, suggestions: r.suggestions, timing: r.timing };
      setMsgs(m => [...m, msg]);
      const failed = full.startsWith('⚠️');
      const aiMood = ['celebrate', 'love', 'sorry', 'surprised', 'wink', 'happy'].includes(r.mood) ? r.mood : null;
      const finale = failed || aiMood === 'sorry' ? 'sad' : (aiMood || 'happy');
      failed ? react('sad', 2600) : (r.visuals || []).length ? react('charting', 1600, 'talk') : (r.files || []).length ? react('file', 1600, 'talk') : react('talk', 900, finale);
      await new Promise(done => { let i = 0; const step = Math.max(3, Math.ceil(full.length / 50));
        const iv = setInterval(() => { i += step; msg.content = full.slice(0, i); setMsgs(m => [...m]);
          if (i >= full.length) { clearInterval(iv); msg.content = full; msg.typing = false; setMsgs(m => [...m]); done(); } }, 16); });
      if ((r.visuals || []).length || (r.files || []).length) react(finale, 2200);
      if (!open) say(failed ? 'Hmm, that didn\'t work 😕' : 'Your answer is ready ✨', 3000);
    } catch (e) { setMsgs(m => [...m, { role: 'assistant', content: '⚠️ ' + e.message }]); react('sad', 2600); } finally { setBusy(false); clearTimeout(taskT.current); setTask(null); }
  };
  const confirm = async (a) => { try { await api(`/api/ai/actions/${a.token}/confirm`, { method: 'POST' }); toast('Done ✓'); a.done = true; setMsgs(m => [...m]); react('happy'); } catch (e) { toast(e.message, 'err'); react('sad'); } };
  const openCase = (id) => { if (capi && capi.openCase) { setOpen(false); capi.openCase(id); } };
  const xlsx = async (title, rows) => {
    try { const X = capi && capi.getXLSX ? await capi.getXLSX() : window.XLSX; if (!X) throw new Error('Excel library not loaded');
      const wb = X.utils.book_new(); X.utils.book_append_sheet(wb, X.utils.aoa_to_sheet(rows), 'Data'); X.writeFile(wb, (title || 'ai-data').replace(/[\\/:*?"<>|]/g, '') + '.xlsx');
    } catch (e) { toast(e.message, 'err'); }
  };

  const mobile = window.innerWidth < 640;
  const W = Math.min(420, window.innerWidth - 16), H = Math.min(600, window.innerHeight - 24);
  const botLeft = window.innerWidth - pos.r - BOT, botTop = window.innerHeight - pos.b - BOT;
  let left = botLeft + BOT - W; if (left < 8) left = Math.min(botLeft, window.innerWidth - W - 8);
  let top = botTop - H - 8; if (top < 8) top = Math.min(botTop + BOT + 8, window.innerHeight - H - 8); if (top < 8) top = 8;
  const panelStyle = mobile ? { left: 6, right: 6, bottom: 6, height: '74vh' } : { left: Math.max(8, left), top, width: W, height: H };
  const bubbleLeft = botLeft > window.innerWidth / 2;
  const quick = ['Explain this page', 'What should I do next here?', 'Summarise what I\'m seeing', 'Show this as a chart', 'How do I use this screen?'];
  const avatar = (sz, lk, s) => useThree && sz >= 70 ? <BotThree state={s} look={lk} onFail={() => setThreeFailed(true)} /> : <Pet kind={flat} size={sz} state={s} look={lk} />;
  const status = busy ? (task === 'reading' ? 'Reading the page…' : 'Thinking…')
    : mood === 'charting' ? 'Drawing your chart…' : mood === 'file' ? 'Preparing your file…'
    : canRead ? (readOn ? <>Reading: <b>{pageLabel || 'this page'}</b></> : 'Page reading paused') : 'Page reading off (admin setting)';

  return <>
    <div data-ai-skip="1" data-v2-overlay className={cx('aibot', 'nb-bot', open && 'is-open', mood === 'hop' && 'hop', dragging && 'dragging')} style={{ right: pos.r, bottom: pos.b, width: BOT, height: BOT }}
      onPointerDown={onDown} onPointerMove={onMove} onPointerUp={onUp} onPointerEnter={() => { if (!busy && !open && !mood && !drag.current) react('happy', 1300); }} title={`${petName} — click to chat, drag to move`}>
      {avatar(BOT, look, state)}
      {(bubble || busy) && !open && <div className={cx('nb-hello', !bubbleLeft && 'right')}>{busy ? (task === 'reading' ? 'Reading the page…' : 'Thinking…') : bubble}</div>}
    </div>
    {open && <div data-ai-skip="1" data-v2-overlay className="nb-panel" style={panelStyle} role="dialog" aria-label={petName}>
      <div className="nb-head">
        <button className="nb-mini" title="Change companion" onClick={() => allowPick && setPicking(p => !p)} style={{ cursor: allowPick ? 'pointer' : 'default' }}>
          <Pet kind={flat} size={40} state={state === 'drag' ? 'idle' : state} look={{ x: 0, y: 0 }} /></button>
        <div className="nb-head-t"><b>{petName}</b><span>{status}</span></div>
        {allowPick && <button className={cx('icon-btn', picking && 'on')} title="Choose your companion" onClick={() => setPicking(p => !p)}><Drama /></button>}
        {canRead && <button className={cx('icon-btn', readOn && 'on')} title={readOn ? 'Stop reading the page' : 'Read the open page'} onClick={() => setReadOn(r => !r)}>{readOn ? <Eye /> : <EyeOff />}</button>}
        <button className="icon-btn" title="New chat" onClick={() => { setMsgs([]); setCid(null); setPicking(false); }}><Plus /></button>
        <button className="icon-btn" title="Close" onClick={() => setOpen(false)}><X /></button>
      </div>
      <div className="nb-body">
        {picking ? <div>
          <CompanionCard kind={kind} state="happy" look={{ x: 0, y: 0 }} status={st} />
          <div className="nb-pick-h">Choose your companion</div>
          <div className="nb-pick-s">It floats on every page and reacts while it works: it thinks, talks, celebrates when an answer lands, and naps when you're away.</div>
          <PetPicker value={kind} onPick={pickPet} allow3d />
          <button className="btn primary" style={{ marginTop: 10, width: '100%' }} onClick={() => setPicking(false)}>Done</button>
        </div> : <>
          {!msgs.length && <div className="nb-empty">
            <CompanionCard kind={kind} state={state === 'drag' ? 'idle' : state} look={look} status={st} onEdit={allowPick ? () => setPicking(true) : null} />
            <b>Hi {String(user.name || '').split(' ')[0]}, I'm {petName}.</b>
            <span>I can see the page you're on{canRead && readOn ? '' : ' (when reading is on)'}, explain it, answer questions about your data, draw charts and guide you step by step.</span>
            <div className="chips nb-quick">{quick.map(x => <button key={x} className="chip" onClick={() => send(x)}>{x}</button>)}</div>
          </div>}
          {msgs.map((m, i) => <AiMsg key={i} m={m} onSend={i === msgs.length - 1 ? send : null} onOpenCase={openCase} onConfirm={confirm} xlsx={xlsx} />)}
          {busy && <div className="ai-bubble bot nb-typing"><span /><span /><span /></div>}
          <div ref={end} />
        </>}
      </div>
      {!picking && <div className="nb-input">
        <input className="input" value={input} autoFocus onChange={e => setInput(e.target.value)} onKeyDown={e => e.key === 'Enter' && send()} placeholder={`Ask ${petName} about this page or anything…`} />
        <button className="btn primary" disabled={busy} onClick={() => send()} aria-label="Send"><Send /></button>
      </div>}
    </div>}
  </>;
}

// Companions for the floating AI bot — the original RecoverIQ characters, ported 1:1 from the classic UI (same art, moods, animations).
import React, { useEffect, useRef, useState } from 'react';
import { cx } from '../lib/format.js';

function PetEyes({ x1, x2, y, rx = 5, ry = 6, look, state, fill = '#1e1b4b', glow }) {
  const th = state === 'thinking', rd = state === 'reading';
  const dx = th ? 2.6 : rd ? 0 : (look.x || 0) * 2.6, dy = th ? -2.6 : rd ? 1.5 : (look.y || 0) * 2;
  if (state === 'love') return <g>{[x1, x2].map(x => <path key={x} transform={`translate(${x} ${y}) scale(${rx / 5})`}
      d="M0 4 C-6 0 -5 -6 -2 -5.5 C-1 -5.3 0 -4.4 0 -3.4 C0 -4.4 1 -5.3 2 -5.5 C5 -6 6 0 0 4Z" fill="#e8284a" stroke="#fff" strokeWidth=".8" />)}</g>;
  if (state === 'happy' || state === 'sleep' || state === 'celebrate') {
    const up = state !== 'sleep';
    return <g>{[x1, x2].map(x => <path key={x} d={up ? `M${x - rx} ${y + 1} Q${x} ${y - ry * 1.1} ${x + rx} ${y + 1}` : `M${x - rx} ${y} Q${x} ${y + ry * .8} ${x + rx} ${y}`}
      fill="none" stroke={fill} strokeWidth="2.6" strokeLinecap="round" style={glow ? { filter: `drop-shadow(0 0 2px ${fill})` } : null} />)}</g>;
  }
  const wide = state === 'drag' || state === 'surprised' ? 1.25 : 1;
  return <g className={cx('pet-eyes', th && 'pet-dart', rd && 'pet-readscan')} style={{ transform: `translate(${dx}px,${dy}px)` }}>
    {[x1, x2].map((x, i) => state === 'wink' && i === 1 ? <path key={i} d={`M${x - rx} ${y + 1} Q${x} ${y - ry * 1.1} ${x + rx} ${y + 1}`} fill="none" stroke={fill} strokeWidth="2.6" strokeLinecap="round" /> : <g key={i}>
      <ellipse className="pet-eye" cx={x} cy={y} rx={rx * wide} ry={ry * wide} fill={fill} style={glow ? { filter: `drop-shadow(0 0 3px ${fill})` } : null} />
      <circle cx={x + rx * .35} cy={y - ry * .38} r={rx * .38} fill="#fff" opacity=".95" />
      {state === 'sad' && <path d={i ? `M${x - rx} ${y - ry - 4} L${x + rx} ${y - ry - 1}` : `M${x - rx} ${y - ry - 1} L${x + rx} ${y - ry - 4}`} stroke={fill} strokeWidth="2" strokeLinecap="round" />}
    </g>)}
  </g>;
}
function PetMouth({ x, y, state, color = '#1e1b4b', w = 7 }) {
  if (state === 'talk') return <ellipse className="pet-talk" cx={x} cy={y + 1} rx={w * .45} ry="3" fill={color} />;
  if (state === 'thinking') return <circle cx={x + 2} cy={y + 1} r="2" fill={color} />;
  if (state === 'happy' || state === 'wave' || state === 'charting' || state === 'file' || state === 'love' || state === 'celebrate') return <path d={`M${x - w * .7} ${y - 1} Q${x} ${y + w} ${x + w * .7} ${y - 1}Z`} fill={color} />;
  if (state === 'sad') return <path d={`M${x - w * .55} ${y + 3} Q${x} ${y - 2} ${x + w * .55} ${y + 3}`} fill="none" stroke={color} strokeWidth="2.2" strokeLinecap="round" />;
  if (state === 'sleep') return <path d={`M${x - 2.5} ${y + 1} h5`} stroke={color} strokeWidth="2" strokeLinecap="round" />;
  if (state === 'drag' || state === 'surprised') return <ellipse cx={x} cy={y + 1} rx="2.6" ry="3.4" fill={color} />;
  return <path d={`M${x - w * .5} ${y} Q${x} ${y + w * .55} ${x + w * .5} ${y}`} fill="none" stroke={color} strokeWidth="2.2" strokeLinecap="round" />;
}
const PetBlush = ({ x1, x2, y, c = '#fb7185' }) => <g opacity=".45">{[x1, x2].map(x => <ellipse key={x} cx={x} cy={y} rx="5" ry="2.8" fill={c} />)}</g>;


/* Holographic human face (original design) — projector base, light cone, wireframe contours and a scan line.
   her = soft violet/pink with long hair; him = cyan/teal with short hair and stronger brows. */
function HoloFace({ s, l, id, her }) {
  const c = her ? '#f0abfc' : '#67e8f9', c2 = her ? '#a78bfa' : '#22d3ee', deep = her ? '#581c87' : '#0e7490';
  const face = 'M50 16 C68 16 75 30 75 44 C75 61 65 76 50 80 C35 76 25 61 25 44 C25 30 32 16 50 16Z';
  const tx = (l.x || 0) * 2.2, ty = (l.y || 0) * 1.4;
  return <>
    <defs>
      <radialGradient id={id + 'hg'} cx=".5" cy=".38" r=".7"><stop offset="0" stopColor={c} stopOpacity=".55" /><stop offset=".7" stopColor={c2} stopOpacity=".22" /><stop offset="1" stopColor={deep} stopOpacity=".08" /></radialGradient>
      <linearGradient id={id + 'hb'} x1="0" y1="1" x2="0" y2="0"><stop offset="0" stopColor={c2} stopOpacity=".55" /><stop offset="1" stopColor={c2} stopOpacity="0" /></linearGradient>
      <clipPath id={id + 'hk'}><path d={face} /></clipPath>
    </defs>
    {/* projector + light cone */}
    <path d="M30 92 L40 70 L60 70 L70 92Z" fill={`url(#${id}hb)`} className="holo-cone" />
    <ellipse cx="50" cy="93" rx="22" ry="4.5" fill={deep} opacity=".85" />
    <ellipse className="holo-base" cx="50" cy="91.5" rx="18" ry="3" fill={c2} />
    <g className="holo-head" style={{ transform: `translate(${tx}px,${ty}px)` }}>
      {her && <path className="holo-hair" d="M50 11 C30 11 20 26 21 46 C22 62 18 74 26 84 C30 74 28 62 30 50 C32 34 40 24 50 22 C60 24 68 34 70 50 C72 62 70 74 74 84 C82 74 78 62 79 46 C80 26 70 11 50 11Z"
        fill={c2} fillOpacity=".28" stroke={c} strokeWidth="1" strokeOpacity=".8" />}
      <path d={face} fill={`url(#${id}hg)`} stroke={c} strokeWidth="1.4" style={{ filter: `drop-shadow(0 0 3px ${c2})` }} />
      <g clipPath={`url(#${id}hk)`} stroke={c} strokeOpacity=".22" strokeWidth=".7" fill="none">
        {[24, 30, 36, 42, 48, 54, 60, 66, 72, 78].map(y => <path key={y} d={`M20 ${y} Q50 ${y + 4} 80 ${y}`} />)}
        <path d="M50 14 V82 M38 16 Q34 48 40 80 M62 16 Q66 48 60 80" />
        <rect className="holo-scan" x="20" y="10" width="60" height="6" fill={c} fillOpacity=".35" stroke="none" />
      </g>
      {!her && <path d="M28 34 C30 18 44 13 52 14 C64 14 73 22 72 35 C66 26 58 23 50 24 C41 24 33 28 28 34Z" fill={c2} fillOpacity=".35" stroke={c} strokeWidth="1" />}
      {her && <path d="M28 36 C32 22 42 17 50 17 C60 17 68 22 72 36 C64 28 58 25 50 26 C42 26 34 30 28 36Z" fill={c2} fillOpacity=".3" stroke={c} strokeWidth=".8" />}
      {/* brows */}
      {s !== 'sleep' && <g stroke={c} strokeWidth={her ? 1.2 : 2} strokeLinecap="round" fill="none" opacity=".9">
        <path d={s === 'sad' ? 'M35 37 Q40 34 45 36' : s === 'thinking' ? 'M35 35 Q40 32 45 35' : 'M35 38 Q40 35 45 38'} />
        <path d={s === 'sad' ? 'M55 36 Q60 34 65 37' : s === 'thinking' ? 'M55 33 Q60 31 65 34' : 'M55 38 Q60 35 65 38'} /></g>}
      <PetEyes x1={40} x2={60} y={44} rx={3.3} ry={her ? 3.9 : 3.5} look={l} state={s} fill="#ecfeff" glow />
      {her && s !== 'sleep' && s !== 'happy' && <g stroke={c} strokeWidth=".9" strokeLinecap="round"><path d="M36 40.5 l-2 -2 M44 40.5 l1.5 -2 M56 40.5 l-1.5 -2 M64 40.5 l2 -2" /></g>}
      <path d="M50 46 Q48.5 54 50.5 56 L52 56" fill="none" stroke={c} strokeWidth="1" strokeOpacity=".8" />
      <PetMouth x={50} y={64} state={s} color={c} w={her ? 7 : 8} />
      {her && <circle cx="25.5" cy="56" r="1.6" fill={c} className="holo-twinkle" />}
      {!her && <path d="M38 70 Q50 77 62 70" fill="none" stroke={c} strokeOpacity=".35" strokeWidth="1" strokeDasharray="1.2 1.6" />}
      {s === 'talk' && <g className="holo-wave" stroke={c} strokeWidth="1.4" strokeLinecap="round">
        {[0, 1, 2, 3, 4].map(i => <path key={i} d={`M${80 + i * 3.2} 62 v-${[3, 7, 10, 6, 3][i]}`} style={{ animationDelay: i * .08 + 's' }} />)}</g>}
    </g>
    {[[18, 30], [84, 24], [14, 62], [86, 70]].map(([x, y], i) => <circle key={i} className="holo-twinkle" cx={x} cy={y} r=".9" fill={c} style={{ animationDelay: i * .5 + 's' }} />)}
  </>;
}


/* Fluffy plush companions (Rui, Lumi, Toffee) — one body, different colours and ears. Fur edge via an SVG noise filter. */
function FluffBall({ s, l, id, c0, c1, c2, limb, feet, ears = 'tufts', eye = '#3b2f2f', blush = '#fda4af', muzzle }) {
  const fur = `url(#${id}rf)`;
  return <>
    <defs>
      <radialGradient id={id + 'rf'} cx=".42" cy=".34" r=".75"><stop offset="0" stopColor={c0} /><stop offset=".6" stopColor={c1} /><stop offset="1" stopColor={c2} /></radialGradient>
      <filter id={id + 'fz'} x="-20%" y="-20%" width="140%" height="140%">
        <feTurbulence type="fractalNoise" baseFrequency="1.1" numOctaves="2" seed="7" result="n" />
        <feDisplacementMap in="SourceGraphic" in2="n" scale="5.5" xChannelSelector="R" yChannelSelector="G" />
      </filter>
    </defs>
    <g filter={`url(#${id}fz)`}>
      {ears === 'tufts' && <><circle className="rui-tuft" cx="35" cy="24" r="8" fill={fur} /><circle className="rui-tuft" cx="65" cy="24" r="8" fill={fur} /></>}
      {ears === 'bunny' && <><g className="fluff-ear-l"><ellipse cx="37" cy="16" rx="7" ry="17" fill={fur} transform="rotate(-12 37 16)" /></g>
        <g className="fluff-ear-r"><ellipse cx="63" cy="16" rx="7" ry="17" fill={fur} transform="rotate(12 63 16)" /></g></>}
      {ears === 'bear' && <><circle className="rui-tuft" cx="28" cy="30" r="10" fill={fur} /><circle className="rui-tuft" cx="72" cy="30" r="10" fill={fur} /></>}
      <ellipse cx="50" cy="56" rx="33" ry="31" fill={fur} />
      <ellipse cx="36" cy="86" rx="8" ry="5" fill={feet} /><ellipse cx="64" cy="86" rx="8" ry="5" fill={feet} />
      <ellipse className="rui-arm-l" cx="19" cy="62" rx="6" ry="9" fill={limb} /><ellipse className="rui-arm-r" cx="81" cy="62" rx="6" ry="9" fill={limb} />
    </g>
    {ears === 'bunny' && <g opacity=".55"><ellipse cx="37" cy="17" rx="3" ry="11" fill="#fbcfe8" transform="rotate(-12 37 17)" /><ellipse cx="63" cy="17" rx="3" ry="11" fill="#fbcfe8" transform="rotate(12 63 17)" /></g>}
    {ears === 'bear' && <g opacity=".6"><circle cx="28" cy="30" r="4.5" fill={c2} /><circle cx="72" cy="30" r="4.5" fill={c2} /></g>}
    {Array.from({ length: 26 }, (_, i) => { const a = i / 26 * Math.PI * 2; const x = 50 + Math.cos(a) * 31, y = 56 + Math.sin(a) * 29;
      return <path key={i} d={`M${x} ${y} l${Math.cos(a) * 3.5} ${Math.sin(a) * 3.5}`} stroke={c0} strokeWidth="1.2" strokeLinecap="round" opacity=".7" />; })}
    <ellipse cx="50" cy="58" rx="19" ry="15" fill={muzzle ? '#fef3e2' : '#ffffff'} opacity={muzzle ? .9 : .5} />
    <PetEyes x1={43} x2={57} y={55} rx={2.6} ry={3.1} look={l} state={s} fill={eye} />
    {muzzle && <ellipse cx="50" cy="60" rx="3" ry="2.2" fill="#3f2a1d" />}
    <PetBlush x1={36} x2={64} y={62} c={blush} />
    <PetMouth x={50} y={muzzle ? 66 : 63} state={s} color={muzzle ? '#3f2a1d' : '#7c2d12'} w={5} /></>;
}

const PETS = {
  aria: { name: 'Aria', tag: 'Her — a holographic guide. Reads, explains, walks you through.', holo: true, draw: (s, l, id) => <HoloFace s={s} l={l} id={id} her />, },
  kabir: { name: 'Kabir', tag: 'Him — a holographic guide. Calm, sharp, straight to the point.', holo: true, draw: (s, l, id) => <HoloFace s={s} l={l} id={id} />, },
  chick: { name: 'Chick', tag: 'The sunny yellow chick. Cheerful, quick, never gives up.', ownFx: true, dom: (s, l, id) => <ChickPet s={s} l={l} id={id} /> },
  bluey: { name: 'Bluey', tag: 'The chick in RecoverIQ blue. Same cheer, office colours.', ownFx: true, dom: (s, l, id) => <ChickPet s={s} l={l} id={id} blue /> },
  rui: { name: 'Rui', tag: 'A soft cotton puffball. Cosy, patient, always happy to help.', fluff: true,
    draw: (s, l, id) => <FluffBall s={s} l={l} id={id} c0="#fffaf3" c1="#f5e6d3" c2="#d9bfa0" limb="#efdcc4" feet="#e8d3b9" ears="tufts" /> },
  lumi: { name: 'Lumi', tag: 'A lavender fluff-bunny. Gentle, curious, hears everything.', fluff: true,
    draw: (s, l, id) => <FluffBall s={s} l={l} id={id} c0="#faf5ff" c1="#e9d5ff" c2="#b794e0" limb="#dcc4f5" feet="#cdb2ef" ears="bunny" eye="#3b0764" blush="#f9a8d4" /> },
  toffee: { name: 'Toffee', tag: 'A caramel fluff-bear. Warm hugs, sharp numbers.', fluff: true,
    draw: (s, l, id) => <FluffBall s={s} l={l} id={id} c0="#fde7c8" c1="#e0a96d" c2="#a8693a" limb="#c98a52" feet="#b9773f" ears="bear" eye="#2b1a12" blush="#fb7185" muzzle /> },
  rivet: { name: 'Rivet', tag: 'The helper robot. Precise, polite, always on duty.', draw: (s, l, id) => <>
    <defs><linearGradient id={id + 'h'} x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor="#fff" /><stop offset="1" stopColor="#cbd5e1" /></linearGradient>
      <linearGradient id={id + 'v'} x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor="#1e3a8a" /><stop offset="1" stopColor="#020617" /></linearGradient></defs>
    <line x1="50" y1="24" x2="50" y2="12" stroke="#94a3b8" strokeWidth="3" strokeLinecap="round" />
    <circle className="pet-bulb" cx="50" cy="10" r="5" fill={s === 'thinking' ? '#f59e0b' : '#60a5fa'} />
    <rect x="13" y="42" width="9" height="18" rx="4.5" fill="#2563eb" /><rect x="78" y="42" width="9" height="18" rx="4.5" fill="#2563eb" />
    <rect x="19" y="22" width="62" height="54" rx="22" fill={`url(#${id}h)`} stroke="#94a3b8" strokeWidth="1.2" />
    <rect x="26" y="32" width="48" height="30" rx="14" fill={`url(#${id}v)`} />
    <PetEyes x1={40} x2={60} y={46} rx={4.6} ry={5.6} look={l} state={s} fill={s === 'thinking' ? '#fbbf24' : '#67e8f9'} glow />
    <PetMouth x={50} y={68} state={s} color="#2563eb" />
    <rect x="35" y="76" width="30" height="9" rx="4.5" fill="#1d4ed8" /></> },
  nova: { name: 'Nova', tag: 'A tiny planet of light. Sees patterns in everything.', draw: (s, l, id) => <>
    <defs><radialGradient id={id + 'o'} cx=".36" cy=".3" r=".8"><stop offset="0" stopColor="#a5f3fc" /><stop offset=".5" stopColor="#6366f1" /><stop offset="1" stopColor="#1e1b4b" /></radialGradient></defs>
    <g transform="rotate(-16 50 54)"><ellipse cx="50" cy="54" rx="45" ry="11" fill="none" stroke="#c4b5fd" strokeWidth="2.5" opacity=".45" /></g>
    <circle cx="50" cy="52" r="30" fill={`url(#${id}o)`} />
    {[[36, 36, 1.2], [64, 40, 1], [58, 70, 1.3], [33, 64, .9], [70, 58, .8], [46, 30, .7]].map(([x, y, r], i) => <circle key={i} className="pet-twinkle" style={{ animationDelay: i * .4 + 's' }} cx={x} cy={y} r={r} fill="#fff" />)}
    <PetEyes x1={41} x2={59} y={50} rx={4.2} ry={5.2} look={l} state={s} fill="#ecfeff" glow />
    <PetMouth x={50} y={62} state={s} color="#ecfeff" />
    <g transform="rotate(-16 50 54)"><path className="pet-ring" d="M5 54 A45 11 0 0 0 95 54" fill="none" stroke="#ddd6fe" strokeWidth="2.8" strokeLinecap="round" /></g></> },
  penny: { name: 'Penny', tag: 'The lucky rupee coin. Counts every collection.', draw: (s, l, id) => <>
    <defs><linearGradient id={id + 'g'} x1="0" y1="0" x2="1" y2="1"><stop offset="0" stopColor="#fef08a" /><stop offset=".5" stopColor="#f59e0b" /><stop offset="1" stopColor="#b45309" /></linearGradient>
      <clipPath id={id + 'c'}><circle cx="50" cy="52" r="32" /></clipPath></defs>
    <circle cx="50" cy="52" r="32" fill={`url(#${id}g)`} stroke="#92400e" strokeWidth="1.2" />
    <circle cx="50" cy="52" r="26.5" fill="none" stroke="#fef3c7" strokeWidth="1.6" strokeDasharray="2 3" opacity=".8" />
    <g clipPath={`url(#${id}c)`}><rect className="pet-shine" x="10" y="0" width="12" height="110" fill="#fff" opacity=".35" transform="rotate(25 50 52)" /></g>
    <text x="50" y="37" textAnchor="middle" fontSize="11" fontWeight="800" fill="#92400e">₹</text>
    <PetEyes x1={41} x2={59} y={51} rx={4} ry={5} look={l} state={s} fill="#78350f" />
    <PetBlush x1={33} x2={67} y={60} c="#f97316" />
    <PetMouth x={50} y={63} state={s} color="#78350f" /></> },
  sikka: { name: 'Sikka', tag: 'A real 3D ₹1 coin — spins, tosses and flips heads & tails.', dom: (s, l, id, size) => <Coin3D state={s} look={l} id={id} size={size} /> },
  mochi: { name: 'Mochi', tag: 'Soft cat-blob. Small paws, big help.', draw: (s, l, id) => <>
    <defs><linearGradient id={id + 'p'} x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor="#fdf2f8" /><stop offset="1" stopColor="#f9a8d4" /></linearGradient></defs>
    <path className="pet-ear-l" d="M25 50 L27 22 L45 38Z" fill="#f9a8d4" /><path className="pet-ear-r" d="M75 50 L73 22 L55 38Z" fill="#f9a8d4" />
    <path d="M29 44 L30 30 L39 38Z" fill="#fbcfe8" /><path d="M71 44 L70 30 L61 38Z" fill="#fbcfe8" />
    <path d="M18 70 Q16 34 50 33 Q84 34 82 70 Q82 86 50 86 Q18 86 18 70Z" fill={`url(#${id}p)`} stroke="#f472b6" strokeWidth="1" />
    <PetEyes x1={40} x2={60} y={58} rx={4} ry={5} look={l} state={s} fill="#4c1d95" />
    <PetBlush x1={31} x2={69} y={66} />
    <g stroke="#db2777" strokeWidth="1" opacity=".5" strokeLinecap="round"><path d="M22 64 h-9 M22 68 l-8 3 M78 64 h9 M78 68 l8 3" /></g>
    <PetMouth x={50} y={69} state={s} color="#9d174d" w={6} /></> },
  sprout: { name: 'Sprout', tag: 'Grows a little with every answer.', draw: (s, l, id) => <>
    <defs><linearGradient id={id + 'b'} x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor="#bbf7d0" /><stop offset="1" stopColor="#16a34a" /></linearGradient></defs>
    <g className="pet-leaf"><path d="M50 30 Q50 22 50 17" stroke="#15803d" strokeWidth="2.5" fill="none" strokeLinecap="round" />
      <path d="M50 19 Q38 8 28 16 Q38 26 50 19Z" fill="#4ade80" /><path d="M50 19 Q62 6 74 13 Q64 25 50 19Z" fill="#22c55e" /></g>
    <path d="M28 52 Q28 30 50 30 Q72 30 72 52 L72 68 Q72 86 50 86 Q28 86 28 68Z" fill={`url(#${id}b)`} />
    <PetEyes x1={42} x2={58} y={55} rx={3.8} ry={4.8} look={l} state={s} fill="#052e16" />
    <PetBlush x1={35} x2={65} y={63} c="#f472b6" />
    <PetMouth x={50} y={66} state={s} color="#052e16" w={6} /></> },
  owlie: { name: 'Owlie', tag: 'The wise night-shift owl. Never misses a PTP.', draw: (s, l, id) => <>
    <defs><linearGradient id={id + 'w'} x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor="#2dd4bf" /><stop offset="1" stopColor="#115e59" /></linearGradient></defs>
    <path d="M24 34 L22 18 L36 28Z M76 34 L78 18 L64 28Z" fill="#0f766e" />
    <ellipse cx="50" cy="56" rx="31" ry="31" fill={`url(#${id}w)`} />
    <ellipse cx="50" cy="68" rx="18" ry="15" fill="#ccfbf1" />
    {[36, 52, 64].map((y, i) => <path key={i} d={`M${44 - i} ${y + 8} q3 3 6 0 M${50 + i} ${y + 8} q3 3 6 0`} stroke="#5eead4" strokeWidth="1" fill="none" opacity=".7" />)}
    <circle cx="38" cy="47" r="11" fill="#fff" stroke="#f59e0b" strokeWidth="2" /><circle cx="62" cy="47" r="11" fill="#fff" stroke="#f59e0b" strokeWidth="2" />
    <PetEyes x1={38} x2={62} y={47} rx={4.6} ry={4.6} look={l} state={s} fill="#0f172a" />
    <path className="pet-beak" d={s === 'talk' || s === 'happy' ? 'M45 56 L55 56 L50 64Z' : 'M46 56 L54 56 L50 62Z'} fill="#f59e0b" />
    <path d="M40 86 v4 M44 86 v4 M56 86 v4 M60 86 v4" stroke="#f59e0b" strokeWidth="2.4" strokeLinecap="round" /></> },
  puff: { name: 'Puff', tag: 'A calm little cloud. Clears up any doubt.', draw: (s, l, id) => <>
    <defs><linearGradient id={id + 'c'} x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor="#fff" /><stop offset="1" stopColor="#bfdbfe" /></linearGradient></defs>
    {s === 'happy' && <g fill="none" strokeWidth="3" strokeLinecap="round" opacity=".85">
      {['#f87171', '#fbbf24', '#34d399', '#60a5fa'].map((c, i) => <path key={c} d={`M${18 + i * 4} 48 A${32 - i * 4} ${30 - i * 4} 0 0 1 ${82 - i * 4} 48`} stroke={c} />)}</g>}
    <g fill={`url(#${id}c)`} style={{ filter: 'drop-shadow(0 2px 2px rgba(59,130,246,.25))' }}>
      <circle cx="32" cy="60" r="16" /><circle cx="50" cy="48" r="21" /><circle cx="69" cy="58" r="17" /><rect x="22" y="58" width="58" height="22" rx="11" /></g>
    <PetEyes x1={42} x2={58} y={58} rx={3.6} ry={4.6} look={l} state={s} fill="#1e3a8a" />
    <PetBlush x1={34} x2={66} y={66} c="#93c5fd" />
    <PetMouth x={50} y={68} state={s} color="#1e3a8a" w={6} />
    {s === 'thinking' && <path className="pet-drop" d="M50 84 q-3 5 0 7 q3 -2 0 -7Z" fill="#60a5fa" />}</> },
  ember: { name: 'Ember', tag: 'A warm spark. Fast answers, never burns out.', draw: (s, l, id) => <>
    <defs><linearGradient id={id + 'f'} x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor="#fde047" /><stop offset=".55" stopColor="#fb923c" /><stop offset="1" stopColor="#dc2626" /></linearGradient></defs>
    <g className="pet-flicker">
      <path d="M50 12 C63 30 79 40 75 62 C72 80 61 88 50 88 C39 88 28 80 25 62 C22 46 37 38 40 25 C44 33 47 35 50 12Z" fill={`url(#${id}f)`} />
      <path d="M50 44 C57 52 63 58 61 69 C59 78 55 82 50 82 C45 82 40 78 39 69 C38 60 45 56 50 44Z" fill="#fef3c7" opacity=".55" /></g>
    <PetEyes x1={42} x2={58} y={62} rx={3.8} ry={4.8} look={l} state={s} fill="#7c2d12" />
    <PetMouth x={50} y={73} state={s} color="#7c2d12" w={6} /></> },
};
const PET_KEYS = Object.keys(PETS);

/* Task / mood effects drawn around any companion (shared by SVG and 3D companions). */
function PetFx({ state }) {
  return <>
    {state === 'thinking' && <g className="pet-think">{[[80, 26, 2.4], [87, 17, 3.2], [92, 7, 4]].map(([x, y, r], i) => <circle key={i} cx={x} cy={y} r={r} fill="#94a3b8" style={{ animationDelay: i * .18 + 's' }} />)}</g>}
    {state === 'happy' && <g className="pet-sparks">{[[12, 20], [88, 18], [8, 70], [92, 66]].map(([x, y], i) =>
      <path key={i} d={`M${x} ${y - 6} L${x + 1.6} ${y - 1.6} L${x + 6} ${y} L${x + 1.6} ${y + 1.6} L${x} ${y + 6} L${x - 1.6} ${y + 1.6} L${x - 6} ${y} L${x - 1.6} ${y - 1.6}Z`} fill={['#fbbf24', '#60a5fa', '#f472b6', '#34d399'][i]} style={{ animationDelay: i * .15 + 's' }} />)}</g>}
    {state === 'sleep' && <g className="pet-zzz" fill="#64748b" fontWeight="800"><text x="76" y="24" fontSize="10">z</text><text x="84" y="13" fontSize="13">z</text></g>}
    {state === 'sad' && <path d="M76 30 q-4 6 0 8 q4 -2 0 -8Z" fill="#60a5fa" />}
    {state === 'reading' && <g className="pet-task pet-doc"><rect x="80" y="30" width="16" height="20" rx="2.5" fill="#fff" stroke="#94a3b8" />
      {[35, 39, 43].map(y => <path key={y} d={`M83 ${y} h10`} stroke="#cbd5e1" strokeWidth="1.4" />)}<rect className="pet-docscan" x="81" y="31" width="14" height="2" fill="#3b82f6" opacity=".7" /></g>}
    {state === 'charting' && <g className="pet-task pet-bars">{[[80, 10, '#2563eb'], [86, 16, '#0ea5e9'], [92, 7, '#16a34a']].map(([x, h, c], i) =>
      <rect key={i} x={x} y={50 - h} width="4.5" height={h} rx="1" fill={c} style={{ animationDelay: i * .12 + 's' }} />)}<path d="M78 50.5 h20" stroke="#94a3b8" /></g>}
    {state === 'file' && <g className="pet-task pet-doc"><path d="M81 28 h10 l5 5 v17 h-15Z" fill="#fff" stroke="#16a34a" /><path d="M88 35 v9 M84.5 40.5 l3.5 3.5 3.5 -3.5" stroke="#16a34a" strokeWidth="1.6" fill="none" strokeLinecap="round" /></g>}
    {state === 'wave' && <text className="pet-wave" x="78" y="40" fontSize="15">👋</text>}
    {state === 'wink' && <g className="pet-sparks">{[[84, 30, 5], [92, 44, 3.2], [88, 18, 2.6]].map(([x, y, r], i) =>
      <path key={i} d={`M${x} ${y - r} Q${x + r * .2} ${y - r * .2} ${x + r} ${y} Q${x + r * .2} ${y + r * .2} ${x} ${y + r} Q${x - r * .2} ${y + r * .2} ${x - r} ${y} Q${x - r * .2} ${y - r * .2} ${x} ${y - r}Z`} fill="#fbbf24" style={{ animationDelay: i * .15 + 's' }} />)}</g>}
    {state === 'surprised' && <text className="pet-bang" x="82" y="34" fontSize="22" fontWeight="900" fill="#2563eb" stroke="#fff" strokeWidth="1.5" paintOrder="stroke">!</text>}
    {state === 'love' && <g className="pet-hearts">{[[84, 26, 1.1], [92, 12, .8], [12, 22, .9]].map(([x, y, k], i) =>
      <path key={i} transform={`translate(${x} ${y}) scale(${k})`} d="M0 4 C-6 0 -5 -6 -2 -5.5 C-1 -5.3 0 -4.4 0 -3.4 C0 -4.4 1 -5.3 2 -5.5 C5 -6 6 0 0 4Z" fill="#f0465f" style={{ animationDelay: i * .25 + 's' }} />)}</g>}
    {state === 'celebrate' && <g className="pet-confetti">{[[10, 18, '#2563eb'], [24, 4, '#f472b6'], [78, 6, '#16a34a'], [92, 26, '#f59e0b'], [6, 52, '#8b5cf6'], [94, 52, '#0ea5e9'], [50, -4, '#ef4444'], [66, -2, '#2563eb']].map(([x, y, c], i) =>
      i % 3 === 0 ? <path key={i} d={`M${x} ${y - 4} L${x + 1.2} ${y - 1.2} L${x + 4} ${y} L${x + 1.2} ${y + 1.2} L${x} ${y + 4} L${x - 1.2} ${y + 1.2} L${x - 4} ${y} L${x - 1.2} ${y - 1.2}Z`} fill={c} style={{ animationDelay: i * .1 + 's' }} />
        : <rect key={i} x={x - 3.5} y={y - 1.4} width="7" height="2.8" rx="1.4" fill={c} transform={`rotate(${i * 47} ${x} ${y})`} style={{ animationDelay: i * .1 + 's' }} />)}</g>}
  </>;
}

/* ₹1 coin faces (SVG). Heads: भारत · INDIA + year around a decorative star rosette (the State Emblem is deliberately
   not reproduced — its use is legally restricted). Tails: big ₹1 with रुपया · RUPEE and grain stalks. */
function CoinFace({ id, side }) {
  const yr = new Date().getFullYear();
  const beads = Array.from({ length: 48 }, (_, i) => { const a = i / 48 * Math.PI * 2; return [50 + Math.cos(a) * 44.5, 50 + Math.sin(a) * 44.5]; });
  const stalk = (flip) => <g transform={(flip ? 'translate(100 0) scale(-1 1) ' : '') + 'translate(-5 4) scale(.92)'} fill="none" stroke={`url(#${id}t)`} strokeWidth="1.6" strokeLinecap="round">
    <path d="M30 76 Q20 58 26 34" />
    {[38, 45, 52, 59, 66].map((y, i) => <g key={i}><path d={`M${24.5 - i * .3} ${y} q-5 -2 -6 -7`} /><path d={`M${25.5 - i * .3} ${y} q4 -3 5 -8`} /></g>)}
  </g>;
  return <svg viewBox="0 0 100 100" className="coin-svg">
    <defs>
      <radialGradient id={id + 'm'} cx=".35" cy=".3" r=".85"><stop offset="0" stopColor="#ffffff" /><stop offset=".35" stopColor="#e2e8f0" /><stop offset=".75" stopColor="#94a3b8" /><stop offset="1" stopColor="#64748b" /></radialGradient>
      <linearGradient id={id + 't'} x1="0" y1="0" x2="1" y2="1"><stop offset="0" stopColor="#475569" /><stop offset=".5" stopColor="#1e293b" /><stop offset="1" stopColor="#64748b" /></linearGradient>
      <path id={id + 'top'} d="M18 50 A32 32 0 0 1 82 50" /><path id={id + 'bot'} d="M16 50 A34 34 0 0 0 84 50" />
    </defs>
    <circle cx="50" cy="50" r="49" fill={`url(#${id}m)`} />
    <circle cx="50" cy="50" r="47" fill="none" stroke="#475569" strokeWidth="1.2" opacity=".6" />
    {beads.map(([x, y], i) => <circle key={i} cx={x} cy={y} r=".9" fill="#64748b" opacity=".75" />)}
    <circle cx="50" cy="50" r="41" fill="none" stroke="#cbd5e1" strokeWidth=".8" />
    {side === 'heads' ? <g fill={`url(#${id}t)`}>
      <text fontSize="9" fontWeight="800" letterSpacing="1"><textPath href={`#${id}top`} startOffset="50%" textAnchor="middle">भारत</textPath></text>
      <text fontSize="8" fontWeight="800" letterSpacing="2"><textPath href={`#${id}bot`} startOffset="50%" textAnchor="middle" dominantBaseline="hanging">INDIA</textPath></text>
      <g transform="translate(50 49)" stroke={`url(#${id}t)`} strokeWidth="1.3" fill="none">
        {Array.from({ length: 8 }, (_, i) => <path key={i} transform={`rotate(${i * 45})`} d="M0 -3 C3 -7 3 -12 0 -16 C-3 -12 -3 -7 0 -3Z" />)}
        <circle r="3.2" fill={`url(#${id}t)`} /><circle r="19" strokeWidth=".7" strokeDasharray="1.5 2" />
      </g>
      <text x="50" y="74" textAnchor="middle" fontSize="6" fontWeight="700" letterSpacing=".5">{yr}</text>
    </g> : <g fill={`url(#${id}t)`}>
      {stalk(false)}{stalk(true)}
      <text x="51" y="61" textAnchor="middle" fontSize="28" fontWeight="900" fontFamily="'Space Grotesk',sans-serif" letterSpacing="-1">₹1</text>
      <text fontSize="7.5" fontWeight="800" letterSpacing="1"><textPath href={`#${id}top`} startOffset="50%" textAnchor="middle">रुपया</textPath></text>
      <text fontSize="7" fontWeight="800" letterSpacing="2"><textPath href={`#${id}bot`} startOffset="50%" textAnchor="middle" dominantBaseline="hanging">RUPEE</textPath></text>
    </g>}
    <ellipse className="coin-glint" cx="34" cy="28" rx="16" ry="7" fill="#fff" opacity=".35" transform="rotate(-35 34 28)" />
  </svg>;
}

/* A real 3D coin: two faces + a stack of edge layers, CSS 3D transforms. It spins, tosses and flips. */
function Coin3D({ state, look, id, size }) {
  const t = Math.max(2.5, size / 18);             // half thickness in px
  const layers = 12;
  return <div className="coin3d" style={{ transform: `rotateX(${-(look.y || 0) * 14}deg)` }}>
    <div className="coin3d-spin">
      {Array.from({ length: layers }, (_, i) => <div key={i} className="coin-layer" style={{ transform: `translateZ(${-t + (2 * t) * i / (layers - 1)}px)` }} />)}
      <div className="coin-face front" style={{ transform: `translateZ(${t + .3}px)` }}><CoinFace id={id + 'H'} side="heads" /></div>
      <div className="coin-face back" style={{ transform: `rotateY(180deg) translateZ(${t + .3}px)` }}><CoinFace id={id + 'T'} side="tails" /></div>
    </div>
  </div>;
}


/* 🐥 Chick companions — your kit's rendered 3D images (yellow original + app-blue recolour) with blink frames;
   a vector chick is drawn instead if an image can't load. */
const PET_TASK_FX = ['reading', 'charting', 'file', 'wave'];
const CHICK_MOOD = { idle: 'hello', wave: 'hello', reading: 'thinking', thinking: 'thinking', talk: 'talking', happy: 'happy', charting: 'happy',
  file: 'happy', sad: 'sorry', sleep: 'sleepy', drag: 'surprised', wink: 'wink', surprised: 'surprised', love: 'love', celebrate: 'celebrate' };
function ChickVector({ s, l, id, blue }) {
  const c0 = blue ? '#bfe0ff' : '#fff38a', c1 = blue ? '#5aa9f5' : '#ffdf1f', c2 = blue ? '#2f7fd6' : '#f2b705';
  return <svg viewBox="0 0 100 100" className="pet-svg"><defs>
      <radialGradient id={id + 'cb'} cx=".4" cy=".3" r=".75"><stop offset="0" stopColor={c0} /><stop offset=".45" stopColor={c1} /><stop offset="1" stopColor={c2} /></radialGradient></defs>
    <g className="pet-body">
      <path d="M46 18 C43 10 45 5 48 7 C48.5 3 52 2 52.5 7 C55 3 59 5 56 12 C60 10 61 14 56 18Z" fill={`url(#${id}cb)`} />
      <ellipse cx="50" cy="55" rx="38" ry="38" fill={`url(#${id}cb)`} />
      <ellipse cx="17" cy="66" rx="6" ry="13" transform="rotate(16 17 66)" fill={c1} /><ellipse cx="83" cy="66" rx="6" ry="13" transform="rotate(-16 83 66)" fill={c1} />
      <path d="M38 92 l-3 5 M42 92 v6 M58 92 v6 M62 92 l3 5" stroke="#f38a1c" strokeWidth="2.6" strokeLinecap="round" />
      <PetEyes x1={36} x2={64} y={50} rx={5.5} ry={6.2} look={l} state={s} fill="#3d1d07" />
      <PetBlush x1={25} x2={75} y={62} c="#ff8a8a" />
      <path d="M50 56 C55 56 58 61 57.5 64 C57 67 54 68 50 68 C46 68 43 67 42.5 64 C42 61 45 56 50 56Z" fill="#f38a1c" />
      {s === 'talk' && <ellipse className="pet-talk" cx="50" cy="69" rx="3.5" ry="2" fill="#5a160a" />}
    </g>{!PET_TASK_FX.includes(s) && <PetFx state={s} />}</svg>;
}
function ChickPet({ s, l, id, blue }) {
  const [broken, setBroken] = useState(false); const [blink, setBlink] = useState(false);
  const mood = CHICK_MOOD[s] || 'hello';
  useEffect(() => { if (!['hello', 'talking', 'thinking'].includes(mood)) return;
    const t = setInterval(() => { setBlink(true); setTimeout(() => setBlink(false), 140); }, 4200 + Math.random() * 900);
    return () => clearInterval(t); }, [mood]);
  if (broken) return <ChickVector s={s} l={l} id={id} blue={blue} />;
  const dir = blue ? 'blue' : 'yellow';
  return <div className="chick-img" style={{ transform: `rotateY(${(l.x || 0) * 10}deg) rotateX(${-(l.y || 0) * 6}deg)` }}>
    <img alt="" draggable="false" src={`/assets/chick/${dir}/chick_${blink ? 'blink' : mood}.webp`} onError={() => setBroken(true)} />
  </div>;
}

function Pet({ kind, state = 'idle', look = { x: 0, y: 0 }, size = 76 }) {
  const P = PETS[kind] || PETS.rivet;
  const id = 'pt' + String(React.useId ? React.useId() : Math.random()).replace(/[^a-zA-Z0-9]/g, '');
  const k = PETS[kind] ? kind : 'rivet';
  if (P.dom) return <div className={cx('pet', 'pet-' + k, 'pet-dom', 's-' + state)} style={{ width: size, height: size }}>
    <div className="pet-body">{P.dom(state, look, id, size)}</div>
    {(!P.ownFx || PET_TASK_FX.includes(state)) && <svg viewBox="0 0 100 100" className="pet-fx"><PetFx state={state} /></svg>}
    <div className="pet-shadow" />
  </div>;
  return <div className={cx('pet', 'pet-' + k, P.holo && 'pet-holo', P.fluff && 'pet-fluff', 's-' + state)} style={{ width: size, height: size }}>
    <svg viewBox="0 0 100 100" className="pet-svg" style={{ transform: `rotateY(${look.x * 14}deg) rotateX(${-look.y * 10}deg)` }}>
      <g className="pet-body">{P.draw(state, look, id)}</g>
      <PetFx state={state} />
    </svg>
    <div className="pet-shadow" />
  </div>;
}


/* Profile card for the chosen companion: big round avatar, name, connection status and a pencil to change it. */
function CompanionCard({ kind, state, look, status, onEdit }) {
  const P = PETS[kind] || PETS.rivet;
  const ok = status && status.configured !== false && !status.off;
  return <div className="pet-profile">
    <div className="pet-profile-av">
      <Pet kind={kind === 'rivet3d' ? 'rivet' : kind} size={96} state={state} look={look} />
      {onEdit && <button className="pet-profile-edit" title="Change companion" onClick={onEdit}>✎</button>}
    </div>
    <b>{P.name}</b>
    <div className={cx('pet-profile-st', ok ? 'ok' : 'bad')}>{ok ? '⚡ Connected' : '⚠ AI not set up'}</div>
  </div>;
}

function PetPicker({ value, onPick, allow3d }) {
  const [hov, setHov] = useState(null);
  return <div className="pet-grid">
    {PET_KEYS.map(k => <div key={k} className={cx('pet-card', value === k && 'on')} onClick={() => onPick(k)} onMouseEnter={() => setHov(k)} onMouseLeave={() => setHov(null)}>
      <Pet kind={k} size={64} state={hov === k ? 'happy' : (value === k ? 'talk' : 'idle')} />
      <b>{PETS[k].name}</b><div className="muted">{PETS[k].tag}</div></div>)}
    {allow3d && <div className={cx('pet-card', value === 'rivet3d' && 'on')} onClick={() => onPick('rivet3d')}>
      <div style={{ fontSize: 40, height: 64, display: 'grid', placeItems: 'center' }}>🧊</div><b>Rivet 3D</b><div className="muted">Full 3D robot (heavier on low-end PCs).</div></div>}
  </div>;
}

function loadThree() {
  if (window.THREE) return Promise.resolve(window.THREE);
  if (!window.__riqThreeP) window.__riqThreeP = new Promise((res, rej) => {
    const s = document.createElement('script'); s.src = 'https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js';
    s.onload = () => res(window.THREE); s.onerror = () => { window.__riqThreeP = null; rej(new Error('three.js failed to load')); };
    document.head.appendChild(s);
  });
  return window.__riqThreeP;
}
function BotThree({ state, look, onFail }) {
  const host = useRef(null); const lookRef = useRef(look); const stRef = useRef(state);
  lookRef.current = look; stRef.current = state;
  useEffect(() => {
    let stop = false, raf = 0, renderer = null;
    loadThree().then(THREE => {
      if (stop || !host.current) return;
      const S = 84, scene = new THREE.Scene(), cam = new THREE.PerspectiveCamera(32, 1, 0.1, 100);
      cam.position.set(0, 0.15, 7);
      renderer = new THREE.WebGLRenderer({ alpha: true, antialias: true });
      renderer.setPixelRatio(Math.min(2, window.devicePixelRatio || 1)); renderer.setSize(S, S);
      host.current.appendChild(renderer.domElement);
      scene.add(new THREE.AmbientLight(0xffffff, 0.6));
      const key = new THREE.DirectionalLight(0xffffff, 0.9); key.position.set(2, 3, 4); scene.add(key);
      const rim = new THREE.PointLight(0x60a5fa, 1.1, 12); rim.position.set(-3, 1.5, 2); scene.add(rim);
      const mat = (c, o = {}) => new THREE.MeshStandardMaterial({ color: c, metalness: 0.3, roughness: 0.35, ...o });
      const bot = new THREE.Group(); scene.add(bot);
      const head = new THREE.Mesh(new THREE.SphereGeometry(1.05, 48, 48), mat(0xf8fafc)); head.scale.set(1.12, 0.96, 1); bot.add(head);
      const visor = new THREE.Mesh(new THREE.SphereGeometry(1, 48, 48), mat(0x0b234f, { metalness: 0.7, roughness: 0.15 }));
      visor.scale.set(0.9, 0.52, 0.42); visor.position.set(0, 0.02, 0.72); bot.add(visor);
      const eyeMat = new THREE.MeshStandardMaterial({ color: 0x67e8f9, emissive: 0x22d3ee, emissiveIntensity: 1.2 });
      const eyes = [-0.32, 0.32].map(x => { const e = new THREE.Mesh(new THREE.SphereGeometry(0.13, 24, 24), eyeMat); e.position.set(x, 0.06, 1.12); bot.add(e); return e; });
      [-1, 1].forEach(s => { const ear = new THREE.Mesh(new THREE.CylinderGeometry(0.24, 0.24, 0.22, 32), mat(0x2563eb));
        ear.rotation.z = Math.PI / 2; ear.position.set(s * 1.18, 0, 0); bot.add(ear); });
      const stalk = new THREE.Mesh(new THREE.CylinderGeometry(0.04, 0.04, 0.45, 12), mat(0x94a3b8)); stalk.position.set(0, 1.12, 0); bot.add(stalk);
      const tipMat = new THREE.MeshStandardMaterial({ color: 0x93c5fd, emissive: 0x3b82f6, emissiveIntensity: 1 });
      const tip = new THREE.Mesh(new THREE.SphereGeometry(0.13, 20, 20), tipMat); tip.position.set(0, 1.4, 0); bot.add(tip);
      const collar = new THREE.Mesh(new THREE.TorusGeometry(0.55, 0.12, 16, 48), mat(0x2563eb)); collar.rotation.x = Math.PI / 2; collar.position.y = -1.0; bot.add(collar);
      const t0 = performance.now();
      const tick = () => {
        if (stop) return;
        const t = (performance.now() - t0) / 1000, lk = lookRef.current || { x: 0, y: 0 }, st = stRef.current;
        bot.position.y = Math.sin(t * 2) * 0.08;
        bot.rotation.y += ((lk.x * 0.6) - bot.rotation.y) * 0.12;
        bot.rotation.x += ((lk.y * 0.35) - bot.rotation.x) * 0.12;
        const blink = (t % 4) < 0.12 ? 0.15 : 1;
        eyes.forEach(e => { e.scale.y = st === 'thinking' ? 0.6 + Math.abs(Math.sin(t * 6)) * 0.5 : blink; });
        eyeMat.emissive.setHex(st === 'thinking' ? 0xf59e0b : 0x22d3ee);
        tipMat.emissiveIntensity = st === 'thinking' ? 0.6 + Math.abs(Math.sin(t * 8)) * 1.6 : 0.8 + Math.sin(t * 2) * 0.3;
        if (st === 'talk') bot.rotation.z = Math.sin(t * 10) * 0.05; else bot.rotation.z *= 0.9;
        renderer.render(scene, cam); raf = requestAnimationFrame(tick);
      };
      tick();
    }).catch(() => onFail && onFail());
    return () => { stop = true; cancelAnimationFrame(raf);
      try { if (renderer) { renderer.dispose(); renderer.domElement.remove(); } } catch (e) {} };
  }, []);
  return <div ref={host} className="bot3d-three" />;
}


export { PETS, PET_KEYS, Pet, CompanionCard, PetPicker, BotThree };

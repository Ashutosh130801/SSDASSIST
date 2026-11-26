import React, { useEffect, useRef, useState } from 'react';

/* ─────────────────────────── Motion & WebGL effects ───────────────────────────
   No 3D library: two tiny raw-WebGL fragment shaders (~2 KB) keep the bundle light.
   Every effect degrades gracefully: no WebGL → CSS blobs; reduced-motion → static frame;
   hidden tab → paused. */

export const reducedMotion = () => typeof window !== 'undefined' && window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;

const hex = (h) => {   // '#RRGGBB' or 'rgb(r, g, b)' → [0..1]×3
  h = String(h || '').trim();
  const m = h.match(/(\d+)\D+(\d+)\D+(\d+)/);
  if (h[0] !== '#' && m) return [m[1], m[2], m[3]].map(x => Number(x) / 255);
  if (h.length === 4) h = '#' + h[1] + h[1] + h[2] + h[2] + h[3] + h[3];
  return [1, 3, 5].map(i => (parseInt(h.slice(i, i + 2), 16) || 0) / 255);
};

const VERT = `attribute vec2 p; void main(){ gl_Position = vec4(p, 0., 1.); }`;

/* Domain-warped fbm "silk" — four brand colours flowing slowly over the page colour. */
const AURORA = `precision mediump float;
uniform vec2 r; uniform float t; uniform vec3 base, c0, c1, c2, c3; uniform float amt;
float h(vec2 p){ return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453); }
float n(vec2 p){ vec2 i = floor(p), f = fract(p); f = f*f*(3.-2.*f);
  return mix(mix(h(i), h(i+vec2(1,0)), f.x), mix(h(i+vec2(0,1)), h(i+vec2(1,1)), f.x), f.y); }
float fbm(vec2 p){ float v = 0., a = .5; for(int i=0;i<5;i++){ v += a*n(p); p *= 2.02; a *= .5; } return v; }
void main(){
  vec2 uv = gl_FragCoord.xy / r; vec2 p = uv * vec2(r.x/r.y, 1.) * 1.6;
  float s = t * .035;
  vec2 q = vec2(fbm(p + s), fbm(p + vec2(5.2, 1.3) - s));
  vec2 w = vec2(fbm(p + 3.*q + vec2(1.7, 9.2) + s*1.4), fbm(p + 3.*q + vec2(8.3, 2.8) - s));
  float f = fbm(p + 2.5*w);
  vec3 col = base;
  col = mix(col, c0, smoothstep(.25, .85, f) * amt);
  col = mix(col, c1, smoothstep(.35, .95, length(q)) * amt * .9);
  col = mix(col, c2, smoothstep(.45, 1., w.x) * amt * .7);
  col = mix(col, c3, smoothstep(.55, 1., w.y) * amt * .55);
  col += (h(gl_FragCoord.xy + t) - .5) * .025;          /* dither / grain */
  gl_FragColor = vec4(col, 1.);
}`;

/* Raymarched liquid sphere with gooey wobble, fresnel rim and a two-tone sheen. */
const ORB = `precision mediump float;
uniform vec2 r; uniform float t; uniform vec3 c0, c1; uniform vec2 m;
float map(vec3 p){
  float d = length(p) - 1.;
  d += .07 * sin(3.*p.x + t*1.1) * sin(3.*p.y + t*.9) * sin(3.*p.z + t*.7);
  return d;
}
vec3 nor(vec3 p){ vec2 e = vec2(.002, 0.);
  return normalize(vec3(map(p+e.xyy)-map(p-e.xyy), map(p+e.yxy)-map(p-e.yxy), map(p+e.yyx)-map(p-e.yyx))); }
void main(){
  vec2 uv = (gl_FragCoord.xy - .5*r) / r.y;
  vec3 ro = vec3(0., 0., 3.2), rd = normalize(vec3(uv, -1.45));
  float a = t*.25 + m.x*1.2, b = m.y*.8;
  mat2 R = mat2(cos(a), -sin(a), sin(a), cos(a)), S = mat2(cos(b), -sin(b), sin(b), cos(b));
  float d = 0.; vec3 p; bool hit = false;
  for(int i=0;i<64;i++){ p = ro + rd*d; vec3 q = p; q.xz *= R; q.yz *= S; float s = map(q); if(s < .001){ hit = true; break; } d += s*.8; if(d > 6.) break; }
  if(!hit){ gl_FragColor = vec4(0.); return; }
  vec3 q = p; q.xz *= R; q.yz *= S;
  vec3 n = nor(q);
  vec3 l = normalize(vec3(-.5, .8, .6));
  float dif = clamp(dot(n, l), 0., 1.);
  float fr = pow(1. - clamp(dot(n, -rd), 0., 1.), 3.);
  float band = .5 + .5*sin(6.*n.y + 4.*n.x + t*.8);
  vec3 col = mix(c0, c1, band);
  col = col*(.35 + .75*dif) + fr*vec3(1.)*.55;
  col += pow(clamp(dot(reflect(-l, n), -rd), 0., 1.), 40.) * .9;
  gl_FragColor = vec4(col, 1.);
}`;

function makeGL(canvas, frag) {
  const gl = canvas.getContext('webgl', { premultipliedAlpha: false, alpha: true, antialias: false, powerPreference: 'low-power' });
  if (!gl) return null;
  const sh = (type, src) => { const s = gl.createShader(type); gl.shaderSource(s, src); gl.compileShader(s); return gl.getShaderParameter(s, gl.COMPILE_STATUS) ? s : null; };
  const vs = sh(gl.VERTEX_SHADER, VERT), fs = sh(gl.FRAGMENT_SHADER, frag);
  if (!vs || !fs) return null;
  const pr = gl.createProgram(); gl.attachShader(pr, vs); gl.attachShader(pr, fs); gl.linkProgram(pr);
  if (!gl.getProgramParameter(pr, gl.LINK_STATUS)) return null;
  gl.useProgram(pr);
  const buf = gl.createBuffer(); gl.bindBuffer(gl.ARRAY_BUFFER, buf);
  gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 3, -1, -1, 3]), gl.STATIC_DRAW);
  const loc = gl.getAttribLocation(pr, 'p'); gl.enableVertexAttribArray(loc); gl.vertexAttribPointer(loc, 2, gl.FLOAT, false, 0, 0);
  const U = (n) => gl.getUniformLocation(pr, n);
  return { gl, U };
}

/** Run a shader on a canvas: resizes, caps FPS, pauses off-screen / hidden tab. */
function useShader(ref, frag, setup, { scale = 0.5, fps = 30, still = false } = {}) {
  const [ok, setOk] = useState(true);
  useEffect(() => {
    const canvas = ref.current; if (!canvas) return undefined;
    const g = makeGL(canvas, frag);
    if (!g) { setOk(false); return undefined; }
    const { gl, U } = g;
    const uR = U('r'), uT = U('t');
    const upd = setup(gl, U) || (() => {});
    let raf = 0, last = 0, visible = true, t0 = performance.now();
    const size = () => {
      const dpr = Math.min(window.devicePixelRatio || 1, 2) * scale;
      const w = Math.max(2, Math.floor(canvas.clientWidth * dpr)), h = Math.max(2, Math.floor(canvas.clientHeight * dpr));
      if (canvas.width !== w || canvas.height !== h) { canvas.width = w; canvas.height = h; gl.viewport(0, 0, w, h); }
      gl.uniform2f(uR, w, h);
    };
    const draw = (now) => {
      raf = requestAnimationFrame(draw);
      if (!visible || document.hidden) return;
      if (now - last < 1000 / fps) return;
      last = now; size(); upd(now);
      gl.uniform1f(uT, still ? 12 : (now - t0) / 1000);
      gl.drawArrays(gl.TRIANGLES, 0, 3);
    };
    const io = new IntersectionObserver(([e]) => { visible = e.isIntersecting; }); io.observe(canvas);
    if (still) { size(); upd(0); gl.uniform1f(uT, 12); gl.drawArrays(gl.TRIANGLES, 0, 3); }
    else raf = requestAnimationFrame(draw);
    return () => { cancelAnimationFrame(raf); io.disconnect(); const x = gl.getExtension('WEBGL_lose_context'); x && x.loseContext(); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [frag, still]);
  return ok;
}

/** Full-page animated aurora (WebGL) over CSS blob fallback. */
export function Backdrop({ pal, particles }) {
  const ref = useRef(null);
  const palRef = useRef(pal); palRef.current = pal;
  const ok = useShader(ref, AURORA, (gl, U) => {
    const uB = U('base'), uC = [U('c0'), U('c1'), U('c2'), U('c3')], uA = U('amt');
    return () => {
      const p = palRef.current;
      gl.uniform3fv(uB, hex(p.base)); p.c.forEach((c, i) => gl.uniform3fv(uC[i], hex(c))); gl.uniform1f(uA, p.amt);
    };
  }, { scale: 0.35, fps: 24, still: reducedMotion() });
  return (
    <div className={'backdrop' + (ok ? ' gl-on' : '')} aria-hidden="true">
      <i className="b1" /><i className="b2" /><i className="b3" /><i className="b4" />
      <canvas ref={ref} className="gl" />
      {particles && <ParticleField colors={particles.colors} dark={particles.dark} />}
      <div className="grain" />
    </div>
  );
}

/** Interactive 3D liquid orb (raymarched). Follows the pointer a little. */
export function LiquidOrb({ size = 220, colors = ['#6366F1', '#22D3EE'], className, style }) {
  const ref = useRef(null);
  const mouse = useRef([0, 0]);
  const colRef = useRef(colors); colRef.current = colors;
  const ok = useShader(ref, ORB, (gl, U) => {
    const u0 = U('c0'), u1 = U('c1'), uM = U('m');
    const cur = [0, 0];
    return () => {
      cur[0] += (mouse.current[0] - cur[0]) * .06; cur[1] += (mouse.current[1] - cur[1]) * .06;
      gl.uniform2f(uM, cur[0], cur[1]);
      gl.uniform3fv(u0, hex(colRef.current[0])); gl.uniform3fv(u1, hex(colRef.current[1]));
    };
  }, { scale: 1, fps: 40, still: reducedMotion() });
  useEffect(() => {
    const mv = (e) => { mouse.current = [(e.clientX / window.innerWidth - .5) * 2, (e.clientY / window.innerHeight - .5) * 2]; };
    window.addEventListener('pointermove', mv, { passive: true });
    return () => window.removeEventListener('pointermove', mv);
  }, []);
  if (!ok) return <div className={'orb-fallback ' + (className || '')} style={{ width: size, height: size, ...style }} />;
  return <canvas ref={ref} className={className} style={{ width: size, height: size, ...style }} aria-hidden="true" />;
}

/** Animated number: eases from the previous value to the new one. */
export function useCountUp(value, ms = 900) {
  const [v, setV] = useState(0);
  const from = useRef(0);
  useEffect(() => {
    const target = Number(value) || 0;
    if (reducedMotion()) { setV(target); from.current = target; return undefined; }
    const start = performance.now(), a = from.current;
    let raf = 0;
    const step = (now) => {
      const k = Math.min(1, (now - start) / ms), e = 1 - Math.pow(1 - k, 4);
      setV(a + (target - a) * e);
      if (k < 1) raf = requestAnimationFrame(step); else from.current = target;
    };
    raf = requestAnimationFrame(step);
    return () => cancelAnimationFrame(raf);
  }, [value, ms]);
  return v;
}
export function CountUp({ value, format = (x) => Math.round(x).toLocaleString('en-IN') }) {
  const v = useCountUp(value);
  return <>{format(v)}</>;
}

/** 3D tilt + moving glare on hover. Wrap any card. */
export function Tilt({ children, max = 7, className, style, as: Tag = 'div' }) {
  const ref = useRef(null);
  const onMove = (e) => {
    const el = ref.current; if (!el || reducedMotion()) return;
    const b = el.getBoundingClientRect();
    const x = (e.clientX - b.left) / b.width, y = (e.clientY - b.top) / b.height;
    el.style.setProperty('--rx', `${(0.5 - y) * max}deg`);
    el.style.setProperty('--ry', `${(x - 0.5) * max}deg`);
    el.style.setProperty('--gx', `${x * 100}%`); el.style.setProperty('--gy', `${y * 100}%`);
    el.classList.add('tilting');
  };
  const onLeave = () => { const el = ref.current; if (!el) return; el.style.setProperty('--rx', '0deg'); el.style.setProperty('--ry', '0deg'); el.classList.remove('tilting'); };
  return <Tag ref={ref} className={'tilt ' + (className || '')} style={style} onPointerMove={onMove} onPointerLeave={onLeave}>{children}</Tag>;
}

/** Ring gauge with gradient stroke that animates in. */
export function Ring({ value = 0, size = 150, stroke = 12, children }) {
  const v = useCountUp(Math.max(0, Math.min(100, value)), 1200);
  const rad = (size - stroke) / 2, c = 2 * Math.PI * rad;
  const id = useRef('rg' + Math.random().toString(36).slice(2, 8)).current;
  return (
    <div className="ring-wrap" style={{ width: size, height: size }}>
      <svg width={size} height={size} style={{ transform: 'rotate(-90deg)', overflow: 'visible' }}>
        <defs>
          <linearGradient id={id} x1="0" y1="0" x2="1" y2="1">
            <stop offset="0%" style={{ stopColor: 'var(--ring-a)' }} /><stop offset="100%" style={{ stopColor: 'var(--ring-b)' }} />
          </linearGradient>
          <filter id={id + 'g'} x="-30%" y="-30%" width="160%" height="160%"><feGaussianBlur stdDeviation="4" /></filter>
        </defs>
        <circle cx={size / 2} cy={size / 2} r={rad} fill="none" style={{ stroke: 'var(--ring-track)' }} strokeWidth={stroke} />
        <circle cx={size / 2} cy={size / 2} r={rad} fill="none" stroke={`url(#${id})`} strokeWidth={stroke} strokeLinecap="round"
          strokeDasharray={c} strokeDashoffset={c * (1 - v / 100)} filter={`url(#${id}g)`} opacity=".55" />
        <circle cx={size / 2} cy={size / 2} r={rad} fill="none" stroke={`url(#${id})`} strokeWidth={stroke} strokeLinecap="round"
          strokeDasharray={c} strokeDashoffset={c * (1 - v / 100)} />
      </svg>
      <div className="ring-c">{children ? children(v) : <div className="ring-v">{v.toFixed(1)}%</div>}</div>
    </div>
  );
}

/** Small SVG sparkline (no axes) with a soft area fill. */
export function Spark({ data = [], className = 'spark' }) {
  if (!data || data.length < 2) return null;
  const w = 100, h = 34, max = Math.max(...data), min = Math.min(...data), span = max - min || 1;
  const pts = data.map((d, i) => [i / (data.length - 1) * w, h - 3 - ((d - min) / span) * (h - 6)]);
  const line = pts.map((p, i) => (i ? 'L' : 'M') + p[0].toFixed(1) + ' ' + p[1].toFixed(1)).join(' ');
  const id = 'sp' + Math.abs(data.length * 7919 + Math.round(max)) % 100000;
  return (
    <svg className={className} viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none" aria-hidden="true">
      <defs><linearGradient id={id} x1="0" y1="0" x2="0" y2="1"><stop offset="0%" style={{ stopColor: 'rgb(var(--t))', stopOpacity: .35 }} /><stop offset="100%" style={{ stopColor: 'rgb(var(--t))', stopOpacity: 0 }} /></linearGradient></defs>
      <path d={`${line} L ${w} ${h} L 0 ${h} Z`} fill={`url(#${id})`} />
      <path d={line} fill="none" style={{ stroke: 'rgb(var(--t))' }} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" vectorEffect="non-scaling-stroke" className="spark-line" />
    </svg>
  );
}

/* ── 3D particle terrain: ~16k points forming flowing "data waves" in perspective ── */
const PV = `attribute vec2 g;
uniform float t; uniform vec2 r; uniform vec2 m; uniform float dpr;
varying float vH; varying float vF;
void main(){
  float x = g.x * 20.0;
  float z = mod(g.y * 30.0 - t * 0.9, 30.0) + 3.0;          /* drifts toward the viewer forever */
  float y = sin(x * 0.42 + t * 0.55) * 0.6 + cos(z * 0.55 - t * 0.4) * 0.55 + sin((x + z) * 0.27 + t * 0.3) * 0.45;
  vec3 p = vec3(x + m.x * 1.6, y * 1.25 - 2.2 - m.y * 0.6, z);
  vec2 q = p.xy / p.z * 1.9; q.x *= r.y / r.x;
  gl_Position = vec4(q, 0.0, 1.0);
  gl_PointSize = clamp(46.0 / p.z, 1.4, 11.0) * dpr;
  vH = (y + 1.6) / 3.2;
  vF = smoothstep(33.0, 14.0, z) * smoothstep(3.0, 6.0, z); /* fade far + very near */
}`;
const PF = `precision mediump float;
uniform vec3 c0, c1; uniform float glow;
varying float vH; varying float vF;
void main(){
  vec2 d = gl_PointCoord - .5; float r = length(d);
  float a = smoothstep(.5, .0, r);
  a = mix(a, a * a, 1. - glow);
  vec3 col = mix(c0, c1, clamp(vH, 0., 1.));
  gl_FragColor = vec4(col, a * vF * (glow > .5 ? 1.0 : .8));
}`;

export function ParticleField({ colors = ['#2563EB', '#0EA5E9'], dark = false }) {
  const ref = useRef(null);
  const col = useRef(colors); col.current = colors;
  const [ok, setOk] = useState(true);
  useEffect(() => {
    const canvas = ref.current; if (!canvas) return undefined;
    const gl = canvas.getContext('webgl', { alpha: true, premultipliedAlpha: false, antialias: false, powerPreference: 'low-power' });
    if (!gl) { setOk(false); return undefined; }
    const sh = (ty, src) => { const s = gl.createShader(ty); gl.shaderSource(s, src); gl.compileShader(s); return gl.getShaderParameter(s, gl.COMPILE_STATUS) ? s : null; };
    const vs = sh(gl.VERTEX_SHADER, PV), fs = sh(gl.FRAGMENT_SHADER, PF);
    if (!vs || !fs) { setOk(false); return undefined; }
    const pr = gl.createProgram(); gl.attachShader(pr, vs); gl.attachShader(pr, fs); gl.linkProgram(pr); gl.useProgram(pr);
    const NX = 200, NZ = 110, pts = new Float32Array(NX * NZ * 2);
    for (let i = 0, k = 0; i < NX; i++) for (let j = 0; j < NZ; j++) { pts[k++] = i / (NX - 1) * 2 - 1; pts[k++] = j / (NZ - 1); }
    const buf = gl.createBuffer(); gl.bindBuffer(gl.ARRAY_BUFFER, buf); gl.bufferData(gl.ARRAY_BUFFER, pts, gl.STATIC_DRAW);
    const loc = gl.getAttribLocation(pr, 'g'); gl.enableVertexAttribArray(loc); gl.vertexAttribPointer(loc, 2, gl.FLOAT, false, 0, 0);
    const U = (n) => gl.getUniformLocation(pr, n);
    const uT = U('t'), uR = U('r'), uM = U('m'), uD = U('dpr'), u0 = U('c0'), u1 = U('c1'), uG = U('glow');
    gl.enable(gl.BLEND);
    if (dark) gl.blendFunc(gl.SRC_ALPHA, gl.ONE); else gl.blendFunc(gl.SRC_ALPHA, gl.ONE_MINUS_SRC_ALPHA);
    const mouse = [0, 0], cur = [0, 0];
    const mv = (e) => { mouse[0] = (e.clientX / window.innerWidth - .5) * 2; mouse[1] = (e.clientY / window.innerHeight - .5) * 2; };
    window.addEventListener('pointermove', mv, { passive: true });
    const still = reducedMotion();
    let raf = 0, last = 0; const t0 = performance.now();
    const frame = (now) => {
      raf = requestAnimationFrame(frame);
      if (document.hidden || now - last < 1000 / 30) return; last = now;
      const dpr = Math.min(window.devicePixelRatio || 1, 1.5);
      const w = Math.floor(canvas.clientWidth * dpr), h = Math.floor(canvas.clientHeight * dpr);
      if (canvas.width !== w || canvas.height !== h) { canvas.width = w; canvas.height = h; gl.viewport(0, 0, w, h); }
      cur[0] += (mouse[0] - cur[0]) * .04; cur[1] += (mouse[1] - cur[1]) * .04;
      gl.clearColor(0, 0, 0, 0); gl.clear(gl.COLOR_BUFFER_BIT);
      gl.uniform1f(uT, still ? 8 : (now - t0) / 1000); gl.uniform2f(uR, w, h); gl.uniform2f(uM, cur[0], cur[1]); gl.uniform1f(uD, dpr);
      gl.uniform3fv(u0, hex(col.current[0])); gl.uniform3fv(u1, hex(col.current[1])); gl.uniform1f(uG, dark ? 1 : 0);
      gl.drawArrays(gl.POINTS, 0, NX * NZ);
      if (still) cancelAnimationFrame(raf);
    };
    raf = requestAnimationFrame(frame);
    return () => { cancelAnimationFrame(raf); window.removeEventListener('pointermove', mv); const x = gl.getExtension('WEBGL_lose_context'); x && x.loseContext(); };
  }, [dark]);
  if (!ok) return null;
  return <canvas ref={ref} className="gl gl-particles" aria-hidden="true" />;
}

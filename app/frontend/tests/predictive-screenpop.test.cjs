const assert = require('node:assert/strict');
const { test } = require('node:test');
const { createWatcher } = require('../predictive-screenpop.js');

function setup(overrides = {}) {
  const calls = [], statuses = [], saved = [], requests = [], timers = new Map();
  let id = 0;
  const context = { live: { state: 'connected', event_id: '1:8001:M1:44:9', case_id: 9 }, visible: true, fail: false };
  const watcher = createWatcher({
    request: async path => { requests.push(path); if (path.includes('my-live-call') || path.includes('/events/')) return context.live; if (context.fail) throw new Error('Temporary failure'); return { id: context.live.case_id }; },
    subscribe: callbacks => { context.callbacks = callbacks; return { close() { context.closed = true; } }; },
    onCall: (c, live) => calls.push({ c, live }), onStatus: s => statuses.push(s),
    seen: new Set(), remember: s => saved.push(s), isVisible: () => context.visible,
    schedule: (fn, ms) => { timers.set(++id, { fn, ms }); return id; }, cancel: key => timers.delete(key),
    ...overrides
  });
  return { watcher, context, calls, statuses, saved, requests, timers };
}

test('connected call opens exact scoped case once; next call to same lead opens again', async () => {
  const t = setup(); await t.watcher.poll(); await t.watcher.poll();
  assert.equal(t.calls.length, 1);
  assert.equal(t.requests.filter(p => p === '/api/cases/9').length, 1);
  t.context.live = { ...t.context.live, event_id: '1:8001:M2:44:9' };
  await t.watcher.poll(); assert.equal(t.calls.length, 2);
  assert.equal(t.timers.size, 0); t.watcher.stop(); assert.equal(t.timers.size, 0);
});
test('failed detail fetch retries without prematurely marking seen', async () => {
  const t = setup(); t.context.fail = true; await t.watcher.poll();
  assert.equal(t.calls.length, 0); assert.equal(t.saved.length, 0);
  assert.equal(t.statuses.at(-1).state, 'error');
  assert.equal([...t.timers.values()][0].ms, 4000);
  t.context.fail = false; await t.watcher.poll(); assert.equal(t.calls.length, 1); t.watcher.stop();
});
test('persisted identity prevents re-opening a manually closed call after reload', async () => {
  const t = setup({ seen: new Set(['1:8001:M1:44:9']) }); await t.watcher.poll();
  assert.equal(t.calls.length, 0); t.watcher.stop();
});
test('non-connected states never fetch case details', async () => {
  const t = setup();
  for (const state of ['waiting', 'logged_out', 'unmatched', 'unavailable', 'disabled', 'error']) {
    t.context.live = { state, poll_after_ms: 15000 }; await t.watcher.poll();
  }
  assert.equal(t.calls.length, 0); assert.ok(t.requests.every(p => p.includes('my-live-call'))); t.watcher.stop();
});
test('hidden view pauses requests; returning resumes; stopped loop makes no calls', async () => {
  const t = setup(); t.context.visible = false; await t.watcher.poll(); assert.equal(t.requests.length, 0);
  t.context.visible = true; await t.watcher.poll(); assert.equal(t.calls.length, 1);
  t.watcher.stop(); await t.watcher.poll(); assert.equal(t.calls.length, 1);
});
test('no overlapping requests, logout aborts and suppresses late delivery', async () => {
  let resolve, signal, count = 0;
  const t = setup({ request: (path, opts) => { count++; signal = opts.signal; return new Promise(r => { resolve = r; }); } });
  const first = t.watcher.poll(); await t.watcher.poll(); assert.equal(count, 1);
  t.watcher.stop(); assert.equal(signal.aborted, true);
  resolve({ state: 'connected', event_id: 'new', case_id: 1 }); await first;
  assert.equal(t.calls.length, 0); assert.equal(t.timers.size, 0);
});

test('React screen-pop keeps earlier case mounted with stable key and restores it on close', () => {
  const fs = require('node:fs');
  const vm = require('node:vm');
  const babel = require('../node_modules/@babel/standalone');
  const source = fs.readFileSync(require('node:path').join(__dirname, '../app.jsx'), 'utf8');
  const component = source.slice(source.indexOf('function PredictiveScreenPop('), source.indexOf('function Shell('));
  const state = [], effects = [];
  let cursor = 0, options, stopped = false;
  const context = {
    React: { Fragment: 'Fragment', createElement: (type, props, ...children) => ({ type, props: props || {}, children }) },
    useState: initial => { const i = cursor++; if (!(i in state)) state[i] = initial; return [state[i], value => { state[i] = typeof value === 'function' ? value(state[i]) : value; }]; },
    useEffect: fn => effects.push(fn),
    window: { RecoverIQPredictive: { createWatcher: opts => { options = opts; return { start() {}, poll() {}, stop() { stopped = true; } }; } }, addEventListener() {}, removeEventListener() {} },
    document: { addEventListener() {}, removeEventListener() {} },
    sessionStorage: { getItem() { return null; }, setItem() {} }, api() {}, ssdWS() {}, toast() {}, CaseDrawer() {}
  };
  vm.createContext(context);
  vm.runInContext(babel.transform(component, { presets: ['react'] }).code, context);
  const render = () => { cursor = 0; return context.PredictiveScreenPop({ user: { id: 8, role: 'telecaller' } }); };
  render();
  const cleanup = effects[1](); // subscription, after the Escape listener effect
  const firstCase = { id: 10, customer_name: 'First' };
  options.onCall(firstCase, { agent_user: '8001', event_id: 'call1' });
  options.onCall({ id: 20 }, { agent_user: '8001', event_id: 'call2' });
  let tree = render();
  let wrappers = tree.children[1];
  assert.equal(wrappers.length, 2);
  assert.equal(wrappers[0].props.key, 10);
  assert.equal(wrappers[0].props.style.display, 'none');
  assert.equal(wrappers[1].props.style.display, 'contents');
  assert.equal(wrappers[0].children[0].props.c, firstCase);
  assert.equal(wrappers[1].children[0].props.manageBack, false);
  wrappers[1].children[0].props.onClose();
  tree = render(); wrappers = tree.children[1];
  assert.equal(wrappers.length, 1);
  assert.equal(wrappers[0].props.key, 10);
  assert.equal(wrappers[0].children[0].props.c, firstCase);
  assert.equal(wrappers[0].children[0].props.focusOnOpen, true);
  cleanup(); assert.equal(stopped, true);
});

test('push opens case without querying ViciDial; idle successful connection has no timer', async () => {
  const t = setup(); t.context.live = { state: 'waiting' };
  t.watcher.start(); await t.context.callbacks.onOpen();
  assert.equal(t.timers.size, 0);
  const id = 'a'.repeat(64); t.context.live = { state: 'connected', event_id: id, case_id: 9 };
  t.context.callbacks.onMessage({ data: JSON.stringify({ type: 'predictive_screenpop', event_id: id }) });
  await new Promise(r => setImmediate(r));
  assert.equal(t.calls.length, 1);
  assert.equal(t.requests.filter(p => p.includes('my-live-call')).length, 1);
  assert.ok(t.requests.includes('/api/integration/vicidial/events/' + id));
  t.context.callbacks.onMessage({ data: JSON.stringify({ type: 'predictive_screenpop', event_id: id }) });
  await new Promise(r => setImmediate(r)); assert.equal(t.calls.length, 1); assert.equal(t.timers.size, 0);
  t.context.callbacks.onClose(); assert.equal(t.statuses.at(-1).state, 'error');
  await t.context.callbacks.onOpen(); assert.equal(t.calls.length, 1);
  t.watcher.stop(); assert.equal(t.context.closed, true);
});

test('unrelated/invalid WebSocket messages never trigger requests', () => {
  const t = setup();
  for (const data of ['invalid', JSON.stringify({ type: 'heartbeat' }), JSON.stringify({ type: 'predictive_screenpop', event_id: '../secret' })]) t.watcher.receive({ data });
  assert.equal(t.requests.length, 0); t.watcher.stop();
});

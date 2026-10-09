const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const Babel = require('../node_modules/@babel/standalone');
const source = fs.readFileSync(path.join(__dirname, '..', 'app.jsx'), 'utf8');

function harness() {
  let slots = [], index = 0, tree;
  const requests = [];
  const context = {
    React: { createElement: (type, props, ...children) => ({ type, props: props || {}, children: children.flat(Infinity) }) },
    useState: initial => { const i = index++; if (!(i in slots)) slots[i] = initial; return [slots[i], value => { slots[i] = typeof value === 'function' ? value(slots[i]) : value; }]; },
    useEffect() {}, useDataChanged() {}, Loader() {}, toast() {}, cx: (...args) => args.filter(Boolean).join(' '),
    URLSearchParams,
    api: async (url, options) => { requests.push({ url, options }); return []; }
  };
  vm.createContext(context);
  const snippet = source.slice(source.indexOf('const LEAVE_TYPES ='), source.indexOf('/* ============================== Devices'));
  vm.runInContext(Babel.transform(snippet, { presets: ['react'] }).code, context);
  const render = () => { index = 0; tree = context.LeaveView({ user: { id: 1, role: 'telecaller' } }); };
  function find(predicate, node = tree) {
    if (!node || typeof node !== 'object') return;
    if (predicate(node)) return node;
    for (const child of node.children || []) { const hit = find(predicate, child); if (hit) return hit; }
  }
  const set = (id, value) => { find(n => n.props.id === id).props.onChange({ target: { value } }); render(); };
  render();
  return { set, find, render, requests, context };
}

test('half-day form needs one date and sends the half_day flag', async () => {
  const h = harness();
  h.set('leave-duration', 'half');
  assert.equal(h.find(n => n.props.id === 'leave-end'), undefined);
  h.set('leave-start', '2026-10-12');
  const button = h.find(n => n.type === 'button' && n.children.includes('Request half-day leave'));
  assert.equal(button.props.disabled, false);
  await button.props.onClick();
  const body = h.requests.find(r => r.options?.method === 'POST').options.body;
  assert.equal(body.half_day, true);
  assert.equal(body.start_date, '2026-10-12');
  assert.equal(body.end_date, '2026-10-12');
  h.render();
  assert.equal(h.find(n => n.props.id === 'leave-duration').props.value, 'full');
});

test('full-day mode keeps range and does not submit a half-day', async () => {
  const h = harness();
  h.set('leave-start', '2026-10-12');
  h.set('leave-end', '2026-10-13');
  await h.find(n => n.type === 'button' && n.children.includes('Apply for leave')).props.onClick();
  const body = h.requests.find(r => r.options?.method === 'POST').options.body;
  assert.equal(body.half_day, false);
  assert.equal(body.end_date, '2026-10-13');
});

test('half-day selection resets a previously entered multi-day end date', async () => {
  const h = harness();
  h.set('leave-start', '2026-10-12');
  h.set('leave-end', '2026-10-20');
  h.set('leave-duration', 'half');
  await h.find(n => n.type === 'button' && n.children.includes('Request half-day leave')).props.onClick();
  assert.equal(h.requests.find(r => r.options?.method === 'POST').options.body.end_date, '2026-10-12');
});

test('balances/history helpers show 0.5 and legacy full-day counts', () => {
  const h = harness();
  assert.equal(vm.runInContext('leaveDays({half_day:true,days:1})', h.context), 0.5);
  assert.equal(vm.runInContext('leaveDuration({half_day:true,days:1,days_effective:0.5})', h.context), '0.5 (Half day)');
  assert.equal(vm.runInContext('leaveDays({half_day:null,days:3})', h.context), 3);
});

test('daily status, detail and exports label half-day even on late check-in', () => {
  const start = source.indexOf('const attendanceLabel =');
  const end = source.indexOf(';', start) + 1;
  const context = vm.createContext({});
  vm.runInContext(source.slice(start, end), context);
  assert.equal(vm.runInContext("attendanceLabel({half_day_leave:true,late:true,check_in_at:'2026-10-08',status:'half_leave'})", context), 'Half-day leave · checked in late');
  assert.equal(vm.runInContext("attendanceLabel({status:'leave',late:true})", context), 'Leave');
});

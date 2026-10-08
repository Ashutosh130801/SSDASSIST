const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const Babel = require('../node_modules/@babel/standalone');

// Render the actual component with a minimal hook harness; no browser or live calls.
function harness(api) {
  const source = fs.readFileSync(path.join(__dirname, '..', 'app.jsx'), 'utf8');
  const component = source.slice(source.indexOf('function ViciDialTestCall('), source.indexOf('function ConnectionsView('));
  let slots = [], index = 0, accepted = 0;
  const context = {
    api,
    React: { createElement: (type, props, ...children) => ({ type, props: props || {}, children: children.flat(Infinity) }) },
    useState: initial => { const i = index++; if (!(i in slots)) slots[i] = initial; return [slots[i], value => { slots[i] = value; }]; },
    useRef: initial => { const i = index++; if (!(i in slots)) slots[i] = { current: initial }; return slots[i]; }
  };
  vm.createContext(context);
  vm.runInContext(Babel.transform(component, { presets: ['react'] }).code, context);
  let tree;
  const render = () => {
    index = 0;
    tree = context.ViciDialTestCall({ connection: { id: 42, name: 'Selected dialer', base_url: 'https://example.test', capabilities: { phone_code: '91' } }, onClose() {}, onAccepted() { accepted++; } });
  };
  function find(predicate, node = tree) {
    if (!node || typeof node !== 'object') return;
    if (predicate(node)) return node;
    for (const child of node.children || []) { const hit = find(predicate, child); if (hit) return hit; }
  }
  const field = id => find(n => n.props.id === id);
  const confirm = () => { find(n => n.props.type === 'checkbox').props.onChange({ target: { checked: true } }); render(); };
  render();
  for (const [id, value] of [['vici-test-agent', '8002'], ['vici-test-phone', '9876543210']]) { field(id).props.onChange({ target: { value } }); render(); }
  return { render, find, confirm, submit: () => find(n => n.type === 'form').props.onSubmit({ preventDefault() {} }), accepted: () => accepted };
}

test('confirmation is required before sending', async () => {
  let calls = 0;
  const h = harness(async () => { calls++; });
  await h.submit();
  assert.equal(calls, 0);
  assert.equal(h.find(n => n.props.type === 'submit').props.disabled, true);
});

test('entered agent and number go to selected connection; repeat click is blocked', async () => {
  let calls = 0, resolve, request;
  const h = harness((url, options) => { calls++; request = { url, options }; return new Promise(r => { resolve = r; }); });
  h.confirm();
  const pending = h.submit();
  await h.submit();
  assert.equal(calls, 1);
  assert.equal(request.url, '/api/integration/vicidial/42/test-call');
  assert.equal(request.options.body.agent_user, '8002');
  assert.equal(request.options.body.phone_number, '9876543210');
  assert.equal(request.options.body.confirmed, true);
  resolve({ ok: true, detail: 'Accepted, not answered' });
  await pending;
  h.render();
  assert.equal(h.accepted(), 1);
  assert.equal(h.find(n => n.props.type === 'submit').props.disabled, true);
  await h.submit();
  assert.equal(calls, 1);
});

test('network failure is shown without retry and new test requires confirmation again', async () => {
  let calls = 0;
  const h = harness(async () => { calls++; throw Error('Network timeout'); });
  h.confirm();
  await h.submit();
  h.render();
  assert.equal(calls, 1);
  assert.ok(h.find(n => n.props.role === 'alert'));
  h.find(n => n.type === 'button' && n.children.includes('Prepare another test')).props.onClick();
  h.render();
  assert.equal(h.find(n => n.props.type === 'checkbox').props.checked, false);
  assert.equal(h.find(n => n.props.type === 'submit').props.disabled, true);
});

'use strict';

// Builder's own regression checks. Starts the service on a free port and
// exercises it over HTTP. Run: node --test test/*.test.js   (from stage-1/)

const test = require('node:test');
const assert = require('node:assert');
const { spawn } = require('node:child_process');
const path = require('node:path');
const net = require('node:net');

let base;
let child;

function freePort() {
  return new Promise((resolve) => {
    const s = net.createServer();
    s.listen(0, '127.0.0.1', () => {
      const { port } = s.address();
      s.close(() => resolve(port));
    });
  });
}

async function call(method, p, { body, token, key, raw } = {}) {
  const headers = { 'content-type': 'application/json' };
  if (token) headers.authorization = `Bearer ${token}`;
  if (key !== undefined) headers['idempotency-key'] = key;
  const r = await fetch(base + p, { method, headers, body: raw !== undefined ? raw : body === undefined ? undefined : JSON.stringify(body) });
  const text = await r.text();
  return { status: r.status, body: text ? JSON.parse(text) : null, text };
}

const FIXTURE = {
  currency: 'EUR',
  minor_units: 2,
  users: [
    { id: 'u_ada', email: 'ada@example.com', password: 'correct horse', display_name: 'Ada', handle: 'ada', balance: 10000 },
    { id: 'u_bob', email: 'bob@example.com', password: 'correct horse', display_name: 'Bob', handle: 'bob', balance: 2500 },
    { id: 'u_cy', email: 'cy@example.com', password: 'correct horse', display_name: 'Cy', handle: 'cy', balance: 0 },
    { id: 'u_op', email: 'op@example.com', password: 'correct horse', display_name: 'Op', handle: 'op', balance: 0 },
  ],
  payments: [{ id: 'p_1', from_user_id: 'u_ada', to_user_id: 'u_bob', amount: 500, note: 'coffee', visibility: 'public' }],
  requests: [{ id: 'rq_1', requester_id: 'u_bob', payer_id: 'u_ada', amount: 1200, note: 'taxi', status: 'pending' }],
  settlement_operator_ids: ['u_op'],
};
const TOTAL = 12500;

async function resetAndLogin() {
  const r = await call('POST', '/_test/reset', { body: FIXTURE });
  assert.strictEqual(r.status, 204);
  const t = {};
  await Promise.all(['ada', 'bob', 'cy', 'op'].map(async (h) => {
    const l = await call('POST', '/auth/login', { body: { email: `${h}@example.com`, password: 'correct horse' } });
    assert.strictEqual(l.status, 200);
    t[h] = l.body.token;
  }));
  return t;
}

async function total(t) {
  let sum = 0;
  for (const h of ['ada', 'bob', 'cy', 'op']) sum += (await call('GET', '/me', { token: t[h] })).body.balance;
  return sum;
}

test.before(async () => {
  const port = await freePort();
  base = `http://127.0.0.1:${port}`;
  child = spawn(process.execPath, [path.join(__dirname, '..', 'src', 'server.js')], { env: { ...process.env, PORT: String(port) }, stdio: 'ignore' });
  for (let i = 0; i < 100; i++) {
    try {
      if ((await fetch(`${base}/health`)).status === 200) return;
    } catch { /* not up yet */ }
    await new Promise((r) => setTimeout(r, 100));
  }
  throw new Error('service did not start');
});

test.after(() => child.kill());

test('auth, me and errors', async () => {
  const t = await resetAndLogin();
  const me = await call('GET', '/me', { token: t.ada });
  assert.deepStrictEqual(me.body, { user_id: 'u_ada', display_name: 'Ada', handle: 'ada', balance: 10000, currency: 'EUR', minor_units: 2 });
  assert.strictEqual((await call('GET', '/me')).body.error.code, 'unauthenticated');
  assert.strictEqual((await call('GET', '/me', { token: 'nope' })).status, 401);
  assert.strictEqual((await call('POST', '/auth/login', { body: { email: 'ada@example.com', password: 'wrong pass' } })).status, 401);
  const s = await call('POST', '/auth/signup', { body: { email: 'Dee.X@example.com', password: 'longenough', display_name: 'Dee' } });
  assert.strictEqual(s.status, 201);
  const dme = await call('GET', '/me', { token: s.body.token });
  assert.strictEqual(dme.body.handle, 'dee_x');
  assert.strictEqual(dme.body.balance, 0);
  assert.strictEqual((await call('POST', '/auth/signup', { body: { email: 'dee.x@example.com', password: 'longenough', display_name: 'D' } })).body.error.code, 'email_taken');
  assert.strictEqual((await call('POST', '/auth/signup', { body: { email: 'dee.x@other.org', password: 'longenough', display_name: 'D' } })).body.error.code, 'handle_taken');
  assert.strictEqual((await call('POST', '/auth/signup', { body: { email: 'z@example.com', password: 'short', display_name: 'D' } })).status, 422);
  assert.strictEqual((await call('POST', '/auth/signup', { raw: '{bad' })).body.error.code, 'malformed_request');
});

test('payments, idempotency and invariants', async () => {
  const t = await resetAndLogin();
  const body = { to_handle: 'bob', amount: 1500, note: 'dinner 🍝' };
  const first = await call('POST', '/payments', { token: t.ada, key: 'k1', body });
  assert.strictEqual(first.status, 201);
  assert.strictEqual(first.body.visibility, 'public');
  assert.strictEqual(first.body.note, 'dinner 🍝');
  assert.strictEqual(first.body.settlement_id, null);
  assert.match(first.body.created_at, /^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\+00:00$/);
  const replay = await call('POST', '/payments', { token: t.ada, key: 'k1', body: { note: 'dinner 🍝', amount: 1500.0, to_handle: 'bob' } });
  assert.strictEqual(replay.status, 200);
  assert.deepStrictEqual(replay.body, first.body);
  assert.strictEqual((await call('POST', '/payments', { token: t.ada, key: 'k1', body: { amount: 'x' } })).body.error.code, 'idempotency_key_reuse');
  assert.strictEqual((await call('POST', '/payments', { token: t.ada, body })).body.error.code, 'missing_idempotency_key');
  assert.strictEqual((await call('POST', '/payments', { token: t.ada, key: 'x'.repeat(256), body })).status, 422);
  assert.strictEqual((await call('POST', '/payments', { token: t.ada, key: 'k2', body: { to_handle: 'ada', amount: 1 } })).body.error.code, 'self_payment');
  assert.strictEqual((await call('POST', '/payments', { token: t.ada, key: 'k2', body: { to_handle: 'zed', amount: 1 } })).status, 404);
  for (const amount of ['5', true, null, 0, 1.5, 1000000001]) {
    assert.strictEqual((await call('POST', '/payments', { token: t.ada, key: 'k2', body: { to_handle: 'bob', amount } })).status, 422, String(amount));
  }
  assert.strictEqual((await call('POST', '/payments', { token: t.ada, key: 'k2', body: { to_handle: 'bob', amount: 1, note: null } })).status, 422);
  const short = await call('POST', '/payments', { token: t.cy, key: 'k2', body: { to_handle: 'bob', amount: 1 } });
  assert.strictEqual(short.body.error.code, 'insufficient_funds');
  // failed key is reusable
  assert.strictEqual((await call('POST', '/payments', { token: t.ada, key: 'k2', body: { to_handle: 'cy', amount: 1e3 } })).status, 201);
  // same key, different path is a different request
  assert.strictEqual((await call('POST', '/requests', { token: t.ada, key: 'k1', body })).status, 422);
  assert.strictEqual(await total(t), TOTAL);
});

test('concurrent identical writes take effect once; concurrent spends never overdraw', async () => {
  const t = await resetAndLogin();
  const body = { to_handle: 'cy', amount: 100 };
  const rs = await Promise.all(Array.from({ length: 50 }, () => call('POST', '/payments', { token: t.ada, key: 'same', body })));
  assert.strictEqual(rs.filter((r) => r.status === 201).length, 1);
  assert.strictEqual(rs.filter((r) => r.status === 200).length, 49);
  assert.ok(rs.every((r) => r.body.payment_id === rs[0].body.payment_id));
  const bobSpends = await Promise.all(Array.from({ length: 50 }, (_, i) => call('POST', '/payments', { token: t.bob, key: `b${i}`, body: { to_handle: 'cy', amount: 100 } })));
  assert.strictEqual(bobSpends.filter((r) => r.status === 201).length, 25);
  assert.ok(bobSpends.every((r) => r.status === 201 || r.body.error.code === 'insufficient_funds'));
  assert.strictEqual((await call('GET', '/me', { token: t.bob })).body.balance, 0);
  assert.strictEqual(await total(t), TOTAL);
});

test('requests lifecycle', async () => {
  const t = await resetAndLogin();
  const big = await call('POST', '/requests', { token: t.cy, key: 'r1', body: { payer_handle: 'bob', amount: 999999 } });
  assert.strictEqual(big.status, 201);
  assert.strictEqual(big.body.status, 'pending');
  const id = big.body.request_id;
  assert.strictEqual((await call('POST', `/requests/${id}/pay`, { token: t.bob, key: 'p1', body: {} })).body.error.code, 'insufficient_funds');
  assert.strictEqual((await call('POST', `/requests/${id}/pay`, { token: t.cy, key: 'p1', body: {} })).status, 403);
  // third party: 403 on every action of an existing request, 404 only for unknown ids
  assert.strictEqual((await call('POST', `/requests/${id}/pay`, { token: t.ada, key: 'p1', body: {} })).status, 403);
  assert.strictEqual((await call('POST', `/requests/${id}/decline`, { token: t.ada })).status, 403);
  assert.strictEqual((await call('POST', `/requests/${id}/cancel`, { token: t.ada })).status, 403);
  assert.strictEqual((await call('POST', '/requests/rq_nope/pay', { token: t.ada, key: 'p1', body: {} })).status, 404);
  assert.strictEqual((await call('POST', '/requests/rq_nope/decline', { token: t.ada })).status, 404);
  assert.strictEqual((await call('POST', '/requests/rq_nope/cancel', { token: t.ada })).status, 404);
  assert.ok(!(await call('GET', '/requests', { token: t.ada })).body.requests.some((r) => r.request_id === id));
  assert.strictEqual((await call('POST', `/requests/${id}/cancel`, { token: t.bob })).status, 403);
  const pays = await Promise.all(Array.from({ length: 20 }, (_, i) => call('POST', '/requests/rq_1/pay', { token: t.ada, key: `q${i % 2}`, body: { visibility: 'private' } })));
  assert.strictEqual(pays.filter((r) => r.status === 201).length, 1);
  assert.ok(pays.every((r) => [200, 201, 409].includes(r.status)));
  const won = pays.find((r) => r.status === 201);
  assert.strictEqual(won.body.request_id, 'rq_1');
  assert.strictEqual(won.body.visibility, 'private');
  assert.strictEqual((await call('GET', '/me', { token: t.ada })).body.balance, 8800);
  const replay = await call('POST', '/requests/rq_1/pay', { token: t.ada, key: pays.indexOf(won) % 2 ? 'q1' : 'q0', body: { visibility: 'private' } });
  assert.strictEqual(replay.status, 200);
  assert.deepStrictEqual(replay.body, won.body);
  assert.strictEqual((await call('POST', '/requests/rq_1/decline', { token: t.ada })).body.error.code, 'request_not_pending');
  const d1 = await call('POST', `/requests/${id}/decline`, { token: t.bob });
  assert.strictEqual(d1.body.status, 'declined');
  assert.strictEqual((await call('POST', `/requests/${id}/decline`, { token: t.bob })).status, 200);
  assert.strictEqual((await call('POST', `/requests/${id}/cancel`, { token: t.cy })).status, 409);
  const list = await call('GET', '/requests?direction=outgoing&limit=1', { token: t.bob });
  assert.strictEqual(list.body.requests[0].request_id, 'rq_1');
  assert.strictEqual(list.body.requests[0].status, 'paid');
  assert.strictEqual(list.body.has_more, false);
  for (const q of ['limit=0', 'limit=201', 'limit=4.0', 'offset=-1', 'offset=1e2', 'direction=up', 'status=done']) {
    assert.strictEqual((await call('GET', `/requests?${q}`, { token: t.bob })).status, 422, q);
  }
  assert.strictEqual(await total(t), TOTAL);
});

test('splits and activity visibility', async () => {
  const t = await resetAndLogin();
  const sp = await call('POST', '/splits', { token: t.ada, key: 's1', body: { amount: 1000, participant_handles: ['bob', 'ada', 'cy'], note: 'dinner' } });
  assert.strictEqual(sp.status, 201);
  assert.deepStrictEqual(sp.body.shares, [{ handle: 'bob', amount: 334 }, { handle: 'ada', amount: 333 }, { handle: 'cy', amount: 333 }]);
  assert.deepStrictEqual(sp.body.requests.map((r) => [r.payer_handle, r.amount]), [['bob', 334], ['cy', 333]]);
  const solo = await call('POST', '/splits', { token: t.ada, key: 's2', body: { amount: 1, participant_handles: ['ada'] } });
  assert.deepStrictEqual(solo.body.requests, []);
  const zero = await call('POST', '/splits', { token: t.ada, key: 's3', body: { amount: 1, participant_handles: ['bob', 'cy', 'ada'] } });
  assert.deepStrictEqual(zero.body.requests.map((r) => r.amount), [1, 0]);
  const zeroReq = zero.body.requests[1];
  const paidZero = await call('POST', `/requests/${zeroReq.request_id}/pay`, { token: t.cy, key: 'z0', body: {} });
  assert.strictEqual(paidZero.status, 201);
  assert.strictEqual(paidZero.body.amount, 0);
  const zl = await call('GET', '/requests?direction=incoming&status=paid', { token: t.cy });
  assert.strictEqual(zl.body.requests[0].payment_id, paidZero.body.payment_id);
  assert.strictEqual((await call('POST', '/splits', { token: t.ada, key: 's4', body: { amount: 3, participant_handles: ['bob', 'bob'] } })).status, 422);
  assert.strictEqual((await call('POST', '/splits', { token: t.ada, key: 's4', body: { amount: 3, participant_handles: ['bob', 'nobody'] } })).status, 404);
  await call('POST', '/payments', { token: t.ada, key: 'priv', body: { to_handle: 'bob', amount: 7, visibility: 'private' } });
  const seen = async (h) => (await call('GET', '/activity?limit=200', { token: t[h] })).body.payments.map((p) => p.amount);
  assert.deepStrictEqual(await seen('cy'), [0, 500]);
  assert.deepStrictEqual(await seen('bob'), [7, 0, 500]);
  assert.deepStrictEqual(await seen('op'), [0, 500]);
  const page = await call('GET', '/activity?limit=1&offset=0', { token: t.bob });
  assert.strictEqual(page.body.has_more, true);
});

test('settlements', async () => {
  const t = await resetAndLogin();
  const transfers = [{ from_handle: 'ada', to_handle: 'bob', amount: 100 }, { from_handle: 'bob', to_handle: 'cy', amount: 2600 }];
  assert.strictEqual((await call('POST', '/settlements', { token: t.ada, key: 'x', body: { transfers } })).status, 403);
  assert.strictEqual((await call('POST', '/settlements', { key: 'x', body: { transfers } })).status, 401);
  const ok = await call('POST', '/settlements', { token: t.op, key: 'st1', body: { transfers } });
  assert.strictEqual(ok.status, 201);
  assert.strictEqual(ok.body.payments.length, 2);
  assert.ok(ok.body.payments.every((p) => p.settlement_id === ok.body.settlement_id && p.created_at === ok.body.committed_at && p.request_id === null));
  const tooMuch = await call('POST', '/settlements', { token: t.op, key: 'st2', body: { transfers: [{ from_handle: 'cy', to_handle: 'ada', amount: 2601 }] } });
  assert.strictEqual(tooMuch.body.error.code, 'insufficient_funds');
  const order = await call('POST', '/settlements', { token: t.op, key: 'st2', body: { transfers: [{ from_handle: 'cy', to_handle: 'zz', amount: 1 }, { from_handle: 'cy', to_handle: 'cy', amount: 1 }] } });
  assert.strictEqual(order.status, 404);
  const order2 = await call('POST', '/settlements', { token: t.op, key: 'st2', body: { transfers: [{ from_handle: 'cy', to_handle: 'cy', amount: 1 }, { from_handle: 'cy', to_handle: 'zz', amount: 1 }] } });
  assert.strictEqual(order2.body.error.code, 'self_payment');
  assert.strictEqual((await call('POST', '/settlements', { token: t.op, key: 'st2', body: { transfers: [] } })).status, 422);
  assert.strictEqual((await call('POST', '/settlements', { token: t.op, key: 'st1', body: { transfers } })).status, 200);
  assert.strictEqual(await total(t), TOTAL);
});

test('export and import round trip; reset validation', async () => {
  const t = await resetAndLogin();
  const p = await call('POST', '/payments', { token: t.ada, key: 'e1', body: { to_handle: 'cy', amount: 42 } });
  const exp = await call('GET', '/_test/export');
  assert.strictEqual(exp.body.track, 'pocketful');
  assert.strictEqual(exp.body.format_version, 1);
  await call('POST', '/payments', { token: t.ada, key: 'e2', body: { to_handle: 'cy', amount: 1 } });
  assert.strictEqual((await call('POST', '/_test/import', { body: { ...exp.body, format_version: 2 } })).status, 422);
  assert.strictEqual((await call('POST', '/_test/import', { body: exp.body })).status, 204);
  assert.strictEqual((await call('POST', '/_test/import', { body: exp.body })).status, 204);
  assert.strictEqual((await call('GET', '/me', { token: t.ada })).body.balance, 10000 - 42);
  const replay = await call('POST', '/payments', { token: t.ada, key: 'e1', body: { to_handle: 'cy', amount: 42 } });
  assert.strictEqual(replay.status, 200);
  assert.deepStrictEqual(replay.body, p.body);
  assert.strictEqual((await call('POST', '/auth/login', { body: { email: 'cy@example.com', password: 'correct horse' } })).status, 200);
  const bad = await call('POST', '/_test/reset', { body: { ...FIXTURE, users: [{ ...FIXTURE.users[0], balance: -1 }] } });
  assert.strictEqual(bad.status, 422);
  assert.strictEqual((await call('GET', '/me', { token: t.ada })).status, 200);
});

test('large reset fixture fits the reset budget and every seeded user can log in', async () => {
  const users = Array.from({ length: 150 }, (_, i) => ({ id: `u${i}`, email: `u${i}@x.io`, password: 'correct horse', display_name: `U${i}`, handle: `u${i}`, balance: 1 }));
  const t0 = Date.now();
  assert.strictEqual((await call('POST', '/_test/reset', { body: { currency: 'JPY', minor_units: 0, users } })).status, 204);
  assert.ok(Date.now() - t0 < 10000, `reset took ${Date.now() - t0} ms`);
  const l = await call('POST', '/auth/login', { body: { email: 'u149@x.io', password: 'correct horse' } });
  assert.strictEqual(l.status, 200);
  assert.strictEqual((await call('GET', '/me', { token: l.body.token })).body.minor_units, 0);
});

test('balances are exact at the 2^53 bound (R1-041)', async () => {
  const MAX = 9007199254740992; // 2^53, in range
  const fixture = { currency: 'EUR', minor_units: 2, users: [
    { id: 'u_r', email: 'rich@x.io', password: 'correct horse', display_name: 'R', handle: 'rich', balance: MAX },
    { id: 'u_p', email: 'poor@x.io', password: 'correct horse', display_name: 'P', handle: 'poor', balance: 0 },
    { id: 'u_m', email: 'mid@x.io', password: 'correct horse', display_name: 'M', handle: 'mid', balance: 10 },
  ] };
  assert.strictEqual((await call('POST', '/_test/reset', { raw: JSON.stringify(fixture) })).status, 204);
  const login = async (e) => (await call('POST', '/auth/login', { body: { email: e, password: 'correct horse' } })).body.token;
  const rich = await login('rich@x.io');
  const poor = await login('poor@x.io');
  const bal = async (tok) => JSON.parse((await call('GET', '/me', { token: tok })).text.replace(/"balance":(\d+)/, '"balance":"$1"')).balance;
  assert.strictEqual(await bal(rich), '9007199254740992');
  assert.strictEqual((await call('POST', '/payments', { token: rich, key: 'm1', body: { to_handle: 'poor', amount: 1 } })).status, 201);
  assert.strictEqual(await bal(rich), '9007199254740991');
  assert.strictEqual(await bal(poor), '1');
  // back to exactly 2^53 is allowed; one more unit above it is refused and changes nothing
  assert.strictEqual((await call('POST', '/payments', { token: poor, key: 'm2', body: { to_handle: 'rich', amount: 1 } })).status, 201);
  assert.strictEqual(await bal(rich), '9007199254740992');
  const ab = await call('POST', '/splits', { token: poor, key: 'm3', body: { amount: 1, participant_handles: ['rich', 'poor'] } });
  assert.strictEqual(ab.status, 201);
  const over = await call('POST', '/payments', { token: rich, key: 'm4', body: { to_handle: 'poor', amount: 5 } });
  assert.strictEqual(over.status, 201);
  const back = await call('POST', '/payments', { token: poor, key: 'm5', body: { to_handle: 'rich', amount: 5 } });
  assert.strictEqual(back.status, 201);
  assert.strictEqual(await bal(rich), '9007199254740992');
  assert.strictEqual(await bal(poor), '0');
  const mid = await login('mid@x.io');
  const tooRich = await call('POST', '/payments', { token: mid, key: 'm6', body: { to_handle: 'rich', amount: 1 } });
  assert.strictEqual(tooRich.status, 422);
  assert.strictEqual(await bal(rich), '9007199254740992');
  assert.strictEqual(await bal(mid), '10');
  const neg = { ...fixture, users: [{ ...fixture.users[0], balance: -1 }] };
  assert.strictEqual((await call('POST', '/_test/reset', { body: neg })).status, 422);
  const above = JSON.stringify(fixture).replace('9007199254740992', '9007199254740994');
  assert.strictEqual((await call('POST', '/_test/reset', { raw: above })).status, 422);
  const exp = await call('GET', '/_test/export');
  assert.ok(exp.text.includes('"balance":9007199254740992'));
  assert.strictEqual((await call('POST', '/_test/import', { raw: exp.text })).status, 204);
  assert.strictEqual(await bal(rich), '9007199254740992');
});

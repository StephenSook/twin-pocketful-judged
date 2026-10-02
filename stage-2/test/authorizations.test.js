'use strict';

// Builder's stage-2 regression checks: holds, captures, expiry, available/held,
// stage-1 export import, HTML negotiation. Run: node --test test/*.test.js

const test = require('node:test');
const assert = require('node:assert');
const { spawn } = require('node:child_process');
const path = require('node:path');
const fs = require('node:fs');
const net = require('node:net');

const children = [];

function freePort() {
  return new Promise((resolve) => {
    const s = net.createServer();
    s.listen(0, '127.0.0.1', () => {
      const { port } = s.address();
      s.close(() => resolve(port));
    });
  });
}

async function startService(serverJs) {
  const port = await freePort();
  const base = `http://127.0.0.1:${port}`;
  const child = spawn(process.execPath, [serverJs], { env: { ...process.env, PORT: String(port) }, stdio: 'ignore' });
  children.push(child);
  for (let i = 0; i < 100; i++) {
    try {
      if ((await fetch(`${base}/health`)).status === 200) return base;
    } catch { /* not up yet */ }
    await new Promise((r) => setTimeout(r, 100));
  }
  throw new Error('service did not start');
}

function client(base) {
  return async (method, p, { body, token, key, raw, accept } = {}) => {
    const headers = { 'content-type': 'application/json' };
    if (token) headers.authorization = `Bearer ${token}`;
    if (key !== undefined) headers['idempotency-key'] = key;
    if (accept) headers.accept = accept;
    const r = await fetch(base + p, { method, headers, body: raw !== undefined ? raw : body === undefined ? undefined : JSON.stringify(body) });
    const text = await r.text();
    let parsed = null;
    try { parsed = text ? JSON.parse(text) : null; } catch { parsed = null; }
    return { status: r.status, body: parsed, text, type: r.headers.get('content-type') };
  };
}

let call;
const HOUR = 3600 * 1000;
const iso = (ms) => new Date(ms).toISOString().replace(/\.\d{3}Z$/, '+00:00');

function fixture(extra = {}) {
  return {
    currency: 'EUR',
    minor_units: 2,
    users: [
      { id: 'u_ada', email: 'ada@example.com', password: 'correct horse', display_name: 'Ada', handle: 'ada', balance: 10000 },
      { id: 'u_bob', email: 'bob@example.com', password: 'correct horse', display_name: 'Bob', handle: 'bob', balance: 2500 },
      { id: 'u_cy', email: 'cy@example.com', password: 'correct horse', display_name: 'Cy', handle: 'cy', balance: 0 },
    ],
    ...extra,
  };
}

async function reset(f) {
  const r = await call('POST', '/_test/reset', { body: f });
  assert.strictEqual(r.status, 204, r.text);
  const t = {};
  for (const h of ['ada', 'bob', 'cy']) {
    t[h] = (await call('POST', '/auth/login', { body: { email: `${h}@example.com`, password: 'correct horse' } })).body.token;
  }
  return t;
}

const me = async (tok) => (await call('GET', '/me', { token: tok })).body;

test.before(async () => {
  call = client(await startService(path.join(__dirname, '..', 'src', 'server.js')));
});
test.after(() => children.forEach((c) => c.kill()));

test('seeded holds: available derived, expired seeds hold nothing, over-held seed is 422', async () => {
  const seeded = [
    { id: 'a_1', from_user_id: 'u_ada', to_user_id: 'u_bob', amount: 2000, note: 'deposit', visibility: 'public', status: 'open', expires_at: iso(Date.now() + 2 * HOUR) },
    { id: 'a_2', from_user_id: 'u_ada', to_user_id: 'u_bob', amount: 3000, status: 'open', expires_at: iso(Date.now() - 2 * HOUR) },
  ];
  const t = await reset(fixture({ authorizations: seeded }));
  assert.deepStrictEqual(await me(t.ada), { user_id: 'u_ada', display_name: 'Ada', handle: 'ada', balance: 10000, total: 10000, available: 8000, held: 2000, currency: 'EUR', minor_units: 2 });
  const list = await call('GET', '/authorizations', { token: t.ada });
  assert.deepStrictEqual(list.body.authorizations.map((a) => [a.authorization_id, a.status, a.remaining_amount]).sort(), [['a_1', 'open', 2000], ['a_2', 'expired', 0]]);
  assert.strictEqual((await call('GET', '/authorizations', { token: t.cy })).body.authorizations.length, 0);
  // ruling S2-3: closed seeds hold nothing and carry valid fields
  const closed = ['captured', 'voided', 'expired'].map((status, i) => ({ id: `a_c${i}`, from_user_id: 'u_bob', to_user_id: 'u_cy', amount: 900, status, expires_at: iso(Date.now() + 2 * HOUR) }));
  const t2 = await reset(fixture({ authorizations: closed }));
  assert.strictEqual((await me(t2.bob)).held, 0);
  const got = (await call('GET', '/authorizations', { token: t2.cy })).body.authorizations.sort((x, y) => x.authorization_id.localeCompare(y.authorization_id));
  assert.deepStrictEqual(got.map((a) => [a.status, a.captured_amount, a.remaining_amount, a.payment_id, a.payment_ids]),
    [['captured', 900, 0, null, []], ['voided', 0, 0, null, []], ['expired', 0, 0, null, []]]);
  assert.strictEqual((await call('POST', '/authorizations/a_c0/capture', { token: t2.cy, key: 'z', body: {} })).body.error.code, 'authorization_not_open');
  assert.strictEqual((await call('POST', '/authorizations/a_c2/capture', { token: t2.cy, key: 'z', body: {} })).body.error.code, 'authorization_expired');
  assert.strictEqual((await call('POST', '/authorizations/a_c1/void', { token: t2.bob })).status, 200);
  await reset(fixture({ authorizations: seeded }));

  assert.strictEqual((await call('POST', '/_test/reset', { body: over })).status, 422);
  assert.strictEqual((await me(t.ada)).held, 2000, 'a refused reset changes nothing');
  for (const ttl of [0, -5, 1.5, '600', null]) {
    assert.strictEqual((await call('POST', '/_test/reset', { body: fixture({ authorization_ttl_seconds: ttl }) })).status, 422, String(ttl));
  }
});

test('authorize, hold limits available, partial final capture releases the remainder', async () => {
  const t = await reset(fixture({ authorization_ttl_seconds: 900 }));
  const body = { to_handle: 'bob', amount: 6000, note: 'deposit', visibility: 'private' };
  const a = await call('POST', '/authorizations', { token: t.ada, key: 'h1', body });
  assert.strictEqual(a.status, 201, a.text);
  assert.strictEqual(a.body.status, 'open');
  assert.strictEqual(a.body.remaining_amount, 6000);
  assert.strictEqual(a.body.captured_amount, 0);
  assert.deepStrictEqual(a.body.payment_ids, []);
  assert.strictEqual(Date.parse(a.body.expires_at) - Date.parse(a.body.created_at), 900 * 1000);
  assert.strictEqual((await call('POST', '/authorizations', { token: t.ada, key: 'h1', body })).status, 200);
  const m = await me(t.ada);
  assert.deepStrictEqual([m.balance, m.total, m.available, m.held], [10000, 10000, 4000, 6000]);
  // held funds cannot pay, authorize or be requested-paid
  assert.strictEqual((await call('POST', '/payments', { token: t.ada, key: 'p1', body: { to_handle: 'cy', amount: 4001 } })).body.error.code, 'insufficient_funds');
  assert.strictEqual((await call('POST', '/authorizations', { token: t.ada, key: 'h2', body: { to_handle: 'cy', amount: 4001 } })).body.error.code, 'insufficient_funds');
  assert.strictEqual((await call('POST', '/payments', { token: t.ada, key: 'p1', body: { to_handle: 'cy', amount: 4000 } })).status, 201);
  // an open authorization is not a feed item
  assert.ok(!(await call('GET', '/activity', { token: t.ada })).body.payments.some((p) => p.amount === 6000));
  const id = a.body.authorization_id;
  assert.strictEqual((await call('POST', `/authorizations/${id}/capture`, { token: t.ada, key: 'c1', body: {} })).status, 403);
  assert.strictEqual((await call('POST', `/authorizations/${id}/capture`, { token: t.cy, key: 'c1', body: {} })).status, 403);
  assert.strictEqual((await call('POST', '/authorizations/a_nope/capture', { token: t.bob, key: 'c1', body: {} })).status, 404);
  assert.strictEqual((await call('POST', `/authorizations/${id}/capture`, { token: t.bob, key: 'c1', body: { amount: 6001 } })).body.error.code, 'capture_exceeds_authorization');
  for (const amount of [0, 1.5, '5', true, null]) {
    assert.strictEqual((await call('POST', `/authorizations/${id}/capture`, { token: t.bob, key: 'c1', body: { amount } })).body.error.code, 'validation_failed', String(amount));
  }
  const cap = await call('POST', `/authorizations/${id}/capture`, { token: t.bob, key: 'c1', body: { amount: 1500 } });
  assert.strictEqual(cap.status, 201, cap.text);
  assert.strictEqual(cap.body.amount, 1500);
  assert.strictEqual(cap.body.authorization_id, id);
  assert.strictEqual(cap.body.request_id, null);
  assert.strictEqual(cap.body.note, 'deposit');
  assert.strictEqual(cap.body.visibility, 'private');
  const replay = await call('POST', `/authorizations/${id}/capture`, { token: t.bob, key: 'c1', body: { amount: 1500 } });
  assert.strictEqual(replay.status, 200);
  assert.deepStrictEqual(replay.body, cap.body);
  assert.strictEqual((await call('POST', `/authorizations/${id}/capture`, { token: t.bob, key: 'c1', body: {} })).body.error.code, 'idempotency_key_reuse');
  assert.strictEqual((await call('POST', `/authorizations/${id}/capture`, { token: t.bob, key: 'c2', body: {} })).body.error.code, 'authorization_not_open');
  const after = await me(t.ada);
  assert.deepStrictEqual([after.total, after.available, after.held], [4500, 4500, 0]);
  assert.strictEqual((await me(t.bob)).total, 4000);
  const view = (await call('GET', '/authorizations?status=captured', { token: t.bob })).body.authorizations[0];
  assert.deepStrictEqual([view.status, view.captured_amount, view.remaining_amount, view.payment_id, view.payment_ids], ['captured', 1500, 0, cap.body.payment_id, [cap.body.payment_id]]);
  assert.strictEqual((await call('POST', `/authorizations/${id}/void`, { token: t.ada })).body.error.code, 'authorization_not_open');
  // ordinary payments carry authorization_id null
  assert.ok((await call('GET', '/activity', { token: t.ada })).body.payments.every((p) => 'authorization_id' in p));
});

test('extended captures keep the remainder held; void releases only the remainder', async () => {
  const t = await reset(fixture());
  const id = (await call('POST', '/authorizations', { token: t.ada, key: 'x1', body: { to_handle: 'bob', amount: 2000 } })).body.authorization_id;
  const c1 = await call('POST', `/authorizations/${id}/capture`, { token: t.bob, key: 'n1', body: { amount: 700, final: false } });
  assert.strictEqual(c1.status, 201);
  let a = (await call('GET', '/authorizations', { token: t.ada })).body.authorizations[0];
  assert.deepStrictEqual([a.status, a.captured_amount, a.remaining_amount], ['open', 700, 1300]);
  assert.deepStrictEqual([(await me(t.ada)).held, (await me(t.ada)).total], [1300, 9300]);
  assert.strictEqual((await call('POST', `/authorizations/${id}/capture`, { token: t.bob, key: 'n2', body: { amount: 1301, final: false } })).body.error.code, 'capture_exceeds_authorization');
  assert.strictEqual((await call('POST', `/authorizations/${id}/capture`, { token: t.bob, key: 'n2', body: { final: 'no' } })).status, 400);
  const c2 = await call('POST', `/authorizations/${id}/capture`, { token: t.bob, key: 'n2', body: { amount: 300, final: false } });
  assert.strictEqual(c2.status, 201);
  assert.strictEqual((await call('POST', `/authorizations/${id}/void`, { token: t.bob })).status, 403);
  assert.strictEqual((await call('POST', `/authorizations/${id}/void`, { token: t.cy })).status, 403);
  const v = await call('POST', `/authorizations/${id}/void`, { token: t.ada });
  assert.deepStrictEqual([v.status, v.body.status, v.body.captured_amount, v.body.remaining_amount, v.body.payment_ids], [200, 'voided', 1000, 0, [c1.body.payment_id, c2.body.payment_id]]);
  assert.strictEqual((await call('POST', `/authorizations/${id}/void`, { token: t.ada })).status, 200);
  assert.deepStrictEqual([(await me(t.ada)).held, (await me(t.ada)).available], [0, 9000]);
  // capturing the whole remainder closes it even with final: false
  const id2 = (await call('POST', '/authorizations', { token: t.ada, key: 'x2', body: { to_handle: 'bob', amount: 500 } })).body.authorization_id;
  await call('POST', `/authorizations/${id2}/capture`, { token: t.bob, key: 'n3', body: { amount: 500, final: false } });
  a = (await call('GET', `/authorizations?direction=outgoing&limit=1`, { token: t.ada })).body.authorizations[0];
  assert.deepStrictEqual([a.authorization_id, a.status, a.remaining_amount], [id2, 'captured', 0]);
  const sum = (await me(t.ada)).total + (await me(t.bob)).total + (await me(t.cy)).total;
  assert.strictEqual(sum, 12500);
});

test('expiry by the clock releases the hold without any request at the deadline', async () => {
  const t = await reset(fixture({ authorization_ttl_seconds: 1 }));
  const id = (await call('POST', '/authorizations', { token: t.ada, key: 'e1', body: { to_handle: 'bob', amount: 9000 } })).body.authorization_id;
  assert.strictEqual((await me(t.ada)).available, 1000);
  await new Promise((r) => setTimeout(r, 2100));
  assert.deepStrictEqual([(await me(t.ada)).available, (await me(t.ada)).held], [10000, 0]);
  const a = (await call('GET', '/authorizations?status=expired', { token: t.bob })).body.authorizations[0];
  assert.deepStrictEqual([a.authorization_id, a.status, a.remaining_amount], [id, 'expired', 0]);
  assert.strictEqual((await call('GET', '/authorizations?status=open', { token: t.bob })).body.authorizations.length, 0);
  assert.strictEqual((await call('POST', `/authorizations/${id}/capture`, { token: t.bob, key: 'e2', body: {} })).body.error.code, 'authorization_expired');
  assert.strictEqual((await call('POST', `/authorizations/${id}/void`, { token: t.ada })).body.error.code, 'authorization_not_open');
  for (const q of ['status=pending', 'direction=sideways', 'limit=0', 'offset=-1']) {
    assert.strictEqual((await call('GET', `/authorizations?${q}`, { token: t.ada })).status, 422, q);
  }
});

test('concurrent holds and payments never overdraw available', async () => {
  const t = await reset(fixture());
  const rs = await Promise.all(Array.from({ length: 50 }, (_, i) => (i % 2
    ? call('POST', '/authorizations', { token: t.ada, key: `ca${i}`, body: { to_handle: 'bob', amount: 400 } })
    : call('POST', '/payments', { token: t.ada, key: `cp${i}`, body: { to_handle: 'cy', amount: 400 } }))));
  assert.strictEqual(rs.filter((r) => r.status === 201).length, 25);
  assert.ok(rs.every((r) => r.status === 201 || r.body.error.code === 'insufficient_funds'));
  const m = await me(t.ada);
  assert.strictEqual(m.available, 0);
  assert.strictEqual(m.total - m.held, m.available);
  const ids = (await call('GET', '/authorizations?limit=200', { token: t.bob })).body.authorizations.map((a) => a.authorization_id);
  const caps = await Promise.all(ids.flatMap((id) => [0, 1].map(() => call('POST', `/authorizations/${id}/capture`, { token: t.bob, key: `k-${id}`, body: {} }))));
  assert.strictEqual(caps.filter((r) => r.status === 201).length, ids.length);
  assert.strictEqual(caps.filter((r) => r.status === 200).length, ids.length);
  const sum = (await me(t.ada)).total + (await me(t.bob)).total + (await me(t.cy)).total;
  assert.strictEqual(sum, 12500);
});

test('stage-2 export/import round trip keeps holds, captures and retries', async () => {
  const t = await reset(fixture());
  const id = (await call('POST', '/authorizations', { token: t.ada, key: 'r1', body: { to_handle: 'bob', amount: 1000 } })).body.authorization_id;
  const cap = await call('POST', `/authorizations/${id}/capture`, { token: t.bob, key: 'r2', body: { amount: 100, final: false } });
  const exp = await call('GET', '/_test/export');
  assert.strictEqual((await call('POST', '/_test/reset', { body: fixture() })).status, 204);
  assert.strictEqual((await call('POST', '/_test/import', { raw: exp.text })).status, 204);
  assert.deepStrictEqual([(await me(t.ada)).held, (await me(t.ada)).total], [900, 9900]);
  const replay = await call('POST', `/authorizations/${id}/capture`, { token: t.bob, key: 'r2', body: { amount: 100, final: false } });
  assert.deepStrictEqual([replay.status, replay.body], [200, cap.body]);
  assert.strictEqual((await call('POST', `/authorizations/${id}/capture`, { token: t.bob, key: 'r3', body: {} })).status, 201);
});

test('a stage-1 export imports: tokens, pending requests and lost-response retries survive', async (t) => {
  const stage1 = path.join(__dirname, '..', '..', 'stage-1', 'src', 'server.js');
  if (!fs.existsSync(stage1)) {
    t.skip('stage-1 service not present next to stage-2');
    return;
  }
  const old = client(await startService(stage1));
  const f = fixture({ requests: [{ id: 'rq_1', requester_id: 'u_bob', payer_id: 'u_ada', amount: 1200, note: 'taxi', status: 'pending' }] });
  assert.strictEqual((await old('POST', '/_test/reset', { body: f })).status, 204);
  const ada = (await old('POST', '/auth/login', { body: { email: 'ada@example.com', password: 'correct horse' } })).body.token;
  const paid = await old('POST', '/payments', { token: ada, key: 'lost-1', body: { to_handle: 'cy', amount: 250, note: 'x' } });
  const exp = await old('GET', '/_test/export');
  assert.strictEqual((await call('POST', '/_test/import', { raw: exp.text })).status, 204);
  const m = await me(ada);
  assert.deepStrictEqual([m.total, m.available, m.held], [9750, 9750, 0]);
  const retry = await call('POST', '/payments', { token: ada, key: 'lost-1', body: { to_handle: 'cy', amount: 250, note: 'x' } });
  assert.deepStrictEqual([retry.status, retry.body], [200, paid.body]);
  assert.strictEqual((await me(ada)).total, 9750, 'the retry moved no money');
  const pay = await call('POST', '/requests/rq_1/pay', { token: ada, key: 'rp', body: {} });
  assert.strictEqual(pay.status, 201);
  assert.strictEqual(pay.body.authorization_id, null);
  assert.strictEqual((await call('GET', '/activity', { token: ada })).body.payments.find((p) => p.payment_id === paid.body.payment_id).authorization_id, null);
});

test('content negotiation and static files', async () => {
  const t = await reset(fixture());
  const api = await call('GET', '/requests', { token: t.ada });
  assert.match(api.type, /application\/json/);
  const hasUi = fs.existsSync(path.join(__dirname, '..', 'public', 'index.html'));
  for (const route of ['/', '/requests', '/split', '/signup', '/login', '/authorizations']) {
    const r = await call('GET', route, { accept: 'text/html,application/xhtml+xml;q=0.9,*/*;q=0.8' });
    if (hasUi) {
      assert.strictEqual(r.status, 200, route);
      assert.match(r.type, /text\/html/);
    } else {
      assert.strictEqual(r.status, 404, route);
    }
  }
  assert.strictEqual((await call('GET', '/static/../src/server.js')).status, 404);
  assert.strictEqual((await call('GET', '/static/%2e%2e/package.json')).status, 404);
  assert.strictEqual((await call('GET', '/static/nope.css')).status, 404);
  assert.strictEqual((await call('POST', '/requests', { token: t.ada, accept: 'text/html', key: 'k', body: { payer_handle: 'bob', amount: 1 } })).status, 201);
});

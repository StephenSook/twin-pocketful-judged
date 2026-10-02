'use strict';

// Builder stage-4 regression checks: refunds, correction batches, precedence,
// concurrency and stage-3 import. Run: node --test test/*.test.js

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
const q = (s) => encodeURIComponent(s);
const PAST = Math.floor((Date.now() - 2 * HOUR) / 1000) * 1000;


function fixture() {
  return {
    currency: 'EUR',
    minor_units: 2,
    users: [
      { id: 'u_ada', email: 'ada@example.com', password: 'correct horse', display_name: 'Ada', handle: 'ada', balance: 10000 },
      { id: 'u_bob', email: 'bob@example.com', password: 'correct horse', display_name: 'Bob', handle: 'bob', balance: 2500 },
      { id: 'u_cy', email: 'cy@example.com', password: 'correct horse', display_name: 'Cy', handle: 'cy', balance: 1000 },
      { id: 'u_op', email: 'op@example.com', password: 'correct horse', display_name: 'Op', handle: 'op', balance: 0 },
    ],
    payments: [{ id: 'p_1', from_user_id: 'u_ada', to_user_id: 'u_bob', amount: 500, note: 'coffee', visibility: 'private', created_at: iso(PAST) }],
    settlement_operator_ids: ['u_op'],
  };
}

async function reset(f = fixture()) {
  const r = await call('POST', '/_test/reset', { body: f });
  assert.strictEqual(r.status, 204, r.text);
  const t = {};
  for (const u of f.users) {
    t[u.handle] = (await call('POST', '/auth/login', { body: { email: u.email, password: 'correct horse' } })).body.token;
  }
  return t;
}
const me = async (tok) => (await call('GET', '/me', { token: tok })).body;
const total = async (t) => { let n = 0; for (const k of Object.keys(t)) n += (await me(t[k])).balance; return n; };
const fix = (x = {}) => ({ expected_revision: 1, amount: 0, effective_at: iso(PAST), reason: 'reversal', ...x });

test.before(async () => {
  call = client(await startService(path.join(__dirname, '..', 'src', 'server.js')));
});
test.after(() => children.forEach((c) => c.kill()));

test('refunds: rules, shape, cap against the corrected amount, immutability', async () => {
  const t = await reset();
  assert.strictEqual((await call('POST', '/payments/p_1/refunds', { token: t.ada, key: 'r', body: { amount: 100 } })).status, 403);
  assert.strictEqual((await call('POST', '/payments/p_1/refunds', { token: t.cy, key: 'r', body: { amount: 100 } })).status, 403);
  assert.strictEqual((await call('POST', '/payments/p_nope/refunds', { token: t.bob, key: 'r', body: { amount: 100 } })).status, 404);
  for (const amount of [0, -1, 1.5, '100', null, true]) {
    assert.strictEqual((await call('POST', '/payments/p_1/refunds', { token: t.bob, key: 'r', body: { amount } })).body.error.code, 'validation_failed', String(amount));
  }
  assert.strictEqual((await call('POST', '/payments/p_1/refunds', { token: t.bob, body: { amount: 1 } })).status, 400);
  const r1 = await call('POST', '/payments/p_1/refunds', { token: t.bob, key: 'r1', body: { amount: 200 } });
  assert.strictEqual(r1.status, 201, r1.text);
  const p = r1.body;
  assert.deepStrictEqual([p.from_user_id, p.to_user_id, p.amount, p.refund_of, p.request_id, p.authorization_id, p.note, p.visibility],
    ['u_bob', 'u_ada', 200, 'p_1', null, null, 'coffee', 'private']);
  const replay = await call('POST', '/payments/p_1/refunds', { token: t.bob, key: 'r1', body: { amount: 200 } });
  assert.deepStrictEqual([replay.status, replay.body], [200, p]);
  assert.deepStrictEqual([(await me(t.ada)).balance, (await me(t.bob)).balance], [10200, 2300]);
  // ordinary payments expose refund_of null; the refund is a feed payment
  const feed = (await call('GET', '/activity', { token: t.ada })).body.payments;
  assert.deepStrictEqual(feed.map((x) => [x.amount, x.refund_of]), [[200, 'p_1'], [500, null]]);
  // a correction cannot go below the refunded amount; refunds cannot exceed the corrected amount
  assert.strictEqual((await call('POST', '/payments/p_1/corrections', { token: t.ada, key: 'c1', body: fix({ amount: 199 }) })).body.error.code, 'refund_exceeds_payment');
  assert.strictEqual((await call('POST', '/payments/p_1/corrections', { token: t.ada, key: 'c1', body: fix({ amount: 300 }) })).status, 201);
  assert.strictEqual((await call('POST', '/payments/p_1/refunds', { token: t.bob, key: 'r2', body: { amount: 101 } })).body.error.code, 'refund_exceeds_payment');
  assert.strictEqual((await call('POST', '/payments/p_1/refunds', { token: t.bob, key: 'r2', body: { amount: 100 } })).status, 201);
  // refunds are immutable and not refundable
  assert.strictEqual((await call('POST', `/payments/${p.payment_id}/refunds`, { token: t.ada, key: 'rr', body: { amount: 1 } })).body.error.code, 'invalid_refund_target');
  assert.strictEqual((await call('POST', `/payments/${p.payment_id}/corrections`, { token: t.bob, key: 'cr', body: fix({ amount: 1 }) })).body.error.code, 'linked_payment_immutable');
  assert.strictEqual(await total(t), 13500);
});

test('refunds use available funds; captures and settlement members are refundable', async () => {
  const t = await reset();
  const hold = await call('POST', '/authorizations', { token: t.bob, key: 'h', body: { to_handle: 'cy', amount: 2400 } });
  assert.strictEqual(hold.status, 201);
  assert.strictEqual((await call('POST', '/payments/p_1/refunds', { token: t.bob, key: 'a1', body: { amount: 101 } })).body.error.code, 'insufficient_funds');
  assert.strictEqual((await call('POST', '/payments/p_1/refunds', { token: t.bob, key: 'a1', body: { amount: 100 } })).status, 201);
  const cap = await call('POST', `/authorizations/${hold.body.authorization_id}/capture`, { token: t.cy, key: 'c', body: { amount: 1000 } });
  const capRefund = await call('POST', `/payments/${cap.body.payment_id}/refunds`, { token: t.cy, key: 'cr', body: { amount: 1000 } });
  assert.strictEqual(capRefund.status, 201);
  const auth = (await call('GET', '/authorizations', { token: t.bob })).body.authorizations[0];
  assert.deepStrictEqual([auth.status, auth.remaining_amount], ['captured', 0], 'a refund never reopens the authorization');
  assert.strictEqual((await me(t.bob)).held, 0);
  const st = await call('POST', '/settlements', { token: t.op, key: 's', body: { transfers: [{ from_handle: 'ada', to_handle: 'cy', amount: 300 }, { from_handle: 'cy', to_handle: 'bob', amount: 100 }] } });
  const member = st.body.payments[0].payment_id;
  const mr = await call('POST', `/payments/${member}/refunds`, { token: t.cy, key: 'mr', body: { amount: 300 } });
  assert.strictEqual(mr.status, 201);
  assert.strictEqual(mr.body.settlement_id, null);
  assert.strictEqual((await call('POST', '/settlements', { token: t.op, key: 's', body: { transfers: [{ from_handle: 'ada', to_handle: 'cy', amount: 300 }, { from_handle: 'cy', to_handle: 'bob', amount: 100 }] } })).body.payments[0].settlement_id, st.body.settlement_id);
  assert.strictEqual(await total(t), 13500);
});

test('concurrent refunds never exceed the cap', async () => {
  const t = await reset();
  const rs = await Promise.all(Array.from({ length: 20 }, (_, i) => call('POST', '/payments/p_1/refunds', { token: t.bob, key: `k${i}`, body: { amount: 100 } })));
  assert.strictEqual(rs.filter((r) => r.status === 201).length, 5);
  assert.ok(rs.every((r) => r.status === 201 || r.body.error.code === 'refund_exceeds_payment'));
});

test('correction batches: auth, shape, item precedence, settlements, combined funds, response', async () => {
  const t = await reset();
  const st = await call('POST', '/settlements', { token: t.op, key: 's', body: { transfers: [{ from_handle: 'ada', to_handle: 'cy', amount: 300 }, { from_handle: 'cy', to_handle: 'bob', amount: 100 }] } });
  const [m1, m2] = st.body.payments;
  const body = { corrections: [fix({ payment_id: m1.payment_id, amount: 200, effective_at: m1.created_at }), fix({ payment_id: m2.payment_id, amount: 100, effective_at: m2.created_at, reason: 'same' })] };
  assert.strictEqual((await call('POST', '/correction-batches', { key: 'b', body })).status, 401);
  assert.strictEqual((await call('POST', '/correction-batches', { token: t.ada, key: 'b', body })).status, 403);
  for (const bad of [{ corrections: [] }, { corrections: Array.from({ length: 33 }, (_, i) => fix({ payment_id: `x${i}` })) }, { corrections: [fix({ payment_id: 'p_1' }), fix({ payment_id: 'p_1' })] }, {}]) {
    assert.strictEqual((await call('POST', '/correction-batches', { token: t.op, key: 'b', body: bad })).body.error.code, 'validation_failed');
  }
  // item errors in input order
  const order1 = { corrections: [fix({ payment_id: 'p_nope' }), fix({ payment_id: 'p_1', reason: '' })] };
  assert.strictEqual((await call('POST', '/correction-batches', { token: t.op, key: 'b', body: order1 })).status, 404);
  const order2 = { corrections: [fix({ payment_id: 'p_1', reason: '' }), fix({ payment_id: 'p_nope' })] };
  assert.strictEqual((await call('POST', '/correction-batches', { token: t.op, key: 'b', body: order2 })).body.error.code, 'validation_failed');
  const stale = { corrections: [fix({ payment_id: 'p_1', expected_revision: 2 }), fix({ payment_id: m1.payment_id })] };
  assert.strictEqual((await call('POST', '/correction-batches', { token: t.op, key: 'b', body: stale })).body.error.code, 'stale_revision');
  // completeness, then equal instants (offset spellings may differ)
  assert.strictEqual((await call('POST', '/correction-batches', { token: t.op, key: 'b', body: { corrections: [body.corrections[0]] } })).body.error.code, 'incomplete_settlement');
  const uneven = { corrections: [body.corrections[0], { ...body.corrections[1], effective_at: iso(PAST) }] };
  assert.strictEqual((await call('POST', '/correction-batches', { token: t.op, key: 'b', body: uneven })).body.error.code, 'validation_failed');
  const t0 = Date.parse(m1.created_at);
  const plus2 = new Date(t0 + 2 * HOUR).toISOString().replace('Z', '').replace(/\.(\d{3})$/, '.$1+02:00');
  const ok = await call('POST', '/correction-batches', { token: t.op, key: 'b', body: { corrections: [body.corrections[0], { ...body.corrections[1], effective_at: plus2 }] } });
  assert.strictEqual(ok.status, 201, ok.text);
  assert.ok(typeof ok.body.correction_batch_id === 'string');
  assert.deepStrictEqual(ok.body.revisions.map((r) => [r.payment_id, r.revision, r.amount, r.correction_batch_id, r.recorded_at]),
    [[m1.payment_id, 2, 200, ok.body.correction_batch_id, ok.body.recorded_at], [m2.payment_id, 2, 100, ok.body.correction_batch_id, ok.body.recorded_at]]);
  assert.ok(Date.parse(ok.body.recorded_at) > Date.parse(m1.created_at));
  const replay = await call('POST', '/correction-batches', { token: t.op, key: 'b', body: { corrections: [body.corrections[0], { ...body.corrections[1], effective_at: plus2 }] } });
  assert.deepStrictEqual([replay.status, replay.body], [200, ok.body]);
  const revs = (await call('GET', `/payments/${m1.payment_id}/revisions`, { token: t.ada })).body.revisions;
  assert.deepStrictEqual(revs.map((r) => r.correction_batch_id), [null, ok.body.correction_batch_id]);
  // the settlement receipt replays unchanged
  assert.strictEqual((await call('POST', '/settlements', { token: t.op, key: 's', body: { transfers: [{ from_handle: 'ada', to_handle: 'cy', amount: 300 }, { from_handle: 'cy', to_handle: 'bob', amount: 100 }] } })).body.payments[0].amount, 300);
  // single corrections still refuse settlement members
  assert.strictEqual((await call('POST', `/payments/${m1.payment_id}/corrections`, { token: t.ada, key: 'x', body: fix({ expected_revision: 2, amount: 1, effective_at: m1.created_at }) })).body.error.code, 'linked_payment_immutable');
  assert.strictEqual(await total(t), 13500);
});

test('batch affordability uses the combined effect; rejected batches change nothing', async () => {
  const t = await reset();
  // cy pays ada 900, ada pays cy 500 (cy 600). Raising the first by 1000 alone is
  // unaffordable; raising the second by 1000 in the same batch nets cy to zero.
  const a = await call('POST', '/payments', { token: t.cy, key: 'a', body: { to_handle: 'ada', amount: 900 } });
  const b = await call('POST', '/payments', { token: t.ada, key: 'b', body: { to_handle: 'cy', amount: 500 } });
  const at = b.body.created_at;
  const combined = { corrections: [fix({ payment_id: a.body.payment_id, amount: 1900, effective_at: at }), fix({ payment_id: b.body.payment_id, amount: 1500, effective_at: at })] };
  const single = { corrections: [combined.corrections[0]] };
  assert.strictEqual((await call('POST', '/correction-batches', { token: t.op, key: 'k', body: single })).body.error.code, 'insufficient_funds');
  assert.strictEqual((await call('POST', `/payments/${a.body.payment_id}/revisions`, { token: t.cy })).status, 405);
  assert.strictEqual((await call('GET', `/payments/${a.body.payment_id}/revisions`, { token: t.cy })).body.revisions.length, 1);
  const ok = await call('POST', '/correction-batches', { token: t.op, key: 'k', body: combined });
  assert.strictEqual(ok.status, 201, ok.text);
  assert.deepStrictEqual([(await me(t.cy)).balance, (await me(t.ada)).balance], [600, 10400]);
  // historical: reversing p_1 at its original time would overdraw bob before cy's later payments
  const t2 = await reset();
  await call('POST', '/payments', { token: t2.bob, key: 'spend', body: { to_handle: 'cy', amount: 2500 } });
  await new Promise((r) => setTimeout(r, 1100));
  await call('POST', '/payments', { token: t2.cy, key: 'back', body: { to_handle: 'bob', amount: 2000 } });
  const h = await call('POST', '/correction-batches', { token: t2.op, key: 'h', body: { corrections: [fix({ payment_id: 'p_1' })] } });
  assert.strictEqual(h.body.error.code, 'historical_overdraft', h.text);
  assert.strictEqual((await call('GET', '/payments/p_1/revisions', { token: t2.ada })).body.revisions.length, 1);
});

test('a batch and single corrections sharing a revision: exactly one succeeds', async () => {
  const t = await reset();
  const rs = await Promise.all([
    ...Array.from({ length: 10 }, (_, i) => call('POST', '/payments/p_1/corrections', { token: t.ada, key: `s${i}`, body: fix({ amount: 400 + i }) })),
    ...Array.from({ length: 10 }, (_, i) => call('POST', '/correction-batches', { token: t.op, key: `b${i}`, body: { corrections: [fix({ payment_id: 'p_1', amount: 300 + i })] } })),
  ]);
  assert.strictEqual(rs.filter((r) => r.status === 201).length, 1);
  assert.ok(rs.every((r) => r.status === 201 || r.body.error.code === 'stale_revision'));
});

test('exports round-trip refunds and batches; a stage-3 snapshot keeps its frozen entries after the upgrade', async (t) => {
  const s4 = await reset();
  await call('POST', '/payments/p_1/refunds', { token: s4.bob, key: 'r', body: { amount: 100 } });
  await call('POST', '/correction-batches', { token: s4.op, key: 'b', body: { corrections: [fix({ payment_id: 'p_1', amount: 400 })] } });
  const exp = await call('GET', '/_test/export');
  await reset();
  assert.strictEqual((await call('POST', '/_test/import', { raw: exp.text })).status, 204);
  assert.strictEqual((await call('POST', '/payments/p_1/refunds', { token: s4.bob, key: 'r2', body: { amount: 301 } })).body.error.code, 'refund_exceeds_payment');
  const bad = JSON.parse(exp.text);
  bad.state.payments.find((x) => x.payment.refund_of).payment.amount = 450;
  assert.strictEqual((await call('POST', '/_test/import', { body: bad })).status, 422, 'refunds over the corrected amount are refused');
  const stage3 = path.join(__dirname, '..', '..', 'stage-3', 'src', 'server.js');
  if (!fs.existsSync(stage3)) {
    t.skip('stage-3 service not present');
    return;
  }
  const old = client(await startService(stage3));
  assert.strictEqual((await old('POST', '/_test/reset', { body: fixture() })).status, 204);
  const ada = (await old('POST', '/auth/login', { body: { email: 'ada@example.com', password: 'correct horse' } })).body.token;
  await old('POST', '/payments', { token: ada, key: 'o', body: { to_handle: 'cy', amount: 50 } });
  const page = (await old('GET', '/statement?limit=1', { token: ada })).body;
  const exp3 = await old('GET', '/_test/export');
  assert.strictEqual((await call('POST', '/_test/import', { raw: exp3.text })).status, 204);
  const again = (await call('GET', `/statement?snapshot=${q(page.snapshot)}&limit=1`, { token: ada })).body;
  assert.deepStrictEqual(again, page);
  const fresh = (await call('GET', '/statement', { token: ada })).body;
  assert.ok(fresh.entries.every((e) => e.payment.refund_of === null));
  assert.strictEqual((await call('POST', '/payments/p_1/refunds', { token: (await call('POST', '/auth/login', { body: { email: 'bob@example.com', password: 'correct horse' } })).body.token, key: 'up', body: { amount: 10 } })).status, 201);
});

'use strict';

// Builder stage-3 regression checks: revisions, corrections, as_of/known_at,
// statements and snapshots, historical holds, imports. Run: node --test test/*.test.js

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
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const T0 = Math.floor(Date.now() / 1000) * 1000;
const P1_AT = T0 - 2 * HOUR;

function fixture(extra = {}) {
  return {
    currency: 'EUR',
    minor_units: 2,
    users: [
      { id: 'u_ada', email: 'ada@example.com', password: 'correct horse', display_name: 'Ada', handle: 'ada', balance: 10000 },
      { id: 'u_bob', email: 'bob@example.com', password: 'correct horse', display_name: 'Bob', handle: 'bob', balance: 2500 },
      { id: 'u_cy', email: 'cy@example.com', password: 'correct horse', display_name: 'Cy', handle: 'cy', balance: 0 },
      { id: 'u_op', email: 'op@example.com', password: 'correct horse', display_name: 'Op', handle: 'op', balance: 0 },
    ],
    payments: [{ id: 'p_1', from_user_id: 'u_ada', to_user_id: 'u_bob', amount: 500, note: 'coffee', visibility: 'public', created_at: iso(P1_AT) }],
    settlement_operator_ids: ['u_op'],
    ...extra,
  };
}

async function reset(f = fixture()) {
  const r = await call('POST', '/_test/reset', { body: f });
  assert.strictEqual(r.status, 204, r.text);
  const t = {};
  for (const h of ['ada', 'bob', 'cy', 'op']) {
    t[h] = (await call('POST', '/auth/login', { body: { email: `${h}@example.com`, password: 'correct horse' } })).body.token;
  }
  return t;
}
const me = async (tok, query = '') => (await call('GET', `/me${query}`, { token: tok })).body;

test.before(async () => {
  call = client(await startService(path.join(__dirname, '..', 'src', 'server.js')));
});
test.after(() => children.forEach((c) => c.kill()));

test('seeded created_at, opening balances and GET /me as_of', async () => {
  const t = await reset();
  assert.strictEqual((await me(t.ada, `?as_of=${q(iso(P1_AT - 1000))}`)).balance, 10500, 'opening before anything moved');
  const at = await me(t.ada, `?as_of=${q(iso(P1_AT))}`);
  assert.deepStrictEqual([at.balance, at.total, at.available, at.held, at.as_of], [10000, 10000, 10000, 0, iso(P1_AT)], 'inclusive at exactly as_of, echoed');
  assert.strictEqual((await me(t.bob, `?as_of=${q('2020-01-01T00:00:00Z')}`)).balance, 2000);
  assert.strictEqual((await me(t.cy, '?as_of=2099-01-01T00:00:00%2B00:00')).balance, 0);
  for (const bad of ['2026-09-24', '2026-09-24T13:20:00', '']) {
    assert.strictEqual((await call('GET', `/me?as_of=${q(bad)}`, { token: t.ada })).status, 422, bad);
  }
  assert.strictEqual((await call('GET', '/me?known_at=', { token: t.ada })).status, 422);
  const future = fixture({ payments: [{ ...fixture().payments[0], created_at: iso(Date.now() + HOUR) }] });
  assert.strictEqual((await call('POST', '/_test/reset', { body: future })).status, 422);
  assert.strictEqual((await me(t.ada)).balance, 10000, 'a refused reset changes nothing');
  const feed = (await call('GET', '/activity', { token: t.ada })).body.payments;
  assert.strictEqual(feed[0].created_at, iso(P1_AT));
});

test('statement window, balances, pagination and snapshots', async () => {
  const t = await reset();
  await call('POST', '/payments', { token: t.ada, key: 's1', body: { to_handle: 'cy', amount: 300 } });
  await call('POST', '/payments', { token: t.bob, key: 's2', body: { to_handle: 'ada', amount: 1200 } });
  const full = await call('GET', '/statement', { token: t.ada });
  assert.strictEqual(full.status, 200, full.text);
  assert.strictEqual(full.body.opening_balance, 10500);
  // p_1 first; the two payments of this second are ordered by payment id
  const tail = full.body.entries.slice(1);
  assert.deepStrictEqual([full.body.entries[0].delta, ...tail.map((e) => e.delta).sort((x, y) => x - y)], [-500, -300, 1200]);
  assert.ok(tail[0].effective_at < tail[1].effective_at || tail[0].payment.payment_id < tail[1].payment.payment_id);
  const sum = full.body.entries.reduce((n, e) => n + e.delta, full.body.opening_balance);
  assert.strictEqual(sum, full.body.closing_balance);
  assert.strictEqual(full.body.closing_balance, 10900);
  assert.strictEqual(full.body.entries[0].payment.payment_id, 'p_1');
  assert.deepStrictEqual([full.body.entries[0].revision, full.body.entries[0].effective_at, full.body.entries[0].recorded_at], [1, iso(P1_AT), iso(P1_AT)]);
  assert.ok(typeof full.body.snapshot === 'string' && full.body.snapshot.length > 0);
  const window = await call('GET', `/statement?from=${q(iso(P1_AT + 1000))}`, { token: t.ada });
  assert.strictEqual(window.body.opening_balance, 10000);
  assert.strictEqual(window.body.entries.length, 2);
  const before = await call('GET', `/statement?to=${q(iso(P1_AT))}`, { token: t.ada });
  assert.deepStrictEqual([before.body.entries.length, before.body.closing_balance], [0, 10500], 'half-open: to excludes a payment at exactly to');
  // pagination keeps full-window values; snapshot pages stay frozen after writes
  const page1 = await call('GET', '/statement?limit=2', { token: t.ada });
  assert.deepStrictEqual([page1.body.entries.length, page1.body.has_more, page1.body.closing_balance], [2, true, 10900]);
  await call('POST', '/payments', { token: t.ada, key: 's3', body: { to_handle: 'cy', amount: 1 } });
  const page2 = await call('GET', `/statement?snapshot=${q(page1.body.snapshot)}&limit=2&offset=2`, { token: t.ada });
  assert.deepStrictEqual([page2.body.entries.length, page2.body.has_more, page2.body.closing_balance, page2.body.entries[0].balance_after], [1, false, 10900, 10900]);
  const beyond = await call('GET', `/statement?snapshot=${q(page1.body.snapshot)}&offset=10`, { token: t.ada });
  assert.deepStrictEqual([beyond.body.entries.length, beyond.body.has_more], [0, false]);
  assert.strictEqual((await call('GET', `/statement?snapshot=${q(page1.body.snapshot)}&from=${q(iso(T0))}`, { token: t.ada })).status, 422);
  assert.strictEqual((await call('GET', `/statement?snapshot=${q(page1.body.snapshot)}`, { token: t.bob })).status, 404);
  assert.strictEqual((await call('GET', '/statement?snapshot=nope', { token: t.ada })).status, 404);
  assert.strictEqual((await call('GET', '/statement')).status, 401);
  // only the caller's own payments, regardless of public visibility
  assert.ok((await call('GET', '/statement', { token: t.cy })).body.entries.every((e) => e.payment.from_user_id === 'u_cy' || e.payment.to_user_id === 'u_cy'));
  await reset();
  assert.strictEqual((await call('GET', `/statement?snapshot=${q(page1.body.snapshot)}`, { token: (await call('POST', '/auth/login', { body: { email: 'ada@example.com', password: 'correct horse' } })).body.token })).status, 404);
});

test('corrections: rules, revisions, replay, statements and known_at', async () => {
  const t = await reset();
  const body = { expected_revision: 1, amount: 400, effective_at: iso(P1_AT + 30 * 60 * 1000), reason: 'corrected amount' };
  assert.strictEqual((await call('POST', '/payments/p_1/corrections', { token: t.bob, key: 'c1', body })).status, 403);
  assert.strictEqual((await call('POST', '/payments/p_1/corrections', { token: t.cy, key: 'c1', body })).status, 403);
  assert.strictEqual((await call('POST', '/payments/p_nope/corrections', { token: t.ada, key: 'c1', body })).status, 404);
  assert.strictEqual((await call('POST', '/payments/p_1/corrections', { token: t.ada, body })).status, 400);
  for (const bad of [{ ...body, expected_revision: 0 }, { ...body, amount: -1 }, { ...body, reason: '' }, { ...body, effective_at: iso(Date.now() + HOUR) }, { ...body, effective_at: '2026-09-20' }]) {
    assert.strictEqual((await call('POST', '/payments/p_1/corrections', { token: t.ada, key: 'c1', body: bad })).status, 422, JSON.stringify(bad));
  }
  const ok = await call('POST', '/payments/p_1/corrections', { token: t.ada, key: 'c1', body });
  assert.strictEqual(ok.status, 201, ok.text);
  assert.deepStrictEqual([ok.body.payment_id, ok.body.revision, ok.body.amount, ok.body.effective_at, ok.body.reason], ['p_1', 2, 400, body.effective_at, 'corrected amount']);
  assert.ok(Date.parse(ok.body.recorded_at) > P1_AT);
  assert.deepStrictEqual([(await me(t.ada)).balance, (await me(t.bob)).balance], [10100, 2400]);
  assert.strictEqual((await call('POST', '/payments/p_1/corrections', { token: t.ada, key: 'c2', body })).body.error.code, 'stale_revision');
  const second = await call('POST', '/payments/p_1/corrections', { token: t.ada, key: 'c2', body: { ...body, expected_revision: 2, amount: 0, reason: 'reversed' } });
  assert.strictEqual(second.status, 201);
  assert.ok(Date.parse(second.body.recorded_at) > Date.parse(ok.body.recorded_at), 'recorded times strictly increase');
  const replay = await call('POST', '/payments/p_1/corrections', { token: t.ada, key: 'c1', body });
  assert.deepStrictEqual([replay.status, replay.body], [200, ok.body]);
  assert.strictEqual((await call('POST', '/payments/p_1/corrections', { token: t.ada, key: 'c1', body: { ...body, reason: 'x' } })).body.error.code, 'idempotency_key_reuse');
  const revs = await call('GET', '/payments/p_1/revisions', { token: t.bob });
  assert.deepStrictEqual(revs.body.revisions.map((r) => [r.revision, r.amount, r.reason]), [[1, 500, ''], [2, 400, 'corrected amount'], [3, 0, 'reversed']]);
  assert.strictEqual((await call('GET', '/payments/p_1/revisions', { token: t.cy })).status, 404);
  assert.strictEqual((await call('GET', '/payments/p_1/revisions')).status, 401);
  // the feed keeps the original payment; no new feed items
  const feed = (await call('GET', '/activity', { token: t.cy })).body.payments;
  assert.deepStrictEqual(feed.map((p) => [p.payment_id, p.amount]), [['p_1', 500]]);
  // statement uses the selected revision; known_at selects by recorded time
  const st = (await call('GET', '/statement', { token: t.bob })).body;
  assert.deepStrictEqual(st.entries.map((e) => [e.payment.amount, e.delta, e.revision]), [[0, 0, 3]]);
  assert.strictEqual(st.closing_balance, 2000);
  const known = (await call('GET', `/statement?known_at=${q(iso(P1_AT))}`, { token: t.bob })).body;
  assert.deepStrictEqual([known.entries.map((e) => [e.payment.amount, e.revision]), known.closing_balance, known.known_at], [[[500, 1]], 2500, iso(P1_AT)]);
  const nothingKnown = (await call('GET', `/statement?known_at=${q(iso(P1_AT - 1000))}`, { token: t.bob })).body;
  assert.deepStrictEqual([nothingKnown.entries.length, nothingKnown.closing_balance], [0, 2000]);
  const viewAt = await me(t.bob, `?as_of=${q(iso(P1_AT + 60 * 60 * 1000))}&known_at=${q(ok.body.recorded_at)}`);
  assert.deepStrictEqual([viewAt.balance, viewAt.known_at], [2400, ok.body.recorded_at]);
  const total = (await me(t.ada)).balance + (await me(t.bob)).balance + (await me(t.cy)).balance + (await me(t.op)).balance;
  assert.strictEqual(total, 12500);
});

test('insufficient_funds before historical_overdraft; failures change nothing', async () => {
  const t = await reset();
  assert.strictEqual((await call('POST', '/payments', { token: t.bob, key: 'b1', body: { to_handle: 'cy', amount: 2400 } })).status, 201);
  const reverse = { expected_revision: 1, amount: 0, effective_at: iso(P1_AT), reason: 'refund' };
  assert.strictEqual((await call('POST', '/payments/p_1/corrections', { token: t.ada, key: 'h1', body: reverse })).body.error.code, 'insufficient_funds');
  await sleep(1100); // a later instant, so the dip below zero stays a separate boundary
  assert.strictEqual((await call('POST', '/payments', { token: t.cy, key: 'y1', body: { to_handle: 'bob', amount: 1000 } })).status, 201);
  const r = await call('POST', '/payments/p_1/corrections', { token: t.ada, key: 'h1', body: reverse });
  assert.strictEqual(r.body.error.code, 'historical_overdraft', r.text);
  assert.strictEqual((await call('GET', '/payments/p_1/revisions', { token: t.ada })).body.revisions.length, 1);
  assert.deepStrictEqual([(await me(t.ada)).balance, (await me(t.bob)).balance], [10000, 1100]);
  // the same key stays usable after a failure
  const moved = await call('POST', '/payments/p_1/corrections', { token: t.ada, key: 'h1', body: { ...reverse, amount: 500, effective_at: iso(P1_AT - 1000), reason: 'earlier' } });
  assert.strictEqual(moved.status, 201, moved.text);
  // increase beyond the sender's available amount
  const big = await call('POST', '/payments/p_1/corrections', { token: t.ada, key: 'h2', body: { expected_revision: 2, amount: 1000000000, effective_at: iso(P1_AT), reason: 'too much' } });
  assert.strictEqual(big.body.error.code, 'insufficient_funds');
});

test('concurrent corrections with one expected revision: exactly one succeeds', async () => {
  const t = await reset();
  const rs = await Promise.all(Array.from({ length: 20 }, (_, i) => call('POST', '/payments/p_1/corrections', {
    token: t.ada, key: `k${i}`, body: { expected_revision: 1, amount: 100 + i, effective_at: iso(P1_AT), reason: `r${i}` },
  })));
  assert.strictEqual(rs.filter((r) => r.status === 201).length, 1);
  assert.ok(rs.every((r) => r.status === 201 || r.body.error.code === 'stale_revision'));
  assert.strictEqual((await call('GET', '/payments/p_1/revisions', { token: t.ada })).body.revisions.length, 2);
});

test('linked payments are immutable; historical holds; closed_at', async () => {
  const t = await reset();
  const st = await call('POST', '/settlements', { token: t.op, key: 'st', body: { transfers: [{ from_handle: 'ada', to_handle: 'cy', amount: 100 }] } });
  const member = st.body.payments[0].payment_id;
  assert.strictEqual((await call('POST', `/payments/${member}/corrections`, { token: t.ada, key: 'l1', body: { expected_revision: 1, amount: 50, effective_at: iso(T0), reason: 'x' } })).body.error.code, 'linked_payment_immutable');
  const before = Date.now();
  await sleep(1100);
  const auth = await call('POST', '/authorizations', { token: t.ada, key: 'a1', body: { to_handle: 'bob', amount: 3000 } });
  assert.strictEqual(auth.body.closed_at, null);
  const id = auth.body.authorization_id;
  const created = Date.parse(auth.body.created_at);
  assert.deepStrictEqual([(await me(t.ada, `?as_of=${q(iso(before - 1000))}`)).held, (await me(t.ada, `?as_of=${q(auth.body.created_at)}`)).held], [0, 3000]);
  const cap = await call('POST', `/authorizations/${id}/capture`, { token: t.bob, key: 'cp', body: { amount: 1000, final: false } });
  assert.strictEqual((await call('POST', `/payments/${cap.body.payment_id}/corrections`, { token: t.ada, key: 'l2', body: { expected_revision: 1, amount: 50, effective_at: iso(T0), reason: 'x' } })).body.error.code, 'linked_payment_immutable');
  await sleep(1100);
  const v = await call('POST', `/authorizations/${id}/void`, { token: t.ada });
  assert.ok(v.body.closed_at && Date.parse(v.body.closed_at) >= Date.parse(cap.body.created_at));
  const now = await me(t.ada);
  assert.deepStrictEqual([now.held, now.total, now.available], [0, 8900, 8900]);
  const atCapture = await me(t.ada, `?as_of=${q(cap.body.created_at)}`);
  assert.deepStrictEqual([atCapture.total, atCapture.held, atCapture.available], [8900, 2000, 6900]);
  const knownBeforeVoid = await me(t.ada, `?known_at=${q(cap.body.created_at)}`);
  assert.deepStrictEqual([knownBeforeVoid.held, knownBeforeVoid.total], [2000, 8900]);
  const beyondExpiry = await me(t.ada, `?as_of=${q(iso(Date.now() + 2 * HOUR))}&known_at=${q(cap.body.created_at)}`);
  assert.strictEqual(beyondExpiry.held, 0, 'an open hold expires at its deadline in future views');
  // statements contain money movements only: the capture once, no hold entries
  const stmt = (await call('GET', '/statement', { token: t.ada })).body;
  assert.strictEqual(stmt.entries.filter((e) => e.payment.authorization_id === id).length, 1);
});

test('imports: stage-2 export and stage-3 round trip keep history', async (t) => {
  const s3 = await reset();
  await call('POST', '/payments/p_1/corrections', { token: s3.ada, key: 'i1', body: { expected_revision: 1, amount: 450, effective_at: iso(P1_AT), reason: 'fix' } });
  const exp = await call('GET', '/_test/export');
  await reset();
  assert.strictEqual((await call('POST', '/_test/import', { raw: exp.text })).status, 204);
  assert.strictEqual((await call('GET', '/payments/p_1/revisions', { token: s3.ada })).body.revisions.length, 2);
  assert.strictEqual((await me(s3.ada, `?as_of=${q(iso(P1_AT - 1000))}`)).balance, 10500, 'opening preserved');
  const stage2 = path.join(__dirname, '..', '..', 'stage-2', 'src', 'server.js');
  if (!fs.existsSync(stage2)) {
    t.skip('stage-2 service not present');
    return;
  }
  const old = client(await startService(stage2));
  const f = fixture();
  delete f.payments[0].created_at;
  assert.strictEqual((await old('POST', '/_test/reset', { body: f })).status, 204);
  const ada = (await old('POST', '/auth/login', { body: { email: 'ada@example.com', password: 'correct horse' } })).body.token;
  await old('POST', '/payments', { token: ada, key: 'o1', body: { to_handle: 'cy', amount: 250 } });
  const id = (await old('POST', '/authorizations', { token: ada, key: 'o2', body: { to_handle: 'bob', amount: 1000 } })).body.authorization_id;
  const exp2 = await old('GET', '/_test/export');
  assert.strictEqual((await call('POST', '/_test/import', { raw: exp2.text })).status, 204);
  const m = await me(ada);
  assert.deepStrictEqual([m.total, m.held, m.available], [9750, 1000, 8750]);
  const st = (await call('GET', '/statement', { token: ada })).body;
  assert.deepStrictEqual([st.opening_balance, st.closing_balance, st.entries.length], [10500, 9750, 2]);
  const a = (await call('GET', '/authorizations', { token: ada })).body.authorizations.find((x) => x.authorization_id === id);
  assert.strictEqual(a.closed_at, null);
  assert.strictEqual((await call('POST', '/payments/p_1/corrections', { token: ada, key: 'o3', body: { expected_revision: 1, amount: 400, effective_at: iso(Date.now() - 1000), reason: 'after upgrade' } })).status, 201);
});

test('snapshot tokens survive export/import (ruling S3-3); destination tokens and reset clear them', async () => {
  const t = await reset();
  const first = (await call('GET', '/statement?limit=1', { token: t.ada })).body;
  const exp = await call('GET', '/_test/export');
  const t2 = await reset();
  const dest = (await call('GET', '/statement', { token: t2.ada })).body.snapshot;
  // writes after the snapshot do not change it
  await call('POST', '/payments', { token: t2.ada, key: 'w', body: { to_handle: 'cy', amount: 5 } });
  assert.strictEqual((await call('POST', '/_test/import', { raw: exp.text })).status, 204);
  const again = (await call('GET', `/statement?snapshot=${q(first.snapshot)}&limit=1`, { token: t.ada })).body;
  assert.deepStrictEqual(again, first);
  assert.strictEqual((await call('GET', `/statement?snapshot=${q(dest)}`, { token: t.ada })).status, 404);
  await call('POST', '/payments/p_1/corrections', { token: t.ada, key: 'z', body: { expected_revision: 1, amount: 1, effective_at: iso(P1_AT), reason: 'r' } });
  assert.deepStrictEqual((await call('GET', `/statement?snapshot=${q(first.snapshot)}&limit=1`, { token: t.ada })).body, first, 'corrections after a snapshot do not change it');
  await reset();
  const fresh = (await call('POST', '/auth/login', { body: { email: 'ada@example.com', password: 'correct horse' } })).body.token;
  assert.strictEqual((await call('GET', `/statement?snapshot=${q(first.snapshot)}`, { token: fresh })).status, 404);
});

test('a seeded open hold already expired at reset still held funds between creation and expiry', async () => {
  const day = (d) => `2020-01-0${d}T00:00:00+00:00`;
  const users = ['ada', 'bob', 'cy', 'op'].map((h) => ({ id: `u_${h}`, email: `${h}@example.com`, password: 'correct horse', display_name: h, handle: h, balance: 300 }));
  const t = await reset({
    currency: 'EUR', minor_units: 2, users,
    payments: [
      { id: 'p_out', from_user_id: 'u_ada', to_user_id: 'u_bob', amount: 200, created_at: day(5) },
      { id: 'p_in', from_user_id: 'u_bob', to_user_id: 'u_ada', amount: 200, created_at: day(6) },
    ],
    authorizations: [{ id: 'a_old', from_user_id: 'u_ada', to_user_id: 'u_bob', amount: 250, status: 'open', created_at: day(2), expires_at: day(4) }],
  });
  const at = await me(t.ada, `?as_of=${q(day(2))}&known_at=${q(day(2))}`);
  assert.deepStrictEqual([at.total, at.held, at.available], [300, 250, 50]);
  assert.strictEqual((await me(t.ada, `?as_of=${q(day(4))}`)).held, 0, 'released at expires_at');
  assert.strictEqual((await me(t.ada)).held, 0);
  const a = (await call('GET', '/authorizations', { token: t.ada })).body.authorizations[0];
  assert.deepStrictEqual([a.status, a.closed_at], ['expired', day(4)]);
});

test('payments created in the same second appear in creation order in statements', async () => {
  const t = await reset();
  const deltas = [];
  for (const amount of [300, 200, 100, 50]) {
    await call('POST', '/payments', { token: t.ada, key: `o${amount}`, body: { to_handle: 'cy', amount } });
    deltas.push(-amount);
  }
  const st = (await call('GET', `/statement?from=${q(iso(T0))}`, { token: t.ada })).body;
  const ids = st.entries.map((e) => e.payment.payment_id);
  assert.deepStrictEqual(ids, [...ids].sort(), 'ordered by payment id');
  assert.deepStrictEqual(st.entries.map((e) => e.delta), deltas);
});

test('historical balances are exact around 2^53 (R2)', async () => {
  const MAX = 9007199254740992;
  const users = [
    { id: 'u_a', email: 'a@x.io', password: 'correct horse', display_name: 'A', handle: 'a', balance: MAX - 1 },
    { id: 'u_b', email: 'b@x.io', password: 'correct horse', display_name: 'B', handle: 'b', balance: 2 },
  ];
  const r = await call('POST', '/_test/reset', { body: { currency: 'EUR', minor_units: 2, users, payments: [
    { id: 'p_in', from_user_id: 'u_b', to_user_id: 'u_a', amount: 1, created_at: '2020-01-01T00:00:00+00:00' },
    { id: 'p_out', from_user_id: 'u_a', to_user_id: 'u_b', amount: 1, created_at: '2020-01-02T00:00:00+00:00' },
  ] } });
  assert.strictEqual(r.status, 204);
  const login = async (e) => (await call('POST', '/auth/login', { body: { email: e, password: 'correct horse' } })).body.token;
  const a = await login('a@x.io');
  const b = await login('b@x.io');
  const c = await call('POST', '/payments/p_in/corrections', { token: b, key: 'x', body: { expected_revision: 1, amount: 2, effective_at: '2020-01-03T00:00:00+00:00', reason: 'more' } });
  assert.strictEqual(c.status, 201, c.text);
  const raw = (await call('GET', `/me?as_of=${q('2020-01-04T00:00:00+00:00')}`, { token: a })).text;
  assert.match(raw, /"balance":9007199254740992,/);
  const st = (await call('GET', '/statement', { token: a })).text;
  assert.match(st, /"closing_balance":9007199254740992/);
});

test('a correction credit above 2^53 is 422 and changes nothing', async () => {
  const MAX = 9007199254740992;
  const users = [
    { id: 'u_a', email: 'a@x.io', password: 'correct horse', display_name: 'A', handle: 'a', balance: 100 },
    { id: 'u_b', email: 'b@x.io', password: 'correct horse', display_name: 'B', handle: 'b', balance: MAX },
  ];
  assert.strictEqual((await call('POST', '/_test/reset', { body: { currency: 'EUR', minor_units: 2, users, payments: [
    { id: 'p', from_user_id: 'u_a', to_user_id: 'u_b', amount: 1, created_at: '2020-01-01T00:00:00+00:00' }] } })).status, 204);
  const a = (await call('POST', '/auth/login', { body: { email: 'a@x.io', password: 'correct horse' } })).body.token;
  const b = (await call('POST', '/auth/login', { body: { email: 'b@x.io', password: 'correct horse' } })).body.token;
  const r = await call('POST', '/payments/p/corrections', { token: a, key: 'k', body: { expected_revision: 1, amount: 2, effective_at: '2020-01-01T00:00:00+00:00', reason: 'more' } });
  assert.deepStrictEqual([r.status, r.body.error.code], [422, 'validation_failed']);
  assert.match((await call('GET', '/me', { token: a })).text, /"balance":100,/);
  assert.match((await call('GET', '/me', { token: b })).text, /"balance":9007199254740992,/);
  assert.strictEqual((await call('GET', '/payments/p/revisions', { token: a })).body.revisions.length, 1);
});

test('import refuses inconsistent history: negative or mismatched openings', async () => {
  const t = await reset();
  const exp = (await call('GET', '/_test/export')).body;
  const tamper = (fn) => { const d = JSON.parse(JSON.stringify(exp)); fn(d.state); return d; };
  const neg = tamper((st) => { st.openings.find((o) => o.user_id === 'u_cy').opening = -1; });
  assert.strictEqual((await call('POST', '/_test/import', { body: neg })).status, 422);
  const off = tamper((st) => { st.openings.find((o) => o.user_id === 'u_ada').opening += 1; });
  assert.strictEqual((await call('POST', '/_test/import', { body: off })).status, 422);
  assert.strictEqual((await me(t.ada)).balance, 10000, 'a refused import changes nothing');
  assert.strictEqual((await call('POST', '/_test/import', { body: exp })).status, 204);
});

test('import refuses impossible hold histories and altered revision 1', async () => {
  const t = await reset();
  const id = (await call('POST', '/authorizations', { token: t.ada, key: 'h', body: { to_handle: 'bob', amount: 20 } })).body.authorization_id;
  assert.strictEqual((await call('POST', `/authorizations/${id}/capture`, { token: t.bob, key: 'c', body: { amount: 5, final: false } })).status, 201);
  const exp = (await call('GET', '/_test/export')).body;
  const tamper = (fn) => { const d = JSON.parse(JSON.stringify(exp)); fn(d.state); return d; };
  const ev = (st) => st.auth_events.find((e) => e.authorization_id === id);
  for (const [name, fn] of [
    ['negative initial hold', (st) => { ev(st).initialHold = -1; }],
    ['negative capture', (st) => { ev(st).captures[0].amount = -5; }],
    ['revision 1 recorded_at moved', (st) => { st.revisions.find((r) => r.payment_id === 'p_1').revisions[0].recorded_at = '2020-01-01T00:00:00+00:00'; }],
  ]) {
    assert.strictEqual((await call('POST', '/_test/import', { body: tamper(fn) })).status, 422, name);
  }
  assert.strictEqual((await me(t.ada)).held, 15, 'refused imports change nothing');
  assert.strictEqual((await call('POST', '/_test/import', { body: exp })).status, 204);
  assert.strictEqual((await me(t.ada)).held, 15);
});

test('void then pay in the same second keeps a valid history; own export re-imports', async () => {
  const users = [
    { id: 'u_a', email: 'a@x.io', password: 'correct horse', display_name: 'A', handle: 'a', balance: 100 },
    { id: 'u_b', email: 'b@x.io', password: 'correct horse', display_name: 'B', handle: 'b', balance: 0 },
  ];
  assert.strictEqual((await call('POST', '/_test/reset', { body: { currency: 'EUR', minor_units: 2, users } })).status, 204);
  const a = (await call('POST', '/auth/login', { body: { email: 'a@x.io', password: 'correct horse' } })).body.token;
  for (let round = 0; round < 3; round++) {
    const id = (await call('POST', '/authorizations', { token: a, key: `h${round}`, body: { to_handle: 'b', amount: 100 } })).body.authorization_id;
    assert.strictEqual((await call('POST', `/authorizations/${id}/void`, { token: a })).status, 200);
    const p = await call('POST', '/payments', { token: a, key: `p${round}`, body: { to_handle: 'b', amount: 100 } });
    assert.strictEqual(p.status, 201);
    const view = await me(a, `?as_of=${q(p.body.created_at)}`);
    assert.deepStrictEqual([view.total, view.held, view.available], [0, 0, 0]);
    const exp = await call('GET', '/_test/export');
    assert.strictEqual((await call('POST', '/_test/import', { raw: exp.text })).status, 204);
    const b = (await call('POST', '/auth/login', { body: { email: 'b@x.io', password: 'correct horse' } })).body.token;
    assert.strictEqual((await call('POST', '/payments', { token: b, key: `back${round}`, body: { to_handle: 'a', amount: 100 } })).status, 201);
  }
});

test('a statement read right after a payment always includes it (default to follows committed events)', async () => {
  const t = await reset();
  for (let i = 0; i < 40; i++) {
    const p = await call('POST', '/payments', { token: t.ada, key: `z${i}`, body: { to_handle: 'cy', amount: 1 } });
    const st = (await call('GET', '/statement?limit=200', { token: t.ada })).body;
    assert.ok(st.entries.some((e) => e.payment.payment_id === p.body.payment_id), `payment ${i} missing from the default window`);
    const m = await me(t.ada, `?known_at=${q(p.body.created_at)}`);
    assert.strictEqual(m.balance, (await me(t.ada)).balance);
  }
});

test('seeded holds past expiry or closed, created_at omitted: own export re-imports', async () => {
  for (const status of ['expired', 'open', 'voided', 'captured']) {
    const users = [
      { id: 'u_a', email: 'a@x.io', password: 'correct horse', display_name: 'A', handle: 'a', balance: 100 },
      { id: 'u_b', email: 'b@x.io', password: 'correct horse', display_name: 'B', handle: 'b', balance: 0 },
    ];
    const authorizations = [{ id: 'a_past', from_user_id: 'u_a', to_user_id: 'u_b', amount: 10, note: '', visibility: 'private', status, expires_at: '2020-01-01T00:00:00+00:00' }];
    assert.strictEqual((await call('POST', '/_test/reset', { body: { currency: 'EUR', minor_units: 2, users, authorizations } })).status, 204, status);
    const exp = await call('GET', '/_test/export');
    assert.strictEqual((await call('POST', '/_test/import', { raw: exp.text })).status, 204, status);
    const a = (await call('POST', '/auth/login', { body: { email: 'a@x.io', password: 'correct horse' } })).body.token;
    for (const at of ['2019-12-31T00:00:00+00:00', '2020-01-02T00:00:00+00:00']) {
      const m = await me(a, `?as_of=${q(at)}`);
      assert.deepStrictEqual([m.total, m.held, m.available], [100, 0, 100], `${status} at ${at}`);
    }
  }
});

test('stage-2 exports with seeded past-expiry holds import, and the stage-3 export re-imports', async (t) => {
  const stage2 = path.join(__dirname, '..', '..', 'stage-2', 'src', 'server.js');
  if (!fs.existsSync(stage2)) {
    t.skip('stage-2 service not present');
    return;
  }
  const old = client(await startService(stage2));
  for (const status of ['expired', 'open', 'voided', 'captured']) {
    const users = [
      { id: 'u_a', email: 'a@x.io', password: 'correct horse', display_name: 'A', handle: 'a', balance: 100 },
      { id: 'u_b', email: 'b@x.io', password: 'correct horse', display_name: 'B', handle: 'b', balance: 0 },
    ];
    const authorizations = [{ id: 'a_past', from_user_id: 'u_a', to_user_id: 'u_b', amount: 10, note: '', visibility: 'private', status, expires_at: '2020-01-01T00:00:00+00:00' }];
    assert.strictEqual((await old('POST', '/_test/reset', { body: { currency: 'EUR', minor_units: 2, users, authorizations } })).status, 204, status);
    const exp2 = await old('GET', '/_test/export');
    assert.strictEqual((await call('POST', '/_test/import', { raw: exp2.text })).status, 204, `stage-2 ${status}`);
    const exp3 = await call('GET', '/_test/export');
    assert.strictEqual((await call('POST', '/_test/import', { raw: exp3.text })).status, 204, `stage-3 re-import ${status}`);
    const a = (await call('POST', '/auth/login', { body: { email: 'a@x.io', password: 'correct horse' } })).body.token;
    const m = await me(a, `?as_of=${q('2020-01-02T00:00:00+00:00')}`);
    assert.deepStrictEqual([m.total, m.held, m.available], [100, 0, 100], status);
  }
});

test('import refuses an open hold marked without history or with a mismatched initial hold', async () => {
  const t = await reset();
  const id = (await call('POST', '/authorizations', { token: t.ada, key: 'nh', body: { to_handle: 'bob', amount: 20 } })).body.authorization_id;
  const exp = (await call('GET', '/_test/export')).body;
  const tamper = (fn) => { const d = JSON.parse(JSON.stringify(exp)); fn(d.state.auth_events.find((e) => e.authorization_id === id)); return d; };
  assert.strictEqual((await call('POST', '/_test/import', { body: tamper((e) => { e.noHistory = true; }) })).status, 422);
  assert.strictEqual((await call('POST', '/_test/import', { body: tamper((e) => { e.initialHold = 10; }) })).status, 422);
  assert.strictEqual((await call('POST', '/_test/import', { body: tamper((e) => { e.createdMs -= 5000; }) })).status, 422);
  assert.strictEqual((await call('POST', '/_test/import', { body: exp })).status, 204);
  assert.strictEqual((await me(t.ada)).held, 20);
});

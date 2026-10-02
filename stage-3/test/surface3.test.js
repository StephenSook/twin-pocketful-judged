'use strict';
// Unit checks for the stage-3 additions to src/validate.js and src/snapshots.js (owned by surface).
const test = require('node:test');
const a = require('node:assert');
const v = require('../src/validate.js');
const { SnapshotStore } = require('../src/snapshots.js');
const P = (s) => v.parseJsonBuffer(Buffer.from(s)).value;
const q = (s) => new URLSearchParams(s);

test('parseInstant accepts strict RFC 3339 instants with an offset', () => {
  const r = v.parseInstant('2026-09-24T13:20:00+02:00', 'as_of');
  a.deepStrictEqual(r.value, { raw: '2026-09-24T13:20:00+02:00', ms: Date.UTC(2026, 8, 24, 11, 20, 0) });
  a.strictEqual(v.parseInstant('2026-09-24T13:20:00Z', 'x').value.ms, Date.UTC(2026, 8, 24, 13, 20));
  a.strictEqual(v.parseInstant('2026-09-24t13:20:00z', 'x').ok, true);
  a.strictEqual(v.parseInstant('2026-09-24T13:20:00.9999-01:30', 'x').value.ms, Date.UTC(2026, 8, 24, 14, 50, 0, 999));
  a.strictEqual(v.parseInstant('2024-02-29T00:00:00+00:00', 'x').ok, true);
  a.strictEqual(v.parseInstant('0001-01-01T00:00:00+00:00', 'x').value.ms, new Date('0001-01-01T00:00:00Z').getTime());
});

test('parseInstant rejects naive, date-only, empty and out-of-range values with 422', () => {
  for (const s of ['', '2026-09-24', '2026-09-24T13:20:00', '2026-09-24 13:20:00+00:00', '2026-09-24T13:20+00:00',
    '2026-02-29T00:00:00+00:00', '2026-13-01T00:00:00Z', '2026-09-31T00:00:00Z', '2026-09-24T24:00:00Z', '2026-09-24T13:60:00Z',
    '2026-09-24T13:20:60Z', '2026-09-24T13:20:00+24:00', '2026-09-24T13:20:00+0200', '2026-09-24T13:20:00.Z', ' 2026-09-24T13:20:00Z',
    '+2026-09-24T13:20:00Z', '2026-9-24T13:20:00Z']) {
    a.strictEqual(v.parseInstant(s, 'as_of').error.status, 422, JSON.stringify(s));
  }
  for (const x of [null, 5, true, {}, []]) a.strictEqual(v.parseInstant(x, 'effective_at').error.status, 422);
});

test('GET /me and /statement query parsing', () => {
  a.deepStrictEqual(v.parseMeQuery(q('')).value, { as_of: null, known_at: null });
  a.strictEqual(v.parseMeQuery(q('as_of=')).error.status, 422);
  a.strictEqual(v.parseMeQuery(q('known_at=2026-09-24')).error.status, 422);
  a.strictEqual(v.parseMeQuery(q('as_of=2026-09-24T13:20:00%2B00:00')).value.as_of.raw, '2026-09-24T13:20:00+00:00');
  // Ruling S3-2: an unencoded '+' offset (decoded as a space) is read as '+' and echoed with '+'.
  const plus = v.parseMeQuery(q('as_of=2026-09-24T13:20:00+02:00&known_at=2026-09-24T13:20:00.5+00:00')).value;
  a.deepStrictEqual([plus.as_of.raw, plus.as_of.ms, plus.known_at.raw], ['2026-09-24T13:20:00+02:00', Date.UTC(2026, 8, 24, 11, 20), '2026-09-24T13:20:00.5+00:00']);
  a.strictEqual(v.validateStatementQuery(q('from=2026-01-01T00:00:00+00:00&to=2026-02-01T00:00:00+01:00')).value.to.raw, '2026-02-01T00:00:00+01:00');
  for (const s of ['2026-09-24T13:20:00  00:00', '2026-09-24T13:20:00 0000', '2026-09-24 13:20:00 00:00', '2026-09-24T13:20:00 00:00 ', ' 2026-09-24T13:20:00 00:00', '2026-09-24T13:20 00:00']) {
    a.strictEqual(v.parseMeQuery(new URLSearchParams([['as_of', s]])).error.status, 422, JSON.stringify(s));
  }
  // The strict body parser never applies the space rule.
  a.strictEqual(v.parseInstant('2026-09-24T13:20:00 00:00', 'effective_at').error.status, 422);
  const s = v.validateStatementQuery(q('from=2026-01-01T00:00:00Z&limit=10&offset=5&x=1')).value;
  a.deepStrictEqual([s.snapshot, s.from.raw, s.to, s.known_at, s.limit, s.offset], [null, '2026-01-01T00:00:00Z', null, null, 10, 5]);
  for (const k of ['from', 'to', 'known_at']) {
    a.strictEqual(v.validateStatementQuery(q(`snapshot=t&${k}=2026-01-01T00:00:00Z`)).error.status, 422, k);
    a.strictEqual(v.validateStatementQuery(q(`snapshot=t&${k}=`)).error.status, 422, k);
  }
  a.strictEqual(v.validateStatementQuery(q('snapshot=')).value.snapshot, '');
  a.strictEqual(v.validateStatementQuery(q('snapshot=t&limit=0')).error.status, 422);
  a.strictEqual(v.validateStatementQuery(q('to=')).error.status, 422);
});

test('validateCorrection: all fields required, every invalid case 422', () => {
  const now = Date.UTC(2026, 8, 24, 12);
  const good = { expected_revision: 1, amount: 400, effective_at: '2026-09-20T12:00:00+00:00', reason: 'corrected amount' };
  a.deepStrictEqual(v.validateCorrection(good, now).value, { expected_revision: 1, amount: 400, reason: 'corrected amount', effective_at: { raw: good.effective_at, ms: Date.UTC(2026, 8, 20, 12) } });
  a.strictEqual(v.validateCorrection({ ...good, amount: 0 }, now).value.amount, 0);
  a.strictEqual(v.validateCorrection({ ...good, effective_at: '2026-09-24T12:00:00Z' }, now).ok, true);
  a.strictEqual(v.validateCorrection({ ...good, reason: '😀'.repeat(200) }, now).ok, true);
  const bad = [
    { expected_revision: undefined }, { expected_revision: 0 }, { expected_revision: -1 }, { expected_revision: 1.5 }, { expected_revision: '1' }, { expected_revision: null },
    { amount: undefined }, { amount: -1 }, { amount: 1000000001 }, { amount: 2.5 }, { amount: '400' }, { amount: null }, { amount: true },
    { reason: undefined }, { reason: '' }, { reason: 'x'.repeat(201) }, { reason: 5 }, { reason: null },
    { effective_at: undefined }, { effective_at: '2026-09-20' }, { effective_at: '2026-09-24T12:00:01Z' }, { effective_at: 5 }, { effective_at: null },
  ];
  for (const patch of bad) {
    const body = { ...good, ...patch };
    for (const k of Object.keys(patch)) if (patch[k] === undefined) delete body[k];
    a.strictEqual(v.validateCorrection(body, now).error.status, 422, JSON.stringify(patch));
  }
  a.strictEqual(v.validateCorrection(P('{"expected_revision":1,"amount":400.0000000000001,"effective_at":"2026-09-20T12:00:00Z","reason":"r"}'), now).error.status, 422);
  a.strictEqual(v.validateCorrection(P('{"expected_revision":1e0,"amount":4e2,"effective_at":"2026-09-20T12:00:00Z","reason":"r"}'), now).value.amount, 400);
});

test('SnapshotStore pages a frozen result and scopes tokens to user and epoch', () => {
  const s = new SnapshotStore();
  const result = { opening_balance: 10, entries: [{ n: 1 }, { n: 2 }, { n: 3 }], closing_balance: 13 };
  const t = s.create('u1', result);
  result.entries.push({ n: 4 });
  result.opening_balance = 99;
  a.ok(typeof t === 'string' && t.length <= 64 && /^[A-Za-z0-9_-]+$/.test(t));
  let p = s.page('u1', t, 2, 0).value;
  a.deepStrictEqual(Object.keys(p), ['opening_balance', 'entries', 'closing_balance', 'has_more', 'snapshot']);
  a.deepStrictEqual([p.opening_balance, p.entries.map((e) => e.n), p.has_more, p.snapshot], [10, [1, 2], true, t]);
  p = s.page('u1', t, 2, 2).value;
  a.deepStrictEqual([p.entries.map((e) => e.n), p.has_more], [[3], false]);
  p = s.page('u1', t, 2, 3).value;
  a.deepStrictEqual([p.entries, p.has_more], [[], false]);
  p = s.page('u1', t, 50, 99).value;
  a.deepStrictEqual([p.entries, p.has_more], [[], false]);
  a.deepStrictEqual(s.page('u1', t, 3, 0).value.has_more, false);
  a.throws(() => { 'use strict'; s.page('u1', t, 1, 0).value.entries[0].n = 7; });
  a.strictEqual(s.page('u2', t, 2, 0).error.status, 404);
  a.strictEqual(s.page('u1', 'nope', 2, 0).error.code, 'not_found');
  a.strictEqual(s.page('u1', '', 2, 0).error.status, 404);
  s.clear();
  a.strictEqual(s.page('u1', t, 2, 0).error.status, 404);
  const t2 = s.create('u1', { opening_balance: 0, entries: [], closing_balance: 0 });
  a.notStrictEqual(t2, t);
  a.deepStrictEqual(s.page('u1', t2, 50, 0).value.entries, []);
});

test('SnapshotStore export/restore carries tokens across import (ruling S3-3)', () => {
  const src = new SnapshotStore();
  const t = src.create('u1', { opening_balance: 5, entries: [{ n: 1 }, { n: 2 }], closing_balance: 7, known_at: null });
  const data = JSON.parse(JSON.stringify(src.export()));
  const dst = new SnapshotStore();
  const old = dst.create('u9', { opening_balance: 0, entries: [], closing_balance: 0 });
  a.strictEqual(SnapshotStore.isValidExport(data), true);
  a.strictEqual(dst.restore(data), true);
  a.strictEqual(dst.page('u9', old, 50, 0).error.status, 404);
  const p = dst.page('u1', t, 1, 1).value;
  a.deepStrictEqual(p, { opening_balance: 5, entries: [{ n: 2 }], closing_balance: 7, known_at: null, has_more: false, snapshot: t });
  a.strictEqual(dst.page('u2', t, 1, 0).error.status, 404);
  const again = JSON.parse(JSON.stringify(dst.export()));
  a.strictEqual(dst.restore(again), true);
  a.strictEqual(dst.page('u1', t, 50, 0).value.entries.length, 2);
  for (const bad of [null, {}, [null], [{ token: '', user_id: 'u', result: { entries: [] } }], [{ token: 't', user_id: 1, result: { entries: [] } }],
    [{ token: 't', user_id: 'u', result: {} }], [{ token: 't', user_id: 'u', result: { entries: [] } }, { token: 't', user_id: 'u', result: { entries: [] } }]]) {
    a.strictEqual(dst.restore(bad), false, JSON.stringify(bad));
  }
  a.strictEqual(dst.page('u1', t, 50, 0).ok, true);
  dst.clear();
  a.strictEqual(dst.page('u1', t, 50, 0).error.status, 404);
  a.deepStrictEqual(dst.export(), []);
});

'use strict';
// Unit checks for the stage-4 additions to src/validate.js (owned by surface).
const test = require('node:test');
const a = require('node:assert');
const v = require('../src/validate.js');
const P = (s) => v.parseJsonBuffer(Buffer.from(s)).value;
const I = (s) => v.parseInstant(s, 'x').value;

test('validateRefund: amount by the payment rule, 422 otherwise', () => {
  a.deepStrictEqual(v.validateRefund({ amount: 200 }).value, { amount: 200 });
  a.strictEqual(v.validateRefund(P('{"amount":2e2}')).value.amount, 200);
  for (const x of [undefined, null, 0, -1, 1.5, 1000000001, '200', true, {}, []]) {
    a.strictEqual(v.validateRefund(x === undefined ? {} : { amount: x }).error.status, 422, JSON.stringify(x));
  }
  a.strictEqual(v.validateRefund(P('{"amount":200.0000000000001}')).error.status, 422);
  a.strictEqual(v.validateRefund({ amount: 1000000000 }).ok, true);
});

test('validateBatchShape: 1..32 objects with distinct string payment_ids', () => {
  const item = (id) => ({ payment_id: id, expected_revision: 1, amount: 0, effective_at: '2026-09-20T12:00:00+00:00', reason: 'r' });
  a.strictEqual(v.validateBatchShape({ corrections: [item('p_a'), item('p_b')] }).value.items.length, 2);
  a.strictEqual(v.validateBatchShape({ corrections: Array.from({ length: 32 }, (_, i) => item(`p${i}`)) }).ok, true);
  for (const bad of [undefined, null, {}, 'x', [], Array.from({ length: 33 }, (_, i) => item(`p${i}`)), [item('p'), item('p')], [1], [null], [[]],
    [{ ...item('p'), payment_id: 5 }], [{ expected_revision: 1 }]]) {
    a.strictEqual(v.validateBatchShape({ corrections: bad }).error.status, 422, JSON.stringify(bad));
  }
  // Item fields are not checked here (they keep input-order precedence).
  a.strictEqual(v.validateBatchShape({ corrections: [{ payment_id: 'p', amount: -5 }] }).ok, true);
});

test('validateCorrectionItem: ordinary correction rules plus payment_id', () => {
  const now = Date.UTC(2026, 8, 24, 12);
  const it = { payment_id: 'p_a', expected_revision: 1, amount: 0, effective_at: '2026-09-20T14:00:00+02:00', reason: 'reversal', extra: 1 };
  a.deepStrictEqual(v.validateCorrectionItem(it, now).value, { payment_id: 'p_a', expected_revision: 1, amount: 0, reason: 'reversal', effective_at: { raw: '2026-09-20T14:00:00+02:00', ms: Date.UTC(2026, 8, 20, 12), sub: '' } });
  for (const patch of [{ payment_id: 1 }, { expected_revision: 0 }, { amount: -1 }, { reason: '' }, { effective_at: '2026-09-25T00:00:00Z' }, { effective_at: '2026-09-20' }]) {
    a.strictEqual(v.validateCorrectionItem({ ...it, ...patch }, now).error.status, 422, JSON.stringify(patch));
  }
});

test('sameInstant compares exact instants across offset spellings', () => {
  a.strictEqual(v.sameInstant(I('2026-09-20T12:00:00+00:00'), I('2026-09-20T14:00:00+02:00')), true);
  a.strictEqual(v.sameInstant(I('2026-09-20T12:00:00Z'), I('2026-09-20T07:00:00.000-05:00')), true);
  a.strictEqual(v.sameInstant(I('2026-09-20T12:00:00.5Z'), I('2026-09-20T12:00:00.500000+00:00')), true);
  a.strictEqual(v.sameInstant(I('2026-09-20T12:00:00Z'), I('2026-09-20T12:00:01Z')), false);
  a.strictEqual(v.sameInstant(I('2026-09-20T12:00:00.1231Z'), I('2026-09-20T12:00:00.1239Z')), false);
  a.strictEqual(v.sameInstant(I('2026-09-20T12:00:00.1231Z'), I('2026-09-20T12:00:00.12310Z')), true);
});

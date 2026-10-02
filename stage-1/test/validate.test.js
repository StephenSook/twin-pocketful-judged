'use strict';
// Unit checks for src/validate.js (owned by surface).
const test = require('node:test');
const a = require('node:assert');
const v = require('../src/validate.js');
const P = (s) => v.parseJsonBuffer(Buffer.from(s)).value;

test('field validators, handles, pagination, shares, body parsing', () => {
  a.deepStrictEqual(v.validateAmount(JSON.parse('1e3')).value, 1000);
  a.deepStrictEqual(v.validateAmount(JSON.parse('1000.0')).value, 1000);
  for (const bad of ['1000', true, null, 0, -1, 1.5, 1000000001, {}, [], undefined]) a.strictEqual(v.validateAmount(bad).error.status, 422, String(bad));
  a.strictEqual(v.validateAmount(1000000000).value, 1000000000);
  a.strictEqual(v.validateNote(undefined).value, '');
  a.strictEqual(v.validateNote(null).error.status, 422);
  a.strictEqual(v.validateNote('😀'.repeat(200)).ok, true);
  a.strictEqual(v.validateNote('x'.repeat(201)).error.status, 422);
  a.strictEqual(v.validateVisibility(undefined).value, 'public');
  a.strictEqual(v.validateVisibility('PUBLIC').error.status, 422);
  a.strictEqual(v.validateVisibility(1).error.status, 422);
  a.strictEqual(v.deriveHandle('Ada.Lovelace+x@ex.com'), 'ada_lovelace_x');
  a.strictEqual(v.deriveHandle('ABCDEFGHIJKLMNOPQRSTUVWXYZ@x'), 'abcdefghijklmnopqrst');
  a.strictEqual(v.deriveHandle('é😀b@x'), '__b');
  a.strictEqual(v.deriveHandle('İ@example.test'), 'i_');
  a.strictEqual(v.deriveHandle('İ'.repeat(10) + 'ABC@x'), 'i_'.repeat(10));
  a.strictEqual(v.deriveHandle('ẞ@x'), '_');
  a.strictEqual(v.validateEmail('a@b').ok, true);
  for (const e of ['ab', '@b', 'a@', 'a@b@c', 'a b@c']) a.strictEqual(v.validateEmail(e).error.status, 422, e);
  a.strictEqual(v.validateEmail(5).error.status, 400);
  a.strictEqual(v.validatePassword('1234567').error.status, 422);
  a.strictEqual(v.validatePassword('12345678').ok, true);
  a.strictEqual(v.validateIdempotencyKey(undefined).error.code, 'missing_idempotency_key');
  a.strictEqual(v.validateIdempotencyKey('').error.status, 400);
  a.strictEqual(v.validateIdempotencyKey('k'.repeat(255)).ok, true);
  a.strictEqual(v.validateIdempotencyKey('k'.repeat(256)).error.status, 422);
  const q = (s) => new URLSearchParams(s);
  a.deepStrictEqual(v.parsePagination(q('')).value, { limit: 50, offset: 0 });
  for (const s of ['limit=0', 'limit=201', 'limit=1e1', 'limit=4.0', 'limit=+4', 'limit=', 'offset=-1', 'offset=1e9', 'offset=x']) a.strictEqual(v.parsePagination(q(s)).error.status, 422, s);
  a.deepStrictEqual(v.parsePagination(q('limit=200&offset=007')).value, { limit: 200, offset: 7 });
  a.strictEqual(v.parseDirection(q('direction=sideways')).error.status, 422);
  a.strictEqual(v.parseRequestStatus(q('status=paid')).value, 'paid');
  a.deepStrictEqual(v.splitShares(1000, 3), [334, 333, 333]);
  a.deepStrictEqual(v.splitShares(1, 3), [1, 0, 0]);
  a.deepStrictEqual(v.splitShares(10, 3), [4, 3, 3]);
  a.deepStrictEqual(v.splitShares(999, 3), [333, 333, 333]);
  a.deepStrictEqual(v.splitShares(5, 5), [1, 1, 1, 1, 1]);
  a.strictEqual(v.validateParticipantHandles(['a', 'a']).error.status, 422);
  a.strictEqual(v.validateParticipantHandles([]).error.status, 422);
  a.strictEqual(v.validateParticipantHandles('a').error.status, 400);
  a.strictEqual(v.validateTransfersShape([]).error.status, 422);
  a.strictEqual(v.validateTransfersShape(new Array(33).fill({})).error.status, 422);
  a.strictEqual(v.validateTransfersShape([1]).error.status, 422);
  a.strictEqual(v.validateTransferEntry({ from_handle: 'a', to_handle: 1, amount: 1 }).error.status, 422);
  a.deepStrictEqual(v.validateTransferEntry({ from_handle: 'a', to_handle: 'b', amount: 1e2 }).value, { from_handle: 'a', to_handle: 'b', amount: 100, note: '', visibility: 'public' });
  a.strictEqual(v.parseJsonBuffer(Buffer.from('')).value, undefined);
  a.strictEqual(v.parseJsonBuffer(Buffer.from('{bad')).error.code, 'malformed_request');
  a.strictEqual(v.parseJsonBuffer(Buffer.from([0x7b, 0xff, 0x7d])).error.status, 400);
  a.strictEqual(v.requireObject([]).error.status, 400);
  a.strictEqual(v.requireObject(null).error.status, 400);
  a.strictEqual(v.canonicalJson(JSON.parse('{"b":1e3,"a":[1,{"y":2,"x":1}]}')), v.canonicalJson(JSON.parse('{ "a":[1,{"x":1,"y":2}],"b":1000.0}')));
  a.notStrictEqual(v.canonicalJson({}), v.canonicalJson({ visibility: 'public' }));
});

test('number literals are kept only when exact', () => {
  for (const s of ['1000', '1000.0', '1e3', '1E3', '1500e-3', '10.00e2', '-0', '0.0', '1000000000', '1000000000000000000000e-12'])
    a.strictEqual(typeof P(`{"amount":${s}}`).amount, 'number', s);
  a.strictEqual(v.validateAmount(P('{"amount":1e3}').amount).value, 1000);
  a.strictEqual(v.validateAmount(P('{"amount":1500000e-3}').amount).value, 1500);
  for (const s of ['1000.0000000000001', '999.99999999999999', '1000000000.00000001', '1e-400', '1001e-3'])
    a.strictEqual(v.validateAmount(P(`{"amount":${s}}`).amount).error.status, 422, s);
  a.notStrictEqual(v.canonicalJson(P('{"amount":1000.0000000000001}')), v.canonicalJson(P('{"amount":1000}')));
  a.strictEqual(v.canonicalJson(P('{"amount":1000.0}')), v.canonicalJson(P('{"amount":1e3}')));
  a.strictEqual(v.requireObject(P('1.00000000000000001')).error.status, 400);
  a.strictEqual(v.validateNote(P('{"n":1.00000000000000001}').n).error.status, 422);
  a.strictEqual(P('{"a":[1,2.5,{"b":3}]}').a[2].b, 3);
  for (const s of ['9007199254740992', '-9007199254740992', '9007199254740991', '1152921504606846976', '-0.0e5', '0e99999', '-0', '1000000000000000000000e-12'])
    a.strictEqual(typeof P(`{"b":${s}}`).b, 'number', s);
  for (const s of ['9007199254740993', '-9007199254740993', '12345678901234567890', '9007199254740993.0', '90071992547409930e-1', '1e300'])
    a.ok(!(typeof P(`{"b":${s}}`).b === 'number'), s);
  a.strictEqual(P('{"b":9007199254740992}').b, 2 ** 53);
});

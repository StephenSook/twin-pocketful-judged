'use strict';

// Builds a complete replacement state from a reset fixture (§4) or from an
// export (§10). Both validate everything first and throw ApiError 422 on any
// problem, so an invalid input never changes the live state: the caller swaps
// the returned state in with one synchronous assignment.

const v = require('./validate');
const { ApiError, emptyState, rfc3339, MAX_ID, MAX_BALANCE } = require('./store');
const { isPasswordHash } = require('./passwords');

const STATUSES = new Set(['pending', 'paid', 'declined', 'cancelled']);
const VISIBILITIES = new Set(['public', 'private']);

function fail(message) {
  throw new ApiError(422, 'validation_failed', message);
}

const isObj = (x) => x !== null && typeof x === 'object' && !Array.isArray(x);
const isId = (x) => typeof x === 'string' && x.length >= 1 && x.length <= MAX_ID;
const isAmount = (x) => Number.isSafeInteger(x) && x >= 1;
// Zero split shares (§9) create zero-amount requests and, when paid, payments.
const isShare = (x) => Number.isSafeInteger(x) && x >= 0;
const isNote = (x) => typeof x === 'string';
const optArray = (x, name) => {
  if (x === undefined) return [];
  if (!Array.isArray(x)) fail(`${name} must be an array`);
  return x;
};

function timestampMs(x, fallback) {
  if (x === undefined || x === null) return fallback;
  if (typeof x !== 'string') fail('created_at must be a string');
  const ms = Date.parse(x);
  if (!Number.isFinite(ms)) fail('created_at must be an RFC 3339 timestamp');
  return ms;
}

// ---- reset fixture ------------------------------------------------------------

// Synchronous structural validation. Returns a plan; passwords are hashed by
// the caller (outside any critical section) and handed to buildFixtureState.
function planFixture(f) {
  if (!isObj(f)) fail('fixture must be an object');
  if (typeof f.currency !== 'string' || f.currency.length === 0) fail('currency is required');
  if (![0, 2, 3].includes(f.minor_units)) fail('minor_units must be 0, 2 or 3');
  if (!Array.isArray(f.users)) fail('users must be an array');

  const ids = new Set();
  const handles = new Set();
  const emails = new Set();
  const users = f.users.map((u) => {
    if (!isObj(u)) fail('user must be an object');
    if (!isId(u.id) || ids.has(u.id)) fail('user id must be a unique string of 1..64 characters');
    if (typeof u.email !== 'string' || !v.validateEmail(u.email).ok) fail('user email is invalid');
    const key = v.emailKey(u.email);
    if (emails.has(key)) fail('duplicate user email');
    if (!v.isValidHandle(u.handle) || handles.has(u.handle)) fail('user handle is invalid or duplicated');
    if (typeof u.password !== 'string') fail('user password must be a string');
    if (u.display_name !== undefined && typeof u.display_name !== 'string') fail('display_name must be a string');
    if (typeof u.balance !== 'number' || !Number.isInteger(u.balance)) fail('balance must be an integer');
    if (u.balance < 0) fail('balance must not be negative');
    if (u.balance > MAX_BALANCE) fail('balance out of range');
    ids.add(u.id);
    handles.add(u.handle);
    emails.add(key);
    return {
      id: u.id, email: u.email, email_key: key, display_name: u.display_name === undefined ? u.handle : u.display_name,
      handle: u.handle, balance: u.balance, password: u.password,
    };
  });

  const paymentIds = new Set();
  const payments = optArray(f.payments, 'payments').map((p) => {
    if (!isObj(p)) fail('payment must be an object');
    if (!isId(p.id) || paymentIds.has(p.id)) fail('payment id must be a unique string of 1..64 characters');
    if (!ids.has(p.from_user_id) || !ids.has(p.to_user_id)) fail('payment references an unknown user');
    if (!isShare(p.amount)) fail('payment amount must be a nonnegative integer');
    if (p.note !== undefined && !isNote(p.note)) fail('payment note must be a string');
    if (p.visibility !== undefined && !VISIBILITIES.has(p.visibility)) fail('payment visibility is invalid');
    paymentIds.add(p.id);
    return p;
  });

  const requestIds = new Set();
  const requests = optArray(f.requests, 'requests').map((r) => {
    if (!isObj(r)) fail('request must be an object');
    if (!isId(r.id) || requestIds.has(r.id)) fail('request id must be a unique string of 1..64 characters');
    if (!ids.has(r.requester_id) || !ids.has(r.payer_id)) fail('request references an unknown user');
    if (!isShare(r.amount)) fail('request amount must be a nonnegative integer');
    if (r.note !== undefined && !isNote(r.note)) fail('request note must be a string');
    if (r.status !== undefined && !STATUSES.has(r.status)) fail('request status is invalid');
    if (r.payment_id !== undefined && r.payment_id !== null && !paymentIds.has(r.payment_id)) fail('request payment_id is unknown');
    requestIds.add(r.id);
    return r;
  });

  const operators = optArray(f.settlement_operator_ids, 'settlement_operator_ids').map((id) => {
    if (!ids.has(id)) fail('settlement_operator_ids references an unknown user');
    return id;
  });

  return { currency: f.currency, minor_units: f.minor_units, users, payments, requests, operators };
}

// hashes[i] is the password hash for plan.users[i].
function buildFixtureState(plan, hashes) {
  const s = emptyState();
  const now = Date.now();
  s.currency = plan.currency;
  s.minor_units = plan.minor_units;
  plan.users.forEach((u, i) => {
    const user = {
      id: u.id, email: u.email, email_key: u.email_key, display_name: u.display_name,
      handle: u.handle, balance: u.balance, password_hash: hashes[i],
    };
    s.users.set(user.id, user);
    s.byHandle.set(user.handle, user);
    s.byEmail.set(user.email_key, user);
  });
  const requestByPayment = new Map();
  for (const r of plan.requests) if (typeof r.payment_id === 'string') requestByPayment.set(r.payment_id, r.id);

  const payments = plan.payments.map((p, seq) => {
    const ms = timestampMs(p.created_at, now);
    const from = s.users.get(p.from_user_id);
    const to = s.users.get(p.to_user_id);
    return {
      ms, seq,
      p: {
        payment_id: p.id,
        from_user_id: from.id, from_handle: from.handle,
        to_user_id: to.id, to_handle: to.handle,
        amount: p.amount, currency: s.currency,
        note: p.note === undefined ? '' : p.note,
        visibility: p.visibility === undefined ? 'public' : p.visibility,
        request_id: typeof p.request_id === 'string' ? p.request_id : requestByPayment.get(p.id) || null,
        settlement_id: typeof p.settlement_id === 'string' ? p.settlement_id : null,
        created_at: rfc3339(ms),
      },
    };
  });
  const requests = plan.requests.map((r, seq) => {
    const ms = timestampMs(r.created_at, now);
    const requester = s.users.get(r.requester_id);
    const payer = s.users.get(r.payer_id);
    return {
      ms, seq,
      r: {
        request_id: r.id,
        requester_id: requester.id, requester_handle: requester.handle,
        payer_id: payer.id, payer_handle: payer.handle,
        amount: r.amount, currency: s.currency,
        note: r.note === undefined ? '' : r.note,
        status: r.status === undefined ? 'pending' : r.status,
        payment_id: typeof r.payment_id === 'string' ? r.payment_id : null,
        created_at: rfc3339(ms),
      },
    };
  });
  const bySeq = (a, b) => a.ms - b.ms || a.seq - b.seq;
  for (const { ms, p } of payments.sort(bySeq)) {
    s.payments.push({ ms, p });
    s.paymentById.set(p.payment_id, p);
    if (p.settlement_id) s.settlements.add(p.settlement_id);
  }
  for (const { ms, r } of requests.sort(bySeq)) {
    s.requests.push({ ms, r });
    s.requestById.set(r.request_id, r);
  }
  for (const id of plan.operators) s.operators.add(id);
  s.lastMs = Math.max(now, ...payments.map((x) => x.ms), ...requests.map((x) => x.ms));
  return s;
}

// ---- import (§10) -------------------------------------------------------------------

const PAYMENT_KEYS = ['payment_id', 'from_user_id', 'from_handle', 'to_user_id', 'to_handle', 'amount',
  'currency', 'note', 'visibility', 'request_id', 'settlement_id', 'created_at'];
const REQUEST_KEYS = ['request_id', 'requester_id', 'requester_handle', 'payer_id', 'payer_handle', 'amount',
  'currency', 'note', 'status', 'payment_id', 'created_at'];

function isMs(x) {
  return Number.isSafeInteger(x) && x >= 0;
}

function buildImportedState(doc) {
  if (!isObj(doc)) fail('import must be an object');
  if (doc.track !== 'pocketful') fail('track must be "pocketful"');
  if (doc.format_version !== 1) fail('format_version must be 1');
  const st = doc.state;
  if (!isObj(st)) fail('state must be an object');
  if (typeof st.currency !== 'string' || st.currency.length === 0) fail('state.currency is invalid');
  if (![0, 2, 3].includes(st.minor_units)) fail('state.minor_units is invalid');
  for (const k of ['users', 'token_digests', 'payments', 'requests', 'split_ids', 'settlement_ids',
    'idempotency', 'settlement_operator_ids']) {
    if (!Array.isArray(st[k])) fail(`state.${k} must be an array`);
  }
  if (!isMs(st.last_ms)) fail('state.last_ms is invalid');

  const s = emptyState();
  s.currency = st.currency;
  s.minor_units = st.minor_units;
  s.lastMs = st.last_ms;

  for (const u of st.users) {
    if (!isObj(u) || !isId(u.id) || s.users.has(u.id)) fail('state user id is invalid');
    if (typeof u.email !== 'string' || !v.validateEmail(u.email).ok) fail('state user email is invalid');
    const key = v.emailKey(u.email);
    if (s.byEmail.has(key)) fail('state user email is duplicated');
    if (!v.isValidHandle(u.handle) || s.byHandle.has(u.handle)) fail('state user handle is invalid');
    if (typeof u.display_name !== 'string') fail('state user display_name is invalid');
    if (typeof u.balance !== 'number' || !Number.isInteger(u.balance) || u.balance < 0 || u.balance > MAX_BALANCE) fail('state user balance is invalid');
    if (!isPasswordHash(u.password_hash)) fail('state user password_hash is invalid');
    const user = {
      id: u.id, email: u.email, email_key: key, display_name: u.display_name,
      handle: u.handle, balance: u.balance, password_hash: u.password_hash,
    };
    s.users.set(user.id, user);
    s.byHandle.set(user.handle, user);
    s.byEmail.set(key, user);
  }
  for (const t of st.token_digests) {
    if (!isObj(t) || typeof t.digest !== 'string' || !/^[0-9a-f]{64}$/.test(t.digest)) fail('state token is invalid');
    if (!s.users.has(t.user_id) || s.tokens.has(t.digest)) fail('state token is invalid');
    s.tokens.set(t.digest, t.user_id);
  }

  const userMatches = (id, handle) => {
    const u = s.users.get(id);
    return u !== undefined && u.handle === handle;
  };
  let prevMs = 0;
  for (const item of st.payments) {
    if (!isObj(item) || !isMs(item.ms) || item.ms < prevMs || !isObj(item.payment)) fail('state payment is invalid');
    const p = item.payment;
    if (Object.keys(p).length !== PAYMENT_KEYS.length || !PAYMENT_KEYS.every((k) => k in p)) fail('state payment fields are invalid');
    if (!isId(p.payment_id) || s.paymentById.has(p.payment_id)) fail('state payment id is invalid');
    if (!userMatches(p.from_user_id, p.from_handle) || !userMatches(p.to_user_id, p.to_handle)) fail('state payment user is invalid');
    if (!isShare(p.amount) || p.currency !== s.currency || !isNote(p.note) || !VISIBILITIES.has(p.visibility)) fail('state payment is invalid');
    if (p.request_id !== null && !isId(p.request_id)) fail('state payment request_id is invalid');
    if (p.settlement_id !== null && !isId(p.settlement_id)) fail('state payment settlement_id is invalid');
    if (typeof p.created_at !== 'string' || !Number.isFinite(Date.parse(p.created_at))) fail('state payment created_at is invalid');
    prevMs = item.ms;
    const copy = {};
    for (const k of PAYMENT_KEYS) copy[k] = p[k];
    s.payments.push({ ms: item.ms, p: copy });
    s.paymentById.set(copy.payment_id, copy);
  }
  prevMs = 0;
  for (const item of st.requests) {
    if (!isObj(item) || !isMs(item.ms) || item.ms < prevMs || !isObj(item.request)) fail('state request is invalid');
    const r = item.request;
    if (Object.keys(r).length !== REQUEST_KEYS.length || !REQUEST_KEYS.every((k) => k in r)) fail('state request fields are invalid');
    if (!isId(r.request_id) || s.requestById.has(r.request_id)) fail('state request id is invalid');
    if (!userMatches(r.requester_id, r.requester_handle) || !userMatches(r.payer_id, r.payer_handle)) fail('state request user is invalid');
    if (!isShare(r.amount) || r.currency !== s.currency || !isNote(r.note) || !STATUSES.has(r.status)) fail('state request is invalid');
    if (r.payment_id !== null && !s.paymentById.has(r.payment_id)) fail('state request payment_id is invalid');
    if (typeof r.created_at !== 'string' || !Number.isFinite(Date.parse(r.created_at))) fail('state request created_at is invalid');
    prevMs = item.ms;
    const copy = {};
    for (const k of REQUEST_KEYS) copy[k] = r[k];
    s.requests.push({ ms: item.ms, r: copy });
    s.requestById.set(copy.request_id, copy);
  }
  for (const id of st.split_ids) {
    if (!isId(id)) fail('state split id is invalid');
    s.splits.add(id);
  }
  for (const id of st.settlement_ids) {
    if (!isId(id)) fail('state settlement id is invalid');
    s.settlements.add(id);
  }
  for (const e of st.idempotency) {
    if (!isObj(e) || typeof e.scope !== 'string' || typeof e.body !== 'string' || typeof e.response !== 'string') fail('state idempotency record is invalid');
    let scope;
    try {
      scope = JSON.parse(e.scope);
      JSON.parse(e.response);
    } catch {
      fail('state idempotency record is invalid');
    }
    if (!Array.isArray(scope) || scope.length !== 4 || !s.users.has(scope[0]) || s.idem.has(e.scope)) fail('state idempotency record is invalid');
    s.idem.set(e.scope, { body: e.body, response: e.response });
  }
  for (const id of st.settlement_operator_ids) {
    if (!s.users.has(id)) fail('state settlement operator is invalid');
    s.operators.add(id);
  }
  const lastOf = (arr) => (arr.length ? arr[arr.length - 1].ms : 0);
  s.lastMs = Math.max(s.lastMs, lastOf(s.payments), lastOf(s.requests));
  return s;
}

module.exports = { planFixture, buildFixtureState, buildImportedState };

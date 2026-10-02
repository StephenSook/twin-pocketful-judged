'use strict';

// Builds a complete replacement state from a reset fixture (§4) or from an
// export (§10). Both validate everything first and throw ApiError 422 on any
// problem, so an invalid input never changes the live state: the caller swaps
// the returned state in with one synchronous assignment.

const v = require('./validate');
const { ApiError, emptyState, rfc3339, MAX_ID, MAX_BALANCE, indexPayment, pushTo } = require('./store');
const ledger = require('./ledger');

const AUTH_STATUSES = new Set(['open', 'captured', 'voided', 'expired']);
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
    // stage 3: a seeded created_at in the future is a reset error
    if (p.created_at !== undefined && p.created_at !== null && timestampMs(p.created_at, 0) > Date.now()) fail('payment created_at is in the future');
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

  // stage 2: authorization_ttl_seconds (default 600) and seeded authorizations
  let ttl = 600;
  if (f.authorization_ttl_seconds !== undefined) {
    if (!Number.isSafeInteger(f.authorization_ttl_seconds) || f.authorization_ttl_seconds < 1) {
      fail('authorization_ttl_seconds must be a positive integer');
    }
    ttl = f.authorization_ttl_seconds;
  }
  const authIds = new Set();
  const now = Date.now();
  const heldBy = new Map();
  const authorizations = optArray(f.authorizations, 'authorizations').map((a) => {
    if (!isObj(a)) fail('authorization must be an object');
    if (!isId(a.id) || authIds.has(a.id)) fail('authorization id must be a unique string of 1..64 characters');
    if (!ids.has(a.from_user_id) || !ids.has(a.to_user_id) || a.from_user_id === a.to_user_id) fail('authorization references invalid users');
    if (!isAmount(a.amount) || a.amount > 1000000000) fail('authorization amount is invalid');
    if (a.note !== undefined && !isNote(a.note)) fail('authorization note must be a string');
    if (a.visibility !== undefined && !VISIBILITIES.has(a.visibility)) fail('authorization visibility is invalid');
    const status = a.status === undefined ? 'open' : a.status;
    if (!AUTH_STATUSES.has(status)) fail('authorization status is invalid');
    // Ruling S2-3: a seeded captured authorization without captured_amount captured its full amount.
    const captured = a.captured_amount === undefined ? (status === 'captured' ? a.amount : 0) : a.captured_amount;
    if (!Number.isSafeInteger(captured) || captured < 0 || captured > a.amount) fail('authorization captured_amount is invalid');
    if (status === 'open' && captured === a.amount) fail('an open authorization must have a remaining amount');
    if (typeof a.expires_at !== 'string' || !Number.isFinite(Date.parse(a.expires_at))) fail('authorization expires_at is required');
    if (a.payment_id !== undefined && a.payment_id !== null && !paymentIds.has(a.payment_id)) fail('authorization payment_id is unknown');
    if (a.payment_ids !== undefined && (!Array.isArray(a.payment_ids) || !a.payment_ids.every((x) => paymentIds.has(x)))) fail('authorization payment_ids is invalid');
    const expMs = Date.parse(a.expires_at);
    if (status === 'open' && expMs > now) {
      heldBy.set(a.from_user_id, (heldBy.get(a.from_user_id) || 0) + (a.amount - captured));
    }
    authIds.add(a.id);
    return { ...a, status, captured, expMs };
  });
  // Seeded unexpired open holds may not exceed the payer's seeded balance (total).
  for (const u of users) {
    if ((heldBy.get(u.id) || 0) > u.balance) fail('seeded open holds exceed the user balance');
  }

  return { currency: f.currency, minor_units: f.minor_units, users, payments, requests, operators, ttl, authorizations };
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
        authorization_id: typeof p.authorization_id === 'string' ? p.authorization_id : null,
        refund_of: typeof p.refund_of === 'string' ? p.refund_of : null,
        created_at: typeof p.created_at === 'string' ? p.created_at : rfc3339(ms), // seeded values kept as given (S3-5)
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
        created_at: typeof r.created_at === 'string' ? r.created_at : rfc3339(ms),
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
  s.authorizationTtlSeconds = plan.ttl;
  const auths = plan.authorizations.map((x, seq) => {
    const ms = timestampMs(x.created_at, now);
    const from = s.users.get(x.from_user_id);
    const to = s.users.get(x.to_user_id);
    const paymentIdsList = Array.isArray(x.payment_ids) ? x.payment_ids.slice()
      : typeof x.payment_id === 'string' ? [x.payment_id] : [];
    const open = x.status === 'open' && x.expMs > now;
    return {
      ms, seq,
      a: {
        authorization_id: x.id,
        from_user_id: from.id, from_handle: from.handle,
        to_user_id: to.id, to_handle: to.handle,
        amount: x.amount,
        captured_amount: x.captured,
        remaining_amount: open ? x.amount - x.captured : 0,
        currency: s.currency,
        note: x.note === undefined ? '' : x.note,
        visibility: x.visibility === undefined ? 'public' : x.visibility,
        status: x.status === 'open' && !open ? 'expired' : x.status,
        expires_at: x.expires_at,
        payment_id: typeof x.payment_id === 'string' ? x.payment_id : paymentIdsList.length ? paymentIdsList[paymentIdsList.length - 1] : null,
        payment_ids: paymentIdsList,
        created_at: typeof x.created_at === 'string' ? x.created_at : rfc3339(ms),
      },
    };
  });
  for (const { ms, a } of auths.sort((p, q) => p.ms - q.ms || p.seq - q.seq)) {
    s.authorizations.push({ ms, a });
    s.authorizationById.set(a.authorization_id, a);
    if (a.status === 'open') s.openAuthorizations.add(a);
  }
  let lastMs = now;
  for (const list of [payments, requests, auths]) for (const x of list) if (x.ms > lastMs) lastMs = x.ms;
  s.lastMs = lastMs;
  // Holds seeded as open have a lifecycle (created, then expiry at expires_at)
  // even when already expired at reset time; seeded closed holds do not.
  deriveHistory(s, { seeded: true, seededOpen: new Set(plan.authorizations.filter((x) => x.status === 'open').map((x) => x.id)) });
  validateHistory(s);
  return s;
}

// ---- import (§10) -------------------------------------------------------------------

const PAYMENT_KEYS = ['payment_id', 'from_user_id', 'from_handle', 'to_user_id', 'to_handle', 'amount',
  'currency', 'note', 'visibility', 'request_id', 'settlement_id', 'authorization_id', 'refund_of', 'created_at'];
// Earlier exports lack the later fields (accepted and filled with null):
// stage 1 has neither authorization_id nor refund_of, stages 2-3 lack refund_of.
const STAGE3_PAYMENT_KEYS = PAYMENT_KEYS.filter((k) => k !== 'refund_of');
const STAGE1_PAYMENT_KEYS = STAGE3_PAYMENT_KEYS.filter((k) => k !== 'authorization_id');
const AUTH_KEYS = ['authorization_id', 'from_user_id', 'from_handle', 'to_user_id', 'to_handle', 'amount',
  'captured_amount', 'remaining_amount', 'currency', 'note', 'visibility', 'status', 'expires_at', 'payment_id',
  'payment_ids', 'created_at'];
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
    const keys = 'refund_of' in p ? PAYMENT_KEYS : 'authorization_id' in p ? STAGE3_PAYMENT_KEYS : STAGE1_PAYMENT_KEYS;
    if (Object.keys(p).length !== keys.length || !keys.every((k) => k in p)) fail('state payment fields are invalid');
    if (p.authorization_id === undefined) p.authorization_id = null;
    if (p.authorization_id !== null && !isId(p.authorization_id)) fail('state payment authorization_id is invalid');
    if (p.refund_of === undefined) p.refund_of = null;
    if (p.refund_of !== null && !isId(p.refund_of)) fail('state payment refund_of is invalid');
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
  // stage 2 additions; a stage-1 export has none of them.
  if (st.authorization_ttl_seconds !== undefined) {
    if (!Number.isSafeInteger(st.authorization_ttl_seconds) || st.authorization_ttl_seconds < 1) fail('state.authorization_ttl_seconds is invalid');
    s.authorizationTtlSeconds = st.authorization_ttl_seconds;
  }
  const authList = st.authorizations === undefined ? [] : st.authorizations;
  if (!Array.isArray(authList)) fail('state.authorizations must be an array');
  prevMs = 0;
  const heldBy = new Map();
  for (const item of authList) {
    if (!isObj(item) || !isMs(item.ms) || item.ms < prevMs || !isObj(item.authorization)) fail('state authorization is invalid');
    const a = item.authorization;
    const authKeys = 'closed_at' in a ? [...AUTH_KEYS, 'closed_at'] : AUTH_KEYS;
    if (Object.keys(a).length !== authKeys.length || !authKeys.every((k) => k in a)) fail('state authorization fields are invalid');
    if ('closed_at' in a && a.closed_at !== null && (typeof a.closed_at !== 'string' || !Number.isFinite(Date.parse(a.closed_at)))) fail('state authorization closed_at is invalid');
    if (!isId(a.authorization_id) || s.authorizationById.has(a.authorization_id)) fail('state authorization id is invalid');
    if (!userMatches(a.from_user_id, a.from_handle) || !userMatches(a.to_user_id, a.to_handle) || a.from_user_id === a.to_user_id) fail('state authorization user is invalid');
    if (!isAmount(a.amount) || a.currency !== s.currency || !isNote(a.note) || !VISIBILITIES.has(a.visibility) || !AUTH_STATUSES.has(a.status)) fail('state authorization is invalid');
    if (!Number.isSafeInteger(a.captured_amount) || !Number.isSafeInteger(a.remaining_amount) || a.captured_amount < 0 || a.remaining_amount < 0
      || a.captured_amount + a.remaining_amount > a.amount) fail('state authorization amounts are invalid');
    if ((a.status === 'open') !== (a.remaining_amount > 0)) fail('state authorization remaining_amount is invalid');
    if (!Array.isArray(a.payment_ids) || !a.payment_ids.every((x) => s.paymentById.has(x))) fail('state authorization payment_ids is invalid');
    if (a.payment_id !== (a.payment_ids.length ? a.payment_ids[a.payment_ids.length - 1] : null)) fail('state authorization payment_id is invalid');
    for (const k of ['expires_at', 'created_at']) {
      if (typeof a[k] !== 'string' || !Number.isFinite(Date.parse(a[k]))) fail(`state authorization ${k} is invalid`);
    }
    prevMs = item.ms;
    const copy = {};
    for (const k of AUTH_KEYS) copy[k] = k === 'payment_ids' ? a[k].slice() : a[k];
    if ('closed_at' in a) copy.closed_at = a.closed_at;
    s.authorizations.push({ ms: item.ms, a: copy });
    s.authorizationById.set(copy.authorization_id, copy);
    if (copy.status === 'open') {
      s.openAuthorizations.add(copy);
      heldBy.set(copy.from_user_id, (heldBy.get(copy.from_user_id) || 0) + copy.remaining_amount);
    }
  }
  for (const [id, h] of heldBy) if (h > s.users.get(id).balance) fail('state holds exceed a balance');
  const lastOf = (arr) => (arr.length ? arr[arr.length - 1].ms : 0);
  s.lastMs = Math.max(s.lastMs, lastOf(s.payments), lastOf(s.requests), lastOf(s.authorizations));
  deriveHistory(s, importHistory(st, s));
  validateHistory(s);
  return s;
}

// The history must be consistent (§10 invalid state is 422; stage 3 "seeded
// history is consistent and nonnegative"): each opening is nonnegative, opening
// plus the net of current revisions equals the balance, and total, held and
// available never go negative at any boundary. Applied to reset fixtures too,
// so every state the service accepts re-imports from its own export.
function validateHistory(s) {
  const now = Date.now();
  for (const u of s.users.values()) {
    if (u.opening < 0) fail('state opening balance is negative');
    let net = 0n;
    for (const p of s.paymentsByUser.get(u.id) || []) {
      const revs = s.revisions.get(p.payment_id);
      const amount = BigInt(revs[revs.length - 1].amount);
      net += p.from_user_id === u.id ? -amount : amount;
    }
    if (BigInt(u.opening) + net !== BigInt(u.balance)) fail('state opening and payments do not match the balance');
    if (!ledger.historyIsSound(s, u, null, now)) fail('state history has a negative balance');
  }
  // stage 4: every refund names an existing non-refund payment, runs in the
  // opposite direction, carries no request/authorization/settlement link, and
  // refunds of one payment never exceed its current amount.
  for (const { p } of s.payments) {
    if (p.refund_of === null) continue;
    const target = s.paymentById.get(p.refund_of);
    if (!target || target.refund_of !== null || p.from_user_id !== target.to_user_id || p.to_user_id !== target.from_user_id
      || p.request_id !== null || p.authorization_id !== null || p.settlement_id !== null || p.amount < 1) fail('state refund is invalid');
    if (s.revisions.get(p.payment_id).length !== 1) fail('state refund has corrections');
  }
  for (const [targetId, total] of s.refundedTotal) {
    const revs = s.revisions.get(targetId);
    if (!revs || total > revs[revs.length - 1].amount) fail('state refunds exceed the payment');
  }
}

// ---- stage-3 history ---------------------------------------------------------------

// Revisions, per-user indexes, opening balances and hold event logs.
// extras: { seeded, revisions: Map, openings: Map, authEvents: Map } (all optional).
function deriveHistory(s, extras) {
  const revisions = extras.revisions || new Map();
  for (const revs of revisions.values()) for (const r of revs) if (r.seq > s.revSeq) s.revSeq = r.seq;
  for (const { p } of s.payments) indexPayment(s, p, revisions.get(p.payment_id));
  const openings = extras.openings || new Map();
  for (const u of s.users.values()) {
    if (openings.has(u.id)) {
      u.opening = openings.get(u.id);
      continue;
    }
    // Opening = ending balance minus the net effect of the payments (current revisions).
    let net = 0n;
    for (const p of s.paymentsByUser.get(u.id) || []) {
      const revs = s.revisions.get(p.payment_id);
      const amount = BigInt(revs[revs.length - 1].amount);
      net += p.from_user_id === u.id ? -amount : amount;
    }
    u.opening = Number(BigInt(u.balance) - net);
  }
  const events = extras.authEvents || new Map();
  for (const { a } of s.authorizations) {
    pushTo(s.authorizationsByPayer, a.from_user_id, a);
    const captures = a.payment_ids.map((id) => s.paymentById.get(id)).filter(Boolean)
      .map((p) => ({ ms: Date.parse(p.created_at), amount: p.amount }));
    const lastCapture = captures.length ? captures[captures.length - 1].ms : null;
    const createdMs = Date.parse(a.created_at);
    const expMs = Date.parse(a.expires_at);
    if (!('closed_at' in a)) {
      a.closed_at = a.status === 'open' ? null
        : a.status === 'expired' ? a.expires_at
          : a.status === 'captured' && lastCapture !== null ? ledger.stamp(lastCapture) : a.created_at;
    }
    if (events.has(a.authorization_id)) {
      s.authEvents.set(a.authorization_id, events.get(a.authorization_id));
      continue;
    }
    // Seeded closed holds have no lifecycle (stage 3); seeded open ones do.
    // An open seed already past its deadline when created (created_at omitted =
    // reset time) never held anything observable either.
    // The same holds for any hold whose deadline is not after its creation,
    // e.g. a stage-2 export of such a seed (no lifecycle can be reconstructed).
    const noHistory = expMs <= createdMs || (extras.seeded === true && !extras.seededOpen.has(a.authorization_id));
    const capturedKnown = captures.reduce((n, c) => n + c.amount, 0);
    s.authEvents.set(a.authorization_id, {
      createdMs,
      initialHold: a.amount - a.captured_amount + capturedKnown,
      expMs,
      captures,
      closedMs: a.status === 'open' ? null : a.status === 'expired' ? expMs : Date.parse(a.closed_at),
      closedKind: a.status === 'open' ? null : a.status,
      noHistory,
    });
  }
}

// History carried by a stage-3 export; absent in stage-1/2 exports.
function importHistory(st, s) {
  const extras = { seeded: false };
  if (st.revisions !== undefined) {
    if (!Array.isArray(st.revisions)) fail('state.revisions must be an array');
    extras.revisions = new Map();
    for (const item of st.revisions) {
      if (!isObj(item) || !s.paymentById.has(item.payment_id) || !Array.isArray(item.revisions) || item.revisions.length < 1) fail('state revision is invalid');
      const p = s.paymentById.get(item.payment_id);
      let prev = null;
      const revs = item.revisions.map((r, i) => {
        if (!isObj(r) || r.revision !== i + 1 || !isShare(r.amount) || r.amount > 1000000000 && i > 0 || typeof r.reason !== 'string') fail('state revision is invalid');
        for (const k of ['effective_at', 'recorded_at']) if (typeof r[k] !== 'string' || !Number.isFinite(Date.parse(r[k]))) fail('state revision time is invalid');
        if (!Number.isSafeInteger(r.seq) || r.seq < 1) fail('state revision seq is invalid');
        if (!(r.correction_batch_id === undefined || r.correction_batch_id === null || (isId(r.correction_batch_id) && i > 0))) fail('state revision correction_batch_id is invalid');
        const rev = { revision: r.revision, amount: r.amount, effMs: Date.parse(r.effective_at), recMs: Date.parse(r.recorded_at), effective_at: r.effective_at, recorded_at: r.recorded_at, reason: r.reason, seq: r.seq, correction_batch_id: r.correction_batch_id === undefined ? null : r.correction_batch_id };
        if (prev && rev.recMs <= prev.recMs) fail('state revision recorded times must increase');
        prev = rev;
        return rev;
      });
      if (revs[0].amount !== p.amount || revs[0].effective_at !== p.created_at || revs[0].recorded_at !== p.created_at || revs[0].reason !== '') {
        fail('state revision 1 must match the payment');
      }
      extras.revisions.set(item.payment_id, revs);
      for (const r of revs) if (r.correction_batch_id) s.correctionBatches.add(r.correction_batch_id);
    }
  }
  if (st.openings !== undefined) {
    if (!Array.isArray(st.openings)) fail('state.openings must be an array');
    extras.openings = new Map();
    for (const o of st.openings) {
      if (!isObj(o) || !s.users.has(o.user_id) || !Number.isInteger(o.opening) || Math.abs(o.opening) > MAX_BALANCE) fail('state opening is invalid');
      extras.openings.set(o.user_id, o.opening);
    }
  }
  if (st.auth_events !== undefined) {
    if (!Array.isArray(st.auth_events)) fail('state.auth_events must be an array');
    extras.authEvents = new Map();
    for (const e of st.auth_events) {
      const okNum = (x) => Number.isSafeInteger(x);
      if (!isObj(e) || !s.authorizationById.has(e.authorization_id) || !okNum(e.createdMs) || !okNum(e.initialHold) || !okNum(e.expMs)
        || !Array.isArray(e.captures) || !e.captures.every((c) => isObj(c) && okNum(c.ms) && okNum(c.amount))
        || !(e.closedMs === null || okNum(e.closedMs)) || typeof e.noHistory !== 'boolean') fail('state authorization history is invalid');
      // Event logs must describe a possible hold: nonnegative, captures within
      // the hold and matching the authorization's capture payments, closure
      // consistent with the status.
      const a = s.authorizationById.get(e.authorization_id);
      const kinds = [null, 'captured', 'voided', 'expired'];
      const capturePayments = a.payment_ids.map((id) => s.paymentById.get(id));
      let prevMs = e.createdMs;
      let capturedSum = 0;
      for (const c of e.captures) {
        if (c.amount < 1 || c.ms < prevMs) fail('state authorization history is invalid');
        prevMs = c.ms;
        capturedSum += c.amount;
      }
      // Seeded holds without a lifecycle (noHistory) contribute nothing to history,
      // so only their shape is checked.
      // noHistory is only possible for a closed hold or one whose deadline is not
      // after its creation; a lifecycle must agree with the authorization record.
      const createdMs = Date.parse(a.created_at);
      const expMs = Date.parse(a.expires_at);
      if (e.noHistory && a.status === 'open' && expMs > createdMs) fail('state authorization history is invalid');
      const timeline = !e.noHistory && (e.createdMs !== createdMs || e.expMs !== expMs
        || a.amount - e.initialHold !== a.captured_amount - capturedSum
        || (a.status === 'open' && a.remaining_amount !== e.initialHold - capturedSum)
        || e.expMs < e.createdMs || (e.closedMs !== null && e.closedMs < e.createdMs)
        || (a.status === 'open' ? e.closedKind !== null : e.closedKind !== a.status)
        || e.captures.length !== capturePayments.length
        || e.captures.some((c, i) => capturePayments[i].amount !== c.amount || Date.parse(capturePayments[i].created_at) !== c.ms));
      if (e.initialHold < 0 || e.initialHold > a.amount || capturedSum > e.initialHold
        || !kinds.includes(e.closedKind) || (e.closedMs === null) !== (e.closedKind === null) || timeline) {
        fail('state authorization history is invalid');
      }
      extras.authEvents.set(e.authorization_id, {
        createdMs: e.createdMs, initialHold: e.initialHold, expMs: e.expMs,
        captures: e.captures.map((c) => ({ ms: c.ms, amount: c.amount })),
        closedMs: e.closedMs, closedKind: e.closedKind === undefined ? null : e.closedKind, noHistory: e.noHistory,
      });
    }
  }
  return extras;
}

module.exports = { planFixture, buildFixtureState, buildImportedState };

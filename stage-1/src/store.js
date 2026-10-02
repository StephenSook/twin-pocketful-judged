'use strict';

// In-memory product state. Every state change happens synchronously inside one
// method of Store, so on Node's single thread each operation is atomic and
// concurrent requests behave as if they had run one at a time. Money moves only
// through commitTransfers(), which is the single place that enforces:
//   - balances never go negative (checked for the whole batch before any write),
//   - the sum of balances is unchanged (every debit has its credit),
//   - balances stay within the safe-integer range.
// Request status changes only through transitionRequest(), which allows
// pending -> paid|declined|cancelled exactly once, so a request moves money at
// most once.

const crypto = require('node:crypto');

// §4: no balance outside ±2^53; 2^53 itself is in range (coordinator ruling,
// ledger R1-041). Every integer up to 2^53 is exact as a double; balance
// arithmetic is done in BigInt so the bound check itself never rounds.
const MAX_BALANCE = 2 ** 53;
const MAX_BALANCE_BIG = 2n ** 53n;
const MAX_ID = 64;

class ApiError extends Error {
  constructor(status, code, message) {
    super(message);
    this.status = status;
    this.code = code;
  }
}

const notFound = () => new ApiError(404, 'not_found', 'not found');

function rfc3339(ms) {
  return new Date(ms).toISOString().replace(/\.\d{3}Z$/, '+00:00');
}

function tokenDigest(token) {
  return crypto.createHash('sha256').update(token, 'utf8').digest('hex');
}

function emptyState() {
  return {
    currency: 'EUR',
    minor_units: 2,
    users: new Map(), // id -> {id, email, email_key, display_name, handle, balance, password_hash}
    byHandle: new Map(), // handle -> user
    byEmail: new Map(), // email_key -> user
    tokens: new Map(), // sha256(token) -> user id
    payments: [], // {ms, p} oldest first; p is the public payment object (immutable)
    paymentById: new Map(),
    requests: [], // {ms, r} oldest first; r is the public request object
    requestById: new Map(),
    splits: new Set(), // split ids (for id uniqueness)
    settlements: new Set(), // settlement ids
    idem: new Map(), // scope -> {body, response} for completed 2xx idempotent writes
    operators: new Set(),
    lastMs: 0,
  };
}

class Store {
  constructor() {
    this.s = emptyState();
  }

  // ---- clock and ids -------------------------------------------------------

  tick() {
    const ms = Math.max(Date.now(), this.s.lastMs);
    this.s.lastMs = ms;
    return ms;
  }

  newId(prefix, taken) {
    for (;;) {
      const id = `${prefix}_${crypto.randomBytes(12).toString('base64url')}`;
      if (!taken(id)) return id;
    }
  }

  // ---- users and tokens ------------------------------------------------------

  get currency() {
    return this.s.currency;
  }

  userByHandle(handle) {
    return this.s.byHandle.get(handle);
  }

  userByEmail(emailKey) {
    return this.s.byEmail.get(emailKey);
  }

  userById(id) {
    return this.s.users.get(id);
  }

  isOperator(userId) {
    return this.s.operators.has(userId);
  }

  me(user) {
    return {
      user_id: user.id,
      display_name: user.display_name,
      handle: user.handle,
      balance: user.balance,
      currency: this.s.currency,
      minor_units: this.s.minor_units,
    };
  }

  authenticate(token) {
    const id = this.s.tokens.get(tokenDigest(token));
    return id === undefined ? null : this.s.users.get(id) || null;
  }

  issueToken(user) {
    const token = crypto.randomBytes(32).toString('base64url');
    this.s.tokens.set(tokenDigest(token), user.id);
    return token;
  }

  // Signup commit, called after the password hash was computed outside.
  // Re-checks uniqueness because other signups may have committed meanwhile.
  createUser({ email, emailKey, displayName, handle, passwordHash }) {
    if (this.s.byEmail.has(emailKey)) throw new ApiError(409, 'email_taken', 'email already registered');
    if (this.s.byHandle.has(handle)) throw new ApiError(409, 'handle_taken', 'handle already taken');
    const id = this.newId('u', (x) => this.s.users.has(x));
    const user = { id, email, email_key: emailKey, display_name: displayName, handle, balance: 0, password_hash: passwordHash };
    this.s.users.set(id, user);
    this.s.byHandle.set(handle, user);
    this.s.byEmail.set(emailKey, user);
    const token = this.issueToken(user);
    return { user_id: id, display_name: displayName, token };
  }

  // ---- idempotency -------------------------------------------------------------

  // Runs fn() for a first use of (user, method, path, key) and records a 2xx
  // result; a replay with the same canonical body returns the stored response
  // with status 200; a different body is 409. 4xx results are not recorded,
  // so the key stays reusable. Everything is synchronous: no interleaving.
  idempotent(userId, method, path, key, canonicalBody, fn) {
    const scope = JSON.stringify([userId, method, path, key]);
    const prior = this.s.idem.get(scope);
    if (prior) {
      if (prior.body !== canonicalBody) {
        throw new ApiError(409, 'idempotency_key_reuse', 'Idempotency-Key already used with a different request body');
      }
      return { status: 200, text: prior.response };
    }
    const result = fn();
    const text = JSON.stringify(result);
    this.s.idem.set(scope, { body: canonicalBody, response: text });
    return { status: 201, text };
  }

  // ---- money: the single state-change point ---------------------------------

  // entries: [{from, to, amount, note, visibility}] with user objects.
  // All-or-nothing: validates the resulting balance of every touched wallet,
  // then creates all payments and applies all balance changes.
  commitTransfers(entries, { requestId = null, settlementId = null } = {}) {
    const delta = new Map();
    for (const e of entries) {
      // amount 0 is legal only for paying a zero split share (§9); callers
      // validate amounts of new payments as 1..1000000000 before reaching here.
      if (!Number.isSafeInteger(e.amount) || e.amount < 0 || e.from === e.to) {
        throw new ApiError(422, 'validation_failed', 'invalid transfer');
      }
      const amount = BigInt(e.amount);
      delta.set(e.from, (delta.get(e.from) || 0n) - amount);
      delta.set(e.to, (delta.get(e.to) || 0n) + amount);
    }
    const nextBalance = new Map();
    for (const [user, d] of delta) {
      const next = BigInt(user.balance) + d;
      if (next < 0n) throw new ApiError(409, 'insufficient_funds', 'insufficient funds');
      if (next > MAX_BALANCE_BIG) throw new ApiError(422, 'validation_failed', 'resulting balance out of range');
      nextBalance.set(user, Number(next));
    }
    const ms = this.tick();
    const createdAt = rfc3339(ms);
    const created = entries.map((e) => {
      const p = {
        payment_id: this.newId('p', (x) => this.s.paymentById.has(x)),
        from_user_id: e.from.id,
        from_handle: e.from.handle,
        to_user_id: e.to.id,
        to_handle: e.to.handle,
        amount: e.amount,
        currency: this.s.currency,
        note: e.note,
        visibility: e.visibility,
        request_id: requestId,
        settlement_id: settlementId,
        created_at: createdAt,
      };
      this.s.payments.push({ ms, p });
      this.s.paymentById.set(p.payment_id, p);
      return p;
    });
    for (const [user, next] of nextBalance) user.balance = next;
    return { payments: created, ms, createdAt };
  }

  transitionRequest(r, status, paymentId = null) {
    if (r.status !== 'pending') throw new ApiError(409, 'request_not_pending', 'request is not pending');
    r.status = status;
    if (paymentId !== null) r.payment_id = paymentId;
  }

  // ---- payments --------------------------------------------------------------

  sendPayment(caller, { to_handle, amount, note, visibility }) {
    if (to_handle === caller.handle) throw new ApiError(422, 'self_payment', 'cannot pay yourself');
    const to = this.s.byHandle.get(to_handle);
    if (!to) throw notFound();
    const { payments } = this.commitTransfers([{ from: caller, to, amount, note, visibility }]);
    return { ...payments[0] };
  }

  // ---- requests ----------------------------------------------------------------

  createRequestRecord(requester, payer, amount, note, ms) {
    const r = {
      request_id: this.newId('rq', (x) => this.s.requestById.has(x)),
      requester_id: requester.id,
      requester_handle: requester.handle,
      payer_id: payer.id,
      payer_handle: payer.handle,
      amount,
      currency: this.s.currency,
      note,
      status: 'pending',
      payment_id: null,
      created_at: rfc3339(ms),
    };
    this.s.requests.push({ ms, r });
    this.s.requestById.set(r.request_id, r);
    return r;
  }

  createRequest(caller, { payer_handle, amount, note }) {
    if (payer_handle === caller.handle) throw new ApiError(422, 'self_request', 'cannot request from yourself');
    const payer = this.s.byHandle.get(payer_handle);
    if (!payer) throw notFound();
    return { ...this.createRequestRecord(caller, payer, amount, note, this.tick()) };
  }

  // Request actions: 404 only for an unknown id; the endpoint rules of §8 then
  // give 403 to anyone who is not the payer (pay, decline) or the requester
  // (cancel), third parties included (coordinator ruling). Listings still
  // show a request only to its two parties.
  existingRequest(id) {
    const r = this.s.requestById.get(id);
    if (!r) throw notFound();
    return r;
  }

  payRequest(caller, id, visibility) {
    const r = this.existingRequest(id);
    if (r.payer_id !== caller.id) throw new ApiError(403, 'forbidden', 'only the payer may pay this request');
    if (r.status !== 'pending') throw new ApiError(409, 'request_not_pending', 'request is not pending');
    const requester = this.s.users.get(r.requester_id);
    const { payments } = this.commitTransfers(
      [{ from: caller, to: requester, amount: r.amount, note: r.note, visibility }],
      { requestId: r.request_id },
    );
    this.transitionRequest(r, 'paid', payments[0].payment_id);
    return { ...payments[0] };
  }

  declineRequest(caller, id) {
    const r = this.existingRequest(id);
    if (r.payer_id !== caller.id) throw new ApiError(403, 'forbidden', 'only the payer may decline this request');
    if (r.status !== 'declined') this.transitionRequest(r, 'declined');
    return { ...r };
  }

  cancelRequest(caller, id) {
    const r = this.existingRequest(id);
    if (r.requester_id !== caller.id) throw new ApiError(403, 'forbidden', 'only the requester may cancel this request');
    if (r.status !== 'cancelled') this.transitionRequest(r, 'cancelled');
    return { ...r };
  }

  listRequests(caller, { direction, status, limit, offset }) {
    const out = [];
    let skipped = 0;
    let hasMore = false;
    for (let i = this.s.requests.length - 1; i >= 0; i--) {
      const { r } = this.s.requests[i];
      const incoming = r.payer_id === caller.id;
      const outgoing = r.requester_id === caller.id;
      if (direction === 'incoming' ? !incoming : direction === 'outgoing' ? !outgoing : !(incoming || outgoing)) continue;
      if (status !== null && r.status !== status) continue;
      if (skipped < offset) { skipped++; continue; }
      if (out.length === limit) { hasMore = true; break; }
      out.push({ ...r });
    }
    return { requests: out, has_more: hasMore };
  }

  // ---- splits ------------------------------------------------------------------

  createSplit(caller, { amount, handles, shares, note }) {
    const users = handles.map((h) => this.s.byHandle.get(h));
    if (users.some((u) => !u)) throw notFound();
    const ms = this.tick();
    const requests = [];
    users.forEach((u, i) => {
      if (u.id !== caller.id) requests.push({ ...this.createRequestRecord(caller, u, shares[i], note, ms) });
    });
    const splitId = this.newId('sp', (x) => this.s.splits.has(x));
    this.s.splits.add(splitId);
    return {
      split_id: splitId,
      amount,
      currency: this.s.currency,
      note,
      shares: handles.map((h, i) => ({ handle: h, amount: shares[i] })),
      requests,
      created_at: rfc3339(ms),
    };
  }

  // ---- activity ------------------------------------------------------------------

  listActivity(caller, { limit, offset }) {
    const out = [];
    let skipped = 0;
    let hasMore = false;
    for (let i = this.s.payments.length - 1; i >= 0; i--) {
      const { p } = this.s.payments[i];
      if (p.visibility !== 'public' && p.from_user_id !== caller.id && p.to_user_id !== caller.id) continue;
      if (skipped < offset) { skipped++; continue; }
      if (out.length === limit) { hasMore = true; break; }
      out.push({ ...p });
    }
    return { payments: out, has_more: hasMore };
  }

  // ---- settlements ---------------------------------------------------------------

  // entries: validated field values with handles; resolved here in input order.
  settle(entries) {
    const resolved = entries.map((e) => {
      const from = this.s.byHandle.get(e.from_handle);
      const to = this.s.byHandle.get(e.to_handle);
      if (!from || !to) throw notFound();
      if (from === to) throw new ApiError(422, 'self_payment', 'a transfer cannot move money to the same wallet');
      return { from, to, amount: e.amount, note: e.note, visibility: e.visibility };
    });
    const settlementId = this.newId('st', (x) => this.s.settlements.has(x));
    const { payments, createdAt } = this.commitTransfers(resolved, { settlementId });
    this.s.settlements.add(settlementId);
    return { settlement_id: settlementId, committed_at: createdAt, payments: payments.map((p) => ({ ...p })) };
  }

  // ---- reset / export / import -----------------------------------------------------

  replace(state) {
    this.s = state;
  }

  exportSnapshot() {
    const s = this.s;
    return {
      track: 'pocketful',
      format_version: 1,
      state: {
        currency: s.currency,
        minor_units: s.minor_units,
        users: [...s.users.values()].map((u) => ({
          id: u.id, email: u.email, display_name: u.display_name, handle: u.handle,
          balance: u.balance, password_hash: u.password_hash,
        })),
        token_digests: [...s.tokens].map(([digest, userId]) => ({ digest, user_id: userId })),
        payments: s.payments.map(({ ms, p }) => ({ ms, payment: p })),
        requests: s.requests.map(({ ms, r }) => ({ ms, request: r })),
        split_ids: [...s.splits],
        settlement_ids: [...s.settlements],
        idempotency: [...s.idem].map(([scope, v]) => ({ scope, body: v.body, response: v.response })),
        settlement_operator_ids: [...s.operators],
        last_ms: s.lastMs,
      },
    };
  }
}

module.exports = { Store, ApiError, emptyState, rfc3339, tokenDigest, MAX_ID, MAX_BALANCE };

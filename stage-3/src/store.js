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
const ledger = require('./ledger');

const INF = Number.POSITIVE_INFINITY;

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
    // stage 2: authorizations (holds)
    authorizationTtlSeconds: 600,
    authorizations: [], // {ms, a} oldest first; a is the public authorization object
    authorizationById: new Map(),
    openAuthorizations: new Set(), // a objects with status 'open' (possibly past expiry until expireDue runs)
    // stage 3: history
    revisions: new Map(), // payment_id -> [{revision, amount, effMs, recMs, effective_at, recorded_at, reason}]
    paymentsByUser: new Map(), // user id -> [payment objects the user sent or received]
    authorizationsByPayer: new Map(), // user id -> [authorization objects the user authorized]
    authEvents: new Map(), // authorization_id -> {createdMs, initialHold, expMs, captures:[{ms, amount}], closedMs, closedKind, noHistory}
    revSeq: 0, // global commit sequence of revisions (statement snapshots freeze a cutoff)
  };
}

function pushTo(map, key, value) {
  const list = map.get(key);
  if (list) list.push(value);
  else map.set(key, [value]);
}

// Indexes a payment for history: revision 1 at created_at (stage 3).
function indexPayment(s, p, revs) {
  const t = Date.parse(p.created_at);
  if (revs) {
    for (const r of revs) if (r.seq > s.revSeq) s.revSeq = r.seq;
  }
  s.revisions.set(p.payment_id, revs || [{
    revision: 1, amount: p.amount, effMs: t, recMs: t, effective_at: p.created_at, recorded_at: p.created_at, reason: '', seq: ++s.revSeq,
  }]);
  pushTo(s.paymentsByUser, p.from_user_id, p);
  if (p.to_user_id !== p.from_user_id) pushTo(s.paymentsByUser, p.to_user_id, p);
}

// Authorization expiry instant in ms (expires_at has second precision).
function expiryMs(a) {
  return Date.parse(a.expires_at);
}

// Public shape of an authorization (a copy, so later changes do not alter
// responses already stored for idempotent replay).
function authorizationView(a) {
  return { ...a, payment_ids: a.payment_ids.slice() };
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

  // Opaque ids that sort in creation order (stage 3: statement entries at the
  // same effective instant are ordered by payment id): fixed-width base-36 time
  // and per-millisecond counter, then a random suffix.
  newId(prefix, taken) {
    for (;;) {
      const now = Math.max(Date.now(), this.idMs || 0);
      this.idSeq = now === this.idMs ? this.idSeq + 1 : 0;
      this.idMs = now;
      const id = `${prefix}_${now.toString(36).padStart(9, '0')}${this.idSeq.toString(36).padStart(4, '0')}${crypto.randomBytes(5).toString('hex')}`;
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
    const held = this.held(user);
    return {
      user_id: user.id,
      display_name: user.display_name,
      handle: user.handle,
      balance: user.balance,
      total: user.balance,
      available: user.balance - held,
      held,
      currency: this.s.currency,
      minor_units: this.s.minor_units,
    };
  }

  // GET /me with as_of (T) and/or known_at (K): all four money fields for that view.
  meAt(user, T, K, echo) {
    this.expireDue();
    const { total, held } = ledger.moneyAt(this.s, user, T, K);
    return {
      user_id: user.id,
      display_name: user.display_name,
      handle: user.handle,
      balance: total,
      total,
      available: total - held,
      held,
      currency: this.s.currency,
      minor_units: this.s.minor_units,
      ...echo,
    };
  }

  // ---- stage 3: corrections, revisions, statements --------------------------------

  // POST /payments/{id}/corrections, after body validation. Appends one
  // revision and moves the difference between the same two wallets in one step.
  correctPayment(caller, id, { expected_revision, amount, effective_at, reason }) {
    this.expireDue();
    const p = this.s.paymentById.get(id);
    if (!p) throw notFound();
    if (p.from_user_id !== caller.id) throw new ApiError(403, 'forbidden', 'only the original sender may correct this payment');
    if (p.settlement_id !== null || p.authorization_id !== null) {
      throw new ApiError(422, 'linked_payment_immutable', 'settlement members and captures cannot be corrected');
    }
    const revs = this.s.revisions.get(id);
    const last = revs[revs.length - 1];
    if (expected_revision !== last.revision) throw new ApiError(409, 'stale_revision', 'expected_revision is not the latest revision');
    const sender = this.s.users.get(p.from_user_id);
    const receiver = this.s.users.get(p.to_user_id);
    const diff = amount - last.amount;
    const debited = diff > 0 ? sender : receiver;
    const credited = diff > 0 ? receiver : sender;
    const move = Math.abs(diff);
    if (move > 0 && debited.balance - this.held(debited) < move) throw new ApiError(409, 'insufficient_funds', 'insufficient funds');
    if (credited.balance + move > MAX_BALANCE) throw new ApiError(422, 'validation_failed', 'resulting balance out of range');
    const now = Date.now();
    const recMs = Math.max(now, last.recMs + 1); // recorded times strictly increase (ruling S3-1)
    const rev = {
      revision: last.revision + 1,
      amount,
      effMs: effective_at.ms,
      recMs,
      effective_at: ledger.stamp(effective_at.ms),
      recorded_at: ledger.stamp(recMs),
      reason,
      seq: this.s.revSeq + 1,
    };
    const override = { paymentId: id, revs: [...revs, rev] };
    // Balances move only after both wallets' histories are proven sound.
    const balances = new Map([[sender, sender.balance], [receiver, receiver.balance]]);
    balances.set(debited, debited.balance - move);
    balances.set(credited, credited.balance + move);
    for (const u of [sender, receiver]) {
      if (!ledger.historyIsSound(this.s, u, override, Math.max(now, recMs))) {
        throw new ApiError(409, 'historical_overdraft', 'the correction would make a past balance negative');
      }
    }
    revs.push(rev);
    this.s.revSeq = rev.seq;
    for (const [u, b] of balances) u.balance = b;
    return ledger.revisionView(id, rev);
  }

  // GET /payments/{id}/revisions: only the two parties; anyone else gets 404.
  revisionsOf(caller, id) {
    const p = this.s.paymentById.get(id);
    if (!p || (p.from_user_id !== caller.id && p.to_user_id !== caller.id)) throw notFound();
    return { revisions: this.s.revisions.get(id).map((r) => ledger.revisionView(id, r)) };
  }

  // Statement snapshot reference: everything needed to recompute the frozen result.
  statementRef(fromMs, toMs, K) {
    return { from: fromMs, to: toMs, known_at: K === INF ? null : K, cutoff: this.s.revSeq };
  }

  statementFor(user, ref) {
    return ledger.statement(this.s, user, ref.from, ref.to, ref.known_at === null ? INF : ref.known_at, ref.cutoff);
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
    const user = { id, email, email_key: emailKey, display_name: displayName, handle, balance: 0, opening: 0, password_hash: passwordHash };
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

  // ---- holds -------------------------------------------------------------------

  // Materialises clock expiry: every open authorization whose expires_at is at
  // or before now becomes 'expired' and holds nothing. Called before any read
  // or write that depends on holds, so expiry shows even if no request
  // happened at the deadline.
  expireDue(now = Date.now()) {
    for (const a of this.s.openAuthorizations) {
      if (expiryMs(a) <= now) {
        a.status = 'expired';
        a.remaining_amount = 0;
        a.closed_at = a.expires_at;
        const ev = this.s.authEvents.get(a.authorization_id);
        if (ev && ev.closedMs === null) {
          ev.closedMs = ev.expMs;
          ev.closedKind = 'expired';
        }
        this.s.openAuthorizations.delete(a);
      }
    }
  }

  // Sum of the user's open holds (after expiry).
  held(user) {
    this.expireDue();
    let sum = 0;
    for (const a of this.s.openAuthorizations) if (a.from_user_id === user.id) sum += a.remaining_amount;
    return sum;
  }

  // ---- money: the single state-change point ---------------------------------

  // entries: [{from, to, amount, note, visibility}] with user objects.
  // All-or-nothing: validates the resulting total and available amount of
  // every touched wallet, then creates all payments and applies all changes.
  // `release` (stage 2 captures) lowers the payer's held amount in the same
  // step: the capture spends the money reserved for it.
  commitTransfers(entries, { requestId = null, settlementId = null, authorizationId = null, release = null } = {}) {
    this.expireDue();
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
      const heldAfter = BigInt(this.held(user)) - BigInt(release && release.user === user ? release.amount : 0);
      // available = total - held must stay >= 0: held funds cannot pay.
      if (next < 0n || next - heldAfter < 0n) throw new ApiError(409, 'insufficient_funds', 'insufficient funds');
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
        authorization_id: authorizationId,
        created_at: createdAt,
      };
      this.s.payments.push({ ms, p });
      this.s.paymentById.set(p.payment_id, p);
      indexPayment(this.s, p);
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

  // ---- authorizations (stage 2) -------------------------------------------------

  createAuthorization(caller, { to_handle, amount, note, visibility }) {
    if (to_handle === caller.handle) throw new ApiError(422, 'self_payment', 'cannot authorize a payment to yourself');
    const to = this.s.byHandle.get(to_handle);
    if (!to) throw notFound();
    // The hold must fit in the caller's available funds (total - held).
    if (caller.balance - this.held(caller) < amount) throw new ApiError(409, 'insufficient_funds', 'insufficient funds');
    const ms = this.tick();
    const createdSec = Math.floor(ms / 1000);
    const a = {
      authorization_id: this.newId('a', (x) => this.s.authorizationById.has(x)),
      from_user_id: caller.id,
      from_handle: caller.handle,
      to_user_id: to.id,
      to_handle: to.handle,
      amount,
      captured_amount: 0,
      remaining_amount: amount,
      currency: this.s.currency,
      note,
      visibility,
      status: 'open',
      expires_at: rfc3339((createdSec + this.s.authorizationTtlSeconds) * 1000),
      payment_id: null,
      payment_ids: [],
      created_at: rfc3339(createdSec * 1000),
      closed_at: null,
    };
    this.s.authorizations.push({ ms, a });
    this.s.authorizationById.set(a.authorization_id, a);
    this.s.openAuthorizations.add(a);
    pushTo(this.s.authorizationsByPayer, caller.id, a);
    this.s.authEvents.set(a.authorization_id, {
      createdMs: createdSec * 1000, initialHold: amount, expMs: Date.parse(a.expires_at),
      captures: [], closedMs: null, closedKind: null, noHistory: false,
    });
    return authorizationView(a);
  }

  // 404 only for an unknown id; the permitted-party check (403) is the caller's.
  existingAuthorization(id) {
    this.expireDue();
    const a = this.s.authorizationById.get(id);
    if (!a) throw notFound();
    return a;
  }

  // amount: integer >= 1 or undefined (= the remaining amount); final: boolean.
  captureAuthorization(caller, id, { amount, final }) {
    const a = this.existingAuthorization(id);
    if (a.to_user_id !== caller.id) throw new ApiError(403, 'forbidden', 'only the receiver may capture this authorization');
    if (a.status === 'expired') throw new ApiError(409, 'authorization_expired', 'authorization has expired');
    if (a.status !== 'open') throw new ApiError(409, 'authorization_not_open', 'authorization is not open');
    const take = amount === undefined ? a.remaining_amount : amount;
    if (take > a.remaining_amount) {
      throw new ApiError(422, 'capture_exceeds_authorization', 'amount exceeds the remaining authorized amount');
    }
    const payer = this.s.users.get(a.from_user_id);
    const receiver = this.s.users.get(a.to_user_id);
    const closes = final || take === a.remaining_amount;
    const released = closes ? a.remaining_amount : take;
    const { payments } = this.commitTransfers(
      [{ from: payer, to: receiver, amount: take, note: a.note, visibility: a.visibility }],
      { authorizationId: a.authorization_id, release: { user: payer, amount: released } },
    );
    const p = payments[0];
    a.captured_amount += take;
    a.remaining_amount -= released;
    a.payment_id = p.payment_id;
    a.payment_ids.push(p.payment_id);
    const ev = this.s.authEvents.get(a.authorization_id);
    const at = Date.parse(p.created_at);
    if (ev) ev.captures.push({ ms: at, amount: take });
    if (closes) {
      a.status = 'captured';
      a.closed_at = p.created_at;
      if (ev) {
        ev.closedMs = at;
        ev.closedKind = 'captured';
      }
      this.s.openAuthorizations.delete(a);
    }
    return { ...p };
  }

  voidAuthorization(caller, id) {
    const a = this.existingAuthorization(id);
    if (a.from_user_id !== caller.id) throw new ApiError(403, 'forbidden', 'only the payer may void this authorization');
    if (a.status === 'open') {
      const ev = this.s.authEvents.get(a.authorization_id);
      const at = Math.max(Date.now(), ev ? ev.createdMs : 0);
      a.status = 'voided';
      a.remaining_amount = 0;
      a.closed_at = ledger.stamp(at);
      if (ev) {
        ev.closedMs = at;
        ev.closedKind = 'voided';
      }
      this.s.openAuthorizations.delete(a);
    } else if (a.status !== 'voided') {
      throw new ApiError(409, 'authorization_not_open', 'authorization is not open');
    }
    return authorizationView(a);
  }

  listAuthorizations(caller, { direction, status, limit, offset }) {
    this.expireDue();
    const out = [];
    let skipped = 0;
    let hasMore = false;
    for (let i = this.s.authorizations.length - 1; i >= 0; i--) {
      const { a } = this.s.authorizations[i];
      const outgoing = a.from_user_id === caller.id;
      const incoming = a.to_user_id === caller.id;
      if (direction === 'incoming' ? !incoming : direction === 'outgoing' ? !outgoing : !(incoming || outgoing)) continue;
      if (status !== null && a.status !== status) continue;
      if (skipped < offset) { skipped++; continue; }
      if (out.length === limit) { hasMore = true; break; }
      out.push(authorizationView(a));
    }
    return { authorizations: out, has_more: hasMore };
  }

  // ---- reset / export / import -----------------------------------------------------

  replace(state) {
    this.s = state;
  }

  exportSnapshot() {
    this.expireDue();
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
        authorization_ttl_seconds: s.authorizationTtlSeconds,
        authorizations: s.authorizations.map(({ ms, a }) => ({ ms, authorization: authorizationView(a) })),
        // stage 3 history
        openings: [...s.users.values()].map((u) => ({ user_id: u.id, opening: u.opening })),
        revisions: [...s.revisions].map(([paymentId, revs]) => ({
          payment_id: paymentId,
          revisions: revs.map((r) => ({ revision: r.revision, amount: r.amount, effective_at: r.effective_at, recorded_at: r.recorded_at, reason: r.reason, seq: r.seq })),
        })),
        auth_events: [...s.authEvents].map(([id, e]) => ({ authorization_id: id, ...e, captures: e.captures.map((c) => ({ ...c })) })),
      },
    };
  }
}

module.exports = { Store, ApiError, emptyState, authorizationView, rfc3339, tokenDigest, MAX_ID, MAX_BALANCE, indexPayment, pushTo };

'use strict';

const http = require('node:http');
const v = require('./validate');
const { Store, ApiError } = require('./store');
const { planFixture, buildFixtureState, buildImportedState } = require('./snapshot');
const passwords = require('./passwords');
const seeding = require('./seeding');
const web = require('./web');
const { SnapshotStore } = require('./snapshots');
const { INF } = require('./ledger');

const snapshots = new SnapshotStore();

const TEST_BODY_BYTES = 64 * 1024 * 1024;

const store = new Store();

// Converts a validate.js result into a value or a thrown ApiError.
function take(result) {
  if (!result.ok) throw new ApiError(result.error.status, result.error.code, result.error.message);
  return result.value;
}

function requireUser(req) {
  const header = req.headers.authorization;
  const m = typeof header === 'string' ? /^Bearer +(\S+) *$/i.exec(header) : null;
  const user = m ? store.authenticate(m[1]) : null;
  if (!user) throw new ApiError(401, 'unauthenticated', 'missing or invalid bearer token');
  return user;
}

async function readObject(req, { emptyAsObject = false, maxBytes } = {}) {
  const body = take(await v.readJsonBody(req, maxBytes ? { maxBytes } : undefined));
  if (body === undefined && emptyAsObject) return {};
  return take(v.requireObject(body));
}

// Shared shape of the five idempotent write paths (§7): authenticate, parse
// the body as an object, require the key, then resolve the key before any
// field validation; fn runs only for a first use.
async function idempotentWrite(req, res, path, { emptyAsObject = false, authorize } = {}, fn) {
  const user = requireUser(req);
  if (authorize) authorize(user);
  const body = await readObject(req, { emptyAsObject });
  const key = take(v.validateIdempotencyKey(req.headers['idempotency-key']));
  const caller = store.userById(user.id);
  if (!caller) throw new ApiError(401, 'unauthenticated', 'missing or invalid bearer token');
  const out = store.idempotent(caller.id, req.method, path, key, v.canonicalJson(body), () => fn(caller, body));
  sendText(res, out.status, out.text);
}

function sendText(res, status, text) {
  const payload = Buffer.from(text, 'utf8');
  res.writeHead(status, {
    'X-Content-Type-Options': 'nosniff',
    'Cache-Control': 'no-store',
    'Content-Type': 'application/json; charset=utf-8',
    'Content-Length': payload.length,
  });
  res.end(payload);
}

// ---- handlers -----------------------------------------------------------------

async function signup(req, res) {
  const body = await readObject(req);
  const email = take(v.validateEmail(body.email));
  const password = take(v.validatePassword(body.password));
  const displayName = take(v.validateDisplayName(body.display_name));
  const emailKey = v.emailKey(email);
  const handle = v.deriveHandle(email);
  if (store.userByEmail(emailKey)) throw new ApiError(409, 'email_taken', 'email already registered');
  if (store.userByHandle(handle)) throw new ApiError(409, 'handle_taken', 'handle already taken');
  const passwordHash = await passwords.hashPassword(password); // outside any critical section
  const out = store.createUser({ email, emailKey, displayName, handle, passwordHash });
  v.sendJson(res, 201, out);
}

async function login(req, res) {
  const body = await readObject(req);
  if (body.email === undefined || body.password === undefined) throw new ApiError(422, 'validation_failed', 'email and password are required');
  if (typeof body.email !== 'string' || typeof body.password !== 'string') throw new ApiError(400, 'malformed_request', 'email and password must be strings');
  const state = store.s;
  const user = store.userByEmail(v.emailKey(body.email));
  const hash = user ? user.password_hash : null;
  const good = user ? await passwords.verifyPassword(body.password, hash) : await passwords.dummyVerify(body.password);
  // Re-read after the async verify: a reset/import may have replaced the state.
  const current = good ? store.userByEmail(v.emailKey(body.email)) : null;
  if (!current || current !== user) throw new ApiError(401, 'unauthenticated', 'wrong email or password');
  // Seeded users carry a reduced-cost hash until their first login: upgrade it.
  seeding.upgradeAfterLogin(current, body.password, hash, () => store.s === state);
  const token = store.issueToken(current);
  v.sendJson(res, 200, { user_id: current.id, display_name: current.display_name, token });
}

function getMe(req, res, url) {
  const started = Date.now();
  const user = requireUser(req);
  const { as_of: asOf, known_at: knownAt } = take(v.parseMeQuery(url.searchParams));
  if (asOf === null && knownAt === null) {
    v.sendJson(res, 200, store.me(user));
    return;
  }
  const echo = {};
  if (asOf !== null) echo.as_of = asOf.raw;
  if (knownAt !== null) echo.known_at = knownAt.raw;
  // Without as_of the view is the instant the request began; without known_at, everything committed.
  v.sendJson(res, 200, store.meAt(user, asOf ? asOf.ms : started, knownAt ? knownAt.ms : INF, echo));
}

// ---- stage 3: statements, corrections, revisions ----------------------------------

function getStatement(req, res, url) {
  const started = Date.now();
  const user = requireUser(req);
  const q = take(v.validateStatementQuery(url.searchParams));
  if (q.snapshot !== null) {
    v.sendJson(res, 200, take(snapshots.page(user.id, q.snapshot, q.limit, q.offset)));
    return;
  }
  const full = store.statementFor(user, q.from ? q.from.ms : null, q.to ? q.to.ms : started, q.known_at ? q.known_at.ms : INF);
  if (q.known_at) full.known_at = q.known_at.raw;
  const token = snapshots.create(user.id, full);
  v.sendJson(res, 200, take(snapshots.page(user.id, token, q.limit, q.offset)));
}

function correctPayment(req, res, id, path) {
  return idempotentWrite(req, res, path, {}, (caller, body) => {
    const c = take(v.validateCorrection(body, Date.now()));
    return store.correctPayment(caller, id, c);
  });
}

function paymentRevisions(req, res, id) {
  const user = requireUser(req);
  req.resume();
  v.sendJson(res, 200, store.revisionsOf(user, id));
}

function createPayment(req, res) {
  return idempotentWrite(req, res, '/payments', {}, (caller, body) => {
    const toHandle = take(v.validateHandleRef(body.to_handle, 'to_handle'));
    const amount = take(v.validateAmount(body.amount));
    const note = take(v.validateNote(body.note));
    const visibility = take(v.validateVisibility(body.visibility));
    return store.sendPayment(caller, { to_handle: toHandle, amount, note, visibility });
  });
}

function createRequest(req, res) {
  return idempotentWrite(req, res, '/requests', {}, (caller, body) => {
    const payerHandle = take(v.validateHandleRef(body.payer_handle, 'payer_handle'));
    const amount = take(v.validateAmount(body.amount));
    const note = take(v.validateNote(body.note));
    return store.createRequest(caller, { payer_handle: payerHandle, amount, note });
  });
}

function payRequest(req, res, id, path) {
  return idempotentWrite(req, res, path, { emptyAsObject: true }, (caller, body) => {
    const visibility = take(v.validateVisibility(body.visibility));
    return store.payRequest(caller, id, visibility);
  });
}

async function declineRequest(req, res, id) {
  const user = requireUser(req);
  await v.readJsonBody(req);
  v.sendJson(res, 200, store.declineRequest(user, id));
}

async function cancelRequest(req, res, id) {
  const user = requireUser(req);
  await v.readJsonBody(req);
  v.sendJson(res, 200, store.cancelRequest(user, id));
}

function listRequests(req, res, url) {
  const user = requireUser(req);
  const direction = take(v.parseDirection(url.searchParams));
  const status = take(v.parseRequestStatus(url.searchParams));
  const { limit, offset } = take(v.parsePagination(url.searchParams));
  v.sendJson(res, 200, store.listRequests(user, { direction, status, limit, offset }));
}

function createSplit(req, res) {
  return idempotentWrite(req, res, '/splits', {}, (caller, body) => {
    const amount = take(v.validateAmount(body.amount));
    const handles = take(v.validateParticipantHandles(body.participant_handles));
    const note = take(v.validateNote(body.note));
    const shares = v.splitShares(amount, handles.length);
    return store.createSplit(caller, { amount, handles, shares, note });
  });
}

function listActivity(req, res, url) {
  const user = requireUser(req);
  const { limit, offset } = take(v.parsePagination(url.searchParams));
  v.sendJson(res, 200, store.listActivity(user, { limit, offset }));
}

function createSettlement(req, res) {
  const authorize = (user) => {
    if (!store.isOperator(user.id)) throw new ApiError(403, 'forbidden', 'settlement operator required');
  };
  return idempotentWrite(req, res, '/settlements', { authorize }, (caller, body) => {
    const transfers = take(v.validateTransfersShape(body.transfers));
    // Entry errors in input order: each entry's field rules, then its handles.
    const entries = transfers.map((t) => {
      const e = take(v.validateTransferEntry(t));
      const from = store.userByHandle(e.from_handle);
      const to = store.userByHandle(e.to_handle);
      if (!from || !to) throw new ApiError(404, 'not_found', 'not found');
      if (from === to) throw new ApiError(422, 'self_payment', 'a transfer cannot move money to the same wallet');
      return e;
    });
    return store.settle(entries);
  });
}

async function reset(req, res) {
  const fixture = await readObject(req, { maxBytes: TEST_BODY_BYTES });
  const plan = planFixture(fixture);
  // Hashing runs before the swap, which is one assignment (seeding.js).
  const hashes = await seeding.hashFixturePasswords(plan);
  store.replace(buildFixtureState(plan, hashes));
  snapshots.clear();
  v.sendNoContent(res);
}

function exportState(req, res) {
  req.resume();
  // Synchronous, so the snapshot is atomic.
  sendText(res, 200, JSON.stringify(store.exportSnapshot()));
}

async function importState(req, res) {
  const doc = await readObject(req, { maxBytes: TEST_BODY_BYTES });
  store.replace(buildImportedState(doc));
  snapshots.clear();
  v.sendNoContent(res);
}

// ---- authorizations (stage 2) ---------------------------------------------------

const AUTH_STATUSES = ['open', 'captured', 'voided', 'expired'];

function createAuthorization(req, res) {
  return idempotentWrite(req, res, '/authorizations', {}, (caller, body) => {
    const toHandle = take(v.validateHandleRef(body.to_handle, 'to_handle'));
    const amount = take(v.validateAmount(body.amount));
    const note = take(v.validateNote(body.note));
    const visibility = take(v.validateVisibility(body.visibility));
    return store.createAuthorization(caller, { to_handle: toHandle, amount, note, visibility });
  });
}

// Capture amount: optional; an integer >= 1 (values above the remaining amount,
// including above 1000000000, are 422 capture_exceeds_authorization in the store).
function captureAmount(value) {
  if (value === undefined) return undefined;
  if (typeof value === 'number' && Number.isInteger(value) && value > 1000000000) return value;
  return take(v.validateAmount(value));
}

function captureAuthorization(req, res, id, path) {
  return idempotentWrite(req, res, path, { emptyAsObject: true }, (caller, body) => {
    const amount = captureAmount(body.amount);
    if (body.final !== undefined && typeof body.final !== 'boolean') throw new ApiError(400, 'malformed_request', 'final must be a boolean');
    const final = body.final === undefined ? true : body.final;
    return store.captureAuthorization(caller, id, { amount, final });
  });
}

async function voidAuthorization(req, res, id) {
  const user = requireUser(req);
  await v.readJsonBody(req);
  v.sendJson(res, 200, store.voidAuthorization(user, id));
}

function listAuthorizations(req, res, url) {
  const user = requireUser(req);
  const direction = take(v.parseDirection(url.searchParams));
  const status = url.searchParams.get('status');
  if (status !== null && !AUTH_STATUSES.includes(status)) throw new ApiError(422, 'validation_failed', 'status must be open, captured, voided or expired');
  const { limit, offset } = take(v.parsePagination(url.searchParams));
  v.sendJson(res, 200, store.listAuthorizations(user, { direction, status, limit, offset }));
}

// ---- routing ------------------------------------------------------------------------

const REQUEST_ACTION = /^\/requests\/([^/]+)\/(pay|decline|cancel)$/;
const PAYMENT_HISTORY = /^\/payments\/([^/]+)\/(corrections|revisions)$/;
const AUTHORIZATION_ACTION = /^\/authorizations\/([^/]+)\/(capture|void)$/;

async function route(req, res) {
  let url;
  try {
    url = new URL(req.url, 'http://localhost');
  } catch {
    throw new ApiError(400, 'malformed_request', 'invalid request target');
  }
  const path = url.pathname;
  const m = req.method;
  // Browser UI (stage 2): HTML for Accept: text/html on UI routes, JSON otherwise.
  if (web.wantsHtml(req, path)) {
    if (await web.sendShell(req, res)) return;
    throw new ApiError(404, 'not_found', 'not found');
  }
  if (m === 'GET' && path.startsWith('/static/')) {
    if (await web.sendStatic(req, res, path)) return;
    throw new ApiError(404, 'not_found', 'not found');
  }
  const routes = {
    '/health': { GET: () => { req.resume(); v.sendJson(res, 200, { status: 'ok' }); } },
    '/_test/reset': { POST: () => reset(req, res) },
    '/_test/export': { GET: () => exportState(req, res) },
    '/_test/import': { POST: () => importState(req, res) },
    '/auth/signup': { POST: () => signup(req, res) },
    '/auth/login': { POST: () => login(req, res) },
    '/me': { GET: () => getMe(req, res, url) },
    '/statement': { GET: () => getStatement(req, res, url) },
    '/payments': { POST: () => createPayment(req, res) },
    '/requests': { POST: () => createRequest(req, res), GET: () => listRequests(req, res, url) },
    '/splits': { POST: () => createSplit(req, res) },
    '/activity': { GET: () => listActivity(req, res, url) },
    '/settlements': { POST: () => createSettlement(req, res) },
    '/authorizations': { POST: () => createAuthorization(req, res), GET: () => listAuthorizations(req, res, url) },
  };
  let handlers = routes[path];
  if (!handlers) {
    const a = REQUEST_ACTION.exec(path);
    if (a) {
      let id;
      try {
        id = decodeURIComponent(a[1]);
      } catch {
        id = null;
      }
      const action = a[2];
      handlers = {
        POST: () => {
          if (id === null) {
            requireUser(req);
            throw new ApiError(404, 'not_found', 'not found');
          }
          if (action === 'pay') return payRequest(req, res, id, path);
          if (action === 'decline') return declineRequest(req, res, id);
          return cancelRequest(req, res, id);
        },
      };
    }
  }
  if (!handlers) {
    const a = AUTHORIZATION_ACTION.exec(path);
    if (a) {
      let id;
      try {
        id = decodeURIComponent(a[1]);
      } catch {
        id = null;
      }
      handlers = {
        POST: () => {
          if (id === null) {
            requireUser(req);
            throw new ApiError(404, 'not_found', 'not found');
          }
          if (a[2] === 'capture') return captureAuthorization(req, res, id, path);
          return voidAuthorization(req, res, id);
        },
      };
    }
  }
  if (!handlers) {
    const a = PAYMENT_HISTORY.exec(path);
    if (a) {
      let id;
      try {
        id = decodeURIComponent(a[1]);
      } catch {
        id = null;
      }
      const unknown = () => {
        requireUser(req);
        throw new ApiError(404, 'not_found', 'not found');
      };
      handlers = a[2] === 'corrections'
        ? { POST: () => (id === null ? unknown() : correctPayment(req, res, id, path)) }
        : { GET: () => (id === null ? unknown() : paymentRevisions(req, res, id)) };
    }
  }
  if (!handlers) throw new ApiError(404, 'not_found', 'not found');
  const h = handlers[m];
  if (!h) throw new ApiError(405, 'method_not_allowed', 'method not allowed');
  await h();
}

const server = http.createServer((req, res) => {
  route(req, res).catch((e) => {
    if (res.headersSent) {
      res.destroy();
      return;
    }
    if (e instanceof ApiError) {
      v.sendError(res, { status: e.status, code: e.code, message: e.message });
    } else {
      process.stderr.write(`internal error: ${e && e.stack ? e.stack : e}\n`);
      v.sendError(res, { status: 500, code: 'internal_error', message: 'internal error' });
    }
    if (!req.complete) req.resume();
  });
});

server.keepAliveTimeout = 65000;
server.headersTimeout = 66000;
server.requestTimeout = 30000;

passwords.dummyHashReady().catch(() => {});

const port = Number(process.env.PORT) || 8080;
server.listen(port, '0.0.0.0', () => {
  process.stdout.write(`pocketful listening on 0.0.0.0:${port}\n`);
});

const stop = () => server.close(() => process.exit(0)) && setTimeout(() => process.exit(0), 2000).unref();
process.on('SIGTERM', stop);
process.on('SIGINT', stop);

'use strict';

const http = require('node:http');
const v = require('./validate');
const { Store, ApiError } = require('./store');
const { planFixture, buildFixtureState, buildImportedState } = require('./snapshot');
const passwords = require('./passwords');

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
  const user = store.userByEmail(v.emailKey(body.email));
  const good = user ? await passwords.verifyPassword(body.password, user.password_hash) : await passwords.dummyVerify(body.password);
  // Re-read after the async verify: a reset/import may have replaced the state.
  const current = good ? store.userByEmail(v.emailKey(body.email)) : null;
  if (!current || current.password_hash !== user.password_hash) throw new ApiError(401, 'unauthenticated', 'wrong email or password');
  const token = store.issueToken(current);
  v.sendJson(res, 200, { user_id: current.id, display_name: current.display_name, token });
}

function getMe(req, res) {
  v.sendJson(res, 200, store.me(requireUser(req)));
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
  // Slow hashing happens before the swap; the swap itself is one assignment.
  // Each distinct seeded password is hashed once per reset (coordinator scope
  // ruling): seeded users with an identical password share one Argon2id hash
  // and salt, so reset time depends on distinct passwords, not on user count.
  // Signups always get their own salt.
  const distinct = [...new Set(plan.users.map((u) => u.password))];
  const params = passwords.paramsForFixture(distinct.length);
  const digests = await Promise.all(distinct.map((pw) => passwords.hashPassword(pw, params)));
  const byPassword = new Map(distinct.map((pw, i) => [pw, digests[i]]));
  const hashes = plan.users.map((u) => byPassword.get(u.password));
  store.replace(buildFixtureState(plan, hashes));
  v.sendNoContent(res);
}

function exportState(req, res) {
  req.resume();
  sendText(res, 200, JSON.stringify(store.exportSnapshot()));
}

async function importState(req, res) {
  const doc = await readObject(req, { maxBytes: TEST_BODY_BYTES });
  store.replace(buildImportedState(doc));
  v.sendNoContent(res);
}

// ---- routing ------------------------------------------------------------------------

const REQUEST_ACTION = /^\/requests\/([^/]+)\/(pay|decline|cancel)$/;

async function route(req, res) {
  let url;
  try {
    url = new URL(req.url, 'http://localhost');
  } catch {
    throw new ApiError(400, 'malformed_request', 'invalid request target');
  }
  const path = url.pathname;
  const m = req.method;
  const routes = {
    '/health': { GET: () => { req.resume(); v.sendJson(res, 200, { status: 'ok' }); } },
    '/_test/reset': { POST: () => reset(req, res) },
    '/_test/export': { GET: () => exportState(req, res) },
    '/_test/import': { POST: () => importState(req, res) },
    '/auth/signup': { POST: () => signup(req, res) },
    '/auth/login': { POST: () => login(req, res) },
    '/me': { GET: () => getMe(req, res) },
    '/payments': { POST: () => createPayment(req, res) },
    '/requests': { POST: () => createRequest(req, res), GET: () => listRequests(req, res, url) },
    '/splits': { POST: () => createSplit(req, res) },
    '/activity': { GET: () => listActivity(req, res, url) },
    '/settlements': { POST: () => createSettlement(req, res) },
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

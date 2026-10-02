'use strict';

// Service edge: body parsing, error envelopes, response helpers and pure field
// validators. Every validator returns either { ok: true, value } or
// { ok: false, error: { status, code, message } } and never throws.

const MAX_AMOUNT = 1000000000;
const MAX_NOTE_CHARS = 200;
const MAX_KEY_CHARS = 255;
const MAX_TRANSFERS = 32;
const DEFAULT_LIMIT = 50;
const MAX_LIMIT = 200;
const DEFAULT_MAX_BODY_BYTES = 1024 * 1024;
const HANDLE_RE = /^[a-z0-9_]{1,20}$/;
const EMAIL_RE = /^[^@\s]+@[^@\s]+$/;
const DIGITS_RE = /^[0-9]+$/;
const VISIBILITIES = ['public', 'private'];
const DIRECTIONS = ['incoming', 'outgoing'];
const REQUEST_STATUSES = ['pending', 'paid', 'declined', 'cancelled'];

const SECURITY_HEADERS = {
  'X-Content-Type-Options': 'nosniff',
  'X-Frame-Options': 'DENY',
  'Referrer-Policy': 'no-referrer',
  'Content-Security-Policy': "default-src 'none'; frame-ancestors 'none'",
  'Cache-Control': 'no-store',
};

function ok(value) {
  return { ok: true, value };
}

function err(status, code, message) {
  return { ok: false, error: { status, code, message } };
}

const malformed = (message) => err(400, 'malformed_request', message);
const invalid = (message) => err(422, 'validation_failed', message);

function errorBody(code, message) {
  return { error: { code, message } };
}

function isPlainObject(v) {
  return v !== null && typeof v === 'object' && !Array.isArray(v) && !(v instanceof InexactNumber);
}

function charLength(s) {
  let n = 0;
  for (const _ of s) n++;
  return n;
}

// ---- responses -------------------------------------------------------------

function sendJson(res, status, body) {
  const payload = Buffer.from(JSON.stringify(body), 'utf8');
  res.writeHead(status, {
    ...SECURITY_HEADERS,
    'Content-Type': 'application/json; charset=utf-8',
    'Content-Length': payload.length,
  });
  res.end(payload);
}

function sendError(res, error) {
  sendJson(res, error.status, errorBody(error.code, error.message));
}

function sendNoContent(res) {
  res.writeHead(204, SECURITY_HEADERS);
  res.end();
}

// ---- body ------------------------------------------------------------------

// Resolves { ok: true, value } where value is the parsed JSON (undefined for an
// empty body), or a 400 malformed_request error for invalid UTF-8, invalid JSON
// or a body above maxBytes. Never rejects.
function readJsonBody(req, { maxBytes = DEFAULT_MAX_BODY_BYTES } = {}) {
  return new Promise((resolve) => {
    const chunks = [];
    let size = 0;
    let done = false;
    const finish = (result) => {
      if (done) return;
      done = true;
      resolve(result);
    };
    req.on('data', (chunk) => {
      if (done) return;
      size += chunk.length;
      if (size > maxBytes) {
        finish(malformed('request body too large'));
        req.resume();
        return;
      }
      chunks.push(chunk);
    });
    req.on('end', () => finish(parseJsonBuffer(Buffer.concat(chunks))));
    req.on('error', () => finish(malformed('request body could not be read')));
    req.on('aborted', () => finish(malformed('request aborted')));
  });
}

const utf8 = new TextDecoder('utf-8', { fatal: true, ignoreBOM: false });

function parseJsonBuffer(buf) {
  let text;
  try {
    text = utf8.decode(buf);
  } catch {
    return malformed('request body is not valid UTF-8');
  }
  if (text.trim() === '') return ok(undefined);
  try {
    return ok(JSON.parse(text, exactNumbers));
  } catch {
    return malformed('request body is not valid JSON');
  }
}

// A number literal whose exact decimal value differs from the integer it
// parses to: a fraction that rounds away (1000.0000000000001 -> 1000) or an
// integer beyond double precision (9007199254740993 -> 9007199254740992).
// Kept as an object so no number check accepts it and canonicalJson keeps it
// distinct.
class InexactNumber {
  constructor(source) {
    this.source = source;
    Object.freeze(this);
  }
}

const NUMBER_LITERAL_RE = /^-?([0-9]+)(?:\.([0-9]+))?(?:[eE]([+-]?[0-9]+))?$/;

// Exact value of a JSON number literal as a BigInt when it denotes an integer
// (e.g. "1000", "1000.0", "1e3", "1500000e-3"); null when it does not.
function integralLiteralValue(source) {
  const m = NUMBER_LITERAL_RE.exec(source);
  if (!m) return null;
  const frac = m[2] || '';
  const all = (m[1] + frac).replace(/^0+/, '');
  if (all === '') return 0n;
  const digits = all.replace(/0+$/, '');
  const scale = Number(m[3] || 0) - frac.length + (all.length - digits.length);
  if (scale < 0) return null;
  const magnitude = BigInt(digits) * 10n ** BigInt(scale);
  return source.startsWith('-') ? -magnitude : magnitude;
}

// Parsed integers are kept only when the literal denotes exactly that integer.
// Non-integral and non-finite parses are left to the field validators.
function exactNumbers(key, value, ctx) {
  if (typeof value === 'number' && Number.isInteger(value) && ctx && typeof ctx.source === 'string') {
    const exact = integralLiteralValue(ctx.source);
    if (exact === null || exact !== BigInt(value)) return new InexactNumber(ctx.source);
  }
  return value;
}

// A body that parsed but is not a JSON object (array, string, number, null,
// or absent) is the wrong type: 400 malformed_request.
function requireObject(value) {
  if (!isPlainObject(value)) return malformed('request body must be a JSON object');
  return ok(value);
}

// ---- field validators ------------------------------------------------------

// Integral number in 1..1000000000. JSON 1000, 1000.0 and 1e3 are all 1000.
// Missing, strings, booleans, null and any other non-number are 422.
function validateAmount(v) {
  if (v === undefined) return invalid('amount is required');
  if (typeof v !== 'number' || !Number.isFinite(v) || !Number.isInteger(v)) {
    return invalid('amount must be an integer number of minor units');
  }
  if (v < 1 || v > MAX_AMOUNT) return invalid(`amount must be between 1 and ${MAX_AMOUNT}`);
  return ok(v);
}

// Optional, default "". Any non-string (including null) is 422; at most 200
// characters (Unicode code points). Returned verbatim.
function validateNote(v) {
  if (v === undefined) return ok('');
  if (typeof v !== 'string') return invalid('note must be a string');
  if (charLength(v) > MAX_NOTE_CHARS) return invalid(`note must be at most ${MAX_NOTE_CHARS} characters`);
  return ok(v);
}

// Optional, default "public". Anything else, of any type, is 422.
function validateVisibility(v) {
  if (v === undefined) return ok('public');
  if (!VISIBILITIES.includes(v)) return invalid('visibility must be "public" or "private"');
  return ok(v);
}

// Recipient/payer handle reference. Missing is 422; a non-string is 400.
// The string is returned unchanged: a string that names no user (whatever its
// format) is the caller's 404 not_found after lookup.
function validateHandleRef(v, field) {
  if (v === undefined) return invalid(`${field} is required`);
  if (typeof v !== 'string') return malformed(`${field} must be a string`);
  return ok(v);
}

function isValidHandle(s) {
  return typeof s === 'string' && HANDLE_RE.test(s);
}

// local@domain: exactly one "@", non-empty local and domain, no whitespace.
function validateEmail(v) {
  if (v === undefined) return invalid('email is required');
  if (typeof v !== 'string') return malformed('email must be a string');
  if (!EMAIL_RE.test(v)) return invalid('email must be of the form local@domain');
  return ok(v);
}

// Case-insensitive identity key for email uniqueness and login lookup.
function emailKey(email) {
  return email.toLowerCase();
}

// At least 8 characters (Unicode code points).
function validatePassword(v) {
  if (v === undefined) return invalid('password is required');
  if (typeof v !== 'string') return malformed('password must be a string');
  if (charLength(v) < 8) return invalid('password must be at least 8 characters');
  return ok(v);
}

// Signup display name: required string, stored verbatim.
function validateDisplayName(v) {
  if (v === undefined) return invalid('display_name is required');
  if (typeof v !== 'string') return malformed('display_name must be a string');
  return ok(v);
}

// §4, in order: take the local part, lowercase it, replace every character
// (code point) outside [a-z0-9_] with "_", truncate to 20 characters.
// Lowercasing may lengthen the text ("İ" -> "i" + U+0307 -> "i_").
// Expects an email accepted by validateEmail.
function deriveHandle(email) {
  const lowered = email.slice(0, email.indexOf('@')).toLowerCase();
  let out = '';
  let n = 0;
  for (const ch of lowered) {
    if (n === 20) break;
    out += /^[a-z0-9_]$/.test(ch) ? ch : '_';
    n++;
  }
  return out;
}

// Header value as given by req.headers['idempotency-key'].
// Absent or empty: 400 missing_idempotency_key. Over 255 characters: 422.
function validateIdempotencyKey(v) {
  if (Array.isArray(v)) v = v.join(', ');
  if (v === undefined || v === null || v === '') {
    return err(400, 'missing_idempotency_key', 'Idempotency-Key header is required');
  }
  if (charLength(v) > MAX_KEY_CHARS) return invalid(`Idempotency-Key must be at most ${MAX_KEY_CHARS} characters`);
  return ok(v);
}

// ---- query -----------------------------------------------------------------

// params: URLSearchParams. limit default 50, range 1..200; offset default 0,
// 0 or more. Values must be plain decimal digits ("1e9", "4.0", "+4", "" are 422).
function parsePagination(params) {
  const rawLimit = params.get('limit');
  const rawOffset = params.get('offset');
  let limit = DEFAULT_LIMIT;
  let offset = 0;
  if (rawLimit !== null) {
    if (!DIGITS_RE.test(rawLimit)) return invalid('limit must be an integer from 1 to 200');
    limit = Number(rawLimit);
    if (limit < 1 || limit > MAX_LIMIT) return invalid('limit must be an integer from 1 to 200');
  }
  if (rawOffset !== null) {
    if (!DIGITS_RE.test(rawOffset)) return invalid('offset must be an integer of 0 or more');
    offset = Number(rawOffset);
  }
  return ok({ limit, offset });
}

// Absent: null (both directions). Otherwise "incoming" or "outgoing", else 422.
function parseDirection(params) {
  const v = params.get('direction');
  if (v === null) return ok(null);
  if (!DIRECTIONS.includes(v)) return invalid('direction must be "incoming" or "outgoing"');
  return ok(v);
}

// Absent: null (all statuses). Otherwise one of the four statuses, else 422.
function parseRequestStatus(params) {
  const v = params.get('status');
  if (v === null) return ok(null);
  if (!REQUEST_STATUSES.includes(v)) return invalid('status must be pending, paid, declined or cancelled');
  return ok(v);
}

// ---- splits ----------------------------------------------------------------

// Missing: 422. Not an array, or a non-string element: 400. Empty or with a
// duplicate: 422. Returns the handles in the given order.
function validateParticipantHandles(v) {
  if (v === undefined) return invalid('participant_handles is required');
  if (!Array.isArray(v)) return malformed('participant_handles must be an array');
  if (v.some((h) => typeof h !== 'string')) return malformed('participant_handles must contain strings');
  if (v.length === 0) return invalid('participant_handles must not be empty');
  if (new Set(v).size !== v.length) return invalid('participant_handles must not contain duplicates');
  return ok(v.slice());
}

// §9 equal split: whole units, sum to amount, differ by at most one, larger
// shares first in the given order.
function splitShares(amount, n) {
  const base = Math.floor(amount / n);
  const extra = amount - base * n;
  const shares = [];
  for (let i = 0; i < n; i++) shares.push(i < extra ? base + 1 : base);
  return shares;
}

// ---- settlements -----------------------------------------------------------

// Batch shape: transfers must be an array of 1..32 objects; anything else is
// 422 validation_failed. Entries are validated separately, in input order.
function validateTransfersShape(v) {
  if (!Array.isArray(v)) return invalid('transfers must be an array');
  if (v.length < 1 || v.length > MAX_TRANSFERS) return invalid(`transfers must contain 1 to ${MAX_TRANSFERS} entries`);
  if (!v.every(isPlainObject)) return invalid('each transfer must be an object');
  return ok(v);
}

// One settlement entry, field rules only (handle lookup, self-transfer and
// funds are the caller's). Handles must be strings (else 422 batch shape);
// amount, note and visibility follow the payment rules.
// Value: { from_handle, to_handle, amount, note, visibility }.
function validateTransferEntry(t) {
  if (typeof t.from_handle !== 'string') return invalid('from_handle must be a string');
  if (typeof t.to_handle !== 'string') return invalid('to_handle must be a string');
  const amount = validateAmount(t.amount);
  if (!amount.ok) return amount;
  const note = validateNote(t.note);
  if (!note.ok) return note;
  const visibility = validateVisibility(t.visibility);
  if (!visibility.ok) return visibility;
  return ok({
    from_handle: t.from_handle,
    to_handle: t.to_handle,
    amount: amount.value,
    note: note.value,
    visibility: visibility.value,
  });
}

// ---- stage 3: instants, temporal queries, corrections -------------------

const INSTANT_RE = /^([0-9]{4})-([0-9]{2})-([0-9]{2})[Tt]([0-9]{2}):([0-9]{2}):([0-9]{2})(\.[0-9]+)?(?:([Zz])|([+-])([0-9]{2}):([0-9]{2}))$/;

function daysInMonth(y, m) {
  if (m === 2) return (y % 4 === 0 && y % 100 !== 0) || y % 400 === 0 ? 29 : 28;
  return [4, 6, 9, 11].includes(m) ? 30 : 31;
}

// Strict RFC 3339 date-time with a required offset. Value: { raw, ms } where
// raw is the original string (for echoes), ms the epoch milliseconds
// (fraction floored to the millisecond) and sub the fraction digits beyond
// the millisecond without trailing zeros. Anything else is 422.
function parseInstant(raw, field) {
  const bad = () => invalid(`${field} must be an RFC 3339 instant with an offset, e.g. 2026-09-24T13:20:00+00:00`);
  if (typeof raw !== 'string') return bad();
  const m = INSTANT_RE.exec(raw);
  if (!m) return bad();
  const [y, mo, d, h, mi, sec] = m.slice(1, 7).map(Number);
  if (mo < 1 || mo > 12 || d < 1 || d > daysInMonth(y, mo) || h > 23 || mi > 59 || sec > 59) return bad();
  let offsetMin = 0;
  if (!m[8]) {
    const oh = Number(m[10]);
    const om = Number(m[11]);
    if (oh > 23 || om > 59) return bad();
    offsetMin = (m[9] === '-' ? -1 : 1) * (oh * 60 + om);
  }
  const frac = m[7] ? Number(m[7].slice(1, 4).padEnd(3, '0')) : 0;
  const sub = m[7] ? m[7].slice(4).replace(/0+$/, '') : '';
  const date = new Date(0);
  date.setUTCFullYear(y, mo - 1, d);
  date.setUTCHours(h, mi, sec, frac);
  const ms = date.getTime() - offsetMin * 60000;
  if (!Number.isFinite(ms)) return bad();
  return ok({ raw, ms, sub });
}

// A '+' offset sent without percent-encoding arrives as a space: a single
// space exactly where the offset sign belongs is read as '+' (ruling S3-2).
const SPACE_OFFSET_RE = /^([0-9]{4}-[0-9]{2}-[0-9]{2}[Tt][0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]+)?) ([0-9]{2}:[0-9]{2})$/;

// Optional instant query parameter: absent -> null; present (even empty) is
// parsed strictly. The echoed raw value carries the '+' restored.
function parseQueryInstant(params, name) {
  if (!params.has(name)) return ok(null);
  const value = params.get(name).replace(SPACE_OFFSET_RE, '$1+$2');
  return parseInstant(value, name);
}

// GET /me temporal parameters: { as_of, known_at }, each null or { raw, ms }.
function parseMeQuery(params) {
  const asOf = parseQueryInstant(params, 'as_of');
  if (!asOf.ok) return asOf;
  const knownAt = parseQueryInstant(params, 'known_at');
  if (!knownAt.ok) return knownAt;
  return ok({ as_of: asOf.value, known_at: knownAt.value });
}

// GET /statement parameters. A snapshot read takes only limit and offset:
// from, to or known_at alongside snapshot is 422. snapshot is the raw string
// (possibly "") or null when absent.
function validateStatementQuery(params) {
  const snapshot = params.has('snapshot') ? params.get('snapshot') : null;
  if (snapshot !== null && ['from', 'to', 'known_at'].some((k) => params.has(k))) {
    return invalid('snapshot cannot be combined with from, to or known_at');
  }
  const page = parsePagination(params);
  if (!page.ok) return page;
  const out = { snapshot, from: null, to: null, known_at: null, limit: page.value.limit, offset: page.value.offset };
  if (snapshot === null) {
    for (const k of ['from', 'to', 'known_at']) {
      const r = parseQueryInstant(params, k);
      if (!r.ok) return r;
      out[k] = r.value;
    }
  }
  return ok(out);
}

// POST /payments/{id}/corrections body; every invalid case is 422.
// Value: { expected_revision, amount, reason, effective_at: { raw, ms } }.
function validateCorrection(body, nowMs) {
  const rev = body.expected_revision;
  if (typeof rev !== 'number' || !Number.isInteger(rev) || rev < 1 || rev > Number.MAX_SAFE_INTEGER) {
    return invalid('expected_revision must be a positive integer');
  }
  const amount = body.amount;
  if (typeof amount !== 'number' || !Number.isInteger(amount) || amount < 0 || amount > MAX_AMOUNT) {
    return invalid(`amount must be an integer from 0 to ${MAX_AMOUNT}`);
  }
  const reason = body.reason;
  if (typeof reason !== 'string') return invalid('reason must be a string');
  const n = charLength(reason);
  if (n < 1 || n > MAX_NOTE_CHARS) return invalid(`reason must be 1 to ${MAX_NOTE_CHARS} characters`);
  if (body.effective_at === undefined) return invalid('effective_at is required');
  const eff = parseInstant(body.effective_at, 'effective_at');
  if (!eff.ok) return eff;
  if (eff.value.ms > nowMs) return invalid('effective_at must not be later than now');
  return ok({ expected_revision: rev, amount: amount === 0 ? 0 : amount, reason, effective_at: eff.value });
}

// ---- stage 4: refunds and correction batches ------------------------------

// Two parsed instants denote the same moment (offset spellings may differ).
function sameInstant(a, b) {
  return a.ms === b.ms && (a.sub || '') === (b.sub || '');
}

// POST /payments/{id}/refunds body: amount by the ordinary payment rule.
function validateRefund(body) {
  const amount = validateAmount(body.amount);
  if (!amount.ok) return amount;
  return ok({ amount: amount.value });
}

const MAX_BATCH = 32;

// POST /correction-batches whole-body rules: corrections is an array of
// 1..32 objects with distinct string payment_ids. Items are validated one by
// one with validateCorrectionItem, in input order.
function validateBatchShape(body) {
  const items = body.corrections;
  if (!Array.isArray(items)) return invalid('corrections must be an array');
  if (items.length < 1 || items.length > MAX_BATCH) return invalid(`corrections must contain 1 to ${MAX_BATCH} items`);
  if (!items.every(isPlainObject)) return invalid('each correction must be an object');
  if (!items.every((c) => typeof c.payment_id === 'string')) return invalid('each correction needs a payment_id string');
  if (new Set(items.map((c) => c.payment_id)).size !== items.length) return invalid('payment_ids must be distinct');
  return ok({ items });
}

// One batch item: the ordinary correction fields plus payment_id.
function validateCorrectionItem(item, nowMs) {
  if (typeof item.payment_id !== 'string') return invalid('payment_id must be a string');
  const c = validateCorrection(item, nowMs);
  if (!c.ok) return c;
  return ok({ payment_id: item.payment_id, ...c.value });
}

// ---- idempotency helper ----------------------------------------------------

// Canonical text of a parsed JSON value: object keys sorted, no whitespace.
// Two bodies are the "same JSON value" exactly when these strings are equal.
function canonicalJson(value) {
  if (value instanceof InexactNumber) return `~${value.source}`;
  if (Array.isArray(value))return `[${value.map(canonicalJson).join(',')}]`;
  if (isPlainObject(value)) {
    const keys = Object.keys(value).sort();
    return `{${keys.map((k) => `${JSON.stringify(k)}:${canonicalJson(value[k])}`).join(',')}}`;
  }
  return JSON.stringify(value);
}

module.exports = {
  MAX_AMOUNT,
  HANDLE_RE,
  SECURITY_HEADERS,
  errorBody,
  isPlainObject,
  sendJson,
  sendError,
  sendNoContent,
  readJsonBody,
  parseJsonBuffer,
  requireObject,
  validateAmount,
  validateNote,
  validateVisibility,
  validateHandleRef,
  isValidHandle,
  validateEmail,
  emailKey,
  validatePassword,
  validateDisplayName,
  deriveHandle,
  validateIdempotencyKey,
  parsePagination,
  parseDirection,
  parseRequestStatus,
  validateParticipantHandles,
  splitShares,
  validateTransfersShape,
  validateTransferEntry,
  canonicalJson,
  parseInstant,
  parseQueryInstant,
  parseMeQuery,
  validateStatementQuery,
  validateCorrection,
  sameInstant,
  validateRefund,
  validateBatchShape,
  validateCorrectionItem,
};

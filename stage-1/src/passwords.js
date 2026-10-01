'use strict';

// Password storage: Argon2id from Node's built-in crypto.argon2 (Node >= 24.7).
// Parameters were measured on 2 vCPU / 2 GiB with 50 concurrent hashes; see RUN.md.
// Hashing runs on the libuv thread pool, never inside a state-changing critical section.

const crypto = require('node:crypto');

const PARAMS = Object.freeze({ memory: 47104, passes: 2, parallelism: 1 }); // KiB, t, p
// OWASP minimum argon2id setting, used only for large reset fixtures so that
// hashing every seeded user still fits the 10 s reset budget on 2 vCPU.
const BULK_PARAMS = Object.freeze({ memory: 19456, passes: 2, parallelism: 1 });
const BULK_THRESHOLD = 64; // seeded users above which BULK_PARAMS is used
const SALT_BYTES = 16;
const TAG_BYTES = 32;
const PREFIX = '$argon2id$v=19$';
const FORMAT = /^\$argon2id\$v=19\$m=(\d{1,7}),t=(\d{1,3}),p=(\d{1,3})\$([A-Za-z0-9_-]{16,})\$([A-Za-z0-9_-]{16,})$/;

function derive(password, salt, { memory, passes, parallelism }, tagLength) {
  return new Promise((resolve, reject) => {
    crypto.argon2('argon2id', {
      message: Buffer.from(password, 'utf8'),
      nonce: salt,
      parallelism,
      tagLength,
      memory,
      passes,
    }, (error, key) => (error ? reject(error) : resolve(key)));
  });
}

async function hashPassword(password, params = PARAMS) {
  const salt = crypto.randomBytes(SALT_BYTES);
  const key = await derive(password, salt, params, TAG_BYTES);
  return `${PREFIX}m=${params.memory},t=${params.passes},p=${params.parallelism}$${salt.toString('base64url')}$${key.toString('base64url')}`;
}

function paramsForFixture(userCount) {
  return userCount > BULK_THRESHOLD ? BULK_PARAMS : PARAMS;
}

// Bounds keep an imported hash from demanding unbounded memory or time.
function parse(stored) {
  const m = typeof stored === 'string' ? FORMAT.exec(stored) : null;
  if (!m) return null;
  const params = { memory: Number(m[1]), passes: Number(m[2]), parallelism: Number(m[3]) };
  if (params.memory < 8 * params.parallelism || params.memory > 65536) return null;
  if (params.passes < 1 || params.passes > 10 || params.parallelism < 1 || params.parallelism > 4) return null;
  return { params, salt: Buffer.from(m[4], 'base64url'), expected: Buffer.from(m[5], 'base64url') };
}

function isPasswordHash(s) {
  return parse(s) !== null;
}

// Resolves true/false; never rejects. Comparison is constant time.
async function verifyPassword(password, stored) {
  const parsed = parse(stored);
  if (!parsed) return false;
  const { params, salt, expected } = parsed;
  try {
    const key = await derive(password, salt, params, expected.length);
    return key.length === expected.length && crypto.timingSafeEqual(key, expected);
  } catch {
    return false;
  }
}

// A real hash of a random secret: unknown-email logins verify against it so
// they cost the same time as a wrong password.
let dummyHash = null;
async function dummyVerify(password) {
  if (dummyHash === null) dummyHash = await hashPassword(crypto.randomBytes(18).toString('base64url'));
  await verifyPassword(password, dummyHash);
  return false;
}

module.exports = { hashPassword, verifyPassword, isPasswordHash, dummyVerify, paramsForFixture, PARAMS, BULK_PARAMS };

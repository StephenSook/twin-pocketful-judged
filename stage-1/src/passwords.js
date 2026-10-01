'use strict';

// Password storage: Argon2id from Node's built-in crypto.argon2 (Node >= 24.7).
// Parameters were measured on 2 vCPU / 2 GiB with 50 concurrent hashes; see RUN.md.
// Hashing runs on the libuv thread pool, never inside a state-changing critical section.

const crypto = require('node:crypto');

const PARAMS = Object.freeze({ memory: 47104, passes: 2, parallelism: 1 }); // KiB, t, p
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

async function hashPassword(password) {
  const salt = crypto.randomBytes(SALT_BYTES);
  const key = await derive(password, salt, PARAMS, TAG_BYTES);
  return `${PREFIX}m=${PARAMS.memory},t=${PARAMS.passes},p=${PARAMS.parallelism}$${salt.toString('base64url')}$${key.toString('base64url')}`;
}

function isPasswordHash(s) {
  return typeof s === 'string' && FORMAT.test(s);
}

// Resolves true/false; never rejects. Comparison is constant time.
async function verifyPassword(password, stored) {
  const m = typeof stored === 'string' ? FORMAT.exec(stored) : null;
  if (!m) return false;
  const params = { memory: Number(m[1]), passes: Number(m[2]), parallelism: Number(m[3]) };
  const salt = Buffer.from(m[4], 'base64url');
  const expected = Buffer.from(m[5], 'base64url');
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

module.exports = { hashPassword, verifyPassword, isPasswordHash, dummyVerify, PARAMS };

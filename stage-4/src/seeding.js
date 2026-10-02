'use strict';

// Seeded-password hashing for POST /_test/reset and rehash-on-login
// (coordinator ruling on §2/§6/§10). Seeded fixture passwords are public test
// input: each seeded user gets a unique salt and an Argon2id hash at the
// reduced SEED_PARAMS, computed before the state swap so reset, an immediate
// export and import stay well under 10 s. After a seeded user's first
// successful login the password is rehashed in the background with the full
// PARAMS used for signups. A plaintext is held only in process memory while
// its hash is being computed; it is never stored in state, exported or logged.

const passwords = require('./passwords');

const RESET_WORKERS = 4; // matches the libuv pool; keeps the queue short
const REHASH_WORKERS = 1; // background upgrades never take the whole pool

// Resolves hashes[i] for plan.users[i], each with its own salt.
async function hashFixturePasswords(plan) {
  const hashes = new Array(plan.users.length);
  let next = 0;
  const worker = async () => {
    while (next < plan.users.length) {
      const i = next++;
      hashes[i] = await passwords.hashPassword(plan.users[i].password, passwords.SEED_PARAMS);
    }
  };
  await Promise.all(Array.from({ length: Math.min(RESET_WORKERS, plan.users.length) }, worker));
  return hashes;
}

// ---- rehash on login --------------------------------------------------------

const queue = []; // {user, password, oldHash, isCurrent}
const queued = new WeakSet(); // users with an upgrade already queued
let running = 0;

async function runOne(job) {
  try {
    // Dropped when the state was replaced or the hash changed meanwhile.
    if (!job.isCurrent() || job.user.password_hash !== job.oldHash) return;
    const hash = await passwords.hashPassword(job.password, passwords.PARAMS);
    if (job.isCurrent() && job.user.password_hash === job.oldHash) job.user.password_hash = hash;
  } catch {
    // keep the working seeded hash; a later login queues the upgrade again
  } finally {
    queued.delete(job.user);
  }
}

function pump() {
  while (running < REHASH_WORKERS && queue.length > 0) {
    running++;
    runOne(queue.shift()).finally(() => {
      running--;
      pump();
    });
  }
}

// Called after a successful login verified `password` against `oldHash`.
function upgradeAfterLogin(user, password, oldHash, isCurrent) {
  if (!passwords.needsRehash(oldHash) || queued.has(user)) return;
  queued.add(user);
  queue.push({ user, password, oldHash, isCurrent });
  pump();
}

module.exports = { hashFixturePasswords, upgradeAfterLogin };

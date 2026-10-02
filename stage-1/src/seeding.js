'use strict';

// Seeded-password hashing for POST /_test/reset (coordinator scope ruling:
// reset cost must not grow with user count; no plaintext is ever persisted or
// exported).
//
// Each distinct seeded password is hashed once with Argon2id; users who share
// it share the hash and salt. Small fixtures are hashed before the state swap.
// Large ones are swapped in at once with password_hash === null and hashed in
// the background, a few at a time so interactive requests keep the worker
// pool. A seeded plaintext lives only in this module's memory until its hash
// is done. Login of a pending user starts that user's hash first and then
// verifies against it; export waits until no hash is pending.

const passwords = require('./passwords');

const INLINE_MAX = passwords.BULK_THRESHOLD; // distinct passwords hashed before the swap
const BACKGROUND_WORKERS = 2;

// state -> job; a WeakMap so a replaced state's job is simply dropped.
const jobs = new WeakMap();

function startGroup(state, group) {
  if (group.promise === null) {
    group.promise = passwords.hashPassword(group.password, group.params).then((hash) => {
      for (const u of group.users) u.password_hash = hash;
      group.password = null; // the plaintext is no longer needed
      group.done = true;
      return hash;
    }, (error) => {
      group.promise = null; // retry on the next demand
      throw error;
    });
  }
  return group.promise;
}

function runBackground(state, job, isCurrent) {
  const worker = async () => {
    // Stops as soon as a later reset/import replaces this state.
    while (job.next < job.groups.length && isCurrent()) {
      const group = job.groups[job.next++];
      try {
        await startGroup(state, group);
      } catch {
        // left pending; a login or export demand retries it
      }
    }
  };
  job.finished = Promise.all(Array.from({ length: BACKGROUND_WORKERS }, worker)).then(() => undefined);
}

// Returns { hashes, attach } where hashes[i] is plan.users[i]'s hash or null
// (pending). attach(state, isCurrent) must be called right after the swap.
async function hashFixturePasswords(plan) {
  const byPassword = new Map();
  for (const u of plan.users) {
    if (!byPassword.has(u.password)) byPassword.set(u.password, []);
    byPassword.get(u.password).push(u);
  }
  const distinct = [...byPassword.keys()];
  const params = passwords.paramsForFixture(distinct.length);
  if (distinct.length <= INLINE_MAX) {
    const digests = await Promise.all(distinct.map((pw) => passwords.hashPassword(pw, params)));
    const hashOf = new Map(distinct.map((pw, i) => [pw, digests[i]]));
    return { hashes: plan.users.map((u) => hashOf.get(u.password)), attach: () => {} };
  }
  return {
    hashes: plan.users.map(() => null),
    attach(state, isCurrent) {
      const groups = distinct.map((pw) => ({
        password: pw,
        params,
        users: byPassword.get(pw).map((u) => state.users.get(u.id)),
        promise: null,
        done: false,
      }));
      const byUser = new Map();
      for (const g of groups) for (const u of g.users) byUser.set(u.id, g);
      const job = { groups, byUser, next: 0, finished: null };
      jobs.set(state, job);
      runBackground(state, job, isCurrent);
    },
  };
}

// The user's password hash, computing it first if it is still pending.
async function hashFor(state, user) {
  if (user.password_hash !== null) return user.password_hash;
  const job = jobs.get(state);
  const group = job && job.byUser.get(user.id);
  if (!group) return null;
  return startGroup(state, group);
}

// Resolves when every seeded hash of `state` is done.
async function allHashed(state) {
  const job = jobs.get(state);
  if (!job) return;
  await job.finished; // background workers, a few hashes at a time
  await Promise.all(job.groups.map((g) => startGroup(state, g))); // any left over
}

module.exports = { hashFixturePasswords, hashFor, allHashed };

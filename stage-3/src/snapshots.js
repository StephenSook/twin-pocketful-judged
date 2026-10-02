'use strict';

// Frozen statement results for stable pagination (stage 3). A token pages
// exactly the result captured at the first read; reset and import clear every
// token, so a token from before them is unknown (404).

const crypto = require('node:crypto');

function notFound() {
  return { ok: false, error: { status: 404, code: 'not_found', message: 'unknown statement snapshot' } };
}

function deepFreeze(v) {
  if (v !== null && typeof v === 'object' && !Object.isFrozen(v)) {
    Object.freeze(v);
    for (const k of Object.keys(v)) deepFreeze(v[k]);
  }
  return v;
}

class SnapshotStore {
  constructor() {
    this.byToken = new Map();
    this.epoch = 0;
  }

  // Forget every token (POST /_test/reset and a successful import).
  clear() {
    this.byToken = new Map();
    this.epoch += 1;
  }

  // Stores a deep, frozen copy of the full-window result and returns its token.
  create(userId, result) {
    const token = `st${this.epoch.toString(36)}_${crypto.randomBytes(24).toString('base64url')}`;
    this.byToken.set(token, { userId, epoch: this.epoch, result: deepFreeze(structuredClone(result)) });
    return token;
  }

  // One page of a stored result: the result's keys in their original order,
  // entries sliced by offset/limit, then has_more and snapshot.
  page(userId, token, limit, offset) {
    if (typeof token !== 'string' || token === '') return notFound();
    const snap = this.byToken.get(token);
    if (!snap || snap.userId !== userId || snap.epoch !== this.epoch) return notFound();
    const all = Array.isArray(snap.result.entries) ? snap.result.entries : [];
    const out = {};
    for (const k of Object.keys(snap.result)) {
      out[k] = k === 'entries' ? all.slice(offset, offset + limit) : snap.result[k];
    }
    if (!('entries' in out)) out.entries = [];
    out.has_more = offset + limit < all.length;
    out.snapshot = token;
    return { ok: true, value: out };
  }
}

module.exports = { SnapshotStore };

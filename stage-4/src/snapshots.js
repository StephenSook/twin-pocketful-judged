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

  // Forget every token (POST /_test/reset).
  clear() {
    this.byToken = new Map();
    this.epoch += 1;
  }

  // JSON-safe copy of every live snapshot in creation order, for
  // GET /_test/export (ruling S3-3). Each entry carries either params (a
  // reference made by createRef) or result (a frozen result made by create).
  exportAll() {
    return Array.from(this.byToken, ([token, snap]) => (snap.params !== undefined
      ? { token, user_id: snap.userId, params: structuredClone(snap.params) }
      : { token, user_id: snap.userId, result: structuredClone(snap.result) }));
  }

  export() {
    return this.exportAll();
  }

  // True when data is an array that restore() accepts.
  static isValidExport(data) {
    if (!Array.isArray(data)) return false;
    const seen = new Set();
    for (const e of data) {
      if (e === null || typeof e !== 'object' || Array.isArray(e)) return false;
      if (typeof e.token !== 'string' || e.token === '' || e.token.length > 64 || seen.has(e.token)) return false;
      if (typeof e.user_id !== 'string') return false;
      const isObj = (x) => x !== null && typeof x === 'object' && !Array.isArray(x);
      if (isObj(e.params) === (e.result !== undefined)) return false;
      if (e.result !== undefined && !(isObj(e.result) && Array.isArray(e.result.entries))) return false;
      seen.add(e.token);
    }
    return true;
  }

  // Replaces every token with the exported set (POST /_test/import): tokens
  // from the destination's previous state are gone, imported ones work again.
  // Returns false and changes nothing when data is invalid.
  restore(data) {
    if (!SnapshotStore.isValidExport(data)) return false;
    this.epoch += 1;
    const next = new Map();
    for (const e of data) {
      next.set(e.token, e.params !== undefined
        ? { userId: e.user_id, epoch: this.epoch, params: deepFreeze(structuredClone(e.params)) }
        : { userId: e.user_id, epoch: this.epoch, result: deepFreeze(structuredClone(e.result)) });
    }
    this.byToken = next;
    return true;
  }

  newToken() {
    return `st${this.epoch.toString(36)}_${crypto.randomBytes(24).toString('base64url')}`;
  }

  // Stores a frozen copy of small recomputation parameters and returns a token.
  createRef(userId, params) {
    const token = this.newToken();
    this.byToken.set(token, { userId, epoch: this.epoch, params: deepFreeze(structuredClone(params)) });
    return token;
  }

  // The frozen parameters behind a token made by createRef, or 404.
  resolve(userId, token) {
    const snap = this.lookup(userId, token);
    if (!snap || snap.params === undefined) return notFound();
    return { ok: true, value: snap.params };
  }

  lookup(userId, token) {
    if (typeof token !== 'string' || token === '') return null;
    const snap = this.byToken.get(token);
    if (!snap || snap.userId !== userId || snap.epoch !== this.epoch) return null;
    return snap;
  }

  // Stores a deep, frozen copy of the full-window result and returns its token.
  create(userId, result) {
    const token = this.newToken();
    this.byToken.set(token, { userId, epoch: this.epoch, result: deepFreeze(structuredClone(result)) });
    return token;
  }

  // One page of a stored result: the result's keys in their original order,
  // entries sliced by offset/limit, then has_more and snapshot.
  page(userId, token, limit, offset) {
    const snap = this.lookup(userId, token);
    if (!snap || snap.result === undefined) return notFound();
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

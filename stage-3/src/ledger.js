'use strict';

// Stage-3 history: payment revisions, effective/recorded time, historical
// balances and holds, statements and the historical-overdraft check. Pure
// functions over the state object `s` built by store.js / snapshot.js.
//
// Times are epoch milliseconds. Every payment has a revision list
// s.revisions.get(payment_id) = [{revision, amount, effMs, recMs,
// effective_at, recorded_at, reason}] (revision 1 at created_at). A read with
// known_at K selects, per payment, the latest revision with recMs <= K
// (K = Infinity means everything committed). Selected revisions apply at their
// effective time. Holds come from s.authEvents (see authHoldEvents).

const INF = Number.POSITIVE_INFINITY;

// RFC 3339 with +00:00; milliseconds only when not a whole second (ruling S3-1).
function stamp(ms) {
  const iso = new Date(ms).toISOString();
  return ms % 1000 === 0 ? iso.replace(/\.\d{3}Z$/, '+00:00') : iso.replace(/Z$/, '+00:00');
}

// Latest revision recorded at or before K, or null. `override` replaces the
// revision list of one payment (used to test a correction before applying it).
function selectRevision(s, paymentId, K, override) {
  const revs = override && override.paymentId === paymentId ? override.revs : s.revisions.get(paymentId);
  for (let i = revs.length - 1; i >= 0; i--) if (revs[i].recMs <= K) return revs[i];
  return null;
}

function paymentsOf(s, userId) {
  return s.paymentsByUser.get(userId) || [];
}

// Hold changes for one authorization as known at K: [{t, dHeld}].
function authHoldEvents(a, ev, K) {
  if (!ev || ev.noHistory || ev.createdMs > K) return [];
  const out = [{ t: ev.createdMs, dHeld: ev.initialHold }];
  let held = ev.initialHold;
  for (const c of ev.captures) {
    if (c.ms > K) break;
    if (ev.closedMs !== null && ev.closedKind !== 'expired' && ev.closedMs <= K && c.ms > ev.closedMs) break;
    out.push({ t: c.ms, dHeld: -c.amount });
    held -= c.amount;
  }
  if (held <= 0) return out;
  if (ev.closedMs !== null && ev.closedKind !== 'expired' && ev.closedMs <= K) {
    out.push({ t: ev.closedMs, dHeld: -held }); // final capture or void releases the remainder
  } else {
    out.push({ t: ev.expMs, dHeld: -held }); // an open hold expires at its deadline
  }
  return out;
}

// All total/held changes for a user as known at K, unsorted.
function userEvents(s, user, K, override) {
  const out = [];
  for (const p of paymentsOf(s, user.id)) {
    const rev = selectRevision(s, p.payment_id, K, override);
    if (!rev || rev.amount === 0) continue;
    out.push({ t: rev.effMs, dTotal: p.from_user_id === user.id ? -rev.amount : rev.amount, dHeld: 0 });
  }
  for (const a of s.authorizationsByPayer.get(user.id) || []) {
    for (const e of authHoldEvents(a, s.authEvents.get(a.authorization_id), K)) out.push({ t: e.t, dTotal: 0, dHeld: e.dHeld });
  }
  return out;
}

// GET /me?as_of=T&known_at=K: total and held at instant T (inclusive).
function moneyAt(s, user, T, K) {
  let total = user.opening;
  let held = 0;
  for (const e of userEvents(s, user, K, null)) {
    if (e.t <= T) {
      total += e.dTotal;
      held += e.dHeld;
    }
  }
  return { total, held };
}

// True when, under the latest revisions (with `override`), the user's total and
// available are nonnegative after every boundary at or before nowMs. All
// movements at one instant are combined before checking.
function historyIsSound(s, user, override, nowMs) {
  const events = userEvents(s, user, INF, override).sort((x, y) => x.t - y.t);
  let total = user.opening;
  let held = 0;
  for (let i = 0; i < events.length;) {
    const t = events[i].t;
    if (t > nowMs) break;
    while (i < events.length && events[i].t === t) {
      total += events[i].dTotal;
      held += events[i].dHeld;
      i++;
    }
    if (total < 0 || total - held < 0) return false;
  }
  return true;
}

function compareIds(a, b) {
  return a < b ? -1 : a > b ? 1 : 0;
}

// Full-window statement for [from, to) as known at K (from = null: wallet opening).
function statement(s, user, fromMs, toMs, K) {
  const rows = [];
  for (const p of paymentsOf(s, user.id)) {
    const rev = selectRevision(s, p.payment_id, K, null);
    if (!rev) continue;
    rows.push({ p, rev, delta: p.from_user_id === user.id ? -rev.amount : rev.amount });
  }
  rows.sort((x, y) => x.rev.effMs - y.rev.effMs || compareIds(x.p.payment_id, y.p.payment_id));
  let opening = user.opening;
  const entries = [];
  let running = 0;
  for (const r of rows) {
    if (fromMs !== null && r.rev.effMs < fromMs) {
      opening += r.delta;
      continue;
    }
    if (r.rev.effMs >= toMs) break;
    entries.push(r);
  }
  running = opening;
  const out = entries.map((r) => {
    running += r.delta;
    return {
      payment: { ...r.p, amount: r.rev.amount },
      delta: r.delta,
      balance_after: running,
      revision: r.rev.revision,
      effective_at: r.rev.effective_at,
      recorded_at: r.rev.recorded_at,
    };
  });
  return { opening_balance: opening, entries: out, closing_balance: running };
}

function revisionView(paymentId, r) {
  return {
    payment_id: paymentId,
    revision: r.revision,
    amount: r.amount,
    effective_at: r.effective_at,
    recorded_at: r.recorded_at,
    reason: r.reason,
  };
}

module.exports = { stamp, selectRevision, moneyAt, historyIsSound, statement, revisionView, INF };

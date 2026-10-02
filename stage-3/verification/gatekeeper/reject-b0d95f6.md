# REJECT b0d95f6

Preflight exact clean revision b0d95f69ec608fd52889d217dbace036e96217bc, built from `/tmp/gatekeeper-s3-x6k0z8vs/candidate-b0d95f6`, 2 CPUs/2 GiB, internal network. This successor fixes the arithmetic and malformed-history-import findings from 8548455: history_exact.py and history_import.py both exit 0.

The provided isolated harness (`--repo /tmp/gatekeeper-s3-x6k0z8vs/candidate-b0d95f6 --stage 3 --mode isolated --out /tmp/gatekeeper-s3-x6k0z8vs/check-b0d95f6`) exits 0, stages 1/2/3 pass, claimed stage 3. The corrected modeler `run_all.py` exits 1 at R1-118 import status. This time it is a product failure: an unchanged export returns 422 `state history has a negative balance`.

Minimal reproduction: wallet a=100, b=0. Authorize 100, void the hold, then immediately pay 100, all within the same wall-clock second. Observed authorization.created_at `2026-10-02T02:06:47+00:00`, void.closed_at `2026-10-02T02:06:47.007+00:00`, subsequent payment.created_at `2026-10-02T02:06:47+00:00`. Historical `/me?as_of=<payment.created_at>` returns total 0, held 100, available −100. Creating a new 100 authorization after the void likewise yields historical total 100, held 200, available −100. Export followed by unchanged import returns 422 in both cases.

Command: `PYTHONDONTWRITEBYTECODE=1 python3 stage-3/verification/gatekeeper/lifecycle_clock.py http://172.24.0.7:18080`, exit 1. Output is in `/tmp/gatekeeper-s3-x6k0z8vs/lifecycle_clock-b0d95f6.log`. All values printed are timestamps, statuses or amounts; no private export or token is logged.

Expected: newly committed money/hold events do not precede the release they depend on; total and available remain nonnegative at every historical boundary; unchanged own exports import with 204. Earlier imported receipts remain unchanged. The builder and coordinator received the full reproduction. Rejection remains open pending a successor and full acceptance gates.

# REJECT 2299fe83ee780dc6b1667d4591617a97940a2920

Stage-1 tree: `338698cde81d5168f43c6f042a0f95abeeec9987`.
Clean checkout: `/tmp/gatekeeper-s1-v_ns6w8t/candidate-2299fe8`.
Evidence logs: `/tmp/gatekeeper-s1-v_ns6w8t/` (private exports/tokens are not logged).

Two concrete specification discrepancies remain open:

1. Section 4 says no operation produces balances outside ±2^53. Reset of a valid one-user fixture with balance 9007199254740992 returns 422 instead of 204. The implementation limits balances to 2^53−1. Inclusion of the stated endpoint requires a fix or an explicit quoted ruling.
2. Section 4 says lowercase the email local part, then replace every character outside `[a-z0-9_]`, then truncate. Signup with U+0130 followed by `@example.test` returns handle `_`; lowercasing U+0130 expands to `i` plus combining dot, so the specified result is `i_`.

Smallest automated reproduction (prints no credentials):

```sh
PYTHONDONTWRITEBYTECODE=1 python3 stage-1/verification/gatekeeper/boundaries.py http://172.24.0.3:18080
```

Observed exit 1, 0 passed / 2 failed. The URL served the clean candidate, with 2 CPUs, 2 GiB and a Docker internal network.

## Gate evidence

1. Provided tool, run from `/home/ubuntu/work/dark-factory-wearedevs`:

   `/home/ubuntu/work/dark-factory-wearedevs/.venv/bin/python -m harness run --track pocketful --repo /tmp/gatekeeper-s1-v_ns6w8t/candidate-2299fe8 --stage 1 --mode isolated --out /tmp/gatekeeper-s1-v_ns6w8t/harness-2299fe8`

   Exit 0. Own stage: collected 147, passed 147, failed 0, not run 0. Next stage: collected 35, passed 0, failed as expected 1, not run 34 (tool fail-fast). Claimed stage 1, highest contiguous stage 1. No independent next-stage probe was written.

2. `PYTHONDONTWRITEBYTECODE=1 python3 stage-1/verification/model/driver.py --base-url http://172.24.0.3:18080`, verification revision 34d30b2: exit 0, `DIFFERENTIAL PASS operations=263 seed=20261001 persistence=pass concurrency=50 auth-controls=pass`. Driver 67dbebc previously failed on an incorrect 21-character expected handle; fixed in e148d3a. Ledger audit closure remains pending and is not claimed complete.

3. `PYTHONDONTWRITEBYTECODE=1 python3 stage-1/verification/gatekeeper/probe.py http://172.24.0.3:18080`: exit 0, 917 assertions, maximum request 0.167 seconds. Fifty concurrent flights; every atomic snapshot in the debit burst checks total conservation, nonnegative balances, request-payment uniqueness and receipt/balance agreement. A successful one-at-a-time history witness is found. An earlier checker invocation was terminated because its exhaustive ordering search was too slow; prioritizing enabled reads and earliest completed writes, with an explicit search budget, fixed the verifier. This aborted run is not a pass.

4. `docker build --no-cache -t gatekeeper-s1-2299fe8 /tmp/gatekeeper-s1-v_ns6w8t/candidate-2299fe8/stage-1`: exit 0. `PYTHONDONTWRITEBYTECODE=1 python3 stage-1/verification/gatekeeper/environment.py gatekeeper-s1-2299fe8 gatekeeper-s1-internal`: exit 0, 171 assertions, startup 0.3504/0.311 seconds, max request 2.6395 seconds including 50 concurrent password logins. Container inspection verified 2 CPUs / 2 GiB and internal-only network.

5. No previous accepted stage exists, so a previous-version upgrade is not applicable. The environment command above exported, stopped and removed the source, started a distinct destination, imported, and verified original tokens, password login, balances and exact retries; destination tokens were invalidated.

6. SHA-256 comparison with initial baseline: exit 0, 30 provided harness/test files checked, zero changed. Product source search: five JS files, zero check/test identifier hits; source review found generic business guards. This is a bounded inspection, not proof of all possible hidden branches.

7. `PYTHONDONTWRITEBYTECODE=1 python3 stage-1/verification/gatekeeper/mutate.py /tmp/gatekeeper-s1-v_ns6w8t/candidate-2299fe8/stage-1 gatekeeper-s1-internal /tmp/gatekeeper-s1-v_ns6w8t/mutations-2299fe8`: exit 0, planted 5, caught 5. Removed overdraft guard → nonnegative snapshot failure; omitted credits → conservation failure; bypassed idempotency → repeated original writes; removed pending guards → repeated request payment; bypassed private visibility → operator sees private transfer. Mutants existed only in temporary copies and their containers were removed. No unobservable faults counted, no uncaught faults.

8. Partial security evidence: independent authorization and visibility checks passed, including operator isolation and wrong-role parties. Imported password storage is Argon2id with per-user random salts; equal passwords produced distinct hashes. No external application dependencies are declared, so pinned-package advisory inventory is empty. Bounded credential-pattern scan: 21 files, zero matching files (never prints matching values). A complete security claim awaits the remaining ledger audit and is not made here. The coordinator ruled page security headers not applicable for stage 1.

9. Own-stage and next-stage counts are separated in gate 1. No earlier stage exists. Harness claimed stage 1.

10. Independent probes and model driver used plain HTTP at non-loopback container IP 172.24.0.3. Stage 1 has no browser screens; UI-origin check is not applicable.

## Earlier findings

- e3f5e4a and b5fac7f isolated harnesses each had 146/147 own-stage checks pass and one failure: third-party request pay returned 404 rather than required 403. Fixed in 2299fe8, observed 147/147 pass. Authorization rulings changed during review; final implementation follows endpoint-specific 403 behavior. The final quoted ruling must be recorded before acceptance.
- Zero-share payment defect reported by builder was fixed in b5fac7f; independent zero-share payment check passes in 2299fe8.
- Auxiliary container startup initially failed because an assumed harness network name did not exist. A dedicated Docker internal network resolved this environment error; the failed attempt is not product evidence.

No acceptance manifest is issued. Rejection remains open until a new candidate resolves the concrete discrepancies and passes all required gates, including ledger audit closure.

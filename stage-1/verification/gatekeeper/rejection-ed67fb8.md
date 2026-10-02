# REJECT ed67fb81a641fbce9e9a24a09bf3a8f78b0aaaca

Stage-1 tree: `d15a9b1635eeea114da2a4a2e82beef47d245893`.
Clean copy: `/tmp/gatekeeper-s1-v_ns6w8t/candidate-ed67fb8`.

Expected: a valid reset completes within its ten-second timeout (§2/§3.3). The supplied requirements state no maximum fixture-user count. Observed: one reset containing 1,000 users (150,750 JSON bytes) times out at 10.0347 seconds in the candidate limited to 2 CPUs / 2 GiB on an internal Docker network. The builder disclosed an approximately 650-user ceiling; independent observation confirms a concrete failure beyond it.

Reproduce with one request, from the result repository:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 stage-1/verification/gatekeeper/reset_size.py http://172.24.0.5:18080 1000
```

The tool generates ephemeral synthetic passwords and prints no credential values. The initial equivalent inline command exited 1 with `users=1000`, `body_bytes=150750`, `outcome=TimeoutError`, `seconds=10.0347`. The committed tool rerun is logged separately in `/tmp/gatekeeper-s1-v_ns6w8t/reset1000-ed67fb8-script.log`.

A fix or an explicit applicable fixture-bound ruling is required. No acceptance manifest is issued.

## Other observed gates on this revision

All commands below exited 0. Logs are under `/tmp/gatekeeper-s1-v_ns6w8t/` with the command family and revision in their filenames.

1. Provided tool from `/home/ubuntu/work/dark-factory-wearedevs`: `/home/ubuntu/work/dark-factory-wearedevs/.venv/bin/python -m harness run --track pocketful --repo /tmp/gatekeeper-s1-v_ns6w8t/candidate-ed67fb8 --stage 1 --mode isolated --out /tmp/gatekeeper-s1-v_ns6w8t/harness-ed67fb8`. Own stage: 147 collected, 147 passed, 0 failed, 0 not run. Next stage: 35 collected, 0 passed, 1 failed as expected, 34 not run because of tool fail-fast. Highest contiguous stage 1; claimed stage 1. No custom next-stage probe.
2. `PYTHONDONTWRITEBYTECODE=1 python3 stage-1/verification/model/driver.py --base-url http://172.24.0.5:18080`: 263 operations, seed 20261001, persistence pass, concurrency 50, auth-controls pass, boundary pass.
3. `PYTHONDONTWRITEBYTECODE=1 python3 stage-1/verification/gatekeeper/probe.py http://172.24.0.5:18080`: 917 assertions, max request 0.1622 seconds; atomic snapshot invariants, serial-history witness, duplicate-key and request-pay bursts passed.
4. `docker build --no-cache -t gatekeeper-s1-ed67fb8 /tmp/gatekeeper-s1-v_ns6w8t/candidate-ed67fb8/stage-1`: clean build passed. `PYTHONDONTWRITEBYTECODE=1 python3 stage-1/verification/gatekeeper/environment.py gatekeeper-s1-ed67fb8 gatekeeper-s1-internal`: 422 assertions, startup 0.2591/0.2715 seconds, maximum request 2.5176 seconds, 50-flight login/signup/unknown-login bursts pass. These smaller-fixture results do not override the 1,000-user reset failure.
5. The environment command above exports, removes the source container, imports into a distinct destination, and verifies tokens, balances, hashed-password login, exact receipts/retries and destination-token invalidation. No previously accepted stage exists, so a prior-version upgrade is not applicable.
6. `PYTHONDONTWRITEBYTECODE=1 python3 stage-1/verification/gatekeeper/integrity.py /tmp/gatekeeper-s1-v_ns6w8t/candidate-ed67fb8 /home/ubuntu/work/dark-factory-wearedevs /tmp/gatekeeper-s1-v_ns6w8t/provided-baseline.json`: 30 provided files byte-identical; 26 tracked files scanned, zero credential-pattern file hits; five product files, zero check-identifier hits; zero declared external package dependencies, so the pinned-package advisory inventory is empty. These are bounded scans supplemented by source review, not claims of exhaustive static proof.
7. `PYTHONDONTWRITEBYTECODE=1 python3 stage-1/verification/gatekeeper/mutate.py /tmp/gatekeeper-s1-v_ns6w8t/candidate-ed67fb8/stage-1 gatekeeper-s1-internal /tmp/gatekeeper-s1-v_ns6w8t/mutations-ed67fb8`: five planted faults, five caught, zero uncaught/discarded. Faults: overdraft guard, credit application, idempotency cache, pending-state guard, private-feed filtering. Scratch containers removed; product untouched.
8. `PYTHONDONTWRITEBYTECODE=1 python3 stage-1/verification/gatekeeper/security.py http://172.24.0.5:18080`: 152 assertions; unauthenticated/unknown bearer matrix, request IDs, handle-based permissions, operator isolation, idempotency user scope, private listings and Argon2id password storage passed. Password salts differed; raw bearer tokens and plaintext passwords were absent from the export. Tokens are stored as cryptographic digests; §10 permits token-bearing state exports. No pages exist; page-header checks are not applicable.
9. Own-stage and next-stage results are separated above; no earlier stage exists.
10. API checks used plain HTTP on non-loopback container IP 172.24.0.5. Stage 1 has no UI screens.

## Prior rejection closure

- Third-party request-action 404: fixed in 2299fe8 and governed by final coordinator ruling recorded in ledger 18805af: endpoint-specific “Not the payer is 403 forbidden” / “Not the requester is 403 forbidden” wins; unknown IDs remain 404.
- Inclusive balance endpoint: fixed in 145a95f; Unicode lowercase expansion: fixed in 9a272ad. `PYTHONDONTWRITEBYTECODE=1 python3 stage-1/verification/gatekeeper/boundaries.py http://172.24.0.5:18080` exited 0, two passed / zero failed.
- Cold unknown-login timeouts: fixed in ed67fb8. `PYTHONDONTWRITEBYTECODE=1 python3 stage-1/verification/gatekeeper/cold_login.py gatekeeper-s1-ed67fb8 gatekeeper-s1-internal` exited 0; 50/50 HTTP 401, maximum 2.357 seconds.
- Earlier verifier defects and environment errors remain recorded in rejection-2299fe8.md and rejection-18805af.md; none counted as passing evidence.
- Known audit findings R1-024, A1, A2, A4 have coordinator quoted rulings in ledger eb261eb, as recorded in rejection-18805af.md. No undelivered audit report is independently treated as an acceptance gate. The concrete reset-timeout finding remains open.

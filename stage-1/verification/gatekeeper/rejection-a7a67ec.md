# REJECT a7a67ec925a1df1cb70d6bab1fb5a3d8d0b7ad8f

Stage-1 tree: `58412602cbe28296796d91618b44b8248339d805`.
Clean copy: `/tmp/gatekeeper-s1-v_ns6w8t/candidate-a7a67ec`.

Section 10 states: “Test control calls have a 10-second timeout.” A 1,000-distinct-password reset returns 204 in 0.0266 seconds, but its immediate export times out after 10.0104 seconds. The candidate defers the expensive seeded-password work to export; the ten-second obligation applies to export too. The supplied requirements contain no fixture-user/distinct-password bound or export exception.

Reproduction (exit 1):

```sh
PYTHONDONTWRITEBYTECODE=1 python3 stage-1/verification/gatekeeper/pending_export.py http://172.24.0.6:18080 1000
```

The tool generates private random passwords, logs only operation/status/timing, and sends exactly reset followed immediately by export. The clean candidate uses two CPUs, 2 GiB and an internal Docker network. No ACCEPT is issued; the export timeout remains open pending a fix or a quoted applicable scope ruling.

## Observed evidence

All commands below exited 0. Unless specified otherwise, run from `/home/ubuntu/work/band-work/current`. Logs are under `/tmp/gatekeeper-s1-v_ns6w8t/`.

1. Clean-copy provided check, from `/home/ubuntu/work/dark-factory-wearedevs`:

   `/home/ubuntu/work/dark-factory-wearedevs/.venv/bin/python -m harness run --track pocketful --repo /tmp/gatekeeper-s1-v_ns6w8t/candidate-a7a67ec --stage 1 --mode isolated --out /tmp/gatekeeper-s1-v_ns6w8t/harness-a7a67ec`

   Exact dispatched shared-repository command, same working directory:

   `.venv/bin/python -m harness run --track pocketful --repo /home/ubuntu/work/band-work/current --stage 1 --mode isolated --out /home/ubuntu/work/band-work/checks/pocketful-judged/s1-1`

   Both report revision a7a67ec, highest contiguous stage 1 and claimed stage 1. Own-stage counts: 147 collected, 147 passed, 0 failed, 0 not run. Next-stage counts: 35 collected, 0 passed, 1 failed as expected, 34 not run due fail-fast. Stage 2 was applicable: the Pocketful stage-1 tool invoked that suite and reported counts, with no exemption; the participant guide specifies the next-suite probe for graded tracks. No independent next-stage probe was written.

2. `PYTHONDONTWRITEBYTECODE=1 python3 stage-1/verification/model/driver.py --base-url http://172.24.0.6:18080`: 263 operations, persistence pass, concurrency 50, auth-controls pass, boundary pass.
3. `PYTHONDONTWRITEBYTECODE=1 python3 stage-1/verification/gatekeeper/probe.py http://172.24.0.6:18080`: 917 assertions, max request 0.1089 seconds; serial-history witness and sampled invariants pass.
4. `docker build --no-cache -t gatekeeper-s1-a7a67ec /tmp/gatekeeper-s1-v_ns6w8t/candidate-a7a67ec/stage-1`: clean build pass. `PYTHONDONTWRITEBYTECODE=1 python3 stage-1/verification/gatekeeper/environment.py gatekeeper-s1-a7a67ec gatekeeper-s1-internal`: 422 assertions, startup 0.2603/0.2751 seconds, max request 2.5763 seconds, including 50-flight normal-login/signup/unknown-login bursts. These small-fixture checks do not override the distinct-password export timeout.
5. The environment command exports a small fixture, removes the source, imports into a fresh destination and validates tokens, balances, password login, exact retries and destination credential removal. No previously accepted stage exists for prior-version upgrade testing.
6. `PYTHONDONTWRITEBYTECODE=1 python3 stage-1/verification/gatekeeper/integrity.py /tmp/gatekeeper-s1-v_ns6w8t/candidate-a7a67ec /home/ubuntu/work/dark-factory-wearedevs /tmp/gatekeeper-s1-v_ns6w8t/provided-baseline.json`: 30 provided files unchanged, 33 tracked files scanned with zero credential-pattern hits, six product files with zero check-identifier hits, zero declared external package dependencies (empty pinned-package advisory inventory). Bounded scans and source review, not exhaustive static proof.
7. `PYTHONDONTWRITEBYTECODE=1 python3 stage-1/verification/gatekeeper/mutate.py /tmp/gatekeeper-s1-v_ns6w8t/candidate-a7a67ec/stage-1 gatekeeper-s1-internal /tmp/gatekeeper-s1-v_ns6w8t/mutations-a7a67ec`: five planted, five caught, zero uncaught/discarded. Same overdraft/credit/idempotency/pending/private-feed faults as earlier reports; scratch-only mutations and removed containers.
8. `PYTHONDONTWRITEBYTECODE=1 python3 stage-1/verification/gatekeeper/security.py http://172.24.0.6:18080`: 152 assertions, authorization/visibility/identifier matrix and hashed export checks passed. Salted Argon2id hashes are checked; raw passwords and bearer tokens do not enter exported state. The verifier's earlier per-account salt-uniqueness assertion was an overconstraint beyond the stated salted-hash requirement: repeated seeded passwords may now share a salted hash, as the builder's scope-ruling handoff explicitly states. Salt presence and slow parameters remain enforced. This correction is disclosed, not a product defect or a hidden exemption.
9. Stage counts are separated in item 1; no earlier stage exists.
10. API checks used plain HTTP on non-loopback container IP 172.24.0.6. No browser UI or page security-header requirements exist in Stage 1.

Prior shared-password reset rejection is closed: `PYTHONDONTWRITEBYTECODE=1 python3 stage-1/verification/gatekeeper/reset_size.py http://172.24.0.6:18080 1000` exited 0, 204 in 0.1105 seconds. Earlier balance/Unicode/authorization and cold-login fixes remain in the candidate; final dedicated rerun logs are alongside this evidence. Earlier failures, verifier corrections and quoted audit rulings remain recorded in the preceding rejection reports and ledger. The current blocker is immediate export after a distinct-password reset.

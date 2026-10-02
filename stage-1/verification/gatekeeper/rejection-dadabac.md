# REJECT dadabacc74b1236f56adae6ff9a5116fc7bcebb0 — security scope unresolved

Stage-1 tree: `87bdb3f0fc1287cb93b8e990cf26864878f16e2f`.
Clean copy: `/tmp/gatekeeper-s1-v_ns6w8t/candidate-dadabac`.

The latest security ruling delivered to this reviewer, coordinator message 9358587b, says: “C is rejected; the OWASP minimum stays.” Candidate dadabac instead initializes seeded hashes with Argon2id m=1024 KiB, t=1, p=1. Builder cites a later ruling, but its text has not yet reached this reviewer. This is a scope blocker, not a claim that the timing fix failed. A later explicit fixture-only exception can close it by ruling; do not silently relabel a below-minimum hash as meeting the original minimum.

```sh
PYTHONDONTWRITEBYTECODE=1 python3 stage-1/verification/gatekeeper/password_scope.py http://172.24.0.7:18080
```

Exit 1: initial seed `m=1024,t=1,p=1`; signup and post-login upgrade `m=47104,t=2,p=1`; `initial_seed_meets_original_minimum=false`; behavior checks passed, 28 assertions. Wrong passwords did not trigger rehash. The original `security.py` also exited 1 at `slow password hash parameters`; its earlier authorization assertions had passed.

## Passing evidence on the exact product revision

Logs are under `/tmp/gatekeeper-s1-v_ns6w8t/`. The commands below exited 0 unless stated otherwise. Run verification commands from `/home/ubuntu/work/band-work/current`.

- Clean build: `docker build --no-cache -t gatekeeper-s1-dadabac /tmp/gatekeeper-s1-v_ns6w8t/candidate-dadabac/stage-1`.
- Provided harness, from `/home/ubuntu/work/dark-factory-wearedevs`: `/home/ubuntu/work/dark-factory-wearedevs/.venv/bin/python -m harness run --track pocketful --repo /tmp/gatekeeper-s1-v_ns6w8t/candidate-dadabac --stage 1 --mode isolated --out /tmp/gatekeeper-s1-v_ns6w8t/harness-dadabac`.
- Shared-path dispatched rerun, same working directory: `.venv/bin/python -m harness run --track pocketful --repo /home/ubuntu/work/band-work/current --stage 1 --mode isolated --out /home/ubuntu/work/band-work/checks/pocketful-judged/s1-2`. Shared HEAD d1ebec2 adds only RUN.md documentation to dadabac's product. Output s1-1 was retained, not overwritten.
- Both harnesses: own-stage 147 collected / 147 passed / 0 failed / 0 not run; applicable next stage 35 collected / 0 passed / 1 failed as expected / 34 not run due tool fail-fast. Claimed stage 1, highest contiguous stage 1. Applicability: Pocketful tool invoked stage 2 and emitted counts, no exemption. No independent next-stage probe.
- `PYTHONDONTWRITEBYTECODE=1 python3 stage-1/verification/model/driver.py --base-url http://172.24.0.7:18080`: 263 operations, persistence pass, concurrency 50, auth-controls pass, boundary pass.
- `PYTHONDONTWRITEBYTECODE=1 python3 stage-1/verification/gatekeeper/probe.py http://172.24.0.7:18080`: concurrency/invariant and serial-history checks passed (917 assertions; precise timing in log).
- `PYTHONDONTWRITEBYTECODE=1 python3 stage-1/verification/gatekeeper/seeded_limits.py http://172.24.0.7:18080`: 544 assertions; 1,000 distinct users reset 0.389s, immediate export 0.0042s; 5,000 distinct reset 2.0064s, immediate export 0.0117s. Each case: 49 correct logins returned 200, one wrong password returned 401, 50 signups returned 201, import preserved credentials and invalidated sessions newer than the snapshot. Maximum immediate seeded-login times 0.0252/0.0309s.
- `PYTHONDONTWRITEBYTECODE=1 python3 stage-1/verification/gatekeeper/environment.py gatekeeper-s1-dadabac gatekeeper-s1-internal`: 422 assertions, startup 0.2678/0.2825s, maximum request 2.6475s. Limited to 2 CPUs / 2 GiB, network internal. Exported small state survives destruction of the source container and import into a fresh destination with original tokens, password login, exact receipts and retries. No previous accepted stage exists for prior-version upgrade.
- `PYTHONDONTWRITEBYTECODE=1 python3 stage-1/verification/gatekeeper/integrity.py /tmp/gatekeeper-s1-v_ns6w8t/candidate-dadabac /home/ubuntu/work/dark-factory-wearedevs /tmp/gatekeeper-s1-v_ns6w8t/provided-baseline.json`: 30 provided files unchanged; 35 tracked files scanned, zero credential-pattern hits; six product files, zero check-identifier hits; zero declared external package dependencies, so advisory inventory is empty. Bounded scan plus source review.
- `PYTHONDONTWRITEBYTECODE=1 python3 stage-1/verification/gatekeeper/mutate.py /tmp/gatekeeper-s1-v_ns6w8t/candidate-dadabac/stage-1 gatekeeper-s1-internal /tmp/gatekeeper-s1-v_ns6w8t/mutations-dadabac`: five planted, five caught, zero uncaught/discarded; overdraft, omitted credit, idempotency, pending-state and private-feed faults. Scratch containers removed; product unmodified.
- Plain HTTP non-loopback origin is the container IP 172.24.0.7. No Stage-1 browser screens or page-header requirements exist.

The former large-reset and pending-export runtime failures are fixed in this revision. Earlier rejection reports preserve their evidence and all other fixed defects. Security is the sole remaining unresolved scope gate; no acceptance manifest is issued in this report.

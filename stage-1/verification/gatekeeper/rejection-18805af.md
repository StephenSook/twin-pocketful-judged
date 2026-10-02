# REJECT 18805af24c11b91e62fff9f7ecb503aaf23f69ac

Stage-1 tree: `0f68b39211dbd649137cbef960b4d78e1665bbef`.
Clean copy: `/tmp/gatekeeper-s1-v_ns6w8t/candidate-18805af`.

Expected: every request finishes within five seconds at up to 50 in flight, under 2 CPUs / 2 GiB and no outbound network (§2).
Observed: a fresh process receiving 50 simultaneous unknown-account login requests returned 48 unauthenticated responses and timed out on two requests. Maximum observed client duration: 5.0138 seconds.

Reproduction from the result repository:

```sh
docker build --no-cache -t gatekeeper-s1-18805af /tmp/gatekeeper-s1-v_ns6w8t/candidate-18805af/stage-1
PYTHONDONTWRITEBYTECODE=1 python3 stage-1/verification/gatekeeper/cold_login.py gatekeeper-s1-18805af gatekeeper-s1-internal
```

Build exit 0. Reproduction exit 1: `FAIL`, 50 requests, 48 HTTP 401, 2 TimeoutError. The tool starts a fresh limited container, waits for health, makes the burst and removes the container. The dedicated `gatekeeper-s1-internal` network was created with `docker network create --internal gatekeeper-s1-internal` (exit 0). No live credential is logged.

Independent corroboration: `PYTHONDONTWRITEBYTECODE=1 python3 stage-1/verification/gatekeeper/environment.py gatekeeper-s1-18805af gatekeeper-s1-internal` exited 1 at the same unknown-account burst after successful normal-login and signup bursts. Its five-second HTTP timeout is a failed limits check, not a pass. It did not reach migration; migration must be rerun after the fix.

Code inspection suggests a cause: `dummyVerify` initializes `dummyHash` after awaiting its hash; concurrent cold callers each enter the initialization and perform separate expensive dummy hashes. This explanation is an inference, not additional behavioral evidence.

## Completed checks on this exact revision

- Provided isolated harness command, from `/home/ubuntu/work/dark-factory-wearedevs`: `/home/ubuntu/work/dark-factory-wearedevs/.venv/bin/python -m harness run --track pocketful --repo /tmp/gatekeeper-s1-v_ns6w8t/candidate-18805af --stage 1 --mode isolated --out /tmp/gatekeeper-s1-v_ns6w8t/harness-18805af`. Exit 0; own stage 147 collected / 147 passed / 0 failed / 0 not run. Next stage 35 collected / 0 passed / 1 failed as expected / 34 not run due tool fail-fast. Claimed stage 1, highest contiguous stage 1.
- `PYTHONDONTWRITEBYTECODE=1 python3 stage-1/verification/model/driver.py --base-url http://172.24.0.4:18080`: exit 0, `DIFFERENTIAL PASS operations=263 seed=20261001 persistence=pass concurrency=50 auth-controls=pass boundary=pass`.
- `PYTHONDONTWRITEBYTECODE=1 python3 stage-1/verification/gatekeeper/probe.py http://172.24.0.4:18080`: exit 0, 917 assertions, max request 0.1473 seconds. Concurrency/invariant snapshots, serial-history witness, request at-most-once and identical-key races passed.
- `PYTHONDONTWRITEBYTECODE=1 python3 stage-1/verification/gatekeeper/boundaries.py http://172.24.0.4:18080`: exit 0, 2 passed / 0 failed. Inclusive 2^53 and Unicode lowercase expansion now comply, closing both 2299fe8 rejection items in 145a95f and 9a272ad respectively.
- `PYTHONDONTWRITEBYTECODE=1 python3 stage-1/verification/gatekeeper/mutate.py /tmp/gatekeeper-s1-v_ns6w8t/candidate-18805af/stage-1 gatekeeper-s1-internal /tmp/gatekeeper-s1-v_ns6w8t/mutations-18805af`: exit 0, 5 planted / 5 caught / 0 uncaught / 0 discarded. Removed overdraft guard, dropped credits, disabled idempotency, removed pending-state guards, bypassed private feed all produced named assertion failures. Mutation anchors were updated for the BigInt implementation; only temporary copies were mutated.
- API checks used plain HTTP on a non-loopback Docker IP and an internal network. No UI exists at this stage.

Full tamper/security recheck and cross-process import were not completed on this revision after the limits failure; prior-revision evidence does not constitute a current pass. No earlier accepted stage exists for an upgrade check. No acceptance manifest is issued.

## Audit rulings now available

Ledger revision eb261eb records coordinator closure of audit f0a9650 findings: null amount is 422 because “invalid amount values (including strings and booleans)” is non-exhaustive; split participants are exactly the supplied ordered handles; “A share of 0 is legal and still produces a request” makes zero-share requests payable; code-point note lengths preserve Unicode/emoji semantics. Ledger 18805af records the final request-action ruling: endpoint-specific “Not the payer is 403 forbidden” and “Not the requester is 403 forbidden” take precedence; any wrong-role caller gets 403 on existing requests and unknown IDs get 404. The inclusive balance ruling excludes neither endpoint of ±2^53. No pending audit artifact alone is treated as an acceptance gate.

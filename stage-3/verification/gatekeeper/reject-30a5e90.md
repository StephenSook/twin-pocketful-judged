# REJECT 30a5e90

The clean image fixes lifecycle chronology: lifecycle_clock.py exits 0 (57 assertions). The full modeler suite exits 0 (532 inherited and 75 temporal operations), and the clean-copy provided harness passes through stage 3.

The dispatched shared-repository harness at verification-only HEAD 5ba69bc exits 1:

`/home/ubuntu/work/dark-factory-wearedevs/.venv/bin/python -m harness run --track pocketful --repo /home/ubuntu/work/band-work/current --stage 3 --mode isolated --out /home/ubuntu/work/band-work/checks/pocketful-judged/s3-2`

Stage 1: 147/147; stage 2: 35/35; stage 3: 5 passed, 1 failed. `test_a_statement_walks_the_balance_forward` expects [-300,-200], observes only [-300]. The issue is no longer ID ordering: the last payment is missing because its millisecond timestamp equals or exceeds the default half-open window's `to=Date.now()`.

Independent reproduction: seed a=100, b=0, then send 50 sequential one-unit payments from a to b with different keys using one persistent HTTP connection. Immediately request `/statement?limit=200` on that connection. Every payment returned 201. Expected 50 entries and closing balance 50; observed 49 and 51.

Command: `PYTHONDONTWRITEBYTECODE=1 python3 stage-3/verification/gatekeeper/read_clock.py http://172.24.0.7:18080`, exit 1. Evidence `/tmp/gatekeeper-s3-x6k0z8vs/read_clock-30a5e90.log`. Default read-time boundaries must follow committed logical events, while explicit `to` retains its strict half-open comparison. Builder committed the proposed fix at 5e403de; independent retest pending.

Other independent scripts on this exact image exit 0: history_exact, history_import (64), history (786), historical_holds (90), correction_races (341, 50 in flight and six atomic snapshots), history_limits (997, 5000 payments/200 snapshots/50 concurrent corrections), and upgrade_holds (67, accepted Stage2 source destroyed before import). Passing subsets do not override the failed provided gate.

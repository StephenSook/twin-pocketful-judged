# Stage3 independent gates

Preparation only: no candidate has passed these checks yet. Stage1 and Stage2 are frozen. All writable checks/evidence live here; scratch clones, builds, sensitive in-memory exports and temporary logs remain under `/tmp`.

Run the supplied isolated harness first on a clean exact candidate and with the dispatched shared-repository command. Count stages1–3 separately from the tool-applicable Stage4 probe. Never write a custom Stage4 probe.

Run the modeler's committed Stage3 driver with two isolated candidate processes and real accepted Stage1/Stage2 sources as documented by the modeler. Then run:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 stage-3/verification/gatekeeper/history.py http://CANDIDATE:8080
PYTHONDONTWRITEBYTECODE=1 python3 stage-3/verification/gatekeeper/historical_holds.py http://CANDIDATE:8080
```

`history.py` checks opening balances, inclusive as_of/known_at, selected effective-time statements, full-window pagination, frozen snapshots after corrections, snapshot ownership/reset epochs, original receipts, current-versus-historical overdraft precedence, zero reversals, immutable replay, strict recorded-time progression, invalid temporal/correction fields, and50-way expected-revision/idempotent races.

`historical_holds.py` checks historical held/available before creation and after void, known_at excluding later lifecycle events, a historical-available failure despite current affordability, failure-key reuse, and immutable settlement/capture revision history.

Inherited probes/browser scripts are copied here from accepted Stage2 verification without changing the frozen folder. Inspect export adapters and mutation source anchors against the exact Stage3 candidate before running them. `integrity.py` inventories Stage3 product sources and compares supplied-check hashes. Use the existing harness venv for browser scripts, plain non-loopback HTTP,375/1440screenshots, all six routes and eight brief rules. No application dependency is introduced by these verification tools.

Additional acceptance coverage to complete with the candidate:

- Equal-effective-time combined movements avoid transient/order-dependent historical overdrafts; statement ties use payment id.
- Corrections move payments into/out of windows while prior snapshots remain frozen; concurrently paged snapshots keep one full-window balance chain.
- Corrections racing against payments, holds, captures and reset/import preserve exact total and available invariants in atomic snapshots.
- Seeded future created_at reset422 leaves all state unchanged; original seed balances are net and opening balances immutable.
- Future temporal queries, offset-equivalent instants and exact echo strings; strict recorded timestamps under rapid corrections follow coordinator ruling if needed.
- Snapshot ownership plus reset/import epochs; limit/offset final partial and beyond-end pages; unknown query fields ignored.
- Export from accepted Stage1 and Stage2, stop/remove source, import into candidate; keep original tokens, pending requests, holds/captures, original replay receipts and balances. Candidate exports preserve revision/opening/event history and corrections.
- Historical captures, final releases, partial void/expiry and known expiry deadlines; seeded closed holds do not invent prior lifecycle.
- Plant Stage3 faults in scratch copies (revision guard, boundary comparison, correction history replacement, snapshot freezing/ownership); add checks for any uncaught observable fault.
- Record full audit closure, every earlier rejection/fix, fixture-hash scope limitation, exact stage tree, commands/exits/counts and retained browser evidence in the final manifest.

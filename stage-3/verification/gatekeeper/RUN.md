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
- Snapshot ownership and reset invalidation; source tokens survive export/import while destination-only tokens disappear (S3-3); limit/offset final partial and beyond-end pages; unknown query fields ignored.
- Export from accepted Stage1 and Stage2, stop/remove source, import into candidate; keep original tokens, pending requests, holds/captures, original replay receipts and balances. Candidate exports preserve revision/opening/event history and corrections.
- Historical captures, final releases, partial void/expiry and known expiry deadlines; seeded closed holds do not invent prior lifecycle.
- Plant Stage3 faults in scratch copies (revision guard, boundary comparison, correction history replacement, snapshot freezing/ownership); add checks for any uncaught observable fault.
- Record full audit closure, every earlier rejection/fix, fixture-hash scope limitation, exact stage tree, commands/exits/counts and retained browser evidence in the final manifest.

## Timestamp ruling S3-1

Coordinator c8fc20a6 supersedes the earlier second-precision choice for Stage3. recorded_at, closed_at and correction effective_at echoes may include milliseconds; revision1 effective_at/recorded_at equal the original created_at exactly. Strictly increasing correction recorded times may bump1ms when the clock does not advance. Original Stage1/2 receipt timestamps remain unchanged. Omitted known_at/current reads select everything committed when the read begins, including a revision assigned a bumped visible timestamp; explicit known_at compares visible instants literally and inclusively. Query offsets resolve to exact instants at millisecond resolution. The strict-order assertion in history.py already compares parsed instants without imposing second precision.

S3-2 (coordinator3f6b8219): for as_of, known_at, from and to, a decoded single space exactly at the offset-sign position followed by HH:MM is read as + and echoed with +. Other malformed values remain422. history.py deliberately sends raw + in each of these query parameters and checks the /me echo normalization.

S3-3 (coordinator7465c99b) supersedes the initial handoff's import-epoch invalidation: snapshots are exported service state. Source tokens retain their frozen result after import; destination-only tokens are removed; reset clears all tokens. history.py now checks replacement through a real export/reset/import round trip. Cross-process coverage remains part of acceptance. The same ruling confirms aggregate nonnegativity at each effective/event instant, not an arbitrary sequential ordering of movements tied at that instant.

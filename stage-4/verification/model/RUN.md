# Stage 4 model verification

Use five isolated services: two stage4 candidates and one frozen source for each earlier stage. Every target is reset. Standard-library Python only; no product source imports.

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -u stage-4/verification/model/run_all.py --base-url http://127.0.0.1:18641 --second-url http://127.0.0.1:18642 --stage1-url http://127.0.0.1:18643 --stage2-url http://127.0.0.1:18644 --stage3-url http://127.0.0.1:18645
```

The wrapper runs inherited financial checks, temporal checks, then refund/batch checks and all three import paths, stopping on nonzero exit. Add `--no-shrink` for a fast first diagnosis. Individual drivers accept `--self-test` for pure oracle checks. Optional source arguments on individual drivers do not constitute complete acceptance; use all five URLs for the wrapper.

`model.py` and `temporal_model.py` are pure state/operation functions. Server-owned IDs/event times enter as nondeterministic inputs; amounts, caps, histories, visibility, revision selection and resulting balances are model-derived. No clocks or network occur inside models. Same-instant affordability aggregates all movements; statement ties use plain string IDs. Refunds add ordinary reverse-direction payments; batch affordability applies proposed deltas together before historical checks.

Drivers compare every wallet and visible payment/request/authorization collection in the inherited suite, and wallets, original activity receipts, histories and statements in temporal/refund phases. Seeded closed history not supplied by fixtures is not invented. Current available, historical available, correction/refund caps, terminal request/hold state, immutable receipts and frozen snapshots are checked.

Sequential generated failures are deletion-reduced, bounded to60 temporal/stage4 attempts (80 inherited). Reproductions contain synthetic operations only in fresh `/tmp` directories. Run the named driver with `--base-url URL --replay FILE`. Procedural lifecycle/import failures report a contract label and are reproducible through the named function. Exports/tokens remain in memory, never printed.

Maximum-balance fixtures stay within S3-6 per-entry bounds. Fresh reads allow optional response fields; cached idempotent bodies and imported snapshots must remain exactly equal to their original JSON.

Independent gatekeeper owns concurrent refund-cap and overlapping-correction races, import corruption attacks, transient internal invariants and UI/visual regression. No modeler pass is an independent acceptance verdict.

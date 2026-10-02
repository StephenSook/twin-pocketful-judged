# Stage 3 model verification

All targets are reset. Use isolated containers at exact candidate revisions. Standard-library Python only; no product source imports.

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -u stage-3/verification/model/run_all.py --base-url http://127.0.0.1:18431 --second-url http://127.0.0.1:18432 --stage1-url http://127.0.0.1:18434 --stage2-url http://127.0.0.1:18433
```

The first two targets run stage3; the legacy URLs run frozen stage1 and stage2 services. The wrapper first runs inherited model checks, then temporal checks, and stops on any nonzero exit. Add `--no-shrink` for a fast initial diagnosis. Run `driver.py --self-test` and `temporal_driver.py --self-test` for product-independent oracle checks.

`temporal_model.py` is a pure state/operation transition oracle. Server-owned IDs and event timestamps enter as nondeterministic operation inputs; monetary amounts, revisions, parties, selection, deltas and resulting balances are independently computed. Logical time never comes from a clock inside the model. Revision selection uses recorded time; balance/statement ordering uses effective time. Holds use event-time knowledge and predictable expiry. Same-instant affordability aggregates all movements before checking total/available.

Sequential correction failures are deletion-reduced (at most60 runs), saving only synthetic operations in a fresh `/tmp/pocketful-temporal-*` directory. Reproduce with `temporal_driver.py --base-url URL --replay FILE`. Authentication, import, snapshot and lifecycle scenarios outside that generated sequence report `TEMPORAL CONTRACT FAIL` and can be called individually from their named functions. Exports and tokens stay in memory and are never logged.

The inherited maximum-balance fixture is adapted for stage3 to avoid an inferred historical opening greater than2^53. Earlier-stage frozen verification is untouched.

Limits: the HTTP driver does not verify browser/visual behavior, cryptographic storage, transient internals or full concurrent linearizability. Gatekeeper independently handles correction races, frozen snapshots under writes and UI regression. Optional individual-driver URLs produce explicit NOT_RUN fields; complete acceptance requires the wrapper with all four URLs.

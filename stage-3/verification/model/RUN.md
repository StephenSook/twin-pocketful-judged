# Independent stage 2 model checks

From the result repository, with an isolated running service:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 stage-2/verification/model/driver.py --base-url http://127.0.0.1:8080
```

The command resets and replaces service state. It uses Python's standard library only,
imports no product source, and exits nonzero for any mismatch, transport error or timeout.
Use `--second-url http://127.0.0.1:8081` to additionally verify export portability into a
separate fresh process. Without it, import replacement is tested in the same process.

`model.py` is a pure transition function. `driver.py` exercises a fixed contract corpus,
100 seeded random operations, every observable user's balances/requests/feed after each
operation, export/import and replay preservation, a 50-request identical-key race, and
authentication/reset checks. A response is compared on required fields; successful
replays are compared as complete JSON values. No response field order or ID spelling is
assumed. Unspecified same-second list ordering is tolerated.

On a differential failure, deletion shrinking preserves the mismatch category and emits
an operation-only JSON file in a fresh `/tmp/pocketful-model-*` directory. Exports, session
tokens and passwords are never written to these artifacts. Shrinking is bounded to 80
attempts; the result is not claimed globally minimal if that budget is reached. Run the
reported reproduction with:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 stage-2/verification/model/driver.py --base-url http://127.0.0.1:8080 --replay /tmp/pocketful-model-EXAMPLE/reproduction.json
```

Use `--seed NUMBER --steps NUMBER` for another random run, `--no-shrink` for a fast first
failure, or `--self-test` for a product-independent model smoke test. The self-test is not
product acceptance evidence. Authentication/persistence/concurrency failures outside the
operation sequence report `CONTRACT FAIL` and are reproducible by rerunning the command;
automatic shrinking applies to sequential differential failures only.

## Limits

No product source is read. Password hashing, transient internal invariants, deployment
artifact completeness, and absence of unintended outbound dependencies need independent
gatekeeper/auditor checks. The single concurrency test checks same-key payments; independent
gatekeeper races must cover requests and other write paths. Request list ordering is checked
to second resolution conservatively; pagination checks compare count and has_more, while
unpaginated collections compare every record. No live pass is implied by coverage labels.

## Stage 2 extension

Use three isolated services: two stage2 targets and one frozen stage1 source. All are reset by the driver.

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -u stage-2/verification/model/driver.py --base-url http://127.0.0.1:18321 --second-url http://127.0.0.1:18322 --stage1-url http://127.0.0.1:18323 --steps 100
```

`--stage1-url` enables actual cross-version HTTP export/import, original bearer tokens, pending requests and exact historical receipt replay. Without it the final summary explicitly says migration=NOT_RUN. `--second-url` tests portable same-version import; without it import is within the original process. Neither option claims browser migration coverage.

The pure model takes logical time in an operation's `now` field. Time advancement may expire open holds even on a rejected operation. Generated authorizations use symbolic receipt timestamps; the driver binds them and checks TTL arithmetic. The live expiry check waits just past a three-second deadline, then verifies partially captured history, released remainder and replay. Seeded closed histories with omitted capture fields are not invented by the oracle.

Deterministic plus random authorization operations cover reservation, final/nonfinal capture, void, available-based spending, party filtering and replay. Every operation compares all four wallets and their visible payment/request/authorization collections. The inherited 50-flight payment race does not establish capture/reservation concurrency correctness; independent gatekeeper histories are required. Browser behavior and visual/motion rules are planned in `../browser-plan.md`, not executed by this HTTP driver.

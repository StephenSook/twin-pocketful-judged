# Twin: the builder never grades its own work

Six seats on three model families built all four Pocketful stages in BAND from one dispatch, with no human message after it.

## Measured run

- Stages reached: 4 of 4
- Time from dispatch: 3h 21m
- Human messages after dispatch: 0
- Gatekeeper verdicts: 12 REJECT and 4 ACCEPT
- Rejections that ended with a newer writer revision the gatekeeper accepted: 12 of 12
- Rejections with a same-stage writer commit after the REJECT itself: 9 of 12
- Commits made by seats: 117 of 117
- Handoffs between seats: 331
- BAND messages retried or undelivered: 0
- Room messages: 5,828 of 10,000
- Sealed holdout the band never saw: 73/73 attacks passed, digest `379f28f6c49b9b99` committed before the dispatch

## Independent checks

The builder and surface write product code. The modeler builds a separate executable reading of the requirements without reading the product. The gatekeeper compares both and is the only seat that accepts a stage. The auditor supplies a third model family's reading.

- Genericity: Tablekeeper comparison was not run.
- Single-agent baseline: Solo comparison was not run.

## Evidence

- `room.json`: unchanged BAND export
- `FACTORY.md`: generated run report
- `JUDGE-GUIDE.md`: short route through exact room messages and commits
- `evidence/floor.json`: derived replay data
- `evidence/claim-evidence.json`: verbatim citations for the central factory claims
- `floor/`: browser replay generated from the room export and Git history

## Reproduce

```sh
python3 tools/check_room.py room.json --expected-accepts 4
```
```sh
python3 tools/check_claim_evidence.py room.json evidence/claim-evidence.json
```
```sh
python3 -m harness run --track pocketful --repo . --all --mode isolated
```

## Limits

- Pocketful keeps state in memory, as the track allows, so a restart clears it; the live demo reseeds its accounts.
- Concurrency and history checks are sampled, not proofs.
- Two untracked auditor placeholder files stayed in the build machine's working tree and are not part of this repository.

Factory source: https://github.com/StephenSook/twin-dark-factory

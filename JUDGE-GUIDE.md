# Judge guide: the run in three minutes

Every stop below is a real room message or commit. Paste the command to see it yourself from a fresh clone of this repository.

**0:00 What it is.** Six seats on three model families built all four Pocketful stages in BAND from one dispatch, with no human message after it. Read the seat table at the top of `FACTORY.md`, then the mandates in `mandates/`.

**0:30 A bad result the factory caught.** At 22m the gatekeeper rejected revision `2299fe8`: "expected reset with balance2^53 to return204 and signup İ@example.test to derive i_; observed422 validation_failed and derived _."
```
jq '.messages[] | select(.id=="5a0d74b8-b5b0-4348-999d-40ffbbf13bf5") | .content' room.json
```
builder followed with a same-stage commit 0m later in `145a95f` ("stage-1: balances valid up to and including 2^53, checked in BigInt (§4, ledger R1-041, coordinator ruling)"):
```
git show --stat 145a95f
```
The run had 12 rejections; every one was followed by a same-stage writer commit.

**1:15 Every stage accepted by a different model family than the one that wrote it.**

| Stage | Accepted at | Revision | Room message |
|---|---|---|---|
| 1 | 1h 03m | `d1ebec2` | `1ede5df6-aee8-4471-9a29-c6e7d21dd715` |
| 2 | 1h 49m | `8038718` | `c4499c2f-ebce-4b63-89ba-e3a9c2620cb7` |
| 3 | 2h 52m | `b67e03c` | `679c6f4b-61ac-4724-a9e6-bf0ba38eb0f4` |
| 4 | 3h 19m | `a288cc4` | `f7d76376-a407-42bb-a7ba-99aa2a615b35` |

**1:45 Hands off.** One dispatch, then 0 human messages. room.json is the unchanged BAND export (sha256 `1d184d0574fccfada5561ec2fd8d89ed91ebc93a94b8e673bef37d00e8302eb8`):
```
python tools/check_room.py room.json
```
**2:15 The stage it reached.** The organizers' checker, isolated mode, every folder:
```
python -m harness run --track pocketful --repo . --all --mode isolated
```
**2:40 Evidence the band never saw.** The sealed holdout digest was committed before dispatch (`379f28f6c49b9b99`); after the event the suite is published and anyone can run `python tools/seal_holdout.py verify <suite folder> <digest>`.

The coordinator's final report: `18094c39-884d-472d-9b46-c18003280f66`.

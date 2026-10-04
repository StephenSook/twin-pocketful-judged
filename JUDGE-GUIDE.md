# Judge guide: the run in three minutes

Every stop below is a real room message or commit. Paste the command to see it yourself from a fresh clone of this repository.

**0:00 What it is.** Six seats on three model families built all four Pocketful stages in BAND from one dispatch, with no human message after it. Read the seat table at the top of `FACTORY.md`, then the mandates in `mandates/`.

**Try it first, if you like.** Open https://twin-pocketful-judged-demo.onrender.com/ and log in as `ada@demo.example`, `bob@demo.example`, `cleo@demo.example`, `dev@demo.example` with the password `pocketful demo` (the demo reseeds every hour; the first visit after an idle spell can take about a minute while free hosting starts). Signing up with any email also works.

**0:30 A bad result the factory caught.** At 2h 09m the gatekeeper rejected revision `8548455`: "expected historical balance 9007199254740992, observed 9007199254740991 after a valid correction."
```
jq '.messages[] | select(.id=="837dd787-aef2-470d-aa36-19807164c107") | .content' room.json
```
builder followed with a same-stage commit 1 minute later in `fce49ac` ("stage-3: exact BigInt accumulation for historical balances, statements, openings and the overdraft sweep (R2; REJECT 8548455 history_exact reproduction)"):
```
git show --stat fce49ac
```
The run had 12 rejections; every one ended with a newer writer revision the gatekeeper accepted, and 9 had a same-stage writer commit after the REJECT itself.

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
**2:15 The stage it reached.** The organizers' checker, isolated mode, every folder. It lives in their kickoff repository, so run it there against a clone of this one:
```
git clone https://github.com/band-ai/dark-factory-wearedevs && cd dark-factory-wearedevs
python3 -m venv .venv && . .venv/bin/activate && python -m pip install -r harness/requirements.txt
python -m harness run --track pocketful --repo <path-to-this-repository> --all --mode isolated
```
**2:40 Evidence the band never saw.** The sealed holdout digest was committed before dispatch (`379f28f6c49b9b99`); after the event the suite is published and anyone can run `python tools/seal_holdout.py verify <suite folder> <digest>`.

**2:50 The interface, every stage-2 state.** The gatekeeper accepted stage 2 (`8038718`, at 1h 49m) with 82 screenshots committed beside the verdict: the same 41 views at 375 px and at 1440 px, covering the empty, loading, filled, refused, held and uncertain states of login, sign-up, home, requests, split and authorizations. 14 minutes earlier it rejected `26581d1` because the phone illustration covered the sign-up heading at 1440 px (`stage-2/verification/gatekeeper/evidence/26581d1-signup-overlap.png`). Browse them in `stage-2/verification/gatekeeper/evidence/8038718/`.

**Try it.** https://twin-pocketful-judged-demo.onrender.com/ (demo logins in `deploy/README.md`).

The coordinator's final report: `18094c39-884d-472d-9b46-c18003280f66`.

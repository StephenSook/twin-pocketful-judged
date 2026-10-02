"""Write JUDGE-GUIDE.md: a three-minute tour of the run, every stop a real room message or commit.

  python judge_guide.py <floor.json> <facts.json> > JUDGE-GUIDE.md

floor.json comes from floor_data.py; facts.json holds the live URL, the room.json sha256 printed by
check_room.py and the sealed holdout digest. Every id below is copied from those files, and every
stop has a command that shows it from a fresh clone.
"""
import json
import re
import sys


def mmss(s):
    s = int(round(s))
    h, m = divmod(s // 60, 60)
    return f"{h}h {m:02d}m" if h else f"{m}m"


def holdout_applies(facts, track):
    expected = track == "pocketful"
    if "holdout_applicable" in facts:
        value = facts["holdout_applicable"]
        if type(value) is not bool:
            sys.exit("holdout_applicable must be boolean")
        if value != expected:
            sys.exit("holdout_applicable must agree with the run track")
    return expected


def validate_holdout(facts):
    digest = facts.get("holdout_digest")
    score = facts.get("holdout_score")
    if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
        sys.exit("holdout_digest must be 64 lowercase hexadecimal characters")
    match = re.fullmatch(r"([0-9]+)/([0-9]+)", score) if isinstance(score, str) else None
    if match is None:
        sys.exit("holdout_score must use passed/total form")
    passed, total = map(int, match.groups())
    if total == 0 or passed > total:
        sys.exit("holdout_score must satisfy 0 <= passed <= total and total > 0")
    return digest


def followup_commit(commits, revision):
    matches = [index for index, commit in enumerate(commits) if commit["sha"].startswith(revision)]
    if len(matches) != 1:
        return None
    index = matches[0]
    rejected_stages = set(commits[index]["stages"])
    return next(
        (candidate for candidate in commits[index + 1:]
         if candidate["by_seat"]
         and candidate["author"] in ("builder", "surface")
         and rejected_stages.intersection(candidate["stages"])),
        None,
    )


def main():
    floor = json.load(open(sys.argv[1]))
    facts = json.load(open(sys.argv[2]))
    track = facts.get("track", "pocketful")
    if not re.fullmatch(r"[a-z0-9_-]+", track):
        sys.exit("facts track must contain only lowercase letters, digits, underscores or hyphens")
    coordinator = facts.get("coordinator_handle", "coordinator")
    if not re.fullmatch(r"[A-Za-z0-9_-]+", coordinator):
        sys.exit("facts coordinator_handle contains unsupported characters")
    ev, commits, T = floor["events"], floor["commits"], floor["totals"]
    rejects = [(e, v["rev"]) for e in ev for v in e["verdicts"] if v["verdict"] == "REJECT"]
    seen, accepts = set(), []
    for e in ev:
        for v in e["verdicts"]:
            if v["verdict"] == "ACCEPT" and v["rev"] not in seen:
                seen.add(v["rev"])
                accepts.append((e, v["rev"]))
    final = next((e for e in reversed(ev) if e["from"] == coordinator and "FINAL REPORT" in e["preview"]), None)
    show = "jq '.messages[] | select(.id==\"{}\") | .content' room.json"
    out = []
    w = out.append
    w("# Judge guide: the run in three minutes\n")
    w("Every stop below is a real room message or commit. Paste the command to see it yourself from a "
      "fresh clone of this repository.\n")
    w(f"**0:00 What it is.** {facts.get('one_line', 'Twin: six agents, three model families; the builder never grades its own work.')} "
      "Read the seat table at the top of `FACTORY.md`, then the mandates in `mandates/`.\n")
    if rejects:
        e, rev = rejects[0]
        text = re.sub(r"^(\s*@\S+\s*)+", "", e["preview"])
        text = re.sub(r"^`?REJECT`?\s*`?[0-9a-f]{7,40}`?:?\s*", "", text)
        text = re.split(r"\s+Reproduce\b", text)[0][:200]
        fix = followup_commit(commits, rev)
        w(f"**0:30 A bad result the factory caught.** At {mmss(e['t'])} the gatekeeper rejected revision "
          f"`{rev}`: \"{text.strip()}\"")
        w(f"```\n{show.format(e['id'])}\n```")
        if fix:
            w(f"{fix['author']} followed with a same-stage commit "
              f"{mmss(max(0, fix['t'] - e['t']))} later in `{fix['sha'][:7]}` "
              f"(\"{fix['subject']}\"):\n```\ngit show --stat {fix['sha'][:7]}\n```")
        followed = T["rejects_followed_by_seat_commit"]
        if followed == T["rejects"]:
            w(f"The run had {T['rejects']} rejections; every one was followed by a same-stage writer commit.\n")
        else:
            w(f"The run had {T['rejects']} rejections; {followed} had a later same-stage writer commit.\n")
    w("**1:15 Every stage accepted by a different model family than the one that wrote it.**\n")
    w("| Stage | Accepted at | Revision | Room message |\n|---|---|---|---|")
    for i, (e, rev) in enumerate(accepts, 1):
        w(f"| {i} | {mmss(e['t'])} | `{rev}` | `{e['id']}` |")
    w("")
    development = bool(facts.get("development_run")) or T["human_messages_after_dispatch"] > 0
    if development:
        autonomy = (f"**1:45 Development autonomy.** One dispatch, then "
                    f"{T['human_messages_after_dispatch']} human recovery messages.")
    else:
        autonomy = f"**1:45 Hands off.** One dispatch, then {T['human_messages_after_dispatch']} human messages."
    w(f"{autonomy} room.json is the unchanged BAND export "
      f"(sha256 `{facts.get('room_sha256', 'see check_room.py')}`):")
    w("```\npython tools/check_room.py room.json\n```")
    w(f"**2:15 The stage it reached.** The organizers' checker, isolated mode, every folder:\n"
      f"```\npython -m harness run --track {track} --repo . --all --mode isolated\n```")
    holdout_applicable = holdout_applies(facts, track)
    if holdout_applicable:
        holdout_digest = validate_holdout(facts)
        w(f"**2:40 Evidence the band never saw.** The sealed holdout digest was committed before dispatch "
          f"(`{holdout_digest[:16]}`); after the event the suite is published and anyone can "
          "run `python tools/seal_holdout.py verify <suite folder> <digest>`.")
    else:
        w(f"**2:40 Private attack suite.** {facts.get('holdout_note', 'No private suite applies to this track.')}")
    if facts.get("live_url"):
        w(f"\n**Try it.** {facts['live_url']} (demo logins in `deploy/README.md`).")
    if final:
        w(f"\nThe coordinator's final report: `{final['id']}`.")
    print("\n".join(out))


if __name__ == "__main__":
    main()

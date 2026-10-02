"""Build floor.json for the Factory Floor page from a Band room export and the result repository.

Every number on the page is computed here from files anyone can download, so a reader can rerun
this script and get the same numbers.

  python floor_data.py <room.json> <result-repo or saved git log file> <out.json>
"""
import datetime as dt
import json
import pathlib
import re
import subprocess
import sys

MENTION = re.compile(r"@\[\[([0-9a-f-]{36})\]\]")
# A verdict is a message whose text, after any leading @mentions, starts with the verdict word
# and a revision (the form the mandates require). Quotes of an old verdict later in a message
# are not verdicts.
LEAD = re.compile(r"^(?:\s*@\[\[[0-9a-f-]{36}\]\])*[\s>*_#-]*")
VERDICT = re.compile(r"^`?(ACCEPT|REJECT)`?\s*`?([0-9a-f]{7,40})`?")
LINE_VERDICT = re.compile(r"(?m)^[\s>*_#-]*`?(ACCEPT|REJECT)`?\s+`?([0-9a-f]{7,40})`?")
STAGE_PATH = re.compile(r"^stage-(\d+)/")


def ts(s: str) -> float:
    return dt.datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()


def load_room(path: pathlib.Path):
    raw = json.loads(path.read_text())
    msgs = sorted(raw["messages"], key=lambda m: m["insertedAt"])
    names = {}
    kinds = {}
    for m in msgs:
        kind = m.get("senderType", "Agent")
        name = m.get("senderName") or m["senderId"][:8]
        if kind == "Agent":
            name = name.rsplit("/", 1)[-1]
        names.setdefault(m["senderId"], name)
        kinds.setdefault(m["senderId"], kind)
    return raw, msgs, names, kinds


def delivery(meta) -> tuple[int, int]:
    """(extra attempts, failed recipients) from a message's delivery status."""
    extra = failed = 0
    status = (meta or {}).get("deliveryStatus") or {}
    for rec in status.values():
        attempts = rec.get("attempts") or []
        extra += max(0, len(attempts) - 1)
        if attempts and not any(a.get("completedAt") for a in attempts):
            failed += 1
    return extra, failed


GIT_FORMAT = "%H%x1f%an%x1f%aI%x1f%s"


def git_commits(repo: pathlib.Path):
    """Commits from a repository, or from a saved log file made with:
    git log --reverse --format='%H%x1f%an%x1f%aI%x1f%s' --name-only > commits.log"""
    if repo.is_file():
        out = repo.read_text()
    else:
        out = subprocess.run(["git", "-C", str(repo), "log", "--reverse", f"--format={GIT_FORMAT}", "--name-only"],
                             capture_output=True, text=True, check=True).stdout
    commits, cur = [], None
    for line in out.splitlines():
        if "\x1f" in line:
            h, a, t, s = line.split("\x1f", 3)
            cur = {"sha": h, "author": a, "t": ts(t), "subject": s, "stages": set()}
            commits.append(cur)
        elif line.strip() and cur is not None:
            mm = STAGE_PATH.match(line.strip())
            if mm:
                cur["stages"].add(int(mm.group(1)))
    for c in commits:
        c["stages"] = sorted(c["stages"])
    return commits


def declared_seats(repo: pathlib.Path):
    """Canonical seat names from the mandates committed in a result repository."""
    if repo.is_file():
        out = repo.read_text()
    else:
        out = subprocess.run(
            ["git", "-C", str(repo), "ls-tree", "-r", "--name-only", "HEAD", "--", "mandates"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout
    return {
        pathlib.PurePosixPath(line).stem
        for line in out.splitlines()
        if re.fullmatch(r"mandates/[^/]+\.md", line)
    }


def followup_commit(commits, revision):
    """First later writer commit touching the rejected revision's stage or stages."""
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
    room_path, repo, out = map(pathlib.Path, sys.argv[1:4])
    raw, msgs, names, kinds = load_room(room_path)
    # The console export holds only the messages the page has loaded. A complete export starts
    # with the human's dispatch; anything else is truncated and every number would be wrong.
    first_text = next((m for m in msgs if m["messageType"] == "text"), None)
    if first_text is None or first_text.get("senderType") == "Agent":
        at = first_text["insertedAt"] if first_text else "none"
        sys.exit(f"TRUNCATED EXPORT: the first text message ({at}) is from an agent, not the human "
                 "dispatch. Scroll the room to its first message in the console, then download again.")
    # Room creation and join events can precede the run by minutes. Every elapsed-time claim is
    # measured from the human dispatch, which is the factory's actual start boundary.
    t0 = ts(first_text["insertedAt"])
    seats = {i: n for i, n in names.items() if kinds.get(i) == "Agent"}
    humans = {i: n for i, n in names.items() if kinds.get(i) != "Agent"}

    events, per_seat = [], {n: {"text": 0, "tool_call": 0, "thought": 0, "error": 0} for n in seats.values()}
    retries = failed = 0
    for m in msgs:
        kind = m["messageType"]
        who = names.get(m["senderId"], "?")
        if who in per_seat and kind in per_seat[who]:
            per_seat[who][kind] += 1
        meta = m.get("metadata") if isinstance(m.get("metadata"), dict) else {}
        r, f = delivery(meta)
        retries += r
        failed += f
        if kind not in ("text", "error"):
            continue
        body = m.get("content") or ""
        to = [names.get(x, x[:8]) for x in MENTION.findall(body)]
        # Only the gatekeeper can make an authoritative acceptance decision. Other seats use
        # ACCEPT and REJECT while reporting model checks or relaying a verdict, and counting
        # those messages would invent extra stage boundaries in FACTORY.md and the deck.
        found = []
        if who == "gatekeeper":
            head = VERDICT.match(LEAD.sub("", body, count=1))
            if head:
                found.append(head.groups())
            found += LINE_VERDICT.findall(body)
        verdicts = [{"verdict": v, "rev": rev[:7]} for v, rev in dict.fromkeys(found)]
        events.append({
            "id": m["id"], "t": round(ts(m["insertedAt"]) - t0, 1), "from": who,
            "human": m["senderId"] in humans, "kind": kind, "to": sorted(set(to)),
            "chars": len(body), "verdicts": verdicts,
            "preview": MENTION.sub(lambda x: "@" + names.get(x.group(1), "?"), body)[:220],
        })

    duration_s = ts(msgs[-1]["insertedAt"]) - t0
    repository_commits = git_commits(repo)
    seat_names = declared_seats(repo)
    for c in repository_commits:
        relative_time = c["t"] - t0
        # Git records seconds while BAND records milliseconds. Time is display-only, so clamp
        # it to the observed room window. Stage paths and Git order define run membership.
        c["t"] = round(max(0.0, min(relative_time, duration_s)), 1)
        c["by_seat"] = c["author"] in seat_names
    commits = [c for c in repository_commits if c["stages"]]
    stage_first = {}
    for c in commits:
        for s in c["stages"]:
            if c["by_seat"]:
                stage_first.setdefault(s, c["t"])
    # One decision per (verdict, revision): the same verdict sent to two seats counts once.
    first = {}
    for e in events:
        for v in e["verdicts"]:
            first.setdefault((v["verdict"], v["rev"]), (e["t"], e["id"]))
    accepts = [(t, rev) for (vd, rev), (t, _) in first.items() if vd == "ACCEPT"]
    rejects = [(t, rev, mid) for (vd, rev), (t, mid) in first.items() if vd == "REJECT"]
    # The room provides the reason. Repository order and a shared stage prove a writer changed
    # the rejected work without comparing second-granular Git time to millisecond room time.
    changed = sum(1 for _, revision, _ in rejects if followup_commit(commits, revision))
    handoffs = [e for e in events if not e["human"] and e["to"]]
    human_after_dispatch = [e for e in events if e["human"]][1:]

    floor = {
        "generated_from": {"room": room_path.name, "room_id": (raw.get("room") or {}).get("id"),
                           "exported_at": raw.get("exportedAt"), "messages": len(msgs)},
        "duration_s": round(duration_s, 1),
        "seats": sorted(seats.values()),
        "per_seat": per_seat,
        "totals": {
            "handoffs": len(handoffs),
            "handoff_chars_median": sorted(e["chars"] for e in handoffs)[len(handoffs) // 2] if handoffs else 0,
            "rejects": len(rejects), "rejects_followed_by_seat_commit": changed, "accepts": len(accepts),
            "human_messages_after_dispatch": len(human_after_dispatch),
            "delivery_retries": retries, "delivery_failures": failed,
            "commits": len(commits), "seat_commits": sum(c["by_seat"] for c in commits),
        },
        "stage_first_commit_s": stage_first,
        "events": events,
        "commits": [{k: c[k] for k in ("sha", "author", "t", "subject", "stages", "by_seat")} for c in commits],
    }
    out.write_text(json.dumps(floor, indent=1))
    print(json.dumps(floor["totals"], indent=1))


if __name__ == "__main__":
    main()

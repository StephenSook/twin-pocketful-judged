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
LEAD = re.compile(r"^(?:[ \t]*@\[\[[0-9a-f-]{36}\]\])*[ \t*_#-]*")  # first line only, never a newline
# A backticked word or revision must close its backtick; a bare one must not touch one. The revision
# ends at a non-word character (Unicode aware), never inside other text.
VERDICT = re.compile(r"^(?:`(?P<w1>ACCEPT|REJECT)`|(?P<w2>ACCEPT|REJECT)(?!`))[ \t]+"
                     r"(?:`(?P<r1>[0-9a-f]{7,40})`|(?P<r2>[0-9a-f]{7,40})(?!`))(?!\w)")
STAGE_PATH = re.compile(r"^stage-(\d+)/")


def message_verdicts(who, kind, body, is_agent=True):
    """The verdict a message posts: only a gatekeeper text message whose first words are one.

    Later lines, quotes, code blocks and error events can repeat an old verdict and never count.
    """
    if who != "gatekeeper" or kind != "text" or not is_agent:  # a human named gatekeeper is not the seat
        return []
    head = VERDICT.match(LEAD.sub("", body, count=1))
    if not head:
        return []
    full = head["r1"] or head["r2"]
    return [{"verdict": head["w1"] or head["w2"], "rev": full[:7], "rev_full": full}]


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


SAVED_LOG_MARKER = "floor-log: committer-time"
GIT_FORMAT = "%H%x1f%an%x1f%cI%x1f%s"  # committer time: when the commit was made, not authored


def git_commits(repo: pathlib.Path):
    """Commits from a repository, or from a saved log file made with:
    { echo 'floor-log: committer-time'; git log --reverse --format='%H%x1f%an%x1f%cI%x1f%s' --name-only; } > commits.log
    The marker line proves the log carries committer times; an unmarked log may be an older
    author-time export and is refused. A saved log lists only the history it was made from, so
    ambiguity against commits on other branches is checked only in repository mode."""
    if repo.is_file():
        out = repo.read_text()
        if not out.startswith(SAVED_LOG_MARKER + "\n"):
            sys.exit(f"saved log {repo} lacks the '{SAVED_LOG_MARKER}' first line; regenerate it")
        out = out[len(SAVED_LOG_MARKER) + 1:]
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


# Git records whole seconds (truncated) and BAND records milliseconds. A commit's real time is at or
# after its Git second, so only a Git time at or after the REJECT proves the commit came later.
# A commit in the REJECT's own second can go either way and is not counted.


def rejection_quote(preview):
    """The first sentence of a REJECT message, without its mentions and verdict prefix."""
    text = re.sub(r"^(\s*@\S+\s*)+", "", preview)
    text = re.sub(r"^`?REJECT`?\s*`?[0-9a-f]{7,40}`?:?\s*", "", text)
    text = re.split(r"\s+Reproduce\b", text)[0].strip()
    return re.split(r"(?<=[.!?])\s", text, maxsplit=1)[0]


def require_rejection_records(floor):
    """Fail with a fix, not a KeyError, on a floor.json written before rejection records existed."""
    totals = floor.get("totals") or {}
    needed = ("rejects_resolved_by_accepted_revision", "rejects_followed_by_seat_commit")
    if not isinstance(floor.get("rejections"), list) or any(key not in totals for key in needed):
        sys.exit("floor.json predates rejection records; regenerate it with tools/floor_data.py")


def featured_rejection(floor, facts):
    """The rejection the judge-facing copy shows: facts may name one, else the first with a follow-up."""
    require_rejection_records(floor)
    rejections = floor["rejections"]
    if not rejections:
        return None
    wanted = facts.get("featured_reject_rev")
    if wanted:
        named = [r for r in rejections if r["rev"] == wanted]
        if len(named) != 1:
            sys.exit(f"featured_reject_rev {wanted!r} is not exactly one rejection in floor.json")
        return named[0]
    return next((r for r in rejections if r["followup"]), rejections[0])


def gap_phrase(seconds):
    """Elapsed time in words for copy: never '0m'."""
    seconds = max(0, int(round(seconds)))
    if seconds < 60:
        return "under a minute"
    hours, minutes = divmod(seconds // 60, 60)
    if hours:
        return f"{hours}h {minutes:02d}m"
    return "1 minute" if minutes == 1 else f"{minutes} minutes"


def rejection_record(commits, accepts, reject_t, revision, message_id, between=None, order=None):
    """What happened after one REJECT: the next writer commit in time and the accepted revision.

    `followup` is the earliest writer commit on a rejected stage made after the REJECT message.
    `resolved_by` is the first later ACCEPT of a newer revision whose writer commits since the
    rejected one, taken together, touch every rejected stage. A writer can push the revision that
    passes before the REJECT reaches the room, so the two answers differ and both are reported.
    Times compare unrounded (`t_exact`) values; the record publishes them rounded.
    `between(rejected_index, accepted_index)` returns the commits that the accepted revision contains
    since the rejected one; without it, a linear history is assumed.
    """
    def exact(commit):
        return commit.get("t_exact", commit["t"])

    matches = [index for index, commit in enumerate(commits) if commit["sha"].startswith(revision)]
    record = {"rev": revision[:7], "t": round(reject_t, 1), "message_id": message_id, "stages": [],
              "followup": None, "resolved_by": None, "fixed_before_reject": False}
    if len(matches) != 1:
        return record
    index = matches[0]
    stages = set(commits[index]["stages"])
    record["stages"] = sorted(stages)
    writers = [c for c in commits[index + 1:]
               if c["by_seat"] and c["author"] in ("builder", "surface") and stages.intersection(c["stages"])]
    later = [c for c in writers if exact(c) >= reject_t]
    followup = min(later, key=exact) if later else None  # earliest in time, not log order
    if followup:
        record["followup"] = {"sha": followup["sha"], "t": round(exact(followup), 1),
                              "author": followup["author"], "subject": followup["subject"]}
    order = order or {}
    rank = lambda t, mid: (t, order.get(mid, 0))
    for accept_t, accept_rev, accept_id in sorted(accepts, key=lambda a: rank(a[0], a[2])):
        if rank(accept_t, accept_id) <= rank(reject_t, message_id):
            continue
        hits = [j for j in range(index + 1, len(commits)) if commits[j]["sha"].startswith(accept_rev)]
        accepted = commits[hits[0]] if len(hits) == 1 else None
        if (accepted is None or not stages.intersection(accepted["stages"])
                or not accepted["by_seat"] or accepted["author"] not in ("builder", "surface")):
            continue  # the accepted revision itself must be a writer commit on a rejected stage
        contained = (between(index, hits[0]) if between else commits[index + 1:hits[0] + 1])
        if accepted not in contained:
            continue  # the accepted revision does not descend from the rejected one
        covered = set()
        for c in contained:
            if c["by_seat"] and c["author"] in ("builder", "surface"):
                covered.update(c["stages"])
        if stages.issubset(covered):
            record["resolved_by"] = {"rev": accept_rev[:7], "t": round(accept_t, 1), "message_id": accept_id}
            fixes = [c for c in contained if c["by_seat"] and c["author"] in ("builder", "surface")
                     and stages.intersection(c["stages"])]
            # Provably earlier only when the whole Git second ends before the REJECT.
            record["fixed_before_reject"] = (record["followup"] is None and bool(fixes)
                                             and all(exact(c) + 1 <= reject_t for c in fixes))
            break
    return record


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
    exact_t = {}  # unrounded message times for ordering; events publish them rounded
    full_revs = {}  # each event's revisions exactly as posted, for de-duplication by commit
    order = {}
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
        found = message_verdicts(who, kind, body, m.get("senderType") == "Agent")
        full_revs[m["id"]] = [v.pop("rev_full") for v in found]
        verdicts = found
        # Export order breaks ties between equal timestamps; the offset stays far below 1 ms.
        relative = ts(m["insertedAt"]) - t0
        order[m["id"]] = len(order)  # export order, which breaks ties between equal timestamps
        exact_t[m["id"]] = relative
        events.append({
            "id": m["id"], "t": round(relative, 1), "from": who,
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
        c["t_exact"] = relative_time  # unclamped, for follow-up order and elapsed time only
        c["by_seat"] = c["author"] in seat_names
    commits = [c for c in repository_commits if c["stages"]]
    stage_first = {}
    for c in commits:
        for s in c["stages"]:
            if c["by_seat"]:
                stage_first.setdefault(s, c["t"])
    # One decision per (verdict, commit): the same verdict sent to two seats, or naming one commit by
    # a short and a full hash, counts once; two commits that share a short prefix stay distinct.
    # Ambiguity is judged against every commit object: in a repository, those reachable from any ref,
    # not only HEAD; a saved log can only speak for the history it lists.
    every_sha = {c["sha"] for c in repository_commits}
    if not repo.is_file():
        every_sha |= set(subprocess.run(["git", "-C", str(repo), "rev-list", "--all"],
                                        capture_output=True, text=True, check=True).stdout.split())

    def commit_key(rev):
        hits = [sha for sha in every_sha if sha.startswith(rev)]
        if len(hits) > 1:
            sys.exit(f"verdict revision {rev} names {len(hits)} commits; refusing ambiguous evidence")
        return hits[0] if hits else rev
    first = {}
    for e in events:
        for v, full in zip(e["verdicts"], full_revs.get(e["id"], [])):
            v["commit"] = commit_key(full)  # consumers de-duplicate on this, never on the short rev
            first.setdefault((v["verdict"], v["commit"]), (e["t"], e["id"]))
    accepts = [(t, rev) for (vd, rev), (t, _) in first.items() if vd == "ACCEPT"]
    rejects = [(t, rev, mid) for (vd, rev), (t, mid) in first.items() if vd == "REJECT"]
    accepts_with_ids = [(exact_t[mid], rev, mid) for (vd, rev), (_t, mid) in first.items() if vd == "ACCEPT"]
    def between(rejected_index, accepted_index):
        """A saved log carries no ancestry, so no accepted revision can be proven to contain a fix."""
        return []
    if not repo.is_file():
        def between(rejected_index, accepted_index):
            """Commits the accepted revision contains since the rejected one, by Git ancestry."""
            listed = subprocess.run(
                ["git", "-C", str(repo), "rev-list", "--ancestry-path",
                 f"{commits[rejected_index]['sha']}..{commits[accepted_index]['sha']}"],
                capture_output=True, text=True, check=True).stdout.split()
            return [c for c in commits if c["sha"] in set(listed)]
    rejections = [rejection_record(commits, accepts_with_ids, exact_t[mid], revision, mid, between, order)
                  for _t, revision, mid in sorted(rejects, key=lambda r: (exact_t[r[2]], order[r[2]]))]
    changed = sum(1 for r in rejections if r["followup"])
    resolved = sum(1 for r in rejections if r["resolved_by"])
    fixed_before = sum(1 for r in rejections if r["fixed_before_reject"])
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
            "rejects": len(rejects), "rejects_followed_by_seat_commit": changed,
            "rejects_resolved_by_accepted_revision": resolved,
            "rejects_fixed_before_reject": fixed_before, "accepts": len(accepts),
            "human_messages_after_dispatch": len(human_after_dispatch),
            "delivery_retries": retries, "delivery_failures": failed,
            "commits": len(commits), "seat_commits": sum(c["by_seat"] for c in commits),
        },
        "stage_first_commit_s": stage_first,
        "events": events,
        "rejections": rejections,
        "commits": [{k: c[k] for k in ("sha", "author", "t", "subject", "stages", "by_seat")} for c in commits],
    }
    out.write_text(json.dumps(floor, indent=1))
    print(json.dumps(floor["totals"], indent=1))


if __name__ == "__main__":
    main()

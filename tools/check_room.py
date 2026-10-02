"""Check that room.json is a complete, unedited BAND export of an unattended run.

  python check_room.py room.json [--expected-accepts N] [--allow-human-after-dispatch]

Checks, each printed as PASS or FAIL, exit 1 on any failure:
  - the export has BAND's own top-level keys and per-message fields (a hand-written log does not);
  - every message id is a UUID and ids are unique;
  - messages are in time order with no duplicates;
  - the first text message is the human's dispatch (a truncated export starts mid-run);
  - no human text message follows the dispatch (the run was hands off);
  - every committed seat appears as an active agent when mandates/ is beside room.json;
  - the room stays within the hard cap and every accepted stage has an exact anchored count report;
  - a count at or above the lean threshold is preceded by the coordinator's lean announcement;
  - prints the file's sha256 and message counts for FACTORY.md.
"""
import collections
import argparse
import hashlib
import json
import pathlib
import re
import sys

UUID_TEXT = r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
UUID = re.compile(rf"^{UUID_TEXT}$")
TOP_KEYS = {"exportedAt", "room", "messages"}
MSG_KEYS = {"id", "insertedAt", "messageType", "senderId", "senderType"}
TEXT_KEYS = {"content", "senderName"}
ROOM_LIMIT = 10_000
LEAN_AT = 6_000
ROOM_COUNT = re.compile(
    rf"\bROOM COUNT\s+([0-9][0-9,]*)\s+OF\s+10000\s+AFTER\s+({UUID_TEXT})\b"
)
ACCEPT = re.compile(r"\bACCEPT\s+([0-9a-f]{7,40})\b")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("room_json")
    parser.add_argument("--expected-accepts", type=int, default=4)
    parser.add_argument("--allow-human-after-dispatch", action="store_true")
    parser.add_argument("--allow-incomplete-run", action="store_true")
    args = parser.parse_args()
    if args.expected_accepts < 1:
        parser.error("--expected-accepts must be at least 1")
    path = pathlib.Path(args.room_json)
    allow_human = args.allow_human_after_dispatch
    raw_bytes = path.read_bytes()
    raw = json.loads(raw_bytes)
    msgs = raw.get("messages") or []
    failures = []

    def check(ok, label):
        print(("PASS  " if ok else "FAIL  ") + label)
        if not ok:
            failures.append(label)

    check(TOP_KEYS <= set(raw), f"export has BAND top-level keys {sorted(TOP_KEYS)}")
    check(bool(msgs), f"export holds messages ({len(msgs)})")
    check(len(msgs) <= ROOM_LIMIT,
          f"room message count is within BAND's hard limit ({len(msgs):,}/{ROOM_LIMIT:,})")
    missing = [m.get("id") for m in msgs if not MSG_KEYS <= set(m)]
    check(not missing, f"every message has {sorted(MSG_KEYS)} ({len(missing)} missing)")
    text_missing = [m.get("id") for m in msgs
                    if m.get("messageType") == "text" and not TEXT_KEYS <= set(m)]
    check(not text_missing,
          f"every text message has {sorted(TEXT_KEYS)} ({len(text_missing)} missing)")
    ids = [m.get("id", "") for m in msgs]
    check(all(UUID.match(i or "") for i in ids), "every message id is a UUID")
    check(len(set(ids)) == len(ids), "message ids are unique")
    times = [m.get("insertedAt", "") for m in msgs]
    check(times == sorted(times), "messages are in time order")

    texts = [m for m in msgs if m.get("messageType") == "text"]
    first = texts[0] if texts else None
    check(first is not None and first.get("senderType") != "Agent",
          "first text message is the human dispatch (export not truncated)")
    humans_after = [m for m in texts[1:] if m.get("senderType") != "Agent"]
    label = f"human text messages after the dispatch: {len(humans_after)}"
    if allow_human:
        print("NOTE  " + label + " (allowed for a development run)")
    else:
        check(not humans_after, label)

    mandates = path.parent / "mandates"
    expected_seats = {item.stem for item in mandates.glob("*.md")} if mandates.is_dir() else set()
    if expected_seats:
        active_seats = {
            (m.get("senderName") or "").split("/")[-1]
            for m in msgs
            if m.get("senderType") == "Agent" and m.get("senderName")
        }
        missing_seats = sorted(expected_seats - active_seats)
        unexpected_seats = sorted(active_seats - expected_seats)
        check(not missing_seats and not unexpected_seats,
              f"room activity matches all committed seats "
              f"(missing {missing_seats}, unexpected {unexpected_seats})")
    else:
        print("NOTE  no mandates directory beside room.json; seat activity was not checked")

    # A judged run proves that the coordinator watched the room budget at every accepted stage.
    # Development exports made before this rule can opt out with the same explicit flag that
    # permits their human nudges.
    if allow_human or args.allow_incomplete_run:
        why = "development run" if allow_human else "explicitly incomplete run"
        print(f"NOTE  completion and room-budget reports are not required for this {why}")
    else:
        accepted = []
        seen_revs = set()
        for pos, m in enumerate(msgs):
            if m.get("messageType") != "text" or m.get("senderType") != "Agent":
                continue
            if (m.get("senderName") or "").split("/")[-1] != "gatekeeper":
                continue
            for rev in ACCEPT.findall(m.get("content") or ""):
                same_revision = any(old.startswith(rev) or rev.startswith(old)
                                    for old in seen_revs)
                if not same_revision:
                    seen_revs.add(rev)
                    accepted.append((pos, rev))

        reports = []
        for pos, m in enumerate(msgs):
            if m.get("messageType") != "text" or m.get("senderType") != "Agent":
                continue
            if (m.get("senderName") or "").split("/")[-1] != "coordinator":
                continue
            for count, anchor in ROOM_COUNT.findall(m.get("content") or ""):
                reports.append((pos, int(count.replace(",", "")), anchor))

        anchors = [anchor for _pos, _count, anchor in reports]
        check(len(accepted) == args.expected_accepts,
              f"gatekeeper posted {args.expected_accepts} unique ACCEPT revisions "
              f"({len(accepted)} found)")
        check(len(set(anchors)) == len(anchors),
              "each ROOM COUNT report uses a distinct boundary anchor")

        for i, (accept_pos, rev) in enumerate(accepted):
            next_accept = accepted[i + 1][0] if i + 1 < len(accepted) else len(msgs)
            stage_reports = [(pos, count, anchor) for pos, count, anchor in reports
                             if accept_pos < pos < next_accept]
            check(len(stage_reports) == 1,
                  f"accepted revision {rev[:12]} has one coordinator ROOM COUNT report "
                  f"({len(stage_reports)} found)")
            if len(stage_reports) != 1:
                continue
            report_pos, count, anchor = stage_reports[0]
            count_in_range = 1 <= count <= len(msgs)
            check(count_in_range, f"ROOM COUNT {count:,} indexes the exported room")
            anchor_matches = count_in_range and msgs[count - 1].get("id") == anchor
            check(anchor_matches,
                  f"ROOM COUNT {count:,} anchor is exported message {count:,}")
            check(count_in_range and accept_pos <= count - 1 < report_pos,
                  f"ROOM COUNT {count:,} snapshot follows ACCEPT and precedes its report")
            if count >= LEAN_AT:
                lean = any(
                    n.get("messageType") == "text"
                    and n.get("senderType") == "Agent"
                    and (n.get("senderName") or "").split("/")[-1] == "coordinator"
                    and "LEAN MODE" in (n.get("content") or "")
                    for n in msgs[accept_pos + 1:report_pos]
                )
                check(lean, f"coordinator announced LEAN MODE before boundary report "
                      f"anchored at {count:,}")

        final_reports = [
            m for m in texts
            if m.get("senderType") == "Agent"
            and (m.get("senderName") or "").split("/")[-1] == "coordinator"
            and re.match(r"^\s*FINAL REPORT\b", m.get("content") or "")
        ]
        check(len(final_reports) == 1,
              f"coordinator posted exactly one FINAL REPORT ({len(final_reports)} found)")
        check(bool(final_reports) and texts[-1].get("id") == final_reports[-1].get("id"),
              "coordinator FINAL REPORT is the last text message")

    kinds = collections.Counter(m.get("messageType") for m in msgs)
    print(f"INFO  sha256 {hashlib.sha256(raw_bytes).hexdigest()}")
    print(f"INFO  messages {len(msgs)}, by type {dict(sorted(kinds.items()))}")
    mode = "lean threshold reached" if len(msgs) >= LEAN_AT else "below lean threshold"
    print(f"INFO  room budget {len(msgs):,}/{ROOM_LIMIT:,} messages, "
          f"{ROOM_LIMIT - len(msgs):,} remaining; {mode} ({LEAN_AT:,})")
    if msgs:
        print(f"INFO  span {times[0]} to {times[-1]}")
    if texts:
        last = texts[-1]
        print(f"INFO  last text message from {last.get('senderName') or last.get('senderId')} at "
              f"{last.get('insertedAt')}")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()

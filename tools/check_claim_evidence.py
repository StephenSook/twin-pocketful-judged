#!/usr/bin/env python3
"""Bind the factory's central public claims to verbatim room evidence."""
import argparse
import json
import pathlib
import sys


REQUIRED = {
    "executable_model": {"modeler", "gatekeeper"},
    "differential_comparison": {"modeler", "gatekeeper"},
    "concurrency_probe": {"gatekeeper"},
    "planted_fault": {"gatekeeper"},
    "third_family_audit": {"auditor"},
}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("room_json")
    parser.add_argument("claim_evidence_json")
    args = parser.parse_args()

    room = json.loads(pathlib.Path(args.room_json).read_text())
    evidence = json.loads(pathlib.Path(args.claim_evidence_json).read_text())
    messages = {item.get("id"): item for item in room.get("messages") or []}
    claims = evidence.get("claims") if isinstance(evidence, dict) else None
    failures = []

    def check(ok, label):
        print(("PASS  " if ok else "FAIL  ") + label)
        if not ok:
            failures.append(label)

    check(isinstance(claims, list), "claim evidence has a claims list")
    claims = claims if isinstance(claims, list) else []
    by_id = {}
    for item in claims:
        claim_id = item.get("id") if isinstance(item, dict) else None
        if claim_id in by_id:
            failures.append(f"duplicate claim id: {claim_id}")
        else:
            by_id[claim_id] = item

    check(set(by_id) == set(REQUIRED),
          f"claim evidence covers exactly {sorted(REQUIRED)}")
    cited_messages = []
    for claim_id, allowed_senders in REQUIRED.items():
        item = by_id.get(claim_id)
        if not isinstance(item, dict):
            continue
        message_id = item.get("room_message_id")
        sender = item.get("sender")
        quote = item.get("quote")
        message = messages.get(message_id)
        actual_sender = ((message or {}).get("senderName") or "").split("/")[-1]
        content = (message or {}).get("content") or ""
        check(message is not None, f"{claim_id} cites an exported room message")
        check(sender in allowed_senders and actual_sender == sender,
              f"{claim_id} cites an allowed sender ({sender})")
        check(isinstance(quote, str) and len(quote.strip()) >= 12 and quote in content,
              f"{claim_id} quote is verbatim and at least 12 characters")
        if message_id:
            cited_messages.append(message_id)

    check(len(cited_messages) == len(set(cited_messages)),
          "each central claim cites a distinct room message")
    raise SystemExit(1 if failures else 0)


if __name__ == "__main__":
    main()

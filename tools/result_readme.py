#!/usr/bin/env python3
"""Generate the result repository README from measured floor and facts files."""
import json
import pathlib
import sys


def need(facts, key):
    value = facts.get(key)
    if value in (None, "", [], {}):
        raise SystemExit(f"facts missing {key}")
    return value


def duration(seconds):
    minutes = int(round(seconds / 60))
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h {minutes:02d}m" if hours else f"{minutes}m"


def build(floor, facts):
    totals = floor.get("totals") or {}
    stages = need(facts, "stage_claims")
    if not isinstance(stages, dict):
        raise SystemExit("stage_claims must be an object")
    lines = [
        "# Twin: the builder never grades its own work",
        "",
        str(need(facts, "one_line")),
        "",
    ]
    try_it = []
    if facts.get("live_url"):
        try_it.append(f"- Live app: {facts['live_url']} (free hosting: the first visit after an idle spell "
                      "can take about a minute while it starts)")
    if facts.get("floor_url"):
        try_it.append(f"- Factory Floor, a replay of the whole room: {facts['floor_url']}")
    if facts.get("demo_logins") and facts.get("demo_password"):
        try_it.append("- Demo logins: " + ", ".join(f"`{e}`" for e in facts["demo_logins"])
                      + f", password `{facts['demo_password']}`. The demo reseeds every hour.")
    if try_it:
        lines.extend(["## Try it", "", *try_it, ""])
    if facts.get("holdout_applicable", True):
        holdout_line = (f"- Sealed holdout the band never saw: {need(facts, 'holdout_score')} attacks passed, "
                        f"digest `{str(need(facts, 'holdout_digest'))[:16]}` committed before the dispatch")
    else:
        holdout_line = f"- Sealed holdout: {need(facts, 'holdout_note')}"
    lines.extend([
        "## Measured run",
        "",
        f"- Stages reached: {len(stages)} of 4",
        f"- Time from dispatch: {duration(floor.get('duration_s') or 0)}",
        f"- Human messages after dispatch: {totals.get('human_messages_after_dispatch', 0)}",
        f"- Gatekeeper verdicts: {totals.get('rejects', 0)} REJECT and {totals.get('accepts', 0)} ACCEPT",
        f"- Rejections followed by a same-stage commit from a writer seat: "
        f"{totals.get('rejects_followed_by_seat_commit', 0)} of {totals.get('rejects', 0)}",
        f"- Commits made by seats: {totals.get('seat_commits', 0)} of {totals.get('commits', 0)}",
        f"- Handoffs between seats: {totals.get('handoffs', 0):,}",
        f"- BAND messages retried or undelivered: "
        f"{totals.get('delivery_retries', 0) + totals.get('delivery_failures', 0)}",
        f"- Room messages: {floor.get('generated_from', {}).get('messages', 0):,} of 10,000",
        holdout_line,
        "",
        "## Independent checks",
        "",
        "The builder and surface write product code. The modeler builds a separate executable reading of the requirements without reading the product. The gatekeeper compares both and is the only seat that accepts a stage. The auditor supplies a third model family's reading.",
        "",
        f"- Genericity: {need(facts, 'genericity')}",
        f"- Single-agent baseline: {need(facts, 'baseline')}",
        "",
        "## Evidence",
        "",
        "- `room.json`: unchanged BAND export",
        "- `FACTORY.md`: generated run report",
        "- `JUDGE-GUIDE.md`: short route through exact room messages and commits",
        "- `evidence/floor.json`: derived replay data",
        "- `evidence/claim-evidence.json`: verbatim citations for the central factory claims",
        "- `floor/`: browser replay generated from the room export and Git history",
    ])
    lines.extend(["", "## Reproduce", ""])
    for command in need(facts, "check_commands"):
        lines.extend(["```sh", str(command), "```"])
    lines.extend(["", "## Limits", ""])
    for item in need(facts, "limits"):
        lines.append(f"- {item}")
    lines.extend([
        "",
        "Factory source: https://github.com/StephenSook/twin-dark-factory",
        "",
    ])
    return "\n".join(lines)


def main():
    if len(sys.argv) != 3:
        raise SystemExit("usage: result_readme.py <floor.json> <facts.json>")
    floor = json.loads(pathlib.Path(sys.argv[1]).read_text())
    facts = json.loads(pathlib.Path(sys.argv[2]).read_text())
    print(build(floor, facts), end="")


if __name__ == "__main__":
    main()

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


def case_study_section(factory_md_text):
    """The FACTORY.md case study, copied verbatim so the two pages cannot disagree."""
    heading = "## Case study at a glance"
    if heading not in factory_md_text:
        raise SystemExit("FACTORY.md has no case study section")
    body = factory_md_text.split(heading, 1)[1].split("\n## ", 1)[0].strip("\n")
    return [heading, "", body, ""]


def build(floor, facts, factory_md_text=None):
    needed = ("rejects_resolved_by_accepted_revision", "rejects_followed_by_seat_commit")
    if not isinstance(floor.get("rejections"), list) or any(key not in (floor.get("totals") or {}) for key in needed):
        sys.exit("floor.json predates rejection records; regenerate it with tools/floor_data.py")
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
    if factory_md_text is not None:
        lines.extend(case_study_section(factory_md_text))
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
        f"- Rejections that ended with a newer writer revision the gatekeeper accepted: "
        f"{totals['rejects_resolved_by_accepted_revision']} of {totals.get('rejects', 0)}",
        f"- Rejections with a same-stage writer commit after the REJECT itself: "
        f"{totals['rejects_followed_by_seat_commit']} of {totals.get('rejects', 0)}",
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
    if len(sys.argv) not in (3, 4):
        raise SystemExit("usage: result_readme.py <floor.json> <facts.json> [FACTORY.md]")
    floor = json.loads(pathlib.Path(sys.argv[1]).read_text())
    facts = json.loads(pathlib.Path(sys.argv[2]).read_text())
    factory_md_text = pathlib.Path(sys.argv[3]).read_text() if len(sys.argv) == 4 else None
    print(build(floor, facts, factory_md_text), end="")


if __name__ == "__main__":
    main()

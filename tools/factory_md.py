"""Generate FACTORY.md from the run's own files, so no number is typed by hand.

  python factory_md.py --repo <result repo> --room room.json --floor floor.json \
      --sessions usage-sessions.json --facts facts.json \
      [--template FACTORY.template.md] [--draft] > FACTORY.md

Seats and models come from the committed mandates' Harness and Model lines; mandate fingerprints
from their bytes; verdicts, times and hands-off counts from floor.json (floor_data.py); tokens and
dollars from Band's usage export; stage claims, holdout, genericity, baseline, checks and limits
from facts.json, which is filled from the outputs of verify_result.sh, seal_holdout.py and the
other runs. Without --draft a missing fact is an error, never a blank.
"""
import argparse
import collections
import hashlib
import json
import pathlib
import re
import sys

HERE = pathlib.Path(__file__).resolve().parent
OWNS = {
    "coordinator": ("the plan, handoffs carrying the full requirements, stage copy-forward, stall recovery, final report", "write product code or checks"),
    "modeler": ("the requirement ledger, the executable model, the differential driver", "read product code"),
    "builder": ("the service, storage, concurrency, the container", "accept its own work"),
    "surface": ("the browser interface and its states, screenshots at two widths", "touch service rules"),
    "gatekeeper": ("clean-copy reruns, isolated checks, concurrency histories, planted faults, security, ACCEPT or REJECT", "edit product code"),
    "auditor": ("a third reading of the requirements against the ledger", "read or write product code"),
}
MISSING = []


def need(facts, key, draft):
    if key in facts and facts[key] not in (None, "", [], {}):
        return facts[key]
    MISSING.append(key)
    return "NOT MEASURED YET" if draft else None


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
    return score, digest


def seats_table(repo):
    rows = ["| Seat | Harness | Model | Owns | Never |", "|---|---|---|---|---|"]
    for f in sorted((repo / "mandates").glob("*.md")):
        head = f.read_text().splitlines()[:3]
        harness = next((l.split(":", 1)[1].strip() for l in head if l.startswith("Harness:")), "?")
        model = next((l.split(":", 1)[1].strip() for l in head if l.startswith("Model:")), "?")
        owns, never = OWNS.get(f.stem, ("", ""))
        rows.append(f"| {f.stem} | {harness} | {model} | {owns} | {never} |")
    return "\n".join(rows)


def hashes(repo):
    return "\n".join(f"- `mandates/{f.name}`: `{hashlib.sha256(f.read_bytes()).hexdigest()}`"
                     for f in sorted((repo / "mandates").glob("*.md")))


def verdicts(floor):
    rows = ["| At | Verdict | Revision | What the gatekeeper said | Room message |", "|---|---|---|---|---|"]
    seen = set()
    for e in floor["events"]:
        for v in e["verdicts"]:
            key = (v["verdict"], v.get("commit", v["rev"]))
            if key in seen:
                continue
            seen.add(key)
            text = re.sub(r"^(\s*@\S+\s*)+", "", e["preview"])
            text = re.sub(r"^`?(ACCEPT|REJECT)`?\s*`?[0-9a-f]{7,40}`?:?\s*", "", text)
            text = re.split(r"\s+Reproduce\b", text)[0].replace("|", "/")
            text = re.sub(r"^[\s.:;,]+", "", text)
            if len(text) > 120:
                text = text[:120].rsplit(" ", 1)[0] + " ..."
            rows.append(f"| {mmss(e['t'])} | {v['verdict']} | `{v['rev']}` | {text} | `{e['id'][:8]}` |")
    return "\n".join(rows)


def _floor_tools():
    """floor_data.py ships beside this file and owns the rejection logic."""
    import importlib.util
    path = pathlib.Path(__file__).resolve().with_name("floor_data.py")
    spec = importlib.util.spec_from_file_location("floor_data", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def first_catch(floor, facts=None):
    tools = _floor_tools()
    featured = tools.featured_rejection(floor, facts or {})
    if featured is None:
        return "no rejection in this run."
    e = next(item for item in floor["events"] if item["id"] == featured["message_id"])
    fix = featured["followup"]
    tail = (f" {fix['author']} followed with a same-stage commit {tools.gap_phrase(fix['t'] - e['t'])} later in "
            f"`{fix['sha'][:7]}` (\"{fix['subject']}\").") if fix else ""
    return (f"at {mmss(e['t'])} the gatekeeper rejected `{featured['rev']}`: "
            f"\"{tools.rejection_quote(e['preview'])}\" (room message `{e['id']}`).{tail}")


def catch_stats(T):
    resolved, followed, rejects = (T["rejects_resolved_by_accepted_revision"],
                                   T["rejects_followed_by_seat_commit"], T["rejects"])
    return (f"{rejects} rejections and {T['accepts']} acceptances over {T['handoffs']} handoffs. "
            f"{resolved} of the {rejects} rejections ended with a newer writer revision of the same stage that the "
            f"gatekeeper later accepted; {followed} had a same-stage writer commit after the REJECT itself"
            + (f", and in the other {rejects - followed} the fixes in the accepted revision were committed before the REJECT was posted. "
               if resolved == rejects and 0 < rejects - followed == T.get("rejects_fixed_before_reject") else ". ")
            + f"{T['seat_commits']} of {T['commits']} commits to stage folders were made by seats.")


def costs(sessions_path, room, facts, draft, development):
    rows = collections.defaultdict(lambda: [set(), 0, 0.0])
    for s in json.load(open(sessions_path))["sessions"]:
        att = s.get("attribution") or {}
        if room not in (att.get("chatIds") or [att.get("chatId")]):
            continue
        r = rows[(att.get("peerName") or "unattributed").split("/")[-1]]
        r[0].update(m["model"] for m in s.get("models") or [])
        r[1] += sum(s.get(k) or 0 for k in ("inputTokens", "outputTokens", "cacheCreationTokens", "cacheReadTokens"))
        r[2] += s.get("totalCost") or 0.0
    if not rows and not draft:
        sys.exit("no usage sessions are attributed to this room")
    out = ["| Seat | Model | Tokens | List-price equivalent (USD) |", "|---|---|---|---|"]
    for seat, (models, tok, usd) in sorted(rows.items(), key=lambda kv: -kv[1][2]):
        out.append(f"| {seat} | {', '.join(sorted(models))} | {tok:,} | {usd:,.2f} |")
    tok = sum(v[1] for v in rows.values())
    usd = sum(v[2] for v in rows.values())
    out.append(f"| **total** | | {tok:,} | {usd:,.2f} |")
    if facts.get("cost_note"):
        if not development:
            sys.exit("cost_note is allowed only for a development run")
        out.append("\n" + facts["cost_note"])
    else:
        fl = facts.get("featherless_usd")
        fl_note = facts.get("featherless_note")
        if fl not in (None, ""):
            auditor = f"The auditor ran on Featherless credits, metered: **${fl}** for the whole run."
        elif fl_note not in (None, ""):
            auditor = f"The auditor ran on Featherless outside Band's export. {fl_note}"
        else:
            need(facts, "featherless_usd or featherless_note", draft)
            auditor = "The auditor's Featherless usage is NOT MEASURED YET." if draft else ""
        out.append("\nThe Claude and Codex seats ran on flat-rate subscriptions; the dollars above are Band's "
                   "own list-price estimate from its usage export, not a bill. " + auditor)
    return "\n".join(out)


def mandate_models(repo):
    """(seat, harness, model) from each committed mandate's header lines."""
    out = []
    for f in sorted((repo / "mandates").glob("*.md")):
        head = f.read_text().splitlines()[:3]
        harness = next((l.split(":", 1)[1].strip() for l in head if l.startswith("Harness:")), "?")
        model = next((l.split(":", 1)[1].strip() for l in head if l.startswith("Model:")), "?")
        out.append((f.stem, harness, model))
    return out


def family(model):
    m = model.lower()
    for key, name in (("claude", "Claude"), ("gpt", "GPT"), ("deepseek", "DeepSeek"), ("qwen", "Qwen"), ("glm", "GLM")):
        if key in m:
            return name
    return model


def case_study(repo, track, claims, holdout_line, sessions_path, room, limits, T, featherless_usd=None, green_short=None):
    """The judges' case-study outline, in their order, from the same inputs as the rest of the page."""
    seats = mandate_models(repo)
    families = sorted({family(model) for _, _, model in seats})
    usage = [s for s in json.load(open(sessions_path))["sessions"]
             if room in ((s.get("attribution") or {}).get("chatIds") or [(s.get("attribution") or {}).get("chatId")])]
    usd = sum(s.get("totalCost") or 0.0 for s in usage)
    tok = sum(sum(s.get(k) or 0 for k in ("inputTokens", "outputTokens", "cacheCreationTokens", "cacheReadTokens"))
              for s in usage)
    reached = (", ".join(f"stage {k} {v}" for k, v in claims.items()) if isinstance(claims, dict) else str(claims))
    lines = [
        f"- **Task.** The {track} track: four cumulative stages from one dispatch in a fresh BAND room.",
        f"- **Band.** {len(seats)} seats on {len(families)} model families ({', '.join(families)}): "
        + ", ".join(f"{seat} ({harness})" for seat, harness, _ in seats) + ".",
        "- **Key design decision.** A seat on a different model family writes an executable model of the "
        "written requirements without reading product code, and the gatekeeper accepts a revision only when "
        "product and model agree.",
        f"- **Verified result.** {reached}; {T['rejects']} rejections and {T['accepts']} acceptances over "
        f"{T['handoffs']:,} handoffs." + (f" {holdout_line}" if holdout_line else "")
        + (f" {green_short}" if isinstance(green_short, str) and green_short.strip() else ""),
        f"- **Cost.** BAND attributes {tok:,} tokens and ${usd:,.2f} of list-price equivalent to this room "
        "(an estimate, not a bill)"
        + (f"; the auditor's Featherless calls cost ${featherless_usd:,.2f} in Featherless's own billed-request log"
           if isinstance(featherless_usd, (int, float)) and not isinstance(featherless_usd, bool) else "")
        + "; see Measured cost and time.",
        f"- **Limitation.** {limits[0]}" if limits else "- **Limitation.** NOT MEASURED YET",
    ]
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    for a in ("--repo", "--room", "--floor", "--sessions", "--facts"):
        ap.add_argument(a, required=True)
    ap.add_argument("--template", default=str(HERE.parent / "docs" / "FACTORY.template.md"))
    ap.add_argument("--draft", action="store_true")
    a = ap.parse_args()
    repo, floor, facts = pathlib.Path(a.repo), json.load(open(a.floor)), json.load(open(a.facts))
    _floor_tools().require_rejection_records(floor)
    track = facts.get("track", "pocketful")
    if not re.fullmatch(r"[a-z0-9_-]+", track):
        sys.exit("facts track must contain only lowercase letters, digits, underscores or hyphens")
    room_bytes = pathlib.Path(a.room).read_bytes()
    room_export = json.loads(room_bytes)
    room_messages = room_export.get("messages") or []
    exported_room = room_export.get("room") or {}
    exported_room_id = exported_room.get("id") if isinstance(exported_room, dict) else exported_room
    floor_source = floor.get("generated_from") or {}
    if exported_room_id != floor_source.get("room_id"):
        sys.exit("room export and floor summary name different room ids")
    if len(room_messages) != floor_source.get("messages"):
        sys.exit("room export and floor summary have different message counts")
    room_hash = hashlib.sha256(room_bytes).hexdigest()
    if facts.get("room_sha256") and facts["room_sha256"] != room_hash:
        sys.exit("room export sha256 differs from facts.json")
    T = floor["totals"]
    room = floor["generated_from"]["room_id"]
    development = bool(facts.get("development_run")) or T["human_messages_after_dispatch"] > 0
    accepts, seen = [], set()
    for e in floor["events"]:
        for v in e["verdicts"]:
            if v["verdict"] == "ACCEPT" and v.get("commit", v["rev"]) not in seen:
                seen.add(v.get("commit", v["rev"]))
                accepts.append((e, v["rev"]))
    claims = need(facts, "stage_claims", a.draft)
    generic = need(facts, "genericity", a.draft)
    baseline = need(facts, "baseline", a.draft)
    holdout_applicable = holdout_applies(facts, track)
    if holdout_applicable:
        holdout = need(facts, "holdout_score", a.draft)
        holdout_digest = need(facts, "holdout_digest", a.draft)
        supplied = any(
            key in facts and facts[key] not in (None, "", [], {})
            for key in ("holdout_score", "holdout_digest")
        )
        if not a.draft or supplied:
            holdout, holdout_digest = validate_holdout(facts)
        holdout_result = (
            f"- **Evidence the band never saw.** Sealed holdout digest `{str(holdout_digest)[:16]}` "
            f"committed before dispatch; score after the run: **{holdout}**."
        )
    else:
        holdout_note = need(facts, "holdout_note", a.draft)
        holdout_result = f"- **Private attack suite.** {holdout_note}"
    if development:
        autonomy_result = (
            f"- **Development autonomy.** {T['human_messages_after_dispatch']} human recovery messages "
            f"after the dispatch; room.json sha256 `{room_hash}`."
        )
    else:
        autonomy_result = (
            f"- **Hands off.** {T['human_messages_after_dispatch']} human messages after the dispatch; "
            f"room.json sha256 `{room_hash}`."
        )
    results = [
        f"- **Stage reached.** The organizers' checker in isolated mode on a fresh clone: "
        + (", ".join(f"stage {k} {v}" for k, v in claims.items()) if isinstance(claims, dict) else str(claims)) + ".",
        autonomy_result,
        holdout_result,
        f"- **Generic.** {generic if isinstance(generic, str) else json.dumps(generic)}",
        f"- **One agent against the band.** {baseline if isinstance(baseline, str) else json.dumps(baseline)}",
    ]
    # Optional derived facts (built from the room, git and the deploy receipt, never typed).
    for key, label in (("green_reject", "Refused while the provided checks were green."),
                       ("seat_paths", "Writers and checkers never cross."),
                       ("live_provenance", "The live demo is the graded folder."),
                       ("provided_checks", "Provided checks, every stage folder."),
                       ("standalone", "Runs without the factory."),
                       ("shipped_share", "What the provided checks leave out."),
                       ("ledger_size", "The spec, read twice."),
                       ("auth_security", "Accounts and passwords."),
                       ("ui_states", "Every stage-2 state, at both widths.")):
        if isinstance(facts.get(key), str) and facts[key].strip():
            results.append(f"- **{label}** {facts[key]}")
    limits_list = need(facts, "limits", a.draft) or []
    holdout_line = (f"Sealed holdout: {holdout}." if holdout_applicable else "")
    fill = {
        "{{CASE_STUDY}}": case_study(repo, track, claims, holdout_line, a.sessions, room, limits_list, T,
                                     facts.get("featherless_usd"), facts.get("green_reject_short")),
        "{{SEATS_TABLE}}": seats_table(repo),
        "{{MANDATE_HASHES}}": hashes(repo),
        "{{CATCH_STATS}}": catch_stats(T),
        "{{VERDICT_TABLE}}": verdicts(floor),
        "{{FIRST_CATCH}}": first_catch(floor, facts),
        "{{COST_TABLE}}": costs(a.sessions, room, facts, a.draft, development),
        "{{ROOM_MESSAGE_COUNT}}": f"{len(room_messages):,}",
        "{{STAGE_TIMES}}": "Wall time from dispatch: " + ", ".join(f"stage {i} accepted at {mmss(e['t'])}" for i, (e, _) in enumerate(accepts, 1))
                           + f"; the whole run took {mmss(floor['duration_s'])}.",
        "{{RESULTS}}": "\n".join(results),
        "{{CHECKS}}": "```\n" + "\n".join(need(facts, "check_commands", a.draft) or []) + "\n```",
        "{{LIMITS}}": "\n".join(f"- {x}" for x in (need(facts, "limits", a.draft) or [])),
    }
    text = pathlib.Path(a.template).read_text()
    for k, v in fill.items():
        text = text.replace(k, str(v))
    left = re.findall(r"\{\{[A-Z_]+\}\}", text)
    if left:
        sys.exit(f"unfilled placeholders: {left}")
    if MISSING and not a.draft:
        sys.exit(f"missing facts (run without --draft only when every fact is measured): {sorted(set(MISSING))}")
    if a.draft:
        text = "> DRAFT: generated from development data; facts marked NOT MEASURED YET are pending.\n\n" + text
    sys.stdout.write(text)


if __name__ == "__main__":
    main()

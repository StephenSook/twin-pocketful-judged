#!/usr/bin/env bash
# Verify a finished result repository the way a judge would: from a fresh clone, with the
# organizers' own checker, in isolated mode. Every check prints PASS or FAIL; nothing is skipped.
#
#   verify_result.sh <result repo path or URL> <kickoff checkout> <track> [stages, default 4]
#
# Needs: git, docker, python3 with the kickoff harness requirements, gitleaks on PATH.
# DEV_RUN=1 allows human messages after the dispatch (development runs only; printed loudly).
set -u
SRC=$1 KICKOFF=$(cd "$2" && pwd) TRACK=$3 STAGES=${4:-4}
HERE=$(cd "$(dirname "$0")" && pwd)
PY=${PYTHON:-python3}
fails=0
pass() { echo "PASS  $*"; }
fail() { echo "FAIL  $*"; fails=$((fails + 1)); }

WORK=$(mktemp -d)
git clone -q --no-local "$SRC" "$WORK/repo" || { echo "FAIL  clone $SRC"; exit 1; }
R="$WORK/repo"
echo "INFO  verifying $(git -C "$R" rev-parse HEAD) from a fresh clone in $R"

# 1. Folder layout: every stage folder present, no nested repositories or submodules.
for s in $(seq 1 "$STAGES"); do
  [ -f "$R/stage-$s/Dockerfile" ] && [ -f "$R/stage-$s/RUN.md" ] \
    && pass "stage-$s has Dockerfile and RUN.md" || fail "stage-$s is missing Dockerfile or RUN.md"
done
nested=$(find "$R" -mindepth 2 -name .git | wc -l | tr -d ' ')
[ "$nested" = 0 ] && pass "no nested .git" || fail "$nested nested .git found"
links=$(git -C "$R" ls-files -s | awk '$1 == "160000"' | wc -l | tr -d ' ')
[ "$links" = 0 ] && pass "no submodules or gitlinks" || fail "$links gitlinks tracked"

# 2. Authorship: every commit touching a stage folder is by a seat named in mandates/.
seats=$(cd "$R/mandates" && ls *.md 2>/dev/null | sed 's/\.md$//' | tr '\n' ' ')
[ -n "$seats" ] && pass "seats from mandates/: $seats" || fail "no mandates/*.md"
bad=0 counted=0
while IFS= read -r a; do
  counted=$((counted + 1))
  case " $seats " in *" $a "*) ;; *) bad=$((bad + 1)); echo "      stage commit by non-seat: $a";; esac
done < <(git -C "$R" log --format=%an -- $(for s in $(seq 1 "$STAGES"); do echo "stage-$s"; done))
[ "$counted" -gt 0 ] && [ "$bad" = 0 ] && pass "all $counted stage commits are by seats" \
  || fail "stage commits checked: $counted, by non-seats: $bad"

# 3. The organizers' offline checker.
if (cd "$KICKOFF" && "$PY" -m harness check "$R" --track "$TRACK") > "$WORK/check.log" 2>&1; then
  pass "harness check"
else
  fail "harness check (see $WORK/check.log)"; tail -20 "$WORK/check.log"
fi

# 4. The organizers' isolated run of every folder. The process status and the summary are
# independent evidence. A stale or partial summary must never hide a failed harness process.
isolated_status=0
(cd "$KICKOFF" && "$PY" -m harness run --track "$TRACK" --repo "$R" --all --mode isolated \
  --out "$WORK/run") > "$WORK/run.log" 2>&1 || isolated_status=$?
summary_status=0
"$PY" - "$WORK/run/summary.json" "$STAGES" <<'EOF' || summary_status=$?
import json, sys
try:
    s = json.load(open(sys.argv[1]))
except (OSError, ValueError) as e:
    print(f"FAIL  isolated run produced no summary ({e})"); sys.exit(1)
want = int(sys.argv[2]); folders = s.get("folders") or {}
ok = True
for n in range(1, want + 1):
    f = folders.get(str(n)) or folders.get(n) or {}
    good = f.get("claimed") is True
    ok &= good
    print(("PASS  " if good else "FAIL  ") + f"stage-{n} claims its stage in isolated mode (share {f.get('share')})")
print(f"INFO  isolated run folders reported: {len(folders)} of {want}")
sys.exit(0 if ok and len(folders) >= want else 1)
EOF
if [ "$isolated_status" -ne 0 ]; then
  fail "isolated harness process exited $isolated_status (see $WORK/run.log)"
  tail -20 "$WORK/run.log"
fi
[ "$summary_status" -eq 0 ] || fails=$((fails + 1))

# 5. The room export.
if [ -f "$R/room.json" ]; then
  flag=; [ "${DEV_RUN:-}" = 1 ] && { flag=--allow-human-after-dispatch; echo "NOTE  DEV_RUN=1: development run"; }
  "$PY" "$HERE/check_room.py" "$R/room.json" --expected-accepts "$STAGES" $flag \
    || fails=$((fails + 1))
else
  fail "room.json missing"
fi

# 6. Central public claims point to distinct, verbatim room evidence.
if [ -f "$R/evidence/claim-evidence.json" ] && [ -f "$HERE/check_claim_evidence.py" ]; then
  "$PY" "$HERE/check_claim_evidence.py" "$R/room.json" "$R/evidence/claim-evidence.json" \
    || fails=$((fails + 1))
elif [ "${DEV_RUN:-}" = 1 ]; then
  echo "NOTE  development run has no public-claim evidence manifest"
else
  fail "evidence/claim-evidence.json or tools/check_claim_evidence.py missing"
fi

# 7. Public copy carries no pending value, banned typography or AI-tone word.
if [ -f "$HERE/check_public_copy.py" ] && [ -f "$R/evidence/floor.json" ]; then
  "$PY" "$HERE/check_public_copy.py" --quotes "$R/room.json" "$R/evidence/floor.json" \
    "$R/README.md" "$R/FACTORY.md" "$R/JUDGE-GUIDE.md" \
    "$R/floor/index.html" "$R/deploy/README.md" \
    || fails=$((fails + 1))
elif [ "${DEV_RUN:-}" = 1 ]; then
  echo "NOTE  development run has no packaged public copy"
else
  fail "tools/check_public_copy.py or evidence/floor.json missing"
fi

# 8. No secrets anywhere in history.
if command -v gitleaks >/dev/null; then
  gitleaks git "$R" --no-banner --redact > "$WORK/leaks.log" 2>&1 \
    && pass "gitleaks: full history clean" || { fail "gitleaks found leaks (see $WORK/leaks.log)"; tail -5 "$WORK/leaks.log"; }
else
  fail "gitleaks not installed, secret scan not run"
fi

echo "INFO  evidence kept in $WORK"
[ "$fails" = 0 ] && { echo "RESULT PASS"; exit 0; } || { echo "RESULT FAIL ($fails)"; exit 1; }

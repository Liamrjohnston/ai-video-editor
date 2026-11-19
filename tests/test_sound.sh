#!/usr/bin/env bash
# End-to-end test of the sound-effects toolkit with tiny synthetic media.
# fit -> build_mix -> mux -> audit_mix must pass; broken plans must be refused; bank verify must pass.
# Needs ffmpeg and python3. Creates a venv (numpy + scipy) at .venv in this folder if missing.
set -euo pipefail
export PYTHONDONTWRITEBYTECODE=1

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCRIPTS="$REPO/.claude/skills/sound-effects/scripts"
VENV="${AVE_VENV:-$REPO/.venv}"
WORK="${AVE_TEST_WORK:-${TMPDIR:-/tmp}/ave-sound-test}"
mkdir -p "$WORK"

if [ ! -x "$VENV/bin/python" ]; then
  python3 -m venv "$VENV"
fi
if ! "$VENV/bin/python" -c "import numpy, scipy" 2>/dev/null; then
  "$VENV/bin/python" -m pip install --quiet numpy scipy
fi
PY="$VENV/bin/python"

step() { printf '\n== %s\n' "$*"; }
expect_fail() {   # run a command that must exit non-zero
  local label="$1"; shift
  if "$@" >"$WORK/expect_fail.log" 2>&1; then
    echo "FAIL: '$label' should have been refused but succeeded"; tail -15 "$WORK/expect_fail.log"; exit 1
  fi
  echo "ok: '$label' was refused"; tail -4 "$WORK/expect_fail.log" | sed 's/^/    /'
}

step "bank verify and list"
"$PY" "$SCRIPTS/bank.py" verify
"$PY" "$SCRIPTS/bank.py" list --type riser

step "make a 6 s synthetic voice and a 6 s 1080x1920 picture (30 fps)"
ffmpeg -y -v error -f lavfi -i "aevalsrc=exprs='(0.10*sin(2*PI*180*t)+0.04*sin(2*PI*540*t))*(0.55+0.45*sin(2*PI*3*t))':s=48000:d=6" -ac 2 "$WORK/voice.wav"
# Picture: a grey frame; a box appears at each cue frame; a full-frame cut at frame 60.
BOX() { echo "drawbox=x=$1:y=$2:w=160:h=160:color=white:t=fill:enable='gte(t,$3)'"; }
VF="$(BOX 60 300 0.9833),$(BOX 260 300 1.1833),$(BOX 460 300 1.3833),$(BOX 660 300 1.5833),drawbox=x=0:y=0:w=iw:h=ih:color=0x203060:t=fill:enable='gte(t,1.9833)',$(BOX 400 900 3.3167),$(BOX 200 1300 4.3167),$(BOX 700 1500 4.9833)"
ffmpeg -y -v error -f lavfi -i "color=c=gray:s=1080x1920:r=30:d=6" -vf "$VF,format=yuv420p" -c:v libx264 -preset ultrafast -crf 23 -an "$WORK/picture.mp4"

step "write a plan"
cat > "$WORK/plan.json" <<'JSON'
{
  "fps": 30,
  "totalFrames": 180,
  "riserPolicy": {"onlyCue": "RISER", "why": "One build from the opening into the main point, on the cut."},
  "graphicsRegion": [0.0, 1.0],
  "cues": [
    {"id": "BLIPS", "what": "Four items appear one after another", "frame": 30, "hits": [30, 36, 42, 48], "count": 4, "motionEnd": 52,
     "fit": {"list": [84, [104, 108]], "why": "A tiny bright blip for each item that appears."}},
    {"id": "RISER", "what": "Cut from the opening into the main point", "frame": 60, "hits": [60], "count": 1, "align": "peak", "motionEnd": 70,
     "fit": {"list": [44], "why": "The one build into the cut."}},
    {"id": "ZOOM", "what": "Camera pushes in on the card", "frame": 90, "motionStart": 90, "hits": [100], "count": 1, "align": "peak", "motionEnd": 118,
     "fit": {"list": [24, [23, 26]], "why": "Soft air sized to a medium push, peaking on the fastest frame."}},
    {"id": "CLICK", "what": "Cursor clicks the button", "frame": 130, "hits": [130], "count": 1, "motionEnd": 134,
     "fit": {"list": [14, 12], "why": "A dry mouse click."}},
    {"id": "WINDOW", "what": "A window pops open", "frame": 150, "hits": [150], "count": 1, "motionEnd": 156,
     "fit": {"list": [16, 15], "why": "A small round pop for something opening."}}
  ]
}
JSON

step "fit"
"$PY" "$SCRIPTS/fit.py" "$WORK/plan.json" --out "$WORK/plan.fit.json"

step "build_mix"
"$PY" "$SCRIPTS/build_mix.py" "$WORK/plan.fit.json" --voice "$WORK/voice.wav" --out "$WORK/mix"
test -s "$WORK/mix/mix.wav"
test -s "$WORK/mix/sound-ledger.json"

step "mux"
"$PY" "$SCRIPTS/mux.py" "$WORK/picture.mp4" "$WORK/mix/mix.wav" "$WORK/final.mp4"

step "audit_mix (must pass)"
"$PY" "$SCRIPTS/audit_mix.py" "$WORK/final.mp4" --plan "$WORK/plan.fit.json" --ledger "$WORK/mix/sound-ledger.json" --out "$WORK/audit.json"

step "levels and cue sheet"
"$PY" "$SCRIPTS/levels.py" "$WORK/mix/sound-ledger.json" --out "$WORK/levels.json"
"$PY" "$SCRIPTS/cue_sheet.py" "$WORK/mix/sound-ledger.json" "$WORK/cues.csv"
test "$(wc -l < "$WORK/cues.csv")" -eq 6

step "motion_gaps: a sliding graphic with and without its cue"
ffmpeg -y -v error -f lavfi -i "color=c=black:s=270x480:r=30:d=6" -f lavfi -i "color=c=white:s=60x60:r=30:d=6" \
  -filter_complex "[0:v][1:v]overlay=x='20+180*clip((t-3.2)/0.5,0,1)':y=200,format=yuv420p" -c:v libx264 -preset ultrafast -an "$WORK/gfx.mp4"
"$PY" "$SCRIPTS/motion_gaps.py" "$WORK/gfx.mp4" --plan "$WORK/plan.fit.json" --out "$WORK/gaps.json"
"$PY" - "$WORK" <<'PYEOF'
import json, sys
w = sys.argv[1]
p = json.load(open(f"{w}/plan.fit.json"))
p["cues"] = [c for c in p["cues"] if c["id"] != "ZOOM"]
json.dump(p, open(f"{w}/plan.nozoom.json", "w"))
PYEOF
expect_fail "motion with no cue" "$PY" "$SCRIPTS/motion_gaps.py" "$WORK/gfx.mp4" --plan "$WORK/plan.nozoom.json" --out "$WORK/gaps2.json"

step "broken plans must be refused"
mkplan() {   # mkplan <name> <python statement editing p>
  "$PY" - "$WORK" "$1" "$2" <<'PYEOF'
import json, sys
w, name, code = sys.argv[1:4]
p = json.load(open(f"{w}/plan.fit.json"))
cue = {c["id"]: c for c in p["cues"]}
exec(code)
json.dump(p, open(f"{w}/{name}.json", "w"))
PYEOF
}
mkplan wrongcount 'cue["BLIPS"]["count"] = 5'
expect_fail "wrong hit count (5 items, 4 hits)" "$PY" "$SCRIPTS/build_mix.py" "$WORK/wrongcount.json" --voice "$WORK/voice.wav" --out "$WORK/mix-wrongcount"
test ! -e "$WORK/mix-wrongcount/mix.wav"

mkplan nonbank 'cue["CLICK"].pop("fit", None); cue["CLICK"]["sound"] = None; cue["CLICK"]["soundFile"] = w + "/voice.wav"' 
expect_fail "a sound file that is not in the bank" "$PY" "$SCRIPTS/build_mix.py" "$WORK/nonbank.json" --voice "$WORK/voice.wav" --out "$WORK/mix-nonbank"
test ! -e "$WORK/mix-nonbank/mix.wav"

mkplan badriser 'cue["CLICK"]["sound"] = 44; cue["CLICK"].pop("fit", None)'
expect_fail "a riser sound on a movement cue" "$PY" "$SCRIPTS/build_mix.py" "$WORK/badriser.json" --voice "$WORK/voice.wav" --out "$WORK/mix-badriser"

mkplan cascade 'cue["BLIPS"]["hits"] = [30, 31, 32, 33]'
expect_fail "a cascade faster than 12 a second with a count of 4" "$PY" "$SCRIPTS/build_mix.py" "$WORK/cascade.json" --voice "$WORK/voice.wav" --out "$WORK/mix-cascade"

mkplan early 'cue["WINDOW"]["hits"] = [150]; cue["WINDOW"]["align"] = "peak"; cue["WINDOW"]["motionStart"] = 150; cue["WINDOW"]["sound"] = 23; cue["WINDOW"].pop("fit", None); cue["WINDOW"]["motionEnd"] = 170'
expect_fail "a swoosh audible long before its movement" "$PY" "$SCRIPTS/build_mix.py" "$WORK/early.json" --voice "$WORK/voice.wav" --out "$WORK/mix-early"

step "audit must fail when the plan no longer matches what was mixed"
mkplan driftplan 'cue["BLIPS"]["hits"] = [30, 36, 42, 49]'
expect_fail "audit against a drifted plan" "$PY" "$SCRIPTS/audit_mix.py" "$WORK/final.mp4" --plan "$WORK/driftplan.json" --ledger "$WORK/mix/sound-ledger.json" --out "$WORK/audit-drift.json"

step "audit must fail on a final whose audio has no effects"
ffmpeg -y -v error -i "$WORK/picture.mp4" -i "$WORK/voice.wav" -map 0:v:0 -map 1:a:0 -c:v copy -c:a aac -b:a 320k -ar 48000 -ac 2 -shortest "$WORK/final-nofx.mp4"
expect_fail "audit of a final with no sound effects" "$PY" "$SCRIPTS/audit_mix.py" "$WORK/final-nofx.mp4" --plan "$WORK/plan.fit.json" --ledger "$WORK/mix/sound-ledger.json" --out "$WORK/audit-nofx.json"

printf '\nALL SOUND TESTS PASSED\n'

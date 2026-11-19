#!/usr/bin/env bash
# Tests for the cut and style scripts, on tiny synthetic media.
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VENV="${AVE_VENV:-$ROOT/.venv}"
CUT="$ROOT/.claude/skills/cut/scripts"
STY="$ROOT/.claude/skills/style/scripts"
TMP="$(mktemp -d)"
cleanup() { command -v trash >/dev/null && trash "$TMP" 2>/dev/null; return 0; }
trap cleanup EXIT
FAILS=0
ok()   { echo "PASS  $1"; }
bad()  { echo "FAIL  $1"; FAILS=$((FAILS+1)); }
expect() { # name expected_rc cmd...
  local name="$1" want="$2"; shift 2
  "$@" >"$TMP/out.txt" 2>&1; local rc=$?
  if [ "$rc" = "$want" ]; then ok "$name (exit $rc)"; else bad "$name (exit $rc, wanted $want)"; sed 's/^/      /' "$TMP/out.txt" | tail -8; fi
}

# venv, idempotent (another process may be creating it)
have() { [ -x "$VENV/bin/python" ] && "$VENV/bin/python" -c "import numpy, scipy" >/dev/null 2>&1; }
if ! have; then
  [ -x "$VENV/bin/python" ] || python3 -m venv "$VENV" 2>/dev/null
  for i in 1 2 3; do have && break; "$VENV/bin/python" -m pip install -q numpy scipy >/dev/null 2>&1 || sleep 3; done
fi
have || { echo "FAIL  venv with numpy and scipy"; exit 1; }
PY="$VENV/bin/python"
export PATH="$VENV/bin:$PATH"

# synthetic audio: ragged speech-like bursts, room tone, a breath, and one smooth-decay dropout
"$PY" - "$TMP" <<'PYEOF'
import sys, numpy as np, struct
sr = 48000; rng = np.random.default_rng(1)
n = sr * 4
x = rng.normal(0, 0.0015, n)
t = np.arange(n) / sr
def burst(a, b, f):
    i, j = int(a * sr), int(b * sr)
    env = 0.25 * (0.6 + 0.4 * rng.random((j - i) // 48 + 2)).repeat(48)[: j - i]
    x[i:j] += env * np.sin(2 * np.pi * f * t[i:j]) * (0.5 + 0.5 * rng.random(j - i))
burst(0.5, 0.9, 220); burst(1.0, 1.4, 300); burst(2.2, 2.9, 250); burst(3.1, 3.5, 270)
i, j = int(1.7 * sr), int(1.85 * sr); x[i:j] += rng.normal(0, 0.03, j - i)
a, b = int(2.5 * sr), int(2.54 * sr)
k = np.arange(b - a); db = -32 - 0.4 * (k / 48.0)
x[a:b] = 10 ** (db / 20) * np.sin(2 * np.pi * 1000 * k / sr)
y = np.stack([x, x], 1).astype("<f4")
data = y.tobytes()
hdr = b"RIFF" + struct.pack("<I", 36 + len(data)) + b"WAVE" + b"fmt " + struct.pack("<IHHIIHH", 16, 3, 2, sr, sr * 8, 8, 32) + b"data" + struct.pack("<I", len(data))
open(sys.argv[1] + "/syn.wav", "wb").write(hdr + data)
PYEOF

# 1. find_dropouts
"$PY" "$CUT/find_dropouts.py" "$TMP/syn.wav" --json "$TMP/dr.json" >"$TMP/o.txt" 2>&1; rc=$?
if [ $rc = 0 ] && "$PY" - "$TMP/dr.json" <<'PYEOF'
import json, sys
d = json.load(open(sys.argv[1]))["dropouts"]
assert len(d) == 1, d
assert abs(d[0]["startSec"] - 2.5) < 0.012 and abs(d[0]["endSec"] - 2.54) < 0.03, d
PYEOF
then ok "find_dropouts finds the injected dropout"; else bad "find_dropouts"; cat "$TMP/o.txt"; fi
read S E < <("$PY" -c "import json;d=json.load(open('$TMP/dr.json'))['dropouts'][0];print(d['startSec'],d['endSec'])")

# 2. repair_dropout
"$PY" "$CUT/repair_dropout.py" "$TMP/syn.wav" --start "$S" --end "$E" --out "$TMP/rep.wav" --json "$TMP/rep.json" >"$TMP/o.txt" 2>&1; rc=$?
if [ $rc = 0 ] && "$PY" - "$TMP" "$CUT" <<'PYEOF'
import sys, json, numpy as np
sys.path.insert(0, sys.argv[2])
from find_dropouts import load_audio
a = load_audio(sys.argv[1] + "/syn.wav"); b = load_audio(sys.argv[1] + "/rep.wav")
r = json.load(open(sys.argv[1] + "/rep.json"))
assert len(a) == len(b), (len(a), len(b))
lo, hi = [int(round(v * 48000)) for v in r["changedSampleRangeSec"]]
assert np.array_equal(a[:lo], b[:lo]) and np.array_equal(a[hi:], b[hi:])
assert not np.array_equal(a[lo:hi], b[lo:hi])
assert r["identicalOutsideChangedRange"] and len(r["sha256"]) == 64
PYEOF
then ok "repair_dropout keeps length, outside samples identical"; else bad "repair_dropout"; cat "$TMP/o.txt"; fi
"$PY" "$CUT/find_dropouts.py" "$TMP/rep.wav" | tail -1 | grep -q "^0 dropout" && ok "repaired file has no dropout" || bad "repaired file still has a dropout"

# 3. find_gaps
cat > "$TMP/words.json" <<'EOT'
[{"word":"one","start":0.5,"end":0.9,"line":"A"},{"word":"two","start":1.0,"end":1.4,"line":"A"},
 {"word":"three","start":2.2,"end":2.9,"line":"A"},{"word":"four","start":3.1,"end":3.5,"line":"B"}]
EOT
"$PY" "$CUT/find_gaps.py" "$TMP/syn.wav" --words "$TMP/words.json" --json "$TMP/gaps.json" >"$TMP/o.txt" 2>&1; rc=$?
if [ $rc = 0 ] && "$PY" - "$TMP/gaps.json" <<'PYEOF'
import json, sys
g = json.load(open(sys.argv[1]))["gaps"]
assert len(g) == 3, g
assert g[1]["breathTail"] and g[1]["proposedEndSec"] is not None and g[1]["flag"] == "KEEP", g[1]
assert g[2]["kind"] == "inter-line"
PYEOF
then ok "find_gaps lists gaps and flags the breath tail"; else bad "find_gaps"; cat "$TMP/o.txt"; fi

# 4. join_jumps on a tiny clip: 30 frames at 10 fps, scene change at frame 15
if ffmpeg -v error -y -f lavfi -i "color=c=0x303030:s=1080x1920:r=10:d=1.5,drawbox=x=300:y=1100:w=300:h=300:color=white:t=fill" \
      -f lavfi -i "color=c=0x303030:s=1080x1920:r=10:d=1.5,drawbox=x=500:y=1300:w=400:h=300:color=black:t=fill" \
      -filter_complex "[0][1]concat=n=2:v=1:a=0,format=yuv420p" -frames:v 30 "$TMP/clip.mp4" 2>"$TMP/ff.txt" && [ -s "$TMP/clip.mp4" ]; then
  cat > "$TMP/cut.json" <<'EOT'
{"pieces":[{"line":"L1","src_in":0,"src_out":15,"out_start":0},{"line":"L1","src_in":40,"src_out":55,"out_start":15},
           {"line":"L2","src_in":90,"src_out":100,"out_start":29}]}
EOT
  echo '{"segments":[[0,"IN_BIG"]]}' > "$TMP/modes.json"
  "$PY" "$CUT/join_jumps.py" "$TMP/clip.mp4" --cut "$TMP/cut.json" --modes "$TMP/modes.json" --json "$TMP/jj.json" >"$TMP/o.txt" 2>&1; rc=$?
  if [ $rc = 1 ] && "$PY" -c "
import json;j=json.load(open('$TMP/jj.json'))['joins'];assert len(j)==1 and j[0]['frame']==15 and j[0]['flagged'],j"; then ok "join_jumps flags the visible jump"; else bad "join_jumps (exit $rc)"; cat "$TMP/o.txt"; fi
  echo '{"segments":[[0,"OUT"]]}' > "$TMP/modes_out.json"
  expect "join_jumps skips OUT joins" 0 "$PY" "$CUT/join_jumps.py" "$TMP/clip.mp4" --cut "$TMP/cut.json" --modes "$TMP/modes_out.json"
else bad "could not generate a test clip with ffmpeg"; cat "$TMP/ff.txt"; fi

# 5. transcribe without faster-whisper
expect "transcribe --help" 0 "$PY" "$CUT/transcribe.py" --help
if "$PY" -c "import faster_whisper" 2>/dev/null; then echo "SKIP  transcribe install message (faster-whisper present)"
else
  expect "transcribe without faster-whisper exits 2" 2 "$PY" "$CUT/transcribe.py" "$TMP/syn.wav" --out "$TMP/w.json"
  grep -q "pip install faster-whisper" "$TMP/out.txt" && ok "install message shown" || bad "install message missing"
fi

# 6. check_captions
echo '[{"text":"this changes","start":0,"end":0.5},{"text":"everything now","start":0.5,"end":1.0},{"text":"go","start":1.0,"end":1.4}]' > "$TMP/cap_ok.json"
echo '[{"text":"this changes","start":0,"end":0.5},{"text":"everything now","start":0.4,"end":1.0}]' > "$TMP/cap_bad.json"
echo '[{"text":"this is too many words","start":0,"end":1}]' > "$TMP/cap_bad2.json"
expect "check_captions pass" 0 "$PY" "$STY/check_captions.py" "$TMP/cap_ok.json" --fps 30
expect "check_captions fails on overlap (4 words)" 1 "$PY" "$STY/check_captions.py" "$TMP/cap_bad.json"
expect "check_captions fails on 5 words" 1 "$PY" "$STY/check_captions.py" "$TMP/cap_bad2.json"
echo '[{"word":"this","start":0,"end":0.2},{"word":"changes","start":0.2,"end":0.5},{"word":"really","start":0.5,"end":0.7},{"word":"everything","start":0.7,"end":0.9},{"word":"now","start":0.9,"end":1},{"word":"go","start":1,"end":1.3}]' > "$TMP/w2.json"
expect "check_captions --words" 0 "$PY" "$STY/check_captions.py" "$TMP/cap_ok.json" --words "$TMP/w2.json"
grep -q "dropped words" "$TMP/out.txt" && ok "check_captions reports dropped word" || bad "dropped word not reported"

# 6b. make_captions: word timings -> house-style cues that pass check_captions with every word kept
"$PY" - "$TMP" <<'PYEOF'
import json, sys
txt = "This whole reel was edited by someone who's never opened CapCut. And that someone is Claude. It finds your best take and cuts out all of the dead air, but it won't chop off the end of your words. Unbelievably comprehensive documentation, honestly."
ws, t = [], 0.2
for w in txt.split():
    d = 0.08 + 0.035 * len(w); ws.append({"word": w, "start": round(t, 3), "end": round(t + d, 3)}); t += d + (0.5 if w.endswith('.') else 0.04)
json.dump(ws, open(sys.argv[1] + "/w3.json", "w"))
json.dump({"segments": [[0, "IN_BIG"], [90, "IN_SMALL"], [200, "OUT"]]}, open(sys.argv[1] + "/modes3.json", "w"))
PYEOF
expect "make_captions writes cues" 0 "$PY" "$STY/make_captions.py" "$TMP/w3.json" --out "$TMP/cap3.json" --srt "$TMP/cap3.srt" --modes "$TMP/modes3.json"
expect "make_captions output passes check_captions with every word" 0 "$PY" "$STY/check_captions.py" "$TMP/cap3.json" --words "$TMP/w3.json" --strict-words
"$PY" -c "import json,sys; c=json.load(open(sys.argv[1])); assert c[0]['y']==962 and c[-1]['y']==1489 and max(x['words'] for x in c)<=3" "$TMP/cap3.json" && ok "caption positions follow the mode, max 3 words" || bad "caption positions or word count wrong"
[ -s "$TMP/cap3.srt" ] && ok "srt written" || bad "srt missing"

# 7. check_coverage
"$PY" - "$TMP" <<'PYEOF'
import json, sys
modes = ["IN_BIG","IN_SMALL","OUT","IN_BIG","IN_SMALL","FULL","IN_BIG","OUT","IN_SMALL","OUT","IN_BIG"]
rows = [{"row": i+1, "line": f"line {i+1}", "mode": m, "startSec": i*3.0, "endSec": i*3.0+3.0} for i, m in enumerate(modes)]
json.dump(rows, open(sys.argv[1] + "/cov_ok.json", "w"))
bad = [dict(r) for r in rows]; bad[0]["mode"] = "IN_SMALL"; bad[1]["mode"] = "FULL"; bad[5]["endSec"] = bad[5]["startSec"] + 6
bad[2]["mode"] = bad[3]["mode"] = "OUT"
json.dump(bad, open(sys.argv[1] + "/cov_bad.json", "w"))
PYEOF
expect "check_coverage pass" 0 "$PY" "$STY/check_coverage.py" "$TMP/cov_ok.json"
expect "check_coverage fail" 1 "$PY" "$STY/check_coverage.py" "$TMP/cov_bad.json"
grep -q "FULL lasts" "$TMP/out.txt" && grep -q "two OUT" "$TMP/out.txt" && ok "check_coverage names the broken rules" || bad "coverage messages"

# 8. check_side_crop
expect "check_side_crop --help" 0 "$PY" "$STY/check_side_crop.py" --help
if [ "$(uname)" = Darwin ] && command -v swiftc >/dev/null; then
  cat > "$TMP/mk.swift" <<'EOT'
import AppKit
let w = 1080, h = 1920
let rep = NSBitmapImageRep(bitmapDataPlanes: nil, pixelsWide: w, pixelsHigh: h, bitsPerSample: 8, samplesPerPixel: 4, hasAlpha: true, isPlanar: false, colorSpaceName: .deviceRGB, bytesPerRow: 0, bitsPerPixel: 0)!
NSGraphicsContext.saveGraphicsState()
NSGraphicsContext.current = NSGraphicsContext(bitmapImageRep: rep)
NSColor.white.setFill(); NSRect(x: 0, y: 0, width: w, height: h).fill()
let attrs: [NSAttributedString.Key: Any] = [.font: NSFont.boldSystemFont(ofSize: 120), .foregroundColor: NSColor.black]
NSString(string: "EDGE TEXT").draw(at: NSPoint(x: 20, y: 900), withAttributes: attrs)
NSGraphicsContext.restoreGraphicsState()
try! rep.representation(using: .png, properties: [:])!.write(to: URL(fileURLWithPath: CommandLine.arguments[1]))
EOT
  if swiftc -O "$TMP/mk.swift" -o "$TMP/mk" 2>"$TMP/sw.txt" && "$TMP/mk" "$TMP/edge.png" \
     && ffmpeg -v error -y -loop 1 -framerate 2 -i "$TMP/edge.png" -t 1 -pix_fmt yuv420p "$TMP/edge.mp4" 2>"$TMP/ff2.txt" && [ -s "$TMP/edge.mp4" ]; then
    "$PY" "$STY/check_side_crop.py" "$TMP/edge.mp4" >"$TMP/o.txt" 2>&1; rc=$?
    if [ $rc = 1 ]; then ok "check_side_crop exits 1 on text near the edge"
    elif [ $rc = 2 ]; then echo "SKIP  check_side_crop real run (could not measure here)"; head -3 "$TMP/o.txt"
    else bad "check_side_crop real run (exit $rc)"; cat "$TMP/o.txt"; fi
  else echo "SKIP  check_side_crop real run (could not build the test frame)"; fi
else echo "SKIP  check_side_crop real run (not macOS)"; fi

echo
if [ $FAILS = 0 ]; then echo "ALL PASSED"; exit 0; else echo "$FAILS FAILED"; exit 1; fi

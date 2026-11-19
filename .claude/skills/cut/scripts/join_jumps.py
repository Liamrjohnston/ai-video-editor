#!/usr/bin/env python3
"""Measure the picture jump at every mid-line join in an encoded video.

    join_jumps.py FINAL.mp4 --cut cut.json --modes modes.json [--json out.json]

Why: a join inside one spoken line should be invisible. If the presenter
visibly jumps (a different head position at the same cut), viewers feel it
even when the audio is clean. This measures it on the encoded file.

cut.json (the pieces of the edit, in output order):
    {"pieces": [
       {"line": "L01", "src_in": 120, "src_out": 210, "out_start": 0},
       {"line": "L01", "src_in": 225, "src_out": 300, "out_start": 90}
    ]}
  line       id of the spoken line the piece belongs to
  src_in/out first and last+1 source frame (informational)
  out_start  first frame of the piece in FINAL.mp4
A join is the boundary between two consecutive pieces with the same line id;
it sits at the second piece's out_start. Boundaries between different lines
are framing cuts by design and are not measured.

modes.json (layout mode over time):
    {"segments": [[0, "IN_BIG"], [150, "OUT"], [210, "FULL"]]}
  [startFrame, mode] pairs; a mode holds until the next segment. Modes:
  IN_BIG, IN_SMALL, OUT, FULL (the IN_ prefix is optional).

Where it looks (as a fraction of a 9:16 frame, so any resolution works):
  IN_BIG    presenter panel below y960 of 1920
  IN_SMALL  presenter panel below y1410 of 1920
  FULL      the whole frame
  OUT       presenter not on screen, join skipped
A join where the mode changes at the cut is skipped too (a framing change).

jump = mean absolute difference across the join / median adjacent-frame
difference over the 16 frames around it. >= 3x is flagged; aim for <= 2x.
Exit 1 if any join is flagged, 0 if none, 2 if the video could not be read.
"""
import argparse
import json
import subprocess
import sys

import numpy as np

TW, TH = 135, 240                 # analysis size: 1/8 of 1080x1920
ROW0 = {"IN_BIG": int(TH * 960 / 1920), "IN_SMALL": int(TH * 1410 / 1920), "FULL": 0}
FLAG_AT = 3.0
TARGET = 2.0


def norm_mode(m):
    m = str(m).upper()
    return m if m.startswith(("IN_", "OUT", "FULL", "NONE")) else "IN_" + m


def load_frames(path):
    raw = subprocess.check_output(
        ["ffmpeg", "-v", "error", "-i", path, "-vf", f"scale={TW}:{TH},format=gray",
         "-f", "rawvideo", "-"])
    return np.frombuffer(raw, np.uint8).reshape(-1, TH, TW).astype(np.float32)


def measure(X, pieces, segments):
    segs = sorted((int(s), norm_mode(m)) for s, m in segments)

    def mode(f):
        cur = segs[0][1]
        for s, m in segs:
            if s <= f:
                cur = m
        return cur

    res = []
    for q, p in zip(pieces, pieces[1:]):
        j = int(p["out_start"])
        if q["line"] != p["line"] or j < 1 or j >= len(X):
            continue
        md = mode(j)
        if md not in ROW0 or mode(j - 1) != md:
            continue
        r = ROW0[md]

        def D(a):
            return float(np.abs(X[a + 1, r:] - X[a, r:]).mean())

        ks = [k for k in range(j - 9, j + 8) if k != j - 1 and 0 <= k < len(X) - 1]
        base = max(float(np.median([D(k) for k in ks])), 0.05) if ks else 0.05
        res.append({"frame": j, "line": p["line"], "mode": md,
                    "jump": round(D(j - 1) / base, 2),
                    "flagged": D(j - 1) / base >= FLAG_AT})
    return res


def main():
    ap = argparse.ArgumentParser(description="Measure picture jump at mid-line joins inside the presenter area.")
    ap.add_argument("video")
    ap.add_argument("--cut", required=True, help="cut.json (see docstring)")
    ap.add_argument("--modes", required=True, help="modes.json (see docstring)")
    ap.add_argument("--json")
    a = ap.parse_args()
    try:
        C = json.load(open(a.cut))
        M = json.load(open(a.modes))
        X = load_frames(a.video)
    except Exception as ex:  # noqa: BLE001
        print(f"could not read inputs: {ex}", file=sys.stderr)
        return 2
    res = measure(X, C["pieces"], M["segments"])
    if a.json:
        json.dump({"flagAt": FLAG_AT, "target": TARGET, "joins": res}, open(a.json, "w"), indent=1)
    for r in sorted(res, key=lambda r: -r["jump"]):
        mark = "FLAG" if r["flagged"] else ("ok" if r["jump"] <= TARGET else "warn")
        print(f"{mark:4} frame {r['frame']:6} line {r['line']} {r['mode']:8} jump {r['jump']}x")
    bad = sum(r["flagged"] for r in res)
    print(f"{len(res)} join(s) measured, {bad} flagged (>= {FLAG_AT}x, target <= {TARGET}x)")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())

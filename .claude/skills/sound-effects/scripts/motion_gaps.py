#!/usr/bin/env python3
"""Find visible graphic motion that has no sound.

Input is a graphics-only video (the graphics layer rendered on its own) or a folder of PNG frames, plus the plan.
Each frame is shrunk to 135x240 grey (alpha is flattened over black, so transparent areas do not count) and compared
with the frame before it (mean absolute difference). A run of at least 4 consecutive frames above the threshold is
visible motion. A run passes if any cue hit (or a cue's movement frame) falls inside it or within 3 frames before it.
Runs wholly inside a plan footageSpans entry (footage playing inside a graphic, which is content and not a graphic
move) are reported but do not fail. Exit 1 if any run is silent.

  motion_gaps.py graphics.mp4 --plan plan.json --out gaps.json
  motion_gaps.py frames_folder/ --plan plan.json --fps 30 --out gaps.json
"""
import argparse
import pathlib
import subprocess
import sys

import numpy as np

import sfxlib as S

W, H = 135, 240


def read_frames(src: pathlib.Path, fps: float):
    cmd = [S.ffmpeg_bin(), "-v", "error"]
    if src.is_dir():
        pngs = sorted(src.glob("*.png"))
        if not pngs:
            raise SystemExit(f"no .png files in {src}")
        cmd += ["-framerate", f"{fps}", "-pattern_type", "glob", "-i", str(src / "*.png")]
    else:
        cmd += ["-i", str(src)]
    cmd += ["-filter_complex", f"[0:v]scale={W}:{H},format=rgba[fg];color=c=black:s={W}x{H}[bg];[bg][fg]overlay=format=auto:shortest=1,format=gray",
            "-f", "rawvideo", "-"]
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE)
    out = []
    while True:
        buf = p.stdout.read(W * H)
        if len(buf) < W * H:
            break
        out.append(np.frombuffer(buf, np.uint8).reshape(H, W).astype(np.float32))
    p.stdout.close(); p.wait()
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("graphics", help="graphics-only video, or a folder of PNG frames")
    ap.add_argument("--plan", required=True)
    ap.add_argument("--out", required=True, help="report json")
    ap.add_argument("--fps", type=float, help="frame rate of a PNG folder (default: the plan's fps)")
    ap.add_argument("--threshold", type=float, default=0.4, help="mean frame difference that counts as motion (default 0.4)")
    ap.add_argument("--min-frames", type=int, default=4, help="shortest run that counts (default 4)")
    ap.add_argument("--window", type=int, default=3, help="a cue this many frames before a run still covers it (default 3)")
    a = ap.parse_args(argv)
    plan = S.read_json(a.plan)
    fps = a.fps or float(plan["fps"])
    frames = read_frames(pathlib.Path(a.graphics), fps)
    if len(frames) < 2:
        print("fewer than 2 frames decoded")
        return 1
    m = np.zeros(len(frames))
    for i in range(1, len(frames)):
        m[i] = float(np.abs(frames[i] - frames[i - 1]).mean())
    hits = sorted({h for c in plan["cues"] for h in (c.get("hits") or [c["frame"]])} | {c["frame"] for c in plan["cues"]})
    spans = [(int(s["from"]), int(s["to"]), s.get("why", "")) for s in plan.get("footageSpans", [])]
    on = m > a.threshold
    runs, i = [], 0
    while i < len(m):
        if on[i]:
            j = i
            while j < len(m) and on[j]:
                j += 1
            if j - i >= a.min_frames:
                covered = [h for h in hits if i - a.window <= h <= j]
                inside = any(s <= i and j <= e for s, e, _ in spans)
                runs.append({"start": i, "end": j, "fastest": int(i + np.argmax(m[i:j])), "peak": round(float(m[i:j].max()), 2),
                             "hitsInside": covered, "insideFootage": inside})
            i = j
        else:
            i += 1
    silent = [r for r in runs if not r["hitsInside"] and not r["insideFootage"]]
    footage = [r for r in runs if not r["hitsInside"] and r["insideFootage"]]
    for r in runs:
        tag = r["hitsInside"] or ("(inside footage)" if r["insideFootage"] else "--- NO SOUND ---")
        print(f"frames {r['start']}-{r['end']} fastest {r['fastest']} peak {r['peak']}: {tag}")
    S.write_json(a.out, {"frames": len(frames), "threshold": a.threshold, "runs": runs, "silent": silent, "footageOnly": footage})
    print(f"runs {len(runs)}, silent {len(silent)}, footage-only {len(footage)}")
    return 1 if silent else 0


if __name__ == "__main__":
    sys.exit(main())

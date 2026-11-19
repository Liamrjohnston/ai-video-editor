#!/usr/bin/env python3
"""Find readable text that Instagram's full-screen Reel view will cut off.

    check_side_crop.py VIDEO                      # 2 frames/s, report + exit code
    check_side_crop.py VIDEO --fps 4 --json out.json --sheet-dir DIR
    check_side_crop.py VIDEO --zoom-plan zoom-plan.json   # allow zoom bleed

Exit 0 = no readable text crosses the crop line.
Exit 1 = at least one CUT finding (text crosses the line). Fix before review.
Exit 2 = could not measure (no ffmpeg, no OCR engine, unreadable video).

Why this exists: the full-screen Reel view scales a 9:16 video to fill a
taller phone screen and trims the sides. A 1080-wide master loses about 97 px
per side on an iPhone (19.5:9) and about 108 px per side on a 20:9 Android.
The feed view shows the full width, so the problem only appears in Reel view.
Keep readable text inside x120-960 on a 1080x1920 frame.

The check reads the actual text with OCR, so a finding means real words or
numbers sit on the crop line. CUT blocks delivery. TIGHT means the text clears
the crop but sits inside the 120 px comfort margin; fix it unless it is
incidental (dimmed background UI nobody needs to read).

Two camera states:
- REGULAR framing (at rest, establishing): every readable element must be
  inside the line. Any CUT blocks.
- DELIBERATE ZOOM: a push onto one focal thing; cropping the rest is intended.
  Declare each zoom in a plan file (times in seconds of the checked video):
      [{"start": 11.0, "end": 13.4, "focus": ["-28%", "Tokens used"],
        "note": "push onto the usage drop"}]
  Inside a window only text matching a focus string (case-insensitive, either
  contains the other) can be CUT; other cut text is reported as ZOOM-BLEED and
  does not block. Outside every window the REGULAR rule applies.

OCR engine: on macOS the bundled ocr_frames.swift (Apple Vision) is compiled on
first use into ~/.cache/ai-video-editor/. Elsewhere, or if that fails, the
tesseract command is used if present. With neither, exit 2.

Writes crop-preview contact sheets with --sheet-dir (red line = Android 108 px,
orange = iPhone 97 px, yellow = 120 px comfort margin).
Needs ffmpeg. Standard library only.
"""

import argparse
import csv
import io
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
SWIFT_SRC = HERE / "ocr_frames.swift"
BIN = Path.home() / ".cache" / "ai-video-editor" / "ocr_frames"
FFMPEG = shutil.which("ffmpeg") or "/opt/homebrew/bin/ffmpeg"
FFPROBE = shutil.which("ffprobe") or "/opt/homebrew/bin/ffprobe"

IPHONE = 97 / 1080      # 19.5:9 full-screen crop per side, fraction of width
ANDROID = 108 / 1080    # 20:9 full-screen crop per side
COMFORT = 120 / 1080    # where readable content should start


class NoOCR(Exception):
    pass


def ocr_engine():
    """Return 'vision' or 'tesseract'; build the Vision helper on first use."""
    if sys.platform == "darwin" and shutil.which("swiftc") and SWIFT_SRC.exists():
        try:
            if not (BIN.exists() and BIN.stat().st_mtime >= SWIFT_SRC.stat().st_mtime):
                BIN.parent.mkdir(parents=True, exist_ok=True)
                subprocess.run(["swiftc", "-O", str(SWIFT_SRC), "-o", str(BIN)],
                               check=True, capture_output=True)
            return "vision"
        except (subprocess.CalledProcessError, OSError):
            pass
    if shutil.which("tesseract"):
        return "tesseract"
    raise NoOCR("no OCR engine: need macOS with swiftc (Apple Vision) or the tesseract command")


def run_ocr(engine, folder):
    """{frame.png: [{text, conf, x0, y0, x1, y1}]} in pixels, top-left origin."""
    if engine == "vision":
        r = subprocess.run([str(BIN), str(folder)], capture_output=True, text=True, check=True)
        return json.loads(r.stdout)
    out = {}
    for p in sorted(folder.glob("*.png")):
        r = subprocess.run(["tesseract", str(p), "stdout", "tsv"], capture_output=True, text=True)
        rows = []
        for d in csv.DictReader(io.StringIO(r.stdout), delimiter="\t", quoting=csv.QUOTE_NONE):
            try:
                conf = float(d["conf"]) / 100.0
                txt = (d["text"] or "").strip()
                if not txt or conf < 0:
                    continue
                x, y, w, h = (float(d[k]) for k in ("left", "top", "width", "height"))
            except (KeyError, ValueError, TypeError):
                continue
            rows.append({"text": txt, "conf": conf, "x0": x, "y0": y, "x1": x + w, "y1": y + h})
        out[p.name] = rows
    return out


def probe(video):
    r = subprocess.run([FFPROBE, "-v", "error", "-select_streams", "v:0",
                        "-show_entries", "stream=width,height", "-of", "json", video],
                       capture_output=True, text=True, check=True)
    s = json.loads(r.stdout)["streams"][0]
    return s["width"], s["height"]


def main():
    ap = argparse.ArgumentParser(description="Find readable text cut off by the full-screen Reel crop (exit 0 pass, 1 CUT, 2 cannot measure).")
    ap.add_argument("video")
    ap.add_argument("--fps", type=float, default=2.0)
    ap.add_argument("--json", help="write full findings JSON here")
    ap.add_argument("--sheet-dir", help="write crop-preview contact sheets here")
    ap.add_argument("--zoom-plan", help="JSON list of zoom windows with focus text")
    ap.add_argument("--min-conf", type=float, default=0.5)
    ap.add_argument("--min-height", type=float, default=14,
                    help="ignore text shorter than this many px (native size)")
    a = ap.parse_args()

    try:
        engine = ocr_engine()
        W, H = probe(a.video)
    except NoOCR as e:
        print(f"could not measure: {e}", file=sys.stderr)
        return 2
    except Exception as e:  # noqa: BLE001
        print(f"could not measure: {e}", file=sys.stderr)
        return 2

    zooms = []
    if a.zoom_plan:
        try:
            zooms = json.loads(Path(a.zoom_plan).read_text())
            for z in zooms:
                float(z["start"]), float(z["end"]), list(z["focus"])
        except Exception as e:  # noqa: BLE001
            print(f"could not read zoom plan: {e}", file=sys.stderr)
            return 2

    def norm(t):
        return " ".join(t.lower().split())

    def zoom_at(t):
        return next((z for z in zooms if float(z["start"]) <= t <= float(z["end"])), None)

    def is_focus(text, z):
        n = norm(text)
        return any(f and (norm(f) in n or n in norm(f)) for f in z["focus"])

    tmp = Path(tempfile.mkdtemp(prefix="sidecrop-"))
    try:
        try:
            subprocess.run([FFMPEG, "-v", "error", "-i", a.video, "-vf", f"fps={a.fps}",
                            str(tmp / "f%05d.png")], check=True)
            ocr = run_ocr(engine, tmp)
        except Exception as e:  # noqa: BLE001
            print(f"could not measure: {e}", file=sys.stderr)
            return 2

        cut_l, cut_r = ANDROID * W, W - ANDROID * W
        ip_l, ip_r = IPHONE * W, W - IPHONE * W
        cf_l, cf_r = COMFORT * W, W - COMFORT * W
        findings = []
        for name in sorted(ocr):
            t = (int(name[1:6]) - 1) / a.fps
            for o in ocr[name]:
                if o["conf"] < a.min_conf or (o["y1"] - o["y0"]) < a.min_height:
                    continue
                x0, x1 = o["x0"], o["x1"]
                if x0 < cut_l or x1 > cut_r:
                    level = "CUT"
                    side = "left" if x0 < cut_l else "right"
                    lost = (cut_l - x0) if side == "left" else (x1 - cut_r)
                elif x0 < cf_l or x1 > cf_r:
                    level, side, lost = "TIGHT", ("left" if x0 < cf_l else "right"), 0
                else:
                    continue
                z = zoom_at(t)
                if z is not None and not is_focus(o["text"], z):
                    level = "ZOOM-BLEED" if level == "CUT" else "ZOOM-TIGHT"
                findings.append({
                    "time": round(t, 2), "level": level, "side": side,
                    "zoom": z.get("note", True) if z is not None else None,
                    "text": o["text"], "x0": round(x0), "x1": round(x1),
                    "y0": round(o["y0"]), "y1": round(o["y1"]),
                    "px_past_android_line": round(max(lost, 0)),
                    "crosses_iphone_line": x0 < ip_l or x1 > ip_r,
                })

        if a.sheet_dir:
            out = Path(a.sheet_dir)
            out.mkdir(parents=True, exist_ok=True)
            s = 4
            lines = []
            for frac, col in ((ANDROID, "red"), (IPHONE, "orange"), (COMFORT, "yellow")):
                for x in (frac * W, W - frac * W):
                    lines.append(f"drawbox=x={int(x / s)}:y=0:w=2:h=ih:color={col}@0.9:t=fill")
            vf = f"scale={W // s}:{H // s}," + ",".join(lines) + ",tile=10x2:padding=6:color=white"
            subprocess.run([FFMPEG, "-v", "error", "-y", "-framerate", "1",
                            "-i", str(tmp / "f%05d.png"), "-vf", vf,
                            str(out / "crop-preview-%02d.png")], check=True)

        cuts = [f for f in findings if f["level"] == "CUT"]
        tight = [f for f in findings if f["level"] == "TIGHT"]
        bleed = [f for f in findings if f["level"] == "ZOOM-BLEED"]
        report = {"video": a.video, "size": [W, H], "fps": a.fps, "engine": engine,
                  "frames_checked": len(ocr),
                  "crop_px_per_side": {"iphone_19.5x9": round(IPHONE * W),
                                       "android_20x9": round(ANDROID * W),
                                       "comfort_margin": round(COMFORT * W)},
                  "zoom_plan": a.zoom_plan, "zoom_windows": zooms,
                  "cut": len(cuts), "tight": len(tight), "zoom_bleed": len(bleed),
                  "findings": findings,
                  "verdict": "REVISE" if cuts else "PASS"}
        if a.json:
            Path(a.json).write_text(json.dumps(report, indent=2))
        print(f"{report['verdict']}: {len(cuts)} CUT, {len(tight)} TIGHT, "
              f"{len(bleed)} ZOOM-BLEED (allowed) "
              f"across {len(ocr)} frames ({a.fps} fps, {engine})")
        for z in zooms:
            print(f"  ZOOM  {float(z['start']):6.1f}-{float(z['end']):.1f}s  focus {z['focus']}  {z.get('note', '')}")
        for f in cuts:
            print(f"  CUT   {f['time']:6.1f}s {f['side']:5}  {f['px_past_android_line']:3}px past  {f['text'][:60]}")
        for f in tight[:40]:
            print(f"  TIGHT {f['time']:6.1f}s {f['side']:5}  {f['text'][:60]}")
        return 1 if cuts else 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())

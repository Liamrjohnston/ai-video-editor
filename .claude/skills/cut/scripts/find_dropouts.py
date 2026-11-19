#!/usr/bin/env python3
"""Find wireless-mic dropouts in a recording.

    find_dropouts.py SOURCE [--json out.json]

SOURCE is any audio or video file ffmpeg can read (first audio stream).

Why: when a wireless receiver loses the signal for a few tens of milliseconds
it hides the gap with a smooth fade (concealment). It sounds like a glitch on
one word and cannot be fixed by cutting around it unless you know where it is.

How: the audio is reduced to a 1 ms peak envelope in dB. A dropout is
  1. an abrupt fall (>= 8 dB within 2 ms),
  2. then a perfectly smooth decay: a straight-line fit over 15 ms leaves a
     residual under 0.8 dB (real speech and room tone are ragged, 2-4 dB),
  3. then an abrupt return (>= 8 dB rise).
Each hit is reported with start and end in seconds (and ms length). Nothing
is hardcoded about frame rate or file; add your own fps downstream.

Exit code: 0 always when the file could be analysed (zero hits is a valid
answer), 2 if the audio could not be decoded.
"""
import argparse
import json
import subprocess
import sys

import numpy as np

SR = 48000
WIN = 15            # ms window for the straight-line fit
RESID_DB = 0.8      # concealment is smoother than this
STEP_DB = 8.0       # abrupt fall / rise size
FLOOR_DB = -75.0    # ignore digital silence


def load_audio(path, sr=SR):
    """Decode the first audio stream to float32 stereo at `sr` Hz."""
    raw = subprocess.check_output(
        ["ffmpeg", "-v", "error", "-i", path, "-map", "0:a:0", "-ac", "2",
         "-ar", str(sr), "-f", "f32le", "-"])
    return np.frombuffer(raw, "<f4").reshape(-1, 2)


def envelope_db(x, sr=SR):
    """1 ms peak envelope in dB across channels."""
    blk = sr // 1000
    a = np.abs(x).max(axis=1)
    n = len(a) // blk
    return 20 * np.log10(a[:n * blk].reshape(n, blk).max(axis=1) + 1e-9)


def fit_residual(e, w=WIN):
    """Std of the residual of a straight-line fit in every w-long window."""
    n = len(e)
    res = np.full(n, 99.0)
    if n < w + 1:
        return res
    t = np.arange(w, dtype=float)
    A = np.stack([t, np.ones(w)], axis=1)
    proj = np.eye(w) - A @ np.linalg.pinv(A)          # residual-maker matrix
    segs = np.lib.stride_tricks.sliding_window_view(e, w)[: n - w]
    r = segs @ proj
    res[: n - w] = np.sqrt((r * r).mean(axis=1))
    return res


def find_dropouts(x, sr=SR):
    e = envelope_db(x, sr)
    n = len(e)
    res = fit_residual(e)
    hits = []
    i = 0
    while i < n - WIN:
        if res[i] < RESID_DB and e[i:i + WIN].max() > FLOOR_DB:
            j = i
            while j < n - WIN and res[j] < RESID_DB:
                j += 1
            a0, a1 = i, j + WIN
            if a0 + 1 < n and a1 - 2 >= 0 and a1 <= n:
                drop = e[max(0, a0 - 3):a0].max() - e[a0 + 1] if a0 > 0 else 0.0
                rise = e[a1:a1 + 3].max() - e[a1 - 2] if a1 < n else 0.0
                if drop >= STEP_DB and rise >= STEP_DB:
                    hits.append({
                        "startSec": round(a0 / 1000, 4),
                        "endSec": round(a1 / 1000, 4),
                        "ms": int(a1 - a0),
                        "dropDb": round(float(drop), 1),
                        "riseDb": round(float(rise), 1),
                        "levelDb": [round(float(e[a0]), 1), round(float(e[a1 - 1]), 1)],
                    })
            i = a1
        else:
            i += 1
    return hits, n / 1000.0


def main():
    ap = argparse.ArgumentParser(description="Find wireless-mic dropouts (abrupt fall, smooth decay, abrupt return).")
    ap.add_argument("source")
    ap.add_argument("--json", help="write the hits as JSON here")
    a = ap.parse_args()
    try:
        x = load_audio(a.source)
    except Exception as ex:  # noqa: BLE001
        print(f"could not read audio: {ex}", file=sys.stderr)
        return 2
    hits, dur = find_dropouts(x)
    if a.json:
        with open(a.json, "w") as f:
            json.dump({"source": a.source, "durationSec": round(dur, 3), "dropouts": hits}, f, indent=1)
    for h in hits:
        print(f"dropout {h['startSec']:.4f}-{h['endSec']:.4f}s ({h['ms']} ms) fall {h['dropDb']} dB, return {h['riseDb']} dB")
    print(f"{len(hits)} dropout(s) in {dur:.1f} s")
    return 0


if __name__ == "__main__":
    sys.exit(main())

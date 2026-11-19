#!/usr/bin/env python3
"""Repair one wireless-mic dropout without changing the file length.

    repair_dropout.py SOURCE --start S --end E --out repaired.wav
                      [--pause SEC] [--json receipt.json]

S and E (seconds) are the concealed stretch, as reported by find_dropouts.py.
The output is 48 kHz stereo 32-bit float WAV, the same length as the decoded
source.

Why: cutting the concealment out shortens the audio and breaks lip sync for
everything after it, and filling it with synthesis or filtering adds artefacts.
This repair moves only real samples around:
  1. delete the concealment [S, E) and join the two real halves with a 3 ms
     equal-power crossfade (the halves are uncorrelated noise, so equal power
     keeps the level steady);
  2. make up the lost time by repeating room tone taken from the nearest
     preceding pause, with a 10 ms equal-power crossfade at the insertion
     point. The audio between the pause and the dropout moves later by the
     repeated length, and everything from the join onward keeps its original
     time, so lip sync is unchanged after the repair.
No synthesis, no filtering, no gain. Every sample outside the edited window
is identical to the source, which the script asserts before writing.

The pause is found automatically: the quietest stretch of at least 60 ms (and
at least as long as the repeat needs) within 1.5 s before the dropout. Pass
--pause SEC to choose the insertion point yourself (the end of a pause).
Writes a JSON receipt with the numbers and the SHA-256 of the output.
"""
import argparse
import hashlib
import json
import struct
import sys

import numpy as np

from find_dropouts import SR, load_audio

XFADE_JOIN_MS = 3.0
XFADE_PAUSE_MS = 10.0
MIN_PAUSE_MS = 60.0
SEARCH_BACK_S = 1.5


def write_wav_f32(path, y, sr=SR):
    data = y.astype("<f4").tobytes()
    ch = y.shape[1]
    hdr = b"RIFF" + struct.pack("<I", 36 + len(data)) + b"WAVE"
    hdr += b"fmt " + struct.pack("<IHHIIHH", 16, 3, ch, sr, sr * ch * 4, ch * 4, 32)
    hdr += b"data" + struct.pack("<I", len(data))
    with open(path, "wb") as f:
        f.write(hdr + data)


def find_pause(x, ga, need, sr=SR):
    """Insertion point P (sample) at the end of the quietest stretch of `need`
    samples inside the 1.5 s before ga. Returns (P, rms_db)."""
    lo = max(0, ga - int(SEARCH_BACK_S * sr))
    hi = ga
    if hi - lo < need:
        raise ValueError("not enough audio before the dropout to find room tone")
    p = np.abs(x[lo:hi]).max(axis=1) ** 2
    cs = np.concatenate([[0.0], np.cumsum(p)])
    step = max(1, sr // 1000)
    best = None
    for s in range(0, hi - lo - need + 1, step):
        m = (cs[s + need] - cs[s]) / need
        if best is None or m <= best[0]:        # ties go to the later (nearer) stretch
            best = (m, s)
    m, s = best
    return lo + s + need, 10 * np.log10(m + 1e-12)


def repair(x, start, end, pause=None, sr=SR):
    ga, gb = int(round(start * sr)), int(round(end * sr))
    if not 0 < ga < gb <= len(x):
        raise ValueError("start/end outside the audio")
    c = int(XFADE_JOIN_MS / 1000 * sr)
    h1 = int(XFADE_PAUSE_MS / 1000 * sr / 2)       # half of the 10 ms crossfade
    L = gb - ga
    Lp = L + c                                     # samples of room tone to insert
    need = max(int(MIN_PAUSE_MS / 1000 * sr), Lp + 2 * h1)
    if pause is None:
        P, level = find_pause(x, ga, need, sr)
        P -= h1                                    # crossfade is centred at P, stretch ends at P+h1
    else:
        P = int(round(pause * sr))
        level = 10 * np.log10(float((x[P - Lp - h1:P + h1] ** 2).max()) + 1e-12)
    if P - Lp - h1 < 0 or P + h1 > ga - c or gb + c > len(x):
        raise ValueError("pause must lie before the dropout with room for the repeat")
    y = x.copy()
    th = np.linspace(0, np.pi / 2, 2 * h1)[:, None]
    t = np.arange(P - h1, P + h1)
    y[t] = x[t] * np.cos(th) + x[t - Lp] * np.sin(th)
    t = np.arange(P + h1, gb)
    y[t] = x[t - Lp]
    th2 = np.linspace(0, np.pi / 2, c)[:, None]
    t = np.arange(gb, gb + c)
    y[t] = x[t - Lp] * np.cos(th2) + x[t] * np.sin(th2)
    a, b = P - h1, gb + c
    assert np.array_equal(y[:a], x[:a]) and np.array_equal(y[b:], x[b:]), "outside window changed"
    assert len(y) == len(x)
    info = {
        "dropoutSec": [ga / sr, gb / sr],
        "dropoutMs": round(L / sr * 1000, 2),
        "joinCrossfadeMs": c / sr * 1000,
        "roomToneInsertedAtSec": P / sr,
        "roomToneRepeatMs": round(Lp / sr * 1000, 2),
        "roomToneCrossfadeMs": 2 * h1 / sr * 1000,
        "roomToneLevelDb": round(float(level), 1),
        "changedSampleRangeSec": [a / sr, b / sr],
        "identicalOutsideChangedRange": True,
        "samples": len(y),
        "sampleRate": sr,
    }
    return y, info


def main():
    ap = argparse.ArgumentParser(description="Delete a dropout's concealment, join the real halves and repeat room tone to keep timing.")
    ap.add_argument("source")
    ap.add_argument("--start", type=float, required=True, help="concealment start, seconds")
    ap.add_argument("--end", type=float, required=True, help="concealment end, seconds")
    ap.add_argument("--out", required=True, help="repaired WAV (48 kHz stereo float)")
    ap.add_argument("--pause", type=float, help="insertion point in seconds (end of a pause); default auto")
    ap.add_argument("--json", help="write a receipt here")
    a = ap.parse_args()
    try:
        x = load_audio(a.source).copy()
        y, info = repair(x, a.start, a.end, a.pause)
    except Exception as ex:  # noqa: BLE001
        print(f"repair failed: {ex}", file=sys.stderr)
        return 2
    write_wav_f32(a.out, y)
    with open(a.out, "rb") as f:
        info["sha256"] = hashlib.sha256(f.read()).hexdigest()
    info["source"] = a.source
    info["output"] = a.out
    if a.json:
        with open(a.json, "w") as f:
            json.dump(info, f, indent=1)
    print(json.dumps({k: info[k] for k in ("dropoutMs", "roomToneInsertedAtSec", "roomToneRepeatMs", "changedSampleRangeSec", "sha256")}))
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""List every gap between spoken words, with its level and a cut candidate flag.

    find_gaps.py AUDIO --words words.json [--json out.json]
                 [--min-gap 0.04] [--min-cut 0.18] [--room-margin 6]

words.json is a list of word timings in seconds (transcribe.py writes it):
    [{"word": "hello", "start": 0.12, "end": 0.48}, ...]
An optional "line" field per word (any id) marks which line a word belongs to;
gaps across a line change are labelled "inter-line", the rest "intra-line".

For each gap the report gives start, end, duration, RMS level in dB, how far
that is above the room tone, and a flag:
  CUT   long enough (>= --min-cut) and within --room-margin dB of room tone,
        so nothing audible is lost by removing most of it
  KEEP  short, or louder than room tone (a breath, a laugh, a missed word)
Room tone is estimated as the 10th percentile of 10 ms RMS blocks.

Breath tails: where the level falls toward room tone after a word and then
rises again with no word there, the rise is a breath or mouth noise. Those
gaps get "breathTail": true and a proposed end for the piece, 20 ms after the
word's last sound (the moment the level reaches room tone + 3 dB).

This tool only reports candidates. It never cuts anything.
"""
import argparse
import json
import sys

import numpy as np

from find_dropouts import SR, load_audio

BLOCK_S = 0.005
TAIL_PAD_S = 0.020


def rms_env(x, sr=SR, block=BLOCK_S):
    m = x.mean(axis=1) if x.ndim == 2 else x
    n = int(sr * block)
    k = len(m) // n
    r = np.sqrt((m[: k * n].reshape(k, n) ** 2).mean(axis=1))
    return 20 * np.log10(r + 1e-9)


def room_tone_db(env):
    k = 2                                    # 10 ms = two 5 ms blocks
    n = len(env) // k
    if n == 0:
        return float(env.min()) if len(env) else -90.0
    blocks = 10 * np.log10((10 ** (env[: n * k] / 10)).reshape(n, k).mean(axis=1) + 1e-18)
    return float(np.percentile(blocks, 10))


def analyse(x, words, min_gap=0.04, min_cut=0.18, margin=6.0, sr=SR):
    env = rms_env(x, sr)
    room = room_tone_db(env)
    out = []
    for i in range(len(words) - 1):
        a, b = float(words[i]["end"]), float(words[i + 1]["start"])
        d = b - a
        if d < min_gap:
            continue
        i0, i1 = int(a / BLOCK_S), max(int(a / BLOCK_S) + 1, int(b / BLOCK_S))
        seg = env[i0:i1]
        if len(seg) == 0:
            continue
        level = float(10 * np.log10((10 ** (seg / 10)).mean() + 1e-18))
        over = level - room
        flag = "CUT" if d >= min_cut and over <= margin else "KEEP"
        # breath tail: falls to room tone + 3 dB, then rises above room + 6 dB with no word
        calm = np.where(seg <= room + 3)[0]
        tail = False
        propose = None
        if len(calm):
            t0 = calm[0]
            if t0 + 2 < len(seg) and seg[t0 + 1:].max() > room + 6:
                tail = True
                propose = round(a + t0 * BLOCK_S + TAIL_PAD_S, 3)
        la, lb = words[i].get("line"), words[i + 1].get("line")
        out.append({
            "after": words[i]["word"], "before": words[i + 1]["word"],
            "startSec": round(a, 3), "endSec": round(b, 3), "durSec": round(d, 3),
            "rmsDb": round(level, 1), "overRoomDb": round(over, 1),
            "kind": "inter-line" if (la is not None and lb is not None and la != lb) else "intra-line",
            "flag": flag, "breathTail": tail, "proposedEndSec": propose,
        })
    return out, room


def main():
    ap = argparse.ArgumentParser(description="Report every gap between words with level and a CUT/KEEP candidate flag. Never cuts.")
    ap.add_argument("audio")
    ap.add_argument("--words", required=True, help="words.json: [{word,start,end}]")
    ap.add_argument("--json")
    ap.add_argument("--min-gap", type=float, default=0.04, help="ignore gaps shorter than this (s)")
    ap.add_argument("--min-cut", type=float, default=0.18, help="shortest gap flagged CUT (s)")
    ap.add_argument("--room-margin", type=float, default=6.0, help="dB above room tone still counted as silence")
    a = ap.parse_args()
    try:
        words = json.load(open(a.words))
        x = load_audio(a.audio)
    except Exception as ex:  # noqa: BLE001
        print(f"could not read inputs: {ex}", file=sys.stderr)
        return 2
    gaps, room = analyse(x, words, a.min_gap, a.min_cut, a.room_margin)
    if a.json:
        json.dump({"roomToneDb": round(room, 1), "gaps": gaps}, open(a.json, "w"), indent=1)
    print(f"room tone {room:.1f} dB, {len(gaps)} gap(s)")
    for g in gaps:
        extra = f"  BREATH TAIL -> end piece at {g['proposedEndSec']}s" if g["breathTail"] else ""
        print(f"{g['flag']:4} {g['startSec']:8.3f}-{g['endSec']:.3f} {g['durSec']*1000:5.0f} ms {g['rmsDb']:6.1f} dB "
              f"({g['kind']}) {g['after']} | {g['before']}{extra}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Check that no more than three caption words are visible at once.

    check_captions.py CAPTIONS.json [--fps 30] [--words words.json]
                      [--max-words 3] [--strict-words]

CAPTIONS.json is a list of cues in seconds:
    [{"text": "this changes everything", "start": 0.40, "end": 1.10}, ...]
words.json (optional, from transcribe.py) is [{"word","start","end"}].

Why: short bursts of two or three words are readable at a glance on a phone;
a fourth word on screen turns captions into subtitles people have to read.
The count includes overlap: while an outgoing cue is still visible, the
incoming cue's words add to it, so a one-frame overlap of two 2-word cues
already shows 4 words.

Cue times are snapped to frames at --fps; a cue is visible from its start
frame up to, not including, its end frame. Fails (exit 1) if the visible
word count ever exceeds --max-words. Also lists the longest cues (a cue that
sits too long feels stuck).

With --words the caption text is compared with the spoken words in order:
words in the speech missing from the captions are "dropped", words repeated
in the captions but not in the speech are "duplicated". These are warnings;
add --strict-words to make them fail too.
"""
import argparse
import difflib
import json
import re
import sys


def toks(s):
    return [w for w in re.sub(r"[^\w\s'%$.-]", " ", s.lower()).replace(" - ", " ").split() if w.strip(".-")]


def peak_words(cues, fps):
    cs = [(round(c["start"] * fps), round(c["end"] * fps), len(toks(c["text"])), c) for c in cues]
    cs = [c for c in cs if c[1] > c[0]]
    pts = sorted({c[0] for c in cs})
    worst = (0, None, [])
    for f in pts:
        act = [c for c in cs if c[0] <= f < c[1]]
        n = sum(c[2] for c in act)
        if n > worst[0]:
            worst = (n, f / fps, [c[3]["text"] for c in act])
    return worst


def compare(cues, words):
    cap = [w for c in sorted(cues, key=lambda c: c["start"]) for w in toks(c["text"])]
    spk = [w for x in words for w in toks(x["word"])]
    dropped, dup = [], []
    sm = difflib.SequenceMatcher(None, spk, cap, autojunk=False)
    for op, i0, i1, j0, j1 in sm.get_opcodes():
        if op in ("delete", "replace"):
            dropped += spk[i0:i1]
        if op in ("insert", "replace"):
            for k in range(j0, j1):
                if k > 0 and cap[k] == cap[k - 1]:
                    dup.append(cap[k])
    return dropped, dup


def main():
    ap = argparse.ArgumentParser(description="Fail if more than 3 caption words are visible at once.")
    ap.add_argument("captions")
    ap.add_argument("--fps", type=float, default=30.0)
    ap.add_argument("--words")
    ap.add_argument("--max-words", type=int, default=3)
    ap.add_argument("--strict-words", action="store_true")
    a = ap.parse_args()
    try:
        cues = json.load(open(a.captions))
        words = json.load(open(a.words)) if a.words else None
        for c in cues:
            c["text"], c["start"], c["end"] = str(c["text"]), float(c["start"]), float(c["end"])
    except Exception as ex:  # noqa: BLE001
        print(f"could not read inputs: {ex}", file=sys.stderr)
        return 2
    n, t, texts = peak_words(cues, a.fps)
    fail = n > a.max_words
    print(f"{len(cues)} cues, peak {n} word(s) visible at once" + (f" at {t:.2f}s: {texts}" if n else ""))
    print("longest cues:")
    for c in sorted(cues, key=lambda c: c["start"] - c["end"])[:5]:
        print(f"  {c['end'] - c['start']:.2f}s  {c['start']:.2f}-{c['end']:.2f}  {c['text']!r}")
    if words is not None:
        dropped, dup = compare(cues, words)
        if dropped:
            print(f"WARN dropped words ({len(dropped)}): {' '.join(dropped[:20])}")
        if dup:
            print(f"WARN duplicated words ({len(dup)}): {' '.join(dup[:20])}")
        if a.strict_words and (dropped or dup):
            fail = True
    print("FAIL" if fail else "PASS")
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())

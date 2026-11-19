#!/usr/bin/env python3
"""Make the captions: turn word timings into short caption cues placed for each layout.

    make_captions.py words.json --out captions.json
    make_captions.py words.json --out captions.json --srt captions.srt --modes modes.json --fps 29.97

Input words.json is a list of {"word", "start", "end"} in seconds (what transcribe.py writes,
re-timed to the final cut). Output captions.json is a list of
{"text", "start", "end", "words", "mode", "x", "y"} that check_captions.py and the Captions.tsx
component read. --srt also writes a subtitle file for people finishing in another editor.

How words are grouped, and why:
  - Two or three words a screen, never more than three visible at once anywhere in the frame.
    Short captions are read in one glance; long ones pull the eye off the speaker.
  - When three words would be long (more than --max-chars characters including spaces), the
    screen takes two. Two long words get a screen of their own.
  - A cue never runs across the end of a sentence or a real pause (--pause seconds), so captions
    break where the speaker breaks.
  - A single word is allowed for emphasis or a natural remainder, rather than gluing it onto the
    next sentence.
  - Every spoken word appears exactly once, in order. Nothing is paraphrased or dropped.
  - Cues never overlap: each one ends when the next starts, or shortly after its last word when
    the speaker pauses, so the screen never shows four or more words.

Positions come from the layout mode at the cue's start (from modes.json, the same file
join_jumps.py reads): IN SMALL (540,1262), IN BIG (540,962), OUT and FULL (540,1489).
Captions sit on their own layer and never follow a camera zoom.
"""
import argparse
import json
import re
import sys

POS = {"IN_SMALL": (540, 1262), "IN_BIG": (540, 962), "OUT": (540, 1489), "FULL": (540, 1489), "NONE": (540, 1262)}
SENTENCE_END = re.compile(r"[.!?]['\")\]]*$")
CLAUSE_END = re.compile(r"[,;:]['\")\]]*$")


def load_words(path):
    data = json.load(open(path))
    if isinstance(data, dict):
        data = data.get("words", [])
    words = []
    for w in data:
        t = str(w.get("word", w.get("text", ""))).strip()
        if not t:
            continue
        words.append({"word": t, "start": float(w["start"]), "end": float(w["end"])})
    words.sort(key=lambda w: w["start"])
    return words


def load_modes(path, fps):
    if not path:
        return None
    segs = json.load(open(path))
    segs = segs.get("segments", segs) if isinstance(segs, dict) else segs
    out = []
    for start, mode in segs:
        m = str(mode).upper()
        if not m.startswith("IN_") and m in ("BIG", "SMALL"):
            m = "IN_" + m
        out.append((float(start) / fps, m))
    out.sort()
    return out


def mode_at(modes, t):
    if not modes:
        return "IN_SMALL"
    cur = modes[0][1]
    for s, m in modes:
        if s <= t + 1e-6:
            cur = m
    return cur


def phrases(words, pause):
    """Split at sentence ends, clause marks (, ; :) and real pauses: captions break where the speaker breaks."""
    out, cur = [], []
    for i, w in enumerate(words):
        cur.append(w)
        nxt = words[i + 1] if i + 1 < len(words) else None
        gap = (nxt["start"] - w["end"]) if nxt else 99
        if SENTENCE_END.search(w["word"]) or CLAUSE_END.search(w["word"]) or gap >= pause:
            out.append(cur); cur = []
    if cur:
        out.append(cur)
    return out


def split_even(ph, k):
    n = len(ph); base, extra = divmod(n, k); sizes = [base + (1 if i < extra else 0) for i in range(k)]
    out, i = [], 0
    for sz in sizes:
        out.append(ph[i:i + sz]); i += sz
    return out


def group(words, max_words, max_chars, pause):
    """Each phrase is split into the fewest, most even screens of at most max_words words.
    A screen of three that runs past max_chars is too crowded, so the phrase gets one more screen.
    Two long words are allowed to stand together; a single long word stands alone."""
    groups = []
    for ph in phrases(words, pause):
        k = -(-len(ph) // max_words)
        while True:
            chunks = split_even(ph, k)
            if all(len(c) <= 2 or len(" ".join(w["word"] for w in c)) <= max_chars for c in chunks) or k >= len(ph):
                break
            k += 1
        groups.extend(chunks)
    return groups


def to_cues(groups, pause, tail, min_dur, modes):
    cues = []
    for i, g in enumerate(groups):
        start = g[0]["start"]
        last_end = g[-1]["end"]
        nxt = groups[i + 1][0]["start"] if i + 1 < len(groups) else None
        if nxt is not None and nxt - last_end < pause:
            end = nxt                      # hand straight over: no blank flash, no overlap
        else:
            end = last_end + tail
            if nxt is not None:
                end = min(end, nxt)
        end = max(end, min(start + min_dur, nxt if nxt is not None else start + min_dur))
        m = mode_at(modes, start)
        x, y = POS.get(m, POS["IN_SMALL"])
        cues.append({"text": " ".join(w["word"] for w in g), "start": round(start, 3), "end": round(end, 3),
                     "words": len(g), "mode": m, "x": x, "y": y})
    return cues


def srt_time(t):
    ms = int(round(t * 1000))
    h, ms = divmod(ms, 3600000); m, ms = divmod(ms, 60000); s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def main():
    ap = argparse.ArgumentParser(description="Group word timings into 2 to 3 word caption cues, never more than 3 visible.")
    ap.add_argument("words", help="words.json: [{word, start, end}] in seconds, timed to the final cut")
    ap.add_argument("--out", required=True, help="captions.json to write")
    ap.add_argument("--srt", help="also write an .srt file")
    ap.add_argument("--modes", help="modes.json {segments: [[startFrame, mode], ...]} to place each cue")
    ap.add_argument("--fps", type=float, default=30000 / 1001, help="frame rate for modes.json frames (default 29.97)")
    ap.add_argument("--max-words", type=int, default=3)
    ap.add_argument("--max-chars", type=int, default=20, help="above this, a screen holds two words instead of three")
    ap.add_argument("--pause", type=float, default=0.35, help="a gap this long (s) always starts a new caption")
    ap.add_argument("--tail", type=float, default=0.15, help="how long a caption stays after its last word before a pause")
    ap.add_argument("--min-dur", type=float, default=0.2, help="shortest time a caption is on screen")
    a = ap.parse_args()
    if a.max_words > 3:
        sys.exit("Captions never show more than three words. Use --max-words 3 or less.")
    words = load_words(a.words)
    if not words:
        sys.exit("No words found in " + a.words)
    cues = to_cues(group(words, a.max_words, a.max_chars, a.pause), a.pause, a.tail, a.min_dur, load_modes(a.modes, a.fps))
    assert sum(c["words"] for c in cues) == len(words), "every spoken word must appear exactly once"
    json.dump(cues, open(a.out, "w"), indent=1)
    if a.srt:
        with open(a.srt, "w") as f:
            for i, c in enumerate(cues, 1):
                f.write(f"{i}\n{srt_time(c['start'])} --> {srt_time(c['end'])}\n{c['text']}\n\n")
    sizes = [c["words"] for c in cues]
    print(f"{len(cues)} captions from {len(words)} words: "
          f"{sizes.count(1)} one-word, {sizes.count(2)} two-word, {sizes.count(3)} three-word. Wrote {a.out}")


if __name__ == "__main__":
    main()

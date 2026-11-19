#!/usr/bin/env python3
"""Transcribe audio or video to word timings, locally.

    transcribe.py MEDIA --out words.json [--model small.en] [--language en]

Writes a list of {"word", "start", "end"} in seconds, the format find_gaps.py
and check_captions.py --words read. Runs on your machine with faster-whisper;
nothing is uploaded. Needs: pip install faster-whisper
"""
import argparse
import json
import sys


def main():
    ap = argparse.ArgumentParser(description="Local word-timestamp transcription with faster-whisper.")
    ap.add_argument("media")
    ap.add_argument("--out", required=True)
    ap.add_argument("--model", default="small.en", help="faster-whisper model name (default small.en)")
    ap.add_argument("--language", default=None)
    a = ap.parse_args()
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        print("faster-whisper is not installed. Install it with:\n    pip install faster-whisper", file=sys.stderr)
        return 2
    model = WhisperModel(a.model, compute_type="int8")
    segs, _ = model.transcribe(a.media, word_timestamps=True, language=a.language)
    words = [{"word": w.word.strip(), "start": round(w.start, 3), "end": round(w.end, 3)}
             for s in segs for w in (s.words or [])]
    with open(a.out, "w") as f:
        json.dump(words, f, indent=1)
    print(f"{len(words)} words -> {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

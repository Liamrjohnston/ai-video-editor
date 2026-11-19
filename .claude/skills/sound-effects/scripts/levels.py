#!/usr/bin/env python3
"""Report how loud each kind of sound is, and whether the effects stay clear of the voice.

Two measurements, both K-weighted (BS.1770 style):
  ROLE LEVELS  each cue is rendered as placed (gain, plan trim and voice trim applied) and its perceived loudness
               (loudest 100 ms window) is listed per role next to the role target from the plan. Cues that were
               trimmed for the voice are marked, because they are meant to sit lower than their role.
  VOICE CLARITY  400 ms windows (100 ms hop) where the voice is speaking (above -45 LUFS): how far the effects stem
               sits under the voice. Any window where the effects come within 6 dB of the voice fails.
Exit code 1 if any speech window has effects within 6 dB of the voice.

  levels.py mix_dir/sound-ledger.json [--voice voice.wav] [--out levels.json]
The voice defaults to the one recorded in the ledger.
"""
import argparse
import pathlib
import sys

import numpy as np

import sfxlib as S


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("ledger", help="sound-ledger.json from build_mix.py")
    ap.add_argument("--voice", help="voice track (default: the one in the ledger)")
    ap.add_argument("--out", help="write the numbers as json")
    ap.add_argument("--bank", help="path to bank.json (default: ../bank/bank.json)")
    ap.add_argument("--margin-db", type=float, default=6.0, help="effects must stay at least this far under the voice (default 6)")
    a = ap.parse_args(argv)
    L = S.read_json(a.ledger)
    bank = S.Bank(a.bank)
    mixdir = pathlib.Path(a.ledger).resolve().parent
    target = L.get("roleLoudness", S.DEFAULT_ROLE_LUFS)

    byrole: dict[str, list] = {}
    for c in L["cues"]:
        cl = S.prepare_clip(bank.file_of(c["sound"]), c["role"])
        m = S.momentary_lufs(S.apply_gain(cl["x"], c["appliedGainDb"]))
        byrole.setdefault(c["role"], []).append((c["id"], round(m, 1), c.get("voiceTrimDb", 0.0) != 0.0))
    report = {"roles": {}, "clarity": None}
    print("ROLE LEVELS (perceived loudness of the loudest 100 ms, LUFS)")
    for role, v in sorted(byrole.items()):
        vals = [x[1] for x in v]
        report["roles"][role] = {"n": len(v), "median": float(np.median(vals)), "min": min(vals), "max": max(vals), "target": target.get(role),
                                 "cues": [{"cue": i, "lufs": m, "voiceTrimmed": t} for i, m, t in v]}
        trimmed = [i for i, _, t in v if t]
        print(f"  {role:8s} n={len(v):2d} median {np.median(vals):6.1f} min {min(vals):6.1f} max {max(vals):6.1f} target {target.get(role)}"
              + (f"  (voice-trimmed: {', '.join(trimmed)})" if trimmed else ""))

    sfx_path = mixdir / "sfx.wav"
    voice_path = a.voice or L.get("voice")
    rc = 0
    if voice_path and sfx_path.exists():
        s = S.decode(sfx_path)
        v = S.decode(voice_path)
        n = min(len(s), len(v))
        W, H = int(0.4 * S.SR), int(0.1 * S.SR)
        starts = np.arange(0, n - W, H)
        lv = S.window_loudness(S.kweight(v[:n].astype(np.float64)), starts, W)
        lx = S.window_loudness(S.kweight(s[:n].astype(np.float64)), starts, W)
        act = (lv > -45) & (lx > -70)
        d = (lx - lv)[act]
        close = int((d > -a.margin_db).sum())
        if len(d):
            at = float(starts[act][d.argmax()] / S.SR)
            report["clarity"] = {"windowsWithEffectsDuringSpeech": int(act.sum()), "medianEffectsMinusVoiceDb": round(float(np.median(d)), 1),
                                 "maxEffectsMinusVoiceDb": round(float(d.max()), 1), "maxAtSec": round(at, 2), "windowsWithinMargin": close}
            print(f"VOICE CLARITY: {int(act.sum())} windows with effects during speech; effects minus voice: median {np.median(d):.1f} dB, "
                  f"max {d.max():.1f} dB at {at:.2f} s; windows within {a.margin_db:g} dB of the voice: {close}")
        else:
            report["clarity"] = {"windowsWithEffectsDuringSpeech": 0, "windowsWithinMargin": 0}
            print("VOICE CLARITY: no window has effects during speech")
        if close:
            print("FAIL: effects come within the margin of the voice")
            rc = 1
    else:
        print("VOICE CLARITY: skipped (no voice file or no sfx.wav)")
    if a.out:
        S.write_json(a.out, report)
    return rc


if __name__ == "__main__":
    sys.exit(main())

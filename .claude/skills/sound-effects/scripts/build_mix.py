#!/usr/bin/env python3
"""Build the sound-effects mix from a plan, the voice track and an optional music bed.

What it does, in order:
  1. Reads plan.json (see PLAN-FORMAT.md). Every cue names the frame its movement happens (code-derived), what moves,
     its exact hit count and hit frames, and one bank sound (run fit.py first to choose them).
  2. Refuses anything that is not a bank sound: each file is re-hashed and must match a bank.json entry (and not be
     in banned.json).
  3. Places every hit so the sound's audible onset (or its peak, for swooshes that swell with a camera move) lands on
     the hit frame. Sounds are never stretched, filtered or limited.
  4. Matches each sound to its role's perceived loudness (K-weighted, loudest 100 ms) and trims any cue that comes
     within 6 dB of the voice around it, so effects never fight speech. No limiter, compressor or auto ducking.
  5. Optionally adds a music bed held a fixed number of LU under the voice (default 12), with start offset and loop.
  6. Checks the rules: exact counts, nothing audible more than 1.5 frames before its movement, tails end by the
     movement's end, one riser at most (only on the cue the plan names), repeats declared and spaced, never the same
     sound on neighbouring cues, no cascade faster than 12 hits a second.
If any rule fails it prints every problem, writes only sound-ledger.json (so you can inspect it), refuses to write
mix.wav and exits 1.

  build_mix.py plan.json --voice voice.wav --out mix_dir
Writes mix_dir/mix.wav (voice + effects + music), sfx.wav (effects alone), music.wav and sound-ledger.json.
"""
import argparse
import pathlib
import sys
import time

import numpy as np

import sfxlib as S


def build_music(m: dict, base: pathlib.Path, n_samples: int, problems: list[str]):
    path = pathlib.Path(m["file"])
    if not path.is_absolute() and not path.exists():
        path = base / path
    if not path.exists():
        problems.append(f"music file not found: {m['file']}")
        return None, None
    start = float(m.get("startSec", 0.0))
    src = S.decode(path, start=start)
    loop = m.get("loop")
    clock_max = start + n_samples / S.SR
    rec = None
    if loop:
        a, b = int(round((loop["startSec"] - start) * S.SR)), int(round((loop["endSec"] - start) * S.SR))
        X = int(float(loop.get("crossfadeSec", 0.05)) * S.SR)
        if not (0 <= a < b <= len(src)) or b - a <= 2 * X:
            problems.append("music.loop must lie inside the file after startSec and be longer than twice its crossfade")
            return None, None
        body = src[a:b]
        acc = src[:b].astype(np.float64)
        t = np.linspace(0, np.pi / 2, X)
        ga, gb = np.cos(t)[:, None], np.sin(t)[:, None]
        while len(acc) < n_samples:
            tail, head = acc[-X:], body[:X].astype(np.float64)
            acc = np.vstack([acc[:-X], tail * ga + head * gb, body[X:]])
        src = acc.astype(np.float32)
        clock_max = loop["endSec"]
        rec = {"startSec": loop["startSec"], "endSec": loop["endSec"], "crossfadeSec": X / S.SR}
    if len(src) < n_samples:
        problems.append("music is shorter than the video: declare music.loop")
        return None, None
    mus = src[:n_samples].copy()
    ex = m.get("excludeFromSec")
    if ex is not None and clock_max >= float(ex):
        problems.append(f"music reaches the excluded section: {clock_max:.3f} s >= {ex} s")
    fo = min(len(mus), int(float(m.get("fadeOutSec", 0.8)) * S.SR))
    if fo:
        mus[-fo:] *= np.linspace(1, 0, fo)[:, None]
    return mus, {"file": str(path), "sha256": S.sha256_file(path), "startSec": start, "loop": rec, "maxMusicClockSec": clock_max}


def voice_trims(voice: np.ndarray, pieces: dict, margin_db: float):
    """Find speech moments where the effects come within 6 dB of the voice (400 ms windows, 100 ms hop, speech above
    -45 LUFS) and trim the loudest cue in each, in 0.5 dB steps, until the window sits margin_db under the voice."""
    n = len(voice)
    W, H = int(0.4 * S.SR), int(0.1 * S.SR)
    if n <= W:
        return {}
    starts = np.arange(0, n - W, H)
    lv = S.window_loudness(S.kweight(voice.astype(np.float64)), starts, W)
    speech = lv > -45
    trim: dict[str, float] = {}
    for _ in range(80):
        tot = np.zeros((n, 2))
        for cid, plist in pieces.items():
            g = 10 ** (trim.get(cid, 0.0) / 20)
            for st, k in plist:
                en = min(n, st + len(k))
                if st < n and en > st:
                    tot[st:en] += k[: en - st] * g
        lx = S.window_loudness(tot, starts, W)
        d = lx - lv
        bad = np.where(speech & (lx > -70) & (d > -6.0))[0]
        if not len(bad):
            break
        w = bad[np.argmax(d[bad])]
        a, z = starts[w], starts[w] + W
        contrib = {}
        for cid, plist in pieces.items():
            e = 0.0
            for st, k in plist:
                lo, hi = max(a, st), min(z, st + len(k))
                if hi > lo:
                    e += float(np.sum(k[lo - st:hi - st] ** 2))
            contrib[cid] = e * 10 ** (trim.get(cid, 0.0) / 10)
        top = max(contrib, key=contrib.get)
        if contrib[top] <= 0:
            break
        step = max(0.5, np.ceil((d[w] + margin_db) * 2) / 2)
        trim[top] = trim.get(top, 0.0) - step
    return trim


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("plan", help="plan.json with sounds chosen (run fit.py first)")
    ap.add_argument("--voice", required=True, help="voice track (any audio or video file ffmpeg can read)")
    ap.add_argument("--out", required=True, help="output folder")
    ap.add_argument("--bank", help="path to bank.json (default: ../bank/bank.json)")
    ap.add_argument("--no-voice-trim", action="store_true", help="skip the automatic trim of cues within 6 dB of the voice")
    ap.add_argument("--margin-db", type=float, default=6.2, help="how far under the voice a trimmed window ends up (default 6.2)")
    a = ap.parse_args(argv)

    plan_path = pathlib.Path(a.plan).resolve()
    out = pathlib.Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    plan = S.read_json(plan_path)
    bank = S.Bank(a.bank)
    fps = float(plan["fps"])
    voice_raw = S.decode(a.voice)
    total = int(plan.get("totalFrames") or int(round(len(voice_raw) / S.SR * fps)))
    N = int(round(total / fps * S.SR))
    voice = voice_raw[:N]
    voice = np.pad(voice, ((0, N - len(voice)), (0, 0)))

    problems = S.validate_plan(plan, bank, stage="build", total_frames=total)
    role_lufs = {**S.DEFAULT_ROLE_LUFS, **(plan.get("roleLoudness") or {})}
    win = float(plan.get("roleWindowSec", S.ROLE_WINDOW_SEC))
    riser_only = (plan.get("riserPolicy") or {}).get("onlyCue")

    # 1. resolve and re-hash every sound; prepare each clip once
    clips: dict[int, dict] = {}
    cue_sound: dict[str, int] = {}
    for c in plan["cues"]:
        cid = c["id"]
        n = c.get("sound")
        if c.get("soundFile"):
            fn, why = bank.resolve_file(c["soundFile"])
            if fn is None:
                problems.append(f"{cid}: {why}")
                continue
            if n is not None and int(n) != fn:
                problems.append(f"{cid}: soundFile is bank #{fn} but sound says #{n}")
                continue
            n = fn
        if n is None:
            continue
        n = int(n)
        ok, why = bank.check_number(n)
        if not ok:
            problems.append(f"{cid}: {why}")
            continue
        cue_sound[cid] = n
        if n not in clips:
            role = bank.role_of(n)
            cl = S.prepare_clip(bank.file_of(n), role)
            cl["role"] = role
            cl["gainDb"] = round(role_lufs[role] - cl["momentaryUnity"], 2) if role in role_lufs else 0.0
            if win != S.ROLE_WINDOW_SEC:
                cl["gainDb"] = round(role_lufs[role] - S.momentary_lufs(cl["x"], win), 2)
            clips[n] = cl

    # 2. place every hit (unity trim first; the voice trim is applied after)
    placements: dict[str, dict] = {}
    for c in plan["cues"]:
        cid = c["id"]
        if cid not in cue_sound:
            continue
        n = cue_sound[cid]
        cl = clips[n]
        role = cl["role"]
        hits = c.get("hits") or [c["frame"]]
        count = c.get("count", len(hits))
        align = c.get("align", "onset")
        align_pt = cl["peakSec"] if align == "peak" else cl["onsetSec"]
        typing = role == "typing"
        pz = cl["pulses"]
        if not typing:
            allowed_multi = (c.get("multiPulse") and count == 1) or (role == "riser" and cid == riser_only)
            if len(pz) > 2 and not allowed_multi:
                problems.append(f"{cid}: bank #{n} has {len(pz)} heard pulses in one clip {pz} (max 2: one blip, or a press and its release). "
                                f"A cue with count 1 may declare multiPulse with a reason")
            if len(pz) > 2 and c.get("multiPulse") and count != 1:
                problems.append(f"{cid}: a many-pulse sound cannot go on a counted list of {count}")
            if count >= 2 and len(pz) == 2 and pz[1] - pz[0] > 0.06:
                problems.append(f"{cid}: a counted list needs one blip per item, but bank #{n} is two blips {pz} apart")
        t_start = ((c.get("motionStart", c["frame"])) / fps) if (align == "peak") else None
        rows = []
        for i, h in enumerate(hits):
            t = h / fps
            st = int(round((t - align_pt) * S.SR))
            if st < 0:
                problems.append(f"{cid}#{i}: the sound would start {-st / S.SR:.2f} s before the video begins")
                continue
            on = st / S.SR + cl["onsetSec"]
            t_early = t_start if t_start is not None else t
            if on < t_early - S.EARLY_FRAMES / fps - 1e-6 and not (role == "riser" and cid == riser_only):
                problems.append(f"{cid}#{i}: audible {(t_early - on) * fps:.1f} frames before its movement")
            end = st + len(cl["x"])
            if end > N:
                problems.append(f"{cid}#{i}: the sound runs {(end - N) / S.SR:.2f} s past the end of the video")
            rows.append({"frame": h, "eventSec": round(t, 4), "startSample": st, "startSec": round(st / S.SR, 4),
                         "endSec": round(end / S.SR, 4), "onsetSec": round(on, 4)})
        if rows:
            last_end = rows[-1]["endSec"]
            motion_end = (c["motionEnd"] + 1) / fps
            if last_end > motion_end + S.TAIL_FRAMES / fps + 1e-6:
                problems.append(f"{cid}: tail outlasts the movement by {(last_end - motion_end) * fps:.1f} frames")
            if c.get("cutFrame") is not None and last_end > c["cutFrame"] / fps + S.TAIL_FRAMES / fps + 1e-6:
                problems.append(f"{cid}: runs {(last_end - c['cutFrame'] / fps) * fps:.1f} frames past the cut")
        placements[cid] = {"cue": c, "n": n, "role": role, "hits": rows, "count": count, "align": align}

    # 3. distribution (repeats, neighbours) from the placed times
    drows = [{"id": cid, "sound": p["n"], "role": p["role"], "t0": p["hits"][0]["eventSec"], "t1": p["hits"][-1]["eventSec"]}
             for cid, p in placements.items() if p["hits"]]
    dist_pr, repeats = S.check_distribution(drows, plan)
    problems += dist_pr

    # 4. levels: voice-clarity trims, computed on K-weighted pieces
    pieces = {}
    for cid, p in placements.items():
        cl = clips[p["n"]]
        base = cl["gainDb"] + float(p["cue"].get("gainTrimDb", 0.0))
        pad = np.vstack([S.apply_gain(cl["x"], base), np.zeros((int(0.5 * S.SR), 2), np.float32)])
        k = S.kweight(pad.astype(np.float64)).astype(np.float32)
        pieces[cid] = [(h["startSample"], k) for h in p["hits"]]
    trims = {} if a.no_voice_trim else voice_trims(voice, pieces, a.margin_db)

    # 5. render the effects stem
    sfx = np.zeros((N, 2), np.float32)
    cues_out = []
    for c in plan["cues"]:
        p = placements.get(c["id"])
        if p is None:
            continue
        cl = clips[p["n"]]
        e = bank.entries[p["n"]]
        applied = round(cl["gainDb"] + float(c.get("gainTrimDb", 0.0)) + trims.get(c["id"], 0.0), 3)
        x = S.apply_gain(cl["x"], applied)
        for h in p["hits"]:
            st = h["startSample"]
            en = min(N, st + len(x))
            sfx[st:en] += x[:en - st]
        cues_out.append({"id": c["id"], "what": c["what"], "frame": c["frame"], "motionStart": c.get("motionStart"), "motionEnd": c["motionEnd"],
                         "sound": p["n"], "name": e["name"], "role": p["role"], "type": e.get("type"), "file": e["file"], "sha256": e["sha256"],
                         "align": p["align"], "count": p["count"], "gainDb": cl["gainDb"], "gainTrimDb": float(c.get("gainTrimDb", 0.0)),
                         "voiceTrimDb": trims.get(c["id"], 0.0), "appliedGainDb": applied, "pulsesPerHit": len(cl["pulses"]),
                         "pulseTimes": cl["pulses"], "fit": c.get("fit"), "choice": c.get("choice"),
                         "alsoUsedBy": sorted({i for r in repeats if r["sound"] == p["n"] for i in r["cues"]} - {c["id"]}),
                         "hits": p["hits"], "motionEndSec": round((c["motionEnd"] + 1) / fps, 4), "reason": c.get("reason")})
    peak_sfx = float(20 * np.log10(np.abs(sfx).max() + 1e-12))

    # 6. music
    music_rec, mus = None, np.zeros_like(voice)
    vI = S.integrated_lufs(voice)
    if plan.get("music"):
        m = plan["music"]
        mus_raw, music_rec = build_music(m, plan_path.parent, N, problems)
        if mus_raw is not None:
            under = float(m.get("underVoiceLU", 12.0))
            target = vI - under if vI > -70 else float(m.get("targetLufs", -30.0))
            mI0 = S.integrated_lufs(mus_raw)
            mus = mus_raw * np.float32(10 ** ((target - mI0) / 20))
            music_rec.update({"underVoiceLU": under, "targetLufs": round(target, 2), "measuredLufs": round(S.integrated_lufs(mus), 2)})

    mix = voice + sfx + mus
    peak = float(20 * np.log10(np.abs(mix).max() + 1e-12))
    if peak > -1.0:
        problems.append(f"mix peak {peak:.2f} dBFS is too hot (limit -1 dBFS). Nothing is limited; lower the voice or the music")

    ledger = {"plan": str(plan_path), "bank": str(bank.path), "voice": str(pathlib.Path(a.voice).resolve()), "fps": fps, "sampleRate": S.SR,
              "frames": total, "cues": cues_out, "repeats": repeats, "roleLoudness": role_lufs, "voiceTrims": trims,
              "music": music_rec, "problems": problems, "hearing": "PENDING. Numeric checks only; not a listening approval."}
    S.write_json(out / "sound-ledger.json", ledger)
    n_hits = sum(len(c["hits"]) for c in cues_out)
    print(f"{len(cues_out)} cues, {n_hits} hits, voice integrated {vI:.1f} LUFS, mix peak {peak:.1f} dBFS, voice trims on {len(trims)} cues")
    if problems:
        stale = [f for f in ("mix.wav", "sfx.wav", "music.wav") if (out / f).exists()]
        if stale:
            d = out / ("stale-" + time.strftime("%Y%m%d-%H%M%S"))
            d.mkdir()
            for f in stale:
                (out / f).replace(d / f)
            print(f"moved the previous outputs to {d}")
        print(f"problems: {len(problems)}. mix.wav NOT written")
        for p in problems:
            print("  -", p)
        return 1
    S.write_wav(out / "sfx.wav", sfx)
    S.write_wav(out / "mix.wav", mix)
    if music_rec:
        S.write_wav(out / "music.wav", mus)
    ledger["files"] = {"mix": "mix.wav", "sfx": "sfx.wav", "mixSha256": S.sha256_file(out / "mix.wav"), "sfxSha256": S.sha256_file(out / "sfx.wav"),
                       "samplePeakDbfs": round(peak, 2), "sfxPeakDbfs": round(peak_sfx, 2), "integratedLufs": round(S.integrated_lufs(mix), 2)}
    S.write_json(out / "sound-ledger.json", ledger)
    print("problems: 0")
    print(f"wrote {out / 'mix.wav'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

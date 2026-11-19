#!/usr/bin/env python3
"""Audit the encoded final video against the plan and the sound ledger. Lists every failure; exits 1 if any.

Why: a mix can be right on paper and wrong after encoding, or drift from the plan while being edited. This tool
checks the thing that will actually be watched.

Checks
  PLAN       the plan still passes every plan rule and matches the ledger (same cues, counts, hit frames, sounds).
  BANK       every sound used is re-hashed now and must match its bank.json entry (not banned).
  FILES      sfx.wav and mix.wav are the files the ledger recorded (hashes).
  NULL       the effects stem is rebuilt from the ledger (every clip re-made from its bank file and gain) and must
             match sfx.wav to below -70 dBFS.
  TIMING     each hit is found in the stem and in the encoded final's audio (final minus the known voice and music),
             must match its clip, and its onset (or peak, for peak-aligned cues) must land within 1 frame of its
             hit frame.
  ENCODED    the final's audio matches mix.wav (correlation), and the video has the planned frame count.
  COUNTS     each cue played alone has exactly count x pulses-per-hit heard pulses ("4 blips and only 4 blips").
  STRAY      nothing above -60 dBFS in the effects stem outside the cues.
  RISER      at most one riser, on the cue the plan names, single hit, peak-aligned.
  DISTRIBUTION  repeats declared and spaced, never the same sound on neighbouring cues.
  PICTURE    the encoded picture visibly changes within 2 frames of every hit (whole frame, then a block re-check at
             540x960 for small events). Use --skip-picture for audio-only deliveries.

  audit_mix.py final.mp4 --plan plan.json --ledger mix_dir/sound-ledger.json --out audit.json
Numbers only: this measures alignment, it is not a listening approval.
"""
import argparse
import pathlib
import subprocess
import sys

import numpy as np
from scipy.signal import correlate

import sfxlib as S

PW, PH = 108, 192
LW, LH, BLK = 540, 960, 8


def video_gray(path, w, h):
    p = subprocess.Popen([S.ffmpeg_bin(), "-v", "error", "-i", str(path), "-vf", f"scale={w}:{h},format=gray", "-f", "rawvideo", "-"],
                         stdout=subprocess.PIPE)
    return p


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("video", help="the encoded final (mp4)")
    ap.add_argument("--plan", required=True)
    ap.add_argument("--ledger", required=True, help="sound-ledger.json written by build_mix.py (its folder holds sfx.wav and mix.wav)")
    ap.add_argument("--out", required=True, help="where to write the report json")
    ap.add_argument("--bank", help="path to bank.json (default: ../bank/bank.json)")
    ap.add_argument("--skip-picture", action="store_true", help="skip the picture checks")
    ap.add_argument("--min-encoded-corr", type=float, default=0.8, help="lowest clip correlation accepted in the lossy encoded audio (default 0.8)")
    a = ap.parse_args(argv)

    bank = S.Bank(a.bank)
    plan = S.read_json(a.plan)
    L = S.read_json(a.ledger)
    mixdir = pathlib.Path(a.ledger).resolve().parent
    fps = float(L["fps"])
    fail: list[str] = []

    # PLAN
    if L.get("problems"):
        fail.append(f"PLAN the ledger itself lists {len(L['problems'])} build problems (first: {L['problems'][0]})")
    for p in S.validate_plan(plan, bank, stage="audit", total_frames=L["frames"]):
        fail.append(f"PLAN {p}")
    pc = {c["id"]: c for c in plan["cues"]}
    lc = {c["id"]: c for c in L["cues"]}
    for cid in sorted(set(pc) ^ set(lc)):
        fail.append(f"PLAN cue {cid} is in the {'plan' if cid in pc else 'ledger'} only")
    for cid in sorted(set(pc) & set(lc)):
        hp = pc[cid].get("hits") or [pc[cid]["frame"]]
        hl = [h["frame"] for h in lc[cid]["hits"]]
        if pc[cid].get("count", len(hp)) != lc[cid]["count"] or hp != hl:
            fail.append(f"PLAN {cid}: plan says count {pc[cid].get('count', len(hp))} hits {hp}, ledger has count {lc[cid]['count']} hits {hl}")
        if pc[cid].get("sound") is not None and int(pc[cid]["sound"]) != lc[cid]["sound"]:
            fail.append(f"PLAN {cid}: plan sound #{pc[cid]['sound']} but the ledger mixed #{lc[cid]['sound']}")

    # BANK (re-hash now)
    clips = {}
    for c in L["cues"]:
        ok, why = bank.check_number(c["sound"])
        if not ok:
            fail.append(f"BANK {c['id']}: {why}")
            continue
        if bank.entries[c["sound"]]["sha256"] != c["sha256"]:
            fail.append(f"BANK {c['id']}: ledger sha256 does not match the bank entry for #{c['sound']}")
        key = (c["sound"], c["appliedGainDb"])
        if key not in clips:
            cl = S.prepare_clip(bank.file_of(c["sound"]), c["role"])
            clips[key] = (S.apply_gain(cl["x"], c["appliedGainDb"]), cl)
    if any(f.startswith("BANK") for f in fail):
        return finish(a, fail, {}, L)

    # FILES
    files = L.get("files") or {}
    for key, name in (("sfxSha256", "sfx.wav"), ("mixSha256", "mix.wav")):
        p = mixdir / name
        if not p.exists():
            fail.append(f"FILES {name} is missing next to the ledger")
        elif files.get(key) != S.sha256_file(p):
            fail.append(f"FILES {name} is not the file the ledger recorded")
    if not (mixdir / "sfx.wav").exists() or not (mixdir / "mix.wav").exists():
        return finish(a, fail, {}, L)
    stem = S.decode(mixdir / "sfx.wav")
    mixw = S.decode(mixdir / "mix.wav")

    # NULL
    recon = np.zeros_like(stem)
    for c in L["cues"]:
        x = clips[(c["sound"], c["appliedGainDb"])][0]
        for h in c["hits"]:
            st = h["startSample"]; en = min(len(recon), st + len(x))
            recon[st:en] += x[:en - st]
    null_db = float(20 * np.log10(np.abs(stem - recon).max() + 1e-12))
    if null_db > -70:
        fail.append(f"NULL the stem differs from the ledger rebuild by {null_db:.1f} dBFS")
    recon_m = recon.mean(axis=1)
    mono = stem.mean(axis=1)

    # ENCODED audio alignment
    enc_ok = False
    resid = None
    try:
        fin = S.decode(a.video)
        n = min(len(fin), len(mixw))
        seg = min(n, 30 * S.SR)
        xc = correlate(fin[:seg].mean(axis=1), mixw[:seg].mean(axis=1), mode="full", method="fft")
        lags = np.arange(-(seg - 1), seg)
        sel = np.abs(lags) <= 4800
        lag = int(lags[sel][np.argmax(xc[sel])])
        if lag > 0:
            fin = fin[lag:]
        elif lag < 0:
            fin = np.vstack([np.zeros((-lag, 2), np.float32), fin])
        n = min(len(fin), len(mixw))
        corr = float(np.corrcoef(fin[:n].ravel(), mixw[:n].ravel())[0, 1])
        if corr < 0.999:
            fail.append(f"ENCODED the final's audio differs from mix.wav (correlation {corr:.5f}, lag {lag} samples)")
        if abs(len(fin) - len(mixw)) > 4096 + S.SR // 50:
            fail.append(f"ENCODED the final's audio is {len(fin) / S.SR:.2f} s, the mix is {len(mixw) / S.SR:.2f} s")
        resid = (fin[:n] - mixw[:n] + stem[:n]).mean(axis=1)
        enc_ok = True
    except Exception as e:  # noqa: BLE001
        fail.append(f"ENCODED could not decode the audio of {a.video}: {e}")
        corr, lag = None, None

    # TIMING and COUNTS
    rows, counts = [], []
    for c in L["cues"]:
        x, cl = clips[(c["sound"], c["appliedGainDb"])]
        xm = x.mean(axis=1)
        peak_align = c.get("align") == "peak"
        off = cl["peakSec"] if peak_align else cl["onsetSec"]
        starts = [h["startSample"] for h in c["hits"]]
        if c["role"] != "typing" and not peak_align:
            t0 = min(starts); t1 = max(starts)
            alone = np.zeros(t1 - t0 + len(x) + int(0.05 * S.SR), np.float32).reshape(-1, 1).repeat(2, 1)
            for st in starts:
                alone[st - t0:st - t0 + len(x)] += x
            nh = len(S.pulses(alone))
            exp = c["count"] * len(cl["pulses"])
            ok = nh == exp and (len(cl["pulses"]) <= 2 or c["count"] == 1)
            counts.append({"cue": c["id"], "expected": exp, "heardAlone": nh, "pass": ok})
            if not ok:
                fail.append(f"COUNTS {c['id']}: {nh} audible pulses alone, expected {exp}")
        for i, h in enumerate(c["hits"]):
            st = starts[i]
            nb = [abs(st - o) for j, o in enumerate(starts) if j != i]
            lag_max = int(min(3 / fps * S.SR, 0.45 * min(nb) if nb else 1e9))
            a0 = max(0, st - lag_max); a1 = min(len(mono), st + len(xm) + lag_max)
            own = np.zeros(a1 - a0); o0 = st - a0; own[o0:o0 + len(xm)] = xm[:len(own) - o0]
            row = {"cue": c["id"], "hit": i, "sound": c["sound"], "frame": h["frame"]}
            for label, src, thr in (("stem", mono, 0.99), ("encoded", resid, a.min_encoded_corr)):
                if src is None:
                    continue
                if a1 - a0 < len(xm):
                    fail.append(f"TIMING {c['id']}#{i}: outside the {label}")
                    continue
                iso = src[a0:a1] - (recon_m[a0:a1] - own)
                cc = correlate(iso, xm, mode="valid", method="fft")
                k = int(np.argmax(cc)) + a0 - st
                found = st + k
                land = (found / S.SR + off) * fps
                d = land - h["frame"]
                seg_iso = iso[found - a0:found - a0 + len(xm)]
                cor = float(cc.max() / (np.sqrt(np.sum(xm ** 2) * np.sum(seg_iso ** 2)) + 1e-12))
                row[label] = {"landMinusHitFrames": round(d, 2), "correlation": round(cor, 3)}
                if abs(d) > 1.0:
                    fail.append(f"TIMING {c['id']}#{i} ({label}): lands {d:+.2f} frames from its hit")
                if cor < thr:
                    fail.append(f"TIMING {c['id']}#{i} ({label}): does not match its clip (correlation {cor:.3f})")
            rows.append(row)

    # STRAY
    mask = np.zeros(len(mono), bool)
    for c in L["cues"]:
        ln = len(clips[(c["sound"], c["appliedGainDb"])][0])
        for h in c["hits"]:
            mask[h["startSample"]:h["startSample"] + ln + 1] = True
    stray = np.abs(stem).max(axis=1)[~mask]
    stray_db = float(20 * np.log10(stray.max() + 1e-12)) if len(stray) else -200.0
    if stray_db >= -60:
        fail.append(f"STRAY sound {stray_db:.1f} dBFS outside the cues")

    # RISER and DISTRIBUTION from the ledger
    riser_policy = plan.get("riserPolicy") or {}
    risers = [c for c in L["cues"] if c["role"] == "riser"]
    if len(risers) > 1:
        fail.append(f"RISER more than one riser: {[c['id'] for c in risers]}")
    for c in risers:
        if c["id"] != riser_policy.get("onlyCue") or c["count"] != 1 or c.get("align") != "peak":
            fail.append(f"RISER {c['id']}: bank #{c['sound']} is a riser and may only be the declared riser cue {riser_policy.get('onlyCue')!r} (single hit, peak-aligned)")
    drows = [{"id": c["id"], "sound": c["sound"], "role": c["role"], "t0": c["hits"][0]["eventSec"], "t1": c["hits"][-1]["eventSec"]} for c in L["cues"]]
    dpr, repeats = S.check_distribution(drows, plan)
    fail += dpr

    # PICTURE and video frame count
    pic = {}
    if not a.skip_picture:
        pic = picture_checks(a.video, plan, L, rows, fail, fps)

    return finish(a, fail, {"hits": rows, "counts": counts, "repeats": repeats, "nullTestDbfs": round(null_db, 1),
                            "strayOutsideCuesDbfs": round(stray_db, 1), "encoded": {"correlationWithMix": corr, "lagSamples": lag}, "picture": pic}, L)


def picture_checks(video, plan, L, rows, fail, fps):
    reg = plan.get("graphicsRegion") or [0.0, 1.0]
    r0, r1 = int(reg[0] * PH), int(reg[1] * PH)
    p = video_gray(video, PW, PH)
    frames = []
    while True:
        buf = p.stdout.read(PW * PH)
        if len(buf) < PW * PH:
            break
        frames.append(np.frombuffer(buf, np.uint8).reshape(PH, PW)[r0:r1].astype(np.float32))
    p.stdout.close(); p.wait()
    if len(frames) != L["frames"]:
        fail.append(f"ENCODED the video has {len(frames)} frames, the plan has {L['frames']}")
    diff = np.zeros(len(frames))
    for f in range(1, len(frames)):
        diff[f] = np.abs(frames[f] - frames[f - 1]).mean()
    small = []
    out = []
    for r in rows:
        E = int(r["frame"])
        lo = max(1, E - 8)
        base = float(np.median(diff[lo:max(lo + 1, E - 2)])) if len(diff) > lo else 0.0
        win = diff[max(1, E - 2):min(len(diff), E + 3)]
        rise = float(win.max()) if len(win) else 0.0
        kind = "moves" if rise > max(base * 1.5, base + 0.15) or rise > 1.5 else "small"
        r["picture"] = kind
        if kind == "small":
            small.append(r)
        out.append({"cue": r["cue"], "hit": r["hit"], "picture": kind, "base": round(base, 3), "near": round(rise, 3)})
    if small:
        need = set()
        for r in small:
            need |= set(range(max(0, r["frame"] - 9), r["frame"] + 4))
        p = video_gray(video, LW, LH)
        keep = {}
        fi = 0
        while True:
            buf = p.stdout.read(LW * LH)
            if len(buf) < LW * LH:
                break
            if fi in need:
                keep[fi] = np.frombuffer(buf, np.uint8).reshape(LH, LW).astype(np.float32)
            fi += 1
        p.stdout.close(); p.wait()
        rr0, rr1 = int(reg[0] * LH) // BLK * BLK, int(reg[1] * LH) // BLK * BLK
        cw = LW // BLK * BLK

        def blocks(f):
            if f not in keep or f - 1 not in keep:
                return None
            d = np.abs(keep[f][rr0:rr1, :cw] - keep[f - 1][rr0:rr1, :cw])
            return d.reshape((rr1 - rr0) // BLK, BLK, cw // BLK, BLK).mean(axis=(1, 3))
        for r in small:
            E = r["frame"]
            bb = [x for x in (blocks(f) for f in range(E - 8, E - 2)) if x is not None]
            nn = [x for x in (blocks(f) for f in range(E - 2, E + 3)) if x is not None]
            if not bb or not nn or rr1 <= rr0:
                r["picture"] = "none"
                fail.append(f"PICTURE {r['cue']}#{r['hit']}: no frames to check")
                continue
            base = np.median(np.stack(bb), axis=0); near = np.max(np.stack(nn), axis=0)
            rise = near - base
            k = np.unravel_index(int(np.argmax(rise)), rise.shape)
            if rise[k] >= 3.0 and near[k] >= 2 * base[k]:
                r["picture"] = "moves-local"
            else:
                r["picture"] = "none"
                fail.append(f"PICTURE {r['cue']}#{r['hit']}: no visible change near frame {E} at either scale (best block {base[k]:.2f} -> {near[k]:.2f})")
    return out


def finish(a, fail, body, L):
    rep = {"video": str(a.video), "ledger": str(a.ledger), **body, "failures": fail, "pass": not fail,
           "hearing": "PENDING. Alignment is measured, not heard."}
    S.write_json(a.out, rep)
    print(f"cues {len(L['cues'])}, hits {sum(len(c['hits']) for c in L['cues'])}")
    if body:
        print(f"null test {body['nullTestDbfs']} dBFS, stray {body['strayOutsideCuesDbfs']} dBFS")
    print(f"FAILURES {len(fail)}")
    for f in fail:
        print("  -", f)
    print("PASS" if not fail else "FAIL")
    return 0 if not fail else 1


if __name__ == "__main__":
    sys.exit(main())

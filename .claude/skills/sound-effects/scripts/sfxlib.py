"""Shared helpers for the sound-effects toolkit (not run directly).

Everything the command line tools have in common lives here: reading the bank and
re-hashing its files, decoding audio through ffmpeg, perceived-loudness measurement
(K-weighted, ITU-R BS.1770 style), placing a sound clip, counting its audible pulses,
validating a plan, and the repeat/neighbour/riser distribution rules. Keeping one copy
means the builder and the auditor can never disagree about how a clip is made.

Only numpy, scipy and the ffmpeg command line are needed.
"""
from __future__ import annotations

import hashlib
import json
import os
import pathlib
import shutil
import subprocess
import sys

import numpy as np
from scipy.signal import lfilter

SR = 48000
HERE = pathlib.Path(__file__).resolve().parent
DEFAULT_BANK = HERE.parent / "bank" / "bank.json"

# Which job each bank type does in the mix. The role decides the loudness target and the repeat spacing.
ROLE_OF_TYPE = {
    "click": "press", "press": "press", "sequence": "press",
    "pop": "pop", "tonal": "pop", "other": "pop",
    "swoosh": "swoosh", "camera": "swoosh", "sweep": "swoosh",
    "riser": "riser",
    "blip": "tick", "tick": "tick",
    "typing": "typing",
}
AIR_ROLES = {"swoosh"}
# Perceived-loudness targets (K-weighted momentary LUFS of the loudest 100 ms) after the clip is placed.
DEFAULT_ROLE_LUFS = {"swoosh": -24.4, "riser": -28.4, "pop": -29.3, "press": -29.4, "tick": -34.0, "typing": -38.0}
ROLE_WINDOW_SEC = 0.1
EARLY_FRAMES = 1.5      # nothing audible more than this many frames before its movement
TAIL_FRAMES = 3.0       # a sound may ring this many frames past the end of its movement
MAX_CASCADE_PER_SEC = 12.0
MIN_REPEAT_GAP_NO_REASON = 20.0


# ---------------------------------------------------------------- ffmpeg and audio i/o
def ffmpeg_bin(name: str = "ffmpeg") -> str:
    env = os.environ.get(name.upper())
    return env or shutil.which(name) or name


def decode(path, start: float | None = None, dur: float | None = None, ac: int = 2) -> np.ndarray:
    """Decode any audio or video file to float32 samples, shape (n, ac), at 48 kHz."""
    cmd = [ffmpeg_bin(), "-v", "error"]
    if start:
        cmd += ["-ss", f"{start:.6f}"]
    if dur is not None:
        cmd += ["-t", f"{dur:.6f}"]
    cmd += ["-i", str(path), "-map", "0:a:0", "-ar", str(SR), "-ac", str(ac), "-f", "f32le", "-"]
    r = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if r.returncode != 0:
        raise RuntimeError(f"ffmpeg could not decode {path}: {r.stderr.decode(errors='replace')[-300:]}")
    return np.frombuffer(r.stdout, "<f4").reshape(-1, ac).copy()


def write_wav(path, x: np.ndarray) -> None:
    """Write 32-bit float stereo WAV at 48 kHz (no normalising, no limiting)."""
    from scipy.io import wavfile
    wavfile.write(str(path), SR, np.asarray(x, np.float32))


def sha256_file(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def read_json(path):
    with open(path) as f:
        return json.load(f)


def write_json(path, obj) -> None:
    with open(path, "w") as f:
        json.dump(obj, f, indent=1)


# ---------------------------------------------------------------- the bank
class Bank:
    """The approved sounds. A file is usable only if its sha256 matches an entry and it is not banned."""

    def __init__(self, path=None):
        self.path = pathlib.Path(path or DEFAULT_BANK).resolve()
        if not self.path.exists():
            raise SystemExit(f"bank file not found: {self.path}")
        data = read_json(self.path)
        self.root = self.path.parent
        self.entries = {int(e["n"]): e for e in data["entries"]}
        self.by_sha = {e["sha256"]: int(e["n"]) for e in data["entries"]}
        self.banned_n: set[int] = set()
        self.banned_sha: set[str] = set()
        bj = self.root / "banned.json"
        if bj.exists():
            raw = read_json(bj)
            items = raw.get("banned", raw.get("entries", [])) if isinstance(raw, dict) else raw
            for it in items:
                if isinstance(it, int):
                    self.banned_n.add(it)
                elif isinstance(it, str):
                    if len(it) == 64:
                        self.banned_sha.add(it)
                    elif it.strip().isdigit():
                        self.banned_n.add(int(it))
                elif isinstance(it, dict):
                    if "n" in it:
                        self.banned_n.add(int(it["n"]))
                    if it.get("sha256"):
                        self.banned_sha.add(it["sha256"])
        self._hash_cache: dict[str, str] = {}

    def file_of(self, n: int) -> pathlib.Path:
        return self.root / self.entries[n]["file"]

    def role_of(self, n: int) -> str:
        return ROLE_OF_TYPE.get(self.entries[n].get("type", "other"), "pop")

    def hash_now(self, path) -> str:
        p = str(pathlib.Path(path).resolve())
        if p not in self._hash_cache:
            self._hash_cache[p] = sha256_file(p)
        return self._hash_cache[p]

    def is_banned(self, n: int | None = None, sha: str | None = None) -> bool:
        if n is not None and n in self.banned_n:
            return True
        if sha is None and n in self.entries:
            sha = self.entries[n]["sha256"]
        return sha in self.banned_sha

    def check_number(self, n) -> tuple[bool, str]:
        """Re-hash the bank file for entry n. Returns (ok, reason)."""
        if n not in self.entries:
            return False, f"bank number {n} is not in bank.json"
        p = self.file_of(n)
        if not p.exists():
            return False, f"bank file missing: {self.entries[n]['file']}"
        if self.hash_now(p) != self.entries[n]["sha256"]:
            return False, f"bank file changed since it was approved (sha256 mismatch): {self.entries[n]['file']}"
        if self.is_banned(n):
            return False, f"bank number {n} is on the banned list"
        return True, ""

    def resolve_file(self, path) -> tuple[int | None, str]:
        """Hash an arbitrary file; return (bank number or None, reason when refused)."""
        p = pathlib.Path(path)
        if not p.exists():
            return None, f"sound file not found: {path}"
        sha = self.hash_now(p)
        n = self.by_sha.get(sha)
        if n is None:
            return None, f"not a bank sound (sha256 matches no bank.json entry): {path}"
        if self.is_banned(n, sha):
            return None, f"bank number {n} is on the banned list: {path}"
        return n, ""


# ---------------------------------------------------------------- loudness
_B1, _A1 = [1.53512485958697, -2.69169618940638, 1.19839281085285], [1.0, -1.69065929318241, 0.73248077421585]
_B2, _A2 = [1.0, -2.0, 1.0], [1.0, -1.99004745483398, 0.99007225036621]


def kweight(x: np.ndarray) -> np.ndarray:
    """K-weighting filter (BS.1770, 48 kHz): high shelf then high pass."""
    return lfilter(_B2, _A2, lfilter(_B1, _A1, x, axis=0), axis=0)


def momentary_lufs(x: np.ndarray, win: float = ROLE_WINDOW_SEC) -> float:
    """Perceived loudness of the loudest `win`-second window of a stereo clip (K-weighted LUFS)."""
    W = max(1, int(win * SR))
    y = np.vstack([np.zeros((W, 2), np.float32), x, np.zeros((W, 2), np.float32)])
    pw = np.sum(kweight(y.astype(np.float64)) ** 2, axis=1)
    cs = np.concatenate([[0], np.cumsum(pw)])
    e = (cs[W:] - cs[:-W]) / W
    return float(-0.691 + 10 * np.log10(e.max() + 1e-15))


def integrated_lufs(x: np.ndarray) -> float:
    """Gated integrated loudness (BS.1770: 400 ms blocks, 75 percent overlap, -70 absolute and -10 relative gates)."""
    W, H = int(0.4 * SR), int(0.1 * SR)
    if len(x) < W:
        return -120.0
    pw = np.sum(kweight(x.astype(np.float64)) ** 2, axis=1)
    cs = np.concatenate([[0], np.cumsum(pw)])
    starts = np.arange(0, len(x) - W + 1, H)
    e = (cs[starts + W] - cs[starts]) / W
    l = -0.691 + 10 * np.log10(e + 1e-15)
    keep = l > -70
    if not keep.any():
        return -120.0
    rel = -0.691 + 10 * np.log10(np.mean(e[keep])) - 10
    keep = l > max(-70, rel)
    if not keep.any():
        return -120.0
    return float(-0.691 + 10 * np.log10(np.mean(e[keep])))


def window_loudness(k: np.ndarray, starts: np.ndarray, W: int) -> np.ndarray:
    """Loudness of each W-sample window of an already K-weighted stereo signal."""
    pw = np.sum(k ** 2, axis=1)
    cs = np.concatenate([[0], np.cumsum(pw)])
    return -0.691 + 10 * np.log10((cs[starts + W] - cs[starts]) / W + 1e-12)


# ---------------------------------------------------------------- clips
def trim_tail(x: np.ndarray, floor_db: float = -60.0) -> np.ndarray:
    """Cut trailing silence below floor_db relative to the clip peak."""
    env = np.abs(x).max(axis=1)
    if env.max() <= 0:
        return x
    idx = np.where(env > env.max() * 10 ** (floor_db / 20))[0]
    return x[: idx[-1] + 1]


def pulses(x: np.ndarray, win: float = 0.02) -> list[float]:
    """Heard pulses in a clip, in seconds. A pulse is a peak of the 20 ms loudness envelope within 10 dB of the clip
    peak, at least 35 ms from the last one, with a 6 dB dip between them. This counts what the ear hears as separate
    blips, not noise ripple inside one whoosh."""
    mm = np.abs(x).max(axis=1) if x.ndim == 2 else np.abs(x)
    w = max(1, int(win * SR))
    e = np.sqrt(np.convolve(mm ** 2, np.ones(w) / w, "same"))
    if len(e) == 0 or e.max() <= 0:
        return []
    d = (20 * np.log10(e / e.max() + 1e-12))[::48]
    pk: list[int] = []
    for i in range(1, len(d) - 1):
        if d[i] >= -10 and d[i] >= d[i - 1] and d[i] > d[i + 1]:
            if pk and (i - pk[-1]) < 35:
                if d[i] > d[pk[-1]]:
                    pk[-1] = i
                continue
            if pk and d[pk[-1]:i + 1].min() > max(d[i], d[pk[-1]]) - 6:
                if d[i] > d[pk[-1]]:
                    pk[-1] = i
                continue
            pk.append(i)
    return [round(q / 1000, 3) for q in pk]


def onset_threshold(role: str) -> float:
    return 0.03 if role == "typing" else 0.1


def prepare_clip(path, role: str) -> dict:
    """Decode a bank file and shape it the way the mix places it: 2 ms fade in, short fade out, trailing silence cut.
    Sounds are never stretched, cropped or processed otherwise. Returns the clip and where its onset and peak are."""
    x = decode(path)
    n = len(x)
    fi, fo = int(0.002 * SR), int(min(0.012, 0.25 * n / SR) * SR)
    if fi and n > fi:
        x[:fi] *= np.linspace(0, 1, fi)[:, None]
    if fo > 0 and n > fo:
        x[-fo:] *= np.linspace(1, 0, fo)[:, None]
    x = trim_tail(x)
    env = np.abs(x).max(axis=1)
    if env.max() <= 0:
        raise RuntimeError(f"{path} is silent")
    onset = int(np.where(env > env.max() * onset_threshold(role))[0][0])
    peak = int(env.argmax())
    return {"x": x, "onsetSec": onset / SR, "peakSec": peak / SR, "lengthSec": len(x) / SR,
            "pulses": pulses(x) if role != "typing" else [], "momentaryUnity": momentary_lufs(x)}


def apply_gain(x: np.ndarray, gain_db: float) -> np.ndarray:
    return x * np.float32(10 ** (gain_db / 20))


# ---------------------------------------------------------------- plan helpers
def parse_tiers(fit_list) -> list[tuple[int, int]]:
    """A fit list is ranked tiers; a nested list inside it is one tier of equally good sounds.
    Returns [(bank number, rank)] with rank 0 for the first tier."""
    out = []
    for rank, tier in enumerate(fit_list or []):
        for n in (tier if isinstance(tier, list) else [tier]):
            out.append((int(n), rank))
    return out


def is_typing_cue(cue: dict, bank: Bank) -> bool:
    n = cue.get("sound")
    if n is not None and int(n) in bank.entries:
        return bank.role_of(int(n)) == "typing"
    opts = parse_tiers((cue.get("fit") or {}).get("list"))
    return bool(opts) and all(bank.role_of(k) == "typing" for k, _ in opts if k in bank.entries)


def validate_plan(plan: dict, bank: Bank, stage: str = "build", total_frames: int | None = None) -> list[str]:
    """Structural and rule checks on a plan. stage is 'fit' (sounds not chosen yet), 'build' or 'audit'."""
    pr: list[str] = []
    fps = plan.get("fps")
    if not isinstance(fps, (int, float)) or fps <= 0:
        return ["plan.fps must be a positive number"]
    cues = plan.get("cues")
    if not isinstance(cues, list) or not cues:
        return ["plan.cues must be a non-empty list"]
    total = total_frames if total_frames is not None else plan.get("totalFrames")
    seen = set()
    risers = []
    riser_policy = plan.get("riserPolicy") or {}
    for c in cues:
        cid = c.get("id")
        if not cid or not isinstance(cid, str):
            pr.append(f"a cue has no id: {c}")
            continue
        if cid in seen:
            pr.append(f"{cid}: duplicate cue id")
        seen.add(cid)
        for k in ("frame", "motionEnd"):
            if not isinstance(c.get(k), int):
                pr.append(f"{cid}: '{k}' must be a whole frame number")
        if not c.get("what"):
            pr.append(f"{cid}: 'what' (what moves) is required")
        count = c.get("count", len(c.get("hits") or [1]))
        hits = c.get("hits") if c.get("hits") is not None else ([c["frame"]] if count == 1 and isinstance(c.get("frame"), int) else [])
        if not isinstance(count, int) or count < 1:
            pr.append(f"{cid}: count must be a whole number of 1 or more")
            continue
        if len(hits) != count:
            pr.append(f"{cid}: COUNT: {len(hits)} hits for {count} visible items")
        if any(not isinstance(h, int) for h in hits):
            pr.append(f"{cid}: hits must be whole frame numbers")
            continue
        if hits != sorted(hits):
            pr.append(f"{cid}: hits must be in time order")
        if total is not None and hits and (min(hits) < 0 or max(hits) >= total):
            pr.append(f"{cid}: a hit is outside the video (0 to {total - 1})")
        if hits and isinstance(c.get("motionEnd"), int) and c["motionEnd"] < max(hits):
            pr.append(f"{cid}: motionEnd {c['motionEnd']} is before its last hit {max(hits)}")
        align = c.get("align", "onset")
        if align not in ("onset", "peak"):
            pr.append(f"{cid}: align must be 'onset' or 'peak'")
        if align == "peak" and hits and isinstance(c.get("frame"), int):
            ms = c.get("motionStart", c["frame"])
            if ms > min(hits):
                pr.append(f"{cid}: motionStart {ms} is after its hit")
        typing = False
        if stage != "fit" or c.get("sound") is not None or c.get("fit"):
            typing = is_typing_cue(c, bank)
        if not typing and count >= 2 and len(hits) >= 2:
            gaps = np.diff(hits) / fps
            if gaps.min() < 1.0 / MAX_CASCADE_PER_SEC - 1e-9:
                pr.append(f"{cid}: CASCADE: hits closer than 1/{MAX_CASCADE_PER_SEC:g} s ({gaps.min():.3f} s). "
                          f"A cascade faster than about {MAX_CASCADE_PER_SEC:g} per second gets one sound: use count 1")
        if c.get("fit") is not None:
            lst = (c["fit"] or {}).get("list")
            if not lst:
                pr.append(f"{cid}: fit.list is empty")
            for n, _ in parse_tiers(lst):
                if n not in bank.entries:
                    pr.append(f"{cid}: fit list names bank number {n}, which is not in bank.json")
        if stage != "fit" and c.get("sound") is None and not c.get("soundFile"):
            pr.append(f"{cid}: no sound chosen (run fit.py first)")
        if c.get("sound") is not None and int(c["sound"]) not in bank.entries:
            pr.append(f"{cid}: sound {c['sound']} is not a bank number")
        # a riser anywhere but the declared cue is refused (type riser)
        cand = []
        if c.get("sound") is not None and int(c["sound"]) in bank.entries:
            cand = [int(c["sound"])]
        elif stage == "fit":
            cand = [n for n, _ in parse_tiers((c.get("fit") or {}).get("list")) if n in bank.entries]
        is_riser_cue = any(bank.role_of(n) == "riser" for n in cand)
        if is_riser_cue:
            if stage == "fit" and not all(bank.role_of(n) == "riser" for n in cand):
                pr.append(f"{cid}: a riser may not sit in the fit list of a cue with other options; give the riser cue a riser-only list")
            risers.append(c)
    if len(risers) > 1:
        pr.append(f"RISER: more than one riser in the video: {[c['id'] for c in risers]}")
    for c in risers:
        if c["id"] != riser_policy.get("onlyCue"):
            pr.append(f"RISER {c['id']}: a riser sound may only sit on the cue named by riserPolicy.onlyCue (now {riser_policy.get('onlyCue')!r})")
        elif c.get("count", 1) != 1 or c.get("align") != "peak":
            pr.append(f"RISER {c['id']}: the riser cue must be a single hit and align 'peak'")
        elif not riser_policy.get("why"):
            pr.append("RISER: riserPolicy.why must say why the video has a riser")
    return pr


def first_last_times(cue: dict, fps: float) -> tuple[float, float]:
    h = cue["hits"]
    return h[0] / fps, h[-1] / fps


def reuse_gap_rules(plan: dict) -> tuple[float, float, list[str]]:
    pol = plan.get("reusePolicy") or {}
    sw = float(pol.get("swooshMinGapSec", MIN_REPEAT_GAP_NO_REASON))
    ot = float(pol.get("otherMinGapSec", MIN_REPEAT_GAP_NO_REASON))
    pr = []
    if min(sw, ot) < MIN_REPEAT_GAP_NO_REASON and not pol.get("why"):
        pr.append(f"reusePolicy: repeats closer than {MIN_REPEAT_GAP_NO_REASON:g} s need a stated reason (reusePolicy.why)")
    return sw, ot, pr


def check_distribution(rows: list[dict], plan: dict) -> tuple[list[str], list[dict]]:
    """rows: one per cue with id, sound (bank number), role, t0, t1 (first and last hit time in seconds).
    Rules: a sound on more than one cue must be declared in plan.repeats and kept the policy gap apart (end of one use to
    start of the next); never the same sound on neighbouring cues. Typing is exempt. Returns (problems, repeat records)."""
    pr: list[str] = []
    sw, ot, pol_pr = reuse_gap_rules(plan)
    pr += pol_pr
    declared: dict[int, set] = {}
    for r in plan.get("repeats") or []:
        declared.setdefault(int(r["sound"]), set()).update(r.get("cues") or [])
    use: dict[int, list[dict]] = {}
    for r in rows:
        if r["role"] != "typing":
            use.setdefault(r["sound"], []).append(r)
    records = []
    for n, rs in use.items():
        if len(rs) < 2:
            continue
        rs = sorted(rs, key=lambda r: r["t0"])
        ids = [r["id"] for r in rs]
        if n not in declared or not set(ids) <= declared[n]:
            pr.append(f"DISTRIBUTION: bank #{n} serves {len(ids)} cues {ids} without a declared repeat (plan.repeats)")
        gaps = [q["t0"] - p["t1"] for p, q in zip(rs, rs[1:])]
        need = sw if rs[0]["role"] in AIR_ROLES else ot
        records.append({"sound": n, "cues": ids, "times": [round(r["t0"], 2) for r in rs],
                        "gapsSec": [round(g, 2) for g in gaps], "needSec": need})
        if min(gaps) < need - 1e-6:
            pr.append(f"DISTRIBUTION: bank #{n} repeats only {min(gaps):.1f} s apart ({ids}; needs {need:g} s)")
    order = sorted([r for r in rows if r["role"] != "typing"], key=lambda r: r["t0"])
    for a, b in zip(order, order[1:]):
        if a["sound"] == b["sound"]:
            pr.append(f"DISTRIBUTION: neighbouring cues {a['id']} and {b['id']} use the same sound (bank #{a['sound']})")
    return pr, records

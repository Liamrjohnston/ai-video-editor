#!/usr/bin/env python3
"""Choose a sound for every cue: fit first, then spacing.

Each cue in the plan lists the bank sounds that suit what moves, best first (a nested list is one tier of equally
good sounds). This tool picks one sound per cue by an exact solve (mixed integer program) that
  1. only ever uses a cue's first or second tier (--max-choice),
  2. never puts the same sound on neighbouring cues,
  3. keeps a repeated sound at least G seconds from its last use, taking the widest G at which every cue still gets
     its first or second choice,
  4. then, holding that fit, spreads repeats as far apart as the cues allow.
A sound that repeats is declared in plan.repeats and listed in the report. Typing sounds may repeat freely and are
not part of the solve. A riser is never a movement sound: it is only allowed on the single cue named by
riserPolicy.onlyCue, and only if that cue lists nothing but risers (or a pinned sound).
A sound whose tail would ring past the end of the cue's movement (plus 3 frames) is dropped from that cue's options.
A cue with "sound" set and no "fit" is pinned and kept as is. Prints the report and writes the plan with `sound`,
`choice`, `repeats` and `reusePolicy` filled in.

  fit.py plan.json --out plan.fitted.json
"""
import argparse
import sys

import numpy as np
from scipy.optimize import milp, LinearConstraint, Bounds
from scipy.sparse import lil_matrix

import sfxlib as S

TIER_COST = [0, 1.0, 2.5, 4.0]


def solve(info, caps, g_other, g_air, spread, fit_cap=None, time_limit=120):
    """One sound per cue. Returns (fit cost, {cue id: bank number}) or None when no assignment exists."""
    var = [(i, n, r) for i, x in enumerate(info) for n, r in x["opts"]]
    nv = len(var)
    fit = np.array([TIER_COST[min(r, 3)] for _, _, r in var])
    rows, lo, hi, by = [], [], [], {}
    for j, (i, n, r) in enumerate(var):
        by.setdefault(i, {})[n] = j
    for i in range(len(info)):
        rows.append([(j, 1) for j in by[i].values()]); lo.append(1); hi.append(1)
    for n in {n for _, n, _ in var}:
        js = [j for j, (i, k, r) in enumerate(var) if k == n]
        rows.append([(j, 1) for j in js]); lo.append(0); hi.append(caps["air"] if info_role(info, n) in S.AIR_ROLES else caps["other"])
    soft = []
    for a in range(len(info)):
        for b in range(a + 1, len(info)):
            gap = info[b]["t0"] - info[a]["t1"]
            for n in set(by[a]) & set(by[b]):
                need = g_air if info_role(info, n) in S.AIR_ROLES else g_other
                if b == a + 1 or gap < need:
                    rows.append([(by[a][n], 1), (by[b][n], 1)]); lo.append(0); hi.append(1)
                elif fit_cap is not None and gap < spread:
                    soft.append((by[a][n], by[b][n], spread - gap))
    for q, (ja, jb, w) in enumerate(soft):
        rows.append([(ja, 1), (jb, 1), (nv + q, -1)]); lo.append(-np.inf); hi.append(1)
    if fit_cap is not None:
        rows.append([(j, fit[j]) for j in range(nv) if fit[j]]); lo.append(0); hi.append(fit_cap + 1e-6)
        c = np.concatenate([np.zeros(nv), [w for _, _, w in soft]])
    else:
        c = np.concatenate([fit, np.zeros(len(soft))])
    M = lil_matrix((len(rows), nv + len(soft)))
    for r_, cs in enumerate(rows):
        for j, v in cs:
            M[r_, j] += v
    res = milp(c, constraints=LinearConstraint(M.tocsr(), lo, hi), integrality=np.ones(nv + len(soft)),
               bounds=Bounds(0, 1), options={"time_limit": time_limit})
    if res.x is None:
        return None
    x = res.x[:nv]
    return float(fit @ (x > 0.5)), {info[i]["id"]: n for j, (i, n, r) in enumerate(var) if x[j] > 0.5}


_ROLES: dict[int, str] = {}


def info_role(info, n):
    return _ROLES[n]


def worst_choice(info, pick):
    return max(dict(x["opts"])[pick[x["id"]]] for x in info) + 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("plan", help="plan.json (see PLAN-FORMAT.md)")
    ap.add_argument("--out", required=True, help="where to write the plan with sounds chosen")
    ap.add_argument("--bank", help="path to bank.json (default: ../bank/bank.json)")
    ap.add_argument("--max-choice", type=int, default=2, help="worst tier any cue may get (default 2: first or second choice)")
    ap.add_argument("--max-gap", type=float, default=6.0, help="widest repeat spacing to try, seconds (default 6)")
    ap.add_argument("--min-gap", type=float, default=2.0, help="narrowest repeat spacing allowed, seconds (default 2)")
    ap.add_argument("--step", type=float, default=0.5, help="spacing step, seconds (default 0.5)")
    ap.add_argument("--spread", type=float, default=12.0, help="after fitting, spread repeats toward this many seconds apart (default 12)")
    ap.add_argument("--cap", type=int, default=6, help="most cues one non-swoosh sound may carry (default 6)")
    ap.add_argument("--cap-air", type=int, default=8, help="most cues one swoosh may carry (default 8)")
    ap.add_argument("--relax", action="store_true", help="if no spacing keeps every cue on its first or second choice, allow lower tiers and report it")
    a = ap.parse_args(argv)

    bank = S.Bank(a.bank)
    plan = S.read_json(a.plan)
    pr = S.validate_plan(plan, bank, stage="fit")
    if pr:
        print("PLAN PROBLEMS"); [print("  -", p) for p in pr]
        return 1
    fps = float(plan["fps"])
    riser_only = (plan.get("riserPolicy") or {}).get("onlyCue")
    cache: dict[int, dict] = {}

    def clip(n):
        if n not in cache:
            ok, why = bank.check_number(n)
            if not ok:
                cache[n] = None
            else:
                cache[n] = S.prepare_clip(bank.file_of(n), bank.role_of(n))
        return cache[n]

    info, typing, errors = [], [], []
    for c in plan["cues"]:
        hits = c.get("hits") or [c["frame"]]
        c["hits"], c["count"] = hits, c.get("count", len(hits))
        t0, t1 = hits[0] / fps, hits[-1] / fps
        room = (c["motionEnd"] + 1 + S.TAIL_FRAMES) / fps - t1
        pinned = c.get("sound") is not None and not c.get("fit")
        if c.get("soundFile") and c.get("sound") is None and not c.get("fit"):
            n, why = bank.resolve_file(c["soundFile"])
            if n is None:
                errors.append(f"{c['id']}: {why}")
                continue
            c["sound"], pinned = n, True
        cands = [(int(c["sound"]), 0)] if pinned else S.parse_tiers(c["fit"]["list"])
        opts, before = [], len(errors)
        for n, rank in cands:
            ok, why = bank.check_number(n)
            if not ok:
                errors.append(f"{c['id']}: {why}")
                continue
            role = bank.role_of(n)
            _ROLES[n] = role
            cl = clip(n)
            tail = cl["lengthSec"] - (cl["peakSec"] if c.get("align") == "peak" else cl["onsetSec"])
            if role == "riser" and c["id"] != riser_only:
                errors.append(f"{c['id']}: bank #{n} is a riser; risers never go on a movement (riserPolicy.onlyCue is {riser_only!r})")
                continue
            if tail > room + 1e-6 and not pinned:
                continue
            if c["count"] >= 2 and role != "typing":
                p = cl["pulses"]
                if len(p) > 2 or (len(p) == 2 and p[1] - p[0] > 0.065) or bank.entries[n].get("type") == "sequence":
                    continue
            opts.append((n, rank))
        if not opts and len(errors) == before:
            errors.append(f"{c['id']}: nothing in its fit list fits (movement ends {room * 1000:.0f} ms after its last hit; counted cues need one-pulse sounds)")
            continue
        if not opts:
            continue
        roles = {_ROLES.get(n) or bank.role_of(n) for n, _ in opts}
        if roles == {"typing"}:
            typing.append((c, opts))
        elif c["id"] == riser_only and roles == {"riser"}:
            c["sound"] = opts[0][0]; c["choice"] = opts[0][1] + 1
            for n, _ in opts: _ROLES[n] = "riser"
            info.append({"id": c["id"], "t0": t0, "t1": t1, "opts": opts[:1], "cue": c, "fixed": True})
        else:
            info.append({"id": c["id"], "t0": t0, "t1": t1, "opts": opts, "cue": c, "pinned": pinned})
    if errors:
        print("FIT PROBLEMS"); [print("  -", e) for e in errors]
        return 1
    for n in cache:
        _ROLES.setdefault(n, bank.role_of(n))
    info.sort(key=lambda x: x["t0"])
    for x in info:
        for n, _ in x["opts"]:
            _ROLES.setdefault(n, bank.role_of(n))
    caps = {"air": a.cap_air, "other": a.cap}

    def restrict(inf, maxc):
        out = []
        for x in inf:
            o = [(n, r) for n, r in x["opts"] if r < maxc]
            out.append({**x, "opts": o})
        return out

    gaps = []
    g = a.max_gap
    while g >= a.min_gap - 1e-9:
        gaps.append(round(g, 4)); g -= a.step
    table, chosen, work = [], None, restrict(info, a.max_choice)
    if any(not x["opts"] for x in work):
        bad = [x["id"] for x in work if not x["opts"]]
        if not a.relax:
            print("FIT PROBLEMS"); print(f"  - no option within the first {a.max_choice} tiers (after tail fit) for: {bad}. Add alternatives or use --relax")
            return 1
        work = info
    for g in gaps:
        r = solve(work, caps, g, g, a.spread)
        row = {"gapSec": g, "fitCost": None if r is None else r[0], "worstChoice": None if r is None else worst_choice(work, r[1])}
        table.append(row)
        if r is not None and chosen is None:
            chosen = g
            break
    if chosen is None and a.relax:
        work = info
        for g in gaps:
            r = solve(work, caps, g, g, a.spread)
            table.append({"gapSec": g, "fitCost": None if r is None else r[0], "worstChoice": None if r is None else worst_choice(work, r[1]), "relaxed": True})
            if r is not None:
                chosen = g
                break
    for row in table:
        print(f"repeat spacing {row['gapSec']:g} s: " + ("no assignment" if row["fitCost"] is None else f"fit cost {row['fitCost']}, worst choice {row['worstChoice']}"))
    if chosen is None:
        print(f"FIT FAILED: no assignment keeps every cue on tier {a.max_choice} or better with repeats at least {a.min_gap:g} s apart "
              f"and never on neighbours. Add more sounds to the tightest cues' fit lists, or lower --min-gap.")
        return 1
    best, _ = solve(work, caps, chosen, chosen, a.spread)
    cost, pick = solve(work, caps, chosen, chosen, a.spread, fit_cap=best)

    for x in info:
        c = x["cue"]
        n = pick[x["id"]]
        rank = dict(x["opts"])[n]
        c["sound"], c["choice"] = n, rank + 1
    # typing: first option that fits, may repeat
    for c, opts in typing:
        c["sound"], c["choice"] = opts[0][0], opts[0][1] + 1
    use: dict[int, list] = {}
    for x in info:
        use.setdefault(x["cue"]["sound"], []).append(x)
    repeats = []
    for n, xs in sorted(use.items()):
        if len(xs) > 1:
            xs = sorted(xs, key=lambda x: x["t0"])
            repeats.append({"sound": n, "cues": [x["id"] for x in xs],
                            "gapsSec": [round(q["t0"] - p["t1"], 2) for p, q in zip(xs, xs[1:])],
                            "why": f"Fit first: each cue takes its best fitting sounds, so a sound that suits several movements repeats. "
                                   f"A repeat comes at least {chosen:g} s after the last use and never on the next cue."})
    plan["repeats"] = repeats
    plan["reusePolicy"] = {"swooshMinGapSec": chosen, "otherMinGapSec": chosen,
                           "why": f"{chosen:g} s is the widest repeat spacing at which every cue still gets one of its first {a.max_choice} choices; repeats are then spread as far apart as the cues allow."}
    plan["fitReport"] = {"repeatMinGapSec": chosen, "spreadSec": a.spread, "fitCost": cost, "spacingTable": table}
    S.write_json(a.out, plan)

    print(f"\nchosen repeat spacing {chosen:g} s, fit cost {cost}")
    for x in info:
        c = x["cue"]
        flag = "" if c["choice"] == 1 else f"  (choice {c['choice']})"
        print(f"{x['t0']:7.2f}s {c['id']:14s} x{c['count']:<2d} bank #{c['sound']:<4d} {bank.entries[c['sound']]['name']}{flag}")
    for c, _ in typing:
        print(f"{c['hits'][0] / fps:7.2f}s {c['id']:14s} x{c['count']:<2d} bank #{c['sound']:<4d} {bank.entries[c['sound']]['name']} (typing, may repeat)")
    for r in repeats:
        print(f"  repeat: bank #{r['sound']} on {r['cues']} gaps {r['gapsSec']}")
    print(f"wrote {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

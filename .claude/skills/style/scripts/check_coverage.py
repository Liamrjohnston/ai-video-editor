#!/usr/bin/env python3
"""Check a graphics coverage map against the pacing rules.

    check_coverage.py COVERAGE.json [--hook-rows 1]

COVERAGE.json is a list of rows, one per script line, in order:
    [{"row": 1, "line": "Stop doing this.", "mode": "IN_BIG",
      "startSec": 0.0, "endSec": 2.5}, ...]
mode is one of IN_BIG, IN_SMALL, OUT, FULL, NONE. startSec and endSec are
optional; without them FULL length and seconds per mode cannot be checked.

Modes: IN_* keep the presenter on screen with graphics in or around the
frame, OUT is graphics only, FULL is a full-frame graphic, NONE has no
graphic.

Hard rules (exit 1 if broken):
  - row 1 is IN_BIG
  - the row after the hook is not FULL (--hook-rows sets how many rows
    make up the hook; default 1)
  - the same mode never runs three rows in a row (NONE excluded)
  - never two OUT rows in a row
  - a FULL row lasts at most 4 s and is never part of the hook
Warning only: OUT used 3 or 4 times is the target; other counts warn.

Why: a map that alternates modes keeps the picture changing without losing
the presenter; long full-frame graphics and runs of the same mode make the
video feel flat or hide the speaker. Prints rows and seconds per mode.
"""
import argparse
import json
import sys

MODES = ("IN_BIG", "IN_SMALL", "OUT", "FULL", "NONE")
FULL_MAX_S = 4.0


def check(rows, hook_rows=1):
    fails, warns = [], []
    rows = sorted(rows, key=lambda r: r["row"])
    if not rows:
        return ["no rows"], [], {}
    for r in rows:
        if r["mode"] not in MODES:
            fails.append(f"row {r['row']}: unknown mode {r['mode']!r}")
    if rows[0]["mode"] != "IN_BIG":
        fails.append(f"row {rows[0]['row']} (first) must be IN_BIG, is {rows[0]['mode']}")
    if len(rows) > hook_rows and rows[hook_rows]["mode"] == "FULL":
        fails.append(f"row {rows[hook_rows]['row']} (after the hook) must not be FULL")
    for i in range(2, len(rows)):
        m = rows[i]["mode"]
        if m != "NONE" and rows[i - 1]["mode"] == m and rows[i - 2]["mode"] == m:
            fails.append(f"rows {rows[i-2]['row']}-{rows[i]['row']}: {m} three rows running")
    for i in range(1, len(rows)):
        if rows[i]["mode"] == "OUT" and rows[i - 1]["mode"] == "OUT":
            fails.append(f"rows {rows[i-1]['row']}-{rows[i]['row']}: two OUT rows running")
    for i, r in enumerate(rows):
        if r["mode"] != "FULL":
            continue
        if i < hook_rows:
            fails.append(f"row {r['row']}: FULL on the hook")
        if r.get("startSec") is not None and r.get("endSec") is not None:
            d = float(r["endSec"]) - float(r["startSec"])
            if d > FULL_MAX_S:
                fails.append(f"row {r['row']}: FULL lasts {d:.1f}s (max {FULL_MAX_S:g}s)")
        else:
            warns.append(f"row {r['row']}: FULL has no startSec/endSec, length not checked")
    outs = sum(r["mode"] == "OUT" for r in rows)
    if not 3 <= outs <= 4:
        warns.append(f"OUT used {outs} time(s); target is 3 to 4")
    stats = {m: {"rows": 0, "seconds": 0.0} for m in MODES}
    for r in rows:
        s = stats.get(r["mode"])
        if s is None:
            continue
        s["rows"] += 1
        if r.get("startSec") is not None and r.get("endSec") is not None:
            s["seconds"] += float(r["endSec"]) - float(r["startSec"])
    return fails, warns, stats


def main():
    ap = argparse.ArgumentParser(description="Enforce coverage-map pacing rules (exit 1 on hard failure).")
    ap.add_argument("coverage")
    ap.add_argument("--hook-rows", type=int, default=1)
    a = ap.parse_args()
    try:
        rows = json.load(open(a.coverage))
        for r in rows:
            r["row"] = int(r["row"])
            r["mode"] = str(r["mode"]).upper()
    except Exception as ex:  # noqa: BLE001
        print(f"could not read coverage: {ex}", file=sys.stderr)
        return 2
    fails, warns, stats = check(rows, a.hook_rows)
    for m, s in stats.items():
        print(f"{m:9} {s['rows']:3} rows {s['seconds']:6.1f} s")
    for w in warns:
        print("WARN", w)
    for f in fails:
        print("FAIL", f)
    print("FAIL" if fails else "PASS")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())

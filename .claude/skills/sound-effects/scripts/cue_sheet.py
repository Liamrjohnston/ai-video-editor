#!/usr/bin/env python3
"""Turn the sound ledger into a readable cue sheet (CSV), one row per cue in time order.

Columns: time, cue, what moves, bank number, sound name, source file, role, why it fits, which choice of the fit
list it was, number of hits, hit times, trim, and every other cue that reuses the same sound (declared repeats).
Open it in any spreadsheet to review the sound choices before a listen.

  cue_sheet.py mix_dir/sound-ledger.json cues.csv
"""
import argparse
import csv
import sys

import sfxlib as S


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("ledger", help="sound-ledger.json from build_mix.py")
    ap.add_argument("out", help="CSV to write")
    a = ap.parse_args(argv)
    L = S.read_json(a.ledger)
    uses: dict[int, list] = {}
    for c in L["cues"]:
        uses.setdefault(c["sound"], []).append((c["hits"][0]["eventSec"], c["id"]))
    rows = []
    for c in L["cues"]:
        if not c["hits"]:
            continue
        other = [f"{i} ({t:.1f}s)" for t, i in sorted(uses[c["sound"]]) if i != c["id"]]
        rows.append({"time_s": f"{c['hits'][0]['eventSec']:.2f}", "cue": c["id"], "what_moves": c["what"], "bank_number": f"#{c['sound']}",
                     "sound": c["name"], "source_file": c["file"], "role": c["role"],
                     "why_it_fits": (c.get("fit") or {}).get("why") or c.get("reason") or "",
                     "choice": c.get("choice") or "", "hits": len(c["hits"]),
                     "hit_times_s": " ".join(f"{h['eventSec']:.2f}" for h in c["hits"]), "trim_db": round(c.get("gainTrimDb", 0.0) + c.get("voiceTrimDb", 0.0), 2),
                     "also_used_by": "typing (reuse allowed)" if c["role"] == "typing" else ", ".join(other)})
    rows.sort(key=lambda r: float(r["time_s"]))
    if not rows:
        print("ledger has no cues")
        return 1
    with open(a.out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    print(f"{len(rows)} rows -> {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

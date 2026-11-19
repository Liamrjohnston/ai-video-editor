#!/usr/bin/env python3
"""List the sound bank or prove it is intact.

The bank is the only source of sound effects. Every file is listed in bank.json with its sha256, and the mix
builder and auditor refuse anything that does not match. `verify` re-hashes every file so a swapped, edited or
missing file is caught before it can reach a mix. An optional banned.json next to bank.json (a list of bank
numbers or sha256 strings) removes sounds from use without deleting them.

  bank.py list [--type swoosh]
  bank.py verify
"""
import argparse
import sys

import sfxlib as S


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--bank", help="path to bank.json (default: ../bank/bank.json next to this script)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    ls = sub.add_parser("list", help="print every usable sound")
    ls.add_argument("--type", help="only this type (click, pop, press, swoosh, typing, riser, camera, sequence, blip, sweep, tonal, tick, other)")
    ls.add_argument("--all", action="store_true", help="include banned sounds (marked)")
    sub.add_parser("verify", help="re-hash every file; exit 1 on any mismatch or missing file")
    a = ap.parse_args(argv)
    bank = S.Bank(a.bank)

    if a.cmd == "list":
        rows = 0
        for n in sorted(bank.entries):
            e = bank.entries[n]
            banned = bank.is_banned(n)
            if banned and not a.all:
                continue
            if a.type and e.get("type") != a.type:
                continue
            rows += 1
            print(f"#{n:<4d} {e.get('type', '?'):9s} {e.get('audibleSec', 0):6.3f}s  {e['name']:28s} {e.get('description', '')}" + ("  [BANNED]" if banned else ""))
        print(f"{rows} sounds")
        return 0

    bad = 0
    for n in sorted(bank.entries):
        e = bank.entries[n]
        p = bank.file_of(n)
        if not p.exists():
            print(f"MISSING  #{n} {e['file']}")
            bad += 1
        elif bank.hash_now(p) != e["sha256"]:
            print(f"MISMATCH #{n} {e['file']} (file is not the approved one)")
            bad += 1
        elif bank.is_banned(n):
            print(f"banned   #{n} {e['file']} (intact, but refused by banned.json)")
    seen: dict[str, int] = {}
    for n, e in bank.entries.items():
        if e["sha256"] in seen:
            print(f"note: #{n} and #{seen[e['sha256']]} are the same file")
        seen[e["sha256"]] = n
    print(f"{len(bank.entries)} entries checked, {bad} problems")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())

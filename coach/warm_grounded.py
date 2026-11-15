#!/usr/bin/env python3
"""Write the grounded hints ahead of time, so they are instant in front of a student.

    python3 coach/warm_grounded.py --levels 0-3 --limit 60
    python3 coach/warm_grounded.py --languages cat --limit 30

On the board a grounded hint takes minutes (the model solves the problem, then explains its own
program), and only about one problem in ten gets one: the program must run, match an option, and
agree with the answer key. This script goes through the bank and keeps the results in
data/teach_grounded.json, which web3/server.py reads when it starts. Run it while nobody else
needs the model. It prints ids and outcomes only, never a problem's text.

Then start the web app with --prefer-grounded, and the coach chooses these problems first.
"""
import argparse
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from copilot.config import ROOT  # noqa: E402
from coach.core import Bank  # noqa: E402
from coach.grounded import Grounder  # noqa: E402


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--bank", default="data/teach.db")
    p.add_argument("--cache", default="data/teach_grounded.json")
    p.add_argument("--levels", default="0-7", help="for example 0-3")
    p.add_argument("--languages", default="eng,cat")
    p.add_argument("--limit", type=int, default=40, help="problems to try in this run")
    p.add_argument("--wait", type=float, default=420, help="seconds to give one problem")
    args = p.parse_args()
    os.chdir(ROOT)
    low, _, high = args.levels.partition("-")
    levels = range(int(low), int(high or low) + 1)
    bank = Bank(args.bank)
    grounder = Grounder(cache_path=args.cache)
    todo = [(pid, lang) for (pid, lang) in sorted(bank.problems)
            if lang in args.languages.split(",") and bank.level[pid] in levels
            and grounder.records.get(grounder.key(pid, lang), {}).get("status") not in ("ready", "none")]
    # Spread over the levels instead of taking the first ids
    todo.sort(key=lambda key: (sum(ord(c) for c in key[0]) % 97, key))
    ready = 0
    for n, (pid, lang) in enumerate(todo[:args.limit], 1):
        start = time.time()
        grounder.open({**bank.problems[(pid, lang)], "id": pid, "language": lang})
        while grounder.get(pid, lang)["status"] == "thinking" and time.time() - start < args.wait:
            time.sleep(0.5)
        status = grounder.get(pid, lang)["status"]
        why = grounder.records.get(grounder.key(pid, lang), {}).get("reason", "")
        ready += status == "ready"
        print(f"[{n}/{min(len(todo), args.limit)}] {pid} {lang}: {status}{' (' + why + ')' if why else ''} "
              f"in {time.time() - start:.0f} s", flush=True)
    total = sum(1 for record in grounder.records.values() if record.get("status") == "ready")
    print(f"{ready} new grounded hints in this run, {total} in {args.cache}")


if __name__ == "__main__":
    main()

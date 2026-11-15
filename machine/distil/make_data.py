#!/usr/bin/env python3
"""Build the training file for train.py: one {"prompt", "completion"} per line.

    python3 machine/distil/make_data.py --out code_train.jsonl [--m3kang problems.jsonl programs.jsonl]

- The 500 invented problems (syn_*.jsonl, in this folder) are always used, in English and in Catalan.
- --m3kang adds M3Kang problems: problems.jsonl has {"id", "text", "text_cat" (optional), "options", "label"} per
  line and programs.jsonl has {"id", "program"}. M3Kang is for research use only, so those two files are not in
  this repository; we used the 734 problems that need no figure and have numeric options, and kept 673 programs.
Every program is run again here, and kept only if its result equals the correct option.
"""
import argparse
import glob
import json
import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", ".."))  # the repository root
from copilot import reason  # noqa: E402


def examples(problem_id, texts, options, label, program):
    program = program.strip()
    value, _ = reason.run_program("```python\n" + program + "\n```")
    if value is None or reason.matching_option(value, options) != label or len(program) > 450 or "#" in program:
        return []
    completion = "```python\n" + program + "\n```<|im_end|>"
    return [{"id": problem_id, "language": language,
             "prompt": reason.math_prompt({"text": text, "options": options}, reason.CODE_INSTRUCTION),
             "completion": completion} for language, text in texts if text]


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--out", default="code_train.jsonl")
    p.add_argument("--m3kang", nargs=2, metavar=("PROBLEMS", "PROGRAMS"))
    args = p.parse_args()
    out = []
    for path in sorted(glob.glob(os.path.join(HERE, "syn_*.jsonl"))):
        for line in open(path, encoding="utf-8"):
            if line.strip():
                r = json.loads(line)
                out += examples(r["id"], (("eng", r["text_eng"]), ("cat", r["text_cat"])),
                                {k: str(v) for k, v in r["options"].items()}, r["label"], r["program"])
    invented = len(out)
    if args.m3kang:
        problems = {json.loads(l)["id"]: json.loads(l) for l in open(args.m3kang[0], encoding="utf-8") if l.strip()}
        for line in open(args.m3kang[1], encoding="utf-8"):
            if line.strip():
                r = json.loads(line)
                q = problems.get(r["id"])
                if q:
                    out += examples(r["id"], (("eng", q["text"]), ("cat", q.get("text_cat"))), q["options"], q["label"], r["program"])
    random.seed(3)
    random.shuffle(out)
    with open(args.out, "w", encoding="utf-8") as f:
        for r in out:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"{invented} examples from the invented problems, {len(out) - invented} from M3Kang -> {args.out}")


if __name__ == "__main__":
    main()

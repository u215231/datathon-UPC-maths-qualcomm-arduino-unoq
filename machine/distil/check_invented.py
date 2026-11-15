#!/usr/bin/env python3
"""python3 machine/distil/check_invented.py machine/distil/syn_0.jsonl -> checks invented problems. One JSON per line:
{"id","level","text_eng","text_cat","options":{"A".."E"},"label","program"}"""
import json, sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))  # the repository root
from copilot import reason
ok, bad, seen = 0, [], set()
for n, line in enumerate(open(sys.argv[1]), 1):
    if not line.strip(): continue
    try:
        r = json.loads(line)
    except ValueError as e:
        bad.append((n, f"not JSON: {e}")); continue
    pr = []
    for k in ("id", "level", "text_eng", "text_cat", "options", "label", "program"):
        if k not in r: pr.append(f"missing {k}")
    if pr: bad.append((n, "; ".join(pr))); continue
    o = r["options"]; src = r["program"].strip()
    if sorted(o) != list("ABCDE"): pr.append("options must be A-E")
    nums = [reason.number(str(v)) for v in o.values()]
    if any(v is None for v in nums): pr.append("every option must be a number (units allowed)")
    elif len(set(nums)) != 5: pr.append("options must be 5 different values")
    if r["id"] in seen: pr.append("duplicate id")
    seen.add(r["id"])
    if len(r["text_eng"]) < 40 or len(r["text_cat"]) < 40: pr.append("text too short")
    value, why = reason.run_program("```python\n" + src + "\n```")
    if value is None: pr.append(f"program gives no value ({why})")
    elif not pr and reason.matching_option(value, {k: str(v) for k, v in o.items()}) != r["label"]:
        pr.append(f"program printed {value}, label {r['label']} is {o.get(r['label'])}")
    lines = [l for l in src.splitlines() if l.strip()]
    if len(lines) > 12 or len(src) > 420: pr.append("program too long (max 12 lines, 420 chars)")
    if "#" in src: pr.append("has a comment")
    if pr: bad.append((r.get("id", n), "; ".join(pr)))
    else: ok += 1
print(f"OK {ok}; {len(bad)} failing")
for i, why in bad: print("FAIL", i, why)

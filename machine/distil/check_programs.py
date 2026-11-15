#!/usr/bin/env python3
"""python3 machine/distil/check_programs.py problems.jsonl programs.jsonl  -> checks each program against the answer key.
programs file: one JSON per line {"id": ..., "program": "python source"}."""
import json, sys, ast, re
import os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))  # the repository root
from copilot import reason
shard = {json.loads(l)["id"]: json.loads(l) for l in open(sys.argv[1])}
seen, ok, bad = set(), 0, []
for line in open(sys.argv[2]):
    if not line.strip(): continue
    r = json.loads(line); p = shard.get(r["id"])
    if p is None: bad.append((r["id"], "unknown id")); continue
    seen.add(r["id"]); src = r["program"].strip()
    value, why = reason.run_program("```python\n" + src + "\n```")
    letter = reason.matching_option(value, p["options"]) if value is not None else None
    lines = [l for l in src.splitlines() if l.strip()]
    consts = {n.value for n in ast.walk(ast.parse(src)) if isinstance(n, ast.Constant)} if why != "syntax" else set()
    problems = []
    if value is None: problems.append(f"no value ({why})")
    elif letter != p["label"]: problems.append(f"printed {value}, matches {letter}, expected option {p['label']}={p['options'][p['label']]}")
    if len(lines) > 12: problems.append(f"{len(lines)} lines (max 12)")
    if len(src) > 420: problems.append(f"{len(src)} chars (max 420)")
    if "#" in src: problems.append("has a comment")
    if len(lines) <= 1 and re.fullmatch(r"print\(\s*-?[\d./]+\s*\)", src): problems.append("just prints a constant: must compute")
    if problems: bad.append((r["id"], "; ".join(problems)))
    else: ok += 1
print(f"OK {ok} of {len(shard)} problems; {len(bad)} failing; {len(shard) - len(seen)} without a program")
for i, why in bad: print("FAIL", i, why)

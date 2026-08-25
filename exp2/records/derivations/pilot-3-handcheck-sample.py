"""Draw 20 challenger replies for the hand check of the line-vs-prose instrument.

Stratified by stance x parent verdict class, so the sample cannot be all easy cases in
one corner of the table. Deterministic at seed 0, printed with the Haiku reading
withheld until the end of each entry, so the hand read is made first.
"""
from __future__ import annotations

import json
import random
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(sys.argv[1] if len(sys.argv) > 1 else "outputs/experiments/pilot-3")
N = int(sys.argv[2]) if len(sys.argv) > 2 else 20
index = {r["cell_id"]: r for r in
         (json.loads(l) for l in (ROOT / "index.jsonl").open() if l.strip())}

strata = defaultdict(list)
for path in sorted(ROOT.glob("cells/*/contests/*/runs/*/agreement.json")):
    cell = next(p for p in path.parts if "__" in p)
    row = index.get(cell)
    if row is None:
        continue
    strata[(row["challenge_stance"], row["verdict"])].append((cell, path))

print("strata (stance x parent verdict):")
for k, v in sorted(strata.items()):
    print(f"  {k[0]:<10} {k[1]:<7} {len(v)}")

rng = random.Random(0)
picked = []
keys = sorted(strata)
# Round-robin over the strata so every non-empty cell of the table is represented
# before any of them is sampled twice.
pools = {k: rng.sample(strata[k], len(strata[k])) for k in keys}
while len(picked) < N and any(pools.values()):
    for k in keys:
        if pools[k] and len(picked) < N:
            picked.append((k, pools[k].pop()))

print(f"\ndrew {len(picked)} replies\n")
for i, (stratum, (cell, path)) in enumerate(picked, 1):
    agreement = json.loads(path.read_text())
    challenge = json.loads((path.parent / "challenge.json").read_text())
    row = index[cell]
    print("=" * 78)
    print(f"[{i:>2}] {cell}")
    print(f"     stratum: stance={stratum[0]} parent_verdict={stratum[1]}  "
          f"gold_flawed={row['gold_flawed']}  initially_correct={row['initially_correct']}")
    print(f"     line the challenger wrote : {agreement['line_word']}")
    print(f"     -- the objection's prose (the ONLY thing the reader saw) --")
    for line in challenge["text"].splitlines():
        print(f"     | {line}")
    print(f"     -- Haiku said: Prose: {agreement['prose_stance']}  "
          f"(agrees={agreement['agrees']}, phantom={agreement['phantom_contest']})")
    print(f"     -- Haiku's reason: {agreement['reasoning'][:400]}")
print("=" * 78)
print("\nHAND READ GOES HERE: for each, RIGHT / WRONG / NEITHER, then agreement count.")

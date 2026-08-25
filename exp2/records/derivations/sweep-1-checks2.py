"""Follow-ups the first pass could not answer, and one classifier it got wrong.

  * truncation shape: did the reply reach its own PUBLIC label? (`_LABEL_RE` matches
    `Thinking:` too, so the first script's "reached_label" column was meaningless.)
  * the scar: is `salvaged_no_thinking` concentrated in the runs that spent a repair,
    and does it appear on stages AFTER the repair? That is what "For this reply only"
    was supposed to stop.
  * revision rates per condition, with n.
"""
from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, "src")
from exp2.prompts import _LABEL_RE, conversation_spent_a_repair  # noqa: E402

ROOT = Path(sys.argv[1] if len(sys.argv) > 1 else "outputs/experiments/sweep-1")
SOLO_ROLES = {"solo", "critic", "recourse_solo"}


def rule(t):
    print(f"\n{'=' * 78}\n{t}\n{'=' * 78}")


def content(call):
    try:
        return call["response_body"]["choices"][0]["message"]["content"] or ""
    except (KeyError, IndexError, TypeError):
        return ""


def reached_public_label(text, role):
    body = text.replace("Reasoning:", "Argument:") if role in SOLO_ROLES else text
    return any(m.group(1).lower() == "argument" for m in _LABEL_RE.finditer(body))


calls = []
for path in sorted(ROOT.rglob("calls.jsonl")):
    if "parent" in path.parts:
        continue
    for line in path.open():
        line = line.strip()
        if line:
            try:
                c = json.loads(line)
            except json.JSONDecodeError:
                continue
            c["_run"] = str(path.parent)
            calls.append(c)

rule("TRUNCATION SHAPE — corrected: did it reach its own PUBLIC label?")
trunc = [c for c in calls if c.get("finish_reason") in ("length", "error")]
print(f"truncated calls: {len(trunc)} of {len(calls)} attempts "
      f"({len(trunc) / len(calls):.1%})")
tbl = Counter()
for c in trunc:
    tbl[(c["role"], c.get("purpose"),
         "PAST its public label (fatal by design)" if
         reached_public_label(content(c), c["role"]) else
         "never reached it (budget route eligible)")] += 1
for (role, purpose, kind), n in sorted(tbl.items()):
    print(f"  {role:<10} {str(purpose):<10} {kind:<42} {n}")
lens = sorted(len(content(c)) for c in trunc)
if lens:
    print(f"\ntruncated reply length (chars): min {lens[0]}  median "
          f"{lens[len(lens) // 2]}  max {lens[-1]}")
print("\ncompletion tokens on truncated calls: "
      + str(sorted({(c.get('usage') or {}).get('completion_tokens') for c in trunc})))

rule("THE SCAR — is salvaged_no_thinking caused by a repair, or is it just the model?")
per_run = []
for path in sorted(ROOT.glob("cells/*/runs/*/trace.json")):
    steps = json.loads(path.read_text())["steps"]
    conv = path.parent / "conversation.json"
    repaired = conversation_spent_a_repair(json.loads(conv.read_text())) \
        if conv.is_file() else False
    per_run.append((repaired, steps))

for label, want in (("runs that spent NO repair", False),
                    ("runs that spent a repair", True)):
    runs = [s for r, s in per_run if r is want]
    steps = [st for s in runs for st in s]
    snt = sum(1 for st in steps if st["parse_mode"].startswith("salvaged_no_thinking"))
    print(f"{label:<28} runs {len(runs):>4}  steps {len(steps):>4}  "
          f"salvaged_no_thinking {snt:>4}"
          + (f" = {snt / len(steps):.1%}" if steps else ""))

print("\nWithin a repaired run, by position relative to the FIRST repaired stage:")
before = after = at = 0
before_snt = after_snt = at_snt = 0
for repaired, steps in per_run:
    if not repaired:
        continue
    first = next((i for i, st in enumerate(steps) if st["repair_attempts"]), None)
    if first is None:
        continue
    for i, st in enumerate(steps):
        snt = st["parse_mode"].startswith("salvaged_no_thinking")
        if i < first:
            before += 1
            before_snt += snt
        elif i == first:
            at += 1
            at_snt += snt
        else:
            after += 1
            after_snt += snt
print(f"  before the repair  steps {before:>4}  salvaged_no_thinking {before_snt:>4}"
      + (f" = {before_snt / before:.1%}" if before else ""))
print(f"  the repaired stage steps {at:>4}  salvaged_no_thinking {at_snt:>4}"
      + (f" = {at_snt / at:.1%}" if at else ""))
print(f"  after the repair   steps {after:>4}  salvaged_no_thinking {after_snt:>4}"
      + (f" = {after_snt / after:.1%}" if after else ""))

rule("REVISION RATES per condition, with n")
index = [json.loads(l) for l in (ROOT / "index.jsonl").open() if l.strip()]
print(f"{'condition':<16} {'revised|incorrect':>20} {'revised|correct':>18} "
      f"{'acc before':>11} {'acc after':>10}")
for cond in ("single", "self_critique", "debate", "ALL"):
    rows = index if cond == "ALL" else [r for r in index if r["condition"] == cond]
    inc = [r for r in rows if r["initially_correct"] is False]
    cor = [r for r in rows if r["initially_correct"] is True]
    ri = sum(1 for r in inc if r.get("changed_the_decision"))
    rc = sum(1 for r in cor if r.get("changed_the_decision"))
    fin = sum(1 for r in rows if r.get("final_correct"))
    print(f"{cond:<16} {f'{ri}/{len(inc)}':>20} {f'{rc}/{len(cor)}':>18} "
          f"{f'{len(cor)}/{len(rows)}':>11} {f'{fin}/{len(rows)}':>10}")

print("\nrulings actually sought (stance == contests):")
for cond in ("single", "self_critique", "debate"):
    rows = [r for r in index if r["condition"] == cond
            and r.get("challenge_stance") == "contests"]
    ch = sum(1 for r in rows if r.get("changed_the_decision"))
    print(f"  {cond:<16} {ch}/{len(rows)} contests changed the decision")

print("\nphantom contests that nonetheless changed a decision:")
for r in index:
    if r.get("phantom_contest") and r.get("changed_the_decision"):
        print(f"  {r['cell_id']}  verdict {r['verdict']} -> changed, "
              f"final_correct={r.get('final_correct')}")

rule("COMPREHENSION")
print(Counter(r.get("comprehension") for r in index))
for cond in ("single", "self_critique", "debate"):
    s = [r["comprehension"] for r in index
         if r["condition"] == cond and r.get("comprehension") is not None]
    print(f"  {cond:<16} n={len(s):<4} mean {sum(s) / len(s):.2f}  {Counter(s)}")

rule("DECISION RECORD LENGTH (the token-balance check)")
for cond in ("single", "self_critique", "debate"):
    w = [r["decision_record_words"] for r in index
         if r["condition"] == cond and r.get("decision_record_words")]
    print(f"  {cond:<16} n={len(w):<4} mean {sum(w) / len(w):.0f} words")

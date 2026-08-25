"""Every number in `outputs/experiments/pilot-3/CHECKLIST.md`, derived from disk.

Reads only what a run left behind — `cells.jsonl`, every `calls.jsonl`, every
`challenge.json` / `agreement.json` / `grade.json`, and `index.jsonl` — so the checklist
can be re-derived from the record rather than from scrollback.

The one derivation worth stating: a format repair is attributed to the call that
**failed**, not to the call that served the repair. Pilot 2's first provider table did
the latter and was wrong for 40% of its repairs, because OpenRouter re-routes freely
between the two calls.
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, "src")
from exp2.prompts import (  # noqa: E402
    _ANY_THINKING_RE,
    _LABEL_RE,
    MalformedOutputError,
    _missing_label_kind,
    parse_debater_output,
    parse_verdict_output,
)

ROOT = Path(sys.argv[1] if len(sys.argv) > 1 else "outputs/experiments/pilot-3")
CHALLENGER = "openai-gpt-4.1-nano"
SOLO_ROLES = {"solo", "critic", "recourse_solo"}
STRONG = "deepseek/deepseek-v4-flash-0731"


def rule(title):
    print(f"\n{'=' * 78}\n{title}\n{'=' * 78}")


def content(call):
    try:
        return call["response_body"]["choices"][0]["message"]["content"] or ""
    except (KeyError, IndexError, TypeError):
        return ""


def truncated(call):
    return call.get("finish_reason") in ("length", "error")


def shape(text, role, purpose):
    if not text.strip():
        return "empty_reply"
    body = text.replace("Reasoning:", "Argument:") if role in SOLO_ROLES else text
    labels = {m.group(1).lower() for m in _LABEL_RE.finditer(body)}
    if "argument" not in labels:
        return _missing_label_kind(body)
    try:
        _, public, _ = parse_debater_output(body)
    except MalformedOutputError as error:
        message = str(error)
        if "contains a 'Thinking:' label" in message:
            return "private_label_in_public"
        if "is empty" in message:
            return "empty_public"
        return "other"
    if role == "solo" and purpose != "critique":
        try:
            parse_verdict_output(public)
        except MalformedOutputError:
            return "no_verdict_line"
    return "parses"


# --- load ---------------------------------------------------------------------------

stage_rows = [json.loads(l) for l in (ROOT / "cells.jsonl").open() if l.strip()]
index = [json.loads(l) for l in (ROOT / "index.jsonl").open() if l.strip()] \
    if (ROOT / "index.jsonl").is_file() else []

decision_calls, contest_calls = [], []
for path in sorted(ROOT.rglob("calls.jsonl")):
    if "parent" in path.parts:
        continue
    bucket = contest_calls if "contests" in path.parts else decision_calls
    run = str(path.parent)
    for line in path.open():
        line = line.strip()
        if not line:
            continue
        try:
            call = json.loads(line)
        except json.JSONDecodeError:
            continue
        call["_run"] = run
        bucket.append(call)
all_calls = decision_calls + contest_calls

# --- row 1: parse --------------------------------------------------------------------

rule("ROW 1 — parse")
decide_rows = [r for r in stage_rows if r["stage"] == "decide"]
last = {}
for r in decide_rows:
    last[r["cell_id"]] = r
done = sum(1 for r in last.values() if r["status"] == "completed")
failed = [r for r in last.values() if r["status"] == "failed"]
total = len(last)
print(f"cells seen in decide: {total}   completed {done}   failed {len(failed)}")
print(f"decided: {done}/{total} = {done / total:.1%}" if total else "no rows")

trunc = [c for c in all_calls if truncated(c)]
print(f"\ntruncated calls: {len(trunc)}")
for key, n in Counter(
    (c["role"], c.get("purpose"), "reached_label" if
     _LABEL_RE.search(content(c).replace("Reasoning:", "Argument:")) else "no_label")
    for c in trunc
).most_common():
    print(f"  role={key[0]:<14} purpose={str(key[1]):<12} {key[2]:<14} {n}")

budget = [c for c in all_calls if c.get("purpose") == "repair"]
modes = Counter()
for path in sorted(ROOT.rglob("trace.json")):
    if "parent" in path.parts:
        continue
    for step in json.loads(path.read_text())["steps"]:
        modes[step["parse_mode"]] += 1
for path in sorted(ROOT.rglob("transcript.json")):
    if "parent" in path.parts:
        continue
    for turn in json.loads(path.read_text())["turns"]:
        modes[turn["parse_mode"]] += 1
print("\nparse_mode over every recorded decision step/turn:")
for k, v in modes.most_common():
    print(f"  {k:<40} {v}")
print(f"\nbudget recoveries (parse_mode *_after_budget_repair): "
      f"{sum(v for k, v in modes.items() if 'after_budget_repair' in k)}")

print("\nfailed cells and their errors:")
for r in sorted(failed, key=lambda r: r["cell_id"]):
    print(f"  {r['cell_id']:<62} {r.get('error', '')[:150]}")
    if "critic" in r.get("error", "") and "truncat" in r.get("error", ""):
        print("      ^^ CRITIQUE TRUNCATED PAST ITS LABEL — the known fatal cause")

# --- row 2: repair, attributed to the failing call -----------------------------------

rule("ROW 2 — repair, attributed to the call that FAILED")
by_run_key = defaultdict(list)
for c in all_calls:
    by_run_key[(c["_run"], c["role"], c.get("speaker"), c.get("round"))].append(c)

originals = [c for c in all_calls if c.get("purpose") != "repair"]
repairs = [c for c in all_calls if c.get("purpose") == "repair"]
blamed = Counter()
paired = 0
for r in repairs:
    key = (r["_run"], r["role"], r.get("speaker"), r.get("round"))
    prior = [c for c in by_run_key[key] if c.get("purpose") != "repair"]
    if prior:
        blamed[prior[-1].get("provider") or "unknown"] += 1
        paired += 1
print(f"original calls {len(originals)}   repair calls {len(repairs)}   "
      f"paired to a failing call {paired}/{len(repairs)}")
if originals:
    print(f"overall repair rate: {len(repairs)}/{len(originals)} = "
          f"{len(repairs) / len(originals):.1%} of original calls")

orig_by_provider = Counter(c.get("provider") or "unknown" for c in originals)
print(f"\n{'provider':<20} {'original calls':>14} {'caused a repair':>16} {'rate':>8}")
for prov, n in orig_by_provider.most_common():
    k = blamed.get(prov, 0)
    print(f"{prov:<20} {n:>14} {k:>16} {k / n:>7.1%}")

strong_orig = [c for c in originals
               if (c.get("request_body") or {}).get("model") == STRONG]
strong_rep = 0
for r in repairs:
    if (r.get("request_body") or {}).get("model") != STRONG:
        continue
    key = (r["_run"], r["role"], r.get("speaker"), r.get("round"))
    prior = [c for c in by_run_key[key] if c.get("purpose") != "repair"]
    if prior:
        strong_rep += 1
print(f"\nSTRONG MODEL ONLY ({STRONG}):")
print(f"  original calls {len(strong_orig)}   caused a repair {strong_rep}   "
      f"rate {strong_rep / len(strong_orig):.1%}" if strong_orig else "  none")

print("\nrepair kind, from the instruction actually sent:")
kinds = Counter()
for r in repairs:
    msg = (r.get("request_body") or {}).get("messages") or [{}]
    text = msg[-1].get("content", "")
    if "ran out of budget" in text:
        kinds["budget"] += 1
    elif "had only a Thinking section" in text:
        kinds["aimed: no_public_label"] += 1
    elif "must begin on its own line" in text:
        kinds["aimed: misplaced label"] += 1
    else:
        kinds["per-role fallback"] += 1
for k, v in kinds.most_common():
    print(f"  {k:<28} {v}")

malformed_after_repair = 0
for r in failed:
    if "still malformed after one" in r.get("error", ""):
        malformed_after_repair += 1
print(f"\nmalformed-after-repair cells: {malformed_after_repair}")

# --- row 3: verdicts -----------------------------------------------------------------

rule("ROW 3 — verdict distribution per condition")
if index:
    print(f"{'condition':<16} {'n':>5} {'FLAWED':>8} {'SOUND':>8} {'max share':>10} "
          f"{'gold flawed':>12} {'accuracy':>9}")
    for cond in ("single", "self_critique", "debate"):
        rows = [r for r in index if r["condition"] == cond]
        if not rows:
            continue
        f = sum(1 for r in rows if r["verdict"] == "FLAWED")
        s = len(rows) - f
        gold = sum(1 for r in rows if r["gold_flawed"])
        acc = sum(1 for r in rows if r["initially_correct"])
        print(f"{cond:<16} {len(rows):>5} {f:>8} {s:>8} "
              f"{max(f, s) / len(rows):>9.1%} {gold:>12} {acc / len(rows):>8.1%}")

# --- row 4: stances ------------------------------------------------------------------

rule("ROW 4 — stances per condition, split by parent verdict and by correctness")
if index:
    def stance_table(title, keyfn):
        print(f"\n-- {title} --")
        print(f"{'condition':<16} {'group':<18} {'n':>4} {'contests':>9} {'declined':>9} "
              f"{'unclear':>8} {'contest rate':>13}")
        for cond in ("single", "self_critique", "debate"):
            rows = [r for r in index
                    if r["condition"] == cond and r.get("challenge_stance")]
            for group in sorted({str(keyfn(r)) for r in rows}):
                g = [r for r in rows if str(keyfn(r)) == group]
                c = sum(1 for r in g if r["challenge_stance"] == "contests")
                d = sum(1 for r in g if r["challenge_stance"] == "declined")
                u = sum(1 for r in g if r["challenge_stance"] == "unclear")
                print(f"{cond:<16} {group:<18} {len(g):>4} {c:>9} {d:>9} {u:>8} "
                      f"{c / len(g):>12.1%}")

    stance_table("pooled", lambda r: "all")
    stance_table("by PARENT VERDICT class", lambda r: r["verdict"])
    stance_table("by correctness",
                 lambda r: "correct" if r["initially_correct"] else "incorrect")

    print("\n-- contests given a false negative vs a false positive --")
    for cond in ("single", "self_critique", "debate"):
        rows = [r for r in index if r["condition"] == cond
                and r.get("challenge_stance") and not r["initially_correct"]]
        fn = [r for r in rows if r["gold_flawed"]]
        fp = [r for r in rows if not r["gold_flawed"]]
        def frac(g):
            c = sum(1 for r in g if r["challenge_stance"] == "contests")
            return f"{c}/{len(g)}" + (f" = {c / len(g):.0%}" if g else "")
        print(f"  {cond:<16} false negative {frac(fn):<16} false positive {frac(fp)}")

    print("\n-- overall claimed_verdict, the column that must NOT be read as a reflex --")
    print("   " + str(Counter(r.get("challenge_claimed_verdict") for r in index)))

# --- row 5: line vs prose ------------------------------------------------------------

rule("ROW 5 — line vs prose")
if index:
    measured = [r for r in index if r.get("prose_stance")]
    print(f"measured {len(measured)} of "
          f"{sum(1 for r in index if r.get('challenge_stance') in ('contests', 'declined'))}"
          " eligible contests")
    print(f"\n{'condition':<16} {'line':<9} {'RIGHT':>7} {'WRONG':>7} {'NEITHER':>9}")
    for cond in ("single", "self_critique", "debate", "ALL"):
        rows = measured if cond == "ALL" else [r for r in measured
                                               if r["condition"] == cond]
        for stance, line in (("contests", "REVERSE"), ("declined", "STANDS")):
            g = [r for r in rows if r["challenge_stance"] == stance]
            c = Counter(r["prose_stance"] for r in g)
            print(f"{cond:<16} {line:<9} {c.get('RIGHT', 0):>7} {c.get('WRONG', 0):>7} "
                  f"{c.get('NEITHER', 0):>9}")
    print()
    for cond in ("single", "self_critique", "debate", "ALL"):
        rows = measured if cond == "ALL" else [r for r in measured
                                               if r["condition"] == cond]
        contests = [r for r in rows if r["challenge_stance"] == "contests"]
        phantom = sum(1 for r in contests if r.get("phantom_contest"))
        declines = [r for r in rows if r["challenge_stance"] == "declined"]
        rev = sum(1 for r in declines if r["prose_stance"] == "WRONG")
        print(f"  {cond:<16} phantom contests {phantom}/{len(contests)}"
              + (f" = {phantom / len(contests):.1%}" if contests else "")
              + f"   declines arguing for reversal {rev}/{len(declines)}")

# --- row 6: containment --------------------------------------------------------------

rule("ROW 6 — containment and native reasoning")
leaks = []
for path in sorted(ROOT.rglob("transcript.json")):
    if "parent" in path.parts:
        continue
    for turn in json.loads(path.read_text())["turns"]:
        if _ANY_THINKING_RE.search(turn["argument"]):
            leaks.append((str(path), turn["speaker"], turn["round"]))
for path in sorted(ROOT.rglob("trace.json")):
    if "parent" in path.parts:
        continue
    for step in json.loads(path.read_text())["steps"]:
        if _ANY_THINKING_RE.search(step["text"]):
            leaks.append((str(path), step["stage"], step["index"]))
n_records = len(list(ROOT.glob("cells/*/runs/*/transcript.json"))) + \
    len(list(ROOT.glob("cells/*/runs/*/trace.json")))
print(f"challenger-visible decision records checked: {n_records}")
print(f"'Thinking:' occurrences in published text: {len(leaks)}")
for leak in leaks:
    print(f"  LEAK {leak}")

nr = Counter()
for c in all_calls:
    if c.get("has_native_reasoning"):
        nr[c.get("provider") or "unknown"] += 1
tot = Counter(c.get("provider") or "unknown" for c in all_calls)
print(f"\n{'provider':<20} {'calls':>8} {'native reasoning':>18} {'rate':>8}")
for prov, n in tot.most_common():
    print(f"{prov:<20} {n:>8} {nr.get(prov, 0):>18} {nr.get(prov, 0) / n:>7.1%}")
withheld = sum(1 for c in all_calls
               if ((c.get("usage") or {}).get("completion_tokens_details") or {})
               .get("reasoning_tokens") and not c.get("has_native_reasoning"))
print(f"reasoning billed but withheld: {withheld}")

# --- row 7: critiques ----------------------------------------------------------------

rule("ROW 7 — critiques")
crit_steps = withheld_steps = 0
runs_with_withheld = set()
for path in sorted(ROOT.glob("cells/*/runs/*/trace.json")):
    steps = json.loads(path.read_text())["steps"]
    for step in steps:
        if step["stage"] != "critique":
            continue
        crit_steps += 1
        if step["parse_mode"] == "unparsed_withheld":
            withheld_steps += 1
            runs_with_withheld.add(str(path.parent))
print(f"critique steps: {crit_steps}   withheld: {withheld_steps}"
      + (f" = {withheld_steps / crit_steps:.1%}" if crit_steps else ""))
print(f"self_critique runs carrying at least one withheld critique: "
      f"{len(runs_with_withheld)}")
shown = 0
for path in sorted(ROOT.glob("cells/*self_critique*/contests/*/runs/*/parent/trace.json")):
    if any(s["parse_mode"] == "unparsed_withheld"
           for s in json.loads(path.read_text())["steps"]):
        shown += 1
print(f"self_critique CHALLENGERS shown a placeholder: {shown}   (0 expected)")

# --- row 8: grader -------------------------------------------------------------------

rule("ROW 8 — graded rows")
for path in sorted(ROOT.rglob("grade.json")):
    if "parent" in path.parts:
        continue
    g = json.loads(path.read_text())
    cell = [p for p in path.parts if "__" in p]
    print(f"\n  {cell[0] if cell else path}")
    print(f"    identified={g['identified_flaw']}  characterised="
          f"{g['characterises_the_flaw']}  valid={g['valid']}  "
          f"ungradable_char={g['characterisation_ungradable']}")
    print(f"    dir: {path.parent}")

# --- row 9: ops ----------------------------------------------------------------------

rule("ROW 9 — ops")
served = Counter(c.get("provider") or "unknown" for c in all_calls)
print("served-provider distribution over every call:")
for prov, n in served.most_common():
    print(f"  {prov:<22} {n:>6}  {n / len(all_calls):>6.1%}")
strong_calls = [c for c in all_calls
                if (c.get("request_body") or {}).get("model") == STRONG]
print(f"\nstrong-model calls: {len(strong_calls)}")
for prov, n in Counter(c.get("provider") or "unknown"
                       for c in strong_calls).most_common():
    print(f"  {prov:<22} {n:>6}  {n / len(strong_calls):>6.1%}")
status = Counter(c.get("status") for c in all_calls)
print(f"\nHTTP status counts: {dict(status)}")
for code in (404, 429, 500, 502, 503):
    n = status.get(code, 0)
    if n:
        print(f"  {code}: {n} = {n / len(all_calls):.2%} of calls")
print(f"non-200 attempts: {sum(v for k, v in status.items() if k != 200)}"
      f" / {len(all_calls)}")

from exp2.accounting import aggregate_tree  # noqa: E402
spend = aggregate_tree(ROOT)
print(f"\nspend: ${spend['cost_usd']:.4f} over {spend['runs']} run directories")
print(f"  decision path ${spend['decision_path']['cost_usd']:.4f}  "
      f"off path ${spend['off_path']['cost_usd']:.4f}")
if done:
    print(f"  $/decided cell: ${spend['cost_usd'] / done:.5f}")
    print(f"  sweep projection at 2110 items x 3 conditions = 6330 cells: "
          f"${spend['cost_usd'] / done * 6330:.2f}"
          f"  (1.3x headroom ${spend['cost_usd'] / done * 6330 * 1.3:.2f})")
tokens_by_model = defaultdict(int)
cost_by_model = defaultdict(float)
for c in all_calls:
    m = (c.get("request_body") or {}).get("model") or "?"
    u = c.get("usage") or {}
    tokens_by_model[m] += (u.get("completion_tokens") or 0)
    cost_by_model[m] += float(u.get("cost") or 0.0)
print("\ncost by model:")
for m, v in sorted(cost_by_model.items(), key=lambda kv: -kv[1]):
    print(f"  {m:<36} ${v:>8.4f}  {v / max(sum(cost_by_model.values()), 1e-9):>6.1%}"
          f"   completion tokens {tokens_by_model[m]}")

# --- salvaged_no_thinking (pre-registered expectation 8) -----------------------------

rule("EXPECTATION 8 — salvaged_no_thinking on solo runs")
solo_modes = Counter()
for path in sorted(ROOT.glob("cells/*/runs/*/trace.json")):
    for step in json.loads(path.read_text())["steps"]:
        solo_modes[step["parse_mode"]] += 1
tot_solo = sum(solo_modes.values())
snt = sum(v for k, v in solo_modes.items() if k.startswith("salvaged_no_thinking"))
print(f"solo decision steps: {tot_solo}")
print(f"salvaged_no_thinking: {snt}"
      + (f" = {snt / tot_solo:.1%}" if tot_solo else ""))
for k, v in solo_modes.most_common():
    print(f"  {k:<44} {v}")

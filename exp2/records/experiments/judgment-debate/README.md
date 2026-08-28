# judgment-debate — the debate-only judgment-challenge run, 2026-08-28

`exp2/outputs/` is **git-ignored**. This directory is what was carried across from the run:
the **summary artifacts only**, so that every number quoted in `../../../LLM_NOTES.md` §3x
can be checked against a file rather than taken on trust. The files are byte-for-byte
copies of what the run wrote under `outputs/`, except `README.md`, `CHECKLIST.md`,
`logs/stage-tails.md`, the `transcripts/*/README.md` headers and the `HANDCHECK-*.md`
files, which were written for this directory. `PREREG.md` was committed **before** the run.

Nothing here is an input to any stage. No code reads this directory; deleting it would
break no command. It is evidence, and it is small (≈4 MB).

**Read [`CHECKLIST.md`](CHECKLIST.md) first**, and its §0 before any recourse-stage number.

## What was run

**The sweep's 1,644 decided `debate` cells, audited and re-ruled.** 2026-08-28,
01:48:17Z → 03:18:22Z (**1 h 30 m**), five stages sequentially under
`scripts/run_sweep.sh`, **every stage exit 0**, **$33.9371**, **9,982 wire calls with 0
non-2xx**, 1,643 of 1,644 cells contested (one lost to a truncated comprehension probe).

Nothing was decided and nothing was regenerated: `experiments/judgment-debate.toml` carries
`decisions_from = "outputs/experiments/sweep"`, which makes `--stage decide` refuse and
routes every decision lookup into the sweep tree. That tree was hashed before and after and
is byte-identical (`5e2eb4d69ecabcce77533fd84a75e6d8d7c6a7676a00b05701737229bdfd2d2f`).

## The question, and why it is paired

Only a debate publishes a judgment that is a document **other than** the decision itself:
`single`'s record *is* its justification and `self_critique`'s is the same model's own
drafts, so auditing the judgment against the record is a procedure that exists in one
condition and is undefined in the other two (`../../pick-auditor/DECISION.md`). So the
comparison is not between conditions. It is **paired and within debate** — the same decided
cells, before recourse and after — which is what `DESIGN.md`'s `## Judgment-challenge` asks
for.

**The pre-registered endpoint** is net accuracy change after recourse, tested with an exact
two-sided McNemar on the discordant pairs at α = 0.05. It came out **+45 cells (173 fixed,
128 broken), p = 0.0111** — positive and significant. `CHECKLIST.md` §3 is the table;
[`derivation.log`](derivation.log) is where it comes from, computed by the committed
`records/derivations/judgment-debate-vs-alone.py` from the committed `index.jsonl`.

**Read that beside `CHECKLIST.md` §0 and §7.** The ruling-line instrument fired on 30.4% of
the rulings, concentrated on FLAWED parents (50.8% against 8.2%), and a post-hoc
sensitivity that takes the reader's reading of each ruling's prose over the ruling's own
line turns +45 into −32. That sensitivity is **not pre-registered**, it was chosen after
the mismatch rate was seen, and it is only as good as the reader; it is reported because a
reader is owed the size of it.

## The two revisions, and one instrument revision

All three are dated and argued in [`PREREG.md`](PREREG.md), which was committed before the
run and amended only before it.

1. **Format (prompt only), 2026-08-28.** `google/gemini-2.5-flash` needed a format repair
   on 59 of the first pilot's 60 objections — it audits inside a correctly labelled
   `Thinking:` block and then runs into the numbered list without writing `Argument:` on a
   line of its own. Two wordings were smoked and **neither cleared its ≤1-of-6 gate**; the
   run went with the repair path, which recovers every cell. 1,588 of 1,644 objections were
   repaired and **0 cells were lost to it**. A parser leniency was refused (ground rule 7).
2. **Recourse (materiality), 2026-08-28.** The object-level ruling prompt tells the judge
   "not on the objection and not on the decision's reasoning" — right for the neutral arm,
   and exactly wrong here, where the objection *is* about the reasoning. Pilot 1 measured
   the cost: the judge re-solved the object-level question with the objection as a nudge and
   overturned 20 of 45, **35% of them on decisions that were CORRECT**. It now rules in two
   steps — is each alleged defect real against the record, and if so is it material — and
   where the decision stands it is given the decision's own `Conclusion:` line to end on.
   The neutral arm is untouched: the template is keyed on the **objection's** arm, so
   `rerule-recontest`, the third paired arm, is ruled in the form its objections were
   written for.
3. **The instrument (`ruling_agreement`), 2026-08-28.** Adapted to the materiality prompt,
   arm-keyed, after pilot 2 showed 12 of 13 alarms falling on upholds whose prose argues
   about the *defect* rather than about the text. Haiku, temperature 0, off the decision
   path — an instrument revision, not a change to the run.

## The disclosed departure

**The challenger is `google/gemini-2.5-flash`, and it was chosen AFTER the numbers.** The
auditor probe (`../../pick-auditor/`) pre-registered its floors in `RULES.md` before any
candidate was called and **no candidate cleared them — the rule picked nobody**. Flash is
the closest: on debate judgments it catches misattributions and contradictions (~95%),
misses a quarter of misquotes (71%) and two omissions in three (32%), and **invents a
defect on 15% of controls**. It is used here as the best available auditor for a
debate-only test, and that sentence stands in `../../pick-auditor/DECISION.md`, in
`PREREG.md`, in both spec headers and in the write-up. The probe measured it under the
**pre-revision** prompt with the repair path in place.

## What this run does not settle

Stated in `PREREG.md` before the run and unchanged by it:

- **A valid procedural objection does not imply a wrong verdict.** The challenger raised on
  69.8% of cells, so much of what the endpoint measures is the third-party recourse judge
  re-ruling with an objection in hand. The materiality revision narrows this — the objection
  now has a defined role — but **the same weak model still decides materiality**, and it is
  the model that decided the debate condition it is ruling on.
- **The specious-objection control is not in this run.** Every cell re-ruled on a placeholder
  objection is what separates "the audit" from "a second look", and it is still owed.
- The standing limitations in `../../../HANDOFF.md` §4 apply unchanged: natural-error
  selection bias, no `weak_alone` condition, the informed judge, and the two denominator
  subtleties.

## Reproducing the tables

```bash
cd exp2
uv run python records/derivations/judgment-debate-vs-alone.py \
    --before      records/experiments/sweep/index.jsonl \
    --neutral     records/experiments/rerule/recontest/index.jsonl \
    --procedural  records/experiments/judgment-debate/index.jsonl
```

That reads three committed indexes and nothing else — no `outputs/` tree, no network, no
API key — and reproduces every table in `derivation.log` except the defects-by-type block,
which needs `--tree outputs/experiments/judgment-debate` and says so when it is absent.

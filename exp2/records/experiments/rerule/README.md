# rerule — the ruling line, fixed and measured, 2026-08-27

`exp2/outputs/` is **git-ignored**. This directory is what was carried across from three
runs that re-ruled objections that already existed: the **summary artifacts only**, so
that every number quoted in `../../../LLM_NOTES.md` §3u can be checked against a file
rather than taken on trust. The files are byte-for-byte copies of what the runs wrote or
of what the post-run analysis wrote under `outputs/`; nothing here was edited in the
copying. `CHECKLIST.md` and this README are the only two files written for this directory.

Nothing here is an input to any stage. No code reads this directory; deleting it would
break no command. It is evidence, and it is small (≈10 MB).

**One directory, three trees.** The three runs are the same change applied to three
different sets of objections, so they share a README, a CHECKLIST and one set of hand
checks; each has its own subdirectory holding its own `metrics.json`, `index.jsonl`,
`cells.jsonl`, `experiment.json`, `DONE.md` and dry-run log.

## What was fixed

The re-contest's hand check (`../recontest/HANDCHECK-ruling-line.md`) found the recourse
judge's `Ruling: UPHOLD|OVERTURN` line contradicting the judge's **own reasoning** in
**8 of 12** sampled rulings on a **FLAWED** parent verdict — and **52 of the 62 phantom
objections overturned** against prose that agreed with the verdict. It is the pilot-2
vocabulary collision one layer down: "the objection is valid" and "the text is flawed"
both land on OVERTURN whichever way the decision went.

`DESIGN.md` `e46ada3` had already settled the re-contest's two changes; the paragraph that
settles **this** one was added in commit **`dfad084`**, under `### Recourse mechanisms`:

> **The recourse judge states its own conclusion; it is never asked to uphold or
> overturn.** The re-contest (2026-08-26) found that a weak judge asked for
> `UPHOLD|OVERTURN` contradicted its own reasoning in most rulings on FLAWED decisions —
> "the objection is valid" and "the text is flawed" were both being mapped onto OVERTURN.
> The judge is therefore told that it rules on the **original text under review** (the
> text in `<solution>`, not the objection, not the decision's reasoning, and not the
> program or proof that text may itself be assessing), and ends with an absolute line —
> *the original text contains a flaw / does not contain a flaw* — from which
> UPHOLD/OVERTURN is derived by comparison with the decision. A separate reading of the
> judge's prose measures the residual rate at which the line disagrees with it, as the
> `agreement` reading does for the challenger.

The same commit carries the code: `Ruling.form` gains `stated_conclusion` with a
`conclusion_line`, UPHOLD/OVERTURN is **derived** and never asked, a new
`ruling_agreement` stage has Haiku read the judge's prose with the line stripped, and a
spec key `contests_from` re-rules another tree's finished objections into a tree of its
own. Old `ruling.json` files are data and are never re-parsed.

## The prompt

Chosen by a 20-cell, three-variant smoke ($0.0202, `outputs/rerule-smoke/`), which re-ruled
the twenty hand-checked rulings of `../recontest/HANDCHECK-ruling-line.md` Evidence 2 under
three candidate tails. It is **variant C**, quoted verbatim from
`outputs/rerule-smoke/prompts.md`, and it replaces the whole tail of `RECOURSE_JUDGE_USER`
from "Explain your reasoning" onward:

```
You are ruling on the ORIGINAL text under review — the text inside <solution> — not on the objection and not on the decision's reasoning. Whether the objection is well argued matters only insofar as it shows what is true of that text.

The text inside <solution> may itself be an assessment of something else — a program, a proof, an argument. You are judging the TEXT, not the thing it assesses. So: if the text says the program has a bug and the program is in fact correct, the text contains a flaw. If the text correctly identifies a real bug, the text does not contain a flaw — even though a bug exists. If the text reaches the right answer by a false claim or an invalid inference, the text contains a flaw.

Explain your reasoning. Then, on the final line, state what is true of the text inside <solution>, formatted exactly as one of:

Conclusion: the original text in <solution> contains a flaw
Conclusion: the original text in <solution> does not contain a flaw
```

The middle paragraph is the whole of C's difference from B, and it exists because
`python800` — 41% of the rulings here — puts a *second* nesting inside the first: the text
under review is itself an analysis of a program, so "the analysis is right that the code
has a bug" means the text has **no** flaw. Line-vs-own-prose contradictions on the twenty:
old **8/20**, A **7/20**, B **5/19**, **C 1/20**; correct against gold **8 → 14/20**.

## The three runs

All three ran on 2026-08-27 under `RUN_SWEEP_STAGES="rerule ruling_agreement analyse"`,
three stages, every stage exit 0, `DONE.md` written. **No decision and no objection was
made or re-made by any of them**; only rulings.

| | `smoke/` | `recontest/` | `sweep/` |
|---|---|---|---|
| spec | `experiments/rerule-smoke.toml` | `experiments/rerule-recontest.toml` | `experiments/rerule-sweep.toml` |
| decisions read from | `outputs/experiments/sweep` | `outputs/experiments/sweep` | `outputs/experiments/sweep` |
| objections read from | `outputs/experiments/recontest` | `outputs/experiments/recontest` | `outputs/experiments/sweep` |
| cases | `data/cases/rerule-smoke.jsonl` (61 items) | `data/cases/ftf-all.jsonl` (2,110) | `data/cases/ftf-all.jsonl` (2,110) |
| cells in the grid | 183 | 6,330 | 6,330 |
| **rulings made** | **69** | **464** | **1,129** |
| ruling forms | `stated_conclusion`: 69 | `stated_conclusion`: 464 | `stated_conclusion`: 1,129 |
| started / finished (UTC) | 07:18:01 / 07:18:55 | 07:24:35 / 07:30:03 | 07:34:46 / 07:47:45 |
| **spend** | **$0.1205** | **$0.8109** | **$2.1371** |
| this tree's own wire calls | 139 attempts, **139 × HTTP 200** | 933, **933 × 200** | 2,275, **2,275 × 200** |
| `ruling_line_mismatch` | **1/69 = 1.4%** | **27/464 = 5.8%** | **68/1,129 = 6.0%** |

**$3.07 for all three**, plus the $0.0202 prompt smoke: **$3.09** to re-rule every
objection either full run ever raised.

**Both source trees were hashed before and after every run and are byte-identical.**
`find <tree> -type f | sort | xargs sha256sum | sha256sum`:

| tree | fingerprint |
|---|---|
| `outputs/experiments/sweep` | `5e2eb4d69ecabcce77533fd84a75e6d8d7c6a7676a00b05701737229bdfd2d2f` |
| `outputs/experiments/recontest` | `518bd5d9bd37c8eaa9ae3085f7893183e14a90011055cb0bfa07354ac608db53` |

Each `experiment.json` here records the source trees' own `experiment.json` sha256s:
`683a55c9…` for the sweep, `4706ee5d…` for the re-contest.

## Start with `CHECKLIST.md`

[`CHECKLIST.md`](CHECKLIST.md) carries the new instrument's table for all three trees, the
three hand checks with their rows filled, a top-level **"THE RULING LINE, FIXED AND
MEASURED"** section, and then **"SWEEP vs RERULE-SWEEP"** and **"RECONTEST vs
RERULE-RECONTEST"** reproducing the two comparison logs verbatim.

**Read [`HANDCHECK-ruling-line.md`](HANDCHECK-ruling-line.md) before quoting any number
out of these trees.** It is Fable's three hand checks: every one of the smoke's 69 rulings
read by eye (**69/69** lines agree with their prose), 20 of `rerule-recontest`'s read
against the new instrument (**19/20** instrument readings correct; **9 of 10** alarms
real), and 10 of `rerule-sweep`'s worst instrument cell (**10/10** alarms real, all in one
direction). The residual is real, about **6%**, flat across parent verdicts, and
concentrated in `python800`.

## What is here

| path | what it is |
|---|---|
| `CHECKLIST.md` | the instrument tables, the hand checks, the fixed-and-measured section, and the two verbatim comparisons |
| `HANDCHECK-ruling-line.md` | **the thing to read first**: Fable's three hand checks of the new line and of the instrument that measures it. Copy of `outputs/rerule-ruling-handcheck.md` |
| `SMOKE-review.md` | all **69** smoke rulings, each with its source ruling, the new `Conclusion:` line, the derived UPHOLD/OVERTURN, Haiku's independent reading and the last 600 characters of the judge's prose. Copy of `outputs/rerule-smoke-review.md` |
| `rerule-compare-smoke.log` | the smoke's 69 rulings against the re-contest's, from `../../derivations/rerule-compare.py` |
| `rerule-compare-recontest.log` | the re-contest's 464 objections under the two ruling lines |
| `rerule-compare-sweep.log` | the sweep's 1,129 objections under the two ruling lines, **and section (g)**: the strong re-decider vs the weak third-party judge on the same 682 solo objections |
| `<tree>/metrics.json` | the funnel, the rates with their CIs, the `caveats` block including `ruling_line_mismatch`, as `analyse` wrote it |
| `<tree>/index.jsonl` | one row per cell, with `ruling_form`, `ruling_prose_conclusion` and `ruling_line_mismatch` beside the detection-side columns copied unchanged from the source |
| `<tree>/cells.jsonl` | one row per cell per stage (`rerule`, `ruling_agreement`): status, error string, timing |
| `<tree>/experiment.json` | the spec each run actually ran with, both source paths and both source hashes included |
| `<tree>/DONE.md` | what the driver wrote when the third stage exited 0 |
| `<tree>/dryrun.log` | the hyperparameter tables shown to the user before each paid run, with the counted (not bounded) ruling term at the top |
| `transcripts/` | the four hand-read `transcript.md` files (below) |

The three comparison logs are also in [`../../derivations/`](../../derivations) beside
`rerule-compare.py`, which produced them; the copies here are byte-identical.

**Reproducible on a bare clone.** `rerule-compare.py` reads two committed `index.jsonl`
files and nothing else — no `outputs/`, no network, no key:

```bash
uv run python records/derivations/rerule-compare.py \
    --source records/experiments/recontest/index.jsonl \
    --rerule  records/experiments/rerule/smoke/index.jsonl
uv run python records/derivations/rerule-compare.py          # the recontest pair, by default
uv run python records/derivations/rerule-compare.py \
    --source records/experiments/sweep/index.jsonl \
    --rerule  records/experiments/rerule/sweep/index.jsonl
```

Each reproduces its log here table for table. Two lines differ and neither is a number:
the `RERULE` path in the header, and the closing **CROSS-CHECK** block, which needs
`--rerule-tree <run tree>` and is omitted without it. No table uses that block.

## The four hand-read transcripts

In [`transcripts/`](transcripts), in the shape of `../sweep/transcripts/`. All four are
from `rerule-sweep`, so both the decision and the objection are the **sweep's own**, and
only the ruling is new.

| file | cell | what it is |
|---|---|---|
| `transcripts/fix-single-python800-p02911-flawed.md` | `python800-p02911-flawed__single__r1` | genuine contest, decision SOUND and wrong, **overturned to FLAWED**, final correct |
| `transcripts/fix-self_critique-lojban-stim162_gpt3-5_B-s2.md` | `lojban-stim162_gpt3-5_B-s2__self_critique__r1` | genuine contest, decision SOUND and wrong, **overturned to FLAWED**, final correct |
| `transcripts/fix-debate-law-con2_gpt3-5_A-s6.md` | `law-con2_gpt3-5_A-s6__debate__r1` | genuine contest, decision SOUND and wrong, **overturned to FLAWED**, final correct |
| `transcripts/upheld-debate-law-con5_gpt4_A-s7.md` | `law-con5_gpt4_A-s7__debate__r1` | genuine contest on a decision that was **right**. The sweep's judge overturned it and the cell ended wrong; the new line **upholds** and the cell ends correct |

**The three `fix-` cells are the same three cells `../sweep/transcripts/` holds** —
`single-python800-p02911-flawed.md`, `self_critique-lojban-stim162_gpt3-5_B-s2.md` and
`debate-law-con2_gpt3-5_A-s6.md`, the sweep's own exemplary overturns. In the sweep the
first two were overturned by the **strong re-decider** re-deciding in its own conversation
(`restated_verdict`) and the third by the weak third-party judge's old relative line. Here
all three are overturned by the **weak third-party judge stating its own conclusion about
the text** — the same outcome reached by a ruler that is weak, external, and now says in
its last line what its reasoning says. Read the two versions side by side: that is what
the fix looks like on a cell.

The fourth is the other half of the same claim: a ruler that discriminates has to be able
to say no, and this is a cell where the old line said yes and broke a correct decision.

## What is deliberately not here

`calls.jsonl` (139 + 933 + 2,275 of this tree's own attempts, plus the copied parents'),
the per-cell `contests/` directories with their `ruling.source.json` and both published
documents per ruling, and the `transcript_full.md` companions of the four transcripts. A
reader wanting to re-derive a number from raw generations has to re-run the stage; at
$3.07 and 20 minutes that is affordable — but it needs both source trees on disk, and
those are 40 GB that no longer exist anywhere but this pod.

## The warning from `../../README.md` applies here too

**Neither `transcript.md` nor `transcript_full.md` may ever be shown to a model.** Both
end with a `## Ground truth` section carrying the gold label and the flaw annotation
(LLM_NOTES §3e).

And the comparability rule: **`rerule-sweep` and the sweep, and `rerule-recontest` and the
re-contest, ARE comparable** — same items, same decisions, same objections, one
measurement layer swapped — and that is the whole point of them. `rerule-smoke` is a
subset of `rerule-recontest`'s cells chosen for being the known failures, so it is a
diagnostic and not a sample of anything. No other two runs in this repository may be
compared cell for cell.

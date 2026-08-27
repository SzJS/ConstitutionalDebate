# recontest — the re-contest of the first full sweep, 2026-08-26

`exp2/outputs/` is **git-ignored**. Everything this run wrote lives there, on a disk that
has been wiped once already and will be again. This directory is what was carried across:
the **summary artifacts only**, so that every number quoted in `../../../LLM_NOTES.md`
§3t can be checked against a file rather than taken on trust. The files are byte-for-byte
copies of what the run wrote or of what the post-run analysis wrote under `outputs/`;
nothing here was edited in the copying. `CHECKLIST.md` and this README are the only two
files written for this directory.

Nothing here is an input to any stage. No code reads this directory; deleting it would
break no command. It is evidence, and it is small (≈7.7 MB).

## The run

| | |
|---|---|
| spec | `experiments/recontest.toml` |
| **decisions from** | **`outputs/experiments/sweep`** — the sweep tree, never written to. Its whole-tree fingerprint (`find … -type f | sort | xargs sha256sum | sha256sum`) is **`5e2eb4d6…`** before and after this run; `experiment.json` here records the source `experiment.json`'s own sha256 as `683a55c9…` |
| corpus | `data/cases/ftf-all.jsonl` — 2,110 items |
| cells | 6,330 = 2,110 × 3 conditions × 1 repeat; **5,724 of them had a decision to contest, and all 5,724 were contested** |
| stages | **four** — `contest agreement grade analyse`, under `RUN_SWEEP_STAGES` |
| started (UTC) | 2026-08-26T22:14:22Z |
| finished (UTC) | 2026-08-26T23:38:34Z |
| wall-clock | **84 min**, four stages sequentially, every stage exit 0 |
| spend | **$10.8942**, $0.00190 per contested cell (the sweep's $32.1326 of decisions was not re-paid) |
| transport | this tree's own calls: **18,430 attempts, 18,427 × HTTP 200**, and 3 client-side `ReadTimeout`s retried to completion |
| models | challenger and recourse judge `openai/gpt-4.1-nano`; `agreement` and grader `anthropic/claude-haiku-4.5`. **No strong-model call was made** — nothing was decided |
| tests | 361 pass |

## What it tests — three changes, and nothing else

The sweep found two defects in the **measurement**, not in the generated records
(`../sweep/CHECKLIST.md`, `LLM_NOTES.md` §3s). `DESIGN.md` commit `e46ada3` settled what
to do about them; this run is that, applied to the sweep's own 5,724 decisions.

1. **The challenger decides last** (`6a911f3`). The sweep asked for `Decision:` at the
   head of the reply and gpt-4.1-nano wrote it before reasoning — **51.8% of its
   objections were phantoms**, a REVERSE line over prose arguing the verdict was right.
   The instruction now asks for reasons first and the line **last**, and glosses each word
   in the phrases of *this* decision; `parse_objection_output` takes the **last** match.
2. **Recourse is a weak third party in every condition** (`6a911f3`,
   `recourse_form = "third_party"`). The sweep ruled `debate` by a third-party weak judge
   and the two solo conditions by the strong decider re-deciding in its own conversation —
   an asymmetry that, on its own numbers, explained most of `self_critique`'s edge. Every
   ruling in this tree is `uphold_overturn`. The in-conversation form is kept, wired and
   tested, as the ablation `DESIGN.md` asks for; it was not run.
3. **The challenger is told where its published reasons go** (`6af26bb`). Smoke 1 sent
   format repairs from ~0 to 10 of 18 replies because the model opened `Thinking:` and
   never closed it with `Argument:`. One sentence fixed it; smoke 2 measured 2 of 18.

## Start with `CHECKLIST.md`

[`CHECKLIST.md`](CHECKLIST.md) is the ten-row checklist in the shape of
[`../sweep/CHECKLIST.md`](../sweep/CHECKLIST.md), plus the three funnels, the second-draw
note, a reconciliations section, and — the reason this directory exists — a top-level
**"SWEEP vs RECONTEST"** section reproducing `recontest-vs-sweep.log` verbatim: the two
runs joined cell by cell on identical decisions.

**Rows 1, 2, 3, 6, 7 and the second-draw table describe the SWEEP's decisions**, read
through `sweep-checks.py --decisions`. They are reproduced, not re-measured.

**Read [`HANDCHECK-ruling-line.md`](HANDCHECK-ruling-line.md) before quoting any number
that came out of the recourse stage.** A hand check of the recourse judge's
`Ruling: UPHOLD|OVERTURN` line found that it contradicts the judge's *own reasoning* in
**8 of 12** sampled rulings on a **FLAWED** parent verdict — and in **0 of 8** on a SOUND
one — and that **52 of the 62 phantom objections were "overturned"** although every one of
them sits on a FLAWED parent and argues the verdict was right. Overturn rates,
`revised_*`, discrimination and net accuracy all pass through that line, in this run **and
in the sweep's `debate` condition**, which the same judge ruled with the same prompt. The
detection side — objection counts, phantom shares, true detection, false alarms — never
touches it and is unaffected. `CHECKLIST.md`'s section
**"THE RULING LINE IS UNRELIABLE ON FLAWED PARENTS"** carries the evidence.

The three checks `HANDOFF.md` §5 requires are **done** and in this directory:
[`HANDCHECK-agreement.md`](HANDCHECK-agreement.md) (20 replies, 11/20),
[`HANDCHECK-graded.md`](HANDCHECK-graded.md) (all 46 graded rows), and the four
[`transcripts/`](transcripts) below. The ruling-line check was not on that list; it came
out of reading the transcripts.

## What is here

| path | what it is |
|---|---|
| `CHECKLIST.md` | the ten-row checklist, the three funnels, the reconciliations, and "SWEEP vs RECONTEST" |
| `checks.log` | the raw output of `../../derivations/sweep-checks.py outputs/experiments/recontest --decisions outputs/experiments/sweep`, exit 0 |
| `recontest-vs-sweep.log` | the paired comparison, the output of `../../derivations/recontest-vs-sweep.py`. **Reproducible on a bare clone** for sections (a)–(g): the script reads only the two committed `index.jsonl` files. Section (h) needs the run tree and prints what it could not read when run from here |
| `metrics.json` | the funnel, the rates with their CIs, the `caveats` block, as `analyse` wrote it |
| `index.jsonl` | one row per contested cell (5,724): the sweep's decision and correctness, this run's stance, prose reading, ruling form, grade |
| `cells.jsonl` | one row per cell per stage (18,990 = 6,330 × 3 stages): status, error string, timing |
| `experiment.json` | the spec the run actually ran with, `decisions_from` and the source tree's hash included |
| `DONE.md` | what the driver wrote when the fourth stage exited 0 |
| `SMOKE-2-review.md` | the 18-cell prompt check, sweep vs smoke-1 vs smoke-2 side by side, with every reply's line/prose/phantom reading — the run that settled the instruction before any slice |
| `PILOT-207-review.md` | the 207-cell validation slice on pilot 3's items, and the two defects it exposed: genuine detection halved, and the instruction's gloss leaking into 5 of 194 published objections |
| `dryrun.log` | the three hyperparameter tables shown to the user before the paid run |
| `HANDCHECK-ruling-line.md` | **the finding that changes how this run is read**: the recourse judge's `Ruling:` line vs its own reasoning — 8 contradictions in 12 FLAWED-parent rulings, 0 in 8 SOUND-parent ones, 52 of 62 phantoms "overturned" |
| `HANDCHECK-agreement.md` | the 20-reply line-vs-prose hand check — **11/20**, all eight misreads on STANDS lines, none on REVERSE, seven of the eight in python800 |
| `HANDCHECK-graded.md` | the hand check of all 46 graded rows — valid **21/46 = 45.7%** (21/41 = 51% excluding gpqa's structurally-invalid five), one valid grade with no reasoning, two rows that would be graded differently |
| `transcripts/` | the four hand-read `transcript.md` files (below) |

## The four hand-read transcripts

In [`transcripts/`](transcripts), named `<label>-<item>.md`, in the shape of
`../sweep/transcripts/`. Selected to the sweep's stricter brief: a genuine contest that
**overturned** a wrong decision, one per condition, plus a decline on a wrong decision.

| file | cell | what it is |
|---|---|---|
| `transcripts/single-python800-p03450-sound.md` | `python800-p03450-sound__single__r1` | genuine contest, overturned FLAWED → SOUND, final correct. **One of only two `single` cells in the whole run where a genuine contest overturned a wrong decision** (2 of 241 wrong `single` decisions; the sweep had 1). Its parent verdict is FLAWED, so its ruling is in the stratum `HANDCHECK-ruling-line.md` found unreliable — read the judge's prose, not the line |
| `transcripts/self_critique-law-evi2_gpt3-5_B-s6.md` | `law-evi2_gpt3-5_B-s6__self_critique__r1` | genuine contest, overturned SOUND → FLAWED, final correct, **graded valid**. The sweep's challenger *declined* on this cell |
| `transcripts/debate-python800-p02684-flawed.md` | `python800-p02684-flawed__debate__r1` | genuine contest, overturned SOUND → FLAWED, final correct, **graded valid**. The sweep's challenger also declined here |
| `transcripts/decline-debate-law-con2_gpt3-5_A-s6.md` | `law-con2_gpt3-5_A-s6__debate__r1` | **declined on a wrong decision — and this is the same cell `../sweep/transcripts/debate-law-con2_gpt3-5_A-s6.md` holds as `debate`'s exemplary overturn.** In the sweep the challenger objected, the judge overturned, the decision came out correct; on the same record, with the decide-last prompt, the re-contest's challenger narrates both debaters and declines. The cell ends wrong and unchallenged |

Two of the four rulings are on SOUND parents and one on a FLAWED parent; the decline has
no ruling.

## What is deliberately not here

`calls.jsonl` (18,430 records), the 5,724 per-cell `contests/` directories, their
`parent/` copies of the sweep's decision, both published documents per contest, and the
`transcript_full.md` companions of the four transcripts (`checks.log` gives every full
path). A
reader wanting to re-derive a number from raw generations has to re-run the stage; at
$10.89 and 84 minutes that is, unusually for this repository, affordable.

## The warning from `../../README.md` applies here too

**Neither `transcript.md` nor `transcript_full.md` may ever be shown to a model.** Both
end with a `## Ground truth` section carrying the gold label and the flaw annotation
(LLM_NOTES §3e).

And, unlike every other pair of runs here: **this run and the sweep ARE comparable**, and
that is the whole point of it. Same items, same decisions, same generations — one
measurement layer swapped. No other two runs in this repository may be compared that way.

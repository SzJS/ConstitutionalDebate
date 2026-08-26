# sweep — the first full sweep, 2026-08-26

`exp2/outputs/` is **git-ignored**. Everything this run wrote lives there, on a disk that
has been wiped once already and will be again. This directory is what was carried across:
the **summary artifacts only**, so that every number quoted in `../../../LLM_NOTES.md`
§3s can be checked against a file rather than taken on trust. The files are byte-for-byte
copies of what the run wrote; nothing here was edited.

Nothing here is an input to any stage. No code reads this directory; deleting it would
break no command. It is evidence, and it is small (≈8.5 MB).

## The run

| | |
|---|---|
| spec | `experiments/sweep.toml` |
| corpus | `data/cases/ftf-all.jsonl` — 2,110 items |
| cells | 6,330 = 2,110 × 3 conditions × 1 repeat |
| started (UTC) | 2026-08-26T01:14:17Z |
| finished (UTC) | 2026-08-26T18:30:34Z |
| wall-clock | **17 h 16 m**, five stages sequentially, every stage exit 0 |
| decided | **5,724 / 6,330 = 90.4%** — 606 lost to truncation, under the 14.5% budgeted |
| spend | **$32.1326**, $0.00561 per decided cell, against a $34 projection |
| models | strong `deepseek/deepseek-v4-flash-0731` pinned to `gmicloud/fp8, coreweave/fp8`; weak judge and challenger `openai/gpt-4.1-nano`; grader `anthropic/claude-haiku-4.5` |
| tests | 344 pass |

**Start with [`CHECKLIST.md`](CHECKLIST.md).** It is the ten-row checklist in the shape of
`../pilot-3/CHECKLIST.md`, with the pooled, per-subset and per-`label_basis` funnels, the
second-draws section §3r requires, and a section reconciling the two valid-objection
denominators. It also names the two things `HANDOFF.md` §5 asks for that have **not** been
done: the 20-reply line-vs-prose hand check, and the hand check of all 99 graded rows.

## What is here

| path | what it is |
|---|---|
| `CHECKLIST.md` | the ten-row checklist, the three funnel tables, the second-draws count, the denominator reconciliations |
| `checks.log` | the raw output of `../../derivations/sweep-checks.py` over `outputs/experiments/sweep` — every number in `CHECKLIST.md` is quoted from here or from `metrics.json` |
| `metrics.json` | the funnel, the rates with their CIs, the `caveats` block, as `analyse` wrote it |
| `index.jsonl` | one row per decided cell (5,724): verdict, correctness, stance, prose reading, ruling form, grade |
| `cells.jsonl` | one row per cell per stage (25,350): status, error string, timing — the failure counts and the loss shapes |
| `experiment.json` | the spec the run actually ran with, every hyperparameter as sent |
| `DONE.md` | what the driver wrote when the fifth stage exited 0 |

## What is deliberately not here

`calls.jsonl` (the wire log, ~54,000 records), the 6,330 per-cell `runs/` directories,
their `parent/` copies, and both published documents per run. Together those are the
~4 GB the run wrote under `outputs/experiments/sweep/`, and they are the raw material,
not the evidence. A reader wanting to re-derive a number from raw generations has to
re-run the stage; the price of doing so is on record above.

The four hand-read transcripts are **not** copied yet, because they have not been read
yet. `CHECKLIST.md` Row 10 names the four cells and `checks.log` gives their full paths;
when they are read they belong here beside the pilot-3 set, under
`../../pilot-3-hand-read/`'s convention.

## The warning from `../../README.md` applies here too

**Neither `transcript.md` nor `transcript_full.md` may ever be shown to a model.** Both
end with a `## Ground truth` section carrying the gold label and the flaw annotation
(LLM_NOTES §3e).

And: **the pilots and this sweep are not comparable with each other.** Prompts, corpus and
routing changed between all four runs, in the same runs, with no controlled arm. Two
figures do line up and are noted in `CHECKLIST.md` as observations rather than
comparisons — the 22.5% strong-model repair rate and the ~16% native-reasoning rate — and
even those were measured on different corpora.

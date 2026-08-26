# records — the small evidence, kept in git

Everything this experiment has measured was written under `exp2/outputs/`, which is
**git-ignored** and lived on a RunPod with a 5 GB disk. That pod is being rebuilt with a
larger one, which wipes `outputs/`, `data/`, `.venv` and `.env`. The wire logs
(`calls.jsonl`), the per-cell run directories and the full probe traces **are gone with
it** and are not recoverable without paying for the runs again.

This directory is what was carried across: the **summary artifacts only**, so that every
number quoted in `../LLM_NOTES.md` §7 (and the §1b, §3h, §3l–§3n numbers it rests on)
can still be checked against a file rather than taken on trust. Nothing here was
edited — the files are byte-for-byte copies of what the runs wrote.

Nothing here is an input to any stage. No code reads this directory; deleting it would
break no command. It is evidence, and it is small (≈4 MB).

The one thing here that is meant to be *run* again is `derivations/`. What each script
does now is **not** the same across the eight, so the blanket "none of them work" that
used to stand here is replaced by the truth per script. All of them must be run from `exp2/`
(the pilot-3 scripts insert `src` on `sys.path`; `sweep-1-provider-check.py` imports the
installed package under `uv run` and needs the root `.env`).

| script | state now |
|---|---|
| `sweep-1-provider-check.py` | **live, and the pre-run check.** One paid call (~$0.00001) against OpenRouter. It reads nothing under `outputs/`, builds its request with `client.OpenRouterClient._build_body` so the call it tests is the call the run makes, and prints `SERVED BY: <provider>` and `VERDICT: PASS`/`FAIL`, exiting non-zero on FAIL. `HANDOFF.md` §5 step 2 runs it; `logs/sweep-provider-check.log` is a passing run. |
| `pilot-3-checks.py` | **takes a `ROOT` argument** (`sys.argv[1]`, default `outputs/experiments/pilot-3`) and derives a whole CHECKLIST from any finished run's directory. This is the one to point at the sweep. |
| `sweep-1-checks2.py` | same, default `outputs/experiments/sweep-1`. The follow-up pass: truncation shape, repair scar, revision rates. |
| `sweep-1-funnel.py` | same, default `outputs/experiments/sweep-1`. Reads only `metrics.json` and `index.jsonl`, so it runs against any analysed run. |
| `pilot-3-paths.py`, `pilot-3-handcheck-sample.py` | same, both take a `ROOT` (the sample script also takes `N`). They pick the cells for a hand read, which the sweep needs too. |
| `pilot-2-shapes.py`, `pilot-3-checks2.py` | **hard-coded** to `outputs/experiments/pilot-2` and `-pilot-3`, which were wiped. One line each to re-point; until then they are a record of a derivation, not a runnable script. `sweep-1-checks2.py` is the generalised `pilot-3-checks2.py`, so prefer it. |

Two `.log` files there have no `.py` beside them — `pilot-3-funnel.log` (superseded by
`sweep-1-funnel.py`, which is the same derivation with the root as an argument) and
`pilot-3-timing.log`. They are output, kept as evidence.

## A vocabulary note

"Step A", "Step B", "Step G", "D1" and the like — in `experiments/pilot-3/GATE.md`,
`logs/sweep-1-estimate.txt` and `../LLM_NOTES.md` — name steps of a **plan file that
lived in `/root/.claude/plans/` on the pod that was wiped**. It is gone and is not
recoverable. `../HANDOFF.md` §5 replaces it; nothing here depends on the plan except
these labels.

`GATE.md` is likewise a **historical** gate: its five rows were the go/no-go between
pilot 3 and the abandoned `sweep-1` slice, and they are stricter than the four
catastrophic stop triggers in `HANDOFF.md` §5, which are the ones that apply to the
sweep. Do not re-apply `GATE.md`'s thresholds to a run it was not written for.

## What is here

| path | what it is | what it backs |
|---|---|---|
| `experiments/{pilot,pilot-2,pilot-3}/CHECKLIST.md` | the go/no-go checklist for each pilot, every row with its number and its derivation | LLM_NOTES §7's pilot sections |
| `experiments/*/metrics.json` | the funnel, the rates, the caveats block, as `analyse` wrote it | every rate in §7 and §3n |
| `experiments/*/index.jsonl` | one row per decided cell: verdict, stance, prose reading, ruling, grade | anything re-derived per cell |
| `experiments/*/cells.jsonl` | one row per cell per stage: status, error string, timing | the failure counts and the loss shapes |
| `experiments/*/experiment.json` | the spec each run actually ran with | which hyperparameters produced which numbers |
| `experiments/pilot-3/GATE.md` | the five-row permissive gate applied before the sweep | the decision to proceed |
| `experiments/sweep-1/experiment.json` | the abandoned slice's spec as it ran | LLM_NOTES §7's sweep-1 entry |
| `pick-weak/DECISION.md` | the weak-model choice and the subset screen, written by `scripts/pick_weak.py` | §1b in full |
| `pick-weak/rows.jsonl` | probe 2's six candidates, one row per call-level outcome | §1b, §3h's six-candidate row |
| `pick-weak/rows-{solo,judge,challenger}-<model>.jsonl` | the same, per pass and per model, **including probe 1's three candidates** | §3h's first-probe McNemar (46 hurt / 24 helped, p = 0.0115) |
| `pick-weak/settings.json`, `liveness.json` | the probe's own hyperparameters, and which models answered a liveness call | §1's live-model table |
| `pick-weak/summary-2.txt`, `tiebreak.txt`, `nano-subsets.txt` | the spend derivation, the tiebreak table, nano's per-subset zones | §7's cost table, §1b |
| `pick-weak/fixture-releak.log` | re-parsing every fixture argument with the fixed `_ANY_THINKING_RE` | §3i's "3 of 426 published arguments" |
| `pick-weak/review/*.md` | the **14 hand-review transcripts** rendered by `scripts/render_probe.py` | the "transcripts are illegible to weak judges" reading behind §3h |
| `logs/*-dryrun.log` | every hyperparameter table each run printed before it spent anything | the repo rule that values are shown and confirmed first |
| `logs/pilot-3-provider-check.log` | the endpoints-API check and five real pinned calls, including the wrong-slug control | §3n.4 — the unescaped model id, and the 404 that reads as retryable |
| `logs/sweep-provider-check.log` | **the reference passing run** of `derivations/sweep-1-provider-check.py`: `SERVED BY: GMICloud`, `VERDICT: PASS` | `HANDOFF.md` §5 step 2 — what a pass looks like |
| `logs/sweep-1-provider-check.log` | the same check before the abandoned slice, run by the earlier script that sent no `reasoning` key: it printed a pass on `content: None` | why the check was rewritten (§3n.4) |
| `logs/sweep-1-estimate.txt` | the abandoned sweep-1 slice's cost and disk projection | §7's sweep-1 entry |
| `logs/sweep-1-decide.log` | that run's own log, ending in 145 `[Errno 28] No space left on device` and `completed=80 error=633 failed=10` | that sweep-1 died of a full disk and not of anything about the experiment |
| `logs/sweep-dryrun.log`, `logs/get-tasks-all-concat.log` | the hyperparameter tables and the corpus counts a fresh pod should reproduce | `HANDOFF.md` sections 3 and 5 |
| `logs/get-tasks*.log`, `logs/make-slice-1.log` | corpus counts and per-file md5s at each build | that a corpus rebuilt on a new pod is the same corpus |
| `logs/pilot-3-paths.log` | how the four hand-read contests below were selected | §3n's outcome section |
| `derivations/*.py` | the scripts that re-derived each checklist's numbers from disk, with their `.log` output beside them | every number in `experiments/*/CHECKLIST.md` |
| `derivations/sweep-1-provider-check.py` | the provider-slug check `HANDOFF.md` section 5 says to run before a sweep: an endpoints read plus one real pinned call, with a PASS/FAIL verdict and a non-zero exit on FAIL | §3n.4; it is a **paid** script, one call |
| `pilot-3-hand-read/<cell>/transcript{,_full}.md` | the four contests read by hand: a genuine contest in each condition, and a decline on a wrong decision | the transparency claim, read rather than counted |

## Two warnings

**Neither `transcript.md` nor `transcript_full.md` may ever be shown to a model.** Both
end with a `## Ground truth` section carrying the gold label and the flaw annotation
(LLM_NOTES §3e). They are safe only because no model-facing module reads them, which is
asserted by `test_no_model_facing_module_reads_the_published_documents`.

**The pilots are not comparable with each other.** Prompts, corpus and routing changed
between all three, in the same runs, with no controlled arm. Every one of these
directories says so in its own words; a table putting two of them side by side is
comparing different questions asked of different inputs.

## What is deliberately not here

`calls.jsonl` (the wire log), the per-cell `runs/` directories, `parent/` copies, the
probe's `calls-*.jsonl` and `fixture*.jsonl`. Together those are ~400 MB and they are
the raw material, not the evidence: a reader wanting to re-derive a number from raw
generations has to re-run the stage, and the price of doing so is on record.

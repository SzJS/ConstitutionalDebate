# records — the small evidence, kept in git

Everything this experiment has measured was written under `exp2/outputs/`, which is
**git-ignored** and lived on a RunPod with a 5 GB disk. That pod is being rebuilt with a
larger one, which wipes `outputs/`, `data/`, `.venv` and `.env`. The wire logs
(`calls.jsonl`), the per-cell run directories and the full probe traces **are gone with
it** and are not recoverable without paying for the runs again.

This directory is what was carried across: the **summary artifacts only**, so that every
number quoted in `../LLM_NOTES.md` §7 (and the §1b, §3h, §3l–§3n numbers it rests on)
can still be checked against a file rather than taken on trust. The files are
byte-for-byte copies of what the runs wrote, with **two logs excepted** — see "The one
exception to 'nothing here was edited'" below, which names every line that differs and
why.

Nothing here is an input to any stage. No code reads this directory; deleting it would
break no command. It is evidence, and it is small (≈33 MB — the sweep, the re-contest
and the three re-rule trees are most of it).

The one thing here that is meant to be *run* again is `derivations/`. What each script
does now is **not** the same across them, so the blanket "none of them work" that
used to stand here is replaced by the truth per script. All of them must be run from `exp2/`
(the pilot-3 scripts insert `src` on `sys.path`; `sweep-1-provider-check.py` imports the
installed package under `uv run` and needs the root `.env`).

| script | state now |
|---|---|
| `sweep-1-provider-check.py` | **live, and the pre-run check.** One paid call (~$0.00001) against OpenRouter. It takes the spec as its argument (default `experiments/sweep.toml`) and reads the model and the pin **out of it** — `[debate] debater_model` and that model's entry in `[debate.provider_order]` — so it checks the slugs the spec actually sends. It reads nothing under `outputs/`, builds its request with `client.OpenRouterClient._build_body` so the call it tests is the call the run makes, and prints `SERVED BY: <provider>` and one of three verdicts: `PASS` (exit 0) only when the **first** pinned provider served it; `WAIT` (exit 4) when another pinned provider did, because `order` is a preference list and the fallback is not the provider the routing argument was made about; `FAIL` (exit 1/2/3/5) otherwise. `HANDOFF.md` §5 step 2 runs it; `logs/sweep-provider-check.log` is a passing run. |
| `pilot-3-checks.py` | **takes a `ROOT` argument** (`sys.argv[1]`, default `outputs/experiments/pilot-3`) and derives a whole CHECKLIST from any finished run's directory. This is the one to point at the sweep. |
| `sweep-checks.py` | the generalised `pilot-3-checks.py`: the same ten rows over any tree (`sys.argv[1]`, default `outputs/experiments/sweep`), and it prints `NOT YET RUN` for stages that have not run rather than a zero, so it is safe on a live tree. Adds the per-subset funnel, the per-`label_basis` funnel and the second-draw count §3r requires. It needs a **run tree**, so on a machine with no `outputs/` it has nothing to read; `experiments/sweep/checks.log` is its output over the finished sweep. |
| `sweep-phantom-corrected.py` | **the only derivation here that runs on a bare `git clone`.** It reads `experiments/sweep/index.jsonl` (`sys.argv[1]`, that path by default) and nothing else — no `outputs/`, no network, no key — and reprints the phantom-corrected funnel: true detection with a contest counted only when the line said REVERSE *and* the prose read WRONG, the phantom share on both denominators, false alarms, revision given a genuine contest, end-to-end, and the net effect on accuracy. Reproduces `experiments/sweep/phantom-corrected.log` number for number; `sweep-phantom-corrected.log` beside it is a run of it. |
| `sweep-1-checks2.py` | same, default `outputs/experiments/sweep-1`. The follow-up pass: truncation shape, repair scar, revision rates. |
| `sweep-1-funnel.py` | same, default `outputs/experiments/sweep-1`. Reads only `metrics.json` and `index.jsonl`, so it runs against any analysed run. |
| `pilot-3-paths.py`, `pilot-3-handcheck-sample.py` | same, both take a `ROOT` (the sample script also takes `N`). They pick the cells for a hand read, which the sweep needs too. |
| `recontest-vs-sweep.py` | **runs on a bare `git clone`** for sections (a)–(g): it joins `experiments/sweep/index.jsonl` and `experiments/recontest/index.jsonl` on `cell_id`, asserts cell by cell that the decisions are the same generations, and prints the two runs side by side. Section (h) needs the re-contest's run tree and prints what it could not read. `experiments/recontest/recontest-vs-sweep.log` is its output. |
| `rerule-compare.py` | **runs on a bare `git clone`.** It takes a SOURCE index and a RERULE index (`--source`, `--rerule`) and prints the same objections under two ruling lines: the join, the ruling forms, the new `ruling_line_mismatch` instrument split by parent verdict, overturn rates by what was actually objected to, discrimination, the net effect on accuracy in `sweep-phantom-corrected.py`'s definitions, the per-cell ruling transitions, and — when the source is the sweep — the paired **strong re-decider vs weak third-party judge** table on its 682 solo objections. A cross-check against the run tree runs when the tree is there and no table uses it. The three `rerule-compare-*.log` files beside it are its output, copied into `experiments/rerule/`. |
| `partisan-vs-neutral.py` | **runs on a bare `git clone`.** It takes a NEUTRAL index (`--neutral`, default `experiments/rerule/recontest/index.jsonl`) and ONE OR MORE PARTISAN indices (`--partisan`, one column each) and prints the same decisions contested by different challengers: the join with a cell-by-cell identity assertion on `verdict`/`initially_correct`/`gold_flawed`, what the challenger did (raised, genuine, phantom, declines split by whether the decision was in fact right), the `ruling_line_mismatch` instrument, overturn by what was actually objected to with discrimination, the net effect on accuracy, end-to-end, the grader, the plan's **go/no-go rule computed**, and the per-cell stance transitions neutral → partisan. A re-rule tree carries stances only for the cells it re-ruled, so `--neutral-stances` (default `experiments/recontest/index.jsonl`) fills the rest in and asserts they agree wherever both indices have one; `--no-stance-fill` turns it off. `experiments/partisan-pilots/partisan-vs-neutral.log` is its output over the three pilot clauses. |
| `judgment-debate-vs-alone.py` | **runs on a bare `git clone`.** The debate-only run's paired endpoint. Takes a BEFORE index (`--before`, default the sweep's), a NEUTRAL index (`--neutral`, default `experiments/rerule/recontest/index.jsonl`) and a PROCEDURAL index (`--procedural`), restricts to `condition == debate`, and prints: the join with a cell-by-cell identity assertion on `verdict` and `initially_correct`; **(a)** the primary 2x2 with fixed / broken / net, the exact two-sided McNemar on the discordant pairs (`math.comb`, no `scipy`) and both accuracies with 95% Wilson intervals; **(b)** the third paired arm, neutral-after against procedural-after on the same cells, plus before-against-neutral for reference; **(c)** the secondaries — raise rate, phantom share, valid-objection rate split by whether the decision was right, misattributed quotes, overturn rates with the discrimination, `ruling_line_mismatch` by parent verdict; **(d)** defects by type, the one block that needs `--tree`; **(e)** per subset and label basis; **(f)** a **post-hoc, not pre-registered** sensitivity that substitutes the materiality reader's reading of each ruling's prose for the ruling's own line. Tested in `tests/test_derivations.py` against a hand-computed p (b=10, c=3 → 756/8192). `experiments/judgment-debate/derivation.log` is its output over the committed indexes. |
| `judgment-debate-smoke-pick.py` | read-only over the first instrument check's tree. Picks the six debate cells the two format smokes ran on — two omission-only objections, two misstatements, two substantive declines — and writes them as a cases file. Needs `outputs/experiments/judgment-debate-pilot`, so it does not run on a bare clone. |
| `rerule-smoke-pick.py` | read-only. Draws the items of the re-contest's 62 phantom cells out of `experiments/recontest/index.jsonl` into the smoke's case file. Runs on a bare clone. |
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
| `experiments/sweep/` | **the first full sweep, 2026-08-26 — the run this repository exists to have done.** Its own [`README.md`](experiments/sweep/README.md) lists the directory; start at `CHECKLIST.md`, whose "THE PHANTOM-CORRECTED FUNNEL" section is the headline. Also there: `DONE.md`, the two hand checks, `phantom-corrected.log`, and the four hand-read transcripts | `LLM_NOTES.md` §3s in full, and `HANDOFF.md` §4's sweep paragraph |
| `experiments/partisan-pilots/` | **the partisan challenger, tried on three clauses and stopped, 2026-08-27.** Three 194-cell pilots that contested the sweep's own decisions under three wordings of one standpoint paragraph, the neutral baseline beside them, and the go/no-go the plan wrote before the runs. All three fail it; the ~$22 full run was never started. Start at [`CHECKLIST.md`](experiments/partisan-pilots/CHECKLIST.md) | `LLM_NOTES.md` §3v, and `HANDOFF.md` §4's partisan paragraph |
| `experiments/judgment-debate/` | **the debate-only judgment-challenge run, 2026-08-28 — the paired measurement the judgment variant was built for.** The sweep's 1,644 decided `debate` cells audited and re-ruled, $33.94, five stages exit 0. Its [`PREREG.md`](experiments/judgment-debate/PREREG.md) was committed before the run and carries the endpoint, the stated confound, the two prompt revisions and the instrument revision. Start at [`CHECKLIST.md`](experiments/judgment-debate/CHECKLIST.md) and read its **§0** before any recourse-stage number. `pilot-1/` and `pilot-2/` are the two 60-cell instrument checks; `transcripts/` holds four cells whole. | `LLM_NOTES.md` §3x, and `HANDOFF.md` §4's judgment-debate paragraph |
| `experiments/judgment-debate-3/` | **the one-judge campaign, 2026-08-28** — `llama-4-maverick` judging the debates AND ruling on the appeals, four arms (real audit, placeholder, specious, gatekeeper) on the sweep's 1,644 debate cells, $90.95. The endpoint is a NULL (−18, p = 0.27). Start at its [`CHECKLIST.md`](experiments/judgment-debate-3/CHECKLIST.md) **§0**, and read **§1b** before quoting the specious arm | `LLM_NOTES.md` §3y, `HANDOFF.md` §4 |
| `experiments/judgment-debate-4/` | **the fabricated auditor, 2026-08-28** — an objection whose every `Judgment says:` quotation is INVENTED, put to the same judge on the 896 cells the real audit contested, $13.89. The manipulation check is a **string comparison and not a grader** (96.0%), and the finding is a **missing existence check** in the ruling prompt: the judge verifies the record quotation and never asks whether the judgment contains the sentence attributed to it. Start at its [`CHECKLIST.md`](experiments/judgment-debate-4/CHECKLIST.md) **§0** | `LLM_NOTES.md` §3z, `HANDOFF.md` §4 |
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
| `logs/sweep-provider-check.log` | **the reference passing run** of `derivations/sweep-1-provider-check.py`: `SERVED BY: GMICloud`, `VERDICT: PASS`. Its four header lines and its verdict line are **re-typed to the current print format** — see "The one exception" below; everything between them is the run's own output | `HANDOFF.md` §5 step 2 — what a pass looks like |
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

## The one exception to "nothing here was edited"

Two logs no longer match, line for line, the code that produced them.

* `logs/sweep-dryrun.log` was **re-recorded** on 2026-08-26 with
  `uv run exp2-experiment --spec experiments/sweep.toml --stage decide --dry-run 2>&1 | tee outputs/sweep-dryrun.log`
  after the resume rule changed (LLM_NOTES §3q). Two lines differ from the previous
  copy — the attempts header and `max_decision_attempts`'s WHY. The corpus, the cell
  counts and the call estimate reproduce byte for byte, which is the thing this log
  exists to let a fresh pod check.
* `logs/sweep-provider-check.log` was recorded by the **previous version** of
  `derivations/sweep-1-provider-check.py`, which hard-coded the model and the pin and
  passed on either pinned provider. Re-running it costs a paid call, so instead its
  four header lines (`spec:`/`model:`/`pin:`/`primary:`) and its final `VERDICT:` line
  are re-typed into the format the current script prints. The endpoints table, the
  request body, the HTTP response and `SERVED BY: GMICloud` are untouched, and the
  verdict is unchanged in substance: GMICloud is `gmicloud/fp8`, the primary.

## What is deliberately not here

`calls.jsonl` (the wire log), the per-cell `runs/` directories, `parent/` copies, the
probe's `calls-*.jsonl` and `fixture*.jsonl`. Together those are ~400 MB and they are
the raw material, not the evidence: a reader wanting to re-derive a number from raw
generations has to re-run the stage, and the price of doing so is on record.

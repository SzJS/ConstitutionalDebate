# findings-1 (`fd1`) — the decomposed judgment, and whether a local contest breaks fewer right decisions

Durable copy of what `outputs/` held after the two arms finished on 2026-09-02. `outputs/`
is git-ignored and dies with the pod; everything a reader needs to recompute a number is
here, and nothing here is an input to any stage.

> **Result: outcome (D) for F-weak — P1 NULL, P2 NOT SHOWN; F-strong P1 NULL.** Recourse on
> a decomposed judgment did not raise accuracy (F-weak +18 of 1,644, p = 0.46; F-strong −4,
> p = 0.48), and the local contest broke MORE right decisions than jd5-B's whole-judgment
> objection, not fewer: 38.7% against 26.8% (+11.8 points, Newcombe [6.7, 16.8]; one-sided
> Fisher p = 1). The decomposition itself made the weak judge worse (68.0% against M0's
> 73.7%, −93, p = 1.5e-6) and the strong one better (77.8%, +68, but a different model).
> The mechanism, from the hand check: the challenger contests almost only toward FLAW
> (98.5% of finding contests), the weak recourse judge ADOPTS arguable contests (5/5 breaks
> read), and under the derived rule one granted contest breaks a right SOUND verdict
> (55.5% of contested right SOUND lists broken; 1.0% of right FLAWED). The strong recourse
> judge refuses 97% of contests and recourse under it is inert.

## Why this phase exists

Every recourse arm of this experiment discriminates and still nets negative on accuracy
(`LLM_NOTES.md` §3ac). The user's hypothesis was that the challenger has to redo the
judge's whole job, and the fix under test was to make the judgment a list of numbered,
locally checkable **findings** with the verdict derived by code, so that a contest is a
finding, an omission or a contradiction rather than the verdict. `debate_variants.md`
is the specification; `PREREG.md` the pre-registration, committed at `a4dfd12` before
the first paid call of either arm.

## What ran

| | F-weak | F-strong |
|---|---|---|
| findings judge = recourse judge | `meta-llama/llama-4-maverick`, pinned `digitalocean` | `openai/gpt-5.6-luna-20260709`, pinned `openai` |
| challenger | `google/gemini-2.5-flash`, neutral + certainty clause | same |
| cells | 1,644 (jd3-main's decided debate cells, fingerprint `dfa9bdca…` before and after) | 1,644 |
| lists / objections / rulings | 1,644 / 1,076 / 1,073 (3 lost at ruling) | 1,644 / 606 / 606 |
| spend | $26.95 | $18.66 |
| wall-clock | 16:21Z → 18:25Z (relaunched 17:01Z at higher concurrency) | 18:22Z → 18:43Z |

Campaign total $48.76 including three smokes ($0.59), two pilots ($1.86), the reader
re-read ($0.16) and the injection instrument ($0.55). Write-up: `LLM_NOTES.md` §3ad.

## The layout

| path | what |
|---|---|
| `PREREG.md` | the pre-registration, committed before the run (`a4dfd12`); unedited since |
| `run-all.sh` | the two-arm driver as it ran |
| `arm-weak/`, `arm-strong/` | `index.jsonl`, `metrics.json`, `cells.jsonl`, `experiment.json`, `format-scan.jsonl` |
| `derivation.log` | `records/derivations/findings-1.py` on the two indexes; `logs/derivation-before-mopup.log` is the pre-mop-up run |
| `attempts.json` | attempts per stage and arm |
| `HANDCHECK.md` | Fable's read of 20 contested cells + 20 objections |
| `CHECKLIST.md` | every registered table, filled |
| `logs/` | driver, fingerprints, DONE, provider check, dry-runs, the three smoke reads, the pilot read, the reader re-read, the injection report, the source scan, the mop-up, the rendered prompts, the prompt digests |
| `transcripts/` | the 45 (group, arm, cell) triples the hand check read, 12 files each |

## Three smokes, two pilots, and what they changed

Smoke 1 found the challenger quoting the findings list under `Record says` and the
weak judge listing the same claim several times; smoke 2 found the challenger's
`Alice: "…" Alice: "…"` quotation shape voiding real contests; smoke 3 found an optional
record quote voiding a finding contest and a stray `Argument:` heading publishing the
challenger's private working. Each was fixed before the next paid step (R1–R12 in
`PREREG.md`), and every fix was validated offline by re-parsing the stored objections or
by re-reading stored rulings; only prompt changes were re-smoked. The pilot read
(`logs/pilot-read.md`) saw the result before the run did.

## The run's two incidents

The driver was relaunched at 17:01Z with `[client]` concurrency 32/24 on the user's
instruction; the kill did not reach the running findings-judgment stage, which ran beside
the new one for two minutes (one cell decided twice, eight run directories left
"running"). A mop-up resume pass (`logs/mopup.log`) re-attempted them and the arm's five
failed lists and eight failed contests; nothing was double-counted. The driver's DONE
table rendered empty (a formatting bug); the per-arm counts are in `logs/all-done.md`'s
stage tails and in `derivation.log` §(0).

## What this directory does not settle

Nothing about a challenger that can seek NOT A FLAW (98.5% of contests sought FLAW), a
recourse judge that does not adopt, a findings judge that does not under-call, the
"covered in substance" rule against consequences, `single`/`self_critique`, or the
same-model property (each arm's judge rules on contests to its own findings). See
`LLM_NOTES.md` §3ad "Still owed".

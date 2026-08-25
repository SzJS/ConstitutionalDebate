# Weak-model probe — decision, 2026-08-25

**Weak judge and challenger: `openai/gpt-4.1-nano`. All seven subsets survive
(six KEEP, `law` gray-and-flagged). Pilot corpus: 42 items. Sweep corpus: 2,110 items.**

Evidence: `outputs/pick-weak-2.log` (the run), `outputs/pick-weak-report-nofloor.log`
(the tables re-derived after the rule change, zero calls),
`outputs/pick-weak-2-dryrun.log` (hyperparameters), `outputs/pick-weak/settings.json`,
`nano-subsets.txt`, `tiebreak.txt`, `summary-2.txt`, `fixture-releak.log`.
Review package: `outputs/pick-weak/review/` (14 items).

This file supersedes the "no candidate survives" version of 2026-08-25 morning. Three
things changed between them, all recorded below: a pre-registered rule was withdrawn, a
leak was fixed and three fixture debates were dropped, and the escalation the rules asked
for turned out to be impossible.

---

## 1. The withdrawn rule — a post-hoc change, disclosed

`MIN_JUDGE_ACCURACY = 0.60` (judge accuracy *with* the transcript) was pre-registered,
and it disqualified **every** candidate on the corrected shortlist plus one of the first
probe's three. **The user withdrew it on 2026-08-25, after seeing that result.** The
reasoning, which is recorded verbatim in `LLM_NOTES` §1b and in the constant's own
comment in `scripts/pick_weak.py`:

> Contestability — can a weak model push back, and does it work — is measured *given* a
> wrong decision and does not depend on why the judge was wrong. The verifiable domain
> is a stand-in for non-verifiable ones where accuracy is not even defined. A
> chance-level judge changes the composition of the incorrect cell, which is the
> difficulty confound already accepted and already in the caveats. The floor was, in
> effect, filtering out the null result the experiment exists to detect.

This is a rule dropped after the numbers were seen. **The write-up must say so**, and
must report the judge accuracies, which are still measured and still printed — they are
reported, not gated. Every other disqualifier stands unchanged: format failure >5%,
native reasoning >5% despite `off`, verdict skew >85%, p95 latency >3× the fastest
survivor, challenger decline rate exactly 0% or 100%.

## 2. Who passes without the floor — verbatim from the disqualifier check

```
  google/gemma-3-12b-it              DISQUALIFIED: verdict skew 87% FLAWED
  inclusionai/ling-3.0-flash         passes
  meta-llama/llama-3.1-8b-instruct   passes
  mistralai/mistral-small-3.2-24b-instruct passes
  nvidia/nemotron-3.5-lightning      DISQUALIFIED: format failure 15%
  openai/gpt-4.1-nano                passes
  qwen/qwen3-14b                     DISQUALIFIED: native reasoning 69% despite off
  qwen/qwen3-8b                      DISQUALIFIED: format failure 32%
  qwen/qwen3.8-27b-20260814          passes
```

Five survivors across both probes. Four disqualified, each on a rule that has nothing to
do with accuracy: a judge that answers one way 87% of the time on a 46%-flawed fixture,
two models that cannot hold the output format, and one that reasons natively on 69% of
calls despite `reasoning_effort="off"` — which removes `qwen/qwen3-14b`, the model
`DESIGN.md` names as the starting point.

## 3. The choice, and where it departs from the pre-registered tiebreak

The pre-registered rule is: among survivors, take the model leaving the **most keep-zone
subsets**; tiebreak on transcript uplift, then cost per decided item, then latency.

| survivor | KEEP | gray | DROP | surviving | uplift | $/judge call | judge p95 (per-request) |
|---|---|---|---|---|---|---|---|
| `meta-llama/llama-3.1-8b-instruct` | **7** | 0 | 0 | 7 | +0.01 | 0.000237 | **27.1 s** |
| `openai/gpt-4.1-nano` | 6 | 1 | 0 | **7** | −0.01 | 0.000524 | 9.5 s |
| `mistralai/mistral-small-3.2-24b-instruct` | 3 | 2 | 2 | 5 | −0.22 | 0.000532 | 6.3 s |
| `inclusionai/ling-3.0-flash` | 1 | 3 | 3 | 4 | −0.09 | 0.000147 | 3.9 s |
| `qwen/qwen3.8-27b-20260814` | 0 | 1 | 6 | 1 | −0.16 | 0.004895 | 49.4 s |

**Read literally, the rule selects `llama-3.1-8b` (7 KEEP to nano's 6), and the user
chose `gpt-4.1-nano`. That is a second post-hoc departure and it is stated here rather
than smoothed over.** The two tie at seven *surviving* subsets — a gray subset is KEPT
and flagged — so the difference is whether `law` is counted as keep-zone or gray. The
grounds for taking nano anyway:

- **Latency.** llama's judge p95 is **27.1 s** against nano's 9.5 s, per request. At
  2,110 items × 3 conditions that tail is what decides whether a sweep fits inside
  `run_timeout_s`. llama's *median* is faster (1.2 s); it is the tail that is the risk.
- **Verdict skew, and what it does to the incorrect cell.** Eight of the nine models
  measured over-call FLAWED (63–87% against a 46% base). `gpt-4.1-nano` is the only one
  that does not — it sits at 51% SOUND. That matters more than it looks: a
  FLAWED-skewed judge's errors are overwhelmingly **false positives on sound items**,
  and on a sound item there is no annotation to grade an objection against, so those
  errors contribute nothing to the valid-objection rate. nano's errors are balanced
  (13 FN / 15 FP on the fixture), so its incorrect cell carries gradable false
  negatives — the cell the contestability metric is actually defined on.
- Solo accuracy 0.61, above chance, so the screen is measuring something.
- Challenger declines on 56% of contests, comfortably inside the 0%/100% guard, so the
  false-alarm control has range.

### Measured latency and throughput — not the table's p50/p95

The `p50`/`p95` columns in the main table are wall-clock around the whole coroutine and
include time spent queued behind the concurrency semaphore. At `max_concurrency = 8`
over 280 items that queue wait dominates: they are a fact about the probe, not the
model, and they are 3–20× the true figure. `print_report` now prints a second table
computed from each request's own `latency_ms` and `completion_tokens`. For nano:

| role | n | p50 | p95 | tok/s p50 | output tokens p50 |
|---|---|---|---|---|---|
| solo | 312 | 6.0 s | 10.8 s | 83 | 490 |
| judge | 73 | 6.6 s | 9.5 s | 81 | 556 |
| challenger | 71 | 1.4 s | 3.7 s | 70 | 97 |

This is what the repo's model-choice rule means by checking throughput and latency:
OpenRouter's API returns `null` for both on every endpoint, so it is measured on our own
prompt lengths instead.

## 4. The leak, the three dropped debates, and what became of their rows

`parse_debater_output` only checked for a `Thinking:` label at the *head* of the
extracted argument, and `_LABEL_RE` is line-anchored, so a debater that restated the
whole structure with no newline before the second label — `...does not contain a
flawThinking: <private>...Argument: <retry>` — had its **private reasoning published to
the judge and the challenger** with `parse_mode="strict"`. Fixed per the user's
decision: an inline `Thinking:` label **anywhere** in the argument is malformed, the one
repair is spent, and the turn fails if it recurs.

Re-parsing every turn's `raw` in the cached fixture with the fixed parser found **3 of
426 published arguments (0.7%), in 3 of 71 debates**, all from `deepseek-v4-flash`, all
in round 1:

| dropped debate | subset | leaked turn | published argument |
|---|---|---|---|
| `law-con5_gpt3-5_A-s8` | law | round 1, Alice | 6,397 chars |
| `law-evi4_gpt4_B-s7` | law | round 1, Bob | 4,616 chars |
| `theoremqa-solutions-math_algebra_3-png-flawed` | theoremqa | round 1, Bob | 4,128 chars |

*(An earlier count said 2. It was wrong: the first draft of the detector used
`\bThinking`, and there is no word boundary between `w` and `T` in `flawThinking`, so it
missed the one case it existed to catch. The regex now carries a second, case-sensitive
alternative for the concatenated form, and a test for both.)*

`fixture.jsonl` now holds **68** debates; the original is kept as
`fixture.with-leaks.jsonl`.

**How their probe rows were handled — in code, not by hand.** Every `rows-judge-*` and
`rows-challenger-*` row for those three items is a measurement of a judge reading text
the protocol says it never sees. They are **excluded in `pick_weak.LEAKED_FIXTURE_ITEMS`
and filtered by `drop_leaked()`**, which `print_report` and `print_flags` both apply,
printing the count when it fires (53 rows across nine models). The rows stay on disk —
deleting a paid measurement is worse than excluding it. **Solo rows are not excluded**:
the solo screen never sees a transcript, so the subset screen is unaffected. Every judge
figure in this file is therefore on n=68, not 71.

## 5. The subset screen — and why `law` could not be escalated

`law` sits at 0.78, inside the (0.70, 0.80) gray zone, and the rule says escalate it by
40 items. **It cannot be escalated.** The entire `law` subset is 40 items (20 flawed,
20 sound — CELS contract law and evidence law, 20 arguments each), and the base draw at
`--per-subset 40` already measured **all 40 of them**. The dry run prints `0 calls`:

```
  pass 1  solo screen      0 items x 1 candidates =     0 calls
            NOTE: the pool is exhausted for ['law'] — fewer items than asked for
```

Nothing was run and nothing was spent (`outputs/pick-weak-escalate-law.log`). Under the
pre-registered rule — "still gray → KEEP and flag" — `law` is **kept and flagged**, and
its accuracy can never be refined: n=40 is the whole population, not a sample of it.

### Final screen for `openai/gpt-4.1-nano`

| subset | k/n | solo acc | 95% CI | zone | corpus items |
|---|---|---|---|---|---|
| gpqa | 21/40 | 0.53 | [0.37, 0.67] | KEEP | 382 |
| law | 31/40 | 0.78 | [0.62, 0.88] | **gray → keep + flag** | 40 |
| lojban | 26/40 | 0.65 | [0.50, 0.78] | KEEP | 120 |
| medqa | 27/40 | 0.68 | [0.52, 0.80] | KEEP | 222 |
| python800 | 15/40 | 0.38 | [0.24, 0.53] | KEEP | 952 |
| surgery | 28/40 | 0.70 | [0.55, 0.82] | KEEP | 212 |
| theoremqa | 24/40 | 0.60 | [0.45, 0.74] | KEEP | 182 |

**All seven subsets survive. 2,110 items.** Failures count as not solved throughout.

Worth noting against prediction 1 in `LLM_NOTES` §5, which said the screen would drop
the maths, science and code subsets: it dropped none of them. `python800` is nano's
*worst* subset at 0.38 and `gpqa` its second worst at 0.53. The prediction was made about
a judge that could read the program or redo the algebra; nano cannot.

## 6. Judge accuracy, reported not gated

| candidate | solo (n=280) | judge (n=68) | 95% CI | uplift | decline |
|---|---|---|---|---|---|
| `openai/gpt-4.1-nano` | 0.61 | 0.59 | [0.47, 0.70] | −0.01 | 0.56 |

nano judges at 0.59 with the transcript against a 0.50 chance line. That is a weak
judge, which is what the protocol asks for, and it is the number the withdrawn floor
would have excluded the experiment on.

## 7. Everything above was measured under an UNDEFINED standard of "flaw"

Added 2026-08-25, after the decisions above were taken and before the pilot.

No prompt in this codebase defined what a flaw is. The only gloss was the circular
"FLAWED means the text under review contains a flaw", and the FindTheFlaws standard the
user asked for at design time never reached `prompts.py` — a lost instruction, recorded
as such in `LLM_NOTES` §3j. Eight of the nine models screened over-call FLAWED (63–87%
on a 46% base); `gpt-4.1-nano` is the only exception, and its balanced error profile is
one of the two reasons it was chosen in §3 above.

All five system prompts — debater, judge, solo reviewer, challenger, grader — now carry
one shared `FLAW_DEFINITION` paragraph. No base-rate hint (the user's choice).

**The user declined a re-probe.** So, exactly:

- **Every number in this file was measured under the undefined standard** and stands as
  the record of behaviour under it: both probes, the fixture, the solo screen and its
  subset zones, the model choice, the `law` non-escalation, the uplift figures, the
  FLAWED skew. Nothing here is restated or re-run.
- **The pilot is the first measurement under the definition.** The probe is not a
  prediction of it. If the pilot's verdict distribution is less FLAWED-skewed than the
  probe's, that is the definition working, not a discrepancy.
- The subset screen therefore rests on solo accuracies taken with the old prompt. nano
  may solve a subset differently once told what it is looking for. Accepted, flagged,
  and first visible in the pilot's per-subset behaviour.

## 8. Spend

| what | calls | $ |
|---|---|---|
| fixture (strong model, 71 debates, 2026-08-24) | 875 | 0.267 |
| probe 1 — first shortlist | 2,368 | 3.898 |
| probe 2 — corrected shortlist | 3,160 | 0.734 |
| law escalation | 0 | 0.000 |
| **total** | **6,403** | **4.899** |

Everything after the probe re-run — the rule change, the leak audit, the subset screen,
the tiebreak table — was derived from measurements already on disk, at zero cost, via
`scripts/pick_weak.py --report-only`.

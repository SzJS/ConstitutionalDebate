# Auditor probe — the rules, stated before the numbers exist

**Written and committed on 2026-08-27, before any candidate was called.** This file is
the pre-registration. `scripts/pick_auditor.py` refuses to send a single request if it
is missing, and `tests/test_pick_auditor.py` fails if any threshold here disagrees with
the constant the script applies. The precedent is `MIN_JUDGE_ACCURACY` in
`scripts/pick_weak.py`: a floor that was pre-registered, disqualified every candidate,
and was withdrawn by the user afterwards — which the write-up has to disclose *because*
it was written down first. A rule invented after the table is printed is not a rule.

## What is being chosen, and why

The judgment-challenge slice (`outputs/experiments/judgment-pilot`, 194 cells, $1.64)
ran `openai/gpt-4.1-nano` as the challenger under `challenger_variant = "judgment"`. It
raised 111 objections alleging 315 defects; the grader could verify 8. **34 of its 66
`Judgment says:` quotations were not in the judgment at all** — they came from a debater,
from the solution, or from nowhere. That is not a reader that fails to find defects; it
is a reader that cannot hold "which text is the judgment" straight, and no prompt fixes
it. The user's decision: find the weakest model that reliably notices contradictions,
misstatements and omissions, and run the variant with that one.

The winner becomes `challenger_model` **for the judgment variant only**. The judge, the
grader, the recourse judge and the two prose readers do not change. The neutral and
partisan arms keep gpt-4.1-nano and stand as the weak-stakeholder measurements.

`anthropic/*` is excluded from the pool: Haiku 4.5 is the grader here and the two prose
readers in the run, and a challenger graded by itself is the "challenger and judge model
variance" confound `DESIGN.md` lists.

## The instrument

60 real judgments out of `outputs/experiments/sweep` — 20 per condition, drawn seed 0
and spread across all seven subsets, from cells whose grounds are at least 200
characters. (Over the whole sweep, 9 debate judgments are a bare `Verdict:` line with no
reasoning and 3 `single` judgments are under 200 characters: 12 of 5,724 decisions have
nothing to audit. They are excluded and counted.)

Each judgment is audited five times: **unchanged** (the control) and with one of four
defects injected **by code**, with the injected span recorded:

| variant | the injection | the span the scorer looks for |
|---|---|---|
| `misquote` | one change inside a quotation the judgment makes — a number altered, else a negation flipped, else two content words swapped — where the quotation is verbatim in the **evidence** before the change and is not after | the corrupted quotation |
| `misattribution` | the parties swapped in one sentence: `Alice`↔`Bob` in a debate judgment, `the solution`↔`the problem statement` / `the critique`↔`the draft` in a solo one | the altered sentence |
| `contradiction` | one sentence appended that denies a specific earlier claim of the judgment, templated from that claim, placed before the `Verdict:` line | the appended sentence |
| `omission` | the judgment sentence with the highest lexical overlap with an **evidence** passage is deleted, where that passage is not quoted anywhere in what is left | that passage |

A judgment that cannot carry a variant — it quotes nothing the evidence contains, it
names no party — is **skipped and counted**, never resampled: which judgments can carry
which defect is a fact about the corpus.

**The solo record contains the judge's own text, several times over.** `single`
publishes `Answer:` and then the reviewer's justification — the judgment is the whole
record. `self_critique` publishes `Draft, (Critique, Revision) × 3`, and the judgment is
the **last Revision**; a revision that changed little is a near-verbatim copy of the one
before it, so counting the judgment's opening in the record gives 1 copy for 9 of the
drawn items, 2 for 6, 3 for 4 and 4 for one. Only `debate` keeps judgment and record
apart. Three rules follow for the two solo conditions, and the fixture is refused if any
of them cannot be met.

1. **Evidence is what the judge did not write.** A misquote's quotation must be verbatim
   in the evidence before the change and absent after; an omission's passage must come
   from the evidence and must not appear in the original judgment. For a solo condition
   the evidence is the problem statement, the solution under review, and — for
   `self_critique` — the **Critique** sections, which are the other voice in that record
   as the debaters are in `debate`. The draft and every revision are excluded: a
   quotation whose only source is an earlier revision is the judge quoting itself, and an
   "omission" whose record passage is a sentence the judge wrote in revision 2 is not a
   point anybody else made. For `debate` the evidence is the record body, which is
   already judgment-free, and nothing about that condition changes.
2. **The edit goes into every copy the judge wrote, and nowhere else.** A misquote, a
   misattribution and an omission are applied to the draft and to all revisions, so no
   copy keeps the original wording; a defect present in the last revision and absent
   from the one before it is not a defect of the judgment, it is a diff an auditor can
   spot without reading anything. The critiques, the problem and the solution are never
   edited — they are the sources a misquote is a misquote *of*, and editing them would
   leave the two agreeing again. A **contradiction** is the exception and goes on the
   final copy alone: an appended sentence is not recoverable from an earlier draft, so
   there is no shortcut to close. How many copies each edit reached is recorded per item
   (`copies_edited`) and printed with the fixture counts.
3. **The record shape is parsed, not assumed.** Every body must read as `Answer` or as
   `Draft` followed by one or more `Critique`/`Revision` pairs; anything else is a shape
   this probe has not been told how to read and the cell is dropped and counted.

Every audit uses the real prompt (`build_challenger_messages` under
`challenger_variant = "judgment"`), the judgment slice's `[client]` settings,
`challenger_temperature = 0.7`, one attempt plus the run's one repair, and the run's
last-resort handler for a reply that is still unreadable. Scoring is by code: an audit
**detects** the injected defect when one of its own flagged quotes shares at least **20
characters** (whitespace and case folded) with the injected span.

Which alteration a misquote received — `number`, `negation` or `swap` — is recorded per
item and detection is broken down by it in the report. That breakdown is **reported, not
a floor**: a model that catches every changed number and no swapped word is not the same
instrument as one that catches both, and the misquote row alone cannot say which it is.

Every fixture item's ground truth is committed as
`records/pick-auditor/fixture-manifest.jsonl` — one line per (cell, variant) with the
span, the deleted sentence, the alteration and `copies_edited` — so any row of the
report can be checked without the 2 MB fixture, which stays in `outputs/`.

A synthetic-defect fixture is a measurement instrument, not the experiment. exp2's
"natural errors only" rule governs *decisions*; injecting a known defect into a copy of a
real judgment to score an auditor does not touch a decision, and nothing built here ever
enters an experiment tree. The sweep is read and never written.

## The thresholds

| metric | floor | scored by |
|---|---|---|
| detection: `misquote` | ≥ **85%** | the injected span overlaps a flagged `Judgment says:` quote — code |
| detection: `misattribution` | ≥ **85%** | as above — code |
| detection: `contradiction` | ≥ **85%** | as above — code |
| detection: `omission` | ≥ **50%** | a flagged `Record says:` quote overlaps the deleted point — code |
| detection, pooled | ≥ **2×** the floor model's pooled detection on the same fixture | code |
| misattributed quotes | ≤ **5%** of checkable `Judgment says:` quotes not verbatim in the judgment | code (`prompts.defect_quote_in_judgment`, the same check the harness now runs on every objection) |
| false alarms on controls | ≤ **15%** of controls carrying an alleged defect that fails the quote check **or** that the Haiku judgment grader rejects against the record | code + the run's own judgment grader |
| tie-break | cheapest by $/task, then p95 latency, both measured in this run | `cost_of`, per-request `latency_ms` |

Why these numbers. **85%** on the three defect types the prompt actually asks about:
they are injected in the plainest form the format allows, and a reader that misses one
in six of those cannot be trusted with the subtle ones that occur naturally. **50%** on
omission because it is the hardest and the least well posed — the deleted sentence is
one of several points a judgment might have addressed, and an auditor that names a
different real omission scores nothing here while having done nothing wrong. **5%** on
misattributed quotes because nano's rate was 52% and that is the diagnosis this whole
probe exists to act on. **15%** on false alarms because a control is a *real* judgment:
some of them contain real defects, so the bar bounds invention rather than demanding
silence.

Wilson 95% intervals are printed beside every rate. n = 60 judgments, so each detection
rate has n ≤ 60 — less where a variant could not be injected, which the report states.

## The decision rule

**The cheapest candidate, by measured $/task, that clears every floor.** Ties broken by
p95 per-request latency.

**If no candidate clears every floor, no model is picked.** The probe is then reported as
the finding — the weakest reliable auditor is above rung 2 — and the judgment-variant
run does not happen. There is no fallback to "the best of a bad set".

`openai/gpt-4.1-nano` is measured on the same fixture and reported first. It is the
**floor**: it sets the pooled bar and it is **not eligible** to be picked. It is the model
whose failure caused this probe.

## The candidates

Ids, prices, throughput and latency confirmed on 2026-08-27 against
`https://openrouter.ai/api/v1/models` and the model pages (the API returns null for
throughput and latency; those two are rendered client-side on the pages).

| candidate | rung | $/Mtok in | $/Mtok out | throughput | latency (TTFT) | liveness |
|---|---|---|---|---|---|---|
| `openai/gpt-4.1-nano` | **the floor — not eligible** | 0.10 | 0.40 | 46 tok/s | 0.61 s | live |
| `qwen/qwen3-32b` | 1 | 0.08 | 0.28 | 52 tok/s | 0.25 s | live |
| `google/gemini-2.5-flash` | 1 | 0.30 | 2.50 | 89 tok/s | 0.50 s | live |
| `openai/gpt-4.1-mini` | 1 | 0.40 | 1.60 | 47 tok/s | 0.69 s | live |
| `openai/gpt-4.1` | 2 | 2.00 | 8.00 | 78 tok/s | 0.72 s | live |
| `openai/gpt-5.6-luna` | 2 | 0.20 | 1.20 | — | — | live |

None is far slower than the rest. A candidate that fails its `liveness` call is out
before any measurement and is recorded as such.

**Two candidates named in the plan are out, both on the same wall.**
`google/gemini-3.7-flash` (the newest Flash) and `google/gemini-2.5-pro` (the current
Pro) answer the liveness call with `HTTP 400: Reasoning is mandatory for this endpoint
and cannot be disabled`. The run sets `reasoning_effort = "off"` so that the
challenger's private channel is the published `Thinking:` block rather than a provider
channel no reader can inspect; a model that cannot turn it off cannot be this
experiment's challenger. The Flash slot therefore goes to `google/gemini-2.5-flash`, the
newest Flash that runs with reasoning off and returns none. **The rung-2 Pro slot has no
occupant**: every Pro-class Gemini on OpenRouter refuses the same way, and so does
`x-ai/grok-4.6`. Measured live with reasoning off on the same day, and available if the
user wants that rung filled: `deepseek/deepseek-v4-pro-0813` ($1.12/$3.37),
`moonshotai/kimi-k2.6` ($0.95/$4.00), `openai/gpt-5.6-luna` ($0.20/$1.20).
`deepseek/deepseek-v4-flash-0731` is deliberately not among them — it wrote the sweep's
debates, and a challenger auditing a record it generated is a confound of its own.

**Added at the user's go on 2026-08-27, before any candidate was called:** `openai/gpt-5.6-luna` fills the second rung-2 slot, so that a ladder failing at `openai/gpt-4.1` still says something about the tier above it. Its throughput and latency were not read off the model page; its liveness call passed.

With no Pro in the pool, a "no model picked" outcome means *the weakest reliable auditor
is above `openai/gpt-4.1`*, which is what rung 2 stands for here.

## Instrument corrections after the run — 2026-08-27, 2026-08-28

The probe ran on 2026-08-27 (`outputs/pick-auditor.log`, $4.15, 1,500 audits, no
candidate clearing every floor). Reading the raw replies turned up **two bugs in the
instrument**. Both are recorded here because this file is the pre-registration and a
correction made after the numbers exist has to be visible beside them.

**Neither bug touches the detection scorer, and no threshold in this file changed.** The
detection failures are real: `openai/gpt-4.1` answers "I find no defects" to a judgment
that quotes the record's `-2-one` as `-3-one`.

**1. The quote check stripped only the outer quotation marks.** `prompts.normalise_quote`
removed the outer pair and nothing else, so a challenger quoting a judgment that itself
quotes something — `Judgment says: "The sentence states: 'X'"` — had the judgment's own
double quotes nested as single ones and an *accurate* quotation was recorded as a
fabrication (difflib ratio 0.97–0.99 against the judgment sentence it was quoting). Every
quotation mark and markdown emphasis character (`"` `'` `“` `”` `‘` `’` `«` `»`
`` ` `` `*` `_`) now comes off **both** sides after whitespace collapse; the parenthetical
rule and the 80-character rule are unchanged. The check is a pure function of two texts
that are both on disk, so every defect ever alleged was re-decided without a single call:

| model | misattributed quotes, as run | re-checked |
|---|---|---|
| `google/gemini-2.5-flash` | 30/155 (0.19) | **8/154 (0.05)** |
| `openai/gpt-4.1` | 20/66 (0.30) | **0/66 (0.00)** |
| `openai/gpt-4.1-mini` | 28/77 (0.36) | **10/77 (0.13)** |
| `openai/gpt-4.1-nano` | 31/50 (0.62) | **21/50 (0.42)** |
| `openai/gpt-5.6-luna` | 10/95 (0.11) | **8/95 (0.08)** |
| `qwen/qwen3-32b` | 150/295 (0.51) | **65/295 (0.22)** |

This is the harness check every future judgment run uses — `grading._grade_judgment`
skips a defect that fails it — so the fix matters well beyond this probe.

**2. The decision line was not recognised in bold.** `_VERDICT_LINE` did not match
`**Verdict: SOUND**`, so `strip_verdict_line` found no line to lift off and, on **17 of
the 59** contradiction items, the appended sentence was placed after the decision line
instead of before it — where a reader of the judgment has stopped looking. The regex now
accepts optional markdown emphasis and the fixture was rebuilt. Exactly **19** variants
changed and were re-audited for all six candidates (plus one misquote the quote-mark fix
newly made injectable): the 17 contradictions, and 2 misquotes whose first
verbatim-in-the-evidence quotation changed under the corrected check. Contradiction
detection on those 17 items, before and after, with the other 42 unchanged for reference:

| model | those 17, before | after | the other 42 |
|---|---|---|---|
| `google/gemini-2.5-flash` | 14/17 | 16/17 | 36/42 |
| `openai/gpt-4.1` | 10/17 | 15/17 | 30/42 |
| `openai/gpt-4.1-mini` | 13/17 | 13/17 | 35/42 |
| `openai/gpt-4.1-nano` | 1/17 | 3/17 | 1/42 |
| `openai/gpt-5.6-luna` | 5/17 | 10/17 | 23/42 |
| `qwen/qwen3-32b` | 12/17 | 11/17 | 37/42 |

**What was re-bought, and what was not.** Every audit row carries the sha256 of the
judgment it was audited against, so the correction re-bought exactly the 20 items per
candidate whose text moved — 120 audits, $0.31 — and kept the other 231 as measured. The
rows they replace are in `rows-audit-<model>.superseded.jsonl`; the fixture as it was is
`outputs/pick-auditor/fixture.before-bold-fix.jsonl`. 15 controls whose surviving-defect
set changed under the corrected check were graded again by the same Haiku call ($0.12);
the rest reuse the ruling already paid for. Re-scored tables:
`outputs/pick-auditor-rescored.log`, and appended to `outputs/pick-auditor.log` beneath
the original.

**What corrections 1 and 2 changed in the verdict: nothing.**
`google/gemini-2.5-flash` gained the contradiction floor (0.88) and `openai/gpt-4.1` the
misattributed-quote floor (0.00), but every candidate still failed at least three floors
and no model was picked.

**3. An ellipsis-stitched quotation failed the check (found 2026-08-28).**
`quote_in_text` compared the first 80 characters of a quotation as one string, so a quote
whose middle had been elided — `"Given all this, the analysis does not contain a
flaw...nor does it make false claims about Python's remove() behavior"` — matched nothing,
even though each of its pieces is verbatim in the judgment. Only a *trailing* ellipsis
survived, and only by accident: the tail falls past the 80-character cut. Three of
`gemini-2.5-flash`'s six `debate` control false alarms were exactly this shape, and each
was recorded as a fabricated quotation and counted as a false alarm **with no grader call
at all**. Eliding the middle of a sentence is ordinary quotation, not misattribution. The
check now splits the normalised quote on `...` / `…`, drops pieces shorter than 15
characters, and requires **every** remaining piece to be in the source — so a stitched
quote with one invented half still fails, and a quote with no substantial piece is read
whole as before.

| model | misattributed quotes | | control false alarms | |
|---|---|---|---|---|
| | before | after | before | after |
| `google/gemini-2.5-flash` | 8/154 (0.05) | **3/154 (0.02)** | 11/60 (0.18) | **8/60 (0.13)** |
| `openai/gpt-4.1` | 0/66 (0.00) | 0/66 (0.00) | 2/60 (0.03) | 2/60 (0.03) |
| `openai/gpt-4.1-mini` | 10/77 (0.13) | **5/77 (0.06)** | 6/60 (0.10) | 6/60 (0.10) |
| `openai/gpt-4.1-nano` | 21/50 (0.42) | **16/50 (0.32)** | 7/60 (0.12) | 7/60 (0.12) |
| `openai/gpt-5.6-luna` | 8/95 (0.08) | 8/95 (0.08) | 4/60 (0.07) | 4/60 (0.07) |
| `qwen/qwen3-32b` | 65/295 (0.22) | **56/295 (0.19)** | 39/60 (0.65) | 39/60 (0.65) |

**Nothing was re-audited.** The fixture is byte-identical — checked, not assumed: all 38
misquote items' ground truth still holds under the corrected check and none would be
re-sited on a rebuild — so every stored objection was re-checked from it for free, and
only the **8 controls whose surviving-defect set changed** were graded again ($0.0520).
Note for a future rebuild: `inject_misquote` and `inject_omission` use this same function
to certify ground truth, so a rebuild after this change is not guaranteed to reproduce the
present fixture even though today it would.

**Floor verdicts that moved.** `google/gemini-2.5-flash` now clears the misattributed-quote
floor (0.02, from 0.05 — which had failed by three thousandths) and the false-alarm floor
(0.13, from 0.18), leaving it failing only the three detection floors it already failed.
`openai/gpt-4.1-mini` still fails misattributed at 0.06. **The decision is re-derived from
the re-scored table and is unchanged: no candidate clears every floor, so no model is
picked.** Tables: `outputs/pick-auditor-rescored.log`, a third section in
`outputs/pick-auditor.log`, and `outputs/pick-auditor-by-condition.log`.

## What this file does not decide

Nothing. The probe prints a table and a decision line; the choice, the evidence and any
departure from the rules above go into `records/pick-auditor/DECISION.md` by hand, and a
rule dropped or changed after the numbers exist must be recorded there and in the
write-up as exactly that.

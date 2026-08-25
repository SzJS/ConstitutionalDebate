# Pilot-2 go/no-go checklist — 2026-08-25

Spec: `experiments/pilot-2.toml` · corpus `data/cases/pilot.jsonl` (42 items, 7 subsets,
21 flawed / 21 sound) · 126 cells (3 conditions × 42 × 1 repeat).
Debaters/solo/critic `deepseek/deepseek-v4-flash-0731`; judge, recourse judge,
challenger and comprehension probe `openai/gpt-4.1-nano`.
`max_tokens = 16384` (decision-line roles) · `generation_max_tokens = 8192`
(record-producing roles) · `challenger_temperature = 0.7` ·
`max_runs_in_flight = 8` / `max_concurrency = 16`.

**No pilot-1 ↔ pilot-2 comparison is valid.** The challenger's instruction, the round
instructions, the solo prompts (the user's critique merge), the corpus text and the
token caps all differ. Where pilot-1 numbers appear below they are context for a
*mechanism*, never a measurement to compare against.

Logs: `outputs/pilot-2-dryrun.log`, `outputs/pilot-2-decide.log`,
`outputs/pilot-2-contest.log`, `outputs/pilot-2-grade.log`,
`outputs/pilot-2-analyse.log`, `outputs/pilot-2-checklist-numbers.log`,
`outputs/pilot-2-metrics-table.log`, `outputs/pilot-2-extra-numbers.log`,
`outputs/pilot-2-ops.log`, `outputs/pilot-2-handread.log`,
`outputs/get-tasks-pilot-2.log`, `outputs/e2e-offline-3.log`.

| # | check | threshold for pilot-2 | measured | verdict |
|---|---|---|---|---|
| 1 | parse | 100% of cells parse; every **no-label** truncation recovered by the budget route; label-present truncations reported by shape | **108 / 126 = 85.7%** decided. 9 truncated calls: **7 reached no public label** → 5 recovered by the budget route, 2 not; **2 reached the label** and were fatal by design | **FAIL** |
| 2 | repair | format repairs <10% of decision calls; budget repairs reported separately; malformed-after-repair ≤1 cell | format repairs **143 / 727 = 19.7%**; budget repairs **7 / 727 = 1.0%**; malformed-after-repair on **15 cells** | **FAIL** |
| 3 | verdicts | neither class >85% of any condition's verdicts | single 54% FLAWED · self_critique 62% · debate 54%. Max share **62%** | **PASS** |
| 4 | stances | at least one `contests`, one `declined`; `agrees` and `unclear` counts reported; objections given FN vs FP | **contests 58, declined 49, agrees 1, unclear 0** over 108 contests. Contests given false negative **5/7**, given false positive **12/17** | **PASS** |
| 5 | containment | zero `Thinking:` in challenger-visible records (both leak shapes); native reasoning reported per provider | **0 hits in 130** challenger/recourse-judge user messages and **0 of 108** `challenge.md`. Native reasoning on **172 / 1015 calls (16.9%)**, all `deepseek`, 1–7 tokens | **PASS on containment; REPORT on native reasoning** |
| 6 | grader | every grade hand-checked; agreement per boolean; if zero rows, say so and why | **0 grades produced — and not for the pre-registered reason.** 5 contests were eligible; every grader call failed **HTTP 404: `anthropic/claude-haiku-4.5:batch` is Batch-API-only** | **FAIL (infrastructure)** |
| 7 | record balance | `decision_record_words` per condition; report | median words: single **111**, self_critique **1621**, debate **1733**. debate:single = **15.6 : 1** | **REPORT** |
| 8 | ops | wall-clock at 8/16 vs `run_timeout_s`; realised $/cell; sweep projection | decide **42.4 min**, contest **3.8 min**. Longest completed run **537 s** of 1800 (30%); longest attempted 736 s (41%). **$0.3899** total, **$0.00361 / decided cell**. Sweep ≈ **39 h**, **$19.6** (**$25.5** at 1.3×) | **PASS** |
| 9 | hand-read | four `transcript.md` paths — three genuine contests, one per condition, plus one `declined` on a wrong decision | four supplied below, each with its `transcript_full.md` | **PENDING — user** |

---

## Row 1 — what truncated, and what the budget route did with it

Nine calls hit `finish_reason="length"`, every one of them at `generation_max_tokens =
8192` and every one a record-producing role. Classified by whether the reply had reached
its public label on a line of its own — the test the budget route makes:

| cell | role / purpose | provider | chars | reached public label | outcome |
|---|---|---|---|---|---|
| `gpqa-93-sound__single__r1` | solo / answer | Relace | 28,170 | no | **budget repair → parsed** |
| `law-con2_gpt4_A-s13__self_critique__r1` | solo / draft | OpenInference | 34,911 | no | **budget repair → parsed** |
| `law-evi5_gpt4_A-s5__self_critique__r1` | critic / critique | Alibaba | 40,305 | no | **budget repair → parsed** |
| `python800-p03240-sound__debate__r1` | debater / turn | Baidu | 32,033 | no | **budget repair → parsed** |
| `python800-p03372-flawed__debate__r1` | debater / turn | Relace | 29,225 | no | **budget repair → parsed** |
| `python800-p03945-flawed__debate__r1` | debater / turn | DigitalOcean | 34,362 | no | budget repair returned an unlabelled reply → cell failed |
| `python800-p03372-flawed__debate__r1` | debater / turn (r2) | DigitalOcean | 29,911 | no | budget repair also truncated → cell failed |
| `python800-p03372-flawed__debate__r1` | debater / repair | DigitalOcean | 30,727 | **yes** | (the repair above) |
| `lojban-stim157_gpt3-5_B-s3__debate__r1` | debater / turn | GMICloud | 32,761 | **yes** | **fatal by design** — public text may have been cut |

So the route fired on **7** truncations and recovered **5**. The two label-present cases
are the ones the rule refuses to touch, which is what it is for.

Five recoveries are visible in the record as `parse_mode`, which is the carrier a report
counts: `salvaged_no_thinking_after_budget_repair` ×3, `strict_after_budget_repair` ×2.

Truncations per provider: DigitalOcean 3, Relace 2, OpenInference 1, Alibaba 1,
GMICloud 1, Baidu 1. The model id was served by 12+ providers across the run; provider
remains an uncontrolled variable in every number here.

## Row 2 — the failure that got worse, and the one that got better

18 cells died. By reason:

- **15 malformed after their one repair.** 12 of these are the same shape: `deepseek`
  writes `Thinking:` and then runs the private block straight into the public answer
  **with no `Argument:`/`Reasoning:` label**. 3 are the mirror: an `Argument:` section
  that contains a second `Thinking:` label. The parser refuses both by design (the
  private/public boundary is unknown) and was not loosened.
- **3 truncation-related** — one solo truncated again after a format repair, one debater
  truncated at a label it had reached, one debater truncated again after a budget repair.

**10 of the 15 malformed cells are solo (`single` / `self_critique`), 8 of them
`self_critique`.** That is the condition whose prompts changed most since pilot 1 — the
user's critique merge rewrote `SOLO_SYSTEM` and `SOLO_CRITIQUE_INSTRUCTION` — and
nothing in *this* plan touched the solo prompts at all. The bounded-deliberation
sentence added here is in the **debate** round instructions only, and the debate
condition contributes 5 of the 15. That points at the solo prompt rather than at this
plan's changes, but it is an inference from where the failures sit, not a controlled
result, and it should be checked before the sweep: **the "no public label" shape is now
the single largest source of lost cells.**

Truncation, by contrast, cost **3** cells here against 11 in pilot 1's first pass at the
same cap. That is the budget route and the bounded-deliberation sentence doing what they
were added to do.

## Row 4 — the contest is no longer one-directional

Pooled over 108 contests, stance by the verdict being contested:

| verdict | contests | agrees | declined |
|---|---|---|---|
| FLAWED (61) | 46 | 1 | 14 |
| SOUND (47) | **12** | 0 | 35 |

Pilot 1 objected to **0 of 55** SOUND verdicts. The SOUND route is open.

Per condition:

| | single | self_critique | debate |
|---|---|---|---|
| decided cells | 41 | 32 | 35 |
| contests | 18 | 18 | 22 |
| agrees | 0 | 0 | 1 |
| declined | 23 | 14 | 12 |
| unclear | 0 | 0 | 0 |
| contests given false negative | 0/1 | 2/2 | 3/4 |
| contests given false positive | 2/3 | 5/7 | 5/7 |

**`agrees` collapsed to 1 and `unclear` to 0.** The stance machinery was built expecting
`agrees` to be the modal outcome (it was, under the old instruction, at roughly 46 of
51); with the question asked about the verdict it is a rounding error. `unclear` never
fired: every one of the 108 replies carried a parsable claimed verdict.

**Every challenger reply parsed as `salvaged_no_labels`** — 108 of 108, no
`Thinking:`/`Argument:` wrapper anywhere, exactly the shape the reworded instruction was
written for.

**12 declines named the contrary verdict** (`contradictory = true`): "Objection: NONE"
followed by "Verdict should be: SOUND" against a FLAWED decision. Scored as declines, as
designed. It is the clearest sign that the two lines are being answered somewhat
independently of each other, and it is worth a look before the sweep.

The claimed verdict itself is heavily skewed: **93 of 108 replies claim SOUND**
(47 declines + 46 contests), 15 claim FLAWED.

## Row 5 — containment, in detail

- Challenger and recourse-judge `user` messages (system prompts excluded, since they
  describe the `Thinking:`/`Argument:` protocol and legitimately name it): **0 hits in
  130**, under the widened `[A-Za-z]` lookbehind that catches both leak shapes. Pilot 1
  had 1 in 120, on the solo path, and that shape is what the widening was for.
- `challenge.md`: **0 of 108**.
- Native reasoning: `reasoning_tokens` nonzero on **172 of 1015 calls (16.9%)**, min 1,
  median 3, max 7. Every one on `deepseek/deepseek-v4-flash-0731`: Relace 119, Baidu 48,
  GMICloud 4, Parasail 1. The payloads are prompt-tail fragments — `'WED'`,
  `' verdict.'`, `' contains a flaw.'` — not hidden deliberation. This is a provider
  property that `reasoning_effort = "off"` does not reach, it is **not** fixed by
  anything in this plan, and it is stated as a count rather than called a pass. It is
  concentrated enough by provider (Relace and Baidu are 97% of it) that **provider
  pinning would remove most of it**, which is the sweep decision this row exists to
  inform.

## Row 6 — the grading cell is NOT empty, and the grader could not be called

Pre-registered expectation (i) said Step A alone was *not* predicted to fill the grading
cell. **It is falsified.** Grading needs a flawed item, a wrong decision, a contesting
objection and an annotation; there are **4** such rows by the index's definition and the
grade stage found **5** eligible contests:

```
law-evi5_gpt4_A-s5__self_critique__r1
medqa-train_2855__self_critique__r1
medqa-train_2855__debate__r1
theoremqa-solutions-kite2-png-flawed__debate__r1
gpqa-161-flawed__debate__r1
```

All five failed identically:

> `FatalError: HTTP 404 from OpenRouter (model='anthropic/claude-haiku-4.5:batch'):
> This model is only available through the Batch API. Use the /api/beta/batches endpoint
> instead.`

`GradingConfig.grader_model` has carried the `:batch` suffix since the harness was
written, and **no run has ever exercised it**: pilot 1 graded zero objections because
its contest was one-directional, so the id was never sent. The pilot has now done what a
pilot is for. This is a model-id decision and was not changed here; the stage resumes on
`grade.json`, so once the id is settled these five cost five calls and nothing else is
re-spent.

## Row 7 — record balance

| | single | self_critique | debate |
|---|---|---|---|
| median `decision_record_words` | 111 | 1621 | 1733 |
| min / max | 26 / 376 | 611 / 3260 | 1392 / 2375 |

debate : single = **15.6 : 1**. The three conditions make the same number of
generations; they do not produce the same amount of record, and the challenger reads the
record. Goes in the write-up as a limitation, as in pilot 1.

## Row 8 — ops

| stage | wall-clock | outcome | spend |
|---|---|---|---|
| decide | 18:48:49 → 19:31:11 (**42.4 min**) | 108 completed, 18 failed | $0.2837 |
| contest | 19:32:08 → 19:35:57 (**3.8 min**) | 108 completed, 18 skipped | $0.1062 |
| grade | seconds | 0 graded, 5 failed (404), 121 skipped | $0.0000 |
| analyse | seconds | 108 rows indexed | $0.0000 |
| | | | **$0.3899** |

727 decision-path calls + 288 contest calls = 1015.

- **$0.00361 per decided cell**, $0.00310 per attempted cell.
- **Sweep projection** at 2110 items × 3 conditions = 6330 cells: **≈ $19.6**, or
  **≈ $25.5** with 1.3× headroom.
- **Wall-clock ≈ 39 h** at `max_runs_in_flight = 8` / `max_concurrency = 16` (decide
  20.2 s/cell → 35.5 h; contest 2.1 s/cell → 3.7 h). Pilot 1 projected 82–110 h at 4/8.
- **`run_timeout_s` headroom improved.** Longest *completed* decision run **537 s**
  (30% of the 1800 s cap); longest attempted, including the failures, **736 s** (41%).
  Pilot 1's longest was 1306 s (73%) — the difference is `generation_max_tokens`, which
  bounds the runaway that was eating the clock. Raising concurrency by 2× did **not**
  eat the margin; it improved it.

## Row 9 — the four transcripts for the hand-read

Three genuine `contests`, one per condition, and one `declined` on a wrong decision.
Each `transcript.md` is the readable document; the `transcript_full.md` beside it is the
verbatim wire record. **The reader now sees the gold label at the bottom of the readable
document**, so read the record before the `## Ground truth` section.

**1. debate — a false negative, contested, and corrected.** Gold FLAWED, the debate
judge said SOUND, the challenger said the verdict should be FLAWED, and the recourse
judge overturned. `final_correct = true`. Comprehension 4/5.

```
outputs/experiments/pilot-2/cells/gpqa-161-flawed__debate__r1/contests/openai-gpt-4.1-nano/runs/20260825T193208Z-gpqa-161-flawed-recourse/transcript.md
outputs/experiments/pilot-2/cells/gpqa-161-flawed__debate__r1/contests/openai-gpt-4.1-nano/runs/20260825T193208Z-gpqa-161-flawed-recourse/transcript_full.md
```

**2. self_critique — the same shape, not corrected.** Gold FLAWED, verdict SOUND,
challenger said FLAWED, the re-decider kept its answer. Comprehension 3/5.

```
outputs/experiments/pilot-2/cells/law-evi5_gpt4_A-s5__self_critique__r1/contests/openai-gpt-4.1-nano/runs/20260825T193227Z-law-evi5_gpt4_A-s5-recourse/transcript.md
outputs/experiments/pilot-2/cells/law-evi5_gpt4_A-s5__self_critique__r1/contests/openai-gpt-4.1-nano/runs/20260825T193227Z-law-evi5_gpt4_A-s5-recourse/transcript_full.md
```

**3. single — a false positive, contested, not corrected.** Gold SOUND, verdict FLAWED,
challenger said SOUND. This is `theoremqa-solutions-angular_momentum-txt-sound`, the
item whose stored `\n` / `π` escapes were fixed in `datasets._clean` — its text now
reads as newlines and π. Comprehension 4/5.

```
outputs/experiments/pilot-2/cells/theoremqa-solutions-angular_momentum-txt-sound__single__r1/contests/openai-gpt-4.1-nano/runs/20260825T193503Z-theoremqa-solutions-angular_momentum-txt-sound-recourse/transcript.md
outputs/experiments/pilot-2/cells/theoremqa-solutions-angular_momentum-txt-sound__single__r1/contests/openai-gpt-4.1-nano/runs/20260825T193503Z-theoremqa-solutions-angular_momentum-txt-sound-recourse/transcript_full.md
```

**4. a decline on a wrong decision.** Gold FLAWED, `single` said SOUND, and the
stakeholder declined to object — a detection failure, recorded as one. Comprehension
5/5, the highest score, on a record it read confidently and wrongly. What it wrote:

> "The reviewer's reasoning correctly states that the sentence under review accurately
> reflects the typical postoperative course of laparoscopic cholecystectomy, including
> potential longer recovery and discomfort, and that the use of 'may' appropriately
> indicates these are possible outcomes."

```
outputs/experiments/pilot-2/cells/surgery-sur40_gpt3-5_A-s7__single__r1/contests/openai-gpt-4.1-nano/runs/20260825T193427Z-surgery-sur40_gpt3-5_A-s7-recourse/transcript.md
outputs/experiments/pilot-2/cells/surgery-sur40_gpt3-5_A-s7__single__r1/contests/openai-gpt-4.1-nano/runs/20260825T193427Z-surgery-sur40_gpt3-5_A-s7-recourse/transcript_full.md
```

---

## The funnel

| | single | self_critique | debate |
|---|---|---|---|
| decided cells | 41 | 32 | 35 |
| gold flawed | 20 | 15 | 16 |
| FLAWED verdicts | 54% | 62% | 54% |
| accuracy before the contest | 37/41 | 23/32 | 24/35 |
| false negatives | 1 | 2 | 4 |
| false positives | 3 | 7 | 7 |
| decline rate | 23/41 (0.56) | 14/32 (0.44) | 12/35 (0.34) |
| objection (contests) given incorrect | 2/4 (0.50) | 7/9 (0.78) | 8/11 (0.73) |
| false alarm given correct | 16/37 (0.43) | 11/23 (0.48) | 14/24 (0.58) |
| … on a correct FLAWED verdict (flawed item) | 15/19 | 11/13 | 8/12 |
| … on a correct SOUND verdict (sound item) | 1/18 | 0/10 | 6/12 |
| **revised given incorrect** | **0/4** | **3/9** | **4/11** |
| **revised given correct** | **0/37** | **1/23** | **8/24** |
| revised given false negative | 0/1 | 0/2 | **3/4** |
| revised given false positive | 0/3 | 3/7 | 1/7 |
| valid objection | 0/0 (eligible 1) | 0/0 (eligible 2) | 0/0 (eligible 3) |
| accuracy after the contest | 37/41 | **25/32** | **20/35** |
| comprehension (mean of 5) | 4.44 | 4.22 | 3.91 |

Pooled: `revised_given_incorrect` **7/24**, `revised_given_correct` **9/84**. The
contest moves wrong decisions about 2.7× more often than right ones — but in `debate`
it moved 8 right decisions as well as 4 wrong ones, and that condition's accuracy fell
24/35 → 20/35 while `self_critique` rose 23/32 → 25/32.

The `false_alarm_given_correct` split by gold label is the row to read carefully.
Objecting to a **correct FLAWED verdict on a flawed item** — denying a real flaw — runs
at 34/44 pooled (77%). Objecting to a **correct SOUND verdict on a sound item** —
inventing a flaw — runs at 7/40 (18%), and 6 of those 7 are in `debate`, where the
challenger has a transcript full of ready-made allegations to borrow. That asymmetry is
what the split was added to make visible, and it is the thing to watch if the challenger
prompt is touched again.

## Pre-registered expectations, scored

Written into `LLM_NOTES.md` §3l at 18:46 UTC, before `decide` was launched at 18:48:49.

| # | expectation | outcome |
|---|---|---|
| i | Step A alone is *not* predicted to fill the grading cell | **falsified** — 5 eligible contests; the cell is non-empty and the grader could not be called for an unrelated reason |
| ii | `revised_given_correct` expected to fall, possibly to 0 | **falsified** — 9/84, up from pilot 1's 3/91, and 8 of the 9 are in `debate` |
| iii | `false_alarm_given_correct` expected to move; report split by gold label | **held** — 41/84 pooled, and the split shows it concentrated on correct FLAWED verdicts (34/44) rather than on sound items (7/40) |
| iv | rows 1 and 5 cannot pass as previously worded | **held** — restated, and row 5's containment half passes while its native-reasoning half is reported |
| v | no pilot-1 ↔ pilot-2 comparison is valid | **held**, and observed throughout |

## Stop / redesign triggers

**Fired:** rows 1, 2 and 6 failed. Under the pre-registered rule — *"any checklist
threshold failed → fix and re-run the pilot; do not carry a known failure into the
sweep"* — the sweep does not start from here.

**Not fired:** row 3 (verdicts non-degenerate) passes comfortably; no cell died for a
reason outside this plan's vocabulary (every failure is a truncation or a
malformed-after-repair, both anticipated); and the pilot-1 trigger about the challenger
declining on every debate false positive is now moot — it declines on 2 of 7.

**Deferred, with numbers, as the plan directs:** provider pinning. Truncation and native
reasoning are both concentrated by provider (Relace and Baidu carry 97% of the native
reasoning; DigitalOcean and Relace carry 5 of 9 truncations), and the model was served
by 12+ providers in 1015 calls. The sweep decision now has counts to work from.

**The three things to settle before the sweep**, in the order they cost cells:

1. The "no public label" reply shape — 12 lost cells, 10 of them solo. It is a prompt
   question, not a parser question; the parser must not be loosened.
2. `grader_model`. Five graded rows are waiting on a model id.
3. Provider pinning, on the numbers above.

---
---

# Second block — 2026-08-25, after the grader fix and the shape-aware repair

**Do not read this block as a re-run of the pilot.** Nothing was re-decided except the
**18 cells that had failed**; the 108 that succeeded were skipped by resume and carry
their original decisions. The retried set is therefore **selected for being the hardest
cells for the format**, and every recovery number below is a **floor**, not an estimate.
The first block above stands unedited as the record of the run as it was.

What changed between the two blocks (LLM_NOTES §3m, and §7's Step-A note):

1. `GradingConfig.grader_model`: `anthropic/claude-haiku-4.5:batch` →
   `anthropic/claude-haiku-4.5`. The `:batch` suffix routes to OpenRouter's Batch API,
   which `client.py` does not speak; it returned HTTP 404 on all five of the first
   block's grader calls. Same model, ordinary chat-completions endpoint.
2. **The one repair attempt is now aimed by the shape of the failure.** A malformed
   reply carries a `kind`; a reply that filed everything under `Thinking:` is told that
   none of it can be published and asked for **only** the public section, and a reply
   whose label was merely glued to the end of a sentence is told where the label goes.
   A public-only reply already parses (`salvaged_no_thinking`). No parser rule was
   loosened, no second repair was added, no model, cap or provider changed.

Commands, each `nohup`, each waited on its own PID, never concurrently:

```bash
nohup uv run exp2-experiment --spec experiments/pilot-2.toml --stage grade \
    > outputs/pilot-2-grade-2.log 2>&1 &      # 20:15  the 5 waiting rows
nohup uv run exp2-experiment --spec experiments/pilot-2.toml --stage analyse \
    > outputs/pilot-2-analyse-2.log 2>&1 &
# --- the shape-aware repair landed here (284 tests) ---
nohup uv run exp2-experiment --spec experiments/pilot-2.toml --stage decide \
    > outputs/pilot-2-decide-3.log 2>&1 &     # 20:26:39-20:36:37  16 recovered, 2 failed
nohup uv run exp2-experiment --spec experiments/pilot-2.toml --stage contest \
    > outputs/pilot-2-contest-2.log 2>&1 &    # 20:36:53-20:37:26  16 completed
nohup uv run exp2-experiment --spec experiments/pilot-2.toml --stage grade \
    > outputs/pilot-2-grade-3.log 2>&1 &      # 1 new eligible contest
nohup uv run exp2-experiment --spec experiments/pilot-2.toml --stage analyse \
    > outputs/pilot-2-analyse-3.log 2>&1 &    # 124 rows indexed
```

Numbers below re-derived by `outputs/pilot-2-numbers-2.py` →
`outputs/pilot-2-checklist-numbers-2.log`; the shape table by
`outputs/pilot-2-shapes.py` → `outputs/pilot-2-shape-table.log`; the per-cell retry
outcomes in `outputs/pilot-2-retry-outcomes.log`.

| # | check | threshold | measured (both passes together) | verdict |
|---|---|---|---|---|
| 1 | parse | 100% of cells parse; every no-label truncation recovered by the budget route; label-present truncations reported by shape | **124 / 126 = 98.4%** decided, up from 108. 13 truncated calls in all: **10 reached no public label** → 6 recovered by the budget route, 4 not; **3 reached the label**, where truncation stays fatal. Both surviving failures are truncations | **FAIL (2 cells)** |
| 2 | repair | format repairs <10% of decision calls; budget repairs separately; malformed-after-repair ≤1 cell | format repairs **157 / 853 = 18.4%** (143 per-role fallback + 14 aimed); budget repairs **9 / 853 = 1.1%**; malformed-after-repair on **0 cells**, from 15 | **FAIL on the rate; PASS on malformed-after-repair** |
| 6 | grader | every grade hand-checked; agreement per boolean; if zero rows, say so and why | **6 grades produced**, all hand-checked against the objection and `flaw.json`. Agreement **6/6** on `identified_flaw` (2 of them strict-but-defensible), **5/5** on `characterises_the_flaw` where it was gradable, 1 dissent | **PASS** |
| 8 | ops | wall-clock vs `run_timeout_s`; realised $/cell; sweep projection | decide 42.4 + 10.0 min, contest 3.8 + 0.6 min. **$0.4860** total, **$0.00392 / decided cell**. Sweep ≈ **$24.8** (**$32.3** at 1.3×), ≈ **39 h** | **PASS** |

Rows 3, 4, 5, 7 and 9 are not re-run here. Their numbers move with the 16 extra cells —
the funnel below is restated in full — but no threshold in them changes.

## Row 1 — the 18 retries, cell by cell

**16 of 18 recovered.** All 15 of the malformed-after-repair cells were re-decided
without a malformed reply; 2 of the 3 truncation-related cells recovered as well.

| cell | shape it died on last time | outcome |
|---|---|---|
| `gpqa-161-flawed__self_critique` | truncated after a format repair | **recovered** (FLAWED, correct) |
| `gpqa-93-sound__debate` | `xml_tag` | **recovered** (FLAWED, wrong) |
| `gpqa-93-sound__self_critique` | `no_public_label` | **recovered** (FLAWED, wrong) |
| `law-con2_gpt4_A-s13__self_critique` | `no_public_label` | **recovered** (FLAWED, correct) |
| `law-con5_gpt4_B-s4__self_critique` | `label_not_at_line_start` | **recovered** (SOUND, correct) |
| `lojban-stim157_gpt3-5_B-s3__debate` | truncated past the label | **recovered** (SOUND, wrong) |
| `lojban-stim157_gpt3-5_B-s3__self_critique` | `no_public_label` | **recovered** (FLAWED, correct) |
| `lojban-stim172_gpt4_B-s4__self_critique` | `label_not_at_line_start` | **FAILED — new shape**: the critic truncated at 29,079 chars *past* its `Reasoning:` label, so truncation stayed fatal by design. A repetition loop: *"I'll output it. \nDone. \nI'll send. \nOk. \nI'll now produce. \nI'll output. \nI'll send. \nDone."* |
| `lojban-stim177_gpt4_A-s22__single` | `label_not_at_line_start` | **recovered** (FLAWED, correct) — no repair needed at all |
| `medqa-train_1442__debate` | `private_label_in_public` | **recovered** (FLAWED, correct) |
| `medqa-train_2769__self_critique` | `label_not_at_line_start` | **recovered** (FLAWED, correct) — no repair needed |
| `python800-p03372-flawed__debate` | truncated after a budget repair | **FAILED — same shape**: turn truncated at 25,617 chars with no public label → budget repair → truncated again at 27,631. A debater assigned to defend a *flawed* text and unable to stop computing counterexamples against itself: *"But I'm assigned to argue that the text does…"* |
| `python800-p03407-flawed__debate` | `no_public_label` | **recovered** (SOUND, wrong) |
| `python800-p03945-flawed__debate` | `no_public_label` (after a budget repair) | **recovered** (FLAWED, correct) |
| `surgery-sur10_gpt3-5_A-s1__self_critique` | `private_label_in_public` | **recovered** (FLAWED, correct) |
| `theoremqa-…-math_abstract_algebra_7_3-…-flawed__self_critique` | `private_label_in_public` | **recovered** (FLAWED, correct) — no repair needed |
| `theoremqa-…-maxku_ipnetwork8-lan-…-sound__self_critique` | `label_not_at_line_start` | **recovered** (SOUND, correct) |
| `theoremqa-…-rate_distortion_function_2-…-sound__debate` | `label_not_at_line_start` | **recovered** (SOUND, correct) — no repair needed |

Neither surviving failure is a malformed reply. Both are the runaway private
deliberation of §3l's defect 2, which this change does not address and did not claim to.

**The aimed instruction is what fired.** Of the 14 format repairs in the retry pass,
**12 were the misplaced-label instruction and 2 the Thinking-only instruction**; two
more cells took a budget repair. **5 of the 18 cells spent no repair at all** — sampling
is nondeterministic and the same prompt came back clean — and 4 of those 5 recovered
(the fifth is `lojban-stim172`, which truncated before it could be repaired). No call
received more than one repair; that is asserted in the script, not assumed.

## Row 2 — a side effect that has to be stated

The aimed instruction says *"do not write a Thinking section"*, and in the **solo
conditions the conversation carries it forward**: every stage after a repair in that
run also came back with no Thinking section. Measured over the decision records:

| | original 108-cell pass | the 18-cell retry pass |
|---|---|---|
| `strict` (both sections) | 472 (90.1%) | 49 (48.0%) |
| `salvaged_no_thinking` | 25 (4.8%) | **52 (51.0%)** |

Every solo run that spent a repair went `salvaged_no_thinking` for **all** of its
remaining stages; every run that spent none stayed `strict` throughout. This is **not a
leak** — nothing marked private is published, because nothing was marked private — but
it does mean those cells' records are a different kind of document from the rest: the
whole reasoning is public. It is a confound between the retried cells and the other 108,
and a design question for the sweep (`repair_instruction_for` could ask for the public
section *for this reply only*). Recorded here rather than fixed, because fixing it is a
prompt change and this pass had one job.

## Row 6 — the six graded rows, hand-checked

| item | condition | basis | identified | characterised | valid | hand-check |
|---|---|---|---|---|---|---|
| `gpqa-161-flawed` | debate | injected_pair | YES | (ungradable) | no | **agree.** Flaw is at step 4; the objection engages step 4's boundary assumption directly. The grader answered YES to the second bar and the `location_only` clamp forced it False — working as designed, since gpqa records where and not what |
| `theoremqa-…-kite2-png-flawed` | debate | injected_pair | YES | YES | **yes** | **agree on both.** The annotation says step 7's arithmetic is wrong (49, not 39); the objection names step 7, says 41+90≠141, and draws the same conclusion |
| `law-evi5_gpt4_A-s5` | self_critique | sentence_labels | YES | NO | no | **agree on the first, dissent on the second.** The objection says graphing skill does not qualify the draftsman as an expert — which is exactly what both annotators say. The grader marked NO because the objection framed it through FRE 1006 vs 702. Strict; I would have said YES |
| `medqa-train_2855` | self_critique | final_answer | NO | NO | no | **agree, strictly.** The objection catches the internal contradiction (ACD means *low* serum iron, the patient's is high) which is the annotator's first observation, but never reaches the recorded flaw — that the answer should be (D), isoniazid-induced sideroblastic anemia |
| `medqa-train_2855` | debate | final_answer | NO | NO | no | **agree, same reasoning.** Same item, same near-miss |
| `python800-p03407-flawed` | debate | injected_pair | NO | NO | no | **agree.** The objection argues the *problem statement* is ambiguous; the recorded flaw is that the text under review misread it. Different claim |

Agreement: **6/6** on `identified_flaw`, **5/5** on `characterises_the_flaw` where it was
gradable, with the `law-evi5` dissent noted. The grader's reasoning is legible and cites
the annotation — this is what row 6 was written to check, and it now checks.

One quoted grade, `theoremqa-…-kite2-png-flawed`:

> "The recorded flaw points to Step 7 as the location of the error. Step 7 states:
> 'Simplifying, we get 141 + m∠KHJ = 180'. The objection correctly identifies that
> 41 + 90 ≠ 141 (it equals 131). … Let me verify: If 41 + 90 + m∠KHJ = 180, then
> m∠KHJ = 180 - 131 = 49. ✓ … **Identified the flaw:** YES … **Characterised the
> flaw:** YES."

`valid_objection` is now **1 of 5 measured** (8 eligible) — the first non-empty
denominator this experiment has produced.

## Row 8 — ops, both passes

| stage | wall-clock | outcome | spend |
|---|---|---|---|
| decide (first pass) | 42.4 min | 108 completed, 18 failed | $0.2837 |
| grade (the 5 waiting rows) | seconds | 5 graded | $0.0194 |
| decide (retry) | 20:26:39 → 20:36:37 (**10.0 min**) | 16 completed, 2 failed, 108 skipped | $0.0545 |
| contest (retry) | 20:36:53 → 20:37:26 (**0.6 min**) | 16 completed, 110 skipped | $0.0173 |
| grade (retry) | seconds | 1 graded, 125 skipped | $0.0049 |
| analyse | seconds | 124 rows indexed | $0.0000 |
| | | | **$0.4860** |

- **$0.00392 per decided cell**, up from $0.00361: the 16 recovered cells are the
  expensive ones by construction — they are the cells that burn a repair.
- **Sweep projection** at 6,330 cells: **$24.8**, **$32.3** at 1.3× headroom.
- **Wall-clock ≈ 39 h** is unchanged; the retry's 33 s/cell is over 18 cells selected
  for difficulty at 8 in flight and is not a fair per-cell figure. No run came near
  `run_timeout_s = 1800`.
- Experiment running total: $4.899 (probes) + $0.335 (pilot 1) + $0.486 = **$5.720**.

## The funnel, restated on 124 cells

**Not comparable with the 108-cell table above.** 16 of these cells were selected for
having failed twice on format, and they entered the funnel on the same footing as the
rest; the table moves for that reason as well as for the extra n.

| | single | self_critique | debate | pooled |
|---|---|---|---|---|
| decided cells | 42 | 41 | 41 | 124 |
| gold flawed | 21 | 21 | 20 | 62 |
| accuracy before the contest | 38/42 | 31/41 | 27/41 | 96/124 |
| false negatives / false positives | 1 / 3 | 2 / 8 | 6 / 8 | 9 / 19 |
| decline rate | 23/42 | 18/41 | 14/41 | 55/124 |
| objection (contests) given incorrect | 2/4 | 8/10 | 10/14 | 20/28 |
| false alarm given correct | 17/38 | 15/31 | 16/27 | 48/96 |
| … on a correct FLAWED verdict | 16/20 | 15/19 | 10/14 | 41/53 |
| … on a correct SOUND verdict | 1/18 | 0/12 | 6/13 | 7/43 |
| **revised given incorrect** | **0/4** | **4/10** | **5/14** | **9/28** |
| **revised given correct** | **0/38** | **1/31** | **9/27** | **10/96** |
| revised given false negative | 0/1 | 0/2 | **4/6** | 4/9 |
| revised given false positive | 0/3 | 4/8 | 1/8 | 5/19 |
| `identified_flaw` | 0/0 (elig. 1) | 1/2 | 2/4 (elig. 6) | **3/6** (elig. 9) |
| `valid_objection` | 0/0 (elig. 1) | 0/2 | 1/3 (elig. 5) | **1/5** (elig. 8) |
| accuracy after the contest | 38/42 | **34/41** | **23/41** | 95/124 |
| comprehension (mean) | 4.43 | 4.22 | 3.93 | — |
| stances (contests / agrees / declined / unclear) | 19/0/23/0 | 23/0/18/0 | 26/1/14/0 | 68/1/55/0 |

The shape of the first block's finding survives the extra cells: the contest moves wrong
decisions more often than right ones pooled (**9/28 vs 10/96**, ≈3.4×), and in `debate`
it moves right ones too — 9 of 27 — so debate's accuracy falls **27/41 → 23/41** while
`self_critique` rises **31/41 → 34/41** and `single` does not move at all. `debate` is
also where false negatives get corrected: **4 of 6**, against 0 of 2 and 0 of 1.

`revised_given_correct = 0/38` in `single` and the 0/4 above it: the single condition's
re-decider has not changed its mind once in 42 contests. That is worth a look before the
sweep — it may be the condition, or it may be that a model asked to contradict itself in
its own conversation simply does not.

## What is still open, in the order it costs

1. **Two truncation cells**, both runaway private deliberation past `generation_max_tokens
   = 8192`. `frequency_penalty` is the knob the config's own `WHY` line points at and it
   is still at 0. A critique that truncates *past* its label kills the whole cell, which
   is worth re-reading before the sweep.
2. **The format-repair rate, 18.4% of decision calls.** The aimed instruction fixed what
   repairs *achieve*, not how often they are needed. 143 of the 157 are still the
   per-role fallback, i.e. first-attempt failures on shapes with no aimed instruction.
3. **The no-Thinking carry-over in solo conversations** (row 2 above).
4. **Provider pinning**, on the first block's numbers.

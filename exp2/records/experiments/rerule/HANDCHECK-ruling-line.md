# Re-rule: the new ruling line and the `ruling_agreement` instrument — hand checks, 2026-08-27

Two hand checks by Fable, both on rulings made with the new `stated_conclusion` line
(variant C: the user's "original text in `<solution>`" paragraph, the nesting rule, an
absolute `Conclusion:` line, UPHOLD/OVERTURN derived by code).

## 1. The 69-ruling smoke (`outputs/experiments/rerule-smoke`) — every ruling read

The 62 phantom objections of the re-contest (prose endorsing the verdict; the old line
overturned 52 of them) plus 7 controls on the same items. Read against the judge's own
closing reasoning: **69 of 69 lines agree with their prose.** The old line overturned
52/62 phantoms; the new line overturns 1/62 (`gpqa-191-sound__single`, whose prose does
argue the text is flawed — consistent). Correct-after on the 62: 15 → 56.

Haiku's `ruling_agreement` flagged 1 mismatch (`python800-p03416-flawed__single`): the
judge's prose ends *"the <solution> correctly assesses the code's logic"* and its line says
no flaw — they agree; Haiku misread. So on the smoke the instrument's one alarm was false
and the line's residual was 0/69.

## 2. `rerule-recontest` (464 rulings) — 20 read, weighted to the instrument's alarms

Haiku flagged 27/464 (5.8%) mismatches: FLAWED parents 18/335 (5.4%), SOUND 9/129 (7.0%)
— flat across parents, unlike the old line's failure, which was concentrated on FLAWED.
Sample: 10 of the 27 mismatches (including 3 of the 5 `single`/SOUND ones, the highest
cell), and 10 non-mismatches stratified by parent × line.

| # | cell | parent | line | Haiku | judge's prose concludes | whose error |
|---|---|---|---|---|---|---|
| 1 | python800-p02991-sound__single | SOUND | FLAWED | SOUND | "<solution> accurately diagnoses the bug… no false statements" → SOUND | **line** |
| 2 | python800-p02570-sound__single | SOUND | FLAWED | SOUND | "<solution> correctly identifies the boundary issue" → SOUND | **line** |
| 3 | python800-p03494-sound__single | SOUND | FLAWED | SOUND | "analysis… accurate and valid" → SOUND | **line** |
| 4 | medqa-train_2769__self_critique | SOUND | FLAWED | SOUND | prose treats the <solution> as a critique that is right → SOUND; muddled | **line** (prose confused) |
| 5 | python800-p03671-flawed__single | FLAWED | SOUND | FLAWED | "the analysis's reasoning is flawed" → FLAWED | **line** |
| 6 | python800-p03502-flawed__single | FLAWED | SOUND | FLAWED | "the analysis's reasoning is flawed" → FLAWED | **line** |
| 7 | python800-p03549-flawed__self_critique | FLAWED | SOUND | FLAWED | "the original text… incorrectly states the program contains a flaw" → FLAWED | **line** |
| 8 | lojban-stim145_gpt3-5_A-s4__self_critique | FLAWED | FLAWED | SOUND | "sentence 4… does not contain a flaw" → SOUND | **line** |
| 9 | medqa-train_1478__self_critique | FLAWED | SOUND | NEITHER | "does not contain a clear, unambiguous flaw" → SOUND | **Haiku** (over-read a hedge) |
| 10 | python800-p02951-flawed__single | FLAWED | SOUND | FLAWED | "the analysis's claim… is false" → FLAWED | **line** |
| 11–20 | ten non-mismatches (medqa, law, python800 ×5, theoremqa, gpqa) | — | — | — | all agree with their line | none |

**Instrument: 19 of 20 readings correct.** Of the 10 alarms, 9 are real. The residual
line error is therefore real, ~5–6%, and it is still the python800 nesting — "the analysis
correctly identifies the bug" → a FLAWED line (1–3), and "the analysis's claim of a bug is
false" → a SOUND line (5, 6, 7, 10) — the double negative the nesting paragraph reduced but
did not eliminate. It now appears in **both** directions at similar rates, which is why it
no longer concentrates on FLAWED parents.

## 3. `rerule-sweep` (1,129 rulings) — the worst cell of the instrument, 10 read

Haiku's mismatch rate on the sweep re-rule is 68/1,122 = 6.1%, flat across parents
(FLAWED 6.0%, SOUND 6.3%) but highest on the solo conditions (single 7.5%, self_critique
9.5%, debate 2.3%); the worst cell is `self_critique`/FLAWED at 26/247 = 10.5%. I read 10
of those 26 (seed 9).

**10 of 10 are the line contradicting the prose; Haiku is right on 8 and returns NEITHER
on 2.** Every one is the same direction of the python800 nesting: the judge's prose says
*"the analysis correctly identifies the flaw in the program… the analysis's conclusion that
the program is flawed is justified"* — i.e. the text under review is **right** — and the
line says the text **contains a flaw** (cells `p02922`, `p03339`, `p03074`, `p02700`,
`p02662`, `p03131`, `p03042`; plus `medqa-train_3256` and `lojban-stim155` with prose
ending "does not contain a flaw" / "the assessment's conclusion is supported"). One
(`p02973-sound`) is a genuine judgement call — the prose says the text's conclusion is
right but its explanation of the cause is wrong, which under the design's definition is a
flaw; the line said SOUND.

So the residual has a **known direction**: on texts that correctly report a bug, the line
over-calls FLAWED. Where the decision was a wrong FLAWED on a sound python800 item, that
turns a would-be overturn into an uphold. The bias is against correcting wrong FLAWED
decisions in the solo conditions on python800, at roughly the measured 6–10%.

## What this settles

* The old line's failure (8/12 on FLAWED parents in the re-contest hand check; 52/62
  phantoms overturned) is gone: 0/69 on the smoke, ~6% measured on the full pass, flat.
* Every recourse-stage number from a `stated_conclusion` tree carries a **measured** bound
  (`ruling_line_mismatch` in `metrics.json`) rather than an unmeasured one.
* The residual is a corpus property (python800's text is an assessment of a program) more
  than a prompt property; a per-subset phrasing of the question is the next lever, and it
  is a design decision.

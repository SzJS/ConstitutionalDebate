# findings-1 — the cells to read by hand

**Fable reads these and writes the verdicts.** This file chooses the cells and
prints their paths; it scores nothing. Every path is `transcript.md`, the
readable record; `transcript_full.md` beside it is the same run verbatim, every
prompt and every reply, and is where the private `Thinking:` sections are. The
decision document carries the FINDINGS LIST and the contest document carries the
objection, the ruling lines and the re-derived verdict.

Seeded per group, so a re-draw of one group does not move the others. Sorted by
`cell_id` inside each group, so the order carries no information.

Index: F-weak 1644 rows (`outputs/experiments/fd1-weak/index.jsonl`).
Index: F-strong 1644 rows (`outputs/experiments/fd1-strong/index.jsonl`).

## (a) recourse BROKE a right decision

The findings judge's own derived verdict was RIGHT and the re-derived verdict
after recourse is WRONG. **This is the failure P2 says the LOCAL contest should
produce less of than jd5-B's whole-job objection did**, so the read should say
which contest did it, whether the ruling's prose supports the line it wrote, and
whether the flipped finding was in fact the annotated flaw.

5 drawn from a pool of 271, `random.Random(101)`.

- **`gpqa-168-sound__debate__r1`** [weak] — SOUND before, 1 findings (0 FLAW), 1 contests
  - weak decision: `outputs/experiments/fd1-weak/cells/gpqa-168-sound__debate__r1/runs/20260902T162558Z-gpqa-168-sound-rejudge/transcript.md`
  - weak contest:  `outputs/experiments/fd1-weak/cells/gpqa-168-sound__debate__r1/contests/google-gemini-2.5-flash/runs/20260902T172611Z-gpqa-168-sound-recourse/transcript.md`
- **`lojban-stim175_gpt3-5_B-s1__debate__r1`** [weak] — SOUND before, 1 findings (0 FLAW), 1 contests
  - weak decision: `outputs/experiments/fd1-weak/cells/lojban-stim175_gpt3-5_B-s1__debate__r1/runs/20260902T164105Z-lojban-stim175_gpt3-5_B-s1-rejudge/transcript.md`
  - weak contest:  `outputs/experiments/fd1-weak/cells/lojban-stim175_gpt3-5_B-s1__debate__r1/contests/google-gemini-2.5-flash/runs/20260902T173545Z-lojban-stim175_gpt3-5_B-s1-recourse/transcript.md`
- **`python800-p03609-sound__debate__r1`** [weak] — SOUND before, 2 findings (0 FLAW), 2 contests
  - weak decision: `outputs/experiments/fd1-weak/cells/python800-p03609-sound__debate__r1/runs/20260902T171235Z-python800-p03609-sound-rejudge/transcript.md`
  - weak contest:  `outputs/experiments/fd1-weak/cells/python800-p03609-sound__debate__r1/contests/google-gemini-2.5-flash/runs/20260902T180238Z-python800-p03609-sound-recourse/transcript.md`
- **`surgery-sur53_gpt4_B-s12__debate__r1`** [weak] — SOUND before, 4 findings (0 FLAW), 1 contests
  - weak decision: `outputs/experiments/fd1-weak/cells/surgery-sur53_gpt4_B-s12__debate__r1/runs/20260902T172026Z-surgery-sur53_gpt4_B-s12-rejudge/transcript.md`
  - weak contest:  `outputs/experiments/fd1-weak/cells/surgery-sur53_gpt4_B-s12__debate__r1/contests/google-gemini-2.5-flash/runs/20260902T181253Z-surgery-sur53_gpt4_B-s12-recourse/transcript.md`
- **`theoremqa-solutions-elaine_econ_micro_4-txt-sound__debate__r1`** [weak] — SOUND before, 3 findings (0 FLAW), 2 contests
  - weak decision: `outputs/experiments/fd1-weak/cells/theoremqa-solutions-elaine_econ_micro_4-txt-sound__debate__r1/runs/20260902T172146Z-theoremqa-solutions-elaine_econ_micro_4-txt-sound-rejudge/transcript.md`
  - weak contest:  `outputs/experiments/fd1-weak/cells/theoremqa-solutions-elaine_econ_micro_4-txt-sound__debate__r1/contests/google-gemini-2.5-flash/runs/20260902T181459Z-theoremqa-solutions-elaine_econ_micro_4-txt-sound-recourse/transcript.md`

## (b) recourse FIXED a wrong decision

The converse: the derived verdict was WRONG and recourse re-derived it RIGHT.
**This is the success P3 reports.** The read should say whether the contest that
did it was a finding flip, an upheld omission or a resolved contradiction — the
three routes are different claims and only the first has a jd5-B counterpart.

5 drawn from a pool of 285, `random.Random(102)`.

- **`lojban-stim158_gpt4_B-s11__debate__r1`** [weak] — SOUND before, 1 findings (0 FLAW), 1 contests
  - weak decision: `outputs/experiments/fd1-weak/cells/lojban-stim158_gpt4_B-s11__debate__r1/runs/20260902T164342Z-lojban-stim158_gpt4_B-s11-rejudge/transcript.md`
  - weak contest:  `outputs/experiments/fd1-weak/cells/lojban-stim158_gpt4_B-s11__debate__r1/contests/google-gemini-2.5-flash/runs/20260902T173725Z-lojban-stim158_gpt4_B-s11-recourse/transcript.md`
- **`lojban-stim168_gpt4_B-s8__debate__r1`** [weak] — SOUND before, 2 findings (0 FLAW), 1 contests
  - weak decision: `outputs/experiments/fd1-weak/cells/lojban-stim168_gpt4_B-s8__debate__r1/runs/20260902T164232Z-lojban-stim168_gpt4_B-s8-rejudge/transcript.md`
  - weak contest:  `outputs/experiments/fd1-weak/cells/lojban-stim168_gpt4_B-s8__debate__r1/contests/google-gemini-2.5-flash/runs/20260902T173657Z-lojban-stim168_gpt4_B-s8-recourse/transcript.md`
- **`lojban-stim182_gpt3-5_B-s5__debate__r1`** [weak] — SOUND before, 2 findings (0 FLAW), 1 contests
  - weak decision: `outputs/experiments/fd1-weak/cells/lojban-stim182_gpt3-5_B-s5__debate__r1/runs/20260902T164022Z-lojban-stim182_gpt3-5_B-s5-rejudge/transcript.md`
  - weak contest:  `outputs/experiments/fd1-weak/cells/lojban-stim182_gpt3-5_B-s5__debate__r1/contests/google-gemini-2.5-flash/runs/20260902T173527Z-lojban-stim182_gpt3-5_B-s5-recourse/transcript.md`
- **`python800-p02787-flawed__debate__r1`** [weak] — SOUND before, 3 findings (0 FLAW), 3 contests
  - weak decision: `outputs/experiments/fd1-weak/cells/python800-p02787-flawed__debate__r1/runs/20260902T170440Z-python800-p02787-flawed-rejudge/transcript.md`
  - weak contest:  `outputs/experiments/fd1-weak/cells/python800-p02787-flawed__debate__r1/contests/google-gemini-2.5-flash/runs/20260902T175059Z-python800-p02787-flawed-recourse/transcript.md`
- **`theoremqa-solutions-math_abstract_algebra_7_4-png-flawed__debate__r1`** [weak] — SOUND before, 1 findings (0 FLAW), 2 contests
  - weak decision: `outputs/experiments/fd1-weak/cells/theoremqa-solutions-math_abstract_algebra_7_4-png-flawed__debate__r1/runs/20260902T172307Z-theoremqa-solutions-math_abstract_algebra_7_4-png-flawed-rejudge/transcript.md`
  - weak contest:  `outputs/experiments/fd1-weak/cells/theoremqa-solutions-math_abstract_algebra_7_4-png-flawed__debate__r1/contests/google-gemini-2.5-flash/runs/20260902T181703Z-theoremqa-solutions-math_abstract_algebra_7_4-png-flawed-recourse/transcript.md`

## (c) an APPENDED finding, or an EMPTY list

The two shapes only the findings form can produce. An APPENDED finding is an
upheld omission written from the CONTEST's own quotes and marked
`added_at_recourse` — the read has to say whether the appended text is the
challenger's quotation or a judge invention. An EMPTY list is a SOUND verdict
reached by finding nothing, and it is contestable by omission alone; the read has
to say whether the FLAWED-side debater really raised nothing.

5 drawn from a pool of 63, `random.Random(103)`.

- **`python800-p02767-flawed__debate__r1`** [strong] — 1 finding(s) APPENDED at recourse
  - strong decision: `outputs/experiments/fd1-strong/cells/python800-p02767-flawed__debate__r1/runs/20260902T182452Z-python800-p02767-flawed-rejudge/transcript.md`
  - strong contest:  `outputs/experiments/fd1-strong/cells/python800-p02767-flawed__debate__r1/contests/google-gemini-2.5-flash/runs/20260902T183327Z-python800-p02767-flawed-recourse/transcript.md`
- **`python800-p03240-flawed__debate__r1`** [weak] — 1 finding(s) APPENDED at recourse
  - weak decision: `outputs/experiments/fd1-weak/cells/python800-p03240-flawed__debate__r1/runs/20260902T170912Z-python800-p03240-flawed-rejudge/transcript.md`
  - weak contest:  `outputs/experiments/fd1-weak/cells/python800-p03240-flawed__debate__r1/contests/google-gemini-2.5-flash/runs/20260902T175816Z-python800-p03240-flawed-recourse/transcript.md`
- **`python800-p03250-flawed__debate__r1`** [strong] — 1 finding(s) APPENDED at recourse
  - strong decision: `outputs/experiments/fd1-strong/cells/python800-p03250-flawed__debate__r1/runs/20260902T182526Z-python800-p03250-flawed-rejudge/transcript.md`
  - strong contest:  `outputs/experiments/fd1-strong/cells/python800-p03250-flawed__debate__r1/contests/google-gemini-2.5-flash/runs/20260902T183505Z-python800-p03250-flawed-recourse/transcript.md`
- **`theoremqa-solutions-math_abstract_algebra_7_4-png-flawed__debate__r1`** [weak] — 1 finding(s) APPENDED at recourse
  - weak decision: `outputs/experiments/fd1-weak/cells/theoremqa-solutions-math_abstract_algebra_7_4-png-flawed__debate__r1/runs/20260902T172307Z-theoremqa-solutions-math_abstract_algebra_7_4-png-flawed-rejudge/transcript.md`
  - weak contest:  `outputs/experiments/fd1-weak/cells/theoremqa-solutions-math_abstract_algebra_7_4-png-flawed__debate__r1/contests/google-gemini-2.5-flash/runs/20260902T181703Z-theoremqa-solutions-math_abstract_algebra_7_4-png-flawed-recourse/transcript.md`
- **`theoremqa-solutions-modulararithmetic5-txt-flawed__debate__r1`** [weak] — 1 finding(s) APPENDED at recourse
  - weak decision: `outputs/experiments/fd1-weak/cells/theoremqa-solutions-modulararithmetic5-txt-flawed__debate__r1/runs/20260902T172139Z-theoremqa-solutions-modulararithmetic5-txt-flawed-rejudge/transcript.md`
  - weak contest:  `outputs/experiments/fd1-weak/cells/theoremqa-solutions-modulararithmetic5-txt-flawed__debate__r1/contests/google-gemini-2.5-flash/runs/20260902T181447Z-theoremqa-solutions-modulararithmetic5-txt-flawed-recourse/transcript.md`

## (d) F-weak and F-strong DISAGREE on the before-verdict

The same debate, the same format, two judges, two derived verdicts — and no
recourse anywhere in the comparison. It is the one group that isolates the JUDGE.
The read should say whether the disagreement is about a FINDING (one judge saw a
flaw the other did not) or about a RULING on the same finding, because those are
different failures and the derivation rule turns both into one verdict.

5 drawn from a pool of 555, `random.Random(104)`.

- **`gpqa-129-flawed__debate__r1`** [both] — F-weak FLAWED (1 findings, 1 FLAW), F-strong SOUND (1 findings, 0 FLAW)
  - weak decision: `outputs/experiments/fd1-weak/cells/gpqa-129-flawed__debate__r1/runs/20260902T162524Z-gpqa-129-flawed-rejudge/transcript.md`
  - weak contest:  `outputs/experiments/fd1-weak/cells/gpqa-129-flawed__debate__r1/contests/google-gemini-2.5-flash/runs/20260902T172558Z-gpqa-129-flawed-recourse/transcript.md`
  - strong decision: `outputs/experiments/fd1-strong/cells/gpqa-129-flawed__debate__r1/runs/20260902T182254Z-gpqa-129-flawed-rejudge/transcript.md`
  - strong contest:  `outputs/experiments/fd1-strong/cells/gpqa-129-flawed__debate__r1/contests/google-gemini-2.5-flash/runs/20260902T182750Z-gpqa-129-flawed-recourse/transcript.md`
- **`medqa-dev_0101__debate__r1`** [both] — F-weak SOUND (1 findings, 0 FLAW), F-strong FLAWED (1 findings, 1 FLAW)
  - weak decision: `outputs/experiments/fd1-weak/cells/medqa-dev_0101__debate__r1/runs/20260902T165324Z-medqa-dev_0101-rejudge/transcript.md`
  - weak contest:  `outputs/experiments/fd1-weak/cells/medqa-dev_0101__debate__r1/contests/google-gemini-2.5-flash/runs/20260902T174314Z-medqa-dev_0101-recourse/transcript.md`
  - strong decision: `outputs/experiments/fd1-strong/cells/medqa-dev_0101__debate__r1/runs/20260902T182414Z-medqa-dev_0101-rejudge/transcript.md`
  - strong contest:  `outputs/experiments/fd1-strong/cells/medqa-dev_0101__debate__r1/contests/google-gemini-2.5-flash/runs/20260902T183141Z-medqa-dev_0101-recourse/transcript.md`
- **`medqa-train_0448__debate__r1`** [both] — F-weak SOUND (4 findings, 0 FLAW), F-strong FLAWED (3 findings, 2 FLAW)
  - weak decision: `outputs/experiments/fd1-weak/cells/medqa-train_0448__debate__r1/runs/20260902T164900Z-medqa-train_0448-rejudge/transcript.md`
  - weak contest:  `outputs/experiments/fd1-weak/cells/medqa-train_0448__debate__r1/contests/google-gemini-2.5-flash/runs/20260902T174126Z-medqa-train_0448-recourse/transcript.md`
  - strong decision: `outputs/experiments/fd1-strong/cells/medqa-train_0448__debate__r1/runs/20260902T182404Z-medqa-train_0448-rejudge/transcript.md`
  - strong contest:  `outputs/experiments/fd1-strong/cells/medqa-train_0448__debate__r1/contests/google-gemini-2.5-flash/runs/20260902T183118Z-medqa-train_0448-recourse/transcript.md`
- **`python800-p02912-sound__debate__r1`** [both] — F-weak SOUND (1 findings, 0 FLAW), F-strong FLAWED (1 findings, 1 FLAW)
  - weak decision: `outputs/experiments/fd1-weak/cells/python800-p02912-sound__debate__r1/runs/20260902T170601Z-python800-p02912-sound-rejudge/transcript.md`
  - weak contest:  `outputs/experiments/fd1-weak/cells/python800-p02912-sound__debate__r1/contests/google-gemini-2.5-flash/runs/20260902T175313Z-python800-p02912-sound-recourse/transcript.md`
  - strong decision: `outputs/experiments/fd1-strong/cells/python800-p02912-sound__debate__r1/runs/20260902T182503Z-python800-p02912-sound-rejudge/transcript.md`
  - strong contest:  `outputs/experiments/fd1-strong/cells/python800-p02912-sound__debate__r1/contests/google-gemini-2.5-flash/runs/20260902T183402Z-python800-p02912-sound-recourse/transcript.md`
- **`python800-p03473-flawed__debate__r1`** [both] — F-weak SOUND (3 findings, 0 FLAW), F-strong FLAWED (2 findings, 2 FLAW)
  - weak decision: `outputs/experiments/fd1-weak/cells/python800-p03473-flawed__debate__r1/runs/20260902T171123Z-python800-p03473-flawed-rejudge/transcript.md`
  - weak contest:  `outputs/experiments/fd1-weak/cells/python800-p03473-flawed__debate__r1/contests/google-gemini-2.5-flash/runs/20260902T180108Z-python800-p03473-flawed-recourse/transcript.md`
  - strong decision: `outputs/experiments/fd1-strong/cells/python800-p03473-flawed__debate__r1/runs/20260902T182541Z-python800-p03473-flawed-rejudge/transcript.md`
  - strong contest:  `outputs/experiments/fd1-strong/cells/python800-p03473-flawed__debate__r1/contests/google-gemini-2.5-flash/runs/20260902T183548Z-python800-p03473-flawed-recourse/transcript.md`

## (e) the PHANTOM read — 20 cells, PREREG §7's two blind spots

`phantom = (stance == contests) != (n_well_formed > 0)` is MECHANICAL: it is a
string comparison, not a model's reading, and it is never pooled with jd3-jd6's
Haiku phantom column. It has exactly two blind spots and neither is visible in any
column, so twenty cells are read by hand:

  1. a REVERSE with a well-formed contest whose `Why` in fact argues the finding
     is RIGHT — mechanically not a phantom, substantively one;
  2. a STANDS whose `Argument` attacks a finding without writing an entry for it
     — mechanically not a phantom, and a contest the harness never ruled on.

Ten of each, under two seeds, so the halves are independent samples.

## (e1) ten REVERSE objections  [blind spot 1]

Read the `Why` of every contest. Does it argue the finding is WRONG, or does it
agree with the finding and object to something else? A REVERSE whose every `Why`
endorses the finding it contests is a phantom the mechanical column cannot see.

10 drawn from a pool of 1682, `random.Random(105)`.

- **`gpqa-10-flawed__debate__r1`** [weak] — 1 contests, 1 void, mechanical phantom False
  - weak decision: `outputs/experiments/fd1-weak/cells/gpqa-10-flawed__debate__r1/runs/20260902T162127Z-gpqa-10-flawed-rejudge/transcript.md`
  - weak contest:  `outputs/experiments/fd1-weak/cells/gpqa-10-flawed__debate__r1/contests/google-gemini-2.5-flash/runs/20260902T172408Z-gpqa-10-flawed-recourse/transcript.md`
- **`gpqa-47-flawed__debate__r1`** [weak] — 1 contests, 0 void, mechanical phantom False
  - weak decision: `outputs/experiments/fd1-weak/cells/gpqa-47-flawed__debate__r1/runs/20260902T162707Z-gpqa-47-flawed-rejudge/transcript.md`
  - weak contest:  `outputs/experiments/fd1-weak/cells/gpqa-47-flawed__debate__r1/contests/google-gemini-2.5-flash/runs/20260902T172700Z-gpqa-47-flawed-recourse/transcript.md`
- **`medqa-train_1566__debate__r1`** [strong] — 1 contests, 0 void, mechanical phantom False
  - strong decision: `outputs/experiments/fd1-strong/cells/medqa-train_1566__debate__r1/runs/20260902T182417Z-medqa-train_1566-rejudge/transcript.md`
  - strong contest:  `outputs/experiments/fd1-strong/cells/medqa-train_1566__debate__r1/contests/google-gemini-2.5-flash/runs/20260902T183150Z-medqa-train_1566-recourse/transcript.md`
- **`medqa-train_3661__debate__r1`** [weak] — 2 contests, 0 void, mechanical phantom False
  - weak decision: `outputs/experiments/fd1-weak/cells/medqa-train_3661__debate__r1/runs/20260902T165921Z-medqa-train_3661-rejudge/transcript.md`
  - weak contest:  `outputs/experiments/fd1-weak/cells/medqa-train_3661__debate__r1/contests/google-gemini-2.5-flash/runs/20260902T174629Z-medqa-train_3661-recourse/transcript.md`
- **`python800-p03371-sound__debate__r1`** [strong] — 1 contests, 0 void, mechanical phantom False
  - strong decision: `outputs/experiments/fd1-strong/cells/python800-p03371-sound__debate__r1/runs/20260902T182533Z-python800-p03371-sound-rejudge/transcript.md`
  - strong contest:  `outputs/experiments/fd1-strong/cells/python800-p03371-sound__debate__r1/contests/google-gemini-2.5-flash/runs/20260902T183527Z-python800-p03371-sound-recourse/transcript.md`
- **`python800-p03609-sound__debate__r1`** [weak] — 2 contests, 0 void, mechanical phantom False
  - weak decision: `outputs/experiments/fd1-weak/cells/python800-p03609-sound__debate__r1/runs/20260902T171235Z-python800-p03609-sound-rejudge/transcript.md`
  - weak contest:  `outputs/experiments/fd1-weak/cells/python800-p03609-sound__debate__r1/contests/google-gemini-2.5-flash/runs/20260902T180238Z-python800-p03609-sound-recourse/transcript.md`
- **`python800-p03658-flawed__debate__r1`** [weak] — 1 contests, 0 void, mechanical phantom False
  - weak decision: `outputs/experiments/fd1-weak/cells/python800-p03658-flawed__debate__r1/runs/20260902T171320Z-python800-p03658-flawed-rejudge/transcript.md`
  - weak contest:  `outputs/experiments/fd1-weak/cells/python800-p03658-flawed__debate__r1/contests/google-gemini-2.5-flash/runs/20260902T180326Z-python800-p03658-flawed-recourse/transcript.md`
- **`python800-p03697-flawed__debate__r1`** [weak] — 2 contests, 0 void, mechanical phantom False
  - weak decision: `outputs/experiments/fd1-weak/cells/python800-p03697-flawed__debate__r1/runs/20260902T171351Z-python800-p03697-flawed-rejudge/transcript.md`
  - weak contest:  `outputs/experiments/fd1-weak/cells/python800-p03697-flawed__debate__r1/contests/google-gemini-2.5-flash/runs/20260902T180353Z-python800-p03697-flawed-recourse/transcript.md`
- **`theoremqa-solutions-Lah_number_1-txt-flawed__debate__r1`** [strong] — 1 contests, 0 void, mechanical phantom False
  - strong decision: `outputs/experiments/fd1-strong/cells/theoremqa-solutions-Lah_number_1-txt-flawed__debate__r1/runs/20260902T182650Z-theoremqa-solutions-Lah_number_1-txt-flawed-rejudge/transcript.md`
  - strong contest:  `outputs/experiments/fd1-strong/cells/theoremqa-solutions-Lah_number_1-txt-flawed__debate__r1/contests/google-gemini-2.5-flash/runs/20260902T183949Z-theoremqa-solutions-Lah_number_1-txt-flawed-recourse/transcript.md`
- **`theoremqa-solutions-elaine_econ_micro_14-txt-sound__debate__r1`** [weak] — 1 contests, 0 void, mechanical phantom False
  - weak decision: `outputs/experiments/fd1-weak/cells/theoremqa-solutions-elaine_econ_micro_14-txt-sound__debate__r1/runs/20260902T172108Z-theoremqa-solutions-elaine_econ_micro_14-txt-sound-rejudge/transcript.md`
  - weak contest:  `outputs/experiments/fd1-weak/cells/theoremqa-solutions-elaine_econ_micro_14-txt-sound__debate__r1/contests/google-gemini-2.5-flash/runs/20260902T181351Z-theoremqa-solutions-elaine_econ_micro_14-txt-sound-recourse/transcript.md`

## (e2) ten STANDS with a non-empty Argument  [blind spot 2]

Read the `Argument`. Does it accept the findings, or does it attack one without
writing a numbered contest for it? The second is an objection the harness never
put to a judge, and it is the failure this half exists to count.

10 drawn from a pool of 1597, `random.Random(106)`.

- **`gpqa-116-sound__debate__r1`** [weak] — stance `declined`, Argument 38 chars
  - weak decision: `outputs/experiments/fd1-weak/cells/gpqa-116-sound__debate__r1/runs/20260902T163252Z-gpqa-116-sound-rejudge/transcript.md`
  - weak contest:  `outputs/experiments/fd1-weak/cells/gpqa-116-sound__debate__r1/contests/google-gemini-2.5-flash/runs/20260902T173014Z-gpqa-116-sound-recourse/transcript.md`
- **`gpqa-160-sound__debate__r1`** [weak] — stance `declined`, Argument 38 chars
  - weak decision: `outputs/experiments/fd1-weak/cells/gpqa-160-sound__debate__r1/runs/20260902T162539Z-gpqa-160-sound-rejudge/transcript.md`
  - weak contest:  `outputs/experiments/fd1-weak/cells/gpqa-160-sound__debate__r1/contests/google-gemini-2.5-flash/runs/20260902T172608Z-gpqa-160-sound-recourse/transcript.md`
- **`gpqa-169-flawed__debate__r1`** [strong] — stance `declined`, Argument 38 chars
  - strong decision: `outputs/experiments/fd1-strong/cells/gpqa-169-flawed__debate__r1/runs/20260902T182321Z-gpqa-169-flawed-rejudge/transcript.md`
  - strong contest:  `outputs/experiments/fd1-strong/cells/gpqa-169-flawed__debate__r1/contests/google-gemini-2.5-flash/runs/20260902T182900Z-gpqa-169-flawed-recourse/transcript.md`
- **`lojban-stim151_gpt4_A-s5__debate__r1`** [strong] — stance `declined`, Argument 47 chars
  - strong decision: `outputs/experiments/fd1-strong/cells/lojban-stim151_gpt4_A-s5__debate__r1/runs/20260902T182352Z-lojban-stim151_gpt4_A-s5-rejudge/transcript.md`
  - strong contest:  `outputs/experiments/fd1-strong/cells/lojban-stim151_gpt4_A-s5__debate__r1/contests/google-gemini-2.5-flash/runs/20260902T183035Z-lojban-stim151_gpt4_A-s5-recourse/transcript.md`
- **`medqa-dev_0949__debate__r1`** [weak] — stance `declined`, Argument 38 chars
  - weak decision: `outputs/experiments/fd1-weak/cells/medqa-dev_0949__debate__r1/runs/20260902T164840Z-medqa-dev_0949-rejudge/transcript.md`
  - weak contest:  `outputs/experiments/fd1-weak/cells/medqa-dev_0949__debate__r1/contests/google-gemini-2.5-flash/runs/20260902T174104Z-medqa-dev_0949-recourse/transcript.md`
- **`python800-p03161-flawed__debate__r1`** [strong] — stance `declined`, Argument 38 chars
  - strong decision: `outputs/experiments/fd1-strong/cells/python800-p03161-flawed__debate__r1/runs/20260902T182522Z-python800-p03161-flawed-rejudge/transcript.md`
  - strong contest:  `outputs/experiments/fd1-strong/cells/python800-p03161-flawed__debate__r1/contests/google-gemini-2.5-flash/runs/20260902T183452Z-python800-p03161-flawed-recourse/transcript.md`
- **`python800-p03193-flawed__debate__r1`** [strong] — stance `declined`, Argument 38 chars
  - strong decision: `outputs/experiments/fd1-strong/cells/python800-p03193-flawed__debate__r1/runs/20260902T182523Z-python800-p03193-flawed-rejudge/transcript.md`
  - strong contest:  `outputs/experiments/fd1-strong/cells/python800-p03193-flawed__debate__r1/contests/google-gemini-2.5-flash/runs/20260902T183454Z-python800-p03193-flawed-recourse/transcript.md`
- **`python800-p03423-flawed__debate__r1`** [weak] — stance `declined`, Argument 38 chars
  - weak decision: `outputs/experiments/fd1-weak/cells/python800-p03423-flawed__debate__r1/runs/20260902T171045Z-python800-p03423-flawed-rejudge/transcript.md`
  - weak contest:  `outputs/experiments/fd1-weak/cells/python800-p03423-flawed__debate__r1/contests/google-gemini-2.5-flash/runs/20260902T180027Z-python800-p03423-flawed-recourse/transcript.md`
- **`python800-p03555-flawed__debate__r1`** [weak] — stance `declined`, Argument 38 chars
  - weak decision: `outputs/experiments/fd1-weak/cells/python800-p03555-flawed__debate__r1/runs/20260902T171202Z-python800-p03555-flawed-rejudge/transcript.md`
  - weak contest:  `outputs/experiments/fd1-weak/cells/python800-p03555-flawed__debate__r1/contests/google-gemini-2.5-flash/runs/20260902T180155Z-python800-p03555-flawed-recourse/transcript.md`
- **`theoremqa-solutions-Cayley_2-txt-flawed__debate__r1`** [weak] — stance `declined`, Argument 38 chars
  - weak decision: `outputs/experiments/fd1-weak/cells/theoremqa-solutions-Cayley_2-txt-flawed__debate__r1/runs/20260902T172136Z-theoremqa-solutions-Cayley_2-txt-flawed-rejudge/transcript.md`
  - weak contest:  `outputs/experiments/fd1-weak/cells/theoremqa-solutions-Cayley_2-txt-flawed__debate__r1/contests/google-gemini-2.5-flash/runs/20260902T181445Z-theoremqa-solutions-Cayley_2-txt-flawed-recourse/transcript.md`

---

Groups (a) and (b) are the two halves of P1's discordant pairs, so their POOL
sizes are the counts `findings-1.py`'s section (1) prints as `b` and `c`. The
samples here are for READING, never for counting, and no rate is computed from
them. Group (e)'s hand count IS a number the write-up quotes, and it is quoted as
a hand count of 20 cells with its two seeds.

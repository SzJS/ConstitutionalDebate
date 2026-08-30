# judgment-debate-6 — the cells to read by hand

cd exp2
    uv run python records/derivations/jd6-handcheck-pick.py > outputs/jd6-handcheck-pick.md

Read-only over `outputs/experiments/jd6-round/` and `outputs/experiments/jd6-plain/`. It
writes nothing under `outputs/experiments/` and it does NOT score anything: the whole point
of a hand check is that a person reads the documents and writes the verdicts, so this file
chooses the cells and prints where they are, and stops.

**Fable reads these and writes the verdicts.** This file chooses the cells and
prints their paths; it scores nothing. Every path is `transcript.md`, the
readable record; `transcript_full.md` beside it is the same run verbatim, every
prompt and every reply, and is where the private `Thinking:` sections are.

Indexes: arm R 1644 rows, arm B 886 rows.

## (a) R BROKE a right decision that B did not

M0 was right; the contest round's ruling left the cell wrong and the plain
round's judgment left it right. **This is the failure P1 says the round should
produce LESS of**, so every one of these is a case against the mechanism and the
read should say whether the round or the judge is what went wrong.

5 drawn from a pool of 176, `random.Random(6)`.

- **`gpqa-139-sound__debate__r1`**
  - contest round: `outputs/experiments/jd6-round/cells/gpqa-139-sound__debate__r1/contests/google-gemini-2.5-flash/runs/20260830T024053Z-gpqa-139-sound-rerule/transcript.md`
  - plain arm:     `outputs/experiments/jd6-plain/cells/gpqa-139-sound__debate__r1/runs/20260830T041057Z-gpqa-139-sound-rejudge/transcript.md`
- **`gpqa-191-sound__debate__r1`**
  - contest round: `outputs/experiments/jd6-round/cells/gpqa-191-sound__debate__r1/contests/google-gemini-2.5-flash/runs/20260830T023453Z-gpqa-191-sound-rerule/transcript.md`
  - plain arm:     `outputs/experiments/jd6-plain/cells/gpqa-191-sound__debate__r1/runs/20260830T041716Z-gpqa-191-sound-rejudge/transcript.md`
- **`medqa-dev_0083__debate__r1`**
  - contest round: `outputs/experiments/jd6-round/cells/medqa-dev_0083__debate__r1/contests/google-gemini-2.5-flash/runs/20260830T030026Z-medqa-dev_0083-rerule/transcript.md`
  - plain arm:     `outputs/experiments/jd6-plain/cells/medqa-dev_0083__debate__r1/runs/20260830T043748Z-medqa-dev_0083-rejudge/transcript.md`
- **`python800-p03737-sound__debate__r1`**
  - contest round: `outputs/experiments/jd6-round/cells/python800-p03737-sound__debate__r1/contests/google-gemini-2.5-flash/runs/20260830T033511Z-python800-p03737-sound-rerule/transcript.md`
  - plain arm:     `outputs/experiments/jd6-plain/cells/python800-p03737-sound__debate__r1/runs/20260830T051036Z-python800-p03737-sound-rejudge/transcript.md`
- **`surgery-sur31_gpt4_A-s6__debate__r1`**
  - contest round: `outputs/experiments/jd6-round/cells/surgery-sur31_gpt4_A-s6__debate__r1/contests/google-gemini-2.5-flash/runs/20260830T034828Z-surgery-sur31_gpt4_A-s6-rerule/transcript.md`
  - plain arm:     `outputs/experiments/jd6-plain/cells/surgery-sur31_gpt4_A-s6__debate__r1/runs/20260830T051850Z-surgery-sur31_gpt4_A-s6-rejudge/transcript.md`

## (b) R SAVED a right decision that B broke

The converse: M0 was right, the plain round's fresh judgment lost it, and the
argued round kept it. **This is the success P1 says the round should produce MORE
of**; the read should say whether the ANTI reply is what kept it, or whether the
judge would have upheld anyway.

5 drawn from a pool of 70, `random.Random(6)`.

- **`gpqa-103-sound__debate__r1`**
  - contest round: `outputs/experiments/jd6-round/cells/gpqa-103-sound__debate__r1/contests/google-gemini-2.5-flash/runs/20260830T023654Z-gpqa-103-sound-rerule/transcript.md`
  - plain arm:     `outputs/experiments/jd6-plain/cells/gpqa-103-sound__debate__r1/runs/20260830T040539Z-gpqa-103-sound-rejudge/transcript.md`
- **`gpqa-149-sound__debate__r1`**
  - contest round: `outputs/experiments/jd6-round/cells/gpqa-149-sound__debate__r1/contests/google-gemini-2.5-flash/runs/20260830T024221Z-gpqa-149-sound-rerule/transcript.md`
  - plain arm:     `outputs/experiments/jd6-plain/cells/gpqa-149-sound__debate__r1/runs/20260830T041149Z-gpqa-149-sound-rejudge/transcript.md`
- **`gpqa-85-flawed__debate__r1`**
  - contest round: `outputs/experiments/jd6-round/cells/gpqa-85-flawed__debate__r1/contests/google-gemini-2.5-flash/runs/20260830T023834Z-gpqa-85-flawed-rerule/transcript.md`
  - plain arm:     `outputs/experiments/jd6-plain/cells/gpqa-85-flawed__debate__r1/runs/20260830T042554Z-gpqa-85-flawed-rejudge/transcript.md`
- **`python800-p02407-flawed__debate__r1`**
  - contest round: `outputs/experiments/jd6-round/cells/python800-p02407-flawed__debate__r1/contests/google-gemini-2.5-flash/runs/20260830T030745Z-python800-p02407-flawed-rerule/transcript.md`
  - plain arm:     `outputs/experiments/jd6-plain/cells/python800-p02407-flawed__debate__r1/runs/20260830T044655Z-python800-p02407-flawed-rejudge/transcript.md`
- **`surgery-sur54_gpt4_B-s12__debate__r1`**
  - contest round: `outputs/experiments/jd6-round/cells/surgery-sur54_gpt4_B-s12__debate__r1/contests/google-gemini-2.5-flash/runs/20260830T035250Z-surgery-sur54_gpt4_B-s12-rerule/transcript.md`
  - plain arm:     `outputs/experiments/jd6-plain/cells/surgery-sur54_gpt4_B-s12__debate__r1/runs/20260830T052315Z-surgery-sur54_gpt4_B-s12-rejudge/transcript.md`

## (c) the adopt-one-reply instrument fired

The ruling's prose tracks ONE reply materially more closely than the other
(distinctive 6-grams, one at least twice the other). **The instrument cannot tell
adoption from agreement** — a judge that reached PRO's conclusion independently
shares its vocabulary — which is exactly why these go to a person. The question
is whether the ruling ANSWERS the other reply anywhere, or only recites one.

5 drawn from a pool of 471, `random.Random(6)`.

- **`gpqa-173-flawed__debate__r1`** — tracks **pro** (pro 0.2763, anti 0.1289)
  - contest round: `outputs/experiments/jd6-round/cells/gpqa-173-flawed__debate__r1/contests/google-gemini-2.5-flash/runs/20260830T024639Z-gpqa-173-flawed-rerule/transcript.md`
  - plain arm:     `outputs/experiments/jd6-plain/cells/gpqa-173-flawed__debate__r1/runs/20260830T041427Z-gpqa-173-flawed-rejudge/transcript.md`
- **`python800-p02899-flawed__debate__r1`** — tracks **pro** (pro 0.2036, anti 0.0559)
  - contest round: `outputs/experiments/jd6-round/cells/python800-p02899-flawed__debate__r1/contests/google-gemini-2.5-flash/runs/20260830T031519Z-python800-p02899-flawed-rerule/transcript.md`
  - plain arm:     `outputs/experiments/jd6-plain/cells/python800-p02899-flawed__debate__r1/runs/20260830T045237Z-python800-p02899-flawed-rejudge/transcript.md`
- **`python800-p03293-flawed__debate__r1`** — tracks **pro** (pro 0.1199, anti 0.045)
  - contest round: `outputs/experiments/jd6-round/cells/python800-p03293-flawed__debate__r1/contests/google-gemini-2.5-flash/runs/20260830T032526Z-python800-p03293-flawed-rerule/transcript.md`
  - plain arm:     `outputs/experiments/jd6-plain/cells/python800-p03293-flawed__debate__r1/runs/20260830T050225Z-python800-p03293-flawed-rejudge/transcript.md`
- **`surgery-sur39_gpt4_B-s1__debate__r1`** — tracks **pro** (pro 0.148, anti 0.0267)
  - contest round: `outputs/experiments/jd6-round/cells/surgery-sur39_gpt4_B-s1__debate__r1/contests/google-gemini-2.5-flash/runs/20260830T035011Z-surgery-sur39_gpt4_B-s1-rerule/transcript.md`
  - plain arm:     `outputs/experiments/jd6-plain/cells/surgery-sur39_gpt4_B-s1__debate__r1/runs/20260830T052013Z-surgery-sur39_gpt4_B-s1-rejudge/transcript.md`
- **`surgery-sur54_gpt4_A-s3__debate__r1`** — tracks **anti** (pro 0.0482, anti 0.1877)
  - contest round: `outputs/experiments/jd6-round/cells/surgery-sur54_gpt4_A-s3__debate__r1/contests/google-gemini-2.5-flash/runs/20260830T035247Z-surgery-sur54_gpt4_A-s3-rerule/transcript.md`
  - plain arm:     `outputs/experiments/jd6-plain/cells/surgery-sur54_gpt4_A-s3__debate__r1/runs/20260830T052314Z-surgery-sur54_gpt4_A-s3-rejudge/transcript.md`

## (d) the plain arm moved a verdict

An ordinary extra round with NO objection anywhere, and the judge changed its
mind about the same debate. The read should say whether round 4 added anything
the judge could have been moved by, or whether this is the judge disagreeing with
itself on a re-draw — which is the caveat PREREG.md attaches to every absolute
rate in this arm, and which no arm here prices.

5 drawn from a pool of 205, `random.Random(6)`.

- **`gpqa-159-flawed__debate__r1`**
  - plain arm: `outputs/experiments/jd6-plain/cells/gpqa-159-flawed__debate__r1/runs/20260830T041243Z-gpqa-159-flawed-rejudge/transcript.md`
- **`python800-p02854-sound__debate__r1`**
  - plain arm: `outputs/experiments/jd6-plain/cells/python800-p02854-sound__debate__r1/runs/20260830T045204Z-python800-p02854-sound-rejudge/transcript.md`
- **`python800-p03372-flawed__debate__r1`**
  - plain arm: `outputs/experiments/jd6-plain/cells/python800-p03372-flawed__debate__r1/runs/20260830T050329Z-python800-p03372-flawed-rejudge/transcript.md`
- **`theoremqa-solutions-differential_entropy-png-sound__debate__r1`**
  - plain arm: `outputs/experiments/jd6-plain/cells/theoremqa-solutions-differential_entropy-png-sound__debate__r1/runs/20260830T052547Z-theoremqa-solutions-differential_entropy-png-sound-rejudge/transcript.md`
- **`theoremqa-solutions-physics_current_and_resistance-txt-sound__debate__r1`**
  - plain arm: `outputs/experiments/jd6-plain/cells/theoremqa-solutions-physics_current_and_resistance-txt-sound__debate__r1/runs/20260830T052849Z-theoremqa-solutions-physics_current_and_resistance-txt-sound-rejudge/transcript.md`

---

Groups (a) and (b) are the two halves of P1's discordant pairs, so their POOL
sizes are the numbers the primary test is computed from; the derivation's
section (1) prints them as `b` and `c`. The samples here are for reading, never
for counting.

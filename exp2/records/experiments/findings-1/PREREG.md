# The findings variant (`fd1`): two arms, pre-registered.

**Drafted 2026-09-02. TO BE COMMITTED BEFORE EITHER FULL ARM'S FIRST PAID CALL**, as
`records/experiments/findings-1/PREREG.md`. Nothing here may be edited after that call.
`outputs/fd1-run-all.sh` refuses to start until this file is tracked by git.

Already spent and NOT covered by this document: three six-cell smokes ($0.21, $0.17, $0.21)
read in `outputs/fd1-smoke-{1,2,3}-read.md`; two 60-cell pilots ($1.09 weak, $0.77 strong); a re-read of the pilots' 66 rulings
with the revised reader ($0.16); the injection instrument ($0.55); the provider check
($0.00006). Total before this document: $3.37. Those are prompt checks under the house
rule (`HANDOFF.md` §2.8) and carry no threshold on any quantity below except the
feasibility rule, which was written before the pilot ran (see *Feasibility*).

The user's specification is `debate_variants.md` (2026-09-02). The plan it was built from
is recorded in `LLM_NOTES.md` §3ad's opening; every departure from the plan is listed in
*What the smokes changed*.

## The question, in one paragraph

Every recourse arm of this experiment so far — the sweep, jd3, jd5, jd6 — discriminates
(fixes 40–54% of the wrong decisions it is put to, breaks 20–36% of the right ones) and
still nets NEGATIVE on accuracy, because `f/b` never beats the prior odds `a/(1−a)` that
the decision was right (`LLM_NOTES.md` §3ac). The user's hypothesis is that the
challenger has to redo the judge's whole job. The mechanism under test: the judge
**decomposes** its judgment into numbered **findings** — one per purported flaw the
FLAWED-side debater raised, each ruled `FLAW` / `NOT A FLAW` — and the verdict is
**derived by code** (FLAWED iff any finding is FLAW; an empty list is SOUND). A contest is
local: a finding's ruling, an omission, or a contradiction. Recourse rules per contest
with an absolute line and the verdict is re-derived. Does finding-level contest break
fewer right decisions than verdict-level contest, and does recourse then net positive?

## The two arms

| | F-weak | F-strong |
|---|---|---|
| findings judge = recourse judge | `meta-llama/llama-4-maverick`, temp 0, pinned `["digitalocean"]`, no fallback | `openai/gpt-5.6-luna-20260709`, temp 0, pinned `["openai"]` (the base slug; `openai/fast` costs 2× and is not the default route), no fallback |
| challenger | `google/gemini-2.5-flash`, temp 0.7, neutral + the certainty clause, may decline, decision line last (unpinned; Google-only provider; as jd3–jd6) | same |
| debaters | not called | not called |
| grader / readers | `anthropic/claude-haiku-4.5`, temp 0 | same |
| reasoning | off, verified: 0 reasoning tokens on every check call (`outputs/fd1-provider-check.log`) | same |
| stages | `rejudge contest agreement ruling_agreement grade analyse` (agreement makes NO call: mechanical) | same |
| spec | `experiments/fd1-weak.toml` | `experiments/fd1-strong.toml` |

Both arms re-judge the SAME 1,644 stored debate transcripts (`transcripts_from =
outputs/experiments/jd3-main`, fingerprint `dfa9bdca3fe93630701b4659cdb4ac8605ce07d58b29c29ad868c1048c12209c`,
taken before and after each arm by the driver). The recourse judge is the findings
judge's own model in each arm — the same-model property jd3–jd6 carried, accepted and
disclosed.

## The population, and the rule for a missing cell

`data/cases/ftf-all.jsonl` (2,110 items), of which the 1,644 debate cells that jd3-main
decided are re-judged; the rejudge stage skips the rest and the driver reports the count.

A cell can be lost at four stages and each is counted in its own row; none enters a
paired table. **(1) At rejudge** — the findings judgment truncated or unparseable after
the one format repair and the one `--retry-failed` re-attempt: the cell has no
before-state in that arm and leaves P1, P2, P3 and the M0 comparison for that arm; it is
the numerator of the feasibility rate; it is neither SOUND nor an empty list. **(2) At
contest** — challenger reply truncated or unparseable after repair and retry: a
before-state and an unknown contest status; not a decline; leaves P1's pairing and P2's
denominator. (The contest stage resumes on "a challenge exists": a cell whose challenge
was written and whose ruling call then failed stays unruled and is counted as (3).)
**(3) At ruling** — recourse judge truncated or malformed after repair and retry:
contested, no after-state; leaves P1's pairing and P2's denominator; never an uphold.
**(4) At grade / reader** — off the decision path; stays in P1–P3, leaves that table.
Losses are printed per stage and per arm by `records/derivations/findings-1.py` §(0) and
by `fd1-ALL-DONE.md`, reported as losses and never as a denominator adjustment. A retried
cell is a different draw (the challenger runs at 0.7; the judges at 0 are not
deterministic either). Rejudge losses are also reported by subset: a python800 list with
many purported flaws may truncate at 16,384 tokens, and if losses concentrate there the
arm's population is not the 1,644 and the M0 comparison says so.

## Feasibility (the user's rule, written before the pilot)

On the 60 decided debate cells of `data/cases/pilot-3.jsonl`, the weak findings judge's
parse rate = cells holding a `findings.json` from which a verdict derived (strict or
after the one repair; a truncation is a failure) ÷ cells attempted. **Below 85% — fewer
than 51 of 60 — F-weak is not run at scale**, its pilot list is reported as the arm's
result, and F-strong runs alone. At n = 60 the rule's resolution is about ±9 points (a
judge truly at 85% fails it roughly 4 times in 10); that is stated and not repaired.
Measured at the pilot: **weak 60/60** (57 strict, 3 after one repair), **strong 60/60**
(all strict). F-weak runs at scale.

## The endpoints

**States.** Before = `initially_correct` (the findings judge's derived verdict). After =
`final_correct` (absent ⇒ before). Contested = `challenge_raised`. Only verdict-moving
outcomes enter P1; a local contest that cannot move the verdict is ruled and graded and
counted under `changed_the_decision`.

**The recourse comparator is the existence-check arm.** "jd5-B" means
`jd5-recheck-real` (`records/experiments/judgment-debate-5/arm-real/`): M1's 896 real
objections re-ruled by Maverick under the ruling prompt WITH the existence check, giving
`fixed | wrong` 144/274 = 52.6% and `broken | right` 167/622 = 26.8% (recomputed from the
committed index by the derivation and asserted). jd3-M1's no-check numbers are not a
comparator anywhere in this campaign, because the findings ruling prompt carries the
same existence check.

**P1 — per arm, α = 0.05.** Exact two-sided McNemar on before/after correctness over the
cells with both states; fixed, broken, net, Wilson accuracies. Two denominators
reported: all contested-and-ruled cells, and cells with at least one well-formed contest
(`challenge_void_only` False), because a void-only objection cannot move a verdict by
construction.

**P2 — co-primary, F-weak only, one-sided α = 0.05.** Among F-weak's cells that (a) the
findings judge got RIGHT, (b) the challenger contested, and (c) reached a ruling, the
share whose final verdict is WRONG (`broken | right`) is LOWER than jd5-B's 167/622.
Fisher's exact test, one-sided, on the 2×2 [F-weak broken / kept ; 167 / 455], with
Wilson intervals on both rates and a Newcombe interval on the difference. jd5-B's 622
are data with their own sampling error, so a one-sample binomial against 26.8% is not
used. **This is an UNPAIRED comparison of two mechanisms on two populations**: jd5-B
contested M1's objections against M0's verdicts under the materiality prompt with
Maverick unpinned; F-weak contests findings against the findings judge's own verdicts
under the findings ruling prompt with Maverick pinned. What moved between them is the
contest object, the ruling prompt, the before-state and the routing, and P2 cannot
separate them. The paired 2×2 on the intersection (right under both before-states and
contested by both challengers) is DESCRIPTIVE, with its n.

**P3 — reported, not tested.** F-weak `fixed | wrong` with its Wilson interval beside
jd5-B's 52.6%.

**α policy.** The registered claim for F-weak is the conjunction P1 ∧ P2, each at 0.05;
a conjunction rejected only when both components reject holds its type-I error at ≤ 0.05
without correction, and no claim is made from either test alone. F-strong's P1 is a
separate family at its own α = 0.05 — a different judge answering a different question
("does finding-level recourse net positive under a strong judge") — never pooled with
F-weak's. There are three α's in this document and they are these three; everything
under *Recorded* carries intervals and no test.

## The four named outcomes, written before the table

P1 is POSITIVE (fixed > broken, p < 0.05), NEGATIVE (broken > fixed, p < 0.05) or NULL;
P2 HOLDS (one-sided p < 0.05) or is NOT SHOWN.

* **(A) P1 POSITIVE and P2 HOLDS.** Finding-level contest breaks fewer right decisions
  than verdict-level contest AND clears the base-rate bar: the first recourse arm in this
  experiment to net positive, by the hypothesised route.
* **(B) P2 HOLDS, P1 NULL or NEGATIVE.** Fewer right decisions broken and still not
  enough: `f/b` remains below `a/(1−a)`. Reported with `a`, `f`, `b`, `f/b`, `a*` beside
  jd5-B's row, as §3ac's identity and not as a failure of the mechanism; P1 NEGATIVE is
  stated as such within (B).
* **(C) P1 POSITIVE, P2 NOT SHOWN.** Recourse nets positive but not by the hypothesised
  route: the gain is on the fix side (P3), not the break side.
* **(D) P1 NULL or NEGATIVE, P2 NOT SHOWN.** No separation from verdict-level contest.

These four partition the (P1 sign × P2) space for F-weak. F-strong is reported in the
same vocabulary on P1 alone, its `broken | right` and `fixed | wrong` beside F-weak's as
DESCRIPTIVE (a different judge model, a different set of right decisions, no comparator
of its own). A pair of arms that land in different cells is reported as that pair; a P3
that falls while P2 holds is reported as the split it is. **Nothing is rounded to the
nearest named outcome.**

## Recorded, not tested

* Findings-judge accuracy against M0 (paired 2×2 on the transcripts both judged, McNemar
  p printed as DESCRIPTIVE beside M0's 1,211/1,644 = 73.7%). The difference contains
  Maverick's disagreement with itself on a re-draw of the same transcript at temperature
  0, the format, the derivation rule (FLAWED iff any FLAW) and a routing change (M0 was
  unpinned); no floor arm prices the re-draw, so none of the four is attributed. For
  F-strong the same table is a different-model comparison and says nothing about
  decomposition.
* Final accuracy after recourse against M0, per arm — ABLATION, same caveat.
* Per arm, `a`, `f`, `b`, `f/b`, `a* = f/(f+b)` beside jd5-B's row (§3ac): the derivation
  rule changes the base rate and hence P1's bar.
* `fixed | wrong` and `broken | right` split by before-verdict (SOUND / FLAWED) and by
  `findings_flaw_n` (0, 1, ≥ 2). **Breaking a right SOUND verdict takes one upheld
  contest; breaking a right FLAWED verdict takes every FLAW finding flipped**, and jd5-B
  has no such asymmetry, so P2 is read with this table beside it.
* Findings per list, empty-list rate, duplicate-passage and non-verbatim-passage rates,
  ellipsis-joined passages, preamble/trailing prose dropped, ruling-token normalisations.
* Contests per objection by kind; void rate and void-only objections; the mechanical
  phantom rate (`(stance == contests) != (parsed contests > 0)`, `parse_mode =
  mechanical`, NOT pooled with jd3–jd6's Haiku column); `challenge_seeks_reversal`.
* Validity by kind and by `label_basis` (never pooled across bases).
* Ruling-line mismatch from the findings reader, which is shown the contest lines — a
  LOWER bound on this arm and not comparable with the sweep's column; lead-ins stripped.
* `findings_added_n` and how many appended findings moved a verdict.
* Comprehension mean; losses per stage; provider mix (the pins must show 100%).

## Validity rules, and their edge clauses

The user's three rules (`debate_variants.md`): NOT A FLAW→FLAW valid iff the item is
flawed AND the finding is the annotated flaw (location-only subsets clamped); FLAW→NOT A
FLAW valid iff the finding is not the annotated flaw (always valid on sound items);
omission and contradiction graded against the record only. Clauses added before any
paid pilot: (a) on flawed items "a real flaw" is the annotated flaw, because that is all
the grader is shown — a NOT A FLAW→FLAW contest on a genuine but unannotated error is
INVALID by rule (validity on flawed items is a lower bound) while its mirror is VALID by
rule (an upper bound); rates are never pooled across `label_basis`; on `location_only`
(gpqa, 191 items) the grader judges by location alone; (b) a same-ruling
"contradiction", an unknown index or `k and k` is void at parse time; (c) an omission on
an empty list is VALID iff the quoted purported flaw is in the record, was raised by the
FLAWED-side debater, and — vacuously — no finding covers it; if the FLAWED side raised
nothing, the empty list is correct and the omission INVALID; (d) a contest that cannot
move the verdict is still a contest. Mechanical grades (no call, `parse_mode =
mechanical`): void ⇒ INVALID; `Should be: FLAW` on a sound item ⇒ INVALID; `Should be:
NOT A FLAW` on a sound item ⇒ VALID. Every contested cell is graded, sound items and
correct decisions included.

## What the smokes changed (and what they did not)

Three six-cell smokes, each on fresh cells (seeds 1, 2, 3; disjoint; one cell per
subset and per type), read by Fable and by an independent reviewer agent; nothing below
was paid for under the final prompts except smoke 3.

* **Smoke 1** (commit `ca3c3a8`, $0.21). Weak arm PASS WITH NOTES; strong arm FAIL on the
  contest path. Findings: the weak judge lists the same claim several times (lojban 4
  findings for 1 claim); 5/20 weak passages not verbatim; trailing meta-prose published;
  three of the strong arm's four contests void because the challenger put a finding's
  `Reason:` under `Record says:` — on gpqa-33 that void discarded a correct FLAW ruling
  and left the cell wrong. Revision R1–R9 (commit `2dd9a96`): `Record says` optional on a
  finding contest and matchable against the findings text; void lines printed annotated;
  phantom = no parsed contests; distinct-claim and verbatim-passage rules; published
  grounds trimmed to the findings; lead-in stripping and the omission two-step for the
  ruling; the grader's location test; the reader shown the lines.
* **Smoke 2** (commit `2dd9a96`, $0.17). Both arms PASS WITH NOTES. The strong arm had no
  void contest and exercised `NOT AN OMISSION`. The weak arm's three void contests failed
  on `Alice: "…" Alice: "…"` — a speaker prefix and several spans. **R10** (commit
  `65bf2be`): `Record says` goes through the house record-quote matcher jd3's gate used
  (`_record_quote_found`: strict, then each ≥15-char quoted span, then with a ≤60-char
  attribution stripped). A parser change, validated OFFLINE by re-parsing every stored
  smoke objection (`records/derivations/fd1-reparse-smokes.py`, `outputs/fd1-reparse-smokes.log`):
  0 void contests remain of 17, nothing well-formed became void, and the two cells the
  void rule had cost move to the right answer (2 fixed, 0 broken). **R11** (commit
  `2a95388`): published ruling grounds lose the lead-in; passages in the text's own
  notation with strict verbatim/ellipsis columns; one settled list; the ruling ends on
  the answer; no unalleged passage listed.
* **Smoke 3** (commit `2a95388`, $0.21; `outputs/fd1-smoke-3-read.md`). Weak PASS WITH
  NOTES, strong PASS: 12/12 lists, 21/21 passages verbatim under the strict test, no
  trailing prose published, reader mismatches 0/7. Four defects found and fixed in **R12**
  (commit `bae02a3`): an unfound OPTIONAL record quote no longer voids a finding contest
  (it is recorded as `record_unverified`); the objection the recourse judge and grader
  see, and the published objection, are the parsed contests re-rendered (one weak cell
  had published 9,142 characters of the challenger's private working after a stray
  `Argument:` heading); the judge repair's example line shows both rulings; the all-void
  header is worded from the flags. **R12g** (commit `3d36448`), after the pilot read: the
  ruling READER — an off-path instrument — is told it does not judge rightness and is
  shown each contest's kind and `Should be:` beside its line; validated by re-reading all
  66 pilot rulings (weak mismatch 17/44 → 1/36 excluding void-only rulings, $0.16), not
  by a smoke; void-only rulings leave the mismatch column; kind-mismatched lines counted.
  **Declined:** accepting a glued `Argument:` label to save the challenger's repair call
  (117 of 120 pilot objections needed one) — that is the parser leak rule `HANDOFF.md`
  §2.7 forbids loosening; the repair is paid for instead (~$16 per arm).
* **What the pilots are and are not.** They ran under commit `ed1f405`, before R12; their
  void and validity figures were re-derived offline under the final parser
  (`outputs/fd1-reparse-pilots.log`): of 18 stored voids 9 are given back (weak 13 → 7,
  strong 5 → 2), two weak verdicts move (one fixed, one broken). Their rulings were made on
  the raw objection text (R12b renders the parsed contests for the full run). They are a
  prompt check, not a comparator, and no pilot number is pooled with the full run's.

Prompt digests under which the arms run, pinned by
`tests/test_prompts.py::FROZEN_FD1_PROMPTS` (`test_the_findings_prompts_are_the_ones_smoke_3_ran`).
Three moved after smoke 3 and the note in `outputs/fd1-prompt-digests.md` (copied to
`logs/prompt-digests.md`) says which and why: the judge repair's example line (R12c,
reached only after a parse failure) and the reader's two (R12g, off-path, validated by
re-reading). Every pre-existing prompt constant is unmoved (`FROZEN_PROMPTS`,
`FROZEN_ARMS`, `FROZEN_JD6_PROMPTS` pass).

| constant | sha256 |
| `FLAW_DEFINITION_FINDINGS` | `65f5f0cb06e05f959e41ad656f49f744445b98250b71e320f7177aac8d0879b9` |
| `JUDGE_SYSTEM_FINDINGS` | `d0ca4e5acc7363ebc860895f9d8687399cc6443c97e220a5a6f8cb4ac584dde9` |
| `JUDGE_CLOSING_FINDINGS` | `ed52a192937c39d85315efedaab785ba1d47f71d6b04ca49b99fa3ea5f7c26e4` |
| `JUDGE_REPAIR_FINDINGS` | `38b768b77435f5ed8b9508ba67c710a5f62e8c95cf36990ee237e935d8ec87e7` |
| `CHALLENGER_SYSTEM_FINDINGS` | `96b33b9f6e0f3850c46fb7b72f98f2afba776c6ed83be7f2dcaefba4e0073692` |
| `CHALLENGER_USER_FINDINGS` | `40ffc1e94a8c524950c0bd39baac0b2f72080bce5ded65cee8c3e3dfec8e16d9` |
| `CHALLENGE_DECISION_INSTRUCTION_FINDINGS` | `33bd972af20db73cc4870100f653992da72556685ed309303a74b21c53be5f05` |
| `RECOURSE_JUDGE_SYSTEM_FINDINGS` | `1acf1201aecb5dfd63631ca56d1701f70f78c1b46c4d14136949482005a2fdf3` |
| `RECOURSE_JUDGE_USER_FINDINGS` | `8c8dd20b5e0b4f155ae1f0c0327b160a1630feec4cdf5a9fe0299002a2308722` |
| `RECOURSE_JUDGE_CLOSING_FINDINGS` | `c74ecf7b8639f91e5c4d25a93e08a0edf97bf23834bf73aee77d53870e4e9109` |
| `RECOURSE_JUDGE_REPAIR_FINDINGS` | `42191f875ca60f0fbd6ec4649e787aec00f6ff26ff638fec6a29d9b6525100db` |
| `RULING_AGREEMENT_SYSTEM_FINDINGS` | `b9789bc8a0f518eb0e8a29054b0a12fc240456985f393aaaa8541b041df1d4cd` |
| `RULING_AGREEMENT_USER_FINDINGS` | `413d41ca61e3678a955c4e6ba4e9f90dfcb5033bc2197c2c0f0be7b28afd2e93` |
| `RULING_AGREEMENT_REPAIR_FINDINGS` | `ad28d291e97f3c025fd2a914a0c22eb90f39baa4468a1e01ff1a59d01ccbfea9` |
| `GRADER_SYSTEM_FINDINGS` | `9a21917749671d637fe9a819bad9cd38200163fbaa7cadd87e56e07b1c87cb55` |
| `GRADER_USER_FINDINGS` | `699294369c788fb7cf9757ad75ea2330062a71f15bde5453116c4b2e59bcc863` |
| `GRADER_FINDINGS_ANNOTATION` | `6090dbad7751b94ff0375bc9b5601be42b2d647b0eed10fd30d90f0b6745b4c0` |
| `GRADER_FINDINGS_SOUND` | `6247b3f1d09851e22cbc508623e4cb8ea568903f4365e544f98d75a5f8b83d40` |
| `GRADER_CLOSING_FINDINGS` | `680408a852b87d3b1596a08a136c52a641fc7cf5341339e1e13971da740370cb` |
| `GRADER_CLOSING_FINDINGS_LOCATION_ONLY` | `f13d042e553f7543b0b68f29960c7afe20961be08739e6a676fe65110360fcb6` |
| `GRADER_SKIPPED_FINDINGS` | `17ef44f6d4b9dd00de925fc8389cbac9e382397303c7d9769edf3b5871d2a513` |
| `GRADER_CLOSING_FINDINGS_UNNUMBERED` | `763cedfdf23b744f2fa29ea2d2b727cea1330a39645006c47c0875b68a2975ba` |
| `GRADER_REPAIR_FINDINGS` | `40779cff1a88f116073148f948a1720869d3ec77bd092b98c8e13b37d289e0a1` |
| `REPAIR_INSTRUCTIONS['judge_findings']` | `38b768b77435f5ed8b9508ba67c710a5f62e8c95cf36990ee237e935d8ec87e7` |
| `REPAIR_INSTRUCTIONS['recourse_judge_findings']` | `42191f875ca60f0fbd6ec4649e787aec00f6ff26ff638fec6a29d9b6525100db` |
| `REPAIR_INSTRUCTIONS['ruling_reader_findings']` | `ad28d291e97f3c025fd2a914a0c22eb90f39baa4468a1e01ff1a59d01ccbfea9` |
| `REPAIR_INSTRUCTIONS['findings_grader']` | `40779cff1a88f116073148f948a1720869d3ec77bd092b98c8e13b37d289e0a1` |
| `challenger-findings system message (rendered)` | `1d0c2db1a155f774f289b83c1770aae562a32637752ab4b49889fc8e9686183a` |

## The inherited record

`records/derivations/fd1-source-scan.py` over jd3-main's 1,644 transcripts (public
arguments only): a glued `Argument:` label inside an argument in **854 cells (51.9%)**,
scaffolding tags in 105 (6.4%), private-deliberation phrases in 4 python800 cells
(p02607, p02711, p03284, p03296). Nothing is excluded; both judges and the challenger
read these records as jd3–jd6's did, and the caveat is quantified rather than
anecdotal. One smoke cell, `theoremqa-solutions-quantum5-png-sound`, is labelled SOUND
and carries an internal inconsistency both judges called FLAWED — label reliability is
reported by `label_basis`, as before.

## The pilots and the instrument

**The pilots** (`data/cases/pilot-3.jsonl`, 60 decided debate cells each, commit `ed1f405`,
`outputs/fd1-pilot-read.md` for the 20-cell hand read; numbers re-derived under the final
parser where noted):

| | F-weak | F-strong |
|---|---|---|
| lists parsed | 60/60 (3 repairs) | 60/60 |
| findings per list | 1: 19, 2: 14, 3: 21, 4: 6 | 1: 34, 2: 18, 3: 6, 4: 1, 5: 1 |
| empty lists | 0 | 0 |
| findings-judge accuracy vs gold | **34/60** (M0 on the same cells: 44/60) | 44/60 (M0: 44/60) |
| verdict mix (M0: 30 FLAWED / 30 SOUND) | **46 SOUND / 14 FLAWED** | 40 FLAWED / 20 SOUND |
| contests raised | 44/60 — on right 22/34, on wrong 22/26 | 22/60 — on right 16/44, on wrong 6/16 |
| contests by kind | 58 finding, 2 omission, 0 contradiction | 22 finding, 4 omission, 0 contradiction |
| direction | 58/58 finding contests sought FLAW | 22/22 sought FLAW |
| void (final parser) | 7 of 60 | 2 of 26 |
| rulings | 44/44 strict; lines FLAW 43 / NOT A FLAW 16 / NOT AN OMISSION 1 | 22/22 strict; NOT A FLAW 18 / NOT AN OMISSION 5 / FLAW 3 |
| grant rate on live finding contests | 33/46 = 72% | 1/17 = 6% |
| fixed \| contested-wrong, broken \| contested-right | 15/22, 10/22 (net +5) | 1/6, 0/16 (net +1) |
| reader mismatch (final reader, ex void-only) | 1/36 | 1/19 |
| graded VALID (objection level; understated, see re-parse) | 16/44 | 6/22 |
| per-cell spend | $0.0182 | $0.0128 |

The hand read of 20 pilot cells (`outputs/fd1-pilot-read.md`): every weak-arm break is
an ARGUABLE contest on a gold-SOUND cell that Maverick ADOPTED ("the contest shows that…
could be seen as…"), 5/5; the designed object — a certain, local contest quoting the
finding's own `Reason:` against its ruling — fired once in 44 objections; luna SHOWS why
a contest fails on every kept ruling read. The derived rule moved the weak judge's base
rate the wrong way (46/60 SOUND), so on the pilot §3ac's condition is met only barely
(`f/b` 1.5 against `a/(1−a)` 1.31) and only because the before-state fell first. These
are the properties the arms measure, not defects; none was tuned away.

**The injection instrument** (`scripts/inject_findings.py`, `outputs/fd1-inject/report.md`,
$0.55; 20 pilot lists per arm with ≥ 2 findings, `k` drawn once per list and reused for
its control; the edit applied to the rendered list the challenger sees and re-derived;
the arm's own recourse judge on detected variants). INSTRUMENT rows, no floor:

| variant | arm | detected | restored (of detected) | paired false alarm | net |
|---|---|---|---|---|---|
| flip_k | weak | 12/20 = 60% [39, 78] | 11/11 | 9/20 = 45% | +3 |
| flip_k | strong | 18/20 = 90% [70, 97] | 13/17 | 2/20 = 10% | +16 |
| delete_k | weak | 6/20 = 30% [15, 52] | 3/5 | 1/20 | +5 |
| delete_k | strong | 12/20 = 60% [39, 78] | 3/12 | 1/20 | +11 |
| duplicate_k_opposite | weak | 20/20 | 11/20 | 0/20 | +20 |
| duplicate_k_opposite | strong | 17/20 = 85% | 14/17 | 0/20 | +17 |

Pooled flip detection 30/40 = 75% (above the 50% at which the plan would have gone back
to the user). Reading: the challenger detects a flipped ruling on luna's lists far better
than on Maverick's, and on Maverick's it contests the same finding on the UNALTERED list
45% of the time — the permissive challenger on weak findings again, which is what P2
prices. Restoration is high for flips, low for deletions (the judge often answers a real
omission with `NOT AN OMISSION` or a different ruling). Control-list behaviour: weak
16/20 objections raised, 1.62 contests each; strong 9/20, 1.11.

## The estimate

Per cell, measured at the pilots over all six stages (challenger repairs included):
F-weak $0.0182, F-strong $0.0128. Over 1,644 cells: **$29.9 and $21.0**; with 1.3×
headroom **$39 and $27**, about **$66 for both arms**. Calls per arm: 1,644 findings
judgments; 1,644 challenger calls plus one repair on nearly all of them and 1,644
comprehension probes; up to 1,644 rulings; up to 1,644 grades and 1,644 reader calls —
at most ~11,500 wire calls per arm. Spend to date $3.37 + the two arms ≈ $70 against
the $150 ceiling. Wall-clock: the weak pilot took 12 minutes for 60 cells at 16 in
flight; the arms are expected at 4–6 h together, F-weak first.

## Stop rules — catastrophic only

1. Provider failures above 25% of calls in a stage. 2. A stage crashing (non-zero exit),
as opposed to cells failing. 3. `STOP.md` appearing under either arm. 4. A hang: no cell
completing for an hour with the process alive. **Wall-clock alone is not a stop. There
is no mid-run threshold on any quantity in this document.** Arms run sequentially under
one driver, F-weak first.

## Launch

    nohup outputs/fd1-run-all.sh > outputs/fd1-run-all.log 2>&1 &
    echo $! > outputs/fd1-run-all.pid

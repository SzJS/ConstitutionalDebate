# fd1 smoke 1 — the read (2026-09-02)

Six cells (`data/cases/fd1-smoke.jsonl`, one per subset and per type), both arms, all six
stages. Trees `outputs/experiments/fd1-smoke-weak` and `fd1-smoke-strong`. Spend **$0.21**
($0.1312 weak, $0.0830 strong). Read by Fable (all six weak documents, the three contested
strong documents) and by an independent reviewer agent (all 24 documents, every JSON
artefact, every `calls.jsonl`). Prompts as of commit `ca3c3a8`.

## What ran
| | weak (Maverick) | strong (luna) |
|---|---|---|
| findings lists | 6/6 strict, 0 repairs, 0 normalised tokens | 6/6 strict, 0 repairs |
| findings per list | 2, 3, 4, 3, 3, 5 (mean 3.33) | 2, 2, 1, 4, 1, 3 (mean 2.17) |
| contests raised | 4 of 6 (7 contests: 5 finding, 1 omission, 1 contradiction; 0 void) | 4 of 6 (4 contests: 4 finding; **3 void**) |
| rulings | 4/4 strict | 3/3 strict |
| verdict moved | 2 (gpqa, surgery — both M0 errors, both FIXED per gold) | 0 |
| findings-judge accuracy vs gold | 3/6 (M0: 2/6 on these cells) | 4/6 |
| after recourse | 5/6 | 4/6 |
| ruling-line mismatch (reader) | 2/4 | 1/3 |
| challenger repairs | 6/6 salvaged_no_thinking (glued `Argument:`, inherited flash behaviour, as jd3–jd6) | 6/6 |
| leaks | none (no Thinking published, no gold above the Ground-truth section, 0 gold needles in any non-grader request) | none |

## Gate: lists parse and are faithful; contests quote real text; lines follow the prose; no leak
* **Weak: PASS WITH NOTES.** Every finding traces to a claim the FLAWED-side debater made;
  no invented finding. But the weak judge lists the SAME claim several times (lojban: 4
  findings, one claim; theoremqa: 5 findings for 3 claims; surgery and law: near-duplicate
  pairs), and 5 of 20 passages are not verbatim (lowercased first word; one ellipsis-joined
  composite; dropped backticks). One genuine omission (law: Bob's June-7-note argument).
* **Strong: FAIL on the contest path, PASS on the judge.** 13/13 passages verbatim, no
  duplicates, lists are exactly the FLAWED side's claims. But 3 of 4 contests were VOID
  because the challenger put the finding's own `Reason:` under `Record says:`; the
  mechanical check (record body only) voided them correctly by the rule as written, and
  the rule was wrong: on gpqa the challenger had correctly shown Finding 1's reasoning
  rested on a chemical impossibility, the ruling judge agreed and wrote `Contest 1: FLAW`,
  the code discarded it (void), the verdict stayed SOUND against gold FLAWED, and the
  published record printed `Contest 1: FLAW` above "0 are ruled FLAW" with no explanation.
  `phantom_contest` fired on both void-only objections, measuring the void rule rather
  than phantoms.

## Other findings
* Ruling prose: Maverick on the law omission said both "none of the findings directly
  address" and "the substance of the findings covers the issue", then wrote `NOT A FLAW`
  (a finding was appended, verdict unchanged). The reader's INCONSISTENT is right.
* Reader artefacts: 2 of the 3 mismatches were the reader defeated by a dangling lead-in
  line ("The final ruling for Contest 1 is:") or by wanting the literal words "the
  objection fails" where "does not establish a flaw" was written.
* Grader: 8/10 agreed by the reviewer. weak/surgery C2 graded INVALID by weighing the
  contest's rhetoric although the finding's passage IS the annotated flaw (rule (a) is
  a location test). strong/lojban C1 mechanically INVALID because void, would be VALID.
* Trailing meta-prose in weak lists ("Findings are done." and three paragraphs of
  self-commentary) was published verbatim in `<findings>`.
* Untested by this smoke: `Findings: none`, the FLAWED→FLAW tolerance, a `NOT AN
  OMISSION` / `NOT A CONTRADICTION` line, an omission ruled FLAW that moves a verdict, a
  conditional contest, truncation.

## The revision (R1–R9), all re-smoked on six FRESH cells before any pilot
R1 finding contests: `Text says:` is the required anchor; `Record says:` optional, and
when given must be in the record OR the findings text (omissions: record only).
R2 void contests: claimed verdict from ALL parsed contests; void lines printed annotated
"not applied"; phantom = contests with NO parsed entries; new `challenge_void_only`.
R3 judge: one finding per DISTINCT claim (repeats across rounds are one finding; "two
findings must not be answerable by one sentence"); passages verbatim, contiguous, no
ellipsis joins; report-only columns `findings_passage_exact_n`, `findings_duplicate_passage_n`.
R4 published grounds trimmed to the findings blocks (preamble/trailing prose counted, kept
in transcript_full.md).
R5 strip a trailing lead-in line before the reader; "Do not announce the lines — write them."
R6 omission two-step in the ruling prompt ("say first whether it is an omission").
R7 grader rule (a) stated as a pure location test.
R8 reader shown the contest lines; told that "the existing ruling stands" is definite.
R9 smoke-2 pick (seed 2, disjoint from smoke 1) and specs.

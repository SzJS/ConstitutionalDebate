# fd1 smoke 3 — the read (2026-09-02)

Six fresh cells (`data/cases/fd1-smoke-3.jsonl`, seed 3, disjoint from smokes 1–2), both
arms, all six stages, under commit `2a95388` (R1–R11). Spend **$0.21** ($0.1279 weak,
$0.0798 strong). Read by Fable (weak law and surgery documents, the strong void contest)
and by an independent reviewer agent (all 24 documents and every artefact).

## What ran
| | weak (Maverick) | strong (luna) |
|---|---|---|
| findings lists | 6/6 (1 repair: gpqa — first attempt wrote a list, revised it in prose, wrote a second list; the parser refused, the repair returned one clean finding) | 6/6 strict |
| findings per list | 1, 3, 1, 1, 1, 3 | 1, 3, 1, 1, 3, 2 |
| passages verbatim (strict) | 10/10 | 11/11 |
| trailing prose published | 0 (319 and 13 chars counted, not published) | 0 |
| contests raised | 5/6 (4 finding, 1 omission; 0 void) | 2/6 (1 finding — void on a paraphrased `Record says` —, 1 omission) |
| rulings | 5/5 strict; 4 finding contests ALL granted (`FLAW`); 1 `NOT AN OMISSION` | 2/2 strict; `NOT A FLAW`, `NOT AN OMISSION` |
| verdict moved | 4: lojban and medqa FIXED, law and surgery BROKEN (both gold SOUND) | 0 |
| findings-judge accuracy vs gold | 4/6 (M0 3/6) | 5/6 |
| after recourse | 4/6 | 5/6 |
| reader mismatches | 0/5 | 0/2 |
| leaks | none | none |

## Gate
**Weak PASS WITH NOTES; strong PASS.** Lists parse and are faithful (no invented or
unalleged findings; duplicates are distinct claims on one-sentence texts), contests quote
real text, ruling lines follow the prose (R11d 7/7, R6 2/2), no private text published
by fd1's own parsers — with one exception that is R12b below.

## Defects found (fixed in R12 before the full run; none affects the pilots' gate)
* R12a — strong/law: a finding contest with a real `Text says` was voided because its
  OPTIONAL `Record says` (two real quotes joined by "and", each prefixed `"Bob: `) failed
  the matcher; the ruling judge had found both. An unfound optional record quote is now a
  recorded flag, not a void.
* R12b — weak/lojban: flash wrote `Argument:` as a heading inside its deliberation, so
  the public section (9,142 chars of private working) was published and fed to the
  ruling judge. The objection the judge and grader see, and the published objection, are
  now the parsed contests re-rendered; the raw stays in transcript_full.md.
* R12c — the judge repair's example line read `Ruling: FLAW`; now `FLAW | NOT A FLAW`.
* R12d — the all-void header is worded from the flags.
* R12e — contest direction columns (`to_flaw_n`, `to_not_a_flaw_n`).

## Measured properties (the campaign quantifies these; not fixed)
* The certainty clause does not restrain flash on arguable cells: both gold-SOUND cells
  were contested with re-argued debate points ("circular", "no baseline"), not showings.
* The weak recourse judge ADOPTS: 3 of 4 granted finding contests restate the objection
  ("the objection correctly identifies…"); medqa is the exception and reads the text.
  Both luna rulings SHOW. jd6's mechanism, on a local object.
* Contest direction is one-way: 6/6 contests sought FLAW; none sought NOT A FLAW, even on
  the strong arm's one false positive. Recourse under this challenger can only fix false
  negatives and only break right SOUND verdicts — the verdict-side split in PREREG.
* The weak judge under-decomposes (1 finding vs luna's 3 on python800-p03137).
* Omission grade VALID and ruling NOT AN OMISSION can both be right (different questions).
* Validity has no location test on `final_answer` items with no `flaw_location`
  (weak/medqa: the contest fixed the cell and graded INVALID, by rule).

## Still untested after three smokes (first seen at the pilots)
`Findings: none`; the FLAWED/SOUND ruling tolerance; a contradiction contest and
`NOT A CONTRADICTION`; an omission ruled FLAW that appends a finding; truncation.

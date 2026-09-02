# fd1 prompt digests

sha256 of the UTF-8 bytes of every prompt the findings campaign `fd1` introduces, as
pinned by `FROZEN_FD1_PROMPTS` in `tests/test_prompts.py` and checked by
`test_the_findings_prompts_are_the_ones_smoke_3_ran`.

Every digest below is byte-identical to what fd1 smoke 3 (2026-09-02, commit 2a95388)
sent, EXCEPT THREE — see the two notes below. A change to any of them means a re-smoke
on six fresh cells and a rewrite of `records/experiments/findings-1/PREREG.md` before any
paid call, UNLESS the prompt is an off-path instrument, which the ruling reader is: it
touches no decision, and it is re-validated by RE-READING stored rulings rather than by
spending a new smoke.

**One digest moved after smoke 3 (R12c, 2026-09-02): `JUDGE_REPAIR_FINDINGS`**, and with
it `REPAIR_INSTRUCTIONS['judge_findings']`, which aliases it —
`99a242a3…` → `38b768b7…`. The repair's example line read `Ruling: FLAW`, which is a
VALID ruling line: a judge that answered the format repair by echoing the template back
would have produced a finding ruled FLAW that it never ruled, and under `derive_verdict`
one such finding is the whole verdict. It now reads `Ruling: FLAW | NOT A FLAW` — the
alternation the judge's own closing already shows — and `_FINDING_RULING_RE`'s
`(?!\s*\|)` lookahead refuses it, so an echoed template is a malformed list the harness
sees and fails rather than a silent FLAW. It is the only fd1 prompt text that moved; it
is reached only after a parse failure, so no smoke-3 call was made under either version.

**Two more moved after the PILOT read (R12g, 2026-09-02): the ruling reader's two,
`RULING_AGREEMENT_SYSTEM_FINDINGS` (`172c8351…` → `b9789bc8…`) and
`RULING_AGREEMENT_USER_FINDINGS` (`5e782bbb…` → `413d41ca…`).** The reader is an OFF-PATH
INSTRUMENT — nothing it says reaches a judge, a challenger or a grader, and no verdict,
grade or ruling moves with it — so its prompt may change and be validated by re-reading
rulings already on disk, which is what was done: all 66 stored pilot rulings were read
again with the new text (`records/derivations/fd1-reread-pilot-rulings.py`,
`outputs/fd1-reread-pilot/report.md`), and no pilot tree was written to.

Why they moved. `ruling_line_mismatch` fired on 17 of the weak pilot arm's 44 rulings, and
a hand read of five of those found the reader doing two things its prompt permitted and
its job forbids. (1) It marked INCONSISTENT when it DISAGREED ON THE MERITS with a ruling
whose prose does reach the answer its own reasons argue for — "reasonableness and
plausibility do not negate the flaw" is an argument about the passage, not about the
reasoning. (2) Once it misread what a ruling line means, saying so in its own words: "'the
finding stands' means the objection fails, but 'Contest 2: FLAW' suggests the objection
succeeds". The system prompt now says outright that the reader is not asked whether the
ruling is right, gives INCONSISTENT as a closed list of three shapes instead of a
description, and states that a `Contest k` line is the FINDING's ruling after the contest
and never a report on whether the objection succeeded; the user prompt SHOWS each
contest's kind and its `Should be:` beside its line, loaded from the sibling
`challenge.json`, so refusing a contest and granting one are visible facts. The two
readings coincide whenever a contest seeks FLAW — 58/58 of the weak arm's — and invert
when it seeks NOT A FLAW, which is why the weak pilot hid the second failure and the
strong one did not.

The table below goes into PREREG.md verbatim.

Three kinds of row, in the order the table lists them:

- 23 module constants in `src/exp2/prompts.py` (the ones matching
  `^[A-Z_]*FINDINGS[A-Z_]* = ` or `^FLAW_DEFINITION_FINDINGS`);
- the 4 `REPAIR_INSTRUCTIONS` entries `fd1` adds, pinned under their table key so the
  WIRING is frozen as well as the text (three of them alias a constant already pinned
  above, and the repeated digest is the point: a role re-pointed at another role's
  repair would be asked for a format its own parser refuses);
- the RENDERED system message of the findings challenger for the fixed dummy config
  (`make_config()` with `challenger_variant="findings"`, `judge_form="findings"`), i.e.
  the neutral clause splice, built with the same helpers `every_message_list` uses — the
  jd6 precedent for splices.

| constant | sha256 |
|---|---|
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

## The three pre-existing tables still pass

`uv run pytest -q tests/test_prompts.py` — 152 passed (147 at smoke 3, plus R12's three
and R12g's two). `FROZEN_PROMPTS` and
`FROZEN_ARMS` (both checked by `test_the_neutral_and_judgment_prompts_are_byte_identical_to_what_ran`)
and `FROZEN_JD6_PROMPTS` (checked by `test_the_contest_rounds_prompts_are_the_ones_the_smoke_ran`)
are unchanged and green; the fd1 table is additive and touches none of them.

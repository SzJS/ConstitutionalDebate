# fd1 pilots — the independent read (2026-09-02)

Two 60-cell pilots, `outputs/experiments/fd1-pilot-weak` (Maverick judge = recourse judge)
and `fd1-pilot-strong` (luna), challenger `google/gemini-2.5-flash` in both. Cells drawn
with `random.Random(11)` from the arms' `index.jsonl`; 20 unique cells read whole
(contest `transcript.md` + `ruling.json` + `ruling_agreement.json` + `grade.json`), plus
mechanical scans over all 120 documents.

**The pilots ran under commit `ed1f405` (15:26–15:40); the R12 fixes from the smoke-3 read
are in the working tree and were NOT in the pilots.** Several numbers below are stale for
that reason and are marked.

Draw:
* weak BROKEN (right→wrong): python800-p02982-sound, surgery-sur38, surgery-sur42,
  law-evi1, lojban-stim177_gpt3-5_B-s7
* weak FIXED (wrong→right): surgery-sur40, medqa-train_3754, lojban-stim144, law-con1,
  medqa-train_3221
* weak MISMATCH: theoremqa-maxku_ipnetwork8, lojban-stim145, law-con1 (also a fix),
  medqa-dev_0076, law-evi2
* strong: lojban-stim180 (the one change), law-con5 / gpqa-19 / surgery-sur20 /
  gpqa-164-sound (kept), gpqa-164-sound + medqa-train_2855 (the two mismatches)

---

## 1. BROKEN (weak, 5) — every one is an arguable contest ADOPTED

All five are gold SOUND, all five were contested toward FLAW, all five broke.
**Certain vs arguable: 0 certain, 5 arguable.** **Show vs adopt: 0 show, 5 adopt.**
On all five I read the passage as **not flawed** — I agree with gold and with the
findings judge's original ruling in every case.

| cell | the `Why` (the certainty clause was supposed to stop this) | the ruling's own words |
|---|---|---|
| law-evi1 | "By stating 'Hearsay is' a particular type of statement, the sentence makes a categorical claim that is legally inaccurate" — the passage is the textbook FRE 801(c) definition | "**Upon closer examination, the contest shows that** the definition's categorical claim is legally inaccurate" — after conceding "the standard for a flaw is not merely being incomplete… it is being false or misleading" |
| surgery-sur38 | "including an irrelevant finding implicitly suggests its relevance, which makes the sentence misleading" — the passage is a factual ECG report | "**The contest shows that** the inclusion of 'without evidence of ischemia' **could be seen as** implying relevance" |
| surgery-sur42 | "misleadingly presents 'increased blood pooling' as an equivalent indicator to 'active bleeding'" | "The sentence's phrasing **could be seen as potentially misleading**… **The contest raises a valid point that** the sentence **could** be misleading" |
| lojban-stim177 | "The ruling fails to address this escalation and overclaim" | "**The objection correctly identifies that** the finding fails to address this escalation" (one genuine textual sentence: s7 does say more than s6) |
| python800-p02982 | "The description of the code's actions is not a substitute for a proof of its correctness" | "the subsequent description, while accurate, does not constitute a proof of correctness" — a paraphrase of the `Why`, one clause engaging the defence |

Three of the five rulings turn on an explicit conditional ("could be seen as", "could be
misleading"), which the fd1 ruling prompt tells the judge is not a showing. This is jd6's
ADOPT mechanism reproduced on a local object, exactly as the smoke-3 read predicted.

## 2. FIXED (weak, 5) — 5/5 grade VALID; 1 certain contest, 4 arguable

| cell | contest grade | show / adopt | on the annotated flaw? |
|---|---|---|---|
| surgery-sur40 | arguable, well grounded | show-lite ("The phrase 'a less invasive approach' followed by 'such as percutaneous gallbladder drainage' implies that drainage is being considered as an alternative management strategy") | YES — loc 15, and the ruling's reason is the annotator's reason |
| medqa-train_3754 | arguable | ADOPT — three one-line "the passage bears out the claim" restatements | YES — 2 of 3 contests VALID; the fix is the wrong answer choice the annotator disputes |
| lojban-stim144 | **CERTAIN** — quotes the finding's own `Reason:` ("The claim is valid because the text invokes a non-existent rule") against its `Ruling: NOT A FLAW` | SHOW ("This phrase does invoke a non-existent rule, as Lojban's grammar is formally defined") | YES — loc 18 |
| law-con1 | arguable | ADOPT — concedes the defence, then "**Upon closer examination**… **can be seen as** misleading" | YES — loc 2 |
| medqa-train_3221 | arguable | adopt-leaning ("The contest shows that the acknowledgment of barriers… is a significant issue") | YES — matches annotator 2's cost/availability objection |

No fix was "right for another reason": all five graded VALID and all five land on the
annotated flaw (or, on the two `final_answer` items, on the reasoning the annotator
disputes). **The one certain-grade contest in the whole weak sample is lojban-stim144, and
it is the one made possible by the findings format itself** — it contests a finding whose
own stated reason contradicts its ruling. That is the mechanism the campaign is testing,
and it fired once in 44 objections.

Combined weak tally over the 10 read: **adopt 8 / show 2; arguable 9 / certain 1.**

## 3. MISMATCH (weak, 5) — the reader, not the parser; dominated by (c)

| cell | reader's `prose_conclusion` vs line | is the reader right? | category |
|---|---|---|---|
| theoremqa-ipnetwork8 | FLAWED vs SOUND | **No.** The prose does conclude FLAW; the reader read the reviewer's *recitation* of the finding ("The finding's ruling is NOT A FLAW because…") as its own conclusion. The SOUND side of the comparison is the *derived* verdict, which ignored the line because the contest was void | **(c)** + a mapping artefact (see §6) |
| lojban-stim145 | FLAWED vs SOUND | **No.** The ruling weighs and concludes "The finding stands"; the reader disagrees on the merits ("reasonableness and plausibility do not negate the flaw") — which its prompt forbids ("You are not judging whether the reviewer was right") | **(c)** |
| law-con1 | SOUND vs FLAWED | **Yes, substantively.** The prose concedes the defence and flips on "can be seen as misleading"; the reader names it: "a much weaker standard that contradicts its own acknowledgment" | **(b)** |
| medqa-dev_0076 | SOUND vs FLAWED | **Half.** Step 3 does state the conclusion, so the line follows; but the support is the conditional "could be misleading" the prompt bars | **(b)/(c) borderline** |
| law-evi2 | FLAWED vs SOUND | **No.** A clean SHOW ("The contest does not show that the sentence is mistaken… The finding stands"); the reader argues the opposite on the merits | **(c)** |

**Dominant category: (c), reader artefact — 3 clear, 1 borderline, 1 real (b).** Cause:
principally the **reader prompt** — `INCONSISTENT` ("it reaches a ruling that its own
reasons contradict") is reachable by plain disagreement with the reviewer, and by mistaking
a recitation of the finding for the reviewer's own view. Not the parser: `ruling.parse_mode`
is `strict` on all 66 rulings and `ruling_prose_empty` is False everywhere.

But the reader is not the *whole* cause, and the arm split proves it: 17/44 weak vs 2/22
strong on the same reader and the same prompt. Maverick's prose shape — recite the
finding, concede the defence, then reverse on a hedge — is what the reader keeps firing on.
Cross-tab over all 44 weak rulings: **9/32 mismatch where at least one line was FLAW,
8/12 where every line kept the finding.** So the flag is bidirectional and fires *hardest*
on rulings that refuse a contest, which is the merits-disagreement mode.

## 4. STRONG — luna shows, and its one change is right

* **Kept cells.** All four rulings SHOW.
  * law-con5: "the facts… do not establish that the expectation pre-existed those
    conversations… **Bob identifies a possible ambiguity, not a demonstrated factual
    error.** The finding stands." (gold SOUND — right)
  * surgery-sur20: routes the point to the other findings — "Findings 1 and 2 already
    address the substance of that concern… the objection does not show that Finding 3's
    specific ruling about conflation was mistaken." (gold SOUND — right)
  * gpqa-19: "The objection shows that the presentation is ambiguous and potentially
    misleading, **but ambiguity alone does not demonstrate an actual logical
    contradiction**." (verdict FLAWED kept — right)
  * gpqa-164-sound: "Showing that chromium with aluminoxanes can oligomerize ethylene
    separately does not establish that it can function alongside the polymerization
    catalyst." Reasoned, but **wrong**: the item is gold SOUND and luna's two FLAW
    findings are the false positive the challenger correctly attacked.
* **The one change (lojban-stim180): RIGHT.** Gold FLAWED, loc 6 = the contested passage,
  grade VALID, and the ruling does the work itself: "The Lojban sequence is `lanme li'u
  ni'o se lu fo'a`: `li'u` closes a quotation, while `lu` later opens one whose content is
  `fo'a`. Thus `lanme` is not quoted." That is the annotator's own point ("'li'u' should be
  'end of quotation'").
* **Its two mismatches.**
  * gpqa-164-sound — **new category, not (a)/(b)/(c): the reader misread the ruling-line
    convention.** In its own words: "the phrasing is ambiguous about what 'FLAW' means in
    the ruling line… 'the finding stands' means the objection fails, but 'Contest 2: FLAW'
    suggests the objection succeeds." The line is the *finding's* ruling, absolute; the
    reader's prompt tells it the reviewer decides "the claim identifies a real flaw, or it
    does not", i.e. it teaches the contest reading. The two readings coincide whenever a
    contest seeks FLAW — 58/58 of the weak arm's — and invert when it seeks NOT A FLAW.
    Both of the strong arm's two NOT-A-FLAW-seeking contests are in this cell.
  * medqa-train_2855 — category **(c)**: a clean SHOW ("ACD can nevertheless be microcytic,
    and an elevated RDW does not rule it out"), reader disagrees on the merits.

## 5. GRADES — 25 contests over the 20 cells; I disagree with 6

Agree: the 10 mechanical "the item is sound, so no finding can have missed a flaw"
(correct by the rule, including all five BROKEN cells); the 6 substantive VALIDs in §2;
lojban-stim180; gpqa-19 contest 1 INVALID (finding is about step 4, the annotated flaw is
step 5 — the location-only clamp applied exactly right) and contest 2 VALID.
medqa-3754 contest 3 INVALID ("warranted first" is not what the annotator disputes) is
defensible; I let it stand.

Disagreements (6):
1. **medqa-train_2855 (strong), contest 1 — should be VALID.** The grader adjudicated the
   contest's argument ("The objection conflates 'weakens reasoning' with 'is a flaw'")
   instead of applying the rule. Finding 3's passage IS the annotated flaw: the annotation
   says ACD "typically presents as normocytic" and the real answer is sideroblastic anemia,
   i.e. precisely the inference Finding 3 blessed. A `should_be: FLAW` contest on the
   annotated flaw is VALID by rule. **This is the grader importing merits into a rule.**
2–6. **Five contests graded INVALID as "void at parse time" by the pre-R12a parser**
   (theoremqa 1 — this one is a *true* void, see §6 — plus lojban-stim145 1,
   surgery-sur20 1, gpqa-164-sound 2). Four of the five are false voids that the current
   working tree would not produce. The two gpqa-164 ones matter most: they are the only
   contests in either pilot that sought NOT A FLAW, they were substantively right (the item
   is gold SOUND), and the rule makes a FLAW→NOT A FLAW contest on a sound item VALID by
   construction. The pilot's validity table therefore **understates** validity.

## 6. DEFECT vs MEASURED PROPERTY

**DEFECTS**

* **D1 — the challenger's glued `Argument:` label costs a repair call on 117 of 120
  objections (97.5%).** `challenge.parse_mode = salvaged_no_thinking` with
  `repair_attempts: 1` on 57/60 weak and 60/60 strong. The cause, verified in
  `calls.jsonl`: flash ends its Thinking block mid-line and writes
  `…focused on this single point.Argument:` — the label is not at line start, the parser
  raises `label_not_at_line_start`, and a second full flash call is spent that returns the
  same argument. Challenger calls are the campaign's largest line item; in the pilot they
  are **50% of all spend** ($0.58 of $1.09 weak, $0.46 of $0.85 strong). At 1,644 × 2 arms
  this is ~3,300 avoidable calls, ~$15–30, and ~9 s of latency each. No data is lost
  (everything before the label is private and is dropped either way), so this is a cost and
  robustness defect, not a correctness one.
* **D2 — the ruling reader is taught the wrong meaning of the ruling line** (§4,
  gpqa-164). `RULING_AGREEMENT_SYSTEM_FINDINGS` frames every line as a verdict on the
  *contest*; `apply_contest_lines` treats it as the *finding's* ruling. Invisible in the
  weak arm (100% of its contests sought FLAW) and it will not stay invisible at 1,644.
* **D3 — the pilots' void, grade and (marginally) ruling numbers predate R12a.** 13/60
  weak and 5/26 strong contests were void; **6 weak and 3 strong of those were void ONLY
  because a finding contest's optional `Record says:` missed the matcher**, which the
  working tree no longer voids. E.g. lojban-stim145's four record fragments are all
  verbatim in `parent/transcript.json`. Any pilot figure quoted in PREREG should be
  re-derived offline under the fixed parser first (R10 already did exactly this for the
  smokes).
* **D4 (small) — `ruling_line_mismatch` is uninterpretable on a void-only ruling.**
  `prose_conclusion` is mapped against the *derived* verdict, which by construction ignores
  the judge's lines when every contest is void; the reader is never told the contest was
  voided. theoremqa and gpqa-164 are both this shape. Exclude void-only rulings from the
  mismatch rate, or map against the line-implied verdict.
* **D5 (small) — a ruling line in the wrong vocabulary silently no-ops.** A *finding*
  contest answered `NOT AN OMISSION`: python800-p02982 contest 2 (weak) and gpqa-19
  contest 2 (strong) — 1/60 and 1/26 lines. `apply_contest_lines` documents this as
  "changes nothing", which is the safe direction, but nothing counts it, so a contest
  disposed of by a category error is indistinguishable from one never raised. Add
  `ruling_kind_mismatch_n`.

**NOT defects — checked and clean**

* No leak: over all 120 documents, no `Gold label` / `label_basis` / `Flaw location` /
  annotation text appears above `## Ground truth`; no `Reconsidered by` stray; the 54
  documents without `## The outcome` are exactly the 54 declined cells.
* No truncation: `finish_reason == stop` on all 120 decisions; `findings.parse_mode`
  strict 57 + `strict_after_repair` 3 (weak), strict 60 (strong) — **parse rate 60/60 in
  both arms, well over the 51/60 feasibility gate**.
* `ruling.parse_mode` strict 66/66 (1 repair, weak); `ruling_prose_empty` 0;
  `ruling_agreement` strict 66/66; `agreement` mechanical 120/120 as designed;
  `findings_ruling_normalised_n` 0 everywhere (the FLAWED/SOUND tolerance is still
  untested); 0 empty findings lists and 0 contradiction contests, so `Findings: none` and
  `NOT A CONTRADICTION` remain untested after the pilots too. The omission→appended-finding
  path DID fire once (weak, gpqa-127-flawed, on a cell that was fixed).
* theoremqa's void is a **true** void and a good one: the challenger's `Text says:`
  "P(no one sending) = 0.65^5" is nowhere in the solution, which is LaTeX
  (`P(\text{Collision}) = 1 - 0.65^5 - …`). The judge's own existence check *hallucinated*
  it ("found in Step 3 of the solution"); only the mechanical check stopped the break.
  That is the jd5 lesson holding, mechanically, where the LLM check failed.

**MEASURED PROPERTIES**

* Contest direction is one-way in the weak arm: **58/58 finding contests sought FLAW**
  (strong: 20/22). Recourse under this challenger can only fix false negatives and only
  break right SOUND verdicts.
* The weak findings judge is far more lenient than its own verdict form: `verdict` SOUND
  46/60 with 32 gold-flawed items, accuracy **34/60 vs 44/60 for the same model's stored
  jd3 verdict**. Recourse then nets +5 (39/60) — the decomposition costs 10 points before
  recourse buys 5 back. luna: 44/60 → 45/60.
* Weak decomposition is noisier: 36 of 134 findings share a passage with another finding
  (27%) vs 4/97 for luna; 5,591 chars of trailing prose counted (0 for luna).
* Comprehension 4.28 (weak) / 4.63 (strong).

---

## Tallies

| | weak | strong |
|---|---|---|
| contested / ruled | 44 / 44 | 22 / 22 |
| finding contests, by direction sought | 58 → FLAW, 0 → NOT A FLAW | 20 → FLAW, 2 → NOT A FLAW |
| omission / contradiction contests | 2 / 0 | 4 / 0 |
| void contests (of which pre-R12a artefacts) | 13 (6) | 5 (3) |
| ruling lines on LIVE contests | FLAW 33, NOT A FLAW 13, NOT AN OMISSION 1 | FLAW 1, NOT A FLAW 16, NOT AN OMISSION 4 |
| grant rate on live finding contests | **33/46 = 72%** | **1/17 = 6%** |
| fixed \| contested-wrong | 15/22 = 68% | 1/6 |
| broken \| contested-right | 10/22 = 45% | 0/16 |
| BROKEN sample: adopt / show | 5 / 0 | — |
| BROKEN sample: arguable / certain | 5 / 0 | — |
| FIXED sample: adopt / show | 3 / 2 | 0 / 1 |
| FIXED sample: arguable / certain | 4 / 1 | 1 / 0 |
| FIXED sample: grade VALID on the annotated flaw | 5/5 | 1/1 |
| mismatch | 17/44 | 2/22 |
| grade disagreements (my read) | 5 of 18 contests | 1 substantive + 2 void-driven of 7 |

## What the weak arm's 43:16 means

**Adoption, and the ratio is not really about the findings judge's NOT A FLAW rulings at
all.** Two facts settle it. First, direction: every one of the weak arm's 58 finding
contests asked for FLAW, so the ruling vocabulary is one-way by construction and the only
question the recourse judge ever answers is "grant or refuse". Second, the arm split: the
same challenger, writing contests of the same shape and the same direction, is granted by
Maverick on 33 of 46 live contests (72%) and by luna on 1 of 17 (6%). The findings
themselves are the same kind of object in both arms. So the 43:16 is the weak recourse
judge's grant rate, not a property of the findings, and the five broken cells show what a
grant is made of: the objection restated as the conclusion ("the contest shows…", "the
objection correctly identifies…"), three of the five turning on a "could be seen as" that
the prompt explicitly bars. The findings decomposition did produce the certain, local,
checkable contest it was designed for — lojban-stim144, where the finding's own `Reason`
contradicts its `Ruling` — but exactly once in 44 objections. Against that, the derived
rule also moved the base rate the wrong way: Maverick's findings verdict is SOUND on 46 of
60 items, so before recourse the weak arm is 34/60 where its own verdict form was 44/60,
and recourse's net +5 does not repay it. §3ac's condition (`f/b` must beat `a/(1−a)`) is
met on these 60 cells for the weak arm (15/10 = 1.5 vs 34/26 = 1.31) but only just, and
only because the before-state was degraded first — which is precisely the reading PREREG
already commits to reporting as ABLATION rather than as a win.

## Three changes before the 1,644-cell run

1. **DEFECT — accept a glued `Argument:` label in the challenger parser** (fall back to a
   non-line-start label when no line-start one exists; discard everything before it, as
   the repair does; count it as `challenge_glued_label_n`). It fires on 97.5% of
   objections, doubles the campaign's single largest cost line and adds ~3,300 calls and
   their latency to a 4–5 h run for nothing. Re-smoke is not needed: the accepted text is
   byte-identical to what the repair already returns.
2. **DEFECT — fix the ruling reader's account of the ruling line** (state that each line
   is the ruling the *finding* carries after the contest, and show the reader each
   contest's `Should be:` so it can tell a refusal from a grant). Then either exclude
   void-only rulings from `ruling_line_mismatch` or map `prose_conclusion` against the
   line-implied verdict (D4). Without this, the mismatch column inverts on every
   NOT-A-FLAW-seeking contest — invisible in these pilots only because there were two of
   them in 120 cells.
3. **DEFECT — re-derive the pilot gates offline under the current parser before PREREG
   quotes them** (R10's re-parse tooling already exists). 6 weak and 3 strong voids are
   pre-R12a artefacts; they suppress two correct, direction-reversing contests and five
   grade rows. If the pilot figures go into PREREG as measured, they should be the figures
   the full run's code would produce.

Runner-up, not in the three: count the kind-mismatched ruling line (D5) — 2 in 86 lines,
silent today.

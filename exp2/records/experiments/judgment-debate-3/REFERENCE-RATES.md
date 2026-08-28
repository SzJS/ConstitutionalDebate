# Reference rates — how often real appeal-like procedures overturn, and what "truth" they have

Compiled 2026-08-28 by a read-only research agent (WebSearch/WebFetch) at the planner's
request; filed by Fable unchanged in substance. **Context for §3y, not a comparison test**:
the experiment reports two conditional rates — the share of WRONG decisions a recourse step
overturns (fixed) and the share of RIGHT decisions it overturns (broken) — and those need
ground truth, which almost none of the sources below have. Every row says what stands in
for truth. `[verified]` = read from the primary source; `[unverified]` = search-result
summary only.

## 1. US federal courts of appeals — Administrative Office Table B-5 `[verified from PDF]`

"Percent reversed" = reversed / terminated on the merits (~60% of all terminations);
"affirmed" includes affirmed-in-part. FY2025 (12 months to 2025-09-30) and FY2014:

| category | FY2025 merits / reversed / % | FY2014 |
|---|---|---|
| total (excl. original proceedings) | 24,318 / 1,845 / **7.9%** | 34,114 / 2,497 / 7.2% |
| criminal | 6,962 / 521 / 7.5% | 8,085 / 527 / 6.5% |
| US prisoner petitions | 1,444 / 57 / 3.9% | 3,393 / 110 / 3.2% |
| other US civil | 1,363 / 155 / 11.4% | 1,380 / 201 / 14.6% |
| private prisoner petitions | 3,237 / 151 / 4.7% | 6,217 / 219 / 3.5% |
| other private civil | 5,602 / 647 / 11.5% | 6,186 / 737 / 11.9% |
| administrative agency | 2,454 / 152 / 6.2% | 3,514 / 265 / 7.5% |
| non-prisoner civil (summed) | 6,965 / 802 / 11.5% | 7,566 / 938 / 12.4% |

Ground truth: none — "reversed" is the appellate disposition; the population is losing
parties who chose to appeal. Sources: uscourts.gov Judicial Business Table B-5, FY2025
(`/sites/default/files/document/jb_b5_0930.2025.pdf`) and FY2014 (`B05Sep14.pdf`).

## 2. State appellate courts

- **BJS, *Criminal Appeals in State Courts* (2010 data; NCJ 248874, 2015)** `[verified]`:
  ~69,300 criminal appeals in 143 state appellate courts; 63% reviewed on the merits, of
  which 81% affirmed; 12% of all appeals had a component reversed/remanded/modified;
  intermediate courts' overall reversal rate **14%** of all appeals (state-initiated 38%,
  defendant-initiated 13%); courts of last resort 7%. ~2% of intermediate decisions were
  reviewed further. No ground truth. https://bjs.ojp.gov/content/pub/pdf/casc.pdf
- **Eisenberg & Miller, "Reversal, Dissent, and Variability in State Supreme Courts", 89
  B.U. L. Rev. 1451 (2009)** `[verified]`: 7,055 state supreme court opinions (2003);
  reversal **51.6%** under discretionary jurisdiction vs **28.1%** under mandatory
  (discretionary range 31–88% by state). No ground truth.
- **Eisenberg & Heise, "Plaintiphobia in State Courts?" (2008/2009) and "Redux" (12 J.
  Empirical Legal Stud. 100, 2015)** `[abstracts verified]`: civil trials on appeal
  (549 and 646 concluded appeals): plaintiff appeals reversed **21–22%**, defendant appeals
  **41%**; jury-trial appeals ~33%, bench ~25–28%. No ground truth; explained by selection
  and appellate attitudes.
- No single national NCSC figure for intermediate-court reversal was found `[flag]`.

## 3. Further review of appellate decisions

- **US Supreme Court reversal of the courts it reviews** `[verified]`: OT2007–OT2025
  cumulative 986/1,381 = **71.4%** reversed (per-term 63–82%); Ninth Circuit 79.5%
  (Ballotpedia, from SCOTUSblog end-of-term statistics). Certiorari is discretionary — the
  Court takes cases to reverse — so this is a selection artefact, not an error rate.
- **En banc**: rehearing en banc is ~0.14% of merits dispositions; no published share of
  en banc decisions reversing the panel was found `[flag]`.

## 4. Error correction with an external truth proxy

- **Garrett, "Judging Innocence", 108 Colum. L. Rev. 55 (2008)** `[abstract verified]`:
  DNA exonerees tracked through direct appeal and habeas *before* exoneration: a **14%**
  reversal rate, "indistinguishable from the background reversal rates of comparable rape
  and murder convictions"; innocence claims were rarely granted; errors often held
  harmless because of "overwhelming evidence of guilt". Later summary (Garrett 2017):
  about a third of the first 250 DNA exonerees raised innocence claims; they rarely
  succeeded. Ground truth: post-conviction DNA — the strongest proxy here, but the
  population is by construction the cases the system got wrong, so 14% is a detection
  rate on known-wrong decisions, not a false-positive rate.
- **National Registry of Exonerations, 1989–2012 report** `[verified]`: 873 exonerations;
  "no more than 1–2% of criminal convictions are reversed on ordinary direct appeals, and
  very few of the exonerations we know about occur in that process" — nearly all came
  through collateral review, dismissal on new evidence, or pardon. 2025 annual report:
  97 exonerations, 58% involving an innocence organisation or conviction-integrity unit.
- **Ramji-Nogales, Schoenholtz & Schrag, "Refugee Roulette", 60 Stan. L. Rev. 295 (2007)**
  `[verified]`: same-nationality asylum grant rates from 5% to 88% across judges in one
  court; courts-of-appeals remand of BIA denials from 1.9% (4th Cir.) to 36.1% (7th Cir.).
  No ground truth — inter-adjudicator disagreement on effectively random assignment.
- **FJC Second Circuit Sentencing Study (1974)** `[verified]`: 50 judges sentenced the same
  20 files; no unanimity on whether to incarcerate in 16 of 20. No ground truth.

## 5. Medicine — second opinions with partial ground truth

- **Van Such et al. (Mayo Clinic), J Eval Clin Pract 23:870 (2017)** `[press release
  verified]`: 286 referrals to general internal medicine; referral diagnosis confirmed
  **12%**, refined **66%**, completely changed **21%**. Truth = Mayo's final diagnosis; no
  independent follow-up validation.
- **Manion et al., Am J Surg Pathol 32:732 (2008)** `[abstract verified]`: 5,629 referred
  pathology cases; major disagreement **2.3%**, minor 9.0%; 1.2% changed management. Truth
  partial (clinical/pathologic follow-up on the major cases; the second reader is still
  the arbiter).
- **Rosenkrantz et al., J Am Coll Radiol 15:1222 (2018), meta-analysis** `[abstract
  verified]`: 12,676 secondary interpretations of outside imaging; discrepancy **32.2%**,
  major-finding 20.4%, management-changing 18.6%; where a reference standard existed the
  second reading was right **90.5%** of the time — the one row with a measured
  "second look is usually right" figure, on a tertiary-referral population.
- **Brady et al., Ulster Med J 81:3 (2012)** `[verified]`: real-time radiologist error
  ~3–5% (peer discrepancy); retrospective miss rates far higher.

## 6. Peer review reliability

- **Pier et al., PNAS 115:2952 (2018)** `[abstract verified]`: 43 reviewers, 25 funded NIH
  R01s: inter-rater ICC = 0 (95% CI 0–0.14). No ground truth.
- **Bornmann, Mutz & Daniel, PLoS ONE 5:e14331 (2010)** `[abstract verified]`: 48 studies,
  19,443 manuscripts: mean ICC .34, mean κ .17. No ground truth.

## What this table can and cannot say beside the experiment

Real appellate systems overturn 7–15% of the decisions brought to them (federal
intermediate; state intermediate criminal), 20–40% of civil trial appeals, ~50% under
discretionary review, and second medical opinions change a diagnosis in 2% (pathology)
to 21% (referral medicine) of cases. None of these has the experiment's ground truth,
and the one that comes closest (DNA exonerations) says ordinary appeal caught ~14% of
known-wrong convictions — about the same as it "caught" among convictions in general.
The experiment's fixed-wrong and broken-right rates therefore have no published
counterpart to be compared *against*; the table bounds what overturn rates look like in
procedures people accept, and shows that the diagnosticity question — does the appeal
find the wrong decisions more than the right ones — is not one those systems can answer
about themselves.

Not found: an en banc reversal share; a single NCSC national intermediate-court figure.
Not verified against source: Garrett's internal counts; the Eisenberg–Heise trial years;
the origin of Brady's 3–5%.

## 7. The nearest thing to our two rates — read against `RESEARCH-user.md` (the user's own research, filed beside this)

The experiment reports **fixed | wrong = 40.1%** and **broken | right = 20.6%** (M1, one
judge throughout). Nothing in either research file measures both, because nothing has
the label. What can be set beside them, with the mismatch stated:

| pair | figure | what it is, and what it is not |
|---|---|---|
| **fixed \| wrong** | **~14%** — Garrett 2008: ordinary appeal/habeas reversed 14% of convictions later proven wrong by DNA | the same quantity as ours, on a population that is wrong by construction; ordinary appeal, deferential standard of review; criminal only |
| **broken \| right** (proxy) | **~14%** — the same study's background reversal rate for comparable convictions, most of which were right | a reversal is not necessarily "breaking a right decision" — legal error ≠ factual error — so this is an upper-bound proxy at best |
| the pair, capital cases | Liebman 2000: 47% of capital convictions reversed on state direct appeal; of reversals, 82% got a lesser sentence and 9% an acquittal on retrial | reversal for *legal* error; the retrial outcomes say the reversals were mostly not "broken right decisions" in the legal sense, and say nothing about factual guilt |
| a gatekeeper | CCRC 1997–2017: referred **2.9%** of applications; **66–70%** of referrals succeeded | the closest real analogue to the leave-to-appeal ablations: a strict gate with high yield among admitted cases; our Haiku gate admitted 72% of objections |
| the base rate that decides the sign | Gross et al. 2014: ≥ 4.1% false convictions among death sentences; our M0 is 26% wrong | with a 4% error rate any review that overturns more than a few percent of right decisions is net negative, which is one reading of why appeal is deferential (7–15% reversal); at 26% wrong the same arithmetic still turns our +19.6-pt discrimination into a net of −18 |
| a second look on the same evidence | DWP PIP: 66% of appeals overturned; 91% of successful appeals won with no new written evidence | the "second look by a different decider" effect isolated by construction — the analogue of our placeholder arm, without a label |
| consistency floor | Kalven & Zeisel / Eisenberg 2005: judge and jury agree on ~78% of verdicts | a lower bound on someone being wrong; our two judges (nano, Maverick) agree on 63% |

Bottom line for §3y: the one comparable pair (Garrett) has ordinary appeal at roughly
**14% / ~14%** — no discrimination at all — against our **40% / 21%**. Our procedure
discriminates better than deferential appeal and still loses cells, because our base
rate of wrong decisions (26%) is far above the ~4% of the legal analogue and our
overturn rate on right decisions (21%) is far above appeal's (~7–15%). That is the
whole difference between "a mechanism that finds errors" and "a mechanism that improves
accuracy", and the legal system resolves it with deference and a gate.

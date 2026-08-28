# judgment-debate-3 — one judge throughout, 2026-08-28

`exp2/outputs/` is **git-ignored**. This directory is what was carried across from the
campaign: the **summary artifacts only**, so that every number quoted in
`../../../LLM_NOTES.md` §3y can be checked against a file rather than taken on trust. The
files are byte-for-byte copies of what the runs wrote under `outputs/`, except `README.md`,
`CHECKLIST.md`, `logs/stage-tails.md`, the four `HANDCHECK-*.md` files, the
`transcripts/*__README.md` headers and `arm-M3/NOT-RUN-YET.md`, which were written for this
directory. [`PREREG.md`](PREREG.md) was committed **before** M1's first paid call, and its M4
amendment before M4's.

Nothing here is an input to any stage. No code reads this directory; deleting it would break
no command. It is evidence, and it is about 11 MB.

**Read [`CHECKLIST.md`](CHECKLIST.md) first**, and its §0 before any other number.

> ## P3 IS NOT VOID — READ §1b BEFORE QUOTING THE SPECIOUS ARM
> M3 landed at 2026-08-28T19:45:06Z. `PREREG.md` voids P3 only if the grader validates *most*
> of the specious objections; it validated **479/1,641 = 29.2%**, so the condition was **not**
> met and P3 is reported **as measured**. The number that survives is the comparison split by
> the grader's verdict: **Maverick overturns 12.2% of the objections confirmed NOT real,
> against M1's 22.7%** — it does not simply fold — while one confirmed-unreal objection in
> eight still moved a decision. [`CHECKLIST.md`](CHECKLIST.md) **§1b** has that, the whole-arm
> comparison with its caveat, and a clearly-labelled **post-hoc** diagnosis of why about a
> third of the arm was real, resting on [`HANDCHECK-M3-specious.md`](HANDCHECK-M3-specious.md)
> and on the mechanism rather than on the 29.2% itself.

## Why this phase exists

The debate-only judgment-challenge run (`../judgment-debate/`) netted **+45, p = 0.011**,
with `gpt-4.1-nano` in both judge seats. The follow-up chain (`../judgment-debate-2/`)
re-ruled those same objections with two flash-class judges and got **+124** and **+114** —
and those two numbers are the problem, not the result. Both judges are **stronger than the
nano that judged the debates**, so "debate + recourse beats debate alone" could be nothing
more than "a better judge re-decided". The chain was stopped after its arm B
(`outputs/jd2-STOPPED-by-user.md`).

**The user's decision was to remove the asymmetry rather than model it.** The whole
debate-only design was re-run with **`meta-llama/llama-4-maverick` as the debate judge and as
the recourse judge** — index 14 with reasoning off, exactly the challenger's level, a fourth
model family, and the winner of the judge-selection rule written in
`../judgment-debate-2/PREREG.md` before any candidate was called. Nothing was re-debated: the
sweep's 1,644 stored transcripts were read from disk through `transcripts_from` and judged
again for one call each.

**With the asymmetry, +124. Without it, −18.**

## What ran

| arm | spec | what it is | window (UTC) | spend | result |
|---|---|---|---|---|---|
| **M0** | `jd3-main.toml`, stage `rejudge` | Maverick re-judges the sweep's 1,644 stored debate transcripts — the before-state | 11:43:59 → 12:37:31 | $2.01 | 1,644/1,644 decided, **0 truncated, 0 unparsed**; 73.7% vs nano's 58.2% |
| **M1** | `jd3-main.toml`, stages `contest agreement ruling_agreement grade analyse` | flash audits M0's judgments; Maverick rules on materiality — **the primary endpoint** | 12:37:31 → 14:43:04 | $30.65 | raised 896/1,644; **P1 = −18, p = 0.27** |
| **M2** | `jd3-placeholder.toml` | the placeholder objection on exactly the cells M1 contested — the second-look control | 14:43:50 → 15:37:17 | $3.11 | **P2 not separated**, −20, p = 0.21 |
| **M4** | `jd3-gatekeeper.toml` | `gpt-4.1-mini` rules on **admissibility only**; M1's rulings reused unchanged — **POST HOC** | 14:48:03 → 15:01:21 | $2.26 | 896/896 admissions; net −14, gate discrimination −1.8 pts |
| **M3** | `jd3-specious.toml` | the specious auditor on every decided cell — the sycophancy control | 15:37:17 → 19:45:06 | $51.72 | **not void**; 29.2% graded valid, so ~a third of it was real |

Total **$89.75**, plus the 60-cell instrument pilot **$1.1897** and the six-cell admissibility
smoke **$0.0151**. Every stage of every arm exited 0; **24,909 wire calls with one non-2xx** —
a `ConnectError: Temporary failure in name resolution` on one `jd3-main` challenger call
(`python800-p03632-flawed`), retried by the client and completed, so no cell was lost to it.
M3 cost **more than the whole rest of the campaign** because it contests every cell rather
than 54.5% of them and every one of those is graded. `logs/stage-tails.md` has every stage's own result line.

Nothing was re-debated and nothing was re-decided after M0. Both source trees were hashed at
three points (`outputs/jd3-fingerprints.md`) and are byte-identical throughout: `sweep`
`5e2eb4d6…` before the first arm and after the last, and `jd3-main` `dfa9bdca…` from the
moment M1 finished to the end of M3 — so M2, M3 and M4 all ruled against exactly the
decisions on disk.

## What was found

**The pre-registered endpoint is a null.** Recourse left accuracy statistically unchanged and
numerically lower: 110 cells fixed, 128 broken, net **−18**, exact two-sided McNemar
**p = 0.27045**, α = 0.05. The audit is *not* separable from a content-free second look
either (P2, p = 0.21) — but §1 of `CHECKLIST.md` says why that is two nulls rather than an
explanation: the placeholder moved 12 cells in all, against the audit's 238.

**And the audit is not the problem.** 1.9% misattributed quotations, one phantom in 896, 72.4%
of objections graded valid, a hand read agreeing with the grader 20/20, and a ruling-line
residual that fell from the previous run's 21.5%/30.4% to **1.2%/4.7%**. The instrument is
in better shape than it has ever been in this experiment.

**What produced the null is arithmetic.** Of the wrong decisions the audit contested it fixed
**40.1%**; of the right ones it contested it broke **20.6%** — a **+19.6-point** difference in
its favour, over the contested cells in both columns. But M0 is right 73.7% of the time, so the audit met 622 right decisions and 274
wrong ones. Nearly-twice-as-likely-to-help still loses at that base rate.
`REFERENCE-RATES.md` §7 puts the one comparable published pair beside it — Garrett's DNA
exonerees, where ordinary appeal reversed ~14% of known-wrong convictions against a ~14%
background rate, i.e. **no discrimination at all** — as context and never as a test.

**And on sycophancy, the first thing this experiment has been able to say.** Split by the
grader's verdict, so the comparison is against objections **confirmed not real**: Maverick
overturned **142/1,162 = 12.2%** of M3's unreal objections against **56/247 = 22.7%** of M1's
— it overturns *less* on objections that are not real, in both directions, so it is not
simply folding under pushback. But **one confirmed-unreal objection in eight still moved a
decision**, and the arm moved 239 decisions and cost the corpus 39 cells while carrying no
information by construction. Descriptive, not a pre-registered test.

**The whole-arm contrast (14.6% specious against 26.6% real, −12.0 pts) understates that
gap**, because about 29% of the "specious" arm's objections were real. Why: with `omission`
struck after the first smoke — it cannot be made false, a compressed judgment genuinely
leaving points unaddressed — the two surviving defect types left the challenger one move,
alleging that the judgment softened a party's position, and a 400-word judgment of a
three-round debate does that constantly. That diagnosis is **post hoc** and rests on
`HANDCHECK-M3-specious.md` (14 cells; the grader right on 6/6 valid and 4/4 invalid) and on
the mechanism, not on the 29.2% itself.

**And gatekeeping does not rescue it.** Three gates were recomputed post hoc (§5 of
`CHECKLIST.md`): a mechanical one that admits an objection only if every quotation in it is
verbatim (**−4**), M4's same-class model asked whether any alleged defect is real (**−14**),
and an upper bound that counts only what the Haiku grader called valid (**+2, p = 0.94**).
Two of the three admit objections to *right* decisions slightly **more** often than
objections to wrong ones.

## The four transcripts

Chosen to be read together, and every one of them named by a hand check.

| | cell | why |
|---|---|---|
| **fixed** | `medqa-dev_0463` | a plain misstatement of the record, caught and repaired |
| **broken** | `gpqa-120-sound` | the judgment hedged, the audit called the hedge a contradiction, the grader agreed, the label says the judgment was right |
| **valid objection, upheld** | `python800-p03288` | the materiality step working: real defect, immaterial, decision stands |
| **gate refusal** | `python800-p03959` | M4 refusing an objection that had **fixed** a wrong decision |

**The second and the fourth are the same argument** — "the judgment called something
incorrect and then concluded SOUND" — and the gate refused both. One was a break and one was
a fix. That is what a gate discrimination of −1.8 points looks like from the inside.

## Layout

    README.md                     this file
    CHECKLIST.md                  every table, with §0 first
    PREREG.md                     committed before M1; the M4 amendment before M4
    REFERENCE-RATES.md            appellate and second-opinion rates, with their sources
    RESEARCH-user.md              the user's own research, filed beside it
    derivation.log                records/derivations/judgment-debate-3.py over these indexes
    HANDCHECK-M0-judgments.md     20 Maverick judgments against their transcripts
    HANDCHECK-A-objections-and-grades.md   20 objection + grade pairs
    HANDCHECK-B-rulings.md        20 rulings, 12 of them instrument alarms
    HANDCHECK-C-fixed-and-broken.md        10 fixed + 10 broken, end to end
    HANDCHECK-M3-specious.md      14 specious cells; the grader right on 6/6 and 4/4
    logs/stage-tails.md           every stage's own result line, spend and failures
    arm-M0-M1/                    jd3-main: index.jsonl, metrics.json, cells.jsonl, experiment.json
    arm-M2/                       jd3-placeholder: index.jsonl, metrics.json, experiment.json
    arm-M4/                       jd3-gatekeeper: index.jsonl, metrics.json, experiment.json
    arm-M3/                       jd3-specious: index.jsonl, metrics.json, experiment.json
    gates/                        the mechanical gate's own file and log, and the 6-cell smoke
    transcripts/                  four records, each with a README saying what to look at

`cells.jsonl` is carried for `arm-M0-M1` only — it is the per-stage result ledger and it is
1.5 MB an arm; the other arms' stage results are in `logs/stage-tails.md` in full.

## How to re-derive every number

    cd exp2
    uv run python records/derivations/judgment-debate-3.py \
      --main        records/experiments/judgment-debate-3/arm-M0-M1/index.jsonl \
      --placeholder records/experiments/judgment-debate-3/arm-M2/index.jsonl \
      --gatekeeper  records/experiments/judgment-debate-3/arm-M4/index.jsonl \
      --specious    records/experiments/judgment-debate-3/arm-M3/index.jsonl \
      --gates       records/experiments/judgment-debate-3/gates/jd3-main-gates.jsonl \
      --jd1             records/experiments/judgment-debate/index.jsonl \
      --jd2-mav         records/experiments/judgment-debate-2/arm-maverick-real/index.jsonl \
      --jd2-mini        records/experiments/judgment-debate-2/arm-mini-real/index.jsonl \
      --jd2-placeholder records/experiments/judgment-debate-2/arm-nano-placeholder/index.jsonl

That is the command that produced [`derivation.log`](derivation.log), and the four prelude
flags are why `../judgment-debate-2/` now carries its three finished arms' indexes
(see its [`README.md`](../judgment-debate-2/README.md)).

Stdlib only, no network, no key, no run tree. The mechanical gate's own file is rebuilt from
a run tree with `records/derivations/jd3-gates.py`, which needs `outputs/experiments/jd3-main`
and is the one script here that does.

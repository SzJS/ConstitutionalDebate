# Stage tails — what each stage of the two arms reported, verbatim

Copied from the per-stage logs under `exp2/outputs/` (git-ignored). Every figure quoted in
`README.md`, `CHECKLIST.md` and `../../../LLM_NOTES.md` §3aa for spend, counts and failures
comes from here or from `arm-fabricated/index.jsonl` and `arm-real/index.jsonl`.

The driver is `scripts/run_sweep.sh` with `RUN_SWEEP_STAGES="rerule ruling_agreement analyse"`,
launched with `--retry-failed` (the user's standing resume rule of 2026-08-26,
`LLM_NOTES.md` §3r), wrapped in `outputs/jd5-run-both.sh` — a `for` loop over the two specs
that halts on a non-zero exit or a `STOP.md` and writes `outputs/jd5-ALL-DONE.md` only if both
finish. **`PREREG.md`'s one ordering rule was kept: the arms ran sequentially, in one process,
never overlapping** (`judgment-debate-3` broke that rule once with M4 over M2 and had to record
it). Per-arm orchestration logs are `outputs/jd5-jd5-recheck-{fabricated,real}-driver.log`.

    ########## jd5-recheck-fabricated  2026-08-28T23:43:00Z
    ########## jd5-recheck-fabricated exited 0  2026-08-29T00:26:46Z
    ########## jd5-recheck-real  2026-08-29T00:26:46Z
    ########## jd5-recheck-real exited 0  2026-08-29T01:12:13Z
    both arms done 2026-08-29T01:12:13Z

## Arm A — `jd5-recheck-fabricated`, 23:43:00Z → 00:26:46Z (43 m 46 s), every stage exit 0

| stage | exited (UTC) | result line | cumulative spend |
|---|---|---|---|
| `rerule` | 00:23:43Z | `rerule: completed=896` | $1.2893 |
| `ruling_agreement` | 00:26:44Z | `ruling_agreement: completed=896` | **$2.9305** |
| `analyse` | 00:26:46Z | `indexed 896 rows -> outputs/experiments/jd5-recheck-fabricated/index.jsonl` | — |

**No cell was lost.** `completed=896` on both paid stages, `failed=0`, no `STOP.md`, no
truncation. jd4 lost two rulings to truncation; this arm ruled all 896, so two cells that jd4
never put to a judge have a jd5 ruling and no jd4 one. They are outside the paired table of
`CHECKLIST.md` §0 and inside the column totals of §1 — which is why 894 and 896 both appear.

## Arm B — `jd5-recheck-real`, 00:26:46Z → 01:12:13Z (45 m 27 s), every stage exit 0

| stage | exited (UTC) | result line | cumulative spend |
|---|---|---|---|
| `rerule` | 01:09:44Z | `rerule: completed=896  skipped=1214` | $1.4091 |
| `ruling_agreement` | 01:12:10Z | `ruling_agreement: completed=896  skipped=1214` | **$3.3370** |
| `analyse` | 01:12:13Z | `indexed 1644 rows -> outputs/experiments/jd5-recheck-real/index.jsonl` | — |

**`skipped=1214` is the design, not a loss.** This arm's cases file is the whole corpus
(`data/cases/ftf-all.jsonl`, 2,110 items) because the `rerule` stage skips every cell with no
source objection; taking the population from an 896-cell file instead would silently drop M1's
declines from the denominator of the raise rate the index prints. 2,110 − 896 = 1,214, and the
skip reasons are `no objection to re-rule` and `no decision to rule against`. M1 lost one
ruling to truncation; this arm ruled all 896.

**Two arms, $6.2675, 1 h 29 m 13 s of wall clock**, against `PREREG.md`'s estimate of ≈$6.9
(≈$9.0 with headroom): **9% under the central estimate**. With the two six-cell smokes that
preceded them (**$0.0062** + **$0.0042**, 2026-08-28, `rerule` only), **judgment-debate-5 cost
$6.2779** — against `judgment-debate-4`'s $14.04 and `judgment-debate-3`'s $90.95, because
nothing is generated: 1,794 call records in each arm and not one challenger, debater, judge
or grader among them.

## Wire health, counted from each tree's own `calls.jsonl` (excluding copied `parent/` logs)

| | arm A | arm B |
|---|---|---|
| call records | 1,794 | 1,794 |
| HTTP 200 | **1,792** | **1,794** |
| non-2xx | **0** | **0** |
| transport failures retried by the client | **2** | 0 |
| parser repairs (a second `recourse_judge` call) | 0 | **2** |

Arm A's two transport failures were `ConnectError: Temporary failure in name resolution`, one
on `python800-p03292-flawed`'s `recourse_judge` call and one on `python800-p03796-flawed`'s
`ruling_reader` call; both succeeded on attempt 2 and neither cost a cell. Arm B's two repairs
were `recourse_judge` replies whose conclusion line the strict parser could not read
(`law-evi3_gpt3-5_A-s7`, `medqa-dev_0364`); one repair attempt is what every role gets and both
were repaired. **2 of 1,792 is the whole of it in each arm**, against jd4's 40 DNS failures and
891 challenger format repairs — a consequence of there being no challenger here at all.

Per role, per arm: `recourse_judge` **896** completed rulings (897 records in A, 898 in B),
`ruling_reader` **896** (897 records in A). No `challenger`, `comprehension`, `agreement`,
`judgment_grader`, debater or judge call was made by either arm — the objection, its grade, its
agreement reading and the decision it contests all came across with the copy.

| | arm A | arm B |
|---|---|---|
| `recourse_judge` spend | $1.2893 | $1.4091 |
| `ruling_reader` spend | $1.6413 | $1.9279 |
| `recourse_judge` latency (median / p95 / max) | 20.7 s / 39.7 s / 58.5 s | 22.0 s / 46.8 s / 70.3 s |
| `ruling_reader` latency (median / p95 / max) | 2.3 s / 6.8 s / 12.9 s | 2.3 s / 4.5 s / 8.4 s |

**The ruling reader costs more than the judge in both arms** ($1.64 against $1.29, $1.93
against $1.41). `anthropic/claude-haiku-4.5` reading 896 rulings is the more expensive half of
a re-rule, which is worth knowing before the next one is budgeted; `PREREG.md`'s estimate had
it at $0.00211 per cell against the ruling's $0.00207 and $0.00140, and that ordering held.

## A confound this campaign did not control, stated rather than smoothed over

**`meta-llama/llama-4-maverick` is not provider-pinned in any of these specs**, and the mix
that served it differs between an arm and the arm it is compared with:

| arm | DigitalOcean | Parasail | DeepInfra |
|---|---|---|---|
| jd4 (old prompt, fabricated) | 758 | 102 | 36 |
| **jd5 A (new prompt, fabricated)** | 730 | 127 | 39 |
| M1 in `jd3-main` (old prompt, real) | 524 | 68 | **304** |
| **jd5 B (new prompt, real)** | 680 | 175 | 43 |

Arm A's mix is close to jd4's. **Arm B's is not close to M1's** — 34% of M1's rulings were
served by DeepInfra against 4.8% of arm B's. Every spec in this campaign inherits
`provider_order` for the *debater* model only, and `HANDOFF.md` §6 forbids adding a fallback to
make a row pass but has never required a pin on the judge. So "the only thing that moves
between M1's rulings and arm B's is one paragraph of Step 1" is the intent and not a measured
fact: the serving stack moved too, and nothing here can say how much of arm B's +8.1 points
that is worth. It is named in `CHECKLIST.md` §7 and in `LLM_NOTES.md` §3aa's *does not show*,
and the mechanical-check arm should pin the judge's provider.

## Provenance — neither source tree moved, before or after

`find <tree> -type f | sort | xargs sha256sum | sha256sum`, the form every fingerprint in this
repo's records uses. `outputs/jd5-fingerprints-before.txt` (23:33Z, before the smoke) and
`outputs/jd5-fingerprints-after-smoke.txt` (23:34Z) hold the first two; the third column was
computed after both arms finished.

| tree | before | after the smoke | after both arms |
|---|---|---|---|
| `jd3-main` | `dfa9bdca…` | `dfa9bdca…` | **`dfa9bdca3fe93630701b4659cdb4ac8605ce07d58b29c29ad868c1048c12209c`** |
| `jd4-fabricated` | `6fe55bca…` | `6fe55bca…` | **`6fe55bcae2b67ccdf532fe0f0d63eeca31c5579e97fef784b203abfc5edb7f36`** |

Both are byte-identical to their values throughout `judgment-debate-3` and
`judgment-debate-4`, so these arms read M0's decisions and M1's and jd4's objections and wrote
nothing into either. **This is the before-and-after check jd4's own stage tails said a future
arm should take**, and it was taken.

The two trees this campaign wrote, hashed after `analyse` so the copies in `arm-fabricated/`
and `arm-real/` can be tied to them:

| tree | sha256 |
|---|---|
| `jd5-recheck-fabricated` | `101044656af0843647cdbdc5a09d606323e041ac8bbf22a1e1a9f5bbcb13f891` |
| `jd5-recheck-real` | `dbd15b92ac500253ff98f6cba045902b09d438aaac34362f4038aa465afa481b` |

## The prompt, and when it was committed

`RECOURSE_JUDGE_USER_JUDGMENT` at sha256
`e77eb5da04e21b64299c2fa09de427f108fc3e55f7368de2e58fbec0100cb7ca`, pinned in
`tests/test_prompts.py`, which also rebuilds the pre-2026-08-28 Step 1 and hashes it to
`a75860528ec0e429055d3305c703b1634151f38101fedc7a636f5b19acf4a74f` — the digest
`judgment-debate` through `judgment-debate-4` all sent. `RECOURSE_JUDGE_USER`, the neutral
arm's, is unchanged at `27fde5a3…`.

**Commit `8ec5384`, `2026-08-28 23:43:00 +0000`**, carries both the prompt change and
`PREREG.md`. `outputs/jd5-run-both.log` records arm A starting at `2026-08-28T23:43:00Z` — the
same minute — so the pre-registration was committed before the first paid call of either arm,
as it required. The six-cell smokes ran ten minutes earlier, at 23:33Z and 23:34Z, under the
same prompt text and before that commit; `PREREG.md` says in its second paragraph that they
precede it, are already spent, and carry no threshold. `git log` shows `PREREG.md` written once,
in that commit, and `src/exp2/prompts.py` unmodified since it.

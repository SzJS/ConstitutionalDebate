# partisan-pilots — the partisan challenger, tried on three clauses, NO-GO (2026-08-27)

`exp2/outputs/` is **git-ignored**. This directory is what was carried across from three
pilot runs that contested the sweep's own decisions with a **partisan** challenger instead
of the neutral one: the **summary artifacts only**, so that every number quoted in
`../../../LLM_NOTES.md` §3v can be checked against a file rather than taken on trust. The
files are byte-for-byte copies of what the runs wrote or of what the post-run comparison
wrote under `outputs/`; nothing here was edited in the copying. `CHECKLIST.md` and this
README are the only two files written for this directory.

Nothing here is an input to any stage. No code reads this directory; deleting it would
break no command. It is evidence, and it is small (≈1.6 MB).

**One directory, three trees.** The three runs are the same ablation under three wordings
of one standpoint paragraph, on the same 207 cells, so they share a README, a CHECKLIST and
one comparison log; each has its own subdirectory holding its own `metrics.json`,
`index.jsonl`, `cells.jsonl`, `experiment.json`, `DONE.md` and dry-run log.

**The result is a NO-GO.** None of the three clauses raised the genuine objection rate to
the plan's gate of 2× the neutral rate on the pooled 194 cells, so the full partisan run
(~$22, ~2 h) was **not started**. What was spent is the **$1.2234** of the three pilots.

## What was tried

`DESIGN.md` names the partisan variant as a planned ablation. The neutral decide-last
challenger objects on ~8% of cells, so every recourse-stage rate — the judge's
discrimination, the grader's valid-objection rate, the phantom rate — rests on tens of
cells per condition. The ablation was meant to raise n: assign the challenger the answer
the decision went against, ask it to argue the decision was mistaken, and let it still
report finding no grounds. Same decisions, same judge, same instruments, same grader; only
the challenger's standpoint differs.

The code is commit **`3e08df4`** ("the challenger gets a standpoint, and the record says
which one it had"). It adds four named arms, a config field `challenger_variant` (default
`"neutral"` — what every paid run before 2026-08-27 did), a validated `Challenge.arm`, a
`challenge_arm` column in `index.jsonl`, an `analysis.caveats()` entry that fires only on
partisan rows, and the four specs. `CHALLENGER_SYSTEM` gained one `{arm_clause}` slot and
nothing else changed: the flaw definition, "Either verdict can be wrong…", the
quote-the-record instruction, the length rule, the two-section format and the decide-last
`Decision: STANDS|REVERSE` line are shared across all four arms, so a difference measured
against the neutral arm is a difference of **standpoint** and of nothing else.

Because a new prompt was involved, the user's rule applied: try it on a small subset first,
read it by hand, and put an explicit go/no-go on the objection rate before anything runs at
scale. Three wordings were written rather than one, and all three were run.

## The three clauses, verbatim from `src/exp2/prompts.py`

`CHALLENGER_ARMS` maps four names to clauses. The neutral one is the paragraph every paid
run before 2026-08-27 used, quoted here as the baseline:

**`neutral`** — the historical clause, the design's primary measurement:

> You are not required to find fault. Many decisions are correct, and saying so when it is
> true is as useful as objecting when it is not. Object only if the record gives you
> grounds to.

**`partisan_advocate`** — the exp1-derived wording; represent the side, argue properly,
credibility is a cost:

> You represent the side this decision went against. You stand for the view that
> {contrary_phrase}, and your task is to argue that the decision was mistaken. Argue it
> properly rather than merely asserting it: say what the error is, quote the part of the
> record it lives in, and say why correcting it changes the decision rather than merely
> improving the reasoning. You are an advocate, not a neutral reviewer — but you are not
> obliged to manufacture a case. If the record genuinely supports the decision, say so and
> let it stand: an objection you cannot support costs the credibility you need for the ones
> you can.

**`partisan_assigned`** — the flatter assignment; search, then decline only on having
searched:

> You have been assigned the position that {contrary_phrase}. Search the record for the
> strongest support for that position — a false claim, an invalid inference, a flaw the
> decision missed, or a claimed flaw that is not one — and argue it, quoting the part of the
> record it lives in. Decline only if, having searched, you find nothing in the record that
> supports your position.

**`partisan_auditor`** — no side at all; a presumption that an objection exists:

> Your job is to find the best objection to this decision. Assume there is one until you
> have looked: check every claim in the grounds against the text under review and the
> problem, and check the text under review itself. Quote what you find. Let the decision
> stand only if every claim in the grounds holds up and you find no flaw the decision
> missed.

`{contrary_phrase}` is `side_phrase(complement(decision_verdict))` — a phrase, never the
FLAWED/SOUND token, so the clause names the side the decision went against without leaking
the vocabulary the challenger's own line is parsed against. `partisan_auditor` takes no
phrase and is formatted with the same call, which is why it is the one arm whose text is
identical whichever way the decision went.

## The neutral baseline, and why `--neutral-stances` exists

The fair baseline is **`rerule-recontest`** restricted to the same cells:
`records/experiments/rerule/recontest/index.jsonl`. It is the only index that carries
neutral objections **and** the corrected ruling line **and** the `ruling_agreement`
instrument, which is what the three partisan trees carry. The re-contest's original rulings
are not a fair comparison — they are under the `Ruling: UPHOLD|OVERTURN` collision §3u
fixed, and comparing a corrected ruler with an uncorrected one would attribute the ruler's
fix to the challenger's standpoint.

But `rerule-recontest` is a **re-rule tree**: it re-ruled the re-contest's objections, so it
carries challenge columns only for the **464 cells whose neutral challenger actually
objected**. Its other rows have no `challenge_stance` at all, and that absence means "this
cell's neutral challenge lives in the source tree", **not** "the neutral challenger
declined". Read naively, every decline in the baseline would vanish and the neutral raise
rate would read 100%.

`records/derivations/partisan-vs-neutral.py --neutral-stances` is the fix. It defaults to
`records/experiments/recontest/index.jsonl` — the re-contest's own index, committed — and
fills in the missing **stances** for the joined cells while keeping every **ruling-side**
column from the re-rule tree, so the corrected ruling line is still the one being compared.
Where both indices carry a stance it **asserts they agree** and dies if they do not.
`--no-stance-fill` turns it off; the decline columns then print "not in index".

On these 194 cells: **175 stances filled, 19 cross-checked, 0 still unknown**, and the join
asserts cell by cell that `verdict`, `initially_correct` and `gold_flawed` are identical in
all four columns — **194/194**. Whatever differs between the columns is the challenger's
and the judge's, and nothing else.

## The three runs

All three ran on 2026-08-27, sequentially, under
`RUN_SWEEP_STAGES="contest agreement ruling_agreement grade analyse"`, five stages, every
stage exit 0, `DONE.md` written. **No decision was made or re-made by any of them.**
`decisions_from = "outputs/experiments/sweep"` makes `decide` refuse and routes every
decision lookup into the finished sweep tree, which is read and never written.

| | `advocate/` | `assigned/` | `auditor/` |
|---|---|---|---|
| spec | `experiments/partisan-pilot-advocate.toml` | `experiments/partisan-pilot-assigned.toml` | `experiments/partisan-pilot-auditor.toml` |
| clause | `partisan_advocate` | `partisan_assigned` | `partisan_auditor` |
| cases | `data/cases/pilot-3.jsonl` (69 items, all seven subsets) | same | same |
| cells in the grid | 207 | 207 | 207 |
| cells with a decision to contest | **194** | **194** | **194** |
| started / finished (UTC) | 09:47:01 / 09:50:40 | 09:50:40 / 09:54:03 | 09:54:03 / 09:57:26 |
| wall clock | 3 min 39 s | 3 min 23 s | 3 min 23 s |
| **spend** | **$0.4345** | **$0.4026** | **$0.3863** |
| this tree's own wire calls | 1,809 attempts, **1,809 × HTTP 200** | 1,791, **1,791 × 200** | 1,793, **1,793 × 200** |
| **non-200 responses** | **0** | **0** | **0** |
| challenger format repairs | **23** (`no_public_label`) | **22** | **31** |
| repairs in any other stage | 0 | 0 | 0 |
| cells failed in any stage | 0 | 0 | 0 |
| genuine objections raised | **27/194 = 13.9%** | **21/194 = 10.8%** | **19/194 = 9.8%** |

**$1.2234 for the three.** The 13 cells of the 207 that carry no decision were lost to
truncation in the sweep and are skipped here with `no decision to contest`, exactly as the
re-contest's validation slice skipped them.

Every repair is a challenger reply with no `Argument:` label, repaired once and then parsed;
the rate is 23/217, 22/216 and 31/225 challenger calls (10.6%, 10.2%, 13.8%), which is the
same shape §3m measured and is **higher than the neutral arm's** — an advocate writes longer
and drifts out of the format more often. Nothing was lost to it: all 194 cells in all three
trees carry a challenge, **0** stances came back unparsed, and **0** lines were
contradictory.

**The sweep tree's fingerprint is unchanged by these runs.**
`find outputs/experiments/sweep -type f | sort | xargs sha256sum | sha256sum` reads
`5e2eb4d69ecabcce77533fd84a75e6d8d7c6a7676a00b05701737229bdfd2d2f`, which is what
`outputs/sweep-tree.sha256` recorded before them. Each `experiment.json` here also records
the sweep's own `experiment.json` sha256, `683a55c9…`, which is how a tree says which
decisions it read.

## The NO-GO, and the rule it was decided by

The plan's step-6 rule, written before the runs:

> GO with the clause that has the highest *genuine* raise rate subject to (i) phantom share
> ≤ the neutral run's 13%, (ii) at least some declines on correct decisions (a 0% decline
> rate means "let it stand" is dead), (iii) parse failures ≈ 0. If **no** clause raises the
> genuine objection rate clearly above neutral's (at least 2× on the pooled 194), NO-GO:
> stop, record the three results in LLM_NOTES, and report to the user — do not run the full
> sweep.

Neutral on these 194 cells raises **19 genuine, 9.8%**. The gate is therefore **≥ 19.6%**.

| clause | genuine raise | × neutral | ≥ 2×? | phantom share | declines on CORRECT | unclear + contradictory |
|---|---|---|---|---|---|---|
| `partisan_advocate` | **27/194 = 13.9%** | 1.42× | **FAIL** | 1/28 = 3.6% PASS | 128/146 = 87.7% PASS | 0 + 0 PASS |
| `partisan_assigned` | **21/194 = 10.8%** | 1.11× | **FAIL** | 0/21 = 0.0% PASS | 129/146 = 88.4% PASS | 0 + 0 PASS |
| `partisan_auditor` | **19/194 = 9.8%** | 1.00× | **FAIL** | 0/19 = 0.0% PASS | 131/146 = 89.7% PASS | 0 + 0 PASS |

Three of the four criteria pass in every clause. The one that fails is the one the ablation
existed for. **Fable decided NO-GO on 2026-08-27**; `experiments/partisan.toml` was never
filled in and never run — `experiment_cli` refuses any spec whose name contains `partisan`
and states no variant, on a dry run and on a real one alike — and no `"partisan"` alias was
ever assigned to a clause.

## What this settles — read `CHECKLIST.md`

[`CHECKLIST.md`](CHECKLIST.md) carries the (a), (b), (c), (g) and (h) tables and the reading
of the declines. In one sentence: **the standpoint instruction does not move
`gpt-4.1-nano`.** A challenger that reasons before committing, over a record that already
contains both sides and a verdict, sides with the verdict regardless of which side it is
told to represent. The low objection rate is a property of the **challenger model reading
these records**, not of the neutral instruction — so the ablation cannot raise n with this
model, and the recourse numbers stay at the neutral n.

## What is here

| path | what it is |
|---|---|
| `CHECKLIST.md` | the four tables, the go/no-go block verbatim, and what the pilots settle |
| `partisan-vs-neutral.log` | the three clauses and the neutral baseline side by side, from `../../derivations/partisan-vs-neutral.py`. Copy of `outputs/partisan-vs-neutral-pilots.log` |
| `<clause>/metrics.json` | the funnel, the rates, the caveats block — including the partisan caveat — as `analyse` wrote it |
| `<clause>/index.jsonl` | one row per decided cell, with the new `challenge_arm` column beside the stance, prose, ruling and grade columns |
| `<clause>/cells.jsonl` | one row per cell per stage (`contest`, `agreement`, `ruling_agreement`, `grade`): status, error string, timing |
| `<clause>/experiment.json` | the spec each run actually ran with, `challenger_variant` included, and the sweep's `experiment.json` sha256 |
| `<clause>/DONE.md` | what the driver wrote when the fifth stage exited 0 |
| `<clause>/dryrun.log` | the hyperparameter table shown to the user before each paid run, with `challenger_variant` and its WHY at line 40 |

**Reproducible on a bare clone.** `partisan-vs-neutral.py` reads `index.jsonl` files and
nothing else — no run tree, no `calls.jsonl`, no network, no API key:

```bash
uv run python records/derivations/partisan-vs-neutral.py \
    --partisan records/experiments/partisan-pilots/advocate/index.jsonl \
               records/experiments/partisan-pilots/assigned/index.jsonl \
               records/experiments/partisan-pilots/auditor/index.jsonl
```

That reproduces `partisan-vs-neutral.log` **byte for byte** except for the three
`--partisan` paths printed in the header and the JOIN block, which name
`outputs/experiments/…` in the copy here because that is where the indices were when the
comparison was first run.

## What is deliberately not here

`calls.jsonl` (1,809 + 1,791 + 1,793 of these trees' own attempts, plus the copied parents'),
the per-cell `cells/` run directories with their `challenge.json`, `ruling.json`,
`agreement.json` and the full copy of the sweep decision each contest carries, and both
published documents per cell. A reader wanting to re-derive a number from raw generations
has to re-run the stage; at $1.22 and eleven minutes that is affordable, and it needs the
sweep tree on disk.

## The comparability rule from `../../README.md` applies here

The three pilots **are** comparable with each other and with the neutral baseline on these
194 cells: same items, same decisions, same judge, same instruments, same grader, one
paragraph swapped. That is the whole point of them, and the join asserts it cell by cell.

They are **not** comparable with any full run. 194 cells is not a sample of the sweep's
5,724 — `data/cases/pilot-3.jsonl` was drawn to exercise all seven subsets, not to be
representative — and every rate here has an n in the tens. Nothing in this directory
supports a statement about the experiment's headline numbers; it supports one statement
about a prompt.

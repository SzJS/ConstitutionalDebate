# HANDOFF — everything needed to run exp2's first full sweep

Written 2026-08-25 for an agent who has not seen this project, on a machine where
nothing but this git repository exists. It assumes **no memory, no earlier
conversation, and no `/root/.claude`**. The plan file that used to carry this state
(`/root/.claude/plans/eager-exploring-island.md`) is gone with the pod it lived on;
this file replaces it.

`outputs/`, `data/`, `.venv` and the repo-root `.env` are git-ignored and were wiped
with that pod. Section 3 rebuilds them. The small summary artifacts behind every number
quoted here were copied into [`records/`](records/README.md) first, so the numbers stay
checkable.

> **THE SWEEP HAS BEEN RUN. DO NOT RE-RUN IT.**
>
> The first full sweep **ran and completed on 2026-08-26**: 17 h 16 m, **$32.13**,
> **5,724 of 6,330 cells decided (90.4%)**, all five stages exit 0.
> [`records/experiments/sweep/DONE.md`](records/experiments/sweep/DONE.md) is the proof,
> and it is in git.
>
> Its evidence is [`records/experiments/sweep/`](records/experiments/sweep/README.md) —
> read [`CHECKLIST.md`](records/experiments/sweep/CHECKLIST.md) **first**, then
> `metrics.json`, then `index.jsonl`. The headline result is that checklist's
> **"THE PHANTOM-CORRECTED FUNNEL"** section; reproduce it from the committed index with
> `uv run python records/derivations/sweep-phantom-corrected.py`. The write-up is
> [`LLM_NOTES.md`](LLM_NOTES.md) **§3s**, and §4 below summarises it in a paragraph.
>
> **Section 5 is kept as the record of how that run was run, and as the procedure for any
> future sweep the user opens — but the run it describes is done.** Do not execute it
> because it is written in the imperative. Running it again costs $32 and re-decides
> cells that are already decided.
>
> **The re-contest also ran, on 2026-08-26 22:14–23:38Z**: the same 5,724 decisions
> contested again with the challenger deciding last and a weak third-party recourse judge
> in every condition, **$10.89**, four stages, nothing regenerated — evidence in
> [`records/experiments/recontest/`](records/experiments/recontest/README.md), write-up in
> `LLM_NOTES.md` **§3t**, and §4 below.
>
> **Before quoting any recourse-stage number from EITHER run — overturn rates, `revised_*`,
> net accuracy — read `LLM_NOTES.md` §3t(d) and
> [`records/experiments/recontest/HANDCHECK-ruling-line.md`](records/experiments/recontest/HANDCHECK-ruling-line.md):**
> a hand check found the recourse judge's `Ruling:` line contradicting its own reasoning in
> 8 of 12 sampled rulings on a FLAWED parent verdict (0 of 8 on SOUND), which puts the
> re-contest's 464 rulings and the sweep's 440 `debate` rulings under the same caveat and
> leaves the sweep's `restated_verdict` rulings untouched. The next step is a prompt fix
> plus a re-rule of those 904 rulings for cents — smoke first, and it is the user's call.
>
> **That fix was made and every objection re-ruled on 2026-08-27** — the judge now states
> its own conclusion about the text under review instead of an `UPHOLD|OVERTURN` word, all
> 464 + 1,129 rulings were re-made for **$3.09**, and a new `ruling_agreement` stage puts a
> **measured ~6% residual** where an unmeasured failure used to be; evidence in
> [`records/experiments/rerule/`](records/experiments/rerule/README.md), write-up
> `LLM_NOTES.md` **§3u**, and §4 below.
>
> **THE DEBATE-ONLY JUDGMENT-CHALLENGE RUN IS DONE — 2026-08-28. DO NOT RE-RUN IT.**
> The sweep's **1,644 decided `debate` cells** were audited and re-ruled: 01:48–03:18Z,
> **1 h 30 m**, **$33.9371**, **9,982 wire calls with 0 non-2xx**, five stages exit 0,
> 1,643 of 1,644 contested. Nothing was decided and nothing regenerated; the sweep tree is
> byte-identical (`5e2eb4d6…`). The **pre-registered endpoint is positive and
> significant** — 173 fixed, 128 broken, **net +45, exact two-sided McNemar p = 0.0111**.
> Evidence:
> [`records/experiments/judgment-debate/`](records/experiments/judgment-debate/README.md) —
> read [`CHECKLIST.md`](records/experiments/judgment-debate/CHECKLIST.md) **§0 first**;
> write-up `LLM_NOTES.md` **§3x**; pre-registration
> [`PREREG.md`](records/experiments/judgment-debate/PREREG.md), committed before the run.
>
> **§0 is not optional.** `ruling_line_mismatch` fired on **30.4% of the rulings**,
> concentrated on **FLAWED parents (50.8% against 8.2%)** — the same shape the OLD ruling
> line failed in — and a **post-hoc** sensitivity that takes the reader's reading of each
> ruling's prose over the ruling's own line turns **+45 into −32**. That sensitivity is
> section (f) of the derivation, it is **not pre-registered**, and it is only as good as a
> Haiku reader. Do not quote the endpoint without it.
>
> **The partisan-challenger ablation was tried on three clauses on the 207-cell slice on
> 2026-08-27 and is a NO-GO** — none reached the pre-written gate of 2× the neutral genuine
> objection rate, so the ~$22 full run was never started; evidence in
> [`records/experiments/partisan-pilots/`](records/experiments/partisan-pilots/README.md),
> write-up `LLM_NOTES.md` **§3v**.

---

## 1. What this is, in five lines

The design is [`DESIGN.md`](DESIGN.md) and it is the user's document — read it before
anything else here; this file never restates it and never speaks for it.

The question it asks: **can a weak stakeholder detect, contest and correct a bad AI
decision more effectively when that decision was produced by debate?** The decision task
is yes/no — given a problem and one proposed solution, does the solution contain a flaw?
Three conditions decide the same items: `single`, `self_critique`, and `debate` judged by
a weak model. Each decision is then contested by a weak challenger that may decline, and
the funnel `error → detection → valid objection → revision` is measured per condition.

Models, settled and not to be changed (see section 6): strong debaters and solo agent
**`deepseek/deepseek-v4-flash-0731`**, pinned to the GMICloud endpoint; weak judge and
challenger **`openai/gpt-4.1-nano`**; grader and the `agreement` stage
**`anthropic/claude-haiku-4.5`**. Corpus: FindTheFlaws, **2,110 items over seven
subsets**.

---

## 2. Ground rules that bind every agent working here

Read [`../CLAUDE.md`](../CLAUDE.md) (parallelism, saving every output, testing each step,
confirming hyperparameters, choosing models) and [`CLAUDE.md`](CLAUDE.md) (run every
command from `exp2/`). These are the rules that are *not* written down anywhere else:

1. **`DESIGN.md` is the user's and is never edited** — not to fix a stale passage, not
   to record a settled decision. Findings, measurements and departures go in
   [`LLM_NOTES.md`](LLM_NOTES.md), which opens by saying that where the two disagree,
   `DESIGN.md` wins. Suggest edits to the user in conversation instead; several such
   suggestions are already parked in `LLM_NOTES.md` §3k and §3l, unapplied.
2. **The user settles design questions by editing `DESIGN.md`, not by replying.** Ask a
   numbered questionnaire with a proposed default per item; expect "check the diff".
   Read `git diff -- exp2/DESIGN.md` to collect the answers. A question pasted back with
   its "?" still attached means unanswered.
3. **Fable plans, Opus executes** — root `CLAUDE.md`, "Have Opus do the implementation":
   the user plans with Fable and every plan spawns an Opus subagent to execute it. If you
   are the Opus executor, do not re-plan or extend the plan you were handed; if you are
   Fable, do the reading and the checking yourself, and hand the coding and the runs to
   Opus. Fable also reviews Opus's deliverables — this file was checked by Fable
   against the repo after Opus wrote it.
4. **Every hyperparameter is printed and confirmed before a paid run.** `--dry-run`
   prints all three tables — `[debate]`, `[client]`, `[grading]` — each field with the
   reason it is what it is. Show the user that output and wait.
5. **Every model output and every terminal output is saved under `outputs/`.** A
   generation that exists only in scrollback did not happen. `nohup … > outputs/x.log`
   or `… 2>&1 | tee outputs/x.log`.
6. **Stages run sequentially; never two paid stages at once.** If you are an agent, you
   cannot sit in a foreground `until … sleep` loop — the harness caps a shell call at
   minutes and blocks `sleep`. Use the driver: `nohup scripts/run_sweep.sh
   experiments/sweep.toml > outputs/sweep-driver.log 2>&1 &` runs the five stages in
   order under one process, halts at the first failing stage (writing `STOP.md`), and
   writes `DONE.md` at the end. Poll it from a *background* shell (`run_in_background`)
   or by reading the logs; never `pgrep -f <script>` — that matches the polling shell's
   own command line and the loop never exits.
7. **No parser leak rule is ever loosened.** Text a model marked private must never
   reach the judge, the challenger or a published record. This has failed three times in
   this experiment's history (`LLM_NOTES.md` §3d, §3i, §7) and the standing answer is
   always the same: refuse, spend the one repair, lose the cell if you must. *A lost
   cell is a number that is missing; a leak is a number that is wrong and looks fine.*
8. **The user reads transcripts as part of testing.** When a change touches what a
   record says, render examples and ask them to read some before spending at scale.
9. **The user pushes.** This sandbox has no git credentials. Commit, then say what is
   ready; the push is theirs (`git push origin main`).
10. **Stop triggers are catastrophic-only, by the user's standing instruction.** Runs are
    launched unattended overnight. A high repair rate, phantom contests, an ugly number
    or a dead cell or two are **reported, never stopped for**. Section 5 lists the four
    things that do stop a run. "Stop and wake the user" means, for an agent:
    `kill <driver PID>` (the driver forwards the signal to the running stage's process
    group, waits for it to die, and writes `STOP.md` naming the signal — confirm with
    `pgrep -f exp2-experiment` that nothing is still spending), add what you saw to
    `outputs/experiments/<name>/STOP.md`, and end your turn with the finding — you
    cannot wake anyone. The only confirmation a run needs is
    the one before it starts (rule 4); nothing mid-run waits on the user.
11. **Nothing may reach across into `../exp1/`** — no import, no symlink, no path. exp2
    was ported from exp1 at `f5fc3c9` and has diverged; reading exp1 to see how it did
    something is fine, depending on it is not.

If you keep memory across sessions, seed it from sections 1, 2 and 4 of this file, and
from `LLM_NOTES.md` §4.

---

## 3. Bootstrap on a fresh pod

**Size the disk first.** A full sweep writes **~3.9 GB** under `outputs/`
(0.616 MB per cell measured on pilot 3 × 6,330 cells), the venv is ~0.3 GB and the
image ~3.6 GB. The previous pod had **5 GB and the first sweep died on ENOSPC 80 cells
in** (`LLM_NOTES.md` §7). Ask for **20 GB or more**; the floor below which do not start
is **12 GB free** after `uv sync` (3.9 GB of outputs, plus resume slack for abandoned
`running` cells, plus room to breathe). Also confirm with the user that the OpenRouter
account holds **≥ $44** of credit before the first paid stage.

```bash
git clone https://github.com/SzJS/ConstitutionalDebate.git
cd ConstitutionalDebate

# The API key lives in the REPO ROOT, one level above exp2; load_dotenv() walks up to
# find it, so every experiment shares one file. THE NAME IS OPENROUTER_KEY, not
# OPENROUTER_API_KEY — the code checks that exact name and exp1 shipped an error
# message with the wrong one.
cat > .env <<'EOF'
OPENROUTER_KEY=sk-or-…
EOF

cd exp2                       # every command below runs from here, never from the root
uv sync                       # the dev group carries pyzipper, pandas and statsmodels
```

(The `.env` heredoc above is the one command that runs at the repo root; everything after
`cd exp2` runs from `exp2/`.) Rebuild the corpus **before** running the tests — one test
skips while the archive is not cached, and "337 passed" is the count *with* it. Nothing
upstream is vendored; the archive is fetched into `data/` (git-ignored) and only its
provenance is recorded.

```bash
uv run python scripts/get_tasks.py --subset all --concat \
    2>&1 | tee outputs/get-tasks-all-concat.log
```

Expected output (`records/logs/get-tasks-all-concat.log` is this command's output; on a
fresh pod its first line reads `fetching https://…` instead of `using cached …`, which is
fine) — if the **counts or the sha** differ, **stop and find out why before spending**:

```
wrote 2110 cases to data/cases/ftf-all.jsonl  sha256=9e479a5edbe8

subset         rows   items   sound  flawed  gradable
-----------------------------------------------------
gpqa            191     382     191     191         0
law              40      40      20      20        20
lojban          120     120      41      79        79
medqa           222     222      62     160       160
python800       633     952     319     633       633
surgery         212     212     137      75        75
theoremqa        91     182      91      91        91
-----------------------------------------------------
TOTAL          1509    2110     861    1249      1058
```

Now the tests: `uv run pytest` — expect **337 passed** in about 4 seconds (336 passed,
1 skipped means the archive is not where `get_tasks.py` put it).

`--concat` is what writes `data/cases/ftf-all.jsonl`, the whole-corpus bundle the sweep
spec points at: the seven per-subset bundles joined in sorted-subset order, each case
round-tripped through `load_cases` and duplicate item ids refused. It is deterministic —
the sha256 above is what a correct rebuild produces. Do **not** use `--sample`, which
rewrites `data/cases/ftf-*.jsonl` in place with a subsample and destroys the corpus every
finished run's provenance describes.

The pilot corpora can be rebuilt the same way and are byte-identical to the ones the
pilots ran on (verified 2026-08-25):

```bash
uv run python scripts/get_tasks.py --subset all --pilot 2 --pilot-longest 2 \
    2>&1 | tee outputs/get-tasks-pilot.log
# 42 pilot cases to data/cases/pilot.jsonl (21 flawed / 21 sound) over 7 subsets
uv run python scripts/get_tasks.py --subset all --pilot 4 --pilot-longest 2 \
    --pilot-out data/cases/pilot-3.jsonl 2>&1 | tee outputs/get-tasks-pilot-3.log
# 69 pilot cases, 34 flawed / 35 sound, over 7 subsets
```

**The first of those is not optional**: `scripts/e2e_offline.py` reads
`data/cases/pilot.jsonl` (`e2e_offline.py:52`) and dies in `load_cases` without it.

Last, the whole harness end to end against a fake client — no network, no key, real
items, both documents written for every cell and every contest:

```bash
uv run python scripts/e2e_offline.py 2>&1 | tee outputs/e2e-offline.log
# its last two lines must read:
#   full documents on the generations-only fallback: 0
#   self_critique readable documents with a withheld critique: 0
```

---

## 4. Where things stand

Total spent so far: **$99.68** — $63.00 through the auditor probe (itemised below), plus
the debate-only judgment-challenge campaign's **$36.6753**: the first instrument check
`judgment-debate-pilot` **$1.3285**, three six-cell prompt smokes **$0.1848**
(`judgment-debate-smoke` $0.0921, `-smoke-2` $0.0793, `-smoke-3` $0.0134), the second
instrument check `judgment-debate-pilot-2` **$1.1483** plus **$0.0766** to re-read its
rulings under the adapted instrument, and **the full run's $33.9371**.

The $63.00 breaks down as: $6.67 through pilot 3, roughly $0.40 for sweep-1's 80
decided cells, the full sweep's **$32.1326**, the ~$0.13 paid smoke that preceded it, the
re-contest's **$10.8942** with its two 18-cell smokes (**$0.06**) and its 207-cell
validation slice (**$0.38**), the re-rule's **$3.0887** (a three-variant prompt smoke
**$0.0202**, a 69-ruling smoke **$0.1205**, `rerule-recontest` **$0.8109**, `rerule-sweep`
**$2.1371**), the three partisan pilots' **$1.2234** (`advocate` **$0.4345**, `assigned`
**$0.4026**, `auditor` **$0.3863**), the judgment-challenge slice's **$1.6429**, the
auditor probe's **$6.3935** (its run, the $0.43 correction of 2026-08-27 and the $0.05
one of 2026-08-28), and a few cents of provider checks and liveness calls that nothing
itemises.

**One figure to read carefully.** The probe's own report prints **$4.15** and the two
corrections **$0.43** and **$0.05**, all computed from the rows, and a row carries the
cost of the completion it kept. The wire log carries every attempt, including the 292
format repairs `qwen/qwen3-32b` and `gpt-4.1-nano` needed, and it says **$6.3935** over
2,022 calls. Every other figure on this page is the wire's, so the wire's is the one
totalled here; the report's number is not wrong, it is answering "what did an audit cost"
rather than "what was spent".

Nothing below needs re-running, and section 6 says why.

### The probe (2026-08-24 to 08-25, $4.90) — how the weak model was chosen

`scripts/pick_weak.py` runs four passes over nine candidate models and prints one table:
a solo screen (can the model solve the item alone?), a cached fixture of 68 strong-model
debates, a judging pass over those transcripts, and a challenger pass. Full write-up in
`records/pick-weak/DECISION.md` and `LLM_NOTES.md` §1, §1b.

**`openai/gpt-4.1-nano` was chosen, and two things about that are post-hoc and must
reach the write-up.** First, a pre-registered floor — `MIN_JUDGE_ACCURACY = 0.60` —
disqualified *every* candidate and **the user withdrew it after seeing that**, on the
grounds that contestability is measured *given* a wrong decision and the floor was
filtering out the null result the experiment exists to detect. The constant survives in
the script as `None` with the reasoning beside it rather than being deleted. Second, the
surviving pre-registered rule selected `llama-3.1-8b`, and the user overrode it for
nano on latency (9.5 s judge p95 against llama's 27.1 s) and on verdict skew: eight of
the nine models over-call FLAWED at 63–87% on a 46%-flawed fixture, and nano is the only
one that does not (51% SOUND). All seven subsets survive the screen.

**The weak model is settled in `DESIGN.md` itself** (its *Weak models* section, commit
`27877b5`, 2026-08-26): the user chose `gpt-4.1-nano` after seeing the probe
(`records/pick-weak/DECISION.md`). Older text in `LLM_NOTES.md` that calls this an
unapplied `DESIGN.md` edit predates that commit. Do not change the model.

**A provider attribution that was published wrong and then corrected.** Pilot 2's first
per-provider table charged each format repair to the provider that served the *repair*,
which for 40% of them was a different provider from the one that served the call that
failed. Re-attributed correctly, GMICloud showed **2.1% on n=48** against a 25.5% pool —
which is why the strong model is pinned to it. **Pilot 3 then measured 22.5% on GMICloud
itself over 880 calls.** Either the n=48 figure was luck or the traffic mix differs;
there is no unpinned arm, so nothing may be attributed to the pin in either direction.
What pilot 3 does establish is that the pinned pair is operationally reliable.

### The three pilots

**Pilot 1** (42 items, 126 cells, $0.34). Found that the challenger's instruction was
satisfiable by *agreeing* — "object if the decision rests on an error", and a FLAWED
verdict does rest on an error — so 46 of its 51 "objections" endorsed the decision they
objected to. `revised_given_incorrect = 0/29` is an artifact, not a finding. Also found
that truncation is runaway private deliberation rather than long input, and a third
`Thinking:` leak. Fixed: the challenger states a claimed verdict; a second token cap
(`generation_max_tokens`) for the roles that write record text; the budget repair route.

**Pilot 2** (42 items, 126 cells + a retry pass, $0.49). The contest stopped being
one-directional: 12 of 47 SOUND verdicts contested against pilot 1's 0 of 55, and
`revised_given_incorrect` **9/28**. The grader ran for the first time (the config had
carried `anthropic/claude-haiku-4.5:batch` since the harness was written, and that
suffix routes to a Batch API `client.py` does not speak — 404 on every call), and its
grades agreed with a hand read 6/6 and 5/5. 15 cells died malformed after their one
repair; the repair was restating a format the model had just failed, so it was made
**shape-aware** — and all 15 came back. Read that 16/18 recovery as a floor: those cells
were selected by the failure being fixed.

**Pilot 3** (69 items, 207 cells, $0.95, 30 min) — the last run before the sweep, and
the run whose rates the sweep is budgeted from. Four changes: the strong model was
pinned to a provider for the first time; the challenger answers one
**relative** line (`Decision: STANDS|REVERSE`) because its two absolute lines collided
with its own vocabulary; a new off-path **`agreement`** stage asks Haiku whether the
objection's *prose* argues the verdict was right or wrong; and the aimed repairs say
"for this reply only". Outcome against nine pre-registered expectations is in
`LLM_NOTES.md` §3n; the full checklist is `records/experiments/pilot-3/CHECKLIST.md`.

**The first sweep slice (`sweep-1`) was abandoned**: it died on ENOSPC partway through
`decide`, 80 of 723 cells done, on the 5 GB pod. Its spec is kept as
`experiments/sweep-1.toml` for the record; its outputs are gone. Nothing was learned from
it and nothing rests on it.

### The first full sweep (2026-08-26) — done

**2,110 items × 3 conditions × 1 repeat = 6,330 cells, $32.1326, 17 h 16 m**, launched
01:14:17Z and finished 18:30:34Z, five stages sequentially under `scripts/run_sweep.sh`,
every stage exit 0, `DONE.md` written. **5,724 cells decided = 90.4%**, so the loss is
9.6% against the 14.5% budgeted; the 606 lost are truncations and failed repairs (debate
466, self_critique 94, single 46). **0 non-200 responses in 53,966 attempts**, and the pin
held at 97.1% GMICloud. Section 5 is the procedure it was run by; it must not be run
again. Four commits carry it: **`4a30ea4`** (§3r, the retry-on-resume decision and
`--retry-failed`), **`85bf7da`** (`records/derivations/sweep-checks.py`, the ten-row
checklist over any finished tree, plus the two funnels and the second draws), **`8dbee7d`**
(`records/experiments/sweep/` and the write-up, `LLM_NOTES.md` §3s), **`beb92d8`** (the two
hand checks, the phantom-corrected funnel and the four transcripts).

The numbers, **reported and not concluded from** — §3s says in its own first paragraph
that it does not conclude debate is or is not more contestable, and the two reasons
(no `weak_alone` arm, no specious-objection control) are in §4 above and in §3s:
accuracy **88.3% / 84.4% / 58.2%** (`single` / `self_critique` / `debate`), so debate's
wrong-set is 688 cells against `single`'s 241 and they are not the same items;
**585 of 1,129 contests are phantom (51.8%)** — the `Decision:` line says REVERSE over
prose that argues the verdict was right; corrected for that, **true detection given
incorrect is 7.5% / 26.3% / 12.4%** against a raw 10.4% / 35.9% / 24.7%; debate's
re-decider **overturns 92% of genuine contests on its wrong decisions and 82% of those on
its correct ones**, ten points apart on 85 and 105 cells; and the net effect of the whole
contest process on accuracy is **+1 cell for `single`, +16 for `self_critique`, −27 for
`debate`**. `records/derivations/sweep-phantom-corrected.py` re-derives that last funnel
from the committed `index.jsonl`.

Two findings about the **instruments** came out of the hand checks and both bind anything
quoted from this run. The `agreement` stage agrees with a 20-reply hand read **14 of 20**,
not pilot 3's 19/20 — but **all six misreads are on STANDS lines** and none on a REVERSE
line, so the 51.8% phantom rate (built entirely from REVERSE lines) is audited clean while
the mirror statistic "192 of 4,595 declines argue for reversal" is an over-count of
unknown size. And of the 99 graded rows, **6 carry no reasoning at all and 3 of those are
`valid=True`** — 3 of the 46 valid objections rest on an unexplained YES. Both are written
up in `records/experiments/sweep/HANDCHECK-agreement.md` and `HANDCHECK-graded.md`.

### The re-contest (2026-08-26) — done

**The sweep's 5,724 decisions contested a second time, and nothing regenerated.**
`experiments/recontest.toml` carries `decisions_from = "outputs/experiments/sweep"`, which
makes `--stage decide` refuse and routes every decision lookup into the sweep tree; the
run wrote a new tree and left the old one byte-identical (whole-tree fingerprint
`5e2eb4d6…` before and after). Launched 22:14:22Z, finished 23:38:34Z: **84 min**, four
stages (`contest agreement grade analyse`, under `RUN_SWEEP_STAGES`), every stage exit 0,
**$10.8942**, $0.00190 per contested cell, **5,724/5,724 contested**, 18,427 of 18,430
attempts HTTP 200 and three client-side `ReadTimeout`s retried to completion. 361 tests
pass. Evidence: [`records/experiments/recontest/`](records/experiments/recontest/README.md);
write-up `LLM_NOTES.md` **§3t**.

It tests three changes and nothing else, all settled by the user in `DESIGN.md` commit
**`e46ada3`**: the challenger **decides last** (reasons first, `Decision:` line at the end,
each word glossed in the phrases of that decision); recourse is a **weak third party in
every condition** (`recourse_form = "third_party"`, so all 464 rulings are
`uphold_overturn`, where the sweep ruled the two solo conditions by the strong decider
re-deciding in its own conversation); and the challenger is told where its published
reasons go. Three commits carry it: **`6a911f3`** (both design changes plus
`decisions_from`), **`41f6a65`** (the estimate charges nothing for decisions it reads
elsewhere; the e2e renders both recourse forms), **`6af26bb`** (the instruction sentence
that took format repairs from 10 of 18 back to 2 of 18). Two 18-cell smokes ($0.06) and a
207-cell validation slice ($0.38) preceded it, each read by the user before the next.

The numbers, **reported and not concluded from** — §3t says so in its own first paragraph.
**The phantom fix worked**: the phantom share of objections fell **585/1,129 = 51.8% →
62/464 = 13.4%**. **But objections fell with it**: 1,129 → 464, and phantom-corrected true
detection given a wrong decision **halved**, 186/1,244 = 15.0% → 85/1,244 = 6.8%. The
per-cell transition table says 980 of the sweep's objections were withdrawn and 315 newly
raised; of its 537 *genuine* objections, 438 were not raised again. The loss is heaviest in
`debate` — 421 of 440 objections withdrawn, true detection 12.4% → 3.1%, genuine false
alarms 11.0% → 2.6%. §3t states both readings ("the phantoms were removed" and "genuine
objections fell too") and the evidence for each, and says the choice between them needs the
hand check.

**The second change has a result of its own, and it is not the one the design hoped for.**
The weak third-party judge overturns **52 of 62 phantom objections (83.9%)** and **233 of
316 genuine objections to a CORRECT decision (73.7%)**, against **54 of 85 (63.5%)** on
genuine objections to a wrong one — discrimination **−10.2pp**, where the sweep's mixed
mechanism gave **+32.0pp**. `single`, which under the sweep broke **0 of 1,823** correct
decisions, breaks **157**. The net effect of the whole contest process on accuracy is
**−221 cells**, 78.3% → 74.4%, against the sweep's −10. Removing the asymmetry did not
remove the confound; it moved it, and `metrics.json`'s own caveat now says so.

**And then the hand checks moved it again.** `LLM_NOTES.md` §3t(d) and
`records/experiments/recontest/HANDCHECK-ruling-line.md`: the recourse judge's
`Ruling: UPHOLD|OVERTURN` line contradicts the judge's *own reasoning* in **8 of 12**
sampled rulings whose parent verdict was **FLAWED** and **0 of 8** whose parent was SOUND,
and **52 of the 62 phantom rulings** — all on FLAWED parents — were "overturned". 273 of
the 464 rulings are on FLAWED parents. So every number in the paragraph above that came out
of the recourse stage, **and the sweep's `debate` 92%/82% and net −27 with it**, describes
that line rather than the judge's judgement; the sweep's `single`/`self_critique`
`restated_verdict` rulings are unaffected, and the detection side of both runs is untouched.
**The next step is the challenger's own fix applied to the judge** — instantiate
UPHOLD/OVERTURN per decision in `RECOURSE_JUDGE_USER` with the line last, add a Haiku
ruling-agreement instrument, and re-rule the 464 + 440 rulings for cents since the
objections already exist; a prompt change, so smoke first and the user decides. Nothing in
`src/` was changed for it.

The three checks §5 asks for after a run are done for this one:
`HANDCHECK-agreement.md` (11/20, all eight misreads on STANDS lines, seven of them
python800), `HANDCHECK-graded.md` (valid 21/46 = 45.7%, or 21/41 excluding gpqa) and four
`transcripts/` — one of which is the same cell the sweep's `transcripts/` holds as
`debate`'s exemplary overturn, and on which the re-contest's challenger declined.

`records/derivations/recontest-vs-sweep.py` reproduces the whole comparison from the two
committed `index.jsonl` files on a bare clone.

### The re-rule (2026-08-27) — done

**The ruling line was fixed and every objection either full run ever raised was re-ruled,
for $3.09.** Nothing was decided and nothing was contested: the three specs carry
`decisions_from` **and** `contests_from`, which make `decide`, `contest`, `agreement` and
`grade` all refuse and route every lookup into a finished tree that is read and never
written. Both source trees were hashed before and after every run and are byte-identical
(`sweep 5e2eb4d6…`, `recontest 518bd5d9…`). Evidence:
[`records/experiments/rerule/`](records/experiments/rerule/README.md) — one directory,
three subtrees; write-up `LLM_NOTES.md` **§3u**. 392 tests pass.

**What changed, commit `dfad084`, from a `DESIGN.md` paragraph in the same commit.** The
recourse judge is no longer asked for `Ruling: UPHOLD|OVERTURN`. It is told it rules on the
**original text under review** — the text in `<solution>`, not the objection, not the
decision's reasoning, and **not the program or proof that text may itself be assessing** —
and ends with an absolute `Conclusion:` line, from which UPHOLD/OVERTURN is derived by
comparison with the decision. `Ruling.form` gains **`stated_conclusion`**; a new
**`ruling_agreement`** stage has Haiku read the judge's prose with the line stripped and
reports the mismatch, mirroring what `agreement` does for the challenger; and the spec key
**`contests_from`** re-rules another tree's finished objections into a tree of its own.
The wording is variant C of a 20-cell three-variant smoke ($0.0202): line-vs-own-prose
contradictions **old 8/20, A 7/20, B 5/19, C 1/20**; correct against gold **8 → 14/20**.

**Three runs**, all `RUN_SWEEP_STAGES="rerule ruling_agreement analyse"`, three stages,
every stage exit 0, every wire attempt HTTP 200:

| | rulings | spend | wall | mismatch |
|---|---|---|---|---|
| `rerule-smoke` — the 62 known-failure phantoms + 7 controls | 69 | $0.1205 | 54 s | 1/69 = 1.4% |
| `rerule-recontest` — all of the re-contest's | 464 | $0.8109 | 5.5 min | 27/464 = 5.8% |
| `rerule-sweep` — all of the sweep's | 1,129 | $2.1371 | 13 min | 68/1,129 = 6.0% |

**The numbers, reported and not concluded from.** On the smoke the old line overturned
**52 of 62** phantoms and the new one overturns **1**; Fable read all 69 by eye and found
**0** line-vs-prose contradictions. On the re-contest's 464 objections, pooled
discrimination goes **−10.2 → +30.7 pts** and net accuracy **−221 → −69 cells**. On the
sweep's `debate`, net **−27 → +4** and discrimination **+9.9 → +21.7 pts**. And on the
sweep's **682 solo objections**, ruled by the strong re-decider in the sweep and by the
weak third-party judge here — identical decisions, identical objections, two rulers — the
weak judge overturns **73%** of genuine objections to wrong decisions against the
re-decider's **42%**, and **35%** against **12%** on genuine objections to correct ones:
discrimination **+37.9 vs +30.4**, net **−24 vs +17**. The re-decider overturned **1 of
334** `single` rulings, so the sweep's solo recourse advantage was substantially **a ruler
that never moved**.

**The residual is measured now, not assumed** — about **6%**, **flat** across parent
verdicts where the old line's failure was concentrated on FLAWED, and concentrated in
**python800** (51 of `rerule-sweep`'s 68 mismatches; 10.9% there against 2.6% elsewhere)
with a known direction: on a text that correctly reports a bug the line over-calls FLAWED,
which biases against correcting wrong FLAWED decisions. Three hand checks in
[`records/experiments/rerule/HANDCHECK-ruling-line.md`](records/experiments/rerule/HANDCHECK-ruling-line.md)
— the smoke's 69/69, a 20-read of `rerule-recontest` (instrument 19/20 correct, 9 of 10
alarms real) and a 10-read of `rerule-sweep`'s worst cell (10/10 alarms real). Four
transcripts in `transcripts/`, three of them the **same cells** the sweep's own
`transcripts/` holds.

**Still owed** (§3u): the python800 phrasing, which is a design decision; a hand read of
the **145 of 682** cells where the two rulers disagree; the specious-objection control; and
the fact that phantoms are a challenger property the re-rule does not touch.

`records/derivations/rerule-compare.py` reproduces all three comparisons from the committed
`index.jsonl` files; the cross-check against the run tree is optional and no table uses it.

### The partisan pilots (2026-08-27) — NO-GO

**The planned partisan-challenger ablation was tried on three clauses and stopped. The
~$22 full run was never started; $1.2234 was spent finding that out.** Evidence:
[`records/experiments/partisan-pilots/`](records/experiments/partisan-pilots/README.md) —
one directory, three subtrees and the comparison log; write-up `LLM_NOTES.md` **§3v**. 403
tests pass.

**Why it was proposed.** The neutral decide-last challenger objects on ~8% of cells, so the
judge's discrimination, the grader's valid-objection rate and the phantom rate all rest on
tens of cells per condition. Under advocacy every cell yields an objection unless the
advocate declines, which would have put those quantities on hundreds.

**What was built, commit `3e08df4`.** `CHALLENGER_SYSTEM` gained one `{arm_clause}` slot and
`CHALLENGER_ARMS` four named arms — `neutral` plus `partisan_{advocate,assigned,auditor}`;
everything else in the prompt is shared, and the tests diff the four rendered prompts
pairwise to prove it. A config field **`challenger_variant`** defaults to `"neutral"` (what
every paid run before this did) and is validated; **`Challenge.arm`** is validated against
the same names and written into `index.jsonl` as **`challenge_arm`**; `analysis.caveats()`
emits a partisan-only caveat saying detection and false-alarm rates become advocacy rates.

**Three runs**, all `RUN_SWEEP_STAGES="contest agreement ruling_agreement grade analyse"` on
`data/cases/pilot-3.jsonl` (207 cells, **194** with a sweep decision to contest), five
stages, every stage exit 0, every wire attempt HTTP 200, 0 cells failed:

| clause | genuine objections raised | × neutral (19/194 = 9.8%) | spend | wall |
|---|---|---|---|---|
| `partisan_advocate` | **27/194 = 13.9%** | **1.42×** | $0.4345 | 3 m 39 s |
| `partisan_assigned` | **21/194 = 10.8%** | **1.11×** | $0.4026 | 3 m 23 s |
| `partisan_auditor` | **19/194 = 9.8%** | **1.00×** | $0.3863 | 3 m 23 s |

**The gate, written before the runs, wanted ≥ 2× on the pooled 194.** Its other three
criteria passed in all three clauses — phantom share 3.6% / 0% / 0% against a 13% ceiling,
declines on correct decisions **88–90%** (0% would have meant "let it stand" was dead), and
zero unparsed or contradictory lines. Only the raise rate failed, and it failed in all
three.

**Why, and it is not the wording.** On `gpqa-127-sound__debate` and
`gpqa-161-flawed__debate` — both **wrong** decisions, both declined under all three clauses
— every partisan reply opens with "The verdict … is correct" and restates the judge's own
grounds, in nearly the words the neutral challenger used on the same cells. The
transitions table says the same thing at scale: the advocate keeps 12 of
the neutral challenger's 19 objections and **drops 7**, `assigned` drops 10, `auditor` drops
11 and lands on exactly the neutral rate. Advocacy is resampling the same challenger, not
adding to it. **The standpoint instruction does not move `gpt-4.1-nano`**, which joins §3h,
§3n and §3u: this model follows the shape of the record in front of it rather than an
instruction about how to stand toward it.

**What this settles, and what it costs.** The low neutral objection rate is **the model's,
not the neutral instruction's** — that was the live alternative and it is now closed. The
recourse numbers therefore stay at the neutral n and every small-denominator caveat in §3s,
§3t and §3u stands unchanged. The ablation itself is **unrun, not refuted**: the code,
tests and four specs are committed, no `"partisan"` alias was ever assigned, and
`experiments/partisan.toml` still refuses to run without a variant. Re-running it with a
stronger challenger costs the same ~$22 and one spec line — **a model choice for the user,
not an agent's.**

`records/derivations/partisan-vs-neutral.py` reproduces the whole comparison from four
committed `index.jsonl` files, no run tree and no key.

### The judgment variant (2026-08-27) — built, sliced, probed, and NOT run

**SUPERSEDED IN PART on 2026-08-28 — read the section below this one first.** What
follows is the state as of 2026-08-27 and is kept because the probe, the slice and the
harness quote check are all still exactly as described. What changed is the conclusion:
the user settled that success for this variant is measured **within debate**, flash was
run as a **disclosed departure** from the rule that picked nobody, and
`experiments/judgment-debate.toml` **has run**. The three-condition
`experiments/judgment.toml` is still unrun and there is no reason to run it — its two solo
conditions have no judgment separate from their record to audit.

**The judgment-challenge variant is in the code and must not be run at scale.** No
challenger model has cleared `records/pick-auditor/RULES.md`, and until one does,
`experiments/judgment.toml` stays unrun. Write-up: `LLM_NOTES.md` **§3w**; decision and
evidence: [`records/pick-auditor/`](records/pick-auditor/DECISION.md).

**What the variant is.** `challenger_variant = "judgment"` swaps the challenger's whole
task: instead of "is this verdict right", it audits the **judgment** — the reasoning given
for the decision — against the published record, for a contradiction, a misstatement or an
omission, quoting both sides of each. The grader that reads it checks each alleged defect
**against the record** and never opens `flaw.json`, which is why every subset is gradable
(gpqa included) and why validity is defined on sound items and on CORRECT decisions. The
`Decision: STANDS|REVERSE` line, `challenge_stance`, the `agreement` stage and the whole
recourse machinery are unchanged.

**What the slice found** (`outputs/experiments/judgment-pilot`, the 194 pilot-3 cells,
**$1.6429**, 920 wire calls, all HTTP 200): `gpt-4.1-nano` raises objections on **111/194 =
57%** against the neutral challenger's 9.8% on the same cells — `debate` 46/60, `single`
32/68, `self_critique` 33/66 — and **7 of the 111 are graded valid (6%)**, from 315 alleged
defects of which 8 held up. In a hand read of 66 of its `Judgment says:` quotations, **34
were not in the judgment at all**. The grader itself came out well: it rejects 94% and for
the right reasons. The read is a capability limit, not a prompt one, and it is what the
probe was commissioned to fix.

**The quote check is harness-wide and applies to any future judgment run.**
`parse_defects(text, judgment)` decides at parse time whether each defect's `Judgment
says:` quotations are really in `RunRecord.decision_grounds`; the grader is never asked
about one that fails and makes **no call at all** when none survives; `index.jsonl` gains
`challenge_defects_n` and `challenge_defects_misattributed_n`, and the analysis a
`misattributed_quote` rate over defects. It is three-valued — `None` where the check does
not apply — so an omission, a defect that quoted nothing, and every `challenge.json`
written before it grade exactly as they did. The nano slice was **not** re-graded on
purpose. The check was corrected **twice** after the probe — it stripped only the outer
quotation marks, so a quote written with nested single quotes read as a fabrication; and
it compared 80 characters as one string, so an ellipsis-stitched quote failed even when
every piece of it was verbatim. Both bugs, their before/after tables and the floors they
did and did not move are in `RULES.md` under *Instrument corrections after the run*. Both
were found by reading raw replies, and a quote-check failure costs an objection its grader
call — so the check does not merely count, it decides.

**How to re-run the probe** — it is offline until the last step and cheap:

```bash
cd exp2
# the fixture and every table, no network, no key, nothing sent:
uv run python scripts/pick_auditor.py --dry-run 2>&1 | tee outputs/pick-auditor-dryrun.log
# re-derive every table from the rows already on disk, re-checking the quote check
# from the fixture text — no calls, this is how a fixed checker is re-applied:
uv run python scripts/pick_auditor.py --report-only 2>&1 | tee outputs/pick-auditor-rescored.log
# rebuild the fixture after changing an injector (KEEP a copy of the old one first):
cp outputs/pick-auditor/fixture.jsonl outputs/pick-auditor/fixture.before-<what>.jsonl
uv run python scripts/pick_auditor.py --dry-run --rebuild-fixture
# the paid run, ~$6 for six candidates; refuses to send anything if RULES.md is missing:
uv run python scripts/pick_auditor.py 2>&1 | tee outputs/pick-auditor.log
```

**Resume is keyed on `judgment_sha`, not on the file.** Every audit row carries the
sha256 of the judgment it was audited against. A re-run keeps every row whose sha still
matches the fixture, re-audits exactly the items whose text moved (and any fixture item
with no row at all), and writes what it replaced to
`rows-audit-<model>.superseded.jsonl` — a paid measurement is evidence about the
instrument that made it and is never deleted. The correction of 2026-08-27 re-bought 20
items per candidate out of 251 for **$0.43** rather than re-running 1,500 audits, and the
quote-check correction of 2026-08-28 re-bought **nothing at all** ($0.05 of re-grading):
the fixture was byte-identical, so every stored objection was re-checked from it offline.
The control false-alarm gradings are reused wherever the surviving-defect set is
unchanged.

**The result: NO MODEL PICKED.** Six candidates — `gpt-4.1-nano` (the floor, not
eligible), `qwen/qwen3-32b`, `google/gemini-2.5-flash`, `openai/gpt-4.1-mini`,
`openai/gpt-4.1`, `openai/gpt-5.6-luna` — over 251 audits each on 60 real judgments with
injected defects. Two cells in the whole table clear a floor; every candidate fails at
least three. **No Gemini Pro is in the pool**: every Pro-class Gemini, `gemini-3.7-flash`
and `x-ai/grok-4.6` answer with `HTTP 400: Reasoning is mandatory for this endpoint and
cannot be disabled`, and this experiment runs `reasoning_effort = "off"` so that the
challenger's private channel is the published `Thinking:` block. `anthropic/*` is excluded
because Haiku is the grader.

**Where the evidence lives.** `records/pick-auditor/` — `RULES.md` (the thresholds,
committed before any candidate was called, plus the two instrument corrections),
`DECISION.md`, `fixture-manifest.jsonl` (one line per fixture item: cell, variant, span,
deleted sentence, alteration, `copies_edited`). In `outputs/` (git-ignored, rebuildable):
`pick-auditor.log` with the re-scored table appended beneath the original,
`pick-auditor-rescored.log`, `pick-auditor-by-condition.log`,
`pick-auditor-fixture-check.log`, `pick-auditor-sample4.log`, and `pick-auditor/` with the
fixture, the rows, the superseded rows and every wire call.

**Do not** re-grade the nano slice, edit `RULES.md`'s thresholds after seeing numbers, or
run `experiments/judgment.toml`. (`experiments/judgment-debate.toml` is a different spec
and it is DONE — see the next section; do not re-run that either.) If the audit prompt is revised — a verification procedure
is the obvious candidate, see §3w(e) — the house rule applies (read it on ~6 examples
first) and the floors must be restated as kept or changed **in `RULES.md`, before the
run**, because a re-run under a new prompt is a new measurement.

### The debate-only judgment-challenge run (2026-08-28) — done

**The sweep's 1,644 decided `debate` cells, audited and re-ruled. DO NOT RE-RUN IT.**
01:48:17Z → 03:18:22Z, **1 h 30 m**, **$33.9371**, five stages exit 0, **9,982 wire calls
with 0 non-2xx**, 1,643 of 1,644 cells contested (one lost to a truncated *comprehension*
probe, off the decision path). Nothing decided, nothing regenerated: `decisions_from`
routes every lookup into the sweep tree, which is byte-identical either side
(`5e2eb4d6…`). Evidence:
[`records/experiments/judgment-debate/`](records/experiments/judgment-debate/README.md);
write-up `LLM_NOTES.md` **§3x**; pre-registration
[`PREREG.md`](records/experiments/judgment-debate/PREREG.md), **committed before the run**.

**What it asks, and why it is paired.** Only a debate publishes a judgment that is a
document other than the decision itself, so procedural recourse is defined in one
condition and undefined in the other two. The comparison is therefore within debate: the
same decided cells, before recourse and after. **Endpoint: net accuracy change, exact
two-sided McNemar on the discordant pairs, α = 0.05.**

**The numbers, reported and not concluded from.** **173 fixed, 128 broken, net +45,
p = 0.0110865** — positive and significant; accuracy **58.2% → 60.9%** [58.5, 63.2]. The
neutral arm (`rerule-recontest`) on the same cells nets **+1**; procedural against neutral
is **+44, p = 0.0164**. Objections were raised on **1,148/1,644 = 69.8%**, **0 phantoms**,
**881/1,148 = 76.7% graded valid**, misattributed quotes **45/1,523 defects = 3.0%**,
discrimination **+13.3 pts** (overturn 33.6% on wrong decisions against 20.3% on correct
ones).

**Read `CHECKLIST.md` §0 before quoting any of that.** `ruling_line_mismatch` fired on
**349/1,147 = 30.4%** of rulings and is **concentrated on FLAWED parents — 50.8% against
8.2%**, and worst on FLAWED-parent overturns (79.1%). That is the same shape the OLD
`Ruling: UPHOLD|OVERTURN` line failed in (§3t), where the re-rule's replacement measured a
**flat ~6%**. It lands on the endpoint's own cells: 27.2% of the *fixed* and 38.3% of the
*broken*. A **post-hoc, not pre-registered** sensitivity — take the reader's reading of
each ruling's prose over the ruling's own line wherever that reader answered STANDS or
CHANGED — turns **+45 into −32, p = 0.114**. It is section (f) of the derivation and it is
only as good as a Haiku reader.

**Three revisions preceded it, all dated in `PREREG.md` and all smoked first.**

| | what | outcome |
|---|---|---|
| format (prompt) | the `Argument:` label shown at the head of the response template | **failed its gate twice** (6/6 then 5/6 repairs on a six-cell smoke); the run went with the repair path, and **1,588 of 1,644** objections were repaired with **0 cells lost** |
| recourse (materiality) | for this arm only, the judge is shown the judgment and rules in two steps — is each defect real against the record, and if so is it material — with the decision's own `Conclusion:` line supplied as the line to end on when it stands | pilot 1 → pilot 2: overturns **44.4% → 32.4%**, breakage of CORRECT decisions **34.6% → 22.2%**, net **+2 → +4**; two-step prose **0/45 → 37/37** |
| instrument (`ruling_agreement`) | arm-keyed reader asking a materiality ruling what it CONCLUDES (STANDS / CHANGED / NEITHER), mapped in code onto the verdict vocabulary | pilot 2 mismatch **35.1% → 16.2%**; off the decision path, so an instrument revision and not a change to the run |

**The challenger is `google/gemini-2.5-flash` and that is a disclosed departure**: the
auditor probe's pre-registered rule picked nobody, and flash was chosen after the numbers
(`records/pick-auditor/DECISION.md`, addendum of 2026-08-28). The probe measured it under
the **pre-revision** prompt.

**Every repaired objection is a second attempt written under the repair instruction, which
suppresses the private section** — so 1,587 of the graded objections carry no `Thinking:`
block and their first attempt's working was discarded. That is a property of what was
graded, not a loss of cells.

**Still owed after this run:** the **specious-objection control** (every cell re-ruled on a
placeholder objection) is what separates "the audit" from "a second look", and it is still
not run; the **python800 phrasing** from §3u is still a design decision; and the
30.4% ruling-line residual above wants a hand read of its alarms before the endpoint is
quoted anywhere outside this repository.

### The open findings the write-up must carry

These are not bugs to fix. They are known properties of the measurement, and a reader
must not have to discover them (`LLM_NOTES.md` §4, §3l–§3o):

- **Natural-error selection bias.** exp2 takes naturally occurring errors only. A weak
  judge errs where the correct side argued *badly*, so debate's incorrect cell selects
  the debates in which debate surfaced the flaw worst — the hypothesis is tested on its
  weakest examples. The direction is favourable (a positive result is a lower bound) but
  `single` has no equivalent filter, so the selection is **asymmetric across
  conditions**.
- **No `weak_alone` condition.** `debate` is judged by a weak model and the baselines are
  decided by a strong one, so the headline comparison confounds the mechanism with model
  strength. If debate loses, this design cannot separate "debate does not help" from
  "the judge was too weak". The probe's own solo-vs-judge rows are that reference point
  and are already paid for (`records/pick-weak/rows-*.jsonl`).
- **No specious-objection control.** The challenger is neutral only, so a high revision
  rate cannot be told apart from a re-decider that capitulates to any pushback. **Still
  true after the 2026-08-28 debate-only run**, which is why its `PREREG.md` states the
  confound rather than resolving it: the materiality ruling gives a procedural objection a
  defined role, but the same weak model still decides materiality, and no cell has ever
  been re-ruled on a placeholder objection.
- **The informed judge.** `DESIGN.md` puts the problem and the solution in front of the
  judge and the challenger, so this is "argument-assisted weak judge", not the
  information-asymmetric debate of the literature. The probe measured the consequence:
  given a debate transcript, the weak judge got *less* accurate, paired on identical
  items (pooled McNemar p = 0.0009 on the first shortlist, `LLM_NOTES.md` §3h), and
  eight of nine weak models over-called FLAWED. Pilot 3 adds that the challenger contests
  SOUND verdicts rarely (3% in `single` and `debate`). Do not cite pilot 1's 6-of-8 /
  0-of-12 asymmetry for this — that number was an artifact of the challenger misreading
  its instruction (§3l), fixed in pilot 2.
- **Debate's persuasion cuts both ways.** Pilot 3: `debate` corrected 4 of its 26 errors
  and broke 2 of its 31 correct decisions. And `debate` errs on 26 of 57 items against
  `single`'s 8 of 68, so its incorrect cell is four times the size and made of different
  items — reading `revised_given_incorrect` across conditions is reading a difference in
  judge strength, not in contestability.
- **Phantom contests, and the instrument that finds them.** 13 of pilot 3's 30 contests
  are `Decision: REVERSE` on top of prose that argues the verdict was **right** — 43%
  overall, 75% in `single`. Without the `agreement` stage the contests column would have
  read 30 and meant 17. A 20-reply hand check agrees with the Haiku reading 19 times out
  of 20. The mirror error is nearly absent (2 of 147 declines).
- **The SOUND/verdict vocabulary collision** that made the instrument necessary: the
  challenger used "SOUND" to mean "the verdict is sound" as readily as "the text is
  sound", in 93 of 108 pilot-2 replies. The fix was to remove the verdict vocabulary from
  the challenger's line entirely. Its cost: `agrees` and `contradictory` became
  structurally unreachable and are reported as 0 with a caveat saying so.
- **Withheld critiques.** A critique whose public section cannot be located is withheld
  rather than guessed, and the challenger then reads a placeholder where the criticism
  should be — in the one condition whose record is *defined* by its critiques. Pilot 2:
  21 of 139. Pilot 3: 0 of 166. Since 2026-08-25 a critique cut off by the token cap can
  also be withheld rather than killing its cell (§3o); the two cases are distinguishable
  in the records.
- **Record-length imbalance.** `decision_record_words` in pilot 3: `single` **151**,
  `self_critique` 1,884, `debate` 1,857. The two long conditions are matched to within
  1.5%; `single` is an order of magnitude shorter. That is a property of the condition,
  not of the run, and `DESIGN.md` lists a token-count ablation for it.
- **`single` never moves — but that is not yet evidence of anchoring.** 0 of 18
  contests (42 cells) changed a `single` decision in pilot 2, 0 of 8 (68 cells) in
  pilot 3. In pilot 2, 16 of those 18 contests were on *correct* decisions and most
  agreed with the verdict in prose (phantom contests); only 2 were on wrong decisions.
  So the strong model has mostly been right to hold. Whether it also holds against a
  *valid* objection is an open question the sweep's `single` false-negative cell answers
  — watch `revised_given_incorrect` for `single` with its n.
- **Two denominator subtleties.** The graded rates are conditional on an objection having
  been raised, so a write-up must multiply through `challenge_raised` or it overstates
  detection (§3f). And gpqa's annotations say *where* a flaw is and not *what* it is, so
  its 382 items are graded for detection and clamped on characterisation (§3g).

---

## 5. The first sweep — exactly what to run

**This ran on 2026-08-26 — see the notice at the top and §4. Kept as the procedure.**

The spec is [`experiments/sweep.toml`](experiments/sweep.toml), already written. It is
`pilot-3.toml` with a different corpus and one explicit `copy_parent`; nothing in the
**spec's** decision path differs from the run its budget comes from. The **code** does
differ in two places that post-date every paid run: `ce51cbc` (a critique cut off past
its label is withheld instead of killing the cell, §3o) and `1cacd0b` (a pinned 404 is
retried, §3p). Both are covered offline by `e2e_offline.py` and the test suite; step 2b
below is the ~$0.10 paid smoke that exercises the real client through them.

**Resume semantics (one attempt per cell).** Re-running a stage skips every cell whose
latest run is `completed` *or* `failed`, and attempts only cells with no run or one left
`running` by a crash. So a re-run after a STOP finishes the sweep without giving any cell
a second draw — which `LLM_NOTES.md` §3p.4 refused to wire as a retry because it selects
for compliant outputs, and which at seed 0 mostly reproduces the same truncation anyway.
`--retry-failed` opts back into re-attempting failed cells; the user confirmed
retry-on-resume on 2026-08-26, so every driver launch carries `--retry-failed` via
`RUN_SWEEP_CMD` — see `LLM_NOTES.md` §3r.

| | |
|---|---|
| corpus | `data/cases/ftf-all.jsonl`, 2,110 items |
| cells | 6,330 = 2,110 × 3 conditions × 1 repeat |
| cost | **~$34**, or **~$44** with 1.3× headroom, from $0.00537 per decided cell |
| wall-clock | **~13 h** of `decide` at 16/8, ~15 h for all five stages |
| disk | **~3.9 GB** under `outputs/` |
| expected loss | ≤ 14.5% of cells to truncation (~900), the accepted price of the caps |

Cost basis: `$0.00537` is per *decided* cell in pilot 3, applied here to all 6,330
*attempted* cells, so it already includes the ~14% that will die — a deliberately
conservative figure (`records/logs/sweep-1-estimate.txt` shows the per-attempted-cell
alternative, ~$29).

`max_concurrency = 16` / `max_runs_in_flight = 8` is what pilot 3 **proved** — 207 cells
in 26 min with 0 non-200 responses in 1,679 attempts. `sweep-1.toml` raised it to 24/12
on a projection and died of a full disk before that could be evaluated, so 24/12 remains
unproven and is not used.

### Run order

Sequentially — one process, five stages, the driver script. The dry-run and the provider
check come first and are the two places to stop for the user.

```bash
cd exp2

# 1. the dry-run: all three hyperparameter tables. Show the user; wait for their word.
uv run exp2-experiment --spec experiments/sweep.toml --stage decide --dry-run \
    2>&1 | tee outputs/sweep-dryrun.log
```

Its header, which is what to check before anything else:

```
experiment: sweep   stage: decide   outputs: outputs/experiments/sweep

cells: 6330  debate=2110  self_critique=2110  single=2110
estimated calls: decision 31650, contest 12660, ruling <= 6330, agreement <= 6330,
                 grading <= 3174  => up to 60144
one attempt per cell per invocation, and one per cell across a resume: re-run the stage to resume, and a cell whose latest run is completed or failed is skipped while only a cell with no run — or one left running by a crash — is attempted. --retry-failed re-attempts failed cells too. Client transport retries and at most one format repair per generation are on top.
```

```bash
# 2. VERIFY THE PROVIDER SLUGS with one real pinned call (~$0.00001). Not optional; no
#    dry-run can replace it. `order` takes OpenRouter provider *slugs* while calls.jsonl
#    records display names, and the endpoints API path takes the model id with the
#    slash UNESCAPED. client.py retries a 404 whose message says "no endpoints
#    available" OR "no endpoints found" — so a momentary GMICloud absence is retried,
#    which a 13-hour run needs — and the price of that is that a MISCONFIGURED slug is
#    also retried, slowly, until max_attempts is spent on every cell. This one call is
#    the guard against that.
uv run python records/derivations/sweep-1-provider-check.py experiments/sweep.toml \
    2>&1 | tee outputs/sweep-provider-check.log
#    The script reads the model and pin from experiments/sweep.toml. Expected:
#    "SERVED BY: GMICloud" and "VERDICT: PASS" with non-empty content
#    (records/logs/sweep-provider-check.log is a passing run). "VERDICT: WAIT" means
#    the call was served by the second pinned provider — GMICloud is absent right
#    now; that is not a go. On WAIT or FAIL: retry once, an hour later; if it still is
#    not PASS, stop and put it to the user. (An agent cannot wait an hour inside a
#    turn: end the turn with the log and retry first thing next turn.) Never run on
#    CoreWeave alone (n=20, no signal) and never add fallbacks.

# 2b. A PAID SMOKE of the real path, ~$0.10: decide the first 10 items into the
#     sweep's own tree, so the driver later skips them and nothing is decided twice.
#     This is the only paid exercise of the two post-pilot-3 code changes.
uv run exp2-experiment --spec experiments/sweep.toml --stage decide --limit 10 \
    2>&1 | tee outputs/sweep-smoke-decide.log
#     Expected: 30 cells attempted, most completed, no traceback, no STOP; a few
#     truncation failures are normal (pilot 3 lost 14%). A traceback or 0 completed
#     is a stop. Read two transcript.md files before going on.

# 3. the five stages (four paid; `analyse` makes no calls), sequentially, one driver:
RUN_SWEEP_CMD="uv run exp2-experiment --retry-failed" \
    nohup scripts/run_sweep.sh experiments/sweep.toml > outputs/sweep-driver.log 2>&1 &
echo $! > outputs/sweep-driver.pid
#    Per-stage logs land in outputs/sweep-<stage>.log. The driver halts at the first
#    stage that exits non-zero and writes outputs/experiments/sweep/STOP.md; on success
#    it writes DONE.md. Poll from a background shell; expect ~15 h.
```

**`RUN_SWEEP_STAGES` is how a subset of the stages runs, and it is how the later passes
ran.** The driver's default is the full list; setting the variable overrides it, and the
stages still run sequentially with the same per-stage logs, `STOP.md` and `DONE.md`:

```bash
# the re-contest (2026-08-26): decisions read from the sweep tree, everything else re-made
RUN_SWEEP_STAGES="contest agreement grade analyse" \
    nohup scripts/run_sweep.sh experiments/recontest.toml > outputs/recontest-driver.log 2>&1 &

# a re-rule (2026-08-27): decisions AND objections read from finished trees, only the
# ruling re-made. `contests_from` in the spec makes contest/agreement/grade refuse, so
# these three stages are the whole of it — this is how all three rerule-* runs ran.
RUN_SWEEP_STAGES="rerule ruling_agreement analyse" \
    nohup scripts/run_sweep.sh experiments/rerule-sweep.toml > outputs/rerule-sweep-driver.log 2>&1 &
```

A re-rule is minutes and cents, not hours and dollars, because no decision and no
objection is generated — the dry-run's ruling term is **counted, not bounded**, and prints
exactly how many rulings the pass will make before it makes them.

**Measuring the stop triggers while it runs** — from a background shell, hourly:
provider failures are the non-`200 OK` lines in `outputs/sweep-decide.log` against the
total (trigger 1); wall-clock is the time since the *latest* `=== run_sweep: decide …`
start line in `outputs/sweep-driver.log` (the stage log is appended across attempts, so
its first line is the wrong clock after a resume) against the 13 h projection
(trigger 2); a crash is `STOP.md` appearing (trigger 3); verdict skew is
read straight from the `verdict.json` files under `outputs/experiments/sweep/cells/`
(trigger 4) — check it once ~200 cells are in, and again at ~1,000. Report the numbers
each time; act only on the four triggers.

**Across turns.** An agent session does not last 15 hours; the driver does. `nohup`'d
processes in this repo's history have outlived the turn that launched them (a waiter
loop once ran all night, `LLM_NOTES.md` §7), so: launch, record the PID, poll from a
background shell until ~200 cells are in, report trigger 4 and the non-200 count, and
**end the turn** with the PID and log paths. Every later session begins by checking
that PID, then `STOP.md`/`DONE.md`, then the tail of the current stage's log, before
believing anything else. Trigger 2 (wall-clock) is therefore checked whenever someone
opens a session, not hourly. **The user opens those sessions** — say so in the pre-run
message: "I will end my turn once ~200 cells are in; open a session every few hours or
in the morning and my first act will be the PID / STOP.md / DONE.md check." A STOP at
hour 2 otherwise sits unnoticed until then, which is acceptable by rule 10 (nothing is
spending after a STOP) but should be said.

Every stage resumes on its own artifacts, so a re-run after a crash spends nothing on
what already succeeded. A cell killed mid-decide leaves `run.json` at `"running"`, which
is **not** a decision — it is retried, and the abandoned directory stays on disk.

### Stop triggers — catastrophic only

Stop the run and wake the user for these four, and **nothing else**:

1. pinned-provider failures above **25% of calls** (pilot 3: 0 of 1,679);
2. `decide` running past **3× the projection** (i.e. ~39 h);
3. a stage crashing rather than a cell failing;
4. every condition answering **> 95% one class**.

Everything else — a high repair rate, phantom contests, a thin grading cell, hundreds of
truncated cells — is **reported with its number, not stopped for**.

### After the run

- The **ten-row checklist**, re-derived from disk with a script saved beside its log, in
  the shape of `records/experiments/pilot-3/CHECKLIST.md`
  (`records/derivations/pilot-3-checks.py` is the template; point it at
  `outputs/experiments/sweep`).
- The **20-reply line-vs-prose hand check**, stratified by stance × parent verdict, as
  the audit of the `agreement` stage.
- **Every graded row hand-checked** against its `flaw.json`. Pilot 3 had 2; a full sweep
  should have enough that this is real work, and it is still the only thing standing
  between the valid-objection rate and a grader nobody audited.
- **Four transcripts read by hand** and shown to the user — a genuine contest in each
  condition and a decline on a wrong decision (`records/logs/pilot-3-paths.log` shows how
  they were selected).
- The report in the shape of `LLM_NOTES.md` §7's pilot-3 section, **plus per-subset and
  per-`label_basis` funnel tables** — the first look at whether contestability differs
  across domains, and the reason the sweep runs the whole corpus rather than a slice.
- Commit everything — `outputs/` is git-ignored, so "everything" means copying the
  sweep's small summary artifacts into `records/experiments/sweep/` in pilot 3's shape
  (`CHECKLIST.md`, `metrics.json`, `index.jsonl`, `cells.jsonl`, `experiment.json`,
  `GATE.md`-equivalent notes, and the hand-read transcripts), never `calls.jsonl` or the
  cell directories. The user pushes.

---

## 6. What NOT to do

- **Do not re-run the probe or any pilot.** They are paid for, they are reported, and
  their inputs no longer exist unchanged.
- **Do not change a model, `frequency_penalty`, or a token cap.** Every one of those was
  argued to its current value against measurements (`LLM_NOTES.md` §3l, §3m, §1b), and a
  change makes the sweep incomparable with the pilot it is budgeted from.
  `frequency_penalty = 0` is a known, accepted cost in truncated cells.
- **Do not add a provider fallback** to make a row pass. A pin that silently falls back
  averages the measurement back over whichever providers were free, invisibly.
- **Do not put pilot numbers and sweep numbers in one table** as if they measured the
  same thing. Prompts, corpora and routing changed between every pair of runs in this
  experiment's history, and each spec says so in its own header.
- **Do not loosen a parser rule** to recover cells. See ground rule 7.
- **Do not go past the full sweep without the user.** No ablations, no second sweep, no
  model comparison. `DESIGN.md`'s "Further experiments & ablations" list is theirs to
  open.

---

## 7. Pointers

**`LLM_NOTES.md` section map** (~4,620 lines; it is the working record, not a summary).
The lettered sections are in the order they were WRITTEN, not in alphabetical order —
§3f–§3g sit before §3d, and §3h sits after §3w — so use this table rather than scrolling:

| § | what |
|---|---|
| 1, 1b | the model catalog, and how the weak model was chosen — including the withdrawn floor |
| 2 | dataset findings: CELS sentence annotations, medqa's `final_answer` basis, gpqa's unusable flaw text, python800's unreliable control side |
| 3 | where the code departs from `DESIGN.md`'s wording, and why |
| 3b–3c | the port's departures from exp1; two decisions the design does not settle |
| 3f–3g | the funnel's denominators — read before quoting any graded rate |
| 3d, 3i | the two leaks, and the parser rules that came out of them |
| 3e, 3k | the two documents per run: readable `transcript.md`, verbatim `transcript_full.md` |
| 3j | the lost instruction — no prompt defined what a flaw is, until 2026-08-25 |
| 3l, 3m, 3n | what each pilot found and what was changed before the next |
| 3o | the critique-truncation fix, and the `"running"` resume rule |
| 3p, 3q | fixes from the second and third hand-off reviews (2026-08-25, 2026-08-26) |
| 3r | the user chose retry-on-resume for the sweep |
| **3s** | **the first full sweep** (2026-08-26) — the headline funnel, and the phantom correction |
| **3t** | **the re-contest** (2026-08-26): a challenger that decides last, a weak third-party recourse judge in every condition — and §3t(d), the ruling line contradicting its own reasoning |
| **3u** | **the re-rule** (2026-08-27): the ruling line fixed, every objection re-ruled, the ~6% residual measured |
| **3v** | the partisan challenger — three clauses, NO-GO (2026-08-27) |
| **3w** | the judgment-challenge variant: the slice, the harness quote check, and the auditor probe that picked nobody (2026-08-27) |
| **3x** | **the debate-only judgment-challenge run** (2026-08-28) — the paired endpoint, the two prompt revisions and the instrument revision |
| 3h | the pre-registered finding that the transcript made the weak judge *worse* |
| 4 | limitations accepted for v1 — the three that must reach the write-up |
| 5, 5b | predictions recorded before the runs; how the weak model and subsets get chosen |
| 6 | open decisions |
| 7 | build state, the order to run things, and every run with its cost |

**`records/`** — the small evidence, kept in git because `outputs/` was wiped. See
[`records/README.md`](records/README.md) for what each file backs. Nothing reads it.
Two vocabulary notes: "Step A/B/G", "D1" and the like in `GATE.md`, `LLM_NOTES.md` and
`sweep-1-estimate.txt` refer to a plan file on the wiped pod — this file replaces it;
and `GATE.md`'s thresholds were the gate *between pilot 3 and the abandoned slice*,
stricter than the sweep's four stop triggers, which are the ones that apply now.

**Scripts.** `scripts/get_tasks.py` (corpus), `scripts/pick_weak.py` (the probe),
`scripts/render_probe.py` (probe transcripts for a human), `scripts/make_slice.py` (a
read-only stratified draw, used for the abandoned `sweep-1`), `scripts/e2e_offline.py`
(the whole harness against a fake client, over real items), `scripts/run_sweep.sh` (the
five-stage driver: one `nohup`, sequential stages, `STOP.md`/`DONE.md`; tested by
`tests/test_run_sweep.py`).

**Derivations** (`records/derivations/`, stdlib only, each runs on a bare clone from
committed indexes): `sweep-checks.py` (the ten-row checklist over any finished tree),
`sweep-phantom-corrected.py` (the sweep's headline funnel), `recontest-vs-sweep.py`,
`rerule-compare.py`, `partisan-vs-neutral.py`, and **`judgment-debate-vs-alone.py`** — the
paired endpoint, the exact McNemar, the third arm, the secondaries, the per-subset table
and the post-hoc sensitivity, tested in `tests/test_derivations.py` against a
hand-computed p. `judgment-debate-smoke-pick.py` and `recontest-smoke-pick.py` write the
six-item cases files their smokes ran on; `sweep-1-provider-check.py` is the one real
pinned call to verify provider slugs before a run that calls the strong model.

**Specs.** `experiments/{pilot,pilot-2,pilot-3}.toml` are what those runs were made with
and must not be edited; nor are `sweep.toml`, `recontest*.toml`, `rerule-*.toml`,
`partisan-pilot-*.toml`, `judgment-pilot.toml` or `judgment-debate*.toml`, all of which
have run. `experiments/sweep-1.toml` is the abandoned slice. `experiments/judgment.toml`
(three conditions) and `experiments/partisan.toml` (no variant set) are the two that have
never run and have no reason to. **Nothing here is now "the one to run"** — every spec in
the directory describes a finished run, and the next one is the user's to open.

The debate-only campaign's five specs, in the order they ran:
`judgment-debate-pilot.toml` (60 cells, the first instrument check),
`judgment-debate-smoke.toml` and `-smoke-2.toml` (six cells each, the two format
wordings), `judgment-debate-smoke-3.toml` (the same six objections re-ruled after the
conclusion-line fix, via `contests_from`), `judgment-debate-pilot-2.toml` (60 cells under
both revisions), and `judgment-debate.toml` (**the run**, 1,644 cells).

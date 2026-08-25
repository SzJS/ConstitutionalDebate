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
3. **Plans are written by a planning agent and executed by another.** Do not re-plan a
   plan you were handed; do not extend one on your own initiative.
4. **Every hyperparameter is printed and confirmed before a paid run.** `--dry-run`
   prints all three tables — `[debate]`, `[client]`, `[grading]` — each field with the
   reason it is what it is. Show the user that output and wait.
5. **Every model output and every terminal output is saved under `outputs/`.** A
   generation that exists only in scrollback did not happen. `nohup … > outputs/x.log`
   or `… 2>&1 | tee outputs/x.log`.
6. **Stages run sequentially, each waited on its own PID** (`until ! ps -p $PID`).
   Never `pgrep -f <script>` — that matches the waiting shell's own command line and the
   loop never exits. Never run two paid stages concurrently.
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
    things that do stop a run.
11. **Nothing may reach across into `../exp1/`** — no import, no symlink, no path. exp2
    was ported from exp1 at `f5fc3c9` and has diverged; reading exp1 to see how it did
    something is fine, depending on it is not.

If you keep memory across sessions, seed it from sections 1, 2 and 4 of this file, and
from `LLM_NOTES.md` §4.

---

## 3. Bootstrap on a fresh pod

**Size the disk first.** A full sweep writes **~3.9 GB** under `outputs/`
(0.616 MB per cell measured on pilot 3 × 6,330 cells), the venvs are ~0.6 GB and the
image ~3.6 GB. The previous pod had **5 GB and the first sweep died on ENOSPC 80 cells
in** (`LLM_NOTES.md` §7). Ask for **20 GB or more**.

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
uv run pytest                 # expect: 325 passed, in about 4 seconds
```

Then rebuild the corpus. Nothing upstream is vendored; the archive is fetched into
`data/` (git-ignored) and only its provenance is recorded.

```bash
uv run python scripts/get_tasks.py --subset all --concat \
    2>&1 | tee outputs/get-tasks-all-concat.log
```

Expected output — if these counts differ, **stop and find out why before spending**:

```
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

wrote 2110 cases to data/cases/ftf-all.jsonl  sha256=9e479a5edbe8
```

`--concat` is what writes `data/cases/ftf-all.jsonl`, the whole-corpus bundle the sweep
spec points at: the seven per-subset bundles joined in sorted-subset order, each case
round-tripped through `load_cases` and duplicate item ids refused. It is deterministic —
the sha256 above is what a correct rebuild produces. Do **not** use `--sample`, which
rewrites `data/cases/ftf-*.jsonl` in place with a subsample and destroys the corpus every
finished run's provenance describes.

The pilot corpora can be rebuilt the same way and are byte-identical to the ones the
pilots ran on (verified 2026-08-25):

```bash
uv run python scripts/get_tasks.py --subset all --pilot 4 --pilot-longest 2 \
    --pilot-out data/cases/pilot-3.jsonl 2>&1 | tee outputs/get-tasks-pilot-3.log
# 69 pilot cases, 34 flawed / 35 sound, over 7 subsets
```

Last, the whole harness end to end against a fake client — no network, no key, real
items, both documents written for every cell and every contest:

```bash
uv run python scripts/e2e_offline.py 2>&1 | tee outputs/e2e-offline.log
# ends with: missing documents: 0 / fallbacks: 0 / withheld critiques: 0
```

---

## 4. Where things stand

Total spent so far: **$6.67**. Nothing below needs re-running, and section 6 says why.

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
the run whose rates the sweep is budgeted from. Three changes: the challenger answers one
**relative** line (`Decision: STANDS|REVERSE`) because its two absolute lines collided
with its own vocabulary; a new off-path **`agreement`** stage asks Haiku whether the
objection's *prose* argues the verdict was right or wrong; and the aimed repairs say
"for this reply only". Outcome against nine pre-registered expectations is in
`LLM_NOTES.md` §3n; the full checklist is `records/experiments/pilot-3/CHECKLIST.md`.

**The first sweep slice (`sweep-1`) was abandoned**: it died on ENOSPC partway through
`decide`, 80 of 723 cells done, on the 5 GB pod. Its spec is kept as
`experiments/sweep-1.toml` for the record; its outputs are gone. Nothing was learned from
it and nothing rests on it.

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
  rate cannot be told apart from a re-decider that capitulates to any pushback.
- **The informed judge.** Pilot 1's pre-registered stop trigger did not fire and its
  mirror image did: the challenger objected to 6 of 8 debate false positives and declined
  on every false *negative*. The question `DESIGN.md` leaves open should go back to the
  user on those grounds.
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
  21 of 139. Pilot 3: 0 of 166. Since 2026-08-26 a critique cut off by the token cap can
  also be withheld rather than killing its cell (§3o); the two cases are distinguishable
  in the records.
- **Record-length imbalance.** `decision_record_words` in pilot 3: `single` **151**,
  `self_critique` 1,884, `debate` 1,857. The two long conditions are matched to within
  1.5%; `single` is an order of magnitude shorter. That is a property of the condition,
  not of the run, and `DESIGN.md` lists a token-count ablation for it.
- **`single` never moves.** 0 of 42 contests changed a `single` decision in pilot 2, 0 of
  68 in pilot 3. A strong model asked to reconsider its own answer in its own
  conversation holds it.
- **Two denominator subtleties.** The graded rates are conditional on an objection having
  been raised, so a write-up must multiply through `challenge_raised` or it overstates
  detection (§3f). And gpqa's annotations say *where* a flaw is and not *what* it is, so
  its 382 items are graded for detection and clamped on characterisation (§3g).

---

## 5. The first sweep — exactly what to run

The spec is [`experiments/sweep.toml`](experiments/sweep.toml), already written. It is
`pilot-3.toml` with a different corpus and one explicit `copy_parent`; **nothing in the
decision path differs from the run its budget comes from.**

| | |
|---|---|
| corpus | `data/cases/ftf-all.jsonl`, 2,110 items |
| cells | 6,330 = 2,110 × 3 conditions × 1 repeat |
| cost | **~$34**, or **~$44** with 1.3× headroom, from $0.00537 per decided cell |
| wall-clock | **~13 h** of `decide` at 16/8, ~15 h for all five stages |
| disk | **~3.9 GB** under `outputs/` |
| expected loss | ≤ 14.5% of cells to truncation (~900), the accepted price of the caps |

`max_concurrency = 16` / `max_runs_in_flight = 8` is what pilot 3 **proved** — 207 cells
in 26 min with 0 non-200 responses in 1,679 attempts. `sweep-1.toml` raised it to 24/12
on a projection and died of a full disk before that could be evaluated, so 24/12 remains
unproven and is not used.

### Run order

Sequentially. Each stage `nohup … &`, waited on `$!`, teed under `outputs/`.

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
retries are on top: max_decision_attempts=2, plus at most one format repair per generation
```

```bash
# 2. VERIFY THE PROVIDER SLUGS with one real pinned call. This is not optional and no
#    dry-run can replace it: `order` takes OpenRouter provider slugs while calls.jsonl
#    records display names, the endpoints API path takes the model id with the slash
#    UNESCAPED, and an unknown slug with allow_fallbacks=false returns
#    "No endpoints found for …" — which contains "no endpoints", so client.py reads it
#    as a RETRYABLE 404 and every cell of a 13-hour stage would die slowly instead of
#    fast. records/logs/pilot-3-provider-check.log is what the check looks like.

# 3. the five paid stages, in this order, each waited on its own PID
nohup uv run exp2-experiment --spec experiments/sweep.toml --stage decide \
    > outputs/sweep-decide.log 2>&1 &
PID=$!; until ! ps -p $PID > /dev/null; do sleep 60; done
#   … then --stage contest, --stage agreement, --stage grade, --stage analyse
```

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
  the shape of `records/experiments/pilot-3/CHECKLIST.md`.
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
- Commit everything. The user pushes.

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

**`LLM_NOTES.md` section map** (2,100 lines; it is the working record, not a summary):

| § | what |
|---|---|
| 1, 1b | the model catalog, and how the weak model was chosen — including the withdrawn floor |
| 2 | dataset findings: CELS sentence annotations, medqa's `final_answer` basis, gpqa's unusable flaw text, python800's unreliable control side |
| 3 | where the code departs from `DESIGN.md`'s wording, and why |
| 3b–3c | the port's departures from exp1; two decisions the design does not settle |
| 3d, 3i | the leaks, and the parser rules that came out of them |
| 3e, 3k | the two documents per run: readable `transcript.md`, verbatim `transcript_full.md` |
| 3f–3g | the funnel's denominators |
| 3h | the pre-registered finding that the transcript made the weak judge *worse* |
| 3j | the lost instruction — no prompt defined what a flaw is, until 2026-08-25 |
| 3l, 3m, 3n | what each pilot found and what was changed before the next |
| 3o | the critique-truncation fix, and the `"running"` resume rule |
| 4 | limitations accepted for v1 — the three that must reach the write-up |
| 5, 5b | predictions recorded before the runs; how the weak model and subsets get chosen |
| 6 | open decisions |
| 7 | build state, the order to run things, and every run with its cost |

**`records/`** — the small evidence, kept in git because `outputs/` was wiped. See
[`records/README.md`](records/README.md) for what each file backs. Nothing reads it.

**Scripts.** `scripts/get_tasks.py` (corpus), `scripts/pick_weak.py` (the probe),
`scripts/render_probe.py` (probe transcripts for a human), `scripts/make_slice.py` (a
read-only stratified draw, used for the abandoned `sweep-1`), `scripts/e2e_offline.py`
(the whole harness against a fake client, over real items).

**Specs.** `experiments/{pilot,pilot-2,pilot-3}.toml` are what those runs were made with
and must not be edited. `experiments/sweep-1.toml` is the abandoned slice.
`experiments/sweep.toml` is the one to run.

# judgment-debate-6 — an argued objection against an un-argued extra round, 2026-08-30

`exp2/outputs/` is **git-ignored**. This directory is what was carried across from the two
arms: the **summary artifacts only**, so that every number quoted in `../../../LLM_NOTES.md`
§3ab can be checked against a file rather than taken on trust. The files are byte-for-byte
copies of what the run wrote under `outputs/`, except `README.md`, `CHECKLIST.md`,
`DONE.md`, `logs/stage-tails.md` and the four scan files (`arm-*/round-language.jsonl`,
`provider-mix.json`, `attempts.json`), which the derivation produced from the run trees
itself. `HANDCHECK.md` is Fable's, written from the documents in `transcripts/`.
[`PREREG.md`](PREREG.md) and [`run-all.sh`](run-all.sh) were committed at `d13400b`
**before either arm's first paid call**, in the same commit as the code.

Nothing here is an input to any stage. No code reads this directory; deleting it would break
no command. It is evidence, and it is about 7 MB.

**Read [`CHECKLIST.md`](CHECKLIST.md) first**, and its §0, before any other number.

> ## THE CONTEST ROUND BREAKS MORE AND FIXES MORE, AND THAT IS A SPLIT
> **P1 FAILED.** On the 583 cells M0 got RIGHT that both arms decided, the argued round
> broke **176** the plain round kept, against **62** the other way (**p = 7.9e-14**). P1
> predicted the contest round would break FEWER; it breaks nearly three times as many.
> **P2 HELD.** On the 263 M0 got WRONG, the argued round fixed **98** the plain round did
> not, against **35** (**p = 4.3e-08**).
>
> **That is none of the four named outcomes**, and `PREREG.md` says a split is reported as
> the split it is. The hand check names the mechanism: **adoption**. In 5 of 5 cells where R
> broke a right decision the ruling reproduces one strong reply and leaves the other
> unanswered, and it is structurally the **PRO** reply — the loser's, the one arguing for
> change. Adopting the advocate for change raises `fixed | wrong` and `broken | right`
> **together**, which is exactly the pair of numbers above.

## Why this phase exists

Every recourse number this campaign has produced came from an exchange between two **weak**
parties with nobody answering the objection: `google/gemini-2.5-flash` audits Maverick's
judgment and Maverick rules on the audit alone. On these same 896 objections
`judgment-debate-5`'s arm B overturns 34.7%, fixes 52.6% of the wrong decisions it is put to,
breaks 26.8% of the right ones and nets −23 (`LLM_NOTES.md` §3aa). The user's hypothesis was
that recourse fails **because** it is weak-vs-weak. `DESIGN.md`'s
§Contestability-debate-round ablation is the test, and this is it.

## What ran

| | arm R — the contest round | arm B — the plain round |
|---|---|---|
| spec | `experiments/jd6-round.toml` | `experiments/jd6-plain.toml` |
| stages | `rerule ruling_agreement analyse` | `rejudge analyse` |
| reads | `outputs/experiments/jd3-main` (M1's objections on M0's decisions) | `outputs/experiments/jd3-main` (M0's decisions) |
| the extra round | the two ORIGINAL debaters each reply once to the OBJECTION, simultaneously | the same two debaters play one more ORDINARY round, no objection anywhere |
| who decides | the recourse judge, on the argued exchange, under the materiality standard | the same judge, on the four-round transcript, deciding afresh |
| attempted / completed / failed | 896 / **855** / 41 | 896 / **886** / 10 |
| calls | 3,574 | 2,827 |
| spend | $7.5823 | $4.4024 |

Debaters `deepseek/deepseek-v4-flash-0731` at 0.7, pinned GMICloud → CoreWeave. Debate
judge = recourse judge = re-judge **`meta-llama/llama-4-maverick`** at 0, **pinned
`digitalocean`** — new in this campaign, because §3aa found 34% of M1's rulings served by
DeepInfra against 4.8% of jd5-B's and an unpinned judge would make "only the round moved" an
intent rather than a fact. The pin held: **856/856 recourse-judge calls and 887/887 judge
calls on DigitalOcean**. No challenger call in either arm — the objections are M1's, copied.

## Who argues what, and it is derived

`types.recourse_stance`: the debater whose assigned side the decision went **against** argues
that the alleged defects are real and material (**PRO**); the winner argues they are not
(**ANTI**). Each still argues its own assigned side, so neither attacks the case it spent
three rounds making. It is derived from the seating and the parent verdict and never stored —
`Ruling.recourse_pro_speaker` is that derivation's own answer, and both smokes checked all
eleven completed cells against it.

## The layout

| | |
|---|---|
| [`DONE.md`](DONE.md) | the run happened; do not re-run it |
| [`CHECKLIST.md`](CHECKLIST.md) | **§0 first** — the two paired tables, then every table the derivation prints |
| [`PREREG.md`](PREREG.md) | committed before the first paid call, at `d13400b` |
| [`HANDCHECK.md`](HANDCHECK.md) | Fable's read of 20 cells, and the six findings that name the mechanism |
| [`run-all.sh`](run-all.sh) | the driver, committed with PREREG.md; the working copy was `outputs/jd6-run-all.sh` |
| `arm-round/`, `arm-plain/` | `index.jsonl`, `metrics.json`, `cells.jsonl`, `experiment.json`, and the `round-language.jsonl` scan |
| `provider-mix.json`, `attempts.json` | the pin checked after the fact, and the loss with each error verbatim |
| `derivation.log` | the whole derivation, as run over the indexes in this directory |
| `logs/` | driver log, stage tails, fingerprints, both smokes' reads and costs, the provider check, the indices note, the hand-check pick, the DESIGN paragraph |
| `transcripts/` | the 20 hand-checked cells: the contest record and, where the pair is the point, the plain arm's document beside it |

## Two smokes, and the two sentences they changed

Nine cells each, **$0.1426 in total**, both outside this registration. Smoke 1 passed its
mechanism gate 6/6 but reading the prompts **as they went over the wire** found two
asymmetries that would have biased P1 toward the direction it predicts, and both were fixed
before any paid call:

* `RECOURSE_EXCHANGE_BLOCK`'s "arguments, not evidence" discount was **one-directional** — it
  discounted the PRO reply and said nothing about the ANTI one, which leans every ruling
  toward UPHOLD, and "breaks fewer" is what a lean toward UPHOLD produces. Now symmetric.
* `RECOURSE_ROUND_ANTI`'s Thinking step **presupposed a failure** ("say which of those two
  tests each one fails"). Now "say for each whether it fails either test".

Smoke 2 re-read the revision on six fresh cells weighted toward P1's population and passed.
Three digests moved between the smokes; **no paid arm ran under the old text**. Both reads
are in `logs/smoke-1-read.txt` and `logs/smoke-2-read.txt`.

**In hindsight the fix mattered less than it looked.** The lean it removed was toward UPHOLD,
and what the arms found is a judge that overturns far more than the baseline — so the defect,
had it survived, would have masked the finding rather than manufactured it.

## What this directory does not settle

The same-model property is `judgment-debate-3`'s design and is unrepaired here: Maverick
judged these debates and rules on the appeals against its own judgments, while
`RECOURSE_DEBATER_CLAUSE` tells the debaters they are addressing "a second judge, who did not
make the decision" — true of the role, false of the weights (`PREREG.md`, E3). Arm B is a
three-round debate plus an appended consolidation round rather than a native four-round one,
and arm R inherits the same property, so the paired test is unaffected and any claim about
"a four-round debate" is not made. Every absolute overturn-vs-M0 rate in arm B contains the
judge's own re-draw disagreement with itself; no floor arm was run to price it.

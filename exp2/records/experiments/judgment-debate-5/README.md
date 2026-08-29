# judgment-debate-5 — one paragraph of Step 1, put to the same judge twice, 2026-08-29

`exp2/outputs/` is **git-ignored**. This directory is what was carried across from the two
arms: the **summary artifacts only**, so that every number quoted in `../../../LLM_NOTES.md`
§3aa can be checked against a file rather than taken on trust. The files are byte-for-byte
copies of what the run wrote under `outputs/`, except `README.md`, `CHECKLIST.md`,
`logs/stage-tails.md`, the `transcripts/*__README.md` headers, the two
`arm-*/ruling-language.jsonl` scans and `derivation.log` (all produced from the copies in
`arm-fabricated/` and `arm-real/`, or from the run trees by the derivation itself).
[`PREREG.md`](PREREG.md) was committed **before either arm's first paid call**, in the same
commit as the prompt change.

Nothing here is an input to any stage. No code reads this directory; deleting it would break
no command. It is evidence, and it is about 5 MB.

**Read [`CHECKLIST.md`](CHECKLIST.md) first**, and its §0 — the two paired tables — before any
other number.

> ## THE TWO ARMS MOVE IN OPPOSITE DIRECTIONS, AND THAT IS THE RESULT
> The same judge ruled the same stored objections twice, under two versions of one prompt.
> On the **896 fabricated objections whose every `Judgment says:` quotation is invented**, the
> overturn rate **halves: 10.2% → 5.5%** (65 lost their overturn, 23 gained one, exact
> McNemar **p = 8.5e-06**). On the **896 real objections of jd3's M1**, it **rises by eight
> points: 26.6% → 34.7%** (122 gained an overturn, 49 lost one, **p = 2.3e-08**).
>
> **What the two arms cannot separate** is whether the check *licenses conviction* — a judge
> that has just verified a quotation treats the defect as established — or whether the added
> paragraph simply *changed the ruling's shape*. This record carries both and picks neither.

## Why this phase exists

`judgment-debate-4` put 896 objections whose evidence does not exist to the recourse judge and
it overturned **10.2%** of them. Eleven rulings read by hand said why: in **8 of 8 overturns**
Step 1 — *is each alleged defect real?* — was answered by looking up the **record** quotation,
which the fabricated clause keeps honest, and **never** by asking whether the judgment contains
the sentence attributed to it. The harness computes exactly that check at parse time
(`prompts.defect_quote_in_judgment`) and had never shown it to the judge. jd4 called the repair
"the cheapest thing this campaign has left" and said, twice, that **nothing in that directory
was evidence it works**. This is the evidence.

## The change, and it is one paragraph

`src/exp2/prompts.py::RECOURSE_JUDGE_USER_JUDGMENT`, as the first thing Step 1 does:

> First, for each alleged defect, find the sentence it puts under `Judgment says:` in the
> `<judgment>` above — the words must actually be there. If they are not there, the defect is
> **not real**, whatever it alleges and however well it argues… Say which quotation you could
> not find and move on; do not repair the objection on its behalf, and do not rule instead on
> what the judgment "implies". An omission is the one exception…

Everything else in the template is byte-identical, and `RECOURSE_JUDGE_USER` — the neutral
arm's — did not move at all. The new digest is
`e77eb5da04e21b64299c2fa09de427f108fc3e55f7368de2e58fbec0100cb7ca`; the one every earlier
judgment arm sent is `a758605…`; `tests/test_prompts.py` rebuilds the old Step 1 and hashes it
to prove the rest did not move. **A ruling made under the new digest is a different measurement
from one made under the old, and the two are never pooled.**

## What ran

| | arm A — fabricated | arm B — real |
|---|---|---|
| spec | `experiments/jd5-recheck-fabricated.toml` | `experiments/jd5-recheck-real.toml` |
| objections | jd4's 896, copied | jd3 M1's 896, copied |
| decisions | **M0's**, read through `decisions_from`, never re-made | M0's, same tree |
| population | the 896 cells M1 contested | the same 896, reached through the full grid |
| judge | `meta-llama/llama-4-maverick` — the model that wrote these judgments **and** ruled these objections the first time |  |
| stages | `rerule ruling_agreement analyse`, all exit 0 | same |
| window (UTC) | 23:43:00 → 00:26:46 (43 m 46 s) | 00:26:46 → 01:12:13 (45 m 27 s) |
| spend | **$2.9305** | **$3.3370** |
| wire | 1,794 records, **1,792 HTTP 200, 0 non-2xx**, 2 transport retries | 1,794 records, **1,794 HTTP 200, 0 non-2xx**, 2 parser repairs |
| ruled | **896/896** | **896/896** |

**Two arms, $6.2675, 1 h 29 m, nothing lost.** With the two six-cell smokes that preceded them
($0.0062 + $0.0042) the phase cost **$6.2779** — against jd4's $14.04 and jd3's $90.95, because
**no challenger, debater, judge or grader call was made by either arm**. `jd3-main` hashes
`dfa9bdca…` and `jd4-fabricated` hashes `6fe55bca…` before and after, unchanged: this is the
before-and-after fingerprint jd4's own stage tails said a future arm should take.

## What was found

| | old Step 1 (`b853218`) | new Step 1 (`8ec5384`) |
|---|---|---|
| **fabricated** objections overturned | 91/894 = **10.2%** | **49/896 = 5.5%** |
| **real** objections overturned | 238/895 = **26.6%** | **311/896 = 34.7%** |
| the gap between them | **+16.4 pts** | **+29.3 pts** |
| fabricated: net against M0 **[ABLATION]** | −7 (42/49), p = 0.53 | **+9** (29/20), p = 0.25 |
| real: net against M0 **[ABLATION]** | −18 (110/128), p = 0.27 — **jd3's P1** | **−23** (144/167), p = 0.21 |

**The rulings say they ran the check.** A keyword instrument over the ruling prose (§4b of the
checklist, with its hand-read precision, and it is *not* an index column) reports a **missing
quotation** in **93.1%** of arm A's rulings and **3.0%** of arm B's — two orders of magnitude,
same judge, same prompt, split only by whether the quoted sentence exists.

**And the fix is partial.** The paragraph forbids repairing the objection on the objector's
behalf. **11 of the 49 fabricated objections that still move a decision (22.4%)** are ones whose
ruling reaches for "essence", "captures the" or "paraphrase" — the judge names the sentence it
could not find and then rules on the repaired version. `PREREG.md` recorded that failure on
2 of 3 smoke cells **before** either arm ran, and said the arms were worth running anyway.

**The pre-registered floor could not fire.** `PREREG.md` fixed 13.3% as the point below which
the fix would be called too strict. Arm B's rate did not fall — it **rose**. The floor is met
and uninformative, and **it was written against the wrong risk**; that is recorded rather than
rewritten.

## What the arms cannot separate — read this before quoting either arm

**(a) Verification licenses conviction.** A judge that has just confirmed a quotation is real
treats the defect as established and moves more readily to Step 2 — so the check removes
credibility from false objections and adds it to true ones.

**(b) The added paragraph changed the ruling's shape.** It is longer and it front-loads
defect-checking, which may shift attention away from the system prompt's *"the decision stands
unless the objection shows it to be mistaken"*, with no verifying involved at all.

**Every number in this directory is consistent with both.** `transcripts/flipped-to-overturn__gpqa-119-sound`
is where the difficulty is visible: the defect is found **real** under both prompts and the flip
is at **Step 2**, not Step 1.

> **THE EXPERIMENT THAT WOULD SEPARATE THEM — first in "still owed", and not run.** Re-rule the
> same 896 real objections with the check delivered **MECHANICALLY**: the harness already
> computes `defect_quote_in_judgment` per quotation, so hand the judge its verdict instead of
> asking it to look. Same cells, same judge, one added *line* rather than one added
> *paragraph*, **~$3** — "the check" isolated from "the paragraph". It should also pin the
> judge's provider, which this campaign did not (`logs/stage-tails.md`).

## The four transcripts

| | cell | arm | why |
|---|---|---|---|
| **the check kills it** | `gpqa-63-sound` | A | jd4's own hand-check cell: *"does not explicitly say… **However, it implies**"* and overturned a right decision. Now: *"not found… this defect is **not real**"*, and the decision stands |
| **survived on "the essence"** | `python800-p03031-sound` | A | *"is not present"*, *"quoting a **non-existent sentence**"*, **"However, the essence of the objection is…"** — and it overturns anyway |
| **flipped to overturn** | `gpqa-119-sound` | B | the shape behind the +8 points: both quotations verified **present**, the defect real under **both** prompts, and **the flip is at Step 2** |
| **unchanged** | `gpqa-133-flawed` | B | a genuine self-contradiction, quotations confirmed present, same overturn as M1 — the check does not turn the judge into a proofreader |

Each has a `README.md` beside it saying what to look at, and each carries `ruling.source.json`,
**the old ruling on the same objection**, next to the new one.

## Layout

    README.md                      this file
    CHECKLIST.md                   every table, §0 (the two paired tables) first
    PREREG.md                      committed at 8ec5384 with the prompt change, before both arms
    derivation.log                 records/derivations/judgment-debate-5.py over these copies
    logs/stage-tails.md            every stage's result line, spend, wire, latency, provider mix, hashes
    arm-fabricated/                jd5-recheck-fabricated: index.jsonl, metrics.json, cells.jsonl,
                                   experiment.json, ruling-language.jsonl
    arm-real/                      jd5-recheck-real: the same five
    transcripts/                   four records, each with a README saying what to look at

## How to re-derive every number

    cd exp2
    uv run python records/derivations/judgment-debate-5.py

The defaults point at the committed indexes — this directory's two arms,
`../judgment-debate-4/arm-jd4/` and `../judgment-debate-3/`'s M1, M2 and M4 — so that command
reproduces [`derivation.log`](derivation.log) on a bare clone. Stdlib only, no network, no key,
no run tree. It imports its loaders, its exact McNemar and its Wilson interval from
`judgment-debate-4.py` rather than copying them, and `tests/test_derivations.py` pins that by
identity as well as pinning 49/896, 91→49, p = 8.50111e-06 and 311/896 against these indexes.

The keyword instrument of §4b is the one thing that needs a run tree, and its output is
committed so the default run does not:

    uv run python records/derivations/judgment-debate-5.py \
        --scan-fabricated outputs/experiments/jd5-recheck-fabricated \
        --scan-real outputs/experiments/jd5-recheck-real \
        --write-language records/experiments/judgment-debate-5

The paired tables can be redone without the script at all, which is the point of them:

    jq -r '[.cell_id, (.changed_the_decision|tostring)] | @tsv' arm-fabricated/index.jsonl \
      | sort > /tmp/new.tsv
    jq -r '[.cell_id, (.changed_the_decision|tostring)] | @tsv' \
      ../judgment-debate-4/arm-jd4/index.jsonl | sort > /tmp/old.tsv
    join /tmp/old.tsv /tmp/new.tsv | awk '{print $2, $3}' | sort | uniq -c

which prints 26 / 65 / 23 / **782** — two more than §0's 780, because it does not drop jd4's
two truncated cells, which have no ruling on that side and read as `false` here. Filtering on
`.ruling_form != null` in both files gives the table exactly.

and by hand, on any cell, by opening `transcripts/*__challenge.json`, reading the
`Judgment says:` quotation, searching the judgment in `*__transcript.md` for it, and then
reading `ruling.source.json` and `ruling.json` in that order.

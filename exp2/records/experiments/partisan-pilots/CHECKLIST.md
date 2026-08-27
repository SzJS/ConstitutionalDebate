# partisan-pilots — checklist

The partisan challenger, tried on three clauses and stopped. Three runs on 2026-08-27, all
three under `RUN_SWEEP_STAGES="contest agreement ruling_agreement grade analyse"
scripts/run_sweep.sh`, five stages each, every stage exit 0, `DONE.md` written.
**$1.2234 for the three.** The full run they were the gate for was **never started**.

**These runs decided nothing.** `decisions_from` points at the finished sweep tree, which is
read and never written; `--stage decide` refuses on a spec carrying that key. Every decision,
label and condition below is the sweep's own, and the comparison asserts that cell by cell
across all four columns before it prints a single rate.

| tree | clause | cells | genuine raised | spend | verdict |
|---|---|---|---|---|---|
| [`advocate/`](advocate) | `partisan_advocate` | 194 | **27/194 = 13.9%** | $0.4345 | fails the 2× gate |
| [`assigned/`](assigned) | `partisan_assigned` | 194 | **21/194 = 10.8%** | $0.4026 | fails the 2× gate |
| [`auditor/`](auditor) | `partisan_auditor` | 194 | **19/194 = 9.8%** | $0.3863 | fails the 2× gate |
| neutral baseline | `neutral` | 194 | **19/194 = 9.8%** | already paid | — |

Every number below is quoted from
[`partisan-vs-neutral.log`](partisan-vs-neutral.log) — the output of
`records/derivations/partisan-vs-neutral.py`, which reads four committed `index.jsonl`
files and nothing else — or from a `<clause>/metrics.json`, or from a driver log named in
the row. The blocks marked *verbatim* are copied out of that log unaltered.

**Read these three things first.**

1. **The neutral column is not a partisan column with the clause removed.** Under advocacy
   "detection" means "could an advocate find grounds", and false alarms on correct decisions
   are high by construction. The raise rates in the two columns are **different quantities
   and must never be pooled**. Every partisan tree's `metrics.json` carries a caveat saying
   so, emitted only because its rows are partisan.
2. **n is in the tens everywhere.** 194 cells, 48 of them wrong decisions, 19–28 objections
   per column. The (c) discrimination figures rest on denominators of 1 to 17. They are
   printed with their n and are not to be quoted without it.
3. **The gate was on one number only** — the genuine raise rate against 2× neutral — and
   that is the number all three clauses failed. Everything else in the rule passed in all
   three.

| # | check | threshold | result | verdict |
|---|---|---|---|---|
| 1 | every cell contested | 194/194 with a challenge on record, none missing | **194/194** in all three trees; 0 cells with no contest | **PASS** |
| 2 | parse | ≤ a few % repaired, 0 lost | challenger format repairs **23/217, 22/216, 31/225** calls (10.6% / 10.2% / 13.8%), all `no_public_label`, all in `contest`; **0** repairs in `agreement`, `ruling_agreement` or `grade`; **0** unparsed stances, **0** contradictory lines, **0** cells failed in any stage | **PASS**, and the repair rate is higher than the neutral arm's — an advocate writes longer and drifts out of the format more often |
| 3 | the source is untouched | the sweep's fingerprint identical before and after every run | `outputs/experiments/sweep` **`5e2eb4d6…`**, unchanged across all three runs (`outputs/sweep-tree.sha256`) | **PASS** |
| 4 | the copied columns are identical | asserted cell by cell, not spot-checked | `verdict`, `initially_correct`, `gold_flawed`: **194/194** identical across all four columns | **PASS** |
| 5 | the neutral baseline's declines are real declines | every joined cell's neutral stance known | **175 filled** from `../recontest/index.jsonl`, **19 cross-checked** against the re-rule tree, **0 still unknown**; the fill dies on any disagreement | **PASS** |
| 6 | (a) what the challenger did | reported, per condition and pooled | below, verbatim | **REPORT** |
| 7 | (b) the ruling line vs the judge's own prose | reported | pooled **4/28, 3/21, 2/19** against neutral's **1/19** | **REPORT**; n is too small to read a level off |
| 8 | (c) what the judge overturned | reported with n | pooled discrimination **+17.1 / −16.2 / −40.0 pts** against neutral's **+40.5** | **REPORT**; denominators of 4 to 17 |
| 9 | (g) the go/no-go rule, computed | the plan's step-6 rule | **all three clauses FAIL** the 2× gate; (i), (ii) and (iii) PASS in all three | **NO-GO** |
| 10 | (h) what advocacy adds, cell by cell | reported | **+15 / +12 / +11** genuine objections added, **−7 / −10 / −11** neutral objections dropped | **REPORT**; the adds and the drops nearly cancel |
| 11 | ops | reported | **$0.4345 / $0.4026 / $0.3863**; this tree's own calls **1,809 / 1,791 / 1,793 attempts, every one HTTP 200**, zero non-2xx and zero status-less; wall clock **3 m 39 s / 3 m 23 s / 3 m 23 s** | **REPORT** |
| 12 | hand-read | the clauses read against the transcripts | Fable read the declines on the two `debate` cells the three clauses agree on; see "What this settles" | **DONE** |

---

## (a) WHAT THE CHALLENGER DID — pooled, all four columns

*Verbatim from `partisan-vs-neutral.log`.*

```
--- POOLED ---
                                    rerule-recontest        partisan-pilot-advocate partisan-pilot-assigned partisan-pilot-auditor  
------------------------------------------------------------------------------------------------------------------------------------
cells                               194                     194                     194                     194                     
  with a challenge on record        194                     194                     194                     194                     
objections raised                   19/194 9.8%             28/194 14.4%            21/194 10.8%            19/194 9.8%             
GENUINE raised (prose WRONG)        19/194 9.8%             27/194 13.9%            21/194 10.8%            19/194 9.8%             
phantom share of raised             0/19 0.0%               1/28 3.6%               0/21 0.0%               0/19 0.0%               
prose NEITHER, of raised            0/19 0.0%               0/28 0.0%               0/21 0.0%               0/19 0.0%               
declined                            175/194 90.2%           166/194 85.6%           173/194 89.2%           175/194 90.2%           
  declined | CORRECT decision       134/146 91.8%           128/146 87.7%           129/146 88.4%           131/146 89.7%           
  declined | WRONG decision         41/48 85.4%             38/48 79.2%             44/48 91.7%             44/48 91.7%             
agrees                              0                       0                       0                       0                       
stance unclear (unparsed line)      0                       0                       0                       0                       
contradictory line                  0                       0                       0                       0                       
no contest on record                0                       0                       0                       0
```

Per condition, the genuine raise rate — the ablation's one job, in the three places it had
to do it:

| condition | cells | neutral | `advocate` | `assigned` | `auditor` |
|---|---|---|---|---|---|
| `single` | 68 | 3/68 = 4.4% | **8/68 = 11.8%** | 4/68 = 5.9% | 6/68 = 8.8% |
| `self_critique` | 66 | 15/66 = 22.7% | **16/66 = 24.2%** | 15/66 = 22.7% | 11/66 = 16.7% |
| `debate` | 60 | 1/60 = 1.7% | **3/60 = 5.0%** | 2/60 = 3.3% | 2/60 = 3.3% |
| **POOLED** | **194** | **19/194 = 9.8%** | **27/194 = 13.9%** | **21/194 = 10.8%** | **19/194 = 9.8%** |

`debate` is where n was thinnest and where the ablation was most needed. The best clause
moves it from **1** objection to **3**. On `self_critique`, where the neutral challenger
already objects on 22.7% of cells, advocacy adds **one** objection and the auditor clause
**loses four**.

The decline rates are the other half of the same fact. Advocacy barely moves them:

| | neutral | `advocate` | `assigned` | `auditor` |
|---|---|---|---|---|
| declined on a **CORRECT** decision | 134/146 = 91.8% | 128/146 = 87.7% | 129/146 = 88.4% | 131/146 = 89.7% |
| declined on a **WRONG** decision | 41/48 = 85.4% | 38/48 = 79.2% | 44/48 = 91.7% | 44/48 = 91.7% |

Criterion (ii) of the gate asked for *some* declines on correct decisions, because a 0%
rate would mean "let it stand" was dead and the advocate was manufacturing a case. It is not
0%. It is **88–90%**, four points below the neutral challenger's. Two of the three clauses
decline on wrong decisions *more* often than the neutral challenger does.

---

## (b) THE RULING LINE vs THE JUDGE'S OWN PROSE — pooled

*Verbatim from `partisan-vs-neutral.log`.*

```
--- POOLED ---
                                    rerule-recontest        partisan-pilot-advocate partisan-pilot-assigned partisan-pilot-auditor  
------------------------------------------------------------------------------------------------------------------------------------
rulings made                        19                      28                      21                      19                      
ruling_line_mismatch                1/19 5.3%               4/28 14.3%              3/21 14.3%              2/19 10.5%              
  prose FLAWED                      8                       15                      8                       9                       
  prose SOUND                       11                      13                      13                      10                      
  prose NEITHER                     0                       0                       0                       0
```

The `ruling_agreement` instrument §3u introduced, running here for the fourth, fifth and
sixth time. `rerule-recontest` measured **5.8%** over 464 rulings and `rerule-sweep`
**6.0%** over 1,129; these three columns are **14.3%, 14.3%, 10.5%** over **28, 21 and 19**.
At those denominators one ruling is 3.6 to 5.3 points, so this is not evidence that
advocacy raises the residual — it is what a 6% rate looks like on twenty draws. It is
reported because it bounds every number in (c) and (d), not because it says anything.

---

## (c) WHAT THE JUDGE OVERTURNED, BY WHAT WAS ACTUALLY OBJECTED TO — pooled

*Verbatim from `partisan-vs-neutral.log`.*

```
--- POOLED ---
                                    rerule-recontest        partisan-pilot-advocate partisan-pilot-assigned partisan-pilot-auditor  
------------------------------------------------------------------------------------------------------------------------------------
overturn | phantom                  0/0 n/a                 0/1 0.0%                0/0 n/a                 0/0 n/a                 
overturn | genuine|wrong            4/7 57.1%               7/10 70.0%              1/4 25.0%               0/4 0.0%                
overturn | genuine|corr             2/12 16.7%              9/17 52.9%              7/17 41.2%              6/15 40.0%              
overturn | other/NEITHER            0/0 n/a                 0/0 n/a                 0/0 n/a                 0/0 n/a                 
DISCRIMINATION                      +40.5 pts               +17.1 pts               -16.2 pts               -40.0 pts               
raised with no ruling               0                       0                       0                       0
```

This is the table the whole ablation was for: the judge's discrimination, which the plan
wanted measured on hundreds of cells per condition instead of tens. It is measured on
**4 to 17**. The neutral baseline's **+40.5 pts** rests on 7 and 12; `advocate`'s
**+17.1 pts** on 10 and 17. The one clause that raises n at all raises it from 19 to 28
objections, and it moves the point estimate by 23 points — which is what a denominator of
ten does, and is precisely why the ablation was proposed. It did not deliver the n that
would have settled it.

---

## (g) GO / NO-GO — the plan's step-6 rule, computed

*Verbatim from `partisan-vs-neutral.log`. The block computes the rule; it decides nothing.*

```
====================================================================================================================================
(g) GO / NO-GO  (the plan's step-6 rule, computed)
====================================================================================================================================
The rule: GO with the clause with the HIGHEST genuine raise rate, subject to
  (i)   phantom share of raised <= 13% (the neutral run's all-contests share)
  (ii)  at least some declines on CORRECT decisions — a 0% decline rate means
        'let it stand' is dead and the advocate is manufacturing a case
  (iii) parse failures ~ 0 (index-visible proxy: stance `unclear` and
        `challenge_contradictory`; true parse/repair counts live in the run
        log, not the index)
and only if some clause reaches >= 2x the NEUTRAL POOLED genuine raise rate.
This block does not decide anything. It prints the four clauses of the rule
with their numbers so the decision is made from them and can be re-checked.

neutral pooled: genuine raise 19/194 9.8%   raised 19/194 9.8%   phantom share of raised 0/19 0.0%
neutral gate:   >= 2x 9.8% = 19.6% genuine raise

clause                                  partisan-pilot-advocate partisan-pilot-assigned partisan-pilot-auditor  
------------------------------------------------------------------------------------------------------------------------------------
genuine raise rate                      27/194 13.9%            21/194 10.8%            19/194 9.8%             
  x neutral pooled (9.8%)               1.42x                   1.11x                   1.00x                   
  >= 2x neutral?                        FAIL                    FAIL                    FAIL                    
phantom share of raised                 1/28 3.6%               0/21 0.0%               0/19 0.0%               
  <= 13%?                               PASS                    PASS                    PASS                    
declines on CORRECT decisions           128/146 87.7%           129/146 88.4%           131/146 89.7%           
  > 0?                                  PASS                    PASS                    PASS                    
unclear + contradictory lines           0+0                     0+0                     0+0                     
  ~ 0?                                  PASS                    PASS                    PASS                    
------------------------------------------------------------------------------------------------------------------------------------
all four clauses                        FAIL                    FAIL                    FAIL                    

NO-GO
  partisan-pilot-advocate: fails 2x neutral
  partisan-pilot-assigned: fails 2x neutral
  partisan-pilot-auditor: fails 2x neutral
  Per the plan: stop, record the results in LLM_NOTES, report to the user,
  and do NOT run the full sweep.

Fable decides. The hand check of the transcripts is the other half of it: does
the advocate argue the assigned side, and is its Decision: line consistent with
its own prose? Numbers alone cannot answer that.
```

**Fable decided NO-GO on 2026-08-27.** `experiments/partisan.toml` still refuses to run —
its `challenger_variant` line is commented out, and `experiment_cli` refuses **any** spec
whose name contains `partisan` and states no variant, on a dry run and on a real one alike.
No `"partisan"` alias was ever assigned to a clause.
The ~$22 full run was not started.

---

## (h) PER-CELL STANCE TRANSITIONS — neutral → partisan

*Verbatim from `partisan-vs-neutral.log`.*

```
====================================================================================================================================
(h) PER-CELL STANCE TRANSITIONS  neutral -> partisan
====================================================================================================================================
What advocacy ADDS, cell by cell: which declines became objections, whether
those objections were genuine or phantom, and which neutral objections the
advocate dropped. Rows = the neutral stance, columns = the partisan stance.
`no contest` is a cell with no challenge on record in that index.

--- neutral -> partisan-pilot-advocate ---
neutral \ partisan       contests|genuine   contests|phantom           declined    total
------------------------------------------------------------------------------------------------------------------------------------
contests|genuine                       12                  0                  7       19
declined                               15                  1                159      175
------------------------------------------------------------------------------------------------------------------------------------
total                                  27                  1                166      194

  genuine objections ADDED by advocacy   15
  phantom objections added by advocacy   1
  neutral objections the advocate DROPPED  7
  genuine in both                        12

--- neutral -> partisan-pilot-assigned ---
neutral \ partisan       contests|genuine           declined    total
------------------------------------------------------------------------------------------------------------------------------------
contests|genuine                        9                 10       19
declined                               12                163      175
------------------------------------------------------------------------------------------------------------------------------------
total                                  21                173      194

  genuine objections ADDED by advocacy   12
  phantom objections added by advocacy   0
  neutral objections the advocate DROPPED  10
  genuine in both                        9

--- neutral -> partisan-pilot-auditor ---
neutral \ partisan       contests|genuine           declined    total
------------------------------------------------------------------------------------------------------------------------------------
contests|genuine                        8                 11       19
declined                               11                164      175
------------------------------------------------------------------------------------------------------------------------------------
total                                  19                175      194

  genuine objections ADDED by advocacy   11
  phantom objections added by advocacy   0
  neutral objections the advocate DROPPED  11
  genuine in both                        8
```

Read the diagonal. Of the **19** cells the neutral challenger objected on, the advocate
keeps **12** and drops **7**; the assigned clause keeps **9** and drops **10**; the auditor
clause keeps **8** and drops **11**. Advocacy is not adding a layer on top of the neutral
challenger's objections — it is **resampling the same challenger at temperature 0.7**, with
a slightly different prior. The auditor clause adds 11 objections and loses 11, and lands on
exactly the neutral pooled rate.

That is the single most informative table here, and it is why the reading below is about the
model and not about the wording.

---

## What this settles

**The standpoint instruction does not move `gpt-4.1-nano` on these records.** Fable's
reading of the declines, recorded verbatim:

> on `gpqa-127-sound__debate` and `gpqa-161-flawed__debate` — both WRONG decisions — every
> partisan clause opens with "The verdict … is correct" and restates the judge's own grounds,
> in nearly the same words the NEUTRAL re-contest challenger used on the same cells
> ("explicitly flagged as an assumption… a legitimate mathematical strategy"). The standpoint
> instruction does not move gpt-4.1-nano at all: a challenger that reasons before committing,
> over a record that already contains both sides and a verdict, sides with the verdict
> regardless of which side it is told to represent. The low objection rate is a property of
> the challenger model reading these records, not of the neutral instruction, and the
> ablation cannot raise n with this model.

Both cells are in this directory's indices and both are `declined` in all three trees:
`gpqa-127-sound__debate__r1` (decision FLAWED, `initially_correct` false) and
`gpqa-161-flawed__debate__r1` (decision SOUND, `initially_correct` false). Their prose is
read `RIGHT` by the `agreement` instrument in every column — the challenger's own words say
the verdict was right, under a clause that told it to argue the verdict was wrong.

**Three consequences, and they are the whole of what these pilots settle.**

1. **The low neutral objection rate is not an artifact of the neutral instruction.** That was
   the live alternative: that "you are not required to find fault" was suppressing objections
   the model could have made. Three clauses that say the opposite, one of them in as many
   words, do not recover them. The rate is the model's.
2. **The recourse numbers stay at the neutral n**, and every caveat §3s, §3t and §3u carry
   about small denominators stands unchanged. Nothing in the headline moves.
3. **The ablation is not refuted, only unrun on this model.** It exists in code, it is
   tested, the four specs are committed and the record carries `challenge_arm`. A stronger
   challenger — one that will hold a position it was assigned against a record that
   contradicts it — would run it for the same ~$22, and that is a model choice for the user
   to make, not a bug to fix.

**What these pilots do not settle.** Whether a *stronger* challenger under the same clauses
would raise n; whether a record that did **not** contain the verdict and its grounds would
free the challenger to argue (the challenger is shown the decision by design — contesting a
decision it cannot see is a different experiment); and whether the wording could be pushed
further than these three. The plan allowed **no iteration beyond these three clauses**, and
none was done.

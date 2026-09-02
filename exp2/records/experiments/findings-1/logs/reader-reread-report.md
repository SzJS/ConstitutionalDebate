# fd1 — the pilot rulings re-read with the revised reader prompt

One Haiku call per stored pilot ruling under the R12g reader prompts, made through `recourse.judge_ruling_prose` so the wire call is the stage's. Neither pilot tree was written to: the OLD column is the reading stored in each contest's `ruling_agreement.json` at run time, the NEW column is today's.

`mismatch` is `prose_conclusion != line_conclusion`; NEITHER counts as a mismatch, as it does everywhere in this codebase. `void-only` rulings are the ones R12g stops computing the column for at all — their verdict is derived with every one of the judge's lines discarded — and they are shown apart rather than dropped here.

## Mismatch rate, old prompt against new

| arm | rulings | OLD mismatch | NEW mismatch | NEW, excluding void-only |
|---|---|---|---|---|
| `fd1-pilot-strong` | 22 | 2/22 (9.1%) | 1/22 (4.5%) | 1/19 (5.3%) |
| `fd1-pilot-weak` | 44 | 17/44 (38.6%) | 3/44 (6.8%) | 1/36 (2.8%) |
| `ALL` | 66 | 19/66 (28.8%) | 4/66 (6.1%) | 2/55 (3.6%) |

## Old against new, per ruling

**fd1-pilot-strong** — mismatch old (rows) x new (columns)

| old \ new | consistent | MISMATCH |
|---|---|---|
| consistent | 19 | 1 |
| MISMATCH | 2 | 0 |

**fd1-pilot-strong** — the reader's own word, old (rows) x new (columns)

| old \ new | CONSISTENT | INCONSISTENT | NEITHER | (unreadable) |
|---|---|---|---|---|
| CONSISTENT | 19 | 1 | 0 | 0 |
| INCONSISTENT | 2 | 0 | 0 | 0 |
| NEITHER | 0 | 0 | 0 | 0 |
| (unreadable) | 0 | 0 | 0 | 0 |

**fd1-pilot-weak** — mismatch old (rows) x new (columns)

| old \ new | consistent | MISMATCH |
|---|---|---|
| consistent | 26 | 1 |
| MISMATCH | 15 | 2 |

**fd1-pilot-weak** — the reader's own word, old (rows) x new (columns)

| old \ new | CONSISTENT | INCONSISTENT | NEITHER | (unreadable) |
|---|---|---|---|---|
| CONSISTENT | 26 | 0 | 1 | 0 |
| INCONSISTENT | 15 | 0 | 1 | 0 |
| NEITHER | 0 | 0 | 1 | 0 |
| (unreadable) | 0 | 0 | 0 | 0 |

**ALL** — mismatch old (rows) x new (columns)

| old \ new | consistent | MISMATCH |
|---|---|---|
| consistent | 45 | 2 |
| MISMATCH | 17 | 2 |

**ALL** — the reader's own word, old (rows) x new (columns)

| old \ new | CONSISTENT | INCONSISTENT | NEITHER | (unreadable) |
|---|---|---|---|---|
| CONSISTENT | 45 | 1 | 1 | 0 |
| INCONSISTENT | 17 | 0 | 1 | 0 |
| NEITHER | 0 | 0 | 1 | 0 |
| (unreadable) | 0 | 0 | 0 | 0 |

## Every ruling the NEW reader still marks a mismatch

Few enough to name. `void-only` rulings are the ones `build_index` no longer computes the column for at all, so the rate that matters is the one over the rest.

| arm | cell | old reading | new reading | void-only |
|---|---|---|---|---|
| `fd1-pilot-weak` | `lojban-stim175_gpt4_A-s4__debate__r1` | INCONSISTENT | NEITHER | True |
| `fd1-pilot-weak` | `surgery-sur20_gpt3-5_A-s4__debate__r1` | NEITHER | NEITHER | False |
| `fd1-pilot-weak` | `theoremqa-solutions-kite2-png-flawed__debate__r1` | CONSISTENT | NEITHER | True |
| `fd1-pilot-strong` | `gpqa-19-flawed__debate__r1` | CONSISTENT | INCONSISTENT | False |

## 6 rulings where the two readers DISAGREE

Printed for the hand check: the tail of the ruling's own prose (the text the reader was given, minus its decision lines), the lines it ended on, and both readings. The question for the reviewer is which reader is right, not which rate is lower.

### `fd1-pilot-weak` — `gpqa-164-sound__debate__r1`

* old reading **INCONSISTENT** → `prose_conclusion` SOUND, mismatch True
* new reading **CONSISTENT** → `prose_conclusion` FLAWED, mismatch False
* the ruling's own verdict FLAWED, parent SOUND, 2 contests, void-only False

The ruling's lines:

```
Contest 1: FLAW
Contest 2: FLAW
```

The last 400 characters of the ruling's prose:

```
ext (oligomerization), which might be seen as consistent. However, the critical point is whether this context is relevant to the dual catalyst system.

The finding is mistaken because the solution's reasoning, while consistent in its application of the fact about aluminoxanes, does not address the dual catalyst system's specifics directly.

The finding is mistaken; the passage does contain a flaw.
```

### `fd1-pilot-weak` — `law-con1_gpt3-5_A-s2__debate__r1`

* old reading **INCONSISTENT** → `prose_conclusion` SOUND, mismatch True
* new reading **CONSISTENT** → `prose_conclusion` FLAWED, mismatch False
* the ruling's own verdict FLAWED, parent SOUND, 1 contests, void-only False

The ruling's lines:

```
Contest 1: FLAW
```

The last 400 characters of the ruling's prose:

```
y that it is a crucial justification for excusing performance. The implication that lack of specification is sufficient for excusing performance, without directly addressing the "basic assumption" requirement, can be seen as misleading. The original finding (Finding 3) ruled this as "NOT A FLAW", but the contest argues it should be "FLAW".

The finding is mistaken; the passage does contain a flaw.
```

### `fd1-pilot-weak` — `law-con5_gpt3-5_B-s5__debate__r1`

* old reading **INCONSISTENT** → `prose_conclusion` SOUND, mismatch True
* new reading **CONSISTENT** → `prose_conclusion` FLAWED, mismatch False
* the ruling's own verdict FLAWED, parent SOUND, 1 contests, void-only False

The ruling's lines:

```
Contest 1: FLAW
```

The last 400 characters of the ruling's prose:

```
tentially misleading, this meets the criterion for being a flaw.

The finding's ruling stands unless the contest shows it mistaken. The contest shows that the sentence being misleading is sufficient to be considered a flaw, according to the given definition. Thus, the finding is mistaken.

The finding is mistaken; the passage does contain a flaw.

## Step 3: Formatting the final line for Contest 1
```

### `fd1-pilot-weak` — `law-con5_gpt4_B-s4__debate__r1`

* old reading **INCONSISTENT** → `prose_conclusion` FLAWED, mismatch True
* new reading **CONSISTENT** → `prose_conclusion` SOUND, mismatch False
* the ruling's own verdict SOUND, parent SOUND, 1 contests, void-only False

The ruling's lines:

```
Contest 1: NOT A FLAW
```

The last 400 characters of the ruling's prose:

```
ng of the need for exceptions, supporting the view that Sentence 4 is not intended to be exhaustive.

The contest does not show that the finding is mistaken because it does not demonstrate that Sentence 4 is affirmatively misleading to the point of being flawed. The sentence's general nature and the acknowledgment of exceptions through "generally" support the finding's ruling.

The finding stands.
```

### `fd1-pilot-weak` — `law-evi2_gpt4_A-s4__debate__r1`

* old reading **INCONSISTENT** → `prose_conclusion` FLAWED, mismatch True
* new reading **CONSISTENT** → `prose_conclusion` SOUND, mismatch False
* the ruling's own verdict SOUND, parent SOUND, 1 contests, void-only False

The ruling's lines:

```
Contest 1: NOT A FLAW
```

The last 400 characters of the ruling's prose:

```
promote candor and the administration of justice, the sentence accurately describes the privilege's operative function.

The contest does not show that the sentence is mistaken in its description of the privilege's purpose. The distinction between means and end, while doctrinally relevant, does not render the sentence flawed as it accurately describes the privilege's function.

The finding stands.
```

### `fd1-pilot-weak` — `lojban-stim145_gpt4_B-s1__debate__r1`

* old reading **INCONSISTENT** → `prose_conclusion` FLAWED, mismatch True
* new reading **CONSISTENT** → `prose_conclusion` SOUND, mismatch False
* the ruling's own verdict SOUND, parent SOUND, 1 contests, void-only True

The ruling's lines:

```
Contest 1: NOT A FLAW
```

The last 400 characters of the ruling's prose:

```
he finding's ruling that the sentence is "NOT A FLAW" stands because, while the sentence makes a claim about the addressee's mental state, it is a reasonable interpretation based on the context provided by the problem. The use of "I see" suggests observation or inference rather than absolute certainty, and the context supports the plausibility of the addressee considering (A).

The finding stands.
```

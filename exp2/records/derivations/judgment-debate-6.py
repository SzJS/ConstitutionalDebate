"""judgment-debate-6 — an argued objection against an un-argued extra round.

    cd exp2
    uv run python records/derivations/judgment-debate-6.py \
        2>&1 | tee outputs/judgment-debate-6-derivation.log

Stdlib only. It reads `index.jsonl` files and two small scan files and nothing else, so
it runs on a blank machine straight after `git clone` — no run tree, no `calls.jsonl`, no
network, no key. Every path is a flag, so the same script runs against the committed
indexes in `records/experiments/judgment-debate-{5,6}/` and against a live
`outputs/experiments/` tree without editing a line; `--help` lists them all. An index
that is missing loads as `{}` and its arm prints NOT RUN rather than crashing.

The exact McNemar, the Wilson interval, the paired block, the population restriction and
the loaders are IMPORTED from `judgment-debate-4.py` (through `judgment-debate-5.py`,
which also gives `ruling_pairs` and `paired_ruling_block`) rather than copied: these
files print rates about the same 896 cells side by side in one write-up, and a definition
that drifted between them would be invisible.

THE QUESTION. Every recourse number this campaign has produced comes from an exchange
between two WEAK parties with nobody answering the objection. On these 896 cells the
latest ruling prompt overturns 34.7%, fixes 52.6% of the wrong decisions it is put to and
breaks 26.8% of the right ones, net -23 (p 0.21). The user's hypothesis is that recourse
fails because it is weak-vs-weak. So arm R puts a REPLY in front of the judge — the two
original strong debaters argue whether the objection should change the ruling — and arm B
is the control that separates "the objection was argued" from "there was one more round of
strong argument at all".

    R  jd6-round   M1's 896 objections ARGUED by the two original debaters, then ruled
    B  jd6-plain   the same 896 cells, ONE MORE ORDINARY ROUND, then re-judged

THE ENDPOINT IS NOT THE NET, and section (1) is where it lives:

    P1  on the initially-CORRECT cells, R BREAKS FEWER than B — exact two-sided McNemar
        on the discordant pairs of AFTER-STATES.
    P2  on the initially-WRONG cells, R FIXES AT LEAST AS MANY as B.

The user's endpoint is P1 and P2 together. The net is dominated by the 26% base rate of
wrong decisions (§3y) and is reported in section (3) as an ABLATION.

THE ONE THING A READER MUST HOLD ONTO: THE TWO ARMS PUT THEIR STATES IN DIFFERENT
COLUMNS, and this file is the only place that fact is written down.

    arm R is a RERULE. Its index row's `initially_correct` is M0's decision — the
        BEFORE-state — and `final_correct` is the ruling's — the AFTER-state. That is
        `judgment-debate-4.py`'s `before_state` / `after_state` unchanged.
    arm B is a REJUDGE. It made its own decision, so its row's `initially_correct` is the
        AFTER-state and M0's is `source_correct`, carried in the manifest and the index.

Reading either arm with the other's accessor silently inverts it, so the two live in
`before_of` / `after_of` below, keyed on the arm, and nothing else in this file touches
those columns.

THE STATED CAVEAT, and it is pre-registered. Every "overturn vs M0" rate in arm B
contains Maverick's own disagreement with itself on a re-draw as well as the extra
round's effect; no floor arm was run to price it. The PAIRED R-vs-B test of section (1)
is free of it — both arms' after-states come from the same judge after one extra round —
and the absolute rates of sections (2) and (3) are not.

SECTION (4) IS DESCRIPTIVE AND CARRIES A PROVIDER CAVEAT. jd5-B ruled these same
objections with NO round, and it is the natural third column — but its judge was
UNPINNED (34% of M1's rulings on DeepInfra against 4.8% of jd5-B's, §3aa) while both jd6
arms pin DigitalOcean, so R-vs-jd5-B mixes the round with the routing. It is printed as a
2x2 and never as an endpoint.

SECTION (5) IS A KEYWORD INSTRUMENT and is labelled one everywhere it appears. No index
carries "did the ANTI reply dispute a quotation" or "does the ruling cite the exchange",
so both are read off text by regex, and both are re-derivable with `--scan-round`.

Definitions shared with `judgment-debate-{3,4,5}.py` and they must stay identical:

    fixed / broken  not correct before and correct after / the converse
    overturn        the after-state verdict differs from the decision the arm was put to
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import re
from collections import Counter
from pathlib import Path

_JD5_PATH = Path(__file__).resolve().with_name("judgment-debate-5.py")
_spec = importlib.util.spec_from_file_location("judgment_debate_5", _JD5_PATH)
jd5 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(jd5)

# Re-exported so this module's readers do not have to know where they came from. They are
# the SAME objects, which is the point.
load = jd5.load
restrict = jd5.restrict
mcnemar_exact = jd5.mcnemar_exact
wilson = jd5.wilson
pct = jd5.pct
rate = jd5.rate
interval = jd5.interval
acc = jd5.acc
head = jd5.head
rule = jd5.rule
verdict_at = jd5.verdict_at
paired_block = jd5.paired_block
paired_counts = jd5.paired_counts
ruling_pairs = jd5.ruling_pairs
paired_ruling_block = jd5.paired_ruling_block
ALPHA = jd5.ALPHA
W = jd5.W
VERDICTS = jd5.VERDICTS


# --------------------------------------------------------------------------- #
# the two arms put their states in different columns
# --------------------------------------------------------------------------- #


def before_of(row: dict, arm: str) -> bool | None:
    """M0's decision on this cell — the BEFORE-state, in either arm.

    In R it is the row's own `initially_correct`, because a rerule decides nothing and
    the decision it was handed is M0's. In B it is `source_correct`, because that arm
    MADE a decision and its `initially_correct` is the new one.
    """
    return row.get("initially_correct") if arm == "R" else row.get("source_correct")


def after_of(row: dict, arm: str) -> bool | None:
    """The cell's state once the arm has had its turn."""
    if arm == "R":
        before = row.get("initially_correct")
        final = row.get("final_correct")
        return before if final is None else bool(final)
    return row.get("initially_correct")


def overturned_of(row: dict, arm: str) -> bool | None:
    """Did the arm move the verdict away from M0's?"""
    if arm == "R":
        return None if row.get("ruling_form") is None else bool(
            row.get("changed_the_decision"))
    if row.get("verdict") is None or row.get("source_verdict") is None:
        return None
    return row["verdict"] != row["source_verdict"]


def ruled(rows: dict[str, dict], arm: str) -> dict[str, dict]:
    """The cells this arm actually decided. A cell whose ruling or judgment truncated was
    never put to that judge and cannot be counted as an uphold — `judgment-debate-4.py`'s
    rule, applied to whichever column the arm uses."""
    return {c: r for c, r in rows.items() if overturned_of(r, arm) is not None}


def paired_states(a: dict[str, dict], b: dict[str, dict], cells: set[str],
                  *, only: str | None = None):
    """(cell, R's after-state, B's after-state) for every cell BOTH arms decided.

    ``only`` restricts to the cells whose BEFORE-state was right ("right") or wrong
    ("wrong"), which is what makes P1 and P2 two tests rather than one. The before-state
    is read from arm R's row — it is M0's decision and the same fact in both arms — and
    the two arms are asserted to agree wherever B carries it, because a disagreement
    would mean the arms are not on the same cells.

    A cell one arm never actually decided LEAVES the table rather than entering it at its
    before-state. `judgment-debate-4.py`'s `after_state` keeps such a cell where it was,
    which is the right rule for an accuracy net — a decision nobody disturbed stands — and
    the wrong one here: an R cell whose ruling truncated was never put to that judge, and
    counting it as a concordant pair would dilute the discordant counts P1 and P2 are
    computed from.
    """
    out, disagreed = [], 0
    for cell_id in sorted(cells):
        left, right = a.get(cell_id), b.get(cell_id)
        if not left or not right:
            continue
        if overturned_of(left, "R") is None or overturned_of(right, "B") is None:
            continue
        before = before_of(left, "R")
        if before is None:
            continue
        b_before = before_of(right, "B")
        if b_before is not None and bool(b_before) != bool(before):
            disagreed += 1
            continue
        after_r, after_b = after_of(left, "R"), after_of(right, "B")
        if after_r is None or after_b is None:
            continue
        if only == "right" and not before:
            continue
        if only == "wrong" and before:
            continue
        out.append((cell_id, bool(after_r), bool(after_b)))
    return out, disagreed


# --------------------------------------------------------------------------- #
# (5) the keyword instruments — the only things here that are not in an index
# --------------------------------------------------------------------------- #
#
# READ THIS BEFORE QUOTING SECTION (5). These are regexes over text, not facts the harness
# computed. They are printed as a CONTRAST between arms and stances, never as an absolute
# rate, and a hand read of a sample belongs in the CHECKLIST beside them.

# The ANTI debater's job is to say a defect is not real or not material. "Disputes a
# quotation" is the narrower half — the sentence is not in the judgment, or the record does
# not say what is claimed — and it is what the existence check of jd5 asked the JUDGE to do
# for itself.
DISPUTES_QUOTATION = re.compile(
    r"(?:judgment|record)[^.\n]{0,80}?"
    r"(?:does not (?:say|contain|state)|never (?:says|states)|nowhere|no such"
    r"|not (?:found|present|there)|misquot|cannot be found|appears nowhere)",
    re.IGNORECASE)
# The ruling citing the exchange rather than only the objection: it names a debater, or
# names the exchange as such.
CITES_EXCHANGE = re.compile(
    r"\b(?:Alice|Bob)\b|\bexchange\b|\bboth debaters\b|\bthe repl(?:y|ies)\b",
    re.IGNORECASE)


# THE GLUED-LABEL HABIT, seen in the smoke and not new to this round: the model writes
# `Argument:` MID-SENTENCE after some planning text, so `parse_debater_output` — which
# takes the LAST label at a line start — publishes the planning text as part of the public
# argument. It is a format defect the parser cannot catch, it is visible in the published
# record, and the question the write-up has to answer is whether the contest round RAISED
# the rate or inherited it, which is why the same count is taken over the PARENT rounds
# 1-3 of the very same cells.
GLUED_LABEL = re.compile(r"Argument:")

# The word limit the debaters were given. Overruns are RECORDED and never truncated — the
# text is what was said — so the count is an instrument and not a fault, and it is split by
# stance because smoke 1's two heavy overruns (441 and 687 words) were BOTH PRO turns and
# a systematic length difference between the two stances would be a length difference in
# what the judge reads on each side of the objection.
WORD_LIMIT = 400


def glued_argument_label(argument: str) -> bool:
    """Whether a PUBLISHED argument still contains an `Argument:` label of its own."""
    return bool(GLUED_LABEL.search(argument or ""))


def turn_flags(turn: dict) -> dict:
    """The per-turn facts sections (5) and (6) read, off one stored `Turn`."""
    return {
        "glued_label": glued_argument_label(turn.get("argument")),
        "finish_reason": turn.get("finish_reason"),
        "truncated": turn.get("finish_reason") == "length",
        "words": turn.get("word_count"),
        "parse_mode": turn.get("parse_mode"),
        "repairs": turn.get("repair_attempts"),
    }


def parent_glued(path: Path, boundary: int | None = None) -> tuple[int, int]:
    """(turns, glued turns) over the rounds a stored transcript already had.

    ``boundary`` is the last parent round; ``None`` means every round in the file. Read
    out of the ARM's own copy of the parent — a contest carries `parent/transcript.json`
    and an extended rejudge carries the whole thing — so nothing here opens `jd3-main`.
    """
    if not Path(path).is_file():
        return 0, 0
    turns = json.loads(Path(path).read_text(encoding="utf-8"))["turns"]
    if boundary is not None:
        turns = [t for t in turns if t.get("round", 0) <= boundary]
    return len(turns), sum(1 for t in turns if glued_argument_label(t.get("argument")))


# DOES THE RULING ANSWER BOTH REPLIES, OR ADOPT ONE?
#
# The failure mode both smokes produced and neither keyword caught. On `lojban-stim169`
# (smoke 1) and `python800-p03214` (smoke 2) the ruling reproduced the PRO reply's
# structure and several of its phrases and never engaged the ANTI reply's counter — and in
# the second it never named a debater at all, so `CITES_EXCHANGE` scored it as not citing
# the exchange while it was in fact reciting one half of it. A judge that adopts one
# advocate is the weak-vs-strong failure this whole arm is testing for, so it needs an
# instrument of its own.
#
# Lexical, deliberately: distinctive word 6-grams shared between the ruling's prose and
# each reply, as a fraction of that reply's own. It cannot tell adoption from agreement —
# a judge that reached PRO's conclusion independently will share its vocabulary because
# both are quoting the same judgment and the same record — so IT IS AN INSTRUMENT FOR
# DIRECTING A HAND READ AND NEVER A MEASUREMENT. The CHECKLIST scores the flagged cells by
# hand and the write-up quotes the hand count, not this one.
SHINGLE = 6
ONE_SIDED_RATIO = 2.0
ONE_SIDED_FLOOR = 0.02


def shingles(text: str, n: int = SHINGLE) -> set[tuple[str, ...]]:
    words = re.findall(r"[a-z0-9_]+", (text or "").lower())
    return {tuple(words[i:i + n]) for i in range(max(0, len(words) - n + 1))}


def overlap(ruling_raw: str, argument: str) -> float:
    """Share of a reply's distinctive 6-grams that reappear in the ruling's prose."""
    reply = shingles(argument)
    if not reply:
        return 0.0
    return len(reply & shingles(ruling_raw)) / len(reply)


def one_sided(pro_overlap: float, anti_overlap: float) -> bool:
    """Whether the ruling tracks one reply materially more closely than the other."""
    high, low = max(pro_overlap, anti_overlap), min(pro_overlap, anti_overlap)
    return high >= ONE_SIDED_FLOOR and high >= ONE_SIDED_RATIO * max(low, 1e-9)


def round_language(argument: str, ruling_raw: str) -> dict:
    return {
        "disputes_quotation": bool(DISPUTES_QUOTATION.search(argument or "")),
        "ruling_cites_exchange": bool(CITES_EXCHANGE.search(ruling_raw or "")),
    }


def scan_round_tree(tree: Path) -> list[dict]:
    """Per-cell flags for section (5) and (6), off a finished arm-R tree.

    The ONE thing in this file that needs a run tree. Its output is committed as
    `arm-round/round-language.jsonl` so that the default invocation stays index-only and
    reproduces on a bare clone.
    """
    rows = []
    # WALKED BY `run.json`, NOT BY `ruling.json`. A cell whose round-4 turn truncated has
    # no ruling — the cell failed — but it DOES have the turn that completed, committed
    # before the raise, and that half-round is exactly what section (6)'s truncation count
    # is about. Globbing rulings would make the truncation instrument read 0 on every
    # truncation, which is the shape of bug the first smoke's reader had.
    for path in sorted(Path(tree).glob("cells/*/contests/*/runs/*/run.json")):
        directory = path.parent
        if "parent" in path.parts:
            continue
        cell_id = str(path).split("/cells/")[1].split("/")[0]
        ruling_path = directory / "ruling.json"
        ruling = (json.loads(ruling_path.read_text(encoding="utf-8"))
                  if ruling_path.is_file() else {})
        pro = ruling.get("recourse_pro_speaker")
        if pro is None:
            # No ruling, so nothing recorded who argued which way. Derive it the way the
            # harness does, from the seating and the parent verdict, so a lost cell's
            # turns still land under the right stance.
            sides = json.loads((directory / "sides.json").read_text(encoding="utf-8"))
            verdict = json.loads(
                (directory / "parent" / "verdict.json").read_text(encoding="utf-8"))
            decision = verdict.get("verdict")
            pro = ("Alice" if sides.get("alice_side") != decision else "Bob")
        exchange_path = directory / "recourse_transcript.json"
        turns = []
        if exchange_path.is_file():
            turns = json.loads(exchange_path.read_text(encoding="utf-8"))["turns"]
        row = {"cell_id": cell_id, "recourse_rounds": ruling.get("recourse_rounds", 0),
               "ruled": bool(ruling), "pro_speaker": pro, "turns_n": len(turns),
               "ruling_cites_exchange": bool(CITES_EXCHANGE.search(
                   ruling.get("raw") or ""))}
        parent_n, parent_glued_n = parent_glued(directory / "parent" / "transcript.json")
        row["parent_turns_n"] = parent_n
        row["parent_glued_n"] = parent_glued_n
        row["glued_n"] = sum(1 for t in turns
                             if glued_argument_label(t.get("argument")))
        row["truncated_n"] = sum(1 for t in turns
                                 if t.get("finish_reason") == "length")
        raw = ruling.get("raw") or ""
        for turn in turns:
            stance = "pro" if str(turn.get("speaker")) == pro else "anti"
            row[f"{stance}_overlap"] = round(overlap(raw, turn.get("argument")), 4)
            row[f"{stance}_disputes_quotation"] = bool(
                DISPUTES_QUOTATION.search(turn.get("argument") or ""))
            for key, value in turn_flags(turn).items():
                row[f"{stance}_{key}"] = value
            row[f"{stance}_over_limit"] = bool(
                (turn.get("word_count") or 0) > WORD_LIMIT)
        if "pro_overlap" in row and "anti_overlap" in row:
            row["one_sided"] = one_sided(row["pro_overlap"], row["anti_overlap"])
            row["tracks"] = ("pro" if row["pro_overlap"] > row["anti_overlap"]
                             else "anti") if row["one_sided"] else None
        rows.append(row)
    return rows


def scan_plain_tree(tree: Path) -> list[dict]:
    """The same per-cell flags for arm B, off its finished decision tree.

    Arm B keeps everything in ONE `transcript.json` — the extended debate — so the parent
    rounds and the added round are told apart by `extended_from_rounds` in the manifest
    rather than by two files. A cell with no `extended_from_rounds` had no round added and
    is recorded with `turns_n = 0` rather than dropped: "no round was played here" is a
    fact the write-up needs, not a missing row.
    """
    rows = []
    for path in sorted(Path(tree).glob("cells/*/runs/*/transcript.json")):
        directory = path.parent
        if "parent" in path.parts or not (directory / "verdict.json").is_file():
            continue
        cell_id = str(path).split("/cells/")[1].split("/")[0]
        manifest = json.loads((directory / "run.json").read_text(encoding="utf-8"))
        boundary = manifest.get("extended_from_rounds")
        turns = json.loads(path.read_text(encoding="utf-8"))["turns"]
        fresh = ([] if boundary is None
                 else [t for t in turns if t.get("round", 0) > boundary])
        parent_n, parent_glued_n = parent_glued(path, boundary)
        rows.append({
            "cell_id": cell_id,
            "extended_from_rounds": boundary,
            "turns_n": len(fresh),
            "parent_turns_n": parent_n,
            "parent_glued_n": parent_glued_n,
            "glued_n": sum(1 for t in fresh if glued_argument_label(t.get("argument"))),
            "truncated_n": sum(1 for t in fresh
                               if t.get("finish_reason") == "length"),
        })
    return rows


def scan_attempts(tree: Path, pattern: str) -> dict:
    """Attempted / completed / failed, and every failure's cell and error.

    A cell that was attempted and lost is a fact this derivation has to carry: under
    `PREREG.md`'s loss rule it leaves every paired table, so the difference between 896
    and an arm's `decided` column is a number the write-up owes a reader — with the reason
    each cell was lost, not just the count. The first smoke's reader walked completed runs
    only and silently printed two cells where three had been attempted; this is that bug
    fixed one layer up.
    """
    attempted = completed = 0
    failures = []
    for path in sorted(Path(tree).glob(pattern)):
        try:
            manifest = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        attempted += 1
        status = manifest.get("status")
        if status == "completed":
            completed += 1
        elif status == "failed":
            failures.append({
                "cell_id": manifest.get("cell_id")
                or str(path).split("/cells/")[1].split("/")[0],
                "error": manifest.get("error") or "(no error recorded)",
                "run_dir": str(path.parent),
            })
    return {"attempted": attempted, "completed": completed,
            "failed": len(failures), "failures": failures}


def scan_providers(tree: Path) -> dict[str, dict[str, int]]:
    """Which provider served each role, off a finished tree's wire logs."""
    out: dict[str, dict[str, int]] = {}
    for path in sorted(Path(tree).rglob("calls.jsonl")):
        if "parent" in path.parts:
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except ValueError:
                continue
            role = record.get("role") or "unknown"
            provider = (record.get("response_body") or {}).get("provider") or "?"
            out.setdefault(role, {})
            out[role][provider] = out[role].get(provider, 0) + 1
    return out


def load_rows(path: Path | None) -> dict[str, dict]:
    if path is None or not Path(path).is_file():
        return {}
    out = {}
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            out[row["cell_id"]] = row
    return out


# --------------------------------------------------------------------------- #
# the sections
# --------------------------------------------------------------------------- #


def section_population(arms, cells, providers, attempts) -> None:
    head("(0) POPULATION — THE 896 CELLS jd3's M1 CONTESTED")
    print("Read off `challenge_raised` in M1's index, exactly as judgment-debate-{4,5}.py")
    print("read it. `data/cases/jd6-contested.jsonl` is the same set and asserts the count.")
    print()
    print(f"{'index':<44}{'rows':>10}{'on the 896':>14}{'decided':>10}")
    rule()
    for key, label, arm in (("m1", "M1 — the real audit (jd3), judge-only", "R"),
                            ("jd5_real", "jd5-B — the same objections, re-ruled", "R"),
                            ("round", "jd6 arm R — ARGUED, then ruled", "R"),
                            ("plain", "jd6 arm B — one plain round, re-judged", "B")):
        rows = arms.get(key, {})
        if not rows:
            print(f"{label:<44}{'NOT RUN':>10}")
            continue
        kept = restrict(rows, cells)
        print(f"{label:<44}{len(rows):>10}{len(kept):>14}"
              f"{len(ruled(kept, arm)):>10}")
    rule()
    print(f"population size: {len(cells)}")
    if arms.get("m1"):
        m1 = restrict(arms["m1"], cells)
        right = sum(1 for r in m1.values() if r.get("initially_correct"))
        print(f"M0's before-state on these cells: {rate(right, len(m1))} correct — "
              f"{len(m1) - right} wrong. P1 is tested on the {right}, P2 on the "
              f"{len(m1) - right}.")
    print()
    print("THE TWO ARMS PUT THEIR STATES IN DIFFERENT COLUMNS. Arm R is a rerule: its")
    print("`initially_correct` is M0's decision and `final_correct` is the ruling's. Arm B")
    print("is a rejudge: it made its own decision, so its `initially_correct` is the AFTER")
    print("state and M0's is `source_correct`. `before_of` / `after_of` in this file are")
    print("the only two places that difference is handled.")

    head("  ATTEMPTED / COMPLETED / FAILED, PER ARM  [the loss, and what caused it]")
    print("`PREREG.md`'s loss rule: a cell missing in either arm — a failed round, a failed")
    print("ruling or a failed judgment, each after the one retry the resume rule allows —")
    print("is DROPPED from every paired table and counted here. A cell that was never put to")
    print("a judge cannot be counted as an uphold or as an unchanged verdict, so it leaves")
    print("the pairing rather than entering it as a concordant pair and diluting exactly the")
    print("discordant counts P1 and P2 are computed from.")
    print()
    if not attempts:
        print("NOT AVAILABLE — no tree was scanned. Re-run with --scan-round-tree / "
              "--scan-plain-tree, or read `attempts.json` in the records directory.")
    else:
        print(f"{'arm':<32}{'attempted':>12}{'completed':>12}{'failed':>10}")
        rule()
        for arm in ("R", "B"):
            got = attempts.get(arm)
            if not got:
                print(f"{('arm ' + arm):<32}{'NOT SCANNED':>12}")
                continue
            print(f"{('arm ' + arm):<32}{got['attempted']:>12}"
                  f"{got['completed']:>12}{got['failed']:>10}")
        rule()
        for arm in ("R", "B"):
            for failure in (attempts.get(arm) or {}).get("failures", []):
                print(f"  arm {arm} LOST {failure['cell_id']}")
                print(f"    {failure['error']}")
        if not any((attempts.get(a) or {}).get("failures") for a in ("R", "B")):
            print("  no run directory in either arm carries status=failed.")
        print()
        print("`--retry-failed` MEANS A RETRIED CELL IS A DIFFERENT DRAW. The debaters run at")
        print("temperature 0.7, so a cell re-attempted after a degenerate generation is")
        print("re-rolled rather than repeated, and the retried cells are not a random sample")
        print("of the population — they are the cells whose first draw went wrong. Retried")
        print("and lost counts are reported per arm and never folded into a denominator.")

    head("  PROVIDER MIX PER ARM  [the pin, checked after the fact]")
    print("Both arms pin `meta-llama/llama-4-maverick` to `digitalocean`. §3aa found 34% of")
    print("M1's rulings served by DeepInfra against 4.8% of jd5-B's, which is why the pin")
    print("exists; this is where it is confirmed to have held. Display names, from the wire")
    print("log — `provider_order` takes slugs, so the two can only be compared here.")
    if not providers:
        print("\nNOT AVAILABLE — no tree was scanned. Re-run with --scan-round-tree / "
              "--scan-plain-tree, or read `provider-mix.json` in the records directory.")
        return
    for arm, by_role in sorted(providers.items()):
        print(f"\n  arm {arm}")
        for role, counts in sorted(by_role.items()):
            total = sum(counts.values())
            spread = "  ".join(f"{name} {n} ({pct(n, total)})"
                               for name, n in sorted(counts.items(),
                                                     key=lambda kv: -kv[1]))
            print(f"    {role:<20}{total:>7} calls   {spread}")


def paired_after_block(pairs, only: str) -> dict:
    """The R-vs-B 2x2, in the words of TWO AFTER-STATES.

    NOT `jd4.paired_block`, and this is a correctness fix rather than a preference.
    That function is written for a BEFORE against an AFTER, so it calls its two discordant
    cells "fixed" and "broken" and prints their difference as a NET. Section (1) pairs two
    AFTER-states with each other — R's ruling against B's judgment, on a decision M0 already
    made — so in it "fixed" would name a cell one arm got right and the other did not, which
    is not a fix by anybody, and the "NET" would be the margin between two arms rather than
    a gain over M0. A reader who copied that net into a write-up would report the opposite
    of the finding. Same counts, same exact test, correct words.
    """
    counts = Counter((a, b) for _, a, b in pairs)
    rr, rw = counts[(True, True)], counts[(True, False)]
    wr, ww = counts[(False, True)], counts[(False, False)]
    n = rr + rw + wr + ww
    r_right, b_right = rr + rw, rr + wr
    p = mcnemar_exact(rw, wr)
    verb = "left wrong" if only == "right" else "left right"
    print(f"{'':<28}{'B right':>16}{'B wrong':>16}{'total':>10}")
    rule()
    print(f"{'R right':<28}{rr:>16}{rw:>16}{r_right:>10}")
    print(f"{'R wrong':<28}{wr:>16}{ww:>16}{n - r_right:>10}")
    rule()
    print(f"{'total':<28}{b_right:>16}{n - b_right:>16}{n:>10}")
    print()
    if only == "right":
        print(f"  M0 was RIGHT on all {n}. A cell is BROKEN by an arm when that arm's")
        print("  after-state is wrong.")
        print(f"  broken by R ALONE   (R wrong, B right)   {wr}")
        print(f"  broken by B ALONE   (R right, B wrong)   {rw}")
        print(f"  broken by BOTH                           {ww}")
        print(f"  broken by NEITHER                        {rr}")
        print(f"  P1 asks whether the FIRST is smaller than the second. "
              f"{wr} vs {rw}.")
    else:
        print(f"  M0 was WRONG on all {n}. A cell is FIXED by an arm when that arm's")
        print("  after-state is right.")
        print(f"  fixed by R ALONE    (R right, B wrong)   {rw}")
        print(f"  fixed by B ALONE    (R wrong, B right)   {wr}")
        print(f"  fixed by BOTH                            {rr}")
        print(f"  fixed by NEITHER                         {ww}")
        print(f"  P2 asks whether the FIRST is at least the second. "
              f"{rw} vs {wr}.")
    print(f"  discordant pairs                         {rw + wr}"
          f"   (concordant {rr + ww}, and they carry no direction)")
    print(f"  EXACT TWO-SIDED McNEMAR                  p = {p:.6g}   {verdict_at(p)}")
    print()
    print(f"  accuracy after R   {acc(r_right, n)}   (95% Wilson)")
    print(f"  accuracy after B   {acc(b_right, n)}   (95% Wilson)")
    print(f"  NOTE: there is no NET on this table. Both columns are AFTER-states; the gain")
    print(f"  or loss against M0 is section (3), and it is an ABLATION.")
    return {"n": n, "rr": rr, "rw": rw, "wr": wr, "ww": ww,
            "r_only": wr if only == "right" else rw,
            "b_only": rw if only == "right" else wr,
            "r_right": r_right, "b_right": b_right, "p": p}


def section_primary(arms, cells) -> dict:
    head("(1) THE PRE-REGISTERED ENDPOINT — R vs B, PAIRED, ON THE SAME CELLS  [PRIMARY]")
    print("Every cell here carries ONE decision by M0 and TWO after-states: the ruling that")
    print("followed an ARGUED objection (R) and the judgment that followed one more ORDINARY")
    print("round (B). Same 896 cells, same two debaters, same judge model, same pin. What")
    print("differs is whether the stakeholder's objection shaped the round, and whether the")
    print("judge decided under `the decision stands unless` or decided afresh — a DOUBLE")
    print("difference, and neither arm can separate its halves.")
    a, b = restrict(arms.get("round", {}), cells), restrict(arms.get("plain", {}), cells)
    out: dict[str, dict] = {}
    if not a or not b:
        print("\nNOT RUN — one of the two arms has no index.")
        return out
    for key, only, title, why in (
            ("P1", "right",
             "P1 (PRIMARY, alpha = 0.05) — on the cells M0 got RIGHT: does R BREAK FEWER?",
             "A cell is BROKEN when the arm's after-state is wrong and M0 was right. "
             "`R correct / B wrong` is a cell the plain round broke and the contest round "
             "did not."),
            ("P2", "wrong",
             "P2 (CO-PRIMARY) — on the cells M0 got WRONG: does R FIX AT LEAST AS MANY?",
             "A cell is FIXED when the arm's after-state is right and M0 was wrong. The "
             "endpoint is P1 AND P2: breaking fewer is only worth having if it does not "
             "cost the fixes.")):
        head(f"  {title}")
        print(f"  {why}")
        print()
        pairs, disagreed = paired_states(a, b, cells, only=only)
        if disagreed:
            print(f"  ! {disagreed} cells were dropped because the two arms disagree "
                  "about M0's own decision; they are not the same cells and cannot be "
                  "paired.")
        if not pairs:
            print("  NOT RUN — no cell of this kind was decided by both arms.")
            continue
        out[key] = paired_after_block(pairs, only)
    return out


def section_rates(arms, cells) -> dict:
    head("(2) THE CONDITIONAL RATES SIDE BY SIDE  [DESCRIPTIVE]")
    print("The margins of section (1), with Wilson intervals. `broken | right` is the rate")
    print("P1 is about and `fixed | wrong` the rate P2 is about; the DIFFERENCE between them")
    print("is what the net of section (3) collapses.")
    print()
    print(f"{'arm':<38}{'n':>7}{'fixed | wrong':>26}{'broken | right':>26}")
    rule()
    out = {}
    for key, arm, label in (("m1", "R", "M1 — judge-only, unpinned (jd3)"),
                            ("jd5_real", "R", "jd5-B — judge-only, unpinned"),
                            ("round", "R", "jd6 R — ARGUED, pinned"),
                            ("plain", "B", "jd6 B — plain round, pinned")):
        rows = restrict(arms.get(key, {}), cells)
        if not rows:
            print(f"{label:<38}{'NOT RUN':>7}")
            continue
        wrong = right = fixed = broken = 0
        for row in rows.values():
            before, after = before_of(row, arm), after_of(row, arm)
            if before is None or after is None:
                continue
            if before:
                right += 1
                broken += not after
            else:
                wrong += 1
                fixed += after
        out[key] = {"fixed": fixed, "n_wrong": wrong, "broken": broken,
                    "n_right": right}
        print(f"{label:<38}{right + wrong:>7}"
              f"{(rate(fixed, wrong) + ' ' + interval(fixed, wrong)):>26}"
              f"{(rate(broken, right) + ' ' + interval(broken, right)):>26}")
    rule()
    if {"round", "plain"} <= set(out):
        r, b = out["round"], out["plain"]
        def share(k, n):
            return 100.0 * k / n if n else float("nan")
        print(f"  broken | right   R {share(r['broken'], r['n_right']):.1f}%  vs  "
              f"B {share(b['broken'], b['n_right']):.1f}%   "
              f"{share(r['broken'], r['n_right']) - share(b['broken'], b['n_right']):+.1f} pts"
              "   (P1's direction: NEGATIVE favours the contest round)")
        print(f"  fixed  | wrong   R {share(r['fixed'], r['n_wrong']):.1f}%  vs  "
              f"B {share(b['fixed'], b['n_wrong']):.1f}%   "
              f"{share(r['fixed'], r['n_wrong']) - share(b['fixed'], b['n_wrong']):+.1f} pts"
              "   (P2's direction: NON-NEGATIVE favours the contest round)")
    print()
    print("EVERY ABSOLUTE RATE IN ARM B CONTAINS MAVERICK'S OWN RE-DRAW DISAGREEMENT WITH")
    print("ITSELF as well as the extra round's effect. No floor arm was run to price it")
    print("(struck by the user, 2026-08-30). Section (1) is free of it; this table is not.")
    return out


def section_ablation(arms, cells) -> dict:
    head("(3) NET ACCURACY AGAINST M0, PER ARM  [ABLATION — NOT AN ENDPOINT]")
    print("The quantity jd3-jd5 reported as P1, kept here so the campaigns are readable in")
    print("one line — and demoted, because it is dominated by the 26% base rate of wrong")
    print("decisions (§3y): an arm that breaks and fixes at equal RATES still nets negative.")
    out = {}
    for key, arm, label in (("round", "R", "jd6 R — ARGUED, then ruled"),
                            ("plain", "B", "jd6 B — one plain round, re-judged")):
        rows = restrict(arms.get(key, {}), cells)
        head(f"  {label}")
        if not rows:
            print("  NOT RUN.")
            continue
        pairs = []
        for cell_id, row in sorted(rows.items()):
            before, after = before_of(row, arm), after_of(row, arm)
            if before is None or after is None:
                continue
            pairs.append((cell_id, bool(before), bool(after)))
        if not pairs:
            print("  NOT RUN — no cell carries both states.")
            continue
        out[key] = paired_block(pairs, "M0", key)
    return out


def section_vs_jd5(arms, cells) -> dict:
    head("(4) R AGAINST jd5-B — THE SAME OBJECTIONS WITH AND WITHOUT A ROUND"
         "  [DESCRIPTIVE]")
    print("The natural third column: jd5-B ruled these same 896 objections under the same")
    print("prompt and the same judge model, with NOBODY answering them.")
    print()
    print("THE PROVIDER CAVEAT, AND IT IS WHY THIS IS NOT AN ENDPOINT. jd5-B's judge was")
    print("UNPINNED and jd6's is pinned to DigitalOcean; §3aa measured 34% of M1's rulings")
    print("on DeepInfra against 4.8% of jd5-B's. So this table mixes the round with the")
    print("routing and cannot separate them. Section (1) can, because both its arms are")
    print("pinned to the same provider.")
    old = restrict(arms.get("jd5_real", {}), cells)
    new = restrict(arms.get("round", {}), cells)
    if not old or not new:
        print("\nNOT RUN — one of the two indexes is missing.")
        return {}
    return {"pairs": paired_ruling_block(ruling_pairs(old, new, cells),
                                         "jd5-B", "jd6-R")}


def section_language(language, arms, cells) -> None:
    head("(5) WHAT THE ROUND ACTUALLY SAID  [KEYWORD INSTRUMENT — NOT A MEASUREMENT]")
    print("Two regexes over text, defined in `RULING_LANGUAGE`-style constants at the head")
    print("of this file and re-derivable with `--scan-round-tree`. They are noisy in both")
    print("directions and what they support is the CONTRAST — between the PRO and the ANTI")
    print("reply, and between a ruling that names the exchange and one that does not — never")
    print("the absolute rate. A hand read of a sample belongs in the CHECKLIST beside them.")
    if not language:
        print("\nNOT AVAILABLE — no scan file and no --scan-round-tree.")
        return
    rows = [r for r in language.values() if r["cell_id"] in cells]
    if not rows:
        print("\nNOT AVAILABLE — the scan holds no cell of this population.")
        return
    print()
    heard = [r for r in rows if r.get("turns_n")]
    print(f"  cells scanned                         {len(rows)}")
    print(f"  cells where a round was heard         {len(heard)}")
    for stance, why in (("anti", "argues the defects are NOT real or not material"),
                        ("pro", "argues they ARE real and material")):
        have = [r for r in heard if f"{stance}_disputes_quotation" in r]
        if not have:
            continue
        n = sum(1 for r in have if r[f"{stance}_disputes_quotation"])
        print(f"  {stance.upper():<5} disputes a quotation           {rate(n, len(have))}"
              f"   ({why})")
    cites = sum(1 for r in heard if r.get("ruling_cites_exchange"))
    print(f"  ruling prose names the exchange       {rate(cites, len(heard))}")
    print()
    print("A ruling that never names either debater may still have been moved by them, and")
    print("one that names them may be summarising. This is an instrument, not a finding.")

    scored = [r for r in heard if r.get("one_sided") is not None]
    if scored:
        print()
        print("  DOES THE RULING ANSWER BOTH REPLIES, OR ADOPT ONE?  [DIRECTS A HAND READ]")
        print("  Distinctive word 6-grams of each reply that reappear in the ruling's prose,")
        print("  as a share of that reply's own. It CANNOT tell adoption from agreement — a")
        print("  judge that reached PRO's conclusion independently shares its vocabulary,")
        print("  since both quote the same judgment and the same record — so what it does is")
        print("  point the hand read at the cells worth reading, and the CHECKLIST's hand")
        print("  count is what the write-up quotes.")
        flagged = [r for r in scored if r["one_sided"]]
        tracks = Counter(r["tracks"] for r in flagged)
        print()
        print(f"  cells scored                          {len(scored)}")
        print(f"  one-sided (>= {ONE_SIDED_RATIO:g}x the other, floor "
              f"{ONE_SIDED_FLOOR:g})   {rate(len(flagged), len(scored))}")
        print(f"    of those, tracking PRO              {tracks.get('pro', 0)}")
        print(f"    of those, tracking ANTI             {tracks.get('anti', 0)}")
        pro_mean = sum(r.get("pro_overlap") or 0 for r in scored) / len(scored)
        anti_mean = sum(r.get("anti_overlap") or 0 for r in scored) / len(scored)
        print(f"  mean overlap with PRO / ANTI          {pro_mean:.3f} / {anti_mean:.3f}")
        print()
        print("  A ruling that tracks PRO and never answers ANTI, on a decision that was")
        print("  RIGHT, is the weak-judge-adopts-the-strong-advocate failure this arm exists")
        print("  to detect. Both smokes produced one (`lojban-stim169`, `python800-p03214`),")
        print("  and in the second the ruling named no debater at all — which is why the")
        print("  `names the exchange` line above is not enough on its own.")


def section_turns(language, plain_language, arms, cells) -> None:
    head("(6) THE ROUND-4 TURNS THEMSELVES, IN BOTH ARMS  [DESCRIPTIVE]")
    print("Parse modes, repairs and word counts. Both arms buy exactly two strong-model")
    print("turns per cell, and if one arm's turns were systematically shorter or more often")
    print("repaired than the other's then 'same debaters, same extra tokens' would be an")
    print("intent rather than a fact.")
    print()
    for key, arm, modes_key, words_key, repairs_key, label in (
            ("round", "R", "recourse_turn_parse_modes", "recourse_turn_words",
             "recourse_turn_repairs", "jd6 R — the contest round"),
            ("plain", "B", "round4_parse_modes", "round4_words", "round4_repairs",
             "jd6 B — the plain round")):
        rows = restrict(arms.get(key, {}), cells)
        head(f"  {label}")
        if not rows:
            print("  NOT RUN.")
            continue
        modes: Counter = Counter()
        words: list[int] = []
        repairs = cells_with_turns = 0
        for row in rows.values():
            got = row.get(modes_key) or []
            if got:
                cells_with_turns += 1
            modes.update(got)
            words.extend(w for w in (row.get(words_key) or []) if w is not None)
            repairs += row.get(repairs_key) or 0
        print(f"  cells with turns recorded             {cells_with_turns} of {len(rows)}")
        print(f"  turns                                 {sum(modes.values())}")
        print(f"  parse modes                           {dict(modes)}")
        print(f"  format repairs                        {repairs}")
        if words:
            words.sort()
            print(f"  words per argument   min {words[0]}  median "
                  f"{words[len(words) // 2]}  max {words[-1]}  mean "
                  f"{sum(words) / len(words):.0f}")
    if language:
        heard = [r for r in language.values()
                 if r["cell_id"] in cells and r.get("turns_n")]
        short = [r for r in heard if r.get("turns_n") != 2]
        if short:
            print()
            print(f"  ! {len(short)} arm-R cells hold a round that is not two turns; a "
                  "half-round is a failed cell re-attempted from scratch, so this should "
                  "be 0.")

    head("  THE GLUED `Argument:` LABEL, AND WHETHER THE ROUND RAISED IT"
         "  [FORMAT INSTRUMENT]")
    print("A turn whose PUBLISHED argument still contains an `Argument:` label of its own:")
    print("the model wrote the label mid-sentence after some planning text, and")
    print("`parse_debater_output` — which takes the last label at a LINE START — published")
    print("the planning text as part of the public argument. The parser cannot catch it and")
    print("a reader of the record can see it, so the question is not whether it happens but")
    print("whether THIS round does it more than the debate it continues. The same count is")
    print("therefore taken over the PARENT rounds 1-3 of the very same cells, out of each")
    print("arm's own copy of them — nothing here opens `jd3-main`.")
    print()
    print(f"{'arm':<28}{'round-4 turns':>15}{'glued':>8}{'rate':>15}"
          f"{'parent turns':>15}{'glued':>8}{'rate':>15}")
    rule()
    both = (("jd6 R — the contest round", language),
            ("jd6 B — the plain round", plain_language))
    for label, scan in both:
        rows = [r for r in (scan or {}).values() if r["cell_id"] in cells]
        if not rows:
            print(f"{label:<28}{'NOT AVAILABLE':>15}")
            continue
        turns = sum(r.get("turns_n") or 0 for r in rows)
        glued = sum(r.get("glued_n") or 0 for r in rows)
        p_turns = sum(r.get("parent_turns_n") or 0 for r in rows)
        p_glued = sum(r.get("parent_glued_n") or 0 for r in rows)
        print(f"{label:<28}{turns:>15}{glued:>8}{rate(glued, turns):>15}"
              f"{p_turns:>15}{p_glued:>8}{rate(p_glued, p_turns):>15}")
    rule()
    print("A round-4 rate at or below its own parent rate is the habit INHERITED; a higher")
    print("one is the round RAISING it, and that would be a fact about the new prompts.")

    head("  THE SAME FOUR INSTRUMENTS, SPLIT BY STANCE  [arm R only]")
    print("PRO argues the alleged defects are real and material; ANTI argues they are not.")
    print("They are different tasks with different amounts to say, and a systematic")
    print("difference between them is a difference in what the judge reads on each side of")
    print("the objection — which is exactly the asymmetry the exchange block's symmetric")
    print("discount was rewritten to avoid leaning on. Smoke 1's two heavy word overruns")
    print("(441 and 687 against a 400-word limit) were BOTH PRO turns, which is why this")
    print("split is pre-registered rather than looked at afterwards.")
    print()
    rows = [r for r in (language or {}).values()
            if r["cell_id"] in cells and r.get("turns_n")]
    if not rows:
        print("  NOT AVAILABLE — no arm-R scan.")
    else:
        print(f"{'stance':<10}{'turns':>8}{'glued':>14}{'truncated':>14}"
              f"{f'over {WORD_LIMIT}w':>14}{'median words':>14}{'max':>7}")
        rule()
        for stance in ("pro", "anti"):
            have = [r for r in rows if f"{stance}_words" in r]
            if not have:
                print(f"{stance.upper():<10}{'NOT AVAILABLE':>8}")
                continue
            words = sorted(r[f"{stance}_words"] for r in have
                           if r[f"{stance}_words"] is not None)
            glued = sum(1 for r in have if r.get(f"{stance}_glued_label"))
            cut = sum(1 for r in have if r.get(f"{stance}_truncated"))
            over = sum(1 for r in have if r.get(f"{stance}_over_limit"))
            print(f"{stance.upper():<10}{len(have):>8}{rate(glued, len(have)):>14}"
                  f"{rate(cut, len(have)):>14}{rate(over, len(have)):>14}"
                  f"{(words[len(words) // 2] if words else 0):>14}"
                  f"{(words[-1] if words else 0):>7}")
        rule()
        print("Arm B has no stances — nobody is arguing about an objection there — so this")
        print("table is arm R's alone, and the un-split counts above are the comparison.")

    head("  TRUNCATED ROUND-4 TURNS  [the cell-loss mechanism]")
    print("`finish_reason == \"length\"` at `generation_max_tokens`: the turn ran out of")
    print("budget mid-argument, which is FATAL and unretryable — a truncated argument would")
    print("enter the public transcript as if authored — so the cell fails and is counted.")
    print("It is the sweep's own failure mode (a restart loop in the private Thinking")
    print("block), not a new one, and the arms report the loss rather than hiding it.")
    print()
    for label, scan in both:
        rows = [r for r in (scan or {}).values() if r["cell_id"] in cells]
        if not rows:
            print(f"  {label:<28}NOT AVAILABLE")
            continue
        turns = sum(r.get("turns_n") or 0 for r in rows)
        cut = sum(r.get("truncated_n") or 0 for r in rows)
        print(f"  {label:<28}{cut} of {turns} completed round-4 turns "
              f"({rate(cut, turns)})")
    print()
    print("READ THIS COUNT WITH THE ATTEMPTS TABLE OF SECTION (0), NOT INSTEAD OF IT.")
    print("A TRUNCATED TURN IS NEVER COMMITTED — `_complete_with_repair` raises rather than")
    print("letting a cut-off argument enter the public transcript as if authored — so it")
    print("leaves NO row on disk to carry `finish_reason = \"length\"`. What it leaves is a")
    print("HALF-ROUND: the other debater's turn, committed before the raise, beside a run")
    print("whose manifest says failed. So this count reads 0 on the very cells it is about,")
    print("and the truncations are visible in three other places instead: the failed-cell")
    print("list in section (0) with the error verbatim, the `turns_n != 2` line above, and")
    print("the difference between 896 and each arm's `decided` column. The count below")
    print("catches the OTHER shape — a turn the provider marked `length` and still")
    print("returned parseably — which has not been seen in either smoke.")


# --------------------------------------------------------------------------- #
# the CLI
# --------------------------------------------------------------------------- #

ARM_FLAGS = {
    "m1": ("--m1", "records/experiments/judgment-debate-3/arm-M0-M1/index.jsonl"),
    "jd5_real": ("--jd5-real",
                 "records/experiments/judgment-debate-5/arm-real/index.jsonl"),
    "round": ("--round", "records/experiments/judgment-debate-6/arm-round/index.jsonl"),
    "plain": ("--plain", "records/experiments/judgment-debate-6/arm-plain/index.jsonl"),
}

LANGUAGE_DEFAULT = ("records/experiments/judgment-debate-6/arm-round/"
                    "round-language.jsonl")
PLAIN_LANGUAGE_DEFAULT = ("records/experiments/judgment-debate-6/arm-plain/"
                          "round-language.jsonl")
PROVIDERS_DEFAULT = "records/experiments/judgment-debate-6/provider-mix.json"
ATTEMPTS_DEFAULT = "records/experiments/judgment-debate-6/attempts.json"


def _dest(flag: str) -> str:
    return flag.lstrip("-").replace("-", "_")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    for key, (flag, default) in ARM_FLAGS.items():
        parser.add_argument(flag, type=Path, default=Path(default),
                            help=f"index.jsonl for {key} (default: {default})")
    parser.add_argument("--round-language", type=Path, default=Path(LANGUAGE_DEFAULT),
                        help=f"section (5)'s scan (default: {LANGUAGE_DEFAULT})")
    parser.add_argument("--plain-language", type=Path,
                        default=Path(PLAIN_LANGUAGE_DEFAULT),
                        help=f"section (6)'s arm-B scan "
                             f"(default: {PLAIN_LANGUAGE_DEFAULT})")
    parser.add_argument("--provider-mix", type=Path, default=Path(PROVIDERS_DEFAULT),
                        help=f"section (0)'s provider table (default: {PROVIDERS_DEFAULT})")
    parser.add_argument("--attempts", type=Path, default=Path(ATTEMPTS_DEFAULT),
                        help=f"section (0)'s attempted/completed/failed table "
                             f"(default: {ATTEMPTS_DEFAULT})")
    parser.add_argument("--scan-round-tree", type=Path, default=None,
                        help="re-derive arm R's language scan and provider mix from a "
                             "finished run tree")
    parser.add_argument("--scan-plain-tree", type=Path, default=None,
                        help="re-derive arm B's provider mix from a finished run tree")
    parser.add_argument("--write-scans", type=Path, default=None,
                        help="with --scan-*: write the scans into this directory and exit")
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)

    language: dict[str, dict] = {}
    providers: dict[str, dict[str, dict[str, int]]] = {}
    attempts: dict[str, dict] = {}
    if args.scan_round_tree is not None:
        language = {r["cell_id"]: r for r in scan_round_tree(args.scan_round_tree)}
        providers["R"] = scan_providers(args.scan_round_tree)
        attempts["R"] = scan_attempts(args.scan_round_tree,
                                      "cells/*/contests/*/runs/*/run.json")
    plain_language: dict[str, dict] = {}
    if args.scan_plain_tree is not None:
        plain_language = {r["cell_id"]: r for r in scan_plain_tree(args.scan_plain_tree)}
        providers["B"] = scan_providers(args.scan_plain_tree)
        attempts["B"] = scan_attempts(args.scan_plain_tree, "cells/*/runs/*/run.json")
    if args.write_scans is not None:
        out = Path(args.write_scans)
        (out / "arm-round").mkdir(parents=True, exist_ok=True)
        (out / "arm-round" / "round-language.jsonl").write_text(
            "".join(json.dumps(r) + "\n" for r in language.values()), encoding="utf-8")
        (out / "arm-plain").mkdir(parents=True, exist_ok=True)
        (out / "arm-plain" / "round-language.jsonl").write_text(
            "".join(json.dumps(r) + "\n" for r in plain_language.values()),
            encoding="utf-8")
        (out / "provider-mix.json").write_text(json.dumps(providers, indent=2),
                                               encoding="utf-8")
        (out / "attempts.json").write_text(json.dumps(attempts, indent=2),
                                           encoding="utf-8")
        print(f"wrote {len(language)} arm-R and {len(plain_language)} arm-B language "
              f"rows and {len(providers)} provider tables -> {out}")
        return 0
    if not language:
        language = load_rows(args.round_language)
    if not plain_language:
        plain_language = load_rows(args.plain_language)
    if not providers and Path(args.provider_mix).is_file():
        providers = json.loads(Path(args.provider_mix).read_text(encoding="utf-8"))
    if not attempts and Path(args.attempts).is_file():
        attempts = json.loads(Path(args.attempts).read_text(encoding="utf-8"))

    arms = {key: load(getattr(args, _dest(flag))) for key, (flag, _) in ARM_FLAGS.items()}

    print("=" * W)
    print("judgment-debate-6 — an argued objection against an un-argued extra round")
    print("=" * W)
    print("Pre-registration: records/experiments/judgment-debate-6/PREREG.md")
    print("Section (1) is the endpoint (P1 and P2 together). (3) is an ABLATION and never")
    print("an endpoint; (4) is DESCRIPTIVE and carries a provider caveat; (5) is a KEYWORD")
    print("INSTRUMENT. Everything else is descriptive.")
    print()
    print(f"{'arm':<12}{'index':<76}{'rows':>8}")
    rule()
    for key, (flag, _) in ARM_FLAGS.items():
        n = len(arms[key])
        print(f"{key:<12}{str(getattr(args, _dest(flag))):<76}"
              f"{(n if n else 'NOT RUN'):>8}")
    print(f"{'R language':<12}{str(args.round_language):<76}"
          f"{(len(language) if language else 'NOT AVAILABLE'):>8}")
    print(f"{'B language':<12}{str(args.plain_language):<76}"
          f"{(len(plain_language) if plain_language else 'NOT AVAILABLE'):>8}")
    rule()

    # THE POPULATION, defined once: the cells M1 objected to. Taken from M1's index where
    # it is available and from arm R's own rows otherwise, so the file still runs on a
    # machine that holds only jd6's records.
    if arms.get("m1"):
        cells = {c for c, r in arms["m1"].items() if r.get("challenge_raised")}
    else:
        cells = set(arms.get("round", {})) | set(arms.get("plain", {}))
        if cells:
            print("note: M1's index is not present, so the population is taken from the "
                  "jd6 arms themselves. `data/cases/jd6-contested.jsonl` is the "
                  "count-asserted definition.")

    if not cells:
        print("\nNOTHING TO DERIVE — no arm index is present. This is what the file prints")
        print("before the run, and it is not an error.")
        return 0

    section_population(arms, cells, providers, attempts)
    primary = section_primary(arms, cells)
    rates = section_rates(arms, cells)
    section_ablation(arms, cells)
    section_vs_jd5(arms, cells)
    section_language(language, arms, cells)
    section_turns(language, plain_language, arms, cells)

    head("THE PRE-REGISTERED READING")
    if not primary:
        print("NOT RUN — both arms are needed before either endpoint can be read.")
        return 0
    p1, p2 = primary.get("P1"), primary.get("P2")
    if p1:
        print(f"P1  on the {p1['n']} initially-CORRECT cells decided by both arms: "
              f"R broke {p1['r_only']} that B did not, B broke {p1['b_only']} that R did "
              f"not, p = {p1['p']:.4g}.")
        print(f"    {'R BREAKS FEWER' if p1['r_only'] < p1['b_only'] else 'R BREAKS MORE'}"
              f" — {verdict_at(p1['p'])}")
    if p2:
        print(f"P2  on the {p2['n']} initially-WRONG cells decided by both arms: "
              f"R fixed {p2['r_only']} that B did not, B fixed {p2['b_only']} that R did "
              f"not, p = {p2['p']:.4g}.")
        print(f"    {'R FIXES AT LEAST AS MANY' if p2['r_only'] >= p2['b_only'] else 'R FIXES FEWER'}")
    if p1 and p2:
        print()
        print("THE RESULT IS A SPLIT AND IS REPORTED AS ONE. P1 FAILS and P2 HOLDS: the")
        print("contest round is MORE INTERVENTIONIST IN BOTH DIRECTIONS — it breaks more of")
        print("the decisions M0 got right AND fixes more of the ones it got wrong. That is")
        print("none of the four named outcomes: (A) needs P1, (B) needs R to break fewer,")
        print("(C) needs B to beat R on both, (D) needs no separation. PREREG.md's rule is")
        print("that a split is reported as the split it is, with both tests' numbers, and")
        print("NOT rounded to whichever named outcome it is nearest. It is not rounded here.")
    print()
    print("THE FOUR NAMED OUTCOMES, written into PREREG.md before either arm ran, so that")
    print("no rule is invented after the table:")
    print("  (A) P1 and P2 hold          the objection makes the extra round more")
    print("                              discriminating than an un-steered one")
    print("  (B) R breaks fewer AND      the contest round is CONSERVATIVE, not")
    print("      fixes fewer             discriminating")
    print("  (C) B beats R on both       the objection is worse than no objection")
    print("  (D) no separation           the round's content does not matter, only that")
    print("                              there was one")
    print()
    print("WHAT THIS FILE DOES NOT CLAIM: nothing about jd3's P1, `single`/`self_critique`,")
    print("natural-error selection, `weak_alone`, or the same-model property (Maverick")
    print("judged these debates and rules on the appeals — the jd3 design, unrepaired here).")
    print("No number here is pooled with jd3-jd5's: the ruling prompt and the pin differ.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

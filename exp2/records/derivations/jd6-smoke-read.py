"""Read the `judgment-debate-6` prompt smoke by hand — the argued round beside the plain one.

    cd exp2
    uv run python records/derivations/jd6-smoke-read.py > outputs/jd6-smoke-read.txt

Read-only over `outputs/experiments/jd6-smoke-round/` and
`outputs/experiments/jd6-smoke-plain/`. It writes nothing and opens no annotation, and it
never touches `jd3-main`, which is the tree the decisions, the judgments and the
objections were copied FROM.

WHAT IS BEING READ. Four new prompts and one inserted block, all shipped at once:

  * `RECOURSE_DEBATER_CLAUSE` — spliced into `DEBATER_SYSTEM`, telling the debater the
    debate is decided, a stakeholder has audited the judgment, and this round is about
    whether the alleged defects are real and material rather than a fourth round of the
    original question;
  * `RECOURSE_DEBATER_USER` — the decision, the judgment and the objection, after the
    three rounds the debater already argued;
  * `RECOURSE_ROUND_PRO` / `RECOURSE_ROUND_ANTI` — the loser argues the defects are real
    and material, the winner argues they are not, and BOTH still argue their assigned
    side;
  * `RECOURSE_EXCHANGE_BLOCK` — one block in the frozen materiality template, naming who
    argues which way and warning that these are arguments and not evidence.

THE GATE, written before the smoke ran, and it is about the ROUND rather than about the
conclusions:

  * each debater argues the side it was ASSIGNED, and the stance the DECISION assigns it
    — the loser for the objection, the winner against it. A debater that argued the other
    way would invert the whole arm and still read fluently.
  * the round stays on the OBJECTION — are the alleged defects real, are they material —
    rather than re-arguing the object-level question for a fourth round.
  * the ruling engages with the exchange rather than reading like jd5's ruling with two
    paragraphs of noise above it.
  * no `Thinking:` reaches any judge, no repair, no parse fallback.

WHAT IS NOT THE GATE: the conclusion lines. Step 2 is unchanged and materiality is the
judge's to weigh, so a cell may keep or lose its overturn for reasons the round had
nothing to do with. Six cells is six cells; the paired arms are the measurement.

WHO ARGUED WHICH WAY IS RECOMPUTED HERE from `sides.json` and the parent verdict, by the
same rule the harness uses (`types.recourse_stance`) written out again in this file, and
compared with the `recourse_pro_speaker` the ruling recorded. A stored field and a
derivation that agree are worth more than either alone, and if they ever disagree this
line is where it shows.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
# Which smoke to read. `--smoke 2` reads the second draw's trees; smoke 1's stay on disk
# and `outputs/jd6-smoke-read.txt` stays as the record of the read that changed two
# sentences of the prompts.
SMOKE = sys.argv[sys.argv.index("--smoke") + 1] if "--smoke" in sys.argv else "1"
SUFFIX = "" if SMOKE == "1" else f"-{SMOKE}"
ROUND_TREE = REPO / "outputs" / "experiments" / f"jd6-smoke{SUFFIX}-round"
PLAIN_TREE = REPO / "outputs" / "experiments" / f"jd6-smoke{SUFFIX}-plain"
# jd5-B's committed index. THE THIRD RULING, and it is not on disk in either tree: the
# smoke's `contests_from` is `jd3-main`, so the `ruling.source.json` beside each new
# ruling is M1's, made under the OLD ruling prompt (before the existence check). jd5-B
# ruled the SAME objection under the SAME prompt jd6 uses, with nobody answering, and
# that is the ruling jd6-R is actually the counterfactual to — so it is read out of the
# committed index rather than left out of the comparison.
JD5_REAL = (REPO / "records" / "experiments" / "judgment-debate-5" / "arm-real"
            / "index.jsonl")

RULE = "=" * 100
THIN = "-" * 100

FLAWED, SOUND = "FLAWED", "SOUND"


def complement(verdict: str) -> str:
    return SOUND if verdict == FLAWED else FLAWED


def stance_of(speaker: str, sides: dict, decision_verdict: str) -> str:
    """`types.recourse_stance`, written out again rather than imported.

    The point of a hand read is that it does not take the harness's word for anything, so
    the rule is restated here and checked against what the ruling recorded.
    """
    side = sides["alice_side"] if speaker == "Alice" else sides["bob_side"]
    return "anti" if side == decision_verdict else "pro"


def indent(text: str, pad: str = "    ") -> str:
    return "\n".join(pad + line for line in (text or "").splitlines())


def read(path: Path):
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None


def attempts(tree: Path, pattern: str) -> tuple[list[Path], list[tuple[Path, str]]]:
    """Every run directory this arm CLAIMED, and the ones whose manifest says `failed`.

    THE FIRST SMOKE HID A LOST CELL and this function is why the second cannot. Arm B's
    `gpqa-13` lost a round-4 turn to a truncation, its run was marked `failed`, and the
    reader — which walked `verdict.json` — simply printed two cells and said nothing about
    the third. A cell that was attempted and lost is a fact the read has to carry: it is
    the difference between "the round works" and "the round works on the cells that
    survived it", and under the pre-registered loss rule those cells leave every paired
    table.
    """
    claimed = sorted(p.parent for p in Path(tree).glob(pattern))
    failed = []
    for directory in claimed:
        manifest = read(directory / "run.json") or {}
        if manifest.get("status") == "failed":
            failed.append((directory, manifest.get("error") or "(no error recorded)"))
    return claimed, failed


def print_attempts(label: str, claimed, failed, completed: int) -> None:
    print()
    print(f"ATTEMPTED / COMPLETED / FAILED — {label}: "
          f"{len(claimed)} attempted, {completed} completed, {len(failed)} failed")
    for directory, error in failed:
        cell = str(directory).split("/cells/")[1].split("/")[0]
        print(f"  FAILED  {cell}")
        print(f"          {directory}")
        print(f"          {error}")
    if not failed:
        print("  no run directory carries status=failed.")


def jd5_rulings() -> dict:
    """`{cell_id: row}` from jd5-B's committed index, or `{}` if it is not there."""
    if not JD5_REAL.is_file():
        return {}
    out = {}
    for line in JD5_REAL.read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            out[row["cell_id"]] = row
    return out


def head_of(text: str, sentences: int = 6) -> str:
    """The opening of a long reasoning block, for the summary table."""
    parts = re.split(r"(?<=[.!?])\s+", (text or "").strip())
    return " ".join(parts[:sentences])


def render_round_cell(directory: Path, jd5: dict) -> dict:
    manifest = read(directory / "run.json") or {}
    item = read(directory / "item.json") or {}
    sides = read(directory / "sides.json") or {}
    challenge = read(directory / "challenge.json") or {}
    parent_verdict = read(directory / "parent" / "verdict.json") or {}
    exchange = read(directory / "recourse_transcript.json") or {"turns": []}
    old = read(directory / "ruling.source.json") or {}
    new = read(directory / "ruling.json") or {}
    reading = read(directory / "ruling_agreement.json")

    decision = parent_verdict.get("verdict")
    pro_derived = ("Alice" if stance_of("Alice", sides, decision) == "pro" else "Bob")
    pro_recorded = new.get("recourse_pro_speaker")

    print()
    print(RULE)
    print(f"{manifest.get('cell_id', directory.name)}   subset={manifest.get('subset')}")
    print(f"M0 decided {decision}  (correct={parent_verdict.get('correct')})   "
          f"gold={'FLAWED' if item.get('gold_flawed') else 'SOUND'}")
    print(f"sides: Alice argued {sides.get('alice_side')}, Bob argued "
          f"{sides.get('bob_side')}")
    print(f"the decision went AGAINST {pro_derived}, so {pro_derived} argues the "
          f"objection is well founded")
    print(f"  derived here: {pro_derived}   recorded on the ruling: {pro_recorded}   "
          f"{'AGREE' if pro_derived == pro_recorded else '!!! DISAGREE !!!'}")
    print(RULE)

    print()
    print("THE JUDGMENT UNDER AUDIT — what both debaters and the judge were shown:")
    print()
    print(indent(parent_verdict.get("raw", "")))

    print()
    print(THIN)
    print("THE OBJECTION, VERBATIM — put to BOTH debaters and to the judge:")
    print()
    print(indent(challenge.get("text", "")))

    print()
    print(THIN)
    print("THE EXCHANGE — one simultaneous turn each, neither seeing the other's reply:")
    leaked = []
    for turn in sorted(exchange["turns"],
                       key=lambda t: (t.get("round", 0), str(t.get("speaker")))):
        speaker = str(turn.get("speaker"))
        stance = stance_of(speaker, sides, decision)
        gloss = ("argues the objection IS well founded" if stance == "pro"
                 else "argues the objection is NOT well founded")
        side = sides["alice_side"] if speaker == "Alice" else sides["bob_side"]
        print()
        print(f"  {speaker} — {stance.upper()}, {gloss}   "
              f"(still arguing its assigned side: {side})")
        print(f"  [round {turn.get('round')}  parse_mode={turn.get('parse_mode')}  "
              f"repairs={turn.get('repair_attempts')}  "
              f"words={turn.get('word_count')}  "
              f"finish={turn.get('finish_reason')}]")
        print()
        print(indent(turn.get("argument", ""), "      "))
        if turn.get("thinking"):
            leaked.append(speaker)

    cell_id = manifest.get("cell_id")
    jd5_row = jd5.get(cell_id) or {}
    jd5_word = (None if jd5_row.get("ruling_form") is None else
                ("OVERTURN" if jd5_row.get("changed_the_decision") else "UPHOLD"))

    for label, ruling in (
            ("SOURCE RULING — M1's (jd3), the same objection with NOBODY answering AND "
             "under the OLD prompt, before the existence check. Copied here as "
             "`ruling.source.json` because this spec's `contests_from` is `jd3-main`.",
             old),
            ("NEW RULING — the same judge, the same objection, ARGUED", new)):
        print()
        print(THIN)
        print(f"{label}   [{ruling.get('ruling')}  "
              f"parse_mode={ruling.get('parse_mode')}  "
              f"repairs={ruling.get('repair_attempts')}  "
              f"rounds_heard={ruling.get('recourse_rounds', 0)}]")
        print()
        print(indent(ruling.get("reasoning", ""), "    "))
        print()
        print(f"  CONCLUSION: {ruling.get('conclusion_line')}")
        print(f"  -> verdict {ruling.get('verdict')}   "
              f"changed_the_decision={ruling.get('changed_the_decision')}   "
              f"final decision correct={ruling.get('correct')}")

    print()
    print(THIN)
    if reading is None:
        print("RULING_AGREEMENT: not run.")
    else:
        print(f"RULING_AGREEMENT (a Haiku reader of the NEW ruling's PROSE, independent "
              f"of its line): prose_conclusion={reading.get('prose_conclusion')}  "
              f"mismatch={reading.get('mismatch')}")
        print(indent(head_of(reading.get("reasoning", ""), 4), "    "))

    print()
    print("THE THREE RULINGS ON THIS ONE OBJECTION, oldest first:")
    print(f"  M1   (jd3, OLD prompt, no round, judge unpinned)   "
          f"{old.get('ruling')}")
    print(f"  jd5-B (SAME prompt as here, no round, judge UNPINNED) "
          f"{jd5_word or 'NOT IN THE COMMITTED INDEX'}")
    print(f"  jd6-R (SAME prompt, ARGUED, judge PINNED to DigitalOcean) "
          f"{new.get('ruling')}")
    print(f"  M0 was {'RIGHT' if parent_verdict.get('correct') else 'WRONG'}. jd5-B is "
          "the row jd6-R is the counterfactual to; M1 differs in the PROMPT as well and "
          "is here only because its ruling is the file that came across with the copy.")
    if leaked:
        print(f"  note: {', '.join(leaked)} wrote a private Thinking section; it is in "
              "`recourse_transcript.json` and `transcript_full.md` and reaches no judge "
              "— the prompt dump beside this file is where that is checked.")
    return {
        "cell_id": manifest.get("cell_id"),
        "subset": manifest.get("subset"),
        "m0_right": parent_verdict.get("correct"),
        "m1": old.get("ruling"), "jd5b": jd5_word, "new": new.get("ruling"),
        "pro": pro_derived, "agree": pro_derived == pro_recorded,
        "turns": len(exchange["turns"]),
        "repairs": sum(t.get("repair_attempts", 0) for t in exchange["turns"]),
        "modes": {t.get("parse_mode") for t in exchange["turns"]},
        "mismatch": (reading or {}).get("mismatch"),
    }


def render_plain_cell(directory: Path) -> dict:
    manifest = read(directory / "run.json") or {}
    item = read(directory / "item.json") or {}
    sides = read(directory / "sides.json") or {}
    transcript = read(directory / "transcript.json") or {"turns": []}
    verdict = read(directory / "verdict.json") or {}

    added = manifest.get("extended_from_rounds")
    fresh = [t for t in transcript["turns"] if t.get("round", 0) > (added or 0)]

    print()
    print(RULE)
    print(f"{manifest.get('cell_id', directory.name)}   subset={manifest.get('subset')}")
    print(f"M0 decided {manifest.get('source_verdict')}  "
          f"(correct={manifest.get('source_correct')})   "
          f"gold={'FLAWED' if item.get('gold_flawed') else 'SOUND'}")
    print(f"sides: Alice argued {sides.get('alice_side')}, Bob argued "
          f"{sides.get('bob_side')}")
    print(f"extended from {added} rounds to {manifest.get('rounds_n')}; "
          f"{len(transcript['turns'])} turns in all, {len(fresh)} of them new")
    print(RULE)

    print()
    print("ROUND 4 — ORDINARY, no objection anywhere in the prompt:")
    for turn in sorted(fresh, key=lambda t: str(t.get("speaker"))):
        speaker = str(turn.get("speaker"))
        side = sides["alice_side"] if speaker == "Alice" else sides["bob_side"]
        print()
        print(f"  {speaker} — still arguing its assigned side: {side}")
        print(f"  [round {turn.get('round')}  parse_mode={turn.get('parse_mode')}  "
              f"repairs={turn.get('repair_attempts')}  "
              f"words={turn.get('word_count')}  finish={turn.get('finish_reason')}]")
        print()
        print(indent(turn.get("argument", ""), "      "))

    print()
    print(THIN)
    print(f"OLD VERDICT (M0, from the THREE-round transcript): "
          f"{manifest.get('source_verdict')}   correct={manifest.get('source_correct')}")
    print(f"NEW VERDICT (the same judge, from the FOUR-round transcript): "
          f"{verdict.get('verdict')}   correct={verdict.get('correct')}   "
          f"[parse_mode={verdict.get('parse_mode')}  "
          f"repairs={verdict.get('repair_attempts')}]")
    changed = verdict.get("verdict") != manifest.get("source_verdict")
    print(f"  -> {'OVERTURNED vs M0' if changed else 'UNCHANGED vs M0'}")
    print()
    print("THE NEW JUDGMENT, VERBATIM:")
    print()
    print(indent(verdict.get("reasoning", "")))
    return {
        "cell_id": manifest.get("cell_id"), "subset": manifest.get("subset"),
        "m0_right": manifest.get("source_correct"),
        "old": manifest.get("source_verdict"), "new": verdict.get("verdict"),
        "changed": changed, "turns": len(fresh),
        "repairs": sum(t.get("repair_attempts", 0) for t in fresh),
        "modes": {t.get("parse_mode") for t in fresh},
    }


def dump_messages() -> int:
    """The exact prompts, off `calls.jsonl` — not a re-render.

    `--messages` writes one round-4 debater turn of each stance and the recourse-judge call
    from the FIRST cell of the round tree that has all three, verbatim as they went over
    the wire. It is what makes "the four new prompts say what they were meant to say" a
    thing a reader can check rather than take from a renderer that might be interpolating
    differently from the builder.
    """
    logs = sorted(ROUND_TREE.glob("cells/*/contests/*/runs/*/calls.jsonl"))
    print("THE EXACT MESSAGES SENT, from calls.jsonl — both round-4 debaters and the "
          "recourse judge")
    print(RULE)
    print(f"smoke {SMOKE}   tree: {ROUND_TREE}")
    print()
    print("The prompt as it went over the wire. The spliced debater system clause, the")
    print("decision/judgment/objection blocks, the PRO and ANTI round instructions, and the")
    print("one block the recourse judge's materiality template gained.")
    for log in logs:
        records = [json.loads(line) for line in log.read_text().splitlines()
                   if line.strip()]
        roles = {r.get("role") for r in records}
        if not {"recourse_debater", "recourse_judge"} <= roles:
            continue
        cell = str(log).split("/cells/")[1].split("/")[0]
        want = {"recourse_debater": 2, "recourse_judge": 1}
        for r in records:
            role = r.get("role")
            if want.get(role, 0) <= 0:
                continue
            want[role] -= 1
            body = r["request_body"]
            print()
            print("#" * 100)
            print(f"# cell={cell}")
            print(f"# role={role}  speaker={r.get('speaker')}  round={r.get('round')}  "
                  f"stance={r.get('stance')}  purpose={r.get('purpose')}")
            print(f"# model={body['model']}  temperature={body['temperature']}  "
                  f"max_tokens={body['max_tokens']}  reasoning={body.get('reasoning')}  "
                  f"provider={body.get('provider')}")
            print(f"# served by: {(r.get('response_body') or {}).get('provider')}  "
                  f"status={r.get('status')}  finish={r.get('finish_reason')}")
            print("#" * 100)
            for message in body["messages"]:
                print()
                print(f"----- {message['role'].upper()} -----")
                print(message["content"])
            print()
            print("----- REPLY -----")
            print((r["response_body"]["choices"][0]["message"] or {}).get("content"))
        return 0
    print(f"\nNOT RUN — no wire log under {ROUND_TREE} holds both roles.")
    return 0


def main() -> int:
    if "--messages" in sys.argv:
        return dump_messages()
    print(__doc__.strip())

    print()
    print("#" * 100)
    print(f"# SMOKE {SMOKE}")
    print("# HALF 1 — THE CONTEST ROUND. The objection is ARGUED, then ruled.")
    print(f"# tree: {ROUND_TREE}")
    print("#" * 100)
    round_rows = []
    jd5 = jd5_rulings()
    if not jd5:
        print(f"\nnote: {JD5_REAL} is not on disk, so jd5-B's ruling on each cell — the "
              "one jd6-R is the counterfactual to — cannot be shown.")
    runs = sorted(ROUND_TREE.glob("cells/*/contests/*/runs/*/ruling.json"))
    claimed_r, failed_r = attempts(
        ROUND_TREE, "cells/*/contests/*/runs/*/run.json")
    print_attempts("HALF 1, the contest round", claimed_r, failed_r, len(runs))
    if not runs:
        print(f"\nNOT RUN — no rulings under {ROUND_TREE}")
    for path in runs:
        round_rows.append(render_round_cell(path.parent, jd5))

    print()
    print("#" * 100)
    print("# HALF 2 — THE PLAIN ROUND. One more ORDINARY round, then re-judged.")
    print(f"# tree: {PLAIN_TREE}")
    print("#" * 100)
    plain_rows = []
    runs = sorted(PLAIN_TREE.glob("cells/*/runs/*/verdict.json"))
    claimed_p, failed_p = attempts(PLAIN_TREE, "cells/*/runs/*/run.json")
    print_attempts("HALF 2, the plain round", claimed_p, failed_p, len(runs))
    if not runs:
        print(f"\nNOT RUN — no decisions under {PLAIN_TREE}")
    for path in runs:
        plain_rows.append(render_plain_cell(path.parent))

    print()
    print(RULE)
    print("SUMMARY — HALF 1, THE CONTEST ROUND")
    print(RULE)
    print(f"attempted {len(claimed_r)} / completed {len(round_rows)} / "
          f"failed {len(failed_r)}"
          + ("   — the failed cells are listed above and LEAVE every paired table under "
             "PREREG.md's loss rule" if failed_r else ""))
    print(f"{'cell_id':<44}{'subset':>11}{'M0 right':>10}{'M1':>10}{'jd5-B':>10}"
          f"{'jd6-R':>10}{'pro':>7}{'turns':>7}{'rep':>5}")
    print(THIN)
    for row in round_rows:
        print(f"{str(row['cell_id']):<44}{str(row['subset']):>11}"
              f"{str(row['m0_right']):>10}{str(row['m1']):>10}"
              f"{str(row['jd5b']):>10}"
              f"{str(row['new']):>10}{str(row['pro']):>7}"
              f"{row['turns']:>7}{row['repairs']:>5}")
    print(THIN)
    if round_rows:
        modes = set().union(*(r["modes"] for r in round_rows))
        print(f"parse modes across every round-4 turn: {sorted(modes)}")
        print(f"format repairs: {sum(r['repairs'] for r in round_rows)}")
        print(f"cells whose derived PRO speaker disagrees with the ruling's record: "
              f"{sum(1 for r in round_rows if not r['agree'])}  (must be 0)")
        print(f"cells whose round is not two turns: "
              f"{sum(1 for r in round_rows if r['turns'] != 2)}  (must be 0)")
        print(f"ruling_line_mismatch: "
              f"{sum(1 for r in round_rows if r['mismatch'])} of {len(round_rows)}")
        moved = [r for r in round_rows if r["jd5b"] and r["jd5b"] != r["new"]]
        print(f"rulings that MOVED against jd5-B's — the SAME prompt with no round: "
              f"{len(moved)} of {len(round_rows)}"
              + (f"  ({', '.join(r['cell_id'] for r in moved)})" if moved else ""))
        moved_m1 = [r for r in round_rows if r["m1"] != r["new"]]
        print(f"rulings that MOVED against M1's — a DIFFERENT prompt, so not the "
              f"round's doing: {len(moved_m1)} of {len(round_rows)}")

    print()
    print(RULE)
    print("SUMMARY — HALF 2, THE PLAIN ROUND")
    print(RULE)
    print(f"attempted {len(claimed_p)} / completed {len(plain_rows)} / "
          f"failed {len(failed_p)}"
          + ("   — the failed cells are listed above and LEAVE every paired table under "
             "PREREG.md's loss rule" if failed_p else ""))
    print(f"{'cell_id':<44}{'subset':>11}{'M0 right':>10}{'M0':>9}"
          f"{'new':>9}{'moved':>8}{'turns':>7}{'rep':>5}")
    print(THIN)
    for row in plain_rows:
        print(f"{str(row['cell_id']):<44}{str(row['subset']):>11}"
              f"{str(row['m0_right']):>10}{str(row['old']):>9}"
              f"{str(row['new']):>9}{str(row['changed']):>8}"
              f"{row['turns']:>7}{row['repairs']:>5}")
    print(THIN)
    if plain_rows:
        modes = set().union(*(r["modes"] for r in plain_rows))
        print(f"parse modes across every round-4 turn: {sorted(modes)}")
        print(f"format repairs: {sum(r['repairs'] for r in plain_rows)}")
        print(f"cells whose round is not two turns: "
              f"{sum(1 for r in plain_rows if r['turns'] != 2)}  (must be 0)")

    print()
    print(RULE)
    print("SIX CELLS IS SIX CELLS. Nothing here is a rate. What this read is for is")
    print("whether the four new prompts say what they were meant to say and whether the")
    print("round is the protocol the design describes; the paired arms are the")
    print("measurement, and they are pre-registered before either is run.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

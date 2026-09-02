"""Re-read the two fd1 pilots' stored rulings with the REVISED ruling-reader prompt.

    cd exp2
    uv run python records/derivations/fd1-reread-pilot-rulings.py --dry-run
    uv run python records/derivations/fd1-reread-pilot-rulings.py 2>&1 | tee outputs/fd1-reread-pilot.log

WHY THIS SCRIPT EXISTS. The pilot read of 2026-09-02 found `ruling_line_mismatch` firing
on 17 of the weak arm's 44 rulings, and a hand read of five of those found the reader
doing two things its prompt permitted and its job forbids: marking INCONSISTENT because it
DISAGREED ON THE MERITS with a ruling whose prose does reach the answer its own reasons
argue for ("reasonableness and plausibility do not negate the flaw"), and once misreading
what a ruling line means ("'the finding stands' means the objection fails, but 'Contest 2:
FLAW' suggests the objection succeeds"). R12g rewrote the reader's two prompts for exactly
those two failures.

THE READER IS AN OFF-PATH INSTRUMENT. Nothing it says reaches a judge, a challenger or a
grader; no decision, ruling, verdict or grade moves with it. So its prompt may change
after a smoke and be validated the cheap way — by RE-READING rulings already on disk —
rather than by spending a fresh smoke, and that is what this does: one Haiku call per
stored pilot ruling, 66 in all, through `recourse.judge_ruling_prose` and
`client.OpenRouterClient` so the wire call is byte-for-byte the call the
`ruling_agreement` stage makes.

IT WRITES NOTHING INTO EITHER PILOT TREE. The stage's sink would append to each contest's
`calls.jsonl` and its writer would overwrite `ruling_agreement.json`; here the sink is a
list in memory and every output goes under `outputs/fd1-reread-pilot/`. The pilots stay
exactly as they were run, so the OLD reading remains on disk to be compared against.

WHAT IT PRINTS. Per arm: the old mismatch rate and the new one, the 2x2 of old-against-new
mismatch, and the 3x3 of the reader's own word (CONSISTENT / INCONSISTENT / NEITHER, read
back out of both raw replies). Then, for a sample of rulings where the two readings
DISAGREE, the tail of the ruling's own prose, its lines, and both readings — so the
reviewer judges which reader was right rather than taking the rate on trust.

`--dry-run` counts the rulings and prices them off the pilots' own recorded reader calls,
and sends nothing.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from exp2.accounting import read_calls
from exp2.client import OpenRouterClient
from exp2.config import load_config, load_grading_config
from exp2.prompts import _FINDINGS_READING_RE
from exp2.recourse import judge_ruling_prose
from exp2.types import Ruling, RulingAgreement

REPO = Path(__file__).resolve().parents[2]          # exp2/
TREES = ("fd1-pilot-weak", "fd1-pilot-strong")
SPEC_FOR_TREE = {
    "fd1-pilot-weak": "experiments/fd1-pilot-weak.toml",
    "fd1-pilot-strong": "experiments/fd1-pilot-strong.toml",
}
READINGS = ("CONSISTENT", "INCONSISTENT", "NEITHER", "(unreadable)")


def reading_word(raw: str) -> str:
    """The reader's own word, read back out of a stored or fresh reply.

    `RulingAgreement` stores the TRANSLATED conclusion, not the word — the translation is
    done in code so it can be tested — so the word is recovered here for the 3x3. Read
    with the PARSER'S OWN regex rather than one written here: the readers wrap the line
    in backticks often enough (3 of the weak pilot's 44 stored replies) that a stricter
    pattern reports "(unreadable)" for replies the harness parsed without trouble. Last
    match wins, as `_last` does.
    """
    matches = _FINDINGS_READING_RE.findall(raw or "")
    return matches[-1].upper() if matches else "(unreadable)"


def rulings_in(tree: Path) -> list[dict[str, Any]]:
    """Every stored ruling under one pilot tree, with the two artifacts beside it.

    The same gate the stage applies: a ruling with no prose is not read, because a
    reading of an empty string is a NEITHER that looks like a measurement.
    """
    found: list[dict[str, Any]] = []
    for path in sorted(tree.glob("cells/*/contests/*/runs/*/ruling.json")):
        directory = path.parent
        ruling = Ruling.from_dict(json.loads(path.read_text(encoding="utf-8")))
        if not ruling.reasoning.strip():
            continue
        challenge_path = directory / "challenge.json"
        contests = None
        if challenge_path.is_file():
            defects = json.loads(challenge_path.read_text(
                encoding="utf-8")).get("defects")
            contests = defects if isinstance(defects, list) else None
        old = None
        old_path = directory / "ruling_agreement.json"
        if old_path.is_file():
            old = RulingAgreement.from_dict(
                json.loads(old_path.read_text(encoding="utf-8")))
        found.append({
            # cells/<cell>/contests/<model>/runs/<run>/ruling.json
            "cell": path.parents[4].name,
            "directory": directory,
            "ruling": ruling,
            "contests": contests,
            "old": old,
            # An objection every one of whose contests was void: its ruling's verdict is
            # derived with all of the judge's lines discarded, so `mismatch` is not a
            # meaningful comparison on it (R12g). Carried here so the report can quote
            # the rate both ways rather than only the pooled one.
            "void_only": bool(contests) and all(c.get("void") for c in contests),
        })
    return found


def measured_reader_cost(tree: Path) -> tuple[float, int]:
    """``(total cost, calls)`` of the reader calls the PILOT itself made.

    The dry run prices the re-read off the very calls it is repeating, on the same model
    over the same prose, which is a better estimate than any token count taken here.
    """
    total, calls = 0.0, 0
    for log in tree.glob("cells/*/contests/*/runs/*/calls.jsonl"):
        for record in read_calls(log):
            if record.get("role") != "ruling_reader":
                continue
            calls += 1
            total += float((record.get("usage") or {}).get("cost") or 0.0)
    return total, calls


async def reread_tree(name: str, *, api_key: str, limit: int | None) -> list[dict]:
    """One arm: one call per stored ruling, concurrent, nothing written to the tree."""
    tree = REPO / "outputs" / "experiments" / name
    spec = REPO / SPEC_FOR_TREE[name]
    config, client_config = load_config(spec)
    grading = load_grading_config(spec)
    items = rulings_in(tree)
    if limit is not None:
        items = items[:limit]

    calls: list[dict[str, Any]] = []

    async def sink(record: dict[str, Any]) -> None:
        # IN MEMORY, NEVER INTO THE TREE. The stage appends to the contest's own
        # `calls.jsonl`; this must not, or the pilot's accounting would carry calls it
        # never made.
        calls.append(record)

    semaphore = asyncio.Semaphore(client_config.max_concurrency)
    rows: list[dict[str, Any]] = []
    async with OpenRouterClient(api_key, client_config, sink=sink,
                                semaphore=semaphore) as client:
        async def one(entry: dict[str, Any]) -> dict[str, Any]:
            ruling = entry["ruling"]
            try:
                new = await judge_ruling_prose(
                    ruling, contests=entry["contests"], config=config,
                    grading=grading, client=client)
            except Exception as error:                       # noqa: BLE001
                return {"arm": name, "cell": entry["cell"], "status": "failed",
                        "error": f"{type(error).__name__}: {error}"}
            old = entry["old"]
            return {
                "arm": name,
                "cell": entry["cell"],
                "directory": str(entry["directory"].relative_to(REPO)),
                "status": "completed",
                "void_only": entry["void_only"],
                "ruling_verdict": ruling.verdict,
                "parent_verdict": ruling.parent_verdict,
                "lines": ruling.conclusion_line,
                "contests_shown": entry["contests"] is not None,
                "n_contests": len(entry["contests"] or []),
                "old_reading": reading_word(old.raw if old else ""),
                "old_prose_conclusion": old.prose_conclusion if old else None,
                "old_mismatch": old.mismatch if old else None,
                "new_reading": reading_word(new.raw),
                "new_prose_conclusion": new.prose_conclusion,
                "new_mismatch": new.mismatch,
                "new_parse_mode": new.parse_mode,
                "new_repair_attempts": new.repair_attempts,
                "new_call_id": new.call_id,
                "prose": ruling.reasoning,
            }

        rows = await asyncio.gather(*(one(entry) for entry in items))

    by_call = {record.get("call_id"): record for record in calls}
    for row in rows:
        usage = (by_call.get(row.get("new_call_id"), {}).get("usage") or {})
        row["cost_usd"] = float(usage.get("cost") or 0.0)
    total = sum(float((record.get("usage") or {}).get("cost") or 0.0)
                for record in calls)
    print(f"{name}: {len(rows)} rulings re-read, {len(calls)} wire calls, "
          f"${total:.4f}")
    return list(rows)


def crosstab(rows: list[dict], old_key: str, new_key: str,
             values: tuple[Any, ...]) -> dict[Any, dict[Any, int]]:
    table = {old: {new: 0 for new in values} for old in values}
    for row in rows:
        old, new = row.get(old_key), row.get(new_key)
        if old in table and new in table[old]:
            table[old][new] += 1
    return table


def rate(k: int, n: int) -> str:
    return f"{k}/{n} ({k / n:.1%})" if n else f"{k}/0 (n/a)"


def report(all_rows: list[dict], out: Path, *, n_disagreements: int) -> str:
    """The summary tables, printed and written to `report.md`."""
    lines: list[str] = ["# fd1 — the pilot rulings re-read with the revised reader prompt",
                        ""]
    lines.append(
        "One Haiku call per stored pilot ruling under the R12g reader prompts, made "
        "through `recourse.judge_ruling_prose` so the wire call is the stage's. Neither "
        "pilot tree was written to: the OLD column is the reading stored in each "
        "contest's `ruling_agreement.json` at run time, the NEW column is today's.")
    lines.append("")
    lines.append("`mismatch` is `prose_conclusion != line_conclusion`; NEITHER counts as "
                 "a mismatch, as it does everywhere in this codebase. `void-only` "
                 "rulings are the ones R12g stops computing the column for at all — "
                 "their verdict is derived with every one of the judge's lines "
                 "discarded — and they are shown apart rather than dropped here.")
    lines.append("")

    arms = sorted({row["arm"] for row in all_rows})
    lines.append("## Mismatch rate, old prompt against new")
    lines.append("")
    lines.append("| arm | rulings | OLD mismatch | NEW mismatch | "
                 "NEW, excluding void-only |")
    lines.append("|---|---|---|---|---|")
    for arm in arms + ["ALL"]:
        rows = [r for r in all_rows
                if r["status"] == "completed" and (arm == "ALL" or r["arm"] == arm)]
        live = [r for r in rows if not r["void_only"]]
        lines.append(
            f"| `{arm}` | {len(rows)} "
            f"| {rate(sum(1 for r in rows if r['old_mismatch']), len(rows))} "
            f"| {rate(sum(1 for r in rows if r['new_mismatch']), len(rows))} "
            f"| {rate(sum(1 for r in live if r['new_mismatch']), len(live))} |")
    lines.append("")

    lines.append("## Old against new, per ruling")
    lines.append("")
    for arm in arms + ["ALL"]:
        rows = [r for r in all_rows
                if r["status"] == "completed" and (arm == "ALL" or r["arm"] == arm)]
        table = crosstab(rows, "old_mismatch", "new_mismatch", (False, True))
        lines.append(f"**{arm}** — mismatch old (rows) x new (columns)")
        lines.append("")
        lines.append("| old \\ new | consistent | MISMATCH |")
        lines.append("|---|---|---|")
        for old in (False, True):
            label = "MISMATCH" if old else "consistent"
            lines.append(f"| {label} | {table[old][False]} | {table[old][True]} |")
        lines.append("")
        words = crosstab(rows, "old_reading", "new_reading", READINGS)
        lines.append(f"**{arm}** — the reader's own word, old (rows) x new (columns)")
        lines.append("")
        lines.append("| old \\ new | " + " | ".join(READINGS) + " |")
        lines.append("|---" * (len(READINGS) + 1) + "|")
        for old in READINGS:
            lines.append(f"| {old} | "
                         + " | ".join(str(words[old][new]) for new in READINGS) + " |")
        lines.append("")

    failed = [r for r in all_rows if r["status"] != "completed"]
    if failed:
        lines.append(f"## {len(failed)} rulings FAILED to re-read")
        lines.append("")
        for row in failed:
            lines.append(f"* `{row['arm']}` `{row['cell']}` — {row['error']}")
        lines.append("")

    lines.append("## Every ruling the NEW reader still marks a mismatch")
    lines.append("")
    lines.append("Few enough to name. `void-only` rulings are the ones `build_index` "
                 "no longer computes the column for at all, so the rate that matters is "
                 "the one over the rest.")
    lines.append("")
    lines.append("| arm | cell | old reading | new reading | void-only |")
    lines.append("|---|---|---|---|---|")
    for row in [r for r in all_rows if r["status"] == "completed" and r["new_mismatch"]]:
        lines.append(f"| `{row['arm']}` | `{row['cell']}` | {row['old_reading']} "
                     f"| {row['new_reading']} | {row['void_only']} |")
    lines.append("")

    lines.append(f"## {n_disagreements} rulings where the two readers DISAGREE")
    lines.append("")
    lines.append("Printed for the hand check: the tail of the ruling's own prose (the "
                 "text the reader was given, minus its decision lines), the lines it "
                 "ended on, and both readings. The question for the reviewer is which "
                 "reader is right, not which rate is lower.")
    lines.append("")
    disagreements = [r for r in all_rows if r["status"] == "completed"
                     and r["old_reading"] != r["new_reading"]]
    for row in disagreements[:n_disagreements]:
        lines.append(f"### `{row['arm']}` — `{row['cell']}`")
        lines.append("")
        lines.append(f"* old reading **{row['old_reading']}** → "
                     f"`prose_conclusion` {row['old_prose_conclusion']}, "
                     f"mismatch {row['old_mismatch']}")
        lines.append(f"* new reading **{row['new_reading']}** → "
                     f"`prose_conclusion` {row['new_prose_conclusion']}, "
                     f"mismatch {row['new_mismatch']}")
        lines.append(f"* the ruling's own verdict {row['ruling_verdict']}, parent "
                     f"{row['parent_verdict']}, {row['n_contests']} contests, "
                     f"void-only {row['void_only']}")
        lines.append("")
        lines.append("The ruling's lines:")
        lines.append("")
        lines.append("```")
        lines.append((row["lines"] or "(none recorded)").strip())
        lines.append("```")
        lines.append("")
        lines.append("The last 400 characters of the ruling's prose:")
        lines.append("")
        lines.append("```")
        lines.append(row["prose"][-400:].strip())
        lines.append("```")
        lines.append("")
    if not disagreements:
        lines.append("*(none: the two prompts read every ruling the same way)*")
        lines.append("")

    text = "\n".join(lines)
    out.write_text(text, encoding="utf-8")
    return text


def rebuild_rows(trees: list[str], out_dir: Path) -> list[dict]:
    """The stored rows again, with `prose` and the OLD reading re-read off disk.

    So the report can be rebuilt — a wording fix, a different sample of disagreements, a
    corrected reading of the stored replies — WITHOUT spending the 66 calls again. The
    NEW columns come from the jsonl this script wrote; everything that can be recovered
    from the untouched pilot trees is recovered rather than trusted.
    """
    rows: list[dict] = []
    for name in trees:
        path = out_dir / f"{name}.jsonl"
        if not path.is_file():
            raise SystemExit(f"no stored rows at {path}; run without --rebuild-report")
        rebuilt: list[dict] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            row = json.loads(line)
            directory = REPO / row["directory"]
            ruling = Ruling.from_dict(
                json.loads((directory / "ruling.json").read_text(encoding="utf-8")))
            row["lines"] = ruling.conclusion_line
            # cells/<cell>/contests/<model>/runs/<run>
            row["cell"] = directory.parents[3].name
            old_path = directory / "ruling_agreement.json"
            if old_path.is_file():
                old = json.loads(old_path.read_text(encoding="utf-8"))
                row["old_reading"] = reading_word(old.get("raw") or "")
            rebuilt.append(dict(row))
            row["prose"] = ruling.reasoning
            rows.append(row)
        with path.open("w", encoding="utf-8") as handle:
            for row in rebuilt:
                handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    return rows


def dry_run(trees: list[str]) -> int:
    total_rulings, total_cost = 0, 0.0
    print("=== fd1 pilot re-read — DRY RUN, nothing is sent ===\n")
    for name in trees:
        tree = REPO / "outputs" / "experiments" / name
        if not tree.is_dir():
            print(f"{name}: NOT FOUND at {tree}")
            return 1
        items = rulings_in(tree)
        cost, calls = measured_reader_cost(tree)
        per_call = cost / calls if calls else 0.0
        total_rulings += len(items)
        total_cost += per_call * len(items)
        void_only = sum(1 for entry in items if entry["void_only"])
        with_contests = sum(1 for entry in items if entry["contests"] is not None)
        print(f"{name}:")
        print(f"  rulings with prose to read : {len(items)}")
        print(f"  of which void-only         : {void_only}")
        print(f"  with contests to show      : {with_contests}")
        print(f"  the pilot's own reader calls: {calls} at ${cost:.4f} "
              f"(${per_call:.5f} each)")
        print(f"  estimated                  : ${per_call * len(items):.4f}\n")
    print(f"TOTAL: {total_rulings} calls, about ${total_cost:.3f}. "
          f"Nothing was sent.")
    return 0


async def main_async(args) -> int:
    load_dotenv()  # the repo-root .env, found by walking up from exp2/
    key = os.environ["OPENROUTER_KEY"]
    out_dir = REPO / "outputs" / "fd1-reread-pilot"
    out_dir.mkdir(parents=True, exist_ok=True)
    all_rows: list[dict] = []
    for name in args.trees:
        rows = await reread_tree(name, api_key=key, limit=args.limit)
        path = out_dir / f"{name}.jsonl"
        with path.open("w", encoding="utf-8") as handle:
            for row in rows:
                # the prose is in the report's excerpts, not in every row
                handle.write(json.dumps({k: v for k, v in row.items()
                                         if k != "prose"}, ensure_ascii=False) + "\n")
        print(f"  wrote {path.relative_to(REPO)}")
        all_rows.extend(rows)
    text = report(all_rows, out_dir / "report.md",
                  n_disagreements=args.disagreements)
    print()
    print(text)
    print(f"\nwrote {(out_dir / 'report.md').relative_to(REPO)}")
    spend = sum(row.get("cost_usd") or 0.0 for row in all_rows)
    print(f"SPENT: ${spend:.4f} over {len(all_rows)} rulings")
    return 0 if all(row["status"] == "completed" for row in all_rows) else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true",
                        help="count the rulings and price them; send nothing")
    parser.add_argument("--tree", "--trees", dest="trees", nargs="*",
                        default=list(TREES), choices=list(TREES))
    parser.add_argument("--limit", type=int, default=None,
                        help="re-read at most this many rulings per tree")
    parser.add_argument("--disagreements", type=int, default=6,
                        help="how many old-vs-new disagreements to print in full")
    parser.add_argument("--rebuild-report", action="store_true",
                        help="rebuild report.md from the stored rows; send nothing")
    args = parser.parse_args()
    if args.dry_run:
        return dry_run(args.trees)
    if args.rebuild_report:
        out_dir = REPO / "outputs" / "fd1-reread-pilot"
        rows = rebuild_rows(args.trees, out_dir)
        print(report(rows, out_dir / "report.md",
                     n_disagreements=args.disagreements))
        return 0
    return asyncio.run(main_async(args))


if __name__ == "__main__":
    sys.exit(main())

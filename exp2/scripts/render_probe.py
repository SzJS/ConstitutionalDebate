#!/usr/bin/env python
"""Turn the probe's wire records into something a person can read.

    uv run python scripts/render_probe.py
    uv run python scripts/render_probe.py --per-subset 2 --out outputs/pick-weak/review

`pick_weak.py` leaves behind `fixture.jsonl` (the strong model's debates) and
`calls-<model>.jsonl` (every request and response, verbatim). Neither is readable, and
the decision the probe feeds — which weak model, which subsets — is one the user has to
be able to check by eye before any of it is paid forward into a pilot. So this writes
one markdown file per selected item:

    the problem, the text under review, who argued which side,
    the six public arguments by round,
    then per candidate: its verdict + stated grounds, and its objection or decline,
    and the gold label, LAST.

**The gold label is at the bottom on purpose.** A reader who knows the answer before
reading the arguments cannot tell whether the record is legible; they can only tell
whether they agree. Read down, decide, then scroll.

## How the join works

`Row` carries `item_id` but no `call_id`, and the wire records carry `call_id` but no
`item_id`, so there is no key shared between them. The join is therefore on **content**:
every judge and challenger prompt interpolates the item's problem and solution verbatim,
so slices of *both* are searched for in the concatenated messages of each request, and a
call belongs to an item only when both appear. Both are needed — flawed and sound
siblings share a problem, and lojban's solutions are forty characters long — and the
pair is checked for uniqueness across the fixture before use, with any item that is
textually indistinguishable from another reported and skipped rather than guessed at.
On the first probe's records this joins 71/71 judge calls per candidate.

Within an item, the *accepted* reply is the last one that parses — which is the repair
when a repair was needed, and the first attempt otherwise. That mirrors what
`_complete_with_repair` did at the time.
"""

from __future__ import annotations

import argparse
import collections
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from exp2.artifacts import _positions_section, _quote, _rounds_section  # noqa: E402
from exp2.prompts import (  # noqa: E402
    MalformedOutputError,
    parse_objection_output,
    parse_verdict_output,
)

# Long enough to be unique across a 7-subset fixture, short enough to survive an item
# whose problem is only a couple of lines.
NEEDLE_CHARS = 160


# --------------------------------------------------------------------------- #
# loading
# --------------------------------------------------------------------------- #


def load_jsonl(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()]


def candidate_models(outputs: Path) -> list[str]:
    """Every model with a judge pass on disk, in filename order."""
    return sorted(p.name[len("rows-judge-"):-len(".jsonl")]
                  for p in outputs.glob("rows-judge-*.jsonl"))


def request_text(record: dict) -> str:
    body = record.get("request_body") or {}
    messages = body.get("messages") or []
    return "\n".join(str(m.get("content", "")) for m in messages)


def response_text(record: dict) -> str:
    body = record.get("response_body") or {}
    try:
        return body["choices"][0]["message"]["content"] or ""
    except (KeyError, IndexError, TypeError):
        return ""


def needles_for(entry: dict) -> tuple[str, ...]:
    """Slices of the item that must ALL appear in a prompt for it to be that item's.

    Neither field alone identifies an item. Sibling FindTheFlaws items share a problem
    statement between their flawed and sound variants, and lojban's problems are a
    shared boilerplate preamble — while lojban's *solutions* are 40 characters long, so
    a solution slice alone is thin. Requiring both is what makes the join exact: the
    first join attempt used one field with a fallback and silently lost the three lojban
    items whose problems begin identically.
    """
    fields = ((entry["item"].get("solution") or ""), (entry["item"].get("problem") or ""))
    return tuple(normalise(f)[:NEEDLE_CHARS] for f in fields if f.strip())


def normalise(text: str) -> str:
    return " ".join(text.split())


# --------------------------------------------------------------------------- #
# the join
# --------------------------------------------------------------------------- #


def index_calls(records: list[dict], fixture: list[dict], purposes: set[str]) -> dict:
    """`item_id -> [records]`, matched on the item's own text appearing in the prompt."""
    needles = {e["item"]["item_id"]: needles_for(e) for e in fixture}
    duplicated = {k for k, v in collections.Counter(needles.values()).items() if v > 1}
    if duplicated:
        clashing = sorted(i for i, n in needles.items() if n in duplicated)
        print(f"  warning: {len(clashing)} fixture items are textually "
              f"indistinguishable and cannot be joined; skipped: {clashing}")
    unique = {i: n for i, n in needles.items() if n and n not in duplicated}

    found: dict[str, list[dict]] = collections.defaultdict(list)
    for record in records:
        if record.get("purpose") not in purposes:
            continue
        haystack = normalise(request_text(record))
        for item_id, needle in unique.items():
            if all(part in haystack for part in needle):
                found[item_id].append(record)
                break
    return found


def accepted(records: list[dict], parse) -> tuple[object | None, str, int]:
    """The last reply that parses, plus its raw text and how many replies preceded it.

    `_complete_with_repair` accepts the first parseable reply and stops, so the last
    parseable record in file order is the one that was used.
    """
    for index in range(len(records) - 1, -1, -1):
        text = response_text(records[index])
        try:
            return parse(text), text, index
        except MalformedOutputError:
            continue
    return None, (response_text(records[-1]) if records else ""), len(records) - 1


# --------------------------------------------------------------------------- #
# selection
# --------------------------------------------------------------------------- #


def verdicts_by_item(outputs: Path, models: list[str]) -> dict[str, dict[str, str]]:
    out: dict[str, dict[str, str]] = collections.defaultdict(dict)
    for model in models:
        for row in load_jsonl(outputs / f"rows-judge-{model}.jsonl"):
            if row.get("verdict"):
                out[row["item_id"]][model] = row["verdict"]
    return out


def select(fixture: list[dict], verdicts: dict, per_subset: int) -> list[dict]:
    """Per subset: the items where the candidates disagreed most, and where they agreed.

    A disagreement is where the record was read two different ways, which is where its
    legibility is actually in question; an agreement is the ordinary case, and a review
    package of nothing but hard cases would misrepresent the corpus.
    """
    by_subset: dict[str, list[dict]] = collections.defaultdict(list)
    for entry in fixture:
        by_subset[entry["item"]["subset"]].append(entry)

    chosen: list[dict] = []
    for subset in sorted(by_subset):
        entries = by_subset[subset]

        def spread(entry: dict) -> tuple[int, str]:
            counts = collections.Counter(
                verdicts.get(entry["item"]["item_id"], {}).values())
            minority = sum(counts.values()) - (counts.most_common(1)[0][1]
                                               if counts else 0)
            return minority, entry["item"]["item_id"]

        ranked = sorted(entries, key=spread, reverse=True)
        picked = []
        half = max(1, per_subset // 2)
        picked += ranked[:half]                      # most disagreement
        for entry in reversed(ranked):               # most agreement
            if len(picked) >= per_subset:
                break
            if entry not in picked:
                picked.append(entry)
        chosen += picked
    return chosen


# --------------------------------------------------------------------------- #
# rendering
# --------------------------------------------------------------------------- #


def render(entry: dict, models: list[str], judge_calls: dict, challenge_calls: dict,
           verdicts: dict) -> str:
    item, sides = entry["item"], entry["sides"]
    item_id = item["item_id"]
    flawed_side = "Alice" if sides["alice_side"] == "FLAWED" else "Bob"
    sound_side = "Bob" if flawed_side == "Alice" else "Alice"

    parts = [
        f"# Probe item — {item_id}",
        "",
        f"Subset **{item['subset']}**. **{flawed_side}** was assigned the position that "
        f"the text contains a flaw; **{sound_side}** the position that it does not. "
        "Positions were assigned at random.",
        "",
        "*The gold label is at the bottom of this file, and only there. Read the "
        "arguments and the candidates' verdicts first, decide what you think, then "
        "scroll.*",
        "",
        "## What was being decided",
        "",
        "The question is whether the text under review contains a flaw.",
        "",
        "### The problem", "", _quote(item["problem"]), "",
        "### The text under review", "", _quote(item["solution"]), "",
        _positions_section(sides),
        _rounds_section(entry["transcript"]["turns"]),
        "## What each candidate made of it",
        "",
        "*Each candidate judged this same transcript, then contested its own verdict as "
        "the challenger. Both roles saw the public arguments only.*",
        "",
    ]

    for model in models:
        parts.append(f"### `{model}`")
        parts.append("")
        jcalls = judge_calls.get(model, {}).get(item_id, [])
        parsed, raw, index = accepted(jcalls, parse_verdict_output)
        if parsed is None:
            parts += [f"**Verdict:** none — {len(jcalls)} reply/replies, none parseable."
                      if jcalls else "**Verdict:** no judge call was found for this item.",
                      ""]
            if raw:
                parts += ["**What it wrote:**", "", _quote(raw), ""]
        else:
            verdict, grounds, _ = parsed
            repaired = " (after a format repair)" if index > 0 else ""
            parts += [f"**Verdict:** {verdict}{repaired}", ""]
            parts += ["**Grounds given:**", "",
                      _quote(grounds or "*none stated before the verdict line*"), ""]

        ccalls = challenge_calls.get(model, {}).get(item_id, [])
        cparsed, craw, cindex = accepted(ccalls, parse_objection_output)
        if cparsed is None:
            parts += [("**As challenger:** no reply parsed."
                       if ccalls else "**As challenger:** no call was found."), ""]
            if craw:
                parts += ["**What it wrote:**", "", _quote(craw), ""]
        else:
            _, raised, body, mode, _claimed = cparsed
            repaired = " (after a format repair)" if cindex > 0 else ""
            head = ("**As challenger: objection RAISED**"
                    if raised else "**As challenger: declined to object**")
            parts += [f"{head}{repaired} — parsed `{mode}`", "", _quote(body), ""]

    # The probe runs no comprehension probe — that call only exists on the contest path
    # in the harness proper — so there is no score to print here. Said, rather than
    # silently omitted, so a reader does not go looking for it.
    parts += ["*(No comprehension score: the probe does not run the Likert probe; it "
              "lives on the harness's contest path, not here.)*", ""]

    agreement = collections.Counter(verdicts.get(item_id, {}).values())
    parts += ["## Where the candidates landed", "",
              ", ".join(f"{v}: {n}" for v, n in sorted(agreement.items())) or "—", ""]

    parts += ["---", "",
              "## Gold label",
              "",
              f"The upstream annotation says this solution "
              f"**{'CONTAINS a flaw' if item['gold_flawed'] else 'does NOT contain a flaw'}**"
              f" (`gold_flawed = {item['gold_flawed']}`, label basis "
              f"`{item.get('label_basis')}`).",
              ""]
    return "\n".join(parts).rstrip() + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--outputs", type=Path, default=Path("outputs/pick-weak"))
    parser.add_argument("--out", type=Path, default=None,
                        help="default: <outputs>/review")
    parser.add_argument("--per-subset", type=int, default=2,
                        help="items per subset: half where the candidates disagreed "
                             "most, half where they agreed")
    parser.add_argument("--models", default=None,
                        help="default: every model with a judge pass on disk")
    args = parser.parse_args(argv)

    out_dir = args.out or (args.outputs / "review")
    fixture = load_jsonl(args.outputs / "fixture.jsonl")
    if not fixture:
        print(f"no fixture at {args.outputs / 'fixture.jsonl'}")
        return 1
    models = ([m.strip().replace("/", "-") for m in args.models.split(",")]
              if args.models else candidate_models(args.outputs))
    if not models:
        print(f"no rows-judge-*.jsonl under {args.outputs}")
        return 1
    print(f"fixture: {len(fixture)} debates; candidates: {', '.join(models)}")

    judge_calls, challenge_calls = {}, {}
    for model in models:
        records = load_jsonl(args.outputs / f"calls-{model}.jsonl")
        judge = [r for r in records if r.get("role") == "judge"]
        challenge = [r for r in records if r.get("role") == "challenger"]
        judge_calls[model] = index_calls(judge, fixture, {"judge", "repair"})
        challenge_calls[model] = index_calls(challenge, fixture, {"challenge", "repair"})
        print(f"  {model:36s} joined {len(judge_calls[model]):3d} judge / "
              f"{len(challenge_calls[model]):3d} challenger items")

    verdicts = verdicts_by_item(args.outputs, models)
    chosen = select(fixture, verdicts, args.per_subset)
    out_dir.mkdir(parents=True, exist_ok=True)
    for entry in chosen:
        path = out_dir / f"{entry['item']['item_id']}.md"
        path.write_text(render(entry, models, judge_calls, challenge_calls, verdicts),
                        encoding="utf-8")
    print(f"\nwrote {len(chosen)} files to {out_dir}")
    for entry in chosen:
        print(f"  {out_dir / (entry['item']['item_id'] + '.md')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

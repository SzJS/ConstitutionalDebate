"""Classify pilot-2's failed cells by the SHAPE of the malformed reply.

Reads only what is on disk: every failed decide cell's `calls.jsonl`. For each it finds
the call the cell actually died on — the last repair reply that the real parser still
refuses, or the truncation that was fatal by design — and pairs it with the reply that
bought the repair. Each is labelled with the shape the parser refused it for, and every
label is cross-checked against the DebateFailure message the harness recorded, so a
mis-paired call shows up as a mismatch rather than as a number in the table.
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, "src")
from exp2.prompts import (  # noqa: E402
    _LABEL_RE,
    MalformedOutputError,
    _missing_label_kind,
    parse_debater_output,
    parse_verdict_output,
)

ROOT = Path("outputs/experiments/pilot-2")
SOLO_ROLES = {"solo", "critic", "recourse_solo"}
XML_RE = re.compile(r"(?i)</?\s*(argument|reasoning)\s*>")
# Every shape that means "the parser refused this reply".
FAILING = {
    "no_public_label", "label_not_at_line_start", "xml_tag", "no_labels_at_all",
    "private_label_in_public", "empty_public", "no_verdict_line", "empty_reply",
    "other",
}
# The four shapes that all raise the same "no 'Argument:' label found" message.
NO_LABEL = {"no_public_label", "label_not_at_line_start", "xml_tag", "no_labels_at_all"}


def public_label(role: str) -> str:
    return "Reasoning" if role in SOLO_ROLES else "Argument"


def shape(text: str, role: str, purpose: str) -> str:
    if not text.strip():
        return "empty_reply"
    label = public_label(role)
    # `arms._split_solo` relabels before parsing; mirror it exactly.
    body = text.replace("Reasoning:", "Argument:") if role in SOLO_ROLES else text
    labels = {m.group(1).lower() for m in _LABEL_RE.finditer(body)}
    if "argument" not in labels:
        # The production classifier, so the table and the repair routing cannot drift.
        return _missing_label_kind(body)
    try:
        _, public, _ = parse_debater_output(body)
    except MalformedOutputError as error:
        message = str(error)
        if "contains a 'Thinking:' label" in message:
            return "private_label_in_public"
        if "is empty" in message:
            return "empty_public"
        return "other"
    if role == "solo" and purpose != "critique":
        try:
            parse_verdict_output(public)
        except MalformedOutputError:
            return "no_verdict_line"
    return "parses"


def content(call: dict) -> str:
    try:
        return call["response_body"]["choices"][0]["message"]["content"] or ""
    except (KeyError, IndexError, TypeError):
        return ""


def truncated(call: dict) -> bool:
    return call.get("finish_reason") in ("length", "error")


def expected_shapes(error: str) -> set[str] | None:
    """What the harness's own failure message says the fatal reply looked like."""
    if "truncated" in error or "finish_reason='length'" in error:
        return {"truncated"}
    if "no 'Argument:' label found" in error:
        return NO_LABEL
    if "contains a 'Thinking:' label" in error:
        return {"private_label_in_public"}
    if "section is empty" in error:
        return {"empty_public"}
    if "no 'Verdict:" in error:
        return {"no_verdict_line"}
    return None


rows = [json.loads(line) for line in (ROOT / "cells.jsonl").open()]
failed = [r for r in rows if r["stage"] == "decide" and r["status"] != "completed"]

table = []
for cell in sorted(failed, key=lambda r: r["cell_id"]):
    cell_id, error = cell["cell_id"], cell.get("error", "")
    calls = [
        json.loads(line)
        for run in sorted((ROOT / "cells" / cell_id / "runs").glob("*/calls.jsonl"))
        for line in run.open()
    ]
    want = expected_shapes(error)

    # The fatal call: the last one that the parser still refuses (or that truncated).
    fatal_idx = None
    for i in range(len(calls) - 1, -1, -1):
        c = calls[i]
        s = "truncated" if truncated(c) else shape(content(c), c["role"], c["purpose"])
        if s in FAILING or s == "truncated":
            if want is None or s in want:
                fatal_idx, fatal_shape = i, s
                break
    assert fatal_idx is not None, f"{cell_id}: no call matches its own error {error!r}"

    fatal = calls[fatal_idx]
    key = (fatal["role"], fatal.get("speaker"), fatal.get("round"))
    if fatal.get("purpose") == "repair":
        prior = [
            c for c in calls[:fatal_idx]
            if c.get("purpose") != "repair"
            and (c["role"], c.get("speaker"), c.get("round")) == key
        ]
        first = prior[-1] if prior else None
        purpose = first["purpose"] if first else fatal["purpose"]
        first_shape = (
            "truncated" if first and truncated(first)
            else shape(content(first), fatal["role"], purpose) if first else "-"
        )
        repair_shape = fatal_shape
    else:
        # Fatal on the first call, with no repair: a truncation past the public label.
        first, purpose = fatal, fatal["purpose"]
        first_shape, repair_shape = fatal_shape, "n/a (no repair — fatal by design)"

    table.append((cell_id, cell_id.split("__")[1], fatal["role"], purpose,
                  first_shape, repair_shape))

w = max(len(r[0]) for r in table)
print(f"{'cell':<{w}} {'cond':<14} {'role':<8} {'stage':<9} {'first':<24} repair")
for r in table:
    print(f"{r[0]:<{w}} {r[1]:<14} {r[2]:<8} {r[3]:<9} {r[4]:<24} {r[5]}")

def counts(title, values):
    print(f"\n--- {title} ---")
    for k, v in Counter(values).most_common():
        print(f"  {k:<32} {v}")

counts("FIRST reply (the one that bought the repair)", (r[4] for r in table))
counts("REPAIR reply (the one the cell died on)", (r[5] for r in table))
print("\n--- repair shape x condition ---")
for k, v in sorted(Counter((r[1], r[5]) for r in table).items()):
    print(f"  {k[0]:<14} {k[1]:<32} {v}")
print("\n--- repair shape x solo stage (solo/critic roles only) ---")
for k, v in sorted(Counter((r[3], r[5]) for r in table if r[2] in SOLO_ROLES).items()):
    print(f"  {k[0]:<10} {k[1]:<32} {v}")

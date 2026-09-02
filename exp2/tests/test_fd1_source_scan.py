"""`records/derivations/fd1-source-scan.py` — the inherited-defect count for PREREG.

The script is read-only over a run tree, so it is tested against a tiny synthetic tree
rather than against `jd3-main`. What matters is that the three counts are the ones PREREG
will quote and that nothing is dropped: a scan that quietly skipped the cells it could not
read, or that counted a well-formed `Argument:` label as a defect, would understate or
overstate a caveat nobody can check afterwards.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

SCAN = Path(__file__).resolve().parents[1] / "records/derivations/fd1-source-scan.py"


def _module():
    spec = importlib.util.spec_from_file_location("fd1_source_scan", SCAN)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _tree(tmp_path: Path, cells: dict[str, tuple[str, list[str]]]) -> Path:
    root = tmp_path / "tree"
    (root / "cells").mkdir(parents=True)
    rows = []
    for cell_id, (subset, arguments) in cells.items():
        run = root / "cells" / cell_id / "runs" / "20260101T000000Z-x"
        run.mkdir(parents=True)
        (run / "transcript.json").write_text(json.dumps({
            "turns": [{"speaker": "Alice", "argument": text,
                       # never read by the scan, and asserted so below
                       "thinking": "I am assigned the position of FLAWED."}
                      for text in arguments]}), encoding="utf-8")
        rows.append({"cell_id": cell_id, "subset": subset, "verdict": "SOUND"})
    (root / "index.jsonl").write_text(
        "".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    return root


def test_the_three_counts_are_what_prereg_will_quote(tmp_path, capsys):
    module = _module()
    root = _tree(tmp_path, {
        # a glued label, twice, and a well-formed one at the start of a line
        "a__debate__r1": ("gpqa", ["My case stands. Argument: and here it is.\n"
                                   "More.Argument: again.",
                                   "Argument: this one is fine."]),
        # scaffolding tags the prompts never asked for
        "b__debate__r1": ("law", ["<thinking>hidden</thinking>\n<argument>x</argument>"]),
        # the marker that changes what a finding MEANS
        "c__debate__r1": ("law", ["I need to respond as the SOUND side here."]),
        # and a clean cell
        "d__debate__r1": ("law", ["The step is sound because the formula is standard."]),
    })
    out = tmp_path / "scan.json"
    assert module.main(tree=root, out=out) == 0
    printed = capsys.readouterr().out
    per_cell = json.loads(out.read_text())

    assert set(per_cell) == {"a__debate__r1", "b__debate__r1", "c__debate__r1",
                             "d__debate__r1"}
    # two glued labels; the line-initial `Argument:` is the format, not a defect
    assert per_cell["a__debate__r1"]["glued_argument_n"] == 2
    assert per_cell["a__debate__r1"]["private_marker_n"] == 0
    assert per_cell["b__debate__r1"]["scaffolding_tag_n"] == 4
    assert per_cell["b__debate__r1"]["tags"]["</argument>"] == 1
    assert per_cell["c__debate__r1"]["markers"] == {"I need to respond as": 1}
    assert per_cell["d__debate__r1"]["glued_argument_n"] == 0
    assert per_cell["d__debate__r1"]["scaffolding_tag_n"] == 0
    assert per_cell["d__debate__r1"]["private_marker_n"] == 0

    # THE PRIVATE `thinking` FIELD IS NEVER READ. Every turn above carries a marker
    # phrase in it, and no fd1 role is ever shown that field — counting it would report
    # a defect in the published record that is not in the published record.
    assert sum(c["private_marker_n"] for c in per_cell.values()) == 1

    # the totals, the per-subset table and the named cells all reach the log
    assert "4 decided cells" in printed
    assert "c__debate__r1" in printed
    assert "CELLS WITH ANY PRIVATE-DELIBERATION MARKER (1)" in printed
    assert "gpqa" in printed and "law" in printed
    assert "NOTHING IS EXCLUDED" in printed


def test_a_cell_with_no_transcript_is_reported_and_still_counted(tmp_path, capsys):
    """The missing-cell rule, one level down: a cell the scan cannot read is a cell whose
    counts are unknown, and it stays in the denominator saying so rather than vanishing
    from it."""
    module = _module()
    root = _tree(tmp_path, {"a__debate__r1": ("law", ["fine."])})
    (root / "index.jsonl").write_text(
        (root / "index.jsonl").read_text()
        + json.dumps({"cell_id": "gone__debate__r1", "subset": "law",
                      "verdict": "SOUND"}) + "\n", encoding="utf-8")
    out = tmp_path / "scan.json"
    assert module.main(tree=root, out=out) == 0
    printed = capsys.readouterr().out
    per_cell = json.loads(out.read_text())
    assert set(per_cell) == {"a__debate__r1", "gone__debate__r1"}
    assert per_cell["gone__debate__r1"]["turns_n"] == 0
    assert "no runs directory" in printed

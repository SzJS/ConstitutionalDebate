"""Converters from upstream question sources to ``Task`` objects.

The conversion functions live in the package rather than in ``scripts/`` so they
can be tested against synthetic rows without a network call.

Nothing upstream is vendored. The Habermas Machine data is CC-BY, but neither
GitHub source repo carries a LICENSE file — they are all-rights-reserved by
default — so raw files are fetched into a git-ignored cache and only provenance
(URL, upstream commit, sha256) is recorded.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
from dataclasses import dataclass
from typing import Any, Iterator

from .types import Task


@dataclass(frozen=True)
class Source:
    key: str
    url: str
    filename: str
    note: str


SOURCES: dict[str, Source] = {
    "habermas": Source(
        key="habermas",
        url=(
            "https://raw.githubusercontent.com/google-deepmind/habermas_machine/"
            "main/questions/230118_chinchilla_questions.json"
        ),
        filename="230118_chinchilla_questions.json",
        note="Habermas Machine (DeepMind, Science 2024), CC-BY",
    ),
    "neurips25": Source(
        key="neurips25",
        url=(
            "https://raw.githubusercontent.com/FAIR-IALAB-UBA/Debate-NeurIPS25/"
            "main/sequential_debate/dataset.csv"
        ),
        filename="dataset.csv",
        note="Debate-NeurIPS25 (FAIR-IALAB-UBA); no LICENSE upstream",
    ),
}


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def convert_habermas(raw: str) -> Iterator[Task]:
    """Map Habermas records to tasks.

    The affirming/negating statement pair is already exactly the two-answer
    binary the protocol needs, and there is no ground truth, so ``gold_index``
    is always ``None``.
    """
    for record in json.loads(raw):
        yield Task(
            task_id=f"habermas-{record['id']}",
            question=record["question"],
            answers=(record["affirming_statement"], record["negating_statement"]),
            gold_index=None,
            source=f"habermas:{record['id']}:split={record.get('split')}",
        )


def convert_neurips25(raw: str) -> Iterator[Task]:
    """Map Debate-NeurIPS25 rows to tasks.

    Stances are read from the ``stance_1``/``stance_2`` columns rather than
    assumed to be Yes/No: two of the 145 rows carry other pairs, and hardcoding
    would silently mislabel them.

    The ``judge_persona`` column is read and deliberately dropped. Upstream it is
    a judge-only normative standard; here a normative standard would have to be
    public to both debaters to fit the whitebox claim, so rather than quietly
    reinterpret it we ignore it and supply constitutions explicitly via
    ``--constitution``. It exists; we are not using it yet.
    """
    reader = csv.DictReader(io.StringIO(raw))
    for index, row in enumerate(reader):
        scenario = (row.get("scenario") or "").strip()
        stance_1 = (row.get("stance_1") or "").strip()
        stance_2 = (row.get("stance_2") or "").strip()
        if not (scenario and stance_1 and stance_2):
            continue
        yield Task(
            task_id=f"neurips25-{index:03d}",
            question=scenario,
            answers=(stance_1, stance_2),
            gold_index=None,
            source=f"neurips25:row={index}",
        )


CONVERTERS = {
    "habermas": convert_habermas,
    "neurips25": convert_neurips25,
}


def convert(source_key: str, raw: str) -> list[Task]:
    if source_key not in CONVERTERS:
        raise KeyError(f"unknown source {source_key!r}; expected {sorted(CONVERTERS)}")
    return list(CONVERTERS[source_key](raw))


def provenance(source: Source, raw: str) -> dict[str, Any]:
    return {
        "source": source.key,
        "url": source.url,
        "note": source.note,
        "sha256": sha256_text(raw),
        "bytes": len(raw.encode("utf-8")),
    }

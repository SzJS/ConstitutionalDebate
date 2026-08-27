"""Writing a run to disk, and reading it back.

Every model output is written as it arrives rather than at the end, because a run that
crashes half way through has still cost money and its generations are still data. The
wire log is appended under a lock, since simultaneous debate rounds finish at the same
moment with multi-kilobyte bodies.

Two documents are published. ``transcript.md`` is the readable one; its sibling
``transcript_full.md`` is the same run verbatim — every prompt and every reply as they
went over the wire. Everything else in a run directory exists so those can be checked:
``config.json`` says what settings produced them, ``calls.jsonl`` says what was
actually sent and received, and ``item.json`` says what was being decided. ``flaw.json`` is written but deliberately **never** read by
``load_run_record`` — only ``grading`` opens it, so no decision-path code can reach the
ground truth by accident.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import shutil
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .artifacts import render_recourse_record, render_run_record
from .artifacts_full import render_full_recourse_record, render_full_run_record
from .config import ClientConfig, DebateConfig
from .types import (
    Challenge,
    Comprehension,
    DecisionRecord,
    FlawAnnotation,
    Item,
    Ruling,
    Sides,
    Step,
    Trace,
    Transcript,
    Turn,
    Verdict,
)


def _write_atomic(path: Path, text: str) -> None:
    """Write via a temp file in the same directory, then rename.

    A half-written ``transcript.md`` is worse than a missing one: it looks like a
    record and is not.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as fh:
            fh.write(text)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def _write_json(path: Path, payload: Any) -> None:
    _write_atomic(path, json.dumps(payload, indent=2, ensure_ascii=False))


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def tree_sha256(root: Path) -> str:
    """A hash over a directory's contents, so a copied parent cannot drift unnoticed."""
    digest = hashlib.sha256()
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        digest.update(str(path.relative_to(root)).encode("utf-8"))
        digest.update(path.read_bytes())
    return digest.hexdigest()


def _timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _claim_run_dir(root: Path, item_id: str, suffix: str = "") -> Path:
    """Claim a fresh directory, disambiguating collisions rather than overwriting."""
    base = f"{_timestamp()}-{item_id}{suffix}"
    for attempt in range(1000):
        candidate = root / (base if attempt == 0 else f"{base}-{attempt}")
        try:
            candidate.mkdir(parents=True, exist_ok=False)
            return candidate
        except FileExistsError:
            continue
    raise RuntimeError(f"could not claim a run directory under {root}")


# What a re-rule does NOT copy from the contest it re-rules. See ``create_rerule`` for
# the reason each one is here; ``transcript*.md`` is matched by shape rather than named,
# and only at the top level — the copied ``parent/`` decision has documents and a wire log
# of its own and they are exactly what makes the record self-contained.
_RERULE_EXCLUDED: frozenset[str] = frozenset(
    {"ruling.json", "calls.jsonl", "ruling_agreement.json"}
)


class RunWriter:
    """Owns one run directory. Not reusable across runs."""

    def __init__(self, directory: Path, run_id: str, *, condition: str,
                 parent: Path | None = None):
        self.dir = directory
        self.run_id = run_id
        self.condition = condition
        self._parent = parent
        self._lock = asyncio.Lock()
        self._manifest: dict[str, Any] = {}
        # The form of the ruling a re-rule replaces, ``None`` for every other kind of
        # run. Reported by the stage so a run's own log says what it converted.
        self.rerule_of_form: str | None = None

    # --- construction ---------------------------------------------------------------

    @classmethod
    def create(cls, *, root: Path, item: Item, sides: Sides, config: DebateConfig,
               client_config: ClientConfig, condition: str,
               flaw: FlawAnnotation | None = None) -> "RunWriter":
        directory = _claim_run_dir(root, item.item_id)
        writer = cls(directory, directory.name, condition=condition)
        _write_json(directory / "item.json", item.to_dict())
        _write_json(directory / "sides.json", sides.to_dict())
        _write_json(directory / "config.json", config.to_dict())
        if flaw is not None:
            # Written for provenance, never read back by load_run_record. Only
            # ``grading`` opens it; see load_flaw.
            _write_json(directory / "flaw.json", flaw.to_dict())
        writer._manifest = {
            "run_id": writer.run_id, "kind": "decision", "condition": condition,
            "item_id": item.item_id, "row_id": item.row_id, "subset": item.subset,
            "status": "running", "client_config": client_config.to_dict(),
        }
        writer._flush_manifest()
        return writer

    @classmethod
    def create_recourse(cls, *, root: Path, parent_dir: Path, item: Item, sides: Sides,
                        config: DebateConfig, client_config: ClientConfig,
                        condition: str, copy_parent: bool = True) -> "RunWriter":
        directory = _claim_run_dir(root, item.item_id, suffix="-recourse")
        writer = cls(directory, directory.name, condition=condition, parent=parent_dir)
        for name in ("item.json", "sides.json", "config.json"):
            shutil.copy2(parent_dir / name, directory / name)
        parent_hash = tree_sha256(parent_dir)
        if copy_parent:
            # Self-contained records are the point of the project: a contest you cannot
            # read without also finding the decision is not a published record.
            shutil.copytree(parent_dir, directory / "parent")
        else:
            _write_json(directory / "parent.json",
                        {"path": str(parent_dir), "sha256": parent_hash})
        writer._manifest = {
            "run_id": writer.run_id, "kind": "recourse", "condition": condition,
            "item_id": item.item_id, "row_id": item.row_id, "subset": item.subset,
            "parent_run_id": parent_dir.name, "parent_sha256": parent_hash,
            "parent_copied": copy_parent, "status": "running",
            "client_config": client_config.to_dict(),
        }
        writer._flush_manifest()
        return writer

    @classmethod
    def create_rerule(cls, *, root: Path, source_dir: Path, item: Item, sides: Sides,
                      client_config: ClientConfig, condition: str) -> "RunWriter":
        """A contest directory copied from another tree, ready for a new ruling.

        The objection is not re-made — it is the stakeholder's, it cost real money, and
        re-drawing it would change the population as well as the ruling. So everything
        the source contest recorded is copied: ``challenge.json`` and ``challenge.md``,
        the comprehension probe, the agreement reading, the grade, ``item.json``,
        ``sides.json``, ``config.json`` and the copied ``parent/`` decision. Copying the
        grade through is what lets a re-rule run skip the ``grade`` stage entirely; the
        grade is of the objection, and the objection has not changed.

        Four things are deliberately NOT copied, because they are about to be replaced or
        would be false:

        * ``ruling.json`` — the whole point. It is kept as ``ruling.source.json``, beside
          the new one, so the record carries both and a reader can see the change rather
          than being told about it.
        * ``calls.jsonl`` — the wire log must describe THIS run's one call. A copied log
          would make the full document print the old judge's prompt as though it were
          this ruling's.
        * ``transcript.md`` / ``transcript_full.md`` — re-rendered from the new state by
          ``record_ruling``. A stale document that says "the decision was overturned"
          beside a ruling that upheld it is worse than a missing one.
        * ``ruling_agreement.json`` — a reading of the OLD ruling's prose. The stage will
          make a new one, and a copied one would be silently attributed to the new
          ruling.

        ``run.json`` is copied and then overwritten by the manifest built here, which
        keeps the source's parent pointers — the decision this contest is of — and adds
        ``source_contest_dir``, ``source_sha256`` (a hash of the whole source directory,
        so a source that drifts cannot do so unnoticed) and ``rerule_of_form``.
        """
        directory = _claim_run_dir(root, item.item_id, suffix="-rerule")
        source_hash = tree_sha256(source_dir)
        for entry in sorted(source_dir.iterdir()):
            if entry.name in _RERULE_EXCLUDED or (
                    entry.name.startswith("transcript") and entry.suffix == ".md"):
                continue
            if entry.is_dir():
                shutil.copytree(entry, directory / entry.name)
            else:
                shutil.copy2(entry, directory / entry.name)
        source_ruling = source_dir / "ruling.json"
        rerule_of_form = None
        if source_ruling.is_file():
            shutil.copy2(source_ruling, directory / "ruling.source.json")
            rerule_of_form = _read_json(source_ruling).get("form")
        # ``parent`` is only ever consulted for its truthiness — it selects the contest
        # renderer over the decision one — and a re-rule IS a contest record.
        writer = cls(directory, directory.name, condition=condition, parent=source_dir)
        writer.rerule_of_form = rerule_of_form
        source_manifest: dict[str, Any] = {}
        if (source_dir / "run.json").is_file():
            try:
                source_manifest = _read_json(source_dir / "run.json")
            except ValueError:
                source_manifest = {}
        writer._manifest = {
            "run_id": writer.run_id, "kind": "rerule", "condition": condition,
            "item_id": item.item_id, "row_id": item.row_id, "subset": item.subset,
            # Carried from the source so the re-ruled record still names the DECISION it
            # contests; a reader who followed `parent_run_id` would otherwise land
            # nowhere.
            "parent_run_id": source_manifest.get("parent_run_id"),
            "parent_sha256": source_manifest.get("parent_sha256"),
            "parent_copied": source_manifest.get("parent_copied"),
            "source_contest_dir": str(source_dir),
            "source_sha256": source_hash,
            "rerule_of_form": rerule_of_form,
            "status": "running", "client_config": client_config.to_dict(),
        }
        writer._flush_manifest()
        return writer

    # --- recording ------------------------------------------------------------------

    def _flush_manifest(self) -> None:
        _write_json(self.dir / "run.json", self._manifest)

    def manifest_update(self, **fields: Any) -> None:
        self._manifest.update(fields)
        self._flush_manifest()

    async def record_call(self, record: dict[str, Any]) -> None:
        line = json.dumps(record, ensure_ascii=False)

        def append() -> None:
            with (self.dir / "calls.jsonl").open("a", encoding="utf-8") as fh:
                fh.write(line + "\n")

        async with self._lock:
            await asyncio.to_thread(append)

    def record_turn(self, transcript: Transcript) -> None:
        _write_json(self.dir / "transcript.json", transcript.to_dict())
        self._render()

    def record_step(self, trace: Trace) -> None:
        _write_json(self.dir / "trace.json", trace.to_dict())
        self._render()

    def record_messages(self, messages: list[dict[str, str]]) -> None:
        """The solo conversation, exactly as sent and received.

        The contest replays this file, so it must include a repair's extra turns.
        """
        _write_json(self.dir / "conversation.json", messages)

    def record_verdict(self, verdict: Verdict, body: Transcript | Trace) -> None:
        _write_json(self.dir / "verdict.json", verdict.to_dict())
        self._render()

    def record_challenge(self, challenge: Challenge) -> None:
        _write_json(self.dir / "challenge.json", challenge.to_dict())
        _write_atomic(self.dir / "challenge.md", challenge.text)
        self.manifest_update(challenge_raised=challenge.raised,
                             challenge_sha256=challenge.sha256())
        self._render()

    def record_ruling(self, ruling: Ruling) -> None:
        _write_json(self.dir / "ruling.json", ruling.to_dict())
        self._render()

    def record_comprehension(self, comprehension: Comprehension) -> None:
        _write_json(self.dir / "comprehension.json", comprehension.to_dict())
        self._render()

    def finish(self, status: str, *, error: str | None = None,
               totals: dict[str, Any] | None = None) -> None:
        self.manifest_update(status=status, error=error, **(totals or {}))
        self._render()

    # --- the published document -----------------------------------------------------

    def _render(self) -> None:
        """Rewrite both documents. Independently, so neither can take the other down.

        A bug in the verbatim renderer must not cost a run its readable record, and a
        bug in the readable one must not cost it the wire-faithful record either.
        """
        try:
            document = (render_recourse_record(self.dir) if self._parent is not None
                        else render_run_record(self.dir))
            _write_atomic(self.dir / "transcript.md", document)
        except Exception:  # a partial run must not lose its data to a render bug
            pass
        try:
            full = (render_full_recourse_record(self.dir) if self._parent is not None
                    else render_full_run_record(self.dir))
            _write_atomic(self.dir / "transcript_full.md", full)
        except Exception:
            pass


# --------------------------------------------------------------------------- #
# reading back
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class RunRecord:
    directory: Path
    item: Item
    sides: Sides
    config: DebateConfig
    verdict: Verdict
    condition: str
    transcript: Transcript | None = None
    trace: Trace | None = None
    messages: list[dict[str, str]] | None = None

    def challenger_view(self) -> DecisionRecord:
        """What the challenger — and the recourse judge — are shown.

        Keyed on which body the run actually produced, deliberately **not** on the
        condition name: a manifest string can be wrong, and exp1 shipped a bug where a
        solo decision was described to the challenger as a debate.
        """
        if self.transcript is not None:
            return DecisionRecord.for_debate(self.transcript)
        assert self.trace is not None
        return DecisionRecord.for_solo(self.trace)

    @property
    def decision_grounds(self) -> str:
        """The grounds a contest prompt quotes back.

        Shape-aware, and the asymmetry is deliberate. For a solo decision ``raw``
        contains the model's private ``Thinking:``, so quoting it would show a
        challenger what the record does not publish. For a debate the judge's ``raw`` is
        what ``transcript.md`` prints, and ``reasoning`` is empty whenever the judge
        answered before explaining.
        """
        if self.trace is not None:
            return self.verdict.reasoning
        return self.verdict.raw


def load_run_record(directory: Path) -> RunRecord:
    """Load a *completed* run. Refuses anything else.

    A run without a verdict, or one whose manifest does not say ``completed``, is not a
    decision — treating it as one is how a half-finished cell silently enters an
    analysis.
    """
    manifest = _read_json(directory / "run.json")
    if manifest.get("status") != "completed":
        raise ValueError(f"{directory.name}: status is {manifest.get('status')!r}")
    if not (directory / "verdict.json").is_file():
        raise ValueError(f"{directory.name}: no verdict.json")

    item = Item.from_dict(_read_json(directory / "item.json"))
    sides = Sides(**{**_read_json(directory / "sides.json"),
                     "verdict_order": tuple(_read_json(
                         directory / "sides.json")["verdict_order"])})
    config = DebateConfig(**_read_json(directory / "config.json"))
    verdict_data = _read_json(directory / "verdict.json")
    verdict = Verdict(**{k: v for k, v in verdict_data.items() if k != "says_flawed"})

    transcript = trace = messages = None
    if (directory / "transcript.json").is_file():
        transcript = Transcript(
            [Turn(**_turn_kwargs(t))
             for t in _read_json(directory / "transcript.json")["turns"]]
        )
    if (directory / "trace.json").is_file():
        trace = Trace([Step(**s) for s in _read_json(directory / "trace.json")["steps"]])
    if (directory / "conversation.json").is_file():
        messages = _read_json(directory / "conversation.json")

    return RunRecord(
        directory=directory, item=item, sides=sides, config=config, verdict=verdict,
        condition=manifest.get("condition", "unknown"),
        transcript=transcript, trace=trace, messages=messages,
    )


def _turn_kwargs(data: dict[str, Any]) -> dict[str, Any]:
    from .types import Speaker

    return {**data, "speaker": Speaker(data["speaker"])}


def load_flaw(directory: Path) -> FlawAnnotation | None:
    """The only door to the ground-truth annotation.

    ``load_run_record`` does not read ``flaw.json`` and must not start: the containment
    is structural, so that no decision-path or contest-path code can reach the answer
    even by accident. Only ``grading`` calls this.
    """
    path = directory / "flaw.json"
    if not path.is_file():
        return None
    return FlawAnnotation.from_dict(_read_json(path))

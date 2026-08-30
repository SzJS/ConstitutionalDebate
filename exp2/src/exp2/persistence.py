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
    Admission,
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
    {"ruling.json", "calls.jsonl", "ruling_agreement.json",
     # The contestability debate round's own two turns. A re-rule that copied them
     # forward would put ANOTHER run's exchange in front of this run's judge — and
     # `render_recourse_record` would print it as though these debaters had argued here.
     "recourse_transcript.json"}
)

# What a RE-JUDGE does not copy from the decision it re-judges. See ``create_rejudge``.
# ``calls.jsonl`` is not in the set because it is not dropped but RENAMED — the debate's
# own prompts and replies are what makes the copied transcript verbatim, and they are the
# source run's wire log, not this one's.
_REJUDGE_EXCLUDED: frozenset[str] = frozenset(
    {"verdict.json", "run.json", "config.json", "calls.jsonl"}
)

# What the M4 GATE does not copy from the contest it gates. Note what is NOT here and is
# the whole difference from `_RERULE_EXCLUDED`: `ruling.json` and `ruling_agreement.json`
# ARE copied, because the gate re-rules nothing — M1's ruling is exactly what it decides
# whether to count, so it has to be in the record beside the admission that gates it.
# `calls.jsonl` is renamed rather than dropped, as a re-judge renames it, so the copied
# objection and ruling keep their own prompts in the verbatim document while this run's
# wire log holds this run's one call and the money stays honest.
_GATE_EXCLUDED: frozenset[str] = frozenset({"run.json", "calls.jsonl"})

# Where a re-judged run keeps the source run's wire log. Read by
# ``artifacts_full._load_calls`` so the verbatim document can still print the debaters'
# prompts, and by nothing that counts money: ``accounting`` walks ``calls.jsonl`` alone,
# so a re-judge's spend is its one judge call and never the debate it re-reads.
SOURCE_CALLS = "calls.source.jsonl"


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
    def create_rejudge(cls, *, root: Path, source_dir: Path, config: DebateConfig,
                       client_config: ClientConfig, condition: str,
                       rejudged_from: Path | None = None) -> "RunWriter":
        """A DECISION directory copied from another tree, ready for a new judgment.

        The debate is not re-run — it is the sweep's, it cost real money, and re-drawing
        it would change the population as well as the verdict. So everything the source
        decision recorded about *what was argued* is copied: ``item.json``,
        ``sides.json``, ``transcript.json`` and ``flaw.json``. What comes out is a run
        directory of exactly the same shape as one this harness decided itself, which is
        the whole point: ``decisions_from`` on the tree that holds it works with no
        change anywhere downstream.

        Four things are deliberately NOT copied:

        * ``verdict.json`` — the whole reason for the run. The source verdict is kept in
          the manifest as ``source_verdict`` instead of beside the new one, because a
          second verdict file in a decision directory is exactly the ambiguity
          ``load_run_record`` must never have to resolve.
        * ``config.json`` — written fresh from THIS run's config, so it names the judge
          that actually judged. A copied one would say the record was judged by the
          model the source used, and every contest of it copies that file forward.
        * ``run.json`` — replaced by the manifest built here.
        * ``transcript.md`` / ``transcript_full.md`` — re-rendered from the new state by
          ``record_verdict``. A document that prints the old verdict beside the new one
          is worse than a missing one.

        ``calls.jsonl`` is neither copied nor dropped: it is copied to
        ``calls.source.jsonl``. The debaters' prompts and replies belong to the source
        run and this run made exactly one call, so a copied wire log would bill the
        debate to the re-judge — ``accounting`` walks ``calls.jsonl`` and nothing else,
        and every per-stage spend figure would then include money spent in another run.
        Renaming it keeps the money honest and keeps ``transcript_full.md`` verbatim:
        ``artifacts_full._load_calls`` reads both files, this run's last, so the new
        judge's call is this run's and the debaters' are the source's.
        """
        directory = _claim_run_dir(root, _read_json(source_dir / "item.json")["item_id"],
                                   suffix="-rejudge")
        source_hash = tree_sha256(source_dir)
        for entry in sorted(source_dir.iterdir()):
            if entry.name in _REJUDGE_EXCLUDED or (
                    entry.name.startswith("transcript") and entry.suffix == ".md"):
                continue
            if entry.is_dir():
                shutil.copytree(entry, directory / entry.name)
            else:
                shutil.copy2(entry, directory / entry.name)
        if (source_dir / "calls.jsonl").is_file():
            shutil.copy2(source_dir / "calls.jsonl", directory / SOURCE_CALLS)
        _write_json(directory / "config.json", config.to_dict())
        writer = cls(directory, directory.name, condition=condition)
        source_manifest: dict[str, Any] = {}
        if (source_dir / "run.json").is_file():
            try:
                source_manifest = _read_json(source_dir / "run.json")
            except ValueError:
                source_manifest = {}
        source_verdict: dict[str, Any] = {}
        if (source_dir / "verdict.json").is_file():
            try:
                source_verdict = _read_json(source_dir / "verdict.json")
            except ValueError:
                source_verdict = {}
        source_config: dict[str, Any] = {}
        if (source_dir / "config.json").is_file():
            try:
                source_config = _read_json(source_dir / "config.json")
            except ValueError:
                source_config = {}
        item = _read_json(directory / "item.json")
        writer._manifest = {
            "run_id": writer.run_id, "kind": "rejudge", "condition": condition,
            "item_id": item["item_id"], "row_id": item.get("row_id"),
            "subset": item.get("subset"),
            # The TREE, so a row can say where the transcript came from without a path
            # walk, and the DIRECTORY with a hash of it, so a source that drifts cannot
            # do so unnoticed. Both, for the same reason a re-rule records both.
            "rejudged_from": str(rejudged_from) if rejudged_from else None,
            "source_run_dir": str(source_dir),
            "source_run_id": source_manifest.get("run_id", source_dir.name),
            "source_sha256": source_hash,
            # What the source judge said about this same transcript, and which judge it
            # was. The M0-vs-nano comparison is a column join off these two and needs no
            # second tree open.
            "source_verdict": source_verdict.get("verdict"),
            "source_correct": source_verdict.get("correct"),
            "source_judge_model": source_config.get("judge_model"),
            "status": "running", "client_config": client_config.to_dict(),
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

    @classmethod
    def create_gate(cls, *, root: Path, source_dir: Path, item: Item,
                    client_config: ClientConfig, condition: str) -> "RunWriter":
        """A contest directory copied from another tree, ready for an admissibility gate.

        POST HOC (2026-08-28), and it is the gentlest of the three copying constructors:
        NOTHING already in the source contest is replaced. The objection stands, the
        ruling stands, the grade stands, the readings stand. One file is ADDED —
        ``admission.json`` — and it says whether the ruling beside it is counted.

        That is why ``ruling.json`` is copied here and stripped by ``create_rerule``: a
        re-rule is about to replace the ruling, and a gate is about to decide whether to
        read it. A gate tree with no ruling in it could not be read at all.

        Two things are not copied, for the reasons ``create_rejudge`` gives for the same
        two: ``run.json`` is replaced by the manifest built here, and ``calls.jsonl`` is
        renamed to ``calls.source.jsonl`` so this run's wire log describes this run's one
        call. ``accounting`` walks ``calls.jsonl`` alone, so the arm's spend is its gate
        calls and never the objections and rulings it reads.

        Nothing under ``source_dir`` is written. Its whole-directory hash goes into the
        manifest as ``source_sha256``, so a source that drifts cannot do so unnoticed.
        """
        directory = _claim_run_dir(root, item.item_id, suffix="-gate")
        source_hash = tree_sha256(source_dir)
        for entry in sorted(source_dir.iterdir()):
            if entry.name in _GATE_EXCLUDED:
                continue
            if entry.is_dir():
                shutil.copytree(entry, directory / entry.name)
            else:
                shutil.copy2(entry, directory / entry.name)
        if (source_dir / "calls.jsonl").is_file():
            shutil.copy2(source_dir / "calls.jsonl", directory / SOURCE_CALLS)
        # ``parent`` is only ever consulted for its truthiness — it selects the contest
        # renderer over the decision one — and a gated contest IS a contest record.
        writer = cls(directory, directory.name, condition=condition, parent=source_dir)
        source_manifest: dict[str, Any] = {}
        if (source_dir / "run.json").is_file():
            try:
                source_manifest = _read_json(source_dir / "run.json")
            except ValueError:
                source_manifest = {}
        writer._manifest = {
            "run_id": writer.run_id, "kind": "gate", "condition": condition,
            "item_id": item.item_id, "row_id": item.row_id, "subset": item.subset,
            # Carried from the source so the gated record still names the DECISION the
            # objection contests; a reader who followed `parent_run_id` would otherwise
            # land nowhere.
            "parent_run_id": source_manifest.get("parent_run_id"),
            "parent_sha256": source_manifest.get("parent_sha256"),
            "parent_copied": source_manifest.get("parent_copied"),
            "source_contest_dir": str(source_dir),
            "source_sha256": source_hash,
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

    def record_recourse_turn(self, own: Transcript) -> None:
        """The contestability debate round's OWN turns, and never `transcript.json`.

        ``own`` is the recourse side of ``Transcript.split_at`` — the round-4 turns
        alone, not the parent debate they continue. It is written under its own name for
        a structural reason: a contest directory that held a `transcript.json` would be
        loaded by ``load_run_record`` as a DECISION whose debate is two turns long, and
        the copied `parent/` decision beside it is the record that actually holds the
        debate. Full ``Turn``s, thinking included, exactly as `record_turn` writes a
        decision's — `transcript_full.md` is where the private half is published and
        `transcript.md` prints the arguments only.
        """
        _write_json(self.dir / "recourse_transcript.json", own.to_dict())
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

    def record_admission(self, admission: Admission) -> None:
        """The M4 gate's finding, beside the ruling it gates and never over it.

        No ``_render()``. The published documents are the record the PARTIES saw — the
        objection, the ruling — and the gate is an analysis applied to that record
        afterwards by a model none of them met. Writing it into ``transcript.md`` would
        put a post-hoc annotation into a document this project's whole claim is that a
        reader can check against what actually happened.
        """
        _write_json(self.dir / "admission.json", admission.to_dict())
        self.manifest_update(gate_admitted=admission.admitted,
                             gate_model=admission.model)

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


def load_recourse_transcript(directory: Path) -> Transcript | None:
    """A contest's own round-4 turns, or ``None`` where no round was heard.

    ``None`` rather than an empty transcript, on the rule every conditional artifact in
    this harness follows: "judge-only recourse" and "a contest round that produced no
    turns" are different facts and the renderers, the index and the analysis all have to
    be able to tell them apart.
    """
    path = directory / "recourse_transcript.json"
    if not path.is_file():
        return None
    return Transcript([Turn(**_turn_kwargs(t)) for t in _read_json(path)["turns"]])


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

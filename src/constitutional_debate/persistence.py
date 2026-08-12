"""Streaming run records.

Artifacts are written *as they are produced*, not dumped at the end: if round 3
throws, rounds 1 and 2 are already on disk. Losing a paid generation to a later
failure would violate the project's own rule that every model output is saved.

The run directory holds the inputs (``config.json``, ``task.json``,
``seating.json``, ``constitution.md``), the wire log (``calls.jsonl``), and the
derived artifacts (``transcript.json``, ``transcript.md``, ``verdict.json``).

``transcript.md`` is the published document: the question, the arguments, the
debaters' ``Thinking``, and the decision with the grounds the judge gave for it.
Everything a reader needs in order to see what determined the outcome is in that
one file, which is what the project means by transparent.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import shutil
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .artifacts import (
    recourse_transcript_document,
    render_decision_record,
    render_recourse_record,
    transcript_document,
)
from .config import ClientConfig, DebateConfig
from .types import (
    Challenge,
    Context,
    Ruling,
    Seating,
    Speaker,
    Task,
    Transcript,
    Turn,
    Verdict,
)

def utc_now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _run_id_stamp() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


def _git(*args: str) -> str | None:
    try:
        result = subprocess.run(
            ["git", *args], capture_output=True, text=True, timeout=10, check=False
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return result.stdout if result.returncode == 0 else None


def git_provenance() -> dict[str, Any]:
    """Which commit produced this run, and whether the tree was clean.

    The two questions a reader of the record actually asks. A full ``git diff``
    would answer a third — what exactly was uncommitted — at the cost of making
    ``run.json`` something nobody can open, which is the wrong trade in a record
    whose point is that a person can read it.
    """
    sha = _git("rev-parse", "HEAD")
    status = _git("status", "--porcelain")
    dirty = bool(status and status.strip())
    provenance: dict[str, Any] = {
        "git_sha": sha.strip() if sha else None,
        "git_dirty": dirty,
    }
    if dirty:
        provenance["git_untracked"] = [
            line[3:] for line in status.splitlines() if line.startswith("??")
        ]
    return provenance


def _write_atomic(path: Path, text: str) -> None:
    """Write via a temp file and rename.

    ``transcript.json`` is rewritten in full after every turn. A plain write
    truncates first, so a crash mid-write would destroy the turns already
    committed — exactly the loss the streaming design exists to prevent.
    """
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def _write_json(path: Path, payload: Any) -> None:
    _write_atomic(path, json.dumps(payload, indent=2, ensure_ascii=False) + "\n")


def _claim_run_dir(outputs_root: Path, base: str) -> tuple[Path, str]:
    """Create and exclusively claim a run directory named after ``base``.

    Two runs of the same task can start within the same second — e.g. a
    word-limit sweep launched in parallel. ``mkdir`` is the exclusive claim, so
    a collision appends a suffix rather than silently overwriting a record.
    """
    (outputs_root / "runs").mkdir(parents=True, exist_ok=True)
    for suffix in ("", *(f"-{n}" for n in range(1, 100))):
        run_id = base + suffix
        run_dir = outputs_root / "runs" / run_id
        try:
            run_dir.mkdir()
        except FileExistsError:
            continue
        return run_dir, run_id
    raise RuntimeError(f"could not claim a run directory for {base}")


def tree_sha256(root: Path) -> str:
    """A hash over a directory's contents: every relative path and its bytes.

    Recorded when a recourse copies the run it challenges, so the copy can be
    shown to be the one that was made rather than one edited since. It proves
    exactly that and nothing more — it says nothing about some other directory
    elsewhere on disk. The load-bearing check is that the copy still verifies as
    a run in its own right.
    """
    digest = hashlib.sha256()
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        digest.update(str(path.relative_to(root)).encode("utf-8"))
        digest.update(b"\0")
        digest.update(hashlib.sha256(path.read_bytes()).digest())
    return digest.hexdigest()


@dataclass(frozen=True)
class RunRecord:
    """A completed run loaded back off disk, for a recourse to build on."""

    dir: Path
    run_id: str
    manifest: dict[str, Any]
    task: Task
    context: Context | None
    seating: Seating
    config: DebateConfig
    profile_key: str
    transcript: Transcript
    verdict: Verdict

    @property
    def chain(self) -> list[str]:
        """Every run this one is built on, oldest first, including itself."""
        return [*self.manifest.get("parent_chain", []), self.run_id]


def load_run_record(run_dir: Path) -> RunRecord:
    """Load a completed run so its decision can be challenged.

    Deliberately *not* shared with ``scripts/verify_run.py``, which reads the
    same files as plain dicts. A loader used by both the thing that writes a
    record and the thing that checks it would hide its own bugs: a field this
    one silently defaulted would be silently defaulted on the way back in too.
    The duplication is the point.
    """
    manifest = _read_json(run_dir / "run.json")
    if manifest.get("status") != "completed":
        raise ValueError(
            f"only a completed run can be challenged; {run_dir} has status "
            f"{manifest.get('status')!r}"
        )
    verdict_path = run_dir / "verdict.json"
    if not verdict_path.is_file():
        raise ValueError(f"{run_dir} records no verdict, so there is nothing to contest")

    task = Task.from_dict(_read_json(run_dir / "task.json"))
    config = DebateConfig(**_read_json(run_dir / "config.json"))
    seating_data = _read_json(run_dir / "seating.json")
    seating = Seating(
        alice_answer=seating_data["alice_answer"],
        bob_answer=seating_data["bob_answer"],
        choice_order=tuple(seating_data["choice_order"]),
        seed_material=seating_data["seed_material"],
    )
    constitution = run_dir / "constitution.md"
    context = (
        Context(
            kind="constitution",
            text=constitution.read_text(encoding="utf-8").strip(),
            source=manifest.get("constitution_source"),
        )
        if constitution.is_file()
        else None
    )

    transcript = Transcript()
    for turn in _read_json(run_dir / "transcript.json")["turns"]:
        transcript.add(
            Turn(
                round=turn["round"],
                speaker=Speaker(turn["speaker"]),
                answer_index=turn["answer_index"],
                thinking=turn["thinking"],
                argument=turn["argument"],
                word_count=turn["word_count"],
                parse_mode=turn["parse_mode"],
                repair_attempts=turn["repair_attempts"],
                finish_reason=turn.get("finish_reason"),
                has_native_reasoning=turn.get("has_native_reasoning", False),
                call_id=turn["call_id"],
                raw=turn.get("raw", ""),
            )
        )

    verdict_data = _read_json(verdict_path)
    verdict = Verdict(
        choice=verdict_data["choice"],
        answer_index=verdict_data["answer_index"],
        parse_mode=verdict_data["parse_mode"],
        raw=verdict_data["raw"],
        call_id=verdict_data["call_id"],
        finish_reason=verdict_data.get("finish_reason"),
        correct=verdict_data.get("correct"),
        repair_attempts=verdict_data.get("repair_attempts", 0),
        reasoning=verdict_data.get("reasoning", ""),
    )
    return RunRecord(
        dir=run_dir,
        run_id=manifest["run_id"],
        manifest=manifest,
        task=task,
        context=context,
        seating=seating,
        config=config,
        profile_key=manifest["profile"],
        transcript=transcript,
        verdict=verdict,
    )


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


class RunWriter:
    """Owns one run directory. Not reusable across runs.

    A recourse does not weaken that: it creates a *second* writer for a second
    directory, and only ever reads and copies the directory it challenges.
    """

    def __init__(
        self,
        dir: Path,
        run_id: str,
        manifest: dict[str, Any],
        task: Task,
        seating: Seating,
        config: DebateConfig,
        parent: RunRecord | None = None,
    ) -> None:
        self.dir = dir
        self.run_id = run_id
        self._manifest = manifest
        # Held because the transcript artifacts state what the debate is about,
        # and a Transcript deliberately knows neither the question nor who
        # defends which answer. The config is held for judge_cot, which is what
        # distinguishes a judge with nothing to say from one told to say nothing.
        self._task = task
        self._seating = seating
        self._config = config
        # Set for a recourse only, and what every recourse-shaped decision in
        # this class keys off. The parent supplies the decision under challenge,
        # the round boundary, and its own judge_cot — which is not necessarily
        # this run's.
        self._parent = parent
        self._challenge: Challenge | None = None
        self._lock = asyncio.Lock()

    @classmethod
    def create(
        cls,
        *,
        task: Task,
        context: Context | None,
        config: DebateConfig,
        client_config: ClientConfig,
        seating: Seating,
        profile_key: str,
        outputs_root: Path = Path("outputs"),
        status: str = "running",
    ) -> "RunWriter":
        run_dir, run_id = _claim_run_dir(outputs_root, f"{_run_id_stamp()}-{task.task_id}")

        _write_json(run_dir / "config.json", config.to_dict())
        _write_json(run_dir / "task.json", task.to_dict())
        _write_json(run_dir / "seating.json", seating.to_dict())
        if context is not None:
            (run_dir / "constitution.md").write_text(context.text, encoding="utf-8")

        writer = cls(
            dir=run_dir,
            run_id=run_id,
            task=task,
            seating=seating,
            config=config,
            manifest={
                "run_id": run_id,
                "status": status,
                "started_utc": utc_now(),
                "ended_utc": None,
                "error": None,
                "profile": profile_key,
                "task_id": task.task_id,
                "task_source": task.source,
                "constitution_source": context.source if context else None,
                "constitution_sha256": context.sha256() if context else None,
                "client_config": client_config.to_dict(),
                "totals": {},
                # Read as ``manifest.get("kind", "debate")``, so every run
                # recorded before recourse existed reads as what it is.
                "kind": "debate",
                **git_provenance(),
            },
        )
        # Flushed before any API call, so a crashed run is distinguishable from
        # a completed one by inspection alone.
        writer._flush_manifest()
        return writer

    @classmethod
    def create_recourse(
        cls,
        *,
        parent: RunRecord,
        config: DebateConfig,
        client_config: ClientConfig,
        outputs_root: Path = Path("outputs"),
        status: str = "running",
        copy_parent: bool = True,
    ) -> "RunWriter":
        """Claim a directory for a recourse against ``parent``.

        The parent run directory is copied in wholesale, before any API call, so
        the recourse record is self-contained: one audit over this directory
        verifies the original debate and the contest of it together, and the
        parent cannot drift or disappear underneath the record that quotes it.

        The task, seating, config and constitution are copied out of the parent
        too, so a recourse directory is shaped like a run directory and every
        builder can read it without a special case. They are restated data and
        can therefore disagree; the audit checks them against ``parent/``.
        """
        if parent.manifest.get("status") != "completed":
            raise ValueError(
                f"only a completed run can be challenged; {parent.run_id} has "
                f"status {parent.manifest.get('status')!r}"
            )
        if config.n_rounds != parent.config.n_rounds:
            # Recourse rounds are numbered as a continuation of the parent's, so
            # the boundary between the two is n_rounds. If the two disagreed,
            # nothing on disk would say where the original debate ended.
            #
            # This is also where chained recourse would have to be reckoned
            # with. ``load_run_record`` refuses a run with no verdict, so a
            # ruling cannot currently be contested — but if that were lifted,
            # this boundary would need revisiting rather than reusing:
            # ``parent.config.n_rounds`` would be the *grandparent's* round
            # count, and the numbering would collide with the parent's own
            # recourse rounds.
            raise ValueError(
                f"a recourse inherits the parent's n_rounds; got "
                f"{config.n_rounds} against the parent's {parent.config.n_rounds}"
            )

        run_dir, run_id = _claim_run_dir(
            outputs_root, f"{_run_id_stamp()}-{parent.task.task_id}-recourse"
        )

        _write_json(run_dir / "config.json", config.to_dict())
        _write_json(run_dir / "task.json", parent.task.to_dict())
        _write_json(run_dir / "seating.json", parent.seating.to_dict())
        if parent.context is not None:
            (run_dir / "constitution.md").write_text(
                parent.context.text, encoding="utf-8"
            )

        parent_sha256 = None
        if copy_parent:
            shutil.copytree(parent.dir, run_dir / "parent")
            parent_sha256 = tree_sha256(run_dir / "parent")

        writer = cls(
            dir=run_dir,
            run_id=run_id,
            task=parent.task,
            seating=parent.seating,
            config=config,
            parent=parent,
            manifest={
                "run_id": run_id,
                "status": status,
                "started_utc": utc_now(),
                "ended_utc": None,
                "error": None,
                "profile": parent.profile_key,
                "task_id": parent.task.task_id,
                "task_source": parent.task.source,
                "constitution_source": parent.manifest.get("constitution_source"),
                "constitution_sha256": parent.manifest.get("constitution_sha256"),
                "client_config": client_config.to_dict(),
                "totals": {},
                "kind": "recourse",
                "parent_run_id": parent.run_id,
                "parent_status": parent.manifest.get("status"),
                "parent_rounds": parent.config.n_rounds,
                "parent_sha256": parent_sha256,
                # The whole ancestry, so the depth of a chained recourse is
                # visible without walking every parent/ directory to find it.
                "parent_chain": parent.chain,
                # Named, not left to be inferred from recourse_rounds. The audit
                # checks the name against the count.
                "recourse_protocol": config.recourse_protocol,
                "challenge_origin": None,
                "challenge_source": None,
                "challenge_arm": None,
                "challenge_visibility": None,
                "challenge_sha256": None,
                **git_provenance(),
            },
        )
        writer._flush_manifest()
        return writer

    def _flush_manifest(self) -> None:
        _write_json(self.dir / "run.json", self._manifest)

    async def record_call(self, record: dict[str, Any]) -> None:
        """Append one HTTP attempt to ``calls.jsonl``.

        The lock matters: during simultaneous rounds two coroutines append here,
        and records carry full request and response bodies — well past any size
        at which a single write is atomic. Interleaved writes would corrupt the
        one artifact the audit reads.
        """
        line = json.dumps(record, ensure_ascii=False) + "\n"
        path = self.dir / "calls.jsonl"

        def append() -> None:
            with path.open("a", encoding="utf-8") as handle:
                handle.write(line)
                handle.flush()

        # to_thread keeps a multi-kilobyte write off the event loop; the lock
        # then genuinely serialises appends, since the await inside the critical
        # section is a real suspension point.
        async with self._lock:
            await asyncio.to_thread(append)

    def record_turn(self, transcript: Transcript) -> None:
        """Rewrite the transcript artifacts after each completed turn."""
        if self._parent is None:
            self._write_transcripts(transcript, verdict=None)
        else:
            self._write_recourse_transcripts(transcript, ruling=None)

    def record_verdict(self, verdict: Verdict, transcript: Transcript) -> None:
        """Record the decision, and restate the full record with it.

        The transcript is a parameter rather than state carried over from
        ``record_turn`` so that what lands on disk depends on the arguments
        alone, not on the order the writer happened to be called in.
        """
        _write_json(self.dir / "verdict.json", verdict.to_dict())
        self._write_transcripts(transcript, verdict=verdict)

    def record_challenge(self, challenge: Challenge, transcript: Transcript) -> None:
        """Record what is being contested, before any recourse round runs.

        ``challenge.md`` is the document verbatim: it is what the published
        record shows a reader was put to the judge, and the audit checks that
        the requests actually carried it. Its provenance — supplied or
        generated, under which arm, shown how much of the record — goes in
        ``challenge.json`` and the manifest, never into the file the prompts
        quote.
        """
        self._challenge = challenge
        _write_atomic(self.dir / "challenge.md", challenge.text + "\n")
        _write_json(self.dir / "challenge.json", challenge.to_dict())
        self._manifest.update(
            challenge_origin=challenge.origin,
            challenge_source=challenge.source,
            challenge_arm=challenge.arm,
            challenge_visibility=challenge.visibility,
            challenge_sha256=challenge.sha256(),
        )
        self._flush_manifest()
        self._write_recourse_transcripts(transcript, ruling=None)

    def record_ruling(self, ruling: Ruling, transcript: Transcript) -> None:
        """Record the ruling on the challenge, and restate the record with it."""
        _write_json(self.dir / "ruling.json", ruling.to_dict())
        self._write_recourse_transcripts(transcript, ruling=ruling)

    def _write_recourse_transcripts(
        self, composed: Transcript, *, ruling: Ruling | None
    ) -> None:
        """Write a recourse's artifacts from the composed transcript.

        ``composed`` carries the parent's turns as well as this run's, because
        that is what the prompts were built from. Only this run's turns are
        written to ``transcript.json``: the parent's already exist, once, in
        ``parent/transcript.json``, joined to the wire log that produced them.
        Filtering here rather than threading two transcript objects through the
        orchestrator is what makes the two views structurally unable to drift.
        """
        parent = self._parent
        if parent is None:  # pragma: no cover - only reachable in recourse mode
            raise ValueError("a recourse artifact needs the run it contests")
        _, own = composed.split_at(parent.config.n_rounds)
        _write_json(
            self.dir / "transcript.json",
            recourse_transcript_document(
                self._task,
                self._seating,
                own,
                parent_run_id=parent.run_id,
                parent_rounds=parent.config.n_rounds,
            ),
        )
        if self._challenge is None:
            # Nothing to render a challenge section from yet. Reachable only if
            # a turn were somehow committed before the challenge was recorded,
            # which run_recourse does not do.
            return
        _write_atomic(
            self.dir / "transcript.md",
            render_recourse_record(
                self._task,
                self._seating,
                composed,
                parent_rounds=parent.config.n_rounds,
                parent_verdict=parent.verdict,
                challenge=self._challenge,
                ruling=ruling,
                judge_cot=self._config.judge_cot,
                parent_judge_cot=parent.config.judge_cot,
            ),
        )

    def _write_transcripts(
        self, transcript: Transcript, *, verdict: Verdict | None
    ) -> None:
        _write_json(
            self.dir / "transcript.json",
            transcript_document(self._task, self._seating, transcript),
        )
        # A re-render rather than a copy of what the judge saw: the judge read a
        # tagged plaintext transcript, and this defends markdown structure
        # instead. The request bodies are in calls.jsonl either way.
        _write_atomic(
            self.dir / "transcript.md",
            render_decision_record(
                self._task,
                self._seating,
                transcript,
                verdict,
                judge_cot=self._config.judge_cot,
            ),
        )

    def finish(
        self,
        *,
        status: str,
        error: str | None = None,
        totals: dict[str, Any] | None = None,
    ) -> None:
        self._manifest.update(
            status=status,
            ended_utc=utc_now(),
            error=error,
            totals=totals or {},
        )
        self._flush_manifest()

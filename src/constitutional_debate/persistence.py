"""Streaming run records.

Artifacts are written *as they are produced*, not dumped at the end: if round 3
throws, rounds 1 and 2 are already on disk. Losing a paid generation to a later
failure would violate the project's own rule that every model output is saved.

The run directory is split into audit inputs (``config.json``, ``task.json``,
``seating.json``, ``constitution.md``), the wire log (``calls.jsonl``), and
derived artifacts (``transcript.json``, ``transcript.public.md``,
``transcript.full.md``, ``verdict.json``). ``scripts/verify_run.py`` re-derives
every request from the inputs and byte-compares it against the wire log.

Only ``transcript.public.md`` is publishable as-is: ``transcript.full.md`` and
``transcript.json`` both carry the debaters' private ``Thinking`` sections.
"""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .artifacts import (
    render_full_markdown,
    render_public_markdown,
    transcript_document,
)
from .config import ClientConfig, DebateConfig
from .types import Context, Seating, Task, Transcript, Verdict

MAX_EMBEDDED_DIFF_BYTES = 200_000


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
    """Commit sha plus, when the tree is dirty, the diff that explains it.

    A bare "dirty" flag would make the sha unverifiable — you would know the
    recorded commit was not what ran, without knowing what did. Embedding the
    diff keeps the record complete without blocking work on an uncommitted tree,
    which a research repo is in essentially all the time.
    """
    sha = _git("rev-parse", "HEAD")
    status = _git("status", "--porcelain")
    dirty = bool(status and status.strip())
    provenance: dict[str, Any] = {
        "git_sha": sha.strip() if sha else None,
        "git_dirty": dirty,
    }
    if dirty:
        diff = _git("diff", "HEAD") or ""
        truncated = len(diff.encode("utf-8")) > MAX_EMBEDDED_DIFF_BYTES
        provenance["git_diff"] = (
            diff.encode("utf-8")[:MAX_EMBEDDED_DIFF_BYTES].decode("utf-8", "ignore")
            if truncated
            else diff
        )
        provenance["git_diff_truncated"] = truncated
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


class RunWriter:
    """Owns one run directory. Not reusable across runs."""

    def __init__(
        self,
        dir: Path,
        run_id: str,
        manifest: dict[str, Any],
        task: Task,
        seating: Seating,
        config: DebateConfig,
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
        # Two runs of the same task can start within the same second — e.g. a
        # word-limit sweep launched in parallel. Claim the directory
        # exclusively so a collision can never silently overwrite a record.
        base = f"{_run_id_stamp()}-{task.task_id}"
        (outputs_root / "runs").mkdir(parents=True, exist_ok=True)
        for suffix in ("", *(f"-{n}" for n in range(1, 100))):
            run_id = base + suffix
            run_dir = outputs_root / "runs" / run_id
            try:
                run_dir.mkdir()
                break
            except FileExistsError:
                continue
        else:
            raise RuntimeError(f"could not claim a run directory for {base}")

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
                **git_provenance(),
            },
        )
        # Flushed before any API call, so a crashed run is distinguishable from
        # a completed one by inspection alone.
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
        self._write_transcripts(transcript, verdict=None)

    def record_verdict(self, verdict: Verdict, transcript: Transcript) -> None:
        """Record the decision, and restate the full record with it.

        The transcript is a parameter rather than state carried over from
        ``record_turn`` so that what lands on disk depends on the arguments
        alone, not on the order the writer happened to be called in.
        """
        _write_json(self.dir / "verdict.json", verdict.to_dict())
        self._write_transcripts(transcript, verdict=verdict)

    def _write_transcripts(
        self, transcript: Transcript, *, verdict: Verdict | None
    ) -> None:
        _write_json(
            self.dir / "transcript.json",
            transcript_document(self._task, self._seating, transcript),
        )
        # Re-renders, not byte-copies of what the judge saw: the byte-exact
        # artifact is the judge request body in calls.jsonl.
        _write_atomic(
            self.dir / "transcript.public.md", render_public_markdown(transcript)
        )
        _write_atomic(
            self.dir / "transcript.full.md",
            render_full_markdown(
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

"""Run helpers that produce a *complete* run directory, wire log included.

Every helper here wires ``client.sink`` to the writer that owns the run, so a test
looking at the directory afterwards sees what a real run leaves behind — including
``calls.jsonl``, which the full transcript is rendered from. A test that builds a
run by hand and forgets the sink silently exercises the fallback path instead.

These live in their own module rather than in ``conftest`` because ``conftest``
imports ``helpers``, so ``helpers`` cannot import back into it.
"""

from __future__ import annotations

from conftest import FakeClient
from helpers import make_config, make_item, make_sides

from exp2.arms import DECIDERS
from exp2.config import ClientConfig
from exp2.persistence import RunWriter, load_run_record
from exp2.recourse import run_recourse


def client_config(**kw) -> ClientConfig:
    base = dict(base_url="https://x/api", max_concurrency=4, max_attempts=3,
                backoff_base_s=1.0, backoff_cap_s=5.0, connect_timeout_s=5.0,
                read_timeout_s=30.0, run_timeout_s=300.0)
    base.update(kw)
    return ClientConfig(**base)


def _sink_into(client: FakeClient, writer: RunWriter) -> FakeClient:
    if client.sink is None:
        client.sink = writer.record_call
    return client


async def recorded(tmp_path, condition, *, client=None, item=None, flaw=None):
    item = item or make_item()
    writer = RunWriter.create(
        root=tmp_path, item=item, sides=make_sides(), config=make_config(),
        client_config=client_config(), condition=condition, flaw=flaw,
    )
    client = _sink_into(client or FakeClient(), writer)
    result = await DECIDERS[condition](
        item, make_config(), make_sides(), client, writer=writer
    )
    writer.finish("completed")
    return writer, result


async def decided(tmp_path, condition, *, client=None):
    """A completed decision on disk, ready to be contested."""
    item, config, sides = make_item(), make_config(), make_sides()
    writer = RunWriter.create(root=tmp_path / "d", item=item, sides=sides, config=config,
                              client_config=client_config(), condition=condition)
    client = _sink_into(client or FakeClient(), writer)
    await DECIDERS[condition](item, config, sides, client, writer=writer)
    writer.finish("completed")
    return load_run_record(writer.dir)


async def contest(tmp_path, condition, *, client=None, rule=True, config=None):
    record = await decided(tmp_path, condition)
    writer = RunWriter.create_recourse(
        root=tmp_path / "c", parent_dir=record.directory, item=record.item,
        sides=record.sides, config=record.config, client_config=client_config(),
        condition=condition)
    client = _sink_into(client or FakeClient(), writer)
    outcome = await run_recourse(record, config or make_config(), client, rule=rule,
                                 writer=writer)
    writer.finish("completed")
    return outcome, client, writer, record

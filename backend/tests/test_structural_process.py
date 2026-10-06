import asyncio
import sys

import pytest

from windops_backend import structural_process


async def test_numerical_deadline_kills_and_reaps_the_owned_child(monkeypatch):
    original = asyncio.create_subprocess_exec
    children = []

    async def launch_sleeping_child(*_args, **kwargs):
        child = await original(
            sys.executable,
            "-c",
            "import sys,time; sys.stdin.buffer.read(); time.sleep(30)",
            **kwargs,
        )
        children.append(child)
        return child

    monkeypatch.setattr(asyncio, "create_subprocess_exec", launch_sleeping_child)
    monkeypatch.setattr(structural_process, "COMPUTATION_TIMEOUT_SECONDS", 0.05)
    with pytest.raises(TimeoutError):
        await structural_process.compute_waveform(b"{}", {}, {})
    assert len(children) == 1
    assert children[0].returncode is not None
    assert children[0].returncode != 0


async def test_worker_cancellation_kills_the_owned_numerical_process(monkeypatch):
    original = asyncio.create_subprocess_exec
    children = []
    started = asyncio.Event()

    async def launch_sleeping_child(*_args, **kwargs):
        child = await original(
            sys.executable,
            "-c",
            "import sys,time; sys.stdin.buffer.read(); time.sleep(30)",
            **kwargs,
        )
        children.append(child)
        started.set()
        return child

    monkeypatch.setattr(asyncio, "create_subprocess_exec", launch_sleeping_child)
    task = asyncio.create_task(structural_process.compute_waveform(b"{}", {}, {}))
    await asyncio.wait_for(started.wait(), 5)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert children[0].returncode is not None
    assert children[0].returncode != 0

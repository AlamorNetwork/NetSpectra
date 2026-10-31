"""Real independent endpoint processes, including cancellation/startup cleanup."""

import asyncio
import hashlib
import os

import pytest
from pprl_core import endpoints
from pprl_core.workload import seeded_payload


@pytest.mark.parametrize("protocol", ["tcp", "udp"])
def test_two_independent_process_endpoints(protocol: str) -> None:
    payload = seeded_payload(42, 0)
    result = asyncio.run(endpoints.probe_process_pair(protocol, payload, 10))
    assert result["scope"] == "ipv4_loopback_only"
    assert result["topology"] == "two_processes"
    assert len({os.getpid(), result["client_pid"], result["server_pid"]}) == 3
    assert result["results"][0]["bytes_echoed"] == len(payload)
    assert result["results"][0]["payload_sha256"] == hashlib.sha256(payload).hexdigest()


@pytest.mark.parametrize("cancel", [False, True])
def test_child_is_reaped_on_timeout_or_cancel(
    monkeypatch: pytest.MonkeyPatch,
    cancel: bool,
) -> None:
    processes = []
    original_spawn = endpoints._spawn

    async def exercise():
        started = asyncio.Event()

        async def stalled_spawn(*args, **kwargs):
            # Child emits no readiness; parent must kill it under its own deadline.
            process = await original_spawn(
                args[0],
                "-c",
                "import time; time.sleep(30)",
                **kwargs,
            )
            processes.append(process)
            started.set()
            return process

        monkeypatch.setattr(endpoints, "_spawn", stalled_spawn)
        task = asyncio.create_task(endpoints.probe_process_pair("tcp", b"test", 0.3))
        if cancel:
            async with asyncio.timeout(5):
                await started.wait()
            task.cancel()
        with pytest.raises(asyncio.CancelledError if cancel else TimeoutError):
            await task
        assert processes
        assert all(process.returncode is not None for process in processes)

    asyncio.run(exercise())


def test_malformed_ready_cleans_up_child(monkeypatch: pytest.MonkeyPatch) -> None:
    processes = []
    original_spawn = endpoints._spawn

    async def malformed_spawn(*args, **kwargs):
        process = await original_spawn(
            args[0], "-c", "print('{}',flush=True)", **kwargs
        )
        processes.append(process)
        return process

    monkeypatch.setattr(endpoints, "_spawn", malformed_spawn)
    with pytest.raises(endpoints.EndpointError, match="endpoint_protocol_error"):
        asyncio.run(endpoints.probe_process_pair("udp", b"test", 5))
    assert all(process.returncode is not None for process in processes)

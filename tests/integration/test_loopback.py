"""Actual local sockets; never contact external endpoints."""

import asyncio
import socket

import pytest
from pprl_core import loopback


def test_tcp_and_udp_echo_and_cleanup(monkeypatch: pytest.MonkeyPatch) -> None:
    sockets = []
    original = socket.socket

    def tracked_socket(*args, **kwargs):
        connection = original(*args, **kwargs)
        sockets.append(connection)
        return connection

    async def exercise():
        monkeypatch.setattr(loopback, "Socket", tracked_socket)
        return await loopback.probe_loopback()

    summary = asyncio.run(exercise())
    assert summary["scope"] == "ipv4_loopback_only"
    assert summary["results"] == [
        {
            "protocol": protocol,
            "bytes_echoed": len(loopback.PAYLOAD),
            "status": "succeeded",
        }
        for protocol in ("tcp", "udp")
    ]
    assert sockets
    assert all(connection.fileno() == -1 for connection in sockets)


def test_tcp_timeout_closes_listener_and_client(monkeypatch: pytest.MonkeyPatch):
    sockets = []
    original = socket.socket

    def tracked_socket(*args, **kwargs):
        connection = original(*args, **kwargs)
        sockets.append(connection)
        return connection

    async def stalled_echo(listener):
        await asyncio.Event().wait()

    async def exercise():
        monkeypatch.setattr(loopback, "Socket", tracked_socket)
        monkeypatch.setattr(loopback, "_tcp_echo", stalled_echo)
        with pytest.raises(TimeoutError):
            await loopback.probe_loopback(timeout=0.1)
        assert not [
            task for task in asyncio.all_tasks() if task is not asyncio.current_task()
        ]

    asyncio.run(exercise())
    assert sockets
    assert all(connection.fileno() == -1 for connection in sockets)


def test_udp_cancellation_closes_sockets(monkeypatch: pytest.MonkeyPatch):
    sockets = []
    original = socket.socket

    def tracked_socket(*args, **kwargs):
        connection = original(*args, **kwargs)
        sockets.append(connection)
        return connection

    async def exercise():
        ready = asyncio.Event()

        async def stalled_echo(listener):
            ready.set()
            await asyncio.Event().wait()

        monkeypatch.setattr(loopback, "Socket", tracked_socket)
        monkeypatch.setattr(loopback, "_udp_echo", stalled_echo)
        task = asyncio.create_task(loopback.probe_loopback())
        async with asyncio.timeout(3):
            await ready.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert not [
            task for task in asyncio.all_tasks() if task is not asyncio.current_task()
        ]

    asyncio.run(exercise())
    assert sockets
    assert all(connection.fileno() == -1 for connection in sockets)

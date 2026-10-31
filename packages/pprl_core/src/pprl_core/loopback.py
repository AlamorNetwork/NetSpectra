"""Bounded TCP/UDP echo smoke probes using only IPv4 loopback."""

import asyncio
import contextlib
import json
import math
import platform
import socket
import sys
from socket import socket as Socket

HOST = "127.0.0.1"
PAYLOAD = b"pprl-synthetic-loopback-v1"


async def _receive_exact(connection: socket.socket, size: int) -> bytes:
    received = bytearray()
    loop = asyncio.get_running_loop()
    while len(received) < size:
        chunk = await loop.sock_recv(connection, size - len(received))
        if not chunk:
            raise ConnectionError("TCP echo ended before the complete payload")
        received.extend(chunk)
    return bytes(received)


async def _tcp_echo(listener: socket.socket) -> None:
    loop = asyncio.get_running_loop()
    connection, _ = await loop.sock_accept(listener)
    with connection:
        connection.setblocking(False)
        data = await _receive_exact(connection, len(PAYLOAD))
        await loop.sock_sendall(connection, data)


async def _tcp_probe() -> dict:
    loop = asyncio.get_running_loop()
    with Socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.setblocking(False)
        listener.bind((HOST, 0))
        listener.listen(1)
        server = asyncio.create_task(_tcp_echo(listener))
        try:
            with Socket(socket.AF_INET, socket.SOCK_STREAM) as client:
                client.setblocking(False)
                client.bind((HOST, 0))
                await loop.sock_connect(client, listener.getsockname())
                await loop.sock_sendall(client, PAYLOAD)
                echoed = await _receive_exact(client, len(PAYLOAD))
                if echoed != PAYLOAD:
                    raise ValueError("TCP echo payload mismatch")
            await server
        finally:
            server.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await server
    return {"protocol": "tcp", "bytes_echoed": len(echoed), "status": "succeeded"}


async def _udp_echo(listener: socket.socket) -> None:
    loop = asyncio.get_running_loop()
    data, peer = await loop.sock_recvfrom(listener, len(PAYLOAD) + 1)
    await loop.sock_sendto(listener, data, peer)


async def _udp_probe() -> dict:
    loop = asyncio.get_running_loop()
    with (
        Socket(socket.AF_INET, socket.SOCK_DGRAM) as listener,
        Socket(socket.AF_INET, socket.SOCK_DGRAM) as client,
    ):
        listener.setblocking(False)
        client.setblocking(False)
        listener.bind((HOST, 0))
        client.bind((HOST, 0))
        server = asyncio.create_task(_udp_echo(listener))
        try:
            await loop.sock_sendto(client, PAYLOAD, listener.getsockname())
            echoed, peer = await loop.sock_recvfrom(client, len(PAYLOAD) + 1)
            if peer != listener.getsockname() or echoed != PAYLOAD:
                raise ValueError("UDP echo peer or payload mismatch")
            await server
        finally:
            server.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await server
    return {"protocol": "udp", "bytes_echoed": len(echoed), "status": "succeeded"}


async def probe_loopback(
    timeout: float = 5.0, protocols: tuple[str, ...] = ("tcp", "udp")
) -> dict:
    """Echo a fixed synthetic payload over TCP and UDP under one deadline."""
    if isinstance(timeout, bool) or not math.isfinite(timeout) or not 0 < timeout <= 30:
        raise ValueError(
            "timeout must be finite, greater than 0 and at most 30 seconds"
        )
    if not protocols or len(set(protocols)) != len(protocols):
        raise ValueError("protocols must be nonempty and unique")
    if any(protocol not in {"tcp", "udp"} for protocol in protocols):
        raise ValueError("only tcp and udp loopback probes are supported")
    async with asyncio.timeout(timeout):
        probes = {"tcp": _tcp_probe, "udp": _udp_probe}
        results = [await probes[protocol]() for protocol in protocols]
    return {
        "scope": "ipv4_loopback_only",
        "platform": platform.system(),
        "python": platform.python_version(),
        "results": results,
    }


def main() -> int:
    """Print a synthetic smoke summary, not a versioned Experiment/Run record."""
    try:
        result = asyncio.run(probe_loopback())
    except KeyboardInterrupt:
        print(json.dumps({"status": "cancelled"}), file=sys.stderr)
        return 130
    except (OSError, TimeoutError, ValueError) as error:
        print(
            json.dumps({"status": "failed", "error_type": type(error).__name__}),
            file=sys.stderr,
        )
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Two single-use local subprocess endpoints; no external target is accepted."""

import argparse
import asyncio
import errno
import hashlib
import json
import math
import os
import socket
import struct
import sys
from pathlib import Path

HOST = "127.0.0.1"
MAX_PAYLOAD = 512
_spawn = asyncio.create_subprocess_exec


class EndpointError(Exception):
    """Safe classification of a child endpoint failure."""


def _exact(connection: socket.socket, size: int) -> bytes:
    data = bytearray()
    while len(data) < size:
        chunk = connection.recv(size - len(data))
        if not chunk:
            raise ConnectionError("incomplete frame")
        data.extend(chunk)
    return bytes(data)


def _result(payload: bytes, protocol: str, role: str) -> dict:
    return {
        "status": "succeeded",
        "protocol": protocol,
        "role": role,
        "pid": os.getpid(),
        "bytes_echoed": len(payload),
        "payload_sha256": hashlib.sha256(payload).hexdigest(),
    }


def _serve(protocol: str, timeout: float) -> dict:
    kind = socket.SOCK_STREAM if protocol == "tcp" else socket.SOCK_DGRAM
    with socket.socket(socket.AF_INET, kind) as listener:
        listener.settimeout(timeout)
        listener.bind((HOST, 0))
        if protocol == "tcp":
            listener.listen(1)
        print(
            json.dumps(
                {
                    "host": HOST,
                    "port": listener.getsockname()[1],
                    "pid": os.getpid(),
                    "protocol": protocol,
                }
            ),
            flush=True,
        )
        if protocol == "tcp":
            connection, peer = listener.accept()
            with connection:
                connection.settimeout(timeout)
                if peer[0] != HOST:
                    raise ValueError("unexpected peer")
                size = struct.unpack("!I", _exact(connection, 4))[0]
                if not 1 <= size <= MAX_PAYLOAD:
                    raise ValueError("invalid frame size")
                payload = _exact(connection, size)
                connection.sendall(struct.pack("!I", size) + payload)
        else:
            payload, peer = listener.recvfrom(MAX_PAYLOAD + 1)
            if peer[0] != HOST or not 1 <= len(payload) <= MAX_PAYLOAD:
                raise ValueError("invalid datagram")
            listener.sendto(payload, peer)
    return _result(payload, protocol, "server")


def _client(protocol: str, port: int, timeout: float) -> dict:
    raw = sys.stdin.buffer.read(4097)
    if len(raw) > 4096:
        raise ValueError("oversize input")
    payload = bytes.fromhex(json.loads(raw)["payload_hex"])
    if not 1 <= len(payload) <= MAX_PAYLOAD:
        raise ValueError("invalid payload")
    kind = socket.SOCK_STREAM if protocol == "tcp" else socket.SOCK_DGRAM
    with socket.socket(socket.AF_INET, kind) as connection:
        connection.settimeout(timeout)
        connection.bind((HOST, 0))
        if protocol == "tcp":
            connection.connect((HOST, port))
            connection.sendall(struct.pack("!I", len(payload)) + payload)
            size = struct.unpack("!I", _exact(connection, 4))[0]
            if size != len(payload):
                raise ValueError("echo length mismatch")
            echoed = _exact(connection, size)
        else:
            connection.sendto(payload, (HOST, port))
            echoed, peer = connection.recvfrom(MAX_PAYLOAD + 1)
            if peer != (HOST, port):
                raise ValueError("unexpected echo peer")
    if echoed != payload:
        raise ValueError("echo mismatch")
    return _result(payload, protocol, "client")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("role", choices=["server", "client"])
    parser.add_argument("--protocol", choices=["tcp", "udp"], required=True)
    parser.add_argument("--timeout", type=float, default=5)
    parser.add_argument("--port", type=int)
    args = parser.parse_args()
    if not math.isfinite(args.timeout) or not 0 < args.timeout <= 30:
        parser.error("timeout must be finite and within (0,30]")
    if args.role == "client" and (args.port is None or not 1 <= args.port <= 65535):
        parser.error("client requires a port within [1,65535]")
    try:
        result = (
            _serve(args.protocol, args.timeout)
            if args.role == "server"
            else _client(args.protocol, args.port, args.timeout)
        )
    except TimeoutError:
        print(json.dumps({"error": "timeout"}), file=sys.stderr)
        return 1
    except OSError as error:
        category = (
            "endpoint_transient_error"
            if error.errno
            in {
                errno.ECONNRESET,
                errno.ECONNREFUSED,
                errno.ECONNABORTED,
                errno.EPIPE,
                errno.ETIMEDOUT,
            }
            else "endpoint_io_error"
        )
        print(json.dumps({"error": category}), file=sys.stderr)
        return 1
    except (ValueError, KeyError, TypeError):
        print(json.dumps({"error": "payload_mismatch"}), file=sys.stderr)
        return 1
    print(json.dumps(result), flush=True)
    return 0


async def _stop(process: asyncio.subprocess.Process | None) -> None:
    if process is None:
        return
    if process.returncode is None:
        try:
            process.terminate()
        except ProcessLookupError:
            pass
    try:
        await asyncio.wait_for(process.communicate(), 1)
    except TimeoutError:
        if process.returncode is None:
            process.kill()
        await process.communicate()


async def _launch(*args, **kwargs) -> asyncio.subprocess.Process:
    # Retain and reap a child even if cancellation arrives during OS process creation.
    task = asyncio.create_task(_spawn(*args, **kwargs))
    try:
        return await asyncio.shield(task)
    except asyncio.CancelledError:
        process = await task
        await _stop(process)
        raise


def _decode(data: bytes) -> dict:
    if len(data) > 8192:
        raise EndpointError("endpoint_protocol_error")
    try:
        result = json.loads(data)
    except (ValueError, UnicodeError) as error:
        raise EndpointError("endpoint_protocol_error") from error
    if not isinstance(result, dict):
        raise EndpointError("endpoint_protocol_error")
    return result


def _check_child(process: asyncio.subprocess.Process, error: bytes) -> None:
    if process.returncode != 0:
        try:
            category = _decode(error).get("error")
        except EndpointError:
            category = None
        if category not in {
            "timeout",
            "endpoint_io_error",
            "endpoint_transient_error",
            "payload_mismatch",
        }:
            category = "endpoint_protocol_error"
        raise EndpointError(category)


async def probe_process_pair(protocol: str, payload: bytes, timeout: float) -> dict:
    """Create, verify and reap independent client/server processes per attempt."""
    if protocol not in {"tcp", "udp"} or not 1 <= len(payload) <= MAX_PAYLOAD:
        raise ValueError("invalid endpoint workload")
    if isinstance(timeout, bool) or not math.isfinite(timeout) or not 0 < timeout <= 30:
        raise ValueError("invalid endpoint timeout")
    server = client = None
    # Windows venv launchers can create an extra interpreter process. Launch the
    # base interpreter directly so Process.pid is the actual endpoint we can reap.
    executable = getattr(sys, "_base_executable", sys.executable)
    command = [executable, "-m", "pprl_core.endpoints"]
    child_env = dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parent.parent))
    try:
        async with asyncio.timeout(timeout):
            server = await _launch(
                *command,
                "server",
                "--protocol",
                protocol,
                "--timeout",
                str(timeout),
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=child_env,
            )
            ready = _decode(await server.stdout.readline())
            port = ready.get("port")
            if (
                ready.get("host") != HOST
                or ready.get("pid") != server.pid
                or ready.get("protocol") != protocol
                or type(port) is not int
                or not 1 <= port <= 65535
            ):
                raise EndpointError("endpoint_protocol_error")
            client = await _launch(
                *command,
                "client",
                "--protocol",
                protocol,
                "--port",
                str(port),
                "--timeout",
                str(timeout),
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=child_env,
            )
            client_out, client_err = await client.communicate(
                json.dumps({"payload_hex": payload.hex()}).encode()
            )
            _check_child(client, client_err)
            server_out, server_err = await server.communicate()
            _check_child(server, server_err)
            client_result, server_result = _decode(client_out), _decode(server_out)
            expected_hash = hashlib.sha256(payload).hexdigest()
            for result, role, pid in (
                (client_result, "client", client.pid),
                (server_result, "server", server.pid),
            ):
                if (
                    result.get("status") != "succeeded"
                    or result.get("role") != role
                    or result.get("pid") != pid
                    or result.get("protocol") != protocol
                    or result.get("bytes_echoed") != len(payload)
                    or result.get("payload_sha256") != expected_hash
                ):
                    raise EndpointError("payload_mismatch")
            return {
                "scope": "ipv4_loopback_only",
                "topology": "two_processes",
                "client_pid": client.pid,
                "server_pid": server.pid,
                "results": [
                    {
                        "protocol": protocol,
                        "bytes_echoed": len(payload),
                        "status": "succeeded",
                        "payload_sha256": expected_hash,
                    }
                ],
            }
    finally:
        try:
            await _stop(client)
        finally:
            await _stop(server)


if __name__ == "__main__":
    raise SystemExit(main())

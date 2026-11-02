"""Dependency-free bounded TCP/UDP echo worker and round-robin lab relay."""

import argparse
import hashlib
import hmac
import importlib.util
import ipaddress
import json
import os
import platform
import select
import shutil
import socket
import struct
import subprocess
import sys
import threading
import time
from pathlib import Path

MAX_FRAME = 4096


def exact(connection: socket.socket, size: int) -> bytes:
    data = bytearray()
    while len(data) < size:
        part = connection.recv(size - len(data))
        if not part:
            raise ValueError("incomplete_frame")
        data.extend(part)
    return bytes(data)


def receive(connection: socket.socket) -> bytes:
    size = struct.unpack("!I", exact(connection, 4))[0]
    if not 1 <= size <= MAX_FRAME:
        raise ValueError("invalid_frame")
    return exact(connection, size)


def send(connection: socket.socket, data: bytes) -> None:
    if not 1 <= len(data) <= MAX_FRAME:
        raise ValueError("invalid_frame")
    connection.sendall(struct.pack("!I", len(data)) + data)


def exchange(protocol: str, host: str, port: int, data: bytes) -> bytes:
    kind = socket.SOCK_STREAM if protocol == "tcp" else socket.SOCK_DGRAM
    with socket.socket(socket.AF_INET, kind) as connection:
        connection.settimeout(3)
        connection.connect((host, port))
        if protocol == "tcp":
            send(connection, data)
            return receive(connection)
        connection.send(data)
        response = connection.recv(MAX_FRAME + 1)
        if len(response) > MAX_FRAME:
            raise ValueError("invalid_frame")
        return response


def validate(config: dict, role: str) -> dict:
    if config.get("protocol") not in {"tcp", "udp", "tls", "h3"}:
        raise ValueError("invalid_protocol")
    if (
        not isinstance(config.get("token"), str)
        or not 32 <= len(config["token"]) <= 128
    ):
        raise ValueError("invalid_token")
    port = config.get("port")
    if type(port) is not int or not 28000 <= port <= 28999:
        raise ValueError("invalid_port")
    if not isinstance(config.get("node_id"), str) or len(config["node_id"]) > 32:
        raise ValueError("invalid_node")
    if role == "client":
        config["host"] = str(ipaddress.IPv4Address(config["host"]))
        if config["protocol"] in {"tls", "h3"}:
            if (
                not isinstance(config.get("certificate"), str)
                or len(config["certificate"]) > 4096
                or not isinstance(config.get("target_node"), str)
                or type(config.get("controlled_failure", False)) is not bool
            ):
                raise ValueError("invalid_certificate_config")
        payloads = config.get("payloads", [])
        if not 1 <= len(payloads) <= 10:
            raise ValueError("invalid_workload")
        for payload in payloads:
            if (
                not isinstance(payload, str)
                or not 1 <= len(bytes.fromhex(payload)) <= 512
            ):
                raise ValueError("invalid_payload")
    else:
        if config["protocol"] in {"tls", "h3"}:
            config["public_address"] = str(
                ipaddress.IPv4Address(config["public_address"])
            )
        config["bind_address"] = str(
            ipaddress.IPv4Address(config.get("bind_address", "0.0.0.0"))
        )
        peers = config.get("peers", [])
        if not 1 <= len(peers) <= 8:
            raise ValueError("invalid_peers")
        config["peers"] = [str(ipaddress.IPv4Address(peer)) for peer in peers]
        if role == "relay":
            backends = config.get("backends", [])
            if not 1 <= len(backends) <= 8:
                raise ValueError("invalid_backends")
            config["backends"] = [str(ipaddress.IPv4Address(peer)) for peer in backends]
    return config


def serve(config: dict, relay: bool = False) -> dict:
    kind = socket.SOCK_STREAM if config["protocol"] == "tcp" else socket.SOCK_DGRAM
    stopped = threading.Event()

    def watch_input():
        os.read(sys.stdin.fileno(), 1)
        stopped.set()

    threading.Thread(target=watch_input, daemon=True).start()
    requests = 0
    with socket.socket(socket.AF_INET, kind) as listener:
        # No SO_REUSEPORT and no service stop: an occupied port simply fails.
        if os.name == "nt":
            listener.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        elif kind == socket.SOCK_STREAM:
            # Permit TIME_WAIT reuse while preserving active listener exclusion.
            listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.bind((config["bind_address"], config["port"]))
        if kind == socket.SOCK_STREAM:
            listener.listen(8)
        print(json.dumps({"ready": True, "port": config["port"]}), flush=True)
        deadline = time.monotonic() + 60
        while not stopped.is_set() and time.monotonic() < deadline:
            if not select.select([listener], [], [], 0.2)[0]:
                continue
            connection = None
            try:
                if kind == socket.SOCK_STREAM:
                    connection, peer = listener.accept()
                    connection.settimeout(3)
                    if peer[0] not in config["peers"]:
                        continue
                    data = receive(connection)
                else:
                    data, peer = listener.recvfrom(MAX_FRAME + 1)
                    if peer[0] not in config["peers"] or len(data) > MAX_FRAME:
                        continue
                message = json.loads(data)
                if not isinstance(message, dict):
                    continue
                if not isinstance(message.get("token"), str) or not hmac.compare_digest(
                    message["token"], config["token"]
                ):
                    continue
                payload = bytes.fromhex(message["payload"])
                if not 1 <= len(payload) <= 512:
                    continue
                if relay:
                    backend = config["backends"][requests % len(config["backends"])]
                    response = exchange(
                        config["protocol"], backend, config["port"], data
                    )
                else:
                    response = json.dumps(
                        {"payload": message["payload"], "backend": config["node_id"]}
                    ).encode()
                if connection:
                    send(connection, response)
                else:
                    listener.sendto(response, peer)
                requests += 1
            except (OSError, ValueError, KeyError, TypeError):
                pass
            finally:
                if connection:
                    connection.close()
    return {"requests": requests, "node_id": config["node_id"]}


def client(config: dict) -> dict:
    observations = []
    for payload in config["payloads"]:
        data = json.dumps({"token": config["token"], "payload": payload}).encode()
        started = time.monotonic()
        response = json.loads(
            exchange(config["protocol"], config["host"], config["port"], data)
        )
        if response.get("payload") != payload:
            raise ValueError("payload_mismatch")
        raw = bytes.fromhex(payload)
        observations.append(
            {
                "client": config["node_id"],
                "backend": response["backend"],
                "bytes_echoed": len(raw),
                "rtt_ms": (time.monotonic() - started) * 1000,
                "payload_sha256": hashlib.sha256(raw).hexdigest(),
            }
        )
    return {"status": "succeeded", "observations": observations}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "role", choices=["check", "server", "relay", "client", "capture"]
    )
    args = parser.parse_args()
    if args.role == "check":
        checkout = Path(__file__).resolve().parents[4]
        source = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=checkout,
            capture_output=True,
            text=True,
            timeout=5,
        )
        print(
            json.dumps(
                {
                    "agent_version": 3,
                    "capture_available": bool(
                        shutil.which("tcpdump") and shutil.which("timeout")
                    ),
                    "git_sha": source.stdout.strip()
                    if source.returncode == 0
                    else None,
                    "python": platform.python_version(),
                    "os": platform.system(),
                    "protocols": ["tcp", "udp"]
                    + (["tls", "h3"] if importlib.util.find_spec("aioquic") else []),
                }
            )
        )
        return 0
    try:
        line = sys.stdin.buffer.readline(16385)
        if len(line) > 16384:
            raise ValueError("invalid_input")
        if args.role == "capture":
            from pprl_core.capture import session

            result = session(json.loads(line))
            print(json.dumps(result), flush=True)
            return 0
        config = validate(json.loads(line), args.role)
        if config["protocol"] in {"tls", "h3"}:
            from pprl_core.secure_agent import session

            if sys.platform == "linux":
                import resource

                resource.setrlimit(resource.RLIMIT_CORE, (0, 0))

            result = session(config, args.role)
            print(json.dumps(result), flush=True)
            return 0
        result = (
            client(config)
            if args.role == "client"
            else serve(config, args.role == "relay")
        )
        print(json.dumps(result), flush=True)
        return 0
    except OSError as error:
        reason = "port_in_use" if error.errno in {48, 98, 10048} else "network_io_error"
    except (ValueError, KeyError, TypeError):
        reason = "invalid_agent_input_or_response"
    print(json.dumps({"error": reason}), flush=True)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

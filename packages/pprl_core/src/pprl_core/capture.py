"""Bounded capture adapters and payload-free, address-redacted classic PCAP."""

import base64
import contextlib
import csv
import hashlib
import io
import ipaddress
import json
import os
import re
import selectors
import shutil
import signal
import struct
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import Protocol

MAX_PACKETS = 2000
MAX_RAW_BYTES = 1024 * 1024


def redact_log(value):
    """Redact structured credentials and IPv4 strings in diagnostic output."""
    if isinstance(value, dict):
        return {
            key: "[redacted]"
            if any(
                word in key.lower()
                for word in (
                    "password",
                    "token",
                    "secret",
                    "authorization",
                    "private_key",
                )
            )
            else redact_log(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact_log(item) for item in value]
    if isinstance(value, str):
        value = re.sub(r"\b(?:\d{1,3}\.){3}\d{1,3}\b", "[ip]", value)
        return re.sub(
            r"(?i)\b(password|token|secret|authorization)\s*[:=]\s*(?:Bearer\s+)?[^\s,;]+",
            r"\1=[redacted]",
            value,
        )
    return value


class CaptureError(ValueError):
    pass


class CaptureAdapter(Protocol):
    def start(self) -> None: ...
    def stop(self) -> tuple[bytes, dict]: ...
    def close(self) -> None: ...


def _checksum(data: bytes) -> int:
    if len(data) % 2:
        data += b"\0"
    total = sum(struct.unpack(f"!{len(data) // 2}H", data))
    while total >> 16:
        total = (total & 65535) + (total >> 16)
    return (~total) & 65535


def _ipv4(frame: bytes, link_type: int) -> bytes | None:
    if link_type == 101:
        return frame
    if link_type == 276 and len(frame) >= 20:
        return frame[20:] if frame[:2] == b"\x08\x00" else None
    if link_type == 113 and len(frame) >= 16:
        return frame[16:] if frame[14:16] == b"\x08\x00" else None
    if link_type == 1 and len(frame) >= 14:
        offset, kind = 14, frame[12:14]
        for _ in range(2):
            if kind not in {b"\x81\x00", b"\x88\xa8"}:
                break
            if len(frame) < offset + 4:
                return None
            kind = frame[offset + 2 : offset + 4]
            offset += 4
        return frame[offset:] if kind == b"\x08\x00" else None
    return None


def sanitize_pcap(
    raw: bytes,
    addresses: dict[str, str],
    pairs: list[list[str]],
    protocol: str,
    port: int,
) -> dict:
    """Parse strict bounded input; export L3 headers only, never original frames."""
    if (
        protocol not in {"tcp", "udp"}
        or type(port) is not int
        or not 28000 <= port <= 28999
    ):
        raise CaptureError("invalid_capture_scope")
    if not 24 <= len(raw) <= MAX_RAW_BYTES:
        raise CaptureError("invalid_pcap_size")
    formats = {
        b"\xd4\xc3\xb2\xa1": ("<", 1),
        b"\xa1\xb2\xc3\xd4": (">", 1),
        b"\x4d\x3c\xb2\xa1": ("<", 1000),
        b"\xa1\xb2\x3c\x4d": (">", 1000),
    }
    if raw[:4] not in formats:
        raise CaptureError("unsupported_pcap_format")
    endian, divisor = formats[raw[:4]]
    major, minor, _, _, snaplen, link_type = struct.unpack(endian + "HHIIII", raw[4:24])
    if (
        (major, minor) != (2, 4)
        or not 1 <= snaplen <= 65535
        or link_type not in {1, 101, 113, 276}
    ):
        raise CaptureError("unsupported_pcap_header")
    mapping = {
        str(ipaddress.IPv4Address(a)): ipaddress.IPv4Address(b).packed
        for a, b in addresses.items()
    }
    allowed = {tuple(pair) for pair in pairs} | {
        tuple(reversed(pair)) for pair in pairs
    }
    output = io.BytesIO()
    output.write(struct.pack("<IHHIIII", 0xA1B2C3D4, 2, 4, 0, 0, 120, 101))
    offset, seen, skipped, origin = 24, 0, 0, None
    flows = {}
    while offset < len(raw):
        if offset + 16 > len(raw) or seen >= MAX_PACKETS:
            raise CaptureError("truncated_or_excess_pcap")
        sec, fraction, included, original = struct.unpack(
            endian + "IIII", raw[offset : offset + 16]
        )
        offset += 16
        if (
            included > snaplen
            or included > original
            or offset + included > len(raw)
            or fraction >= 1000000 * divisor
        ):
            raise CaptureError("invalid_pcap_record")
        frame = raw[offset : offset + included]
        offset += included
        seen += 1
        ip = _ipv4(frame, link_type)
        if ip is None or len(ip) < 20 or ip[0] >> 4 != 4:
            skipped += 1
            continue
        ihl = (ip[0] & 15) * 4
        ip_size = int.from_bytes(ip[2:4], "big")
        source, destination = (
            str(ipaddress.IPv4Address(ip[12:16])),
            str(ipaddress.IPv4Address(ip[16:20])),
        )
        if (
            not 20 <= ihl <= 60
            or len(ip) < ihl + 8
            or int.from_bytes(ip[6:8], "big") & 0x3FFF
        ):
            skipped += 1
            continue
        transport = ip[ihl:]
        expected = 6 if protocol == "tcp" else 17
        source_port, destination_port = struct.unpack("!HH", transport[:4])
        if (
            ip[9] != expected
            or (source, destination) not in allowed
            or port not in {source_port, destination_port}
        ):
            skipped += 1
            continue
        if source not in mapping or destination not in mapping:
            skipped += 1
            continue
        thl = (
            ((transport[12] >> 4) * 4) if expected == 6 and len(transport) >= 20 else 8
        )
        if (
            (expected == 6 and not 20 <= thl <= 60)
            or len(transport) < thl
            or ip_size < ihl + thl
        ):
            skipped += 1
            continue
        header = bytearray(ip[:ihl] + transport[:thl])
        header[12:16], header[16:20] = mapping[source], mapping[destination]
        header[20:ihl] = b"\0" * (ihl - 20)
        if expected == 6:
            header[ihl + 16 : ihl + 18] = b"\0\0"
            header[ihl + 20 :] = b"\0" * (thl - 20)
        else:
            header[ihl + 6 : ihl + 8] = b"\0\0"
        header[10:12] = b"\0\0"
        header[10:12] = struct.pack("!H", _checksum(bytes(header[:ihl])))
        timestamp = sec * 1000000 + fraction // divisor
        if origin is None:
            origin = timestamp
        relative = max(0, timestamp - origin)
        output.write(
            struct.pack(
                "<IIII", relative // 1000000, relative % 1000000, len(header), ip_size
            )
        )
        output.write(header)
        key = (
            str(ipaddress.IPv4Address(mapping[source])),
            str(ipaddress.IPv4Address(mapping[destination])),
            source_port,
            destination_port,
            protocol,
        )
        flow = flows.setdefault(
            key,
            {
                "source_ip": key[0],
                "destination_ip": key[1],
                "source_port": source_port,
                "destination_port": destination_port,
                "protocol": protocol,
                "packets": 0,
                "ip_bytes": 0,
                "header_bytes": 0,
            },
        )
        flow["packets"] += 1
        flow["ip_bytes"] += ip_size
        flow["header_bytes"] += len(header)
    data = output.getvalue()
    return {
        "schema_version": "1.0.0",
        "packets": sum(f["packets"] for f in flows.values()),
        "ip_bytes": sum(f["ip_bytes"] for f in flows.values()),
        "records_seen": seen,
        "records_excluded": skipped,
        "flows": list(flows.values()),
        "pcap_base64": base64.b64encode(data).decode(),
        "pcap_sha256": hashlib.sha256(data).hexdigest(),
        "redaction": "payload_removed_ips_pseudonymized_options_zeroed",
        "timestamps": "relative_to_first_accepted_packet",
        "transport_checksums": "not_verifiable_without_payload",
    }


def flows_csv(report: dict) -> bytes:
    buffer = io.StringIO(newline="")
    fields = [
        "source_ip",
        "destination_ip",
        "source_port",
        "destination_port",
        "protocol",
        "packets",
        "ip_bytes",
        "header_bytes",
    ]
    writer = csv.DictWriter(buffer, fieldnames=fields)
    writer.writeheader()
    writer.writerows(report["flows"])
    return buffer.getvalue().encode("utf-8")


class TcpdumpCapture:
    def __init__(
        self, directory: Path, pairs: list[list[str]], protocol: str, port: int
    ):
        if (
            protocol not in {"tcp", "udp"}
            or type(port) is not int
            or not 28000 <= port <= 28999
            or not 1 <= len(pairs) <= 64
        ):
            raise CaptureError("invalid_capture_scope")
        edges = []
        for a, b in pairs:
            a, b = str(ipaddress.IPv4Address(a)), str(ipaddress.IPv4Address(b))
            edges.append(f"(host {a} and host {b})")
        self.filter = f"ip and {protocol} port {port} and (" + " or ".join(edges) + ")"
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.temp = tempfile.TemporaryDirectory(prefix="capture-", dir=directory)
        self.path = Path(self.temp.name) / "private-raw.pcap"
        self.process = None

    def start(self) -> None:
        binary = shutil.which("tcpdump")
        watchdog = shutil.which("timeout")
        if not binary or not watchdog:
            raise CaptureError("capture_tool_unavailable")
        self.process = subprocess.Popen(
            [
                watchdog,
                "--signal=INT",
                "--kill-after=3",
                "60",
                binary,
                "-i",
                "any",
                "-p",
                "-nn",
                "--immediate-mode",
                "-s",
                "256",
                "-U",
                "-c",
                str(MAX_PACKETS),
                "-Z",
                "root",
                "-w",
                str(self.path),
                self.filter,
            ],
            stdout=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            bufsize=0,
            start_new_session=True,
            env=os.environ | {"LC_ALL": "C"},
        )
        deadline = time.monotonic() + 5
        with selectors.DefaultSelector() as selector:
            selector.register(self.process.stderr, selectors.EVENT_READ)
            while time.monotonic() < deadline:
                if selector.select(0.1):
                    line = self.process.stderr.readline(2048)
                    if b"listening on" in line:
                        return
                if self.process.poll() is not None:
                    break
        raise CaptureError("capture_start_failed")

    def stop(self) -> tuple[bytes, dict]:
        if self.process is None:
            raise CaptureError("capture_not_started")
        if self.process.poll() is None:
            with contextlib.suppress(ProcessLookupError):
                os.killpg(self.process.pid, signal.SIGINT)
        try:
            _, errors = self.process.communicate(timeout=3)
        except subprocess.TimeoutExpired:
            with contextlib.suppress(ProcessLookupError):
                os.killpg(self.process.pid, signal.SIGKILL)
            self.process.communicate()
            raise CaptureError("capture_stop_failed") from None
        if self.process.returncode not in {0, 130, -signal.SIGINT}:
            raise CaptureError("capture_process_failed")
        dropped = re.search(rb"(\d+) packets dropped by kernel", errors)
        return self.path.read_bytes(), {
            "kernel_dropped_packets": int(dropped[1]) if dropped else None
        }

    def close(self) -> None:
        if self.process is not None and self.process.poll() is None:
            with contextlib.suppress(ProcessLookupError):
                os.killpg(self.process.pid, signal.SIGTERM)
            try:
                self.process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                with contextlib.suppress(ProcessLookupError):
                    os.killpg(self.process.pid, signal.SIGKILL)
            self.process.communicate()
        self.temp.cleanup()


def session(config: dict) -> dict:
    pairs = config["pairs"]
    addresses = config["address_map"]
    if not isinstance(addresses, dict) or len(addresses) > 32:
        raise CaptureError("invalid_capture_scope")
    for address, alias in addresses.items():
        ipaddress.IPv4Address(address)
        if ipaddress.IPv4Address(alias) not in ipaddress.IPv4Network("198.18.0.0/15"):
            raise CaptureError("invalid_redaction_address")
    directory = Path(__file__).resolve().parents[4] / "artifacts/capture"
    adapter: CaptureAdapter = TcpdumpCapture(
        directory, pairs, config["protocol"], config["port"]
    )
    stopped = threading.Event()

    def watch():
        os.read(sys.stdin.fileno(), 1)
        stopped.set()

    try:
        adapter.start()
        print(json.dumps({"ready": True, "capture": True}), flush=True)
        threading.Thread(target=watch, daemon=True).start()
        stopped.wait(55)
        raw, stats = adapter.stop()
        report = sanitize_pcap(
            raw, addresses, pairs, config["protocol"], config["port"]
        )
        report.update(
            stats,
            adapter="tcpdump",
            interface="any",
            limit_reached=report["records_seen"] >= MAX_PACKETS,
        )
        return report
    finally:
        adapter.close()

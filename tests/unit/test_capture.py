"""Adversarial PCAP parsing, scope filtering and payload/IP redaction."""

import base64
import hashlib
import ipaddress
import json
import struct
from pathlib import Path

import pytest
from pprl_core import capture, cli
from pprl_core.capture import CaptureError, flows_csv, redact_log, sanitize_pcap

MAPPING = {"10.0.0.1": "198.18.0.1", "10.0.0.2": "198.18.0.2"}
PAIRS = [["10.0.0.1", "10.0.0.2"]]


def packet(
    protocol="udp",
    source="10.0.0.1",
    destination="10.0.0.2",
    port=28080,
    payload=b"token=PRIVATE_SYNTHETIC_SECRET",
    options=False,
):
    transport = struct.pack("!HHHH", 42000, port, 8 + len(payload), 1234)
    if protocol == "tcp":
        transport = struct.pack(
            "!HHIIBBHHH",
            42000,
            port,
            1,
            2,
            0x60 if options else 0x50,
            0x18,
            4096,
            1234,
            0,
        )
        if options:
            transport += b"SECR"
    header = struct.pack(
        "!BBHHHBBH4s4s",
        0x46 if options else 0x45,
        0,
        20 + (4 if options else 0) + len(transport) + len(payload),
        1,
        0,
        64,
        6 if protocol == "tcp" else 17,
        0,
        ipaddress.IPv4Address(source).packed,
        ipaddress.IPv4Address(destination).packed,
    )
    return header + (b"IPOP" if options else b"") + transport + payload


def pcap(packets, link_type=101, endian="<", nano=False):
    magic = 0xA1B23C4D if nano else 0xA1B2C3D4
    result = struct.pack(endian + "IHHIIII", magic, 2, 4, 0, 0, 256, link_type)
    for index, data in enumerate(packets):
        if link_type == 1:
            data = b"MAC_SECRET!!" + b"\x08\x00" + data
        elif link_type == 113:
            data = b"\0" * 14 + b"\x08\x00" + data
        elif link_type == 276:
            data = b"\x08\x00" + b"\0" * 18 + data
        result += (
            struct.pack(endian + "IIII", 100 + index, 15000, len(data), len(data))
            + data
        )
    return result


@pytest.mark.parametrize("link_type", [1, 101, 113, 276])
@pytest.mark.parametrize("protocol", ["tcp", "udp"])
@pytest.mark.parametrize(
    "endian,nano", [("<", False), (">", False), ("<", True), (">", True)]
)
def test_headers_only_export_is_redacted_and_byte_counts_preserved(
    link_type, protocol, endian, nano
):
    source = packet(protocol)
    report = sanitize_pcap(
        pcap([source], link_type, endian, nano), MAPPING, PAIRS, protocol, 28080
    )
    data = base64.b64decode(report["pcap_base64"])
    assert report["packets"] == 1
    assert report["ip_bytes"] == len(source)
    assert report["flows"][0]["source_ip"] == "198.18.0.1"
    assert report["pcap_sha256"] == hashlib.sha256(data).hexdigest()
    assert b"PRIVATE_SYNTHETIC_SECRET" not in data and b"MAC_SECRET" not in data
    assert ipaddress.IPv4Address("10.0.0.1").packed not in data
    assert len(data) == 24 + 16 + (40 if protocol == "tcp" else 28)
    exported = flows_csv(report)
    assert b"10.0.0.1" not in exported and b"198.18.0.1" in exported


def test_scope_excludes_other_hosts_ports_and_protocols():
    frames = [packet(), packet(source="10.0.0.99"), packet(port=443), packet("tcp")]
    report = sanitize_pcap(pcap(frames), MAPPING, PAIRS, "udp", 28080)
    assert report["packets"] == 1 and report["records_excluded"] == 3


def test_options_and_payload_removed_even_when_headers_contain_opaque_data():
    report = sanitize_pcap(
        pcap([packet("tcp", options=True)]), MAPPING, PAIRS, "tcp", 28080
    )
    data = base64.b64decode(report["pcap_base64"])
    assert b"IPOP" not in data and b"SECR" not in data
    assert report["flows"][0]["header_bytes"] == 48


@pytest.mark.parametrize(
    "raw",
    [
        b"",
        b"garbage" * 5,
        pcap([packet()])[:-1],
        pcap([]) + b"x",
        pcap([packet()], link_type=9999),
    ],
)
def test_malformed_or_unsupported_input_fails_closed(raw):
    with pytest.raises(CaptureError):
        sanitize_pcap(raw, MAPPING, PAIRS, "udp", 28080)


def test_fragmented_datagram_is_counted_as_excluded():
    frame = bytearray(packet())
    frame[6:8] = b"\x20\0"
    report = sanitize_pcap(pcap([bytes(frame)]), MAPPING, PAIRS, "udp", 28080)
    assert report["packets"] == 0 and report["records_excluded"] == 1


def test_structured_and_text_diagnostics_redact_secrets_and_ips():
    source = {
        "token": "do-not-log",
        "details": [
            "peer 87.107.146.217 token=private",
            {"Authorization": "Bearer private"},
        ],
        "packets": 3,
    }
    result = redact_log(source)
    assert result["token"] == "[redacted]"
    assert "87.107.146.217" not in str(result)
    assert "private" not in str(result) and result["packets"] == 3


def test_capture_session_closes_adapter_after_start_failure(monkeypatch):
    state = {"closed": False}

    class BrokenAdapter:
        def __init__(self, *args):
            pass

        def start(self):
            raise CaptureError("capture_start_failed")

        def close(self):
            state["closed"] = True

    monkeypatch.setattr(capture, "TcpdumpCapture", BrokenAdapter)
    with pytest.raises(CaptureError, match="capture_start_failed"):
        capture.session(
            {"pairs": PAIRS, "address_map": MAPPING, "protocol": "udp", "port": 28080}
        )
    assert state["closed"] is True


def test_synthetic_example_matches_contract_and_csv_digest():
    directory = Path(__file__).resolve().parents[2] / "datasets/synthetic/capture"
    report = json.loads((directory / "example.json").read_text())
    cli._validate(report, "capture")
    assert report["adapter"] == "synthetic_fixture"
    assert (
        report["csv_sha256"]
        == hashlib.sha256((directory / "example.csv").read_bytes()).hexdigest()
    )

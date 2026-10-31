"""Regenerate the public synthetic JSON/CSV fixture and ignored header-only PCAP."""

import base64
import hashlib
import ipaddress
import json
import struct
from pathlib import Path

from pprl_core import cli
from pprl_core.capture import flows_csv, sanitize_pcap


def main() -> None:
    repository = Path(__file__).resolve().parents[1]
    payload = b"synthetic-capture-example"
    udp = struct.pack("!HHHH", 42000, 28080, 8 + len(payload), 0)
    packet = (
        struct.pack(
            "!BBHHHBBH4s4s",
            0x45,
            0,
            20 + len(udp) + len(payload),
            1,
            0,
            64,
            17,
            0,
            ipaddress.IPv4Address("10.0.0.1").packed,
            ipaddress.IPv4Address("10.0.0.2").packed,
        )
        + udp
        + payload
    )
    raw = struct.pack("<IHHIIII", 0xA1B2C3D4, 2, 4, 0, 0, 256, 101)
    for index in range(2):
        raw += struct.pack("<IIII", 100 + index, 0, len(packet), len(packet)) + packet
    report = sanitize_pcap(
        raw,
        {"10.0.0.1": "198.18.0.1", "10.0.0.2": "198.18.0.2"},
        [["10.0.0.1", "10.0.0.2"]],
        "udp",
        28080,
    )
    data = base64.b64decode(report.pop("pcap_base64"))
    csv_data = flows_csv(report)
    report.update(
        adapter="synthetic_fixture",
        interface="synthetic",
        node_id="node-b",
        kernel_dropped_packets=0,
        limit_reached=False,
        csv_sha256=hashlib.sha256(csv_data).hexdigest(),
    )
    cli._validate(report, "capture")
    directory = repository / "datasets/synthetic/capture"
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "example.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    (directory / "example.csv").write_bytes(csv_data)
    artifact = repository / "artifacts/synthetic-capture-example.pcap"
    artifact.parent.mkdir(exist_ok=True)
    artifact.write_bytes(data)
    print("Synthetic JSON/CSV regenerated; sanitized PCAP is in ignored artifacts/.")


if __name__ == "__main__":
    main()

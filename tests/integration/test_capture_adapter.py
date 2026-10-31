"""Actual tcpdump lifecycle on Linux root; no system tool installation by tests."""

import base64
import json
import os
import shutil
import socket
import struct
import sys
import time

import pytest
from fastapi.testclient import TestClient
from pprl_core import cli, cluster_runner, panel
from pprl_core.capture import TcpdumpCapture, sanitize_pcap
from pprl_core.cluster import Inventory, Node, Topology
from pprl_core.cluster_ssh import SSH


@pytest.mark.skipif(
    sys.platform != "linux"
    or not hasattr(os, "geteuid")
    or os.geteuid() != 0
    or not shutil.which("tcpdump"),
    reason="requires existing Linux root tcpdump",
)
def test_real_filtered_capture_closes_process_and_removes_private_raw(tmp_path):
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as server:
        for port in range(28300, 28400):
            try:
                server.bind(("127.0.0.1", port))
                break
            except OSError:
                continue
        else:
            pytest.skip("dedicated test ports unavailable")
        server.settimeout(3)
        adapter = TcpdumpCapture(tmp_path, [["127.0.0.1", "127.0.0.1"]], "udp", port)
        temporary = adapter.path.parent
        try:
            adapter.start()
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as client:
                client.settimeout(3)
                client.sendto(b"private-synthetic-token", ("127.0.0.1", port))
                payload, peer = server.recvfrom(1024)
                server.sendto(payload, peer)
                assert client.recvfrom(1024)[0] == payload
            time.sleep(0.15)
            raw, stats = adapter.stop()
            report = sanitize_pcap(
                raw,
                {"127.0.0.1": "198.18.0.1"},
                [["127.0.0.1", "127.0.0.1"]],
                "udp",
                port,
            )
            assert report["packets"] >= 2
            assert b"private-synthetic-token" not in base64.b64decode(
                report["pcap_base64"]
            )
            assert stats["kernel_dropped_packets"] == 0
        finally:
            adapter.close()
        assert adapter.process.poll() is not None and not temporary.exists()
        with pytest.raises(ProcessLookupError):
            os.killpg(adapter.process.pid, 0)


def test_capture_download_is_authenticated_checksummed_and_empty_not_success(
    tmp_path, monkeypatch
):
    inventory = Inventory(tmp_path)
    for identifier, address in [("a", "10.0.0.1"), ("b", "10.0.0.2")]:
        inventory.add_node(
            Node(
                node_id=identifier,
                name=identifier,
                address=address,
                host_key="ssh-ed25519 " + "A" * 68,
            )
        )
    topology = inventory.add_topology(
        Topology(name="capture", clients=["a"], servers=["b"])
    )
    raw = struct.pack("<IHHIIII", 0xA1B2C3D4, 2, 4, 0, 0, 256, 101)
    metadata = sanitize_pcap(
        raw,
        {"10.0.0.1": "198.18.0.1", "10.0.0.2": "198.18.0.2"},
        [["10.0.0.1", "10.0.0.2"]],
        "tcp",
        28080,
    )

    async def execute(transport, plan, definition, payloads, observations, captures):
        assert definition["capture"] is True
        captures.append(metadata | {"node_id": "b"})
        return []

    monkeypatch.setattr(cluster_runner, "execute", execute)
    monkeypatch.setattr(
        cli, "_source_metadata", lambda: {"git_sha": "a" * 40, "dirty": False}
    )
    import threading

    result = cluster_runner.run(
        tmp_path,
        inventory,
        SSH(tmp_path),
        topology["topology_id"],
        threading.Event(),
        capture_override=True,
    )
    assert result["status"] == "failed" and result["failure_reason"] == "capture_empty"
    access = tmp_path / "access.json"
    panel.initialize(tmp_path, access)
    url = f"/api/cluster/runs/{result['run_id']}/capture/b/pcap"
    with TestClient(panel.create_app(tmp_path), base_url="http://127.0.0.1") as client:
        assert client.get(url).status_code == 401
        client.post(
            "/api/login",
            json=json.loads(access.read_text()),
            headers={"X-NetSpectra-Client": "panel"},
        ).raise_for_status()
        assert client.get(url).content == base64.b64decode(metadata["pcap_base64"])
        assert client.get(url.replace("/pcap", "/csv")).status_code == 200
        path = tmp_path / "network-captures" / result["run_id"] / "b.pcap"
        path.write_bytes(b"tampered")
        assert client.get(url).status_code == 400
        assert client.get(url.replace("/b/", "/unknown/")).status_code == 404

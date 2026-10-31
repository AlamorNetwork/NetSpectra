"""Real socket TLS/HTTP3, certificate rejection, qlog privacy and exclusive bind."""

import asyncio
import json
import socket
import subprocess
import sys
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient
from pprl_core import cli, cluster_runner, panel, remote_agent
from pprl_core.cluster import Inventory, Node, Topology
from pprl_core.cluster_ssh import SSH
from pprl_core.qlog import SafeLogger, read_qlog
from pydantic import ValidationError


@pytest.mark.parametrize("protocol", ["tls", "h3"])
@pytest.mark.parametrize("failure", [False, True])
def test_secure_worker_real_handshake_echo_and_certificate_failure(protocol, failure):
    kind = socket.SOCK_STREAM if protocol == "tls" else socket.SOCK_DGRAM
    for port in range(28100, 28999):
        with socket.socket(socket.AF_INET, kind) as probe:
            try:
                probe.bind(("0.0.0.0", port))
                break
            except OSError:
                pass
    config = {
        "protocol": protocol,
        "port": port,
        "node_id": "backend",
        "token": "x" * 40,
        "bind_address": "127.0.0.1",
        "public_address": "127.0.0.1",
        "peers": ["127.0.0.1"],
    }
    process = subprocess.Popen(
        [sys.executable, "-m", "pprl_core.remote_agent", "server"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        process.stdin.write(json.dumps(config) + "\n")
        process.stdin.flush()
        with ThreadPoolExecutor(max_workers=1) as executor:
            ready = json.loads(
                executor.submit(process.stdout.readline).result(timeout=10)
            )
        assert ready.get("ready"), ready
        from pprl_core.secure_agent import client

        result = asyncio.run(
            client(
                config
                | {
                    "node_id": "client",
                    "target_node": "backend",
                    "host": "127.0.0.1",
                    "certificate": ready["certificate"],
                    "payloads": ["616263", "646566"],
                    "controlled_failure": failure,
                }
            )
        )
        assert result["status"] == ("failed" if failure else "succeeded")
        assert len(result["observations"]) == (1 if failure else 2)
        for sample in result["observations"]:
            assert sample["bytes_echoed"] == (0 if failure else 3)
            assert (sample["handshake_ms"] is None) == failure
            if not failure:
                assert sample["handshake_ms"] > 0 and sample["request_ms"] > 0
            if protocol == "h3":
                summary = read_qlog(sample["qlog"])
                assert summary["packets_sent"] > 0
                assert summary["retry_packets"] >= (0 if failure else 1)
                exported = json.dumps(sample["qlog"])
                assert "127.0.0.1" not in exported and "x" * 40 not in exported
                assert "616263" not in exported and "ODCID" not in exported
    finally:
        process.stdin.close()
        process.wait(timeout=8)
        assert process.returncode == 0, process.stderr.read()
    with socket.socket(socket.AF_INET, kind) as probe:
        if protocol == "tls" and sys.platform != "win32":
            probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        probe.bind(("127.0.0.1", port))


@pytest.mark.parametrize("protocol", ["tls", "h3"])
def test_secure_topology_rejects_unsupported_relay(protocol):
    with pytest.raises(ValidationError):
        Topology(
            name="invalid",
            protocol=protocol,
            clients=["a"],
            servers=["b"],
            load_balancer="c",
        )
    with pytest.raises(ValueError):
        remote_agent.validate({"protocol": protocol}, "client")


def test_failed_secure_sample_qlog_download_auth_and_tampering(tmp_path, monkeypatch):
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
        Topology(name="h3", clients=["a"], servers=["b"], protocol="h3")
    )

    async def execute(transport, plan, definition, payloads, observations, captures):
        import hashlib

        logger = SafeLogger()
        trace = logger.start_trace(True, b"secret-id")
        trace.log_event(
            category="transport",
            event="packet_sent",
            data={"header": {"packet_type": "initial"}},
        )
        observations.append(
            {
                "client": "a",
                "backend": "b",
                "bytes_echoed": 0,
                "payload_sha256": hashlib.sha256(payloads[0]).hexdigest(),
                "status": "failed",
                "failure_reason": "handshake_timeout",
                "timeout": True,
                "rtt_ms": 7000,
                "handshake_ms": None,
                "request_ms": None,
                "qlog": logger.export(),
            }
        )
        raise cli.CLIError("handshake_timeout")

    monkeypatch.setattr(cluster_runner, "execute", execute)
    result = cluster_runner.run(
        tmp_path, inventory, SSH(tmp_path), topology["topology_id"], threading.Event()
    )
    assert result["status"] == "failed" and len(result["observations"]) == 1
    assert result["analysis"]["observed"]["timeouts"] == 1
    assert "qlog" not in result["observations"][0]
    access = tmp_path / "access.json"
    panel.initialize(tmp_path, access)
    url = f"/api/cluster/runs/{result['run_id']}/qlog/trace-0000"
    with TestClient(panel.create_app(tmp_path), base_url="http://127.0.0.1") as client:
        assert client.get(url).status_code == 401
        client.post(
            "/api/login",
            json=json.loads(access.read_text()),
            headers={"X-NetSpectra-Client": "panel"},
        ).raise_for_status()
        assert read_qlog(client.get(url).json())["packets_sent"] == 1
        assert client.get(url.replace("trace-0000", "trace-9999")).status_code == 404
        path = tmp_path / "network-qlogs" / result["run_id"] / "trace-0000.qlog"
        path.write_bytes(b"tampered")
        assert client.get(url).status_code == 400


@pytest.mark.parametrize("protocol", ["tls", "h3"])
def test_secure_occupied_port_preserves_listener(protocol):
    kind = socket.SOCK_STREAM if protocol == "tls" else socket.SOCK_DGRAM
    with socket.socket(socket.AF_INET, kind) as listener:
        for port in range(28200, 28999):
            try:
                listener.bind(("0.0.0.0", port))
                break
            except OSError:
                continue
        if kind == socket.SOCK_STREAM:
            listener.listen(1)
        config = {
            "protocol": protocol,
            "port": port,
            "node_id": "b",
            "token": "x" * 40,
            "bind_address": "0.0.0.0",
            "public_address": "127.0.0.1",
            "peers": ["127.0.0.1"],
        }
        result = subprocess.run(
            [sys.executable, "-m", "pprl_core.remote_agent", "server"],
            input=json.dumps(config) + "\n",
            text=True,
            capture_output=True,
            timeout=10,
        )
        assert (
            result.returncode == 1
            and json.loads(result.stdout)["error"] == "port_in_use"
        )
        assert listener.getsockname()[1] == port


def test_blackholed_quic_has_timeout_observation_and_readable_qlog(tmp_path):
    from pprl_core.secure_agent import certificate, client

    cert = certificate("127.0.0.1", tmp_path)
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as blackhole:
        blackhole.bind(("127.0.0.1", 0))
        result = asyncio.run(
            client(
                {
                    "protocol": "h3",
                    "host": "127.0.0.1",
                    "port": blackhole.getsockname()[1],
                    "certificate": cert,
                    "token": "x" * 40,
                    "node_id": "a",
                    "target_node": "b",
                    "payloads": ["616263"],
                }
            )
        )
    sample = result["observations"][0]
    assert result["status"] == "failed" and sample["timeout"] is True
    assert sample["failure_reason"] == "handshake_timeout"
    assert sample["handshake_ms"] is None
    assert read_qlog(sample["qlog"])["packets_received"] == 0

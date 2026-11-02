"""Network topology, SSH safety and actual bounded worker/relay acceptance."""

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
from pydantic import ValidationError


def node(identifier: str, address: str) -> Node:
    return Node(node_id=identifier, name=identifier, address=address)


def test_inventory_direct_matrix_and_optional_balancer(tmp_path):
    inventory = Inventory(tmp_path)
    for index in range(1, 6):
        inventory.add_node(node(f"n{index}", f"10.10.0.{index}"))
    topology = Topology(name="matrix", clients=["n1", "n2"], servers=["n3", "n4"])
    assert inventory.plan(topology)["edges"] == [
        {"from": "n1", "to": "n3"},
        {"from": "n1", "to": "n4"},
        {"from": "n2", "to": "n3"},
        {"from": "n2", "to": "n4"},
    ]
    balanced = topology.model_copy(update={"load_balancer": "n5"})
    plan = inventory.plan(balanced)
    assert plan["edges"] == [
        {"from": "n1", "to": "n5"},
        {"from": "n2", "to": "n5"},
        {"from": "n5", "to": "n3"},
        {"from": "n5", "to": "n4"},
    ]
    saved = inventory.add_topology(topology)
    assert Inventory(tmp_path).topology(saved["topology_id"]) == topology
    with pytest.raises(cli.CLIError, match="duplicate_node"):
        inventory.add_node(node("another", "10.10.0.1"))
    with pytest.raises(cli.CLIError, match="node_not_found"):
        inventory.plan(topology.model_copy(update={"servers": ["missing"]}))


@pytest.mark.parametrize(
    "directory",
    [
        "/root",
        "/root/phoenix",
        "/",
        "/opt/phoenix",
        "/opt/netspectra-a/../phoenix",
        "/opt/netspectra-a;touch /tmp/x",
    ],
)
def test_existing_project_paths_cannot_be_install_targets(directory):
    with pytest.raises(ValidationError):
        Node(
            node_id="iran", name="Iran", address="87.107.146.217", install_dir=directory
        )


def test_roles_and_ports_are_constrained():
    with pytest.raises(ValidationError):
        Topology(name="bad", clients=["n1"], servers=["n1"])
    with pytest.raises(ValidationError):
        Topology(name="bad", clients=["n1"], servers=["n2"], load_balancer="n1")
    with pytest.raises(ValidationError):
        Topology(name="bad", clients=["n1"], servers=["n2"], port=443)
    with pytest.raises(ValidationError):
        node("bad", "127.0.0.1")


def test_ssh_requires_explicit_host_pin_and_never_uses_password(tmp_path):
    ssh = SSH(tmp_path)
    target = node("iran", "87.107.146.217")
    with pytest.raises(cli.CLIError, match="host_key_required"):
        ssh.command(target, ["python3", "--version"])
    ssh.key.touch()
    pinned = target.model_copy(update={"host_key": "ssh-ed25519 " + "A" * 68})
    command = ssh.command(pinned, ["printf", "$(touch /tmp/nope)"])
    assert "StrictHostKeyChecking=yes" in command
    assert "BatchMode=yes" in command
    assert command[-1] == "printf '$(touch /tmp/nope)'"
    assert "sshpass" not in command


def test_bootstrap_refuses_existing_directory_before_git_operations(
    tmp_path, monkeypatch
):
    captured = {}

    async def execute(target, command, timeout):
        captured["command"] = command
        return {"agent_version": 1}

    ssh = SSH(tmp_path)
    monkeypatch.setattr(ssh, "execute", execute)
    asyncio.run(ssh.bootstrap(node("iran", "87.107.146.217"), "a" * 40))
    script = captured["command"][2]
    assert script.index('test ! -e "$target"') < script.index('mkdir "$target"')
    assert "rm " not in script and "apt" not in script and "systemctl" not in script
    assert "kill" not in script and "iptables" not in script


@pytest.fixture
def workers():
    processes = []

    def start(role, config):
        process = subprocess.Popen(
            [sys.executable, "-m", "pprl_core.remote_agent", role],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
        )
        processes.append(process)
        process.stdin.write(json.dumps(config) + "\n")
        process.stdin.flush()
        with ThreadPoolExecutor(max_workers=1) as executor:
            line = executor.submit(process.stdout.readline).result(timeout=8)
        return process, json.loads(line)

    yield start
    for process in reversed(processes):
        if process.stdin and not process.stdin.closed:
            process.stdin.close()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()


def available_port(host="127.0.0.1"):
    for port in range(28100, 28200):
        with socket.socket() as probe:
            try:
                probe.bind((host, port))
                return port
            except OSError:
                continue
    pytest.skip("no dedicated test port available")


@pytest.mark.parametrize("protocol", ["tcp", "udp"])
def test_worker_actual_round_trip_and_occupied_port_preservation(workers, protocol):
    config = {
        "protocol": protocol,
        "port": available_port(),
        "token": "a" * 40,
        "node_id": "backend",
        "peers": ["127.0.0.1"],
        "bind_address": "127.0.0.1",
    }
    process, ready = workers("server", config)
    assert ready["ready"] is True
    competing, failure = workers("server", config)
    assert failure == {"error": "port_in_use"}
    assert competing.wait(timeout=5) == 1
    sample = remote_agent.client(
        config | {"node_id": "client", "host": "127.0.0.1", "payloads": ["aa55"]}
    )
    assert sample["observations"][0]["backend"] == "backend"
    assert sample["observations"][0]["bytes_echoed"] == 2
    process.stdin.close()
    assert process.wait(timeout=5) == 0


@pytest.mark.parametrize("protocol", ["tcp", "udp"])
def test_relay_forwards_real_traffic_and_round_robins_backends(workers, protocol):
    port = available_port("127.0.0.2")
    common = {
        "protocol": protocol,
        "port": port,
        "token": "b" * 40,
        "peers": ["127.0.0.1"],
    }
    for address, identifier in [("127.0.0.2", "b1"), ("127.0.0.3", "b2")]:
        _, ready = workers(
            "server", common | {"node_id": identifier, "bind_address": address}
        )
        assert ready["ready"]
    _, ready = workers(
        "relay",
        common
        | {
            "node_id": "lb",
            "bind_address": "127.0.0.4",
            "backends": ["127.0.0.2", "127.0.0.3"],
        },
    )
    assert ready["ready"]
    result = remote_agent.client(
        common
        | {
            "node_id": "client",
            "host": "127.0.0.4",
            "payloads": ["11", "22", "33", "44"],
        }
    )
    assert [sample["backend"] for sample in result["observations"]] == [
        "b1",
        "b2",
        "b1",
        "b2",
    ]


def test_network_failure_preserves_partial_observations_and_detects_tamper(
    tmp_path, monkeypatch
):
    inventory = Inventory(tmp_path)
    for identifier, address in [("a", "10.10.0.1"), ("b", "10.10.0.2")]:
        inventory.add_node(
            node(identifier, address).model_copy(
                update={"host_key": "ssh-ed25519 " + "A" * 68}
            )
        )
    topology = inventory.add_topology(
        Topology(name="path", clients=["a"], servers=["b"])
    )
    monkeypatch.setattr(
        cli, "_source_metadata", lambda: {"git_sha": "a" * 40, "dirty": False}
    )

    async def fail(
        transport, plan, definition, payloads, observations, capture_results=None
    ):
        observations.append({"client": "a", "backend": "b", "bytes_echoed": 10})
        raise cli.CLIError("remote_run_failed")

    monkeypatch.setattr(cluster_runner, "execute", fail)
    result = cluster_runner.run(
        tmp_path, inventory, SSH(tmp_path), topology["topology_id"], threading.Event()
    )
    assert result["status"] == "failed" and len(result["observations"]) == 1
    controller = panel.Controller(tmp_path)
    try:
        assert controller.network_record(result["run_id"]) == result
        path = tmp_path / "network-runs" / (result["run_id"] + ".json")
        path.write_text("{}")
        with pytest.raises(cli.CLIError, match="artifact_integrity_failed"):
            controller.network_record(result["run_id"])
        assert controller.state()["network_runs"][0]["status"] == "integrity_error"
    finally:
        controller.close()


def test_cluster_api_authentication_inventory_and_role_validation(tmp_path):
    access = tmp_path / "access.json"
    panel.initialize(tmp_path, access)
    with TestClient(panel.create_app(tmp_path), base_url="http://127.0.0.1") as client:
        headers = {"X-NetSpectra-Client": "panel"}
        record = node("iran", "87.107.146.217").model_dump()
        assert (
            client.post("/api/cluster/nodes", json=record, headers=headers).status_code
            == 401
        )
        assert (
            client.post(
                "/api/login", json=json.loads(access.read_text()), headers=headers
            ).status_code
            == 200
        )
        assert (
            client.post("/api/cluster/nodes", json=record, headers=headers).status_code
            == 201
        )
        assert (
            client.get("/api/state").json()["cluster"]["nodes"][0]["address"]
            == "87.107.146.217"
        )
        assert (
            client.post(
                "/api/cluster/topologies",
                json={"name": "invalid", "clients": ["iran"], "servers": ["iran"]},
                headers=headers,
            ).status_code
            == 422
        )
        assert (
            client.post(
                "/api/cluster/nodes/iran/pin",
                json={"host_key": "invalid"},
                headers=headers,
            ).status_code
            == 422
        )


@pytest.mark.parametrize("protocol", ["tcp", "udp"])
@pytest.mark.parametrize("balanced", [False, True, "shared"])
def test_orchestrator_real_children_direct_and_balanced(tmp_path, protocol, balanced):
    inventory = Inventory(tmp_path)
    for index in range(1, 5):
        inventory.add_node(node(f"n{index}", f"10.10.0.{index}"))
    definition = Topology(
        name="integration",
        clients=["n1"],
        servers=["n1"] if balanced == "shared" else ["n2", "n3"],
        load_balancer="n4" if balanced else None,
        protocol=protocol,
        port=available_port("0.0.0.0"),
    )
    script = """import json,sys
from pprl_core import remote_agent as agent
role=sys.argv[1]
config=json.loads(sys.stdin.buffer.readline())
mapped=lambda value: "127.0.0."+value.rsplit(".",1)[1]
config["bind_address"]=mapped(sys.argv[2])
config["peers"]=["127.0.0.1"]
if "host" in config: config["host"]=mapped(config["host"])
if "backends" in config: config["backends"]=[mapped(v) for v in config["backends"]]
config=agent.validate(config,role)
result=agent.client(config) if role=="client" else agent.serve(config,role=="relay")
print(json.dumps(result),flush=True)
"""

    class LocalTransport:
        async def preflight(self, target):
            return {"agent_version": 1}

        def agent_command(self, target, role):
            return [sys.executable, "-c", script, role, target.address]

    observations = []
    result = asyncio.run(
        cluster_runner.execute(
            LocalTransport(),
            inventory.plan(definition),
            definition.model_dump(),
            [b"aa", b"bb"],
            observations,
        )
    )
    assert len(result) == (2 if balanced else 4)
    expected = {"n1"} if balanced == "shared" else {"n2", "n3"}
    assert {sample["backend"] for sample in result} == expected
    assert all(sample["via"] == ("n4" if balanced else None) for sample in result)


def test_inventory_edit_invalidates_pin_when_ssh_destination_changes(tmp_path):
    inventory = Inventory(tmp_path)
    original = node("iran", "87.107.146.217").model_copy(
        update={"host_key": "ssh-ed25519 " + "A" * 68}
    )
    inventory.add_node(original)
    assert inventory.update_node("iran", original.model_copy(update={"name": "Iran"}))[
        "host_key"
    ]
    assert (
        inventory.update_node("iran", original.model_copy(update={"ssh_port": 9011}))[
            "host_key"
        ]
        == ""
    )


def test_shared_client_backend_role_uses_network_hops_and_excludes_self_pairs(tmp_path):
    inventory = Inventory(tmp_path)
    inventory.add_node(node("iran", "87.107.146.217"))
    inventory.add_node(node("eu", "54.36.113.36"))
    direct = Topology(name="both", clients=["iran", "eu"], servers=["iran", "eu"])
    assert inventory.plan(direct)["edges"] == [
        {"from": "iran", "to": "eu"},
        {"from": "eu", "to": "iran"},
    ]
    balanced = Topology(
        name="relay", clients=["iran"], servers=["iran"], load_balancer="eu"
    )
    assert inventory.plan(balanced)["edges"] == [
        {"from": "iran", "to": "eu"},
        {"from": "eu", "to": "iran"},
    ]


@pytest.mark.skipif(sys.platform == "win32", reason="Linux TCP TIME_WAIT reuse policy")
def test_completed_tcp_run_can_rebind_without_displacing_active_listener(workers):
    config = {
        "protocol": "tcp",
        "port": available_port(),
        "token": "a" * 40,
        "node_id": "backend",
        "peers": ["127.0.0.1"],
        "bind_address": "127.0.0.1",
    }
    for _ in range(2):
        process, ready = workers("server", config)
        assert ready["ready"]
        result = remote_agent.client(
            config | {"node_id": "client", "host": "127.0.0.1", "payloads": ["aa55"]}
        )
        assert result["status"] == "succeeded"
        process.stdin.close()
        assert process.wait(timeout=5) == 0

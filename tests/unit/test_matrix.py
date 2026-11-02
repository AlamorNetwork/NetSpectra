import hashlib
import json
import threading

import pytest
from pprl_core import cli, matrix
from pprl_core.cluster import Inventory, Node
from pprl_core.cluster_ssh import SSH


def inventory_at(root):
    inventory = Inventory(root)
    for index, name in enumerate(("iran", "turkey"), 1):
        inventory.add_node(
            Node(
                node_id=name,
                name=name,
                address=f"192.0.2.{index}",
                host_key="ssh-ed25519 " + "A" * 68,
            )
        )
    return inventory


def test_matrix_is_bounded_bidirectional_and_controlled():
    cases = matrix.cases(["iran", "turkey"])
    assert len(cases) == 10
    assert [(c.protocol, c.clients, c.servers) for c in cases[:2]] == [
        ("tcp", ["iran"], ["turkey"]),
        ("tcp", ["turkey"], ["iran"]),
    ]
    assert all(c.repetitions == 1 and c.controlled_failure for c in cases[-2:])
    with pytest.raises(cli.CLIError, match="two_distinct"):
        matrix.cases(["iran", "iran"])


def test_legacy_samples_do_not_hide_real_failures():
    assert matrix.sample_succeeded({"bytes_echoed": 123})
    assert not matrix.sample_succeeded({"status": "failed", "bytes_echoed": 123})
    assert not matrix.sample_succeeded(
        {"bytes_echoed": 123, "failure_reason": "timeout"}
    )
    assert not matrix.sample_succeeded({})


def test_failed_case_retained_and_timeout_not_certificate_rejection(
    tmp_path, monkeypatch
):
    inventory = inventory_at(tmp_path)
    count = 0

    def run(root, inventory, transport, identifier, cancel):
        nonlocal count
        count += 1
        record = {
            "run_id": f"net-{count}",
            "status": "failed" if count > 1 else "succeeded",
            "failure_reason": "timeout" if count > 1 else None,
            "observations": [{"status": "succeeded"}] if count == 1 else [],
        }
        directory = cli._path(root, "network-runs")
        directory.mkdir(exist_ok=True)
        cli._atomic_write(directory / (record["run_id"] + ".json"), record)
        return record

    monkeypatch.setattr(matrix.cluster_runner, "run", run)
    result = matrix.run_matrix(
        tmp_path,
        inventory,
        SSH(tmp_path),
        matrix.cases(["iran", "turkey"]),
        threading.Event(),
    )
    assert result["status"] == "failed" and count == 10
    assert result["cases"][0]["expected_outcome_observed"]
    assert not result["cases"][-1]["expected_outcome_observed"]
    path = tmp_path / "network-matrices" / (result["matrix_id"] + ".json")
    assert json.loads(path.read_text()) == result
    assert json.loads(path.with_suffix(".sha256").read_text())["sha256"] == (
        hashlib.sha256(path.read_bytes()).hexdigest()
    )


def test_cancelled_matrix_does_not_start_nodes(tmp_path, monkeypatch):
    cancel = threading.Event()
    cancel.set()
    monkeypatch.setattr(matrix.cluster_runner, "run", lambda *_: pytest.fail("started"))
    result = matrix.run_matrix(
        tmp_path,
        inventory_at(tmp_path),
        SSH(tmp_path),
        matrix.cases(["iran", "turkey"]),
        cancel,
    )
    assert result["status"] == "cancelled" and not result["cases"]


def test_per_node_identity_does_not_mutate_default(tmp_path):
    identity = tmp_path / "private"
    identity.touch()
    transport = SSH(tmp_path, {"iran": identity})
    node = inventory_at(tmp_path).node("iran")
    command = transport.command(node, ["python3", "--version"])
    assert command[command.index("-i") + 1] == str(identity)
    assert not transport.key.exists()

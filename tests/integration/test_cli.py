"""Exercise experiment persistence and real loopback runs in temporary stores."""

import asyncio
import hashlib
import json
from pathlib import Path

import pytest
from pprl_core import cli

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(
        cli,
        "_source_metadata",
        lambda: {
            "git_sha": "a" * 40,
            "dirty": False,
        },
    )
    manifest = ROOT / "experiments/templates/loopback.json"
    cli.create(tmp_path, manifest)
    return tmp_path


def test_registry_round_trip_and_no_overwrite(store: Path) -> None:
    items = cli.list_experiments(store)["experiments"]
    assert len(items) == 1
    record = cli.inspect(store, "exp-loopback-demo")
    assert items == [record]
    with pytest.raises(cli.CLIError, match="experiment_exists"):
        cli.create(store, ROOT / "experiments/templates/loopback.json")
    assert cli.inspect(store, "exp-loopback-demo") == record


@pytest.mark.parametrize("protocol", ["tcp", "udp"])
def test_real_run_records_snapshots_and_hashes(store: Path, protocol: str) -> None:
    path = store / "experiments/exp-loopback-demo/experiment.json"
    manifest = json.loads(path.read_text())
    manifest["protocol"] = protocol
    path.write_text(json.dumps(manifest))
    record, code = cli.run(store, "exp-loopback-demo", 5)
    assert code == 0
    assert record["status"] == "succeeded"
    assert record["sample_size"] == 3
    assert record["metrics"][0]["value"] == 78
    assert record["started_at"] <= record["finished_at"]
    assert record["git_sha"] == "a" * 40
    assert cli.inspect(store, record["run_id"]) == record
    for artifact in record["artifacts"]:
        data = (store / "runs" / record["run_id"] / artifact["path"]).read_bytes()
        assert hashlib.sha256(data).hexdigest() == artifact["sha256"]
        assert len(data) == artifact["size_bytes"]
    summary = json.loads(
        (store / "runs" / record["run_id"] / "summary.json").read_text()
    )
    assert summary["scenario"]["network_profile_applied"] is False
    assert all(
        item["results"][0]["protocol"] == protocol for item in summary["observations"]
    )


def test_runs_do_not_overwrite_each_other(store: Path) -> None:
    first, _ = cli.run(store, "exp-loopback-demo", 5)
    second, _ = cli.run(store, "exp-loopback-demo", 5)
    assert first["run_id"] != second["run_id"]
    assert first["run_seed"] == second["run_seed"]
    assert first["metrics"] == second["metrics"]
    assert cli.inspect(store, first["run_id"]) == first


@pytest.mark.parametrize(
    ("error", "reason", "status", "exit_code"),
    [
        (TimeoutError(), "timeout", "failed", 1),
        (OSError("private content"), "loopback_error", "failed", 1),
        (RuntimeError("private content"), "internal_error", "failed", 1),
        (KeyboardInterrupt(), "cancelled", "cancelled", 130),
    ],
)
def test_failed_and_cancelled_runs_are_recorded(
    store: Path,
    monkeypatch: pytest.MonkeyPatch,
    error: BaseException,
    reason: str,
    status: str,
    exit_code: int,
) -> None:
    async def fail(**kwargs):
        raise error

    # Raise the interrupt around asyncio.run so its own signal machinery is not mocked.
    if isinstance(error, KeyboardInterrupt):

        def interrupt(coroutine):
            coroutine.close()
            raise error

        monkeypatch.setattr(cli.asyncio, "run", interrupt)
    else:
        monkeypatch.setattr(cli, "probe_loopback", fail)
    record, code = cli.run(store, "exp-loopback-demo", 5)
    assert code == exit_code
    assert record["status"] == status
    assert record["failure_reason"] == reason
    assert record["sample_size"] == 0
    assert "private content" not in json.dumps(record)
    assert cli.inspect(store, record["run_id"]) == record


def test_batch_timeout_keeps_completed_repetitions(
    store: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = 0

    async def probe(**kwargs):
        nonlocal calls
        calls += 1
        if calls > 1:
            await asyncio.Event().wait()
        return {"results": [{"bytes_echoed": 26}]}

    monkeypatch.setattr(cli, "probe_loopback", probe)
    record, code = cli.run(store, "exp-loopback-demo", 0.05)
    assert code == 1
    assert record["failure_reason"] == "timeout"
    assert record["sample_size"] == 1
    assert record["metrics"][0]["value"] == 26


def test_inspect_detects_artifact_tampering(store: Path) -> None:
    record, _ = cli.run(store, "exp-loopback-demo", 5)
    (store / "runs" / record["run_id"] / "summary.json").write_text("{}")
    with pytest.raises(cli.CLIError, match="artifact_integrity_failed"):
        cli.inspect(store, record["run_id"])


def test_inspect_detects_run_snapshot_mismatch(store: Path) -> None:
    record, _ = cli.run(store, "exp-loopback-demo", 5)
    path = store / "runs" / record["run_id"] / "run.json"
    record["run_seed"] += 1
    path.write_text(json.dumps(record))
    with pytest.raises(cli.CLIError, match="run_snapshot_mismatch"):
        cli.inspect(store, record["run_id"])


@pytest.mark.parametrize(
    "identifier", ["../elsewhere", "exp-../out", "/tmp", "run-a\n"]
)
def test_identifiers_cannot_escape_store(store: Path, identifier: str) -> None:
    with pytest.raises(cli.CLIError, match="invalid_identifier"):
        cli.inspect(store, identifier)


def test_unsupported_scope_rejected_before_probe(
    store: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = store / "experiments/exp-loopback-demo/experiment.json"
    manifest = json.loads(path.read_text())
    manifest["network_profile"]["packet_loss_pct"] = 5
    path.write_text(json.dumps(manifest))
    with pytest.raises(cli.CLIError, match="unsupported_loopback_configuration"):
        cli.run(store, "exp-loopback-demo", 5)
    assert not (store / "runs").exists()


def test_symlinked_store_component_rejected(tmp_path: Path) -> None:
    target = tmp_path / "elsewhere"
    target.mkdir()
    try:
        (tmp_path / "experiments").symlink_to(target, target_is_directory=True)
    except OSError:
        pytest.skip("OS does not allow symlink creation in this session")
    with pytest.raises(cli.CLIError, match="store_symlink_rejected"):
        cli.list_experiments(tmp_path)


@pytest.mark.parametrize("text", ['{"x":1,"x":2}', '{"x":NaN}', "[]"])
def test_strict_json_import(tmp_path: Path, text: str) -> None:
    manifest = tmp_path / "invalid.json"
    manifest.write_text(text)
    with pytest.raises(cli.CLIError):
        cli.create(tmp_path / "data", manifest)
    assert not (tmp_path / "data").exists()


def test_cli_json_interface(store: Path, capsys: pytest.CaptureFixture) -> None:
    assert cli.main(["--data-dir", str(store), "list"]) == 0
    assert len(json.loads(capsys.readouterr().out)["experiments"]) == 1
    assert cli.main(["--data-dir", str(store), "inspect", "../secret"]) == 2
    output = capsys.readouterr()
    assert json.loads(output.err) == {"error": "invalid_identifier"}
    assert output.out == ""

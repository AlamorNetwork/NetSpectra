"""Bounded retries and immutable seeded replay using the actual CLI store."""

import asyncio
import errno
import hashlib
import json
from pathlib import Path

import pytest
from pprl_core import cli
from pprl_core.endpoints import EndpointError

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def seeded_store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(
        cli, "_source_metadata", lambda: {"git_sha": "a" * 40, "dirty": False}
    )
    cli.create(tmp_path, ROOT / "experiments/templates/seeded-tcp.json")
    return tmp_path


def summary(root: Path, record: dict) -> dict:
    return json.loads((root / "runs" / record["run_id"] / "summary.json").read_text())


def test_seeded_replay_uses_immutable_snapshot(seeded_store: Path) -> None:
    first, code = cli.run(seeded_store, "exp-seeded-tcp", 20, attempt_timeout=5)
    assert code == 0
    path = seeded_store / "experiments/exp-seeded-tcp/experiment.json"
    changed = json.loads(path.read_text())
    changed["run_seed"] = 999
    path.write_text(json.dumps(changed))
    second, code = cli.replay(seeded_store, first["run_id"])
    assert code == 0
    assert first["run_id"] != second["run_id"]
    assert first["run_seed"] == second["run_seed"] == 42
    assert first["metrics"] == second["metrics"]
    a, b = summary(seeded_store, first), summary(seeded_store, second)
    assert a["workload"] == b["workload"]
    assert a["workload_sha256"] == b["workload_sha256"]
    assert b["replay_of"] == first["run_id"]
    assert len(a["attempts"]) == 3
    assert all(item["client_pid"] != item["server_pid"] for item in a["observations"])
    assert cli.inspect(seeded_store, second["run_id"]) == second


@pytest.mark.parametrize("permanent", [False, True])
def test_only_transient_failures_are_retried(
    seeded_store: Path,
    monkeypatch: pytest.MonkeyPatch,
    permanent: bool,
) -> None:
    calls = 0

    async def probe(protocol, payload, timeout):
        nonlocal calls
        calls += 1
        if permanent:
            raise EndpointError("payload_mismatch")
        if calls == 1:
            raise OSError(errno.ECONNRESET, "private detail")
        return {"results": [{"bytes_echoed": len(payload)}]}

    monkeypatch.setattr(cli, "probe_process_pair", probe)
    record, code = cli.run(seeded_store, "exp-seeded-tcp", 5, retries=2, retry_delay=0)
    if permanent:
        assert code == 1
        assert calls == 1
        assert record["failure_reason"] == "payload_mismatch"
    else:
        assert code == 0
        assert calls == 4  # three successful samples plus the first failed attempt
        assert record["sample_size"] == 3
    evidence = summary(seeded_store, record)
    assert evidence["attempts"][0]["status"] == "failed"
    assert "private detail" not in json.dumps(evidence)


def test_retry_limit_is_enforced(seeded_store: Path, monkeypatch: pytest.MonkeyPatch):
    async def fail(*args):
        raise EndpointError("endpoint_transient_error")

    monkeypatch.setattr(cli, "probe_process_pair", fail)
    record, code = cli.run(seeded_store, "exp-seeded-tcp", 5, retries=2, retry_delay=0)
    assert code == 1
    assert len(summary(seeded_store, record)["attempts"]) == 3
    assert record["sample_size"] == 0


def test_attempt_timeout_can_retry_within_total_budget(
    seeded_store: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = 0

    async def probe(protocol, payload, timeout):
        nonlocal calls
        calls += 1
        if calls == 1:
            await asyncio.Event().wait()
        return {"results": [{"bytes_echoed": len(payload)}]}

    monkeypatch.setattr(cli, "probe_process_pair", probe)
    record, code = cli.run(
        seeded_store,
        "exp-seeded-tcp",
        5,
        retries=1,
        attempt_timeout=0.05,
        retry_delay=0,
    )
    assert code == 0
    assert calls == 4
    assert summary(seeded_store, record)["attempts"][0]["reason"] == "timeout"


def test_global_deadline_includes_retry_backoff(
    seeded_store: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fail(*args):
        raise TimeoutError()

    monkeypatch.setattr(cli, "probe_process_pair", fail)
    record, code = cli.run(
        seeded_store, "exp-seeded-tcp", 0.05, retries=2, retry_delay=1
    )
    assert code == 1
    assert record["failure_reason"] == "timeout"
    assert len(summary(seeded_store, record)["attempts"]) == 1


def test_replay_rejects_changed_workload(seeded_store: Path) -> None:
    record, code = cli.run(seeded_store, "exp-seeded-tcp", 20, attempt_timeout=5)
    assert code == 0
    directory = seeded_store / "runs" / record["run_id"]
    saved = summary(seeded_store, record)
    saved["workload"]["samples"][0]["size_bytes"] += 1
    data = cli._json_bytes(saved)
    (directory / "summary.json").write_bytes(data)
    entry = next(item for item in record["artifacts"] if item["path"] == "summary.json")
    entry.update(sha256=hashlib.sha256(data).hexdigest(), size_bytes=len(data))
    (directory / "run.json").write_bytes(cli._json_bytes(record))
    with pytest.raises(cli.CLIError, match="replay_definition_mismatch"):
        cli.replay(seeded_store, record["run_id"])


@pytest.mark.parametrize("retries", [-1, 3, True, 0.5])
def test_invalid_retry_policy_starts_no_run(seeded_store: Path, retries):
    with pytest.raises(cli.CLIError, match="invalid_retry_policy"):
        cli.run(seeded_store, "exp-seeded-tcp", 5, retries=retries)
    assert not (seeded_store / "runs").exists()

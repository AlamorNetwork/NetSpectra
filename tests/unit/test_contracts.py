"""Contract acceptance tests; validation is local and performs no measurements."""

import copy
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry

SCHEMAS = Path(__file__).resolve().parents[2] / "schemas"


def load(relative: str) -> dict:
    return json.loads((SCHEMAS / relative).read_text(encoding="utf-8"))


def validator(kind: str) -> Draft202012Validator:
    return Draft202012Validator(
        load(f"{kind}.schema.json"),
        format_checker=FormatChecker(),
        registry=Registry(),
    )


def test_timestamp_format_checker_is_installed() -> None:
    assert "date-time" in FormatChecker().checkers


@pytest.mark.parametrize("kind", ["experiment", "run"])
def test_schema_is_valid(kind: str) -> None:
    Draft202012Validator.check_schema(load(f"{kind}.schema.json"))


@pytest.mark.parametrize(
    "path", sorted((SCHEMAS / "examples/valid").glob("*.json")), ids=lambda p: p.stem
)
def test_valid_examples(path: Path) -> None:
    kind = "experiment" if path.stem == "experiment" else "run"
    validator(kind).validate(json.loads(path.read_text(encoding="utf-8")))


@pytest.mark.parametrize(
    "path", sorted((SCHEMAS / "examples/invalid").glob("*.json")), ids=lambda p: p.stem
)
def test_invalid_examples(path: Path) -> None:
    kind = "experiment" if path.stem.startswith("experiment") else "run"
    assert not validator(kind).is_valid(json.loads(path.read_text(encoding="utf-8")))


@pytest.mark.parametrize("kind", ["experiment", "run"])
def test_each_required_field_is_enforced(kind: str) -> None:
    filename = "experiment" if kind == "experiment" else "run-succeeded"
    record = load(f"examples/valid/{filename}.json")
    for field in load(f"{kind}.schema.json")["required"]:
        incomplete = copy.deepcopy(record)
        del incomplete[field]
        assert not validator(kind).is_valid(incomplete), field


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("schema_version", "0.2.0"),
        ("experiment_id", "exp-0001\n"),
        ("scenario", "../external"),
        ("scenario_version", 0),
        ("run_seed", -1),
        ("run_seed", 4294967296),
        ("run_seed", True),
        ("repetitions", 0),
        ("repetitions", 1.5),
        ("lab_mode", "public"),
        ("consent_scope", "real_users"),
        ("protocol", "unknown"),
        ("unexpected", "reject me"),
    ],
)
def test_experiment_rejects_invalid_values(field: str, value: object) -> None:
    record = load("examples/valid/experiment.json")
    record[field] = value
    assert not validator("experiment").is_valid(record)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("latency_ms", -1),
        ("packet_loss_pct", -0.1),
        ("packet_loss_pct", 100.1),
        ("bandwidth_mbps", 0),
        ("jitter_ms", -1),
        ("unknown", 1),
    ],
)
def test_network_profile_bounds(field: str, value: object) -> None:
    record = load("examples/valid/experiment.json")
    record["network_profile"][field] = value
    assert not validator("experiment").is_valid(record)


def test_experiment_boundaries_and_explicit_raw_retention() -> None:
    record = load("examples/valid/experiment.json")
    record.update(run_seed=4294967295, repetitions=1)
    record["network_profile"].update(latency_ms=0, packet_loss_pct=100, jitter_ms=0)
    record["artifacts"]["retain_raw_pcap"] = True
    validator("experiment").validate(record)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("schema_version", "0.2.0"),
        ("run_id", "run-0001\n"),
        ("git_sha", "main"),
        ("git_sha", "b" * 40 + "\n"),
        ("scenario_sha256", "a" * 63),
        ("scenario_sha256", "a" * 64 + "\n"),
        ("status", "running"),
        ("sample_size", -1),
        ("sample_size", True),
        ("started_at", "2026-10-31T08:00:00+03:30"),
        ("started_at", "2026-02-30T08:00:00Z"),
        ("finished_at", "2026-10-31"),
        ("finished_at", "2026-10-31T08:00:00Z\n"),
        ("tool_versions", {}),
        ("tool_versions", {"pprl": " "}),
        ("failure_reason", "success cannot have a failure reason"),
        ("unexpected", "reject me"),
    ],
)
def test_run_rejects_invalid_values(field: str, value: object) -> None:
    record = load("examples/valid/run-succeeded.json")
    record[field] = value
    assert not validator("run").is_valid(record)


@pytest.mark.parametrize("status", ["failed", "cancelled"])
@pytest.mark.parametrize("reason", [None, "", " \n\t"])
def test_unsuccessful_runs_require_reason(status: str, reason: object) -> None:
    record = load("examples/valid/run-succeeded.json")
    record.update(status=status, failure_reason=reason)
    assert not validator("run").is_valid(record)


@pytest.mark.parametrize(
    "path",
    [
        "/tmp/out",
        "../out",
        "logs/../out",
        "logs/./out",
        "C:/out",
        "logs\\out",
        "logs//out",
        "logs/out\n",
        "",
    ],
)
def test_artifact_paths_stay_relative(path: str) -> None:
    record = load("examples/valid/run-succeeded.json")
    record["artifacts"][0]["path"] = path
    assert not validator("run").is_valid(record)


@pytest.mark.parametrize(
    ("field", "value"),
    [("sha256", "not-a-hash"), ("size_bytes", -1), ("payload", "private")],
)
def test_artifact_metadata(field: str, value: object) -> None:
    record = load("examples/valid/run-succeeded.json")
    record["artifacts"][0][field] = value
    assert not validator("run").is_valid(record)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("value", None),
        ("value", True),
        ("result_class", "hypothesis"),
        ("result_class", "unknown"),
        ("unit", ""),
        ("extra", "private"),
    ],
)
def test_metrics_require_quantitative_evidence(field: str, value: object) -> None:
    record = load("examples/valid/run-succeeded.json")
    record["metrics"][0][field] = value
    assert not validator("run").is_valid(record)

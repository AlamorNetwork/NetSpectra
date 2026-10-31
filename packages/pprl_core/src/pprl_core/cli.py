"""Local experiment registry and bounded loopback runner."""

import argparse
import asyncio
import hashlib
import json
import math
import os
import platform
import re
import subprocess
import sys
import tempfile
import uuid
from datetime import UTC, datetime
from importlib import metadata, resources
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import ValidationError
from referencing import Registry

from pprl_core.loopback import PAYLOAD, probe_loopback

MAX_JSON_BYTES = 1024 * 1024
SCENARIO = {
    "name": "loopback_echo",
    "version": 1,
    "address": "127.0.0.1",
    "payload_hex": PAYLOAD.hex(),
    "network_profile_applied": False,
}


class CLIError(Exception):
    """Safe error category; never include raw payloads or exception messages."""


def _json_bytes(value: object) -> bytes:
    return (
        json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n"
    ).encode()


def _reject_constant(value: str) -> None:
    raise CLIError("invalid_json")


def _unique_pairs(pairs: list) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise CLIError("duplicate_json_field")
        result[key] = value
    return result


def _read(path: Path) -> dict:
    with path.open("rb") as source:
        data = source.read(MAX_JSON_BYTES + 1)
    if len(data) > MAX_JSON_BYTES:
        raise CLIError("json_too_large")
    try:
        result = json.loads(
            data, parse_constant=_reject_constant, object_pairs_hook=_unique_pairs
        )
    except (ValueError, UnicodeError, RecursionError) as error:
        raise CLIError("invalid_json") from error
    if not isinstance(result, dict):
        raise CLIError("json_object_required")
    return result


def _schema(kind: str) -> dict:
    packaged = resources.files("pprl_core").joinpath("schemas", f"{kind}.schema.json")
    if packaged.is_file():
        return json.loads(packaged.read_text(encoding="utf-8"))
    # Editable installs map the package source; wheel force-includes live elsewhere.
    return _read(
        Path(__file__).resolve().parents[4] / "schemas" / f"{kind}.schema.json"
    )


def _validate(record: dict, kind: str) -> None:
    checker = FormatChecker()
    if "date-time" not in checker.checkers:
        raise CLIError("timestamp_validator_missing")
    try:
        Draft202012Validator(
            _schema(kind), format_checker=checker, registry=Registry()
        ).validate(record)
    except (ValidationError, RecursionError) as error:
        raise CLIError(f"invalid_{kind}") from error


def _path(root: Path, *parts: str) -> Path:
    """Reject symlink components before touching the local single-user store."""
    current = root
    for part in parts:
        if not re.fullmatch(r"[A-Za-z0-9_.-]+", part) or part in {".", ".."}:
            raise CLIError("invalid_identifier")
        current = current / part
        if current.is_symlink():
            raise CLIError("store_symlink_rejected")
    return current


def _atomic_write(path: Path, value: dict) -> dict:
    data = _json_bytes(value)
    descriptor, temporary = tempfile.mkstemp(prefix=".pending-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)
    return {
        "path": path.name,
        "sha256": hashlib.sha256(data).hexdigest(),
        "size_bytes": len(data),
    }


def create(root: Path, manifest: Path) -> dict:
    record = _read(manifest)
    _validate(record, "experiment")
    directory = _path(root, "experiments", record["experiment_id"])
    directory.parent.mkdir(parents=True, exist_ok=True)
    try:
        directory.mkdir()
    except FileExistsError as error:
        raise CLIError("experiment_exists") from error
    _atomic_write(directory / "experiment.json", record)
    return {"experiment_id": record["experiment_id"], "status": "created"}


def inspect(root: Path, identifier: str) -> dict:
    if re.fullmatch(r"exp-[A-Za-z0-9][A-Za-z0-9_-]{0,63}", identifier):
        record = _read(_path(root, "experiments", identifier, "experiment.json"))
        _validate(record, "experiment")
    elif re.fullmatch(r"run-[A-Za-z0-9][A-Za-z0-9_-]{0,63}", identifier):
        record = _read(_path(root, "runs", identifier, "run.json"))
        _validate(record, "run")
        directory = _path(root, "runs", identifier)
        names = [item["path"] for item in record["artifacts"]]
        if sorted(names) != ["experiment.json", "summary.json"]:
            raise CLIError("invalid_artifact_manifest")
        for artifact in record["artifacts"]:
            # This runner emits flat JSON artifacts only, even if a schema permits more.
            path = _path(directory, artifact["path"])
            data = path.read_bytes()
            if (
                hashlib.sha256(data).hexdigest() != artifact["sha256"]
                or len(data) != artifact["size_bytes"]
            ):
                raise CLIError("artifact_integrity_failed")
        snapshot = _read(_path(directory, "experiment.json"))
        _validate(snapshot, "experiment")
        summary = _read(_path(directory, "summary.json"))
        if (
            any(
                record[field] != snapshot[field]
                for field in (
                    "experiment_id",
                    "run_seed",
                    "scenario_version",
                )
            )
            or record["scenario_sha256"]
            != hashlib.sha256(_json_bytes(summary.get("scenario"))).hexdigest()
        ):
            raise CLIError("run_snapshot_mismatch")
    else:
        raise CLIError("invalid_identifier")
    if record.get("run_id", record.get("experiment_id")) != identifier:
        raise CLIError("record_identity_mismatch")
    return record


def list_experiments(root: Path) -> dict:
    directory = _path(root, "experiments")
    if not directory.exists():
        return {"experiments": []}
    return {
        "experiments": [
            inspect(root, entry.name)
            for entry in sorted(directory.iterdir())
            if entry.is_dir() or entry.is_symlink()
        ]
    }


def _source_metadata() -> dict:
    source = Path(__file__).resolve().parent
    try:
        checkout = Path(
            subprocess.run(
                ["git", "-C", str(source), "rev-parse", "--show-toplevel"],
                check=True,
                capture_output=True,
                text=True,
                timeout=5,
            ).stdout.strip()
        )
        expected = checkout / "packages/pprl_core/src/pprl_core"
        if expected.resolve() != source:
            raise CLIError("source_checkout_required_for_run")
        revision = subprocess.run(
            ["git", "-C", str(source), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        ).stdout.strip()
        dirty = subprocess.run(
            ["git", "-C", str(source), "status", "--porcelain"],
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        ).stdout
    except (OSError, subprocess.SubprocessError) as error:
        raise CLIError("source_revision_unavailable") from error
    if not re.fullmatch(r"[a-f0-9]{40}|[a-f0-9]{64}", revision):
        raise CLIError("source_revision_unavailable")
    return {"git_sha": revision, "dirty": bool(dirty)}


def _check_executable(experiment: dict) -> None:
    profile = experiment["network_profile"]
    if (
        experiment["scenario"] != "loopback_echo"
        or experiment["scenario_version"] != 1
        or experiment["protocol"] not in {"tcp", "udp"}
        or experiment["repetitions"] > 10
        or profile["latency_ms"] != 0
        or profile["packet_loss_pct"] != 0
        or profile.get("jitter_ms", 0) != 0
        or profile["bandwidth_mbps"] != 100
        or any(experiment["artifacts"].values())
    ):
        raise CLIError("unsupported_loopback_configuration")


def _now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def run(root: Path, identifier: str, timeout: float) -> tuple[dict, int]:
    if not math.isfinite(timeout) or not 0 < timeout <= 30:
        raise CLIError("invalid_timeout")
    experiment = inspect(root, identifier)
    _validate(experiment, "experiment")
    _check_executable(experiment)
    source = _source_metadata()
    run_id = f"run-{uuid.uuid4().hex}"
    directory = _path(root, "runs", run_id)
    directory.parent.mkdir(parents=True, exist_ok=True)
    directory.mkdir()
    record = {
        "schema_version": "0.1.0",
        "run_id": run_id,
        "experiment_id": identifier,
        "scenario_version": 1,
        "scenario_sha256": hashlib.sha256(_json_bytes(SCENARIO)).hexdigest(),
        "run_seed": experiment["run_seed"],
        "started_at": _now(),
        "platform": {
            "os": platform.system(),
            "architecture": platform.machine(),
            "python": platform.python_version(),
        },
        "git_sha": source["git_sha"],
        "tool_versions": {"pprl": metadata.version("pprl")},
        "status": "succeeded",
        "metrics": [],
        "sample_size": 0,
        "failure_reason": None,
        "artifacts": [],
    }
    observations = []

    async def execute() -> None:
        async with asyncio.timeout(timeout):
            for _ in range(experiment["repetitions"]):
                observations.append(
                    await probe_loopback(
                        timeout=timeout, protocols=(experiment["protocol"],)
                    )
                )

    exit_code = 0
    try:
        asyncio.run(execute())
    except KeyboardInterrupt:
        record.update(status="cancelled", failure_reason="cancelled")
        exit_code = 130
    except TimeoutError:
        record.update(status="failed", failure_reason="timeout")
        exit_code = 1
    except (OSError, ValueError):
        record.update(status="failed", failure_reason="loopback_error")
        exit_code = 1
    except Exception:
        record.update(status="failed", failure_reason="internal_error")
        exit_code = 1
    record["finished_at"] = _now()
    record["sample_size"] = len(observations)
    record["metrics"] = (
        [
            {
                "name": "bytes_echoed",
                "value": sum(
                    result["bytes_echoed"]
                    for item in observations
                    for result in item["results"]
                ),
                "unit": "bytes",
                "result_class": "observed",
            }
        ]
        if observations
        else []
    )
    record["artifacts"] = [
        _atomic_write(directory / "experiment.json", experiment),
        _atomic_write(
            directory / "summary.json",
            {
                "scenario": SCENARIO,
                "source": source,
                "observations": observations,
                "note": "bandwidth_mbps is a nominal label, not applied or measured",
            },
        ),
    ]
    _validate(record, "run")
    _atomic_write(directory / "run.json", record)
    return record, exit_code


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=Path("artifacts/cli"))
    commands = parser.add_subparsers(dest="command", required=True)
    create_parser = commands.add_parser("create", help="Import an Experiment JSON")
    create_parser.add_argument("manifest", type=Path)
    commands.add_parser("list", help="List registered experiments")
    inspect_parser = commands.add_parser("inspect", help="Inspect an experiment or run")
    inspect_parser.add_argument("identifier")
    run_parser = commands.add_parser("run", help="Run the fixed loopback scenario")
    run_parser.add_argument("identifier")
    run_parser.add_argument("--timeout", type=float, default=5.0)
    args = parser.parse_args(argv)
    try:
        root = args.data_dir.resolve()
        exit_code = 0
        match args.command:
            case "create":
                result = create(root, args.manifest)
            case "list":
                result = list_experiments(root)
            case "inspect":
                result = inspect(root, args.identifier)
            case "run":
                result, exit_code = run(root, args.identifier, args.timeout)
        print(json.dumps(result, sort_keys=True, allow_nan=False))
        return exit_code
    except CLIError as error:
        print(json.dumps({"error": str(error)}), file=sys.stderr)
        return 2
    except OSError:
        print(json.dumps({"error": "storage_or_io_error"}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

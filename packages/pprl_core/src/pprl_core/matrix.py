"""Bounded, sequential, two-node transport comparisons with immutable run evidence."""

import argparse
import hashlib
import json
import signal
import threading
import uuid
from pathlib import Path

from pprl_core import cli, cluster_runner
from pprl_core.cluster import Inventory, Topology
from pprl_core.cluster_ssh import SSH


def sample_succeeded(sample: dict) -> bool:
    if "status" in sample:
        return sample["status"] == "succeeded"
    # Agent v1 TCP/UDP observations predate the explicit status field.
    return sample.get("bytes_echoed", 0) > 0 and not sample.get("failure_reason")


def cases(
    nodes: list[str],
    port: int = 28080,
    repetitions: int = 3,
    seed: int = 42,
    capture: bool = False,
) -> list[Topology]:
    if len(nodes) != 2 or len(set(nodes)) != 2:
        raise cli.CLIError("matrix_requires_two_distinct_nodes")
    result = []
    for protocol in ("tcp", "udp", "tls", "h3"):
        for source, target in (nodes, nodes[::-1]):
            result.append(
                Topology(
                    name=f"Matrix {protocol} {source} to {target}",
                    clients=[source],
                    servers=[target],
                    protocol=protocol,
                    port=port,
                    repetitions=repetitions,
                    run_seed=seed,
                    capture=capture,
                )
            )
    for source, target in (nodes, nodes[::-1]):
        result.append(
            Topology(
                name=f"Matrix TLS certificate rejection {source} to {target}",
                clients=[source],
                servers=[target],
                protocol="tls",
                port=port,
                repetitions=1,
                run_seed=seed,
                capture=capture,
                controlled_failure=True,
            )
        )
    return result


def run_matrix(
    root: Path,
    inventory: Inventory,
    transport: SSH,
    definitions: list[Topology],
    cancel: threading.Event,
) -> dict:
    # Validate every destination before the first remote operation or mutation.
    for definition in definitions:
        if inventory.plan(definition)["missing_host_keys"]:
            raise cli.CLIError("host_key_required")
    identifier = "matrix-" + uuid.uuid4().hex
    folder = cli._path(root, "network-matrices")
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / (identifier + ".json")
    summary = {
        "schema_version": "1.0.0",
        "matrix_id": identifier,
        "started_at": cli._now(),
        "finished_at": None,
        "status": "running",
        "planned_cases": len(definitions),
        "cases": [],
        "source": cli._source_metadata(),
        "limitations": [
            "Small synthetic echo samples are not throughput measurements.",
            "A timeout does not identify a filtering mechanism or device.",
            "Controlled rejection counts only explicit certificate failures.",
        ],
    }

    def save():
        cli._atomic_write(path, summary)
        cli._atomic_write(
            path.with_suffix(".sha256"),
            {
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            },
        )

    save()
    for definition in definitions:
        if cancel.is_set():
            break
        topology = inventory.add_topology(definition)
        record = cluster_runner.run(
            root,
            inventory,
            transport,
            topology["topology_id"],
            cancel,
        )
        reason = record.get("failure_reason")
        controlled = definition.controlled_failure
        expected = (
            (
                record["status"] == "failed"
                and reason == "certificate_verification_failed"
                and any(
                    s.get("expected_certificate_rejection")
                    for s in record["observations"]
                )
            )
            if controlled
            else record["status"] == "succeeded"
        )
        summary["cases"].append(
            {
                "protocol": definition.protocol,
                "source": definition.clients[0],
                "target": definition.servers[0],
                "port": definition.port,
                "controlled_failure": controlled,
                "run_id": record["run_id"],
                "status": record["status"],
                "failure_reason": reason,
                "expected_outcome_observed": expected,
                "successful_samples": sum(
                    sample_succeeded(s) for s in record["observations"]
                ),
                "sample_count": len(record["observations"]),
                "run_sha256": hashlib.sha256(
                    cli._path(
                        root,
                        "network-runs",
                        record["run_id"] + ".json",
                    ).read_bytes()
                ).hexdigest(),
            }
        )
        save()
    complete = len(summary["cases"]) == len(definitions)
    summary["status"] = (
        "cancelled"
        if cancel.is_set()
        else "succeeded"
        if complete
        and all(case["expected_outcome_observed"] for case in summary["cases"])
        else "failed"
    )
    summary["finished_at"] = cli._now()
    save()
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", required=True, type=Path)
    parser.add_argument("--nodes", nargs=2, required=True)
    parser.add_argument("--port", type=int, default=28080)
    parser.add_argument("--repetitions", type=int, default=3)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--capture", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--identity", action="append", default=[], metavar="NODE=PATH")
    args = parser.parse_args()
    inventory = Inventory(args.data_dir)
    definitions = cases(
        args.nodes, args.port, args.repetitions, args.seed, args.capture
    )
    plans = [inventory.plan(case) for case in definitions]
    if args.dry_run:
        print(
            json.dumps(
                {"cases": [case.model_dump() for case in definitions], "plans": plans},
                indent=2,
            )
        )
        return 0
    identities = {}
    for item in args.identity:
        node, separator, filename = item.partition("=")
        if not separator or node not in args.nodes or node in identities:
            parser.error("identity must be a unique selected NODE=PATH")
        identity = Path(filename).expanduser().resolve()
        if not identity.is_file():
            parser.error("identity file is unavailable")
        identities[node] = identity
    cancel = threading.Event()
    previous = signal.signal(signal.SIGINT, lambda *_: cancel.set())
    try:
        result = run_matrix(
            args.data_dir,
            inventory,
            SSH(args.data_dir, identities),
            definitions,
            cancel,
        )
    finally:
        signal.signal(signal.SIGINT, previous)
    print(json.dumps(result, indent=2))
    return 0 if result["status"] == "succeeded" else 1


if __name__ == "__main__":
    raise SystemExit(main())

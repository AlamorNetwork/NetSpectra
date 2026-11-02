"""Short-lived agents over SSH; data flows between selected nodes, never via SSH."""

import asyncio
import base64
import contextlib
import hashlib
import json
import math
import secrets
import threading
import uuid
from pathlib import Path

from pprl_core import cli
from pprl_core.capture import flows_csv, redact_log, sanitize_pcap
from pprl_core.cluster import Inventory
from pprl_core.cluster_ssh import SSH
from pprl_core.qlog import read_qlog
from pprl_core.workload import seeded_payload


async def execute(
    transport: SSH,
    plan: dict,
    definition: dict,
    payloads: list[bytes],
    observations: list[dict],
    capture_results: list[dict] | None = None,
) -> list[dict]:
    nodes = {node["node_id"]: transport_node(node) for node in plan["nodes"]}
    processes = []
    captures = []
    certificates = {}
    capture_nodes = list(
        dict.fromkeys(
            definition["servers"]
            + ([definition["load_balancer"]] if definition["load_balancer"] else [])
            + (definition["clients"] if definition["protocol"] in {"tls", "h3"} else [])
        )
    )
    token = secrets.token_urlsafe(32)
    shared = {
        "token": token,
        "protocol": definition["protocol"],
        "port": definition["port"],
    }

    async def launch(identifier: str, role: str, extra: dict):
        process = await asyncio.create_subprocess_exec(
            *transport.agent_command(nodes[identifier], role),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
            limit=65536,
        )
        processes.append(process)
        process.stdin.write(
            (json.dumps(shared | {"node_id": identifier} | extra) + "\n").encode()
        )
        await process.stdin.drain()
        if role != "client":
            response = json.loads(await asyncio.wait_for(process.stdout.readline(), 12))
            if not response.get("ready"):
                raise cli.CLIError(response.get("error", "agent_not_ready"))
            if role == "server" and definition["protocol"] in {"tls", "h3"}:
                certificates[identifier] = response["certificate"]
        return process

    try:
        for node in nodes.values():
            checked = await transport.preflight(node)
            plan.setdefault("agent_reports", {})[node.node_id] = checked
            if checked.get("agent_version") not in {1, 2, 3}:
                raise cli.CLIError("agent_version_mismatch")
            if definition["protocol"] not in checked.get("protocols", ["tcp", "udp"]):
                raise cli.CLIError("protocol_dependency_unavailable")
            if (
                definition.get("capture")
                and node.node_id in capture_nodes
                and not checked.get("capture_available")
            ):
                raise cli.CLIError("capture_tool_unavailable")
        lb = definition["load_balancer"]
        peers = (
            [nodes[lb].address]
            if lb
            else [nodes[n].address for n in definition["clients"]]
        )
        for server in definition["servers"]:
            await launch(
                server,
                "server",
                {"peers": peers, "public_address": nodes[server].address},
            )
        if lb:
            await launch(
                lb,
                "relay",
                {
                    "peers": [nodes[n].address for n in definition["clients"]],
                    "backends": [nodes[n].address for n in definition["servers"]],
                },
            )
        if definition.get("capture"):
            address_map = {
                node.address: f"198.18.0.{index + 1}"
                for index, node in enumerate(nodes.values())
            }
            for identifier in capture_nodes:
                pairs = [
                    [nodes[edge["from"]].address, nodes[edge["to"]].address]
                    for edge in plan["edges"]
                    if identifier in {edge["from"], edge["to"]}
                ]
                if not pairs:
                    continue
                capture = await launch(
                    identifier,
                    "capture",
                    {
                        "pairs": pairs,
                        "address_map": address_map,
                        "protocol": "udp"
                        if definition["protocol"] == "h3"
                        else "tcp"
                        if definition["protocol"] == "tls"
                        else definition["protocol"],
                    },
                )
                captures.append((identifier, capture))
        for client in definition["clients"]:
            targets = [lb] if lb else definition["servers"]
            for target in targets:
                if target == client:
                    continue
                process = await launch(
                    client,
                    "client",
                    {
                        "host": nodes[target].address,
                        "payloads": [payload.hex() for payload in payloads],
                        **(
                            {
                                "certificate": certificates[target],
                                "target_node": target,
                                "controlled_failure": definition.get(
                                    "controlled_failure", False
                                ),
                            }
                            if definition["protocol"] in {"tls", "h3"}
                            else {}
                        ),
                    },
                )
                output, _ = await asyncio.wait_for(process.communicate(), 35)
                result = json.loads(output)
                if process.returncode or "observations" not in result:
                    raise cli.CLIError(result.get("error", "remote_run_failed"))
                samples = result["observations"]
                if not isinstance(samples, list) or not 1 <= len(samples) <= len(
                    payloads
                ):
                    raise cli.CLIError("invalid_remote_observation")
                if (
                    len(samples) != len(payloads)
                    and result.get("status") == "succeeded"
                ):
                    raise cli.CLIError("incomplete_remote_samples")
                for sample, payload in zip(samples, payloads, strict=False):
                    if definition["protocol"] in {"tls", "h3"}:
                        if sample.get("status") not in {"succeeded", "failed"}:
                            raise cli.CLIError("invalid_remote_observation")
                        for field in ["rtt_ms", "handshake_ms", "request_ms"]:
                            value = sample.get(field)
                            if (
                                value is None
                                and field != "rtt_ms"
                                and sample["status"] == "failed"
                            ):
                                continue
                            if (
                                type(value) not in {float, int}
                                or not math.isfinite(value)
                                or not 0 <= value <= 60000
                            ):
                                raise cli.CLIError("invalid_remote_observation")
                        if definition["protocol"] == "h3" and "qlog" not in sample:
                            raise cli.CLIError("qlog_missing")
                    if (
                        sample["backend"] not in definition["servers"]
                        or (not lb and sample["backend"] != target)
                        or sample["client"] != client
                        or sample["bytes_echoed"]
                        != (0 if sample.get("status") == "failed" else len(payload))
                        or sample["payload_sha256"]
                        != hashlib.sha256(payload).hexdigest()
                    ):
                        raise cli.CLIError("invalid_remote_observation")
                    sample["via"] = lb
                observations.extend(samples)
                if result.get("status") != "succeeded":
                    raise cli.CLIError(result.get("error", "remote_run_failed"))
        return observations
    finally:
        for identifier, capture in captures:
            if capture.stdin:
                capture.stdin.close()
            try:
                output, _ = await asyncio.wait_for(capture.communicate(), 5)
                result = json.loads(output)
                if (
                    capture.returncode
                    or not isinstance(result, dict)
                    or "pcap_base64" not in result
                ):
                    raise cli.CLIError("capture_failed")
                result["node_id"] = identifier
                if capture_results is not None:
                    capture_results.append(result)
            except (ValueError, OSError, TimeoutError, TypeError, cli.CLIError):
                if capture_results is not None:
                    capture_results.append(
                        {"node_id": identifier, "error": "capture_failed"}
                    )
        for process in reversed(processes):
            if process.stdin:
                process.stdin.close()
            if process.returncode is None:
                try:
                    await asyncio.wait_for(process.wait(), 4)
                except TimeoutError:
                    process.kill()
                    await process.wait()


def transport_node(record: dict):
    from pprl_core.cluster import Node

    return Node.model_validate(record)


def run(
    root: Path,
    inventory: Inventory,
    transport: SSH,
    identifier: str,
    cancel: threading.Event,
    capture_override: bool | None = None,
) -> dict:
    topology = inventory.topology(identifier)
    plan = inventory.plan(topology)
    if plan["missing_host_keys"]:
        raise cli.CLIError("host_key_required")
    definition = topology.model_dump()
    if capture_override is not None:
        definition["capture"] = capture_override
    payloads = [
        seeded_payload(topology.run_seed, index)
        for index in range(topology.repetitions)
    ]
    record = {
        "schema_version": "1.0.0",
        "run_id": "net-" + uuid.uuid4().hex,
        "scope": "selected_owned_nodes",
        "topology_id": identifier,
        "topology": definition,
        "plan": plan,
        "started_at": cli._now(),
        "source": cli._source_metadata(),
        "status": "running",
        "observations": [],
        "workload_sha256": hashlib.sha256(b"".join(payloads)).hexdigest(),
        "failure_reason": None,
        "captures": [],
        "qlogs": [],
    }

    async def perform():
        async with asyncio.timeout(60):
            task = asyncio.create_task(
                execute(
                    transport,
                    plan,
                    definition,
                    payloads,
                    record["observations"],
                    record["captures"],
                )
            )
            try:
                while not task.done():
                    if cancel.is_set():
                        raise asyncio.CancelledError
                    await asyncio.sleep(0.05)
                return await task
            finally:
                if not task.done():
                    task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task

    try:
        record["observations"] = asyncio.run(perform())
        record["status"] = "succeeded"
    except asyncio.CancelledError:
        record.update(status="cancelled", failure_reason="cancelled")
    except TimeoutError:
        record.update(status="failed", failure_reason="timeout")
    except cli.CLIError as error:
        record.update(status="failed", failure_reason=redact_log(str(error)))
    except (ValueError, OSError, KeyError):
        record.update(status="failed", failure_reason="remote_transport_error")
    record["finished_at"] = cli._now()
    artifacts = cli._path(root, "network-captures", record["run_id"])
    for capture in record["captures"]:
        if "pcap_base64" not in capture:
            if record["status"] == "succeeded":
                record.update(status="failed", failure_reason="capture_failed")
            continue
        encoded = capture.pop("pcap_base64")
        try:
            cli._validate(capture, "capture")
            data = base64.b64decode(encoded, validate=True)
            if (
                len(data) > 400000
                or hashlib.sha256(data).hexdigest() != capture["pcap_sha256"]
            ):
                raise ValueError("capture_integrity_failed")
            alias = {
                node["node_id"]: f"198.18.0.{index + 1}"
                for index, node in enumerate(plan["nodes"])
            }
            pairs = [
                [alias[edge["from"]], alias[edge["to"]]]
                for edge in plan["edges"]
                if capture["node_id"] in {edge["from"], edge["to"]}
            ]
            checked = sanitize_pcap(
                data,
                {ip: ip for ip in alias.values()},
                pairs,
                "udp"
                if definition["protocol"] == "h3"
                else "tcp"
                if definition["protocol"] == "tls"
                else definition["protocol"],
                definition["port"],
            )
            if (
                checked["pcap_sha256"] != capture["pcap_sha256"]
                or checked["flows"] != capture["flows"]
                or checked["packets"] != capture["packets"]
                or checked["ip_bytes"] != capture["ip_bytes"]
            ):
                raise ValueError("capture_projection_mismatch")
        except (ValueError, TypeError, KeyError, cli.CLIError):
            identifier = capture.get("node_id", "unknown")
            capture.clear()
            capture.update(node_id=identifier, error="capture_integrity_failed")
            if record["status"] == "succeeded":
                record.update(
                    status="failed", failure_reason="capture_integrity_failed"
                )
            continue
        artifacts.mkdir(parents=True, exist_ok=True)
        prefix = artifacts / capture["node_id"]
        prefix.with_suffix(".pcap").write_bytes(data)
        csv_data = flows_csv(capture)
        prefix.with_suffix(".csv").write_bytes(csv_data)
        capture["csv_sha256"] = hashlib.sha256(csv_data).hexdigest()
        if capture["packets"] == 0 and record["status"] == "succeeded":
            record.update(status="failed", failure_reason="capture_empty")
    for index, sample in enumerate(record["observations"]):
        if sample.get("failure_reason"):
            sample["failure_reason"] = redact_log(sample["failure_reason"])
        document = sample.pop("qlog", None)
        if document is None:
            continue
        try:
            summary = read_qlog(document)
            data = (
                json.dumps(document, separators=(",", ":"), allow_nan=False) + "\n"
            ).encode()
            if len(data) > 600000:
                raise ValueError("qlog_too_large")
            trace_id = f"trace-{index:04d}"
            folder = cli._path(root, "network-qlogs", record["run_id"])
            folder.mkdir(parents=True, exist_ok=True)
            (folder / (trace_id + ".qlog")).write_bytes(data)
            record["qlogs"].append(
                {
                    "trace_id": trace_id,
                    "sample_index": index,
                    "sha256": hashlib.sha256(data).hexdigest(),
                    **summary,
                }
            )
        except (ValueError, TypeError, KeyError, AttributeError):
            record.update(status="failed", failure_reason="qlog_integrity_failed")
    if definition["protocol"] in {"tls", "h3"}:
        good = [s for s in record["observations"] if s.get("status") == "succeeded"]
        record["analysis"] = {
            "observed": {
                "successful_samples": len(good),
                "failed_samples": len(record["observations"]) - len(good),
                "timeouts": sum(
                    s.get("timeout", False) for s in record["observations"]
                ),
                "retry_packets": sum(q["retry_packets"] for q in record["qlogs"])
                if definition["protocol"] == "h3"
                else None,
            },
            "derived": {
                "mean_handshake_ms": sum(s["handshake_ms"] for s in good) / len(good)
                if good
                else None,
                "mean_request_ms": sum(s["request_ms"] for s in good) / len(good)
                if good
                else None,
            },
            "hypothesis": (
                "Path or implementation differences may affect timings; "
                "a small baseline does not establish causality."
            ),
            "unknown": [
                "one_way_latency",
                "network_loss_rate",
                "performance_under_load",
            ],
        }
    directory = cli._path(root, "network-runs")
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / (record["run_id"] + ".json")
    pending = directory / (".pending-" + record["run_id"])
    cli._atomic_write(pending, record)
    cli._atomic_write(
        path.with_suffix(".sha256"),
        {"sha256": hashlib.sha256(pending.read_bytes()).hexdigest()},
    )
    pending.replace(path)
    return record

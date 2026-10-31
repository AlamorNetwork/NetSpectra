"""Short-lived agents over SSH; data flows between selected nodes, never via SSH."""

import asyncio
import contextlib
import hashlib
import json
import secrets
import threading
import uuid
from pathlib import Path

from pprl_core import cli
from pprl_core.cluster import Inventory
from pprl_core.cluster_ssh import SSH
from pprl_core.workload import seeded_payload


async def execute(
    transport: SSH,
    plan: dict,
    definition: dict,
    payloads: list[bytes],
    observations: list[dict],
) -> list[dict]:
    nodes = {node["node_id"]: transport_node(node) for node in plan["nodes"]}
    processes = []
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
        return process

    try:
        for node in nodes.values():
            checked = await transport.preflight(node)
            plan.setdefault("agent_reports", {})[node.node_id] = checked
            if checked.get("agent_version") != 1:
                raise cli.CLIError("agent_version_mismatch")
        lb = definition["load_balancer"]
        peers = (
            [nodes[lb].address]
            if lb
            else [nodes[n].address for n in definition["clients"]]
        )
        for server in definition["servers"]:
            await launch(server, "server", {"peers": peers})
        if lb:
            await launch(
                lb,
                "relay",
                {
                    "peers": [nodes[n].address for n in definition["clients"]],
                    "backends": [nodes[n].address for n in definition["servers"]],
                },
            )
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
                    },
                )
                output, _ = await asyncio.wait_for(process.communicate(), 35)
                result = json.loads(output)
                if process.returncode or result.get("status") != "succeeded":
                    raise cli.CLIError(result.get("error", "remote_run_failed"))
                samples = result["observations"]
                if len(samples) != len(payloads):
                    raise cli.CLIError("incomplete_remote_samples")
                for sample, payload in zip(samples, payloads, strict=True):
                    if (
                        sample["backend"] not in definition["servers"]
                        or (not lb and sample["backend"] != target)
                        or sample["client"] != client
                        or sample["bytes_echoed"] != len(payload)
                        or sample["payload_sha256"]
                        != hashlib.sha256(payload).hexdigest()
                    ):
                        raise cli.CLIError("invalid_remote_observation")
                    sample["via"] = lb
                observations.extend(samples)
        return observations
    finally:
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
) -> dict:
    topology = inventory.topology(identifier)
    plan = inventory.plan(topology)
    if plan["missing_host_keys"]:
        raise cli.CLIError("host_key_required")
    definition = topology.model_dump()
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
    }

    async def perform():
        async with asyncio.timeout(60):
            task = asyncio.create_task(
                execute(transport, plan, definition, payloads, record["observations"])
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
        record.update(status="failed", failure_reason=str(error))
    except (ValueError, OSError, KeyError):
        record.update(status="failed", failure_reason="remote_transport_error")
    record["finished_at"] = cli._now()
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

"""Versioned inventory and explicit multi-host paths, separate from loopback runs."""

import ipaddress
import re
import threading
import uuid
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from pprl_core import cli


class Node(BaseModel):
    model_config = ConfigDict(extra="forbid")
    node_id: str = Field(pattern=r"^[a-z][a-z0-9-]{0,31}$")
    name: str = Field(min_length=1, max_length=64, pattern=r"\S")
    address: str
    ssh_port: int = Field(default=22, ge=1, le=65535, strict=True)
    ssh_user: str = Field(default="root", pattern=r"^[a-z_][a-z0-9_-]{0,31}$")
    install_dir: str = "/opt/netspectra-worker"
    host_key: str = ""

    @field_validator("address")
    @classmethod
    def valid_address(cls, value: str) -> str:
        address = ipaddress.IPv4Address(value)
        if address.is_loopback or address.is_unspecified or address.is_multicast:
            raise ValueError("a distinct network node address is required")
        if str(address) == "255.255.255.255" or address.is_link_local:
            raise ValueError("invalid node address")
        return str(address)

    @field_validator("install_dir")
    @classmethod
    def dedicated_directory(cls, value: str) -> str:
        if not re.fullmatch(r"/(opt|srv)/netspectra-[a-z0-9-]{1,40}", value):
            raise ValueError(
                "use a dedicated /opt/netspectra-* or /srv/netspectra-* directory"
            )
        return value

    @field_validator("host_key")
    @classmethod
    def valid_key(cls, value: str) -> str:
        if value and not re.fullmatch(
            r"ssh-ed25519 [A-Za-z0-9+/]{40,100}={0,2}", value
        ):
            raise ValueError("an SSH ed25519 host public key is required")
        return value


class Topology(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=64, pattern=r"\S")
    clients: list[str] = Field(min_length=1, max_length=8)
    servers: list[str] = Field(min_length=1, max_length=8)
    load_balancer: str | None = None
    protocol: Literal["tcp", "udp"] = "tcp"
    port: int = Field(default=28080, ge=28000, le=28999, strict=True)
    repetitions: int = Field(default=3, ge=1, le=10, strict=True)
    run_seed: int = Field(default=42, ge=0, le=4294967295, strict=True)

    @model_validator(mode="after")
    def distinct_roles(self):
        roles = self.clients + self.servers
        if self.load_balancer:
            roles.append(self.load_balancer)
        if len(roles) != len(set(roles)):
            raise ValueError("each selected node must have one role per topology")
        return self


class Inventory:
    def __init__(self, root: Path):
        self.root = root
        self.path = cli._path(root, "cluster-inventory.json")
        self.lock = threading.RLock()

    def read(self) -> dict:
        with self.lock:
            return (
                cli._read(self.path)
                if self.path.exists()
                else {"schema_version": "1.0.0", "nodes": [], "topologies": []}
            )

    def add_node(self, node: Node) -> dict:
        with self.lock:
            data = self.read()
            if any(
                n["node_id"] == node.node_id or n["address"] == node.address
                for n in data["nodes"]
            ):
                raise cli.CLIError("duplicate_node")
            if len(data["nodes"]) >= 32:
                raise cli.CLIError("node_limit")
            record = node.model_dump()
            data["nodes"].append(record)
            cli._atomic_write(self.path, data)
            return record

    def node(self, identifier: str) -> Node:
        for record in self.read()["nodes"]:
            if record["node_id"] == identifier:
                return Node.model_validate(record)
        raise cli.CLIError("node_not_found")

    def update_node(self, identifier: str, node: Node) -> dict:
        with self.lock:
            previous = self.node(identifier)
            if node.node_id != identifier:
                raise cli.CLIError("node_id_is_immutable")
            data = self.read()
            if any(
                item["address"] == node.address and item["node_id"] != identifier
                for item in data["nodes"]
            ):
                raise cli.CLIError("duplicate_node")
            same_host = (previous.address, previous.ssh_port) == (
                node.address,
                node.ssh_port,
            )
            record = node.model_dump() | {
                "host_key": previous.host_key if same_host else ""
            }
            data["nodes"] = [
                record if item["node_id"] == identifier else item
                for item in data["nodes"]
            ]
            cli._atomic_write(self.path, data)
            return record

    def pin(self, identifier: str, key: str) -> dict:
        with self.lock:
            node = self.node(identifier).model_copy(update={"host_key": key})
            Node.model_validate(node.model_dump())
            if not key:
                raise cli.CLIError("host_key_required")
            data = self.read()
            for index, item in enumerate(data["nodes"]):
                if item["node_id"] == identifier:
                    if item["host_key"] and item["host_key"] != key:
                        raise cli.CLIError("host_key_change_requires_operator")
                    data["nodes"][index] = node.model_dump()
            cli._atomic_write(self.path, data)
            return node.model_dump()

    def plan(self, topology: Topology) -> dict:
        selected = {
            identifier: self.node(identifier)
            for identifier in topology.clients
            + topology.servers
            + ([topology.load_balancer] if topology.load_balancer else [])
        }
        if topology.load_balancer:
            edges = [(client, topology.load_balancer) for client in topology.clients]
            edges += [(topology.load_balancer, server) for server in topology.servers]
        else:
            edges = [
                (client, server)
                for client in topology.clients
                for server in topology.servers
            ]
        return {
            "scope": "selected_owned_nodes",
            "protocol": topology.protocol,
            "port": topology.port,
            "edges": [{"from": a, "to": b} for a, b in edges],
            "nodes": [node.model_dump() for node in selected.values()],
            "missing_host_keys": [
                n.node_id for n in selected.values() if not n.host_key
            ],
        }

    def add_topology(self, topology: Topology) -> dict:
        with self.lock:
            self.plan(topology)
            data = self.read()
            if len(data["topologies"]) >= 200:
                raise cli.CLIError("topology_limit")
            record = topology.model_dump() | {
                "topology_id": "top-" + uuid.uuid4().hex[:16]
            }
            data["topologies"].append(record)
            cli._atomic_write(self.path, data)
            return record

    def topology(self, identifier: str) -> Topology:
        for record in self.read()["topologies"]:
            if record["topology_id"] == identifier:
                return Topology.model_validate(
                    {k: v for k, v in record.items() if k != "topology_id"}
                )
        raise cli.CLIError("topology_not_found")

"""Controller-to-node OpenSSH transport with pinned hosts and dedicated installs."""

import asyncio
import base64
import hashlib
import json
import re
import shlex
import subprocess
from pathlib import Path

from pprl_core import cli
from pprl_core.cluster import Node

REPOSITORY = "https://github.com/AlamorNetwork/NetSpectra.git"


class SSH:
    def __init__(self, root: Path):
        self.directory = cli._path(root, "cluster-ssh")
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.key = self.directory / "id_ed25519"

    def public_key(self, create: bool = False) -> str | None:
        if create and not self.key.exists():
            subprocess.run(
                [
                    "ssh-keygen",
                    "-q",
                    "-t",
                    "ed25519",
                    "-N",
                    "",
                    "-C",
                    "netspectra-controller",
                    "-f",
                    str(self.key),
                ],
                check=True,
                capture_output=True,
                timeout=15,
            )
        public = self.key.with_suffix(".pub")
        return public.read_text().strip() if public.exists() else None

    async def scan(self, node: Node) -> list[dict]:
        process = await asyncio.create_subprocess_exec(
            "ssh-keyscan",
            "-T",
            "5",
            "-t",
            "ed25519",
            "-p",
            str(node.ssh_port),
            node.address,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        try:
            output, _ = await asyncio.wait_for(process.communicate(), 8)
        finally:
            if process.returncode is None:
                process.kill()
                await process.wait()
        keys = []
        for line in output.decode(errors="replace").splitlines():
            fields = line.split()
            if len(fields) != 3 or fields[1] != "ssh-ed25519":
                continue
            key = " ".join(fields[1:])
            Node.model_validate(node.model_dump() | {"host_key": key})
            digest = hashlib.sha256(base64.b64decode(fields[2])).digest()
            keys.append(
                {
                    "host_key": key,
                    "fingerprint": "SHA256:"
                    + base64.b64encode(digest).decode().rstrip("="),
                }
            )
        if not keys:
            raise cli.CLIError("ssh_host_unreachable")
        return keys

    def command(self, node: Node, command: list[str]) -> list[str]:
        if not node.host_key:
            raise cli.CLIError("host_key_required")
        if not self.key.exists():
            raise cli.CLIError("controller_key_required")
        known_hosts = self.directory / (node.node_id + "-known_hosts")
        known_hosts.write_text(
            f"[{node.address}]:{node.ssh_port} {node.host_key}\n"
            f"{node.address} {node.host_key}\n"
        )
        return [
            "ssh",
            "-F",
            "/dev/null",
            "-T",
            "-o",
            "BatchMode=yes",
            "-o",
            "IdentitiesOnly=yes",
            "-o",
            "StrictHostKeyChecking=yes",
            "-o",
            "GlobalKnownHostsFile=/dev/null",
            "-o",
            f"UserKnownHostsFile={known_hosts}",
            "-o",
            "ConnectTimeout=8",
            "-o",
            "ServerAliveInterval=5",
            "-o",
            "ServerAliveCountMax=2",
            "-i",
            str(self.key),
            "-p",
            str(node.ssh_port),
            f"{node.ssh_user}@{node.address}",
            shlex.join(command),
        ]

    async def execute(
        self, node: Node, command: list[str], timeout: float = 15
    ) -> dict:
        process = await asyncio.create_subprocess_exec(
            *self.command(node, command),
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            output, _ = await asyncio.wait_for(process.communicate(), timeout)
        finally:
            if process.returncode is None:
                process.kill()
                await process.wait()
        if process.returncode:
            raise cli.CLIError("ssh_command_failed")
        try:
            return json.loads(output)
        except ValueError as error:
            raise cli.CLIError("invalid_agent_response") from error

    async def bootstrap(self, node: Node, revision: str) -> dict:
        if not re.fullmatch(r"[0-9a-f]{40}", revision):
            raise cli.CLIError("invalid_source_revision")
        # A fresh directory is mandatory. Never pull, clean, checkout or overwrite
        # an existing remote folder, including a previous worker installation.
        script = """set -eu
target="$1"
revision="$2"
command -v git >/dev/null
command -v python3 >/dev/null
test ! -e "$target"
test ! -L "$target"
umask 077
mkdir "$target"
git -C "$target" init -q
git -C "$target" remote add origin https://github.com/AlamorNetwork/NetSpectra.git
git -C "$target" fetch -q --depth 1 origin "$revision"
git -C "$target" checkout -q --detach FETCH_HEAD
PYTHONPATH="$target/packages/pprl_core/src" python3 -m pprl_core.remote_agent check
"""
        return await self.execute(
            node,
            ["sh", "-c", script, "netspectra-bootstrap", node.install_dir, revision],
            120,
        )

    def agent_command(self, node: Node, role: str) -> list[str]:
        return self.command(
            node,
            [
                "env",
                f"PYTHONPATH={node.install_dir}/packages/pprl_core/src",
                "sh",
                "-c",
                'if test -x "$1/.venv/bin/python"; then '
                'interpreter="$1/.venv/bin/python"; else interpreter=python3; fi; '
                'exec "$interpreter" -m pprl_core.remote_agent "$2"',
                "netspectra-agent",
                node.install_dir,
                role,
            ],
        )

    async def preflight(self, node: Node) -> dict:
        command = self.agent_command(node, "check")
        # execute expects the remote argv, while agent_command includes SSH argv.
        return await self.execute(node, shlex.split(command[-1]))

    async def install_dependencies(self, node: Node) -> dict:
        script = """set -eu
target="$1"
test -d "$target/.git"
test ! -L "$target/.venv"
test -f "$target/worker-requirements.txt"
umask 077
if test ! -e "$target/.venv"; then python3 -m venv --without-pip "$target/.venv"; fi
python3 -m pip --python "$target/.venv/bin/python" install --quiet \
  --disable-pip-version-check --require-hashes --only-binary=:all: \
  -r "$target/worker-requirements.txt" >&2
PYTHONPATH="$target/packages/pprl_core/src" \
  "$target/.venv/bin/python" -m pprl_core.remote_agent check
"""
        return await self.execute(
            node, ["sh", "-c", script, "netspectra-dependencies", node.install_dir], 240
        )

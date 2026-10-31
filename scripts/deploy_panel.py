"""Install the IP HTTPS panel service from a clean, already-pulled checkout."""

import argparse
import ipaddress
import os
import subprocess
import sys
from pathlib import Path

from pprl_core.panel import initialize


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ip", required=True, type=ipaddress.IPv4Address)
    args = parser.parse_args()
    if sys.platform != "linux" or os.geteuid() != 0:
        parser.error("requires Linux root")
    repo = Path(__file__).resolve().parents[1]
    if any(char.isspace() for char in str(repo)):
        parser.error("checkout path must not contain whitespace")
    dirty = subprocess.check_output(
        ["git", "status", "--porcelain"], cwd=repo, text=True
    )
    if dirty.strip():
        parser.error("commit and pull source changes before deploying")
    state = repo / "artifacts" / "panel"
    state.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(state, 0o700)
    credentials = state / "initial-access.json"
    if not (state / "panel-auth.json").exists():
        initialize(state, credentials)
    certificate, key = state / "tls.crt", state / "tls.key"
    if not certificate.exists() or not key.exists():
        subprocess.run(
            [
                "openssl",
                "req",
                "-x509",
                "-newkey",
                "rsa:2048",
                "-nodes",
                "-days",
                "90",
                "-subj",
                f"/CN={args.ip}",
                "-addext",
                f"subjectAltName=IP:{args.ip}",
                "-keyout",
                str(key),
                "-out",
                str(certificate),
            ],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
        os.chmod(key, 0o600)
    service = Path("/etc/systemd/system/netspectra-panel.service")
    if not service.exists():
        # Do not displace an unrelated listener on first installation.
        listeners = subprocess.check_output(
            ["ss", "-H", "-ltn", "sport = :8765"], text=True
        )
        if listeners.strip():
            parser.error("port 8765 is occupied; no service was replaced")
    service.write_text(
        "[Unit]\nDescription=NetSpectra private experiment panel\n"
        "After=network.target\n\n[Service]\nType=simple\n"
        f"WorkingDirectory={repo}\n"
        f"ExecStart={repo}/.venv/bin/pprl-panel --data-dir {state} serve "
        f"--host 0.0.0.0 --port 8765 --allowed-host {args.ip} "
        f"--certfile {certificate} --keyfile {key}\n"
        "Restart=on-failure\nRestartSec=3\nKillMode=control-group\n"
        "TimeoutStopSec=45\nNoNewPrivileges=true\nPrivateTmp=true\n"
        "ProtectSystem=strict\n"
        f"ReadWritePaths={state}\n"
        "UMask=0077\nLimitNOFILE=4096\n\n[Install]\n"
        "WantedBy=multi-user.target\n",
        encoding="utf-8",
    )
    subprocess.run(["systemctl", "daemon-reload"], check=True)
    subprocess.run(["systemctl", "enable", "netspectra-panel"], check=True)
    subprocess.run(["systemctl", "restart", "netspectra-panel"], check=True)
    print(f"Panel: https://{args.ip}:8765")
    print(f"Initial credentials (private file): {credentials}")


if __name__ == "__main__":
    main()

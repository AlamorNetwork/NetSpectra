"""Real TCP/UDP process endpoints and deterministic input replay, end to end."""

import json
import shutil
import subprocess
import tempfile
from pathlib import Path


def main() -> None:
    executable = shutil.which("pprl")
    if executable is None:
        raise SystemExit("pprl entry point missing; run uv sync --locked")
    templates = Path(__file__).resolve().parents[1] / "experiments/templates"
    results = []
    with tempfile.TemporaryDirectory(prefix="pprl-replay-smoke-") as directory:
        store = Path(directory)

        def command(*args: str) -> dict:
            process = subprocess.run(
                [executable, "--data-dir", directory, *args],
                check=True,
                capture_output=True,
                text=True,
                timeout=40,
            )
            return json.loads(process.stdout)

        def summary(record: dict) -> dict:
            return json.loads(
                (store / "runs" / record["run_id"] / "summary.json").read_text()
            )

        for protocol in ("tcp", "udp"):
            command("create", str(templates / f"seeded-{protocol}.json"))
            first = command(
                "run",
                f"exp-seeded-{protocol}",
                "--timeout",
                "20",
                "--attempt-timeout",
                "5",
                "--retries",
                "1",
            )
            second = command("replay", first["run_id"])
            assert command("inspect", second["run_id"]) == second
            a, b = summary(first), summary(second)
            assert a["workload"] == b["workload"]
            assert a["workload_sha256"] == b["workload_sha256"]
            assert first["metrics"] == second["metrics"]
            assert first["run_id"] != second["run_id"]
            assert b["replay_of"] == first["run_id"]
            for observation in a["observations"] + b["observations"]:
                assert observation["client_pid"] != observation["server_pid"]
                assert observation["scope"] == "ipv4_loopback_only"
            results.append(
                {
                    "protocol": protocol,
                    "samples_per_run": first["sample_size"],
                    "bytes_per_run": first["metrics"][0]["value"],
                    "workload_sha256": a["workload_sha256"],
                    "replay_matches": True,
                    "git_sha": first["git_sha"],
                }
            )
    print(json.dumps({"status": "succeeded", "results": results}, sort_keys=True))


if __name__ == "__main__":
    main()

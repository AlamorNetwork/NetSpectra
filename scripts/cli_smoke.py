"""Exercise installed CLI commands in a disposable local store."""

import json
import shutil
import subprocess
import tempfile
from pathlib import Path


def main() -> None:
    executable = shutil.which("pprl")
    if executable is None:
        raise SystemExit("pprl entry point missing; run uv sync --locked")
    template = (
        Path(__file__).resolve().parents[1] / "experiments/templates/loopback.json"
    )
    with tempfile.TemporaryDirectory(prefix="pprl-cli-smoke-") as directory:

        def command(*args: str) -> dict:
            output = subprocess.run(
                [executable, "--data-dir", directory, *args],
                check=True,
                capture_output=True,
                text=True,
                timeout=30,
            )
            return json.loads(output.stdout)

        created = command("create", str(template))
        identifier = created["experiment_id"]
        assert len(command("list")["experiments"]) == 1
        experiment = command("inspect", identifier)
        run = command("run", identifier)
        assert run["status"] == "succeeded"
        assert run["sample_size"] == experiment["repetitions"]
        assert command("inspect", run["run_id"]) == run
        print(
            json.dumps(
                {
                    "status": "succeeded",
                    "commands": ["create", "list", "run", "inspect"],
                    "sample_size": run["sample_size"],
                    "git_sha": run["git_sha"],
                    "bytes_echoed": run["metrics"][0]["value"],
                },
                sort_keys=True,
            )
        )


if __name__ == "__main__":
    main()

# W01 T05: loopback smoke

This step echoes a fixed synthetic payload on TCP and UDP using ephemeral ports
bound to 127.0.0.1. No hostname lookup, external destination or configurable
target exists. The total deadline defaults to 5 seconds and every socket and
server task is cleaned up on success, error, timeout or cancellation.

```sh
uv sync --locked
uv run --locked python -m pprl_core.loopback
uv run --locked pytest tests/integration/test_loopback.py -q
```

Expected JSON: scope ipv4_loopback_only, with TCP and UDP status succeeded and
26 bytes echoed each. The command exits 0 on success, 1 on an operational error
or 130 on Ctrl+C. Error output contains only status and exception type.
This is a smoke summary, not a Run contract record or performance benchmark.
The payload is fixed for reproducibility; no latency conclusions are made.

The loopback restriction constrains these probes, not other processes on the
host. This does not establish the namespace/veth isolation planned for W05.

## Windows / WSL2 setup

Windows can run this smoke directly. For a local Linux environment, an
administrator can install WSL2 with Ubuntu (installation needs downloads):

```powershell
wsl --install -d Ubuntu --no-launch
```

Restart Windows if requested, launch Ubuntu, and finish its user setup.
Inside Ubuntu, install uv from its official distribution, then clone the repo
inside the Linux home directory and run the three smoke commands above.
Dependency setup may access package registries; the smoke itself stays local.

Verify WSL2 with `wsl --list --verbose` on Windows. CI also runs the smoke and
integration tests on native Ubuntu and Windows. A passing Linux CI run is Linux
evidence, but does not prove that local WSL is configured.

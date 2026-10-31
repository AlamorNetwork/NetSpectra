# W02 verification

## Scope

Initial T01–T03 local CLI with fixed loopback execution and per-run provenance.
See clients/cli/README.md for unsupported configurations and storage limits.
No remote measurement endpoints are used. T04–T06 now have same-host process
endpoints, bounded retry and versioned seeded replay; independent review remains.

## Reproduction

```sh
uv sync --locked
uv run --locked ruff check .
uv run --locked ruff format --check .
uv run --locked pytest
uv run --locked python scripts/cli_smoke.py
uv build
```

## Windows observations

- 97 tests passed, including real TCP/UDP, unique run directories, failed and
  cancelled runs, partial batch results, artifact tampering, snapshot mismatch,
  strict JSON, path/symlink rejection and the JSON command interface.
- Ruff passes; all Python files are formatted.
- CLI smoke: create/list/run/inspect succeed; 3 repetitions echo 78 total bytes.
- Source and wheel builds succeed. Both schemas are included in the wheel and
  the extracted wheel's CLI can create/list with installed runtime dependencies.
- The separate offline wheel-environment resolver could not find rpds-py in its
  cache. Full isolated wheel install is not claimed from that attempt.

## Ubuntu / GitHub

Code commit c77b4915c8bae24446d81098a91e69cc40e4da95 was pulled from GitHub
with git pull --ff-only on the separate Ubuntu 24 server. No source files were
created or edited on the server. Python 3.12.12 and uv 0.12.5 were used.

Observed: locked sync succeeds; Ruff passes; 8 Python files pass formatting;
97 tests pass in 0.78s. CLI create/list/run/inspect smoke succeeds with 3 samples
and 78 echoed bytes. Source and wheel build succeed. Server HEAD equals the
GitHub branch SHA and git status --porcelain is empty. Generated run data remains
local and ignored. Credentials and server addresses are not published.

The final evidence-only commit is pulled afterward and HEAD equality rechecked.
Hosted CI is checked separately; server success alone is not a CI assertion.

## W02 T04–T06: seeded process endpoints, retry and replay

Reproduction:

```sh
uv run --locked pytest
uv run --locked python scripts/seeded_replay_smoke.py
```

Windows precommit validation: 121 tests passed in 12.45s; Ruff and formatting
pass; source/wheel build succeeds. Native process endpoints validate both peer
roles/PIDs, exact payload lengths and SHA256. Cancellation and startup-timeout
tests verify children exit; malformed readiness is rejected and reaped.

A Windows-specific failure initially revealed venv launcher PIDs differed from
actual child PIDs. Base-interpreter invocation plus an explicit trusted package
path fixes process ownership and cleanup; all tests subsequently passed.

Transient-only retry, retry exhaustion, per-attempt deadline and total-budget
backoff are tested. Replay retains the original seed despite registry changes,
rejects changed workload definitions, and creates a distinct Run.

Native Windows seeded smoke: 3 samples and 734 bytes per TCP/UDP run and replay.
Input hashes match per protocol:

- TCP: 7be443ff67bec2b09801b985da07adc4a47ad0edde11a9b22a6f3e8e52d91b85
- UDP: 3583ed681b153a60a8d6295c4f6b40dd80aa740190eeb6813443dff7c7aeba60

These are input-plan fingerprints, not timing or outcome guarantees. No public
ports, namespace topology or remote-target traffic are introduced. Server and
CI evidence for the committed revision follows after synchronization.

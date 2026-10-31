# W01 foundation verification — 2026-10-31

## Standard commands

```sh
uv python install
uv sync --locked
uv run --locked ruff check .
uv run --locked ruff format --check .
uv run --locked pytest
uv build
```

## Observed local results

Python 3.12.12, uv 0.12.5, pytest 9.1.1, Ruff 0.11.13.
uv.lock was generated with official registry metadata. All eight installed
package versions match it. The official Ruff Windows wheel was downloaded using
curl through SOCKS5 on localhost port 10808; its SHA256 matches uv.lock exactly.
No lock hashes were edited.

Ruff lint passes; both Python files pass formatting; the smoke test passes.
Source distribution and wheel builds succeed. No network experiments occurred.

## Historical network workaround and limitation (resolved below)

Direct registry TLS failed; HTTP proxy timed out. SOCKS5 allowed curl to obtain
the wheel, but uv still failed to download it. A temporary loopback tunnel did
not fix that download and was stopped. No proxy settings were stored in the repo.

Other dependencies were synced from cache; Ruff was installed from the verified
local registry wheel. Verification avoids automatic synchronization:

```sh
uv run --locked --no-sync ruff check .
uv run --locked --no-sync ruff format --check .
uv run --locked --no-sync pytest
uv build --offline
git diff --cached --check
```

Version equality was checked using importlib.metadata against every package in
uv.lock; the Ruff wheel hash was checked using hashlib against its lock entry.

Ordinary fresh uv sync remains blocked by the Ruff download on this connection.
Hosted CI, remote branch protection and independent reproduction remain pending.
T04 is not implemented. T03 local tool checks pass, but full fresh-install
acceptance is still blocked by network behavior.

## Resolution — 2026-10-31

The earlier download blocker is resolved. With UV_HTTP_TIMEOUT=120 and retries
disabled, uv sync --locked exited 0: downloaded the 11 MiB Ruff wheel, replacing
the local-file installation with the registry installation. No proxy overrides
were added for this successful invocation. Download preparation took 3.81s.

Fresh verification, all exit 0:

- uv sync --locked
- uv run --locked ruff check . — All checks passed
- uv run --locked ruff format --check . — 2 files already formatted
- uv run --locked pytest — 1 passed in 0.05s

T03 is ready for review locally. Hosted CI and independent reproduction remain
pending. This resolution supersedes the historical network blocker above.

## T04 contracts — 2026-10-31

Added schemas/experiment.schema.json and schemas/run.schema.json, plus four valid
and two intentionally invalid synthetic examples. No real measurements or raw
captures are included. Schema details and limits: schemas/README.md.

Initial test run caught missing optional RFC3339 support: 71 passed, 1 failed
because February 30 was accepted. Added explicit rfc3339-validator dependency
and a guard asserting the date-time checker is installed; rerun: 73 passed.

Acceptance includes required fields, unknown fields, bounds and booleans,
synthetic/isolated scope, terminal status/failure reason, UTC calendar timestamps,
relative artifact paths and hashes, and quantitative metric classifications.
Schemas do not enforce cross-record identity/seed equality, timestamp ordering,
actual artifact checksums, symlinks or network isolation. Runner work is separate.

Reproduction:

```sh
uv sync --locked
uv run --locked pytest tests/unit/test_contracts.py -q
uv run --locked ruff check .
uv run --locked ruff format --check .
uv run --locked pytest
uv build --offline
```

T04 is implemented for local review; independent review and hosted CI remain
pending. T05 (WSL/Linux loopback) and T06 (ADR-001) are not implemented.

## T05/T06 — loopback and scope policy

Windows loopback command returned scope ipv4_loopback_only, Python 3.12.12,
TCP and UDP succeeded with 26 bytes each. All 76 tests pass locally.

Reproduce:

```sh
uv run --locked python -m pprl_core.loopback
uv run --locked pytest tests/integration/test_loopback.py -q
uv run --locked pytest
```

Timeout/cancellation tests assert all tracked sockets close and server tasks
terminate. The smoke binds only to 127.0.0.1 on ephemeral ports and accepts no
external destination. No captures or public probes are performed.

WSL is not installed locally and the current process is not Administrator.
No elevation or restart was attempted. Native Ubuntu/Windows CI is configured
to run the smoke, independently of the local WSL setup. Both Ubuntu and Windows
push CI passed for code commit f4da54a:
https://github.com/AlamorNetwork/NetSpectra/actions/runs/41175594893
Draft review: https://github.com/AlamorNetwork/NetSpectra/pull/1
ADR-001 is proposed for independent review, not a claim that future privacy
controls or namespace isolation are already implemented.

## Ubuntu server execution — 2026-10-31

A separate Ubuntu 24.04.4 LTS x86_64 server cloned code e2e227d. Dedicated tools
were installed for this project: uv 0.12.5 and managed Python 3.12.12. No system
Python packages were installed. The system Python 3.12.3 loopback also succeeded.

Observed with pinned Python: uv sync --locked succeeded, Ruff passed, five files
passed format check, 76 tests passed in 0.83s. TCP and UDP each echoed 26 bytes
on 127.0.0.1. No public measurement port was opened.

The first build was stopped because its cache lived inside the source tree.
.tools/ is now ignored to exclude downloaded tools/caches from source artifacts;
final package build evidence is recorded after rebuilding.

Server credentials, addresses and private keys are deliberately absent. T05 is
ready for review using native Ubuntu evidence; local WSL is no longer required
for this iteration. Human review and proposed ADR approval remain pending.

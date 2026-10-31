# NetSpectra — Phoenix Protocol Research Lab (PPRL)

[فارسی](README.fa.md)

A research lab for reproducible measurements of TCP, TLS, QUIC and HTTP/3 under
controlled impairment and simulated DPI. Measurements use lab-owned endpoints
and synthetic traffic by default. Results distinguish observed facts, derived
metrics, hypotheses and unknowns.

## Current scope

W01 T01–T06: repository layout, contribution templates, pinned Python,
dependency configuration, Ruff, pytest and a CI smoke workflow. The package currently
exposes only its version. Experiment and completed Run JSON Schemas include
synthetic fixtures and acceptance tests; see [contract guide](schemas/README.md).
The fixed [loopback smoke](lab/README.md) echoes synthetic bytes over TCP/UDP on
127.0.0.1 only. No general probes, captures, API, UI or namespace provisioning
exist. Local WSL setup is pending; native Ubuntu is covered by CI.
The scope/data policy is recorded in [ADR-001](docs/ADR/ADR-001-lab-scope-and-data-policy.md),
pending independent review.

## Quickstart

Install Git and uv, then open a terminal in this directory. Dependency setup
downloads Python and packages; the smoke test itself sends no network traffic.
Windows supports this foundation; future namespace experiments require Linux/WSL2.

```sh
uv python install
uv sync --locked
uv run --locked ruff check .
uv run --locked ruff format --check .
uv run --locked pytest
uv build
```

Python is pinned in .python-version; uv.lock records resolved versions and
registry hashes. Commit both when intentionally updating the toolchain. Use
uv lock only when changing dependencies. The workflow defines checks for Ubuntu
and Windows. Repository: https://github.com/AlamorNetwork/NetSpectra
Branch protection requires administrator configuration.

Local verification: uv sync --locked successfully downloaded Ruff from the
registry on 2026-10-31. Standard locked lint, formatting and pytest checks pass.
See reports/w01/README.md for evidence.

## Layout

| Path | Responsibility |
| --- | --- |
| packages/ | Core package; capture and analysis placeholders |
| services/, clients/ | Future API, worker, CLI and web clients |
| lab/, experiments/, schemas/ | Future isolated lab, scenarios and contracts |
| datasets/, reports/ | Synthetic data guidance, report templates and evidence |
| docs/ | Specification, roadmap, methodology and weekly status |
| tests/, scripts/, .github/ | Verification, utilities and collaboration |

The empty directories are tracked with .gitkeep; they are not implemented modules.
See docs/weekly/W01.md for evidence and outstanding acceptance requirements.

## Licensing

Code: Apache-2.0 (LICENSE). Documentation: CC BY 4.0 (docs/LICENSE.md).
Datasets have separate terms and must not be assumed covered by either license.

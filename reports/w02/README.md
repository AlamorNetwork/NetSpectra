# W02 verification

## Scope

Initial T01–T03 local CLI with fixed loopback execution and per-run provenance.
See clients/cli/README.md for unsupported configurations and storage limits.
No remote measurement endpoints are used. W02 T04–T06 are not complete.

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

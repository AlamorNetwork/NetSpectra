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

Pending execution of the committed revision. Evidence will record the source
commit, command results and equality with the GitHub branch head. No credentials
or server addresses will be published.

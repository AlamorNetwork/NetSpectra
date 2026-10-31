# W02 local experiment CLI

Run from a Git checkout with Python 3.12 and uv:

```sh
uv sync --locked
uv run --locked pprl create experiments/templates/loopback.json
uv run --locked pprl list
uv run --locked pprl run exp-loopback-demo
uv run --locked pprl inspect exp-loopback-demo
```

The run command prints a run_id. Inspect that identifier to validate the Run
record and verify artifact hashes and sizes. `create` never overwrites an
existing experiment. For an isolated repeatable demo of all commands:

```sh
uv run --locked python scripts/cli_smoke.py
```

Place the global `--data-dir <path>` option before the command to choose a local
store (default artifacts/cli). Symlink store components and invalid identifiers
are rejected. This is a local, single-user store, not a service for untrusted
multi-user access; it does not promise protection from concurrent hostile
filesystem replacement, power loss, or administrators modifying its files.

## Supported execution

Only loopback_echo version 1 can run, with protocol tcp or udp and 1–10
repetitions. Scope must be isolated / synthetic_only, delay/loss/jitter zero,
bandwidth_mbps exactly 100 as the nominal baseline label, and both raw PCAP/qlog
retention flags false. The runner does not configure or measure bandwidth;
the summary explicitly records network_profile_applied=false. It does not
create namespace isolation. Other valid manifests can be imported and inspected
but execution is rejected before any probe starts.

The fixed payload does not use randomness. The seed is preserved for lineage;
equal seeds do not yet select a randomized workload. No general replay guarantee
or separate client/server endpoints are implemented in this step.

`run --timeout <seconds>` applies one deadline to the entire batch (0 < timeout
<= 30; default 5). Known failures are categorized as timeout, loopback_error,
internal_error or cancelled. Completed repetitions survive a later failure in
the terminal record. Ctrl+C creates a cancelled record when normal Python signal
handling can finish. SIGKILL, power loss and storage failures can leave an
incomplete run directory without run.json; those are not successful runs.
Automatic retry/resume is not implemented.

Exit codes: 0 successful command; 1 failed execution or I/O; 2 invalid input or
unsupported configuration; 130 cancelled execution. Errors expose categories,
not private exception messages.

## Provenance and layout

```text
artifacts/cli/
  experiments/exp-.../experiment.json
  runs/run-.../
    experiment.json   # immutable configuration snapshot for this run
    summary.json      # source dirty flag, scenario descriptor, observations
    run.json          # terminal record and artifact manifest
```

Run metadata includes UUID-based run_id, UTC timestamps, source Git SHA,
platform/tool versions, sample count, metrics and a SHA256 of the canonical
scenario descriptor. Artifact hashes cover exact bytes, including the experiment
snapshot. They detect accidental changes; they are not signatures against a
malicious party who can rewrite both files and their manifest.

Source provenance comes from the editable source checkout. The summary marks
uncommitted source as dirty; such runs must not be used for published benchmark
claims. Standalone wheels contain schemas for create/list/inspect but cannot run
measurements without their editable source checkout; they fail with a safe
source-provenance error rather than attributing another repository's commit.

The default artifacts directory is ignored by Git. Only code, templates and
reviewed summaries are synchronized to the server through Git. Local captures,
private credentials and transient run directories are never published by this
workflow. Server source files are updated by fast-forward pull, not manual edits.

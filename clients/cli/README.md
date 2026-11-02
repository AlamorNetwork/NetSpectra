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

Two version-1 scenarios can run: loopback_echo retains its fixed in-process
payload for compatibility; seeded_echo uses independent client/server processes
on the same host. Both protocols (TCP/UDP) use IPv4 loopback only. This is not
a two-machine or namespace topology and exposes no public measurement listener.

Both scenarios allow 1–10 repetitions, isolated / synthetic_only scope, zero
delay/loss/jitter, bandwidth_mbps=100 as a nominal label (not shaped or measured),
and false PCAP/qlog retention flags. Unsupported configurations are rejected
before any endpoint starts. See the seeded TCP and UDP templates.

```sh
uv run --locked pprl create experiments/templates/seeded-tcp.json
uv run --locked pprl run exp-seeded-tcp --timeout 20 --attempt-timeout 5 --retries 1
# Substitute the run_id printed above:
uv run --locked pprl replay run-REPLACE_WITH_RUN_ID
uv run --locked python scripts/seeded_replay_smoke.py
```

## Retry and cancellation

The entire batch, including retry delays, has one --timeout budget (0 < seconds
<= 30; default 5). Each attempt has --attempt-timeout (0 < seconds <= 30; default
2). --retries is 0–2 additional attempts per sample (default 0); --retry-delay
is 0–1 seconds (default 0.05). A timeout or known transient connection error may
retry. Payload/protocol mismatch, configuration, permission and internal errors
do not retry. Every attempt is recorded, so failures are not hidden by success.

An attempt creates new endpoints and reuses that sample's exact planned bytes.
Subprocesses are terminated/reaped after errors, deadlines and cancellation;
cleanup can take additional time after a deadline. Windows uses the base Python
interpreter directly to avoid a venv launcher's extra process. No system Python
packages or shell commands are injected into child endpoints.

Completed samples survive a later batch failure. bytes_echoed counts successful
samples, not failed-attempt wire traffic; attempts.bytes_planned is declared input,
not measured traffic volume. Failure categories include timeout, loopback_error,
endpoint_io_error, endpoint_transient_error, endpoint_protocol_error,
payload_mismatch, internal_error and cancelled. Error messages expose no payload
or private exception details.

Ctrl+C finalizes a cancelled run when Python signal handling can finish. SIGKILL,
power loss, repeated interruption or storage failure can leave incomplete run
directories. No in-place crash resume is implemented.

## Seed and replay

seeded_echo uses generator pprl-sha256-v1: ASCII prefix
`pprl-sha256-v1:{seed}:{sample_index}:`; size is 32 plus the first two bytes of
SHA256(prefix), interpreted big-endian, modulo 481. Payload blocks are
SHA256(prefix + ASCII decimal block counter starting at 0), truncated to that
size. Inputs contain no private data. A golden-vector test fixes this behavior
across Python platforms. The older fixed scenario records seed_used=false.

summary.json records the canonical workload plan/hash, generator, per-sample
length/hash, attempt history and execution policy. replay first verifies original
artifacts, compares the saved scenario/workload definition with the current
version, then uses the immutable experiment snapshot and saved policy. Editing
the experiment registry does not change a replay. A replay always creates a new
run_id and references the old one; it never overwrites the original. Older runs
without replay metadata or changed definitions are rejected.

Equal plan hashes establish equal synthetic inputs, not identical timing, PIDs,
ports, network conditions or outcomes. Each replay records its current source
SHA. Cross-machine comparability still requires compatible versions and controls.

Exit codes: 0 successful command; 1 failed execution or I/O; 2 invalid input or
unsupported configuration; 130 cancelled execution. Errors expose categories,
not private exception messages.

## Provenance and layout

```text
artifacts/cli/
  experiments/exp-.../experiment.json
  runs/run-.../
    experiment.json   # immutable configuration snapshot for this run
    summary.json      # source, workload, policy, attempts, replay link, observations
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

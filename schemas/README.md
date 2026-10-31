# Experiment and Run contracts v0.1.0

Both schemas use JSON Schema Draft 2020-12. Validate with date-time format
checking enabled (jsonschema FormatChecker plus rfc3339-validator, both included
in the development dependencies). JSON Schema format annotations alone do not
validate timestamps. Unknown fields are rejected, including within nested objects.

Experiment is an input configuration matching the specification's conceptual
manifest, with an explicit schema_version. This initial version accepts only
isolated / synthetic_only scope. Raw PCAP retention is an explicit choice, not a
publication permission; neither schema proves isolation, consent or redaction.

Run describes a terminal execution (succeeded, failed or cancelled), not an
orchestrator's pending/running state. Every record includes UTC timestamps ending
in Z, source revision, tool/platform versions, scenario hash, seed, metrics,
sample size and artifact hashes. A successful run has null failure_reason; a
failed/cancelled run needs a nonblank reason. Failed runs may contain partial
metrics or no artifacts. Zero samples and empty metrics are allowed and must
not later be interpreted as evidence of success by analysis code.

Metrics are quantitative observed/derived values only. Hypotheses and unknown
findings belong in future analysis/report contracts; this schema does not turn
missing measurements into numeric observations.

Artifacts use relative POSIX-style paths, with no absolute paths, drive letters,
backslashes, dot segments or empty segments. Consumers must still resolve paths
inside the artifact root and reject symlink escapes before file access.

Schemas check structure, not cross-record semantics: the runner must later check
that experiment IDs, scenario versions and seeds agree; finish time follows
start time; actual artifact contents match hashes/sizes; repeated artifact paths
or metric names are handled; and the source revision exists and is clean.
The example hashes and revisions are synthetic placeholders, not execution evidence.

Fixtures are in examples/valid and examples/invalid. Files marked invalid contain
intentional errors. Run the contract demo/tests without network traffic:

```sh
uv run --locked pytest tests/unit/test_contracts.py -q
```

Changing required fields or their meaning requires a schema version change.

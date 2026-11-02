# Iran–Turkey transport matrix

The bounded matrix runner compares two pinned SSH nodes sequentially, using the
existing worker and immutable network-run records. Run it from an installed
checkout with `python -m pprl_core.matrix --data-dir artifacts/panel --nodes
iran-1 turkey-1 --capture`. Use `--dry-run` first to inspect all ten plans.
Separate controller identities can be selected with repeated
`--identity NODE=/absolute/path/to/private-key` arguments; key contents are never
included in reports.

The suite runs TCP, UDP, TLS and HTTP/3 in both directions, then verifies explicit
TLS certificate rejection in both directions. It defaults to port 28080, three
samples per positive case, one sample per negative control, and seed 42. Existing
topology validation and worker cleanup remain in effect. Ctrl+C requests
cancellation. Each completed case checkpoints a matrix JSON and SHA-256 sidecar
under `network-matrices/`, referencing the individual network-run hash.

## Observed baseline, 2026-11-02

Tests used the dedicated Iran worker and Turkey worker, with both workers at
commit `40693cba6c151a5d3962ede28965792e63cd382a` and aioquic 1.7.0.

| Transport | Iran → Turkey | Turkey → Iran |
| --- | --- | --- |
| TCP | 3 successful samples | 3 successful samples |
| UDP | 3 successful samples | 3 successful samples |
| TLS | 3 successful samples | 3 successful samples |
| HTTP/3 | handshake timeout | handshake timeout |
| Invalid TLS certificate control | explicit certificate rejection | explicit certificate rejection |

Local evidence is under `artifacts/iran-turkey-2026-11-02`, including individual
run records, captures and qlogs. The first matrix summary incorrectly counted
legacy TCP/UDP observations as zero successes; individual run records retained
the correct results. The runner now accepts their `bytes_echoed` success format
while respecting explicit failures. Original evidence has not been rewritten.

These are small echo probes, not throughput measurements. The HTTP/3 timeouts
do not establish a filtering cause; W04 acceptance remains open. Capture analysis
and independent review are still required before closing that gate.

The Turkey controller uses a dedicated SSH key. Its authorization on Iran is
restricted to source IP `206.1.97.251`, with agent, port and X11 forwarding and
PTY allocation disabled. Existing authorized keys were preserved and backed up.

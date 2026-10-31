# W04 secure network baseline

The cluster protocol selector supports `h3` (QUIC / HTTP3 POST echo, aioquic) and
`tls` (TCP / TLS 1.3 framed JSON echo). Select direct client/backend nodes, a free
port in 28000–28999, repetitions and seed. Optional PCAP uses UDP for h3 and TCP
for TLS. Secure runs capture both client and backend vantage points so an outgoing
Initial and a silent destination can be distinguished. The pre-existing TCP/UDP relay remains available; secure relay topologies
are rejected explicitly in this milestone.

## Operator workflow

1. Update clean controller and worker checkouts with Git fetch/pull only.
2. On each selected node choose **نصب ابزار QUIC**. This installs the locked,
   hash-checked binary-wheel dependency closure into that node's own `.venv`.
   It needs Python 3.12 with `venv` and a system `pip` supporting `--python`.
   No apt, system package replacement, firewall changes or service stops occur.
3. Add a direct topology with QUIC / HTTP3 or TCP / TLS 1.3. Run with or without
   PCAP. Details include per-sample establishment/request/total durations and qlog.
4. To test rejection, select the explicit controlled certificate-failure checkbox
   on a secure topology. It omits the ephemeral trust anchor; verification stays
   enabled. A certificate rejection is expected and remains failed in history. A timeout or
   transport failure does not prove certificate verification was reached.

Fresh worker provisioning uses a new dedicated install directory via SSH clone,
followed by the dependency step above. Existing folders are never bootstrap targets.
Agent capability preflight refuses secure runs when dependencies are unavailable.

## TLS trust and lifecycle

Each server process generates a fresh EC key and one-hour self-signed certificate
with its selected IPv4 SAN. The public certificate travels over pinned SSH to the
controller, then to selected clients as the sole trust anchor. Clients verify
certificate trust and IP identity; no CERT_NONE, persistent TLS key, session tickets,
0-RTT, or resumption. Private keys stay in the server's mode-0700 temporary session
folder with mode-0600 files. Normal exit removes it. Linux processes disable core
dumps; hard OS kill/power loss can leave that private temporary directory for manual
cleanup. Public run reports include neither certificate PEM nor private keys.

Selected IP peers are filtered; QUIC filters before allocating connection state.
QUIC uses address-validation Retry and at most 16 concurrent connection states.
There is no SO_REUSEPORT. An existing listener causes port_in_use; it is not stopped.
Servers stop on SSH stdin EOF or 55-second deadline. Each sample has a four-second
establishment/request deadline; the run retains the existing overall 60-second cap.
Malformed or oversized application frames are rejected. Payloads are <=512 bytes.

## Measurement interpretation

Each sample uses a fresh connection and identical seeded application bytes.
`handshake_ms` is measured from client setup through authenticated establishment;
for TLS it includes TCP establishment, and for QUIC it includes Retry. It is not
pure cryptographic CPU time. `request_ms` covers application echo after establishment.
`rtt_ms` is total operation duration including connection shutdown; it is not ICMP
RTT or one-way latency. Timers use perf_counter on all platforms.

HTTP3 framing and QUIC Retry differ from the TLS framed echo. Same seed, direction,
nodes, port and repetitions provide a controlled small baseline, not a claim of
equivalent wire workloads or proof that one protocol is faster. No load, shaping,
clock synchronization or network loss-rate inference is introduced.

Reports distinguish observed sample success/failure/timeout and Retry counts,
derived means, a tentative hypothesis and unknown one-way latency/loss/load behavior.
Failure observations survive; a failed capture or invalid qlog cannot become success.

## qlog export and reader

aioquic's qlog 0.3 JSON events are projected at creation, before storage/SSH transfer.
The projection retains only packet type, optional packet length and numeric recovery
metrics. HTTP headers/bodies, TLS secrets, tokens, connection IDs, addresses and
raw packet bytes are discarded. Timestamps are relative milliseconds. Each trace
has a hard 2000-event cap, reported in metadata; the controller caps encoded size
at 600 KB and validates the projection again. Export is deliberately incomplete.
Only client vantage is currently collected; no server qlog claim is made.

The reader explicitly supports qlog_version `0.3` with `JSON` format and
projection `netspectra-headers-v1`; it rejects other versions, unexpected keys,
nonfinite/nonmonotonic times and unprojected fields. Unknown formats are not silently
interpreted. Each run checksum binds each qlog SHA256. Authenticated download:
`/api/cluster/runs/<run-id>/qlog/trace-0000`; a modified file fails integrity checking.
Raw qlog exports remain Git-ignored, like runtime PCAP.

## Reproduce from a clean checkout

With uv 0.12.5 and Python 3.12: `uv sync --locked`, then
`uv run --locked pytest tests/integration/test_secure_baseline.py tests/unit/test_qlog.py`.
These are real local TLS/HTTP3 socket tests, including certificate rejection,
exclusive binds, cleanup and a silent UDP endpoint timeout. They are separate from
the actual two-server acceptance in reports/w04/README.md. Regenerate worker hashes
after a lock change with `uv run --locked python scripts/export_worker_requirements.py`.

Implementation references: [aioquic asyncio API](https://aioquic.readthedocs.io/en/latest/asyncio.html),
[HTTP3 API](https://aioquic.readthedocs.io/en/latest/h3.html),
[upstream qlog logger](https://github.com/aiortc/aioquic/blob/main/src/aioquic/quic/logger.py).
The lockfile records the tested version. Formal independent reproduction/review
and the monthly gate remain pending until a reviewer records their own evidence.
